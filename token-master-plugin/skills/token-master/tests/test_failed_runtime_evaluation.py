"""Failed runtime work remains owned and known costs never become a certificate."""
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import sqlite3

import pytest

from brainspace.optimizer import EvaluationAttemptFailed, EvaluationAttemptInterrupted, OptimizerError
from brainspace.request_policy import RequestPolicy
from brainspace.token_ledger import DeploymentHorizon, TokenLedger
from test_optimizer import controller, evaluate, freeze, initialize, model_baseline, pair


RECEIPTS = ("a" * 64, "b" * 64)


def partial_pair(trial, task, *, measured_candidate=True):
    obs = pair(trial, task)
    pending = f"{task}:unmeasured"
    candidate = replace(
        obs.candidate, calls=obs.candidate.calls if measured_candidate else (),
        expected_call_ids=(*((obs.candidate.calls[0].call_id,) if measured_candidate else ()), pending),
        coverage="partial", missing_or_opaque_components=(pending,),
    )
    return obs.incumbent, candidate


def owner(opt, call_id):
    with sqlite3.connect(opt.path) as db:
        return db.execute("SELECT event_id FROM opt_call_ids WHERE call_hash=?",
                          (hashlib.sha256(call_id.encode()).hexdigest(),)).fetchone()


@pytest.mark.parametrize("carrier,state", [
    (EvaluationAttemptFailed, "failed"), (EvaluationAttemptInterrupted, "cancelled"),
])
@pytest.mark.parametrize("measured_candidate,known,calls", [(True, 100, 2), (False, 90, 1)])
def test_failed_pair_retains_known_partial_costs_but_no_outcome_or_complete_trace(
    tmp_path, carrier, state, measured_candidate, known, calls,
):
    def evaluator(trial, task):
        raise carrier(traces=partial_pair(trial, task, measured_candidate=measured_candidate),
                      reason="transport_incomplete", receipt_sha256s=RECEIPTS)

    opt = controller(tmp_path, evaluator, calls_per_pair=4)
    initialize(opt)
    trial = freeze(opt, n=1)
    with pytest.raises(KeyboardInterrupt if carrier is EvaluationAttemptInterrupted else OptimizerError):
        evaluate(opt, trial)
    status = opt.status()
    learning = status["learning"]
    assert status["trials"][0]["state"] == state
    assert status["calls_budget_spent"] == 4
    assert learning["reference_tokens"] is None
    assert learning["known_reference_tokens"] == known
    assert learning["known_partial_reference_tokens"] == known
    assert learning["known_partial_calls"] == calls
    assert learning["complete_calls"] == learning["unique_complete_calls"] == 0
    assert learning["unresolved_evaluation_attempts"] == 1
    record = learning["failed_evaluations"][0]
    assert record["counts_trusted"] is True
    assert record["receipt_sha256s"] == list(RECEIPTS)
    assert record["reason"] == "transport_incomplete"
    assert len(record["traces"]) == 2
    assert record["complete_arm_policy_ids"] == [trial.incumbent.policy_id]
    assert len(record["unresolved_call_hashes"]) == 1
    assert "success" not in record and "outcome" not in record
    inventory = opt.learning_inventory()
    assert inventory["failed_evaluations"] == learning["failed_evaluations"]
    assert inventory["known_partial_reference_tokens"] == known
    assert len(inventory["traces"]) == 1  # Only the explicit empty baseline trace.
    assert inventory["traces"][0].calls == ()
    assert owner(opt, "fresh-0:unmeasured") == (f"trial-{trial.trial_id}:fresh-0",)
    for trace in partial_pair(trial, "fresh-0", measured_candidate=measured_candidate):
        for call in trace.calls:
            assert owner(opt, call.call_id) == (f"trial-{trial.trial_id}:fresh-0",)
    with sqlite3.connect(opt.path) as db:
        row = db.execute("SELECT coverage,records_json,diagnostics_json FROM opt_learning "
                         "WHERE trial_id=?", (trial.trial_id,)).fetchone()
        assert row[0] == "unknown" and row[1] is None and row[2]
        assert db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM looks").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM tasks WHERE round_id=?", (trial.round_id,)).fetchone()[0] == 1
    for operation in (lambda: opt.promote(trial.trial_id),
                      lambda: opt.seal_learning_run(trial.learning_run_id),
                      lambda: evaluate(opt, trial)):
        with pytest.raises(OptimizerError):
            operation()
    reopened = controller(tmp_path, calls_per_pair=4)
    assert reopened.status() == status
    assert reopened.learning_inventory() == inventory
    assert reopened.cancel(trial.trial_id) == status
    ledger = TokenLedger(opt.config.measurement, horizon=DeploymentHorizon(
        "failed-runtime-horizon", ("future-deployment",),
        tuple(r["run_id"] for r in inventory["runs"])))
    opt.export_learning(ledger)
    assert ledger.summary()["all_in"]["status"] == "incomplete_horizon"
    assert trial.learning_run_id in ledger.summary()["all_in"]["unsealed_learning_runs"]
    assert ledger.summary()["all_in"]["tokens_per_verified_success"] is None
    assert opt.status() == status  # Export doesn't reclassify/count partial arms.


