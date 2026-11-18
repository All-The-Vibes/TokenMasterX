"""Deterministic, token-capped repository and cross-session recall brief (Pillar 5).

Builds `.token-master/brief.md` (and receipt `.token-master/brief.json`) from
`.token-master/symbols.sqlite`, `.token-master/graph.json`, and optional
prior-session navigation footprints in `.token-master/recall.jsonl`.

Cache-stability invariants:
- `record_recall` appends resolved production symbol hits to `recall.jsonl` only;
  it NEVER mutates `brief.md` during live MCP calls, keeping the prompt prefix
  byte-identical across sessions between explicit builds/refreshes.
- `build_brief` uses `symbol_index._assemble` so the whole joined brief (header,
  entries, footer and newlines included) is strictly bounded by `BRIEF_BUDGET`
  tokens (`NavCap.assemble_le`).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any

from . import symbol_index, tokens

BRIEF_DIR = Path(".token-master")
BRIEF_PATH = BRIEF_DIR / "brief.md"
BRIEF_META_PATH = BRIEF_DIR / "brief.json"
RECALL_PATH = BRIEF_DIR / "recall.jsonl"

BRIEF_SCHEMA = 2
BRIEF_BUDGET = 320
MAX_BRIEF_BYTES = 8_192
MAX_RECALL_BYTES = 262_144

ALGORITHMS = ("r1", "v1")
DEFAULT_ALGORITHM = "r1"

MAX_AREAS = 6
MAX_HUBS = 10
MAX_HUBS_PER_FILE = 2
MAX_ENTRYPOINTS = 4
MAX_RECALL = 5

FLOOR_HUB = 3
FLOOR_ENTRY = 3
FLOOR_RECALL = 3

# Non-increasing non-negative integer marginal increment curves for discrete-concave
# coverage atoms x in U: g_x(k) = sum_{j < k} curve[j]. Because every curve is
# non-increasing and >= 0, F(S) = sum_x g_x(count_x(S)) is provably monotone submodular
# in exact integer arithmetic with zero floating-point drift.
_MOD_INC_CORE = (340, 35)
_MOD_INC_AUX = (40, 5)
_DIR_INC = (130, 30, 10)
_IN_FILE_INC = (45, 15, 5)
_OUT_FILE_INC = (40, 15, 5)
_HOP_INC = (30, 8)

_HUB_KINDS = ("class", "struct", "trait", "enum", "function", "method")
_ENTRYPOINT_NAMES = frozenset({"main", "cli", "make_server", "create_app", "app", "run"})
_BOILERPLATE_NAMES = frozenset({
    "__init__", "__repr__", "__str__", "__eq__", "__hash__", "__enter__", "__exit__",
    "new", "default", "fmt", "from", "into", "drop",
})
_CODE_SUFFIXES = symbol_index.CODE_SUFFIXES + symbol_index.RUST_SUFFIXES


def _is_code_file(path: str) -> bool:
    return path.lower().endswith(_CODE_SUFFIXES)


def _both_within_budget(text: str, budget: int) -> bool:
    if symbol_index._count(text) > budget:
        return False
    if tokens.backend_info().get("exact_reference") and tokens.count_tokens(text) > budget:
        return False
    return True


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


_AUX_DIRS = frozenset({
    "examples", "example", "samples", "sample", "demos", "demo",
    "docs", "doc", "assets", "benchmarks", "benchmark",
    "evals", "eval", "evidence", "site", "scripts", "tools",
})


def _is_aux_path(rel: str) -> bool:
    parts = [p.lower() for p in rel.replace("\\", "/").split("/")[:-1]]
    return any(part in _AUX_DIRS for part in parts)


def _find_repo_root(start: Path) -> Path | None:
    try:
        cur = start.resolve()
    except OSError:
        return None
    if cur.is_file():
        cur = cur.parent
    for candidate in (cur, *cur.parents):
        tm = candidate / BRIEF_DIR
        if tm.is_dir() and not tm.is_symlink():
            return candidate
        if (candidate / ".git").exists():
            # Do not walk past an unindexed git repository root into an ancestor repo.
            return None
    return None


def read_valid_brief(cwd: Path, *, budget: int = BRIEF_BUDGET) -> tuple[str, Path] | None:
    """Return `(brief_text, brief_path)` for `cwd` if present, safe, and within `budget`."""
    if type(budget) is not int or budget <= 0:
        return None
    root = _find_repo_root(cwd)
    if root is None:
        return None
    brief_file = root / BRIEF_PATH
    try:
        if brief_file.is_symlink() or not brief_file.is_file():
            return None
        size = brief_file.stat().st_size
        if size <= 0 or size > MAX_BRIEF_BYTES:
            return None
        text = brief_file.read_bytes().decode("utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    if not text or not _both_within_budget(text, budget):
        return None
    return text, brief_file


def _resolve_recall_targets(index: symbol_index.SymbolIndex, tool: str, arguments: dict) -> list[tuple[str, str]]:
    """Resolve an MCP navigation call's argument to canonical non-test `(path, qualname)` pairs."""
    raw = ""
    if tool == "locate":
        raw = str(arguments.get("query") or "").strip()
    elif tool == "read_symbol":
        raw = str(arguments.get("target") or "").strip()
    elif tool == "impact":
        raw = str(arguments.get("symbol") or "").strip()
    if not raw:
        return []

    # Range target `path:start-end`: attribute to the innermost enclosing non-module symbol if any.
    match = re.fullmatch(r"(.+?):(\d+)(?:-(\d+))?", raw)
    if match and "::" not in raw:
        files = index._paths(match.group(1))
        if len(files) != 1:
            return []
        rel = files[0]
        if not _is_code_file(rel) or symbol_index._is_test(rel):
            return []
        line = int(match.group(2))
        row = index.db.execute(
            "SELECT qualname FROM symbols WHERE path = ? AND kind != 'module' AND start <= ? AND end >= ? "
            "ORDER BY (end - start) ASC, start ASC LIMIT 1",
            (rel, line, line),
        ).fetchone()
        return [(rel, row["qualname"])] if row else []

    # File-only target in locate/read_symbol: record its largest production symbol as anchor if unambiguous.
    if "::" not in raw and ("/" in raw or "\\" in raw or raw.lower().endswith(symbol_index.INDEXED_SUFFIXES)):
        files = index._paths(raw)
        if len(files) != 1:
            return []
        rel = files[0]
        if not _is_code_file(rel) or symbol_index._is_test(rel):
            return []
        row = index.db.execute(
            "SELECT qualname FROM symbols WHERE path = ? AND kind IN ('class','struct','trait','function','method') "
            "ORDER BY tokens DESC, start ASC LIMIT 1",
            (rel,),
        ).fetchone()
        return [(rel, row["qualname"])] if row else []

    kinds = symbol_index.CALLABLE if tool == "impact" else None
    rows = index._find(raw, broad=(tool == "locate"), kinds=kinds)
    out: list[tuple[str, str]] = []
    for row in rows:
        rel = row["path"]
        if _is_code_file(rel) and not symbol_index._is_test(rel) and row["qualname"]:
            pair = (rel, row["qualname"])
            if pair not in out:
                out.append(pair)
            if len(out) >= 2:
                break
    return out


