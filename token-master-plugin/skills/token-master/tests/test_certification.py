"""Strict, frozen, fresh-confirmation and durable spending regression tests."""
import hashlib
import json
import math
import sqlite3
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest

_SKILL = Path(__file__).resolve().parents[1]
if str(_SKILL) not in sys.path:
    sys.path.insert(0, str(_SKILL))

from brainspace.certification import (  # noqa: E402
    CertificationRegistry,
    ComparisonSpec,
    PairedObservation,
    VerifiedOutcome,
    round_alpha,
    radius,
)
from brainspace.token_ledger import CallRecord, MeasurementIdentity, TaskTrace, TokenLedger  # noqa: E402


def measurement():
    return MeasurementIdentity("ref", "1", "vocab-1", "full", "1", "full-model-text")


def spec(**changes):
    return ComparisonSpec(**dict(dict(
        candidate_id="candidate-v1", incumbent_id="incumbent-v1",
        measurement=measurement(), oracle_id="trusted-tests-v1",
        workload_id="iid-fixtures-v1", environment_id="model-tools-v1",
        token_cap=100, minimum_token_reduction=10,
    ), **changes))


def observation(task_id, *, candidate_success=True, incumbent_success=False,
                candidate_tokens=10, incumbent_tokens=90, comparison=None):
    s = comparison or spec()

    def run(policy, tokens):
        c = CallRecord(
            call_id=f"{task_id}:{policy}", task_id=task_id, attempt_id="a1",
            phase="learning", role="primary", model_id="m-v1", harness_id="test",
            measurement_id=s.measurement.identity,
            reference_input_tokens=tokens, reference_output_tokens=0,
            completion_status="succeeded", coverage="complete_for_declared_boundary",
        )
        return TaskTrace(
            task_id=task_id, policy_id=policy, measurement=s.measurement,
            phase="learning", learning_run_id="confirmation", calls=(c,),
            expected_call_ids=(c.call_id,), coverage="complete_for_declared_boundary",
        )

    return PairedObservation(
        task_id=task_id,
        incumbent=run(s.incumbent_id, incumbent_tokens),
        candidate=run(s.candidate_id, candidate_tokens),
        incumbent_outcome=VerifiedOutcome(task_id, s.incumbent_id, s.oracle_id,
                                          incumbent_success, "a" * 64),
        candidate_outcome=VerifiedOutcome(task_id, s.candidate_id, s.oracle_id,
                                          candidate_success, "b" * 64),
    )


def registry(tmp_path, **changes):
    return CertificationRegistry(
        tmp_path / "confirmation.sqlite",
        **dict(dict(alpha=0.05, trusted_oracle_id="trusted-tests-v1"), **changes),
    )


def submit_batch(r, k, observations, comparison=None):
    comparison = comparison or spec()
    r.reserve_tasks(k, comparison, [o.task_id for o in observations])
    r.submit(k, comparison, observations)


def test_exact_fixed_and_anytime_constants():
    for k in (1, 2, 19):
        a = 6 * 0.05 / (math.pi ** 2 * k ** 2)
        assert round_alpha(0.05, k) == pytest.approx(a, rel=1e-15)
        assert radius(0.05, k, 100) == pytest.approx(math.sqrt(2 * math.log(2 / a) / 100))
        assert radius(0.05, k, 100, anytime=True) == pytest.approx(
            math.sqrt(2 * math.log(2 * 100 * 101 / a) / 100)
        )
    assert math.ceil(2 * math.log(2 / round_alpha(0.05, 1)) / 0.05**2) == 3350
    assert sum(round_alpha(0.05, k) for k in range(1, 10000)) < 0.05


@pytest.mark.parametrize("alpha", [0, 1, -1, float("nan"), float("inf"), True, "0.05"])
def test_invalid_alpha_rejected(tmp_path, alpha):
    with pytest.raises(ValueError):
        registry(tmp_path, alpha=alpha)


