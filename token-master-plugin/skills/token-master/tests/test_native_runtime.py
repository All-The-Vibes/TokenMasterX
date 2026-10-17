"""Real runtime/ledger with explicitly synthetic upstream replies; no LLM."""
from copy import deepcopy
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener

import pytest

from brainspace.native_mcp import NativeRecoveryClient
from brainspace.native_runtime import NativeBridge, NativeRuntime, RECOVERY_ALIASES
from brainspace.native_transport import NativeResponsesTransport
from brainspace.runtime import RuntimeSession
from brainspace.transport import Reply, ResponsesTransport


def tools():
    result = [{"type": "function", "name": "view", "parameters": {
        "type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"],
    }}]
    for tool in RuntimeSession.recovery_tools():
        function = deepcopy(tool["function"])
        function["name"] = RECOVERY_ALIASES[function["name"]]
        function["strict"] = False
        function["parameters"]["title"] = "NativeMcpArguments"
        for name, schema in function["parameters"]["properties"].items():
            schema["title"] = name.title()
        result.append({"type": "function", **function})
    return result


def body():
    return {
        "model": "fixture", "input": [
            {"type": "message", "role": "system", "content": [
                {"type": "input_text", "text": "Keep system metadata.", "prompt_cache_breakpoint": True},
            ]},
            {"type": "message", "role": "user", "content": "Read the supplied file."},
        ],
        "tools": tools(), "store": False, "parallel_tool_calls": True,
        "prompt_cache_key": "opaque-cache-key", "include": ["reasoning.encrypted_content"],
        "reasoning": {"effort": "low", "summary": "auto"},
    }


def transport(**changes):
    return NativeResponsesTransport(
        base_url="http://127.0.0.1:1/v1", model="fixture", allow_network=True,
        reasoning_effort="low", recovery_aliases=RECOVERY_ALIASES,
        recovery_tools=RuntimeSession.recovery_tools(), **changes,
    )


def test_transport_preserves_native_fields_and_records_common_controls(monkeypatch):
    sent = []
    monkeypatch.setattr(ResponsesTransport, "_send_validated_wire",
                        lambda self, text: sent.append(text) or Reply(False, "fixture", input_text=text))
    adapter = transport()
    native = body()
    before = deepcopy(native)
    canonical = adapter.bind(native)
    wire = adapter.encode(canonical)
    result = json.loads(wire)
    assert native == before
    assert result["input"] == before["input"]
    assert result["tools"] == before["tools"]
    assert result["include"] == before["include"]
    assert result["reasoning"] == before["reasoning"]
    assert result["prompt_cache_key"] == before["prompt_cache_key"]
    assert result["max_output_tokens"] == 2048
    assert result["parallel_tool_calls"] is result["store"] is result["stream"] is False
    assert adapter.controls["scope"] == "common_transport_controls_not_optimizer_savings"
    assert adapter.send(wire + " ").reason == "invalid_request"
    assert not sent
    adapter.send(wire)
    assert sent == [wire]
    assert adapter.send(wire).reason == "invalid_request"


@pytest.mark.parametrize("patch", [
    {"stream": True}, {"store": True}, {"model": "other"},
    {"previous_response_id": "state"}, {"conversation": "state"},
    {"background": True}, {"unknown_field": "must-not-drop"},
    {"parallel_tool_calls": "false"}, {"max_output_tokens": True},
    {"max_output_tokens": 0}, {"reasoning": {"effort": "high"}},
])
def test_transport_rejects_unqualified_controls_without_network(monkeypatch, patch):
    monkeypatch.setattr(ResponsesTransport, "_send_validated_wire",
                        lambda *args: pytest.fail("must not submit"))
    with pytest.raises(ValueError):
        transport().bind({**body(), **patch})


def call(name, args, call_id="actual-native-id"):
    return {"type": "function_call", "id": "fc_" + call_id, "call_id": call_id,
            "name": name, "arguments": json.dumps(args), "status": "completed"}


