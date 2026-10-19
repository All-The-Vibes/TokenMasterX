"""brainspace_copilot_bridge: the cache-stable system prompt plus v6 on every request, as a local BYOK bridge."""
from __future__ import annotations

import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import urllib.error
import urllib.request

import pytest

SKILL = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("brainspace_copilot_bridge", SKILL / "brainspace_copilot_bridge.py")
bridge_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bridge_module)

SYSTEM = "You are Copilot.\n<session_context>\nSession folder: C:/Users/dev/.copilot/session-state/{}\n</session_context>"
BIG = "\n".join(f"def function_{i}():\n    return {i}" for i in range(3000))  # far above every v6 budget
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def count(text):  # deterministic stand-in for the pinned tokenizer
    return len(text) // 4


def request(folder="abc", history=()):
    return {"model": "m", "stream": True, "input": [
        {"type": "message", "role": "system", "content": SYSTEM.format(folder)},
        {"type": "message", "role": "user", "content": "Find the bug."}, *history]}


def call(call_id, name, arguments, output):
    return [{"type": "function_call", "call_id": call_id, "name": name, "arguments": json.dumps(arguments)},
            {"type": "function_call_output", "call_id": call_id, "output": output}]


def test_rewrite_moves_the_folder_and_shapes_only_measured_tools():
    history = (call("1", "view", {"path": "a.py"}, BIG) + call("2", "powershell", {"command": "x"}, BIG)
               + call("3", "view", {"path": "a.py", "view_range": [1, 5]}, BIG)
               + call("4", "grep", {"pattern": "x"}, "Error: bad pattern\n" + BIG))
    body = request(history=history)
    before = json.dumps(body)
    out, receipt = bridge_module.rewrite_request(body, count)
    assert json.dumps(body) == before  # the client's object is untouched
    assert receipt["stable_prefix"] is True and receipt["shaped"] == 1 and receipt["tool_outputs"] == 4
    outputs = [item["output"] for item in out["input"] if item.get("type") == "function_call_output"]
    assert "[Outline only" in outputs[0] and len(outputs[0]) < len(BIG)
    assert outputs[1:] == [BIG, BIG, "Error: bad pattern\n" + BIG]
    assert out["input"][1]["content"].startswith("Session folder: C:/Users/dev/.copilot/session-state/abc\n\n")


def test_every_call_and_every_session_repeat_the_same_prefix_bytes():
    first, _ = bridge_module.rewrite_request(request("one", call("1", "view", {"path": "a.py"}, BIG)), count)
    later, _ = bridge_module.rewrite_request(
        request("one", call("1", "view", {"path": "a.py"}, BIG) + call("2", "glob", {"pattern": "*"}, "a.py")), count)
    other, receipt = bridge_module.rewrite_request(request("two"), count)
    assert later["input"][:4] == first["input"]  # earlier messages stay byte-identical as history grows
    assert first["input"][0] == other["input"][0]  # every session shares the system prompt
    assert receipt["prefix_sha256"] == bridge_module.rewrite_request(request("three"), count)[1]["prefix_sha256"]


def test_without_a_tokenizer_only_the_prefix_moves():
    out, receipt = bridge_module.rewrite_request(request(history=call("1", "view", {"path": "a.py"}, BIG)), None)
    assert receipt["stable_prefix"] is True and receipt["shaped"] == 0 and out["input"][-1]["output"] == BIG


class Upstream:
    """A fake provider: records what it receives and answers with an event stream."""

    def __init__(self):
        self.seen = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass

            def do_GET(self):
                outer.seen.append(("GET", self.path, dict(self.headers), None))
                self.send(200, "application/json", b'{"data":[]}')

            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                outer.seen.append(("POST", self.path, dict(self.headers), body))
                if not self.path.endswith("/responses"):
                    return self.send(400, "application/json", b'{"error":"nope"}')
                self.send(200, "text/event-stream",
                          b'data: {"type":"response.created","response":{"usage":null}}\n\n'
                          b'data: {"type":"response.completed","response":{"usage":{"input_tokens":3600,'
                          b'"input_tokens_details":{"cached_tokens":3500,"cache_write_tokens":0},"output_tokens":9}}}\n\n')

            def send(self, status, kind, payload):
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"


@pytest.fixture
def upstream():
    fake = Upstream()
    yield fake
    fake.server.shutdown()
    fake.server.server_close()


