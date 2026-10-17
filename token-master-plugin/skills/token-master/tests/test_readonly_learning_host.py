"""Real RuntimeSession and checker; only ResponsesTransport.send is mocked."""
from copy import deepcopy
from dataclasses import replace
import json
import socket

import pytest

from brainspace.learning_runtime import (
    CheckedOutcome, RuntimeLearningManifest, RuntimePairEvaluator,
)
from brainspace.optimizer import (
    BaselineValidation, EvaluationAttemptFailed, FrozenTrial, Optimizer, OptimizerConfig,
    OptimizerError, reference_measurement,
)
from brainspace import readonly_learning_host as readonly
from brainspace.readonly_learning_host import ReadonlyGatewayHost
from brainspace.request_policy import RequestPolicy
from brainspace.runtime import RuntimeSession
from brainspace.token_ledger import COMPLETE, TaskTrace
from brainspace.transport import Reply, ResponsesTransport


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("tests must never open sockets")
    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


def manifest(*, expected=None, files=None, intent="exact"):
    return {"schema_version": 1, "tasks": [{
        "prompt": "Read the task files and answer the requested JSON.",
        "files": files if files is not None else {"src/note.txt": "value: 7\n"},
        "expected": {"value": 7} if expected is None else expected,
        "intent": intent,
    }]}


def host(data=None, **kwargs):
    return ReadonlyGatewayHost(data or manifest(), **{
        "base_url": "http://127.0.0.1:8765/v1", "model": "fixture-model",
        "allow_network": True, "max_calls": 8, **kwargs})


def action(name, arguments, call_id=None):
    return {"type": "function_call", "name": name,
            "arguments": json.dumps(arguments), "call_id": call_id}


