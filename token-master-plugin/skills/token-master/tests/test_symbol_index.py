"""Graph-first navigation index: exact ranges, compact tools, graphify call edges."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from brainspace import symbol_index, tokens
from brainspace.symbol_index import SymbolIndex, _json_keys, _markdown, _python, dispatch

PY = '''"""Module."""
LIMIT = 5


def helper(x):
    return x + LIMIT


@decorator
def entry(items):
    def inner(y):
        return helper(y)
    return [inner(i) for i in items]


class Store:
    """Keeps things."""
    SIZE = 3

    def save(self, value):
        return helper(value)

    def load(self):
        return self.save(entry([1]))


if True:
    def late():
        return Store().load()
'''
NODES = [{"id": "h", "label": "helper()", "source_file": "pkg/core.py", "source_location": "L5"},
         {"id": "s", "label": ".save()", "source_file": "pkg/core.py", "source_location": "L20"},
         {"id": "l", "label": ".load()", "source_file": "pkg/core.py", "source_location": "L23"},
         {"id": "t", "label": "test_save()", "source_file": "tests/test_core.py", "source_location": "L3"}]
LINKS = [{"source": "s", "target": "h", "relation": "calls", "confidence": "EXTRACTED", "source_location": "L21"},
         {"source": "t", "target": "s", "relation": "calls", "confidence": "INFERRED", "source_location": "L4"},
         {"source": "l", "target": "s", "relation": "imports", "source_location": "L23"}]


def _repo(root: Path) -> Path:
    (root / "pkg").mkdir(parents=True)
    (root / "pkg/core.py").write_text(PY, encoding="utf-8")
    (root / "pkg/other.py").write_text("from .core import helper\n\n\ndef helper2():\n    return helper(2)\n",
                                       encoding="utf-8")
    (root / "docs.md").write_text("# Guide\n\nIntro.\n\n## Setup\n\n```\n# not a heading\n```\n\n## Usage\n\nRun.\n",
                                  encoding="utf-8")
    (root / "config.json").write_text(json.dumps({"service": "gw", "limits": {"max": 5, "timeout": 30},
                                                  "routes": [1, 2]}, indent=2), encoding="utf-8")
    return root


def _graph(root: Path, sources: dict | None = None) -> None:
    graph = {"nodes": NODES, "links": LINKS}
    if sources is not None:
        graph["token_master_index"] = {"sources": sources}
    (root / ".token-master").mkdir(exist_ok=True)
    (root / ".token-master/graph.json").write_text(json.dumps(graph), encoding="utf-8")


def test_python_symbols_have_exact_ranges_kinds_and_call_forms():
    symbols = {s["qualname"]: s for s in _python(PY)}
    assert symbols["LIMIT"]["kind"] == symbols["Store.SIZE"]["kind"] == "constant"
    assert (symbols["entry"]["start"], symbols["entry"]["line"], symbols["entry"]["end"]) == (9, 10, 13)
    assert symbols["entry.inner"]["kind"] == "function" and symbols["Store.save"]["kind"] == "method"
    assert (symbols["late"]["kind"], symbols["late"]["start"]) == ("function", 28)  # defined under `if`
    assert [c[:2] for c in symbols["entry"]["calls"]] == [("inner", "bare")]  # helper() belongs to inner
    assert [c[:3] for c in symbols["Store.load"]["calls"]] == [("save", "self", "self"), ("entry", "bare", "")]
    assert [c[:3] for c in symbols["late"]["calls"]] == [("load", "attr", ""), ("Store", "bare", "")]
    assert symbols["Store"]["signature"] == "class Store:"


def test_markdown_sections_skip_fenced_lines_and_nest():
    text = "# Guide\n\nIntro.\n\n## Setup\n\n```\n# not a heading\n```\n\n## Usage\n\nRun.\n\n# C# notes ##\n"
    sections = {s["qualname"]: (s["start"], s["end"]) for s in _markdown(text)}
    assert sections == {"Guide": (1, 14), "Guide > Setup": (5, 10), "Guide > Usage": (11, 14), "C# notes": (15, 15)}


def test_json_keys_cover_two_levels_with_ranges_and_values():
    text = json.dumps({"service": "gw", "limits": {"max": 5, "timeout": 30}, "routes": [1, 2]}, indent=2)
    keys = {k["qualname"]: (k["start"], k["end"], k["signature"]) for k in _json_keys(text)}
    assert keys == {"service": (2, 2, '"service": "gw",'), "limits": (3, 6, '"limits": {'),
                    "limits.max": (4, 4, '"max": 5,'), "limits.timeout": (5, 6, '"timeout": 30'),
                    "routes": (7, 11, '"routes": [')}
    assert [k["qualname"] for k in _json_keys('[{"a": 1}, {"b": 2, "c": 3}]')] == ["a", "b", "c"]
    tricky = '{"k": "a{b:c,\\"d}", "m": {"n": "x", "o": {"deep": 1}}, "e": {}}'
    assert [k["qualname"] for k in _json_keys(tricky)] == ["k", "m", "m.n", "m.o", "e"]


def test_locate_and_read_symbol_resolve_names_paths_and_ranges(tmp_path: Path):
    index = SymbolIndex(_repo(tmp_path))
    try:
        assert "pkg/core.py:5-6 function helper ~" in dispatch(index, "locate", {"query": "helper"})
        for query in ("Store.save", "core.Store.save", "pkg.core.Store.save"):
            assert "pkg/core.py:20-21 method Store.save ~" in dispatch(index, "locate", {"query": query})
        assert "docs.md:11-13 section Guide > Usage ~" in dispatch(index, "locate", {"query": "Usage"})
        located = dispatch(index, "locate", {"query": "max"})
        assert "config.json:4-4 key limits.max ~" in located and located.endswith('| "max": 5,')
        outline = dispatch(index, "locate", {"query": str(tmp_path / "pkg" / "core.py")})
        assert outline.startswith("pkg/core.py: 9 symbols, 29 lines, ~") and "\n16-24 class Store ~" in outline
        assert dispatch(index, "locate", {"query": "core.py"}) == outline  # unique trailing path
        assert dispatch(index, "read_symbol", {"target": "core.py::Store.save"}).splitlines() == [
            "pkg/core.py::Store.save (20-21):", "20.     def save(self, value):", "21.         return helper(value)"]
        assert dispatch(index, "read_symbol", {"target": "pkg\\core.py:1-2"}).splitlines()[1:] == [
            '1. """Module."""', "2. LIMIT = 5"]
        assert dispatch(index, "read_symbol", {"target": "core.helper"}).startswith("pkg/core.py::helper (5-6):")
        assert dispatch(index, "read_symbol", {"target": "other.py"}).splitlines()[-1] == "5.     return helper(2)"
        assert dispatch(index, "read_symbol", {"target": "config.json::limits.max"}).endswith('4.     "max": 5,')
        (tmp_path / "pkg/extra.py").write_text("def helper():\n    return 0\n\n\nclass Box:\n    def entry(self):\n"
                                               "        return 1\n", encoding="utf-8")
        assert dispatch(index, "read_symbol", {"target": "helper"}).startswith('"helper" matches 2 symbols')
        assert dispatch(index, "read_symbol", {"target": "extra.py::helper"}).startswith("pkg/extra.py::helper (1-2):")
        assert dispatch(index, "read_symbol", {"target": "entry"}).endswith(
            "[1 other definition named entry, e.g. pkg/extra.py::Box.entry; use path::Name to pick one.]")
        assert dispatch(index, "impact", {"symbol": "entry"}).endswith(
            "[1 other definition named entry, e.g. pkg/extra.py::Box.entry; use path::Name to pick one.]")
        assert dispatch(index, "read_symbol", {"target": "pkg//core.py"}).startswith("pkg/core.py (1-29):")
        (tmp_path / "lib").mkdir()
        (tmp_path / "lib/core.py").write_text("X = 1\n", encoding="utf-8")
        assert dispatch(index, "read_symbol", {"target": "core.py"}).startswith('"core.py" matches 2 files; use one:')
        assert dispatch(index, "locate", {"query": "nothing_here"}).startswith("No symbol or file matches")
        assert dispatch(index, "read_symbol", {"target": "nothing_here"}).startswith("Error: no symbol")
        assert dispatch(index, "edit", {}) is None
    finally:
        index.close()


def test_reads_never_leave_the_workspace_or_enter_hidden_folders(tmp_path: Path):
    root = _repo(tmp_path / "repo")
    (tmp_path / "secret.py").write_text("TOKEN = 'leak'\n", encoding="utf-8")
    (root / ".hidden.py").write_text("def hidden_fn():\n    return 'leak'\n", encoding="utf-8")
    index = SymbolIndex(root)
    try:
        for target in ("../secret.py", "../secret.py:1-1", str(tmp_path / "secret.py"),
                       str(tmp_path / "secret.py") + ":1-1", ".token-master/symbols.sqlite",
                       ".token-master/symbols.sqlite:1-2", "pkg/../../secret.py:1-1", ".hidden.py"):
            result = dispatch(index, "read_symbol", {"target": target})
            assert result.startswith("Error") and "leak" not in result, (target, result)
        assert "leak" not in dispatch(index, "locate", {"query": "../secret.py"})
        assert dispatch(index, "locate", {"query": "hidden_fn"}).startswith("No symbol or file matches")
    finally:
        index.close()


def test_graph_paths_outside_the_workspace_are_never_read(tmp_path: Path):
    root = _repo(tmp_path / "repo")
    (tmp_path / "outside.py").write_text("def evil():\n    return 'leak'\n", encoding="utf-8")
    nodes = NODES + [{"id": "x", "label": "evil()", "source_file": "../outside.py", "source_location": "L1"},
                     {"id": "y", "label": "sneak()", "source_file": ".token-master/x.py", "source_location": "L1"}]
    links = LINKS + [{"source": "x", "target": "h", "relation": "calls", "confidence": "EXTRACTED",
                      "source_location": "L2"},
                     {"source": "y", "target": "h", "relation": "calls", "confidence": "EXTRACTED",
                      "source_location": "L1"}]
    (root / ".token-master").mkdir(exist_ok=True)
    (root / ".token-master/graph.json").write_text(json.dumps({"nodes": nodes, "links": links}), encoding="utf-8")
    (root / ".token-master/x.py").write_text("hidden = 'leak'\n", encoding="utf-8")
    index = SymbolIndex(root)
    try:
        result = dispatch(index, "impact", {"symbol": "helper"})
        assert "  ../outside.py:2 evil" in result and "leak" not in result
    finally:
        index.close()


def test_long_titles_are_found_by_their_full_text(tmp_path: Path):
    title = ("A very long section title " * 6).strip()
    (tmp_path / "doc.md").write_text(f"# {title}\n\ntext\n", encoding="utf-8")
    index = SymbolIndex(tmp_path)
    try:
        assert "doc.md:1-3 section " in dispatch(index, "locate", {"query": title})
        assert dispatch(index, "read_symbol", {"target": f"doc.md::{title}"}).endswith("3. text")
    finally:
        index.close()


def test_copied_index_is_reused_and_old_schemas_rebuild(tmp_path: Path, monkeypatch):
    first = _repo(tmp_path / "first")
    SymbolIndex(first).close()
    copy = tmp_path / "copy"
    shutil.copytree(first, copy)  # keeps mtimes, as the study copies its template

    def reparse(*_):
        raise AssertionError("an unchanged copy was re-parsed")

    monkeypatch.setattr(SymbolIndex, "_store", reparse)
    SymbolIndex(copy).close()
    monkeypatch.undo()
    db = sqlite3.connect(copy / ".token-master/symbols.sqlite")
    db.execute("PRAGMA user_version = 1")
    db.commit()
    db.close()
    index = SymbolIndex(copy)
    try:
        assert "function helper2" in dispatch(index, "locate", {"query": "helper2"})
        (copy / "pkg/other.py").unlink()
        assert dispatch(index, "locate", {"query": "helper2"}).startswith("No symbol or file matches")
    finally:
        index.close()


@pytest.mark.skipif(not tokens.backend_info()["exact_reference"], reason="needs the verified cl100k vocabulary")
def test_every_result_stays_inside_the_budget(tmp_path: Path):
    methods = "".join(f"    def method_{n}(self, value):\n        return helper(value) + {n}\n\n" for n in range(400))
    (tmp_path / "big.py").write_text("def helper(x):\n    return x\n\n\nclass Big:\n" + methods, encoding="utf-8")
    (tmp_path / "emoji.py").write_text('X = "' + "\U0001F600" * 6000 + '"\n', encoding="utf-8")
    (tmp_path / "long.md").write_text("# " + "Very long title " * 400 + "\n\n## Child\n\ntext\n", encoding="utf-8")
    index = SymbolIndex(tmp_path)
    try:
        results = {key: dispatch(index, tool, args) for key, tool, args in (
            ("class", "read_symbol", {"target": "Big"}), ("file", "read_symbol", {"target": "big.py"}),
            ("range", "read_symbol", {"target": "big.py:1-1200"}), ("outline", "locate", {"query": "big.py"}),
            ("hits", "locate", {"query": "method"}), ("callers", "impact", {"symbol": "helper", "depth": 4}),
            ("emoji", "read_symbol", {"target": "emoji.py:1-1"}), ("heading", "read_symbol", {"target": "long.md::Child"}),
            ("echo", "locate", {"query": "x" * 5000}))}
        for key, text in results.items():
            assert tokens.count_tokens(text) < 3000, (key, tokens.count_tokens(text))  # v6 cuts "other" results above
        assert "Members (read_symbol one" in results["class"] and "[Shown 5-" in results["class"]
        assert results["file"].startswith("[big.py is ~") and "\n5-1204 class Big ~" in results["file"]
        assert results["range"].endswith("for the rest.]") and "more not shown" in results["hits"]
        assert "more lines not shown" in results["callers"] and results["emoji"].endswith("[line cut]")
    finally:
        index.close()


def test_edits_are_indexed_on_the_next_call(tmp_path: Path):
    root = _repo(tmp_path)
    index = SymbolIndex(root)
    try:
        core = root / "pkg/core.py"
        core.write_text(PY + "\n\ndef added():\n    return helper(1)\n", encoding="utf-8")
        os.utime(core, ns=(core.stat().st_atime_ns, core.stat().st_mtime_ns + 1_000_000))
        assert "function added" in dispatch(index, "locate", {"query": "added"})
        assert " added | return helper(1)" in dispatch(index, "impact", {"symbol": "helper"})
    finally:
        index.close()


def test_impact_without_a_graph_matches_names_by_call_form(tmp_path: Path):
    index = SymbolIndex(_repo(tmp_path))
    try:
        assert dispatch(index, "impact", {"symbol": "helper"}).splitlines() == [
            "Callers of helper (pkg/core.py:5) (no call graph: name matches only):",
            "  pkg/core.py:12 entry.inner | return helper(y)",
            "  pkg/core.py:21 Store.save | return helper(value)",
            "  pkg/other.py:5 helper2 | return helper(2)"]
        assert dispatch(index, "impact", {"symbol": "Store.save", "depth": "2"}).splitlines()[1:] == [
            "depth 1:", "  pkg/core.py:24 Store.load | return self.save(entry([1]))",
            "depth 2:", "  pkg/core.py:29 late (calls load) | return Store().load()"]
        assert "  pkg/core.py:29 late | return Store().load()" in dispatch(index, "impact", {"symbol": "Store"})
        assert dispatch(index, "impact", {"symbol": "LIMIT"}).startswith("Error: no function, method or class")
        assert dispatch(index, "impact", {"symbol": "helper", "depth": "\u00b2"}).startswith("Callers of helper")
    finally:
        index.close()


def test_impact_merges_graph_edges_with_unresolved_name_matches(tmp_path: Path):
    root = _repo(tmp_path)
    _graph(root)
    index = SymbolIndex(root)
    try:
        assert dispatch(index, "impact", {"symbol": "helper", "depth": 2}).splitlines() == [
            "Callers of helper (pkg/core.py:5) (path:line caller | call; [inferred], [name] = unverified):",
            "depth 1:",
            "  pkg/core.py:21 Store.save | return helper(value)",  # resolved edge: unmarked, listed first
            "  pkg/core.py:12 entry.inner [name] | return helper(y)",  # missed by the graph, found by name
            "  pkg/other.py:5 helper2 [name] | return helper(2)",
            "depth 2:",
            "  pkg/core.py:13 entry (calls inner) [name] | return [inner(i) for i in items]",
            "  pkg/core.py:24 Store.load (calls save) [name] | return self.save(entry([1]))",
            "  tests/test_core.py:4 test_save (calls Store.save) [inferred]",  # tests last; imports edge ignored
        ]
    finally:
        index.close()


def test_graph_edges_from_files_edited_since_the_graph_are_dropped(tmp_path: Path):
    root = _repo(tmp_path)
    current = hashlib.sha256((root / "pkg/core.py").read_bytes()).hexdigest()
    for digest, line in ((current, "  pkg/core.py:21 Store.save | return helper(value)"),
                         ("0" * 64, "  pkg/core.py:21 Store.save [name] | return helper(value)"),
                         (None, "  pkg/core.py:21 Store.save [name] | return helper(value)")):  # edited during build
        _graph(root, {"pkg/core.py": digest})
        index = SymbolIndex(root)
        try:
            assert line in dispatch(index, "impact", {"symbol": "helper"})
        finally:
            index.close()


def test_unresolved_calls_on_unknown_objects_are_counted_per_name(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(symbol_index, "MAX_LOOSE", 0)
    index = SymbolIndex(_repo(tmp_path))
    try:
        result = dispatch(index, "impact", {"symbol": "Store.save", "depth": 2})
        assert "  pkg/core.py:24 Store.load | return self.save(entry([1]))" in result  # self.save() in Store: precise
        assert "late" not in result
        assert result.endswith("[Not listed: 1 calls to .load() on objects of unknown type; grep to check.]")
    finally:
        index.close()


def test_qualified_calls_count_as_precise(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(symbol_index, "MAX_LOOSE", 0)
    (tmp_path / "tokens.py").write_text("def count(x):\n    return 1\n\n\nclass Owner:\n    @staticmethod\n"
                                        "    def make():\n        return 1\n", encoding="utf-8")
    (tmp_path / "use.py").write_text("import tokens\n\n\nclass User:\n    def f(self, obj):\n"
                                     "        a = tokens.count(1)\n        b = self.tokens.count(3)\n"
                                     "        return a + b + obj.count(2) + tokens.Owner.make()\n", encoding="utf-8")
    index = SymbolIndex(tmp_path)
    try:
        result = dispatch(index, "impact", {"symbol": "count"})
        assert "  use.py:6 User.f | a = tokens.count(1)" in result and "use.py:7" not in result  # self.tokens: unknown
        assert result.endswith("[Not listed: 2 calls to .count() on objects of unknown type; grep to check.]")
        assert "  use.py:8 User.f | return a + b" in dispatch(index, "impact", {"symbol": "Owner.make"})
    finally:
        index.close()


def test_same_named_definitions_share_one_unresolved_count(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(symbol_index, "MAX_LOOSE", 0)
    (tmp_path / "a.py").write_text("class A:\n    def run(self):\n        return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("class B:\n    def run(self):\n        return 2\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("def go(x, y):\n    x.run()\n    return y.run()\n", encoding="utf-8")
    index = SymbolIndex(tmp_path)
    try:
        result = dispatch(index, "impact", {"symbol": "run"})
        assert result.startswith("Callers of 2 definitions of run")
        assert result.endswith("[Not listed: 2 calls to .run() on objects of unknown type; grep to check.]")
    finally:
        index.close()


def test_tool_definitions_stay_small():
    # They ride on every request; the graph tools shipped before v7 cost 1,165 tokens per call (PRS-2).
    assert tokens.estimate(json.dumps(symbol_index.TOOL_SPECS)) < 400
