"""Pinned Windows Copilot launcher; native execution remains client-owned.

No executable discovery, profile import, provider-key discovery, task retries or
generated-code execution happens here. The bridge is pumped on the calling
thread; only trusted native stdout is delivered from a reader thread.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any

from .native_runtime import NativeBridge, NativeRuntime
from .runtime_io import parse_json, safe_root
from .runtime_policy import RuntimePolicy
from .runtime_resources import RuntimeResources


COPILOT_SHA256 = "dfa6ee7844950fdf9c13dea8b3f89a12922cdb50886038ef2f5cff0be05ff9c7"
COPILOT_VERSION = "1.0.95-0"
QUALIFIED_COPILOT_VERSIONS = {
    "23e44448b2589401081aa90ee04201fa4b17e4e36d2ac2a10f57e5e1a317cc54": "1.0.98",
}
_TOOLS = ("view", "tokenmaster-retrieve_original", "tokenmaster-headroom_retrieve")
_PERMISSIONS = ("view", "tokenmaster(retrieve_original)", "tokenmaster(headroom_retrieve)")


def _digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, allow_nan=False, indent=2)
        handle.write("\n")


def _redact(text, secrets):
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def _windows_profile_home():
    """Resolve the process user's OS profile, never HOME/USERPROFILE guesses."""
    try:
        import win32api
        import win32con
        import win32profile
        import win32security

        token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
        try:
            profile = win32profile.GetUserProfileDirectory(token)
        finally:
            token.Close()
        if type(profile) is not str or not profile or "\0" in profile or not Path(profile).is_absolute():
            raise ValueError("invalid_os_profile_path")
        # Path metadata only: no profile enumeration, loading or content reads.
        root = safe_root(profile)
        if not root.is_dir():
            raise ValueError("missing_os_profile_directory")
        return root
    except Exception:
        raise ValueError("native_os_profile_resolution_failed") from None


def _environment(root, real_home):
    # PATH, auth, proxies, NODE_OPTIONS, PYTHONPATH and shell initialization
    # variables are deliberately NOT inherited. All commands are absolute.
    windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    env = {"SystemRoot": str(windows), "WINDIR": str(windows),
           "COMSPEC": str(windows / "System32" / "cmd.exe"),
           "PATH": str(windows / "System32"), "PATHEXT": ".EXE"}
    for key, directory in {
        "HOME": "home", "USERPROFILE": "home", "APPDATA": "appdata",
        "LOCALAPPDATA": "localappdata", "XDG_CONFIG_HOME": "xdg-config",
        "XDG_CACHE_HOME": "xdg-cache", "XDG_DATA_HOME": "xdg-data",
        "XDG_STATE_HOME": "xdg-state", "COPILOT_HOME": "copilot",
        "COPILOT_CACHE_HOME": "copilot-cache", "CLAUDE_CONFIG_DIR": "claude",
        "CLAUDE_HOME": "claude", "CODEX_HOME": "codex", "TEMP": "temp", "TMP": "temp",
    }.items():
        folder = root / directory
        folder.mkdir(exist_ok=True)
        env[key] = str(folder)
    env.update({
        "COPILOT_OFFLINE": "true", "COPILOT_AUTO_UPDATE": "false",
        "COPILOT_DISABLE_TERMINAL_TITLE": "true", "USE_TGREP": "false",
        "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
        "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1",
        "DO_NOT_TRACK": "1", "NO_COLOR": "1", "CI": "true",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(root / "empty-gitconfig"),
    })
    (root / "empty-gitconfig").write_text("", encoding="utf-8")
    settings = {
        "ignoredSkillsLocations": [
            str(real_home / name / "skills")
            for name in (".agents", ".claude", ".copilot", ".github")
        ],
        "disableAllHooks": True, "dynamicRetrieval": {"skills": False},
    }
    settings_path = Path(env["COPILOT_HOME"]) / "settings.json"
    _write_new(settings_path, settings)
    return env, {"settings": settings, "settings_sha256": _digest(settings_path)}


