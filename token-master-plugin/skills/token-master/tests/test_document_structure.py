"""Pure structural checks only: no inference, source execution or source reread."""
import json
from pathlib import Path

import pytest

from brainspace.document_structure import CONTRACT, document_structure_preserved as preserved
from brainspace.protected_text import protected_text_preserved


TABLE = "| Resource | Path |\n| :--- | ---: |\n| Catalog | config/models.json |\n"
LIST = "1. canonical config\n2. legacy fallback\n"


def around(block, ending="\n"):
    return "Long introduction." + ending + block, "Short introduction." + ending + block


def test_contract_and_changed_surrounding_prose():
    assert CONTRACT == "document-structure-v1"
    original = "Long introduction.\n" + TABLE + "\n" + LIST + "\nLong conclusion.\n"
    projected = "Brief.\n" + TABLE + "\n" + LIST + "\nDone.\n"
    assert preserved(original, projected)
    # This necessary condition intentionally cannot certify semantics.
    assert preserved("First path wins.", "Second path wins.")


@pytest.mark.parametrize("block", [
    TABLE, "A | B\n--- | ---\na | b\n", "  | A | B |\n  | --- | :---: |\n  | | 雪 |\n",
    "A|B\n:---|---:\n", "| A | B |\n| --- | --- |\n| a | b |",
    "| A | B |\n| --- | --- |\n| `config.json` | `${CONFIG}/models.json` |\n",
    LIST, "1) café e\u0301\n2) 雪\n", "123456789. item\n",
    "1. parent\n   continuation\n   - child\n     child continuation\n   1) ordered child\n"
    "   2) next child\n\n   continuation after blank\n2. next parent\n\n",
    "10. parent\n    continuation\n11. next\n",
])
def test_recognized_blocks_allow_irrelevant_prose_changes(block):
    assert preserved(*around(block))


@pytest.mark.parametrize("block", [TABLE, LIST, TABLE + "\n" + LIST])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_exact_line_endings_and_unicode(block, newline):
    block = block.replace("\n", newline)
    assert preserved(*around(block, newline))
    assert not preserved("Before.\n" + block, "After.\n" + block.replace("Catalog", "Catalogue")
                         .replace("canonical", "Canonical"))
    other = "\n" if newline == "\r\n" else "\r\n"
    assert not preserved("Before.\n" + block, "After.\n" + block.replace(newline, other))


@pytest.mark.parametrize("replacement", [
    "", TABLE.replace("Catalog", "Other"), TABLE.replace("| Catalog | config/models.json |\n", ""),
    TABLE + TABLE, TABLE.replace("| :--- | ---: |", "| --- | --- |"),
    TABLE.replace("config/models.json", "config/models.json "),
    TABLE.replace("\n", "\r\n"), TABLE[:-1],
])
def test_table_removal_duplication_or_byte_change_fails(replacement):
    assert not preserved("Before.\n" + TABLE, "After.\n" + replacement)


@pytest.mark.parametrize("replacement", [
    "", "2. legacy fallback\n1. canonical config\n", LIST + LIST,
    "canonical config\nlegacy fallback\n", "1. config\n2. legacy fallback\n",
    LIST.replace("1.", "1)"), LIST.replace("\n", "\r\n"), LIST[:-1],
])
def test_list_removal_reorder_duplication_or_byte_change_fails(replacement):
    assert not preserved("Before.\n" + LIST, "After.\n" + replacement)


def test_global_block_order_and_duplicate_multiplicity():
    original = "Before.\n" + TABLE + "\n" + LIST + "\n" + TABLE
    assert preserved(original, "After.\n" + TABLE + "\n" + LIST + "\n" + TABLE)
    for changed in (LIST + "\n" + TABLE + TABLE, TABLE + "\n" + LIST + "\n",
                    TABLE + "\n" + LIST + "\n" + TABLE + TABLE):
        assert not preserved(original, "After.\n" + changed)


