"""Task-start selection is pinned, evidence-backed and strictly read-only."""
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
import json
import shutil
import sqlite3

import pytest

from brainspace.jev import Diagnostics, Result
from brainspace.optimizer import OptimizerError
from brainspace.request_policy import RequestPolicy
from test_optimizer import controller, evaluate, freeze, initialize, model_baseline


def select(opt, version=1, **changes):
    args = dict(expected_version=version, measurement=opt.config.measurement,
                model_id=opt.config.model_id, workload_id=opt.config.workload_id,
                environment_id=opt.config.environment_id)
    return opt.deployment_policy(**{**args, **changes})


def dump(opt):
    with sqlite3.connect(opt.path) as db:
        return "\n".join(db.iterdump())


def mutate(opt, sql, params=()):
    with sqlite3.connect(opt.path) as db:
        db.execute(sql, params)


@pytest.fixture(scope="module")
def promotion_fixture(tmp_path_factory):
    """One real offline confirmation, copied only for isolated corruption tests."""
    opt = controller(tmp_path_factory.mktemp("deployment-confirmation"))
    initialize(opt)
    trial = freeze(opt)
    evaluate(opt, trial)
    opt.promote(trial.trial_id)
    return opt.path, trial


@pytest.fixture
def promoted(tmp_path, promotion_fixture):
    path, trial = promotion_fixture
    shutil.copyfile(path, tmp_path / "optimizer.sqlite")
    return controller(tmp_path), trial


def test_selection_is_frozen_one_transaction_and_no_writes(tmp_path, monkeypatch):
    opt = controller(tmp_path)
    initialize(opt)
    before, statements = dump(opt), []
    before_bytes = opt.path.read_bytes()
    original = opt._transaction
    transactions = []

    @contextmanager
    def counted():
        transactions.append(True)
        with original() as db:
            db.set_trace_callback(statements.append)
            yield db

    monkeypatch.setattr(opt, "_transaction", counted)
    monkeypatch.setattr(opt, "status", lambda: pytest.fail("must not trust status"))
    monkeypatch.setattr(opt, "_evaluator", lambda *a: pytest.fail("no evaluator"))
    policy = select(opt)
    assert policy == RequestPolicy(enabled=True)
    with pytest.raises(FrozenInstanceError):
        policy.enabled = False
    assert len(transactions) == 1
    assert dump(opt) == before
    assert opt.path.read_bytes() == before_bytes
    assert all(s.split()[0].upper() in {"SELECT", "COMMIT"} for s in statements)


@pytest.mark.parametrize("change", [
    {"expected_version": 0}, {"expected_version": True}, {"expected_version": 2},
    {"model_id": "wrong"}, {"workload_id": "wrong"}, {"environment_id": "wrong"},
    {"measurement": None},
])
def test_mismatched_regime_or_version_rejected_without_mutation(tmp_path, change):
    opt = controller(tmp_path)
    initialize(opt)
    before = dump(opt)
    with pytest.raises(OptimizerError):
        select(opt, **change)
    assert dump(opt) == before


def test_different_measurement_and_synthetic_rejected(tmp_path):
    opt = controller(tmp_path, synthetic_only=True)
    initialize(opt)
    with pytest.raises(OptimizerError, match="synthetic"):
        select(opt)
    (tmp_path / "other").mkdir()
    other = controller(tmp_path / "other")
    initialize(other)
    with pytest.raises(OptimizerError):
        select(other, measurement=replace(other.config.measurement, extraction_protocol_version="other"))


def test_missing_validation_and_jev_only_proposal_are_not_deployable(tmp_path):
    opt = controller(tmp_path)
    with pytest.raises(OptimizerError):
        select(opt)
    initialize(opt)
    candidate = opt.propose()[0]  # Advisory proposals have no independent certificate.
    mutate(opt, "UPDATE opt_champion SET policy_id=?", (candidate.policy_id,))
    with pytest.raises(OptimizerError):
        select(opt)
    mutate(opt, "UPDATE opt_champion SET policy_id=?,validated_seq=999",
           (RequestPolicy(enabled=True).policy_id,))
    with pytest.raises(OptimizerError):
        select(opt)


def test_jev_advice_never_replaces_validated_champion(tmp_path):
    opt = controller(tmp_path)
    initialize(opt)
    candidates = opt.propose()

    class Screener:
        def decide(self, state, questions, **kwargs):
            choice = candidates[-1].policy_id
            body = {"model": "jev-1.13.0", "usage": {"input_tokens": 1, "output_tokens": 1},
                    "answers": {"proposal": {"type": "choice", "choice": choice, "confidence": 1,
                        "probabilities": {k: int(k == choice)
                                          for k in questions["proposal"]["criteria"]}}}}
            return Result(True, "ok", "fixture", json.dumps(body), body,
                          Diagnostics(attempts=1, response_complete=True))

    proposed = opt.propose(screener=Screener(), summaries={p.policy_id: "fixture" for p in candidates},
                           data_classification="synthetic")
    assert proposed[0] == candidates[-1]
    before = dump(opt)
    assert select(opt) == RequestPolicy(enabled=True)
    assert dump(opt) == before
    mutate(opt, "UPDATE opt_champion SET policy_id=?", (proposed[0].policy_id,))
    with pytest.raises(OptimizerError):
        select(opt)


