"""Regression contract for complete, token-only measurement."""
import json
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

# Match existing repository tests: runnable from either repository or skill root.
_SKILL = Path(__file__).resolve().parents[1]
if str(_SKILL) not in sys.path:
    sys.path.insert(0, str(_SKILL))

from brainspace.token_ledger import (  # noqa: E402
    CallRecord,
    DeploymentHorizon,
    MeasurementIdentity,
    TaskTrace,
    TokenLedger,
    measure_call,
)


def measurement(**changes):
    return MeasurementIdentity(
        **dict(
            dict(
                tokenizer_id="reference",
                tokenizer_version="1",
                vocabulary_id="vocab-sha256:abc",
                extraction_protocol_id="full-text",
                extraction_protocol_version="1",
                boundary="materialized-model-text-v1",
            ),
            **changes,
        )
    )


def call(call_id="c1", task_id="t1", **changes):
    return CallRecord(
        **dict(
            dict(
                call_id=call_id,
                task_id=task_id,
                attempt_id="attempt-1",
                phase="deployment",
                role="primary",
                model_id="model-v1",
                harness_id="fixture",
                measurement_id=measurement().identity,
                reference_input_tokens=10,
                reference_output_tokens=2,
                coverage="complete_for_declared_boundary",
                completion_status="succeeded",
            ),
            **changes,
        )
    )


def trace(task_id="t1", calls=None, **changes):
    calls = tuple(calls) if calls is not None else (call(task_id=task_id),)
    return TaskTrace(
        **dict(
            dict(
                task_id=task_id,
                policy_id="policy-v1",
                measurement=measurement(),
                phase="deployment",
                calls=calls,
                expected_call_ids=tuple(c.call_id for c in calls),
                coverage="complete_for_declared_boundary",
            ),
            **changes,
        )
    )


def test_measurement_identity_is_immutable_and_covers_every_version():
    m = measurement()
    assert m.identity == measurement().identity
    assert len(m.identity) == 64
    for field in (
        "tokenizer_id", "tokenizer_version", "vocabulary_id",
        "extraction_protocol_id", "extraction_protocol_version", "boundary",
    ):
        assert replace(m, **{field: "changed"}).identity != m.identity
    with pytest.raises(FrozenInstanceError):
        m.boundary = "changed"


@pytest.mark.parametrize("field", [
    "tokenizer_id", "tokenizer_version", "vocabulary_id",
    "extraction_protocol_id", "extraction_protocol_version", "boundary",
])
def test_measurement_identity_requires_all_pins(field):
    with pytest.raises(ValueError):
        measurement(**{field: ""})


def test_full_serialized_input_counted_once_no_payload_in_telemetry():
    seen = []

    def count(text):
        seen.append(text)
        return {"ab": 1, "answer-secret": 4}[text]

    c = measure_call(
        measurement(), count, input_text="ab", output_text="answer-secret",
        call_id="c", task_id="t", attempt_id="a", phase="deployment",
        role="primary", model_id="m", harness_id="h",
        completion_status="succeeded",
        coverage="complete_for_declared_boundary",
    )
    assert seen == ["ab", "answer-secret"]
    assert (c.reference_input_tokens, c.reference_output_tokens) == (1, 4)
    data = c.to_dict()
    assert len(data["input_sha256"]) == len(data["output_sha256"]) == 64
    assert "answer-secret" not in json.dumps(data)
    assert "input_text" not in data


def test_replayed_inputs_failed_attempts_recovery_and_auxiliaries_count_in_full():
    calls = (
        call("main", reference_input_tokens=100, reference_output_tokens=20,
             completion_status="failed"),
        call("retry", attempt_id="attempt-2", role="retry",
             reference_input_tokens=130, reference_output_tokens=30),
        call("jev", role="auxiliary", reference_input_tokens=40,
             reference_output_tokens=5),
        call("recover", role="recovery", parent_call_id="retry",
             reference_input_tokens=50, reference_output_tokens=10),
        call("verify", role="verification", reference_input_tokens=60,
             reference_output_tokens=5),
    )
    ledger = TokenLedger(measurement())
    ledger.record(trace(calls=calls), success=True)
    ledger.record(trace("t2", [call("failure", "t2", completion_status="failed")]),
                  success=False)
    report = ledger.summary()
    d = report["deployment"]
    assert (d["input_tokens"], d["output_tokens"], d["total_tokens"]) == (390, 72, 462)
    assert (d["peak_input_tokens"], d["calls"], d["tasks"]) == (130, 6, 2)
    assert (d["verified_successes"], d["success_rate"]) == (1, 0.5)
    assert d["tokens_per_verified_success"] == 462
    assert d["by_role"]["auxiliary"]["total_tokens"] == 45
    assert d["by_status"]["failed"]["calls"] == 2
    assert report["learning"]["total_tokens"] == 0