@pytest.mark.parametrize("only_incumbent", [True, False])
def test_known_complete_arms_remain_unsealable_when_execution_or_oracle_raises(tmp_path, only_incumbent):
    def evaluator(trial, task):
        obs = pair(trial, task)
        traces = (obs.incumbent,) if only_incumbent else (obs.incumbent, obs.candidate)
        raise EvaluationAttemptFailed(traces=traces, reason="oracle_failed", receipt_sha256s=RECEIPTS)

    opt = controller(tmp_path, evaluator)
    initialize(opt)
    trial = freeze(opt, n=1)
    with pytest.raises(OptimizerError):
        evaluate(opt, trial)
    data = opt.status()["learning"]
    assert data["known_partial_reference_tokens"] == (90 if only_incumbent else 100)
    assert data["reference_tokens"] is None and data["complete_calls"] == 0
    assert data["failed_evaluations"][0]["missing_arm_policy_ids"] == (
        [trial.candidate.policy_id] if only_incumbent else [])


def test_unmeasured_exposed_id_cannot_be_reused_by_later_confirmation(tmp_path):
    def evaluator(trial, task):
        if task.startswith("first"):
            raise EvaluationAttemptFailed(traces=partial_pair(trial, task), receipt_sha256s=RECEIPTS)
        obs = pair(trial, task)
        call = replace(obs.incumbent.calls[0], call_id="first-0:unmeasured")
        return replace(obs, incumbent=replace(obs.incumbent, calls=(call,), expected_call_ids=(call.call_id,)))

    opt = controller(tmp_path, evaluator, calls_per_pair=4)
    initialize(opt)
    first = freeze(opt, n=1)
    with pytest.raises(OptimizerError):
        evaluate(opt, first, "first")
    reopened = controller(tmp_path, evaluator, calls_per_pair=4)
    second = freeze(reopened, n=1)
    with pytest.raises(OptimizerError):
        evaluate(reopened, second, "second")
    assert owner(reopened, "first-0:unmeasured") == (f"trial-{first.trial_id}:first-0",)
    assert reopened.status()["learning"]["known_partial_reference_tokens"] == 100
    assert reopened.status()["champion"]["version"] == 1


