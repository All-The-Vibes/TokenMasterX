from dataclasses import asdict, fields
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import sys
from threading import Thread
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
from quality.responses import ResponsesTransport  # noqa: E402
from refinement.messages import MessagesTransport, message_reason  # noqa: E402


MODEL = "unregistered-exact-model-name"
PAYLOAD = {"input": [{"role": "user", "content": "漢 <|endoftext|>"}]}


def message(**changes):
    return {"type": "message", "role": "assistant", "model": MODEL,
            "stop_reason": "end_turn", "content": [{"type": "text", "text": "answer"}],
            "usage": {"input_tokens": 2, "cache_creation_input_tokens": 3,
                      "cache_read_input_tokens": 5, "output_tokens": 7}, **changes}


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        status = 200
        body = json.dumps(message(), indent=2).encode()
        requests = []
        disconnect = False

        def log_message(self, *_):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            self.requests.append((self.path, dict(self.headers), raw))
            if self.disconnect:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            self.send_response(self.status)
            if 300 <= self.status < 400:
                self.send_header("Location", "/must-not-follow")
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(self.body)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/v1/", Handler
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def client(server, **kwargs):
    return MessagesTransport(server[0], MODEL, allow_network=True, **kwargs)


def test_dataclass_contract_and_detached_request(server):
    transport = client(server)
    assert fields(transport)[:-1] == fields(ResponsesTransport)
    assert fields(transport)[-1].name == "expected_model"
    assert asdict(transport)["model"] == MODEL
    assert transport.api == "messages"
    payload = {"input": [{"role": "user", "content": "original"}]}
    body = transport.request(payload)
    payload["input"][0]["content"] = "changed"
    assert body["messages"][0]["content"] == "original"
    assert "system" not in body and "output_config" not in body


def test_explicit_response_id_mapping_preserves_both_identifiers(server):
    canonical = "native-exact-model-id"
    server[1].body = json.dumps(message(model=canonical)).encode()
    reply = client(server, expected_model=canonical).call(PAYLOAD)
    assert reply.ok and reply.body["model"] == canonical
    assert json.loads(reply.input_text)["model"] == MODEL
    assert client(server).call(PAYLOAD).reason == "model_mismatch"
    server[1].body = json.dumps(message(model="unapproved-model")).encode()
    assert client(server, expected_model=canonical).call(PAYLOAD).reason == "model_mismatch"


@pytest.mark.parametrize("expected", ["", " ", True, 3])
def test_invalid_response_model_mapping_fails_closed(server, expected):
    with pytest.raises(ValueError):
        client(server, expected_model=expected)


def test_wire_capture_headers_low_effort_no_credentials_or_proxies(server, monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(key, "DO_NOT_USE")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("no_proxy", "")
    monkeypatch.setenv("NO_PROXY", "")
    reply = client(server, max_output_tokens=129).call(
        {**PAYLOAD, "instructions": "system text", "reasoning": {"effort": "low"}})
    assert reply.ok and reply.complete and reply.reason == "ok"
    path, headers, raw = server[1].requests[0]
    assert path == "/v1/messages"
    headers = {k.lower(): v for k, v in headers.items()}
    assert headers["anthropic-version"] == "2023-06-01"
    assert headers["content-type"] == headers["accept"] == "application/json"
    assert not {"authorization", "x-api-key", "proxy-authorization"} & headers.keys()
    assert json.loads(raw) == {
        "model": MODEL, "messages": PAYLOAD["input"], "max_tokens": 129,
        "stream": False, "system": "system text", "output_config": {"effort": "low"}}
    assert reply.input_text == raw.decode()
    assert reply.output_text == server[1].body.decode()
    assert reply.body == message()
    assert reply.body["usage"]["input_tokens"] == 2
    assert "total_tokens" not in reply.body["usage"]
    assert "DO_NOT_USE" not in repr(reply)


@pytest.mark.parametrize("usage", [
    {"input_tokens": "2", "output_tokens": True},
    {"input_tokens": 1.5, "cache_read_input_tokens": -3},
])
def test_usage_is_never_coerced_or_synthesized(server, usage):
    server[1].body = json.dumps(message(usage=usage)).encode()
    reply = client(server).call(PAYLOAD)
    assert reply.ok and reply.body["usage"] == usage
    assert {k: type(v) for k, v in reply.body["usage"].items()} == {
        k: type(v) for k, v in usage.items()}
    assert reply.output_text == server[1].body.decode()


def test_network_disabled_precedes_request_validation(server):
    reply = MessagesTransport(server[0], MODEL).call(None)
    assert reply.reason == "network_not_allowed" and reply.input_text is None
    assert not server[1].requests


@pytest.mark.parametrize("extra", [
    {"tools": []}, {"store": False}, {"previous_response_id": "old"},
    {"model": "other"}, {"stream": True}, {"output_config": {"effort": "low"}},
    {"reasoning": None}, {"reasoning": {"effort": "high"}},
    {"reasoning": {"effort": "low", "summary": "auto"}}, {"instructions": []},
])
def test_unsupported_payloads_never_send(server, extra):
    reply = client(server).call({**PAYLOAD, **extra})
    assert reply.reason == "invalid_request"
    assert not server[1].requests


@pytest.mark.parametrize("value", [
    None, "text", [], [{"role": "assistant", "content": "x"}],
    [{"role": "user", "content": []}], [{"role": "user", "content": "x", "id": "a"}],
    [{"role": "user", "content": "x"}] * 2,
])
def test_only_one_user_text(server, value):
    assert client(server).call({"input": value}).reason == "invalid_request"
    assert not server[1].requests


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308, 400, 401, 429, 500])
def test_http_errors_captured_without_retry_or_redirect(server, status):
    server[1].status = status
    server[1].body = b'{"error":{"type":"unsupported_api_for_model"}}'
    reply = client(server).call(PAYLOAD)
    assert not reply.ok and reply.complete and reply.reason == "http_error"
    assert reply.http_status == status
    assert reply.output_text == server[1].body.decode()
    assert len(server[1].requests) == 1


