"""Offline ground-truth fixture, NOT evidence of real-model quality/performance.

The toy responder has a deliberately limited 200-character tool-result reader.
A long synthetic tool result yields "unresolved"; a reversible policy-produced
summary makes its label visible. An independent oracle compares against the
label derived from the task identity. This favorable constructed workload tests
the full acceptance pipeline without weakening the strict equal-quality gate.
"""
from dataclasses import asdict
import hashlib
import json

from brainspace.certification import PairedObservation, VerifiedOutcome
from brainspace.optimizer import BaselineValidation, OptimizerConfig, reference_measurement
from brainspace.request_policy import PROTOCOL, RequestPolicy, TransformResult, plan_request
from brainspace.token_ledger import COMPLETE, TaskTrace, measure_call
from brainspace.tokens import count_tokens, serialize

ORACLE = "synthetic-label-oracle-v1"
MODEL = "synthetic-200-char-reader-v1"
WORKLOAD = "synthetic-long-tool-label-v1"
BASELINE_TASK = "synthetic-baseline-validation-v1"


def synthetic_config():
    # Count the actual insertion-order RequestPlan.serialized string unchanged.
    # Fixture-generated response JSON and optional raw Jev responses use the same
    # full-body-text measurement; the counter never recanonicalizes either.
    return OptimizerConfig(
        measurement=reference_measurement(), oracle_id=ORACLE, workload_id=WORKLOAD,
        model_id=MODEL, environment_id="offline-fixture-v1", token_cap=1024,
        minimum_token_reduction=1, max_candidates=6, max_calls=4096,
        calls_per_pair=2, synthetic_only=True,
    )


def _label(task_id):
    return hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:8]


def _request(task_id):
    text = ("answer=" + _label(task_id) + "\n" + "a " * 600)[:960]
    return {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Return the label visible in the earlier tool result."},
            {"role": "user", "content": "Summarize the synthetic lookup."},
            {"role": "assistant", "content": None, "tool_calls": [{
                "id": "old", "type": "function",
                "function": {"name": "lookup", "arguments": "{}"},
            }]},
            {"role": "tool", "tool_call_id": "old", "content": text},
            {"role": "assistant", "content": None, "tool_calls": [{
                "id": "recent", "type": "function",
                "function": {"name": "lookup", "arguments": "{}"},
            }]},
            {"role": "tool", "tool_call_id": "recent", "content": "Latest unrelated context."},
        ],
        "max_tokens": 64,
    }


def _plan(policy, task_id):
    originals = {}

    def transform(text):
        reference = "[recovery:" + hashlib.sha256(text.encode()).hexdigest()[:12] + "]"
        originals[reference] = text
        return TransformResult(text.splitlines()[0] + " " + reference, reference)

    return plan_request(
        _request(task_id), policy=policy, protocol=PROTOCOL, intent="overview",
        transform=transform, recover=originals.__getitem__, count=count_tokens,
        stable_prefix_messages=2,
    )


def validate_baseline(policy, config, reservation):
    """Fixture-only baseline safety check; no claim of strong baseline quality."""
    plan = _plan(policy, BASELINE_TASK)
    original = _request(BASELINE_TASK)
    passed = (
        policy.enabled and policy.recovery_required
        and config.oracle_id == ORACLE and config.model_id == MODEL
        and plan.request["messages"][:2] == original["messages"][:2]
        and plan.request["messages"][-1] == original["messages"][-1]
        and plan.serialized is not None
        and count_tokens(plan.serialized) + 64 <= config.token_cap
    )
    return BaselineValidation(
        policy.policy_id, config.identity, config.oracle_id, passed,
        hashlib.sha256(serialize({"fixture": BASELINE_TASK, "passed": passed,
                                  "policy": policy.to_dict()}).encode()).hexdigest(),
        TaskTrace(
            reservation.task_id, policy.policy_id, config.measurement, "learning",
            (), (), COMPLETE, reservation.learning_run_id,
        ),
    )


def evaluate_pair(trial, task_id):
    spec = trial.comparison
    if spec.oracle_id != ORACLE:
        raise ValueError("synthetic_oracle_mismatch")

    def run(policy):
        plan = _plan(policy, task_id)
        if plan.serialized is None:
            raise ValueError("synthetic_request_not_materialized")
        # The actual fixture request is parsed from the captured submitted text.
        submitted = json.loads(plan.serialized)
        tool_text = submitted["messages"][3]["content"]
        answer = tool_text.split()[0].removeprefix("answer=") if len(tool_text) <= 200 else "unresolved"
        response = serialize({"model": MODEL, "answer": answer})
        # Independent outcome oracle uses task ground truth, never a Jev score
        # or the responder's own assertion of confidence/correctness.
        success = json.loads(response)["answer"] == _label(task_id)
        call = measure_call(
            spec.measurement, count_tokens, input_text=plan.serialized, output_text=response,
            call_id=f"fixture:{task_id}:{policy.policy_id}", task_id=task_id,
            attempt_id="1", phase="learning", role="primary", model_id=MODEL,
            harness_id="synthetic-wire-fixture-v1", coverage=COMPLETE,
            completion_status="succeeded",
        )
        trace = TaskTrace(
            task_id, policy.policy_id, spec.measurement, "learning", (call,), (call.call_id,),
            COMPLETE, trial.learning_run_id,
        )
        if trace.totals().total_tokens > spec.token_cap:
            raise ValueError("synthetic_cap_exceeded")
        outcome = VerifiedOutcome(
            task_id, policy.policy_id, ORACLE, success,
            hashlib.sha256(serialize({
                "expected": _label(task_id), "observed": answer,
                "trace": asdict(trace), "oracle": ORACLE,
            }).encode()).hexdigest(),
        )
        return trace, outcome

    incumbent, incumbent_outcome = run(trial.incumbent)
    candidate, candidate_outcome = run(trial.candidate)
    return PairedObservation(task_id, incumbent, candidate, incumbent_outcome, candidate_outcome)


def baseline_policy():
    return RequestPolicy(enabled=True)
