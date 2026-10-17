"""Offline selection tests; fake upstream projections, real guards and counter.

The optional recorded projection replay makes no Docker/model/inference calls
and never modifies its evidence. Synthetic fixtures are not savings evidence.
"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import socket
from typing import Any

import pytest

from brainspace import headroom, ponytail, tokens
from brainspace.protected_text import protected_text_preserved
from brainspace.request_policy import RequestPolicy, SourceReadInfo
from brainspace.runtime import RuntimeSession
from brainspace.task_mode import TaskContract, task_local_mode
from brainspace.transport import Reply, ResponsesTransport


FENCE = "```python\nraise ValueError('retain this exact code')\n```"
GUIDANCE = "Synthetic optional guidance; not an upstream performance fixture. " * 350


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("network forbidden")
    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)


@pytest.fixture
def component(monkeypatch):
    digest = hashlib.sha256(GUIDANCE.encode()).hexdigest()
    monkeypatch.setattr(ponytail, "PINNED_SOURCE_COMMIT", "a" * 40)
    monkeypatch.setattr(ponytail, "PINNED_INSTRUCTIONS_SHA256", digest)
    return ponytail.PonytailInstructions(GUIDANCE, "a" * 40, digest)


@pytest.fixture
def sent(monkeypatch):
    wires = []

    def send(self, wire):
        wires.append(wire)
        body = {"model": self.model, "output": [], "usage": {
            "input_tokens": 10, "output_tokens": 2, "total_tokens": 12}}
        return Reply(True, "ok", True, wire, json.dumps(body), body, 200)

    monkeypatch.setattr(ResponsesTransport, "send", send)
    return wires


def upstream(monkeypatch, projection=None):
    state: dict[str, Any] = {"prepare": 0, "finish": 0, "close": 0, "inputs": [], "outputs": []}

    class FakeHeadroom:
        def __init__(self, path, **kwargs):
            path.mkdir()

        def start(self):
            return {"ready": True, "local_inference_inventory_complete": True}

        def prepare(self, chat):
            state["prepare"] += 1
            state["inputs"].append(deepcopy(chat))
            messages = deepcopy(chat["messages"])
            if projection:
                messages = projection(messages)
            else:
                for message in messages:
                    if message["role"] == "tool":
                        message["content"] = "Retained operational facts.\n" + FENCE
            result = {"model": chat["model"], "messages": messages}
            state["outputs"].append(deepcopy(result))
            return result

        def finish(self):
            state["finish"] += 1
            return {"fixture_only": True}

        def close(self):
            state["close"] += 1
            return {"container_id": None}

    monkeypatch.setattr(headroom, "HeadroomContainer", FakeHeadroom)
    return state


def request(size=90, *, original_guidance=None, original_tools=True):
    content = "".join(f"Operational detail {i}: retain the documented boundary.\n" for i in range(size))
    content += FENCE
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "System must remain exact."},
        {"role": "developer", "content": "Developer must remain exact."},
        {"role": "user", "content": "Synthesize documents; preserve protected code."},
    ]
    if original_guidance is not None:
        messages.append({"role": "user", "content": original_guidance})
    for call_id, body in (("old", content), ("recent", "Newest result remains exact.\n" + FENCE)):
        messages.extend([
            {"role": "assistant", "content": None, "tool_calls": [{
                "id": call_id, "type": "function", "function": {
                    "name": "fetch_artifact", "arguments": '{"path":"' + call_id + '.md"}'}}]},
            {"role": "tool", "tool_call_id": call_id, "content": body},
        ])
    chat = {"model": "offline-guidance", "messages": messages}
    if original_tools:
        chat["tools"] = RuntimeSession.recovery_tools()
    return chat


def make(tmp_path, component=None, transport=None, **options):
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    session = RuntimeSession(
        workspace=workspace, output=tmp_path / "run", session_id="selection",
        transport=transport or ResponsesTransport(
            base_url="http://127.0.0.1:1/not-used", model="offline-guidance"),
        backend="headroom", ponytail=component,
        headroom_options={"cache": tmp_path / "cache", "assets": tmp_path / "assets",
                          "docker_config": None}, **options)
    return session


def bind(session, chat):
    for message in chat["messages"]:
        if message["role"] == "tool":
            session.observe_source_read(SourceReadInfo.from_text(
                call_id=message["tool_call_id"], tool_name="fetch_artifact",
                source_path=message["tool_call_id"] + ".md", content=message["content"], status="success"))


def row(session):
    return json.loads((session.output / "preparations.jsonl").read_text().splitlines()[-1])


def test_optional_guidance_elision_preserves_validated_projection_and_exact_originals(
        tmp_path, monkeypatch, sent, component):
    state = upstream(monkeypatch)
    session = make(tmp_path, component, require_nonexpanding_input=True)
    guidance = "Optional execution guidance; the user's actual task and requested depth take precedence.\n" + GUIDANCE
    original = request(original_guidance=guidance)
    before = deepcopy(original)
    bind(session, original)
    session.invoke(original, intent="overview")
    receipt = row(session)
    assert receipt["input_composition"]["decision"] == "optional_guidance_elided"
    assert receipt["reason"] == "optional_guidance_elided"
    assert receipt["instruction_component_configured"] == "ponytail"
    assert receipt["instruction_component_applied"] == receipt["instruction_component"] == "none"
    prepared = receipt["prepared"]
    changed = next(i for i, m in enumerate(original["messages"]) if m["role"] == "tool")
    assert receipt["changed_messages"] == [changed]  # Shifted back after deletion.
    assert len(prepared["messages"]) == len(original["messages"])
    expected = deepcopy(original)
    expected["messages"][changed]["content"] = prepared["messages"][changed]["content"]
    assert prepared == expected and original == before
    assert protected_text_preserved(original["messages"][changed]["content"], prepared["messages"][changed]["content"])
    match = re.search(r"\[\[BR:[^\]]+\]\]", prepared["messages"][changed]["content"])
    assert match is not None
    reference = match[0]
    assert session.ccr.retrieve(reference) == original["messages"][changed]["content"]
    metrics = receipt["input_composition"]
    assert metrics["optional_guidance_elided"] == metrics["final"]
    assert metrics["candidate"]["reference_tokens"] >= metrics["original"]["reference_tokens"]
    assert metrics["candidate_reason"] == "headroom_with_exact_root_recovery"
    assert metrics["optional_guidance_removed_index"] == 2
    assert tokens.count_tokens(sent[0]) < tokens.count_tokens(session.transport.encode(original))
    assert len(sent[0].encode()) <= len(session.transport.encode(original).encode())
    assert state["prepare"] == 1 and len(sent) == 1
    assert state["outputs"][0]["messages"][2]["content"] == guidance  # Detached, not mutated.
    assert session.finish()["transformations"] == 1
    session.close()
    assert state["finish"] == state["close"] == 1


def test_recovery_schema_overhead_still_forces_exact_original_fallback(tmp_path, monkeypatch, sent, component):
    upstream(monkeypatch)
    session = make(tmp_path, component, require_nonexpanding_input=True)
    original = request(size=12, original_tools=False)
    bind(session, original)
    session.invoke(original, intent="overview")
    receipt = row(session)
    assert receipt["input_composition"]["candidate_reason"] == "headroom_with_exact_root_recovery"
    assert receipt["input_composition"]["optional_guidance_elided"] is not None
    assert receipt["input_composition"]["decision"] == "whole_request_reversion"
    assert receipt["prepared"] == original and receipt["changed_messages"] == []
    assert sent == [session.transport.encode(original)]
    assert session.finish()["transformations"] == 0
    session.close()


class TableTransport:
    """Non-provider encoder isolates ordering and two independent wire guards."""
    model, max_request_bytes, max_output_tokens = "offline-guidance", 1000000, 2048

    def __init__(self, *, original, augmented, full, elided):
        self.wires = original, augmented, full, elided
        self.sent = []

    def encode(self, chat):
        guidance = any(str(m.get("content", "")).startswith("Optional execution guidance;")
                       for m in chat["messages"])
        reduced = any("[[BR:" in str(m.get("content", "")) for m in chat["messages"])
        return self.wires[(2 if guidance else 3) if reduced else (1 if guidance else 0)]

    def send(self, wire):
        self.sent.append(wire)
        body = {"model": self.model}
        return Reply(True, "ok", True, wire, json.dumps(body), body, 200)


@pytest.mark.parametrize("original,elided", [
    ("alpha beta gamma", "one two three"),  # Equal reference cost is not enough.
    ("a b c d e", "中中中中"),  # Fewer tokens but more UTF-8 bytes.
    ("abc " * 100, "a " * 101),  # Fewer bytes but more tokens.
])
def test_alternative_requires_strict_tokens_and_nonincreasing_utf8(tmp_path, monkeypatch, component, original, elided):
    upstream(monkeypatch)
    transport = TableTransport(original=original, augmented="z " * 1000, full="z " * 500, elided=elided)
    session = make(tmp_path, component, transport, require_nonexpanding_input=True)
    chat = request()
    bind(session, chat)
    session.invoke(chat, intent="overview")
    assert transport.sent == [original]
    assert row(session)["input_composition"]["decision"] == "whole_request_reversion"
    assert row(session)["input_composition"]["optional_guidance_elided"]["reference_tokens"] == tokens.count_tokens(elided)
    assert row(session)["prepared"] == chat and row(session)["changed_messages"] == []
    assert session.finish()["transformations"] == 0
    session.close()


def test_augmented_guard_does_not_destroy_validated_projection_before_alternative_selection(
        tmp_path, monkeypatch, component):
    state = upstream(monkeypatch)
    transport = TableTransport(original="x " * 100, augmented="x " * 200,
                               full="x " * 300, elided="x " * 50)
    session = make(tmp_path, component, transport, require_nonexpanding_input=True)
    chat = request()
    bind(session, chat)
    session.invoke(chat, intent="overview")
    assert transport.sent == [transport.wires[3]]
    receipt = row(session)
    assert receipt["input_composition"]["candidate_reason"] == "final_wire_guard_reversion"
    assert receipt["input_composition"]["projection_reason"] == "headroom_with_exact_root_recovery"
    assert receipt["input_composition"]["candidate"]["reference_tokens"] == tokens.count_tokens(transport.wires[2])
    assert receipt["changed_messages"] and state["prepare"] == 1
    assert session.finish()["transformations"] == 1
    session.close()


@pytest.mark.parametrize("flag", [False, True])
def test_profitable_full_composition_and_disabled_flag_keep_guidance(
        tmp_path, monkeypatch, component, sent, flag):
    upstream(monkeypatch)
    session = make(tmp_path, component, require_nonexpanding_input=flag)
    chat = request(size=1200 if flag else 90)
    bind(session, chat)
    session.invoke(chat, intent="overview")
    receipt = row(session)
    assert receipt["instruction_component_applied"] == "ponytail"
    assert receipt["input_composition"]["decision"] == ("nonexpanding_composition" if flag else "disabled")
    assert receipt["input_composition"]["optional_guidance_elided"] is None
    assert len(receipt["prepared"]["messages"]) == len(chat["messages"]) + 1
    assert session.finish()["transformations"] == 1 and len(sent) == 1
    session.close()


@pytest.mark.parametrize("flag", [False, True])
def test_local_mode_is_elided_only_with_the_explicit_flag(tmp_path, monkeypatch, sent, flag):
    upstream(monkeypatch)
    mode = task_local_mode(TaskContract(GUIDANCE, (), ("Verify facts.",), "JSON"))
    session = make(tmp_path, mode=mode, require_nonexpanding_input=flag)
    chat = request()
    bind(session, chat)
    session.invoke(chat, intent="overview")
    assert row(session)["input_composition"]["decision"] == ("optional_guidance_elided" if flag else "disabled")
    assert row(session)["instruction_component_configured"] == "local"
    assert row(session)["instruction_component_applied"] == ("none" if flag else "local")
    assert len(sent) == 1
    session.finish()
    session.close()


def test_elided_projection_keeps_new_recovery_schemas_and_all_metadata(tmp_path, monkeypatch, component):
    upstream(monkeypatch)

    class CanonicalTransport(TableTransport):
        def encode(self, chat):
            return tokens.serialize(chat)

    transport = CanonicalTransport(original="", augmented="", full="", elided="")
    session = make(tmp_path, component, transport, require_nonexpanding_input=True)
    chat = request(original_tools=False)
    chat["metadata"] = {"opaque": ["keep", 0, None]}
    chat["messages"][0]["metadata"] = {"protected": True}
    for message in chat["messages"]:
        if message["role"] == "tool":
            message["source"] = "metadata-must-survive"
    bind(session, chat)
    session.invoke(chat, intent="overview")
    receipt = row(session)
    assert receipt["input_composition"]["decision"] == "optional_guidance_elided"
    expected = deepcopy(chat)
    expected["tools"] = RuntimeSession.recovery_tools()
    old_index = next(i for i, m in enumerate(chat["messages"]) if m["role"] == "tool")
    expected["messages"][old_index]["content"] = receipt["prepared"]["messages"][old_index]["content"]
    assert receipt["prepared"] == expected
    assert json.loads(transport.sent[0]) == expected
    assert session.finish()["transformations"] == 1
    session.close()


def test_guard_strategy_versions_profile_without_changing_disabled_profile(tmp_path, component):
    enabled = make(tmp_path, component, require_nonexpanding_input=True)
    old_profile = enabled.profile
    assert old_profile.pop("composition_guard_version") == "optional-guidance-selection-v1"
    old_id = old_profile["version"] + ":" + hashlib.sha256(tokens.serialize(old_profile).encode()).hexdigest()
    assert enabled.profile_id != old_id
    assert old_profile["require_nonexpanding_input"] is True
    detached = enabled.profile
    detached["composition_guard_version"] = "tampered"
    assert enabled.profile["composition_guard_version"] == "optional-guidance-selection-v1"
    other = tmp_path / "disabled"
    other.mkdir()
    disabled = make(other, component)
    legacy_profile = disabled.profile
    assert legacy_profile["require_nonexpanding_input"] is False
    assert "composition_guard_version" not in legacy_profile
    expected_id = legacy_profile["version"] + ":" + hashlib.sha256(tokens.serialize(legacy_profile).encode()).hexdigest()
    assert disabled.profile_id == expected_id
    for session in (enabled, disabled):
        session.finish()
        session.close()


@pytest.mark.parametrize("block", ["no_receipt", "protected", "structural", "fence"])
def test_rejected_or_protected_projection_is_not_revived(tmp_path, monkeypatch, sent, component, block):
    def projection(messages):
        for message in messages:
            if message["role"] == "tool":
                message["content"] = "small" if block == "fence" else "Small.\n" + FENCE
                if block == "structural":
                    message["tool_call_id"] = "forged"
                break
        return messages
    state = upstream(monkeypatch, projection)
    session = make(tmp_path, component, require_nonexpanding_input=True)
    chat = request()
    if block != "no_receipt":
        bind(session, chat)
    old_index = next(i for i, m in enumerate(chat["messages"]) if m["role"] == "tool")
    session.invoke(chat, intent="overview", exact_message_indices=(old_index,) if block == "protected" else ())
    assert sent == [session.transport.encode(chat)]
    assert row(session)["input_composition"]["optional_guidance_elided"] is None
    assert session.finish()["transformations"] == 0
    assert state["prepare"] == (0 if block in ("no_receipt", "protected") else 1)
    session.close()


@pytest.mark.parametrize("cap", ["input", "policy_bytes", "transport_bytes", "output"])
def test_caps_still_apply_after_alternative_selection(tmp_path, monkeypatch, component, cap):
    upstream(monkeypatch)
    transport = TableTransport(original="x " * 100, augmented="x " * 300,
                               full="x " * 200, elided="x " * 50)
    policy = RequestPolicy(enabled=False, min_tool_chars=512)
    if cap == "input":
        policy = replace(policy, max_input_tokens=tokens.count_tokens(transport.wires[3]) - 1)
    elif cap == "policy_bytes":
        policy = replace(policy, max_wire_bytes=len(transport.wires[3].encode()) - 1)
    elif cap == "transport_bytes":
        transport.max_request_bytes = len(transport.wires[3].encode()) - 1
    else:
        policy = replace(policy, max_output_tokens=transport.max_output_tokens - 1)
    session = make(tmp_path, component, transport, policy=policy, require_nonexpanding_input=True)
    chat = request()
    bind(session, chat)
    with pytest.raises(ValueError, match="budget"):
        session.invoke(chat, intent="overview")
    assert transport.sent == [] and session.finish()["model_calls"] == 0
    session.close()


def test_frozen_attempt_three_replay_uses_saved_projection_not_inference(tmp_path, monkeypatch, sent):
    root_value = os.environ.get("TOKENMASTER_TEST_GUIDANCE_REPLAY")
    if not root_value:
        pytest.skip("optional frozen projection receipt not supplied")
    root = Path(root_value)
    preparations = root / "preparations.jsonl"
    assert hashlib.sha256(preparations.read_bytes()).hexdigest() == (
        "b71e4b6c256b95314bde1d9940b12726cd9166b907cdd2e814ee541465a9cdd8")
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    old = next(r for r in map(json.loads, preparations.read_text("utf-8").splitlines()) if r["attempt"] == 3)
    assert old["input_composition"]["decision"] == "whole_request_reversion"
    saved_session = json.loads((root / "session.json").read_text("utf-8"))
    component = ponytail.PonytailInstructions(**saved_session["profile"]["ponytail"])
    rpc = [json.loads(line) for line in (root / "headroom/rpc.jsonl").read_text("utf-8").splitlines()]
    pending = next(r["request"] for r in rpc if r["id"] == "3" and "request" in r)
    response = next(r["response"] for r in rpc if r["id"] == "3" and "response" in r)
    assert response["ok"] is True

    def projection(messages):
        assert messages == pending["messages"]
        return deepcopy(response["result"]["messages"])

    state = upstream(monkeypatch, projection)
    transport = ResponsesTransport(base_url="http://127.0.0.1:1/not-used",
                                   model=saved_session["profile"]["model"],
                                   max_output_tokens=saved_session["profile"]["transport_declaration"]["max_output_tokens"],
                                   reasoning_effort=saved_session["profile"]["transport_declaration"]["reasoning_effort"])
    session = make(tmp_path, component, transport, require_nonexpanding_input=True)
    for line in (root / "source-reads.jsonl").read_text("utf-8").splitlines():
        session.observe_source_read(SourceReadInfo.from_dict(json.loads(line)))
    session.invoke(old["original"], intent="overview")
    receipt = row(session)
    assert receipt["input_composition"]["decision"] == "optional_guidance_elided"
    assert receipt["input_composition"]["original"] == old["input_composition"]["original"]
    assert receipt["input_composition"]["candidate"]["reference_tokens"] >= receipt["input_composition"]["original"]["reference_tokens"]
    assert receipt["input_composition"]["final"]["reference_tokens"] < receipt["input_composition"]["original"]["reference_tokens"]
    assert receipt["instruction_component_applied"] == "none" and state["prepare"] == 1
    assert session.finish()["transformations"] == 1 and len(sent) == 1
    session.close()
    assert before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
