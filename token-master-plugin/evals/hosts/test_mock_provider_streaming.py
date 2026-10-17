"""Offline synthetic SSE contract regressions, not native-host qualification.

No external provider/CLI execution or credentials. Loopback-only HTTP tests
exercise framing and stream selection; remaining checks call the builder.
"""
from copy import deepcopy
import json
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any
from urllib.request import ProxyHandler, Request, build_opener

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mock_provider import MockProvider  # noqa: E402


@pytest.fixture(autouse=True)
def local_only(monkeypatch):
    connect = socket.socket.connect

    def loopback(self, address):
        assert isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1")
        return connect(self, address)

    def no_process(*args, **kwargs):
        pytest.fail("streaming regressions must not invoke a CLI or subprocess")

    monkeypatch.setattr(socket.socket, "connect", loopback)
    monkeypatch.setattr(subprocess, "Popen", no_process)


@pytest.fixture
def provider():
    # The unit builder needs no server or background thread.
    value = MockProvider.__new__(MockProvider)
    value.requests = [{"synthetic": True}]
    return value


def action(arguments, namespace=None):
    return {"name": "read_document", "namespace": namespace, "arguments": arguments, "call_id": "call_fixture"}


def event(events, kind):
    found = [body for name, body in events if name == kind]
    assert len(found) == 1
    return found[0]


def validate_lifecycle(events):
    assert events[0][0] == "response.created" and events[-1][0] == "response.completed"
    assert [body["sequence_number"] for _, body in events] == list(range(len(events)))
    assert all(type(body["sequence_number"]) is int and name == body["type"] for name, body in events)
    created = event(events, "response.created")["response"]
    final = event(events, "response.completed")["response"]
    assert created["id"] == final["id"] and created["object"] == final["object"] == "response"
    assert created["status"] == "in_progress" and created["output"] == []
    assert created["usage"] is None
    assert final["status"] == "completed" and len(final["output"]) == 1
    assert final["metadata"]["usage_source"] == "synthetic"
    for name, body in events:
        assert body["response_id"] == final["id"]
        if name not in ("response.created", "response.in_progress", "response.completed"):
            assert body["output_index"] == 0
        if name.startswith(("response.function_call_arguments.", "response.content_part.", "response.output_text.")):
            assert body["item_id"] == final["output"][0]["id"]
    assert event(events, "response.output_item.done")["item"] == final["output"][0]
    return final


def reconstruct_call(events):
    added = event(events, "response.output_item.added")["item"]
    assert added["type"] == "function_call"
    assert added["arguments"] == "" and added["status"] == "in_progress"
    final = validate_lifecycle(events)
    reconstructed = deepcopy(added)
    deltas = []
    for kind, data in events:
        if kind == "response.function_call_arguments.delta":
            assert type(data["delta"]) is str and data["delta"]
            reconstructed["arguments"] += data["delta"]
            deltas.append(data["delta"])
        elif kind == "response.function_call_arguments.done":
            assert reconstructed["arguments"] == data["arguments"]
        elif kind == "response.output_item.done":
            reconstructed["status"] = "completed"
            assert reconstructed == data["item"]
    assert deltas
    assert "".join(deltas) == event(events, "response.function_call_arguments.done")["arguments"]
    names = [kind for kind, _ in events]
    assert names.index("response.output_item.added") < names.index("response.function_call_arguments.delta")
    assert max(i for i, name in enumerate(names) if name == "response.function_call_arguments.delta") < names.index(
        "response.function_call_arguments.done") < names.index("response.output_item.done")
    assert not any(name.startswith("response.output_text.") or name.startswith("response.content_part.") for name in names)
    assert reconstructed == final["output"][0]
    return reconstructed, deltas


def reconstruct_text(events):
    added = event(events, "response.output_item.added")["item"]
    assert added["type"] == "message" and added["role"] == "assistant"
    assert added["status"] == "in_progress" and added["content"] == []
    final = validate_lifecycle(events)
    reconstructed = deepcopy(added)
    delta_count = 0
    for kind, data in events:
        if kind == "response.content_part.added":
            assert data["content_index"] == 0
            assert data["part"]["type"] == "output_text" and data["part"]["text"] == ""
            reconstructed["content"].append(deepcopy(data["part"]))
        elif kind == "response.output_text.delta":
            assert data["content_index"] == 0
            assert data["logprobs"] == []
            reconstructed["content"][0]["text"] += data["delta"]
            delta_count += 1
        elif kind == "response.output_text.done":
            assert data["content_index"] == 0 and data["text"] == reconstructed["content"][0]["text"]
            assert data["logprobs"] == []
        elif kind == "response.content_part.done":
            assert data["content_index"] == 0 and data["part"] == reconstructed["content"][0]
        elif kind == "response.output_item.done":
            reconstructed["status"] = "completed"
            assert reconstructed == data["item"]
    assert delta_count > 0
    names = [kind for kind, _ in events]
    assert names.index("response.content_part.added") < names.index("response.output_text.delta")
    assert names.index("response.output_text.done") < names.index("response.content_part.done") < names.index(
        "response.output_item.done")
    assert not any(name.startswith("response.function_call_arguments.") for name in names)
    assert reconstructed == final["output"][0]
    return reconstructed


