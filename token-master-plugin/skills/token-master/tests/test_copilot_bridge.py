"""brainspace_copilot_bridge: the cache-stable system prompt plus v6 on every request, as a local BYOK bridge."""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

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


def test_lean_command_drops_the_workflow_tools_unless_a_workflow_is_asked_for(monkeypatch, tmp_path):
    workflow_tools = {"run_dynamic_workflow", "dynamic_workflows_manage"}  # about 2,040 tokens a call on 1.0.104
    lookup = bridge_module.lean_command(["copilot", "-p", "Who calls validate_password? Answer with JSON."])
    assert workflow_tools <= set(lookup[lookup.index("--excluded-tools") + 1:])
    skill_home(tmp_path, monkeypatch, "review-pr")
    for prompt in ("Run the nightly-audit workflow on this repo", "Use run_dynamic_workflow to review the diff",
                   "Start my_audit_workflow", "/review-pr 123"):  # a skill's slash command may start a workflow
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
    (tmp_path / ".git").mkdir()
    (tmp_path / "skills" / "impeccable").mkdir(parents=True)
    (tmp_path / "skills" / "review-pr").mkdir(parents=True)
    for prompt in ("/review-pr 123", "Use the tokenomics skill", "Run impeccable on this UI"):
        assert not agent_tools & excluded(["copilot", "-p", prompt]), prompt
    for command in (["copilot", "-p", "fix the failing test in parser.py"], ["copilot"]):
        assert agent_tools <= excluded(command), command
    monkeypatch.setenv("TOKENMASTER_KEEP_TOOLS", "skills")
    assert not agent_tools & excluded(["copilot", "-p", "hi"])


def skill_home(tmp_path, monkeypatch, *skills):
    """An empty Copilot home with these skills, and a repository root as the working folder."""
    monkeypatch.delenv("TOKENMASTER_KEEP_TOOLS", raising=False)
    monkeypatch.delenv("COPILOT_SKILLS_DIRS", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))  # no Copilot CLI package, so no built-in skills
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir(exist_ok=True)
    for name in skills:
        (tmp_path / "home" / "skills" / name).mkdir(parents=True)
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    monkeypatch.chdir(tmp_path / "repo")


def kept_tools(command):
    return set(bridge_module.LEAN_EXCLUDED_TOOLS) - set(bridge_module.select_excluded_tools(command))


def test_only_an_installed_skill_named_by_a_slash_or_a_verb_keeps_the_skill_tools(monkeypatch, tmp_path):
    skill_home(tmp_path, monkeypatch, "loop", "humanizer", "review-pr", "token-master")
    for prompt in ("/review-pr 123", "Please run /review-pr on 123", "/REVIEW-PR, now", "Run `/review-pr` on 123",
                   "(/review-pr 123)", "/token-master uninstall", "Use the humanizer skill",
                   "Review this using the humanizer skill", "Run humanizer on the README", "Use the humanizer on README.md",
                   "Don't forget to use the humanizer skill", "Fetch skill://humanizer/notes.md",
                   "Use the skill tool to list the available skills"):
        assert "skill" in kept_tools(["copilot", "-p", prompt]), prompt
    for prompt in ("Fix the bug in /src/app.py", "POST /users returns 400", "the /login route is broken",
                   "fix the infinite loop in parser.py", "/review-prs 123", "the humanizer output looks odd",
                   "Seed the database with sample skills", "use the skills table for the join", "ask humanizer to tidy up",
                   "Do not use the review skill", "never run the humanizer skill on code comments",
                   "don't use the humanizer skill", "don\u2019t use the humanizer skill", "dont use the humanizer skill",
                   "avoid using the humanizer skill", "without using the humanizer skill", "do not  use the humanizer skill",
                   "never run /review-pr here", "don't run `/review-pr` here", 'never use "/review-pr" here',
                   "avoid using (/review-pr)", "Why does the launcher exclude the skill tool?"):
        assert not kept_tools(["copilot", "-p", prompt]), prompt