def scripted(monkeypatch, actions):
    sent = []
    iterator = iter(actions)

    def send(self, wire):
        sent.append(wire)
        value = next(iterator)
        if callable(value):
            value = value(self, wire)
        if isinstance(value, Reply):
            return value
        if isinstance(value, Exception):
            raise value
        output = value if isinstance(value, list) else [deepcopy(value)]
        for index, item in enumerate(output):
            if item.get("type") == "function_call" and item.get("call_id") is None:
                item["call_id"] = f"c{len(sent)}-{index}"
        body = {"object": "response", "status": "completed", "model": self.model,
                "output": output, "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}
        return Reply(True, "ok", True, wire, json.dumps(body), body, 200)

    monkeypatch.setattr(ResponsesTransport, "send", send)
    return sent


def session_for(owner, tmp_path, *, name="arm", backend="none", policy=None):
    task_id = owner.task_ids[0]
    prepared = owner.prepare(task_id, tmp_path / name)
    session = RuntimeSession(
        workspace=prepared.workspace, transport=prepared.transport,
        output=tmp_path / name / "runtime", session_id=name,
        task_id=task_id, backend=backend, policy=policy,
        max_calls=owner._limits[0], phase="learning", learning_run_id="host-test")
    return task_id, prepared, session


def finish(owner, task_id, prepared, session):
    artifacts = owner.drive(task_id, session, prepared)
    result = session.finish()
    session.close()
    checked = owner.check(task_id, artifacts, prepared)
    return artifacts, result, checked


def test_actual_session_list_read_answer_and_private_oracle(monkeypatch, tmp_path):
    secret = {"oracle_only": "held-out-secret-918"}
    owner = host(manifest(expected=secret))
    sent = scripted(monkeypatch, [
        action("list_files", {}), action("read_file", {"path": "src/note.txt"}),
        action("answer", {"content": json.dumps(secret)}),
    ])
    task, prepared, session = session_for(owner, tmp_path)
    artifacts, result, checked = finish(owner, task, prepared, session)
    assert type(prepared.transport) is ResponsesTransport
    assert type(checked) is CheckedOutcome and checked.success
    assert len(checked.evidence_sha256) == 64
    assert artifacts["status"] == "answered" and len(artifacts["outcomes"]) == 3
    assert len(artifacts["events"]) == result["wrapped_tool_attempts"] == 3
    assert result["source_read_receipts"] == 1
    assert result["model_calls"] == 3 and result["trace_complete"]
    assert result["external_outcome_supplied"] is None
    assert result["quality_verified"] is None
    assert "held-out-secret-918" not in "".join(sent)
    assert sorted(p.relative_to(prepared.workspace).as_posix()
                  for p in prepared.workspace.rglob("*") if p.is_file()) == ["src/note.txt"]
    assert "expected" not in repr(prepared)
    assert owner.check(task, deepcopy(artifacts), prepared) == checked
    assert len(sent) == 3  # checking never calls a model


def test_task_ids_are_immutable_content_digests_not_aliases():
    data = manifest()
    first, second = host(data), host(deepcopy(data))
    assert first.identity == second.identity
    task = first.task_ids[0]
    assert task == "readonly:" + first.task_digest(task)
    assert len(first.task_digest(task)) == 64
    data["tasks"][0]["files"]["src/note.txt"] = "different"
    data["tasks"][0]["expected"]["value"] = 100
    assert first.identity == second.identity and first.task_ids == second.task_ids
    assert host(data).task_ids != first.task_ids
    for field, value in (("prompt", "Changed question"), ("expected", {"value": True}),
                         ("intent", "overview")):
        changed = manifest()
        changed["tasks"][0][field] = value
        assert host(changed).task_ids != first.task_ids
    with pytest.raises(ValueError, match="unknown_content_task"):
        first.task_digest("renamed-alias")
    data = manifest()
    data["tasks"][0]["id"] = "alias"
    with pytest.raises(ValueError, match="invalid_task_fields"):
        host(data)
    with pytest.raises(AttributeError, match="frozen"):
        first._limits = (1000, 1000)


@pytest.mark.parametrize("option,value", [
    ("model", "other-model"), ("base_url", "http://localhost:8765/v1"),
    ("allow_network", False), ("max_calls", 9), ("max_tool_calls", 33),
    ("max_output_tokens", 2000), ("max_request_bytes", 500000),
    ("max_response_bytes", 500000), ("timeout", 40), ("reasoning_effort", "low"),
])
def test_identity_binds_every_host_and_transport_setting(option, value):
    normal, changed = host(), host(**{option: value})
    assert normal.identity != changed.identity
    assert normal.task_ids == changed.task_ids


@pytest.mark.parametrize("path", [
    "../escape", "/absolute", "C:/outside", "a\\b", "a//b", "a/./b", "a/../b",
    "NUL", "CON.txt", "COM1.txt", "LPT²", "a.", "a ", "a/b ", "a:b", "a?b",
    "a*b", 'a"b', "a|b", "a<b", "a\x00b", "", "//server/share",
])
def test_unsafe_paths_rejected_before_materialization(path):
    with pytest.raises(ValueError):
        host(manifest(files={path: "x"}))


@pytest.mark.parametrize("paths", [
    ("a.txt", "A.txt"), ("Dir/a", "dir/b"), ("é/a", "e\u0301/b"),
    ("a", "a/b"), ("a/b", "a"), ("a", "A/b"),
])
def test_colliding_files_and_directory_aliases_are_rejected(paths):
    with pytest.raises(ValueError, match="collision|colliding"):
        host(manifest(files={path: "x" for path in paths}))


@pytest.mark.parametrize("expected", [(1, 2), {"x": float("nan")}, {1: "not-string"}, "\ud800"])
def test_nonjson_or_nonutf8_gold_is_rejected(expected):
    with pytest.raises((ValueError, UnicodeError)):
        host(manifest(expected=expected))


def test_strict_manifest_fields_duplicates_and_bounds():
    data = manifest()
    data["tasks"].append(deepcopy(data["tasks"][0]))
    with pytest.raises(ValueError, match="duplicate_content_task"):
        host(data)
    data = manifest()
    data["tasks"][0]["command"] = "no external executors"
    with pytest.raises(ValueError):
        host(data)
    with pytest.raises(ValueError):
        host(manifest(files={"large": "x" * 262145}))
    with pytest.raises(ValueError, match="fixture_path_budget"):
        host(manifest(files={str(i) + "/" + "/".join(["d"] * 460) + "/f": "x" for i in range(9)}))
    with pytest.raises(ValueError):
        host(manifest(intent="edit"))
    with pytest.raises(ValueError):
        host(max_calls=True)
    with pytest.raises(ValueError):
        host(base_url="https://example.com/v1")
    with pytest.raises(ValueError):
        host(base_url="http://secret@localhost/v1")


def test_task_order_and_fixture_order_do_not_change_content_identity():
    data = manifest(files={"z": "last", "a": "first"})
    other = manifest(expected={"second": 2})["tasks"][0]
    data["tasks"].append(other)
    reordered = deepcopy(data)
    reordered["tasks"].reverse()
    reordered["tasks"][1]["files"] = {"a": "first", "z": "last"}
    assert host(data).identity == host(reordered).identity
    assert host(data).task_ids == host(reordered).task_ids


def test_fresh_identical_arm_workspaces_and_foreign_prepared_rejected(tmp_path):
    owner = host(manifest(files={"a/b.txt": "α\r\nβ\n", "other.md": ""}))
    task = owner.task_ids[0]
    left = owner.prepare(task, tmp_path / "left")
    (tmp_path / "right").mkdir()
    right = owner.prepare(task, tmp_path / "right")
    assert left.workspace != right.workspace
    assert left.transport == right.transport and left.transport is not right.transport
    assert (left.workspace / "a/b.txt").read_bytes() == (right.workspace / "a/b.txt").read_bytes()
    assert (left.workspace / "a/b.txt").read_bytes() == "α\r\nβ\n".encode()
    with pytest.raises(ValueError, match="fresh_arm_root"):
        owner.prepare(task, tmp_path / "left")
    with pytest.raises(ValueError, match="foreign_prepared"):
        owner.check(task, {}, replace(left))


@pytest.mark.parametrize("answer", ['{"value":true}', '{"value":7.0}', '{"value":"7"}',
                                  '{"value":7,"extra":1}', '{}', '{"value":8}',
                                  '{"value":7,"value":7}', '{"value":NaN}', "not JSON"])
def test_wrong_or_invalid_answers_are_complete_negative_outcomes(monkeypatch, tmp_path, answer):
    owner = host()
    scripted(monkeypatch, [action("answer", {"content": answer})])
    task, prepared, session = session_for(owner, tmp_path)
    artifacts, result, checked = finish(owner, task, prepared, session)
    assert not checked.success and result["trace_complete"]
    assert result["model_calls"] == 1 and len(artifacts["outcomes"]) == 1


@pytest.mark.parametrize("expected,actual", [
    ({"nested": [1]}, {"nested": [True]}),
    ({"nested": [True]}, {"nested": [1]}),
])
def test_nested_boolean_is_never_interchangeable_with_integer_one(monkeypatch, tmp_path, expected, actual):
    owner = host(manifest(expected=expected))
    scripted(monkeypatch, [action("answer", {"content": json.dumps(actual)})])
    task, prepared, session = session_for(owner, tmp_path)
    _, result, checked = finish(owner, task, prepared, session)
    assert not checked.success and result["trace_complete"] and result["model_calls"] == 1


@pytest.mark.parametrize("call", [
    action("write_file", {"path": "src/note.txt", "content": "value: 7\n"}),
    action("read_file", {"path": "../outside.txt"}),
    action("read_file", {"path": "unowned.txt"}),
    action("read_file", {"path": "src/note.txt", "extra": True}),
    action("read_file", {"path": True}),
    action("run_python", {"code": "print('do not execute')"}),
])
def test_denied_tools_are_recorded_without_effects(monkeypatch, tmp_path, call):
    owner = host()
    scripted(monkeypatch, [call])
    task, prepared, session = session_for(owner, tmp_path)
    (tmp_path / "outside.txt").write_text("not available to model")
    artifacts, result, checked = finish(owner, task, prepared, session)
    assert artifacts["status"] == "readonly_violation" and not checked.success
    assert result["wrapped_tool_attempts"] == 1
    assert artifacts["events"][0]["status"] == "rejected"
    assert "not available to model" not in json.dumps(artifacts)
    assert (prepared.workspace / "src/note.txt").read_bytes() == b"value: 7\n"


def test_duplicate_ids_and_multi_call_envelopes_fail_without_hidden_work(monkeypatch, tmp_path):
    owner = host()
    sent = scripted(monkeypatch, [action("list_files", {}, "same"),
                                  action("answer", {"content": '{"value":7}'}, "same")])
    task, prepared, session = session_for(owner, tmp_path)
    artifacts, result, checked = finish(owner, task, prepared, session)
    assert not checked.success and artifacts["status"] == "invalid_model_action"
    assert result["wrapped_tool_attempts"] == 1 and len(sent) == 2
    scripted(monkeypatch, [[action("list_files", {}), action("answer", {"content": '{"value":7}'})]])
    task, prepared, session = session_for(owner, tmp_path, name="batch")
    artifacts, result, checked = finish(owner, task, prepared, session)
    assert not checked.success and result["wrapped_tool_attempts"] == 0


@pytest.mark.parametrize("option,value,expected_calls,expected_tools", [
    ("max_calls", 1, 1, 1), ("max_tool_calls", 1, 2, 1),
])
def test_model_and_tool_attempts_have_fixed_bounds(monkeypatch, tmp_path, option, value,
                                                  expected_calls, expected_tools):
    owner = host(**{option: value})
    sent = scripted(monkeypatch, [action("list_files", {}), action("list_files", {})])
    task, prepared, session = session_for(owner, tmp_path)
    artifacts, result, checked = finish(owner, task, prepared, session)
    assert not checked.success and artifacts["status"].endswith("call_limit")
    assert len(sent) == expected_calls and result["wrapped_tool_attempts"] == expected_tools
    with pytest.raises(ValueError, match="already_driven"):
        owner.drive(task, session, prepared)


def test_original_history_survives_local_policy_and_assistant_text(monkeypatch, tmp_path):
    content = "def source():\n" + "".join(f"    n{i} = {i}\n" for i in range(120))
    owner = host(manifest(files={"module.py": content}, intent="navigation"))
    sent = scripted(monkeypatch, [
        [{"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": "I will read the source."}]},
         action("read_file", {"path": "module.py"})],
        action("read_file", {"path": "module.py"}),
        action("read_file", {"path": "module.py"}),
        action("answer", {"content": '{"value":7}'}),
    ])
    policy = RequestPolicy(version="request-policy-v3", enabled=True, min_tool_chars=512)
    task, prepared, session = session_for(owner, tmp_path, backend="local", policy=policy)
    artifacts, result, checked = finish(owner, task, prepared, session)
    assert checked.success and result["source_read_receipts"] == 3
    assert artifacts["messages"][2]["content"] == "I will read the source."
    assert [message["content"] for message in artifacts["messages"] if message["role"] == "tool"][:3] == [
        content, content, content]
    preparations = [json.loads(line) for line in (session.output / "preparations.jsonl").read_text().splitlines()]
    for previous, following in zip(preparations, preparations[1:]):
        history = previous["original"]["messages"]
        assert following["original"]["messages"][:len(history)] == history
    assert len(sent) == 4 and result["trace_complete"]


