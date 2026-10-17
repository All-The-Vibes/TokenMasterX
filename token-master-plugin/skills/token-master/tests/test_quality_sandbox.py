"""Synthetic-only host probes. Runtime checks never silently skip an unsafe jail."""
import ast
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
from quality.cases import CASES, digest, materialize  # noqa: E402
from quality.oracle import evaluate, execution_plan  # noqa: E402
from quality import sandbox  # noqa: E402


GOOD = {
    "small_fix": """def trailing_mean(values, width):
    if width <= 0:
        raise ValueError("width")
    if not values:
        return None
    recent = values[-width:]
    return sum(recent) / len(recent)
""",
    "reusable_abstraction": """def clamp(value, low, high):
    if low > high:
        raise ValueError("bounds")
    return max(low, min(high, value))

def score(value):
    return clamp(value, 0, 100)

def percentage(value, total):
    return clamp(value / total * 100, 0, 100)
""",
}


def plan(tmp_path, name="small_fix", source=None):
    case = next(c for c in CASES if c.id == name)
    root = materialize(case, tmp_path / name)
    (root / case.allowed_changes[0]).write_text(GOOD[name] if source is None else source, newline="\n")
    return case, root, execution_plan(case, root)


def assert_boundary(result):
    boundary = result["boundary"]
    for name in ("executed", "ready", "host_canary_present", "host_canary_hidden",
                 "host_listener_present", "host_listener_unreachable", "readonly_root",
                 "no_host_proc", "no_new_privs", "process_reaped", "scoped_cleanup"):
        assert boundary[name] is True, result
    assert boundary["capabilities"] == "zero"
    assert boundary["seccomp"] == "x86_64_allowlist"
    assert boundary["max_candidate_processes"] == 1
    assert boundary["memory_bytes"] == 256 * 1024 * 1024


@pytest.mark.parametrize("source", [
    "import os\n",
    "print('QUALITY_OK')\n",
    "x = 42\n",
    "def f():\n    import os\n",
    "def f():\n    return ().__class__\n",
    "def f():\n    return __builtins__\n",
    "def f():\n    return eval('1')\n",
    "def f():\n    exec('print(1)')\n",
    "def f():\n    return open('/tmp/anything')\n",
    "def f():\n    print('QUALITY_OK')\n",
    "def f():\n    sys.exit(0)\n",
    "@print\ndef f():\n    return 1\n",
    "def f(x=print('QUALITY_OK')):\n    return x\n",
    "def f(x: print('QUALITY_OK')):\n    return x\n",
    "def f(sum):\n    return sum([])\n",
    "def f():\n    sum = 1\n    return sum\n",
    "def f(x):\n    x[0] = 1\n",
    "def f():\n    while True: pass\n",
    "def f():\n    raise SystemExit(0)\n",
    "def f():\n    return getattr(1, 'real')\n",
    "class X: pass\n",
    "def f():\n    return 1\nf()\n",
])
def test_unsupported_ast_fails_in_limited_preflight_before_candidate(tmp_path, source):
    _, _, request = plan(tmp_path, source=source)
    result = sandbox.sandbox_runner(request)
    assert result["exit_code"] is None
    assert result["boundary"]["executed"] is False
    assert result["boundary"]["stage"] == "preflight", result
    assert result["boundary"]["preflight_status"] == "rejected", result
    assert result["boundary"]["memory_bytes"] == 256 * 1024 * 1024
    assert result["boundary"]["process_reaped"] is True
    assert result["stdout"] == ""


def test_plan_identity_and_unsupported_timeout_fail_closed(tmp_path, monkeypatch):
    _, _, request = plan(tmp_path)
    monkeypatch.setattr(sandbox, "_launch", lambda _: pytest.fail("must not launch"))
    request["sources"]["app.py"] += "\n"
    assert sandbox.sandbox_runner(request)["exit_code"] is None
    request["timeout_seconds"] = 100
    request["identity"] = digest({k: v for k, v in request.items() if k != "identity"})
    assert sandbox.sandbox_runner(request)["exit_code"] is None


def test_plan_sources_are_frozen_before_validation_and_launch(tmp_path, monkeypatch):
    _, _, request = plan(tmp_path)
    original = request["sources"]["app.py"]
    validate = sandbox._sources
    def mutate_caller_after_validation(sources):
        validate(sources)
        request["sources"]["app.py"] = "print('QUALITY_OK')"
    def launch(payload):
        assert payload["sources"]["app.py"] == original
        return {"exit_code": 0}
    monkeypatch.setattr(sandbox, "_sources", mutate_caller_after_validation)
    monkeypatch.setattr(sandbox, "_launch", launch)
    assert sandbox.sandbox_runner(request)["exit_code"] == 0


