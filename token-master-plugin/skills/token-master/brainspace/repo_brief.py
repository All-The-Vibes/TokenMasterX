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
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from . import symbol_index, tokens

BRIEF_DIR = Path(".token-master")
BRIEF_PATH = BRIEF_DIR / "brief.md"
BRIEF_META_PATH = BRIEF_DIR / "brief.json"
RECALL_PATH = BRIEF_DIR / "recall.jsonl"

BRIEF_SCHEMA = 1
BRIEF_BUDGET = 320
MAX_BRIEF_BYTES = 8_192
MAX_RECALL_BYTES = 262_144

MAX_AREAS = 6
MAX_HUBS = 10
MAX_HUBS_PER_FILE = 2
MAX_ENTRYPOINTS = 4
MAX_RECALL = 5

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


def load_recall_counts(root: Path, index: symbol_index.SymbolIndex) -> list[tuple[sqlite3.Row, int]]:
    """Return validated current `(symbol_row, hit_count)` pairs from `.token-master/recall.jsonl`."""
    recall_file = root / RECALL_PATH
    if not recall_file.is_file() or recall_file.is_symlink():
        return []
    counts: Counter[tuple[str, str]] = Counter()
    try:
        raw_lines = recall_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
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
                counts[(rel, qual)] += 1
    if not counts:
        return []
    validated: list[tuple[sqlite3.Row, int]] = []
    for (rel, qual), hits in counts.items():
        row = index.db.execute(
            f"SELECT {', '.join(symbol_index._COLUMNS)} FROM symbols "
            "WHERE path = ? AND qualname = ? AND kind != 'module' ORDER BY start ASC LIMIT 1",
            (rel, qual),
        ).fetchone()
        if row is not None:
            validated.append((row, hits))
    validated.sort(key=lambda item: (-item[1], item[0]["path"], item[0]["start"], item[0]["qualname"]))
    return validated


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


def _layout_line(code_paths: list[str], test_paths: list[str]) -> str:
    prefix = _common_code_prefix(code_paths)
    plen = len(prefix) + 1 if prefix else 0
    top_counts: Counter[str] = Counter()
    for p in code_paths:
        rel = p[plen:] if plen and p.startswith(prefix + "/") else p
        top_counts[rel.split("/", 1)[0] if "/" in rel else "."] += 1
    dominant = {k for k, v in top_counts.items() if k != "." and v * 2 >= len(code_paths)}
    buckets: Counter[str] = Counter()
    for p in code_paths:
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
    test_note = f"; tests: {len(test_paths)} files" if test_paths else ""
    return f"Layout ({len(code_paths)} code files{test_note}): {root_note}" + ", ".join(shown)


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


def _cross_file_caller_counts(index: symbol_index.SymbolIndex) -> dict[int, int]:
    """Count distinct non-test external caller files for each non-test symbol id."""
    prod_rows = index.db.execute(
        f"SELECT {', '.join(symbol_index._COLUMNS)} FROM symbols "
        "WHERE kind IN ('class','struct','trait','enum','function','method')"
    ).fetchall()
    prod_rows = [r for r in prod_rows if _is_code_file(r["path"]) and not symbol_index._is_test(r["path"])]
    if not prod_rows:
        return {}

    caller_files: dict[int, set[str]] = defaultdict(set)

    # 1. Graphify resolved call edges (when fresh for both endpoints).
    graph = index._graph()
    if graph is not None:
        nodes, callers_by_target, node_by_place, sources = graph
        fresh_cache: dict[str, bool] = {}
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
                            and not symbol_index._is_test(src_file)
                            and _file_unchanged_since_graph(index.root, src_file, sources, fresh_cache)):
                        caller_files[row["id"]].add(src_file)

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
        "SELECT s.path AS caller_path, c.callee AS callee, c.form AS form, c.receiver AS receiver "
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
            caller_files[target_row["id"]].add(cpath)

    # Roll up resolved external method callers to their enclosing class/struct/trait as well.
    for row in prod_rows:
        if row["kind"] == "method" and "." in row["qualname"] and caller_files.get(row["id"]):
            owner = row["qualname"].rsplit(".", 1)[0]
            cid = class_by_key.get((row["path"], owner))
            if cid is not None:
                caller_files[cid].update(caller_files[row["id"]])

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


