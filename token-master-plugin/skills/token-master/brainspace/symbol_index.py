"""Graph-first code navigation for TokenMaster, built on graphify's call graph.

Symbols come from a local SQLite index with exact line ranges, one-line signatures and
token costs; graphify (``graphify update``) supplies resolved call edges:

* Python: classes, functions, methods, and module and class constants (stdlib ``ast``).
* Markdown: sections (heading to the next heading of the same or higher level).
* JSON: top-level and second-level keys, with their first line as the signature.

Three compact tools answer navigation questions in tens of tokens instead of whole-file
reads (designs borrowed from Aider's repo map, AutoCodeRover/Serena symbol reads, Cline's
definition outline and SWE-agent's capped search):

  locate(query)          matching symbols, or the outline of a file
  read_symbol(target)    one symbol, file or line range, with line numbers
  impact(symbol, depth)  callers: graphify's resolved edges first, then call sites the graph
                         did not resolve, matched by name and marked [name]

Every result stays under ``BUDGET`` tokens, so request-level shaping never cuts one.
Changed files are re-indexed on every call, and graph edges from files edited since the
graph was built are dropped (their line numbers are stale; name matches cover them).
"""
from __future__ import annotations

import ast
from collections import defaultdict
import hashlib
import itertools
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Callable, NamedTuple

from . import tokens

INDEX_PATH = Path(".token-master") / "symbols.sqlite"
GRAPH_PATH = Path(".token-master") / "graph.json"
SCHEMA_VERSION = 4
SKIP_DIRS = {"node_modules", "__pycache__", "graphify-out", "venv"}
CODE_SUFFIXES = (".py", ".pyi")
DOC_SUFFIXES = (".md", ".markdown")
DATA_SUFFIXES = (".json",)
INDEXED_SUFFIXES = CODE_SUFFIXES + DOC_SUFFIXES + DATA_SUFFIXES
MAX_FILE_BYTES = 4_000_000
BUDGET = 2400  # tokens per result; request-policy-v6 digests results of unknown tools above 3,000
MAX_HITS = 25
MAX_LOOSE = 25  # obj.name() calls on objects of unknown type listed per name before they are only counted
MAX_TITLE = 80  # characters kept from a heading or JSON key
MAX_ECHO = 100  # characters of a caller-supplied argument repeated in a result
CALLABLE = ("function", "method", "class")
_COLUMNS = ("id", "path", "start", "end", "line", "name", "qualname", "kind", "tokens", "signature")

_SCHEMA = """
CREATE TABLE files(path TEXT PRIMARY KEY, mtime_ns INTEGER, size INTEGER);
CREATE TABLE symbols(id INTEGER PRIMARY KEY, path TEXT, name TEXT, qualname TEXT, kind TEXT,
    start INTEGER, end INTEGER, line INTEGER, signature TEXT, tokens INTEGER);
CREATE TABLE calls(caller INTEGER, callee TEXT, form TEXT, receiver TEXT, line INTEGER, text TEXT);
CREATE INDEX symbols_name ON symbols(name);
CREATE INDEX symbols_qualname ON symbols(qualname);
CREATE INDEX symbols_path ON symbols(path, line);
CREATE INDEX calls_callee ON calls(callee);
"""
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+#+)?\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_NESTED = tuple(getattr(ast, name) for name in ("If", "Try", "TryStar", "ExceptHandler", "With", "AsyncWith")
                if hasattr(ast, name))


def _count(text: str) -> int:
    return tokens.estimate(text)


def _fit(lines: list[str], budget: int) -> tuple[list[str], int]:
    """The leading lines that fit in a token budget, and how many were left out."""
    used = 0
    for index, line in enumerate(lines):
        used += _count(line) + 1
        if used > budget:
            return lines[:index], len(lines) - index
    return lines, 0


def _echo(text: str) -> str:
    return text if len(text) <= MAX_ECHO else text[:MAX_ECHO - 3] + "..."


def _is_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return "/tests/" in "/" + path or name.startswith("test_") or name.endswith("_test.py")


def _module_path(path: str) -> str:
    return path.rsplit(".", 1)[0].removesuffix("/__init__")


def _in_module(path: str, module: str) -> bool:
    stem = _module_path(path)
    return stem == module or stem.endswith("/" + module)


