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
from brainspace.symbol_index import SymbolIndex, _json_keys, _markdown, _python, _rust, dispatch

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
LIB_RS = '''//! Crate docs.
pub mod store;

pub const LIMIT: usize = 5;

/// Adds the limit.
pub fn helper(x: usize) -> usize {
    x + LIMIT
}

#[inline]
pub fn entry(items: &[usize]) -> Vec<usize> {
    fn inner(y: usize) -> usize {
        helper(y)
    }
    items.iter().map(|i| inner(*i)).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn helper_adds() {
        assert_eq!(helper(1), 6);
    }
}
'''
STORE_RS = '''use crate::helper as add_limit;

#[derive(Debug, Default)]
pub struct Store {
    items: Vec<usize>,
}

pub trait Saver {
    fn save(&mut self, value: usize) -> usize;
    fn describe(&self) -> String {
        String::from("saver")
    }
}

impl Store {
    pub const SIZE: usize = 3;

    pub fn new() -> Self {
        Self { items: Vec::new() }
    }

    pub fn load(&mut self) -> usize {
        self.save(crate::entry(&[1])[0])
    }
}

impl Saver for Store {
    fn save(&mut self, value: usize) -> usize {
        self.items.push(value);
        add_limit(value)
    }
}

pub fn late() -> usize {
    Store::new().load()
}

pub fn other() -> bool {
    std::path::Path::new("y").exists()
}

pub fn through_trait(s: &mut Store) -> usize {
    Saver::save(s, 1)
}
'''
# What graphify 0.9.17 emits for these two files. It sends other()'s std::path::Path::new() to Store.new, and has no
# edge for the calls inside assert_eq!, through the alias, to crate::entry, or from the nested fn.
RUST_NODES = [{"id": "src_lib_helper", "label": "helper()", "source_file": "src/lib.rs", "source_location": "L7"},
              {"id": "src_store_store_new", "label": ".new()", "source_file": "src/store.rs", "source_location": "L18"},
              {"id": "src_store_store_load", "label": ".load()", "source_file": "src/store.rs", "source_location": "L22"},
              {"id": "src_store_store_save", "label": ".save()", "source_file": "src/store.rs", "source_location": "L28"},
              {"id": "src_store_late", "label": "late()", "source_file": "src/store.rs", "source_location": "L34"},
              {"id": "src_store_other", "label": "other()", "source_file": "src/store.rs", "source_location": "L38"},
              {"id": "src_store_through_trait", "label": "through_trait()", "source_file": "src/store.rs",
               "source_location": "L42"}]
RUST_LINKS = [{"source": source, "target": target, "relation": "calls", "confidence": "EXTRACTED",
               "source_location": line} for source, target, line in (
    ("src_store_late", "src_store_store_new", "L35"), ("src_store_other", "src_store_store_new", "L39"),
    ("src_store_late", "src_store_store_load", "L35"), ("src_store_store_load", "src_store_store_save", "L23"),
    ("src_store_through_trait", "src_store_store_save", "L43"))]


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


def _rust_repo(root: Path) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "src/lib.rs").write_text(LIB_RS, encoding="utf-8")
    (root / "src/store.rs").write_text(STORE_RS, encoding="utf-8")
    return root


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