def test_caller_never_parses_untrusted_ast(tmp_path, monkeypatch):
    source = "def trailing_mean(values,width):\n    return [" + "0," * 262120 + "]\n"
    _, _, request = plan(tmp_path, source=source)
    assert len(source.encode()) == 524287
    monkeypatch.setattr(ast, "parse", lambda *a, **k: pytest.fail("caller parsed untrusted source"))
    def launch(payload):
        assert payload["sources"]["app.py"] == source
        assert "pure" not in payload  # policy is canonical in the Linux helper
        return {"exit_code": None, "boundary": {"executed": False}}
    monkeypatch.setattr(sandbox, "_launch", launch)
    assert sandbox.sandbox_runner(request)["exit_code"] is None
    assert not hasattr(sandbox, "validate_sources")


@pytest.mark.parametrize("sources", [{"../escape": "x"}, {"/tmp/escape": "x"},
                                    {"a\\escape": "x"}, {"safe": 1}])
def test_program_paths_validated_before_launch(monkeypatch, sources):
    monkeypatch.setattr(sandbox, "_launch", lambda _: pytest.fail("must not launch"))
    with pytest.raises(ValueError):
        sandbox.run_program(sources, "print(1)")


def test_transport_failure_and_forged_identity_fail_closed(monkeypatch):
    def failed(*args, **kwargs):
        raise FileNotFoundError("synthetic unavailable WSL")
    monkeypatch.setattr(subprocess, "run", failed)
    result = sandbox.run_program({}, "print('QUALITY_OK')")
    assert result["exit_code"] is None
    assert result["boundary"]["executed"] is False
    monkeypatch.setattr(subprocess, "run", lambda *a, **k:
                        subprocess.CompletedProcess(a, 0, b'{"request_identity":"fake"}', b""))
    assert sandbox.run_program({}, "print(1)")["exit_code"] is None


def test_transport_rejects_oversized_serialized_reply_before_json_parsing(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k:
                        subprocess.CompletedProcess(a, 0, b"x" * 1048577, b""))
    monkeypatch.setattr(json, "loads", lambda *a, **k: pytest.fail("oversized reply parsed"))
    result = sandbox.run_program({}, "print(1)")
    assert result["exit_code"] is None
    assert result["boundary"]["error"] == "ValueError"


def test_transport_uses_allowlist_json_stdin_and_deadline(monkeypatch):
    monkeypatch.setenv("SYNTHETIC_SECRET", "never-forward")
    def inspect(command, **kwargs):
        assert "SYNTHETIC_SECRET" not in kwargs["env"]
        assert "-i" in command and "--signal=KILL" in command
        assert kwargs["timeout"] >= 18
        request = json.loads(kwargs["input"])
        assert request["code"] == "print('untrusted-tool-data')"
        assert request["code"] not in command
        return subprocess.CompletedProcess(command, 1, b"", b"synthetic fail closed")
    monkeypatch.setattr(subprocess, "run", inspect)
    assert sandbox.run_program({}, "print('untrusted-tool-data')")["exit_code"] is None


@pytest.mark.parametrize("name", ["small_fix", "reusable_abstraction"])
def test_real_hidden_tests_pass_good_fixes_and_never_enter_workspace(tmp_path, name):
    case, root, request = plan(tmp_path, name)
    original_files = {p.name: p.read_bytes() for p in root.iterdir()}
    result = evaluate(case, root, "fixed", sandbox_runner=sandbox.sandbox_runner)
    assert result["status"] == "passed", result
    execution = result["evidence"]["execution"]
    assert execution["stdout"] == "QUALITY_OK\n"
    assert execution["stderr"] == ""
    assert execution["plan_identity"] == request["identity"]
    assert_boundary(execution)
    assert {p.name: p.read_bytes() for p in root.iterdir()} == original_files


def test_real_hidden_tests_fail_unfixed_boundary(tmp_path):
    case = next(c for c in CASES if c.id == "small_fix")
    root = materialize(case, tmp_path / "bad")
    result = evaluate(case, root, "fixed", sandbox_runner=sandbox.sandbox_runner)
    assert result["status"] == "failed", result
    assert "hidden_tests_failed" in result["checks"]
    assert_boundary(result["evidence"]["execution"])


