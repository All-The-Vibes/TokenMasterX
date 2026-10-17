"""No native CLI, provider/model calls, or user-profile changes in these tests."""
import io
import json
from pathlib import Path
import socket
import threading
import time
from types import SimpleNamespace

import pytest

from brainspace import native_copilot as native

WINDOWS_PROCESS = native._WindowsJobProcess


def line(event):
    return (json.dumps(event) + "\n").encode()


SKILLS = {"type": "session.skills_loaded", "data": {"skills": []}}
START = {"type": "tool.execution_start",
         "data": {"toolCallId": "ACTUAL-UPSTREAM-ID", "toolName": "view"}}


@pytest.fixture(autouse=True)
def no_external_effects(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("real native processes and sockets are forbidden")
    monkeypatch.setattr(native, "_WindowsJobProcess", denied)
    monkeypatch.setattr(native.subprocess, "Popen", denied)
    for method in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, method, denied)
    monkeypatch.setattr(socket, "create_connection", denied)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    import win32api
    import win32con
    import win32profile
    import win32security

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executable = tmp_path / "copilot.exe"
    executable.write_bytes(b"pinned fixture")
    python = tmp_path / "python.exe"
    python.write_bytes(b"trusted interpreter fixture")
    real_home = tmp_path / "real-home"
    real_home.mkdir()
    state = SimpleNamespace(processes=[], runtimes=[], bridges=[], order=[],
                            stdout=line(SKILLS) + line(START), stderr=b"",
                            version=b"GitHub Copilot CLI 1.0.95-0.\n",
                            process_live=False, pump_error=None, on_pump=None,
                            bootstrap_validator=None, validated=[],
                            profile_queries=[], profile_token_closed=False)
    monkeypatch.setattr(native.sys, "platform", "win32")
    monkeypatch.setattr(native.sys, "executable", str(python))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: real_home))
    token = SimpleNamespace(Close=lambda: setattr(state, "profile_token_closed", True))
    monkeypatch.setattr(win32api, "GetCurrentProcess", lambda: "current-process")

    def open_token(process, access):
        assert process == "current-process"
        assert access == win32con.TOKEN_QUERY
        return token

    def profile_directory(received_token):
        assert received_token is token
        state.profile_queries.append("GetUserProfileDirectory")
        return str(real_home)
    monkeypatch.setattr(win32security, "OpenProcessToken", open_token)
    monkeypatch.setattr(win32profile, "GetUserProfileDirectory", profile_directory)
    digest = native._digest
    monkeypatch.setattr(native, "_digest", lambda path:
                        native.COPILOT_SHA256 if path == executable else digest(path))

    class Runtime:
        def __init__(self, **kwargs):
            self.kwargs, self.events, self.finish_args = kwargs, [], None
            self.output = kwargs["output"]
            self.output.mkdir()
            state.runtimes.append(self)

        def observe_event(self, event):
            self.events.append(event)
            state.order.append("event")

        def validate_bootstrap_event(self, event):
            state.validated.append(event)
            if state.bootstrap_validator is not None:
                return state.bootstrap_validator(event)
            return event.get("data") == {"skills": []}

        def finish(self, **kwargs):
            assert all(process.settled and process.closed for process in state.processes)
            assert all(bridge.cancelled and bridge.closed for bridge in state.bridges)
            self.finish_args = kwargs
            state.order.append("finish")
            return {"complete": kwargs["native_exit_code"] == 0 and kwargs["native_io_complete"],
                    "preserved": "runtime-summary"}

    class Bridge:
        primary_token, control_token = "task-primary-secret", "task-control-secret"
        url = "http://127.0.0.1:54321"

        def __init__(self, runtime):
            self.runtime = runtime
            self.cancelled = self.closed = False
            state.bridges.append(self)

        def __enter__(self):
            return self

        def pump_once(self, timeout=0.05):
            assert threading.current_thread() is threading.main_thread()
            state.order.append("pump")
            if state.on_pump:
                state.on_pump(self)
            if state.pump_error is not None:
                raise state.pump_error
            time.sleep(0.001)

        def cancel_pending(self):
            self.cancelled = True
            state.order.append("cancel")

        def __exit__(self, *args):
            self.cancelled = self.closed = True
            state.order.append("bridge-close")

    class Process:
        def __init__(self, argv, *, env, cwd):
            self.argv, self.env, self.cwd = argv, env.copy(), cwd
            self.is_version = "--version" in argv
            self.stdout = io.BytesIO(state.version if self.is_version else state.stdout)
            self.stderr = io.BytesIO(b"" if self.is_version else state.stderr)
            self.live = not self.is_version and state.process_live
            self.settled = self.closed = self.terminated = False
            self.exit_code = 0
            if not self.is_version:
                config_path = Path(env["COPILOT_HOME"]) / "mcp-config.json"
                self.config = json.loads(config_path.read_text())
                self.settings = json.loads((config_path.parent / "settings.json").read_text())
            state.processes.append(self)

        def poll(self):
            return None if self.live else self.exit_code

        def terminate_tree(self):
            self.terminated, self.live = True, False
            self.exit_code = 1
            state.order.append("terminate")

        def settle(self):
            self.settled, self.live = True, False
            state.order.append("settle")

        def close(self, *, close_streams=True):
            self.closed = True
            state.order.append("process-close")
            self.stdout.close()
            self.stderr.close()

    monkeypatch.setattr(native, "_WindowsJobProcess", Process)
    monkeypatch.setattr(native, "NativeRuntime", Runtime)
    monkeypatch.setattr(native, "NativeBridge", Bridge)
    state.args = dict(workspace=workspace, session_id="test-session",
                      output=tmp_path / "output", base_url="http://127.0.0.1:9999/v1",
                      model="declared-model", prompt="Read only.", copilot_exe=executable,
                      allow_network=True)
    state.real_home = real_home
    state.Process, state.Runtime, state.Bridge = Process, Runtime, Bridge
    return state


