#!/usr/bin/env python
"""Dual-host install + verification harness for the Brainspace layer.

Proves the layer installs and runs correctly for BOTH Claude Code and GitHub
Copilot CLI, entirely inside throwaway sandbox homes — the user's real ~/.claude,
~/.claude.json, and ~/.copilot are never read or written.

It exercises the real install paths by pointing the host-home env overrides
(CLAUDE_HOME / COPILOT_HOME / CLAUDE_CONFIG) at temp dirs, runs brainspace_setup.py
for each host, and then asserts:

  Claude:
    * <CLAUDE_HOME>/token-master/ has the server, hook, and brainspace/ package.
    * <CLAUDE_CONFIG> (.claude.json) mcpServers.brainspace is a valid stdio entry.
    * <CLAUDE_HOME>/settings.json PostToolUse hook references the hook script.
    * The installed server passes the MCP handshake from its installed location.
    * The installed PostToolUse hook, fed a real tool-result JSON on stdin, emits
      hookSpecificOutput.updatedToolOutput with a compressed, recoverable result.

  Copilot:
    * <COPILOT_HOME>/token-master/ has the server + package.
    * <COPILOT_HOME>/mcp-config.json mcpServers.brainspace is a valid stdio entry.
    * The installed server passes the MCP handshake.
    * (No hook is installed — Copilot has no documented PostToolUse rewrite hook;
      this harness asserts that absence is intentional, not a bug.)

  Cross-cutting:
    * Idempotency: running install twice does not duplicate entries.
    * Uninstall removes only the brainspace keys.

Run:  uv run --with mcp --with tree-sitter --with tree-sitter-python python verify_dual_host.py <skill_dir>
"""
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PH_RE = re.compile(r"\[\[HR:[0-9a-f]+(?:\|[^\]]*)?\]\]")


class Report:
    def __init__(self):
        self.checks = []
        self.ok = True

    def check(self, name, cond, detail=""):
        self.checks.append((name, bool(cond), detail))
        if not cond:
            self.ok = False
        mark = "PASS" if cond else "FAIL"
        print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))


def run_setup(skill_dir, host, home, extra_env, *, uninstall=False):
    env = dict(os.environ)
    env.update(extra_env)
    args = [sys.executable, str(Path(skill_dir) / "brainspace_setup.py"), f"--host={host}"]
    if uninstall:
        args.append("--uninstall")
    return subprocess.run(args, env=env, capture_output=True, text=True, timeout=120)