def fake_sender(monkeypatch, outputs):
    sent = []

    def send(self, wire):
        output = outputs[len(sent)]
        sent.append(json.loads(wire))
        response = {"object": "response", "model": "fixture", "status": "completed",
                    "output": output, "usage": {"input_tokens": 100, "output_tokens": 10,
                                              "total_tokens": 110},
                    "metadata": {"usage_source": "synthetic"}}
        return Reply(True, "ok", True, wire, json.dumps(response), response, 200)
    monkeypatch.setattr(ResponsesTransport, "_send_validated_wire", send)
    return sent


def runtime(tmp_path, **changes):
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    result = NativeRuntime(
        workspace=workspace, session_id="native-test", output=tmp_path / "output",
        base_url="http://127.0.0.1:1/v1", model="fixture", allow_network=True,
        event_wait_seconds=0, **changes,
    )
    result.observe_event({"type": "session.skills_loaded", "data": {"skills": []}})
    return result


def start(item):
    return {"type": "tool.execution_start", "id": "start_" + item["call_id"],
            "data": {"toolCallId": item["call_id"], "toolName": item["name"],
                     "arguments": json.loads(item["arguments"]), "model": "fixture",
                     "turnId": "0"}}


def done(item, content, *, success=True):
    return {"type": "tool.execution_complete", "id": "done_" + item["call_id"],
            "data": {"toolCallId": item["call_id"], "model": "fixture", "turnId": "0",
                     "interactionId": "native-interaction",
                     "success": success, "rte": False,
                     "result": {"content": content, "detailedContent": ""},
                     "toolTelemetry": {"properties": {"viewType": "file"}}}}


def test_native_ids_provenance_and_complete_runtime_accounting(tmp_path, monkeypatch):
    native = runtime(tmp_path)
    item = call("view", {"path": str(native.workspace / "source.json")})
    sent = fake_sender(monkeypatch, [[item], []])
    first = body()
    assert native.invoke(first).ok
    native.observe_event(start(item))
    native.observe_event(done(item, '{"value":7}'))
    second = deepcopy(first)
    second["input"] += [item, {"type": "function_call_output", "call_id": item["call_id"],
                              "output": '{"value":7}'}]
    assert native.invoke(second).ok
    summary = native.finish(native_exit_code=0)
    assert len(sent) == 2
    assert summary["complete"] and summary["quality_verified"] is None
    assert summary["runtime"]["source_read_receipts"] == 1
    assert summary["runtime"]["model_calls"] == 2
    assert summary["runtime"]["gateway_reported_tokens"] == 220  # synthetic fixture only
    assert summary["native_executor"]["calls"][item["call_id"]]["status"] == "success"
    assert native.runtime.source_reads[item["call_id"]].tool_name == "view"
    assert summary["runtime"]["tool_inventory_scope"].startswith("runtime-wrapped")


def test_recovery_binds_real_native_call_and_requires_observed_start(tmp_path, monkeypatch):
    native = runtime(tmp_path)
    ref = native.runtime.ccr.stash("exact original", ctype="source", source="fixture", kind="root")
    args = {"ref": ref, "offset": 0}
    item = call(RECOVERY_ALIASES["retrieve_original"], args, "native-recovery-id")
    fake_sender(monkeypatch, [[item], []])
    first = body()
    assert native.invoke(first).ok
    with pytest.raises(ValueError, match="execution_not_observed"):
        native.recover("retrieve_original", args)
    native.observe_event(start(item))
    recovered = native.recover("retrieve_original", args)
    assert json.loads(recovered)["content"] == "exact original"
    with pytest.raises(ValueError):
        native.recover("retrieve_original", args)
    native.observe_event(done(item, recovered))
    second = deepcopy(first)
    second["input"] += [item, {"type": "function_call_output", "call_id": item["call_id"],
                              "output": recovered}]
    native.invoke(second)
    summary = native.finish(native_exit_code=0)
    assert summary["complete"]
    assert summary["runtime"]["recovery_tool_attempts"] == 1
    assert "native-recovery-id" in native.runtime._tool_ids


def test_preexisting_or_unobserved_result_is_not_invented_provenance(tmp_path, monkeypatch):
    native = runtime(tmp_path)
    sent = fake_sender(monkeypatch, [])
    item = call("view", {"path": str(native.workspace / "source.json")})
    request = body()
    request["input"] += [item, {"type": "function_call_output", "call_id": item["call_id"],
                               "output": "unobserved"}]
    with pytest.raises(ValueError, match="unobserved_preexisting"):
        native.invoke(request)
    result = native.finish(native_exit_code=1)
    assert not sent and not result["complete"]
    assert result["runtime"]["model_calls"] == 0