def test_success_exact_contract_and_owned_homes(setup, monkeypatch):
    for key in ("NODE_OPTIONS", "PYTHONPATH", "OPENAI_API_KEY", "GITHUB_TOKEN",
                "COPILOT_PROVIDER_API_KEY", "TOKENMASTER_NATIVE_CONTROL_TOKEN",
                "HTTPS_PROXY", "BASH_ENV"):
        monkeypatch.setenv(key, "forbidden-inherited-secret")
    result = native.run_native_copilot(**setup.args)
    assert result["complete"] is True
    assert result["preserved"] == "runtime-summary"
    assert setup.runtimes[0].kwargs["source_contract"] == "native-full-view-v1"
    assert result["native_process"]["source_contract"] == "native-full-view-v1"
    assert len(setup.processes) == 2  # version probe + exactly one task
    process = setup.processes[1]
    assert process.argv[0] == str(setup.args["copilot_exe"])
    assert "--allow-all-tools" not in process.argv
    assert "--no-bash-env" in process.argv
    available = process.argv[process.argv.index("--available-tools") + 1:process.argv.index("--allow-tool")]
    assert available == list(native._TOOLS)
    assert "tokenmaster(retrieve_original)" in process.argv
    assert "tokenmaster(headroom_retrieve)" in process.argv
    assert process.env["COPILOT_PROVIDER_BASE_URL"] == "http://127.0.0.1:54321/v1"
    assert process.env["COPILOT_PROVIDER_WIRE_API"] == "responses"
    assert process.env["COPILOT_PROVIDER_TRANSPORT"] == "http"
    assert process.env["COPILOT_PROVIDER_TYPE"] == "openai"
    assert process.env["COPILOT_PROVIDER_MODEL_ID"] == setup.args["model"]
    assert process.env["COPILOT_PROVIDER_WIRE_MODEL"] == setup.args["model"]
    assert process.env["COPILOT_PROVIDER_API_KEY"] == "task-primary-secret"
    assert not any("forbidden-inherited-secret" in value for value in process.env.values())
    assert not {"NODE_OPTIONS", "PYTHONPATH", "OPENAI_API_KEY", "GITHUB_TOKEN", "BASH_ENV"} & process.env.keys()
    for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "COPILOT_HOME",
                "COPILOT_CACHE_HOME", "TEMP", "TMP"):
        assert Path(process.env[key]).is_relative_to(setup.args["output"])
        assert not Path(process.env[key]).is_relative_to(setup.args["workspace"])
    assert process.settings == {
        "ignoredSkillsLocations": [str(setup.real_home / name / "skills")
                                  for name in (".agents", ".claude", ".copilot", ".github")],
        "disableAllHooks": True, "dynamicRetrieval": {"skills": False},
    }
    entry = process.config["mcpServers"]["tokenmaster"]
    assert entry["command"] == native.sys.executable
    assert entry["args"][-1].endswith("brainspace_native_mcp.py")
    assert entry["env"] == {
        "TOKENMASTER_NATIVE_CONTROL_URL": "http://127.0.0.1:54321",
        "TOKENMASTER_NATIVE_CONTROL_TOKEN": "task-control-secret",
    }
    assert setup.runtimes[0].events == [SKILLS, START]
    assert result["native_process"]["verified_version"] == native.COPILOT_VERSION
    assert result["native_process"]["secret_config_removed"] is True
    assert not (Path(process.env["COPILOT_HOME"]) / "mcp-config.json").exists()
    assert not list(setup.real_home.iterdir())
    assert setup.order.index("settle") < setup.order.index("finish")


