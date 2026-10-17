"""Production materialization preserves supported text and rejects unknown fields."""
from copy import deepcopy
import json

import pytest

from brainspace.transport import ResponsesTransport


def payload():
    return {"model": "fixture", "messages": [
        {"role": "system", "content": "System."},
        {"role": "user", "content": "Read source."},
        {"role": "assistant", "content": "This accompanying text must survive.",
         "tool_calls": [{"id": "read", "type": "function", "function": {
             "name": "read_file", "arguments": '{"path":"module.py"}'}}]},
        {"role": "tool", "tool_call_id": "read", "content": "literal source\r\n漢字"},
    ], "tools": [{"type": "function", "function": {
        "name": "read_file", "description": "Exact text.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                       "required": ["path"], "additionalProperties": False}, "strict": True}}]}


def test_full_final_wire_preserves_assistant_text_calls_results_and_schema():
    transport = ResponsesTransport("http://127.0.0.1:1/v1", "fixture", reasoning_effort="low")
    chat = payload()
    before = deepcopy(chat)
    wire = transport.encode(chat)
    body = json.loads(wire)
    assert chat == before
    assert body["input"][2] == {
        "role": "assistant", "content": "This accompanying text must survive."}
    assert body["input"][3]["arguments"] == '{"path":"module.py"}'
    assert body["input"][4]["output"] == "literal source\r\n漢字"
    assert body["tools"][0]["parameters"] == chat["tools"][0]["function"]["parameters"]
    assert body["max_output_tokens"] == 2048 and body["reasoning"] == {"effort": "low"}
    assert body["stream"] is body["store"] is body["parallel_tool_calls"] is False


@pytest.mark.parametrize("change", [
    "unknown_top", "message_metadata", "image", "call_metadata", "tool_metadata",
    "wrong_model", "output_cap", "missing_result",
])
def test_unsupported_shapes_are_not_silently_dropped(change):
    chat = payload()
    if change == "unknown_top":
        chat["previous_response_id"] = "opaque"
    elif change == "message_metadata":
        chat["messages"][0]["important_metadata"] = "must preserve"
    elif change == "image":
        chat["messages"][1]["content"] = [{"type": "image_url", "image_url": "unobserved"}]
    elif change == "call_metadata":
        chat["messages"][2]["tool_calls"][0]["extra"] = "must preserve"
    elif change == "tool_metadata":
        chat["tools"][0]["function"]["extra"] = "must preserve"
    elif change == "wrong_model":
        chat["model"] = "different"
    elif change == "output_cap":
        chat["max_tokens"] = 100
    else:
        chat["messages"].pop()
    with pytest.raises(ValueError):
        ResponsesTransport("http://127.0.0.1:1/v1", "fixture").encode(chat)


def test_send_rejects_changed_or_noncanonical_wire_before_network(monkeypatch):
    from brainspace import transport as module
    monkeypatch.setattr(module, "build_opener", lambda *_: pytest.fail("must not submit"))
    transport = ResponsesTransport("http://127.0.0.1:1/v1", "fixture", allow_network=True)
    wire = transport.encode(payload())
    for bad in (wire + " ", wire.replace('"model":"fixture"', '"model":"other"'),
                wire.replace('"stream":false', '"stream":true')):
        result = transport.send(bad)
        assert result.reason == "invalid_request" and result.input_text is None


def test_explicit_reasoning_configuration_cannot_be_silently_overridden():
    transport = ResponsesTransport("http://127.0.0.1:1/v1", "fixture", reasoning_effort="low")
    with pytest.raises(ValueError):
        transport.request({"input": [], "reasoning": {"effort": "high"}})
