#!/usr/bin/env python
"""Build graph candidates and install an explicitly scoped host adapter.

Usage: python setup.py [REPO_ROOT] --host claude|codex|copilot --python PATH
       python setup.py --host HOST --uninstall

PATH must be an already provisioned runtime. Launch never resolves dependencies.
Optional codegraph installation requires --install-codegraph. Codex configuration
supports CLI/Desktop MCP only; no native routing agent or output hook is claimed.
"""
import argparse
import hashlib
import json
import time
import os
import shutil
import subprocess
import sys
from pathlib import Path

from hosts import (HOSTS, capabilities, config_path, host_home, preflight,
                   resolve_host, wire_mcp)
from hosts.config import atomic_write
from hosts.files import owned_file
from hosts.runtime import runtime_entry, validate_runtime
from graphify_mcp import stamp_graph

SKILL_DIR = Path(__file__).resolve().parent
GITIGNORE_LINE = ".token-master/"
GITIGNORE_CG_LINE = ".codegraph/"


_resolve_host = resolve_host
_host_home = host_home


def _claude_mcp_config_path():
    return config_path("claude")


def _git_root(start: Path) -> Path:
    """Return the git toplevel for `start`, or `start` if not in a git repo."""
    git = shutil.which("git")
    if not git:
        return start
    try:
        out = subprocess.run(
            [git, "rev-parse", "--show-toplevel"],
            cwd=str(start),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        root = out.stdout.strip()
        return Path(root).resolve() if root else start
    except (subprocess.CalledProcessError, OSError):
        return start


def _fail(msg: str) -> int:
    print(f"[token-master] ERROR: {msg}")
    return 1


def _ensure_gitignore_lines(gitignore: Path, lines: list) -> None:
    """Add any missing lines to .gitignore (best effort, idempotent)."""
    try:
        existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
        existing_lines = existing.splitlines()
        to_add = [ln for ln in lines if ln not in existing_lines]
        if not to_add:
            return
        with open(gitignore, "a", encoding="utf-8") as fh:
            if existing and not existing.endswith("\n"):
                fh.write("\n")
            for ln in to_add:
                fh.write(f"{ln}\n")
    except OSError as exc:
        print(f"[token-master] warning: could not update .gitignore ({exc})")


def _ensure_codegraph(home: Path, install: bool = False):
    """Locate or install the codegraph shim.

    Returns (node_path, shim_path) if codegraph is available, or (None, None)
    if node is missing or installation failed.  All failures are non-fatal.
    """
    node = shutil.which("node")
    if not node:
        print("[token-master] codegraph: `node` not found on PATH — skipping codegraph backend.")
        return None, None

    # 1. Explicit env override.
    env_shim = os.environ.get("TOKEN_MASTER_CG_SHIM", "")
    if env_shim:
        p = Path(env_shim)
        if p.is_file():
            return node, str(p)
        print(
            f"[token-master] warning: TOKEN_MASTER_CG_SHIM={env_shim!r} does not exist, "
            "falling back to local install."
        )

    # 2. Stable local install home.
    cg_home = home / "token-master" / "cgtool"
    shim_path = (
        cg_home / "node_modules" / "@colbymchenry" / "codegraph" / "npm-shim.js"
    )
    if shim_path.is_file():
        return node, str(shim_path)

    if not install:
        print("[token-master] codegraph: not installed; optional provisioning requires --install-codegraph.")
        return None, None

    # 3. Explicitly requested local npm install (never part of a server launch).
    npm = shutil.which("npm")
    if not npm:
        print("[token-master] codegraph: `npm` not found — skipping codegraph backend.")
        return None, None

    print(f"[token-master] codegraph: installing @colbymchenry/codegraph into {cg_home} ...")
    try:
        cg_home.mkdir(parents=True, exist_ok=True)
        pkg_json = cg_home / "package.json"
        if not pkg_json.is_file():
            subprocess.run(
                [npm, "init", "-y"],
                cwd=str(cg_home),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
        subprocess.run(
            [npm, "install", "@colbymchenry/codegraph"],
            cwd=str(cg_home),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        msg = getattr(exc, "output", None) or str(exc)
        print(
            f"[token-master] codegraph: npm install failed ({msg!r}) — "
            "skipping codegraph backend."
        )
        return None, None

    if shim_path.is_file():
        print("[token-master] codegraph: installed successfully.")
        return node, str(shim_path)

    print(
        "[token-master] codegraph: shim not found after install — skipping codegraph backend."
    )
    return None, None


def _codegraph_node_count(node_path: str, shim_path: str, repo: Path):
    """Return codegraph's indexed node count via ``status --json``, or None on failure.

    Used as a post-index sanity check: a codegraph DB that built but holds zero nodes
    cannot answer structural queries, so we should not advertise it as a backend.
    """
    try:
        out = subprocess.run(
            [node_path, shim_path, "status", "--json", "."],
            cwd=str(repo),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        data = json.loads(out.stdout)
        return int(data.get("nodeCount", 0))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, ValueError, TypeError):
        return None


def _calls_edge_count(graph_path: Path):
    """Return the count of 'calls' edges in a networkx node-link graph JSON.

    The graph uses the node-link serialisation: links are under ``"links"``, each
    link dict carries the relation in a ``"relation"`` or ``"type"`` key.
    Returns None if the file cannot be read or parsed.
    """
    try:
        with open(graph_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        links = data.get("links", [])
        return sum(
            1 for lnk in links
            if (lnk.get("relation") or lnk.get("type")) == "calls"
        )
    except (OSError, ValueError):
        return None


def _strip_codegraph_from_template(template: str) -> str:
    """Remove the codegraph mcp-server block and tool reference from the agent template.

    Handles both host formats:
      - Copilot: a quoted ``'codegraph/*'`` entry in the tools list plus an inline
        ``  codegraph:`` mcp-server block.
      - Claude: a bare ``codegraph`` token in a comma-separated tools string and no
        inline mcp-server block (the codegraph block detection is simply a no-op there).

    Operates line-by-line so it is robust to any surrounding whitespace changes.
    """
    lines = template.splitlines(keepends=True)
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip("\r\n")

        # Remove the codegraph entry from the top-level tools list (either format).
        if stripped.lstrip().startswith("tools:") and "codegraph" in stripped:
            new_stripped = (
                stripped
                # Copilot quoted-glob form.
                .replace("'codegraph/*', ", "")
                .replace(", 'codegraph/*'", "")
                .replace("'codegraph/*'", "")
                # Claude bare-token comma-string form.
                .replace("codegraph, ", "")
                .replace(", codegraph", "")
                .replace("codegraph", "")
            )
            eol = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            out.append(new_stripped + eol)
            i += 1
            continue

        # Detect start of the codegraph mcp-server block (exactly "  codegraph:").
        if stripped == "  codegraph:":
            # Consume this line and all subsequent more-deeply-indented lines.
            i += 1
            while i < len(lines):
                next_stripped = lines[i].rstrip("\r\n")
                # A non-empty line with fewer than 3 leading spaces is a sibling
                # server entry or end of the mcp-servers block — stop consuming.
                if next_stripped and not next_stripped.startswith("   "):
                    break
                i += 1
            continue

        out.append(line)
        i += 1
    return "".join(out)


def _write_claude_mcp_servers(python: str, mcp_script: str, node_path, shim_path) -> Path:
    entry = runtime_entry(python, mcp_script)
    entry["env"]["GRAPH_PATH"] = ".token-master/graph.json"
    path = wire_mcp("claude", "graphify-nav", entry)
    if node_path and shim_path:
        wire_mcp("claude", "codegraph", {"command": node_path,
                 "args": [shim_path, "serve", "--mcp", "-p", "."]})
    return path


def _supplier(executable):
    version = None
    try:
        result = subprocess.run([executable, "--version"], capture_output=True,
                                encoding="utf-8", errors="replace", timeout=15, check=True)
        version = result.stdout.strip()[:300] or None
    except (OSError, subprocess.SubprocessError):
        pass
    return {"name": "graphify", "version": version,
            "executable_sha256": hashlib.sha256(Path(executable).read_bytes()).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", nargs="?")
    parser.add_argument("--host", "-H", choices=HOSTS, default="")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--install-codegraph", action="store_true")
    args = parser.parse_args()
    host = _resolve_host(args.host)
    home = _host_home(host)
    preflight(host)
    if args.uninstall:
        wire_mcp(host, "graphify-nav", None)
        # Only remove a codegraph entry if this installer owns it.
        from hosts.config import parse, read
        receipt_path = config_path(host).with_name(config_path(host).name + ".token-master-owned.json")
        if "server:codegraph" in parse(read(receipt_path).decode("utf-8")):
            wire_mcp(host, "codegraph", None)
        if host != "codex":
            filename = "token-master.agent.md" if host == "copilot" else "token-master.md"
            owned_file(home / "agents" / filename, None)
        print("[token-master] removed owned host configuration; retained indexes, packages and user settings.")
        return 0
    receipt = validate_runtime(args.python, ("mcp",))
    python = receipt["python"]
    passed = Path(args.repo).resolve() if args.repo else Path.cwd()
    if not passed.is_dir():
        return _fail(f"repository path is not a directory: {passed}")
    repo = _git_root(passed)
    if repo != passed:
        print(f"[token-master] using git root: {repo}")
    print(f"[token-master] host: {host}")

    graphify = shutil.which("graphify")
    if not graphify:
        return _fail(
            "`graphify` not found on PATH. Install it with `uv tool install graphify` "
            "(https://github.com/safishamsi/graphify), then run /token-master again."
        )
    print(f"[token-master] indexing {repo} ...")
    build_started = time.monotonic()
    build_started_ns = time.time_ns()
    try:
        subprocess.run(
            [graphify, "update", "."],
            cwd=str(repo),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        return _fail(f"`graphify update` failed: {getattr(exc, 'output', None) or exc}")

    src_graph = repo / "graphify-out" / "graph.json"
    if not src_graph.is_file():
        return _fail(f"expected graph not produced at {src_graph}")

    code_nodes = _code_node_count(src_graph)
    if not code_nodes:
        return _fail(
            "graphify indexed no code symbols — this repo may have no supported source files. "
            "Nothing to route; not enabling TokenMaster."
        )

    # Relocate the graph into the canonical .token-master/ home.
    tm_dir = repo / ".token-master"
    tm_dir.mkdir(exist_ok=True)
    graph = json.loads(src_graph.read_text(encoding="utf-8"))
    stamp_graph(graph, repo, _supplier(graphify), time.monotonic() - build_started)
    # A source modified during indexing is not proof of the indexed bytes. Mark
    # it unknown rather than blessing the post-build snapshot as current.
    provenance = graph["token_master_index"]
    for name in provenance["sources"]:
        source = (repo / name).resolve()
        if source.is_relative_to(repo) and source.is_file() and source.stat().st_mtime_ns >= build_started_ns:
            provenance["sources"][name] = None
    from graphify_mcp import _fingerprint
    provenance["source_fingerprint"] = _fingerprint(provenance["sources"])
    atomic_write(tm_dir / "graph.json", (json.dumps(graph, ensure_ascii=False) + "\n").encode("utf-8"))
    # Keep supplier output: never recursively delete a potentially pre-existing directory.

    # Gitignore the per-repo build artifacts (best effort).
    _ensure_gitignore_lines(repo / ".gitignore", [GITIGNORE_LINE, GITIGNORE_CG_LINE])

    # Install the MCP server to a stable, install-independent location.
    home = _host_home(host)
    install_dir = home / "token-master"
    install_dir.mkdir(parents=True, exist_ok=True)
    mcp_target = install_dir / "graphify_mcp.py"
    atomic_write(mcp_target, (SKILL_DIR / "graphify_mcp.py").read_bytes())
    atomic_write(install_dir / "graph-runtime.json", (json.dumps(receipt, indent=2) + "\n").encode("utf-8"))

    # Locate or install codegraph (best effort, optional).
    node_path, shim_path = _ensure_codegraph(home, install=args.install_codegraph)

    # Index with codegraph if the shim is available.
    if node_path and shim_path:
        # codegraph requires `init` (which builds the initial index and creates
        # .codegraph/codegraph.db) before `index`/`sync` will run — calling `index`
        # on an uninitialized repo errors with "CodeGraph not initialized". So pick
        # the subcommand by whether the repo has been initialized already.
        cg_db = repo / ".codegraph" / "codegraph.db"
        if cg_db.is_file():
            cg_cmd, cg_action = [node_path, shim_path, "sync", "."], "syncing"
        else:
            cg_cmd, cg_action = [node_path, shim_path, "init", "."], "initializing"
        print(f"[token-master] codegraph: {cg_action} {repo} ...")
        try:
            subprocess.run(
                cg_cmd,
                cwd=str(repo),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
            print("[token-master] codegraph: index complete.")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            msg = getattr(exc, "output", None) or str(exc)
            print(
                f"[token-master] warning: codegraph indexing failed ({msg!r}) — "
                "continuing graphify-only."
            )
            node_path, shim_path = None, None

    # Post-index sanity check: a codegraph DB that built but indexed zero nodes
    # cannot answer structural queries, so don't advertise it as a backend.
    if node_path and shim_path:
        cg_nodes = _codegraph_node_count(node_path, shim_path, repo)
        if cg_nodes is None:
            print(
                "[token-master] warning: could not read codegraph status — "
                "continuing graphify-only."
            )
            node_path, shim_path = None, None
        elif cg_nodes == 0:
            print(
                "[token-master] warning: codegraph indexed 0 nodes for this repo — "
                "continuing graphify-only."
            )
            node_path, shim_path = None, None
        else:
            print(f"[token-master] codegraph: {cg_nodes} nodes indexed.")

    # Sparse call-graph gate.
    graph_json = tm_dir / "graph.json"
    calls_edge_count = _calls_edge_count(graph_json)
    sparse_warning = False
    if calls_edge_count is not None and code_nodes:
        # Ratio-based: a healthy call graph has roughly one 'calls' edge per code
        # symbol; below ~0.1 edges/symbol the call graph is effectively absent and
        # "who calls X" will fall back to grep. (Django ~0.73 dense; Express ~0.06
        # sparse — a 12x gap an absolute floor fails to separate.)
        threshold = code_nodes * 0.1
        if calls_edge_count < threshold:
            sparse_warning = True
            cg_note = (
                "codegraph (installed) will be the better backend for call-resolution here."
                if node_path
                else "Installing codegraph (`node` + `npm` required) would provide "
                "AST-resolved call edges for this repo."
            )
            print(
                f"[token-master] WARNING: sparse call graph detected — "
                f"{calls_edge_count} 'calls' edges for {code_nodes} code symbols "
                f"(threshold {threshold:.0f}). "
                "This is common in JavaScript/TypeScript repos (e.g. Express had 19 calls edges "
                f"for 313 code nodes). 'Who calls X' queries may fall back to grep. {cg_note}"
            )

    # Preserve existing host-specific routing agents, but render argv with the
    # tested interpreter. No edits to the source templates are needed.
    entry = runtime_entry(python, str(mcp_target))
    entry["env"]["GRAPH_PATH"] = ".token-master/graph.json"
    agent_path = None
    if host != "codex":
        template_name = f"agent.template.{host}.md"
        template = (SKILL_DIR / template_name).read_text(encoding="utf-8")
        if not node_path or not shim_path:
            template = _strip_codegraph_from_template(template)
        agent = (template
                 .replace("command: __UV__", "command: " + json.dumps(python))
                 .replace("args: ['run', '--with', 'mcp', 'python', '__MCP_SCRIPT__']",
                          "args: " + json.dumps(entry["args"], ensure_ascii=False))
                 .replace("command: __NODE__", "command: " + json.dumps(node_path))
                 .replace("args: ['__CG_SHIM__', 'serve', '--mcp', '-p', '.']",
                          "args: " + json.dumps([shim_path, "serve", "--mcp", "-p", "."]))
                 .replace("__UV__", python)
                 .replace("__MCP_SCRIPT__", str(mcp_target))
                 .replace("__NODE__", node_path or "")
                 .replace("__CG_SHIM__", shim_path or ""))
        filename = "token-master.agent.md" if host == "copilot" else "token-master.md"
        agent_path = home / "agents" / filename
        owned_file(agent_path, agent.encode("utf-8"))
    mcp_config_path = wire_mcp(host, "graphify-nav", entry)
    if node_path and shim_path:
        wire_mcp(host, "codegraph", {"command": node_path,
                 "args": [shim_path, "serve", "--mcp", "-p", "."]})

    node_count = _node_count(graph_json)

    # Build summary lines.
    summary = ["[token-master] done."]
    graph_line = f"  graph:  {graph_json}"
    if node_count is not None:
        graph_line += f"  ({node_count} nodes)"
    summary.append(graph_line)
    if calls_edge_count is not None:
        ce_line = f"  calls edges: {calls_edge_count}"
        if sparse_warning:
            ce_line += " (SPARSE — see warning above)"
        summary.append(ce_line)
    summary.append(f"  agent:  {agent_path}")
    summary.append(f"  server: {mcp_target}")
    if mcp_config_path is not None:
        summary.append(f"  mcp config: {mcp_config_path}")
    if node_path and shim_path:
        summary.append(f"  codegraph: {shim_path}")
    else:
        if not shutil.which("node"):
            summary.append("  codegraph: skipped (node not found)")
        else:
            summary.append("  codegraph: skipped (npm install failed or shim missing)")
    if host == "codex":
        summary.append("Codex CLI/Desktop MCP configured; no Codex routing agent or replacement hook installed.")
    elif host == "copilot":
        summary.append(
            "Restart Copilot (or start it with `copilot --agent token-master`) to activate "
            "routing, then ask structural questions normally."
        )
    else:
        summary.append(
            "Restart Claude Code (or start it with `claude --agent token-master`) to activate "
            "routing, then ask structural questions normally."
        )
    summary.append(json.dumps(capabilities(host)))
    print("\n".join(summary))
    return 0


def _node_count(graph_path: Path):
    try:
        with open(graph_path, "r", encoding="utf-8") as fh:
            return len(json.load(fh).get("nodes", []))
    except (OSError, ValueError):
        return None


def _code_node_count(graph_path: Path):
    try:
        with open(graph_path, "r", encoding="utf-8") as fh:
            nodes = json.load(fh).get("nodes", [])
        return sum(1 for n in nodes if n.get("file_type") == "code")
    except (OSError, ValueError):
        return None


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        raise SystemExit(_fail(str(exc)))