def _like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _dotted(node) -> str:
    """a.b.c for a chain of names; "" for anything else (calls, subscripts, literals)."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    return ".".join([node.id, *reversed(parts)]) if isinstance(node, ast.Name) else ""


def _signature(lines: list[str], start: int) -> str:
    parts = []
    for line in lines[start - 1:start + 4]:
        parts.append(line.strip())
        if line.rstrip().endswith(":"):
            break
    return re.sub(r"\s+", " ", " ".join(parts))[:200]


def _symbol(name, qualname, kind, start, end, line, signature="", calls=()) -> dict[str, Any]:
    return {"name": name, "qualname": qualname, "kind": kind, "start": start, "end": end, "line": line,
            "signature": signature, "calls": list(calls)}


def _aliases(node, base: dict[str, str] | None = None) -> dict[str, str]:
    """Import aliases (`import a.b as c`, `from a import b as c`) in one scope, minus shadowed parameters."""
    out = dict(base or {})
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = node.args
        for param in (*args.posonlyargs, *args.args, *args.kwonlyargs,
                      *([args.vararg] if args.vararg else []), *([args.kwarg] if args.kwarg else [])):
            out.pop(param.arg, None)
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.Import, ast.ImportFrom)):
            for alias in child.names:
                if alias.asname:
                    out[alias.asname] = alias.name.rsplit(".", 1)[-1]
        elif isinstance(child, _NESTED):
            out = _aliases(child, out)
    return out


class _Calls(ast.NodeVisitor):
    """Call sites inside one body, excluding nested definitions (indexed separately).

    Each is (name, form, receiver, line, text); form is "bare" for name(), "self" for
    self.name() or cls.name(), and "attr" for any other obj.name(). Import aliases are
    resolved back to the imported symbol or module name.
    """

    def __init__(self, lines: list[str], aliases: dict[str, str] | None = None):
        self.lines, self.aliases, self.found = lines, aliases or {}, []

    def visit_FunctionDef(self, node):
        pass

    visit_AsyncFunctionDef = visit_ClassDef = visit_FunctionDef

    def visit_Call(self, node):
        func = node.func
        if isinstance(func, ast.Name):
            found = (self.aliases.get(func.id, func.id), "bare", "")
        elif isinstance(func, ast.Attribute):
            receiver = _dotted(func.value)
            head, dot, rest = receiver.partition(".")
            if head in self.aliases:
                receiver = self.aliases[head] + (dot + rest if dot else "")
            found = (func.attr, "self" if receiver in ("self", "cls") else "attr", receiver)
        else:
            found = None
        if found:
            self.found.append((*found, node.lineno, self.lines[node.lineno - 1].strip()[:140]))
        self.generic_visit(node)

    def body(self, node):
        for child in ast.iter_child_nodes(node):
            self.visit(child)
        return self.found


def _python(text: str) -> list[dict[str, Any]]:
    tree = ast.parse(text)
    lines = text.splitlines()
    root_aliases = _aliases(tree)
    out = [_symbol("<module>", "<module>", "module", 1, max(1, len(lines)), 1,
                   calls=_Calls(lines, root_aliases).body(tree))]

    def visit(node, prefix: str, parent_kind: str, scope_aliases: dict[str, str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qualname = f"{prefix}.{child.name}" if prefix else child.name
                kind = ("class" if isinstance(child, ast.ClassDef) else "method" if parent_kind == "class"
                        else "function")
                start = min([d.lineno for d in child.decorator_list] + [child.lineno])
                inner_aliases = _aliases(child, scope_aliases)
                out.append(_symbol(child.name, qualname, kind, start, child.end_lineno or child.lineno, child.lineno,
                                   _signature(lines, child.lineno), _Calls(lines, inner_aliases).body(child)))
                visit(child, qualname, kind, inner_aliases)
            elif isinstance(child, (ast.Assign, ast.AnnAssign)) and parent_kind in ("module", "class"):
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                for target in targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        out.append(_symbol(target.id, f"{prefix}.{target.id}" if prefix else target.id, "constant",
                                           child.lineno, child.end_lineno or child.lineno, child.lineno,
                                           lines[child.lineno - 1].strip()[:200]))
            elif isinstance(child, _NESTED):  # definitions under if/try/with keep their scope
                visit(child, prefix, parent_kind, scope_aliases)

    visit(tree, "", "module", root_aliases)
    return out


def _markdown(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    heads, fenced = [], False
    for number, line in enumerate(lines, 1):
        if _FENCE.match(line):
            fenced = not fenced
        elif not fenced and (match := _HEADING.match(line)):
            heads.append((number, len(match.group(1)), match.group(2)[:MAX_TITLE]))
    out, trail = [], []
    for index, (number, level, title) in enumerate(heads):
        end = next((n - 1 for n, lv, _ in heads[index + 1:] if lv <= level), len(lines))
        trail = [t for t in trail if t[0] < level] + [(level, title)]
        out.append(_symbol(title, " > ".join(t for _, t in trail), "section", number, end, number,
                           lines[number - 1].strip()[:200]))
    return out


def _json_keys(text: str) -> list[dict[str, Any]]:
    """Object keys at the first two nesting levels, with line ranges, from one lexical pass."""
    rows = text.splitlines()
    out: list[dict[str, Any]] = []
    stack: list[str] = []
    open_keys: list[tuple[int, dict[str, Any]]] = []  # keys whose value is still open, outermost first
    line, i, pending = 1, 0, None
    while i < len(text):
        char = text[i]
        if char == "\n":
            line += 1
        elif char == '"':
            j = i + 1
            while j < len(text) and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            pending = (text[i + 1:j][:MAX_TITLE], line) if stack and stack[-1] == "{" else None
            line += text[i:j].count("\n")
            i = j
        elif char == ":" and pending and stack and stack[-1] == "{":
            if len(stack) <= 2:
                key, key_line = pending
                parents = [entry["name"] for depth, entry in open_keys if depth < len(stack)]
                entry = _symbol(key, ".".join([*parents, key]), "key", key_line, key_line, key_line,
                                rows[key_line - 1].strip()[:200] if key_line <= len(rows) else "")
                out.append(entry)
                open_keys.append((len(stack), entry))
            pending = None
        elif char in "{[":
            stack.append(char)
            pending = None
        elif char in "}]":
            if stack:
                stack.pop()
            while open_keys and open_keys[-1][0] > len(stack):
                open_keys.pop()[1]["end"] = line
            pending = None
        elif char == ",":
            if open_keys and open_keys[-1][0] == len(stack):
                open_keys.pop()[1]["end"] = line
            pending = None
        i += 1
    for _, entry in open_keys:
        entry["end"] = line
    return out


def _parse(path: str, text: str) -> list[dict[str, Any]]:
    lowered = path.lower()
    try:
        if lowered.endswith(CODE_SUFFIXES):
            return _python(text)
        if lowered.endswith(DOC_SUFFIXES):
            return _markdown(text)
        if lowered.endswith(DATA_SUFFIXES):
            return _json_keys(text)
    except (SyntaxError, ValueError, RecursionError):
        return []
    return []


class _Site(NamedTuple):
    path: str
    line: int
    caller: sqlite3.Row | None  # the calling symbol, when it is indexed
    label: str
    flag: str  # "" resolved, " [inferred]" graph guess, " [name]" name match
    text: str
    via: str  # what this site calls, shown below depth 1
    by_name: bool


class SymbolIndex:
    def __init__(self, root: Path | str, database: Path | str | None = None):
        self.root = Path(root).resolve()
        location = Path(database) if database else self.root / INDEX_PATH
        location.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(location), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        if self.db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            self.db.executescript("DROP TABLE IF EXISTS files; DROP TABLE IF EXISTS symbols; "
                                  f"DROP TABLE IF EXISTS calls; {_SCHEMA} PRAGMA user_version = {SCHEMA_VERSION};")
        self._graph_data: tuple | None | bool = None
        self.refresh()

    def close(self) -> None:
        self.db.close()

    # ------------------------------------------------------------------ indexing
    def _files(self):
        for directory, dirs, names in os.walk(self.root):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
            for name in sorted(names):
                full = Path(directory) / name
                if name.lower().endswith(INDEXED_SUFFIXES) and not name.startswith(".") and not full.is_symlink():
                    yield full.relative_to(self.root).as_posix(), full

    def refresh(self) -> int:
        """Re-parse new or changed files and drop deleted ones; returns files re-parsed."""
        known = {row[0]: (row[1], row[2]) for row in self.db.execute("SELECT path, mtime_ns, size FROM files")}
        seen, changed = set(), 0
        for rel, full in self._files():
            seen.add(rel)
            try:
                stat = full.stat()
                if known.get(rel) == (stat.st_mtime_ns, stat.st_size):
                    continue
                text = full.read_text(encoding="utf-8", errors="replace") if stat.st_size <= MAX_FILE_BYTES else ""
            except OSError:
                continue
            self._forget(rel)
            self._store(rel, text)
            self.db.execute("INSERT OR REPLACE INTO files VALUES (?, ?, ?)", (rel, stat.st_mtime_ns, stat.st_size))
            changed += 1
        for rel in set(known) - seen:
            self._forget(rel)
            self.db.execute("DELETE FROM files WHERE path = ?", (rel,))
        self.db.commit()
        return changed

    def _store(self, rel: str, text: str) -> None:
        lines = text.splitlines()
        for symbol in _parse(rel, text):
            body = "\n".join(lines[symbol["start"] - 1:symbol["end"]])
            cursor = self.db.execute(
                "INSERT INTO symbols(path, name, qualname, kind, start, end, line, signature, tokens) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (rel, symbol["name"], symbol["qualname"], symbol["kind"], symbol["start"], symbol["end"],
                 symbol["line"], symbol["signature"], _count(body)))
            self.db.executemany("INSERT INTO calls(caller, callee, form, receiver, line, text) VALUES (?, ?, ?, ?, ?, ?)",
                                [(cursor.lastrowid, *call) for call in symbol["calls"]])

    def _forget(self, rel: str) -> None:
        self.db.execute("DELETE FROM calls WHERE caller IN (SELECT id FROM symbols WHERE path = ?)", (rel,))
        self.db.execute("DELETE FROM symbols WHERE path = ?", (rel,))

    def _graph(self):
        """graphify's call edges as (nodes, callers by target, node by (file, def line, name), source
        digests at build time); None when there is no graph."""
        if self._graph_data is None:
            self._graph_data = False
            try:
                data = json.loads((self.root / GRAPH_PATH).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
            nodes = {}
            for node in data.get("nodes", []):
                location = str(node.get("source_location") or "")
                if node.get("source_file") and location[:1] == "L" and location[1:].isdigit():
                    name = str(node.get("label", "")).strip(".").removesuffix("()")
                    nodes[node["id"]] = (node["source_file"], int(location[1:]), name)
            callers = defaultdict(list)
            for link in data.get("links", []):
                if (link.get("relation") in ("calls", "indirect_call") and link.get("source") in nodes
                        and link.get("target") in nodes):
                    location = str(link.get("source_location") or "")
                    line = int(location[1:]) if location[:1] == "L" and location[1:].isdigit() else \
                        nodes[link["source"]][1]
                    callers[link["target"]].append((link["source"], line, link.get("confidence") == "EXTRACTED"))
            stamp = data.get("token_master_index")
            sources = stamp.get("sources") if isinstance(stamp, dict) else None
            self._graph_data = (nodes, callers, {place: node_id for node_id, place in nodes.items()},
                                sources if isinstance(sources, dict) else {})
        return self._graph_data or None

    # ------------------------------------------------------------------ lookup
    def _inside(self, rel: str) -> Path | None:
        """The path for a root-relative name, unless it leaves the root or enters a hidden folder."""
        if not rel or any(part.startswith(".") for part in Path(rel).parts):
            return None
        full = (self.root / rel).resolve()
        return full if full.is_relative_to(self.root) else None

    def _relative(self, value: str) -> str:
        text = value.strip().replace("\\", "/")
        root = self.root.as_posix().rstrip("/") + "/"
        if text.lower().startswith(root.lower()):
            text = text[len(root):]
        return text.removeprefix("./").lstrip("/")

    def _paths(self, value: str) -> list[str]:
        """Indexed files matching a path exactly, else by trailing path components."""
        rel = self._relative(value)
        if not rel:
            return []
        if self.db.execute("SELECT 1 FROM files WHERE path = ?", (rel,)).fetchone():
            return [rel]
        return [row[0] for row in self.db.execute("SELECT path FROM files WHERE path LIKE ? ESCAPE '\\' ORDER BY path",
                                                  ("%/" + _like(rel),))]

    def _targets(self, value: str) -> list[str]:
        """Files a read can mean: indexed matches, else an existing visible file under the root."""
        paths = self._paths(value)
        if paths:
            return paths
        full = self._inside(self._relative(value))
        return [full.relative_to(self.root).as_posix()] if full is not None and full.is_file() else []

    def _rows(self, where: str, args: tuple, kinds: tuple[str, ...] | None = None) -> list[sqlite3.Row]:
        clause = f"kind != 'module' AND ({where})" + (f" AND kind IN ({','.join('?' * len(kinds))})" if kinds else "")
        rows = self.db.execute(f"SELECT {', '.join(_COLUMNS)} FROM symbols WHERE {clause}",
                               (*args, *(kinds or ()))).fetchall()
        return sorted(rows, key=lambda r: (_is_test(r["path"]), r["path"], r["start"]))

    def _module_rows(self, query: str, kinds) -> list[sqlite3.Row]:
        """module.name or package.module.Class.method, longest module path first."""
        parts = query.split(".")
        for cut in range(len(parts) - 1, 0, -1):
            module, rest = "/".join(parts[:cut]), ".".join(parts[cut:])
            rows = [r for r in self._rows("qualname = ?", (rest,), kinds) if _in_module(r["path"], module)]
            if rows:
                return rows
        return []

    def _find(self, query: str, broad: bool = False, kinds: tuple[str, ...] | None = None) -> list[sqlite3.Row]:
        """Symbols for path::Name, Class.method, module.name or a bare name; broad adds fuzzy matches."""
        if "::" in query:
            rel, name = (part.strip() for part in query.rsplit("::", 1))
            paths = set(self._paths(rel))
            return [r for r in self._rows("qualname = ? OR name IN (?, ?)", (name, name, name[:MAX_TITLE]), kinds)
                    if r["path"] in paths]
        steps: list[Callable[[], list[sqlite3.Row]]] = [
            lambda: self._rows("qualname = ?", (query,), kinds),
            lambda: self._module_rows(query, kinds),
            lambda: self._rows("qualname LIKE ? ESCAPE '\\'", ("%." + _like(query),), kinds),
            lambda: self._rows("name = ?", (query,), kinds),
        ]
        if broad:
            steps.insert(0, lambda: self._rows("name = ?", (query,), kinds))
            steps += [lambda: self._rows("lower(name) = lower(?)", (query,), kinds),
                      lambda: self._rows("lower(qualname) LIKE lower(?) ESCAPE '\\'", ("%" + _like(query) + "%",),
                                         kinds)]
        for step in steps:
            rows = step()
            if rows:
                return rows
        if len(query) > MAX_TITLE:  # headings and JSON keys are stored cut to MAX_TITLE characters
            return self._find(query[:MAX_TITLE], broad, kinds)
        return []

    def _others_note(self, query: str, rows: list[sqlite3.Row], kinds=None) -> str:
        """For a bare name, point at same-named symbols the lookup did not pick."""
        if any(mark in query for mark in (".", "::", "/", "\\")):
            return ""
        ids = {r["id"] for r in rows}
        others = [r for r in self._rows("name = ?", (rows[0]["name"],), kinds) if r["id"] not in ids]
        if not others:
            return ""
        return (f"[{len(others)} other definition{'s' if len(others) > 1 else ''} named {rows[0]['name']}, e.g. "
                f"{others[0]['path']}::{others[0]['qualname']}; use path::Name to pick one.]")

    # ------------------------------------------------------------------ tools
    def locate(self, query: str) -> str:
        self.refresh()
        query = (query or "").strip()
        if not query:
            return "Error: give a symbol name, Class.method, a heading, a JSON key or a file path."
        if "::" not in query and ("/" in query or "\\" in query or query.lower().endswith(INDEXED_SUFFIXES)):
            paths = self._paths(query)
            if len(paths) == 1:
                return self._outline(paths[0])
            if paths:
                return self._not_one_file(query, paths)
        rows = self._find(query, broad=True)
        if not rows:
            return f'No symbol or file matches "{_echo(query)}". Try a shorter name, or grep for text.'
        header = (f'{len(rows)} match{"es" if len(rows) != 1 else ""} for "{_echo(query)}" '
                  "(path:lines kind name ~tokens | signature):")
        entries = [f"{r['path']}:{r['start']}-{r['end']} {r['kind']} {r['qualname']} ~{r['tokens']}"
                   + (f" | {r['signature']}" if r["signature"] else "") for r in rows[:MAX_HITS]]
        shown, _ = _fit(entries, BUDGET - _count(header))
        lines = [header, *shown]
        if len(rows) > len(shown):
            lines.append(f"[{len(rows) - len(shown)} more not shown; use a more specific name.]")
        return "\n".join(lines)

    def _outline(self, rel: str) -> str:
        rows = self.db.execute("SELECT start, end, kind, qualname, tokens, signature FROM symbols WHERE path = ? "
                               "AND kind != 'module' ORDER BY start", (rel,)).fetchall()
        module = self.db.execute("SELECT tokens, end FROM symbols WHERE path = ? AND kind = 'module'", (rel,)).fetchone()
        header = (f"{rel}: {len(rows)} symbols" + (f", {module['end']} lines, ~{module['tokens']} tokens" if module else "")
                  + " (lines kind name ~tokens | signature):")
        entries = [f"{r['start']}-{r['end']} {r['kind']} {r['qualname']} ~{r['tokens']}"
                   + (f" | {r['signature']}" if r["signature"] else "") for r in rows]
        shown, hidden = _fit(entries, BUDGET - _count(header))
        lines = [header, *shown]
        if hidden:
            lines.append(f"[{hidden} more symbols from line {rows[len(shown)]['start']}; read a range or locate a name.]")
        if not rows:
            lines.append("(no symbols indexed; read a line range instead)")
        return "\n".join(lines)

    def read(self, target: str) -> str:
        self.refresh()
        target = (target or "").strip()
        if not target:
            return "Error: give path::Name, Class.method, a file path or path:start-end."
        match = re.fullmatch(r"(.+?):(\d+)(?:-(\d+))?", target)
        if match and "::" not in target:
            files = self._targets(match.group(1))
            if len(files) != 1:
                return self._not_one_file(match.group(1), files)
            start = int(match.group(2))
            return self._lines(files[0], start, int(match.group(3) or start), files[0])
        if "::" not in target:
            files = self._targets(target)
            if len(files) > 1:
                return self._not_one_file(target, files)
            if files:
                return self._lines(files[0], 1, 10**9, files[0], whole_file=True)
        rows = self._find(target)
        if not rows:
            return f'Error: no symbol "{_echo(target)}". Use locate first; targets look like path::Name or path:10-40.'
        note = self._others_note(target, rows)
        if len(rows) > 1:
            header = f'"{_echo(target)}" matches {len(rows)} symbols; read one of:'
            options, hidden = _fit([f"  {r['path']}::{r['qualname']} ({r['start']}-{r['end']})" for r in rows],
                                   BUDGET - _count(header) - _count(note))
            return "\n".join([header, *options, *([f"  [{hidden} more]"] if hidden else []), *([note] if note else [])])
        row = rows[0]
        text = self._lines(row["path"], row["start"], row["end"], f"{row['path']}::{row['qualname']}")
        return text + (f"\n{note}" if note else "")

    def _not_one_file(self, value: str, files: list[str]) -> str:
        if not files:
            return f'Error: no file "{_echo(value)}".'
        header = f'"{_echo(value)}" matches {len(files)} files; use one:'
        shown, hidden = _fit(files, BUDGET - _count(header))
        return "\n".join([header, *shown, *([f"[{hidden} more]"] if hidden else [])])

    def _lines(self, rel: str, start: int, end: int, label: str, whole_file: bool = False) -> str:
        full = self._inside(rel)
        if full is None or not full.is_file():
            return f'Error: no file "{_echo(rel)}".'
        if full.stat().st_size > MAX_FILE_BYTES:  # read only what was asked for, never all of a huge file
            end = min(end, start + 999)
            with full.open(encoding="utf-8", errors="replace") as handle:
                lines = [line.rstrip("\n") for line in itertools.islice(handle, end)]
        else:
            lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
        start, end = max(1, start), min(len(lines), end)
        if start > end:
            return f'Error: "{_echo(rel)}" has {len(lines)} lines.'
        body = [f"{n}. {lines[n - 1]}" for n in range(start, end + 1)]
        header = f"{label} ({start}-{end}):"
        total = _count("\n".join(body))
        if total + _count(header) <= BUDGET:
            return "\n".join([header, *body])
        if whole_file and self.db.execute("SELECT 1 FROM symbols WHERE path = ? AND kind != 'module'",
                                          (rel,)).fetchone():
            return f"[{rel} is ~{total} tokens; its outline follows. Read a symbol or a range.]\n" + self._outline(rel)
        header = f"{label} ({start}-{end}) is ~{total} tokens; first lines:"
        members = [f"  {r['start']}-{r['end']} {r['kind']} {r['qualname']} ~{r['tokens']}" for r in self.db.execute(
            "SELECT start, end, kind, qualname, tokens FROM symbols WHERE path = ? AND start > ? AND end <= ? "
            "AND kind != 'module' ORDER BY start", (rel, start, end))]
        members, hidden = _fit(members, BUDGET // 2)
        room = BUDGET - _count(header) - sum(_count(m) + 1 for m in members) - 60  # 60: the two footer lines
        shown, _ = _fit(body, room)
        if not shown:  # one enormous line
            cut = body[0]
            while cut and _count(cut) > room:
                cut = cut[:len(cut) * 3 // 4]
            shown = [cut + " [line cut]"]
        last = start + len(shown) - 1
        parts = [header, *shown]
        if members:
            parts += ["Members (read_symbol one, or a range path:start-end):", *members]
            if hidden:
                parts.append(f"  [{hidden} more members]")
        if last < end:
            parts.append(f"[Shown {start}-{last}. Read {rel}:{last + 1}-{end} or a member for the rest.]")
        return "\n".join(parts)

    def impact(self, symbol: str, depth: Any = 1) -> str:
        self.refresh()
        query = (symbol or "").strip()
        if not query:
            return "Error: give a function, method or class name."
        try:
            depth = min(max(int(depth), 1), 4)
        except (TypeError, ValueError):
            depth = 1
        targets = self._find(query, kinds=CALLABLE)
        if not targets:
            return f'Error: no function, method or class "{_echo(query)}". Use locate, or grep for other references.'
        graph = self._graph()
        first = targets[0]
        title = (f"Callers of {first['qualname']} ({first['path']}:{first['line']})" if len(targets) == 1
                 else f"Callers of {len(targets)} definitions of {_echo(query)}")
        legend = "path:line caller | call; [inferred], [name] = unverified" if graph else \
            "no call graph: name matches only"
        header = f"{title} ({legend}):"
        note = self._others_note(query, targets, CALLABLE)
        entries: list[str] = []
        loose: dict[str, int] = {}
        seen, texts, digests = set(), {}, {}
        visited = {r["id"] for r in targets}
        frontier = targets
        for level in range(1, depth + 1):
            found: list[_Site] = []
            for target in frontier:
                sites, hidden = self._sites(target, graph, digests)
                if hidden:
                    loose[target["name"]] = max(loose.get(target["name"], 0), hidden)
                found += sites
            found.sort(key=lambda s: (_is_test(s.path), s.by_name, s.path, s.line))
            if depth > 1:
                entries.append(f"depth {level}:")
            frontier = []
            for site in found:
                if (site.path, site.line, site.label) in seen:
                    continue
                seen.add((site.path, site.line, site.label))
                via = f" (calls {site.via})" if level > 1 or len(targets) > 1 else ""
                text = site.text or self._line_text(site.path, site.line, texts)
                entries.append(f"  {site.path}:{site.line} {site.label}{via}{site.flag}" + (f" | {text}" if text else ""))
                if site.caller is not None and site.caller["kind"] in CALLABLE and site.caller["id"] not in visited:
                    visited.add(site.caller["id"])
                    frontier.append(site.caller)
            if not frontier:
                break
        shown, hidden = _fit(entries, BUDGET - _count(header) - _count(note))
        lines = [header, *shown]
        if hidden:
            lines.append(f"[{hidden} more lines not shown; use path::Name or a lower depth.]")
        if loose:
            top = sorted(loose.items(), key=lambda item: -item[1])
            names = ", ".join(f"{count} calls to .{name}()" for name, count in top[:3])
            more = f" and {len(top) - 3} more names" if len(top) > 3 else ""
            lines.append(f"[Not listed: {names}{more} on objects of unknown type; grep to check.]")
        if not seen and not loose:
            lines.append("  none found (dynamic calls, callbacks and string dispatch are invisible; grep to be sure)")
        if note:
            lines.append(note)
        return "\n".join(lines)

    def _sites(self, target: sqlite3.Row, graph, digests: dict[str, bool]) -> tuple[list[_Site], int]:
        """Call sites of one symbol: graph edges first, then name matches the graph did not resolve.

        Also returns how many obj.name() calls on objects of unknown type were left out because
        there were more than MAX_LOOSE of them.
        """
        found: dict[tuple[str, int], _Site] = {}
        if graph:
            nodes, callers, by_place, sources = graph
            for source, line, exact in callers.get(by_place.get((target["path"], target["line"], target["name"])), []):
                path, def_line, name = nodes[source]
                if not self._unchanged(path, sources, digests):
                    continue  # edited since the graph was built: its lines are stale; name matches cover it
                caller = self._symbol_at(path, def_line, name)
                found.setdefault((path, line), _Site(path, line, caller, caller["qualname"] if caller else name,
                                                     "" if exact else " [inferred]", "", target["qualname"], False))
        method = target["kind"] == "method"
        parts = target["qualname"].split(".")
        owner = ".".join(parts[:-1]) + "."
        # module.name() for functions and classes, Owner.name() for methods
        qualifier = parts[-2] if method and len(parts) > 1 else _module_path(target["path"]).rsplit("/", 1)[-1]

        def precise(row) -> bool:
            if row["form"] == "bare":
                return True
            if row["form"] == "self":  # self.name() inside the same class
                return row["path"] == target["path"] and row["qualname"].startswith(owner)
            receiver = row["receiver"]
            return not receiver.startswith(("self.", "cls.")) and receiver.rsplit(".", 1)[-1] == qualifier

        rows = self.db.execute(
            f"SELECT {', '.join('s.' + c for c in _COLUMNS)}, c.form, c.receiver, c.line AS call_line, c.text "
            "FROM calls c JOIN symbols s ON s.id = c.caller WHERE c.callee = ? AND c.form IN (?, ?)",
            (target["name"], *(("self", "attr") if method else ("bare", "attr")))).fetchall()
        extra = [r for r in rows if (r["path"], r["call_line"]) not in found]
        sure = [r for r in extra if precise(r)]
        unsure = [r for r in extra if not precise(r)]
        hidden = len(unsure) if len(unsure) > MAX_LOOSE else 0
        for r in sure + ([] if hidden else unsure):
            found.setdefault((r["path"], r["call_line"]), _Site(r["path"], r["call_line"], r, r["qualname"],
                                                                " [name]" if graph else "", r["text"], target["name"],
                                                                True))
        return list(found.values()), hidden

    def _unchanged(self, rel: str, sources: dict, digests: dict[str, bool]) -> bool:
        """False when a file's bytes differ from those graphify indexed, or were never recorded."""
        if rel not in sources:
            return True  # an unstamped graph cannot tell
        if rel not in digests:
            full = self._inside(rel)
            try:
                digests[rel] = (sources[rel] is not None and full is not None
                                and hashlib.sha256(full.read_bytes()).hexdigest() == sources[rel])
            except OSError:
                digests[rel] = False
        return digests[rel]

    def _symbol_at(self, path: str, line: int, name: str) -> sqlite3.Row | None:
        return self.db.execute(f"SELECT {', '.join(_COLUMNS)} FROM symbols WHERE path = ? AND line = ? AND name = ?",
                               (path, line, name)).fetchone()

    def _line_text(self, rel: str, line: int, cache: dict[str, list[str]]) -> str:
        if rel not in cache:
            full = self._inside(rel)
            try:
                cache[rel] = full.read_text(encoding="utf-8", errors="replace").splitlines() \
                    if full is not None and full.is_file() else []
            except OSError:
                cache[rel] = []
        lines = cache[rel]
        return lines[line - 1].strip()[:140] if 0 < line <= len(lines) else ""