def test_one_and_two_character_skill_names_count(monkeypatch, tmp_path):
    # Copilot CLI 1.0.105 lists skills named `ui` and `x` (PR #19 review); an explicit invocation keeps their tool too.
    skill_home(tmp_path, monkeypatch, "ui", "x")
    for prompt in ("/ui Review the page", "Use ui to review the page", "/x go"):
        assert "skill" in kept_tools(["copilot", "-p", prompt]), prompt
    for prompt in ("the ui looks off", "x marks the spot", "Fix the bug in /src/app.py"):
        assert not kept_tools(["copilot", "-p", prompt]), prompt


def test_a_negation_cancels_only_skill_and_agent_names(monkeypatch, tmp_path):
    skill_home(tmp_path, monkeypatch)
    workflow_tools = {"run_dynamic_workflow", "dynamic_workflows_manage"}
    assert kept_tools(["copilot", "-p", "Never run the workflow on main"]) == workflow_tools
    assert kept_tools(["copilot", "-p", "don't run subagents in parallel, run them one at a time"]) == {
        "task", "read_agent", "write_agent", "list_agents"}
    assert kept_tools(["copilot", "-p", "never run sql scratchpad queries against prod"]) == {"sql"}


def test_a_prompt_given_with_i_counts_like_one_given_with_p(monkeypatch, tmp_path):
    skill_home(tmp_path, monkeypatch, "review-pr")
    for command in (["copilot", "-i", "/review-pr 123"], ["copilot", "--interactive=/review-pr 123"],
                    ["copilot", "--interactive", "Use the humanizer skill"]):
        assert "skill" in kept_tools(command), command
    assert not kept_tools(["copilot", "-i", "fix the failing test in parser.py"])


def test_skill_names_come_from_every_folder_copilot_cli_reads(monkeypatch, tmp_path):
    def skill(*parts):
        tmp_path.joinpath(*parts).mkdir(parents=True)
        tmp_path.joinpath(*parts, "SKILL.md").write_text("---\nname: x\ndescription: x\n---\n", encoding="utf-8")

    monkeypatch.delenv("TOKENMASTER_KEEP_TOOLS", raising=False)
    monkeypatch.delenv("COPILOT_HOME", raising=False)
    for variable in ("USERPROFILE", "HOME"):
        monkeypatch.setenv(variable, str(tmp_path / "profile"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    monkeypatch.setenv("COPILOT_SKILLS_DIRS", f"{tmp_path / 'env-a'}, {tmp_path / 'env-b'}")
    (tmp_path / ".git").mkdir()  # keeps every walk inside tmp_path
    skill("profile", ".copilot", "skills", "group", "nested-skill")
    skill("profile", ".agents", "skills", "home-agents-skill")
    skill("profile", ".claude", "skills", "home-claude-skill")  # Copilot CLI does not read it
    skill("profile", ".copilot", "installed-plugins", "market", "plug", "skills", "plugin-skill")
    skill("localappdata", "copilot", "pkg", "win32-x64", "9.9.9", "builtin", "builtin-skill")
    skill("env-a", "env-skill-a")
    skill("env-b", "env-skill-b")
    skill("custom", "custom-skill")
    (tmp_path / "profile" / ".copilot" / "settings.json").write_text(
        json.dumps({"skillDirectories": [str(tmp_path / "custom")]}), encoding="utf-8")
    skill("w", ".github", "skills", "outside-skill")  # above the repository root
    skill("w", "repo", ".agents", "skills", "repo-skill")
    skill("w", "repo", ".github", "skills", "repo-github-skill")
    (tmp_path / "w" / "repo" / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / "w" / "repo" / ".claude" / "commands" / "claude-command.md").write_text("Do it.", encoding="utf-8")
    skill("w", "other", ".claude", "skills", "other-skill")
    skill("w", "added", ".github", "skills", "added-skill")
    skill("w", "plugin", "skills", "dir-plugin-skill")
    for repo in ("repo", "other"):
        (tmp_path / "w" / repo / ".git").mkdir()
    (tmp_path / "w" / "repo" / "src").mkdir()
    monkeypatch.chdir(tmp_path / "w" / "repo" / "src")
    names = bridge_module._installed_names("skills")
    assert {"nested-skill", "home-agents-skill", "plugin-skill", "builtin-skill", "env-skill-a", "env-skill-b",
            "custom-skill", "repo-skill", "repo-github-skill", "claude-command"} <= names
    assert not {"outside-skill", "other-skill", "added-skill", "dir-plugin-skill", "home-claude-skill"} & names
    assert "skill" in kept_tools(["copilot", "-p", "/plug:plugin-skill go"])
    flags = ["copilot", "-C", "../../other", "--add-dir", "../added", "--plugin-dir", str(tmp_path / "w" / "plugin")]
    names = bridge_module._installed_names("skills", flags)
    assert {"other-skill", "added-skill", "dir-plugin-skill"} <= names and "repo-skill" not in names
    (tmp_path / "profile" / "work").mkdir()
    monkeypatch.chdir(tmp_path / "profile" / "work")  # outside any repository: the walk passes the profile
    names = bridge_module._installed_names("skills")
    assert "home-agents-skill" in names and "home-claude-skill" not in names
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / "profile" / ".copilot"))  # then Copilot CLI skips ~/.agents
    monkeypatch.chdir(tmp_path / "w" / "repo")
    names = bridge_module._installed_names("skills")
    assert "nested-skill" in names and "home-agents-skill" not in names


