"""Native Claude install/uninstall check with real user-source settings.

All homes are temporary. No observer substitutes for the installed hook and no
ambient tokenizer variable/cache supplies its vocabulary. One unrelated hook
records only fixture metadata. The provider is synthetic and loopback-only.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from mock_provider import MockProvider
from native_envelopes import (
    NATIVE_VERSION, _hash, _write, expected_native_result, prepare_case,
    provider_result, source_files, verify_sources,
)
from native_host_smoke import clean_environment, discover, invoke, provider_env, SKILL

sys.path.insert(0, str(SKILL))
from brainspace import tokens  # noqa: E402
from brainspace.token_ledger import _canonical  # noqa: E402

LOGGER = """import json, os, sys
from pathlib import Path
payload = json.load(sys.stdin)
record = {"phase": os.environ["TOKENMASTER_TEST_PHASE"],
          "call_id": payload["tool_use_id"],
          "sentinel": os.environ.get("TOKENMASTER_UNRELATED_SENTINEL"),
          "tokenizer": os.environ.get("BRAINSPACE_TOKENIZER_FILE")}
with Path(sys.argv[1]).open("a", encoding="utf-8") as output:
    output.write(json.dumps(record) + "\\n")
"""


def configuration_snapshot(home, output, label):
    settings = json.loads((home / "settings.json").read_text(encoding="utf-8"))
    mcp = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
    # Native CLI counters/preferences can change between CLI runs. Record
    # field fingerprints, not private/native preference values, and compare
    # exact objects immediately across the installer operation being tested.
    def fingerprint(value):
        return hashlib.sha256(_canonical(value).encode()).hexdigest()
    _write(output / (label + "-configuration.json"), {
        "settings_sha256": fingerprint(settings), "mcp_sha256": fingerprint(mcp),
        "settings_fields": {k: fingerprint(v) for k, v in settings.items()},
        "mcp_fields": {k: fingerprint(v) for k, v in mcp.items()},
    })
    return settings, mcp


def expected_uninstalled_settings(before, owned_group, token_path):
    value = copy.deepcopy(before)
    groups = value["hooks"]["PostToolUse"]
    found = [i for i, group in enumerate(groups) if _canonical(group) == _canonical(owned_group)]
    if len(found) != 1 or value["env"].get("BRAINSPACE_TOKENIZER_FILE") != token_path:
        raise ValueError("owned installation changed before uninstall")
    groups.pop(found[0])
    value["env"].pop("BRAINSPACE_TOKENIZER_FILE")
    return value


def expected_uninstalled_mcp(before, owned_entry):
    value = copy.deepcopy(before)
    if _canonical(value["mcpServers"].get("brainspace")) != _canonical(owned_entry):
        raise ValueError("owned MCP entry changed before uninstall")
    value["mcpServers"].pop("brainspace")
    return value


def installation_checks(before_settings, before_mcp, installed_settings, installed_mcp,
                        owned_group, token_path):
    """Only owned additions may differ immediately across installation."""
    return {
        "install_started_without_owned_entries":
            "BRAINSPACE_TOKENIZER_FILE" not in before_settings.get("env", {})
            and "brainspace" not in before_mcp.get("mcpServers", {}),
        "install_preserved_all_other_settings":
            _canonical(before_settings) == _canonical(
                expected_uninstalled_settings(installed_settings, owned_group, token_path)),
        "install_preserved_all_other_mcp_configuration":
            _canonical(before_mcp) == _canonical(
                expected_uninstalled_mcp(installed_mcp, installed_mcp["mcpServers"]["brainspace"])),
    }


def phase(label, root, case, env, command, python, output, timeout):
    destination = output / label
    destination.mkdir()
    process_env = env.copy()
    process_env["TOKENMASTER_TEST_PHASE"] = label
    if "BRAINSPACE_TOKENIZER_FILE" in process_env:
        raise ValueError("ambient tokenizer would mask installer configuration")
    with MockProvider("hook", case["fixture"], "") as provider:
        provider_env(process_env, provider, "claude")
        argv = command + [
            "-p", "Run the supplied synthetic read once.", "--model", "claude-sonnet-4-20250514",
            "--output-format", "stream-json", "--verbose", "--no-session-persistence",
            "--setting-sources", "user", "--settings", str(root / "empty-settings.json"),
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--tools", "Read", "--allowedTools", "Read",
            "--system-prompt", "Synthetic transport test; use the supplied local Read only.",
            "--debug-file", str(destination / "claude-debug.log"),
        ]
        result = invoke(argv, process_env, root / "workspace", timeout=timeout)
        requests, errors = list(provider.requests), list(provider.errors)
    _write(destination / "process.json", result)
    _write(destination / "provider-requests.json", requests)
    _write(destination / "mock-errors.json", errors)
    observed = provider_result(requests)
    return {
        "provider_result": observed,
        "result_reference_tokens": tokens.count_tokens(tokens.serialize(observed)),
        "clean_exit": result["exit_code"] == 0 and not result["timed_out"],
        "successful_tool_result": observed.get("is_error", False) is False,
        "mock_errors": errors,
    }


def run(output, python, vocabulary, timeout=60):
    command = discover("claude")
    if not command:
        raise ValueError("native Claude unavailable")
    with tempfile.TemporaryDirectory(prefix="tokenmaster-native-lifecycle-") as temporary:
        root = Path(temporary).resolve()
        if root.parent != Path(tempfile.gettempdir()).resolve() or not root.name.startswith("tokenmaster-native-lifecycle-"):
            raise RuntimeError("temporary-directory ownership check failed")
        env = clean_environment(root)
        workspace = root / "workspace"
        workspace.mkdir()
        case = prepare_case("read-json", workspace, python)
        before_files = {p.name: _hash(p) for p in workspace.iterdir() if p.is_file()}
        env.update(BRAINSPACE_WORKSPACE_ROOT=str(workspace), BRAINSPACE_SESSION_ID="native-lifecycle")
        home = Path(env["CLAUDE_CONFIG_DIR"])
        log, logger = root / "unrelated-hook.jsonl", root / "unrelated-hook.py"
        logger.write_text(LOGGER, encoding="utf-8")
        _write(root / "empty-settings.json", {})
        settings = {"env": {"TOKENMASTER_UNRELATED_SENTINEL": "preserve-me"},
                    "hooks": {"PostToolUse": [{"matcher": "Read", "hooks": [{
                        "type": "command", "command": python,
                        "args": ["-I", "-X", "utf8", str(logger), str(log)],
                    }]}]}}
        mcp = {"mcpServers": {"unrelated": {
            "command": python, "args": ["-I", "-c", "raise SystemExit(23)"],
        }}}
        _write(home / "settings.json", settings)
        _write(home / ".claude.json", mcp)
        version = invoke(command + ["--version"], env, workspace)
        if version["stdout"].strip() != NATIVE_VERSION:
            raise ValueError("native render version not qualified")
        executable_sha = _hash(Path(command[0]))
        baseline = phase("before-install", root, case, env, command, python, output, timeout)
        pre_settings, pre_mcp = configuration_snapshot(home, output, "before-install")
        setup = [python, "-X", "utf8", str(SKILL / "brainspace_setup.py"), "--host", "claude"]
        install = invoke(setup + ["--python", python, "--tokenizer-file", str(vocabulary)], env, workspace)
        _write(output / "install.json", install)
        if install["exit_code"] != 0 or install["timed_out"]:
            raise RuntimeError("isolated install failed")
        installed_settings, installed_mcp = configuration_snapshot(home, output, "immediately-installed")
        owned_groups = [g for g in installed_settings["hooks"]["PostToolUse"]
                        if all(_canonical(g) != _canonical(old) for old in pre_settings["hooks"]["PostToolUse"])]
        if len(owned_groups) != 1:
            raise ValueError("expected one separately owned hook group")
        installed = phase("installed", root, case, env, command, python, output, timeout)
        before_uninstall, mcp_before_uninstall = configuration_snapshot(home, output, "before-uninstall")
        uninstall = invoke(setup + ["--uninstall"], env, workspace)
        _write(output / "uninstall.json", uninstall)
        if uninstall["exit_code"] != 0 or uninstall["timed_out"]:
            raise RuntimeError("isolated uninstall failed")
        after_uninstall, mcp_after_uninstall = configuration_snapshot(home, output, "immediately-uninstalled")
        restored = phase("after-uninstall", root, case, env, command, python, output, timeout)
        configuration_snapshot(home, output, "after-restored-native-run")
        records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        _write(output / "unrelated-hook-observations.json", records)
        phases = {"before-install": baseline, "installed": installed, "after-uninstall": restored}
        token_path = str(home / "token-master/tokenizer/cl100k_base.tiktoken")
        by_phase = {entry["phase"]: entry for entry in records}
        expected_phases = set(phases)
        compact = json.dumps(json.loads(case["text"]), ensure_ascii=False, separators=(",", ":"))
        expected_installed_result = expected_native_result(
            case, baseline["provider_result"],
            {"file": {"content": case["text"], "startLine": 1}},
            {"file": {"content": compact, "startLine": 1}},
        )
        assertions = {
            **installation_checks(pre_settings, pre_mcp, installed_settings, installed_mcp,
                                  owned_groups[0], token_path),
            "native_phases_exited": all(p["clean_exit"] and not p["mock_errors"] for p in phases.values()),
            "all_native_reads_succeeded": all(p["successful_tool_result"] for p in phases.values()),
            "unrelated_hook_ran_once_per_phase": len(records) == 3 and set(by_phase) == expected_phases,
            "unrelated_hook_saw_intended_call_ids": all(r["call_id"] == "smoke_call_0" for r in records),
            "unrelated_setting_visible_in_every_phase": all(r["sentinel"] == "preserve-me" for r in records),
            "installed_tokenizer_setting_is_owned_copy": installed_settings.get("env", {}).get("BRAINSPACE_TOKENIZER_FILE") == token_path,
            "installed_settings_supplied_tokenizer_without_ambient_env":
                by_phase.get("before-install", {}).get("tokenizer") is None and
                by_phase.get("installed", {}).get("tokenizer") == token_path and
                by_phase.get("after-uninstall", {}).get("tokenizer") is None,
            "installed_hook_changed_native_result":
                _canonical(baseline["provider_result"]) != _canonical(installed["provider_result"]),
            "installed_native_result_matches_complete_expected_fixture":
                _canonical(installed["provider_result"]) == _canonical(expected_installed_result),
            "installed_hook_reduced_target_result_reference_tokens":
                installed["result_reference_tokens"] < baseline["result_reference_tokens"],
            "uninstall_restored_exact_native_result":
                _canonical(restored["provider_result"]) == _canonical(baseline["provider_result"]),
            "unrelated_settings_restored":
                _canonical(after_uninstall) == _canonical(
                    expected_uninstalled_settings(before_uninstall, owned_groups[0], token_path)),
            "unrelated_mcp_configuration_restored":
                _canonical(mcp_after_uninstall) == _canonical(
                    expected_uninstalled_mcp(mcp_before_uninstall, installed_mcp["mcpServers"]["brainspace"])),
            "uninstall_retained_package_files": (home / "token-master/brainspace_posttooluse.py").is_file(),
            "fixture_files_unchanged": before_files == {p.name: _hash(p) for p in workspace.iterdir() if p.is_file()},
            "native_executable_unchanged": _hash(Path(command[0])) == executable_sha,
        }
        report = {
            "schema_version": 1, "scope": "native Claude user-settings install lifecycle; mock transport only",
            "model_quality_verified": False, "version": version["stdout"].strip(),
            "native_executable_sha256": executable_sha, "assertions": assertions,
            "phases": phases, "no_ambient_tokenizer_in_child_environment": True,
            "real_host_configuration_changed": False,
            "installed_host_output_sha256": _hash(home / "token-master/brainspace/host_output.py"),
        }
    report["temporary_state_removed"] = not root.exists()
    passed = all(assertions.values()) and report["temporary_state_removed"]
    report.update(status="passed" if passed else "failed", runtime_acceptance_verified=passed)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--tokenizer-file", required=True, type=Path)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout", type=int, choices=range(10, 121), default=60)
    args = parser.parse_args()
    output, vocabulary = args.output.resolve(), args.tokenizer_file.resolve()
    if _hash(vocabulary) != tokens.VOCABULARY_SHA256:
        raise ValueError("verified local vocabulary required")
    output.mkdir(parents=True, exist_ok=False)
    # This is the measurement process only. clean_environment never copies it.
    os.environ["BRAINSPACE_TOKENIZER_FILE"] = str(vocabulary)
    tokens.count_tokens("offline reference readiness")
    source_hashes = {str(p): _hash(p) for p in source_files() + [Path(__file__)]}
    _write(output / "source-manifest.json", source_hashes)
    verify_sources(source_hashes)
    report = run(output, args.python, vocabulary, args.timeout)
    verify_sources(source_hashes)
    report["runner_sha256"] = _hash(Path(__file__))
    _write(output / "result.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "phases"}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