@pytest.mark.parametrize("value", [-1, 1.5, True, float("nan"), float("inf"), None])
@pytest.mark.parametrize("field", ["reference_input_tokens", "reference_output_tokens"])
def test_reference_counts_are_nonnegative_exact_integers(field, value):
    with pytest.raises(ValueError):
        call(**{field: value})


@pytest.mark.parametrize("change", [
    {"coverage": "partial"},
    {"coverage": "unknown"},
    {"count_kind": "native"},
    {"count_kind": "estimate"},
    {"input_kind": "transport_delta"},
    {"missing_or_opaque_components": ("hidden auxiliary call",)},
])
def test_inexact_partial_or_nonmaterialized_call_rejected(change):
    with pytest.raises(ValueError):
        TokenLedger(measurement()).record(trace(calls=[call(**change)]))


@pytest.mark.parametrize("change", [
    {"coverage": "partial"},
    {"coverage": "unknown"},
    {"expected_call_ids": ("c1", "unseen")},
    {"expected_call_ids": ("c1", "c1")},
    {"missing_or_opaque_components": ("verification input",)},
    {"calls": (), "expected_call_ids": ("unseen",)},
])
def test_incomplete_task_rejected(change):
    with pytest.raises(ValueError):
        TokenLedger(measurement()).record(trace(**change))


def test_duplicate_task_call_and_cross_task_call_ids_are_rejected():
    ledger = TokenLedger(measurement())
    ledger.record(trace())
    with pytest.raises(ValueError):
        ledger.record(trace())
    with pytest.raises(ValueError):
        ledger.record(trace("t2", [call(task_id="t2")]))
    with pytest.raises(ValueError):
        ledger.record(trace("t3", [call("dup", "t3"), call("dup", "t3")]))
    assert ledger.summary()["deployment"]["calls"] == 1


@pytest.mark.parametrize("change", [
    {"measurement_id": measurement(vocabulary_id="other").identity},
    {"task_id": "other"},
    {"phase": "learning"},
    {"parent_call_id": "missing"},
    {"parent_call_id": "c1"},
])
def test_call_trace_identity_and_parent_mismatch(change):
    with pytest.raises(ValueError):
        TokenLedger(measurement()).record(trace(calls=[call(**change)]))


def test_parent_cycle_is_rejected():
    with pytest.raises(ValueError):
        TokenLedger(measurement()).record(trace(calls=[
            call("a", parent_call_id="b"), call("b", parent_call_id="a"),
        ]))


def test_measurement_mismatch_and_phase_leakage_are_rejected():
    ledger = TokenLedger(measurement(vocabulary_id="changed"))
    with pytest.raises(ValueError):
        ledger.record(trace())
    with pytest.raises(ValueError):
        trace(learning_run_id="not-learning")
    with pytest.raises(ValueError):
        trace(phase="learning")


def test_zero_success_and_unknown_outcome_are_not_free_tokens():
    ledger = TokenLedger(measurement())
    ledger.record(trace(), success=False)
    d = ledger.summary()["deployment"]
    assert d["total_tokens"] == 12
    assert d["tokens_per_verified_success"] is None
    assert d["ratio_status"] == "no_verified_successes"
    ledger.record(trace("t2", [call("c2", "t2")]))
    assert ledger.summary()["deployment"]["ratio_status"] == "incomplete_outcomes"
    json.dumps(ledger.summary(), allow_nan=False)
    with pytest.raises(ValueError):
        TokenLedger(measurement()).record(trace(), success=0.99)


