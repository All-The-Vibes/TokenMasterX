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
from hosts.runtime import copilot_hook_entry, hook_entry, runtime_entry, validate_runtime
from hosts.tokenizer import read_tokenizer

SKILL_DIR = Path(__file__).resolve().parent
TOKENOMICS_MARKER = "<!-- Installed by TokenMaster (brainspace_setup.py)"


def _fail(msg):
    print(f"[brainspace] ERROR: {msg}")
    return 1


def tokenomics_skill(home, python):
    """Copilot CLI personal skill for /tokenomics: the model runs tokenomics.py and shows its output unchanged."""
    from tokenomics import shell_command
    tool, command = shell_command(python, home / "token-master" / "tokenomics.py")
    return f"""---
name: tokenomics
description: TokenMaster tokenomics dashboard. Shows Copilot CLI token usage, GitHub's charges and the estimated TokenMaster savings by day, week, month or session, like ccusage. Use only when the user runs /tokenomics.
argument-hint: "[daily|weekly|monthly|session] [--since YYYYMMDD] [--until YYYYMMDD] [--project TEXT] [--only tokenmaster|stock] [--breakdown] [--full] [--json]"
disable-model-invocation: true
---

{TOKENOMICS_MARKER}; a reinstall rewrites this file and --uninstall removes it. -->

Run this one command with the {tool} tool. Append any arguments that the user typed after /tokenomics
(`--full` shows every column):

{command} --compact

Then reply with the command's complete output, unchanged, inside one ```text code block. Do not summarize,
reformat or recompute it, and add nothing else.
"""


def _wire_tokenomics_skill(home, python):
    """Install (python set) or remove (python None) the /tokenomics skill; never touch a skill TokenMaster did not write."""
    path = home / "skills" / "tokenomics" / "SKILL.md"
    owned = not path.exists() or TOKENOMICS_MARKER in path.read_text(encoding="utf-8", errors="replace")
    if not owned:
        print(f"[brainspace] kept {path}: it was not written by TokenMaster.")
        return None
    if python is None:
        if path.exists():
            path.unlink()
            try:
                path.parent.rmdir()
            except OSError:
                pass
        return None
    atomic_write(path, tokenomics_skill(home, python).encode("utf-8"))
    return str(path)


def _install_files(home):
    install_dir = home / "token-master"
    install_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(install_dir / "THIRD_PARTY_NOTICES.txt",
                 (SKILL_DIR.parents[1] / "THIRD_PARTY_NOTICES.txt").read_bytes())
    for name in ("brainspace_mcp.py", "brainspace_posttooluse.py", "brainspace_benchmark.py",
                 "brainspace_tools.py", "token_efficiency.py", "brainspace_native_mcp.py",
                 "brainspace_copilot_bridge.py", "tokenomics.py"):
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", nargs="?")  # retained legacy positional; no workspace edits
    parser.add_argument("--host", choices=HOSTS, default="")
    parser.add_argument("--python", default=sys.executable, help="pre-provisioned runtime interpreter")
    parser.add_argument("--tokenizer-file", help="copy an existing SHA-256-verified local vocabulary; never downloads")
    parser.add_argument("--copilot-output-hook", action=argparse.BooleanOptionalAction, default=None,
                        help="Copilot only, on by default: shape whole-file view results with "
                             "request-policy-v6 (--no-copilot-output-hook skips it); not a task-savings certificate")
    parser.add_argument("--brainspace-mcp", action=argparse.BooleanOptionalAction, default=None,
                        help="install the brainspace MCP server (compress/retrieve tools). Default: on, except for "
                             "Copilot, where live sessions never called its 5 tools and their definitions add about "
                             "500 tokens to every model call")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    try:
        host = resolve_host(args.host)
        home = host_home(host)
        brainspace_mcp = args.brainspace_mcp if args.brainspace_mcp is not None else host != "copilot"
        if args.copilot_output_hook and host != "copilot":
            raise ValueError("--copilot-output-hook requires --host copilot")
        copilot_hook = host == "copilot" and args.copilot_output_hook is not False and not args.uninstall
        preflight(host, include_hook=host == "claude" or host == "copilot"
                  and (copilot_hook or args.uninstall))
        if host == "copilot" and (copilot_hook or args.uninstall) \
                and copilot_hook_status(home) is None:
            raise ValueError("owned Copilot hook was edited; preserving hook and MCP configuration")
        if copilot_hook:
            settings = parse(read(home / "settings.json").decode("utf-8-sig"))
            if settings.get("disableAllHooks") is True:
                if args.copilot_output_hook:
                    raise ValueError("Copilot hooks are disabled in existing settings; preserving that choice")
                copilot_hook = False
                print("[brainspace] Copilot hooks are disabled in existing settings; skipping the output hook.")
        install_dir = home / "token-master"
        mcp_script = str(install_dir / "brainspace_mcp.py")
        hook_script = str(install_dir / "brainspace_posttooluse.py")
        tokenizer_path = install_dir / "tokenizer" / "cl100k_base.tiktoken"
        tokenomics = None
        if args.uninstall:
            wire_mcp(host, "brainspace", None)
            if host == "claude":
                wire_hook(home, None)
                environment(home / "settings.json", "BRAINSPACE_TOKENIZER_FILE", None)
            elif host == "copilot":
                wire_copilot_hook(home, None)
                _wire_tokenomics_skill(home, None)
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
            if brainspace_mcp:
                wire_mcp(host, "brainspace", entry)
            else:
                try:  # an earlier install's server costs tokens on every call; remove it if it is ours
                    wire_mcp(host, "brainspace", None)
                except ValueError as exc:
                    print(f"[brainspace] kept the existing brainspace MCP entry: {exc}")
            if host == "claude":
                wire_hook(home, command)
                environment(home / "settings.json", "BRAINSPACE_TOKENIZER_FILE", str(tokenizer_path))
            elif copilot_hook:
                wire_copilot_hook(home, copilot_hook_entry(python, hook_script, tokenizer_path))
            if host == "copilot":
                tokenomics = _wire_tokenomics_skill(home, python)
        print(f"[brainspace] {'uninstalled configuration' if args.uninstall else 'configured'}: {config_path(host)}")
        print(json.dumps({**capabilities(host),
                          "hook_installed": copilot_hook_status(home) if host == "copilot"
                              else host == "claude" and not args.uninstall,
                          "mcp_installed": brainspace_mcp and not args.uninstall,
                          "tokenomics_skill": tokenomics}, indent=2))
        print("Runtime acceptance is NOT verified by installation. Uninstall retains package files and data.")
        return 0
    except (OSError, ValueError) as exc:
        return _fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
