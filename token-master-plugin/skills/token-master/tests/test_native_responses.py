"""Offline native Responses codec checks; no bridge/native-host qualification."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import socket
import subprocess

import pytest

from brainspace.native_responses import NativeResponsesEnvelope
from brainspace.request_policy import _protected, _tool_indices
from brainspace.runtime import RuntimeSession
from brainspace.transport import Reply


GUIDANCE = "Optional execution guidance; the user's actual task and requested depth take precedence.\nBe concise."
CAPTURE = (Path(__file__).resolve().parents[4] / "evidence" / "integrated-runtime-20261009"
           / "native-host-route" / "probe-002" / "provider-requests.json")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("codec checks must not invoke providers or processes")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


def body():
    text = 'same "quoted" \\ path\n雪🙂'
    return {
        "model": "offline-model", "stream": True, "store": False,
        "include": ["reasoning.encrypted_content"], "prompt_cache_key": "frozen-cache",
        "reasoning": {"effort": "high", "summary": "auto"},
        "metadata": {"nested": [False, {"value": 1}]}, "max_output_tokens": 100,
        "parallel_tool_calls": True,
        "tools": [{"type": "function", "name": "view", "description": "Read text.",
                   "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                                  "required": ["path"]}, "strict": False}],
        "input": [
            {"type": "message", "role": "system", "content": [
                {"type": "input_text", "text": "Protected system.",
                 "prompt_cache_breakpoint": {"type": "ephemeral", "nested": [1, False]}}]},
            {"role": "user", "content": text, "id": "u1"},
            {"type": "reasoning", "id": "rs1", "encrypted_content": "opaque/encrypted==",
             "summary": [{"type": "summary_text", "text": "Opaque summary"}], "status": "completed"},
            {"type": "function_call", "id": "fc1", "call_id": "call1", "name": "view",
             "arguments": '{"path":"a.json","lexeme":-0}', "status": "completed", "phase": "analysis"},
            {"type": "function_call_output", "call_id": "call1", "output": text,
             "id": "out1", "status": "completed", "metadata": {"preserved": [1, False]}},
            {"type": "message", "id": "m1", "role": "assistant", "phase": "final_answer",
             "status": "completed", "content": [
                 {"type": "output_text", "text": text, "annotations": [], "logprobs": []}]},
        ],
    }


def recovery_body():
    native = body()
    standards = RuntimeSession.recovery_tools()
    aliases = {tool["function"]["name"]: "tokenmaster-" + tool["function"]["name"] for tool in standards}
    for standard in standards:
        function = deepcopy(standard["function"])
        function["name"] = aliases[function["name"]]
        function["description"] = "Native registered description (not the internal planner description)."
        function["strict"] = False
        function["parameters"].pop("additionalProperties")
        for prop in function["parameters"]["properties"].values():
            prop["description"] = "Native help."
        native["tools"].append({"type": "function", **function})
    native["input"][3]["name"] = aliases["retrieve_original"]
    native["input"][3]["arguments"] = '{"ref":"opaque-reference","offset":0}'
    return native, aliases, standards


def test_actual_two_captured_native_requests_roundtrip_without_view_rename():
    captures = json.loads(CAPTURE.read_text(encoding="utf-8"))
    assert len(captures) == 2
    for row in captures:
        native = row["body"]
        codec = NativeResponsesEnvelope(native)
        canonical = codec.canonical_request
        assert codec.render(canonical) == native
        assert json.loads(codec.encode(canonical)) == native
        assert canonical["tools"][0]["function"]["name"] == "view"
        assert canonical["messages"][0]["content"] == "".join(
            block["text"] for block in native["input"][0]["content"])
        assert "prompt_cache_breakpoint" not in canonical["messages"][0]
        for message in canonical["messages"]:
            for call in message.get("tool_calls", []):
                assert call["function"]["name"] == "view"
        assert len(_tool_indices(canonical)) == (1 if len(native["input"]) > 2 else 0)


def test_rich_native_metadata_and_opaque_reasoning_roundtrip_in_exact_order():
    native = body()
    codec = NativeResponsesEnvelope(native)
    canonical = codec.canonical_request
    assert codec.render(canonical) == native
    assert "opaque/encrypted==" in codec.encode(canonical)
    assert canonical["messages"][0] == {"role": "system", "content": "Protected system."}
    assert isinstance(codec.native_to_canonical, tuple)
    assert codec.native_to_canonical[2] is None  # Opaque item is not fabricated assistant prose.
    assert codec.native_to_canonical[3] != codec.native_to_canonical[4]
    assert len(codec.native_to_canonical) == len(native["input"])
    assert _tool_indices(canonical) == [codec.native_to_canonical[4]]


def test_immutable_snapshots_and_returned_values_are_detached():
    native, aliases, standards = recovery_body()
    frozen = deepcopy(native)
    codec = NativeResponsesEnvelope(native, recovery_aliases=aliases, recovery_tools=standards)
    baseline = codec.canonical_request
    native["input"][2]["encrypted_content"] = "changed"
    aliases["retrieve_original"] = "changed"
    standards[0]["function"]["parameters"]["required"].clear()
    first = codec.canonical_request
    first["messages"][0]["content"] = "changed"
    rendered = codec.render(baseline)
    rendered["tools"].clear()
    assert codec.canonical_request == baseline
    assert codec.render(baseline) == frozen
    with pytest.raises((FrozenInstanceError, AttributeError)):
        setattr(codec, "native_to_canonical", ())


def test_only_selected_tool_content_changes_not_identical_text_elsewhere():
    native = body()
    codec = NativeResponsesEnvelope(native)
    canonical = codec.canonical_request
    canonical["messages"][codec.native_to_canonical[4]]["content"] = 'short "雪"\n'
    expected = deepcopy(native)
    expected["input"][4]["output"] = 'short "雪"\n'
    assert codec.render(canonical) == expected
    assert codec.render(codec.canonical_request) == native


def test_optional_guidance_and_lower_existing_budget_preserve_every_original_item():
    native = body()
    codec = NativeResponsesEnvelope(native)
    canonical = codec.canonical_request
    first_user = next(i for i, msg in enumerate(canonical["messages"]) if msg["role"] == "user")
    canonical["messages"].insert(first_user, {"role": "user", "content": GUIDANCE})
    canonical["max_tokens"] = 40
    result = codec.render(canonical)
    assert result["max_output_tokens"] == 40 and "max_tokens" not in result
    inserted = result["input"].pop(1)
    assert inserted == {"type": "message", "role": "user", "content": GUIDANCE}
    expected = deepcopy(native)
    expected["max_output_tokens"] = 40
    assert result == expected


def test_parallel_calls_group_once_and_preserve_native_positions_with_opaque_items():
    native = body()
    second = {**native["input"][3], "id": "fc2", "call_id": "call2", "arguments": '{"path":"b.json"}'}
    native["input"].insert(4, second)
    # Reasoning between results must not create an invalid canonical assistant turn.
    native["input"].insert(6, {"type": "reasoning", "id": "rs2", "encrypted_content": "second", "summary": []})
    native["input"].insert(7, {"type": "function_call_output", "call_id": "call2", "output": "second result"})
    codec = NativeResponsesEnvelope(native)
    canonical = codec.canonical_request
    group = canonical["messages"][codec.native_to_canonical[3]]
    assert [call["id"] for call in group["tool_calls"]] == ["call1", "call2"]
    assert codec.native_to_canonical[3] == codec.native_to_canonical[4]
    assert len(_tool_indices(canonical)) == 2
    assert codec.render(canonical) == native


@pytest.mark.parametrize("damage", [
    "system", "user", "assistant", "block_metadata", "message_id", "phase", "call_id",
    "arguments", "call_name", "result_metadata", "tool_schema", "top_metadata", "reasoning",
    "opaque_reasoning", "reorder", "delete", "new_tool", "bool_for_number",
])
def test_protected_fields_deletion_reorder_and_tool_mutations_rejected(damage):
    codec = NativeResponsesEnvelope(body())
    canonical = codec.canonical_request
    messages = canonical["messages"]
    call = messages[codec.native_to_canonical[3]]["tool_calls"][0]
    if damage in ("system", "user", "assistant"):
        next(m for m in messages if m["role"] == damage)["content"] = "tampered"
    elif damage == "block_metadata":
        messages[0]["prompt_cache_breakpoint"] = {"tampered": True}
    elif damage == "message_id":
        messages[1]["id"] = "changed"
    elif damage == "phase":
        messages[-1]["phase"] = "changed"
    elif damage == "call_id":
        call["id"] = "changed"
    elif damage in ("arguments", "call_name"):
        call["function"]["arguments" if damage == "arguments" else "name"] = "changed"
    elif damage == "result_metadata":
        messages[codec.native_to_canonical[4]]["unknown"] = "changed"
    elif damage == "tool_schema":
        canonical["tools"][0]["function"]["description"] = "changed"
    elif damage == "top_metadata":
        canonical["prompt_cache_key"] = "changed"
    elif damage == "reasoning":
        canonical["reasoning"]["effort"] = "low"
    elif damage == "opaque_reasoning":
        canonical["_native_responses_opaque"][0]["item"]["encrypted_content"] = "changed"
    elif damage == "reorder":
        messages.reverse()
    elif damage == "delete":
        messages.pop()
    elif damage == "new_tool":
        canonical["tools"].extend(RuntimeSession.recovery_tools())
    else:
        canonical["metadata"]["nested"][1]["value"] = True
    with pytest.raises(ValueError):
        codec.render(canonical)


@pytest.mark.parametrize("value", [0, -1, 101, True, 40.0, "40", None])
def test_invalid_or_raised_budget_rejected(value):
    codec = NativeResponsesEnvelope(body())
    canonical = codec.canonical_request
    canonical["max_tokens"] = value
    with pytest.raises(ValueError):
        codec.render(canonical)


def test_budget_cannot_be_added_when_native_budget_was_absent():
    native = body()
    del native["max_output_tokens"]
    codec = NativeResponsesEnvelope(native)
    canonical = codec.canonical_request
    canonical["max_tokens"] = 20
    with pytest.raises(ValueError):
        codec.render(canonical)


def test_json_strings_are_not_implicitly_coerced_into_request_objects():
    native = body()
    with pytest.raises(ValueError):
        NativeResponsesEnvelope(json.dumps(native))  # type: ignore[arg-type]
    codec = NativeResponsesEnvelope(native)
    with pytest.raises(ValueError):
        codec.render(json.dumps(codec.canonical_request))  # type: ignore[arg-type]


def test_guidance_index_shift_still_changes_only_the_bound_tool_result():
    native = body()
    codec = NativeResponsesEnvelope(native)
    canonical = codec.canonical_request
    canonical["messages"].insert(1, {"role": "user", "content": GUIDANCE})
    result_index = codec.native_to_canonical[4]
    assert result_index is not None
    canonical["messages"][result_index + 1]["content"] = "bound replacement"
    actual = codec.render(canonical)
    actual["input"].pop(1)
    expected = deepcopy(native)
    expected["input"][4]["output"] = "bound replacement"
    assert actual == expected


@pytest.mark.parametrize("damage", ["wrong_position", "two", "assistant", "metadata", "unmarked", "no_user"])
def test_only_one_marked_guidance_before_first_user_is_allowed(damage):
    native = body()
    if damage == "no_user":
        native["input"][1]["role"] = "developer"
    codec = NativeResponsesEnvelope(native)
    canonical = codec.canonical_request
    added = {"role": "user", "content": GUIDANCE}
    if damage == "assistant":
        added["role"] = "assistant"
    elif damage == "metadata":
        added["id"] = "new-id"
    elif damage == "unmarked":
        added["content"] = "unmarked extra task"
    canonical["messages"].insert(0 if damage == "wrong_position" else 1, added)
    if damage == "two":
        canonical["messages"].insert(1, deepcopy(added))
    with pytest.raises(ValueError):
        codec.render(canonical)


@pytest.mark.parametrize("damage", [
    "missing_result", "orphan_result", "duplicate_call", "duplicate_item_id",
    "unknown_item", "image", "structured_output", "stateful", "conversation",
    "input_reference", "nonfinite", "ambiguous_messages", "incomplete_call", "builtin_tool",
])
def test_unsupported_or_incomplete_native_requests_fail_explicitly(damage):
    native = body()
    if damage == "missing_result":
        del native["input"][4]
    elif damage == "orphan_result":
        native["input"][4]["call_id"] = "unknown"
    elif damage == "duplicate_call":
        native["input"].insert(4, {**native["input"][3], "id": "fc-other"})
    elif damage == "duplicate_item_id":
        native["input"][2]["id"] = native["input"][1]["id"]
    elif damage == "unknown_item":
        native["input"].insert(2, {"type": "configuration_update", "reasoning": {"effort": "low"}})
    elif damage == "image":
        native["input"][0]["content"].append({"type": "input_image", "image_url": "synthetic"})
    elif damage == "structured_output":
        native["input"][4]["output"] = [{"type": "input_text", "text": "unsupported output shape"}]
    elif damage == "stateful":
        native["previous_response_id"] = "resp_previous"
    elif damage == "conversation":
        native["conversation"] = "conv"
    elif damage == "input_reference":
        native["input"].insert(2, {"type": "item_reference", "id": "item_previous"})
    elif damage == "nonfinite":
        native["metadata"]["number"] = float("nan")
    elif damage == "ambiguous_messages":
        native["messages"] = []
    elif damage == "incomplete_call":
        native["input"][3]["status"] = "in_progress"
    else:
        native["tools"].append({"type": "web_search"})
    with pytest.raises(ValueError):
        NativeResponsesEnvelope(native)


def test_recovery_aliases_normalize_only_registered_tools_and_restore_verbatim():
    native, aliases, standards = recovery_body()
    codec = NativeResponsesEnvelope(native, recovery_aliases=aliases, recovery_tools=standards)
    canonical = codec.canonical_request
    assert canonical["tools"][1:] == standards
    group = canonical["messages"][codec.native_to_canonical[3]]
    assert group["tool_calls"][0]["function"]["name"] == "retrieve_original"
    assert canonical["tools"][0]["function"]["name"] == "view"
    assert codec.render(canonical) == native
    # Uses the real RuntimeSession augmentation code without constructing workers.
    session = object.__new__(RuntimeSession)
    object.__setattr__(session, "ponytail", None)
    object.__setattr__(session, "mode", None)
    object.__setattr__(session, "backend", "headroom")
    augmented, inserted = session._augment(canonical)
    assert inserted is None and augmented == canonical
    assert codec.render(augmented) == native


@pytest.mark.parametrize("damage", [
    "unregistered", "duplicate_target", "duplicate_tool", "missing_alias", "missing_standard",
    "unknown_alias", "wrong_type", "wrong_required", "extra_property", "extra_constraint",
    "reserved_collision", "canonical_call_without_alias",
])
def test_missing_conflicting_or_incompatible_recovery_aliases_rejected(damage):
    native, aliases, standards = recovery_body()
    if damage == "unregistered":
        aliases["retrieve_original"] = "not-registered"
    elif damage == "duplicate_target":
        aliases["headroom_retrieve"] = aliases["retrieve_original"]
    elif damage == "duplicate_tool":
        native["tools"].append(deepcopy(native["tools"][1]))
    elif damage == "missing_alias":
        del aliases["retrieve_original"]
    elif damage == "missing_standard":
        standards.pop(0)
    elif damage == "unknown_alias":
        aliases["arbitrary"] = "view"
    elif damage == "wrong_type":
        native["tools"][1]["parameters"]["properties"]["offset"]["type"] = "string"
    elif damage == "wrong_required":
        native["tools"][1]["parameters"]["required"] = ["ref"]
    elif damage == "extra_property":
        native["tools"][1]["parameters"]["properties"]["command"] = {"type": "string"}
    elif damage == "extra_constraint":
        native["tools"][1]["parameters"]["properties"]["offset"]["enum"] = [0]
    elif damage == "reserved_collision":
        native["tools"].append({"type": "function", **deepcopy(standards[0]["function"])})
    else:
        native["input"][3]["name"] = "retrieve_original"
    with pytest.raises(ValueError):
        NativeResponsesEnvelope(native, recovery_aliases=aliases, recovery_tools=standards)


def test_unqualified_canonical_recovery_registration_is_not_implicitly_trusted():
    native = body()
    native["tools"].append({"type": "function", **RuntimeSession.recovery_tools()[0]["function"]})
    with pytest.raises(ValueError):
        NativeResponsesEnvelope(native)


def test_explicit_identity_alias_is_allowed_without_rewriting_native_schema():
    native = body()
    standards = RuntimeSession.recovery_tools()[:1]
    native["tools"].append({"type": "function", **deepcopy(standards[0]["function"])})
    codec = NativeResponsesEnvelope(native, recovery_aliases={"retrieve_original": "retrieve_original"},
                                   recovery_tools=standards)
    assert codec.render(codec.canonical_request) == native


def continued_body():
    native = body()
    native["input"][0]["id"] = "system-native-id"
    native["input"][0]["content"] = [
        {"type": "input_text", "text": "Protected "},
        {"type": "input_text", "text": "system.", "prompt_cache_breakpoint": {"moved": True}},
    ]
    native["input"][1]["id"] = "new-user-native-id"
    native["input"][1]["content"] = [
        {"type": "input_text", "text": native["input"][1]["content"], "prompt_cache_breakpoint": True}]
    native["input"][2]["encrypted_content"] = "current-opaque-replay=="
    native["input"][3]["id"] = "new-function-native-id"
    native["input"][3]["phase"] = "commentary"
    native["input"][3].pop("status")
    native["input"][4]["id"] = "new-output-native-id"
    native["input"][4].pop("status")
    native["input"][4]["prompt_cache_breakpoint"] = {"type": "ephemeral"}
    native["input"][5]["id"] = "new-assistant-native-id"
    native["input"][5]["phase"] = "commentary"
    native["input"][5]["content"][0]["annotations"] = [{"type": "file_citation", "file_id": "retained"}]
    native["input"].append({"role": "user", "content": "Continue."})
    return native


def test_encoding_annotations_do_not_change_canonical_message_prefix():
    first = NativeResponsesEnvelope(body())
    later_native = continued_body()
    later = NativeResponsesEnvelope(later_native)
    prefix = first.canonical_request["messages"]
    assert later.canonical_request["messages"][:len(prefix)] == prefix
    assert later.render(later.canonical_request) == later_native
    assert later_native["input"][0]["content"][1]["prompt_cache_breakpoint"] == {"moved": True}
    assert first.render(first.canonical_request) == body()


def test_real_runtime_append_only_guard_accepts_cache_marker_moves_offline(tmp_path):
    class Transport:
        model = "offline-model"
        max_output_tokens = 100
        max_request_bytes = 524288

        def __init__(self, codec):
            self.codec = codec
            self.sent = []

        def encode(self, canonical):
            return self.codec.encode(canonical)

        def send(self, wire):
            self.sent.append(wire)
            response = {"model": self.model, "output": [], "usage": {
                "input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}
            return Reply(True, "offline_fixture", True, wire, json.dumps(response), response, 200)

    first_native, second_native = body(), continued_body()
    first, second = NativeResponsesEnvelope(first_native), NativeResponsesEnvelope(second_native)
    transport = Transport(first)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session = RuntimeSession(workspace=workspace, output=tmp_path / "runtime",
                             session_id="codec-continuity", transport=transport, backend="none", max_calls=2)
    try:
        assert session.invoke(first.canonical_request).ok
        transport.codec = second
        assert session.invoke(second.canonical_request).ok
        assert [json.loads(wire) for wire in transport.sent] == [first_native, second_native]
        assert session.finish()["model_calls"] == 2  # Synthetic send count, not live inference.
    finally:
        session.close()


@pytest.mark.parametrize("metadata", [
    {"isError": True}, {"error": "failed"}, {"stderr": "denied"}, {"interrupted": True},
    {"exitCode": 1}, {"metadata": {"success": False}}, {"preserve_exact": True},
])
def test_tool_failure_metadata_remains_visible_and_content_is_protected(metadata):
    native = body()
    native["input"][4].update(metadata)
    codec = NativeResponsesEnvelope(native)
    canonical = codec.canonical_request
    result_index = codec.native_to_canonical[4]
    result = canonical["messages"][result_index]
    assert _protected({k: v for k, v in result.items() if k != "content"}, strict_status=True)
    assert codec.render(canonical) == native
    result["content"] = "must not hide the failed result"
    with pytest.raises(ValueError):
        codec.render(canonical)


@pytest.mark.parametrize("extra", [
    {"tool_call_id": "conflicting"}, {"role": "user"}, {"content": "second output"},
    {"structuredContent": {"second": "representation"}},
])
def test_conflicting_tool_output_fields_are_not_encoding_annotations(extra):
    native = body()
    native["input"][4].update(extra)
    with pytest.raises(ValueError):
        NativeResponsesEnvelope(native)