def test_recovery_runs_through_real_runtime_and_keeps_call_id(monkeypatch, tmp_path):
    owner = host()
    task, prepared, session = session_for(owner, tmp_path)
    ref = session.ccr.stash("exact recovered detail", source="src/note.txt", ctype="source")
    scripted(monkeypatch, [action("retrieve_original", {"ref": ref, "offset": 0}, "recover-1"),
                           action("answer", {"content": '{"value":7}'})])
    artifacts, result, checked = finish(owner, task, prepared, session)
    assert checked.success and result["recovery_tool_attempts"] == 1
    assert artifacts["events"][0]["call"]["id"] == "recover-1"
    assert "exact recovered detail" in artifacts["events"][0]["content"]
    tools = json.loads(owner._tools_json)
    assert [t for t in tools if t["function"]["name"] in ("retrieve_original", "headroom_retrieve")] == (
        RuntimeSession.recovery_tools())


@pytest.mark.parametrize("call", [
    action("retrieve_original", {"ref": "abc", "offset": True}),
    action("headroom_retrieve", {"hash": 123}),
    action("headroom_retrieve", {"hash": "abc"}),  # not active in this runtime
])
def test_invalid_or_unavailable_recovery_is_negative(monkeypatch, tmp_path, call):
    owner = host()
    scripted(monkeypatch, [call])
    task, prepared, session = session_for(owner, tmp_path)
    artifacts, result, checked = finish(owner, task, prepared, session)
    assert not checked.success and result["trace_complete"]
    assert artifacts["events"]