def test_learning_totals_and_predeclared_horizon_are_separate():
    horizon = DeploymentHorizon("h1", ("t1", "t2"), ("search-1",))
    ledger = TokenLedger(measurement(), horizon=horizon)
    learning = trace("l1", [call("lc", "l1", phase="learning", role="auxiliary")],
                     phase="learning", learning_run_id="search-1")
    ledger.record(learning)
    ledger.record(trace(), success=True)
    assert ledger.summary()["all_in"]["status"] == "incomplete_horizon"
    ledger.record(trace("t2", [call("c2", "t2")]), success=False)
    ledger.seal_learning_run("search-1", ("l1",))
    report = ledger.summary()
    assert report["deployment"]["total_tokens"] == 24
    assert report["learning"]["total_tokens"] == 12
    assert report["learning"]["by_run"]["search-1"]["total_tokens"] == 12
    assert report["all_in"]["total_tokens"] == 36
    assert report["all_in"]["tokens_per_verified_success"] == 36
    assert report["all_in"]["horizon_id"] == "h1"
    with pytest.raises(ValueError):
        ledger.record(trace("outside", [call("outside", "outside")]), success=True)
    with pytest.raises(FrozenInstanceError):
        horizon.horizon_id = "post-selected"


def test_unregistered_learning_run_and_unpinned_horizon():
    ledger = TokenLedger(measurement(), horizon=DeploymentHorizon("h", ("t1",), ("run",)))
    with pytest.raises(ValueError):
        ledger.record(trace("l", [call("lc", "l", phase="learning")],
                            phase="learning", learning_run_id="other"))
    assert TokenLedger(measurement()).summary()["all_in"] is None


def test_learning_run_presence_cannot_claim_complete_all_in_accounting():
    ledger = TokenLedger(measurement(), horizon=DeploymentHorizon("h", ("t1",), ("run",)))
    ledger.record(trace(), success=True)
    ledger.record(trace("l1", [call("lc1", "l1", phase="learning")],
                        phase="learning", learning_run_id="run"))
    assert ledger.summary()["all_in"]["tokens_per_verified_success"] is None
    assert ledger.summary()["all_in"]["unsealed_learning_runs"] == ["run"]
    ledger.record(trace("l2", [call("lc2", "l2", phase="learning",
                                  reference_input_tokens=1000)],
                        phase="learning", learning_run_id="run"))
    with pytest.raises(ValueError):
        ledger.seal_learning_run("run", ("l1",))
    ledger.seal_learning_run("run", ("l1", "l2"))
    assert ledger.summary()["all_in"]["status"] == "defined"
    with pytest.raises(ValueError):
        ledger.record(trace("l3", [call("lc3", "l3", phase="learning")],
                            phase="learning", learning_run_id="run"))


def test_learning_seal_is_explicit_idempotent_and_validated():
    ledger = TokenLedger(measurement(), horizon=DeploymentHorizon("h", ("t1",), ("run",)))
    ledger.record(trace(), success=True)
    with pytest.raises(ValueError):
        ledger.seal_learning_run("other", ())
    with pytest.raises(ValueError):
        ledger.seal_learning_run("run", ("missing",))
    ledger.seal_learning_run("run", ())
    ledger.seal_learning_run("run", ())
    assert ledger.summary()["all_in"]["status"] == "defined"
    assert ledger.summary()["learning"]["by_run"]["run"]["inventory_sealed"]
    with pytest.raises(ValueError):
        ledger.seal_learning_run("run", ("invented",))


def test_mutable_container_inputs_are_defensively_frozen():
    calls = [call()]
    ids = ["c1"]
    t = trace(calls=calls, expected_call_ids=ids)
    calls.clear()
    ids.clear()
    assert t.totals().calls == 1
    assert t.expected_call_ids == ("c1",)


def test_no_cache_discount_native_count_or_pricing_fields():
    fields = CallRecord.__dataclass_fields__
    assert not {"cached_tokens", "native_tokens", "price", "cost", "discount"} & fields.keys()
    with pytest.raises(TypeError):
        call(cached_tokens=9)


def test_explicit_complete_zero_call_task_is_not_an_unknown_trace():
    ledger = TokenLedger(measurement())
    ledger.record(trace(calls=(), expected_call_ids=()), success=True)
    report = ledger.summary()["deployment"]
    assert report["calls"] == report["total_tokens"] == report["peak_input_tokens"] == 0
    assert report["tokens_per_verified_success"] == 0
    with pytest.raises(ValueError):
        ledger.record(trace("unknown", calls=(), expected_call_ids=(), coverage="unknown"))