TOOL_SPECS = [
    {"type": "function", "name": "locate", "strict": False,
     "description": "Find a function, class, method, constant, Markdown section or JSON key by name, or pass a file "
                    "path to get its outline. Returns path:lines and signatures. Use this first, instead of grep, "
                    "rg, Select-String or reading whole files.",
     "parameters": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}}},
    {"type": "function", "name": "read_symbol", "strict": False,
     "description": "Read exactly one function, class, method, section or line range, with line numbers. target: "
                    "path::Name, Class.method, module.func, path or path:start-end. Use this instead of Get-Content, "
                    "cat or view to read specific code: it returns only that code.",
     "parameters": {"type": "object", "required": ["target"], "properties": {"target": {"type": "string"}}}},
    {"type": "function", "name": "impact", "strict": False,
     "description": "List who calls a function, method or class (path:line caller | call), from a resolved call graph "
                    "plus name matches. depth 1-4 (default 1) adds callers of callers. Use this instead of grep or "
                    "Select-String to find usages before changing code.",
     "parameters": {"type": "object", "required": ["symbol"],
                    "properties": {"symbol": {"type": "string"}, "depth": {"type": "integer"}}}},
]


def dispatch(index: SymbolIndex, name: str, arguments: dict[str, Any]) -> str | None:
    """Run a navigation tool; None means the name is not one of ours."""
    handlers: dict[str, Callable[[], str]] = {
        "locate": lambda: index.locate(str(arguments.get("query", ""))),
        "read_symbol": lambda: index.read(str(arguments.get("target", ""))),
        "impact": lambda: index.impact(str(arguments.get("symbol", "")), arguments.get("depth", 1)),
    }
    handler = handlers.get(name)
    return handler() if handler else None
