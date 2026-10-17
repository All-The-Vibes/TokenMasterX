from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
from quality.responses import ResponsesTransport  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    status = 200
    body = b'{"object":"response","status":"completed","model":"fixture","output":[]}'
    requests = []

    def log_message(self, *_):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.requests.append((self.path, dict(self.headers), body))
        self.send_response(self.status)
        if self.status == 302:
            self.send_header("Location", "http://example.invalid/never-follow")
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.body)


@pytest.fixture
def server():
    Handler.requests = []
    Handler.status = 200
    Handler.body = b'{"object":"response","status":"completed","model":"fixture","output":[]}'
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_disabled_transport_does_not_send(server):
    result = ResponsesTransport(server, "fixture").call({"input": []})
    assert result.reason == "network_not_allowed"
    assert not Handler.requests


def test_transport_initialization_error_is_not_a_sent_model_request(server, monkeypatch):
    import ssl
    def broken(*args):
        raise ssl.SSLError("synthetic setup failure")
    monkeypatch.setattr("quality.responses.build_opener", broken)
    result = ResponsesTransport(server, "fixture", allow_network=True).call({"input": []})
    assert result.reason == "transport_setup_error"
    assert result.error_type == "SSLError"
    assert result.input_text is None
    assert not Handler.requests


def test_captures_actual_full_wire_strings_and_no_credentials(server, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "DO_NOT_USE")
    transport = ResponsesTransport(server, "fixture", allow_network=True)
    result = transport.call({"input": [{"role": "user", "content": "漢 <|endoftext|>"}]})
    assert result.ok and result.complete
    path, headers, body = Handler.requests[0]
    assert path == "/v1/responses"
    assert "Authorization" not in headers
    assert body.decode() == result.input_text
    assert Handler.body.decode() == result.output_text
    assert json.loads(body)["stream"] is False
    assert json.loads(body)["store"] is False
    assert "DO_NOT_USE" not in repr(result)


@pytest.mark.parametrize("status", [302, 401, 500])
def test_failed_http_response_still_has_complete_observed_text(server, status):
    Handler.status = status
    result = ResponsesTransport(server, "fixture", allow_network=True).call({"input": []})
    assert not result.ok and result.complete
    assert result.output_text == Handler.body.decode()
    assert len(Handler.requests) == 1


def test_no_response_clipping_masquerades_as_complete(server):
    Handler.body = b"x" * 1000
    result = ResponsesTransport(server, "fixture", allow_network=True,
                                max_response_bytes=64).call({"input": []})
    assert result.reason == "response_too_large"
    assert not result.complete and result.output_text is None


def test_model_mismatch_is_explicit(server):
    result = ResponsesTransport(server, "other", allow_network=True).call({"input": []})
    assert not result.ok and result.reason == "model_mismatch"
    assert result.complete


@pytest.mark.parametrize("url", [
    "https://api.openai.com/v1", "http://user:secret@127.0.0.1/v1",
    "http://localhost.example.com/v1", "http://127.0.0.1/v1?key=secret",
])
def test_rejects_nonlocal_or_credential_bearing_urls(url):
    with pytest.raises(ValueError):
        ResponsesTransport(url, "fixture", allow_network=True)
