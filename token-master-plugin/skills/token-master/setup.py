#!/usr/bin/env python
"""Build the code graph and install TokenMaster's v7 code navigation for one host.

Usage: python setup.py [REPO_ROOT] --host claude|codex|copilot --python PATH
       python setup.py --host HOST --uninstall

PATH must be an already provisioned runtime. Launch never resolves dependencies.
The navigation server (navigation_mcp.py) answers locate, read_symbol and impact
from an exact-range symbol index and graphify's call graph. Codex configuration
supports CLI/Desktop MCP only; no native routing agent or output hook is claimed.
"""
import argparse
import hashlib
import json
import time
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
# graphify's own output (a multi-megabyte graph.json). Unignored, every agent grep searches it.
GRAPHIFY_OUTPUT_LINE = "graphify-out/"
NAV_SERVER = "tokenmaster-nav"
# Graph servers installed before v7; removed on install and uninstall when TokenMaster owns them.
LEGACY_SERVERS = ("graphify-nav", "codegraph")
# What navigation_mcp.py imports, copied next to it.
NAV_MODULES = ("brainspace/__init__.py", "brainspace/tokens.py", "brainspace/symbol_index.py")


_resolve_host = resolve_host
_host_home = host_home


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


def _remove_owned_servers(host: str, names) -> None:
    """Remove MCP entries this installer owns; a user's own entry of the same name stays."""
    from hosts.config import parse, read
    receipt_path = config_path(host).with_name(config_path(host).name + ".token-master-owned.json")
    owned = parse(read(receipt_path).decode("utf-8"))
    for name in names:
        if f"server:{name}" in owned:
            wire_mcp(host, name, None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", nargs="?")
    parser.add_argument("--host", "-H", choices=HOSTS, default="")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    host = _resolve_host(args.host)
    home = _host_home(host)
    preflight(host)
    agent_file = "token-master.agent.md" if host == "copilot" else "token-master.md"
    if args.uninstall:
        _remove_owned_servers(host, (NAV_SERVER, *LEGACY_SERVERS))
        if host != "codex":
            owned_file(home / "agents" / agent_file, None)
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
            "`graphify` not found on PATH. Install it with `uv tool install graphifyy` (the PyPI package "
            "that provides `graphify`: https://github.com/Graphify-Labs/graphify), then run /token-master again."
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
    _ensure_gitignore_lines(repo / ".gitignore", [GITIGNORE_LINE, GRAPHIFY_OUTPUT_LINE])

    # Install the navigation server and the modules it imports to a stable location.
    install_dir = home / "token-master"
    nav_target = install_dir / "navigation_mcp.py"
    for rel in ("navigation_mcp.py", *NAV_MODULES):
        (install_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        atomic_write(install_dir / rel, (SKILL_DIR / rel).read_bytes())
    atomic_write(install_dir / "graph-runtime.json", (json.dumps(receipt, indent=2) + "\n").encode("utf-8"))

    # Build the symbol index now, so the first navigation call does not wait for it.
    from brainspace.symbol_index import SymbolIndex
    index = SymbolIndex(repo)
    try:
        symbols = index.db.execute("SELECT count(*) FROM symbols WHERE kind != 'module'").fetchone()[0]
    finally:
        index.close()

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
            print(
                f"[token-master] WARNING: sparse call graph detected — "
                f"{calls_edge_count} 'calls' edges for {code_nodes} code symbols "
                f"(threshold {threshold:.0f}). "
                "This is common in JavaScript/TypeScript repos (e.g. Express had 19 calls edges "
                "for 313 code nodes). `impact` then relies on name matches, marked [name]."
            )

    entry = runtime_entry(python, str(nav_target))
    agent_path = None
    if host != "codex":
        template = (SKILL_DIR / f"agent.template.{host}.md").read_text(encoding="utf-8")
        agent = (template
                 .replace("command: __UV__", "command: " + json.dumps(python))
                 .replace("args: ['run', '--with', 'mcp', 'python', '__MCP_SCRIPT__']",
                          "args: " + json.dumps(entry["args"], ensure_ascii=False))
                 .replace("__UV__", python)
                 .replace("__MCP_SCRIPT__", str(nav_target)))
        agent_path = home / "agents" / agent_file
        owned_file(agent_path, agent.encode("utf-8"))
    _remove_owned_servers(host, LEGACY_SERVERS)
    mcp_config_path = wire_mcp(host, NAV_SERVER, entry)

    node_count = _node_count(graph_json)
    summary = ["[token-master] done."]
    graph_line = f"  graph:  {graph_json}"
    if node_count is not None:
        graph_line += f"  ({node_count} nodes)"
    summary.append(graph_line)
    if calls_edge_count is not None:
        summary.append(f"  calls edges: {calls_edge_count}" + (" (SPARSE — see warning above)" if sparse_warning else ""))
    summary.append(f"  symbols: {symbols} in {repo / '.token-master' / 'symbols.sqlite'}")
    summary.append(f"  agent:  {agent_path}")
    summary.append(f"  server: {nav_target}")
    if mcp_config_path is not None:
        summary.append(f"  mcp config: {mcp_config_path}")
    if host == "codex":
        summary.append("Codex CLI/Desktop MCP configured; no Codex routing agent or replacement hook installed.")
    else:
        command = "copilot" if host == "copilot" else "claude"
        summary.append(f"Restart {'Copilot' if host == 'copilot' else 'Claude Code'} (or start it with "
                       f"`{command} --agent token-master`) to activate navigation.")
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
