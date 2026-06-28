"""Tests for ContentRouter detection + the never-expand invariant.

Focused on the classification decisions that feed compressor selection, including
the regression that markdown/rST docs (which embed code-fence keywords) must route
to PROSE, not CODE.
"""

import sys
from pathlib import Path

# Make the brainspace package importable when tests run from the repo.
_SKILL = Path(__file__).resolve().parents[2]
if str(_SKILL) not in sys.path:
    sys.path.insert(0, str(_SKILL))

from brainspace.router import ContentType, detect, lang_from_hint, route_typed  # noqa: E402


# --- hint-based detection (cheapest, highest-precision signal) -----------------

def test_markdown_hint_routes_to_prose_even_with_code_fences():
    """Regression: a .md file full of import/def keywords is prose, not code."""
    md = "# Title\n\nIntro prose.\n\n```python\nimport os\ndef f():\n    return 1\n```\n"
    assert detect(md, "README.md") is ContentType.PROSE


def test_rst_and_other_doc_exts_route_to_prose():
    for hint in ("guide.rst", "notes.markdown", "doc.adoc"):
        assert detect("Title\n=====\n\nimport this\n", hint) is ContentType.PROSE


def test_code_extension_still_routes_to_code():
    src = "import os\ndef f():\n    return 1\n\nclass X:\n    pass\n"
    assert detect(src, "foo.py") is ContentType.CODE


def test_json_hint_routes_to_json():
    assert detect('{"a": 1}', "data.json") is ContentType.JSON


def test_log_hints_route_to_log():
    for hint in ("build.log", "out.txt", "pytest", "build"):
        assert detect("anything", hint) is ContentType.LOG


# --- content-based detection (no hint) -----------------------------------------

def test_markdown_without_hint_is_prose():
    assert detect("# Title\n\nJust some prose, no code.\n", None) is ContentType.PROSE


def test_json_content_sniffed_without_hint():
    assert detect('[{"x": 1}, {"x": 2}]', None) is ContentType.JSON


# --- never-expand invariant (enforced centrally in route_typed) ----------------

def test_route_typed_never_expands_tiny_input():
    """Tiny inputs where overhead would dominate must pass through unchanged."""
    tiny = "ok"
    out, _ = route_typed(tiny, "x.py")
    assert out == tiny


def test_route_typed_empty_is_safe():
    out, ctype = route_typed("", None)
    assert out == ""
    assert ctype is ContentType.PROSE


def test_route_typed_never_expands_in_tokens_even_when_char_smaller():
    """Regression: the never-expand guard bills in TOKENS, not characters.

    Code made of many tiny functions can compress to output that is char-smaller
    but token-larger, because content-addressed placeholders carry random hex
    hashes and long identifier metadata that do not BPE-merge. A char-only guard
    would wave that through and silently cost tokens. We assert the guard holds in
    tokens — the unit that actually costs — by constructing exactly that case.
    """
    from brainspace.tokens import estimate

    # Many tiny functions: short bodies, long descriptive names -> placeholder
    # metadata that is char-cheap but token-expensive.
    src = "\n\n".join(
        f"def function_with_a_fairly_long_descriptive_name_number_{i}():\n"
        f"    return {i}"
        for i in range(40)
    ) + "\n"
    out, _ = route_typed(src, "many_small_funcs.py")
    # Whatever the compressor produced, the guard must guarantee no token growth.
    assert estimate(out) <= estimate(src)


# --- code language resolution (hint extension -> compressor lang) ---------------

def test_lang_from_hint_resolves_known_extensions():
    assert lang_from_hint("src/main.rs") == "rust"
    assert lang_from_hint("module.py") == "python"
    assert lang_from_hint("stubs.pyi") == "python"


def test_lang_from_hint_unknown_or_missing_is_none():
    assert lang_from_hint(None) is None
    assert lang_from_hint("Read") is None          # a tool name, not a filename
    assert lang_from_hint("service.go") is None     # code, but no grammar wired yet


def test_route_typed_skeletonizes_rust_via_hint():
    """End-to-end: a .rs hint must reach the code compressor as lang='rust' and
    actually skeletonize. Without lang threading the Rust source would be parsed
    as Python and pass through unchanged."""
    rs = (
        "/// Adds two numbers.\n"
        "pub fn add(a: i64, b: i64) -> i64 {\n"
        "    let sum = a + b;\n"
        "    let doubled = sum * 2;\n"
        "    let result = doubled / 2;\n"
        "    result\n"
        "}\n"
    ) * 4
    out, ctype = route_typed(rs, "lib.rs")
    assert ctype is ContentType.CODE
    # The doc comment and signature survive; the executable body is elided.
    assert "pub fn add(a: i64, b: i64) -> i64" in out
    assert "/// Adds two numbers." in out
    assert "let doubled = sum * 2;" not in out
    assert len(out) < len(rs)


def test_route_typed_rust_without_hint_does_not_corrupt():
    """No hint => the compressor cannot know the language and defaults to Python.
    Parsing Rust as Python must still honor the contract: never raise, never
    expand (the worst case is a harmless no-op)."""
    rs = "pub fn f() {\n    let x = 1;\n    let y = 2;\n}\n" * 6
    out, _ = route_typed(rs, None)
    assert isinstance(out, str)
    assert len(out) <= len(rs)

