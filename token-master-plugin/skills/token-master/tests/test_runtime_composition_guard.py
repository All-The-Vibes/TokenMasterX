"""Offline input-boundary regressions, not task-quality or all-in savings evidence.

Reducers below are explicit fakes to isolate the final-wire acceptance boundary.
The optional pinned Ponytail check consumes a local recorded profile, never an API.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import socket

import pytest

import brainspace_tools
from brainspace import ponytail, runtime, session_cli, tokens
from brainspace.request_policy import RequestPlan, RequestPolicy, SourceReadInfo
from brainspace.runtime import RuntimeSession
from brainspace.task_mode import TaskContract, task_local_mode
from brainspace.transport import Reply, ResponsesTransport


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("no network in composition-boundary tests")
    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)


@pytest.fixture
def sent(monkeypatch):
    wires = []

    def send(self, wire):
        wires.append(wire)
        body = {"object": "response", "status": "completed", "model": self.model, "output": [],
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}
        return Reply(True, "ok", True, wire, json.dumps(body), body, 200)

    monkeypatch.setattr(ResponsesTransport, "send", send)
    return wires


@pytest.fixture
def full_component(monkeypatch):
    text = "Synthetic FULL-mode instructions, not upstream evidence.\nPreserve the whole task.\n"
    commit = "a" * 40
    checksum = hashlib.sha256(text.encode()).hexdigest()
    monkeypatch.setattr(ponytail, "PINNED_SOURCE_COMMIT", commit)
    monkeypatch.setattr(ponytail, "PINNED_INSTRUCTIONS_SHA256", checksum)
    return ponytail.PonytailInstructions(text, commit, checksum)


def request(content=None):
    chat = {"model": "offline-fixture", "messages": [
        {"role": "system", "content": "Keep this instruction."},
        {"role": "user", "content": "Inspect the supplied source."},
    ]}
    if content is not None:
        for call_id, text in (("r1", content), ("r2", "recent")):
            chat["messages"].extend([
                {"role": "assistant", "content": None, "tool_calls": [{
                    "id": call_id, "type": "function", "function": {
                        "name": "read_file", "arguments": '{"path":"source.txt"}'}}]},
                {"role": "tool", "tool_call_id": call_id, "content": text},
            ])
    return chat


def transport(**changes):
    return ResponsesTransport(base_url="http://127.0.0.1:1/not-used", model="offline-fixture",
                              **changes)


def make(tmp_path, *, name="run", wire_transport=None, **options):
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return RuntimeSession(workspace=workspace, output=tmp_path / name,
                          session_id=name, transport=wire_transport or transport(), **options)


def record(session):
    return json.loads((session.output / "preparations.jsonl").read_text().splitlines()[-1])


def mode():
    return task_local_mode(TaskContract("Inspect source.", (), ("Verify the answer.",), "Answer complete."))


def fake_reducer(monkeypatch, replacement):
    def prepare(chat, policy, **kwargs):
        candidate = deepcopy(chat)
        index = next(i for i, m in enumerate(candidate["messages"]) if m["role"] == "tool")
        candidate["messages"][index]["content"] = replacement
        return RequestPlan(candidate, None, "transformed", "offline_fake_reducer",
                           policy.policy_id, (index,))
    monkeypatch.setattr(runtime, "prepare_request", prepare)


def test_full_mode_ponytail_reverts_entire_wire_and_preserves_history(tmp_path, sent, full_component):
    session = make(tmp_path, ponytail=full_component, require_nonexpanding_input=True)
    original = request()
    before = deepcopy(original)
    wire = session.transport.encode(original)
    session.invoke(original)
    assert sent == [wire] and original == before
    row = record(session)
    assert row["prepared"] == original and row["changed_messages"] == []
    assert row["reason"] == "input_composition_guard_reversion"
    assert row["instruction_component_configured"] == "ponytail"
    assert row["instruction_component_applied"] == row["instruction_component"] == "none"
    assert row["input_composition"]["original"] == row["input_composition"]["final"]
    original["messages"].append({"role": "assistant", "content": "Done."})
    session.invoke(original)
    assert sent[-1] == session.transport.encode(original)
    result = session.finish()
    assert result["model_calls"] == result["attempts"] == 2
    assert result["transformations"] == 0 and result["trace_complete"]
    assert result["quality_verified"] is None and result["all_in_compute_savings"] is None
    assert session.close()["complete"]


def test_actual_pinned_full_ponytail_reverts_byte_for_byte(tmp_path, sent):
    path = os.environ.get("TOKENMASTER_TEST_PONYTAIL_SESSION")
    if not path:
        pytest.skip("optional local pinned full-mode profile not supplied")
    data = json.loads(Path(path).read_text(encoding="utf-8"))["profile"]["ponytail"]
    component = ponytail.PonytailInstructions(**data)
    session = make(tmp_path, ponytail=component, require_nonexpanding_input=True)
    original = request()
    wire = session.transport.encode(original)
    session.invoke(original)
    assert sent == [wire]
    row = record(session)
    assert row["input_composition"]["augmented"]["reference_tokens"] > tokens.count_tokens(wire)
    assert row["instruction_component_applied"] == "none"
    assert session.finish()["transformations"] == 0
    session.close()


@pytest.mark.parametrize("with_mode", [False, True])
def test_actual_recovery_schema_and_local_mode_taxes_are_included(tmp_path, sent, with_mode):
    session = make(
        tmp_path, backend="local", policy=RequestPolicy(enabled=True),
        mode=mode() if with_mode else None, require_nonexpanding_input=True)
    original = request()
    original_wire = session.transport.encode(original)
    session.invoke(original, intent="navigation")
    assert sent == [original_wire] and "tools" not in record(session)["prepared"]
    row = record(session)
    metrics = row["input_composition"]
    augmented, _ = session._augment(original)
    for label, wire in (("original", original_wire),
                        ("augmented", session.transport.encode(augmented)),
                        ("final", sent[0])):
        assert metrics[label] == {
            "reference_tokens": tokens.count_tokens(wire), "utf8_bytes": len(wire.encode("utf-8")),
            "wire_sha256": runtime._digest(wire)}
    assert row["instruction_component_configured"] == ("local" if with_mode else "none")
    assert row["instruction_component_applied"] == "none"
    assert session.finish()["transformations"] == 0
    session.close()


def test_profitable_fake_reduction_can_keep_guidance_and_recovery_schema(tmp_path, sent, monkeypatch):
    fake_reducer(monkeypatch, "Small recovered view.")
    session = make(tmp_path, backend="local", policy=RequestPolicy(enabled=True),
                   mode=mode(), require_nonexpanding_input=True)
    original = request("source detail " * 1500)
    before = deepcopy(original)
    original_wire = session.transport.encode(original)
    session.invoke(original, intent="navigation")
    assert original == before
    assert tokens.count_tokens(sent[0]) < tokens.count_tokens(original_wire)
    assert len(sent[0].encode()) <= len(original_wire.encode())
    row = record(session)
    assert row["reason"] == "offline_fake_reducer"
    assert row["instruction_component_applied"] == "local"
    assert row["changed_messages"]
    assert row["input_composition"]["decision"] == "nonexpanding_composition"
    body = json.loads(sent[0])
    assert any(tool["name"] == "retrieve_original" for tool in body["tools"])
    assert any("Task contract:" in str(item.get("content")) for item in body["input"])
    assert session.finish()["transformations"] == 1
    session.close()


class TableTransport:
    """Synthetic final-wire boundary fixture; no provider protocol/quality claim."""
    model = "offline-fixture"
    max_request_bytes = 524288
    max_output_tokens = 2048

    def __init__(self, original, augmented, reduced):
        self.wires = original, augmented, reduced
        self.sent = []

    def encode(self, chat):
        if not chat.get("tools"):
            return self.wires[0]
        if any(m.get("content") == "reduced" for m in chat["messages"]):
            return self.wires[2]
        return self.wires[1]

    def send(self, wire):
        self.sent.append(wire)
        output = json.dumps({"model": self.model, "usage": {
            "input_tokens": 3, "output_tokens": 2, "total_tokens": 5}})
        return Reply(True, "ok", True, wire, output, json.loads(output), 200)


@pytest.mark.parametrize("original,reduced,constraint", [
    ("a b c d e", "中中中中", "utf8"),
    ("abc " * 100, "a " * 101, "tokens"),
    ("alpha beta gamma", "one two three", "strict"),
])
def test_both_utf8_bytes_and_strict_tokens_are_required(tmp_path, monkeypatch, original, reduced, constraint):
    fake_reducer(monkeypatch, "reduced")
    wire_transport = TableTransport(original, "z " * 1000, reduced)
    assert tokens.count_tokens(reduced) < tokens.count_tokens(wire_transport.wires[1])
    assert len(reduced.encode()) <= len(wire_transport.wires[1].encode())
    if constraint == "utf8":
        assert tokens.count_tokens(reduced) < tokens.count_tokens(original)
        assert len(reduced) < len(original) < len(reduced.encode())
    elif constraint == "tokens":
        assert len(reduced.encode()) < len(original.encode())
        assert tokens.count_tokens(reduced) > tokens.count_tokens(original)
    else:
        assert tokens.count_tokens(reduced) == tokens.count_tokens(original)
        assert reduced != original and len(reduced.encode()) <= len(original.encode())
    session = make(tmp_path, wire_transport=wire_transport, backend="local",
                   policy=RequestPolicy(enabled=True), require_nonexpanding_input=True)
    original_request = request("original source")
    session.invoke(original_request)
    assert wire_transport.sent == [original]
    assert record(session)["prepared"] == original_request
    assert record(session)["changed_messages"] == []
    assert session.finish()["transformations"] == 0
    session.close()


def test_equal_utf8_byte_count_is_allowed_with_strict_token_reduction(tmp_path, monkeypatch):
    fake_reducer(monkeypatch, "reduced")
    t = TableTransport("a b c d e", "z " * 1000, "aaaaaaaaa")
    assert len(t.wires[0].encode()) == len(t.wires[2].encode())
    assert tokens.count_tokens(t.wires[2]) < tokens.count_tokens(t.wires[0])
    session = make(tmp_path, wire_transport=t, backend="local",
                   policy=RequestPolicy(enabled=True), require_nonexpanding_input=True)
    session.invoke(request("original source"))
    assert t.sent == [t.wires[2]]
    assert record(session)["input_composition"]["decision"] == "nonexpanding_composition"
    assert session.finish()["transformations"] == 1
    session.close()


def test_existing_augmented_wire_reversion_is_followed_by_whole_request_guard(tmp_path, sent, monkeypatch):
    fake_reducer(monkeypatch, "larger replacement " * 1000)
    session = make(tmp_path, backend="local", policy=RequestPolicy(enabled=True),
                   mode=mode(), require_nonexpanding_input=True)
    original = request("tiny")
    session.invoke(original)
    assert sent == [session.transport.encode(original)]
    row = record(session)
    assert row["input_composition"]["candidate_reason"] == "final_wire_guard_reversion"
    assert row["reason"] == "input_composition_guard_reversion"
    assert row["prepared"] == original and row["changed_messages"] == []
    assert session.finish()["transformations"] == 0
    session.close()


def test_equal_original_wire_is_allowed_and_original_encoding_precedes_augmentation(tmp_path, sent, monkeypatch):
    session = make(tmp_path, require_nonexpanding_input=True)
    events = []
    encode, augment = ResponsesTransport.encode, session._augment

    def observed_encode(self, chat):
        events.append("encode")
        return encode(self, chat)

    def observed_augment(chat):
        assert events == ["encode"]
        events.append("augment")
        return augment(chat)

    monkeypatch.setattr(ResponsesTransport, "encode", observed_encode)
    monkeypatch.setattr(session, "_augment", observed_augment)
    original = request()
    session.invoke(original)
    assert record(session)["input_composition"]["decision"] == "original_unchanged"
    assert sent == [encode(session.transport, original)]
    session.finish()
    session.close()


def test_disabled_default_keeps_full_component_and_legacy_encode_behavior(tmp_path, sent, full_component, monkeypatch):
    session = make(tmp_path, ponytail=full_component)
    original = request()
    calls = []
    encode = ResponsesTransport.encode

    def observed(self, chat):
        calls.append(deepcopy(chat))
        return encode(self, chat)

    monkeypatch.setattr(ResponsesTransport, "encode", observed)
    augmented, _ = session._augment(original)
    session.invoke(original)
    assert calls == [augmented] and sent == [encode(session.transport, augmented)]
    assert session.require_nonexpanding_input is False
    row = record(session)
    assert row["input_composition"]["decision"] == "disabled"
    assert row["input_composition"]["original"] is None
    assert row["instruction_component_applied"] == "ponytail"
    session.finish()
    session.close()


@pytest.mark.parametrize("cap", ["transport_bytes", "policy_bytes", "policy_tokens"])
def test_caps_are_applied_to_guarded_wire_not_discarded_augmentation(tmp_path, sent, cap):
    original = request()
    wire = transport().encode(original)
    count = tokens.count_tokens(wire)
    t = transport(max_request_bytes=len(wire.encode()) if cap == "transport_bytes" else 524288)
    policy = RequestPolicy(
        version="request-policy-v3", enabled=False,
        max_wire_bytes=len(wire.encode()) if cap == "policy_bytes" else None,
        max_input_tokens=count if cap == "policy_tokens" else None)
    session = make(tmp_path, wire_transport=t, policy=policy, mode=mode(), require_nonexpanding_input=True)
    session.invoke(original)
    assert sent == [wire]
    session.finish()
    session.close()


def test_guard_does_not_waive_caps_when_original_is_too_large(tmp_path, sent):
    original = request()
    wire = transport().encode(original)
    session = make(tmp_path, wire_transport=transport(max_request_bytes=len(wire.encode()) - 1),
                   mode=mode(), require_nonexpanding_input=True)
    with pytest.raises(ValueError, match="final_request_budget"):
        session.invoke(original)
    assert not sent and session.finish()["model_calls"] == 0
    session.close()


@pytest.mark.parametrize("invalid", [0, 1, None, "true", [], {}])
def test_flag_is_strict_boolean_and_rejected_before_output(tmp_path, invalid):
    with pytest.raises(ValueError, match="invalid_nonexpanding_input"):
        make(tmp_path, require_nonexpanding_input=invalid)
    assert not (tmp_path / "run").exists()


def test_flag_is_frozen_and_profile_bound(tmp_path):
    enabled = make(tmp_path, name="on", require_nonexpanding_input=True)
    disabled = make(tmp_path, name="off")
    assert enabled.profile["require_nonexpanding_input"] is True
    assert disabled.profile["require_nonexpanding_input"] is False
    assert enabled.profile_id != disabled.profile_id
    with pytest.raises(AttributeError, match="frozen"):
        enabled.require_nonexpanding_input = False
    for session in (enabled, disabled):
        session.finish()
        session.close()


def test_optimizer_registry_selection_cannot_silently_gain_new_guard(tmp_path):
    with pytest.raises(ValueError, match="nonexpanding_input_optimizer_selection_unsupported"):
        make(tmp_path, backend="local", optimizer=object(), require_nonexpanding_input=True)
    assert not (tmp_path / "run").exists()


def cli_args(tmp_path, *extra):
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return brainspace_tools._parser().parse_args([
        "--workspace", str(workspace), "--session", "cli", "session",
        "--output", str(tmp_path / "runtime"), "--base-url", "http://127.0.0.1:1/not-used",
        "--model", "offline-fixture", "--backend", "none", "--allow-network", *extra])


@pytest.mark.parametrize("enabled", [False, True])
def test_cli_parser_and_session_propagate_flag(tmp_path, enabled):
    args = cli_args(tmp_path, *(["--require-nonexpanding-input"] if enabled else []))
    session = session_cli._session(args)
    assert session.require_nonexpanding_input is enabled
    session.finish()
    session.close()


def test_embedded_old_argparse_object_defaults_to_false(tmp_path):
    args = cli_args(tmp_path)
    if hasattr(args, "require_nonexpanding_input"):
        delattr(args, "require_nonexpanding_input")
    session = session_cli._session(args)
    assert session.require_nonexpanding_input is False
    session.finish()
    session.close()


def test_cli_rejects_guard_with_registry_before_open(tmp_path, monkeypatch):
    args = cli_args(tmp_path, "--require-nonexpanding-input", "--optimizer-db", "not-opened.sqlite",
                    "--optimizer-version", "1", "--workload-id", "w", "--environment-id", "e")
    args.backend = "local"
    monkeypatch.setattr(session_cli.Optimizer, "open", lambda *_: pytest.fail("registry must not open"))
    with pytest.raises(ValueError, match="nonexpanding_input_optimizer_selection_unsupported"):
        session_cli._session(args)


def test_reverted_headroom_work_is_still_recorded_and_cleaned_up(tmp_path, sent, monkeypatch, full_component):
    from brainspace import headroom
    state = []

    class OfflineComponent:
        def __init__(self, path, **kwargs):
            path.mkdir()

        def start(self):
            state.append("start")
            return {"ready": True, "local_inference_inventory_complete": True}

        def prepare(self, chat):
            state.append("prepare")
            return {"model": chat["model"], "messages": deepcopy(chat["messages"])}

        def finish(self):
            state.append("finish")
            return {"offline_test": True, "work_units": 1}

        def close(self):
            state.append("close")
            return {"container_id": None, "container_removed": True}

    monkeypatch.setattr(headroom, "HeadroomContainer", OfflineComponent)
    session = make(tmp_path, backend="headroom", ponytail=full_component,
                   headroom_options={"cache": tmp_path / "cache", "assets": tmp_path / "assets",
                                     "docker_config": None}, require_nonexpanding_input=True)
    # The guarded runtime now avoids even starting a component when no bound
    # result can be accepted. Supply a genuinely eligible offline receipt so
    # this test continues to cover work that ran but was reverted.
    original = request("ordinary source content\n" * 80)
    session.observe_source_read(SourceReadInfo.from_text(
        call_id="r1", tool_name="read_file", source_path="source.txt",
        content=original["messages"][3]["content"], status="success"))
    session.invoke(original, intent="navigation")
    assert sent == [session.transport.encode(original)]
    assert "tools" not in record(session)["prepared"]
    result = session.finish()
    assert result["model_calls"] == 1 and result["transformations"] == 0
    assert result["component"]["headroom_executed"] is True
    assert result["component"]["headroom"]["work_units"] == 1
    assert result["all_in_compute_savings"] is None
    session.close()
    assert state == ["start", "prepare", "finish", "close"]