def test_import_aliases_resolve_for_functions_classes_and_modules(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(symbol_index, "MAX_LOOSE", 0)
    (tmp_path / "auth.py").write_text("def login(req):\n    return req\n\n\nclass Guard:\n    @staticmethod\n"
                                      "    def check():\n        return True\n", encoding="utf-8")
    (tmp_path / "views.py").write_text(
        "from auth import login as auth_login, Guard as G\nimport auth as auth_mod\n\n\n"
        "def sign_in(req):\n    auth_login(req)\n    G.check()\n    return auth_mod.login(req)\n\n\n"
        "def shadowed(auth_login):\n    return auth_login(1)\n",
        encoding="utf-8",
    )
    index = SymbolIndex(tmp_path)
    try:
        login_impact = dispatch(index, "impact", {"symbol": "login"})
        assert "  views.py:6 sign_in | auth_login(req)" in login_impact
        assert "  views.py:8 sign_in | return auth_mod.login(req)" in login_impact
        assert "shadowed" not in login_impact
        check_impact = dispatch(index, "impact", {"symbol": "Guard.check"})
        assert "  views.py:7 sign_in | G.check()" in check_impact
    finally:
        index.close()


def test_rust_symbols_have_exact_ranges_kinds_and_call_forms():
    lib = {s["qualname"]: s for s in _rust(LIB_RS)}
    store = {s["qualname"]: s for s in _rust(STORE_RS)}
    assert (lib["helper"]["start"], lib["helper"]["line"], lib["helper"]["end"]) == (6, 7, 9)  # with its doc comment
    assert (lib["entry"]["start"], lib["entry"]["line"], lib["entry"]["end"]) == (11, 12, 17)  # with its attribute
    assert lib["LIMIT"]["kind"] == store["Store.SIZE"]["kind"] == "constant"
    assert [lib[q]["kind"] for q in ("entry.inner", "tests", "tests.helper_adds")] == ["function", "mod", "function"]
    assert [c[:3] for c in lib["entry"]["calls"]] == [("collect", "attr", ""), ("map", "attr", ""),
                                                      ("iter", "attr", "items"), ("inner", "bare", "")]
    assert [c[:2] for c in lib["entry.inner"]["calls"]] == [("helper", "bare")]  # not entry's
    assert [c[:2] for c in lib["tests.helper_adds"]["calls"]] == [("helper", "bare")]  # inside assert_eq!
    assert [(s["kind"], s["signature"]) for s in (store["Store"], store["Saver"], store["Saver.save"])] == [
        ("struct", "pub struct Store"), ("trait", "pub trait Saver"),
        ("method", "fn save(&mut self, value: usize) -> usize;")]
    assert (store["Store.save"]["line"], store["Store.new"]["signature"]) == (28, "pub fn new() -> Self")
    assert [store[q]["trait"] for q in ("Store.save", "Store.new", "Saver.save")] == ["Saver", "", "Saver"]
    assert [c[:3] for c in store["Store.load"]["calls"]] == [("save", "self", "self"), ("entry", "bare", "")]
    assert [c[:3] for c in store["Store.save"]["calls"]] == [("push", "attr", "self.items"), ("helper", "bare", "")]
    assert [c[:3] for c in store["late"]["calls"]] == [("load", "attr", ""), ("new", "path", "Store")]
    assert [c[:3] for c in store["Store.new"]["calls"]] == [("new", "path", "Vec")]
    assert [c[:3] for c in store["other"]["calls"]] == [("exists", "attr", ""), ("new", "path", "std.path.Path")]
    assert [c[:3] for c in store["through_trait"]["calls"]] == [("save", "path", "Saver")]
    local = _rust("fn f(x: Vec<u8>) {\n    const LOCAL: u8 = 1;\n    Vec::<u8>::with_capacity(1);\n"
                  "    x.iter().collect::<Vec<_>>();\n}\n")
    assert [s["qualname"] for s in local] == ["<module>", "f"]  # like Python, function locals are not indexed
    assert [c[:3] for c in local[1]["calls"]] == [("with_capacity", "path", "Vec"), ("collect", "attr", ""),
                                                  ("iter", "attr", "x")]
    odd = _rust("const _: () = ();\nfn draw(p: u8, Point { x, y }: Point) {}\nm! { fn defined() -> u8 { 1 } }\n")
    assert [(s["qualname"], s["signature"]) for s in odd[1:]] == [("draw", "fn draw(p: u8, Point { x, y }: Point)")]
    assert odd[0]["calls"] == []  # fn defined() inside a macro is a definition, not a call


def test_rust_locate_and_read_symbol_resolve_names_paths_and_rust_paths(tmp_path: Path):
    root = _rust_repo(tmp_path)
    (root / "target/debug").mkdir(parents=True)  # Cargo's build output is not indexed
    (root / "target/CACHEDIR.TAG").write_text("Signature: 8a477f597d28d172789f06886806bc55\n", encoding="utf-8")
    (root / "target/debug/generated.rs").write_text("pub fn helper() {}\n", encoding="utf-8")
    (root / "src/util").mkdir()
    (root / "src/util/mod.rs").write_text("pub fn clamp(x: usize) -> usize {\n    x\n}\n", encoding="utf-8")
    index = SymbolIndex(root)
    try:
        located = dispatch(index, "locate", {"query": "helper"})
        assert located.startswith('1 match for "helper"') and "\nsrc/lib.rs:6-9 function helper ~" in located
        assert "src/util/mod.rs:1-3 function clamp ~" in dispatch(index, "locate", {"query": "util::clamp"})
        for query in ("Store.save", "store.Store.save", "Store::save", "crate::store::Store::save"):
            assert "src/store.rs:28-31 method Store.save ~" in dispatch(index, "locate", {"query": query}), query
        outline = dispatch(index, "locate", {"query": "store.rs"})
        assert outline.startswith("src/store.rs: 11 symbols, 44 lines, ~")
        assert "\n3-6 struct Store ~" in outline and "\n9-9 method Saver.save ~" in outline
        store_new = dispatch(index, "read_symbol", {"target": "store.rs::Store.new"})
        assert store_new.splitlines() == [
            "src/store.rs::Store.new (18-20):", "18.     pub fn new() -> Self {",
            "19.         Self { items: Vec::new() }", "20.     }"]
        for target in ("Store::new", "src/store.rs::Store::new"):
            assert dispatch(index, "read_symbol", {"target": target}) == store_new, target
        # src/store names a path, not an indexed file: an error, not a guess from the rest of the target
        assert dispatch(index, "read_symbol", {"target": "src/store::Store::new"}).startswith("Error: no symbol")
        assert dispatch(index, "read_symbol", {"target": "tests::helper_adds"}).startswith(
            "src/lib.rs::tests.helper_adds (23-26):")
        assert dispatch(index, "read_symbol", {"target": "helper"}).splitlines()[:2] == [
            "src/lib.rs::helper (6-9):", "6. /// Adds the limit."]
    finally:
        index.close()


def test_rust_impact_matches_names_through_macros_aliases_and_paths(tmp_path: Path):
    index = SymbolIndex(_rust_repo(tmp_path))
    try:
        assert dispatch(index, "impact", {"symbol": "helper"}).splitlines() == [
            "Callers of helper (src/lib.rs:7) (no call graph: name matches only):",
            "  src/lib.rs:14 entry.inner | helper(y)",
            "  src/lib.rs:25 tests.helper_adds | assert_eq!(helper(1), 6);",
            "  src/store.rs:30 Store.save | add_limit(value)"]  # use crate::helper as add_limit
        assert dispatch(index, "impact", {"symbol": "Store::save", "depth": 2}).splitlines()[1:] == [
            "depth 1:", "  src/store.rs:23 Store.load | self.save(crate::entry(&[1])[0])",
            "  src/store.rs:43 through_trait | Saver::save(s, 1)",  # through a trait: may be this impl
            "depth 2:", "  src/store.rs:35 late (calls load) | Store::new().load()"]
        assert dispatch(index, "impact", {"symbol": "Store.new"}).splitlines()[1:] == [
            "  src/store.rs:35 late | Store::new().load()"]  # Vec::new() and std::path::Path::new() are other types'
        assert dispatch(index, "impact", {"symbol": "entry"}).splitlines()[1:] == [
            "  src/store.rs:23 Store.load | self.save(crate::entry(&[1])[0])"]
        assert dispatch(index, "impact", {"symbol": "Store"}).startswith("Error: no function, method or class")
    finally:
        index.close()


def test_rust_impact_merges_graphify_edges_with_name_matches(tmp_path: Path):
    root = _rust_repo(tmp_path)
    (root / ".token-master").mkdir()
    (root / ".token-master/graph.json").write_text(json.dumps({"nodes": RUST_NODES, "links": RUST_LINKS}),
                                                   encoding="utf-8")
    index = SymbolIndex(root)
    try:
        assert dispatch(index, "impact", {"symbol": "Store.save", "depth": 2}).splitlines() == [
            "Callers of Store.save (src/store.rs:28) (path:line caller | call; [inferred], [name] = unverified):",
            "depth 1:",
            "  src/store.rs:23 Store.load | self.save(crate::entry(&[1])[0])",  # graphify's edge: unmarked
            "  src/store.rs:43 through_trait [inferred] | Saver::save(s, 1)",  # any Saver may be called
            "depth 2:",
            "  src/store.rs:35 late (calls Store.load) | Store::new().load()"]
        assert dispatch(index, "impact", {"symbol": "helper"}).splitlines()[1:] == [
            "  src/lib.rs:14 entry.inner [name] | helper(y)",
            "  src/lib.rs:25 tests.helper_adds [name] | assert_eq!(helper(1), 6);",
            "  src/store.rs:30 Store.save [name] | add_limit(value)"]
        assert dispatch(index, "impact", {"symbol": "Store.new"}).splitlines()[1:] == [
            "  src/store.rs:35 late | Store::new().load()"]  # graphify's other() edge names std::path::Path
    finally:
        index.close()


def test_rust_impact_marks_graph_edges_whose_path_leads_elsewhere(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(symbol_index, "MAX_LOOSE", 0)  # list precise name matches only
    (tmp_path / "src").mkdir()
    (tmp_path / "src/error.rs").write_text(
        "use std::io::{self, Write};\n\npub struct Error;\n\nimpl Error {\n    pub fn new() -> Self {\n        Error\n"
        "    }\n}\n\n"
        'pub fn wrap() -> io::Error {\n    io::Error::new(io::ErrorKind::Other, "x")\n}\n\n'
        "pub fn make() -> Error {\n    Error::new()\n}\n\npub fn qualified() -> Error {\n    crate::error::Error::new()\n}\n\n"
        "pub fn from_dep() -> dep::Error {\n    dep::Error::new()\n}\n", encoding="utf-8")
    (tmp_path / "src/items.rs").write_text(
        "pub mod inner {\n    pub struct Item;\n\n    impl Item {\n        pub fn new() -> Self {\n            Item\n"
        "        }\n    }\n}\n\npub fn item() -> inner::Item {\n    inner::Item::new()\n}\n", encoding="utf-8")
    # graphify 0.9.17's edges for these files, all EXTRACTED: it also sends std's io::Error::new() and a dependency's
    # dep::Error::new() to the crate's Error::new(), and has no edge (nor a node) for item()
    nodes = [{"id": node, "label": label, "source_file": "src/error.rs", "source_location": location}
             for node, label, location in (("new", ".new()", "L6"), ("wrap", "wrap()", "L11"), ("make", "make()", "L15"),
                                           ("qualified", "qualified()", "L19"), ("from_dep", "from_dep()", "L23"))]
    nodes.append({"id": "item_new", "label": ".new()", "source_file": "src/items.rs", "source_location": "L5"})
    links = [{"source": source, "target": "new", "relation": "calls", "confidence": "EXTRACTED", "source_location": line}
             for source, line in (("from_dep", "L24"), ("make", "L16"), ("qualified", "L20"), ("wrap", "L12"))]
    (tmp_path / ".token-master").mkdir()
    (tmp_path / ".token-master/graph.json").write_text(json.dumps({"nodes": nodes, "links": links}), encoding="utf-8")
    index = SymbolIndex(tmp_path)
    try:
        assert dispatch(index, "impact", {"symbol": "Error.new"}).splitlines()[1:] == [
            "  src/error.rs:16 make | Error::new()",  # not std's io::Error::new(), as `use std::io` says
            "  src/error.rs:20 qualified | crate::error::Error::new()",  # the module that defines Error
            "  src/error.rs:24 from_dep [inferred] | dep::Error::new()"]  # another crate's, or a re-export
        assert dispatch(index, "impact", {"symbol": "Item.new"}).splitlines()[1:] == [
            "  src/items.rs:12 item [name] | inner::Item::new()"]  # inner, the inline module that defines Item
    finally:
        index.close()


def test_rust_impact_knows_what_std_imports_name(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/fs.rs").write_text(
        "use std::fs;\nuse std::fs::read as load;\n\npub fn read(path: &str) -> Vec<u8> {\n"
        "    fs::read(path).unwrap_or_default()\n}\n\npub fn read_config() -> Vec<u8> {\n"
        '    std::fs::read("config.toml").unwrap_or_default()\n}\n\npub fn read_cache() -> Vec<u8> {\n'
        '    load("cache.bin").unwrap_or_default()\n}\n\npub fn twice() -> Vec<u8> {\n    read("a.txt")\n}\n\n'
        'pub fn local_import() -> Vec<u8> {\n    use std::fs::read;\n    read("c.toml").unwrap_or_default()\n}\n',
        encoding="utf-8")
    # graphify 0.9.17's edges for this file: std's read in read_config() and local_import() becomes this crate's read()
    nodes = [{"id": node, "label": f"{node}()", "source_file": "src/fs.rs", "source_location": location}
             for node, location in (("read", "L4"), ("read_config", "L8"), ("read_cache", "L12"), ("twice", "L16"),
                                    ("local_import", "L20"))]
    links = [{"source": source, "target": "read", "relation": "calls", "confidence": "EXTRACTED", "source_location": line}
             for source, line in (("local_import", "L22"), ("read_config", "L9"), ("twice", "L17"))]
    (tmp_path / ".token-master").mkdir()
    (tmp_path / ".token-master/graph.json").write_text(json.dumps({"nodes": nodes, "links": links}), encoding="utf-8")
    index = SymbolIndex(tmp_path)
    try:  # not fs::read() after `use std::fs`, std::fs::read(), load() (std's read renamed) or a read() that
        # `use std::fs::read` brought into one function
        assert dispatch(index, "impact", {"symbol": "fs.rs::read"}).splitlines()[1:] == [
            '  src/fs.rs:17 twice | read("a.txt")']
    finally:
        index.close()


def test_rust_impact_tells_other_types_from_aliases_and_generics(tmp_path: Path):
    root = _rust_repo(tmp_path)
    (root / "src/extra.rs").write_text(
        "use std::io::{Error, ErrorKind};\n\npub struct Other;\n\nimpl TryFrom<u8> for Other {\n"
        "    type Error = std::io::Error;\n    fn try_from(_: u8) -> Result<Self, Self::Error> {\n"
        '        Err(Error::new(ErrorKind::Other, "x"))\n    }\n}\n\n'
        "pub type Db = crate::store::Store;\n\npub fn open() -> Db {\n    Db::new()\n}\n\n"
        "pub trait Maker {\n    fn new() -> Self;\n}\n\npub fn build<T: Maker>() -> T {\n    T::new()\n}\n\n"
        "pub trait Path {}\n\nimpl Default for Other {\n    fn default() -> Self {\n        Other\n    }\n}\n\n"
        "pub fn fresh() -> Other {\n    std::default::Default::default()\n}\n\n"
        "pub fn describe_store(s: &crate::store::Store) -> String {\n    crate::store::Store::describe(s)\n}\n\n"
        'pub fn open_file() -> Result<(), Error> {\n    Err(Error::new(ErrorKind::Other, "x"))\n}\n\n'
        "pub fn describe_other(o: &Other) -> String {\n    Other::describe(o)\n}\n\n"
        "pub type Handle = std::sync::Arc<crate::store::Store>;\n\n"
        "pub fn share(s: crate::store::Store) -> Handle {\n    Handle::new(s)\n}\n", encoding="utf-8")
    index = SymbolIndex(root)
    try:
        assert dispatch(index, "impact", {"symbol": "Store.new"}).splitlines()[1:] == [
            "  src/extra.rs:15 open | Db::new()",  # an alias of Store, unlike Handle, an alias of Arc
            "  src/extra.rs:23 build | T::new()",  # a generic parameter: may be Store
            "  src/store.rs:35 late | Store::new().load()"]
        # Not Error::new() (io's Error, though an associated type is also named Error and open_file returns
        # Result<(), Error>), nor std::path::Path::new() (std's Path, though this crate has a trait Path). The trait
        # Other.default implements can reach it, and a type implementing Saver can reach Saver's own method:
        assert dispatch(index, "impact", {"symbol": "Other.default"}).splitlines()[1:] == [
            "  src/extra.rs:35 fresh | std::default::Default::default()"]
        assert dispatch(index, "impact", {"symbol": "Saver.describe"}).splitlines()[1:] == [
            "  src/extra.rs:39 describe_store | crate::store::Store::describe(s)"]  # Other does not implement Saver
    finally:
        index.close()


def test_rust_impact_keeps_aliases_in_their_module_and_languages_apart(tmp_path: Path):
    root = _rust_repo(tmp_path)
    (root / "src/scope.rs").write_text("mod a {\n    use crate::helper as run;\n}\n\npub fn run() {}\n\n"
                                       "pub fn main_entry() {\n    run()\n}\n", encoding="utf-8")
    (root / "src/tok.rs").write_text("pub fn tokenize(x: u8) -> u8 {\n    parse(x)\n}\n", encoding="utf-8")
    (root / "pkg").mkdir()
    (root / "pkg/parser.py").write_text("def parse(x):\n    return x\n", encoding="utf-8")
    index = SymbolIndex(root)
    try:
        assert "  src/scope.rs:8 main_entry | run()" in dispatch(index, "impact", {"symbol": "run"})
        assert "main_entry" not in dispatch(index, "impact", {"symbol": "helper"})
        assert dispatch(index, "impact", {"symbol": "parse"}).splitlines()[1:] == [
            "  none found (dynamic calls, callbacks and string dispatch are invisible; grep to be sure)"]
    finally:
        index.close()


def test_rust_files_are_indexed_once_the_grammar_is_installed(tmp_path: Path, monkeypatch):
    root = _rust_repo(tmp_path)
    monkeypatch.setattr(symbol_index, "_rust_parser", lambda: None)
    index = SymbolIndex(root)
    try:
        assert dispatch(index, "locate", {"query": "helper"}).startswith("No symbol or file matches")
    finally:
        index.close()
    monkeypatch.undo()
    index = SymbolIndex(root)  # the same index file, opened by a runtime that has tree-sitter-rust
    try:
        assert "src/lib.rs:6-9 function helper ~" in dispatch(index, "locate", {"query": "helper"})
    finally:
        index.close()


def test_tool_definitions_stay_small():
    # They ride on every request; the graph tools shipped before v7 cost 1,165 tokens per call (PRS-2).
    assert tokens.estimate(json.dumps(symbol_index.TOOL_SPECS)) < 400
