#!/usr/bin/env python
"""Graph candidate navigation with freshness, provenance and bounded paging.

Launch with the preflight-tested interpreter recorded by setup.py. No imports of
source parsers are required. Missing MCP disables transport, not local queries.
Every tool still returns a string; its final ``metadata: {...}`` line is JSON.
"""
import collections
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None

GRAPH_PATH = os.environ.get("GRAPH_PATH", os.path.join(".token-master", "graph.json"))
CALL_LOG = os.environ.get("MCP_CALL_LOG")
MAX_DEFS = 8
MAX_ROWS = 60
_STATE: dict[str, Any] = {"loaded": False, "NODES": {}, "OUT": {}, "IN": {}, "BY_NAME": {}}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _source_digest(root, name):
    """Never follow a graph-supplied source path outside the workspace."""
    try:
        path = (root / name).resolve()
        path.relative_to(root.resolve())
        return _sha(path.read_bytes()) if path.is_file() else None
    except (OSError, ValueError):
        return None


def _fingerprint(manifest):
    return _sha(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def stamp_graph(graph, root, supplier, build_seconds=None, source_manifest=None):
    """Record source bytes and supplier at build time, not first query time.

    Scope is referenced source files only; newly added unindexed files are not
    covered. Supplier version may be unknown, never inferred from our version.
    A pre-build source manifest can be supplied to detect edits during indexing.
    """
    files = sorted({n["source_file"] for n in graph["nodes"]
                    if isinstance(n.get("source_file"), str) and n["source_file"]})
    manifest = {name: _source_digest(Path(root), name) for name in files}
    if source_manifest is not None:
        manifest = {name: source_manifest.get(name) for name in files}
    graph["token_master_index"] = {
        "schema_version": 1, "supplier": supplier,
        "source_scope": "indexed_source_files_only", "sources": manifest,
        "source_fingerprint": _fingerprint(manifest),
        "build_seconds": build_seconds,
        "edge_semantics": "name-inferred candidates; not exhaustive or verified",
    }
    return graph


def _find_graph():
    path = Path(GRAPH_PATH)
    if path.is_absolute():
        return path
    here = Path.cwd().resolve()
    for directory in [here, *here.parents]:
        candidate = directory / path
        if candidate.is_file():
            return candidate
    return here / path


def _norm(label):
    return str(label).strip().rstrip("()").lower()


def _log(tool, symbol):
    if CALL_LOG:
        try:
            path = Path(CALL_LOG)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(f"{time.time()}\t{tool}\t{symbol}\n")
        except OSError:
            pass


def _validate(graph):
    if not isinstance(graph, dict):
        raise ValueError("graph must be an object")
    nodes, links = graph.get("nodes"), graph.get("links")
    if not isinstance(nodes, list) or not nodes or not isinstance(links, list):
        raise ValueError("expected nonempty nodes list and links list")
    ids = set()
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"]:
            raise ValueError("node IDs must be nonempty strings")
        if node["id"] in ids:
            raise ValueError("duplicate node ID")
        ids.add(node["id"])
    for link in links:
        if not isinstance(link, dict) or not all(isinstance(link.get(k), str) for k in ("source", "target", "relation")):
            raise ValueError("edge requires string source, target and relation")
        if link["source"] not in ids or link["target"] not in ids:
            raise ValueError("dangling edge endpoint")
    provenance = graph.get("token_master_index")
    if provenance is not None:
        if not isinstance(provenance, dict) or provenance.get("schema_version") != 1:
            raise ValueError("unsupported provenance schema")
        sources = provenance.get("sources")
        if not isinstance(sources, dict) or any(not isinstance(k, str) or (v is not None and not isinstance(v, str)) for k, v in sources.items()):
            raise ValueError("invalid source manifest")
        if provenance.get("source_fingerprint") != _fingerprint(sources):
            raise ValueError("source manifest fingerprint mismatch")
        source_files = {n["source_file"] for n in nodes
                        if isinstance(n.get("source_file"), str) and n["source_file"]}
        if set(sources) != source_files:
            raise ValueError("source manifest does not cover indexed source files")
        if not isinstance(provenance.get("supplier"), dict):
            raise ValueError("invalid supplier provenance")
    return nodes, links, provenance


def _ensure_loaded():
    path = _find_graph()
    try:
        content = path.read_bytes()
        digest = _sha(content)
        if not _STATE["loaded"] or _STATE.get("digest") != digest or _STATE.get("path") != path:
            graph = json.loads(content.decode("utf-8-sig"))
            nodes, links, provenance = _validate(graph)
            by_name, outgoing, incoming = (collections.defaultdict(list) for _ in range(3))
            for node in nodes:
                if node.get("file_type") == "code":
                    by_name[_norm(node.get("label", ""))].append(node["id"])
            for link in links:
                outgoing[link["source"]].append((link["relation"], link["target"], link))
                incoming[link["target"]].append((link["relation"], link["source"], link))
            _STATE.update(loaded=True, path=path, digest=digest, provenance=provenance,
                          NODES={n["id"]: n for n in nodes}, OUT=outgoing, IN=incoming,
                          BY_NAME=by_name)
        provenance = _STATE["provenance"]
        metadata = {"index_sha256": digest, "supplier": {"name": "unknown", "version": None},
                    "source_status": "unknown", "source_scope": "unknown",
                    "source_fingerprint": None, "current_source_fingerprint": None,
                    "semantic_complete": False,
                    "caveat": "INFERRED candidates only; verify cited source. Dynamic dispatch and name collisions may be missing or wrong."}
        if provenance:
            # Canonical path is <workspace>/.token-master/graph.json. For an
            # explicitly selected graph elsewhere, its containing dir is root.
            root = path.parent.parent if path.parent.name == ".token-master" else path.parent
            expected = provenance["sources"]
            current = {name: _source_digest(root, name) for name in expected}
            changed = [name for name in expected if expected[name] != current[name]]
            status = "stale" if changed else "fresh" if expected and all(expected.values()) else "unknown"
            metadata.update(supplier=provenance["supplier"], source_status=status,
                            source_scope="indexed_source_files_only",
                            source_fingerprint=provenance["source_fingerprint"],
                            current_source_fingerprint=_fingerprint(current),
                            changed_source_count=len(changed), changed_sources=changed[:MAX_ROWS],
                            build_seconds=provenance.get("build_seconds"))
        _STATE["metadata"] = metadata
        return None
    except (OSError, ValueError, TypeError, KeyError) as exc:
        _STATE["loaded"] = False
        return f"TokenMaster graph missing or invalid at '{path}': {exc}. Rebuild the index; use source search meanwhile."


def _loc(node):
    return f"{node.get('source_file', '?')}:{node.get('source_location', '?')}"


def _resolve(symbol):
    if symbol in _STATE["NODES"]:
        return [symbol]
    return sorted(_STATE["BY_NAME"].get(_norm(symbol), []))


def _render(title, rows=(), offset=0, limit=MAX_ROWS, **extra):
    if isinstance(offset, bool) or isinstance(limit, bool) or not isinstance(offset, int) or not isinstance(limit, int) or offset < 0 or limit < 1:
        return "Invalid pagination: offset must be >= 0 and limit must be >= 1 (integers)."
    limit = min(limit, MAX_ROWS)
    page = rows[offset:offset + limit]
    total = len(rows)
    metadata = {**_STATE["metadata"], "offset": offset, "limit": limit,
                "returned": len(page), "total": total,
                "row_ids": [row[0] for row in page],
                "next_offset": offset + len(page) if offset + len(page) < total else None,
                "enumeration_complete": offset + len(page) >= total,
                "all_rows_in_response": offset == 0 and len(page) == total,
                "enumeration_scope": "indexed candidate nodes, not exhaustive source relationships",
                "pagination_contract": "reuse offsets only for the same index_sha256; restart if it changes",
                **extra}
    warning = "\nSTALE SOURCE: rebuild before trusting candidates." if metadata["source_status"] == "stale" else ""
    return title + warning + "\n" + "\n".join(row[1] for row in page) + "\nmetadata: " + json.dumps(metadata, ensure_ascii=False, sort_keys=True)


def _query(tool, symbol):
    error = _ensure_loaded()
    if error:
        return [], error
    _log(tool, symbol)
    ids = _resolve(symbol)
    if not ids:
        return [], _render(f"No definition node found for '{symbol}'.")
    if len(ids) > 1 and tool not in ("find",):
        rows = [(i, f"  - id={i}  {_STATE['NODES'][i].get('label')} [{_loc(_STATE['NODES'][i])}]") for i in ids]
        return [], _render(f"'{symbol}' is ambiguous — {len(ids)} definitions. Use a specific node id; find() pages all definitions.", rows, limit=MAX_DEFS, ambiguous=True)
    return ids, None


mcp = FastMCP("graphify-nav") if FastMCP else None


def _tool(fn):
    return mcp.tool()(fn) if mcp else fn


@_tool
def find(symbol: str, offset: int = 0, limit: int = MAX_ROWS) -> str:
    """Page definition candidates with source/index freshness and provenance."""
    ids, error = _query("find", symbol)
    if error:
        return error
    rows = [(i, f"  - {_STATE['NODES'][i].get('label')} [{_loc(_STATE['NODES'][i])}] id={i}") for i in ids]
    return _render(f"Definitions of '{symbol}' ({len(ids)}):", rows, offset, limit)


def _direct(tool, symbol, reverse, offset, limit):
    ids, error = _query(tool, symbol)
    if error:
        return error
    edges = _STATE["IN" if reverse else "OUT"].get(ids[0], [])
    candidates = collections.defaultdict(list)
    for relation, other, edge in edges:
        if relation == "calls":
            candidates[other].append(edge)
    rows = []
    for other, links in sorted(candidates.items()):
        node = _STATE["NODES"][other]
        edge = links[0]
        rows.append((other, f"  - {node.get('label')} [{_loc(node)}] id={other} "
                     f"call@{edge.get('source_location', '?')} conf={edge.get('confidence', 'unknown')} "
                     f"indexed_call_sites={len(links)}"))
    return _render(f"DIRECT {tool} of '{symbol}' ({len(rows)}) — INFERRED edges, verify at source:", rows, offset, limit)


@_tool
def callers(symbol: str, offset: int = 0, limit: int = MAX_ROWS) -> str:
    """Page direct calling candidate nodes (not verified or exhaustive calls)."""
    return _direct("callers", symbol, True, offset, limit)


@_tool
def callees(symbol: str, offset: int = 0, limit: int = MAX_ROWS) -> str:
    """Page directly called candidate nodes (not verified or exhaustive calls)."""
    return _direct("callees", symbol, False, offset, limit)


@_tool
def impact(symbol: str, depth: int = 3, offset: int = 0, limit: int = MAX_ROWS) -> str:
    """Page reverse-call candidates within 1-5 hops; inference uncertainty compounds."""
    ids, error = _query("impact", symbol)
    if error:
        return error
    if isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= 5:
        return "Invalid depth: expected integer 1 through 5."
    visited, frontier, rows = set(ids), set(ids), []
    for hop in range(1, depth + 1):
        nxt = {other for node in frontier for rel, other, edge in _STATE["IN"].get(node, [])
               if rel == "calls" and other not in visited}
        if not nxt:
            frontier = set()
            break
        visited.update(nxt)
        for node in sorted(nxt):
            n = _STATE["NODES"][node]
            rows.append((node, f"  - hop={hop} {n.get('label')} [{_loc(n)}] id={node}"))
        frontier = nxt
    beyond = any(rel == "calls" and other not in visited for node in frontier
                 for rel, other, edge in _STATE["IN"].get(node, []))
    return _render(f"IMPACT of '{symbol}' — INFERRED, within {depth} hops:", rows, offset, limit,
                   depth=depth, depth_boundary_has_more=beyond)


@_tool
def inheritors(symbol: str, offset: int = 0, limit: int = MAX_ROWS) -> str:
    """Page direct subtype/implementor candidates. Method previews are bounded."""
    ids, error = _query("inheritors", symbol)
    if error:
        return error
    candidates: dict[str, set[str]] = {}
    for rel, other, edge in _STATE["IN"].get(ids[0], []):
        if rel in ("inherits", "implements"):
            candidates.setdefault(other, set()).add(rel)
    rows = []
    for other, relations in sorted(candidates.items()):
        node = _STATE["NODES"][other]
        methods = sorted({target for rel, target, edge in _STATE["OUT"].get(other, []) if rel == "method"})
        names = [str(_STATE["NODES"][i].get("label", i)) for i in methods[:12]]
        rows.append((other, f"  - {node.get('label')} ({','.join(sorted(relations))}) [{_loc(node)}] id={other}\n"
                     f"      methods preview ({min(12, len(methods))}/{len(methods)}): {', '.join(names)}"))
    return _render(f"Subtypes/implementors of '{symbol}' — graph candidates:", rows, offset, limit,
                   methods_preview_complete=False)


@_tool
def explain(symbol: str, offset: int = 0, limit: int = MAX_ROWS) -> str:
    """Page immediate neighbor edges across all indexed relations."""
    ids, error = _query("explain", symbol)
    if error:
        return error
    node = _STATE["NODES"][ids[0]]
    rows = []
    for direction, key in (("out", "OUT"), ("in", "IN")):
        for index, (rel, other, edge) in enumerate(_STATE[key].get(ids[0], [])):
            neighbor = _STATE["NODES"][other]
            rows.append((f"{direction}:{index}:{other}", f"  - {direction}:{rel} {neighbor.get('label')} [{_loc(neighbor)}] id={other}"))
    return _render(f"{node.get('label')} [{_loc(node)}] id={ids[0]}", rows, offset, limit)


if __name__ == "__main__":
    if mcp is None:
        print("TokenMaster: MCP dependency unavailable; use source search or provision the explicit runtime.", file=sys.stderr)
        raise SystemExit(1)
    mcp.run()