@pytest.mark.parametrize("change", ["edit", "missing", "extra", "directory", "forge"])
def test_independent_checker_rejects_workspace_and_artifact_tampering(monkeypatch, tmp_path, change):
    owner = host()
    scripted(monkeypatch, [action("answer", {"content": '{"value":7}'})])
    task, prepared, session = session_for(owner, tmp_path)
    artifacts = owner.drive(task, session, prepared)
    session.finish()
    session.close()
    if change == "edit":
        (prepared.workspace / "src/note.txt").write_text("changed")
    elif change == "missing":
        (prepared.workspace / "src/note.txt").unlink()
    elif change == "extra":
        (prepared.workspace / "extra").write_text("unknown")
    elif change == "directory":
        (prepared.workspace / "extra").mkdir()
    else:
        artifacts["events"].append({"status": "forged"})
    before = deepcopy(artifacts)
    assert not owner.check(task, artifacts, prepared).success
    assert artifacts == before


@pytest.mark.parametrize("error", [OSError("transient read failure"), PermissionError("unreadable")])
def test_checker_io_failure_is_not_a_negative_quality_label(monkeypatch, tmp_path, error):
    owner = host()
    scripted(monkeypatch, [action("answer", {"content": '{"value":7}'})])
    task, prepared, session = session_for(owner, tmp_path)
    artifacts = owner.drive(task, session, prepared)
    session.finish()
    session.close()

    def failed_read(*args):
        raise error

    monkeypatch.setattr(ReadonlyGatewayHost, "_owned_bytes", staticmethod(failed_read))
    with pytest.raises(type(error)):
        owner.check(task, artifacts, prepared)