@pytest.mark.parametrize("value", [0, -1, 1.5, True, float("nan"), float("inf")])
def test_invalid_cap_rejected(value):
    with pytest.raises(ValueError):
        spec(token_cap=value)


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True, 101])
def test_invalid_required_improvement_rejected(value):
    with pytest.raises(ValueError):
        spec(minimum_token_reduction=value)


def test_fixed_gate_machine_readable_certificate_and_idempotent_result(tmp_path):
    r = registry(tmp_path)
    k = r.start_round(spec(), sample_size=100)
    submit_batch(r, k, [observation(str(i)) for i in range(100)])
    c = r.certify(k, spec())
    assert c.decision == "certified"
    assert c.quality_difference_lower == pytest.approx(1 - radius(.05, 1, 100))
    assert c.normalized_token_difference_upper == pytest.approx(-.8 + radius(.05, 1, 100))
    assert c.alpha_round == pytest.approx(6 * .05 / math.pi**2)
    assert c.alpha_look == c.alpha_round
    assert c.sample_size == 100
    assert c.comparison == spec()
    data = c.to_dict()
    assert data["assumptions"] and data["limits"]
    assert "universal" in " ".join(data["limits"]).lower()
    assert "external labels" in " ".join(data["limits"]).lower()
    json.dumps(data, allow_nan=False)
    assert r.certify(k, spec()).to_dict() == data
    with pytest.raises(ValueError):
        r.reserve_tasks(k, spec(), ["late"])


@pytest.mark.parametrize("candidate_success,incumbent_success,candidate_tokens,incumbent_tokens", [
    (True, True, 0, 100),       # equal success cannot pass a strict finite-n bound
    (False, True, 0, 100),      # cheaper failures are not progress
    (True, False, 90, 90),      # quality alone is insufficient
    (True, False, 85, 90),      # less than required token reduction
])
def test_not_certified_is_not_proof_of_no_improvement(
    tmp_path, candidate_success, incumbent_success, candidate_tokens, incumbent_tokens,
):
    r = registry(tmp_path)
    k = r.start_round(spec(), sample_size=100)
    submit_batch(r, k, [observation(
        str(i), candidate_success=candidate_success, incumbent_success=incumbent_success,
        candidate_tokens=candidate_tokens, incumbent_tokens=incumbent_tokens,
    ) for i in range(100)])
    assert r.certify(k, spec()).decision == "not_certified"


def test_fixed_sample_size_no_early_look_no_extension(tmp_path):
    r = registry(tmp_path)
    k = r.start_round(spec(), sample_size=2)
    submit_batch(r, k, [observation("one")])
    with pytest.raises(ValueError):
        r.certify(k, spec())
    with pytest.raises(ValueError):
        r.reserve_tasks(k, spec(), ["two", "three"])
    submit_batch(r, k, [observation("two")])
    r.certify(k, spec())
    with pytest.raises(ValueError):
        r.submit(k, spec(), [observation("three")])


def test_anytime_looks_use_correct_spending_and_survive_restart(tmp_path):
    r = registry(tmp_path)
    k = r.start_round(spec(), mode="anytime")
    submit_batch(r, k, [observation("0")])
    first = r.certify(k, spec())
    assert first.decision == "not_certified"
    assert first.radius == pytest.approx(radius(.05, k, 1, anytime=True))
    assert first.alpha_look == pytest.approx(first.alpha_round / 2)
    r = registry(tmp_path)
    assert r.certify(k, spec()).to_dict() == first.to_dict()
    submit_batch(r, k, [observation(str(i)) for i in range(1, 100)])
    second = r.certify(k, spec())
    assert second.sample_size == 100
    assert second.alpha_look == pytest.approx(second.alpha_round / (100 * 101))
    assert second.radius == pytest.approx(radius(.05, k, 100, anytime=True))
    assert second.decision == "certified"