@pytest.mark.parametrize("ambiguous", [
    "| A | B |\n| -- | --- |\n", "| A | B |\n| --- | --- |\n| a | b | c |\n",
    "| A | B |\n| --- | --- |\n | a | b |\n",
    "| A | |\n| --- | --- |\n", "ordinary prose | a shell pipeline\n",
    "| A | B |\n| --- | --- |\n| `a|b` | c |\n",
    "| A | B |\n| --- | --- |\n| a\\|b | c |\n",
    "| A | B |\n| --- | --- |\n| `unmatched | c |\n",
    "| A | B |\n| --- | --- |\n| ``double`` | c |\n",
    "1. A | B\n--- | ---\na | b\n", "- A | B\n--- | ---\na | b\n",
    "> " + TABLE, "> 1. quoted ordered item\n", "> quoted prose\n",
    "1. item\nlazy continuation\n", "1. item\n  underindented continuation\n",
    "1. item\n- ambiguous list switch\n", " 1. orphan indented list\n",
    "\t1. tab indentation\n", "1.  two spaces\n", "1.\t tab separator\n",
    "1. \n", "1.item\n", "1234567890. overlong marker\n", "3.14 decimal prose\n",
    "1. item\n   | A | B |\n   | --- | --- |\n", "1. item\n   > quote\n",
    "1. item\n   2.bad nested marker\n", "1. item\n   -  bad nested bullet\n",
    "1. item\n```\ncode\n```\n",
    "```unclosed\n", "Before ```inline``` after\n", "```py\nbody\n~~~\n",
    "```\nbody\r```\n", "a\rb\n",
])
def test_ambiguous_syntax_rejects_any_changed_projection_but_identity_passes(ambiguous):
    assert preserved(ambiguous, ambiguous)
    assert not preserved(*around(ambiguous))
    assert not preserved(ambiguous, "Plain replacement.\n")
    assert not preserved("Plain original.\n", ambiguous)


def test_continuation_subitem_and_blank_line_bytes_are_part_of_list():
    block = "1. parent\n   details\n   - child\n\n   more details\n2. end\n\n"
    for modified in (block.replace("details", "detail", 1), block.replace("   - child\n", ""),
                     block.replace("\n\n", "\n", 1), block[:-1]):
        assert not preserved("Before.\n" + block, "After.\n" + modified)
    assert preserved("Before.\n" + block + "Conclusion.", "After.\n" + block + "Short.")


@pytest.mark.parametrize("fence", [
    "```\n> ambiguous | pipe\n1.bad marker\n```\n",
    "~~~text\r\n| malformed\r\n1.  malformed\r\n~~~\r\n",
    "````markdown\n```\n> quote\n```\n````\n",
])
def test_closed_fences_are_opaque_and_exactness_is_separate(fence):
    assert preserved(*around(fence + TABLE))
    projected = "After.\n" + fence.replace("malformed", "changed").replace("ambiguous", "changed") + TABLE
    assert preserved("Before.\n" + fence + TABLE, projected)
    # Enforced by the existing independent fence guard, not this new feature.
    if "changed" in projected:
        assert not protected_text_preserved("Before.\n" + fence + TABLE, projected)


def test_structural_blocks_cannot_be_hidden_inside_fences_or_inline_prose():
    assert not preserved(TABLE, "```\n" + TABLE + "```\n")
    assert not preserved(LIST, "```\n" + LIST + "```\n")
    assert not preserved(LIST, "inline " + LIST)
    assert preserved(LIST + "\n```\ncode\n```\n", LIST + "\n```\nother\n```\n")


def test_review_nested_fence_cannot_release_ordered_list_continuation():
    original = ("Before.\n1. use config\n\n   ```text\n   literal code\n   ```\n\n"
                "   config path wins\n")
    for projected in (
        original.replace("Before.", "After.").replace("config path wins", "workspace path wins"),
        original.replace("Before.", "After.").replace("   config path wins\n", ""),
    ):
        assert protected_text_preserved(original, projected)
        assert not preserved(original, projected)
    assert preserved(original, original)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("indent", [" ", "  ", "   "])