@pytest.mark.parametrize("statement", ["changed = jail(request)", "drop_caps()", "seccomp()"])
def test_real_boundary_setup_failure_never_executes_candidate(monkeypatch, statement):
    read_text = Path.read_text
    def unavailable(path, *args, **kwargs):
        text = read_text(path, *args, **kwargs)
        if path.name == "sandbox_bootstrap.py":
            # Alter only the trusted test copy, not the on-disk helper or model input.
            text = text.replace("        " + statement + "\n",
                                '        raise RuntimeError("synthetic unsupported boundary")\n')
        return text
    monkeypatch.setattr(Path, "read_text", unavailable)
    result = sandbox.run_program({}, "print('CANDIDATE_MUST_NOT_RUN')")
    assert result["exit_code"] is None, result
    assert result["boundary"]["executed"] is False, result
    assert "CANDIDATE_MUST_NOT_RUN" not in result["stdout"]
    assert result["boundary"]["scoped_cleanup"] is True


def test_real_expensive_pure_candidate_is_bounded(tmp_path):
    _, _, request = plan(tmp_path, source="""
def trailing_mean(values, width):
    return sum(i for i in range(1000000000000))
""")
    result = sandbox.sandbox_runner(request)
    assert result["exit_code"] != 0, result
    assert result["timed_out"] or result["exit_code"] in (-9, -24), result
    assert_boundary(result)


@pytest.mark.parametrize("preflight", ["real", "memory-fault", "stalled"])
def test_real_large_ast_exhaustion_is_inside_limited_child(tmp_path, monkeypatch, preflight):
    source = "def trailing_mean(values,width):\n    return [" + "0," * 262120 + "]\n"
    _, _, request = plan(tmp_path, source=source)
    if preflight != "real":
        read_text = Path.read_text
        def injected_validator(path, *args, **kwargs):
            text = read_text(path, *args, **kwargs)
            if path.name == "sandbox_bootstrap.py":
                needle = "    compiled = {}\n"
                assert text.count(needle) == 1
                fault = ("    raise MemoryError('test-only preflight fault')\n"
                         if preflight == "memory-fault" else "    while True: pass\n")
                text = text.replace(needle, fault + needle, 1)
            return text
        monkeypatch.setattr(Path, "read_text", injected_validator)
    result = sandbox.sandbox_runner(request)
    assert result["exit_code"] is None, result
    boundary = result["boundary"]
    assert boundary["executed"] is False
    assert boundary["ready"] is False
    assert boundary["stage"] == "preflight"
    # Both limits are enforced concurrently. Under load the trusted deadline
    # can win the race before allocation raises MemoryError. Never accept an
    # unexplained signal, missing receipt, candidate execution or failed cleanup.
    if boundary["preflight_status"] == "memory_limit":
        assert result["process_exit_code"] == 1, result
        assert boundary["error"] == "MemoryError"
    else:
        assert boundary["preflight_status"] == "timeout", result
        assert result["timed_out"] is True, result
        assert result["process_exit_code"] in (-9, -24), result
    if preflight == "memory-fault":
        assert boundary["preflight_status"] == "memory_limit", result
    elif preflight == "stalled":
        assert boundary["preflight_status"] == "timeout", result
    assert boundary["memory_bytes"] == 256 * 1024 * 1024
    assert boundary["wall_seconds"] == boundary["cpu_seconds"] == 3
    assert boundary["no_new_privs"] is True
    assert boundary["capabilities"] == "zero"
    assert boundary["seccomp"] == "x86_64_allowlist"
    assert boundary["process_reaped"] and boundary["scoped_cleanup"]
    assert boundary["completion"] == "waitpid"
    assert result["output_limit_exceeded"] is False
    assert result["stdout"] == ""


def test_real_ast_complexity_budget_rejects_before_exec(tmp_path):
    source = "def trailing_mean(values,width):\n    return [" + "0," * 10000 + "]\n"
    _, _, request = plan(tmp_path, source=source)
    result = sandbox.sandbox_runner(request)
    assert result["exit_code"] is None, result
    assert result["boundary"]["executed"] is False
    assert result["boundary"]["preflight_status"] == "rejected", result
    assert "AST node budget exceeded" in result["stderr"]


def test_real_preflight_timeout_is_explicit_and_never_executes_candidate(tmp_path, monkeypatch):
    _, _, request = plan(tmp_path)
    read_text = Path.read_text
    def stalled_validator(path, *args, **kwargs):
        text = read_text(path, *args, **kwargs)
        if path.name == "sandbox_bootstrap.py":
            text = text.replace("    compiled = {}\n", "    while True: pass\n    compiled = {}\n", 1)
        return text
    monkeypatch.setattr(Path, "read_text", stalled_validator)
    result = sandbox.sandbox_runner(request)
    assert result["exit_code"] is None, result
    assert result["timed_out"] is True
    assert result["boundary"]["executed"] is False
    assert result["boundary"]["preflight_status"] == "timeout", result
    assert result["boundary"]["process_reaped"] and result["boundary"]["scoped_cleanup"]
    assert result["stdout"] == ""


