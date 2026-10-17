"""Offline R4 seam checks: real runtime/counter, fake transport, private oracle."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from brainspace import learning_runtime as learning, runtime, tokens
from brainspace.learning_runtime import (
    CheckedOutcome, RuntimeLearningManifest, RuntimePairEvaluator, learn_once,
)
from brainspace.optimizer import (
    BaselineValidation, EvaluationAttemptFailed, EvaluationAttemptInterrupted,
    FrozenTrial, Optimizer, OptimizerConfig, OptimizerError, reference_measurement,
)
from brainspace.request_policy import RequestPolicy
from brainspace.runtime import RuntimeSession
from brainspace.token_ledger import COMPLETE, TaskTrace
from brainspace.transport import Reply


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def config(max_calls_per_arm=2, **changes):
    return OptimizerConfig(**{
        "measurement": reference_measurement(), "oracle_id": "private-test-oracle-v1",
        "workload_id": "synthetic-test-workload", "model_id": "offline-fixture-model",
        "environment_id": "fake-transport-v1", "token_cap": 10000,
        "calls_per_pair": max_calls_per_arm * 2, "max_calls": 100,
        "synthetic_only": True, **changes,
    })


INCUMBENT = RequestPolicy(version="request-policy-v3", enabled=True, min_tool_chars=512)
CANDIDATE = replace(INCUMBENT, min_tool_chars=640)


def trial(cfg, **changes):
    return FrozenTrial(**{
        "trial_id": 1, "round_id": 1, "incumbent_version": 1,
        "comparison": cfg.comparison(CANDIDATE.policy_id, INCUMBENT.policy_id),
        "incumbent": INCUMBENT, "candidate": CANDIDATE, "sample_size": 1,
        "calls_per_pair": cfg.calls_per_pair, **changes,
    })


class FakeTransport:
    """Explicit fake authority, no socket/client/provider implementation."""
    model = "offline-fixture-model"
    allow_network = True
    base_url = "http://127.0.0.1:1/not-used"
    reasoning_effort = None
    max_request_bytes = 524288
    max_response_bytes = 524288
    max_output_tokens = 1024
    timeout = 1

    def __init__(self, host, arm):
        self.host, self.arm, self.sent = host, arm, []

    def encode(self, chat):
        return tokens.serialize({**deepcopy(chat), "max_output_tokens": self.max_output_tokens})

    def send(self, wire):
        self.sent.append(wire)
        if self.host.fail_arm == self.arm:
            if self.host.failure == "interrupt":
                raise KeyboardInterrupt("private cancellation detail")
            if self.host.failure == "partial":
                return Reply(False, "transport_error", input_text=wire)
            if self.host.failure == "exception":
                raise TimeoutError("sensitive transport detail")
            if self.host.failure == "no_submission":
                return Reply(False, "network_not_allowed")
            if self.host.failure == "http":
                return Reply(False, "http_error", True, wire, "upstream failed", None, 500)
            if self.host.failure in ("model_mismatch", "hidden_model_mismatch"):
                body = {"model": "different-model", "output": "not from the declared regime"}
                reason = "model_mismatch" if self.host.failure == "model_mismatch" else "http_error"
                return Reply(False, reason, True, wire, json.dumps(body), body, 200)
        body = {"model": self.model, "output": "candidate text", "usage": {
            "input_tokens": 11, "output_tokens": 7, "total_tokens": 18}}
        text = json.dumps(body, ensure_ascii=False, indent=2)
        return Reply(True, "ok", True, wire, text, body, 200)


class Host:
    identity = "trusted-offline-test-host-v1"

    def __init__(self):
        self.events, self.sessions, self.prepared = [], {}, {}
        self.fail_arm, self.failure = None, None
        self.authority = True
        self.check_success = {"incumbent": True, "candidate": True}
        self.mutate = None
        self.transport_overrides = {}
        self.source_changed = False
        self.model_calls = 1
        self.zero_calls = False
        self.different_request = False

    def task_digest(self, task_id):
        return digest(task_id + ("changed" if self.source_changed else "-fixture-v1"))

    def prepare(self, task_id, arm_root):
        arm = arm_root.name
        self.events.append(("prepare", task_id, arm))
        assert (arm_root.parent / "pair-plan.json").is_file()
        workspace = arm_root / "workspace"
        workspace.mkdir()
        (workspace / "source.txt").write_text("immutable synthetic input", encoding="utf-8")
        transport = FakeTransport(self, arm)
        transport.allow_network = self.authority
        for key, value in self.transport_overrides.items():
            setattr(transport, key, value)
        prepared = SimpleNamespace(workspace=workspace, transport=transport, arm=arm)
        self.prepared[arm] = prepared
        return prepared

    def drive(self, task_id, session, prepared):
        assert type(session) is RuntimeSession
        assert all(x in self.prepared for x in ("incumbent", "candidate"))
        assert (session.output.parent.parent / "prepared.json").is_file()
        self.events.append(("drive", task_id, prepared.arm))
        self.sessions[prepared.arm] = session
        messages = [{"role": "system", "content": "Fixed protected instructions."},
                    {"role": "user", "content": "Answer from source."}]
        if self.different_request and prepared.arm == "candidate":
            messages[0]["content"] = "Changed protected instruction."
        for _ in range(0 if self.zero_calls else self.model_calls):
            session.invoke({"model": prepared.transport.model, "messages": deepcopy(messages),
                            "tools": []})
            messages.append({"role": "assistant", "content": "continuation"})
        if self.mutate == "drive_source":
            self.source_changed = True
        if self.mutate == "capture":
            path = session.output / "captures.jsonl"
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            rows[0]["input"] += " "
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        if self.mutate == "missing_capture":
            (session.output / "captures.jsonl").unlink()
        return {"answer": 7}

    def check(self, task_id, artifacts, prepared):
        self.events.append(("check", task_id, prepared.arm))
        session = self.sessions[prepared.arm]
        assert session._closed and session._finished
        if self.mutate == "oracle_artifacts":
            artifacts["answer"] = 99
        if self.mutate == "oracle_workspace":
            (prepared.workspace / "source.txt").write_text("changed", encoding="utf-8")
        if self.mutate == "oracle_receipt":
            (session.output / "result.json").write_text("{}", encoding="utf-8")
        if self.mutate == "oracle_previous_capture" and prepared.arm == "candidate":
            (self.sessions["incumbent"].output / "captures.jsonl").write_text("", encoding="utf-8")
        if self.mutate == "oracle_next_workspace" and prepared.arm == "incumbent":
            (self.prepared["candidate"].workspace / "source.txt").write_text("changed", encoding="utf-8")
        if self.mutate == "oracle_pair_plan":
            (session.output.parent.parent / "pair-plan.json").write_text("{}", encoding="utf-8")
        if self.mutate == "oracle_manifest":
            (prepared.workspace.parents[2] / "learning-manifest.json").write_text("{}", encoding="utf-8")
        if self.mutate == "unknown":
            return None
        return CheckedOutcome(self.check_success[prepared.arm], digest("independent check evidence"))


def setup(tmp_path, host=None, *, tasks=("fresh",), cfg=None):
    host = host or Host()
    cfg = cfg or config()
    manifest = RuntimeLearningManifest(
        cfg, host.identity, tuple((t, host.task_digest(t)) for t in tasks), cfg.calls_per_pair // 2)
    evaluator = RuntimePairEvaluator(manifest, host=host, output_root=tmp_path / "pairs")
    return host, manifest, evaluator, trial(cfg)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_pair_uses_native_identity_exact_policy_and_recounted_bytes(tmp_path):
    host, manifest, evaluate, frozen = setup(tmp_path)
    observation = evaluate(frozen, "fresh")
    observation.validate(frozen.comparison)
    assert [event[0] for event in host.events] == ["prepare", "prepare", "drive", "check", "drive", "check"]
    calls = []
    for arm, trace in (("incumbent", observation.incumbent),
                       ("candidate", observation.candidate)):
        session = host.sessions[arm]
        assert trace.task_id == session.task_id == "fresh"
        assert trace.policy_id == getattr(frozen, arm).policy_id == session.policy_id
        assert trace.learning_run_id == frozen.learning_run_id
        assert trace.phase == "learning"
        assert session.backend == "local" and session.ponytail is None and session.mode is None
        assert trace.expected_call_ids == (session.run_id + ":1",)
        capture = json.loads((session.output / "captures.jsonl").read_text())
        assert capture["input"] == session.transport.sent[0]
        call = trace.calls[0]
        assert call.reference_input_tokens == tokens.count_tokens(capture["input"])
        assert call.reference_output_tokens == tokens.count_tokens(capture["output"])
        assert call.input_sha256 == digest(capture["input"])
        assert call.output_sha256 == digest(capture["output"])
        assert read_json(session.output / "result.json")["quality_verified"] is None
        assert read_json(session.output / "cleanup.json")["complete"] is True
        calls.append(call.call_id)
    assert calls[0] != calls[1]
    assert read_json(evaluate.output_root / "learning-manifest.json")["identity"] == manifest.identity
    assert all(x.success is True for x in (observation.incumbent_outcome, observation.candidate_outcome))


def test_frozen_values_and_exact_both_arm_allocation(tmp_path):
    _, manifest, _, _ = setup(tmp_path)
    with pytest.raises(FrozenInstanceError):
        manifest.order_seed = 3
    with pytest.raises(FrozenInstanceError):
        CheckedOutcome(True, "a" * 64).success = False
    with pytest.raises(ValueError, match="both_arm"):
        replace(manifest, max_calls_per_arm=1)
    with pytest.raises(ValueError, match="immutable_task"):
        replace(manifest, task_digests=list(manifest.task_digests))
    with pytest.raises(ValueError, match="duplicate_task"):
        replace(manifest, task_digests=manifest.task_digests * 2)
    with pytest.raises(ValueError, match="invalid_checked"):
        CheckedOutcome(None, "a" * 64)
    with pytest.raises(ValueError, match="invalid_checked"):
        CheckedOutcome(False, "not-evidence")


def test_counterbalanced_order_frozen_before_any_calls(tmp_path):
    host, manifest, evaluate, frozen = setup(tmp_path, tasks=("a", "b"))
    orders = [manifest.arm_order(task) for task in ("a", "b")]
    assert {order[0] for order in orders} == {"incumbent", "candidate"}
    assert orders == [replace(manifest).arm_order(task) for task in ("a", "b")]
    saved = read_json(evaluate.output_root / "learning-manifest.json")
    for task in ("a", "b"):
        host.prepared.clear()
        evaluate(frozen, task)
        actual = [event[2] for event in host.events if event[:2] == ("drive", task)]
        assert actual == saved["orders"][task]


def test_complete_incorrect_answer_is_a_valid_negative_observation(tmp_path):
    host, _, evaluate, frozen = setup(tmp_path)
    host.check_success["candidate"] = False
    result = evaluate(frozen, "fresh")
    assert result.candidate_outcome.success is False and result.incumbent_outcome.success is True
    result.candidate.validate_complete()


@pytest.mark.parametrize("failure", ["partial", "exception", "interrupt"])
def test_candidate_failure_retains_completed_incumbent_and_missing_call(tmp_path, failure):
    host, _, evaluate, frozen = setup(tmp_path)
    host.fail_arm, host.failure = "candidate", failure
    expected = EvaluationAttemptInterrupted if failure == "interrupt" else EvaluationAttemptFailed
    with pytest.raises(expected) as caught:
        evaluate(frozen, "fresh")
    error = caught.value
    assert len(error.traces) == 2 and error.receipt_sha256s
    first, second = error.traces
    assert first.policy_id == INCUMBENT.policy_id and first.totals().total_tokens > 0
    assert second.policy_id == CANDIDATE.policy_id and len(second.expected_call_ids) == 1
    assert second.calls == () and second.coverage == "partial"
    assert all(session._closed for session in host.sessions.values())
    assert not list(evaluate.output_root.rglob("observation.json"))
    assert "sensitive" not in str(error) and "private cancellation" not in str(error)
    assert not any(event == ("check", "fresh", "candidate") for event in host.events)


def test_complete_http_failure_costs_are_counted_and_checked(tmp_path):
    host, _, evaluate, frozen = setup(tmp_path)
    host.fail_arm, host.failure = "candidate", "http"
    host.check_success["candidate"] = False
    result = evaluate(frozen, "fresh")
    assert result.candidate.calls[0].completion_status == "failed"
    assert result.candidate.calls[0].reference_output_tokens == tokens.count_tokens("upstream failed")
    assert result.candidate_outcome.success is False


@pytest.mark.parametrize("authority,changes", [
    (False, {}), (True, {"model": "other-model"}), (True, {"max_request_bytes": None}),
])
def test_missing_authority_or_wrong_regime_rejects_before_dispatch(tmp_path, authority, changes):
    host = Host()
    host.authority, host.transport_overrides = authority, changes
    _, _, evaluate, frozen = setup(tmp_path, host)
    with pytest.raises(EvaluationAttemptFailed) as caught:
        evaluate(frozen, "fresh")
    assert not host.sessions and caught.value.traces == ()


@pytest.mark.parametrize("mutation", [
    "oracle_artifacts", "oracle_workspace", "oracle_receipt", "unknown",
    "capture", "missing_capture", "drive_source",
])
def test_unknown_or_changed_evidence_fails_closed_retaining_costs(tmp_path, mutation):
    host, _, evaluate, frozen = setup(tmp_path)
    host.mutate = mutation
    with pytest.raises(EvaluationAttemptFailed) as caught:
        evaluate(frozen, "fresh")
    assert sum(len(t.calls) for t in caught.value.traces) == 1
    assert all(session._closed for session in host.sessions.values())
    assert not list(evaluate.output_root.rglob("observation.json"))


def test_missing_capture_ack_retains_known_runtime_cost_but_no_observation(tmp_path, monkeypatch):
    host, _, evaluate, frozen = setup(tmp_path)
    append = runtime.append_receipt

    def fail_ack(path, value):
        if path.name == "invocations.jsonl" and value.get("state") == "captured":
            raise OSError("simulated lost ack")
        return append(path, value)

    monkeypatch.setattr(runtime, "append_receipt", fail_ack)
    with pytest.raises(EvaluationAttemptFailed) as caught:
        evaluate(frozen, "fresh")
    trace = caught.value.traces[0]
    assert len(trace.calls) == 1 and trace.coverage == "partial"
    assert trace.calls[0].reference_input_tokens > 0
    assert host.sessions["incumbent"]._closed


def test_source_fingerprint_change_fails_before_prepare(tmp_path, monkeypatch):
    host, _, evaluate, frozen = setup(tmp_path)
    monkeypatch.setattr(learning, "_sources", lambda: {"changed.py": "a" * 64})
    with pytest.raises(ValueError, match="runtime_source_changed"):
        evaluate(frozen, "fresh")
    assert host.events == []


def test_manifest_task_change_rejected_before_prepare(tmp_path):
    host, _, evaluate, frozen = setup(tmp_path)
    host.source_changed = True
    with pytest.raises(ValueError, match="task_source_changed"):
        evaluate(frozen, "fresh")
    assert host.events == []


def test_transport_regime_cannot_change_between_task_pairs(tmp_path):
    host, _, evaluate, frozen = setup(tmp_path, tasks=("a", "b"))
    evaluate(frozen, "a")
    host.transport_overrides["max_output_tokens"] = 512
    prior = len([event for event in host.events if event[0] == "drive"])
    with pytest.raises(EvaluationAttemptFailed):
        evaluate(frozen, "b")
    assert len([event for event in host.events if event[0] == "drive"]) == prior


@pytest.mark.parametrize("failed", [False, True])
def test_same_task_cannot_replay_after_success_or_failure(tmp_path, failed):
    host, _, evaluate, frozen = setup(tmp_path)
    if failed:
        host.fail_arm, host.failure = "candidate", "partial"
        with pytest.raises(EvaluationAttemptFailed):
            evaluate(frozen, "fresh")
    else:
        evaluate(frozen, "fresh")
    before = list(host.events)
    with pytest.raises(FileExistsError):
        evaluate(frozen, "fresh")
    assert host.events == before


@pytest.mark.parametrize("case", ["zero", "no_submission", "over_budget", "different_request"])
def test_invalid_pair_never_constructs_observation(tmp_path, case):
    host, _, evaluate, frozen = setup(tmp_path)
    if case == "zero":
        host.zero_calls = True
    elif case == "no_submission":
        host.fail_arm, host.failure = "incumbent", "no_submission"
    elif case == "over_budget":
        host.model_calls = 3
    else:
        host.different_request = True
    with pytest.raises(EvaluationAttemptFailed):
        evaluate(frozen, "fresh")
    assert not list(evaluate.output_root.rglob("observation.json"))
    assert all(session._closed for session in host.sessions.values())


def synthetic_initialization(policy, cfg, reservation):
    # Unit-test controller bootstrapping ONLY; not evidence of actual quality.
    return BaselineValidation(policy.policy_id, cfg.identity, cfg.oracle_id, True, "a" * 64,
                              TaskTrace(reservation.task_id, policy.policy_id, cfg.measurement,
                                        "learning", (), (), COMPLETE, reservation.learning_run_id))


def test_learn_once_freezes_before_consuming_tasks_and_never_promotes(tmp_path):
    host, manifest, evaluate, _ = setup(tmp_path)
    optimizer = Optimizer(tmp_path / "registry.sqlite", config=manifest.config, evaluator=evaluate)
    optimizer.initialize(INCUMBENT, validator=synthetic_initialization, validation_call_limit=0)

    def fresh_tasks():
        assert optimizer.status()["trials"][0]["state"] != "complete"
        assert optimizer.status()["budget"]["rounds"] == 1
        yield "fresh"

    result = learn_once(optimizer, task_ids=fresh_tasks(), samples=1)
    assert result["status"] == "not_certified" and result["policy_promoted"] is False
    assert optimizer.status()["champion"]["policy_id"] == INCUMBENT.policy_id
    assert optimizer.status()["learning"]["complete_calls"] == 2
    events = list(host.events)
    with pytest.raises(OptimizerError):
        learn_once(optimizer, task_ids=["fresh"], samples=1)
    assert host.events == events


def test_optimizer_retains_adapter_failure_costs_without_false_quality(tmp_path):
    host, manifest, evaluate, _ = setup(tmp_path)
    host.fail_arm, host.failure = "candidate", "partial"
    optimizer = Optimizer(tmp_path / "registry.sqlite", config=manifest.config, evaluator=evaluate)
    optimizer.initialize(INCUMBENT, validator=synthetic_initialization, validation_call_limit=0)
    with pytest.raises(OptimizerError, match="evaluation_failed"):
        learn_once(optimizer, task_ids=["fresh"], samples=1)
    status = optimizer.status()
    assert status["learning"]["known_reference_tokens"] > 0
    assert status["learning"]["reference_tokens"] is None
    assert status["champion"]["policy_id"] == INCUMBENT.policy_id
    assert status["trials"][0]["state"] == "failed"


def test_screening_requires_explicit_disclosure_before_proposal(tmp_path):
    _, manifest, evaluate, _ = setup(tmp_path)
    optimizer = Optimizer(tmp_path / "registry.sqlite", config=manifest.config, evaluator=evaluate)
    with pytest.raises(ValueError, match="explicit_screening"):
        learn_once(optimizer, task_ids=["fresh"], samples=1, screener=object())
    assert optimizer.status()["budget"]["rounds"] == 0


def test_production_adapter_has_no_eval_imports():
    tree = ast.parse(Path(learning.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith(("evals", "quality", "refinement"))
        elif isinstance(node, ast.Import):
            assert all(not item.name.startswith(("evals", "quality", "refinement")) for item in node.names)


def test_actual_readonly_host_and_runtime_adapter_without_network(tmp_path, monkeypatch):
    from brainspace.readonly_learning_host import ReadonlyGatewayHost
    from brainspace.transport import ResponsesTransport

    sent = []

    def fake_send(self, wire):
        sent.append(wire)
        body = {"object": "response", "model": self.model, "status": "completed",
                "output": [{"type": "function_call", "call_id": "answer-call",
                            "name": "answer", "arguments": json.dumps({"content": '{"value":7}'})}],
                "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}}
        output = json.dumps(body)
        return Reply(True, "ok", True, wire, output, body, 200)

    monkeypatch.setattr(ResponsesTransport, "send", fake_send)
    host = ReadonlyGatewayHost(
        {"schema_version": 1, "tasks": [{"prompt": "Return the JSON value from note.txt.",
          "files": {"note.txt": '{"value":7}'}, "expected": {"value": 7}}]},
        base_url="http://127.0.0.1:1/not-used", model="offline-fixture-model",
        allow_network=True, max_calls=2)
    cfg = config()
    manifest = RuntimeLearningManifest(
        cfg, host.identity, tuple((t, host.task_digest(t)) for t in host.task_ids), 2)
    evaluate = RuntimePairEvaluator(manifest, host=host, output_root=tmp_path / "pairs")
    task_id = host.task_ids[0]
    result = evaluate(trial(cfg), task_id)
    assert result.incumbent_outcome.success and result.candidate_outcome.success
    assert len(sent) == 2 and sent[0] == sent[1]
    assert result.incumbent.task_id == result.candidate.task_id == task_id
    assert result.incumbent.calls[0].call_id != result.candidate.calls[0].call_id
    assert all(read_json(p)["complete"] for p in evaluate.output_root.rglob("cleanup.json"))


def test_cleanup_failure_cannot_erase_primary_costs_or_create_outcome(tmp_path, monkeypatch):
    host, _, evaluate, frozen = setup(tmp_path)
    close = RuntimeSession.close

    def failing_close(self):
        close(self)
        raise OSError("simulated cleanup reporting failure")

    monkeypatch.setattr(RuntimeSession, "close", failing_close)
    with pytest.raises(EvaluationAttemptFailed) as caught:
        evaluate(frozen, "fresh")
    assert caught.value.reason == "cleanup_failed"
    assert caught.value.traces[0].totals().total_tokens > 0
    assert host.sessions["incumbent"]._closed


def test_interrupted_controller_retains_costs_and_rethrows_cancellation(tmp_path):
    host, manifest, evaluate, _ = setup(tmp_path)
    host.fail_arm, host.failure = "candidate", "interrupt"
    optimizer = Optimizer(tmp_path / "registry.sqlite", config=manifest.config, evaluator=evaluate)
    optimizer.initialize(INCUMBENT, validator=synthetic_initialization, validation_call_limit=0)
    with pytest.raises(EvaluationAttemptInterrupted):
        learn_once(optimizer, task_ids=["fresh"], samples=1)
    status = optimizer.status()
    assert status["trials"][0]["state"] == "cancelled"
    assert status["learning"]["known_reference_tokens"] > 0
    assert status["learning"]["reference_tokens"] is None
    assert len([event for event in host.events if event[0] == "drive"]) == 2


@pytest.mark.parametrize("mutation,expected_calls,code", [
    ("oracle_previous_capture", 2, "completed_arm_evidence_changed"),
    ("oracle_next_workspace", 1, "unstarted_workspace_changed"),
    ("oracle_pair_plan", 1, "frozen_pair_plan_changed"),
    ("oracle_manifest", 1, "frozen_manifest_changed"),
])
def test_oracle_cannot_mutate_other_arm_or_frozen_plan(tmp_path, mutation, expected_calls, code):
    host, _, evaluate, frozen = setup(tmp_path)
    host.mutate = mutation
    with pytest.raises(EvaluationAttemptFailed) as caught:
        evaluate(frozen, "fresh")
    assert str(caught.value.__context__) == code
    assert sum(len(t.calls) for t in caught.value.traces) == expected_calls
    assert not list(evaluate.output_root.rglob("observation.json"))


@pytest.mark.parametrize("reason", ["model_mismatch", "hidden_model_mismatch"])
def test_complete_failed_reply_with_foreign_model_cannot_be_negative_observation(tmp_path, reason):
    host, _, evaluate, frozen = setup(tmp_path)
    host.fail_arm, host.failure = "incumbent", reason
    host.check_success["incumbent"] = False
    with pytest.raises(EvaluationAttemptFailed) as caught:
        evaluate(frozen, "fresh")
    assert caught.value.reason == "transport_incomplete"
    assert str(caught.value.__context__) == "response_model_mismatch"
    assert len(caught.value.traces) == 1
    trace = caught.value.traces[0]
    assert trace.policy_id == INCUMBENT.policy_id and trace.totals().total_tokens > 0
    assert trace.expected_call_ids == (host.sessions["incumbent"].run_id + ":1",)
    assert trace.calls[0].completion_status == "failed"
    assert not any(event[0] == "check" for event in host.events)
    assert len([event for event in host.events if event[0] == "drive"]) == 1
    assert not list(evaluate.output_root.rglob("observation.json"))
