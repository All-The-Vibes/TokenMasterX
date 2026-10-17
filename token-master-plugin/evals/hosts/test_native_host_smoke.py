import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_host_smoke import clean_environment, dictionaries, invoke, run_scenario
from mock_provider import MockProvider


def test_environment_does_not_inherit_real_keys_or_custom_config(tmp_path, monkeypatch):
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GH_TOKEN", "GITHUB_TOKEN",
                "COPILOT_GITHUB_TOKEN", "CODEX_HOME", "CLAUDE_CONFIG_DIR",
                "NODE_OPTIONS", "PYTHONPATH", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.setenv(key, "DO_NOT_INHERIT")
    env = clean_environment(tmp_path)
    assert "DO_NOT_INHERIT" not in env.values()
    assert set(env).isdisjoint({"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN",
                              "GH_TOKEN", "COPILOT_GITHUB_TOKEN", "NODE_OPTIONS", "PYTHONPATH"})
    assert Path(env["CODEX_HOME"]).is_relative_to(tmp_path)


def test_codex_native_output_envelope_parser():
    page = {"ok": True, "content": "synthetic\noriginal", "complete": True}
    content = json.dumps([{"type": "text", "text": json.dumps(page)}])
    value = "Wall time: 0.01 seconds\nOutput:\n" + content
    assert page in list(dictionaries(value))
    assert list(dictionaries("random preamble " + content)) == []


def test_mock_anthropic_read_loop(tmp_path):
    with MockProvider("hook", tmp_path / "synthetic.json", "") as provider:
        body = {"tools": [{"name": "Read", "input_schema": {"type": "object"}}], "stream": False}
        request = urllib.request.Request(provider.url + "/v1/messages",
                                         data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            result = json.load(response)
        assert result["content"][0]["name"] == "Read"
        assert result["stop_reason"] == "tool_use"
        assert len(provider.requests) == 1


def test_mock_codex_deferred_discovery(tmp_path):
    with MockProvider("mcp", tmp_path / "fixture.json", "reference") as provider:
        discovery = provider.action({"tools": [{"type": "tool_search", "execution": "client"}]})
        assert discovery["kind"] == "tool_search"
        events = provider.responses(discovery, {"model": "mock"})
        assert events[-1][1]["response"]["output"][0]["type"] == "tool_search_call"
        action = provider.action({"input": [{"type": "tool_search_output", "tools": [
            {"type": "namespace", "name": "mcp__brainspace", "tools": [
                {"type": "function", "name": "brainspace_stats"}]}]}]})
        assert action["namespace"] == "mcp__brainspace"


def test_desktop_is_explicitly_blocked_without_invocation(tmp_path):
    result = run_scenario("codex-desktop", "mcp", tmp_path, sys.executable, tmp_path / "none", 1)
    assert result["status"] == "blocked"
    assert not result["runtime_acceptance_verified"]
    import jsonschema
    jsonschema.validate(result, json.loads((Path(__file__).parent / "result.schema.json").read_text()))


@pytest.mark.skipif(os.name != "nt", reason="Windows private-job cleanup proof")
@pytest.mark.parametrize("startup_delay", [0, 1.25], ids=["normal-startup", "startup-exceeds-timeout"])
def test_timeout_cleans_owned_descendant_processes(tmp_path, monkeypatch, startup_delay):
    import win32api
    import win32event
    import win32process
    env = clean_environment(tmp_path)
    start = tmp_path / "start"
    code = """
import subprocess, sys, time
from pathlib import Path
while not Path("start").exists():
    time.sleep(0.01)
time.sleep(float(sys.argv[1]))
p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
print(p.pid, flush=True)
Path(f"descendant-{p.pid}.ready").touch()
time.sleep(60)
"""
    communicate = subprocess.Popen.communicate
    handle = None
    pid = None
    was_running = False

    def communicate_after_startup(process, *args, **kwargs):
        nonlocal handle, pid, was_running
        if not start.exists():
            # invoke assigns the real private job before calling communicate.
            # Gate spawning on that assignment, then allow a bounded startup
            # budget before the unchanged one-second communicate timeout.
            start.touch()
            deadline = time.monotonic() + 15
            ready = None
            while time.monotonic() < deadline:
                ready = next(tmp_path.glob("descendant-*.ready"), None)
                if ready is not None:
                    break
                time.sleep(0.01)
            if ready is not None:
                # Carry the PID in the signal's name: no cross-process file
                # read or Windows rename/share-mode race is needed.
                pid = int(ready.stem.removeprefix("descendant-"))
                # QUERY_LIMITED_INFORMATION | SYNCHRONIZE; retain the exact
                # process handle across cleanup, avoiding PID-reuse ambiguity.
                handle = win32api.OpenProcess(0x1000 | 0x100000, False, pid)
                was_running = win32process.GetExitCodeProcess(handle) == 259
            # Even failed startup must pass through invoke's real timeout and
            # cleanup path before the readiness assertion reports diagnostics.
        return communicate(process, *args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "communicate", communicate_after_startup)
    try:
        result = invoke([sys.executable, "-X", "utf8", "-c", code, str(startup_delay)],
                        env, tmp_path, timeout=1)
        assert result["timed_out"], result
        assert result["process_tree_cleanup"] == "private-job-closed", result
        assert handle is not None, f"Descendant not ready within startup deadline: {result}"
        assert was_running, "Descendant must be alive before the real timeout"
        assert result["stdout"].strip() == str(pid), result
        assert win32event.WaitForSingleObject(handle, 5000) == win32event.WAIT_OBJECT_0
        assert win32process.GetExitCodeProcess(handle) != 259  # STILL_ACTIVE
    finally:
        if handle is not None:
            handle.Close()
