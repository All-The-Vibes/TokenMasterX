"""V4 final-wire/recovery wiring; synthetic inputs are NOT savings evidence."""
from copy import deepcopy
import json
import socket

import pytest

from brainspace import tokens
from brainspace.compressors.json_compressor import compress_json
from brainspace.request_policy import RequestPolicy, SourceReadInfo
from brainspace.runtime import RuntimeSession
from brainspace.transport import Reply, ResponsesTransport


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("no real network in JSON guard tests")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


@pytest.fixture
def sent(monkeypatch):
    wires = []

    def send(self, wire):
        wires.append(wire)
        body = {"object": "response", "status": "completed", "model": self.model, "output": [],
                "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}}
        return Reply(True, "ok", True, wire, json.dumps(body), body, 200)

    monkeypatch.setattr(ResponsesTransport, "send", send)
    return wires


def request(content):
    messages = [{"role": "system", "content": "Keep every value and instruction."},
                {"role": "user", "content": "Summarize the JSON data."}]
    for call, path, text in (("data", "data.json", content), ("latest", "note.txt", "Latest source.")):
        messages.extend([
            {"role": "assistant", "content": None, "tool_calls": [{
                "id": call, "type": "function",
                "function": {"name": "read_file", "arguments": json.dumps({"path": path})}}]},
            {"role": "tool", "tool_call_id": call, "content": text},
        ])
    return {"model": "offline-json", "messages": messages}


def make(tmp_path, *, policy=None):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return RuntimeSession(
        workspace=workspace, output=tmp_path / "runtime", session_id="json-v4",
        transport=ResponsesTransport("http://127.0.0.1:1/unused", "offline-json"),
        backend="local", policy=policy or RequestPolicy(version="request-policy-v4", enabled=True,
                                                       min_tool_chars=1),
        require_nonexpanding_input=False)


def bind(session, content, *, status="success"):
    session.observe_source_read(SourceReadInfo.from_text(
        call_id="data", tool_name="read_file", source_path="data.json",
        content=content, status=status))


def last_preparation(session):
    return json.loads((session.output / "preparations.jsonl").read_text("utf-8").splitlines()[-1])


def test_v4_requires_real_full_wire_saving_including_recovery_schema(tmp_path, sent):
    content = json.dumps({"records": [{"id": i, "message": "error remains data", "active": True}
                                      for i in range(80)]}, indent=2)
    original = request(content)
    session = make(tmp_path)
    bind(session, content)
    before = session.transport.encode(original)
    session.invoke(deepcopy(original), intent="aggregate", stable_prefix_messages=2)
    row = last_preparation(session)
    assert session.require_nonexpanding_input is True
    assert session.profile["json_projection_contract"] == "lexical-json-whitespace-with-root-footer-v1"
    assert row["changed_messages"] == [3]
    assert tokens.count_tokens(sent[0]) < tokens.count_tokens(before)
    assert len(sent[0].encode()) <= len(before.encode())
    assert row["prepared"]["messages"][:3] == original["messages"][:3]
    assert row["prepared"]["messages"][4:] == original["messages"][4:]
    payload, reference = row["prepared"]["messages"][3]["content"].rsplit("\n", 1)
    assert payload == compress_json(content, intent="conservative")
    assert session.ccr.retrieve(reference).encode() == content.encode()
    assert any(tool["name"] == "retrieve_original" for tool in json.loads(sent[0])["tools"])
    result = session.finish()
    assert result["transformations"] == result["model_calls"] == 1
    assert result["quality_verified"] is None and result["all_in_compute_savings"] is None
    assert session.close()["complete"]


def test_recovery_overhead_cannot_turn_small_compaction_into_inflation(tmp_path, sent):
    content = '{\n  "value": 7\n}\n'
    original = request(content)
    session = make(tmp_path)
    bind(session, content)
    session.invoke(original, intent="aggregate")
    assert sent == [session.transport.encode(original)]
    assert last_preparation(session)["changed_messages"] == []
    assert session.finish()["transformations"] == 0
    session.close()


@pytest.mark.parametrize("intent", ["exact", "edit", "debug", "unknown"])
def test_protected_intents_restore_original_including_no_schema_tax(tmp_path, sent, intent):
    content = json.dumps({"records": list(range(90))}, indent=4)
    original = request(content)
    session = make(tmp_path)
    bind(session, content)
    session.invoke(original, intent=intent)
    assert sent == [session.transport.encode(original)]
    assert session.finish()["transformations"] == 0
    session.close()


@pytest.mark.parametrize("status", ["error", "unknown"])
def test_failed_or_unknown_read_never_gets_a_semantic_exception(tmp_path, sent, status):
    content = json.dumps({"records": list(range(90))}, indent=4)
    original = request(content)
    session = make(tmp_path)
    bind(session, content, status=status)
    session.invoke(original, intent="aggregate")
    assert sent == [session.transport.encode(original)]
    assert session.finish()["transformations"] == 0
    session.close()


def test_caps_apply_after_v4_composition_selection(tmp_path, sent):
    content = '{\n  "value": 7\n}'
    original = request(content)
    policy = RequestPolicy(version="request-policy-v4", enabled=True, min_tool_chars=1,
                           max_wire_bytes=1)
    session = make(tmp_path, policy=policy)
    bind(session, content)
    with pytest.raises(ValueError, match="budget"):
        session.invoke(original, intent="aggregate")
    assert not sent and session.finish()["model_calls"] == 0
    session.close()
