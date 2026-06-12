"""Tests for ContentRouter detection + the never-expand invariant.

Focused on the classification decisions that feed compressor selection, including
the regression that markdown/rST docs (which embed code-fence keywords) must route
to PROSE, not CODE.
"""

import sys
from pathlib import Path

# Make the headroom package importable when tests run from the repo.
_SKILL = Path(__file__).resolve().parents[2]
if str(_SKILL) not in sys.path:
    sys.path.insert(0, str(_SKILL))

from headroom.router import ContentType, detect, route_typed  # noqa: E402


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
    from headroom.tokens import estimate

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