@pytest.mark.parametrize("namespace", [None, "mcp__brainspace"])
@pytest.mark.parametrize("arguments", [
    {},
    {"path": "plain.json", "offset": 0, "limit": 32768},
    {"path": "資料/naïve-🙂.json", "text": 'quoted "value" \\ slash\n雪\tcafé', "flags": [True, False, None]},
])
def test_function_stream_starts_empty_and_reconstructs_arguments_once(provider, namespace, arguments):
    selected = action(arguments, namespace)
    original = deepcopy(selected)
    events = provider.responses(selected, {"model": "synthetic-model", "stream": True})
    item, deltas = reconstruct_call(events)
    assert json.loads(item["arguments"]) == arguments
    assert item["arguments"] == json.dumps(arguments)
    assert item["call_id"] == selected["call_id"] and item["name"] == selected["name"]
    assert item.get("namespace") == namespace
    assert ("namespace" in item) is (namespace is not None)
    assert len(item["arguments"]) == sum(map(len, deltas))  # No completed args also present at start.
    if arguments:
        assert len(deltas) > 1  # Exercise partial JSON, including escape boundaries.
    assert selected == original


def test_final_text_reconstructs_from_content_and_text_deltas(provider):
    events = provider.responses(None, {"model": "synthetic-model", "stream": True})
    message = reconstruct_text(events)
    assert message["content"][0]["text"] == "MOCK_TRANSPORT_DONE"
    assert message["content"][0]["annotations"] == []


def test_added_items_can_be_accumulated_without_mutating_completion(provider):
    for selected in (action({"path": "資料.json"}, "mcp__brainspace"), None):
        events = provider.responses(selected, {"model": "synthetic-model"})
        expected = deepcopy(events[-1][1]["response"])
        # Mirrors clients that accumulate directly into the added event object.
        initial = event(events, "response.output_item.added")["item"]
        if selected:
            for kind, body in events:
                if kind == "response.function_call_arguments.delta":
                    initial["arguments"] += body["delta"]
        else:
            part = event(events, "response.content_part.added")["part"]
            initial["content"].append(part)
            for kind, body in events:
                if kind == "response.output_text.delta":
                    part["text"] += body["delta"]
        assert events[-1][1]["response"] == expected


def test_deferred_tool_search_remains_client_executed_object_arguments(provider):
    selected = {"kind": "tool_search", "name": "tool_search", "namespace": None,
                "arguments": {"query": "brainspace", "limit": 2}, "call_id": "smoke_discovery"}
    events = provider.responses(selected, {"model": "synthetic-model"})
    final = validate_lifecycle(events)
    item = final["output"][0]
    assert item["type"] == "tool_search_call" and item["execution"] == "client"
    assert item["arguments"] == selected["arguments"] and type(item["arguments"]) is dict
    assert item["call_id"] == "smoke_discovery"
    assert not any(kind.startswith("response.function_call_arguments.") for kind, _ in events)


@pytest.mark.parametrize("selected", [action({"path": "資料.json"}), None])
def test_anthropic_message_and_delta_path_remains_unchanged(provider, selected):
    message, events = provider.anthropic(selected, {"model": "synthetic-model"})
    assert [name for name, _ in events] == [
        "message_start", "content_block_start", "content_block_delta",
        "content_block_stop", "message_delta", "message_stop"]
    start = event(events, "content_block_start")["content_block"]
    delta = event(events, "content_block_delta")["delta"]
    if selected:
        assert start["input"] == {} and delta["type"] == "input_json_delta"
        assert json.loads(delta["partial_json"]) == message["content"][0]["input"] == selected["arguments"]
        assert message["stop_reason"] == "tool_use"
    else:
        assert start["text"] == "" and delta["type"] == "text_delta"
        assert delta["text"] == message["content"][0]["text"] == "MOCK_TRANSPORT_DONE"
        assert message["stop_reason"] == "end_turn"
    assert not any(name.startswith("response.") for name, _ in events)