def test_the_profile_under_another_name_still_skips_its_claude_skills(monkeypatch, tmp_path):
    """Copilot CLI 1.0.105 skipped ~/.claude/skills from an 8.3 short path too. A junction (or a symlink) gives the
    profile a second name the same way."""
    profile = tmp_path / "profile"
    (profile / ".claude" / "skills" / "home-claude-skill").mkdir(parents=True)
    (profile / ".claude" / "skills" / "home-claude-skill" / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    (profile / "work").mkdir()
    (tmp_path / ".git").mkdir()
    alias = tmp_path / "alias"
    try:
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(profile)], check=True, capture_output=True)
        else:
            alias.symlink_to(profile, target_is_directory=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("cannot make a junction or a symlink here")
    for variable in ("COPILOT_HOME", "COPILOT_SKILLS_DIRS"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    for variable in ("USERPROFILE", "HOME"):
        monkeypatch.setenv(variable, str(profile))
    monkeypatch.chdir(alias / "work")
    assert "home-claude-skill" not in bridge_module._installed_names("skills")


def test_agent_names_need_an_invocation_too(monkeypatch, tmp_path):
    skill_home(tmp_path, monkeypatch)
    (tmp_path / "home" / "agents").mkdir()
    (tmp_path / "home" / "agents" / "auditor.agent.md").write_text("# auditor", encoding="utf-8")
    agent_tools = {"task", "read_agent", "write_agent", "list_agents"}
    for prompt in ("Ask auditor to check this diff", "Ask the auditor to check this diff", "use auditor to verify the fix",
                   "the auditor agent should look"):
        assert kept_tools(["copilot", "-p", prompt]) == agent_tools, prompt
    for prompt in ("the auditor report is wrong", "do not use auditor for this", "don't ask the auditor agent"):
        assert not kept_tools(["copilot", "-p", prompt]), prompt


def test_fleet_agent_commands_and_short_resume_keep_what_they_use(monkeypatch, tmp_path):
    skill_home(tmp_path, monkeypatch)
    agent_tools = {"task", "read_agent", "write_agent", "list_agents"}
    # In an interactive Copilot CLI 1.0.104 session these commands tell the model to use task(agent_type=...), and fleet
    # mode tracks its subagents in the sql tool's todos table (evidence/skill-trigger-20261029/tty_captures.json).
    for command in (["copilot", "--fleet", "-p", "Add docstrings"], ["copilot", "-i", "/fleet Add docstrings"]):
        assert kept_tools(command) == agent_tools | {"sql"}, command
    for prompt in ("/review", "/security-review", "/research how does parse work"):
        assert kept_tools(["copilot", "-p", prompt]) == agent_tools, prompt
    for prompt in ("/rubber-duck critique app.py", "POST /review returns 500", "check the /fleet status page"):
        assert not kept_tools(["copilot", "-p", prompt]), prompt  # unconfirmed, or not at the start
    for command in (["copilot", "-r"], ["copilot", "-r", "abc123"], ["copilot", "-rabc123"]):
        assert kept_tools(command) == {"session_store_sql"}, command


def test_without_a_provider_url_the_launcher_runs_the_command_directly(monkeypatch):
    monkeypatch.delenv("COPILOT_PROVIDER_BASE_URL", raising=False)
    script = "import os, sys; sys.exit(5 if 'COPILOT_PROVIDER_BASE_URL' not in os.environ else 1)"
    assert bridge_module.main(["--", sys.executable, "-c", script]) == 5
    with pytest.raises(SystemExit):
        bridge_module.main([])  # nothing to run and nothing to serve


def stamp():
    time.sleep(0.002)  # Copilot CLI writes times to the millisecond; keep each one apart
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class FakeCopilot:
    """Stands in for Copilot CLI 1.0.105 in run_child. It keeps each command it gets and, as the real one does, a
    folder in <COPILOT_HOME>/session-state and a row in session-store.db per session. --resume, -r and --session-id
    resume the session whose ID starts with their value, and --continue the session updated last (prompt mode's rule;
    the tests that use it from an interactive launch have all their sessions in one folder)."""

    def __init__(self, home):
        self.home, self.commands, self.session = home, [], None
        (home / "session-state").mkdir(parents=True, exist_ok=True)
        self.sql("create table if not exists sessions (id text primary key, cwd text, repository text, "
                 "created_at text, updated_at text)")

    def sql(self, statement, *values):
        db = sqlite3.connect(self.home / "session-store.db")
        try:
            rows = db.execute(statement, values).fetchall()
            db.commit()
            return rows
        finally:
            db.close()

    def add(self, session, folder, created, repository=None):
        (self.home / "session-state" / session).mkdir()
        self.sql("insert into sessions values (?, ?, ?, ?, ?)", session, folder, repository, created, created)

    def __call__(self, parser, command, env):
        self.commands.append(command)
        ids = [row[0] for row in self.sql("select id from sessions order by updated_at")]
        target = ids[-1] if "--continue" in command and ids else None
        for flag in ("--resume", "-r", "--session-id"):
            if flag in command[:-1]:
                target = next((i for i in ids if i.startswith(command[command.index(flag) + 1])), None)
        if target:
            self.sql("update sessions set updated_at = ? where id = ?", stamp(), target)
        else:
            target = str(uuid.uuid4())
            folder = command[command.index("-C") + 1] if "-C" in command[:-1] else "."
            self.add(target, os.path.abspath(folder), stamp())
        self.session = target
        return 0

    def excluded(self):
        command = self.commands[-1]
        return command[command.index("--excluded-tools") + 1:] if "--excluded-tools" in command else []


@pytest.fixture
def copilot(tmp_path, monkeypatch):
    """main() runs this fake Copilot CLI, without a provider URL, in an empty Copilot home and a repository root."""
    skill_home(tmp_path, monkeypatch)
    monkeypatch.delenv("COPILOT_PROVIDER_BASE_URL", raising=False)
    fake = FakeCopilot(tmp_path / "home")
    monkeypatch.setattr(bridge_module, "run_child", fake)
    return fake


def test_a_resumed_session_sends_the_tool_list_it_started_with(copilot, monkeypatch):
    # Copilot CLI sends the old history with the new launch's tools, so a resume that routed again (12 tools, with
    # session_store_sql kept) changed the start of every request the session sent.
    lean, agents = set(bridge_module.LEAN_EXCLUDED_TOOLS), set(bridge_module.CAPABILITY_GROUPS["agents"][0])
    bridge_module.main(["--", "copilot"])
    plain = copilot.session
    assert set(copilot.excluded()) == lean
    bridge_module.main(["--", "copilot", "-p", "spawn an agent to review this"])
    kept, first = copilot.session, copilot.excluded()
    assert set(first) == lean - agents
    bridge_module.main(["--", "copilot", "--continue", "-p", "now fix what it found"])
    assert copilot.session == kept and copilot.excluded() == first
    bridge_module.main(["--", "copilot", "--resume", plain, "-p", "spawn an agent to review this"])
    assert copilot.session == plain and set(copilot.excluded()) == lean  # the resume's own prompt changes nothing
    bridge_module.main(["--", "copilot", "-r", kept[:8]])
    assert copilot.session == kept and copilot.excluded() == first
    bridge_module.main(["--", "copilot", "--session-id", kept, "-p", "look at previous sessions"])
    assert copilot.session == kept and copilot.excluded() == first
    elsewhere = copilot.home.parent / "elsewhere"
    elsewhere.mkdir()
    bridge_module.main(["--", "copilot", "-C", str(elsewhere), "-p", "spawn an agent to review this"])
    other = copilot.session
    bridge_module.main(["--", "copilot", "--resume", other])  # tied through the -C folder it ran in
    assert copilot.excluded() == first
    monkeypatch.setenv("TOKENMASTER_KEEP_TOOLS", "sql,skills")  # still keeps tools, as on any launch
    bridge_module.main(["--", "copilot", "--resume", plain])
    with_keep = copilot.excluded()
    assert set(with_keep) == set(bridge_module.select_excluded_tools(["copilot"])) != lean
    monkeypatch.delenv("TOKENMASTER_KEEP_TOOLS")
    bridge_module.main(["--", "copilot", "--resume", plain])  # and later resumes keep the list it sent
    assert copilot.excluded() == with_keep


def test_a_resume_without_a_record_routes_as_before(copilot):
    def routed(command):
        return list(bridge_module.select_excluded_tools(command))

    for command in (["copilot", "--continue"], ["copilot", "--resume", "no-such-session"]):
        bridge_module.main(["--", *command])  # nothing to resume yet: Copilot CLI starts a new session
        assert copilot.excluded() == routed(command), command
    copilot(None, ["copilot"], {})  # a session started without the launcher
    stock = copilot.session
    for command in (["copilot", "--resume", stock], ["copilot", "-r"], ["copilot", "--resume", "my session name"]):
        bridge_module.main(["--", *command])
        assert copilot.excluded() == routed(command) and "session_store_sql" not in copilot.excluded(), command
    registry = bridge_module.launch_registry()
    registry.write_text(registry.read_text(encoding="utf-8").replace(', "excluded": [', ', "old": ['), encoding="utf-8")
    bridge_module.main(["--", "copilot", "--continue"])  # records written before the launcher listed its tools
    assert copilot.excluded() == routed(["copilot", "--continue"])


def test_the_latest_launch_of_a_session_sets_its_list(copilot):
    bridge_module.main(["--", "copilot", "-p", "spawn an agent to review this"])
    session = copilot.session
    bridge_module.main(["--all-tools", "--", "copilot", "--resume", session])
    assert copilot.excluded() == []
    bridge_module.main(["--", "copilot", "--resume", session])  # every tool, as the last launch sent
    assert copilot.excluded() == []
    records = [json.loads(line) for line in bridge_module.launch_registry().read_text(encoding="utf-8").splitlines()]
    assert [r["session"] for r in records if r["event"] == "start"] == [None, session, session]


def test_resumed_session_reads_ids_prefixes_and_continue(copilot):
    elsewhere, here = str(copilot.home.parent / "elsewhere"), os.getcwd()  # here: a repository root
    one, two, three, four, five = (f"aaaaaaa{n}-0000-4000-8000-000000000000" for n in range(1, 6))
    copilot.add(one, elsewhere, stamp())
    copilot.add(two, elsewhere, stamp())
    for flags in (["--resume", one], [f"--resume={one}"], ["-r", one[:8]], [f"-r{one[:8]}"], ["--session-id", one],
                  ["--allow-all-tools", "--resume", one[:9], "-p", "x"]):
        assert bridge_module.resumed_session(["copilot", *flags]) == one, flags
    for flags in ([], ["-r"], ["--resume", "-p", "x"], ["-r", "aaaaaaa"], ["-r", one[:6]], ["--session-id", one[:8]],
                  ["--session-id", str(uuid.uuid4())]):
        assert bridge_module.resumed_session(["copilot", *flags]) is None, flags
    lone = "bbbbbbb1-0000-4000-8000-000000000000"
    copilot.add(lone, elsewhere, "2026-10-01T00:00:00.000Z")
    (copilot.home / "session-state" / f"{lone}.jsonl").write_text("", encoding="utf-8")  # as older versions kept one
    assert bridge_module.resumed_session(["copilot", "-r", lone[:7]]) == lone
    assert bridge_module.resumed_session(["copilot", "-r", lone[:6]]) is None  # 7 characters at least

    def continued(*flags):
        return bridge_module.resumed_session(["copilot", "--continue", *flags])

    # Prompt mode takes the session updated last in any folder; without -p (an interactive session, or a prompt piped
    # on stdin) it is the one updated last in the working folder's GitHub repository, else in the folder, else
    # anywhere (evidence/session-tools-20261030).
    assert continued("-p", "x") == continued() == two
    copilot.add(three, here, stamp())
    copilot.sql("update sessions set updated_at = ? where id = ?", stamp(), two)
    assert continued("-p", "x") == two and continued() == three and continued("-C", elsewhere) == two
    copilot.add(four, os.path.join(here, "sub"), stamp(), "octo/repo")
    copilot.add(five, elsewhere, stamp())
    assert continued("-p", "x") == five and continued() == four  # the repository's session, though not this folder's
    copilot.add(six := "aaaaaaa6-0000-4000-8000-000000000000", str(copilot.home.parent / "clone"), stamp(), "octo/repo")
    assert continued() == six  # another clone of the same GitHub repository counts too
    copilot.sql("create table older as select id, cwd, created_at, updated_at from sessions")
    copilot.sql("drop table sessions")
    copilot.sql("alter table older rename to sessions")  # a store without the repository column
    assert continued("-p", "x") == six and continued() == three


def test_a_session_that_no_one_launch_alone_started_is_routed_as_before(copilot):
    """A session is tied to the launch that started it only when that new launch saw it start, and no other session,
    in its folder in its first two minutes, and no other new launch saw it start. In the probes Copilot CLI 1.0.105
    started each launch's session within 9 s. Otherwise which list went where is a guess."""
    base, folder = datetime.now(timezone.utc) - timedelta(days=1), os.getcwd()
    other = str(copilot.home.parent / "elsewhere")

    def at(seconds):
        return (base + timedelta(seconds=seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def launch(name, start, end=None, cwd=folder, resumes=None):
        bridge_module._record_launch({"event": "start", "id": name, "at": at(start), "cwd": cwd, "lean": True,
                                      "excluded": ["sql"], "session": resumes})
        if end is not None:
            bridge_module._record_launch({"event": "end", "id": name, "at": at(end)})

    launch("alone", 0, 60)
    copilot.add("s-alone", folder, at(2))
    launch("calm", 500, 560)
    copilot.add("s-calm", folder, at(502))
    copilot.add("s-calm-elsewhere", other, at(505))  # another folder's session does not count
    launch("first", 1000, 1600)
    launch("second", 1003, 1600)
    copilot.add("s-overlap", folder, at(1007))  # two launches saw it start
    launch("busy", 2000, 2600)
    copilot.add("s-busy", folder, at(2002))
    copilot.add("s-stranger", folder, at(2030))  # another session in that launch's first two minutes
    launch("killed", 3000)  # no end record
    copilot.add("s-late", folder, at(6600))  # an hour later
    launch("away", 7000, 7060, cwd=other)
    copilot.add("s-away", folder, at(7002))  # the only launch then ran in another folder
    launch("resuming", 8000, 8060, resumes="s-old")
    copilot.add("s-during-resume", folder, at(8002))  # a launch that resumed a session started none
    for session in ("s-alone", "s-calm"):
        bridge_module.main(["--", "copilot", "--resume", session])
        assert copilot.excluded() == ["sql"], session
    for session in ("s-overlap", "s-busy", "s-stranger", "s-late", "s-away", "s-during-resume"):
        command = ["copilot", "--resume", session]
        bridge_module.main(["--", *command])
        assert copilot.excluded() == list(bridge_module.select_excluded_tools(command)), session


def test_the_users_own_tools_and_a_damaged_record_route_as_before(copilot):
    bridge_module.main(["--", "copilot", "--excluded-tools", "sql", "-p", "fix the parser"])
    own = copilot.session
    records = [json.loads(line) for line in bridge_module.launch_registry().read_text(encoding="utf-8").splitlines()]
    assert copilot.commands[-1] == ["copilot", "--excluded-tools", "sql", "-p", "fix the parser"]
    assert records[0]["excluded"] is None  # the launcher cannot give the session that list again
    command = ["copilot", "--resume", own]
    bridge_module.main(["--", *command])
    assert copilot.excluded() == list(bridge_module.select_excluded_tools(command))
    bridge_module._record_launch({"event": "start", "id": "damaged", "at": 1})  # valid JSON, wrong types
    assert bridge_module.main(["--", *command]) == 0  # no traceback: a damaged record never stops a launch
    assert copilot.excluded() == list(bridge_module.select_excluded_tools(command))
