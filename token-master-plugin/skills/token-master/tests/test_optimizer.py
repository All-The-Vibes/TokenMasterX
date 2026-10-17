"""Regression-first durability, independence and promotion boundary tests."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import sqlite3

import pytest

from brainspace.certification import PairedObservation, VerifiedOutcome
from brainspace.jev import Diagnostics, Result
from brainspace.optimizer import (
    BaselineValidation, Optimizer, OptimizerConfig, OptimizerError, reference_measurement,
)
from brainspace.request_policy import RequestPolicy
from brainspace.token_ledger import (
    COMPLETE, DeploymentHorizon, TaskTrace, TokenLedger, measure_call,
)
from brainspace.tokens import count_tokens


def config(**changes):
    return OptimizerConfig(**{
        "measurement": reference_measurement(),
        "oracle_id": "independent-test-v1", "workload_id": "synthetic-v1",
        "model_id": "fixture-model-v1", "environment_id": "offline-v1",
        "token_cap": 100, "minimum_token_reduction": 1, "alpha": 0.05,
        "max_candidates": 6, "max_calls": 2000, "calls_per_pair": 2, **changes,
    })


def baseline_check(policy, regime, reservation):
    return BaselineValidation(policy.policy_id, regime.identity, regime.oracle_id,
                              True, "a" * 64, TaskTrace(
                                  reservation.task_id, policy.policy_id, regime.measurement,
                                  "learning", (), (), COMPLETE, reservation.learning_run_id))


def pair(trial, task_id, *, equal=False):
    spec = trial.comparison

    def trace(policy_id, text):
        call = measure_call(
            spec.measurement, count_tokens, input_text=text, output_text="",
            call_id=f"{task_id}:{policy_id}", task_id=task_id, attempt_id="1",
            phase="learning", role="primary", model_id="fixture-model-v1",
            harness_id="offline-fixture", coverage=COMPLETE, completion_status="succeeded",
        )
        return TaskTrace(task_id, policy_id, spec.measurement, "learning", (call,),
                         (call.call_id,), COMPLETE, trial.learning_run_id)

    return PairedObservation(
        task_id, trace(spec.incumbent_id, "x " * 89), trace(spec.candidate_id, "x " * 9),
        VerifiedOutcome(task_id, spec.incumbent_id, spec.oracle_id, equal, "b" * 64),
        VerifiedOutcome(task_id, spec.candidate_id, spec.oracle_id, True, "c" * 64),
    )


def controller(tmp_path, evaluator=pair, **changes):
    return Optimizer(tmp_path / "optimizer.sqlite", config=config(**changes),
                     evaluator=evaluator)


def initialize(opt):
    return opt.initialize(RequestPolicy(enabled=True), validator=baseline_check,
                          validation_call_limit=0)


def trial_inventory(opt, trial):
    inventory = opt.learning_inventory()
    return {
        "runs": [r for r in inventory["runs"] if r["run_id"] == trial.learning_run_id],
        "traces": [t for t in inventory["traces"] if t.learning_run_id == trial.learning_run_id],
    }


def freeze(opt, n=100, index=0):
    candidate = opt.propose()[index]
    return opt.freeze(candidate.policy_id, sample_size=n)


def evaluate(opt, trial, prefix="fresh"):
    return opt.evaluate(trial.trial_id, [f"{prefix}-{i}" for i in range(trial.sample_size)])


def test_baseline_requires_fixed_independent_validation(tmp_path):
    opt = controller(tmp_path)
    with pytest.raises(OptimizerError):
        opt.initialize(RequestPolicy(), validator=lambda p, c, r: True, validation_call_limit=0)
    with pytest.raises(OptimizerError):
        opt.initialize(RequestPolicy(), validator=lambda p, c, r:
                       replace(baseline_check(p, c, r), passed=False), validation_call_limit=0)
    assert initialize(opt)["champion"]["policy_id"] == RequestPolicy(enabled=True).policy_id
    with pytest.raises(OptimizerError):
        initialize(opt)


def test_proposals_are_immutable_validated_neighbors_and_deterministic(tmp_path):
    opt = controller(tmp_path)
    initialize(opt)
    a, b = opt.propose(), opt.propose()
    assert a == b and 0 < len(a) <= 6
    assert all(p.enabled and p.recovery_required for p in a)
    with pytest.raises(FrozenInstanceError):
        a[0].enabled = False
    with pytest.raises(OptimizerError):
        opt.freeze(RequestPolicy().policy_id, sample_size=100)


def test_complete_promotion_restart_history_and_rollback(tmp_path):
    opt = controller(tmp_path)
    initial = initialize(opt)
    trial = freeze(opt)
    cert = evaluate(opt, trial)
    assert cert.decision == "certified"
    promoted = opt.promote(trial.trial_id)
    assert promoted["champion"]["policy_id"] == trial.candidate.policy_id
    reopened = controller(tmp_path)
    assert reopened.status() == promoted
    rolled = reopened.rollback(expected_version=promoted["champion"]["version"])
    assert rolled["champion"]["policy_id"] == initial["champion"]["policy_id"]
    assert rolled["champion"]["version"] > promoted["champion"]["version"]
    assert [h["action"] for h in rolled["history"]] == ["initialize", "promote", "rollback"]
    assert rolled["learning"]["complete_calls"] == 200
    assert rolled["learning"]["reference_tokens"] == 10000
    assert rolled["learning"]["deployments"] == 0
    assert rolled["budget"]["rounds"] == 1


def test_equal_quality_remains_inconclusive(tmp_path):
    opt = controller(tmp_path, lambda t, task: pair(t, task, equal=True))
    initialize(opt)
    trial = freeze(opt)
    assert evaluate(opt, trial).decision == "not_certified"
    with pytest.raises(OptimizerError):
        opt.promote(trial.trial_id)
    assert opt.status()["champion"]["version"] == 1


def test_search_exclusions_persist_and_reservations_precede_callback(tmp_path):
    seen = []
    opt = controller(tmp_path)
    initialize(opt)
    opt.propose(search_task_ids=["search-only"])
    assert "search-only" in opt.status()["search_task_ids"]

    def evaluator(t, task):
        with sqlite3.connect(opt.path) as db:
            reservation = db.execute("SELECT kind FROM tasks WHERE task_hash=?",
                                     (hashlib.sha256(task.encode()).hexdigest(),)).fetchone()
        assert reservation == ("confirmation",)
        seen.append(task)
        return pair(t, task)

    opt = controller(tmp_path, evaluator)
    trial = freeze(opt, n=1)
    with pytest.raises(OptimizerError):
        opt.evaluate(trial.trial_id, ["search-only"])
    assert not seen
    trial2 = freeze(opt, n=1, index=0)
    opt.evaluate(trial2.trial_id, ["fresh"])
    assert seen == ["fresh"]
    trial3 = freeze(opt, n=1, index=0)
    with pytest.raises(OptimizerError):
        opt.evaluate(trial3.trial_id, ["fresh"])
    assert seen == ["fresh"]


def test_cancelled_round_cannot_replay_or_reset_budget(tmp_path):
    def interrupted(t, task):
        raise KeyboardInterrupt
    opt = controller(tmp_path, interrupted)
    initialize(opt)
    trial = freeze(opt)
    with pytest.raises(KeyboardInterrupt):
        evaluate(opt, trial)
    reopened = controller(tmp_path)
    status = reopened.status()
    assert status["trials"][0]["state"] == "cancelled"
    assert status["budget"]["rounds"] == 1
    assert status["calls_budget_spent"] == 200
    assert status["learning"]["unknown_events"] == 100
    assert status["learning"]["unsealed_runs"] == 1
    assert status["learning"]["reference_tokens"] is None
    with pytest.raises(OptimizerError):
        evaluate(reopened, trial)
    second = freeze(reopened, n=1)
    with pytest.raises(OptimizerError):
        reopened.evaluate(second.trial_id, ["fresh-0"])


def test_forged_certificate_or_unregistered_trial_not_accepted(tmp_path):
    opt = controller(tmp_path)
    initialize(opt)
    trial = freeze(opt)
    for forged in ({"decision": "certified"}, '{"decision":"certified"}', True, 99999):
        with pytest.raises(OptimizerError):
            opt.promote(forged)
    with pytest.raises(OptimizerError):
        opt.promote(trial.trial_id)


def test_stale_promotion_and_concurrent_cas(tmp_path):
    opt = controller(tmp_path)
    initialize(opt)
    first, second = freeze(opt), freeze(opt, index=0)
    evaluate(opt, first, "first")
    evaluate(opt, second, "second")
    other = controller(tmp_path)

    def promote(args):
        owner, trial = args
        try:
            owner.promote(trial.trial_id)
            return True
        except OptimizerError:
            return False

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(promote, [(opt, first), (other, second)]))
    assert sorted(results) == [False, True]
    assert opt.status()["champion"]["version"] == 2


def test_regime_mutation_and_policy_storage_tampering_fail_closed(tmp_path):
    opt = controller(tmp_path)
    initialize(opt)
    with pytest.raises((OptimizerError, ValueError)):
        controller(tmp_path, model_id="changed")
    trial = freeze(opt)
    with sqlite3.connect(opt.path) as db:
        db.execute("UPDATE opt_policies SET policy_json=? WHERE policy_id=?",
                   (RequestPolicy().to_json(), trial.candidate.policy_id))
    with pytest.raises(OptimizerError):
        evaluate(opt, trial)


def test_evaluator_mutation_or_wrong_model_never_certifies(tmp_path):
    def mutate(t, task):
        obs = pair(t, task)
        object.__setattr__(t.candidate, "min_tool_chars", 1234)
        return obs
    opt = controller(tmp_path, mutate)
    initialize(opt)
    trial = freeze(opt, n=1)
    with pytest.raises(OptimizerError):
        evaluate(opt, trial)
    assert opt.status()["trials"][0]["state"] == "failed"
    assert opt.status()["learning"]["unknown_events"] == 1


def test_candidate_and_call_bounds_are_durable(tmp_path):
    opt = controller(tmp_path, max_candidates=1, max_calls=2)
    initialize(opt)
    trial = freeze(opt, n=1)
    opt.cancel(trial.trial_id)
    reopened = controller(tmp_path, max_candidates=1, max_calls=2)
    with pytest.raises(OptimizerError):
        freeze(reopened, n=1)
    assert reopened.status()["calls_budget_spent"] == 2


def test_screening_is_learning_only_and_unknown_capture_is_not_zero(tmp_path):
    opt = controller(tmp_path)
    initialize(opt)
    candidates = opt.propose()

    class Screener:
        def decide(self, state, questions, *, data_classification):
            assert data_classification == "synthetic"
            assert state == {p.policy_id: "invented summary" for p in candidates}
            return Result(False, "transport_error", request_text="captured-request",
                          diagnostics=Diagnostics(attempts=1))

    selected = opt.propose(screener=Screener(),
                           summaries={p.policy_id: "invented summary" for p in candidates},
                           data_classification="synthetic", search_task_ids=["screen-data"])
    assert selected == candidates
    status = opt.status()
    assert status["learning"]["unknown_events"] == 1
    assert status["learning"]["deployments"] == 0
    assert status["learning"]["reference_tokens"] is None
    assert status["calls_budget_spent"] == 1


def test_screening_failure_full_bodies_are_counted_and_never_persisted(tmp_path):
    opt = controller(tmp_path)
    initialize(opt)
    proposals = opt.propose()

    class Screener:
        def decide(self, *args, **kwargs):
            return Result(False, "http_error", "sensitive request", "sensitive response",
                          diagnostics=Diagnostics(attempts=1, response_complete=True))

    opt.propose(screener=Screener(), summaries={p.policy_id: "invented" for p in proposals},
                data_classification="sanitized")
    learning = opt.status()["learning"]
    assert learning["complete_calls"] == 1
    assert learning["reference_tokens"] == (
        count_tokens("sensitive request") + count_tokens("sensitive response"))
    assert b"sensitive request" not in opt.path.read_bytes()
    assert b"sensitive response" not in opt.path.read_bytes()


def test_screening_exception_is_sanitized_and_budget_spent(tmp_path):
    opt = controller(tmp_path)
    initialize(opt)
    proposals = opt.propose()

    class Screener:
        def decide(self, *args, **kwargs):
            raise RuntimeError("raw-secret")

    assert opt.propose(screener=Screener(), summaries={p.policy_id: "x" for p in proposals},
                       data_classification="synthetic") == proposals
    assert "raw-secret" not in json.dumps(opt.status())
    assert opt.status()["calls_budget_spent"] == 1


def test_enabled_baseline_is_explicit(tmp_path):
    opt = controller(tmp_path)
    with pytest.raises(OptimizerError, match="enabled_baseline_required"):
        opt.initialize(RequestPolicy(), validator=baseline_check, validation_call_limit=0)


def test_pending_inventory_is_not_a_complete_learning_run(tmp_path):
    opt = controller(tmp_path)
    initialize(opt)
    trial = freeze(opt, n=2)
    status = opt.status()
    assert status["learning"]["unsealed_runs"] == 1
    assert status["learning"]["reference_tokens"] is None
    assert trial_inventory(opt, trial)["runs"] == [{
        "run_id": trial.learning_run_id, "kind": "confirmation",
        "state": "pending", "expected_task_ids": None,
    }]
    with pytest.raises(OptimizerError, match="unknown_learning_inventory"):
        opt.seal_learning_run(trial.learning_run_id)


def test_partial_run_exports_one_combined_trace_without_sealing(tmp_path):
    def partial(trial, task):
        if task.endswith("-1"):
            raise RuntimeError("no raw content")
        return pair(trial, task)
    opt = controller(tmp_path, partial)
    initialize(opt)
    trial = freeze(opt, n=3)
    with pytest.raises(OptimizerError):
        evaluate(opt, trial)
    inventory = trial_inventory(opt, trial)
    assert len(inventory["traces"]) == 1
    assert len(inventory["traces"][0].calls) == 2
    assert inventory["runs"][0]["expected_task_ids"] == ["fresh-0", "fresh-1", "fresh-2"]
    assert inventory["runs"][0]["state"] == "incomplete"
    status = opt.status()["learning"]
    assert status["known_reference_tokens"] == 100 and status["reference_tokens"] is None
    assert status["unknown_events"] == 2 and status["complete_calls"] == 2
    with pytest.raises(OptimizerError, match="incomplete_learning_inventory"):
        opt.seal_learning_run(trial.learning_run_id)

    ledger = TokenLedger(opt.config.measurement, horizon=DeploymentHorizon(
        "future-deploy", ("deploy-1",),
        tuple(r["run_id"] for r in opt.learning_inventory()["runs"])))
    opt.export_learning(ledger)
    summary = ledger.summary()
    assert summary["learning"]["tasks"] == 2  # Explicit zero-call baseline plus one pair.
    assert not summary["learning"]["by_run"][trial.learning_run_id]["inventory_sealed"]
    assert summary["all_in"]["status"] == "incomplete_horizon"
    assert summary["all_in"]["unsealed_learning_runs"] == [trial.learning_run_id]


def test_complete_inconclusive_learning_run_is_sealed_not_deployed(tmp_path):
    opt = controller(tmp_path)
    initialize(opt)
    trial = freeze(opt, n=2)
    assert evaluate(opt, trial).decision == "not_certified"
    inventory = trial_inventory(opt, trial)
    assert inventory["runs"][0]["state"] == "sealed"
    assert inventory["runs"][0]["expected_task_ids"] == ["fresh-0", "fresh-1"]
    assert opt.status()["learning"]["unsealed_runs"] == 0
    assert opt.status()["learning"]["reference_tokens"] == 200
    assert opt.status()["learning"]["deployments"] == 0
    ledger = TokenLedger(opt.config.measurement)
    opt.export_learning(ledger)
    summary = ledger.summary()
    assert summary["learning"]["tasks"] == 3  # Baseline and two combined paired tasks.
    assert summary["learning"]["by_run"][trial.learning_run_id]["inventory_sealed"]
    assert summary["learning"]["total_tokens"] == 200
    assert summary["deployment"]["calls"] == 0
    with pytest.raises(ValueError, match="sealed"):
        opt.export_learning(ledger)


def test_reused_model_call_ids_across_tasks_never_promote(tmp_path):
    def repeated(trial, task):
        obs = pair(trial, task)
        def trace(t):
            call = replace(t.calls[0], call_id=t.policy_id)
            return replace(t, calls=(call,), expected_call_ids=(call.call_id,))
        return replace(obs, incumbent=trace(obs.incumbent), candidate=trace(obs.candidate))
    opt = controller(tmp_path, repeated)
    initialize(opt)
    trial = freeze(opt, n=2)
    with pytest.raises(OptimizerError):
        evaluate(opt, trial)
    with pytest.raises(OptimizerError):
        opt.promote(trial.trial_id)
    with pytest.raises((OptimizerError, ValueError)):
        opt.seal_learning_run(trial.learning_run_id)


@pytest.mark.parametrize("defect", ["model", "cap", "coverage", "run", "hash", "task"])
def test_bad_independent_evaluator_output_fails_closed(tmp_path, defect):
    def bad(trial, task):
        obs = pair(trial, task)
        changes = {
            "model": {"model_id": "different-model"},
            "cap": {"reference_input_tokens": 101},
            "coverage": {"coverage": "partial"},
            "hash": {"input_sha256": None},
        }
        if defect in changes:
            call = replace(obs.candidate.calls[0], **changes[defect])
            return replace(obs, candidate=replace(obs.candidate, calls=(call,)))
        if defect == "run":
            return replace(obs, candidate=replace(obs.candidate, learning_run_id="foreign"))
        return replace(obs, task_id="foreign")
    opt = controller(tmp_path, bad)
    initialize(opt)
    trial = freeze(opt, n=1)
    with pytest.raises(OptimizerError, match="evaluation_failed"):
        evaluate(opt, trial)
    assert opt.status()["learning"]["reference_tokens"] is None
    assert opt.status()["trials"][0]["state"] == "failed"


def test_hill_climb_is_bounded_and_every_promotion_has_saved_certificate(tmp_path):
    opt = controller(tmp_path, max_candidates=2, max_calls=400)
    initialize(opt)
    result = opt.hill_climb(sample_size=100, fresh_tasks=lambda t:
                            [f"round-{t.round_id}-{i}" for i in range(t.sample_size)])
    assert len(result["trials"]) == 2 and result["calls_budget_spent"] == 400
    assert result["champion"]["version"] == 3
    with sqlite3.connect(opt.path) as db:
        assert db.execute("SELECT COUNT(*) FROM looks").fetchone()[0] == 2
    assert result["learning"]["unsealed_runs"] == 0


def test_screening_selection_is_advisory_and_captured_once(tmp_path, monkeypatch):
    count_inputs = []
    opt = Optimizer(tmp_path / "optimizer.sqlite", config=config(), evaluator=pair)
    # Instrument the private capture boundary without claiming a custom public counter.
    monkeypatch.setattr(opt, "_count", lambda text: count_inputs.append(text) or count_tokens(text))
    initialize(opt)
    candidates = opt.propose()

    class Screener:
        def decide(self, state, questions, **kwargs):
            keys = list(questions["proposal"]["criteria"])
            body = {"model": "jev-1.13.0", "usage": {"input_tokens": 99, "output_tokens": 9},
                    "answers": {"proposal": {
                        "type": "choice", "choice": candidates[-1].policy_id, "confidence": 1,
                        "probabilities": {key: int(key == candidates[-1].policy_id) for key in keys},
                    }}}
            return Result(True, "ok", "exact request", json.dumps(body), body,
                          Diagnostics(attempts=1, response_complete=True))

    ordered = opt.propose(screener=Screener(), summaries={p.policy_id: "x" for p in candidates},
                          data_classification="synthetic")
    assert ordered[0] == candidates[-1]
    assert len(count_inputs) == 2  # Each captured full string once.
    assert opt.status()["champion"]["version"] == 1
    assert all(r["state"] == "sealed" for r in opt.status()["learning"]["runs"])


def test_export_cannot_hide_an_unstarted_run_outside_horizon(tmp_path):
    opt = controller(tmp_path)
    initialize(opt)
    freeze(opt, n=1)
    ledger = TokenLedger(opt.config.measurement, horizon=DeploymentHorizon(
        "incomplete", ("deployment",), ()))
    with pytest.raises(OptimizerError, match="learning_run_outside_horizon"):
        opt.export_learning(ledger)


def test_hard_process_exit_spends_round_and_never_replays(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    opt = controller(tmp_path)
    initialize(opt)
    trial = freeze(opt, n=2)
    script = (
        "import os,sys; from brainspace.optimizer import Optimizer; "
        "o=Optimizer.open(sys.argv[1], evaluator=lambda t,k: os._exit(17)); "
        "o.evaluate(int(sys.argv[2]), ['crash-1','crash-2'])"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(opt.path), str(trial.trial_id)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 17
    reopened = controller(tmp_path)
    status = reopened.status()
    assert status["trials"][0]["state"] == "evaluating"
    assert status["learning"]["unknown_events"] == 2
    assert status["learning"]["reference_tokens"] is None
    with pytest.raises(OptimizerError):
        reopened.evaluate(trial.trial_id, ["crash-1", "crash-2"])
    reopened.cancel(trial.trial_id)
    second = freeze(reopened, n=1)
    with pytest.raises(OptimizerError):
        reopened.evaluate(second.trial_id, ["crash-1"])
    assert reopened.status()["budget"]["rounds"] == 2


def test_custom_counter_cannot_claim_exact_reference_measurement(tmp_path):
    from evals.synthetic_efficiency import synthetic_config
    with pytest.raises(OptimizerError, match="unsupported_reference_counter"):
        Optimizer(tmp_path / "forged.sqlite", config=synthetic_config(), count_reference=len)
    assert not (tmp_path / "forged.sqlite").exists()


@pytest.mark.parametrize("field,value", [
    ("tokenizer_id", "claimed-counter"),
    ("tokenizer_version", "wrong-version"),
    ("vocabulary_id", "wrong-vocabulary"),
    ("extraction_protocol_id", "canonicalized-response"),
    ("extraction_protocol_version", "0"),
    ("boundary", "provider-hidden-tokens"),
])
def test_custom_measurement_cannot_bypass_check_with_supplied_counter(tmp_path, field, value):
    from brainspace.tokens import count_tokens
    from evals.synthetic_efficiency import synthetic_config
    regime = synthetic_config()
    regime = replace(regime, measurement=replace(regime.measurement, **{field: value}))
    with pytest.raises(OptimizerError, match="counter_identity_mismatch"):
        Optimizer(tmp_path / "forged.sqlite", config=regime, count_reference=count_tokens)
    assert not (tmp_path / "forged.sqlite").exists()


def test_primary_and_jev_use_same_unchanged_complete_body_text_protocol(tmp_path):
    from brainspace.tokens import count_tokens
    from evals.synthetic_efficiency import synthetic_config
    regime = synthetic_config()
    assert regime.measurement.extraction_protocol_id == "complete-json-body-text/utf8-ordinary"
    assert regime.measurement.boundary == "logical-model-call-json-bodies"
    opt = Optimizer(tmp_path / "mixed.sqlite", config=regime)
    initialize(opt)
    candidates = opt.propose()
    raw_request = '{ "z": "café", "a": 1 }\n'
    raw_response = '{\n "error": "synthetic", "model": "jev-1.13.0"\n}\n'

    class Screener:
        def decide(self, *args, **kwargs):
            return Result(False, "http_error", raw_request, raw_response,
                          diagnostics=Diagnostics(attempts=1, response_complete=True))

    opt.propose(screener=Screener(), summaries={p.policy_id: "invented" for p in candidates},
                data_classification="synthetic")
    trace = next(t for t in opt.learning_inventory()["traces"] if t.calls)
    call = trace.calls[0]
    assert trace.measurement == regime.measurement
    assert call.reference_input_tokens == count_tokens(raw_request)
    assert call.reference_output_tokens == count_tokens(raw_response)
    assert call.input_sha256 == hashlib.sha256(raw_request.encode()).hexdigest()
    assert call.output_sha256 == hashlib.sha256(raw_response.encode()).hexdigest()
    assert call.output_sha256 != hashlib.sha256(
        json.dumps(json.loads(raw_response), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_old_protocol_registry_is_not_silently_relabeled(tmp_path):
    opt = controller(tmp_path)
    initialize(opt)
    freeze(opt, n=1)
    with sqlite3.connect(opt.path) as db:
        stored = json.loads(db.execute("SELECT value FROM opt_config").fetchone()[0])
        stored["measurement"]["extraction_protocol_id"] = (
            "chat-completions-v1/compact-request+canonical-response")
        db.execute("UPDATE opt_config SET value=?", (json.dumps(stored),))
    before = opt.path.read_bytes()
    with pytest.raises(OptimizerError, match="counter_identity_mismatch"):
        Optimizer.open(opt.path)
    assert opt.path.read_bytes() == before


def test_unavailable_reference_fails_closed_without_creating_registry(tmp_path, monkeypatch):
    from brainspace import tokens
    regime = config()

    def unavailable(boundary):
        raise tokens.ReferenceTokenizerUnavailable("verified local reference tokenizer unavailable")

    monkeypatch.setattr(tokens, "measurement_identity", unavailable)
    with pytest.raises(tokens.ReferenceTokenizerUnavailable):
        Optimizer(tmp_path / "missing-reference.sqlite", config=regime,
                  count_reference=tokens.count_tokens)
    assert not (tmp_path / "missing-reference.sqlite").exists()


def test_cross_round_call_replay_stays_incomplete_and_unsealable(tmp_path):
    def replay(trial, task):
        observation = pair(trial, task)
        def reused(trace, call_id):
            call = replace(trace.calls[0], call_id=call_id)
            return replace(trace, calls=(call,), expected_call_ids=(call_id,))
        return replace(observation,
                       incumbent=reused(observation.incumbent, "global-incumbent"),
                       candidate=reused(observation.candidate, "global-candidate"))
    opt = controller(tmp_path, replay)
    initialize(opt)
    first = freeze(opt, n=1)
    evaluate(opt, first, "first")
    second = freeze(opt, n=1)
    with pytest.raises(OptimizerError):
        evaluate(opt, second, "second")
    with pytest.raises((OptimizerError, ValueError)):
        opt.seal_learning_run(second.learning_run_id)
    learning = opt.status()["learning"]
    assert learning["complete_calls"] == 2
    assert learning["known_reference_tokens"] == 100
    assert learning["reference_tokens"] is None
    ledger = TokenLedger(opt.config.measurement)
    opt.export_learning(ledger)
    assert ledger.summary()["learning"]["calls"] == 2


def test_baseline_model_call_is_counted_and_limits_confirmation(tmp_path):
    opt = controller(tmp_path, max_calls=2)

    def validator(policy, regime, reservation):
        # Reproduce an actual 32-reference-token validation invocation.
        call = measure_call(
            regime.measurement, count_tokens, input_text="x " * 31, output_text="",
            call_id="baseline-check", task_id=reservation.task_id, attempt_id="1",
            phase="learning", role="verification", model_id=regime.model_id,
            harness_id="fixture-validator", coverage=COMPLETE, completion_status="succeeded",
        )
        assert call.reference_input_tokens == 32
        validation = baseline_check(policy, regime, reservation)
        return replace(validation, trace=replace(
            validation.trace, calls=(call,), expected_call_ids=(call.call_id,)))

    opt.initialize(RequestPolicy(enabled=True), validator=validator, validation_call_limit=1)
    assert opt.status()["calls_budget_spent"] == 1
    assert opt.status()["learning"]["reference_tokens"] == 32
    with pytest.raises(OptimizerError, match="call_budget_exhausted"):
        freeze(opt, n=1)


def model_baseline(policy, regime, reservation, *, call_id=None, passed=True):
    validation = baseline_check(policy, regime, reservation)
    call = measure_call(
        regime.measurement, count_tokens, input_text="x " * 31, output_text="",
        call_id=call_id or reservation.task_id + ":verification",
        task_id=reservation.task_id, attempt_id="1", phase="learning", role="verification",
        model_id=regime.model_id, harness_id="baseline-fixture", coverage=COMPLETE,
        completion_status="succeeded",
    )
    return replace(validation, passed=passed, trace=replace(
        validation.trace, calls=(call,), expected_call_ids=(call.call_id,)))


def test_baseline_allowance_and_inventory_exist_before_callback(tmp_path):
    opt = controller(tmp_path, max_calls=2)

    def validator(policy, regime, reservation):
        status = opt.status()
        assert not status["initialized"] and status["champion"] is None
        assert status["calls_budget_spent"] == 1
        assert status["baseline_attempts"][0]["state"] == "pending"
        assert reservation.call_limit == 1
        assert opt.learning_inventory()["runs"][0]["expected_task_ids"] == [reservation.task_id]
        with sqlite3.connect(opt.path) as db:
            assert db.execute("SELECT kind FROM tasks WHERE task_hash=?",
                              (hashlib.sha256(reservation.task_id.encode()).hexdigest(),)).fetchone() \
                == ("excluded",)
        return model_baseline(policy, regime, reservation)

    status = opt.initialize(RequestPolicy(enabled=True), validator=validator, validation_call_limit=1)
    assert status["calls_budget_spent"] == 1
    assert status["learning"]["complete_calls"] == status["learning"]["unique_complete_calls"] == 1
    assert status["learning"]["reference_tokens"] == 32
    assert controller(tmp_path, max_calls=2).status() == status


def test_explicit_empty_baseline_trace_is_sealed(tmp_path):
    opt = controller(tmp_path)
    status = initialize(opt)
    inventory = opt.learning_inventory()
    assert status["calls_budget_spent"] == 0
    assert len(inventory["traces"]) == 1 and inventory["traces"][0].calls == ()
    assert inventory["runs"][0]["kind"] == "baseline"
    assert inventory["runs"][0]["state"] == "sealed"


def test_rejected_baseline_has_measured_cost_and_spent_allowance(tmp_path):
    opt = controller(tmp_path, max_calls=2)
    with pytest.raises(OptimizerError, match="baseline_validation_failed"):
        opt.initialize(RequestPolicy(enabled=True), validation_call_limit=1,
                       validator=lambda p, c, r: model_baseline(p, c, r, passed=False))
    status = opt.status()
    assert status["champion"] is None and status["baseline_attempts"][0]["state"] == "rejected"
    assert status["calls_budget_spent"] == 1 and status["learning"]["reference_tokens"] == 32
    called = []
    with pytest.raises(OptimizerError, match="call_budget_exhausted"):
        opt.initialize(RequestPolicy(enabled=True), validation_call_limit=2,
                       validator=lambda *args: called.append(True))
    assert not called
    initialize(opt)
    with pytest.raises(OptimizerError, match="call_budget_exhausted"):
        freeze(opt, n=1)
    ledger = TokenLedger(opt.config.measurement)
    opt.export_learning(ledger)
    assert ledger.summary()["learning"]["total_tokens"] == 32


@pytest.mark.parametrize("failure", ["exception", "no_trace", "partial", "wrong_task", "wrong_run"])
def test_invalid_baseline_attempt_spends_budget_and_stays_unsealable(tmp_path, failure):
    opt = controller(tmp_path, max_calls=2)

    def validator(policy, regime, reservation):
        if failure == "exception":
            raise RuntimeError("raw secret must not escape")
        if failure == "no_trace":
            return True
        result = model_baseline(policy, regime, reservation)
        changes = {"partial": {"coverage": "partial"}, "wrong_task": {"task_id": "foreign"},
                   "wrong_run": {"learning_run_id": "foreign"}}
        return replace(result, trace=replace(result.trace, **changes[failure]))

    with pytest.raises(OptimizerError, match="baseline_validation_failed") as error:
        opt.initialize(RequestPolicy(enabled=True), validator=validator, validation_call_limit=1)
    assert "secret" not in str(error.value)
    reopened = controller(tmp_path, max_calls=2)
    status = reopened.status()
    assert status["calls_budget_spent"] == 1 and status["champion"] is None
    assert status["learning"]["reference_tokens"] is None
    assert status["learning"]["unknown_events"] == 1
    run = reopened.learning_inventory()["runs"][0]
    with pytest.raises(OptimizerError):
        reopened.seal_learning_run(run["run_id"])
    initialize(reopened)
    with pytest.raises(OptimizerError, match="call_budget_exhausted"):
        freeze(reopened, n=1)


def test_reported_baseline_call_overrun_is_charged_and_never_accepted(tmp_path):
    opt = controller(tmp_path, max_calls=2)

    def validator(policy, regime, reservation):
        result = model_baseline(policy, regime, reservation)
        first = result.trace.calls[0]
        second = replace(first, call_id="unallowed-extra-call")
        return replace(result, trace=replace(result.trace, calls=(first, second),
                                             expected_call_ids=(first.call_id, second.call_id)))

    with pytest.raises(OptimizerError):
        opt.initialize(RequestPolicy(enabled=True), validator=validator, validation_call_limit=1)
    assert opt.status()["calls_budget_spent"] == 2
    assert opt.status()["learning"]["reference_tokens"] is None
    called = []
    with pytest.raises(OptimizerError, match="call_budget_exhausted"):
        opt.initialize(RequestPolicy(enabled=True), validation_call_limit=1,
                       validator=lambda *args: called.append(True))
    assert not called


def test_global_call_ids_cover_baseline_to_confirmation(tmp_path):
    def evaluator(trial, task):
        obs = pair(trial, task)
        call = replace(obs.incumbent.calls[0], call_id="baseline-call")
        return replace(obs, incumbent=replace(obs.incumbent, calls=(call,),
                                             expected_call_ids=(call.call_id,)))
    opt = controller(tmp_path, evaluator)
    opt.initialize(RequestPolicy(enabled=True), validation_call_limit=1,
                   validator=lambda p, c, r: model_baseline(p, c, r, call_id="baseline-call"))
    trial = freeze(opt, n=1)
    with pytest.raises(OptimizerError):
        evaluate(opt, trial)
    with pytest.raises(OptimizerError):
        opt.seal_learning_run(trial.learning_run_id)
    assert opt.status()["learning"]["complete_calls"] == 1
    assert opt.status()["learning"]["known_reference_tokens"] == 32
    assert opt.status()["learning"]["reference_tokens"] is None
    ledger = TokenLedger(opt.config.measurement)
    opt.export_learning(ledger)
    assert ledger.summary()["learning"]["calls"] == 1


def test_global_call_ids_cover_rejected_baseline_to_baseline(tmp_path):
    opt = controller(tmp_path)
    for passed in (False, True):
        with pytest.raises(OptimizerError):
            opt.initialize(
                RequestPolicy(enabled=True), validation_call_limit=1,
                validator=lambda p, c, r: model_baseline(p, c, r, call_id="replay", passed=passed),
            )
    status = opt.status()
    assert status["champion"] is None and status["calls_budget_spent"] == 2
    assert status["learning"]["unique_complete_calls"] == 1
    assert status["learning"]["known_reference_tokens"] == 32
    assert status["learning"]["reference_tokens"] is None
    failed_run = next(r for r in opt.learning_inventory()["runs"] if r["state"] != "sealed")
    with pytest.raises(OptimizerError):
        opt.seal_learning_run(failed_run["run_id"])


def test_global_call_ids_cover_screen_to_confirmation(tmp_path):
    opt = controller(tmp_path)
    initialize(opt)
    proposals = opt.propose()

    class Screener:
        def decide(self, *args, **kwargs):
            return Result(False, "http_error", '{"request":1}', '{"error":1}',
                          diagnostics=Diagnostics(attempts=1, response_complete=True))

    opt.propose(screener=Screener(), summaries={p.policy_id: "synthetic" for p in proposals},
                data_classification="synthetic")
    screen = next(t for t in opt.learning_inventory()["traces"] if t.calls)
    call_id = screen.calls[0].call_id

    def evaluator(trial, task):
        obs = pair(trial, task)
        call = replace(obs.incumbent.calls[0], call_id=call_id)
        return replace(obs, incumbent=replace(obs.incumbent, calls=(call,),
                                             expected_call_ids=(call_id,)))
    reopened = controller(tmp_path, evaluator)
    trial = freeze(reopened, n=1)
    with pytest.raises(OptimizerError):
        evaluate(reopened, trial)
    with pytest.raises(OptimizerError):
        reopened.seal_learning_run(trial.learning_run_id)
    assert reopened.status()["learning"]["complete_calls"] == 1
    assert reopened.status()["learning"]["reference_tokens"] is None


def test_registry_rejection_after_capture_is_never_complete(tmp_path, monkeypatch):
    opt = controller(tmp_path)
    initialize(opt)
    trial = freeze(opt, n=1)

    def reject(*args):
        status = opt.status()
        assert status["learning"]["complete_calls"] == 0
        assert status["learning"]["reference_tokens"] is None
        with sqlite3.connect(opt.path) as db:
            assert db.execute("SELECT state FROM opt_learning WHERE trial_id=?",
                              (trial.trial_id,)).fetchone() == ("captured",)
            assert db.execute("SELECT COUNT(*) FROM opt_call_ids").fetchone()[0] == 2
        raise ValueError("registry rejects captured evidence")

    monkeypatch.setattr(opt._registry, "submit", reject)
    with pytest.raises(OptimizerError):
        evaluate(opt, trial)
    reopened = controller(tmp_path)
    with pytest.raises(OptimizerError):
        reopened.seal_learning_run(trial.learning_run_id)
    assert reopened.status()["learning"]["complete_calls"] == 0
    assert reopened.status()["learning"]["known_reference_tokens"] == 0
    assert reopened.status()["learning"]["reference_tokens"] is None
    ledger = TokenLedger(opt.config.measurement)
    reopened.export_learning(ledger)
    assert ledger.summary()["learning"]["calls"] == 0


def test_pre_trace_schema_is_rejected_without_resetting_alpha_history(tmp_path):
    opt = controller(tmp_path)
    initialize(opt)
    freeze(opt, n=1)
    before_budget = opt.status()["budget"]
    with sqlite3.connect(opt.path) as db:
        db.execute("DROP TABLE opt_accounting")  # Simulate an interim pre-trace fixture database.
    before = opt.path.read_bytes()
    with pytest.raises(OptimizerError, match="accounting_schema_mismatch"):
        Optimizer.open(opt.path)
    assert opt.path.read_bytes() == before
    with sqlite3.connect(opt.path) as db:
        assert db.execute("SELECT COUNT(*) FROM rounds").fetchone()[0] == before_budget["rounds"]


def test_concurrent_confirmation_global_call_reservation_is_atomic(tmp_path):
    from threading import Barrier
    barrier = Barrier(2)

    def evaluator(trial, task):
        obs = pair(trial, task)
        def reused(trace, name):
            call = replace(trace.calls[0], call_id=name)
            return replace(trace, calls=(call,), expected_call_ids=(name,))
        barrier.wait(timeout=10)
        return replace(obs, incumbent=reused(obs.incumbent, "concurrent-a"),
                       candidate=reused(obs.candidate, "concurrent-b"))

    opt = controller(tmp_path, evaluator)
    initialize(opt)
    first, second = freeze(opt, n=1), freeze(opt, n=1)
    reopened = controller(tmp_path, evaluator)

    def run(args):
        owner, trial, prefix = args
        try:
            evaluate(owner, trial, prefix)
            return True
        except OptimizerError:
            return False

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(run, [(opt, first, "one"), (reopened, second, "two")]))
    assert sorted(results) == [False, True]
    status = opt.status()
    assert status["learning"]["complete_calls"] == status["learning"]["unique_complete_calls"] == 2
    assert status["learning"]["known_reference_tokens"] == 100
    assert status["learning"]["reference_tokens"] is None
    failed = next(t for t in status["trials"] if t["state"] == "failed")
    with pytest.raises(OptimizerError):
        opt.seal_learning_run(f"trial-{failed['id']}")
    ledger = TokenLedger(opt.config.measurement)
    opt.export_learning(ledger)
    assert ledger.summary()["learning"]["calls"] == 2


def test_concurrent_baseline_allowance_is_reserved_before_second_validator(tmp_path):
    from threading import Event
    entered, release = Event(), Event()
    opt = controller(tmp_path, max_calls=1)
    other = controller(tmp_path, max_calls=1)

    def validator(policy, regime, reservation):
        entered.set()
        assert release.wait(timeout=10)
        return model_baseline(policy, regime, reservation)

    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(opt.initialize, RequestPolicy(enabled=True),
                             validator=validator, validation_call_limit=1)
        assert entered.wait(timeout=10)
        called = []
        try:
            with pytest.raises(OptimizerError, match="call_budget_exhausted"):
                other.initialize(RequestPolicy(enabled=True), validation_call_limit=1,
                                 validator=lambda *args: called.append(True))
        finally:
            release.set()
        assert future.result(timeout=10)["learning"]["reference_tokens"] == 32
    assert not called
    assert other.status()["calls_budget_spent"] == 1
    assert len(other.status()["baseline_attempts"]) == 1


def test_baseline_interruption_spends_allowance_and_preserves_unknown_inventory(tmp_path):
    opt = controller(tmp_path, max_calls=2)

    def interrupted(*args):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        opt.initialize(RequestPolicy(enabled=True), validator=interrupted, validation_call_limit=1)
    reopened = controller(tmp_path, max_calls=2)
    status = reopened.status()
    assert status["baseline_attempts"][0]["state"] == "cancelled"
    assert status["calls_budget_spent"] == 1 and status["learning"]["reference_tokens"] is None
    with pytest.raises(OptimizerError):
        reopened.seal_learning_run(status["baseline_attempts"][0]["task_id"])
    initialize(reopened)
    with pytest.raises(OptimizerError, match="call_budget_exhausted"):
        freeze(reopened, n=1)


def test_baseline_hard_process_exit_does_not_erase_reserved_allowance(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    opt = controller(tmp_path, max_calls=2)
    script = (
        "import os,sys; from brainspace.optimizer import Optimizer; "
        "from brainspace.request_policy import RequestPolicy; "
        "o=Optimizer.open(sys.argv[1]); "
        "o.initialize(RequestPolicy(enabled=True), validation_call_limit=1, "
        "validator=lambda p,c,r: os._exit(19))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(opt.path)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 19
    reopened = controller(tmp_path, max_calls=2)
    status = reopened.status()
    assert status["baseline_attempts"][0]["state"] == "pending"
    assert status["calls_budget_spent"] == 1 and status["learning"]["unknown_events"] == 1
    assert status["learning"]["reference_tokens"] is None
    initialize(reopened)
    with pytest.raises(OptimizerError, match="call_budget_exhausted"):
        freeze(reopened, n=1)


@pytest.mark.parametrize("collision_first", [True, False])
def test_mixed_collision_consumes_new_ids_before_rejection_and_blocks_later_promotion(
    tmp_path, collision_first,
):
    def named(trace, name):
        call = replace(trace.calls[0], call_id=name)
        return replace(trace, calls=(call,), expected_call_ids=(name,))

    def evaluator(trial, task):
        obs = pair(trial, task)
        if task.startswith("mixed"):
            names = ("baseline-owned", "newly-exposed")
            if not collision_first:
                names = names[::-1]
        else:
            names = ("newly-exposed", f"later-fresh-{task}")
        return replace(obs, incumbent=named(obs.incumbent, names[0]),
                       candidate=named(obs.candidate, names[1]))

    opt = controller(tmp_path, evaluator)
    opt.initialize(RequestPolicy(enabled=True), validation_call_limit=1,
                   validator=lambda p, c, r: model_baseline(p, c, r, call_id="baseline-owned"))
    first = freeze(opt, n=1)
    with pytest.raises(OptimizerError):
        evaluate(opt, first, "mixed")
    with sqlite3.connect(opt.path) as db:
        owner = db.execute("SELECT event_id FROM opt_call_ids WHERE call_hash=?",
                           (hashlib.sha256(b"newly-exposed").hexdigest(),)).fetchone()
    assert owner == (f"trial-{first.trial_id}:mixed-0",)
    reopened = controller(tmp_path, evaluator)
    second = freeze(reopened, n=100)
    with pytest.raises(OptimizerError):
        evaluate(reopened, second, "replay")
    for trial in (first, second):
        with pytest.raises(OptimizerError):
            reopened.promote(trial.trial_id)
        with pytest.raises(OptimizerError):
            reopened.seal_learning_run(trial.learning_run_id)
    status = reopened.status()
    assert status["champion"]["version"] == 1
    assert status["budget"]["rounds"] == 2
    assert status["learning"]["complete_calls"] == 1
    assert status["learning"]["known_reference_tokens"] == 32
    assert status["learning"]["reference_tokens"] is None
    with sqlite3.connect(opt.path) as db:
        assert db.execute("SELECT COUNT(*) FROM looks").fetchone()[0] == 0


@pytest.mark.parametrize("collision_first", [True, False])
def test_rejected_mixed_baseline_consumes_every_new_call_id(tmp_path, collision_first):
    opt = controller(tmp_path)
    with pytest.raises(OptimizerError):
        opt.initialize(RequestPolicy(enabled=True), validation_call_limit=1,
                       validator=lambda p, c, r: model_baseline(
                           p, c, r, call_id="already-seen", passed=False))

    def mixed(policy, regime, reservation):
        result = model_baseline(policy, regime, reservation, call_id="already-seen")
        old = result.trace.calls[0]
        new = replace(old, call_id="baseline-new")
        calls = (old, new) if collision_first else (new, old)
        return replace(result, trace=replace(result.trace, calls=calls,
                                             expected_call_ids=tuple(c.call_id for c in calls)))

    with pytest.raises(OptimizerError):
        opt.initialize(RequestPolicy(enabled=True), validation_call_limit=2, validator=mixed)
    reopened = controller(tmp_path)
    with pytest.raises(OptimizerError):
        reopened.initialize(RequestPolicy(enabled=True), validation_call_limit=1,
                            validator=lambda p, c, r: model_baseline(
                                p, c, r, call_id="baseline-new"))
    assert reopened.status()["champion"] is None
    assert reopened.status()["calls_budget_spent"] == 4
    assert reopened.status()["learning"]["reference_tokens"] is None
    assert reopened.status()["learning"]["complete_calls"] == 1
    for run in reopened.learning_inventory()["runs"]:
        if run["state"] != "sealed":
            with pytest.raises(OptimizerError):
                reopened.seal_learning_run(run["run_id"])


@pytest.mark.parametrize("collision_first", [True, False])
@pytest.mark.parametrize("kind", ["baseline", "screening", "confirmation"])
def test_shared_staging_commits_all_unseen_siblings_before_raising(tmp_path, kind, collision_first):
    opt = controller(tmp_path)
    opt.initialize(RequestPolicy(enabled=True), validation_call_limit=1,
                   validator=lambda p, c, r: model_baseline(p, c, r, call_id="owned-collision"))
    baseline_event = opt.status()["baseline_attempts"][0]["task_id"]
    # Use the common staging boundary for all event kinds. Screening normally
    # reports only one pre-reserved call; exercise a hostile mixed trace too.
    event = "hostile-" + kind
    with opt._transaction() as db:
        db.execute("""INSERT INTO opt_learning(event_id,kind,task_id,state,coverage)
                      VALUES(?,?,?,'pending','unknown')""", (event, kind, event))
        db.execute("INSERT INTO opt_learning_runs VALUES(?,?,NULL,?,'pending')",
                   (event, kind, json.dumps([event])))
    names = ["owned-collision", "new-a", "new-b"]
    if not collision_first:
        names.reverse()
    calls = tuple(measure_call(
        opt.config.measurement, count_tokens, input_text="{}", output_text="{}",
        call_id=name, task_id=event, attempt_id="1", phase="learning",
        role="auxiliary", model_id="fixture-model-v1", harness_id="test",
        coverage=COMPLETE, completion_status="succeeded",
    ) for name in names)
    trace = TaskTrace(event, "test-policy", opt.config.measurement, "learning",
                      calls, tuple(names), COMPLETE, event)
    with pytest.raises(OptimizerError):
        opt._stage_event(event, trace)
    with sqlite3.connect(opt.path) as db:
        for name in ("new-a", "new-b"):
            assert db.execute("SELECT event_id FROM opt_call_ids WHERE call_hash=?",
                              (hashlib.sha256(name.encode()).hexdigest(),)).fetchone() == (event,)
        assert db.execute("SELECT event_id FROM opt_call_ids WHERE call_hash=?",
                          (hashlib.sha256(b"owned-collision").hexdigest(),)).fetchone() \
            == (baseline_event,)
        assert db.execute("SELECT state,coverage,records_json FROM opt_learning WHERE event_id=?",
                          (event,)).fetchone() == ("invalid", "unknown", None)
    with pytest.raises(OptimizerError):
        opt.seal_learning_run(event)


@pytest.mark.parametrize("failure", ["partial", "wrong_task", "wrong_model", "duplicate_in_pair"])
def test_invalid_pair_validation_cannot_resurrect_reported_ids(tmp_path, failure):
    def evaluator(trial, task):
        obs = pair(trial, task)
        first = replace(obs.incumbent.calls[0], call_id="exposed-before-validation")
        candidate = obs.candidate
        if failure == "duplicate_in_pair":
            second = replace(candidate.calls[0], call_id=first.call_id)
            candidate = replace(candidate, calls=(second,), expected_call_ids=(second.call_id,))
        if failure == "wrong_model":
            first = replace(first, model_id="wrong")
        incumbent = replace(obs.incumbent, calls=(first,), expected_call_ids=(first.call_id,))
        obs = replace(obs, incumbent=incumbent, candidate=candidate)
        if failure == "partial":
            obs = replace(obs, incumbent=replace(incumbent, coverage="partial"))
        if failure == "wrong_task":
            obs = replace(obs, task_id="foreign")
        return obs

    opt = controller(tmp_path, evaluator)
    initialize(opt)
    trial = freeze(opt, n=1)
    with pytest.raises(OptimizerError):
        evaluate(opt, trial)
    with sqlite3.connect(opt.path) as db:
        assert db.execute("SELECT event_id FROM opt_call_ids WHERE call_hash=?",
                          (hashlib.sha256(b"exposed-before-validation").hexdigest(),)).fetchone() \
            == (f"trial-{trial.trial_id}:fresh-0",)
    assert opt.status()["learning"]["reference_tokens"] is None
    with pytest.raises(OptimizerError):
        opt.seal_learning_run(trial.learning_run_id)


@pytest.mark.parametrize("failure", ["partial", "wrong_task", "wrong_run", "over_limit"])
def test_invalid_baseline_validation_cannot_resurrect_reported_ids(tmp_path, failure):
    opt = controller(tmp_path)

    def validator(policy, regime, reservation):
        result = model_baseline(policy, regime, reservation, call_id="rejected-baseline-id")
        changes = {"partial": {"coverage": "partial"}, "wrong_task": {"task_id": "foreign"},
                   "wrong_run": {"learning_run_id": "foreign"}, "over_limit": {}}
        return replace(result, trace=replace(result.trace, **changes[failure]))

    with pytest.raises(OptimizerError):
        opt.initialize(RequestPolicy(enabled=True), validator=validator,
                       validation_call_limit=0 if failure == "over_limit" else 1)
    reopened = controller(tmp_path)
    with pytest.raises(OptimizerError):
        reopened.initialize(RequestPolicy(enabled=True), validation_call_limit=1,
                            validator=lambda p, c, r: model_baseline(
                                p, c, r, call_id="rejected-baseline-id"))
    assert reopened.status()["champion"] is None
    assert reopened.status()["learning"]["reference_tokens"] is None
    assert reopened.status()["learning"]["complete_calls"] == 0