@pytest.mark.parametrize("contract", ["native-full-view-v1", "native-view-result-v2"])
def test_source_contract_forwarded_and_retained_without_secrets(setup, contract):
    result = native.run_native_copilot(**setup.args, source_contract=contract)
    assert result["complete"]
    assert setup.runtimes[0].kwargs["source_contract"] == contract
    receipt_text = (setup.args["output"] / "native-process.json").read_text()
    assert json.loads(receipt_text)["source_contract"] == contract
    assert result["native_process"]["source_contract"] == contract
    assert "task-primary-secret" not in receipt_text
    assert "task-control-secret" not in receipt_text
    assert len(setup.processes) == 2
    assert "--source-contract" not in setup.processes[1].argv  # Adapter option, not native flag.


@pytest.mark.parametrize("contract", [
    None, "", "native-view-result-v1", "native-full-view-v2",
    "native-view-result-v2 ", True, 2, [], {},
])
def test_invalid_source_contract_precedes_output_profile_and_launch(setup, monkeypatch, contract):
    monkeypatch.setattr(native, "_windows_profile_home",
                        lambda: pytest.fail("invalid contract must not query OS profile"))
    with pytest.raises(ValueError, match="source_contract"):
        native.run_native_copilot(**setup.args, source_contract=contract)
    assert not setup.runtimes and not setup.processes and not setup.bridges
    assert not setup.args["output"].exists()


def test_redirected_parent_homes_still_exclude_actual_os_profile(setup, monkeypatch, tmp_path):
    redirected = tmp_path / "redirected-parent-home"
    redirected.mkdir()
    monkeypatch.setenv("HOME", str(redirected))
    monkeypatch.setenv("USERPROFILE", str(redirected))

    def no_environment_home(cls):
        pytest.fail("OS profile resolution must not consult Path.home")
    monkeypatch.setattr(Path, "home", classmethod(no_environment_home))
    result = native.run_native_copilot(**setup.args)
    assert result["complete"]
    assert setup.profile_queries == ["GetUserProfileDirectory"]
    assert setup.profile_token_closed
    expected = [str(setup.real_home / name / "skills")
                for name in (".agents", ".claude", ".copilot", ".github")]
    assert setup.processes[1].settings["ignoredSkillsLocations"] == expected
    receipt = json.loads((setup.args["output"] / "native-process.json").read_text())
    assert receipt["settings"]["ignoredSkillsLocations"] == expected
    assert all(not Path(path).is_relative_to(redirected) for path in expected)
    assert not list(setup.real_home.iterdir())
    assert not list(redirected.iterdir())


@pytest.mark.parametrize("failure", ["token-open", "profile-query", "token-close"])
def test_os_profile_api_failure_stops_before_runtime_or_native_launch(setup, monkeypatch, failure):
    import win32profile
    import win32security

    def unavailable(*args):
        raise OSError("private profile API error detail")
    if failure == "token-open":
        monkeypatch.setattr(win32security, "OpenProcessToken", unavailable)
    elif failure == "profile-query":
        monkeypatch.setattr(win32profile, "GetUserProfileDirectory", unavailable)
    else:
        monkeypatch.setattr(win32security, "OpenProcessToken",
                            lambda *args: SimpleNamespace(Close=unavailable))
        monkeypatch.setattr(win32profile, "GetUserProfileDirectory", lambda _: str(setup.real_home))
    with pytest.raises(ValueError, match="^native_os_profile_resolution_failed$"):
        native.run_native_copilot(**setup.args)
    assert not setup.processes and not setup.runtimes
    assert not setup.args["output"].exists()
    if failure == "profile-query":
        assert setup.profile_token_closed


@pytest.mark.parametrize("value", ["", "relative/profile", "%USERPROFILE%", "\0", None, "missing"])
def test_invalid_os_profile_metadata_never_falls_back_to_environment(setup, monkeypatch, value):
    import win32profile

    if value == "missing":
        value = str(setup.real_home / "does-not-exist")
    monkeypatch.setattr(win32profile, "GetUserProfileDirectory", lambda _: value)
    with pytest.raises(ValueError, match="^native_os_profile_resolution_failed$"):
        native.run_native_copilot(**setup.args)
    assert setup.profile_token_closed
    assert not setup.processes and not setup.runtimes
    assert not setup.args["output"].exists()