def test_directory_walk_io_failure_is_not_silently_treated_as_missing_files(monkeypatch, tmp_path):
    owner = host()
    scripted(monkeypatch, [action("answer", {"content": '{"value":7}'})])
    task, prepared, session = session_for(owner, tmp_path)
    artifacts = owner.drive(task, session, prepared)
    session.finish()
    session.close()

    def failed_walk(*args, **kwargs):
        assert kwargs["followlinks"] is False
        kwargs["onerror"](PermissionError("transient directory failure"))
        return iter(())

    monkeypatch.setattr(readonly.os, "walk", failed_walk)
    with pytest.raises(PermissionError):
        owner.check(task, artifacts, prepared)


def test_symlinked_arm_or_replaced_owned_file_never_read(monkeypatch, tmp_path):
    owner = host()
    original = tmp_path / "original"
    original.mkdir()
    try:
        (tmp_path / "alias").symlink_to(original, target_is_directory=True)
    except OSError:
        pytest.skip("OS symlink creation unavailable")
    with pytest.raises(ValueError, match="linked"):
        owner.prepare(owner.task_ids[0], tmp_path / "alias")
    scripted(monkeypatch, [action("read_file", {"path": "src/note.txt"})])
    task, prepared, session = session_for(owner, tmp_path)
    outside = tmp_path / "outside"
    outside.write_text("must not disclose")
    target = prepared.workspace / "src/note.txt"
    target.unlink()
    target.symlink_to(outside)
    artifacts, result, checked = finish(owner, task, prepared, session)
    assert not checked.success
    assert "must not disclose" not in json.dumps(artifacts)