class _WindowsJobProcess:
    """Start suspended, assign private job, THEN resume (no unowned-child race)."""
    def __init__(self, argv, *, env, cwd):
        import msvcrt
        import pywintypes
        import win32api
        import win32con
        import win32file
        import win32job
        import win32pipe
        import win32process

        self._job_api, self._process_api = win32job, win32process
        self._job = self._handle = None
        self.stdout = self.stderr = None
        self._settled = False
        assigned = False
        handles: list[Any] = []
        try:
            self._job = win32job.CreateJobObject(None, "")
            limits = win32job.QueryInformationJobObject(
                self._job, win32job.JobObjectExtendedLimitInformation)
            limits["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            win32job.SetInformationJobObject(
                self._job, win32job.JobObjectExtendedLimitInformation, limits)
            security = pywintypes.SECURITY_ATTRIBUTES()
            security.bInheritHandle = True
            readers, writers = [], []
            for _ in range(2):
                reader, writer = win32pipe.CreatePipe(security, 0)
                handles.extend((reader, writer))
                win32api.SetHandleInformation(reader, win32con.HANDLE_FLAG_INHERIT, 0)
                readers.append(reader)
                writers.append(writer)
            stdin = win32file.CreateFile(
                "NUL", win32con.GENERIC_READ,
                win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE,
                security, win32con.OPEN_EXISTING, 0, None)
            handles.append(stdin)
            startup = win32process.STARTUPINFO()
            startup.dwFlags = win32con.STARTF_USESTDHANDLES
            startup.hStdInput = stdin
            startup.hStdOutput, startup.hStdError = writers
            self._handle, thread, _, _ = win32process.CreateProcess(
                str(argv[0]), subprocess.list2cmdline([str(arg) for arg in argv]),
                None, None, True,
                win32con.CREATE_NO_WINDOW | win32con.CREATE_SUSPENDED
                | win32con.CREATE_UNICODE_ENVIRONMENT,
                env, str(cwd), startup,
            )
            handles.append(thread)
            win32job.AssignProcessToJobObject(self._job, self._handle)
            assigned = True
            streams = []
            for reader in readers:
                descriptor = msvcrt.open_osfhandle(reader.Detach(), os.O_RDONLY | os.O_BINARY)
                handles.remove(reader)
                streams.append(os.fdopen(descriptor, "rb"))
                if len(streams) == 1:
                    self.stdout = streams[0]
                else:
                    self.stderr = streams[1]
            win32process.ResumeThread(thread)
        except BaseException as error:
            stopped = self._handle is None
            try:
                if assigned:
                    self.settle()
                    stopped = True
                elif self._handle is not None:
                    # Assignment failed; the process is still suspended.
                    win32process.TerminateProcess(self._handle, 1)
                    import win32event
                    stopped = win32event.WaitForSingleObject(self._handle, 10000) == win32event.WAIT_OBJECT_0
            except BaseException as cleanup_error:
                error.add_note("native_start_cleanup_failed:" + type(cleanup_error).__name__)
            finally:
                self.close()
            setattr(error, "native_process_receipt", {
                "process_tree_settled": stopped, "io_complete": False,
                "exit_code": None, "errors": ["native_process_start_failed"],
            })
            raise
        finally:
            for handle in handles:
                handle.Close()

    def poll(self):
        import win32event
        if win32event.WaitForSingleObject(self._handle, 0) == win32event.WAIT_TIMEOUT:
            return None
        return self._process_api.GetExitCodeProcess(self._handle)

    def terminate_tree(self):
        if self._job is not None:
            self._job_api.TerminateJobObject(self._job, 1)

    def settle(self, timeout=10):
        self.terminate_tree()
        deadline = time.monotonic() + timeout
        while self._job_api.QueryInformationJobObject(
            self._job, self._job_api.JobObjectBasicAccountingInformation
        )["ActiveProcesses"] or self.poll() is None:
            if time.monotonic() >= deadline:
                raise RuntimeError("native_process_tree_not_settled")
            time.sleep(0.01)
        self._settled = True

    def close(self, *, close_streams=True):
        if self._job is not None:
            self._job.Close()
            self._job = None
        if self._handle is not None:
            self._handle.Close()
            self._handle = None
        if close_streams:
            for stream in (self.stdout, self.stderr):
                if stream is not None:
                    stream.close()