@pytest.mark.parametrize("value", ["1.0.95-1", "1.0.950-0", "1.0.95-0.evil", "1.0.94"])
def test_exact_version_not_substring(setup, value):
    setup.version = f"GitHub Copilot CLI {value}.\n".encode()
    result = native.run_native_copilot(**setup.args)
    assert not result["complete"]
    assert len(setup.processes) == 1
    assert not setup.bridges
    assert setup.runtimes[0].finish_args["native_io_complete"] is False


def test_nonwindows_fails_before_runtime_or_process(setup, monkeypatch):
    monkeypatch.setattr(native.sys, "platform", "linux")
    with pytest.raises(ValueError, match="windows_only"):
        native.run_native_copilot(**setup.args)
    assert not setup.processes and not setup.runtimes


def test_wrong_hash_fails_before_runtime_or_process(setup, monkeypatch):
    monkeypatch.setattr(native, "_digest", lambda path: "wrong")
    with pytest.raises(ValueError, match="executable_hash"):
        native.run_native_copilot(**setup.args)
    assert not setup.processes and not setup.runtimes


@pytest.mark.parametrize("options", [
    {"allow_network": False}, {"native_timeout": 0}, {"native_timeout": float("inf")},
    {"version_timeout": float("nan")}, {"max_stdout_bytes": 0},
    {"max_stderr_bytes": True}, {"reasoning_effort": "unknown"}, {"prompt": "\0"},
])
def test_invalid_configuration_never_launches(setup, options):
    with pytest.raises(ValueError):
        native.run_native_copilot(**{**setup.args, **options})
    assert not setup.processes and not setup.runtimes


@pytest.mark.parametrize("path", ["copilot.exe", "copilot.cmd", "copilot.ps1"])
def test_no_shim_or_path_resolution(setup, path):
    args = {**setup.args, "copilot_exe": path}
    with pytest.raises(ValueError):
        native.run_native_copilot(**args)
    assert not setup.processes and not setup.runtimes


@pytest.mark.parametrize("location", ["workspace", "existing"])
def test_output_must_be_new_and_outside_workspace(setup, location):
    output = setup.args["workspace"] / "output" if location == "workspace" else setup.real_home
    with pytest.raises(ValueError, match="new_private_output"):
        native.run_native_copilot(**{**setup.args, "output": output})
    assert not setup.processes and not setup.runtimes


@pytest.mark.parametrize("data,error,options", [
    (line(SKILLS) + b"not json\n", "native_stdout_malformed", {}),
    (line(SKILLS) + b'{"type":"partial"}', "native_stdout_truncated", {}),
    (line(SKILLS) + b'{"type":"x","type":"y"}\n', "native_stdout_malformed", {}),
    (line(SKILLS) + b"\xff\n", "native_stdout_malformed", {}),
    (line(SKILLS) + b"x" * 201 + b"\n", "native_stdout_line_limit", {"max_stdout_line_bytes": 200}),
    (line(SKILLS) + line(START), "native_stdout_total_limit", {"max_stdout_bytes": len(line(SKILLS))}),
    (line(START), "native_skills_event_missing", {}),
])
def test_bounded_invalid_stream_is_incomplete_and_drained(setup, data, error, options):
    setup.stdout = data
    result = native.run_native_copilot(**setup.args, **options)
    assert not result["complete"]
    assert error in result["native_process"]["errors"]
    assert result["native_process"]["stdout_eof"] is True
    assert result["native_process"]["reader_threads_stopped"] is True
    assert setup.runtimes[0].finish_args["native_io_complete"] is False


def test_stderr_bound_and_both_credentials_redacted(setup):
    setup.stdout = line(SKILLS) + line({"type": "assistant.message", "data": {
        "content": "task-primary-secret task-control-secret"}})
    setup.stderr = b"task-primary-secret task-control-secret" * 10
    result = native.run_native_copilot(**setup.args, max_stderr_bytes=100)
    assert not result["complete"]
    assert "native_stderr_limit" in result["native_process"]["errors"]
    text = (setup.args["output"] / "native-process.json").read_text()
    assert "task-primary-secret" not in text and "task-control-secret" not in text
    assert "[REDACTED]" in text


@pytest.mark.parametrize("data", [{"skills": [{"name": "PRIVATE CATALOG"}]}, {}, {"skills": None}])
def test_skills_isolation_fails_closed_without_catalog_receipt(setup, data):
    setup.stdout = line({"type": "session.skills_loaded", "data": data}) + line(START)
    result = native.run_native_copilot(**setup.args)
    assert not result["complete"]
    assert "native_skills_rejected" in result["native_process"]["errors"]
    assert not setup.runtimes[0].events
    assert "PRIVATE CATALOG" not in json.dumps(result)