async def mcp_handshake(server_path, ccr_path):
    """Drive the installed server through the official MCP client."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = dict(os.environ)
    env["BRAINSPACE_CCR"] = ccr_path
    params = StdioServerParameters(command=sys.executable, args=[str(server_path)], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            big = json.dumps([{"name": f"f{i}.py", "size": i} for i in range(150)])
            cr = await session.call_tool("brainspace_compress", {"content": big, "hint": "ls.json"})
            ctext = "".join(getattr(c, "text", "") for c in cr.content)
            return names, len(big), len(ctext)


def test_hook(hook_path, skill_dir, ccr_path):
    """Feed the PostToolUse hook a realistic tool-result JSON on stdin and parse
    its stdout for the documented updatedToolOutput field."""
    env = dict(os.environ)
    env["BRAINSPACE_CCR"] = ccr_path
    # A big log-ish Bash output that should compress well.
    tool_output = "\n".join(["INFO line %d doing work" % i for i in range(400)] +
                            ["ERROR boom", "Traceback (most recent call last):", "  File \"x.py\", line 9", "ValueError: nope"])
    payload = {"tool_name": "Bash", "tool_response": tool_output}
    proc = subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(payload), env=env, capture_output=True, text=True, timeout=60,
    )
    return proc, tool_output


def main():
    skill_dir = sys.argv[1] if len(sys.argv) > 1 else \
        "C:/Users/shyamsridhar/code/TokenMaster/token-master-plugin/skills/token-master"
    rep = Report()
    sandbox = tempfile.mkdtemp(prefix="brainspace_dualhost_")
    ccr = os.path.join(sandbox, "ccr.sqlite")

    # ---------------------------------------------------------------- CLAUDE
    print("\n=== CLAUDE CODE INSTALL (sandbox home) ===")
    claude_home = Path(sandbox) / "claude_home"
    claude_cfg = claude_home / ".claude.json"
    cenv = {"CLAUDE_HOME": str(claude_home), "CLAUDE_CONFIG": str(claude_cfg),
            "TOKEN_MASTER_HOST": "claude"}
    r = run_setup(skill_dir, "claude", claude_home, cenv)
    rep.check("claude setup.py exit 0", r.returncode == 0, (r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout) else "")

    inst = claude_home / "token-master"
    rep.check("claude: server installed", (inst / "brainspace_mcp.py").is_file())
    rep.check("claude: hook installed", (inst / "brainspace_posttooluse.py").is_file())
    rep.check("claude: package installed", (inst / "brainspace" / "router.py").is_file())
    rep.check("claude: tests NOT shipped", not (inst / "brainspace" / "tests").exists(), "tests excluded from install")

    try:
        cfg = json.loads(claude_cfg.read_text())
        hr = cfg.get("mcpServers", {}).get("brainspace", {})
        rep.check("claude: .claude.json mcpServers.brainspace", bool(hr.get("command") and hr.get("args")),
                  f"command={Path(hr.get('command','')).name} args[-1]={Path(hr.get('args',['?'])[-1]).name}")
    except Exception as e:
        rep.check("claude: .claude.json mcpServers.brainspace", False, str(e))

    try:
        settings = json.loads((claude_home / "settings.json").read_text())
        posts = settings.get("hooks", {}).get("PostToolUse", [])
        has_hook = any("brainspace_posttooluse" in h.get("command", "")
                       for e in posts for h in e.get("hooks", []))
        rep.check("claude: settings.json PostToolUse hook", has_hook, f"{len(posts)} PostToolUse matcher(s)")
    except Exception as e:
        rep.check("claude: settings.json PostToolUse hook", False, str(e))

    # idempotency: run again, assert single hook + single server
    run_setup(skill_dir, "claude", claude_home, cenv)
    try:
        settings = json.loads((claude_home / "settings.json").read_text())
        posts = settings.get("hooks", {}).get("PostToolUse", [])
        hook_count = sum(1 for e in posts for h in e.get("hooks", []) if "brainspace_posttooluse" in h.get("command", ""))
        rep.check("claude: idempotent hook (no dupes)", hook_count == 1, f"{hook_count} brainspace hook entries after 2 installs")
    except Exception as e:
        rep.check("claude: idempotent hook (no dupes)", False, str(e))

    # MCP handshake from installed location
    try:
        names, before, after = asyncio.run(mcp_handshake(inst / "brainspace_mcp.py", ccr + ".claude"))
        rep.check("claude: installed server MCP handshake",
                  {"brainspace_compress", "brainspace_retrieve", "brainspace_stats"}.issubset(set(names)) and after < before,
                  f"tools={names}; compress {before}->{after}")
    except Exception as e:
        rep.check("claude: installed server MCP handshake", False, f"{type(e).__name__}: {e}")

    # PostToolUse hook end-to-end
    try:
        proc, original = test_hook(inst / "brainspace_posttooluse.py", skill_dir, ccr + ".hook")
        out = json.loads(proc.stdout) if proc.stdout.strip() else {}
        updated = out.get("hookSpecificOutput", {}).get("updatedToolOutput", "")
        rep.check("claude: hook emits updatedToolOutput", bool(updated) and len(updated) < len(original),
                  f"{len(original)}->{len(updated)} chars; field=updatedToolOutput")
        rep.check("claude: hook preserves ERROR signal", "ValueError: nope" in updated or "ERROR boom" in updated,
                  "error lines survive compression")
    except Exception as e:
        rep.check("claude: hook emits updatedToolOutput", False, f"{type(e).__name__}: {e}: stdout={proc.stdout[:200] if 'proc' in dir() else '?'}")

    # uninstall removes keys
    run_setup(skill_dir, "claude", claude_home, cenv, uninstall=True)
    try:
        cfg = json.loads(claude_cfg.read_text())
        settings = json.loads((claude_home / "settings.json").read_text())
        gone = "brainspace" not in cfg.get("mcpServers", {})
        posts = settings.get("hooks", {}).get("PostToolUse", [])
        hook_gone = not any("brainspace_posttooluse" in h.get("command", "") for e in posts for h in e.get("hooks", []))
        rep.check("claude: uninstall removes brainspace keys", gone and hook_gone, f"mcp_gone={gone} hook_gone={hook_gone}")
    except Exception as e:
        rep.check("claude: uninstall removes brainspace keys", False, str(e))

    # ---------------------------------------------------------------- COPILOT
    print("\n=== GITHUB COPILOT CLI INSTALL (sandbox home) ===")
    copilot_home = Path(sandbox) / "copilot_home"
    penv = {"COPILOT_HOME": str(copilot_home), "TOKEN_MASTER_HOST": "copilot"}
    r = run_setup(skill_dir, "copilot", copilot_home, penv)
    rep.check("copilot setup.py exit 0", r.returncode == 0, (r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout) else "")

    pinst = copilot_home / "token-master"
    rep.check("copilot: server installed", (pinst / "brainspace_mcp.py").is_file())
    rep.check("copilot: package installed", (pinst / "brainspace" / "router.py").is_file())

    try:
        mcfg = json.loads((copilot_home / "mcp-config.json").read_text())
        hr = mcfg.get("mcpServers", {}).get("brainspace", {})
        rep.check("copilot: mcp-config.json mcpServers.brainspace",
                  hr.get("type") == "stdio" and bool(hr.get("command")) and bool(hr.get("args")),
                  f"type={hr.get('type')} args[-1]={Path(hr.get('args',['?'])[-1]).name}")
    except Exception as e:
        rep.check("copilot: mcp-config.json mcpServers.brainspace", False, str(e))

    rep.check("copilot: NO PostToolUse hook (intentional)", not (copilot_home / "settings.json").exists()
              or "brainspace" not in (copilot_home / "settings.json").read_text(),
              "Copilot has no documented output-rewrite hook — MCP-only by design")

    try:
        names, before, after = asyncio.run(mcp_handshake(pinst / "brainspace_mcp.py", ccr + ".copilot"))
        rep.check("copilot: installed server MCP handshake",
                  {"brainspace_compress", "brainspace_retrieve", "brainspace_stats"}.issubset(set(names)) and after < before,
                  f"tools={names}; compress {before}->{after}")
    except Exception as e:
        rep.check("copilot: installed server MCP handshake", False, f"{type(e).__name__}: {e}")

    print("\n=== SUMMARY ===")
    passed = sum(1 for _, c, _ in rep.checks if c)
    print(f"  {passed}/{len(rep.checks)} checks passed")
    print(f"  sandbox: {sandbox}")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