def test_hardlinked_owned_file_is_rejected(monkeypatch, tmp_path):
    owner = host()
    scripted(monkeypatch, [action("read_file", {"path": "src/note.txt"})])
    task, prepared, session = session_for(owner, tmp_path)
    outside = tmp_path / "outside"
    outside.write_bytes(b"value: 7\n")
    target = prepared.workspace / "src/note.txt"
    target.unlink()
    try:
        target.hardlink_to(outside)
    except OSError:
        session.finish()
        session.close()
        pytest.skip("OS hardlink creation unavailable")
    artifacts, result, checked = finish(owner, task, prepared, session)
    assert not checked.success and artifacts["status"] == "readonly_violation"
    assert outside.read_bytes() == b"value: 7\n"


@pytest.mark.parametrize("answer", [None, [1, {"valid": True}], "scalar", 1.0])
def test_any_exact_json_root_type_is_supported(monkeypatch, tmp_path, answer):
    data = manifest()
    data["tasks"][0]["expected"] = answer
    owner = host(data)
    scripted(monkeypatch, [action("answer", {"content": json.dumps(answer)})])
    task, prepared, session = session_for(owner, tmp_path)
    assert finish(owner, task, prepared, session)[2].success


def test_checker_rejects_success_invented_without_drive(tmp_path):
    owner = host()
    task = owner.task_ids[0]
    prepared = owner.prepare(task, tmp_path / "arm")
    assert not owner.check(task, {"status": "answered", "answer": {"value": 7}}, prepared).success


@pytest.mark.parametrize("output", [
    [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "done"}]}],
    [{"type": "function_call", "name": "answer", "call_id": "x", "arguments": "not JSON"}],
    [{"type": "function_call", "name": "answer", "call_id": "x",
      "arguments": '{"content":"{}","content":"{}"}'}],
    [{"type": "function_call", "name": "answer", "call_id": "x",
      "arguments": '{"content":"\\ud800"}'}],
])
def test_malformed_complete_model_actions_are_negative_not_adapter_errors(monkeypatch, tmp_path, output):
    owner = host()
    scripted(monkeypatch, [output])
    task, prepared, session = session_for(owner, tmp_path)
    artifacts, result, checked = finish(owner, task, prepared, session)
    assert artifacts["status"] == "invalid_model_action"
    assert not checked.success and result["trace_complete"]
    assert len(artifacts["outcomes"]) == 1


def test_bounded_nested_wrong_answer_can_be_retained_in_artifact_envelope(monkeypatch, tmp_path):
    answer = 7
    for _ in range(31):
        answer = [answer]
    owner = host()
    scripted(monkeypatch, [action("answer", {"content": json.dumps(answer)})])
    task, prepared, session = session_for(owner, tmp_path)
    artifacts, result, checked = finish(owner, task, prepared, session)
    assert artifacts["status"] == "answered"
    assert not checked.success and result["trace_complete"]


def test_complete_http_failure_negative_but_partial_capture_stays_incomplete(monkeypatch, tmp_path):
    owner = host()
    def failed(self, wire):
        return Reply(False, "http_error", True, wire, "service unavailable", http_status=503)
    scripted(monkeypatch, [failed])
    task, prepared, session = session_for(owner, tmp_path)
    artifacts, result, checked = finish(owner, task, prepared, session)
    assert not checked.success and result["trace_complete"]
    assert artifacts["outcomes"][0]["output_text"] == "service unavailable"
    def partial(self, wire):
        return Reply(False, "transport_error", input_text=wire)
    scripted(monkeypatch, [partial])
    task, prepared, session = session_for(owner, tmp_path, name="partial")
    artifacts, result, checked = finish(owner, task, prepared, session)
    assert not checked.success and not result["trace_complete"]
    assert result["reference_totals"] is None and result["incomplete_calls"]
    assert artifacts["capture_complete"] is False


def test_failure_is_not_retried_and_answer_does_not_force_reads(monkeypatch, tmp_path):
    owner = host()
    sent = scripted(monkeypatch, [TimeoutError("private transport exception"),
                                  action("answer", {"content": '{"value":7}'})])
    task, prepared, session = session_for(owner, tmp_path)
    artifacts, result, checked = finish(owner, task, prepared, session)
    assert len(sent) == result["attempts"] == result["model_calls"] == 1
    assert not checked.success and not result["trace_complete"]
    assert "private transport exception" not in json.dumps(artifacts)
    scripted(monkeypatch, [action("answer", {"content": '{"value":7}'})])
    task, prepared, session = session_for(owner, tmp_path, name="direct-answer")
    artifacts, result, checked = finish(owner, task, prepared, session)
    assert checked.success and result["source_read_receipts"] == 0
    assert result["wrapped_tool_attempts"] == result["model_calls"] == 1


