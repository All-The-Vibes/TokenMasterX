"""Closed-family controller tests. All paired outcomes/calls are synthetic fixtures.

No runtime component, provider, Docker or Jev client is executed. Certification
here tests the existing math/state machine, not model quality or useful savings.
"""
from dataclasses import FrozenInstanceError, asdict, fields, replace
import json
import sqlite3

import pytest

from brainspace import optimizer as module
from brainspace.optimizer import (
    EvaluationAttemptFailed, EvaluationAttemptInterrupted, FrozenTrial, Optimizer,
    OptimizerConfig, OptimizerError,
)
from brainspace.request_policy import RequestPolicy, policy_neighbors
from brainspace.runtime_policy import (
    RuntimePolicy, controller_policy_neighbors, controller_policy_sort_key, decode_policy,
)
from test_optimizer import baseline_check, config, pair


# Captured legacy wire and identity before adding the closed-union imports.
LEGACY_JSON = (
    '{"enabled":true,"keep_recent_tool_results":1,"max_input_tokens":null,'
    '"max_output_tokens":null,"max_transforms":4,"max_wire_bytes":null,'
    '"measurement_protocol":"json-utf8-compact-v1","min_tool_chars":1024,'
    '"protected_roles":["system","developer"],'
    '"quality_gate":"external-certification-required","recovery_required":true,'
    '"version":"request-policy-v1"}'
)
LEGACY_ID = "request-policy-v1:417fcc4d57dea8f0d510e82eb3ee15adb393bfb2ae76374492798674bd43a66d"
CONFIG_FIELDS = (
    "measurement", "oracle_id", "workload_id", "model_id", "environment_id", "token_cap",
    "minimum_token_reduction", "alpha", "max_candidates", "max_calls", "calls_per_pair",
    "synthetic_only",
)


def controller(tmp_path, evaluator=pair, **changes):
    return Optimizer(tmp_path / "runtime-policy.sqlite",
                     config=config(synthetic_only=True, **changes), evaluator=evaluator)


def initialize(opt, policy=None):
    return opt.initialize(RuntimePolicy() if policy is None else policy,
                          validator=baseline_check, validation_call_limit=0)


def dump(opt):
    with sqlite3.connect(opt.path) as db:
        return "\n".join(db.iterdump())


def register(opt, policy):
    with sqlite3.connect(opt.path) as db:
        db.execute("INSERT INTO opt_policies VALUES(?,?)", (policy.policy_id, policy.to_json()))


def select(opt, version):
    return opt.deployment_policy(
        expected_version=version, model_id=opt.config.model_id,
        workload_id=opt.config.workload_id, environment_id=opt.config.environment_id,
        measurement=opt.config.measurement,
    )


def test_cached_legacy_baseline_reopens_without_wire_config_or_schema_changes(tmp_path):
    legacy = RequestPolicy.from_json(LEGACY_JSON)
    assert legacy.to_json() == LEGACY_JSON and legacy.policy_id == LEGACY_ID
    opt = controller(tmp_path)
    initialize(opt, legacy)
    with sqlite3.connect(opt.path) as db:
        db.execute("UPDATE opt_policies SET policy_json=? WHERE policy_id=?", (LEGACY_JSON, LEGACY_ID))
        schema = db.execute("SELECT name,sql FROM sqlite_master ORDER BY name").fetchall()
        stored_config = db.execute("SELECT value FROM opt_config").fetchone()[0]
    before = dump(opt)
    reopened = Optimizer.open(opt.path, evaluator=pair)
    assert dump(reopened) == before
    assert reopened.status()["champion"]["policy_id"] == LEGACY_ID
    with sqlite3.connect(opt.path) as db:
        assert db.execute("SELECT name,sql FROM sqlite_master ORDER BY name").fetchall() == schema
        assert db.execute("SELECT policy_json FROM opt_policies").fetchone()[0] == LEGACY_JSON
        assert db.execute("SELECT value FROM opt_config").fetchone()[0] == stored_config
        assert db.execute("SELECT version FROM opt_accounting").fetchone()[0] == 2
    assert json.loads(stored_config) == json.loads(json.dumps(asdict(opt.config)))
    assert tuple(f.name for f in fields(OptimizerConfig)) == CONFIG_FIELDS
    expected = tuple(sorted(policy_neighbors(legacy), key=lambda p: (
        p.min_tool_chars, p.keep_recent_tool_results, -p.max_transforms, p.policy_id)))
    receipt = reopened.preflight_learning(("synthetic-fresh",))
    assert reopened.propose() == expected
    assert receipt["available_candidate_ids"] == tuple(p.policy_id for p in expected)


