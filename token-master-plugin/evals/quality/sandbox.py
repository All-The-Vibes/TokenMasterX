"""Bounded WSL/Linux execution, never an unrestricted-host fallback.

Only sandbox_runner accepts trusted, held-out oracle plans. run_program returns
untrusted tool output and cannot produce an oracle attestation. The narrow AST
policy is deliberately not a general Python validator.
"""
import json
import os
from pathlib import Path
import subprocess

from .cases import digest, safe_path


def _sources(sources):
    if type(sources) is not dict or len(sources) > 256:
        raise ValueError("invalid sources")
    size = 0
    for path, source in sources.items():
        if type(path) is not str or len(path) > 512:
            raise ValueError("invalid source path size/type")
        safe_path(path)
        if type(source) is not str or len(source) > 524288:
            raise ValueError("invalid source size/type")
        encoded_size = len(source.encode())
        if encoded_size > 524288:
            raise ValueError("invalid source size/type")
        size += encoded_size
    if size > 4194304:
        raise ValueError("source budget exceeded")


def _launch(payload):
    helper = Path(__file__).with_name("sandbox_bootstrap.py").read_text(encoding="utf-8")
    # Only trusted helper text is an argv value. Model text travels as JSON stdin.
    command = ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "HOME=/nonexistent",
               "/usr/bin/timeout", "--signal=KILL", "18s",
               "/usr/bin/python3", "-I", "-S", "-c", helper]
    if os.name == "nt":
        windows = os.environ.get("SystemRoot", r"C:\Windows")
        command = [str(Path(windows) / "System32" / "wsl.exe"),
                   "-d", "Ubuntu", "--exec", *command]
        environment = {"SystemRoot": windows, "WINDIR": windows}
    else:
        environment = {}
    reply = dict(exit_code=None, stdout="", stderr="", timed_out=False,
                 boundary={"executed": None})
    try:
        result = subprocess.run(command, input=json.dumps(
            dict(payload, helper=helper), ensure_ascii=True).encode(),
            capture_output=True, timeout=60, env=environment)
        if result.returncode != 0:
            reply["stderr"] = result.stderr.decode("utf-8", "replace")[:4096]
            reply["boundary"]["error"] = "trusted Linux supervisor failed"
            reply["timed_out"] = result.returncode in (124, 137, -9)
            return reply
        if len(result.stdout) > 1048576:
            raise ValueError("supervisor serialization budget exceeded")
        output = json.loads(result.stdout)
        if type(output) is not dict or output.get("request_identity") != digest(payload):
            raise ValueError("invalid supervisor response")
        return output
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        reply["boundary"]["error"] = type(exc).__name__
        if isinstance(exc, OSError):
            reply["boundary"]["executed"] = False
        reply["timed_out"] = isinstance(exc, subprocess.TimeoutExpired)
        return reply


def sandbox_runner(plan):
    """oracle.sandbox_runner(plan) contract; caller must supply trusted test_code."""
    identity = plan.get("identity") if type(plan) is dict else None
    try:
        if type(plan) is not dict or set(plan) != {
            "identity", "case_identity", "oracle_identity", "sources",
            "test_code", "timeout_seconds",
        }:
            raise ValueError("invalid plan fields")
        if type(plan["sources"]) is not dict:
            raise ValueError("invalid sources")
        # Freeze caller containers; ONLY bounded type/byte/path checks run here.
        # Untrusted parsing and compilation belong to the limited Linux child.
        # All accepted leaf values are immutable strings/numbers.
        plan = dict(plan, sources=plan["sources"].copy())
        identity = plan["identity"]
        _sources(plan["sources"])
        if any(type(plan[k]) is not str or len(plan[k]) != 64 for k in
               ("identity", "case_identity", "oracle_identity")):
            raise ValueError("invalid identity fields")
        if type(plan["timeout_seconds"]) not in (int, float) or not 3 <= plan["timeout_seconds"] <= 5:
            raise ValueError("only 3-5 second candidate deadlines supported")
        if (type(plan["test_code"]) is not str or len(plan["test_code"]) > 65536
                or len(plan["test_code"].encode()) > 65536):
            raise ValueError("invalid trusted tests")
        if identity != digest({k: v for k, v in plan.items() if k != "identity"}):
            raise ValueError("plan identity mismatch")
    except (ValueError, TypeError, RecursionError) as exc:
        return dict(plan_identity=identity, exit_code=None, stdout="", stderr="",
                    timed_out=False, boundary={"executed": False, "error": str(exc)})
    reply = _launch(dict(mode="oracle", sources=plan["sources"], code=plan["test_code"],
                         seconds=plan["timeout_seconds"]))
    return dict(reply, plan_identity=identity)


def run_program(sources, code):
    """Ephemeral calculator; UNTRUSTED stdout/stderr, at most 64 KiB RAW each.

    Replacement decoding permits up to 192 KiB UTF-8 per stream. The trusted
    supervisor guards the complete ASCII-escaped JSON response at 1 MiB.
    """
    _sources(sources)
    if type(code) is not str or len(code) > 65536 or len(code.encode()) > 65536:
        raise ValueError("invalid program size/type")
    return dict(_launch(dict(mode="program", sources=sources, code=code, seconds=3)),
                output_trust="untrusted", purpose="calculator_not_oracle")