def test_restarts_cannot_reset_alpha_reuse_holdouts_or_change_config(tmp_path):
    r = registry(tmp_path)
    k1 = r.start_round(spec(), sample_size=1)
    r.reserve_tasks(k1, spec(), ["never-completed"])
    r = registry(tmp_path)
    k2 = r.start_round(spec(), sample_size=1)
    assert k2 == k1 + 1
    assert r.budget()["rounds"] == 2
    assert r.budget()["allocated_alpha"] == pytest.approx(round_alpha(.05, 1) + round_alpha(.05, 2))
    with pytest.raises(ValueError):
        r.reserve_tasks(k2, spec(), ["never-completed"])
    with pytest.raises(ValueError):
        registry(tmp_path, alpha=.1)
    with pytest.raises(ValueError):
        registry(tmp_path, trusted_oracle_id="different")
    r.submit(k1, spec(), [observation("never-completed")])
    r.certify(k1, spec())


def test_search_task_exclusions_and_duplicate_ids_atomic(tmp_path):
    r = registry(tmp_path)
    r.exclude_tasks(["search-exposed"])
    k = r.start_round(spec(), sample_size=3)
    for ids in (["search-exposed"], ["dup", "dup"], ["fresh", "search-exposed"]):
        with pytest.raises(ValueError):
            r.reserve_tasks(k, spec(), ids)
    r.reserve_tasks(k, spec(), ["fresh"])
    with pytest.raises(ValueError):
        r.exclude_tasks(["fresh"])
    with pytest.raises(ValueError):
        r.submit(k, spec(), [observation("not-reserved")])
    r.submit(k, spec(), [observation("fresh")])
    with pytest.raises(ValueError):
        r.submit(k, spec(), [observation("fresh")])


@pytest.mark.parametrize("change", [
    {"candidate_id": "changed"}, {"incumbent_id": "changed"},
    {"measurement": replace(measurement(), vocabulary_id="changed")},
    {"oracle_id": "changed"}, {"workload_id": "changed"},
    {"environment_id": "changed"}, {"token_cap": 200},
    {"minimum_token_reduction": 11},
])
def test_frozen_comparison_cannot_be_changed_after_start(tmp_path, change):
    r = registry(tmp_path)
    k = r.start_round(spec(), sample_size=1)
    with pytest.raises(ValueError):
        r.reserve_tasks(k, spec(**change), ["task"])
    with pytest.raises(ValueError):
        r.submit(k, spec(**change), [observation("task")])
    with pytest.raises(ValueError):
        r.certify(k, spec(**change))


def test_untrusted_oracle_and_nonbinary_score_rejected(tmp_path):
    r = registry(tmp_path)
    with pytest.raises(ValueError):
        r.start_round(spec(oracle_id="jev-score"), sample_size=1)
    with pytest.raises(ValueError):
        VerifiedOutcome("t", "p", "trusted-tests-v1", .99, "a" * 64)
    k = r.start_round(spec(), sample_size=1)
    o = observation("task")
    o = replace(o, candidate_outcome=replace(o.candidate_outcome, oracle_id="jev-score"))
    r.reserve_tasks(k, spec(), ["task"])
    with pytest.raises(ValueError):
        r.submit(k, spec(), [o])


@pytest.mark.parametrize("kind", [
    "over_cap", "partial", "missing_call", "wrong_policy", "wrong_task",
    "wrong_measurement", "deployment", "oracle_policy", "oracle_task", "duplicate_call",
])
def test_invalid_traces_and_misattributed_labels_rejected(tmp_path, kind):
    r = registry(tmp_path)
    k = r.start_round(spec(), sample_size=1)
    o = observation("task")
    if kind == "over_cap":
        o = observation("task", candidate_tokens=101)
    elif kind == "partial":
        o = replace(o, candidate=replace(o.candidate, coverage="partial"))
    elif kind == "missing_call":
        o = replace(o, candidate=replace(o.candidate, expected_call_ids=("missing",)))
    elif kind == "wrong_policy":
        o = replace(o, candidate=replace(o.candidate, policy_id="mutated"))
    elif kind == "wrong_task":
        o = replace(o, task_id="other")
    elif kind == "wrong_measurement":
        o = replace(o, candidate=replace(o.candidate, measurement=replace(measurement(), boundary="delta")))
    elif kind == "deployment":
        o = replace(o, candidate=replace(o.candidate, phase="deployment", learning_run_id=None))
    elif kind == "oracle_policy":
        o = replace(o, candidate_outcome=replace(o.candidate_outcome, policy_id="wrong"))
    elif kind == "oracle_task":
        o = replace(o, candidate_outcome=replace(o.candidate_outcome, task_id="wrong"))
    else:
        c = replace(o.candidate.calls[0], call_id=o.incumbent.calls[0].call_id)
        o = replace(o, candidate=replace(o.candidate, calls=(c,), expected_call_ids=(c.call_id,)))
    r.reserve_tasks(k, spec(), [o.task_id])
    with pytest.raises(ValueError):
        r.submit(k, spec(), [o])