class _Capture:
    def __init__(self, *, callback, line_limit, stdout_limit, stderr_limit,
                 bootstrap_validator=None):
        self.callback = callback
        # Production delegates the exact stock-builtin/path policy to the
        # runtime's shared validator. Generic callers remain empty-only.
        self.bootstrap_validator = bootstrap_validator
        self.line_limit, self.stdout_limit, self.stderr_limit = line_limit, stdout_limit, stderr_limit
        self.stdout, self.stderr = bytearray(), bytearray()
        self.errors = []
        self.failed = threading.Event()
        self.stdout_eof = self.stderr_eof = False
        self.skills_loaded = False
        self.threads = []

    def fail(self, code):
        if code not in self.errors:
            self.errors.append(code)
        self.failed.set()

    def start(self, process):
        for target, stream in ((self._stdout, process.stdout), (self._stderr, process.stderr)):
            thread = threading.Thread(target=target, args=(stream,), daemon=True)
            self.threads.append(thread)
            thread.start()

    def _stdout(self, stream):
        total = 0
        try:
            while True:
                line = stream.readline(self.line_limit + 1)
                if not line:
                    self.stdout_eof = True
                    return
                total += len(line)
                if len(line) > self.line_limit:
                    self.fail("native_stdout_line_limit")
                if total > self.stdout_limit:
                    self.fail("native_stdout_total_limit")
                if self.failed.is_set():
                    continue  # Drain to actual EOF after the main thread kills the job.
                if self.callback is None:
                    self.stdout.extend(line)
                    continue
                if not line.endswith(b"\n"):
                    self.stdout.extend(line)
                    self.fail("native_stdout_truncated")
                    continue
                try:
                    event = parse_json(line.decode("utf-8"))
                    if type(event) is not dict or type(event.get("type")) is not str:
                        raise ValueError("native_event_object_required")
                except (ValueError, UnicodeError, RecursionError):
                    self.stdout.extend(line)
                    self.fail("native_stdout_malformed")
                    continue
                if event["type"] == "session.skills_loaded":
                    try:
                        accepted = (event.get("data") == {"skills": []}
                                    if self.bootstrap_validator is None
                                    else self.bootstrap_validator(event) is True)
                    except BaseException as error:
                        self.fail("native_skills_validator_" + type(error).__name__)
                        continue
                    if not accepted:
                        # Do not persist the accidentally discovered private catalog.
                        self.fail("native_skills_not_empty" if self.bootstrap_validator is None
                                  else "native_skills_rejected")
                        continue
                    self.skills_loaded = True
                self.stdout.extend(line)
                try:
                    self.callback(event)  # Actual native IDs, never reconstructed IDs.
                except BaseException as error:
                    self.fail("native_stdout_callback_" + type(error).__name__)
        except BaseException as error:
            self.fail("native_stdout_reader_" + type(error).__name__)

    def _stderr(self, stream):
        try:
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    self.stderr_eof = True
                    return
                room = self.stderr_limit - len(self.stderr)
                self.stderr.extend(chunk[:room])
                if len(chunk) > room:
                    self.fail("native_stderr_limit")
        except BaseException as error:
            self.fail("native_stderr_reader_" + type(error).__name__)

    def join(self):
        deadline = time.monotonic() + 10
        for thread in self.threads:
            if thread.ident is not None:
                thread.join(max(0, deadline - time.monotonic()))
        if any(thread.is_alive() for thread in self.threads):
            self.fail("native_reader_not_settled")
        if self.callback is not None and not self.skills_loaded:
            self.fail("native_skills_event_missing")


