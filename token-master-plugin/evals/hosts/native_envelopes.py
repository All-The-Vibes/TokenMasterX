"""Paired native Claude envelope checks, using a synthetic loopback provider.

Runs only predetermined reads (including a fixed PowerShell read through Bash)
and a fixture MCP server. No real model, credentials, profile installation,
arbitrary shell program, policy promotion or whole-task savings claim.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shlex
import struct
import sys
import tempfile
import zlib

from mock_provider import MockProvider
from native_host_smoke import clean_environment, discover, invoke, provider_env, strings, SKILL, EVAL

sys.path.insert(0, str(SKILL))
from brainspace import tokens  # noqa: E402
from brainspace.token_ledger import _canonical  # noqa: E402

CASES = ("read-json", "grep-json", "bash-json", "powershell-json", "glob-paths",
         "read-image", "bash-error", "mcp-json", "mcp-mixed", "mcp-error", "mcp-structured")
TRANSFORMED = {"read-json", "grep-json", "bash-json", "powershell-json", "mcp-json"}
ERROR_MARKER = "TOKENMASTER_SYNTHETIC_ERROR"
NATIVE_VERSION = "2.1.289 (Claude Code)"
RENDER_CONTRACT = "claude-2.1.289-tool-result-v1"


def _png_chunk(kind, data):
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))


PNG = (b"\x89PNG\r\n\x1a\n"
       + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
       + _png_chunk(b"IDAT", zlib.compress(b"\x00\x00\xff\x00\xff"))
       + _png_chunk(b"IEND", b""))


def _write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False))


def _hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_files():
    files = [Path(__file__), EVAL / "mock_provider.py", EVAL / "hook_observer.py",
             EVAL / "envelope_fixture_mcp.py", EVAL / "native_host_smoke.py",
             SKILL / "brainspace_posttooluse.py", SKILL / "brainspace_setup.py"]
    files += list((SKILL / "brainspace").glob("*.py"))
    files += list((SKILL / "brainspace/compressors").glob("*.py"))
    files += list((SKILL / "hosts").glob("*.py"))
    return sorted(set(files))


def verify_sources(receipt):
    if any(_hash(Path(path)) != expected for path, expected in receipt.items()):
        raise RuntimeError("source_changed")


def prepare_case(name, workspace, python):
    if name not in CASES:
        raise ValueError("unknown native envelope case")
    fixture = workspace / "fixture Ω.json"
    image = workspace / "pixel Ω.png"
    text = json.dumps({"marker": "TOKENMASTER_NATIVE_ENVELOPE_" + name,
                       "rows": [{"index": i, "value": "synthetic item"} for i in range(25)]}, indent=4)
    fixture.write_text(text, encoding="utf-8")
    image.write_bytes(PNG)
    tool, arguments = "Read", {"file_path": str(fixture)}
    if name == "grep-json":
        tool, arguments = "Grep", {"pattern": "^", "path": str(fixture),
                                  "output_mode": "content", "-n": False}
    elif name == "glob-paths":
        for index in range(16):
            (workspace / f"TOKENMASTER_GLOB_{index:02d}.json").write_text("{}", encoding="utf-8")
        tool, arguments = "Glob", {"pattern": "*.json", "path": str(workspace)}
    elif name == "read-image":
        arguments = {"file_path": str(image)}
    elif name in ("bash-json", "bash-error"):
        # Isolated Python reads only this fixture; source is a fixed harness
        # literal, not model text. No script/profile loads from the workspace.
        program = ("import pathlib,sys;sys.stdout.buffer.write(pathlib.Path(sys.argv[1]).read_bytes());"
                   + (f"sys.stderr.write('{ERROR_MARKER}\\n');raise SystemExit(7)"
                      if name == "bash-error" else ""))
        argv = [str(Path(python).as_posix()), "-I", "-X", "utf8", "-c", program, fixture.as_posix()]
        tool, arguments = "Bash", {"command": shlex.join(argv), "timeout": 10000}
    elif name == "powershell-json":
        powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        if not powershell.is_file():
            raise ValueError("PowerShell executable unavailable")
        literal = str(fixture).replace("'", "''")
        script = ("[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
                  f"Get-Content -LiteralPath '{literal}' -Raw -Encoding UTF8")
        argv = [powershell.as_posix(), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script]
        tool, arguments = "Bash", {"command": shlex.join(argv), "timeout": 10000}
    elif name.startswith("mcp-"):
        method = {"mcp-json": "json_text", "mcp-mixed": "mixed_content", "mcp-error": "error_content",
                  "mcp-structured": "structured_content"}[name]
        tool, arguments = "mcp__fixture__" + method, {}
    return {"name": name, "tool": tool, "arguments": arguments, "fixture": fixture,
            "image": image, "text": text, "expect_transform": name in TRANSFORMED}


def provider_result(requests, call_id="smoke_call_0"):
    results = []
    for request in requests:
        for message in request["body"].get("messages", []):
            content = message.get("content")
            for block in content if isinstance(content, list) else []:
                if type(block) is dict and block.get("type") == "tool_result" and block.get("tool_use_id") == call_id:
                    results.append(block)
    if len(results) != 1:
        raise ValueError("exactly one provider-bound target tool result required")
    return results[0]


def leaf_paths(case, response):
    if case == "read-json":
        return [("file", "content")]
    if case == "grep-json":
        return [("content",)]
    if case in ("bash-json", "powershell-json"):
        return [("stdout",)]
    if case == "mcp-json":
        if isinstance(response, list):
            return [(i, "text") for i in range(len(response))]
        if isinstance(response, dict) and isinstance(response.get("content"), list):
            return [("content", i, "text") for i in range(len(response["content"]))]
    return []


def _leaf(value, path):
    for key in path:
        value = value[key]
    return value


def masked(value, paths):
    value = copy.deepcopy(value)
    for path in paths:
        node = value
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = None
    return value


def _same_json(left, right):
    return _canonical(left) == _canonical(right)


def _fixture_json(text, case):
    return type(text) is str and _same_json(json.loads(text), json.loads(case["text"]))


def _fixture_image(block):
    if type(block) is not dict:
        return False
    source = block.get("source", {})
    return (block.get("type") == "image" and source.get("type") == "base64"
            and source.get("media_type") == "image/png"
            and source.get("data") == base64.b64encode(PNG).decode("ascii"))


def native_shape_matches(case, payload, result):
    """Require the intended successful fixture, not matching unexpected errors."""
    name, response = case["name"], payload.get("tool_response")
    if name in ("bash-error", "mcp-error"):
        error = payload.get("error")
        if type(error) is not str or ERROR_MARKER not in error:
            return False
        if name == "bash-error":
            return error.startswith("Exit code 7\n") and case["text"] in error.replace("\r\n", "\n")
        expected = json.loads(case["text"])
        expected["error_marker"] = ERROR_MARKER
        return _same_json(json.loads(error), expected)
    if name == "read-json":
        file = response.get("file", {}) if type(response) is dict else {}
        return (response.get("type") == "text" and _fixture_json(file.get("content"), case)
                and type(file.get("startLine")) is int and file["startLine"] >= 1)
    if name == "grep-json":
        return type(response) is dict and response.get("mode") == "content" and _fixture_json(response.get("content"), case)
    if name in ("bash-json", "powershell-json"):
        return (type(response) is dict and _fixture_json(response.get("stdout"), case)
                and response.get("stderr") == "" and response.get("interrupted") is False
                and response.get("isImage") is False)
    if name == "glob-paths":
        expected = {"fixture Ω.json"} | {f"TOKENMASTER_GLOB_{i:02d}.json" for i in range(16)}
        found = response.get("filenames") if type(response) is dict else None
        return (type(found) is list and len(found) == len(expected) and set(found) == expected
                and type(response.get("numFiles")) is int and response["numFiles"] == len(expected)
                and response.get("truncated") is False and response.get("countIsComplete") is True
                and type(result.get("content")) is str and result["content"].startswith("\n".join(found)))
    if name == "mcp-structured":
        return (_fixture_json(response, case) and type(result.get("content")) is str
                and result["content"].startswith(response))
    if name == "mcp-json":
        return (type(response) is list and len(response) == 1 and response[0].get("type") == "text"
                and _fixture_json(response[0].get("text"), case))
    if name in ("read-image", "mcp-mixed"):
        content = result.get("content")
        provider_image = type(content) is list and sum(_fixture_image(b) for b in content) == 1
        if name == "read-image":
            file = response.get("file", {}) if type(response) is dict else {}
            return (provider_image and response.get("type") == "image" and file.get("type") == "image/png"
                    and file.get("base64") == base64.b64encode(PNG).decode("ascii"))
        return (provider_image and type(response) is list and len(response) == 2
                and response[0].get("type") == "text" and _fixture_json(response[0].get("text"), case)
                # Claude converts the MCP image into the provider image shape
                # before exposing this native hook; do not guess SDK fields.
                and _fixture_image(response[1]) and len(content) >= 2
                # Unlike the pure-text native rendering, mixed content keeps
                # the text block literal; this is the captured 2.1.289 shape.
                and content[0].get("type") == "text" and content[0].get("text") == response[0]["text"]
                and _fixture_image(content[1]))
    return False


def expected_native_result(case, before, original, replacement):
    """Pinned observed rendering, NOT recursive substring matching.

    Read numbers each line as ``number\\ttext``. Grep/Bash keep their text.
    Native MCP text blocks add one newline. Only these fixture text positions
    change; all native-added blocks, suffixes, status and other fields freeze.
    """
    result = copy.deepcopy(before)
    paths = leaf_paths(case["name"], original)
    old, new = ([_leaf(value, p) for p in paths] for value in (original, replacement))
    if case["name"] == "mcp-json":
        content = result.get("content")
        if type(content) is not list or len(content) < len(old):
            raise ValueError("native MCP block inventory mismatch")
        for index, (left, right) in enumerate(zip(old, new)):
            block = content[index]
            if block.get("type") != "text" or block.get("text") != left + "\n":
                raise ValueError("native MCP text rendering mismatch")
            block["text"] = right + "\n"
    else:
        if len(old) != 1 or type(result.get("content")) is not str:
            raise ValueError("native builtin text rendering mismatch")
        left, right = old[0], new[0]
        if case["name"] == "read-json":
            start = original["file"]["startLine"]
            left = "\n".join(f"{i}\t{line}" for i, line in enumerate(left.split("\n"), start))
            right = "\n".join(f"{i}\t{line}" for i, line in enumerate(right.split("\n"), start))
        if not result["content"].startswith(left):
            raise ValueError("native text prefix does not match fixture")
        result["content"] = right + result["content"][len(left):]
    return result


def assess(case, baseline, enabled, observations, process):
    """Correlate actual native output/observer/provider result, not schema text."""
    before, after = provider_result(baseline), provider_result(enabled)
    selected = [o for o in observations if o["input"].get("tool_name") == case["tool"]
                and o["input"].get("tool_use_id") == "smoke_call_0"]
    assertions = {
        "native_process_exited": process["exit_code"] == 0 and not process["timed_out"],
        "exact_target_hook_observed": len(selected) == 1,
    }
    before_count = tokens.count_tokens(tokens.serialize(before))
    after_count = tokens.count_tokens(tokens.serialize(after))
    detail = {"provider_result_before_reference_tokens": before_count,
              "provider_result_after_reference_tokens": after_count,
              "reference_count_scope": "one native tool-result JSON only, not whole-task or provider-native usage",
              "assertions": assertions}
    if len(selected) != 1:
        return detail
    observed = selected[0]
    assertions["hook_exited_cleanly"] = observed["exit_code"] == 0 and observed["stderr"] == ""
    assertions["before_provider_has_result"] = True
    error_case = case["name"] in ("bash-error", "mcp-error")
    assertions["expected_native_event"] = observed["input"].get("hook_event_name") == (
        "PostToolUseFailure" if error_case else "PostToolUse")
    assertions["expected_provider_status"] = (
        before.get("is_error", False) is error_case and after.get("is_error", False) is error_case)
    if not assertions["expected_native_event"] or not assertions["expected_provider_status"]:
        return detail
    try:
        assertions["intended_native_shape_and_fixture"] = native_shape_matches(case, observed["input"], before)
    except (ValueError, TypeError, KeyError, AttributeError):
        assertions["intended_native_shape_and_fixture"] = False
    if not assertions["intended_native_shape_and_fixture"]:
        return detail
    detail["native_render_contract"] = RENDER_CONTRACT
    if case["expect_transform"]:
        response = observed["input"].get("tool_response")
        paths = leaf_paths(case["name"], response)
        emitted = json.loads(observed["output"]) if observed["output"] else None
        specific = emitted.get("hookSpecificOutput") if type(emitted) is dict else None
        valid_envelope = (type(emitted) is dict and set(emitted) == {"hookSpecificOutput"}
                          and type(specific) is dict and set(specific) == {"hookEventName", "updatedToolOutput"}
                          and specific["hookEventName"] == "PostToolUse")
        assertions["override_uses_only_the_native_tool_result_channel"] = valid_envelope
        replacement = specific["updatedToolOutput"] if valid_envelope else None
        assertions["hook_emitted_replacement"] = replacement is not None and bool(paths)
        if replacement is not None and paths:
            old = [_leaf(response, path) for path in paths]
            new = [_leaf(replacement, path) for path in paths]
            assertions["eligible_text_changed"] = old != new
            assertions["json_values_preserved"] = all(
                _canonical(json.loads(a)) == _canonical(json.loads(b)) for a, b in zip(old, new))
            assertions["other_envelope_fields_unchanged"] = (
                _canonical(masked(response, paths)) == _canonical(masked(replacement, paths)))
            expected = expected_native_result(case, before, response, replacement)
            assertions["complete_provider_result_matches_expected_rendering"] = _same_json(expected, after)
            assertions["actual_provider_result_reference_reduced"] = after_count < before_count
    else:
        assertions["hook_returned_no_override"] = observed["output"] == ""
        assertions["provider_result_unchanged"] = _canonical(before) == _canonical(after)
        if case["name"] in ("bash-error", "mcp-error"):
            assertions["error_remains_error"] = after.get("is_error") is True
            assertions["error_marker_preserved"] = any(ERROR_MARKER in text for text in strings(after))
        if case["name"] in ("read-image", "mcp-mixed"):
            assertions["image_content_preserved"] = any(
                block.get("type") == "image" for block in after.get("content", []) if isinstance(block, dict))
    return detail


def execute_arm(case, root, env, command, python, installed, destination, enabled, timeout):
    marker = "enabled" if enabled else "baseline"
    arm_dir = destination / marker
    arm_dir.mkdir()
    observations = root / (marker + "-hook.jsonl")
    settings = root / (marker + "-settings.json")
    hook = {"type": "command", "command": python,
            "args": ["-X", "utf8", str(EVAL / "hook_observer.py"), str(observations),
                     str(installed / "brainspace_posttooluse.py"), python]}
    hooks = {event: [{"matcher": case["tool"], "hooks": [hook]}]
             for event in ("PostToolUse", "PostToolUseFailure")} if enabled else {}
    _write(settings, {"hooks": hooks})
    mcp = {}
    if case["name"].startswith("mcp-"):
        mcp["fixture"] = {
            "type": "stdio", "command": python,
            "args": ["-X", "utf8", str(EVAL / "envelope_fixture_mcp.py"),
                     "--fixture", str(case["fixture"]), "--image", str(case["image"])],
        }
    with MockProvider("envelope", case["fixture"], "", tool_steps=[(case["tool"], case["arguments"])]) as provider:
        arm_env = env.copy()
        provider_env(arm_env, provider, "claude")
        builtins = "" if mcp else case["tool"]
        argv = command + [
            "-p", "Run the supplied synthetic native-envelope read once.",
            "--model", "claude-sonnet-4-20250514", "--output-format", "stream-json",
            "--verbose", "--no-session-persistence", "--setting-sources", "",
            "--settings", str(settings), "--strict-mcp-config",
            "--mcp-config", json.dumps({"mcpServers": mcp}),
            "--allowedTools", case["tool"], "--tools", builtins,
            "--system-prompt", "Synthetic transport test. Use only the predetermined local read.",
            "--debug-file", str(arm_dir / "claude-debug.log"),
        ]
        process = invoke(argv, arm_env, root / "workspace", timeout=timeout)
        requests, actions, errors = list(provider.requests), provider.actions, provider.errors
    _write(arm_dir / "process.json", process)
    _write(arm_dir / "provider-requests.json", requests)
    records = ([json.loads(line) for line in observations.read_text(encoding="utf-8").splitlines()]
               if observations.exists() else [])
    _write(arm_dir / "hook-observations.json", records)
    _write(arm_dir / "mock-actions.json", {"actions": actions, "errors": errors})
    return requests, records, process, errors


def run_case(name, output, python, tokenizer, timeout=75):
    destination = output / name
    destination.mkdir()  # Never overwrite a previous case.
    report = {"case": name, "host": "claude", "status": "blocked",
              "evidence_kind": "mock-provider-transport-only", "model_quality_verified": False,
              "runtime_acceptance_verified": False, "assertions": {}}
    command = discover("claude")
    if not command:
        return dict(report, reason="native_claude_unavailable")
    with tempfile.TemporaryDirectory(prefix="tokenmaster-native-envelope-") as temp:
        root = Path(temp).resolve()
        if root.parent != Path(tempfile.gettempdir()).resolve() or not root.name.startswith("tokenmaster-native-envelope-"):
            raise RuntimeError("temporary-directory ownership check failed")
        env = clean_environment(root)
        workspace = root / "workspace"
        workspace.mkdir()
        case = prepare_case(name, workspace, python)
        fixture_hashes = {p.name: _hash(p) for p in workspace.iterdir() if p.is_file()}
        env.update(BRAINSPACE_WORKSPACE_ROOT=str(workspace), BRAINSPACE_SESSION_ID="native-envelope")
        install = invoke([python, "-X", "utf8", str(SKILL / "brainspace_setup.py"),
                          "--host", "claude", "--python", python, "--tokenizer-file", str(tokenizer)],
                         env, workspace, timeout=45)
        _write(destination / "install.json", install)
        if install["exit_code"] != 0 or install["timed_out"]:
            return dict(report, reason="isolated_install_failed")
        installed = Path(env["CLAUDE_CONFIG_DIR"]) / "token-master"
        env["BRAINSPACE_TOKENIZER_FILE"] = str(installed / "tokenizer/cl100k_base.tiktoken")
        report["version"] = invoke(command + ["--version"], env, workspace)["stdout"].strip()
        if report["version"] != NATIVE_VERSION:
            return dict(report, reason="native_render_version_not_qualified")
        report["native_executable_sha256"] = _hash(Path(command[0]))
        report["tested_source_sha256"] = {
            name: _hash(installed / name) for name in
            ("brainspace_posttooluse.py", "brainspace/host_output.py", "brainspace/router.py",
             "brainspace/tokens.py", "brainspace/ccr.py")}
        before = execute_arm(case, root, env, command, python, installed, destination, False, timeout)
        after = execute_arm(case, root, env, command, python, installed, destination, True, timeout)
        fixtures_unchanged = fixture_hashes == {p.name: _hash(p) for p in workspace.iterdir() if p.is_file()}
        report["tool"] = case["tool"]
        report["predetermined_arguments"] = case["arguments"]
        report["expected_disposition"] = "transformed" if case["expect_transform"] else "passthrough"
        report["baseline_exited"] = before[2]["exit_code"] == 0 and not before[2]["timed_out"]
        report["mock_errors"] = before[3] + after[3]
        try:
            report.update(assess(case, before[0], after[0], after[1], after[2]))
            report["assertions"]["fixture_files_unchanged"] = fixtures_unchanged
            report["assertions"]["native_executable_unchanged"] = _hash(Path(command[0])) == report["native_executable_sha256"]
            passed = (report["baseline_exited"] and not report["mock_errors"]
                      and all(report["assertions"].values()))
            report.update(status="passed" if passed else "failed", runtime_acceptance_verified=passed)
        except (ValueError, TypeError, KeyError, IndexError) as error:
            report.update(status="failed", reason="incomplete_or_unsupported_native_evidence",
                          error_type=type(error).__name__)
        report["temporary_configs_only"] = True
        report["real_auth_copied_or_supplied"] = False
        report["cleanup"] = "owned_temporary_directory_and_private_process_jobs"
    report["temporary_state_removed"] = not root.exists()
    if not report["temporary_state_removed"]:
        report.update(status="failed", runtime_acceptance_verified=False, reason="temporary_cleanup_incomplete")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--tokenizer-file", type=Path, required=True)
    parser.add_argument("--timeout", type=int, choices=range(10, 121), default=75)
    args = parser.parse_args()
    if len(set(args.cases)) != len(args.cases):
        parser.error("duplicate cases")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    vocabulary = args.tokenizer_file.resolve()
    if _hash(vocabulary) != tokens.VOCABULARY_SHA256:
        raise ValueError("verified local tokenizer required")
    os.environ["BRAINSPACE_TOKENIZER_FILE"] = str(vocabulary)
    tokens.count_tokens("offline tokenizer preflight")
    files = source_files()
    source_hashes = {str(path): _hash(path) for path in files}
    _write(output / "source-manifest.json", source_hashes)
    _write(output / "plan.json", {
        "schema_version": 1, "cases": args.cases, "host": "claude", "phase": "mock-transport-only",
        "model_quality_verified": False, "timeout_per_native_process": args.timeout,
        "python": sys.version, "mcp_version": importlib.metadata.version("mcp"),
        "tiktoken_version": importlib.metadata.version("tiktoken"),
        "vocabulary_sha256": _hash(vocabulary), "real_auth_supplied": False,
        "source_integrity": "checked before/after each case; not an OS-enforced immutable filesystem",
    })
    results = []
    for name in args.cases:
        verify_sources(source_hashes)
        result = run_case(name, output, args.python, vocabulary, args.timeout)
        try:
            verify_sources(source_hashes)
        except RuntimeError:
            result.update(status="failed", runtime_acceptance_verified=False, reason="source_changed_during_case")
        _write(output / name / "result.json", result)
        results.append(result)
        print(json.dumps(result, ensure_ascii=True), flush=True)
    _write(output / "summary.json", {
        "schema_version": 1, "scope": "native Claude tool-envelope transport only; no model quality or whole-task savings",
        "model_quality_verified": False, "results": results,
        "complete": all(r["status"] == "passed" for r in results),
        "fixture_source_sha256": _hash(EVAL / "envelope_fixture_mcp.py"),
        "runner_source_sha256": _hash(Path(__file__)),
        "mock_source_sha256": _hash(EVAL / "mock_provider.py"),
    })
    return 0 if all(r["status"] == "passed" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