def test_native_view_path_cannot_escape_workspace(tmp_path, monkeypatch):
    native = runtime(tmp_path)
    item = call("view", {"path": str(tmp_path / "not-authorized")})
    fake_sender(monkeypatch, [[item]])
    reply = native.invoke(body())
    assert not reply.ok and reply.reason == "native_output_rejected"
    result = native.finish(native_exit_code=1)
    assert result["runtime"]["model_calls"] == 1
    assert result["native_executor"]["calls"] == {}
    assert not result["complete"]


def test_real_mcp_http_client_and_main_thread_dispatch(tmp_path, monkeypatch):
    calls = []
    native = runtime(tmp_path)
    monkeypatch.setattr(native, "recover",
                        lambda name, args: calls.append((name, args))
                        or '{"ok":true,"content":"literal"}')
    with NativeBridge(native) as bridge, ThreadPoolExecutor(max_workers=1) as pool:
        client = NativeRecoveryClient(base_url=bridge.url, token=bridge.control_token)
        pending = pool.submit(client.recover, "headroom_retrieve", {"hash": "fixture"})
        while not pending.done():
            bridge.pump_once(timeout=0.01)
        assert pending.result() == '{"ok":true,"content":"literal"}'
    assert calls == [("headroom_retrieve", {"hash": "fixture"})]
    assert native.finish(native_exit_code=0)["complete"]


def test_mcp_control_key_does_not_authorize_primary_or_bad_credentials(tmp_path):
    native = runtime(tmp_path)
    with NativeBridge(native) as bridge:
        client = NativeRecoveryClient(base_url=bridge.url, token=bridge.primary_token)
        with pytest.raises(ValueError, match="unavailable"):
            client.recover("headroom_retrieve", {"hash": "fixture"})
    assert native.finish(native_exit_code=0)["native_http"]["authenticated_requests"] == 0