def _execute(argv, *, env, cwd, timeout, capture, bridge=None):
    """The watchdog bounds the PROCESS, not interruptible main-thread HTTP work."""
    process = _WindowsJobProcess(argv, env=env, cwd=cwd)
    done, timed_out = threading.Event(), threading.Event()
    watchdog_errors = []
    interruption = None
    exit_code, settled = None, False
    queue_settled = bridge is None

    def watchdog():
        if not done.wait(timeout):
            try:
                if process.poll() is None:
                    timed_out.set()
                    process.terminate_tree()
            except BaseException as error:
                watchdog_errors.append(type(error).__name__)

    timer = threading.Thread(target=watchdog, daemon=True)
    try:
        capture.start(process)
        timer.start()
        while process.poll() is None and not capture.failed.is_set():
            if bridge is None:
                done.wait(0.01)
            else:
                bridge.pump_once(timeout=0.05)
        exit_code = process.poll()
    except BaseException as error:
        interruption = error
    finally:
        done.set()
        if timer.ident is not None:
            try:
                timer.join()
            except BaseException as error:
                interruption = interruption or error
                timer.join()
        # No finish/close of runtime is allowed until process and observers stop.
        for _ in range(2):  # Cleanup retry only; never a task/process restart.
            try:
                process.settle()
                settled = True
                if exit_code is None:
                    exit_code = process.poll()
                break
            except BaseException as error:
                interruption = interruption or error
                capture.fail("native_tree_cleanup_" + type(error).__name__)
        try:
            capture.join()
        except BaseException as error:
            interruption = interruption or error
            capture.fail("native_reader_cleanup_" + type(error).__name__)
            capture.join()
        if bridge is not None:
            try:
                bridge.cancel_pending()
                queue_settled = True
            except BaseException as error:
                interruption = interruption or error
                capture.fail("native_queue_cleanup_" + type(error).__name__)
        # Job accounting and pipe EOF can precede a signaled process handle.
        # Recheck before closing it, also when tree settlement failed: an
        # observed parent exit code never substitutes for whole-tree proof.
        if exit_code is None:
            try:
                exit_code = process.poll()
            except BaseException as error:
                interruption = interruption or error
                capture.fail("native_exit_code_" + type(error).__name__)
        try:
            process.close(close_streams=not any(thread.is_alive() for thread in capture.threads))
        except BaseException as error:
            interruption = interruption or error
            capture.fail("native_process_close_" + type(error).__name__)
    if timed_out.is_set():
        capture.fail("native_process_timeout")
    if watchdog_errors:
        capture.fail("native_watchdog_failed")
    receipt = {
        "exit_code": exit_code, "timed_out": timed_out.is_set(),
        "process_tree_settled": settled,
        "stdout_eof": capture.stdout_eof, "stderr_eof": capture.stderr_eof,
        "reader_threads_stopped": not any(thread.is_alive() for thread in capture.threads),
        "queue_settled": queue_settled,
        "errors": list(capture.errors),
        "io_complete": settled and queue_settled and capture.stdout_eof and capture.stderr_eof
        and not capture.errors and interruption is None,
    }
    if interruption is not None:
        # Preserve original KeyboardInterrupt/SystemExit, while making partial
        # stream and cleanup evidence available to the caller's finally block.
        setattr(interruption, "native_process_receipt", receipt)
        raise interruption
    return receipt


def _remove_owned_config(path, identity, expected):
    """Never unlink a replaced, linked, moved or content-modified config."""
    if safe_root(path) != path or path.is_symlink():
        raise ValueError("native_mcp_config_ownership_changed")
    stat = path.stat()
    if (stat.st_dev, stat.st_ino) != identity or path.read_bytes() != expected:
        raise ValueError("native_mcp_config_ownership_changed")
    path.unlink()