@pytest.mark.parametrize("defect", [
    "task", "policy", "run", "phase", "measurement", "model", "call_task", "call_measurement",
    "missing_hash", "duplicate_expected", "duplicate_call", "unlisted_observed", "duplicate_arm",
    "negative_count", "cycle", "mutated_trial", "receipt", "recursive_metadata",
])
def test_invalid_metadata_never_accepts_totals_but_every_exposed_id_stays_spent(tmp_path, defect):
    seen = []

    def evaluator(trial, task):
        a, b = partial_pair(trial, task)
        call = b.calls[0]
        if defect == "task":
            b = replace(b, task_id="foreign")
        elif defect == "policy":
            b = replace(b, policy_id="foreign")
        elif defect == "run":
            b = replace(b, learning_run_id="foreign")
        elif defect == "phase":
            b = replace(b, phase="deployment", learning_run_id=None)
        elif defect == "measurement":
            b = replace(b, measurement=replace(b.measurement, extraction_protocol_version="foreign"))
        elif defect in ("model", "call_task", "call_measurement", "missing_hash"):
            field, value = {"model": ("model_id", "foreign"), "call_task": ("task_id", "foreign"),
                            "call_measurement": ("measurement_id", "foreign"),
                            "missing_hash": ("output_sha256", None)}[defect]
            b = replace(b, calls=(replace(call, **{field: value}),))
        elif defect == "duplicate_expected":
            b = replace(b, expected_call_ids=b.expected_call_ids + b.expected_call_ids)
        elif defect == "duplicate_call":
            b = replace(b, calls=(call, call))
        elif defect == "unlisted_observed":
            b = replace(b, expected_call_ids=("fresh-0:unmeasured",))
        elif defect == "duplicate_arm":
            b = replace(b, policy_id=a.policy_id)
        elif defect == "negative_count":
            object.__setattr__(call, "reference_input_tokens", -1)
        elif defect == "cycle":
            b = replace(b, calls=(replace(call, parent_call_id=call.call_id),))
        elif defect == "mutated_trial":
            object.__setattr__(trial.candidate, "min_tool_chars", 12345)
        elif defect == "recursive_metadata":
            object.__setattr__(call, "model_id", call)
        seen.extend([c.call_id for t in (a, b) for c in t.calls])
        seen.extend([cid for t in (a, b) for cid in t.expected_call_ids])
        raise EvaluationAttemptFailed(
            traces=(a, b), reason="SECRET_DO_NOT_PERSIST",
            receipt_sha256s=("bad",) if defect == "receipt" else RECEIPTS)

    opt = controller(tmp_path, evaluator, calls_per_pair=4)
    initialize(opt)
    trial = freeze(opt, n=1)
    with pytest.raises(OptimizerError):
        evaluate(opt, trial)
    status = opt.status()
    data = status["learning"]
    assert data["known_partial_reference_tokens"] == data["known_reference_tokens"] == 0
    assert data["reference_tokens"] is None and data["complete_calls"] == 0
    record = data["failed_evaluations"][0]
    assert record["counts_trusted"] is False and record["known_reference_tokens"] is None
    assert record["reported_trace_sha256s"]
    assert len(record["traces"]) == 2  # Untrusted metadata is retained, not turned into totals.
    assert record["traces"][0]["policy_id"] == trial.incumbent.policy_id
    assert "SECRET_DO_NOT_PERSIST" not in json.dumps(status)
    assert b"SECRET_DO_NOT_PERSIST" not in opt.path.read_bytes()
    for cid in set(seen):
        assert owner(opt, cid) == (f"trial-{trial.trial_id}:fresh-0",)


@pytest.mark.parametrize("reverse", [False, True])
def test_collision_does_not_double_count_or_resurrect_fresh_expected_siblings(tmp_path, reverse):
    def evaluator(trial, task):
        a, b = partial_pair(trial, task)
        call = replace(a.calls[0], call_id="baseline-owned")
        a = replace(a, calls=(call,), expected_call_ids=(call.call_id, "new-a"))
        a = replace(a, coverage="partial")
        traces = (b, a) if reverse else (a, b)
        raise EvaluationAttemptFailed(traces=traces, receipt_sha256s=RECEIPTS)

    opt = controller(tmp_path, evaluator, calls_per_pair=5)
    opt.initialize(RequestPolicy(enabled=True), validation_call_limit=1,
                   validator=lambda p, c, r: model_baseline(p, c, r, call_id="baseline-owned"))
    baseline_owner = owner(opt, "baseline-owned")
    baseline_cost = opt.status()["learning"]["known_reference_tokens"]
    trial = freeze(opt, n=1)
    with pytest.raises(OptimizerError):
        evaluate(opt, trial)
    data = opt.status()["learning"]
    assert data["known_reference_tokens"] == baseline_cost
    assert data["known_partial_reference_tokens"] == 0
    assert owner(opt, "baseline-owned") == baseline_owner
    for cid in ("new-a", "fresh-0:unmeasured"):
        assert owner(opt, cid) == (f"trial-{trial.trial_id}:fresh-0",)


def test_successful_pair_then_partial_pair_counts_each_call_once(tmp_path):
    def evaluator(trial, task):
        if task.endswith("-0"):
            return pair(trial, task)
        raise EvaluationAttemptFailed(traces=partial_pair(trial, task), receipt_sha256s=RECEIPTS)

    opt = controller(tmp_path, evaluator, calls_per_pair=4)
    initialize(opt)
    trial = freeze(opt, n=2)
    with pytest.raises(OptimizerError):
        evaluate(opt, trial)
    data = opt.status()["learning"]
    assert data["complete_calls"] == 2
    assert data["known_partial_calls"] == 2
    assert data["known_reference_tokens"] == 200
    assert data["known_partial_reference_tokens"] == 100
    assert data["reference_tokens"] is None and data["unsealed_runs"] == 1
    assert len(opt.learning_inventory()["traces"]) == 2  # Baseline + accepted combined pair.
    assert len(opt.learning_inventory()["failed_evaluations"]) == 1
    assert controller(tmp_path, calls_per_pair=4).status()["learning"] == data