def test_modified_owned_bytes_are_not_disclosed_and_negative_evidence_binds_them(monkeypatch, tmp_path):
    owner = host()
    scripted(monkeypatch, [action("read_file", {"path": "src/note.txt"})])
    task, prepared, session = session_for(owner, tmp_path)
    target = prepared.workspace / "src/note.txt"
    target.write_bytes(b"DO_NOT_DISCLOSE_CHANGED_BYTES")
    artifacts, result, first = finish(owner, task, prepared, session)
    assert not first.success and "DO_NOT_DISCLOSE_CHANGED_BYTES" not in json.dumps(artifacts)
    target.write_bytes(b"OTHER_CHANGED_BYTES")
    second = owner.check(task, artifacts, prepared)
    assert not second.success and first.evidence_sha256 != second.evidence_sha256


def test_explicit_network_opt_in_is_not_silently_enabled(tmp_path):
    owner = host(allow_network=False)
    task, prepared, session = session_for(owner, tmp_path)
    artifacts, result, checked = finish(owner, task, prepared, session)
    assert not prepared.transport.allow_network and not checked.success
    assert artifacts["outcomes"][0]["reason"] == "network_not_allowed"
    assert result["model_calls"] == 0


def evaluator(owner, tmp_path):
    measurement = reference_measurement()
    config = OptimizerConfig(
        measurement=measurement, oracle_id="host:" + owner.identity, workload_id="readonly-fixture",
        model_id="fixture-model", environment_id=owner.identity, token_cap=1000000,
        calls_per_pair=16, max_calls=64)
    declaration = RuntimeLearningManifest(
        config=config, host_id=owner.identity,
        task_digests=tuple((task, owner.task_digest(task)) for task in owner.task_ids),
        max_calls_per_arm=8)
    pair = RuntimePairEvaluator(declaration, host=owner, output_root=tmp_path / "pair")
    incumbent = RequestPolicy(version="request-policy-v3", enabled=True, min_tool_chars=512)
    candidate = replace(incumbent, keep_recent_tool_results=2)
    if candidate.policy_id == incumbent.policy_id:
        candidate = replace(incumbent, keep_recent_tool_results=1)
    trial = FrozenTrial(
        trial_id=1, round_id=1, incumbent_version=1,
        comparison=config.comparison(candidate.policy_id, incumbent.policy_id),
        incumbent=incumbent, candidate=candidate, sample_size=1, calls_per_pair=16)
    return pair, trial


def test_adapter_accepts_real_host_negative_quality_without_self_grading(monkeypatch, tmp_path):
    owner = host()
    scripted(monkeypatch, [action("answer", {"content": '{"value":8}'}),
                           action("answer", {"content": '{"value":7}'})])
    pair, trial = evaluator(owner, tmp_path)
    observation = pair(trial, owner.task_ids[0])
    assert {observation.incumbent_outcome.success, observation.candidate_outcome.success} == {True, False}
    observation.validate(trial.comparison)


def test_adapter_rejects_partial_capture_instead_of_certifying_failure(monkeypatch, tmp_path):
    owner = host()
    def partial(self, wire):
        return Reply(False, "transport_error", input_text=wire)
    scripted(monkeypatch, [partial])
    pair, trial = evaluator(owner, tmp_path)
    with pytest.raises(EvaluationAttemptFailed) as failed:
        pair(trial, owner.task_ids[0])
    assert failed.value.traces and failed.value.receipt_sha256s