def build_brief(
    root: Path,
    *,
    index: symbol_index.SymbolIndex | None = None,
    budget: int = BRIEF_BUDGET,
    include_recall: bool = True,
) -> tuple[str, dict[str, Any]]:
    """Synthesize a deterministic, `<= budget`-token repository brief and metadata receipt."""
    if type(budget) is not int or budget <= 0:
        raise ValueError("budget must be a positive int")
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
                "sha256": None,
                "tokens": 0,
                "estimated_tokens": 0,
                "token_budget": budget,
                "source_fingerprint": _source_fingerprint(idx.root, idx),
                "code_files": 0,
                "hub_count": 0,
                "entrypoint_count": 0,
                "recall_count": 0,
                "include_recall": bool(include_recall),
            }
            return "", meta

        in_degrees = _cross_file_caller_counts(idx)
        prod_symbols = [
            r for r in idx.db.execute(
                f"SELECT {', '.join(symbol_index._COLUMNS)} FROM symbols "
                f"WHERE kind IN ({','.join('?' * len(_HUB_KINDS))})",
                _HUB_KINDS,
            ).fetchall()
            if _is_code_file(r["path"]) and not symbol_index._is_test(r["path"])
        ]

        # Select diverse cross-file hubs (`MAX_HUBS_PER_FILE` per module), prioritizing core paths over aux dirs.
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

        # Fallback for flat/single-module repos with zero cross-file call edges: top symbols by token weight.
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

        # Select concise top-level entrypoints not already listed as hubs (skipping aux demos when core hubs exist).
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

        # Load validated cross-session recall hotspots if enabled.
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
            _layout_line(code_files, test_files),
        ]

        entries: list[str] = []
        # Place verified cross-session recall first and top 4 hubs next so budget pressure trims only tail items.
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
            entries.append(
                f"Hub: {r['path']}::{r['qualname']} ({r['start']}-{r['end']}, ~{r['tokens']}t{deg_note})"
            )
        for r in entrypoints:
            if r["id"] not in recall_ids:
                entries.append(f"Entry: {r['path']}::{r['qualname']} ({r['start']}-{r['end']}, ~{r['tokens']}t)")
        for r in core_hubs[4:]:
            deg = in_degrees.get(r["id"], 0)
            deg_note = f", callers={deg}" if deg else ""
            entries.append(
                f"Hub: {r['path']}::{r['qualname']} ({r['start']}-{r['end']}, ~{r['tokens']}t{deg_note})"
            )

        text = symbol_index._assemble(header, entries, lambda _shown: [], budget=budget)
        # Guarantee exact_reference counter (if distinct from fallback) also stays <= budget.
        shown = len(entries)
        while not _both_within_budget(text, budget) and shown > 0:
            shown -= 1
            text = symbol_index._assemble(header, entries[:shown], lambda _s: [], budget=budget)
        while text and not _both_within_budget(text, budget):
            text = text[:len(text) * 4 // 5].rstrip()

        exact_tok = tokens.count_tokens(text) if tokens.backend_info().get("exact_reference") else symbol_index._count(text)
        est_tok = symbol_index._count(text)
        meta = {
            "schema_version": BRIEF_SCHEMA,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "tokens": exact_tok,
            "estimated_tokens": est_tok,
            "token_budget": budget,
            "source_fingerprint": _source_fingerprint(idx.root, idx),
            "code_files": len(code_files),
            "hub_count": len(hubs),
            "entrypoint_count": len(entrypoints),
            "recall_count": len(recall_selected),
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
) -> dict[str, Any]:
    """Build and atomically write `.token-master/brief.md` and `.token-master/brief.json`."""
    text, meta = build_brief(root, index=index, budget=budget, include_recall=include_recall)
    brief_path = root / BRIEF_PATH
    meta_path = root / BRIEF_META_PATH
    if text:
        _atomic_write_bytes(brief_path, (text + "\n").encode("utf-8"))
    elif brief_path.is_file() and not brief_path.is_symlink():
        brief_path.unlink()
    _atomic_write_bytes(meta_path, (json.dumps(meta, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return meta