def post(url, body, headers=None):
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with OPENER.open(req, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def test_bridge_forwards_rewritten_requests_and_relays_streams(upstream, tmp_path):
    log = tmp_path / "usage.jsonl"
    with bridge_module.Bridge(upstream.url, log=log, count=count) as bridge:
        status, data = post(bridge.url + "/responses", json.dumps(request()).encode(),
                            {"Authorization": "Bearer user-key"})
        assert status == 200 and b"response.created" in data and data.endswith(b'"output_tokens":9}}}\n\n')
        method, path, headers, sent = upstream.seen[-1]
        assert (method, path, headers["Authorization"]) == ("POST", "/v1/responses", "Bearer user-key")
        assert json.loads(sent) == bridge_module.rewrite_request(request(), count)[0]
        assert post(bridge.url + "/other", b"not json") == (400, b'{"error":"nope"}')
        assert upstream.seen[-1][3] == b"not json"  # only Responses requests are rewritten
        with OPENER.open(bridge.url + "/models", timeout=10) as response:
            assert (response.status, response.read()) == (200, b'{"data":[]}')
        assert upstream.seen[-1][:2] == ("GET", "/v1/models")
    text = log.read_text(encoding="utf-8")
    rows = [json.loads(line) for line in text.splitlines()]
    assert len(rows) == 1 and rows[0]["path"] == "/responses" and rows[0]["status"] == 200
    assert (rows[0]["input"], rows[0]["cached"], rows[0]["output"], rows[0]["stable_prefix"]) == (3600, 3500, 9, True)
    assert "Session folder" not in text and "Find the bug" not in text  # usage numbers only, no content


def test_unreachable_upstream_is_a_clear_gateway_error():
    with bridge_module.Bridge("http://127.0.0.1:9", count=count) as bridge:
        status, data = post(bridge.url + "/responses", json.dumps(request()).encode())
    assert status == 502 and b"tokenmaster_bridge_upstream_" in data


def raw_get(bridge, target):
    import socket
    with socket.create_connection(("127.0.0.1", bridge.server.server_address[1]), timeout=10) as sock:
        sock.sendall(f"GET {target} HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n".encode())
        return sock.makefile("rb").readline()


@pytest.mark.parametrize("target", ["@127.0.0.1:9/responses", "http://127.0.0.1:9/x"])
def test_request_targets_cannot_redirect_to_another_host(upstream, target):
    with bridge_module.Bridge(upstream.url, count=count) as bridge:
        assert raw_get(bridge, target).startswith(b"HTTP/1.1 400")
    assert upstream.seen == []


def test_double_slash_paths_stay_on_the_upstream(upstream):
    with bridge_module.Bridge(upstream.url, count=count) as bridge:
        assert raw_get(bridge, "//127.0.0.1:9/models").startswith(b"HTTP/1.1 200")
    assert upstream.seen[-1][:2] == ("GET", "/v1/127.0.0.1:9/models")


def test_server_errors_stay_out_of_the_terminal(capsys):
    with bridge_module.Bridge("http://127.0.0.1:9", count=count) as bridge:
        for error in (ConnectionResetError(10054, "reset by the client"), RuntimeError("boom")):
            try:
                raise error
            except Exception:
                bridge.server.handle_error(None, ("127.0.0.1", 1))
    err = capsys.readouterr().err
    assert "Traceback" not in err and err.count("[tokenmaster] bridge request failed: RuntimeError") == 1


def test_launcher_points_the_cli_at_the_bridge(upstream, monkeypatch):
    monkeypatch.setenv("COPILOT_PROVIDER_BASE_URL", upstream.url)
    monkeypatch.delenv("COPILOT_PROVIDER_TYPE", raising=False)
    monkeypatch.delenv("COPILOT_PROVIDER_WIRE_API", raising=False)
    script = ("import os, sys, urllib.request\n"
              "base = os.environ['COPILOT_PROVIDER_BASE_URL']\n"
              "assert base.startswith('http://127.0.0.1:') and os.environ['COPILOT_PROVIDER_WIRE_API'] == 'responses'\n"
              "req = urllib.request.Request(base + '/responses', data=b'{\"input\": []}', method='POST')\n"
              "opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))\n"
              "sys.exit(7 if opener.open(req, timeout=10).status == 200 else 1)\n")
    assert bridge_module.main(["--", sys.executable, "-c", script]) == 7
    assert upstream.seen[-1][:2] == ("POST", "/v1/responses")


@pytest.mark.parametrize("name, value", [("COPILOT_PROVIDER_TYPE", "anthropic"),
                                         ("COPILOT_PROVIDER_WIRE_API", "completions")])
def test_launcher_refuses_wire_formats_it_cannot_rewrite(upstream, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(SystemExit):
        bridge_module.main(["--upstream", upstream.url, "--", sys.executable, "-c", "pass"])
    assert upstream.seen == []


def test_launcher_reports_a_missing_command(upstream):
    with pytest.raises(SystemExit) as stopped:
        bridge_module.main(["--upstream", upstream.url, "--", "no-such-copilot-command-xyz"])
    assert stopped.value.code == 2