def test_legacy_public_neighbor_alias_still_drives_preflight_propose_and_freeze(tmp_path, monkeypatch):
    opt = controller(tmp_path)
    baseline = RequestPolicy(enabled=True)
    initialize(opt, baseline)
    chosen = policy_neighbors(baseline)[-1]
    monkeypatch.setattr(module, "policy_neighbors", lambda p: (chosen,))
    assert opt.preflight_learning(("synthetic-fresh",))["available_candidate_ids"] == (chosen.policy_id,)
    assert opt.propose() == (chosen,)
    assert opt.freeze(chosen.policy_id, sample_size=1).candidate == chosen


@pytest.mark.parametrize("backend", ["none", "local", "headroom"])
def test_runtime_dispatch_same_membership_and_no_legacy_enabled_assumption(tmp_path, monkeypatch, backend):
    baseline = RuntimePolicy()
    if backend != "none":
        baseline = next(p for p in controller_policy_neighbors(baseline) if p.backend == backend)
    opt = controller(tmp_path, max_candidates=12)
    initialize(opt, baseline)
    assert not hasattr(baseline, "enabled")
    monkeypatch.setattr(module, "policy_neighbors",
                        lambda p: pytest.fail("runtime family must use its own neighbor helper"))
    expected = tuple(sorted(controller_policy_neighbors(baseline), key=controller_policy_sort_key))
    before = dump(opt)
    receipt = opt.preflight_learning(("synthetic-fresh",), screening=True)
    assert dump(opt) == before and receipt["reservation"] is False
    assert receipt["available_candidate_ids"] == tuple(p.policy_id for p in expected)
    assert receipt["required_call_slots"] == 3
    assert opt.propose() == expected
    for candidate in expected:
        trial = opt.freeze(candidate.policy_id, sample_size=1)
        assert type(trial.incumbent) is type(trial.candidate) is RuntimePolicy
        assert trial.candidate == decode_policy(candidate.to_json())
        with pytest.raises(FrozenInstanceError):
            trial.candidate.backend = "local"
        opt.cancel(trial.trial_id)
    assert opt.status()["champion"]["policy_id"] == baseline.policy_id
    assert opt.status()["calls_budget_spent"] == 2 * len(expected)


def test_runtime_true_off_complete_pair_explicit_promotion_restart_and_rollback(tmp_path):
    opt = controller(tmp_path)
    baseline = RuntimePolicy()
    initialize(opt, baseline)
    candidate = opt.propose()[0]
    trial = opt.freeze(candidate.policy_id, sample_size=100)
    certificate = opt.evaluate(trial.trial_id, [f"synthetic-{i}" for i in range(100)])
    assert certificate.decision == "certified"
    assert opt.status()["synthetic_only"] is True
    assert opt.status()["champion"]["policy_id"] == baseline.policy_id  # No auto-promotion.
    reopened = Optimizer.open(opt.path, evaluator=pair)
    promoted = reopened.promote(trial.trial_id)
    assert promoted["champion"]["policy_id"] == candidate.policy_id
    rolled = Optimizer.open(opt.path).rollback(expected_version=2)
    assert rolled["champion"]["policy_id"] == baseline.policy_id
    assert rolled["champion"]["policy"]["backend"] == "none"
    assert [h["action"] for h in rolled["history"]] == ["initialize", "promote", "rollback"]
    assert rolled["learning"]["complete_calls"] == 200
    assert rolled["learning"]["reference_tokens"] == 10000
    assert rolled["calls_budget_spent"] == 200
    with pytest.raises(OptimizerError, match="synthetic_deployment_forbidden"):
        select(reopened, 3)
    with pytest.raises(OptimizerError):
        reopened.evaluate(trial.trial_id, [f"synthetic-{i}" for i in range(100)])