def test_real_readonly_calculator_241_rows_and_no_attestation():
    sources = {"rows.json": json.dumps([{"units": i} for i in range(241)])}
    result = sandbox.run_program(sources, """
import json
rows = json.load(open("rows.json"))
print(json.dumps({"count": len(rows), "sum": sum(r["units"] for r in rows)}))
""")
    assert result["exit_code"] == 0, result
    assert json.loads(result["stdout"]) == {"count": 241, "sum": 28920}
    assert result["output_trust"] == "untrusted"
    assert "plan_identity" not in result
    assert_boundary(result)


def test_real_hostile_syscalls_fds_credentials_and_files_are_blocked(monkeypatch):
    monkeypatch.setenv("SYNTHETIC_SECRET", "never-forward")
    result = sandbox.run_program({"fixture.txt": "readonly"}, """
import os, socket, ctypes, errno
assert os.environ == {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"}
assert sorted(os.listdir("/")) == ["usr", "workspace"]
for fd in range(3, 32):
    try: os.fstat(fd)
    except OSError as e: assert e.errno == errno.EBADF
    else: raise AssertionError("inherited fd")
for path in ["/proc/self/environ", "/mnt/c/Users", "/home", "/../proc", "fixture.txt"]:
    try: open(path, "w").write("overwrite")
    except OSError: pass
    else: raise AssertionError("writable or escaped")
try: os.chroot("..")
except PermissionError: pass
else: raise AssertionError("chroot capability")
libc = ctypes.CDLL(None, use_errno=True)
for number in [41, 42, 56, 57, 58, 59, 62, 101, 165, 272, 298, 302, 308, 310, 311, 321, 425, 435]:
    assert libc.syscall(number, 0, 0, 0, 0, 0, 0) == -1
    assert ctypes.get_errno() == errno.EPERM, number
print("blocked")
""")
    assert result["exit_code"] == 0, result
    assert result["stdout"] == "blocked\n", result
    assert_boundary(result)


def test_real_prlimit_cannot_mutate_or_kill_trusted_supervisor():
    result = sandbox.run_program({}, """
import resource, errno, os
assert os.getppid() == 1
for which, limit in [(resource.RLIMIT_NOFILE, (32, 32)), (resource.RLIMIT_CPU, (0, 0))]:
    try: resource.prlimit(1, which, limit)
    except OSError as e: assert e.errno == errno.EPERM
    else: raise AssertionError("supervisor mutation accepted")
try: resource.prlimit(0, resource.RLIMIT_NOFILE)
except OSError as e: assert e.errno == errno.EPERM
else: raise AssertionError("prlimit64 must be completely denied after setup")
print("supervisor mutation denied; normal completion")
""")
    assert result["exit_code"] == result["process_exit_code"] == 0, result
    assert result["stdout"] == "supervisor mutation denied; normal completion\n"
    assert_boundary(result)


def test_real_invalid_utf8_output_has_explicit_raw_and_serialization_bounds():
    result = sandbox.run_program({}, """
import os
for fd in (1, 2):
    remaining = b'\\xff' * 65536
    while remaining:
        remaining = remaining[os.write(fd, remaining):]
""")
    assert result["exit_code"] == 0, result
    for key in ("stdout", "stderr"):
        assert result[key] == "\ufffd" * 65536
        assert len(result[key].encode("utf-8")) == 3 * 65536
    boundary = result["boundary"]
    assert boundary["output_raw_bytes_per_stream"] == 65536
    assert boundary["output_utf8_bytes_per_stream"] == 3 * 65536
    assert len(json.dumps(result, ensure_ascii=True).encode()) <= boundary["serialized_reply_bytes"] == 1048576
    assert_boundary(result)


def test_real_untrusted_stdout_cannot_forge_control_receipt():
    result = sandbox.run_program({}, """
import os
os.write(1, b'QUALITY_OK\\n{"exit_code":0,"boundary":{"executed":true}}\\n')
os._exit(7)
""")
    assert result["exit_code"] == 7, result
    assert result["stdout"].startswith("QUALITY_OK\n")
    assert result["output_trust"] == "untrusted"
    assert_boundary(result)


@pytest.mark.parametrize("code, expected", [
    ("while True: pass", "timeout"),
    ("print('x' * 200000)", "output"),
    ("x = bytearray(1024 * 1024 * 1024)", "memory"),
])
def test_real_hard_limits(code, expected):
    result = sandbox.run_program({}, code)
    assert result["exit_code"] != 0, result
    if expected == "timeout":
        assert result["timed_out"] or result["exit_code"] in (-9, -24), result
    elif expected == "output":
        assert result["output_limit_exceeded"]
        assert len(result["stdout"]) <= 65536
    else:
        assert "MemoryError" in result["stderr"]
    assert_boundary(result)