def stock_skills(cache_root):
    return {"type": "session.skills_loaded", "data": {"skills": [
        {"name": name, "commandName": name, "description": "Stock builtin fixture",
         "source": "builtin", "userInvocable": False, "enabled": True,
         "path": str(cache_root / "pkg" / "win32-x64" / native.COPILOT_VERSION
                     / "builtin" / name / "SKILL.md")}
        for name in ("customize-cloud-agent", "github-pr-media")
    ]}}


def test_production_capture_delegates_stock_skills_without_rewriting(setup):
    event = stock_skills(setup.args["output"] / "native-home" / "copilot-cache")
    setup.stdout = line(event) + line(START)
    setup.bootstrap_validator = lambda candidate: candidate == event
    result = native.run_native_copilot(**setup.args)
    assert result["complete"]
    assert setup.validated == [event]
    assert setup.runtimes[0].events == [event, START]
    assert result["native_process"]["stdout"] == setup.stdout.decode()


@pytest.mark.parametrize("case", ["accepted", "foreign-path", "personal-source", "extra-skill", "renamed"])
def test_capture_integrates_real_runtime_bootstrap_validator(setup, monkeypatch, case):
    from brainspace.native_runtime import NativeRuntime

    event = stock_skills(setup.args["output"] / "native-home" / "copilot-cache")
    skills = event["data"]["skills"]
    if case != "accepted":
        skills[0]["description"] = "PRIVATE CATALOG"
    if case == "foreign-path":
        skills[0]["path"] = str(setup.real_home / ".copilot" / "skills" / "SKILL.md")
    elif case == "personal-source":
        skills[0]["source"] = "personal"
    elif case == "extra-skill":
        skills.append({**skills[0], "name": "personal-extra"})
    elif case == "renamed":
        skills[0]["name"] = skills[0]["commandName"] = "arbitrary-builtin"
    setup.stdout = line(event) + line(START)
    monkeypatch.setattr(setup.Runtime, "validate_bootstrap_event", NativeRuntime.validate_bootstrap_event)
    result = native.run_native_copilot(**setup.args)
    if case == "accepted":
        assert result["complete"]
        assert setup.runtimes[0].events == [event, START]
        assert result["native_process"]["stdout"] == setup.stdout.decode()
    else:
        assert not result["complete"]
        assert not setup.runtimes[0].events
        assert "native_skills_rejected" in result["native_process"]["errors"]
        assert result["native_process"]["stdout"] == ""
        assert "PRIVATE CATALOG" not in (setup.args["output"] / "native-process.json").read_text()


@pytest.mark.parametrize("verdict", [False, None, 1, "true", {"valid": True}])
def test_validator_requires_true_and_rejected_catalog_never_persists(setup, verdict):
    event = {"type": "session.skills_loaded", "data": {"skills": [
        {"name": "PRIVATE CATALOG", "path": "private-home/secret/SKILL.md"}]}}
    setup.stdout = line(event) + line(START)
    setup.bootstrap_validator = lambda candidate: verdict
    result = native.run_native_copilot(**setup.args)
    assert not result["complete"]
    assert setup.validated == [event]
    assert not setup.runtimes[0].events
    assert result["native_process"]["stdout"] == ""
    assert "native_skills_rejected" in result["native_process"]["errors"]
    receipt = (setup.args["output"] / "native-process.json").read_text()
    assert "PRIVATE CATALOG" not in receipt and "private-home" not in receipt


def test_validator_exception_fails_closed_without_recording_private_message(setup):
    event = stock_skills(setup.args["output"] / "native-home" / "copilot-cache")
    setup.stdout = line(event) + line(START)

    def rejected(candidate):
        raise ValueError("PRIVATE CATALOG error detail")
    setup.bootstrap_validator = rejected
    result = native.run_native_copilot(**setup.args)
    assert not result["complete"]
    assert not setup.runtimes[0].events
    assert result["native_process"]["stdout"] == ""
    assert "native_skills_validator_ValueError" in result["native_process"]["errors"]
    assert "PRIVATE CATALOG" not in json.dumps(result)


@pytest.mark.parametrize("nonempty", [False, True])
def test_generic_capture_without_validator_remains_empty_only(tmp_path, nonempty):
    event = stock_skills(tmp_path / "cache") if nonempty else SKILLS
    observed = []
    capture = native._Capture(callback=observed.append, line_limit=4096,
                              stdout_limit=8192, stderr_limit=4096)
    capture._stdout(io.BytesIO(line(event) + line(START)))
    capture.join()
    assert capture.stdout_eof
    if nonempty:
        assert observed == []
        assert capture.stdout == b""
        assert "native_skills_not_empty" in capture.errors
    else:
        assert observed == [event, START]
        assert not capture.errors