def test_invalid_batch_rollback_keeps_previously_reserved_ids(tmp_path):
    r = registry(tmp_path)
    k = r.start_round(spec(), sample_size=2)
    r.reserve_tasks(k, spec(), ["one", "two"])
    with pytest.raises(ValueError):
        r.submit(k, spec(), [observation("one"), observation("two", candidate_tokens=101)])
    r.submit(k, spec(), [observation("one"), observation("two")])
    assert r.certify(k, spec()).sample_size == 2


def test_concurrent_round_allocation_has_no_reset_or_duplicate_k(tmp_path):
    registry(tmp_path)

    def start(_):
        return registry(tmp_path).start_round(spec(), sample_size=1)

    with ThreadPoolExecutor(max_workers=8) as pool:
        ks = list(pool.map(start, range(20)))
    assert sorted(ks) == list(range(1, 21))
    assert registry(tmp_path).budget()["rounds"] == 20


def test_concurrent_holdout_reservation_and_submission_exactly_once(tmp_path):
    r = registry(tmp_path)
    ks = [r.start_round(spec(), sample_size=1) for _ in range(2)]

    def reserve(k):
        try:
            registry(tmp_path).reserve_tasks(k, spec(), ["shared"])
            return k
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, ks))
    assert sum(x is not None for x in results) == 1
    winner = next(x for x in results if x is not None)

    def submit(_):
        try:
            registry(tmp_path).submit(winner, spec(), [observation("shared")])
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(submit, range(2))) == 1
    assert r.certify(winner, spec()).sample_size == 1


def test_registry_stores_hashes_not_raw_task_identifiers(tmp_path):
    r = registry(tmp_path)
    k = r.start_round(spec(), sample_size=1)
    secret = "customer-secret-task-123"
    submit_batch(r, k, [observation(secret)])
    r.certify(k, spec())
    with sqlite3.connect(tmp_path / "confirmation.sqlite") as db:
        dump = "\n".join(db.iterdump())
    assert secret not in dump
    assert "input_text" not in dump


@pytest.mark.parametrize("mode,n", [("fixed", None), ("fixed", 0), ("fixed", True),
                                    ("fixed", 1.5), ("anytime", 5), ("other", 5)])
def test_invalid_look_configuration_rejected(tmp_path, mode, n):
    with pytest.raises(ValueError):
        registry(tmp_path).start_round(spec(), mode=mode, sample_size=n)


def test_paired_confirmation_is_accounted_once_as_learning_not_deployment():
    o = observation("task")
    ledger = TokenLedger(measurement())
    ledger.record(o.learning_trace(spec()))
    report = ledger.summary()
    assert report["learning"]["total_tokens"] == 100
    assert report["learning"]["calls"] == 2
    assert report["deployment"]["total_tokens"] == 0
    with pytest.raises(ValueError):
        ledger.record(o.learning_trace(spec()))