@pytest.mark.parametrize("sql", [
    "UPDATE opt_history SET validation_json='{}'",
    "UPDATE opt_history SET validation_json=NULL",
    "UPDATE opt_history SET parent_seq=seq",
    "UPDATE opt_history SET previous_id='foreign'",
    "UPDATE opt_baseline_attempts SET state='rejected'",
    "UPDATE opt_baseline_attempts SET policy_id='foreign'",
    "UPDATE opt_learning_runs SET state='pending'",
    "UPDATE opt_learning_runs SET expected_tasks_json='[]'",
    "UPDATE opt_learning SET records_json='{}'",
    "UPDATE opt_learning SET state='pending'",
    "UPDATE opt_policies SET policy_json='{}'",
    "DELETE FROM opt_history",
    "DELETE FROM tasks",
    "UPDATE opt_champion SET validated_seq=999",
])
def test_baseline_forgery_rejected(tmp_path, sql):
    opt = controller(tmp_path)
    initialize(opt)
    mutate(opt, sql)
    before = dump(opt)
    with pytest.raises(OptimizerError):
        select(opt)
    assert dump(opt) == before


def test_baseline_trace_call_ownership_rechecked(tmp_path):
    opt = controller(tmp_path)
    opt.initialize(RequestPolicy(enabled=True), validator=model_baseline, validation_call_limit=1)
    assert select(opt).enabled
    mutate(opt, "UPDATE opt_call_ids SET event_id='foreign'")
    with pytest.raises(OptimizerError):
        select(opt)


def test_successful_promotion_rollback_and_task_frozen_copy(promoted):
    opt, trial = promoted
    before = dump(opt)
    selected = select(opt, 2)
    assert selected == trial.candidate
    assert dump(opt) == before
    opt.rollback(expected_version=2)
    before = dump(opt)
    assert select(opt, 3) == RequestPolicy(enabled=True)
    assert selected == trial.candidate
    assert dump(opt) == before
    with pytest.raises(OptimizerError):
        select(opt, 2)


def test_rollback_to_promoted_ancestor_uses_validated_seq_not_latest_history(promoted):
    opt, first = promoted
    second = freeze(opt)
    evaluate(opt, second, "second")
    opt.promote(second.trial_id)
    assert select(opt, 3) == second.candidate
    opt.rollback(expected_version=3)
    before = dump(opt)
    assert select(opt, 4) == first.candidate
    assert dump(opt) == before
    mutate(opt, "UPDATE opt_history SET validation_json='{}' WHERE action='initialize'")
    with pytest.raises(OptimizerError):
        select(opt, 4)


@pytest.mark.parametrize("sql", [
    "DELETE FROM looks",
    "UPDATE looks SET certificate='{}'",
    "UPDATE looks SET n=n+1",
    "UPDATE opt_history SET previous_id='foreign' WHERE action='promote'",
    "UPDATE opt_history SET parent_seq=seq WHERE action='promote'",
    "UPDATE opt_history SET validation_json='{}' WHERE action='initialize'",
    "UPDATE opt_trials SET state='certified'",
    "UPDATE opt_trials SET incumbent_version=999",
    "DELETE FROM observations",
    "UPDATE observations SET evidence_hash='forged'",
    "DELETE FROM calls",
    "UPDATE opt_call_ids SET event_id='foreign' WHERE event_id LIKE 'trial-%'",
    "UPDATE opt_learning SET records_json='{}' WHERE kind='confirmation'",
    "UPDATE opt_learning_runs SET state='pending' WHERE kind='confirmation'",
])
def test_promoted_lineage_evidence_and_ownership_rechecked(promoted, sql):
    opt, _ = promoted
    mutate(opt, sql)
    before = dump(opt)
    with pytest.raises(OptimizerError):
        select(opt, 2)
    assert dump(opt) == before


@pytest.mark.parametrize("field,value", [
    ("evidence_sha256", "f" * 64), ("task_set_sha256", "f" * 64),
    ("radius", 0), ("alpha_total", 0.99), ("schema_version", 999),
    ("mean_quality_difference", 99), ("quality_difference_lower", 99),
])
def test_plausibly_passing_forged_certificate_rejected(promoted, field, value):
    opt, _ = promoted
    with sqlite3.connect(opt.path) as db:
        cert = json.loads(db.execute("SELECT certificate FROM looks").fetchone()[0])
    cert[field] = value
    mutate(opt, "UPDATE looks SET certificate=?", (json.dumps(cert),))
    with pytest.raises(OptimizerError):
        select(opt, 2)


def test_forged_current_version_rejected(tmp_path):
    opt = controller(tmp_path)
    initialize(opt)
    mutate(opt, "UPDATE opt_champion SET version=99")
    with pytest.raises(OptimizerError):
        select(opt, 99)