def test_early_rejection_retains_delayed_exit_code_before_handle_close(setup, monkeypatch):
    setup.process_live = True
    setup.stdout = line({"type": "session.skills_loaded", "data": {"skills": [
        {"name": "PRIVATE CATALOG"}]}})
    original_poll = setup.Process.poll
    settled_polls = []

    def poll(self):
        if not self.is_version and self.settled:
            settled_polls.append(True)
            return None if len(settled_polls) == 1 else 73
        return original_poll(self)
    monkeypatch.setattr(setup.Process, "poll", poll)
    result = native.run_native_copilot(**setup.args)
    assert not result["complete"]
    assert result["native_process"]["exit_code"] == 73
    assert result["native_process"]["process_tree_settled"] is True
    assert setup.runtimes[0].finish_args["native_exit_code"] == 73


def test_observed_parent_exit_does_not_claim_failed_tree_settlement(setup, monkeypatch):
    setup.process_live = True
    setup.stdout = line({"type": "session.skills_loaded", "data": {"skills": [{"name": "private"}]}})
    settle = setup.Process.settle

    def broken(self):
        if not self.is_version:
            self.live, self.exit_code = False, 74
            raise OSError("tree descendants not settled")
        settle(self)
    monkeypatch.setattr(setup.Process, "settle", broken)
    result = native.run_native_copilot(**setup.args)
    assert not result["complete"]
    assert result["native_process"]["exit_code"] == 74
    assert result["native_process"]["process_tree_settled"] is False
    assert setup.runtimes[0].finish_args is None


@pytest.mark.parametrize("signaled", [False, True])
def test_job_empty_is_not_settled_until_parent_handle_signals(monkeypatch, signaled):
    process = WINDOWS_PROCESS.__new__(WINDOWS_PROCESS)
    process._job, process._settled = object(), False
    process._job_api = SimpleNamespace(
        JobObjectBasicAccountingInformation=1,
        QueryInformationJobObject=lambda *_: {"ActiveProcesses": 0},
        TerminateJobObject=lambda *_: None,
    )
    polls = []

    def poll():
        polls.append(True)
        return 75 if signaled and len(polls) == 2 else None
    process.poll = poll
    monkeypatch.setattr(native.time, "sleep", lambda _: None)
    if signaled:
        process.settle()
        assert len(polls) == 2
        assert process._settled
    else:
        with pytest.raises(RuntimeError, match="native_process_tree_not_settled"):
            process.settle(timeout=0)
        assert not process._settled


def test_watchdog_kills_native_process_while_main_pump_is_blocked(setup):
    setup.process_live = True

    def blocked(bridge):
        deadline = time.monotonic() + 2
        while not setup.processes[1].terminated and time.monotonic() < deadline:
            time.sleep(0.001)
        assert setup.processes[1].terminated
    setup.on_pump = blocked
    result = native.run_native_copilot(**setup.args, native_timeout=0.02)
    assert not result["complete"]
    assert result["native_process"]["timed_out"]
    assert "native_process_timeout" in result["native_process"]["errors"]
    assert setup.order.index("terminate") < setup.order.index("finish")


@pytest.mark.parametrize("error", [KeyboardInterrupt("original"), SystemExit(7), ValueError("secret")])
def test_error_settles_tree_and_preserves_original_interruption(setup, error):
    setup.process_live = True
    setup.pump_error = error
    if not isinstance(error, Exception):
        with pytest.raises(type(error)) as raised:
            native.run_native_copilot(**setup.args)
        assert raised.value is error
    else:
        assert not native.run_native_copilot(**setup.args)["complete"]
    assert setup.processes[1].settled
    assert setup.bridges[0].cancelled
    assert setup.runtimes[0].finish_args["native_io_complete"] is False
    assert setup.runtimes[0].events == [SKILLS, START]
    assert setup.order.index("cancel") < setup.order.index("finish")
    assert (setup.args["output"] / "native-process.json").is_file()


def test_config_content_tampering_is_preserved_and_failure_reported(setup):
    setup.process_live = True

    def tamper(bridge):
        config = Path(setup.processes[1].env["COPILOT_HOME"]) / "mcp-config.json"
        config.write_text("foreign replacement", encoding="utf-8")
        setup.processes[1].live = False
    setup.on_pump = tamper
    result = native.run_native_copilot(**setup.args)
    assert not result["complete"]
    assert result["native_process"]["secret_config_removed"] is False
    config = Path(setup.processes[1].env["COPILOT_HOME"]) / "mcp-config.json"
    assert config.read_text() == "foreign replacement"