def run_native_copilot(
    *, workspace, session_id, output, base_url, model, prompt, copilot_exe,
    allow_network=False, policy: RuntimePolicy | None = None,
    resources: RuntimeResources | None = None, intent="conservative",
    max_calls=64, max_output_tokens=2048, max_request_bytes=524288,
    max_response_bytes=524288, timeout=45, reasoning_effort="low",
    event_wait_seconds=5, phase="deployment", learning_run_id=None, task_id=None,
    native_timeout=180, version_timeout=15, max_stdout_line_bytes=1048576,
    max_stdout_bytes=16777216, max_stderr_bytes=1048576,
    source_contract="native-full-view-v1",
):
    """Run once, returning runtime summary plus ``native_process`` evidence.

    ``timeout`` is the runtime HTTP timeout; ``native_timeout`` is a separate
    process watchdog, NOT a hard whole-runtime deadline. Preflight errors raise
    before runtime creation. Later ordinary failures return complete=False;
    interruptions are re-raised unchanged after partial receipts/finalization.
    Only Windows and the pinned absolute executable are qualified. No native
    process is started by importing this module.
    """
    from .native_events import validate_source_contract

    validate_source_contract(source_contract)
    if sys.platform != "win32":
        raise ValueError("native_copilot_windows_only")
    if allow_network is not True:
        raise ValueError("explicit_network_opt_in_required")
    if type(prompt) is not str or not prompt.strip() or "\0" in prompt:
        raise ValueError("native_prompt_required")
    if type(model) is not str or not model.strip() or "\0" in model:
        raise ValueError("native_model_required")
    if reasoning_effort not in ("none", "minimal", "low", "medium", "high", "xhigh", "max"):
        raise ValueError("invalid_native_reasoning_effort")
    for value in (native_timeout, version_timeout):
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError("invalid_native_process_timeout")
    for value in (max_stdout_line_bytes, max_stdout_bytes, max_stderr_bytes):
        if type(value) is not int or value < 1:
            raise ValueError("invalid_native_capture_bound")
    if not Path(copilot_exe).is_absolute():
        raise ValueError("absolute_native_executable_required")
    executable = safe_root(copilot_exe)
    if executable.suffix.lower() != ".exe" or not executable.is_file():
        raise ValueError("native_executable_required")
    exe_digest = _digest(executable)
    if exe_digest == COPILOT_SHA256:
        expected_version = COPILOT_VERSION
    elif exe_digest in QUALIFIED_COPILOT_VERSIONS:
        expected_version = QUALIFIED_COPILOT_VERSIONS[exe_digest]
    else:
        raise ValueError("unqualified_native_executable_hash")
    python = safe_root(sys.executable)
    mcp_script = Path(__file__).resolve().parents[1] / "brainspace_native_mcp.py"
    if python.suffix.lower() != ".exe" or not python.is_file() or not mcp_script.is_file():
        raise ValueError("installed_native_python_mcp_required")
    workspace, output = safe_root(workspace), safe_root(output)
    if not workspace.is_dir() or output.exists() or output.is_relative_to(workspace):
        raise ValueError("new_private_output_required")
    # Copilot can discover the OS profile despite redirected parent HOME values.
    # Fail before runtime creation or either native launch if it cannot be resolved.
    real_home = _windows_profile_home()
    python_digest = _digest(python)
    runtime = NativeRuntime(
        workspace=workspace, session_id=session_id, output=output, base_url=base_url,
        model=model, allow_network=allow_network, policy=policy, resources=resources,
        intent=intent, max_calls=max_calls, max_output_tokens=max_output_tokens,
        max_request_bytes=max_request_bytes, max_response_bytes=max_response_bytes,
        timeout=timeout, reasoning_effort=reasoning_effort,
        event_wait_seconds=event_wait_seconds, phase=phase,
        learning_run_id=learning_run_id, task_id=task_id,
        source_contract=source_contract,
    )
    if expected_version != COPILOT_VERSION:
        runtime._copilot_version = expected_version
    receipt = {"executable_sha256": exe_digest, "expected_version": expected_version,
               "python_sha256": python_digest, "source_contract": source_contract, "io_complete": False,
               "exit_code": None, "errors": []}
    capture = _Capture(callback=runtime.observe_event, line_limit=max_stdout_line_bytes,
                       stdout_limit=max_stdout_bytes, stderr_limit=max_stderr_bytes,
                       bootstrap_validator=runtime.validate_bootstrap_event)
    secret_values: tuple[str, ...] = ()
    config_path, config_identity, config_bytes = None, None, None
    interruption, summary = None, None
    try:
        home = output / "native-home"
        home.mkdir()
        env, settings_receipt = _environment(home, real_home)
        receipt.update(settings_receipt)
        version_capture = _Capture(callback=None, line_limit=8192, stdout_limit=32768, stderr_limit=32768)
        version = _execute(
            [str(executable), "--version", "--no-auto-update"], env=env, cwd=home,
            timeout=version_timeout, capture=version_capture,
        )
        version["stdout"] = version_capture.stdout.decode("utf-8", errors="replace")
        version["stderr"] = version_capture.stderr.decode("utf-8", errors="replace")
        receipt["version_probe"] = version
        if (not version["io_complete"] or version["exit_code"] != 0
                or version["stdout"].splitlines()[:1] != [f"GitHub Copilot CLI {expected_version}."]):
            raise ValueError("unqualified_native_version")
        receipt["verified_version"] = expected_version
        with NativeBridge(runtime) as bridge:
            secret_values = (bridge.primary_token, bridge.control_token)
            env.update({
                "COPILOT_PROVIDER_BASE_URL": bridge.url + "/v1",
                "COPILOT_PROVIDER_TYPE": "openai", "COPILOT_PROVIDER_WIRE_API": "responses",
                "COPILOT_PROVIDER_TRANSPORT": "http", "COPILOT_MODEL": model,
                "COPILOT_PROVIDER_MODEL_ID": model, "COPILOT_PROVIDER_WIRE_MODEL": model,
                "COPILOT_PROVIDER_MAX_OUTPUT_TOKENS": str(max_output_tokens),
                "COPILOT_PROVIDER_API_KEY": bridge.primary_token,
                "HTTP_PROXY": bridge.url, "HTTPS_PROXY": bridge.url,
                "ALL_PROXY": bridge.url, "NO_PROXY": "127.0.0.1,localhost,::1",
                "NODE_USE_ENV_PROXY": "1",
            })
            config_path = Path(env["COPILOT_HOME"]) / "mcp-config.json"
            _write_new(config_path, {"mcpServers": {"tokenmaster": {
                "type": "local", "command": str(python),
                "args": ["-E", "-s", "-B", "-X", "utf8", str(mcp_script)],
                "tools": ["retrieve_original", "headroom_retrieve"],
                "env": {"TOKENMASTER_NATIVE_CONTROL_URL": bridge.url,
                        "TOKENMASTER_NATIVE_CONTROL_TOKEN": bridge.control_token},
            }}})
            config_stat = config_path.stat()
            config_identity = (config_stat.st_dev, config_stat.st_ino)
            config_bytes = config_path.read_bytes()
            # Catch accidental executable replacement between version and prompt.
            if _digest(executable) != exe_digest:
                raise ValueError("native_executable_changed")
            if _digest(python) != python_digest:
                raise ValueError("native_python_changed")
            argv = [
                str(executable), "-p", prompt, "--model", model,
                "--reasoning-effort", reasoning_effort,
                "--available-tools", *_TOOLS, "--allow-tool", *_PERMISSIONS,
                "--output-format", "json", "--stream", "off", "--log-level", "none",
                "--no-custom-instructions", "--no-auto-update", "--no-ask-user",
                "--no-remote", "--no-remote-export", "--no-experimental",
                "--no-eager-powershell-resolution", "--no-bash-env",
                "--disable-builtin-mcps", "--disallow-temp-dir",
                "--secret-env-vars", "COPILOT_PROVIDER_API_KEY",
            ]
            try:
                receipt.update(_execute(
                    argv, env=env, cwd=workspace, timeout=native_timeout,
                    capture=capture, bridge=bridge,
                ))
            except BaseException as error:
                receipt.update(getattr(error, "native_process_receipt", {}))
                if not isinstance(error, Exception):
                    interruption = error
                raise
    except BaseException as error:
        receipt.update(getattr(error, "native_process_receipt", {}))
        receipt["errors"].append(type(error).__name__)
        if type(error) is ValueError and str(error) in (
            "unqualified_native_version", "native_executable_changed", "native_python_changed",
        ):
            receipt["errors"].append(str(error))
        receipt["io_complete"] = False
        if not isinstance(error, Exception):
            interruption = interruption or error
    finally:
        if config_identity is not None:
            try:
                _remove_owned_config(config_path, config_identity, config_bytes)
                receipt["secret_config_removed"] = True
            except BaseException as error:
                receipt["secret_config_removed"] = False
                receipt["errors"].append("native_config_cleanup_" + type(error).__name__)
                receipt["io_complete"] = False
                if not isinstance(error, Exception):
                    interruption = interruption or error
        receipt["stdout"] = _redact(capture.stdout.decode("utf-8", errors="replace"), secret_values)
        receipt["stderr"] = _redact(capture.stderr.decode("utf-8", errors="replace"), secret_values)
        if interruption is not None:
            receipt["interruption"] = type(interruption).__name__
        # An unproven stop is a bounded blocker, not permission to race a live
        # observer/operation with runtime cleanup. Normal/error EOFs finalize.
        settle_keys = ("process_tree_settled", "reader_threads_stopped", "queue_settled",
                       "stdout_eof", "stderr_eof")
        can_finish = all(record.get(key, True) for record in (
            receipt, receipt.get("version_probe", {})) for key in settle_keys)
        if not can_finish:
            receipt["errors"].append("native_finalization_deferred_unsettled_io")
            receipt["io_complete"] = False
        else:
            try:
                summary = runtime.finish(native_exit_code=receipt["exit_code"],
                                         native_io_complete=receipt["io_complete"])
            except BaseException as error:
                receipt["errors"].append("native_finish_" + type(error).__name__)
                receipt["io_complete"] = False
                if not isinstance(error, Exception):
                    interruption = interruption or error
        try:
            _write_new(output / "native-process.json", receipt)
        except BaseException as error:
            if interruption is None:
                raise
            interruption.add_note("native_process_receipt_write_failed:" + type(error).__name__)
    if interruption is not None:
        raise interruption
    result = dict(summary) if summary is not None else {}
    result["native_process"] = receipt
    result["complete"] = bool(result.get("complete")) and receipt["io_complete"]
    return result