def test_token_cap_covers_recovery_and_failed_attempts_not_just_final_call(tmp_path):
    r = registry(tmp_path)
    k = r.start_round(spec(), sample_size=1)
    o = observation("task")
    extra = replace(o.candidate.calls[0], call_id="recovery", role="recovery",
                    reference_input_tokens=91, completion_status="failed")
    o = replace(o, candidate=replace(
        o.candidate, calls=(*o.candidate.calls, extra),
        expected_call_ids=(*o.candidate.expected_call_ids, extra.call_id),
    ))
    r.reserve_tasks(k, spec(), ["task"])
    with pytest.raises(ValueError, match="cap"):
        r.submit(k, spec(), [o])


def test_relabelled_task_cannot_reuse_a_call_from_previous_round(tmp_path):
    r = registry(tmp_path)
    k1 = r.start_round(spec(), sample_size=1)
    submit_batch(r, k1, [observation("one")])
    k2 = r.start_round(spec(), sample_size=1)
    o = observation("two")
    c = replace(o.candidate.calls[0], call_id="one:candidate-v1")
    o = replace(o, candidate=replace(o.candidate, calls=(c,), expected_call_ids=(c.call_id,)))
    r.reserve_tasks(k2, spec(), ["two"])
    with pytest.raises(ValueError):
        r.submit(k2, spec(), [o])
    # A failed mixed insert must roll back all parts of the submission.
    r.submit(k2, spec(), [observation("two")])
    assert r.certify(k2, spec()).sample_size == 1


def _allocate_in_process(path):
    r = CertificationRegistry(path, alpha=.05, trusted_oracle_id="trusted-tests-v1")
    return r.start_round(spec(), sample_size=1)


def test_processes_share_the_same_durable_error_budget(tmp_path):
    r = registry(tmp_path)
    with ProcessPoolExecutor(max_workers=2) as pool:
        ks = list(pool.map(_allocate_in_process, [tmp_path / "confirmation.sqlite"] * 6))
    assert sorted(ks) == list(range(1, 7))
    assert r.budget()["rounds"] == 6


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0, 1, None, "true"])
def test_outcomes_require_actual_booleans_not_numeric_or_model_scores(value):
    with pytest.raises(ValueError):
        VerifiedOutcome("t", "p", "trusted-tests-v1", value, "a" * 64)


def test_corrupted_persisted_bounds_fail_closed(tmp_path):
    r = registry(tmp_path)
    k = r.start_round(spec(), sample_size=1)
    submit_batch(r, k, [observation("t")])
    with sqlite3.connect(tmp_path / "confirmation.sqlite") as db:
        db.execute("UPDATE observations SET candidate_tokens=101")
    with pytest.raises(ValueError, match="cap"):
        r.certify(k, spec())


def test_complete_zero_call_candidate_is_bounded_and_valid(tmp_path):
    r = registry(tmp_path)
    k = r.start_round(spec(), sample_size=1)
    o = observation("t")
    o = replace(o, candidate=replace(o.candidate, calls=(), expected_call_ids=()))
    submit_batch(r, k, [o])
    assert r.certify(k, spec()).mean_normalized_token_difference == -.9


def test_anytime_cannot_omit_pending_reserved_tasks_from_a_look(tmp_path):
    r = registry(tmp_path)
    k = r.start_round(spec(), mode="anytime")
    r.reserve_tasks(k, spec(), ["one", "two"])
    r.submit(k, spec(), [observation("one")])
    with pytest.raises(ValueError, match="reserved"):
        r.certify(k, spec())
    r.submit(k, spec(), [observation("two")])
    assert r.certify(k, spec()).sample_size == 2


def test_certificate_binds_evidence_and_durable_registry_identity(tmp_path):
    r = registry(tmp_path)
    k = r.start_round(spec(), sample_size=1)
    submit_batch(r, k, [observation("t")])
    c = r.certify(k, spec())
    assert c.registry_id == r.budget()["registry_id"]
    assert registry(tmp_path).budget()["registry_id"] == c.registry_id
    assert len(c.evidence_sha256) == 64
    other = CertificationRegistry(tmp_path / "other.sqlite", alpha=.05,
                                  trusted_oracle_id="trusted-tests-v1")
    assert other.budget()["registry_id"] != c.registry_id