def test_runtime_configuration_forwarded_explicitly(setup):
    policy, resources = object(), object()
    native.run_native_copilot(**setup.args, policy=policy, resources=resources,
                              timeout=12, event_wait_seconds=2, max_calls=4,
                              phase="learning", task_id="task", learning_run_id="run")
    kwargs = setup.runtimes[0].kwargs
    assert kwargs["policy"] is policy and kwargs["resources"] is resources
    assert kwargs["timeout"] == 12 and kwargs["max_calls"] == 4
    assert kwargs["phase"] == "learning" and kwargs["task_id"] == "task"
    assert kwargs["learning_run_id"] == "run" and kwargs["event_wait_seconds"] == 2


def test_partial_events_retained_when_callback_fails(setup, monkeypatch):
    def observe(self, event):
        self.events.append(event)
        if event == START:
            raise ValueError("private source must not be in error receipts")
    monkeypatch.setattr(setup.Runtime, "observe_event", observe)
    result = native.run_native_copilot(**setup.args)
    assert not result["complete"]
    assert setup.runtimes[0].events == [SKILLS, START]
    assert "native_stdout_callback_ValueError" in result["native_process"]["errors"]
    assert "private source" not in json.dumps(result)
    assert result["native_process"]["stdout_eof"] is True


def test_cleanup_interruption_does_not_replace_original(setup, monkeypatch):
    original = KeyboardInterrupt("original main interrupt")
    setup.process_live, setup.pump_error = True, original
    settle = setup.Process.settle
    failed = []

    def interrupted_once(self):
        if not self.is_version and not failed:
            failed.append(True)
            raise KeyboardInterrupt("secondary cleanup interrupt")
        settle(self)
    monkeypatch.setattr(setup.Process, "settle", interrupted_once)
    with pytest.raises(KeyboardInterrupt) as caught:
        native.run_native_copilot(**setup.args)
    assert caught.value is original
    assert setup.runtimes[0].finish_args is not None
    assert setup.processes[1].settled


def test_unsettled_process_tree_never_races_runtime_finish(setup, monkeypatch):
    settle = setup.Process.settle

    def broken(self):
        if not self.is_version:
            raise OSError("cannot prove tree termination")
        settle(self)
    monkeypatch.setattr(setup.Process, "settle", broken)
    result = native.run_native_copilot(**setup.args)
    assert not result["complete"]
    assert setup.runtimes[0].finish_args is None
    assert "native_finalization_deferred_unsettled_io" in result["native_process"]["errors"]


def test_finish_failure_does_not_replace_original_interrupt(setup, monkeypatch):
    original = KeyboardInterrupt("original")
    setup.process_live, setup.pump_error = True, original

    def fail(self, **kwargs):
        self.finish_args = kwargs
        raise RuntimeError("finalization failed")
    monkeypatch.setattr(setup.Runtime, "finish", fail)
    with pytest.raises(KeyboardInterrupt) as caught:
        native.run_native_copilot(**setup.args)
    assert caught.value is original
    receipt = json.loads((setup.args["output"] / "native-process.json").read_text())
    assert "native_finish_RuntimeError" in receipt["errors"]


def test_bridge_exit_failure_does_not_replace_original_interrupt(setup, monkeypatch):
    original = KeyboardInterrupt("original")
    setup.process_live, setup.pump_error = True, original
    exit_bridge = setup.Bridge.__exit__

    def fail(self, *args):
        exit_bridge(self, *args)
        raise RuntimeError("bridge cleanup failure")
    monkeypatch.setattr(setup.Bridge, "__exit__", fail)
    with pytest.raises(KeyboardInterrupt) as caught:
        native.run_native_copilot(**setup.args)
    assert caught.value is original
    assert setup.runtimes[0].finish_args["native_io_complete"] is False


def test_config_identity_replacement_is_never_deleted(tmp_path):
    path = tmp_path / "mcp-config.json"
    expected = b'{"task_owned":"secret"}'
    path.write_bytes(expected)
    stat = path.stat()
    identity = (stat.st_dev, stat.st_ino)
    path.rename(tmp_path / "original.json")
    path.write_bytes(expected)
    with pytest.raises(ValueError, match="ownership_changed"):
        native._remove_owned_config(path, identity, expected)
    assert path.read_bytes() == expected