@pytest.mark.parametrize("raw", [
    b"{", b"[]", b"null", b'{"type":"message","type":"message"}',
    b'{"type":"message","usage":{"input_tokens":1,"input_tokens":2}}',
    b'{"type":"message","usage":{"input_tokens":NaN}}',
])
def test_malformed_duplicate_nonfinite_json(server, raw):
    server[1].body = raw
    reply = client(server).call(PAYLOAD)
    assert not reply.ok and reply.complete and reply.reason == "invalid_response"
    assert reply.output_text == raw.decode()


@pytest.mark.parametrize("changes,reason", [
    ({"type": "response"}, "invalid_response"),
    ({"role": "user"}, "invalid_response"),
    ({"model": MODEL.upper()}, "model_mismatch"),
    ({"content": None}, "incomplete_model_response"),
    ({"content": ["answer"]}, "invalid_response"),
    ({"content": [{"type": "text", "text": 1}]}, "invalid_response"),
    ({"content": [{"type": "tool_use"}]}, "incomplete_model_response"),
    ({"content": [{"type": "refusal"}]}, "incomplete_model_response"),
])
def test_shape_validation_matches_offline_audit(server, changes, reason):
    body = message(**changes)
    assert message_reason(body, MODEL) == reason
    server[1].body = json.dumps(body).encode()
    reply = client(server).call(PAYLOAD)
    assert not reply.ok and reply.complete and reply.reason == reason
    assert reply.body == body and reply.output_text == server[1].body.decode()


@pytest.mark.parametrize("stop", [
    "max_tokens", "refusal", "tool_use", "pause_turn", "stop_sequence", "unknown", None,
])
def test_only_end_turn_is_successful(server, stop):
    server[1].body = json.dumps(message(stop_reason=stop)).encode()
    reply = client(server).call(PAYLOAD)
    assert not reply.ok and reply.complete and reply.reason == "incomplete_model_response"
    assert message_reason(reply.body, MODEL) == reply.reason


def test_thinking_remains_native(server):
    body = message(content=[{"type": "thinking", "thinking": "reasoning", "signature": "sig"},
                            {"type": "redacted_thinking", "data": "opaque"},
                            {"type": "text", "text": "answer"}])
    server[1].body = json.dumps(body).encode()
    reply = client(server).call(PAYLOAD)
    assert reply.ok and reply.body == body


@pytest.mark.parametrize("raw,limit,reason", [
    (b"x" * 65, 64, "response_too_large"), (b"\xff", 64, "invalid_utf8"),
])
def test_incomplete_wire_capture_not_countable(server, raw, limit, reason):
    server[1].body = raw
    reply = client(server, max_response_bytes=limit).call(PAYLOAD)
    assert not reply.ok and not reply.complete and reply.reason == reason
    assert reply.output_text is None and reply.body is None
    assert reply.input_text and reply.http_status == 200


def test_byte_bounds_exact_and_over_limit(server):
    transport = client(server)
    request_size = len(json.dumps(transport.request(PAYLOAD), ensure_ascii=False,
                                  separators=(",", ":"), sort_keys=True).encode())
    reply = client(server, max_request_bytes=request_size - 1).call(PAYLOAD)
    assert reply.reason == "request_too_large" and not server[1].requests
    assert client(server, max_request_bytes=request_size,
                  max_response_bytes=len(server[1].body)).call(PAYLOAD).ok


def test_setup_failure_is_not_marked_sent(server, monkeypatch):
    monkeypatch.setattr("refinement.messages.build_opener", Mock(side_effect=RuntimeError("setup")))
    reply = client(server).call(PAYLOAD)
    assert reply.reason == "transport_setup_error" and reply.error_type == "RuntimeError"
    assert not reply.complete and reply.input_text is None and not server[1].requests


def test_connection_failure_has_attempted_request_no_retry(server):
    server[1].disconnect = True
    reply = client(server).call(PAYLOAD)
    assert reply.reason == "transport_error" and not reply.complete
    assert reply.input_text and reply.error_type and reply.output_text is None
    assert len(server[1].requests) == 1


def test_socket_timeout_is_forwarded(server, monkeypatch):
    opener = Mock()
    opener.open.side_effect = TimeoutError("bounded socket")
    monkeypatch.setattr("refinement.messages.build_opener", Mock(return_value=opener))
    reply = client(server, timeout=0.125).call(PAYLOAD)
    assert reply.reason == "transport_error" and reply.error_type == "TimeoutError"
    assert opener.open.call_args.kwargs == {"timeout": 0.125}
    assert opener.open.call_count == 1


@pytest.mark.parametrize("url", [
    "https://api.anthropic.com/v1", "http://user:secret@127.0.0.1/v1",
    "http://localhost.example.com", "http://127.0.0.1?key=secret",
    "http://127.0.0.1/#secret",
])
def test_only_credential_free_loopback(url):
    with pytest.raises(ValueError):
        MessagesTransport(url, MODEL)


@pytest.mark.parametrize("name,value", [
    ("max_output_tokens", True), ("max_output_tokens", "2"),
    ("max_request_bytes", 0), ("max_response_bytes", 4_194_305),
    ("allow_network", 1), ("timeout", 0), ("timeout", float("nan")),
])
def test_inherited_bounds_are_not_coerced(name, value):
    with pytest.raises(ValueError):
        MessagesTransport("http://127.0.0.1", MODEL, **{name: value})