@pytest.mark.parametrize("tail", [
    "   continuation\n", "   - child\n", "   continuation\n2. next item\n",
])
def test_blank_separated_indented_fence_is_unsupported_even_with_intact_fenced_bytes(
    newline, indent, tail,
):
    block = ("1. root\n\n" + indent + "~~~text\n" + indent + "literal\n"
             + indent + "~~~\n\n" + tail).replace("\n", newline)
    original = "Before." + newline + block
    assert preserved(original, original)
    for projected in (
        "After." + newline + block,
        "After." + newline + block.replace("continuation", "replacement").replace("child", "other"),
        "After." + newline + block.removesuffix(tail.replace("\n", newline)),
    ):
        assert protected_text_preserved(original, projected)
        assert not preserved(original, projected)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("tail", ["Conclusion.\n", "2. next item\n   continuation\n"])
def test_blank_separated_unindented_fence_is_an_explicit_top_level_boundary(newline, tail):
    block = ("1. root\n\n```text\nliteral\n```\n\n" + tail).replace("\n", newline)
    original, projected = "Before." + newline + block, "After." + newline + block
    assert preserved(original, projected)
    assert protected_text_preserved(original, projected)
    if tail.startswith("2."):
        assert not preserved(original, projected.replace("continuation", "changed"))
        assert not preserved(original, projected.replace(tail.replace("\n", newline), ""))


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_nested_fence_after_list_terminated_by_unindented_prose_is_opaque(newline):
    block = ("1. root\n\nEnd of list.\n\n   ```text\n   literal\n   ```\n").replace("\n", newline)
    assert preserved("Before." + newline + block, "After." + newline + block)


def test_unicode_separators_are_not_newlines_or_normalized():
    assert preserved(*around("| A | B |\n| --- | --- |\n| x\u2028y | e\u0301 |\n"))
    assert not preserved("| A | B |\n| --- | --- |\n| café | 雪 |\n",
                         "| A | B |\n| --- | --- |\n| cafe\u0301 | 雪 |\n")
    assert preserved("prose\u20281. text", "other prose")  # Literal non-LF separator.


@pytest.mark.parametrize("value", [None, True, 1, b"text", [], {}, "\ud800"])
def test_invalid_text_fails_even_on_identity(value):
    assert not preserved(value, value)
    assert not preserved(value, "")
    assert not preserved("", value)


def test_string_subclasses_cannot_override_identity_or_parsing():
    class Hostile(str):
        def __eq__(self, other):
            raise AssertionError("no overloaded equality")

        def encode(self, *args, **kwargs):
            raise AssertionError("no overloaded encoding")

    text = Hostile("1. item")
    assert not preserved(text, text)
    assert not preserved("plain", text)


def test_changed_text_limits_and_identity_exception():
    for text in ("x" * 1_048_577, "\n" * 20001):
        assert preserved(text, text)
        assert not preserved(text, "small")
        assert not preserved("small", text)


def test_saved_live_001_submitted_projection_loses_recognized_structure():
    path = (Path(__file__).resolve().parents[4] / "evidence/integrated-runtime-20261009"
            "/native-ranged-results/live-runs/live-001/candidate-handoff-001/run/runtime"
            "/preparations.jsonl")
    if not path.is_file():
        pytest.skip("retained live-001 evidence is not distributed with the package")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    changed = [row for row in rows if row["changed_messages"]]
    assert len(changed) == 1 and changed[0]["changed_messages"] == [5]
    row = changed[0]
    original, projected = (row[key]["messages"][5]["content"] for key in ("original", "prepared"))
    assert preserved(original, original)
    assert preserved(original, "Additional irrelevant prose.\n" + original)
    assert not preserved(original, projected)