def test_live_registry_refuses_replaced_identity(tmp_path):
    r = registry(tmp_path)
    k = r.start_round(spec(), sample_size=1)
    with sqlite3.connect(tmp_path / "confirmation.sqlite") as db:
        db.execute("UPDATE config SET registry_id=?", ("changed",))
    with pytest.raises(ValueError, match="identity"):
        r.reserve_tasks(k, spec(), ["task"])


def relabel_observation(obs, task_id):
    """Change only task labels, deliberately preserving exposed call IDs."""
    def trace(old):
        return replace(old, task_id=task_id, calls=tuple(
            replace(call, task_id=task_id) for call in old.calls))

    return replace(
        obs, task_id=task_id, incumbent=trace(obs.incumbent), candidate=trace(obs.candidate),
        incumbent_outcome=replace(obs.incumbent_outcome, task_id=task_id),
        candidate_outcome=replace(obs.candidate_outcome, task_id=task_id),
    )


@pytest.mark.parametrize("kind", ["prevalidation", "sql_collision"])
@pytest.mark.parametrize("invalid_first", [False, True])
def test_rejected_batch_exposure_blocks_review_reproductions_after_restart(
    tmp_path, kind, invalid_first,
):
    r = registry(tmp_path)
    original = r.start_round(spec(), sample_size=1)
    submit_batch(r, original, [observation("original")])
    exposed = [observation(f"exposed-{i}") for i in range(100)]
    invalid = observation("invalid")
    if kind == "prevalidation":
        invalid = replace(invalid, candidate=replace(invalid.candidate, coverage="partial"))
    else:
        call = replace(invalid.candidate.calls[0], call_id="original:candidate-v1")
        invalid = replace(invalid, candidate=replace(
            invalid.candidate, calls=(call,), expected_call_ids=(call.call_id,)))
    batch = [invalid, *exposed] if invalid_first else [*exposed, invalid]
    rejected = r.start_round(spec(), sample_size=101)
    r.reserve_tasks(rejected, spec(), [o.task_id for o in batch])
    with pytest.raises(ValueError):
        r.submit(rejected, spec(), batch)
    with closing(sqlite3.connect(tmp_path / "confirmation.sqlite")) as db:
        assert db.execute("SELECT COUNT(*) FROM tasks WHERE round_id=?", (rejected,)).fetchone()[0] == 101
        assert db.execute("SELECT COUNT(*) FROM observations WHERE round_id=?", (rejected,)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 2
        for obs in batch:
            for trace in (obs.incumbent, obs.candidate):
                for call in trace.calls:
                    original_task = "original" if call.call_id.startswith("original:") else obs.task_id
                    assert db.execute(
                        "SELECT task_hash FROM reported_calls WHERE call_hash=?",
                        (hashlib.sha256(call.call_id.encode()).hexdigest(),),
                    ).fetchone() == (hashlib.sha256(original_task.encode()).hexdigest(),)

    r = registry(tmp_path)
    replay = r.start_round(spec(), sample_size=100)
    recycled = [relabel_observation(o, f"relabelled-{i}") for i, o in enumerate(exposed)]
    r.reserve_tasks(replay, spec(), [o.task_id for o in recycled])
    with pytest.raises(ValueError):
        r.submit(replay, spec(), recycled)
    with pytest.raises(ValueError):
        r.certify(replay, spec())
    # The unseen arm of the colliding/invalid pair must also remain consumed.
    sibling = relabel_observation(invalid, "invalid-sibling")
    sibling = replace(sibling, candidate=observation("invalid-sibling").candidate)
    sibling_round = r.start_round(spec(), sample_size=1)
    r.reserve_tasks(sibling_round, spec(), [sibling.task_id])
    with pytest.raises(ValueError):
        r.submit(sibling_round, spec(), [sibling])
    fresh = r.start_round(spec(), sample_size=100)
    submit_batch(r, fresh, [observation(f"fresh-{i}") for i in range(100)])
    assert r.certify(fresh, spec()).decision == "certified"


@pytest.mark.parametrize("kind", [
    "malformed", "duplicate_observation", "duplicate_call", "invalid_call_id", "invalid_task_id",
])
@pytest.mark.parametrize("invalid_first", [False, True])
def test_rejected_batch_exposure_preserves_valid_siblings(tmp_path, kind, invalid_first):
    r = registry(tmp_path)
    k = r.start_round(spec(), sample_size=2)
    r.reserve_tasks(k, spec(), ["good", "bad"])
    good, bad = observation("good"), observation("bad")
    if kind == "malformed":
        bad = None
    elif kind == "duplicate_observation":
        bad = good
    elif kind == "duplicate_call":
        bad = replace(bad, candidate=replace(
            bad.candidate, calls=bad.candidate.calls * 2))
    elif kind == "invalid_call_id":
        call = replace(bad.candidate.calls[0], call_id="\ud800")
        bad = replace(bad, candidate=replace(
            bad.candidate, calls=(call,), expected_call_ids=(call.call_id,)))
    else:
        bad = replace(bad, task_id="\ud800")
    batch = [bad, good] if invalid_first else [good, bad]
    with pytest.raises(ValueError):
        r.submit(k, spec(), batch)
    r = registry(tmp_path)
    replay = r.start_round(spec(), sample_size=1)
    r.reserve_tasks(replay, spec(), ["replay"])
    with pytest.raises(ValueError):
        r.submit(replay, spec(), [relabel_observation(good, "replay")])
    # Correcting a rejected observation under its ORIGINAL reservation is supported.
    # An invalid task ID cannot establish ownership of that pair's own calls.
    corrected = (relabel_observation(observation("fresh-bad"), "bad")
                 if kind == "invalid_task_id" else observation("bad"))
    r.submit(k, spec(), [good, corrected])
    assert r.certify(k, spec()).sample_size == 2


def test_rejected_batch_exposure_survives_sql_rollback(tmp_path):
    r = registry(tmp_path)
    k = r.start_round(spec(), sample_size=2)
    batch = [observation("one"), observation("two")]
    r.reserve_tasks(k, spec(), [o.task_id for o in batch])
    with closing(sqlite3.connect(tmp_path / "confirmation.sqlite")) as db, db:
        db.execute("""CREATE TRIGGER reject_second BEFORE INSERT ON observations
                      WHEN (SELECT COUNT(*) FROM observations)=1
                      BEGIN SELECT RAISE(ABORT, 'injected SQL rejection'); END""")
    with pytest.raises(ValueError):
        r.submit(k, spec(), batch)
    with closing(sqlite3.connect(tmp_path / "confirmation.sqlite")) as db, db:
        assert db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 0
        db.execute("DROP TRIGGER reject_second")
    r = registry(tmp_path)
    for i, obs in enumerate(batch):
        replay = r.start_round(spec(), sample_size=1)
        recycled = relabel_observation(obs, f"replay-{i}")
        r.reserve_tasks(replay, spec(), [recycled.task_id])
        with pytest.raises(ValueError):
            r.submit(replay, spec(), [recycled])
    r.submit(k, spec(), batch)
    assert r.certify(k, spec()).sample_size == 2


@pytest.mark.parametrize("kind", ["unreserved", "wrong_round", "changed_spec", "closed"])
def test_rejected_batch_exposure_cannot_be_rebound_to_later_reservation(tmp_path, kind):
    r = registry(tmp_path)
    k = r.start_round(spec(), sample_size=1)
    obs = observation("reported")
    submitted_spec = spec()
    if kind == "wrong_round":
        other = r.start_round(spec(), sample_size=1)
        r.reserve_tasks(other, spec(), [obs.task_id])
    elif kind == "changed_spec":
        r.reserve_tasks(k, spec(), [obs.task_id])
        submitted_spec = spec(environment_id="changed")
    elif kind == "closed":
        submit_batch(r, k, [observation("accepted")])
        r.certify(k, spec())
    with pytest.raises(ValueError):
        r.submit(k, submitted_spec, [obs])
    r = registry(tmp_path)
    replay = r.start_round(spec(), sample_size=1)
    r.reserve_tasks(replay, spec(), ["replay"])
    with pytest.raises(ValueError):
        r.submit(replay, spec(), [relabel_observation(obs, "replay")])
    if kind == "unreserved":
        r.reserve_tasks(k, spec(), [obs.task_id])
        with pytest.raises(ValueError):
            r.submit(k, spec(), [obs])


def test_rejected_batch_exposure_survives_interrupted_iterable(tmp_path):
    r = registry(tmp_path)
    k = r.start_round(spec(), sample_size=1)
    r.reserve_tasks(k, spec(), ["reported"])

    def interrupted():
        yield observation("reported")
        raise RuntimeError("interrupted after reporting")

    with pytest.raises(RuntimeError, match="interrupted"):
        r.submit(k, spec(), interrupted())
    r = registry(tmp_path)
    replay = r.start_round(spec(), sample_size=1)
    r.reserve_tasks(replay, spec(), ["replay"])
    with pytest.raises(ValueError):
        r.submit(replay, spec(), [relabel_observation(observation("reported"), "replay")])


def test_legacy_registry_adds_exposure_without_rewriting_evidence_or_certificates(tmp_path):
    r = registry(tmp_path)
    k = r.start_round(spec(), sample_size=100)
    submit_batch(r, k, [observation(f"legacy-{i}") for i in range(100)])
    certificate = r.certify(k, spec()).to_dict()
    pending = r.start_round(spec(), sample_size=1)
    r.reserve_tasks(pending, spec(), ["pending"])
    tables = ("config", "rounds", "tasks", "observations", "calls", "looks")
    with closing(sqlite3.connect(tmp_path / "confirmation.sqlite")) as db, db:
        # Remove only the additive table to reproduce the exact legacy schema.
        db.execute("DROP TABLE reported_calls")
        before = {table: db.execute(f"SELECT * FROM {table}").fetchall() for table in tables}
    r = registry(tmp_path)
    assert r.certify(k, spec()).to_dict() == certificate
    with closing(sqlite3.connect(tmp_path / "confirmation.sqlite")) as db:
        assert {table: db.execute(f"SELECT * FROM {table}").fetchall()
                for table in tables} == before
        assert db.execute("SELECT COUNT(*) FROM reported_calls").fetchone()[0] == 0
    replay = r.start_round(spec(), sample_size=1)
    r.reserve_tasks(replay, spec(), ["replay"])
    with pytest.raises(ValueError):
        r.submit(replay, spec(), [relabel_observation(observation("legacy-0"), "replay")])
    # Retrying cannot overwrite the accepted original, either.
    with pytest.raises(ValueError):
        r.submit(k, spec(), [observation("legacy-0", candidate_success=False)])
    assert r.certify(k, spec()).to_dict() == certificate
    r.submit(pending, spec(), [observation("pending")])
    assert r.certify(pending, spec()).sample_size == 1


def test_concurrent_reported_call_ownership_cannot_transfer_between_tasks(tmp_path):
    r = registry(tmp_path)
    rounds = [r.start_round(spec(), sample_size=1) for _ in range(2)]
    for i, k in enumerate(rounds):
        r.reserve_tasks(k, spec(), [f"task-{i}"])

    def submit(i):
        obs = relabel_observation(observation("shared-calls"), f"task-{i}")
        try:
            registry(tmp_path).submit(rounds[i], spec(), [obs])
            return i
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert sum(i is not None for i in results) == 1
    winner = next(i for i in results if i is not None)
    r = registry(tmp_path)
    assert r.certify(rounds[winner], spec()).sample_size == 1
    with pytest.raises(ValueError):
        r.certify(rounds[1 - winner], spec())
