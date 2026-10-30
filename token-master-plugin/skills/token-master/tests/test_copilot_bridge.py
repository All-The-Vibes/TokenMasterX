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


@pytest.mark.parametrize("name, value", [("COPILOT_PROVIDER_TYPE", "azure"),
                                         ("COPILOT_PROVIDER_WIRE_API", "completions")])
def test_launcher_refuses_wire_formats_it_cannot_rewrite(upstream, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(SystemExit):
        bridge_module.main(["--upstream", upstream.url, "--", sys.executable, "-c", "pass"])
    assert upstream.seen == []


def messages_request(folder="abc", history=(), blocks=False):
    system = SYSTEM.format(folder)
    return {"model": "claude", "max_tokens": 100, "stream": True,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}] if blocks else system,
            "messages": [{"role": "user", "content": [{"type": "text", "text": "Find the bug."}] if blocks
                          else "Find the bug."}, *history]}


def tool_turn(use_id, name, arguments, output, **extra):
    return [{"role": "assistant", "content": [{"type": "tool_use", "id": use_id, "name": name, "input": arguments}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": use_id, "content": output, **extra}]}]


def test_messages_rewrite_moves_the_folder_and_shapes_measured_tools():
    history = (tool_turn("1", "view", {"path": "a.py"}, BIG) + tool_turn("2", "powershell", {"command": "x"}, BIG)
               + tool_turn("3", "view", {"path": "a.py"}, [{"type": "text", "text": BIG}])
               + tool_turn("4", "view", {"path": "a.py"}, BIG, is_error=True))
    for blocks in (False, True):
        body = messages_request(history=history, blocks=blocks)
        before = json.dumps(body)
        out, receipt = bridge_module.rewrite_messages_request(body, count)
        assert json.dumps(body) == before
        assert receipt["stable_prefix"] is True and receipt["tool_outputs"] == 4 and receipt["shaped"] == 2
        system = out["system"] if isinstance(out["system"], str) else out["system"][0]["text"]
        assert "session-state" not in system and "Session folder: stated in the first user message" in system
        first = out["messages"][0]["content"]
        assert (first if isinstance(first, str) else first[0]["text"]).startswith("Session folder: C:/Users/dev/")
        if blocks:
            assert out["system"][0]["cache_control"] == {"type": "ephemeral"}
        results = [b["content"] for m in out["messages"][1:] if m["role"] == "user" for b in m["content"]]
        assert "[Outline only" in results[0] and results[1] == BIG and "[Outline only" in results[2][0]["text"]
        assert results[3] == BIG  # errors pass through


def test_messages_sessions_share_the_system_prompt_and_history_stays_stable():
    one, a = bridge_module.rewrite_messages_request(messages_request("one", tool_turn("1", "rg", {"pattern": "x"}, BIG)), count)
    two, b = bridge_module.rewrite_messages_request(messages_request("two"), count)
    later, _ = bridge_module.rewrite_messages_request(
        messages_request("one", tool_turn("1", "rg", {"pattern": "x"}, BIG) + tool_turn("2", "glob", {}, "a.py")), count)
    assert one["system"] == two["system"] and a["prefix_sha256"] == b["prefix_sha256"]
    assert later["messages"][:3] == one["messages"]


def test_usage_reads_anthropic_streams_and_json():
    stream = (b'event: message_start\ndata: {"type":"message_start","message":{"usage":{"input_tokens":120,'
              b'"cache_creation_input_tokens":300,"cache_read_input_tokens":14000,"output_tokens":1}}}\n\n'
              b'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":57}}\n\n')
    assert bridge_module._usage(stream) == {"input": 14420, "cached": 14000, "cache_write": 300, "output": 57}
    body = json.dumps({"usage": {"input_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                                 "output_tokens": 2}}).encode()
    assert bridge_module._usage(body) == {"input": 5, "cached": 0, "cache_write": 0, "output": 2}


def test_launcher_runs_the_anthropic_type_without_a_wire_api(upstream, monkeypatch):
    monkeypatch.setenv("COPILOT_PROVIDER_BASE_URL", upstream.url)
    monkeypatch.setenv("COPILOT_PROVIDER_TYPE", "anthropic")
    monkeypatch.delenv("COPILOT_PROVIDER_WIRE_API", raising=False)
    script = ("import os, sys, urllib.request\n"
              "assert 'COPILOT_PROVIDER_WIRE_API' not in os.environ\n"
              "req = urllib.request.Request(os.environ['COPILOT_PROVIDER_BASE_URL'] + '/v1/messages', "
              "data=b'{\"messages\": []}', method='POST')\n"
              "opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))\n"
              "try:\n    opener.open(req, timeout=10)\nexcept urllib.error.HTTPError as e:\n    sys.exit(7 if e.code == 400 else 1)\n")
    assert bridge_module.main(["--", sys.executable, "-c", script]) == 7  # the fake upstream answers 400 off /responses
    assert upstream.seen[-1][:2] == ("POST", "/v1/v1/messages")


def test_launcher_reports_a_missing_command(upstream):
    with pytest.raises(SystemExit) as stopped:
        bridge_module.main(["--upstream", upstream.url, "--", "no-such-copilot-command-xyz"])
    assert stopped.value.code == 2


def test_lean_command_excludes_unused_tools_unless_the_user_chose():
    lean = bridge_module.lean_command(["C:/x/copilot.exe", "-p", "hi", "--model", "m"])
    assert lean[:5] == ["C:/x/copilot.exe", "-p", "hi", "--model", "m"]
    assert lean[5] == "--excluded-tools" and set(lean[6:]) == set(bridge_module.LEAN_EXCLUDED_TOOLS)
    assert "view" not in lean and "powershell" not in lean and "apply_patch" not in lean
    for kept in (["copilot", "--excluded-tools", "task"], ["copilot", "--available-tools=view"],
                 ["copilot", "help"], ["python", "-c", "pass"]):
        assert bridge_module.lean_command(kept) == kept
    assert bridge_module.lean_command(["copilot"])[1] == "--excluded-tools"


def test_dynamic_tool_routing_keeps_capabilities_matched_by_prompt_or_flags(monkeypatch, tmp_path):
    sub = bridge_module.lean_command(["copilot", "-p", "Spawn a parallel subagent to audit auth"])
    for tool in ("task", "read_agent", "write_agent", "list_agents"):
        assert tool not in sub
    bg = bridge_module.lean_command(["copilot", "-p", "Start the server in the background and check logs"])
    for tool in ("read_powershell", "stop_powershell", "list_powershell"):
        assert tool not in bg
    hist = bridge_module.lean_command(["copilot", "--resume", "-p", "continue"])
    assert "session_store_sql" not in hist
    sk = bridge_module.lean_command(["copilot", "-p", "Use the tokenomics skill"])
    assert "skill" not in sk
    docs = bridge_module.lean_command(["copilot", "-p", "Check Copilot CLI documentation for flags"])
    assert "fetch_copilot_cli_documentation" not in docs
    (tmp_path / "skills" / "impeccable").mkdir(parents=True)
    (tmp_path / "agents").mkdir(parents=True)
    (tmp_path / "agents" / "auditor.agent.md").write_text("# auditor", encoding="utf-8")
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    assert "skill" not in bridge_module.lean_command(["copilot", "-p", "Run impeccable on this UI"])
    assert "task" not in bridge_module.lean_command(["copilot", "-p", "Ask auditor to check this diff"])
    monkeypatch.setenv("TOKENMASTER_KEEP_TOOLS", "sql,agents")
    env_kept = bridge_module.lean_command(["copilot", "-p", "hi"])
    assert "sql" not in env_kept and "task" not in env_kept


def test_lean_command_drops_the_workflow_tools_unless_a_workflow_is_asked_for(monkeypatch):
    workflow_tools = {"run_dynamic_workflow", "dynamic_workflows_manage"}  # about 2,040 tokens a call on 1.0.104
    lookup = bridge_module.lean_command(["copilot", "-p", "Who calls validate_password? Answer with JSON."])
    assert workflow_tools <= set(lookup[lookup.index("--excluded-tools") + 1:])
    for prompt in ("Run the nightly-audit workflow on this repo", "Use run_dynamic_workflow to review the diff",
                   "Start my_audit_workflow", "/review-pr 123"):  # a slash command may start a workflow
        assert not workflow_tools & set(bridge_module.lean_command(["copilot", "-p", prompt])), prompt
    monkeypatch.setenv("TOKENMASTER_KEEP_TOOLS", "workflows")
    assert not workflow_tools & set(bridge_module.lean_command(["copilot", "-p", "hi"]))


def test_a_prompt_that_starts_a_skill_keeps_the_subagent_tools(monkeypatch, tmp_path):
    agent_tools = {"task", "read_agent", "write_agent", "list_agents"}  # about 2,670 tokens a call on 1.0.104

    def excluded(command):
        lean = bridge_module.lean_command(command)
        return set(lean[lean.index("--excluded-tools") + 1:])

    monkeypatch.delenv("TOKENMASTER_KEEP_TOOLS", raising=False)
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "skills" / "impeccable").mkdir(parents=True)
    for prompt in ("/review-pr 123", "Use the tokenomics skill", "Run impeccable on this UI"):
        assert not agent_tools & excluded(["copilot", "-p", prompt]), prompt
    for command in (["copilot", "-p", "fix the failing test in parser.py"], ["copilot"]):
        assert agent_tools <= excluded(command), command
    monkeypatch.setenv("TOKENMASTER_KEEP_TOOLS", "skills")
    assert not agent_tools & excluded(["copilot", "-p", "hi"])


def test_without_a_provider_url_the_launcher_runs_the_command_directly(monkeypatch):
    monkeypatch.delenv("COPILOT_PROVIDER_BASE_URL", raising=False)
    script = "import os, sys; sys.exit(5 if 'COPILOT_PROVIDER_BASE_URL' not in os.environ else 1)"
    assert bridge_module.main(["--", sys.executable, "-c", script]) == 5
    with pytest.raises(SystemExit):
        bridge_module.main([])  # nothing to run and nothing to serve