def record_recall(index: symbol_index.SymbolIndex, tool: str, arguments: dict, result: str) -> None:
    """Append resolved production symbol hits to `.token-master/recall.jsonl` (best effort)."""
    try:
        if not isinstance(result, str) or result.startswith(("Error:", "No symbol")):
            return
        tm_dir = index.root / BRIEF_DIR
        if not tm_dir.is_dir() or tm_dir.is_symlink():
            return
        recall_file = index.root / RECALL_PATH
        if recall_file.is_symlink():
            return
        targets = _resolve_recall_targets(index, tool, arguments if isinstance(arguments, dict) else {})
        if not targets:
            return
        lines = "".join(
            json.dumps({"tool": tool, "path": rel, "qualname": qual}, ensure_ascii=False) + "\n"
            for rel, qual in targets
        ).encode("utf-8")
        if recall_file.is_file() and recall_file.stat().st_size + len(lines) > MAX_RECALL_BYTES:
            existing = recall_file.read_bytes().splitlines(keepends=True)
            kept = b"".join(existing[len(existing) // 2:]) + lines
            _atomic_write_bytes(recall_file, kept)
        else:
            with recall_file.open("ab") as fh:
                fh.write(lines)
    except Exception:
        return


def load_recall_scores(root: Path, index: symbol_index.SymbolIndex) -> list[tuple[sqlite3.Row, int, int]]:
    """Return validated `(symbol_row, raw_hits, recency_score)` triples from `recall.jsonl`.

    Uses exact integer step-recency weights over validated chronological code-symbol
    events: the latest 16 events carry weight 4, the prior 32 carry weight 2, and
    older historical events carry weight 1.
    """
    recall_file = root / RECALL_PATH
    if not recall_file.is_file() or recall_file.is_symlink():
        return []
    try:
        raw_lines = recall_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    events: list[tuple[str, str]] = []
    for line in raw_lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        rel = rec.get("path")
        qual = rec.get("qualname")
        if isinstance(rel, str) and isinstance(qual, str) and rel and qual:
            if _is_code_file(rel) and not symbol_index._is_test(rel):
                events.append((rel, qual))
    if not events:
        return []

    # Validate current existence once per distinct `(path, qualname)` before weighting.
    unique_keys = set(events)
    row_by_key: dict[tuple[str, str], sqlite3.Row] = {}
    for rel, qual in unique_keys:
        row = index.db.execute(
            f"SELECT {', '.join(symbol_index._COLUMNS)} FROM symbols "
            "WHERE path = ? AND qualname = ? AND kind != 'module' ORDER BY start ASC LIMIT 1",
            (rel, qual),
        ).fetchone()
        if row is not None:
            row_by_key[(rel, qual)] = row
    if not row_by_key:
        return []

    valid_events = [ev for ev in events if ev in row_by_key]
    total = len(valid_events)
    counts: Counter[tuple[str, str]] = Counter()
    recency: Counter[tuple[str, str]] = Counter()
    for pos, key in enumerate(valid_events):
        age = total - 1 - pos
        weight = 8 if age < 8 else (3 if age < 24 else 1)
        counts[key] += 1
        recency[key] += weight

    validated = [
        (row_by_key[key], counts[key], recency[key])
        for key in counts
    ]
    validated.sort(
        key=lambda item: (-item[2], -item[1], item[0]["path"], item[0]["start"], item[0]["qualname"])
    )
    return validated


def load_recall_counts(root: Path, index: symbol_index.SymbolIndex) -> list[tuple[sqlite3.Row, int]]:
    """Return validated current `(symbol_row, hit_count)` pairs from `.token-master/recall.jsonl`."""
    scored = load_recall_scores(root, index)
    pairs = [(row, hits) for row, hits, _score in scored]
    pairs.sort(key=lambda item: (-item[1], item[0]["path"], item[0]["start"], item[0]["qualname"]))
    return pairs


def fold_brief_path(root_prefix: str, full_path: str, is_unique_stripped: bool) -> str:
    """Fold `full_path` relative to `root_prefix` when unambiguous; else emit `/full_path`.

    Because repo-relative paths never begin with `/`, leading `/` distinguishes an
    unfactored repo-root path from a `@root`-relative path without consulting disk,
    while `SymbolIndex._relative` strips leading `/` so both forms are directly
    callable in `read_symbol` and `impact`.
    """
    clean = full_path.lstrip("/")
    if not root_prefix:
        return clean
    prefix_slash = root_prefix.strip("/") + "/"
    if clean.startswith(prefix_slash) and is_unique_stripped:
        stripped = clean[len(prefix_slash):]
        if stripped and not stripped.startswith("/"):
            return stripped
    return "/" + clean


def unfold_brief_path(root_prefix: str, rendered_path: str) -> str:
    """Exact syntactic inverse of `fold_brief_path`."""
    if rendered_path.startswith("/"):
        return rendered_path.lstrip("/")
    prefix = root_prefix.strip("/")
    return f"{prefix}/{rendered_path}" if prefix else rendered_path


def _common_code_prefix(paths: list[str]) -> str:
    if not paths:
        return ""
    split_dirs = [p.rsplit("/", 1)[0].split("/") if "/" in p else [] for p in paths]
    if not split_dirs or not split_dirs[0]:
        return ""
    prefix: list[str] = []
    for idx, part in enumerate(split_dirs[0]):
        if all(len(d) > idx and d[idx] == part for d in split_dirs):
            prefix.append(part)
        else:
            break
    return "/".join(prefix)


def _layout_line(code_paths: list[str], test_paths: list[str], *, separate_aux: bool = False) -> str:
    aux_paths: list[str] = []
    target_paths = code_paths
    if separate_aux:
        core_only = [p for p in code_paths if not _is_aux_path(p)]
        if core_only:
            target_paths = core_only
            aux_paths = [p for p in code_paths if _is_aux_path(p)]

    prefix = _common_code_prefix(target_paths)
    plen = len(prefix) + 1 if prefix else 0
    top_counts: Counter[str] = Counter()
    for p in target_paths:
        rel = p[plen:] if plen and p.startswith(prefix + "/") else p
        top_counts[rel.split("/", 1)[0] if "/" in rel else "."] += 1
    dominant = {k for k, v in top_counts.items() if k != "." and v * 2 >= len(target_paths)}
    buckets: Counter[str] = Counter()
    for p in target_paths:
        rel = p[plen:] if plen and p.startswith(prefix + "/") else p
        parts = rel.split("/")
        if len(parts) == 1:
            area = "."
        elif (parts[0] in ("src", "lib", "pkg", "crates") or parts[0] in dominant) and len(parts) >= 3:
            area = f"{parts[0]}/{parts[1]}"
        else:
            area = parts[0]
        buckets[area] += 1
    ordered = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    shown = [f"{area} ({cnt})" for area, cnt in ordered[:MAX_AREAS]]
    if len(ordered) > MAX_AREAS:
        shown.append(f"+{len(ordered) - MAX_AREAS} dirs")
    root_note = f"{prefix}/ -> " if prefix else ""
    counts_note = (
        f"{len(target_paths)} core, {len(aux_paths)} aux"
        if aux_paths
        else f"{len(code_paths)} code files"
    )
    test_note = f"; tests: {len(test_paths)} files" if test_paths else ""
    return f"Layout ({counts_note}{test_note}): {root_note}" + ", ".join(shown)


def _file_unchanged_since_graph(root: Path, rel: str, sources: dict[str, Any], cache: dict[str, bool]) -> bool:
    if rel in cache:
        return cache[rel]
    if not sources:
        cache[rel] = True
        return True
    expected = sources.get(rel)
    if not isinstance(expected, str) or not expected:
        cache[rel] = False
        return False
    try:
        digest = hashlib.sha256((root / rel).read_bytes()).hexdigest()
        ok = digest == expected
    except OSError:
        ok = False
    cache[rel] = ok
    return ok


def _call_graph_topology(
    index: symbol_index.SymbolIndex,
) -> tuple[
    list[sqlite3.Row],
    dict[int, set[str]],
    dict[int, set[str]],
    dict[str, set[str]],
    dict[int, set[int]],
]:
    """Extract directed cross-file production call neighborhoods for non-test symbols.

    Returns `(prod_rows, caller_files, callee_files, file_callee_files, neighbors_1hop)`.
    Combines fresh Graphify call edges with `symbols.sqlite` syntax-aware call sites
    (bare calls never match methods like `str.join`; receiver calls verify module/class),
    rolling up external method edges to their enclosing class/struct/trait.
    """
    prod_rows = index.db.execute(
        f"SELECT {', '.join(symbol_index._COLUMNS)} FROM symbols "
        f"WHERE kind IN ({','.join('?' * len(_HUB_KINDS))})",
        _HUB_KINDS,
    ).fetchall()
    prod_rows = [r for r in prod_rows if _is_code_file(r["path"]) and not symbol_index._is_test(r["path"])]
    if not prod_rows:
        return [], {}, {}, {}, {}

    row_by_id = {r["id"]: r for r in prod_rows}
    caller_files: dict[int, set[str]] = defaultdict(set)
    callee_files: dict[int, set[str]] = defaultdict(set)
    file_callee_files: dict[str, set[str]] = defaultdict(set)
    neighbors_1hop: dict[int, set[int]] = defaultdict(set)

    # 1. Graphify resolved call edges (when fresh for both endpoints).
    graph = index._graph()
    if graph is not None:
        nodes, callers_by_target, node_by_place, sources = graph
        fresh_cache: dict[str, bool] = {}
        nid_to_sid: dict[str, int] = {}
        for row in prod_rows:
            if not _file_unchanged_since_graph(index.root, row["path"], sources, fresh_cache):
                continue
            for place in (
                (row["path"], row["line"], row["qualname"]),
                (row["path"], row["line"], row["name"]),
                (row["path"], row["start"], row["qualname"]),
                (row["path"], row["start"], row["name"]),
            ):
                nid = node_by_place.get(place)
                if nid is not None:
                    nid_to_sid.setdefault(nid, row["id"])

        for row in prod_rows:
            if not _file_unchanged_since_graph(index.root, row["path"], sources, fresh_cache):
                continue
            candidates = (
                (row["path"], row["line"], row["qualname"]),
                (row["path"], row["line"], row["name"]),
                (row["path"], row["start"], row["qualname"]),
                (row["path"], row["start"], row["name"]),
            )
            seen_nids = set()
            for place in candidates:
                nid = node_by_place.get(place)
                if nid is None or nid in seen_nids:
                    continue
                seen_nids.add(nid)
                for src_nid, _call_line, _extracted in callers_by_target.get(nid, ()):
                    src_file = nodes[src_nid][0].replace("\\", "/")
                    if (src_file != row["path"]
                            and _is_code_file(src_file)
                            and not symbol_index._is_test(src_file)
                            and _file_unchanged_since_graph(index.root, src_file, sources, fresh_cache)):
                        caller_files[row["id"]].add(src_file)
                        file_callee_files[src_file].add(row["path"])
                        src_sid = nid_to_sid.get(src_nid)
                        if src_sid is not None and src_sid != row["id"]:
                            callee_files[src_sid].add(row["path"])
                            neighbors_1hop[row["id"]].add(src_sid)
                            neighbors_1hop[src_sid].add(row["id"])

    # 2. SQLite call-site index using symbol_index's precise form/receiver rules (bare calls never
    #    falsely match methods like str.join/Path.resolve; receiver calls require matching module/class).
    top_by_name: dict[str, list[sqlite3.Row]] = defaultdict(list)
    all_by_name: dict[str, list[sqlite3.Row]] = defaultdict(list)
    class_by_key: dict[tuple[str, str], int] = {}
    for row in prod_rows:
        all_by_name[row["name"]].append(row)
        if row["kind"] != "method" and "." not in row["qualname"]:
            top_by_name[row["name"]].append(row)
        if row["kind"] in ("class", "struct", "trait"):
            class_by_key[(row["path"], row["qualname"])] = row["id"]

    call_rows = index.db.execute(
        "SELECT s.id AS caller_id, s.path AS caller_path, c.callee AS callee, c.form AS form, c.receiver AS receiver "
        "FROM calls c JOIN symbols s ON c.caller = s.id"
    ).fetchall()
    for cr in call_rows:
        cpath = cr["caller_path"]
        if not _is_code_file(cpath) or symbol_index._is_test(cpath):
            continue
        target_row = None
        form = cr["form"]
        recv_raw = cr["receiver"] or ""
        if form == "bare":
            defs = top_by_name.get(cr["callee"], ())
            if len(defs) == 1:
                target_row = defs[0]
        elif form in ("attr", "path") and recv_raw and not recv_raw.startswith(("self.", "cls.")):
            recv = recv_raw.rsplit(".", 1)[-1]
            defs = all_by_name.get(cr["callee"], ())
            matched = [
                d for d in defs
                if (d["kind"] != "method" and symbol_index._in_module(d["path"], recv))
                or (d["kind"] == "method" and d["qualname"].startswith(recv + "."))
            ]
            if len(matched) == 1:
                target_row = matched[0]
        if target_row is not None and target_row["path"] != cpath:
            tid = target_row["id"]
            caller_files[tid].add(cpath)
            file_callee_files[cpath].add(target_row["path"])
            cid = cr["caller_id"]
            if cid in row_by_id and cid != tid:
                callee_files[cid].add(target_row["path"])
                neighbors_1hop[tid].add(cid)
                neighbors_1hop[cid].add(tid)

    # Roll up resolved external method edges to their enclosing class/struct/trait as well.
    for row in prod_rows:
        if row["kind"] == "method" and "." in row["qualname"]:
            owner = row["qualname"].rsplit(".", 1)[0]
            cid = class_by_key.get((row["path"], owner))
            if cid is not None:
                if caller_files.get(row["id"]):
                    caller_files[cid].update(caller_files[row["id"]])
                if callee_files.get(row["id"]):
                    callee_files[cid].update(callee_files[row["id"]])
                if neighbors_1hop.get(row["id"]):
                    neighbors_1hop[cid].update(neighbors_1hop[row["id"]] - {cid})

    return prod_rows, caller_files, callee_files, file_callee_files, neighbors_1hop


def _cross_file_caller_counts(index: symbol_index.SymbolIndex) -> dict[int, int]:
    """Count distinct non-test external caller files for each non-test symbol id."""
    _rows, caller_files, _callee_files, _file_callees, _hop = _call_graph_topology(index)
    return {sid: len(files) for sid, files in caller_files.items() if files}


def _eligible_hub(row: sqlite3.Row, in_deg: int) -> bool:
    if in_deg <= 0 or (row["tokens"] or 0) < 10:
        return False
    name = row["name"]
    if name in _BOILERPLATE_NAMES and in_deg < 4:
        return False
    if name.startswith("_") and not name.startswith("__") and in_deg < 3:
        return False
    return True


def _source_fingerprint(root: Path, index: symbol_index.SymbolIndex) -> str:
    try:
        graph_data = json.loads((root / symbol_index.GRAPH_PATH).read_text(encoding="utf-8"))
        stamp = graph_data.get("token_master_index") or {}
        fp = stamp.get("source_fingerprint")
        if isinstance(fp, str) and fp:
            return fp
    except (OSError, ValueError):
        pass
    rows = index.db.execute("SELECT path, size FROM files ORDER BY path").fetchall()
    digest = hashlib.sha256()
    for r in rows:
        digest.update(f"{r['path']}:{r['size']}\n".encode("utf-8"))
    return digest.hexdigest()


@dataclass(frozen=True)
class BriefCandidate:
    """One candidate brief anchor with its discrete-concave coverage atoms."""

    role: str  # "recall" | "hub" | "entry"
    sid: int
    path: str
    qualname: str
    start: int
    end: int
    sym_tokens: int
    in_degree: int
    raw_hits: int
    recency_score: int
    is_aux: bool
    line: str
    line_tokens: int
    atoms: tuple[tuple[tuple[str, Any], tuple[int, ...]], ...]


_ROLE_DISPLAY_ORDER = {"recall": 0, "hub": 1, "entry": 2}
_ROLE_CAPS = {"recall": MAX_RECALL, "hub": MAX_HUBS, "entry": MAX_ENTRYPOINTS}
_ROLE_FLOORS = {"recall": FLOOR_RECALL, "hub": FLOOR_HUB, "entry": FLOOR_ENTRY}


def marginal_gain(candidate: BriefCandidate, atom_counts: Counter[tuple[str, Any]]) -> int:
    """Exact integer marginal coverage gain `F(S u {candidate}) - F(S)`."""
    gain = 0
    for atom_key, curve in candidate.atoms:
        k = atom_counts[atom_key]
        if k < len(curve):
            gain += curve[k]
    return gain


def submodular_value(candidates: list[BriefCandidate] | tuple[BriefCandidate, ...]) -> int:
    """Exact integer coverage objective `F(S)` for any subset `S` (order-independent)."""
    counts: Counter[tuple[str, Any]] = Counter()
    total = 0
    for cand in candidates:
        for atom_key, curve in cand.atoms:
            k = counts[atom_key]
            if k < len(curve):
                total += curve[k]
            counts[atom_key] = k + 1
    return total


def _apply_candidate_atoms(candidate: BriefCandidate, atom_counts: Counter[tuple[str, Any]]) -> None:
    for atom_key, _curve in candidate.atoms:
        atom_counts[atom_key] += 1


def _parent_dir_key(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else "."


def _render_candidate_line(
    role: str,
    rendered_path: str,
    row: sqlite3.Row,
    *,
    in_deg: int,
    raw_hits: int = 0,
) -> str:
    deg_note = f", callers={in_deg}" if in_deg else ""
    if role == "recall":
        return (
            f"Recall: {rendered_path}::{row['qualname']} ({row['start']}-{row['end']}, "
            f"~{row['tokens']}t, hits={raw_hits}{deg_note})"
        )
    if role == "hub":
        return f"Hub: {rendered_path}::{row['qualname']} ({row['start']}-{row['end']}, ~{row['tokens']}t{deg_note})"
    return f"Entry: {rendered_path}::{row['qualname']} ({row['start']}-{row['end']}, ~{row['tokens']}t)"


def _line_cost(line: str) -> int:
    c_est = symbol_index._count(line + "\n")
    if tokens.backend_info().get("exact_reference"):
        return max(1, max(c_est, tokens.count_tokens(line + "\n")))
    return max(1, c_est)


def _make_candidate(
    role: str,
    row: sqlite3.Row,
    *,
    rendered_path: str,
    in_files: set[str],
    out_files: set[str],
    hop_sids: set[int],
    raw_hits: int = 0,
    recency_score: int = 0,
) -> BriefCandidate:
    sid = int(row["id"])
    path = str(row["path"])
    is_aux = _is_aux_path(path)
    in_deg = len(in_files)
    sym_tok = int(row["tokens"] or 0)
    if role == "hub":
        base = 115 * in_deg + 25 * len(out_files) + min(sym_tok, 400) // 10
    elif role == "entry":
        base = 110 * len(out_files) + 80 * in_deg + min(sym_tok, 1200) // 8
    else:
        island_bonus = 220 if in_deg <= 2 else (80 if in_deg <= 5 else 0)
        base = 140 * min(recency_score, 40) + island_bonus + min(sym_tok, 400) // 10
    if is_aux:
        base = max(1, base // 4)

    atoms: list[tuple[tuple[str, Any], tuple[int, ...]]] = [
        (("sym", (role, sid)), (max(1, base),)),
        (("mod", path), _MOD_INC_AUX if is_aux else _MOD_INC_CORE),
        (("dir", _parent_dir_key(path)), _DIR_INC),
    ]
    for f in sorted(in_files):
        atoms.append((("in_file", f), _IN_FILE_INC))
    for f in sorted(out_files):
        atoms.append((("out_file", f), _OUT_FILE_INC))
    for nid in sorted(hop_sids | {sid}):
        atoms.append((("hop", nid), _HOP_INC))

    line = _render_candidate_line(role, rendered_path, row, in_deg=in_deg, raw_hits=raw_hits)
    return BriefCandidate(
        role=role,
        sid=sid,
        path=path,
        qualname=str(row["qualname"]),
        start=int(row["start"]),
        end=int(row["end"]),
        sym_tokens=sym_tok,
        in_degree=in_deg,
        raw_hits=raw_hits,
        recency_score=recency_score,
        is_aux=is_aux,
        line=line,
        line_tokens=_line_cost(line),
        atoms=tuple(atoms),
    )


def _canonical_lines(selected: list[BriefCandidate]) -> list[str]:
    ordered = sorted(
        enumerate(selected),
        key=lambda item: (_ROLE_DISPLAY_ORDER[item[1].role], item[0]),
    )
    return [cand.line for _idx, cand in ordered]


def _selection_fits(header: list[str], selected: list[BriefCandidate], budget: int) -> bool:
    entries = _canonical_lines(selected)
    joined = "\n".join([*header, *entries])
    if not _both_within_budget(joined, budget):
        return False
    return symbol_index._assemble(header, entries, lambda _shown: [], budget=budget) == joined


def _better_density(
    gain_a: int,
    cand_a: BriefCandidate,
    gain_b: int,
    cand_b: BriefCandidate,
) -> bool:
    """Exact integer comparison of `gain / line_tokens` with deterministic tie-break."""
    lhs = gain_a * cand_b.line_tokens
    rhs = gain_b * cand_a.line_tokens
    if lhs != rhs:
        return lhs > rhs
    if gain_a != gain_b:
        return gain_a > gain_b
    key_a = (cand_a.is_aux, _ROLE_DISPLAY_ORDER[cand_a.role], cand_a.path, cand_a.start, cand_a.qualname)
    key_b = (cand_b.is_aux, _ROLE_DISPLAY_ORDER[cand_b.role], cand_b.path, cand_b.start, cand_b.qualname)
    return key_a < key_b


def _solve_submodular_knapsack(
    header: list[str],
    candidates: list[BriefCandidate],
    budget: int,
) -> list[BriefCandidate]:
    """Two-phase partition-floor + cost-normalized submodular knapsack greedy solver."""
    if not _both_within_budget("\n".join(header), budget):
        return []

    selected: list[BriefCandidate] = []
    selected_sids: set[int] = set()
    per_file: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    atom_counts: Counter[tuple[str, Any]] = Counter()

    def pick_best(allowed_roles: set[str], *, max_per_file: int) -> BriefCandidate | None:
        best: BriefCandidate | None = None
        best_gain = -1
        for cand in candidates:
            if cand.role not in allowed_roles:
                continue
            if cand.sid in selected_sids:
                continue
            if role_counts[cand.role] >= _ROLE_CAPS[cand.role]:
                continue
            if per_file[cand.path] >= max_per_file:
                continue
            if not _selection_fits(header, [*selected, cand], budget):
                continue
            gain = marginal_gain(cand, atom_counts)
            if best is None or _better_density(gain, cand, best_gain, best):
                best = cand
                best_gain = gain
        return best

    def commit(cand: BriefCandidate) -> None:
        selected.append(cand)
        selected_sids.add(cand.sid)
        per_file[cand.path] += 1
        role_counts[cand.role] += 1
        _apply_candidate_atoms(cand, atom_counts)

    # Phase 1: Interleaved partition-matroid floor reservations (`hub`, `recall`, `entry`)
    # with 1-anchor-per-module diversity so warm `Recall:` never starves `Entry:`/`Hub:`.
    max_floor = max(_ROLE_FLOORS.values())
    for _round in range(max_floor):
        for role in ("hub", "recall", "entry"):
            if role_counts[role] < _ROLE_FLOORS[role]:
                chosen = pick_best({role}, max_per_file=1)
                if chosen is not None:
                    commit(chosen)

    # Phase 2a: Global marginal-coverage-per-token knapsack fill under strict
    # 1-anchor-per-module partition matroid (`max_per_file=1`).
    all_roles = {"recall", "hub", "entry"}
    while True:
        chosen = pick_best(all_roles, max_per_file=1)
        if chosen is None:
            break
        commit(chosen)

    # Phase 2b: Residual submodular knapsack fill (`max_per_file=MAX_HUBS_PER_FILE`)
    # only after no uncovered-module candidate fits remaining token slack.
    while True:
        chosen = pick_best(all_roles, max_per_file=MAX_HUBS_PER_FILE)
        if chosen is None:
            break
        commit(chosen)

    return selected


def _finalize_brief_text(header: list[str], entries: list[str], budget: int) -> str:
    text = symbol_index._assemble(header, entries, lambda _shown: [], budget=budget)
    shown = len(entries)
    while not _both_within_budget(text, budget) and shown > 0:
        shown -= 1
        text = symbol_index._assemble(header, entries[:shown], lambda _s: [], budget=budget)
    while text and not _both_within_budget(text, budget):
        text = text[:len(text) * 4 // 5].rstrip()
    return text


def _build_brief_v1(
    idx: symbol_index.SymbolIndex,
    code_files: list[str],
    test_files: list[str],
    prod_symbols: list[sqlite3.Row],
    in_degrees: dict[int, int],
    *,
    budget: int,
    include_recall: bool,
) -> tuple[str, dict[str, Any]]:
    """Frozen v1 baseline (PR #36): fixed degree sort + sequential concatenation."""
    ranked_hubs = sorted(
        (r for r in prod_symbols if _eligible_hub(r, in_degrees.get(r["id"], 0))),
        key=lambda r: (
            _is_aux_path(r["path"]),
            -in_degrees.get(r["id"], 0),
            -min(int(r["tokens"] or 0), 400),
            r["path"],
            r["start"],
            r["qualname"],
        ),
    )
    hubs: list[sqlite3.Row] = []
    per_file: Counter[str] = Counter()
    for r in ranked_hubs:
        if per_file[r["path"]] >= MAX_HUBS_PER_FILE:
            continue
        hubs.append(r)
        per_file[r["path"]] += 1
        if len(hubs) >= MAX_HUBS:
            break

    if not hubs:
        fallback_syms = sorted(
            (r for r in prod_symbols if (r["tokens"] or 0) >= 15 and not r["name"].startswith("_")),
            key=lambda r: (
                _is_aux_path(r["path"]),
                -min(int(r["tokens"] or 0), 400),
                r["path"],
                r["start"],
                r["qualname"],
            ),
        )
        for r in fallback_syms:
            if per_file[r["path"]] >= MAX_HUBS_PER_FILE:
                continue
            hubs.append(r)
            per_file[r["path"]] += 1
            if len(hubs) >= min(6, MAX_HUBS):
                break

    hub_ids = {r["id"] for r in hubs}
    has_core_hubs = any(not _is_aux_path(r["path"]) for r in hubs)
    entry_candidates = sorted(
        (
            r for r in prod_symbols
            if r["id"] not in hub_ids
            and r["kind"] == "function"
            and "." not in r["qualname"]
            and r["name"] in _ENTRYPOINT_NAMES
            and (r["tokens"] or 0) >= 10
            and (not has_core_hubs or not _is_aux_path(r["path"]))
        ),
        key=lambda r: (
            _is_aux_path(r["path"]),
            r["path"].count("/"),
            -in_degrees.get(r["id"], 0),
            r["path"],
            r["start"],
            r["qualname"],
        ),
    )
    entrypoints = entry_candidates[:MAX_ENTRYPOINTS]

    recall_pairs = load_recall_counts(idx.root, idx) if include_recall else []
    top3_hub_ids = {r["id"] for r in hubs[:3]}
    recall_selected: list[tuple[sqlite3.Row, int]] = []
    for row, hits in recall_pairs:
        if row["id"] in top3_hub_ids and len(recall_pairs) > MAX_RECALL:
            continue
        recall_selected.append((row, hits))
        if len(recall_selected) >= MAX_RECALL:
            break
    recall_ids = {row["id"] for row, _ in recall_selected}

    header = [
        "[TokenMaster repo brief: jump directly with read_symbol(path::Symbol) or impact(path::Symbol); "
        "skip broad glob/rg orientation]",
        _layout_line(code_files, test_files, separate_aux=False),
    ]
    entries: list[str] = []
    for row, hits in recall_selected:
        deg = in_degrees.get(row["id"], 0)
        deg_note = f", callers={deg}" if deg else ""
        entries.append(
            f"Recall: {row['path']}::{row['qualname']} ({row['start']}-{row['end']}, ~{row['tokens']}t, "
            f"hits={hits}{deg_note})"
        )
    core_hubs = [r for r in hubs if r["id"] not in recall_ids]
    for r in core_hubs[:4]:
        deg = in_degrees.get(r["id"], 0)
        deg_note = f", callers={deg}" if deg else ""
        entries.append(f"Hub: {r['path']}::{r['qualname']} ({r['start']}-{r['end']}, ~{r['tokens']}t{deg_note})")
    for r in entrypoints:
        if r["id"] not in recall_ids:
            entries.append(f"Entry: {r['path']}::{r['qualname']} ({r['start']}-{r['end']}, ~{r['tokens']}t)")
    for r in core_hubs[4:]:
        deg = in_degrees.get(r["id"], 0)
        deg_note = f", callers={deg}" if deg else ""
        entries.append(f"Hub: {r['path']}::{r['qualname']} ({r['start']}-{r['end']}, ~{r['tokens']}t{deg_note})")

    text = _finalize_brief_text(header, entries, budget)
    emitted_lines = text.splitlines()[2:] if len(text.splitlines()) >= 2 else []
    emitted_hubs = sum(1 for ln in emitted_lines if ln.startswith("Hub: "))
    emitted_entries = sum(1 for ln in emitted_lines if ln.startswith("Entry: "))
    emitted_recall = sum(1 for ln in emitted_lines if ln.startswith("Recall: "))
    exact_tok = tokens.count_tokens(text) if tokens.backend_info().get("exact_reference") else symbol_index._count(text)
    est_tok = symbol_index._count(text)
    meta = {
        "schema_version": BRIEF_SCHEMA,
        "algorithm": "v1",
        "root_prefix": "",
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "tokens": exact_tok,
        "estimated_tokens": est_tok,
        "token_budget": budget,
        "source_fingerprint": _source_fingerprint(idx.root, idx),
        "code_files": len(code_files),
        "hub_count": emitted_hubs,
        "entrypoint_count": emitted_entries,
        "recall_count": emitted_recall,
        "include_recall": bool(include_recall),
    }
    return text, meta


def _resolve_algorithm(algorithm: str | None) -> str:
    chosen = (algorithm or os.environ.get("TOKENMASTER_BRIEF_ALGORITHM") or DEFAULT_ALGORITHM).strip().lower()
    if chosen not in ALGORITHMS:
        raise ValueError(f"algorithm must be one of {ALGORITHMS}, got {algorithm!r}")
    return chosen


def build_brief(
    root: Path,
    *,
    index: symbol_index.SymbolIndex | None = None,
    budget: int = BRIEF_BUDGET,
    include_recall: bool = True,
    algorithm: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Synthesize a deterministic, `<= budget`-token repository brief and metadata receipt."""
    if type(budget) is not int or budget <= 0:
        raise ValueError("budget must be a positive int")
    algo = _resolve_algorithm(algorithm)
    own_index = index is None
    idx = symbol_index.SymbolIndex(root) if own_index else index
    assert idx is not None
    try:
        idx.refresh()
        all_files = [r["path"] for r in idx.db.execute("SELECT path FROM files ORDER BY path")]
        code_files = [p for p in all_files if _is_code_file(p) and not symbol_index._is_test(p)]
        test_files = [p for p in all_files if _is_code_file(p) and symbol_index._is_test(p)]
        if not code_files:
            meta = {
                "schema_version": BRIEF_SCHEMA,
                "algorithm": algo,
                "root_prefix": "",
                "sha256": None,
                "tokens": 0,
                "estimated_tokens": 0,
                "token_budget": budget,
                "source_fingerprint": _source_fingerprint(idx.root, idx),
                "code_files": 0,
                "hub_count": 0,
                "entrypoint_count": 0,
                "recall_count": 0,
                "covered_modules": 0,
                "objective_value": 0,
                "include_recall": bool(include_recall),
            }
            return "", meta

        prod_symbols, caller_files, callee_files, file_callee_files, neighbors_1hop = _call_graph_topology(idx)
        in_degrees = {sid: len(files) for sid, files in caller_files.items() if files}
        if algo == "v1":
            return _build_brief_v1(
                idx,
                code_files,
                test_files,
                prod_symbols,
                in_degrees,
                budget=budget,
                include_recall=include_recall,
            )

        # --- R1: Submodular Graph-Coverage Knapsack + Partition Role Floors + Lossless @root Folding ---
        core_files = [p for p in code_files if not _is_aux_path(p)]
        effective_core = core_files or code_files
        core_prefix = _common_code_prefix(effective_core)
        has_core_symbols = any(not _is_aux_path(r["path"]) for r in prod_symbols)

        eligible_hub_rows = [
            r for r in prod_symbols
            if _eligible_hub(r, in_degrees.get(r["id"], 0))
            and (not has_core_symbols or not _is_aux_path(r["path"]))
        ]
        if not eligible_hub_rows:
            eligible_hub_rows = sorted(
                (
                    r for r in prod_symbols
                    if (r["tokens"] or 0) >= 15
                    and not r["name"].startswith("_")
                    and (not has_core_symbols or not _is_aux_path(r["path"]))
                ),
                key=lambda r: (-min(int(r["tokens"] or 0), 400), r["path"], r["start"], r["qualname"]),
            )[:12]
        else:
            eligible_hub_rows = sorted(
                eligible_hub_rows,
                key=lambda r: (
                    _is_aux_path(r["path"]),
                    -in_degrees.get(r["id"], 0),
                    -len(callee_files.get(r["id"], ())),
                    -min(int(r["tokens"] or 0), 400),
                    r["path"],
                    r["start"],
                    r["qualname"],
                ),
            )[:28]

        def _entry_out_files(r: sqlite3.Row) -> set[str]:
            direct = set(callee_files.get(r["id"], set()))
            if not direct:
                return set()
            return direct | set(file_callee_files.get(r["path"], set()))

        eligible_entry_rows = sorted(
            (
                r for r in prod_symbols
                if r["kind"] == "function"
                and "." not in r["qualname"]
                and r["name"] in _ENTRYPOINT_NAMES
                and (r["tokens"] or 0) >= 10
                and (not has_core_symbols or not _is_aux_path(r["path"]))
            ),
            key=lambda r: (
                _is_aux_path(r["path"]),
                -len(callee_files.get(r["id"], ())),
                -len(_entry_out_files(r)),
                r["path"].count("/"),
                -min(int(r["tokens"] or 0), 1200),
                r["path"],
                r["start"],
                r["qualname"],
            ),
        )[:16]

        # Top-4 distinct-module structural hubs are already anchored by the `Hub:` pool;
        # de-prioritize them in `Recall:` when non-hub recall candidates exist.
        top_hub_sids: set[int] = set()
        seen_hub_mods: set[str] = set()
        for r in eligible_hub_rows:
            if r["path"] not in seen_hub_mods:
                seen_hub_mods.add(r["path"])
                top_hub_sids.add(int(r["id"]))
                if len(top_hub_sids) >= 4:
                    break

        raw_recall_scored = load_recall_scores(idx.root, idx) if include_recall else []
        non_top_recall = [it for it in raw_recall_scored if int(it[0]["id"]) not in top_hub_sids]
        top_overlap_recall = [it for it in raw_recall_scored if int(it[0]["id"]) in top_hub_sids]
        if len(non_top_recall) >= MAX_RECALL:
            recall_scored = non_top_recall[:16]
        else:
            recall_scored = [*non_top_recall, *top_overlap_recall[: MAX_RECALL - len(non_top_recall)]]

        # Pre-check 1-step `SymbolIndex._paths` uniqueness for stripped paths under `core_prefix`.
        unique_stripped_by_path: dict[str, bool] = {}
        if core_prefix:
            prefix_slash = core_prefix + "/"
            candidate_paths = {
                *(r["path"] for r in eligible_hub_rows),
                *(r["path"] for r in eligible_entry_rows),
                *(row["path"] for row, _h, _s in recall_scored),
            }
            for p in candidate_paths:
                if p.startswith(prefix_slash):
                    stripped = p[len(prefix_slash):]
                    unique_stripped_by_path[p] = bool(stripped) and idx._paths(stripped) == [p]
                else:
                    unique_stripped_by_path[p] = False

        layout_str = _layout_line(code_files, test_files, separate_aux=True)

        def build_pool_and_solve(active_prefix: str) -> tuple[list[str], list[BriefCandidate], int]:
            if active_prefix:
                hdr = [
                    f"[TokenMaster repo brief (@root={active_prefix}/): jump directly with "
                    "read_symbol(path::Symbol) or impact(path::Symbol); skip broad glob/rg orientation]",
                    layout_str,
                ]
            else:
                hdr = [
                    "[TokenMaster repo brief: jump directly with read_symbol(path::Symbol) or "
                    "impact(path::Symbol); skip broad glob/rg orientation]",
                    layout_str,
                ]

            pool: list[BriefCandidate] = []
            for row, raw_hits, rec_score in recall_scored:
                rp = fold_brief_path(active_prefix, row["path"], unique_stripped_by_path.get(row["path"], False))
                pool.append(
                    _make_candidate(
                        "recall",
                        row,
                        rendered_path=rp,
                        in_files=caller_files.get(row["id"], set()),
                        out_files=callee_files.get(row["id"], set()),
                        hop_sids=neighbors_1hop.get(row["id"], set()),
                        raw_hits=raw_hits,
                        recency_score=rec_score,
                    )
                )
            for row in eligible_hub_rows:
                rp = fold_brief_path(active_prefix, row["path"], unique_stripped_by_path.get(row["path"], False))
                pool.append(
                    _make_candidate(
                        "hub",
                        row,
                        rendered_path=rp,
                        in_files=caller_files.get(row["id"], set()),
                        out_files=callee_files.get(row["id"], set()),
                        hop_sids=neighbors_1hop.get(row["id"], set()),
                    )
                )
            for row in eligible_entry_rows:
                rp = fold_brief_path(active_prefix, row["path"], unique_stripped_by_path.get(row["path"], False))
                ent_out = _entry_out_files(row)
                pool.append(
                    _make_candidate(
                        "entry",
                        row,
                        rendered_path=rp,
                        in_files=caller_files.get(row["id"], set()),
                        out_files=ent_out,
                        hop_sids=neighbors_1hop.get(row["id"], set()),
                    )
                )
            chosen = _solve_submodular_knapsack(hdr, pool, budget)
            return hdr, chosen, submodular_value(chosen)

        header_unfactored, selected_unfactored, val_unfactored = build_pool_and_solve("")
        active_root_prefix = ""
        header = header_unfactored
        selected = selected_unfactored
        obj_value = val_unfactored

        # Activate `@root=<core_prefix>/` iff factoring strictly increases packed submodular coverage F(S).
        if core_prefix and _line_cost(core_prefix + "/") >= 3:
            header_factored, selected_factored, val_factored = build_pool_and_solve(core_prefix)
            if val_factored > val_unfactored:
                active_root_prefix = core_prefix
                header = header_factored
                selected = selected_factored
                obj_value = val_factored

        entries = _canonical_lines(selected)
        text = _finalize_brief_text(header, entries, budget)
        emitted_lines = text.splitlines()[2:] if len(text.splitlines()) >= 2 else []
        emitted_hubs = sum(1 for ln in emitted_lines if ln.startswith("Hub: "))
        emitted_entries = sum(1 for ln in emitted_lines if ln.startswith("Entry: "))
        emitted_recall = sum(1 for ln in emitted_lines if ln.startswith("Recall: "))
        covered_mods = len({cand.path for cand in selected[: len(emitted_lines)]})

        exact_tok = tokens.count_tokens(text) if tokens.backend_info().get("exact_reference") else symbol_index._count(text)
        est_tok = symbol_index._count(text)
        meta = {
            "schema_version": BRIEF_SCHEMA,
            "algorithm": "r1",
            "root_prefix": active_root_prefix,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "tokens": exact_tok,
            "estimated_tokens": est_tok,
            "token_budget": budget,
            "source_fingerprint": _source_fingerprint(idx.root, idx),
            "code_files": len(code_files),
            "hub_count": emitted_hubs,
            "entrypoint_count": emitted_entries,
            "recall_count": emitted_recall,
            "covered_modules": covered_mods,
            "objective_value": obj_value,
            "include_recall": bool(include_recall),
        }
        return text, meta
    finally:
        if own_index:
            idx.close()


def write_brief(
    root: Path,
    *,
    index: symbol_index.SymbolIndex | None = None,
    budget: int = BRIEF_BUDGET,
    include_recall: bool = True,
    algorithm: str | None = None,
) -> dict[str, Any]:
    """Build and atomically write `.token-master/brief.md` and `.token-master/brief.json`."""
    text, meta = build_brief(
        root,
        index=index,
        budget=budget,
        include_recall=include_recall,
        algorithm=algorithm,
    )
    brief_path = root / BRIEF_PATH
    meta_path = root / BRIEF_META_PATH
    if text:
        _atomic_write_bytes(brief_path, (text + "\n").encode("utf-8"))
    elif brief_path.is_file() and not brief_path.is_symlink():
        brief_path.unlink()
    _atomic_write_bytes(meta_path, (json.dumps(meta, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return meta