def test_runtime_equal_quality_remains_uncertified_and_unpromoted(tmp_path):
    opt = controller(tmp_path, evaluator=lambda t, task: pair(t, task, equal=True))
    initialize(opt)
    trial = opt.freeze(opt.propose()[0].policy_id, sample_size=100)
    assert opt.evaluate(trial.trial_id, [f"synthetic-equal-{i}" for i in range(100)]).decision == "not_certified"
    with pytest.raises(OptimizerError):
        opt.promote(trial.trial_id)
    assert opt.status()["champion"]["version"] == 1


def test_non_synthetic_empty_safety_admission_selects_true_off_without_model_quality_claim(tmp_path):
    # No paired synthetic/model evidence: deterministic, complete empty admission only.
    opt = Optimizer(tmp_path / "admission.sqlite", config=config(synthetic_only=False))
    initialize(opt)
    before = dump(opt)
    assert select(opt, 1) == RuntimePolicy()
    assert dump(opt) == before
    assert opt.status()["learning"]["complete_calls"] == 0


@pytest.mark.parametrize("runtime_incumbent", [False, True])
def test_registered_cross_family_candidate_is_rejected_before_spending(tmp_path, runtime_incumbent):
    opt = controller(tmp_path)
    baseline = RuntimePolicy() if runtime_incumbent else RequestPolicy(enabled=True)
    foreign = RequestPolicy(enabled=True) if runtime_incumbent else RuntimePolicy()
    initialize(opt, baseline)
    register(opt, foreign)
    before = dump(opt)
    with pytest.raises(OptimizerError, match="policy_family_mismatch"):
        opt.freeze(foreign.policy_id, sample_size=1)
    assert dump(opt) == before


def test_same_family_registered_non_neighbor_cannot_freeze(tmp_path):
    opt = controller(tmp_path)
    initialize(opt)
    distant = RuntimePolicy(backend="headroom", headroom_time_budget_seconds=60)
    register(opt, distant)
    before = dump(opt)
    assert distant.policy_id not in opt.preflight_learning(("synthetic-fresh",))["available_candidate_ids"]
    assert distant not in opt.propose()
    after_proposals = dump(opt)
    assert after_proposals != before  # Propose may register real neighbors, not a trial.
    with pytest.raises(OptimizerError, match="not_current_neighbor"):
        opt.freeze(distant.policy_id, sample_size=1)
    assert dump(opt) == after_proposals


def test_cross_family_neighbor_injection_fails_at_all_admission_paths(tmp_path, monkeypatch):
    opt = controller(tmp_path)
    initialize(opt)
    real = opt.propose()[0]
    monkeypatch.setattr(module, "controller_policy_neighbors",
                        lambda p: (RequestPolicy(enabled=True),))
    before = dump(opt)
    for operation in (
        lambda: opt.preflight_learning(("synthetic-fresh",)),
        opt.propose, lambda: opt.freeze(real.policy_id, sample_size=1),
    ):
        with pytest.raises(OptimizerError, match="policy_family_mismatch"):
            operation()
        assert dump(opt) == before


def test_frozen_trial_rejects_cross_family_directly_and_from_registry(tmp_path):
    opt = controller(tmp_path)
    initialize(opt)
    trial = opt.freeze(opt.propose()[0].policy_id, sample_size=1)
    foreign = RequestPolicy(enabled=True)
    with pytest.raises(OptimizerError, match="policy_family_mismatch"):
        replace(trial, candidate=foreign)
    assert isinstance(trial, FrozenTrial)
    register(opt, foreign)
    with sqlite3.connect(opt.path) as db:
        db.execute("UPDATE opt_trials SET candidate_id=? WHERE id=?", (foreign.policy_id, trial.trial_id))
    before = dump(opt)
    with pytest.raises(OptimizerError, match="policy_family_mismatch"):
        opt.evaluate(trial.trial_id, ("synthetic-never-executed",))
    assert dump(opt) == before