def parse_sse(raw):
    result = []
    for frame in raw.decode("utf-8").split("\n\n"):
        if not frame:
            continue
        rows = frame.splitlines()
        assert len(rows) == 2 and rows[0].startswith("event: ") and rows[1].startswith("data: ")
        name, body = rows[0][7:], json.loads(rows[1][6:])
        assert body["type"] == name
        result.append((name, body))
    return result


def test_loopback_sse_complete_tool_then_final_text_without_native_cli(tmp_path):
    arguments = {"path": "資料/雪.json", "text": "héllo🙂\n"}
    with MockProvider("envelope", tmp_path / "unused", "", tool_steps=[("read_document", arguments)]) as local:
        opener = build_opener(ProxyHandler({}))
        body: dict[str, Any] = {"model": "synthetic-model", "stream": True, "input": [], "tools": [
            {"type": "namespace", "name": "mcp__brainspace", "tools": [
                {"type": "function", "name": "read_document", "parameters": {"type": "object"}}]}]}

        def request():
            req = Request(local.url + "/v1/responses", data=json.dumps(body).encode(),
                          headers={"Content-Type": "application/json"})
            with opener.open(req, timeout=5) as response:
                assert response.status == 200 and response.headers.get_content_type() == "text/event-stream"
                return parse_sse(response.read())

        first = request()
        call, _ = reconstruct_call(first)
        assert json.loads(call["arguments"]) == arguments and call["namespace"] == "mcp__brainspace"
        body["input"] = [{"type": "function_call_output", "call_id": call["call_id"], "output": "tool result"}]
        second = request()
        assert reconstruct_text(second)["content"][0]["text"] == "MOCK_TRANSPORT_DONE"
        assert first[-1][1]["response"]["id"] != second[-1][1]["response"]["id"]
        assert len(local.requests) == 2 and len(local.actions) == 1 and local.errors == []


@pytest.mark.parametrize("stream", [False, None], ids=["false", "omitted"])
@pytest.mark.parametrize("kind", ["function", "text", "tool_search"])
def test_loopback_nonstream_returns_same_completed_json(tmp_path, monkeypatch, stream, kind):
    # Fix only the clock so JSON can be compared with the builder's exact final
    # response. Synthetic usage is not a model measurement.
    monkeypatch.setattr("mock_provider.time.time", lambda: 1791500000)
    arguments = {"path": "資料/雪.json", "text": "héllo🙂\n"}
    steps = [] if kind == "text" else [("read_document", arguments)]
    with MockProvider("envelope", tmp_path / "unused", "", tool_steps=steps) as local:
        tools = ([{"type": "tool_search", "execution": "client"}] if kind == "tool_search" else [
            {"type": "namespace", "name": "mcp__brainspace", "tools": [
                {"type": "function", "name": "read_document", "parameters": {"type": "object"}}]}])
        body = {"model": "synthetic-model", "input": [], "tools": tools}
        if stream is not None:
            body["stream"] = stream
        req = Request(local.url + "/v1/responses", data=json.dumps(body).encode(),
                      headers={"Content-Type": "application/json"})
        with build_opener(ProxyHandler({})).open(req, timeout=5) as response:
            raw = response.read()
            assert response.status == 200
            assert response.headers.get_content_type() == "application/json"
            assert int(response.headers["Content-Length"]) == len(raw)
        result = json.loads(raw)
        selected = local.actions[0] if local.actions else None
        expected = local.responses(selected, body)[-1][1]["response"]
        assert result == expected
        assert result["status"] == "completed" and result["object"] == "response"
        assert result["metadata"]["usage_source"] == "synthetic"
        assert result["usage"] == {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110}
        assert "sequence_number" not in result and "data:" not in raw.decode()
        if kind == "function":
            assert json.loads(result["output"][0]["arguments"]) == arguments
            assert result["output"][0]["namespace"] == "mcp__brainspace"
        elif kind == "tool_search":
            assert result["output"][0]["type"] == "tool_search_call"
            assert result["output"][0]["execution"] == "client"
            assert type(result["output"][0]["arguments"]) is dict
        else:
            assert result["output"][0]["content"][0]["text"] == "MOCK_TRANSPORT_DONE"
        assert len(local.requests) == 1 and local.errors == []