def test_executable_change_after_version_never_launches_prompt(setup, monkeypatch):
    digest = native._digest
    calls = []

    def changed(path):
        if path == setup.args["copilot_exe"]:
            calls.append(path)
            if len(calls) > 1:
                return "changed-executable"
        return digest(path)
    monkeypatch.setattr(native, "_digest", changed)
    result = native.run_native_copilot(**setup.args)
    assert not result["complete"]
    assert len(setup.processes) == 1
    assert "native_executable_changed" in result["native_process"]["errors"]
    assert result["native_process"]["secret_config_removed"]


def test_pump_http_delay_after_native_exit_is_not_process_timeout(setup):
    setup.process_live = True

    def finish_native_then_delay(bridge):
        setup.processes[1].live = False
        time.sleep(0.06)
    setup.on_pump = finish_native_then_delay
    result = native.run_native_copilot(**setup.args, native_timeout=0.02)
    assert result["complete"]
    assert not result["native_process"]["timed_out"]


@pytest.mark.parametrize("failure", [None, "assign", "create"])
def test_windows_process_assigns_job_before_resume_and_never_runs_unowned(monkeypatch, failure):
    import msvcrt
    import pywintypes
    import win32api
    import win32con
    import win32event
    import win32file
    import win32job
    import win32pipe
    import win32process

    actions, created = [], []

    class Handle:
        def __init__(self, name):
            self.name, self.closed = name, False
            created.append(self)

        def Close(self):
            self.closed = True
            actions.append("close:" + self.name)

        def Detach(self):
            actions.append("detach:" + self.name)
            return 42

    monkeypatch.setattr(win32job, "CreateJobObject", lambda *_: Handle("job"))

    def query(job, information):
        if information == win32job.JobObjectExtendedLimitInformation:
            return {"BasicLimitInformation": {"LimitFlags": 0}}
        return {"ActiveProcesses": 0}
    monkeypatch.setattr(win32job, "QueryInformationJobObject", query)

    def limits(job, information, value):
        assert value["BasicLimitInformation"]["LimitFlags"] & win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        actions.append("kill-on-close")
    monkeypatch.setattr(win32job, "SetInformationJobObject", limits)
    monkeypatch.setattr(pywintypes, "SECURITY_ATTRIBUTES", SimpleNamespace)
    monkeypatch.setattr(win32pipe, "CreatePipe", lambda *args: (Handle("read"), Handle("write")))
    monkeypatch.setattr(win32api, "SetHandleInformation", lambda *args: actions.append("read-not-inherited"))
    monkeypatch.setattr(win32file, "CreateFile", lambda *args: Handle("stdin"))
    monkeypatch.setattr(win32process, "STARTUPINFO", SimpleNamespace)

    def create(executable, command, *_args):
        flags = _args[3]
        assert flags & win32con.CREATE_NO_WINDOW
        assert flags & win32con.CREATE_SUSPENDED
        assert flags & win32con.CREATE_UNICODE_ENVIRONMENT
        actions.append("create-suspended")
        if failure == "create":
            raise OSError("creation failed")
        return Handle("process"), Handle("thread"), 100, 101
    monkeypatch.setattr(win32process, "CreateProcess", create)

    def assign(*args):
        actions.append("assign")
        if failure == "assign":
            raise OSError("assignment failed")
    monkeypatch.setattr(win32job, "AssignProcessToJobObject", assign)
    monkeypatch.setattr(msvcrt, "open_osfhandle", lambda *args: 42)
    monkeypatch.setattr(native.os, "fdopen", lambda *args: io.BytesIO())
    monkeypatch.setattr(win32process, "ResumeThread", lambda *args: actions.append("resume"))
    monkeypatch.setattr(win32process, "TerminateProcess", lambda *args: actions.append("terminate"))
    monkeypatch.setattr(win32event, "WaitForSingleObject", lambda *args: win32event.WAIT_OBJECT_0)
    monkeypatch.setattr(win32process, "GetExitCodeProcess", lambda *args: 0)
    monkeypatch.setattr(win32job, "TerminateJobObject", lambda *args: actions.append("terminate-job"))
    if failure:
        with pytest.raises(OSError) as caught:
            WINDOWS_PROCESS(["C:\\owned\\copilot.exe"], env={}, cwd="C:\\owned")
        assert "resume" not in actions
        assert caught.value.native_process_receipt["process_tree_settled"]
        if failure == "assign":
            assert "terminate" in actions
    else:
        process = WINDOWS_PROCESS(["C:\\owned\\copilot.exe"], env={}, cwd="C:\\owned")
        assert actions.index("create-suspended") < actions.index("assign") < actions.index("resume")
        assert process.poll() == 0
        process.settle()
        process.close()
    assert all(handle.closed for handle in created if handle.name != "read")