def post(bridge, route, raw, token):
    request = Request(bridge.url + route, data=raw, method="POST",
                      headers={"Authorization": "Bearer " + token,
                               "Content-Type": "application/json"})
    try:
        response = build_opener(ProxyHandler({})).open(request, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.read()


def pumped_post(bridge, route, raw, token):
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(post, bridge, route, raw, token)
        while not pending.done():
            bridge.pump_once(timeout=0.01)
        return pending.result()


@pytest.mark.parametrize("route", ["/v1/responses", "/control/recover"])
@pytest.mark.parametrize("encoded,key_position", [(False, False), (True, False), (True, True)])
def test_decoded_credentials_never_dispatch_or_persist(tmp_path, monkeypatch, route, encoded, key_position):
    native = runtime(tmp_path)
    sent = fake_sender(monkeypatch, [[]])
    with NativeBridge(native) as bridge:
        token = bridge.primary_token if route == "/v1/responses" else bridge.control_token
        request = body() if route == "/v1/responses" else {
            "name": "headroom_retrieve", "arguments": {"hash": "fixture"},
        }
        request[token if key_position else "instructions"] = "x" if key_position else token
        wire = json.dumps(request).encode()
        if encoded:
            escaped = "".join("\\u" + format(ord(char), "04x") for char in token).encode()
            wire = wire.replace(token.encode(), escaped)
            assert token.encode() not in wire
        status, _ = pumped_post(bridge, route, wire, token)
        rejected = status == 400
        persisted = any(token.encode() in path.read_bytes()
                        for path in native.output.rglob("*.json*") if path.is_file())
        assert rejected and not persisted and not sent
    result = native.finish(native_exit_code=0)
    assert not result["complete"]
    assert result["runtime"]["model_calls"] == 0


@pytest.mark.parametrize("success", [False, True])
def test_terminal_native_recovery_cannot_be_claimed(tmp_path, monkeypatch, success):
    native = runtime(tmp_path)
    ref = native.runtime.ccr.stash("original", ctype="source", source="fixture", kind="root")
    args = {"ref": ref, "offset": 0}
    item = call(RECOVERY_ALIASES["retrieve_original"], args, "terminal-native-id")
    fake_sender(monkeypatch, [[item]])
    native.invoke(body())
    native.observe_event(start(item))
    native.observe_event(done(item, "native operation already ended", success=success))
    with pytest.raises(ValueError):
        native.recover("retrieve_original", args)
    result = native.finish(native_exit_code=0)
    assert result["runtime"]["recovery_tool_attempts"] == 0


def test_authenticated_rejection_is_counted_without_invented_model_call(tmp_path, monkeypatch):
    native = runtime(tmp_path)
    sent = fake_sender(monkeypatch, [[]])
    with NativeBridge(native) as bridge:
        status, _ = pumped_post(bridge, "/v1/responses", b"{malformed", bridge.primary_token)
        assert status == 400
        status, _ = pumped_post(bridge, "/v1/responses", json.dumps(body()).encode(), bridge.primary_token)
        assert status == 200
    result = native.finish(native_exit_code=0)
    assert len(sent) == result["runtime"]["model_calls"] == 1
    assert result["native_ingress_requests"] == 2
    assert result["native_rejections"] == 1
    assert result["native_http"]["rejected_before_dispatch"] == 1
    assert not result["complete"]


@pytest.mark.parametrize("error_type", [ValueError, KeyboardInterrupt])
def test_collector_close_failure_never_skips_runtime_cleanup(tmp_path, monkeypatch, error_type):
    native = runtime(tmp_path)
    closed = []
    real_close = native.runtime.close

    def tracked_close():
        closed.append(True)
        return real_close()

    def fail():
        raise error_type("fixture")

    monkeypatch.setattr(native.runtime, "close", tracked_close)
    monkeypatch.setattr(native.events, "close", fail)
    if error_type is KeyboardInterrupt:
        with pytest.raises(KeyboardInterrupt):
            native.finish(native_exit_code=0)
    else:
        native.finish(native_exit_code=0)
    assert closed and native.runtime.cleanup_settled
    saved = json.loads((native.output / "result.json").read_text("utf-8"))
    assert saved["complete"] is False
    assert saved["native_executor"]["coverage_complete"] is False


def test_old_terminal_recovery_does_not_hide_fresh_pending_call(tmp_path, monkeypatch):
    native = runtime(tmp_path)
    ref = native.runtime.ccr.stash("original", ctype="source", source="fixture", kind="root")
    args = {"ref": ref, "offset": 0}
    old = call(RECOVERY_ALIASES["retrieve_original"], args, "old-terminal")
    fresh = call(RECOVERY_ALIASES["retrieve_original"], args, "fresh-pending")
    fake_sender(monkeypatch, [[old], [fresh], []])
    original = body()
    native.invoke(original)
    native.observe_event(start(old))
    native.observe_event(done(old, "native MCP failed before recovery", success=False))
    second = deepcopy(original)
    second["input"] += [old, {"type": "function_call_output", "call_id": old["call_id"],
                             "output": "native MCP failed before recovery"}]
    native.invoke(second)
    native.observe_event(start(fresh))
    recovered = native.recover("retrieve_original", args)
    assert json.loads(recovered)["content"] == "original"
    native.observe_event(done(fresh, recovered))
    third = deepcopy(second)
    third["input"] += [fresh, {"type": "function_call_output", "call_id": fresh["call_id"],
                             "output": recovered}]
    native.invoke(third)
    summary = native.finish(native_exit_code=0)
    assert summary["complete"]
    assert native.runtime._tool_ids == {"fresh-pending"}


def test_summary_write_error_does_not_mask_original_interruption(tmp_path, monkeypatch):
    native = runtime(tmp_path)
    interrupted = KeyboardInterrupt("first interruption")

    def fail_close():
        raise interrupted

    real_open = Path.open

    def fail_summary(path, *args, **kwargs):
        if path == native.output / "result.json":
            raise OSError("summary storage unavailable")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(native.events, "close", fail_close)
    monkeypatch.setattr(Path, "open", fail_summary)
    with pytest.raises(KeyboardInterrupt) as caught:
        native.finish(native_exit_code=0)
    assert caught.value is interrupted
    assert native.runtime.cleanup_settled
