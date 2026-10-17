#!/usr/bin/env python
"""Install Brainspace into an explicit host home using an already provisioned runtime.

No dependency install or resolution occurs here or at server launch. Use --python
with an isolated environment containing the existing runtime dependencies.
Configuration support does not certify actual host output replacement.
"""
import argparse
import json
import sys
from pathlib import Path

from hosts import (HOSTS, capabilities, config_path, host_home, preflight,
                   resolve_host, wire_hook, wire_mcp, wire_copilot_hook, copilot_hook_status)
from hosts.config import atomic_write, environment, parse, read
from hosts.runtime import (DEPENDENCIES, copilot_hook_entry, hook_entry, runtime_entry,
                           validate_runtime)
from hosts.tokenizer import read_tokenizer

SKILL_DIR = Path(__file__).resolve().parent
RUN_WITH = DEPENDENCIES  # dependency inventory only; never uv --with launch arguments
_resolve_host = resolve_host
_host_home = host_home


def _claude_json_path():
    return config_path("claude")


def _fail(msg):
    print(f"[brainspace] ERROR: {msg}")
    return 1


def _install_files(home):
    install_dir = home / "token-master"
    install_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(install_dir / "THIRD_PARTY_NOTICES.txt",
                 (SKILL_DIR.parents[1] / "THIRD_PARTY_NOTICES.txt").read_bytes())
    for name in ("brainspace_mcp.py", "brainspace_posttooluse.py", "brainspace_benchmark.py",
                 "brainspace_tools.py", "token_efficiency.py", "brainspace_native_mcp.py"):
        atomic_write(install_dir / name, (SKILL_DIR / name).read_bytes())
    for name in ("__init__.py", "synthetic_efficiency.py"):
        atomic_write(install_dir / "evals" / name, (SKILL_DIR / "evals" / name).read_bytes())
    # Do not recursively remove an existing user directory. Refresh shipped files
    # only; installer never deletes runtime/data or other packages on uninstall.
    for source in (SKILL_DIR / "brainspace").rglob("*.py"):
        if "tests" not in source.relative_to(SKILL_DIR / "brainspace").parts:
            atomic_write(install_dir / "brainspace" / source.relative_to(SKILL_DIR / "brainspace"),
                         source.read_bytes())
    return install_dir


def _wire_claude_mcp(python, mcp_script, *, remove=False):
    return wire_mcp("claude", "brainspace", None if remove else runtime_entry(python, mcp_script))


def _wire_claude_hook(home, python, hook_script, *, remove=False):
    return wire_hook(home, None if remove else hook_entry(python, hook_script))


def _wire_copilot_mcp(home, python, mcp_script, *, remove=False):
    # Use the explicit home argument, including for isolated direct callers.
    from hosts.config import json_server
    entry = None if remove else {**runtime_entry(python, mcp_script), "type": "local", "tools": ["*"]}
    return json_server(home / "mcp-config.json", "brainspace", entry)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", nargs="?")  # retained legacy positional; no workspace edits
    parser.add_argument("--host", choices=HOSTS, default="")
    parser.add_argument("--python", default=sys.executable, help="pre-provisioned runtime interpreter")
    parser.add_argument("--tokenizer-file", help="copy an existing SHA-256-verified local vocabulary; never downloads")
    parser.add_argument("--copilot-output-hook", action="store_true",
                        help="Explicitly register the qualified native Copilot view-text contract; "
                             "not a full-profile or task-savings certificate")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    try:
        host = resolve_host(args.host)
        home = host_home(host)
        if args.copilot_output_hook and host != "copilot":
            raise ValueError("--copilot-output-hook requires --host copilot")
        preflight(host, include_hook=host == "claude" or host == "copilot"
                  and (args.copilot_output_hook or args.uninstall))
        if host == "copilot" and (args.copilot_output_hook or args.uninstall) \
                and copilot_hook_status(home) is None:
            raise ValueError("owned Copilot hook was edited; preserving hook and MCP configuration")
        if host == "copilot" and args.copilot_output_hook and not args.uninstall:
            settings = parse(read(home / "settings.json").decode("utf-8-sig"))
            if settings.get("disableAllHooks") is True:
                raise ValueError("Copilot hooks are disabled in existing settings; preserving that choice")
        install_dir = home / "token-master"
        mcp_script = str(install_dir / "brainspace_mcp.py")
        hook_script = str(install_dir / "brainspace_posttooluse.py")
        tokenizer_path = install_dir / "tokenizer" / "cl100k_base.tiktoken"
        if args.uninstall:
            wire_mcp(host, "brainspace", None)
            if host == "claude":
                wire_hook(home, None)
                environment(home / "settings.json", "BRAINSPACE_TOKENIZER_FILE", None)
            elif host == "copilot":
                wire_copilot_hook(home, None)
        else:
            receipt = validate_runtime(args.python)
            vocabulary, tokenizer_receipt = read_tokenizer(args.tokenizer_file, tokenizer_path)
            tokenizer_receipt["installed_path"] = str(tokenizer_path)
            receipt["tokenizer"] = tokenizer_receipt
            python = receipt["python"]
            command = hook_entry(python, hook_script) if host == "claude" else None
            _install_files(home)
            atomic_write(tokenizer_path, vocabulary)
            atomic_write(install_dir / "brainspace-runtime.json",
                         (json.dumps(receipt, indent=2) + "\n").encode("utf-8"))
            entry = runtime_entry(python, mcp_script)
            entry["env"]["BRAINSPACE_TOKENIZER_FILE"] = str(tokenizer_path)
            wire_mcp(host, "brainspace", entry)
            if host == "claude":
                wire_hook(home, command)
                environment(home / "settings.json", "BRAINSPACE_TOKENIZER_FILE", str(tokenizer_path))
            elif host == "copilot" and args.copilot_output_hook:
                wire_copilot_hook(home, copilot_hook_entry(python, hook_script, tokenizer_path))
        print(f"[brainspace] {'uninstalled configuration' if args.uninstall else 'configured'}: {config_path(host)}")
        print(json.dumps({**capabilities(host),
                          "hook_installed": copilot_hook_status(home) if host == "copilot"
                              else host == "claude" and not args.uninstall,
                          "mcp_installed": not args.uninstall}, indent=2))
        print("Runtime acceptance is NOT verified by installation. Uninstall retains package files and data.")
        return 0
    except (OSError, ValueError) as exc:
        return _fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