@pytest.mark.parametrize("completion_status", ["failed", "cancelled"])
def test_fully_captured_failed_calls_are_still_known_costs(tmp_path, completion_status):
    def evaluator(trial, task):
        a, b = partial_pair(trial, task)
        b = replace(b, calls=(replace(b.calls[0], completion_status=completion_status),))
        raise EvaluationAttemptFailed(traces=(a, b), receipt_sha256s=RECEIPTS)

    opt = controller(tmp_path, evaluator, calls_per_pair=4)
    initialize(opt)
    trial = freeze(opt, n=1)
    with pytest.raises(OptimizerError):
        evaluate(opt, trial)
    learning = opt.status()["learning"]
    assert learning["known_partial_reference_tokens"] == 100
    assert learning["reference_tokens"] is None
    assert learning["failed_evaluations"][0]["traces"][1]["calls"][0]["completion_status"] == completion_status


def test_partial_call_record_is_retained_but_not_invented_as_a_complete_measurement(tmp_path):
    def evaluator(trial, task):
        a, b = partial_pair(trial, task)
        b = replace(b, calls=(replace(b.calls[0], coverage="partial", output_sha256=None),))
        raise EvaluationAttemptFailed(traces=(a, b), receipt_sha256s=RECEIPTS)

    opt = controller(tmp_path, evaluator, calls_per_pair=4)
    initialize(opt)
    trial = freeze(opt, n=1)
    with pytest.raises(OptimizerError):
        evaluate(opt, trial)
    learning = opt.status()["learning"]
    assert learning["known_partial_reference_tokens"] == 90
    assert learning["known_partial_calls"] == 1
    saved = learning["failed_evaluations"][0]
    assert saved["traces"][1]["calls"][0]["coverage"] == "partial"
    assert saved["traces"][1]["calls"][0]["output_sha256"] is None
    assert len(saved["unresolved_call_hashes"]) == 2


def test_invalid_interrupted_attempt_still_cancels_and_burns_exposed_ids(tmp_path):
    def evaluator(trial, task):
        raise EvaluationAttemptInterrupted(traces=partial_pair(trial, task), receipt_sha256s=("invalid",))

    opt = controller(tmp_path, evaluator, calls_per_pair=4)
    initialize(opt)
    trial = freeze(opt, n=1)
    with pytest.raises(EvaluationAttemptInterrupted):
        evaluate(opt, trial)
    assert opt.status()["trials"][0]["state"] == "cancelled"
    assert opt.status()["learning"]["known_partial_reference_tokens"] == 0
    assert owner(opt, "fresh-0:unmeasured") == (f"trial-{trial.trial_id}:fresh-0",)


@pytest.mark.parametrize("error", [RuntimeError("do not persist"), KeyboardInterrupt()])
def test_plain_failures_remain_unknown_without_invented_partial_evidence(tmp_path, error):
    def evaluator(*_):
        raise error

    opt = controller(tmp_path, evaluator)
    initialize(opt)
    trial = freeze(opt, n=1)
    with pytest.raises(KeyboardInterrupt if isinstance(error, KeyboardInterrupt) else OptimizerError):
        evaluate(opt, trial)
    learning = opt.status()["learning"]
    assert learning["reference_tokens"] is None
    assert learning["failed_evaluations"] == []
    assert learning["known_partial_reference_tokens"] == 0


@pytest.mark.parametrize("carrier", [EvaluationAttemptFailed, EvaluationAttemptInterrupted])
def test_carriers_detach_immutable_payloads_and_sanitize_reason(tmp_path, carrier):
    opt = controller(tmp_path)
    initialize(opt)
    trial = freeze(opt, n=1)
    traces = list(partial_pair(trial, "fresh"))
    error = carrier(traces=traces, reason="private exception details", receipt_sha256s=list(RECEIPTS))
    object.__setattr__(traces[0], "task_id", "later-mutation")
    traces.clear()
    assert type(error.traces) is tuple and error.traces[0].task_id == "fresh"
    assert error.receipt_sha256s == RECEIPTS
    assert "private exception details" not in str(error)
    with pytest.raises(AttributeError):
        error.traces = ()
    with pytest.raises(FrozenInstanceError):
        error.traces[0].phase = "deployment"
    with pytest.raises(carrier):
        raise error
    with pytest.raises(TypeError):
        carrier(traces=(), success=True)