@pytest.mark.parametrize("field", ["policy_id", "previous_id"])
def test_cross_family_history_rejects_status_preflight_propose_and_rollback(tmp_path, field):
    opt = controller(tmp_path)
    initialize(opt)
    real = opt.propose()[0]
    foreign = RequestPolicy(enabled=True)
    register(opt, foreign)
    with sqlite3.connect(opt.path) as db:
        # Include an inactive history entry: it must not escape the family boundary.
        values = dict(policy_id=RuntimePolicy().policy_id, previous_id=RuntimePolicy().policy_id)
        values[field] = foreign.policy_id
        db.execute("INSERT INTO opt_history(action,policy_id,previous_id,parent_seq) VALUES('rollback',?,?,1)",
                   (values["policy_id"], values["previous_id"]))
    before = dump(opt)
    for operation in (opt.status, opt.propose, lambda: opt.preflight_learning(("synthetic-fresh",)),
                      lambda: opt.freeze(real.policy_id, sample_size=1),
                      lambda: opt.rollback(expected_version=1)):
        with pytest.raises(OptimizerError, match="policy_family_mismatch"):
            operation()
        assert dump(opt) == before


@pytest.mark.parametrize("corruption", ["wrong_json", "unknown_version", "wrong_pin", "duplicate"])
def test_runtime_stored_policy_corruption_rejected_on_restart(tmp_path, corruption):
    opt = controller(tmp_path)
    initialize(opt)
    policy = RuntimePolicy()
    data = policy.to_dict()
    if corruption == "unknown_version":
        data["version"] = "runtime-policy-v999"
    elif corruption == "wrong_pin":
        data["headroom_source_commit"] = "0" * 40
    wire = json.dumps(data)
    if corruption == "wrong_json":
        wire = RequestPolicy(enabled=True).to_json()
    elif corruption == "duplicate":
        wire = '{"version":"runtime-policy-v1",' + policy.to_json()[1:]
    with sqlite3.connect(opt.path) as db:
        db.execute("UPDATE opt_policies SET policy_json=?", (wire,))
    reopened = Optimizer.open(opt.path)
    before = dump(reopened)
    with pytest.raises(OptimizerError, match="policy_identity_mismatch"):
        reopened.status()
    assert dump(reopened) == before


@pytest.mark.parametrize("carrier,expected", [
    (EvaluationAttemptFailed, OptimizerError), (EvaluationAttemptInterrupted, KeyboardInterrupt),
])
def test_runtime_partial_failures_keep_exposed_calls_and_unknown_totals(tmp_path, carrier, expected):
    def fail(trial, task):
        observation = pair(trial, task)
        candidate = replace(observation.candidate, calls=(), coverage="partial",
                            missing_or_opaque_components=("unmeasured",))
        raise carrier(traces=(observation.incumbent, candidate),
                      reason="transport_incomplete", receipt_sha256s=("a" * 64,))
    opt = controller(tmp_path, evaluator=fail)
    initialize(opt)
    trial = opt.freeze(opt.propose()[0].policy_id, sample_size=1)
    with pytest.raises(expected):
        opt.evaluate(trial.trial_id, ("synthetic-failed",))
    status = Optimizer.open(opt.path).status()
    assert status["learning"]["known_partial_reference_tokens"] == 90
    assert status["learning"]["reference_tokens"] is None
    assert status["learning"]["unresolved_evaluation_attempts"] == 1
    assert status["calls_budget_spent"] == 2 and status["champion"]["version"] == 1
    with sqlite3.connect(opt.path) as db:
        assert db.execute("SELECT COUNT(*) FROM opt_call_ids").fetchone()[0] == 2
    with pytest.raises(OptimizerError, match="task_already_consumed"):
        opt.preflight_learning(("synthetic-failed",))