@pytest.mark.parametrize("failed_check", [1, 2])
def test_controller_rejects_checker_io_failure_and_retains_actual_costs(monkeypatch, tmp_path, failed_check):
    owner = host()
    sent = scripted(monkeypatch, [action("answer", {"content": '{"value":7}'}),
                                  action("answer", {"content": '{"value":7}'})])
    pair, example = evaluator(owner, tmp_path)
    real_read = ReadonlyGatewayHost._owned_bytes
    checks = []

    def transient_read_failure(*args):
        checks.append(args[1])
        if len(checks) == failed_check:
            raise OSError("injected private checker read failure")
        return real_read(*args)

    monkeypatch.setattr(ReadonlyGatewayHost, "_owned_bytes", staticmethod(transient_read_failure))
    optimizer = Optimizer(tmp_path / "registry.sqlite", config=pair.manifest.config, evaluator=pair)

    def deterministic_bootstrap(policy, config, reservation):
        # Unit-test controller setup only: no provider work or learned-quality claim.
        assert policy.enabled and reservation.call_limit == 0
        return BaselineValidation(
            policy.policy_id, config.identity, config.oracle_id, True, "a" * 64,
            TaskTrace(reservation.task_id, policy.policy_id, config.measurement,
                      "learning", (), (), COMPLETE, reservation.learning_run_id))

    optimizer.initialize(example.incumbent, validator=deterministic_bootstrap, validation_call_limit=0)
    candidate = optimizer.propose()[0]
    trial = optimizer.freeze(candidate.policy_id, sample_size=1)
    with pytest.raises(OptimizerError, match="evaluation_failed"):
        optimizer.evaluate(trial.trial_id, [owner.task_ids[0]])
    status = optimizer.status()
    assert status["trials"][0]["state"] == "failed"
    assert status["champion"]["policy_id"] == example.incumbent.policy_id
    assert status["learning"]["reference_tokens"] is None
    assert status["learning"]["complete_calls"] == 0
    assert len(sent) == failed_check
    failed = json.loads(next(pair.output_root.rglob("attempt-failed.json")).read_text())
    assert failed["reason"] == "oracle_failed"
    assert sum(len(trace["calls"]) for trace in failed["traces"]) == failed_check
    results = [json.loads(path.read_text()) for path in pair.output_root.rglob("result.json")]
    cost = sum(result["reference_totals"]["total_tokens"] for result in results)
    assert cost > 0 and status["learning"]["known_partial_reference_tokens"] == cost
    assert not list(pair.output_root.rglob("observation.json"))


def test_opt_in_document_alias_is_a_real_scoped_read_with_native_receipt(monkeypatch, tmp_path):
    data = manifest(files={"docs/note.md": "value: 7\n"}, intent="overview")
    owner = host(data, document_tools=True)
    sent = scripted(monkeypatch, [
        action("fetch_artifact", {"path": "docs/note.md"}),
        action("answer", {"content": '{"value":7}'})])
    task, prepared, session = session_for(owner, tmp_path)
    artifacts, result, checked = finish(owner, task, prepared, session)
    assert checked.success and artifacts["status"] == "answered"
    assert result["source_read_receipts"] == 1 and len(sent) == 2
    receipt = json.loads((session.output / "source-reads.jsonl").read_text("utf-8"))
    assert receipt["tool_name"] == "fetch_artifact" and receipt["source_path"] == "docs/note.md"
    assert receipt["status"] == "success"
    request = json.loads(sent[0])
    assert any(t["name"] == "fetch_artifact" for t in request["tools"])


def test_legacy_readonly_host_does_not_acquire_document_tools_implicitly(monkeypatch, tmp_path):
    data = manifest(files={"note.md": "value: 7\n"})
    legacy = host(data)
    opted_in = host(data, document_tools=True)
    assert legacy.identity != opted_in.identity and legacy.task_ids == opted_in.task_ids
    sent = scripted(monkeypatch, [action("fetch_artifact", {"path": "note.md"})])
    task, prepared, session = session_for(legacy, tmp_path)
    artifacts, _, checked = finish(legacy, task, prepared, session)
    assert not checked.success and artifacts["status"] == "readonly_violation"
    assert all(t["name"] != "fetch_artifact" for t in json.loads(sent[0])["tools"])


@pytest.mark.parametrize("flag", [0, 1, None, "true", []])
def test_document_capability_flag_is_a_real_boolean(flag):
    with pytest.raises(ValueError, match="invalid_document_tools_flag"):
        host(document_tools=flag)
