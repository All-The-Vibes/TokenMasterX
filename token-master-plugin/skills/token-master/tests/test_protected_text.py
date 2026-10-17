"""Exact protected spans, not semantic equivalence of the surrounding prose."""
import pytest

from brainspace.protected_text import protected_text_preserved, restore_protected_text


def changed(block):
    return "Long introduction.\n" + block + "Long conclusion.\n", "Short.\n" + block + "Done.\n"


@pytest.mark.parametrize("text", [
    "", "ordinary text", "中文 👩🏽‍💻 e\u0301\r\n",
    "```unbalanced", "inline ~~~ fence", "<exact-answer>gold</exact-answer>",
    "BEGIN EXACT\nliteral", "    ```indented",
])
def test_valid_identity_passes_even_if_changed_forms_would_be_ambiguous(text):
    assert protected_text_preserved(text, text) is True


@pytest.mark.parametrize("original,projected", [
    ("Long ordinary prose.", "Short."),
    ("", "New prose."),
    ("Plain\r\ntext.", "Plain text."),
    ("Unicode café e\u0301 👩🏽‍💻", "Unicode summary."),
    ("Some `inline` code and ~~strikethrough~~.", "Some summary."),
])
def test_unprotected_prose_is_not_a_semantic_gate(original, projected):
    assert protected_text_preserved(original, projected)


@pytest.mark.parametrize("block", [
    "```python\nprint('hello')\n```\n",
    "~~~rust\nfn main() {}\n~~~\n",
    "```\n```\n",
    "~~~\n~~~\n",
    "   ```text\n  indented content\n ```\n",
    " ```python\nprint(1)\n   `````` \t\n",
    "  ~~~~~ rust\nfn main() {}\n~~~~~~~\t \n",
    "```日本語\r\nλ = '🌍'\r\n```\r\n",
    "~~~info with `a single backtick`\nbody\n~~~\n",
    "````markdown\n```python\nprint(1)\n```\n````\n",
    "`````markdown\n````\n```\n~~~\ninline ``` here\n````not a closer\n`````\n",
    "~~~~markdown\n~~~rust\n~~~\n````literal\n~~~~\n",
    "```text\nliteral\u2028separator\u0085still inside\n```\n",
])
def test_complete_blocks_preserved_with_prose_changes(block):
    assert protected_text_preserved(*changed(block))


def test_closing_fence_at_end_of_file_and_leading_indentation_are_preserved():
    block = "   ```py\r\nprint('λ')\r\n  ```` \t"
    assert protected_text_preserved("Before.\n" + block, "After.\n" + block)
    assert not protected_text_preserved("Before.\n" + block, "After.\n" + block + "\n")


def test_fence_character_length_indentation_and_line_ending_combinations():
    for char in ("`", "~"):
        for size in (3, 4, 8):
            for extra in (0, 1, 3):
                for opening_indent in range(4):
                    for closing_indent in range(4):
                        for newline in ("\n", "\r\n"):
                            block = (" " * opening_indent + char * size + "\ttext" + newline
                                     + "Unicode λ 🌏" + newline
                                     + " " * closing_indent + char * (size + extra) + "\t " + newline)
                            assert protected_text_preserved(*changed(block))


@pytest.mark.parametrize("marker", [
    "<exact-answer>gold</exact-answer>", "<exact_answer>gold</exact_answer>",
    "<EXACT-ANSWER attr='x'>gold</EXACT-ANSWER>", "</exact_answer>",
    "<exact-answer", "BEGIN EXACT", "begin exact", "BEGIN\tEXACT",
    "BEGIN\nEXACT",
])
def test_changed_text_with_explicit_markers_fails_in_either_input(marker):
    for original, projected in [
        (marker + "\nverbose", marker + "\nshort"),
        (marker + "\nverbose", "short"),
        ("verbose", marker + "\nshort"),
        changed("```\n" + marker + "\n```\n"),
    ]:
        assert not protected_text_preserved(original, projected)


@pytest.mark.parametrize("ambiguous", [
    "```python\nnot closed\n",
    "~~~\nnot closed\n",
    "```python\nbody\n~~~\n",
    "````\nbody\n```\n",
    "```python\nbody\n```suffix\n",
    "inline ```code``` text\n",
    "inline ~~~code~~~ text\n",
    "```python ```\n",
    "~~~text ~~~\n",
    "```py`thon\nbody\n```\n",
    "    ```python\nbody\n    ```\n",
    "\t```python\nbody\n\t```\n",
    " \t~~~\nbody\n~~~\n",
    "\u00a0```\nbody\n```\n",
    "```\nbody\n```\u00a0\n",
    "> ```python\nbody\n> ```\n",
    "- ```python\nbody\n  ```\n",
    "<pre>```python\nbody\n```\n",
    "\\```python\nbody\n```\n",
    "``~\nbody\n``~\n",
    "~~~```\nbody\n~~~\n",
    "```~\nbody\n```\n",
    "~~~`\nbody\n~~~\n",
    "prefix\u2028```python\nbody\n```\n",
    "prefix\u0085~~~\nbody\n~~~\n",
    "```python\rbody\r```\r",
    "~~~\nbody\r~~~\n",
])
def test_ambiguous_delimiters_fail_closed_even_when_unchanged_within_changed_prose(ambiguous):
    assert not protected_text_preserved(*changed(ambiguous))
    assert not protected_text_preserved("Before.\n" + ambiguous, "Summary.\n")
    assert not protected_text_preserved("Before.\n", "Summary.\n" + ambiguous)


@pytest.mark.parametrize("replacement", [
    "```python\nprint(2)\n```\n",
    "```py\nprint(1)\n```\n",
    "```python\nprint(1)\n````\n",
    " ```python\nprint(1)\n```\n",
    "```python\nprint(1)\n ```\n",
    "```python\n print(1)\n```\n",
    "```python\nprint(1)\n``` \n",
    "```python\r\nprint(1)\r\n```\r\n",
    "~~~python\nprint(1)\n~~~\n",
    "",
])
def test_modifying_any_protected_byte_or_removing_block_is_rejected(replacement):
    original = "Before.\n```python\nprint(1)\n```\nAfter.\n"
    assert not protected_text_preserved(original, "Short.\n" + replacement + "Done.\n")


def test_unicode_normalization_inside_block_is_not_byte_preserving():
    assert not protected_text_preserved(*(
        "Prose.\n```\n" + s + "\n```\n" for s in ("café", "cafe\u0301")))


def test_order_and_duplicate_multiplicity_are_required():
    a, b = "```\nA\n```\n", "~~~\nB\n~~~\n"
    original = "Before.\n" + a + b + a
    assert protected_text_preserved(original, "Short.\n" + a + "Between.\n" + b + a)
    for blocks in (a + b, a + a + b, b + a + a, a + b + a + a, a + b + b):
        assert not protected_text_preserved(original, "Short.\n" + blocks)
    assert not protected_text_preserved("Before.\n", "After.\n" + a)


@pytest.mark.parametrize("stray", ["```", "~~~", "inline ``` here", "    ~~~", "``~"])
def test_new_stray_delimiters_outside_retained_spans_rejected(stray):
    a = "```python\nprint(1)\n```\n"
    original = "Before.\n" + a + "After.\n"
    assert not protected_text_preserved(original, "Short.\n" + a + stray + "\n")
    assert not protected_text_preserved(original, stray + "\n" + a + "Done.\n")


def test_literals_inside_outer_block_not_separately_parsed_but_must_remain_exact():
    block = "````markdown\n> ```\ninline ~~~ here\n    ```\n```\n````\n"
    assert protected_text_preserved(*changed(block))
    assert not protected_text_preserved(
        "Before.\n" + block, "After.\n" + block.replace("inline ~~~", "inline ~~"))


@pytest.mark.parametrize("value", [None, 1, True, b"text", b"\xff", [], {}, object()])
def test_nonstrings_fail_closed_including_identical_values(value):
    assert protected_text_preserved(value, value) is False
    assert protected_text_preserved(value, "text") is False
    assert protected_text_preserved("text", value) is False


@pytest.mark.parametrize("value", ["\ud800", "\udfff", "\ud83d\ude00", "```\n\ud800\n```\n"])
def test_utf8_unencodable_strings_fail_even_on_identity(value):
    assert not protected_text_preserved(value, value)
    assert not protected_text_preserved(value, "safe")
    assert not protected_text_preserved("safe", value)


def test_string_subclasses_cannot_override_protection_checks():
    class PretendString(str):
        def __eq__(self, _):
            return True

    assert not protected_text_preserved(PretendString("```\ngold\n```\n"), "removed")


def test_restore_observed_unknown_info_normalization_without_touching_projected_prose():
    original = "Long introduction.\n```\nrun --example\n```\nLong conclusion.\n"
    projected = "Short.\n```unknown\nrun --example\n```\nDone.\n"
    expected = "Short.\n```\nrun --example\n```\nDone.\n"
    assert not protected_text_preserved(original, projected)
    assert restore_protected_text(original, projected) == expected
    assert protected_text_preserved(original, expected)
    assert restore_protected_text(original, expected) == expected


@pytest.mark.parametrize("text", [
    "", "unchanged", "```\nunbalanced", "inline ``` literal",
    "<exact-answer>gold</exact-answer>", "BEGIN EXACT",
])
def test_restore_valid_identity_retains_existing_guard_semantics(text):
    assert restore_protected_text(text, text) == text


def test_restore_already_safe_projection_is_returned_unchanged():
    original, projected = changed("```py\nx = 1\n```\n")
    assert restore_protected_text(original, projected) == projected
    assert restore_protected_text("Long prose.", "Short.") == "Short."


def test_restore_full_fence_spans_crlf_unicode_indentation_and_delimiters():
    original = "Before.\n  ````日本語\r\nλ = '🌍'\r\n ````` \t\r\nAfter.\n"
    projected = "Short.\n~~~unknown\nλ = '🌍'\r\n~~~~\nDone.\n"
    expected = "Short.\n  ````日本語\r\nλ = '🌍'\r\n ````` \t\r\nDone.\n"
    assert restore_protected_text(original, projected) == expected
    assert protected_text_preserved(original, expected)


def test_restore_multiple_distinct_interiors_retains_order_and_intervening_prose():
    a, b = "```python\nprint(1)\n```\n", "~~~rust\nfn main() {}\n~~~\n"
    original = "Long.\n" + a + "Long middle.\n" + b
    projected = "Short.\n~~~unknown\nprint(1)\n~~~\nMiddle.\n```unknown\nfn main() {}\n```\n"
    expected = "Short.\n" + a + "Middle.\n" + b
    assert restore_protected_text(original, projected) == expected


def test_restore_outer_four_backticks_with_triple_backtick_literals():
    original = "Before.\n````markdown\n```python\nx = 1\n```\n````\n"
    projected = "After.\n~~~~unknown\n```python\nx = 1\n```\n~~~~\n"
    assert restore_protected_text(original, projected) == original.replace("Before.", "After.")
    # A too-short outer fence cannot be guessed back into a valid parse.
    assert restore_protected_text(original, projected.replace("~~~~", "```")) is None


def test_restore_identical_duplicate_blocks_is_unambiguous_and_preserves_multiplicity():
    block = "```\nsame\n```\n"
    original = "Before.\n" + block * 2
    projected = "After.\n" + block.replace("```\nsame", "```unknown\nsame") * 2
    assert restore_protected_text(original, projected) == "After.\n" + block * 2
    assert restore_protected_text(original, "After.\n" + block) is None
    assert restore_protected_text(original, "After.\n" + block * 3) is None


@pytest.mark.parametrize("projected_blocks", [
    "```js\nsame\n```\n```python\nsame\n```\n",
    "```unknown\nsame\n```\n```unknown\nsame\n```\n",
    "```python\nsame\n```\n```unknown\nsame\n```\n",
])
def test_restore_same_body_different_language_blocks_refuses_ambiguous_reassociation(projected_blocks):
    original = "Before.\n```python\nsame\n```\n```js\nsame\n```\n"
    assert restore_protected_text(original, "After.\n" + projected_blocks) is None
    unchanged_blocks = original.replace("Before.", "After.")
    assert restore_protected_text(original, unchanged_blocks) == unchanged_blocks


def test_restore_unchanged_ambiguous_group_does_not_block_separate_unique_body_repair():
    duplicates = "```python\nsame\n```\n~~~js\nsame\n~~~\n"
    unique = "```\ndifferent\n```\n"
    original = "Before.\n" + duplicates + unique
    projected = "After.\n" + duplicates + unique.replace("```\ndifferent", "```unknown\ndifferent")
    assert restore_protected_text(original, projected) == "After.\n" + duplicates + unique


@pytest.mark.parametrize("body", [
    "print(2)\n", " print(1)\n", "print(1) \n", "print(1)\r\n", "\nprint(1)\n", "",
])
def test_restore_never_repairs_changed_interior_bytes(body):
    assert restore_protected_text(
        "Before.\n```python\nprint(1)\n```\n",
        "After.\n```unknown\n" + body + "```\n",
    ) is None


def test_restore_rejects_interior_unicode_normalization():
    assert restore_protected_text("```\ncafé\n```\n", "```unknown\ncafe\u0301\n```\n") is None


@pytest.mark.parametrize("blocks", [
    "```\nB\n```\n```\nA\n```\n", "```\nA\n```\n",
    "```\nA\n```\n```\nB\n```\n```\nC\n```\n",
])
def test_restore_count_and_interior_order_mismatches(blocks):
    original = "Before.\n```\nA\n```\n```\nB\n```\n"
    assert restore_protected_text(original, "After.\n" + blocks) is None


@pytest.mark.parametrize("marker", ["<exact-answer>", "</exact_answer>", "BEGIN EXACT"])
def test_restore_changed_marker_text_is_never_repaired(marker):
    marker += "\n"
    original = "Before.\n```\ncode\n```\n"
    projected = "After.\n```unknown\ncode\n```\n"
    assert restore_protected_text(marker + original, projected) is None
    assert restore_protected_text(original, marker + projected) is None
    assert restore_protected_text(marker + original, marker + projected) is None


@pytest.mark.parametrize("bad", [
    "```unknown\ncode\n", "inline ```code```\n", "    ```unknown\ncode\n    ```\n",
    "~~~unknown\ncode\n```\n", "```unknown\ncode\n```suffix\n", "``~\ncode\n``~\n",
    "```unknown\rbody\r```\r", "```unknown\ncode\n```\nstray ~~~\n",
])
def test_restore_malformed_or_stray_fences_fail_in_either_input(bad):
    valid = "Before.\n```\ncode\n```\n"
    assert restore_protected_text(valid, bad) is None
    assert restore_protected_text(bad, valid) is None


def test_restore_empty_block_fence_formatting_and_closing_eof():
    assert restore_protected_text("Before.\n```\n```", "After.\n~~~unknown\n~~~") == "After.\n```\n```"
    # Restoring the original EOF closing span would merge a new prose suffix
    # into that closing line. The mandatory post-repair guard must reject it.
    assert restore_protected_text("Before.\n```\n```", "After.\n~~~unknown\n~~~\nSuffix") is None


@pytest.mark.parametrize("value", [None, b"\xff", [], "\ud800", "\ud83d\ude00"])
def test_restore_invalid_types_and_utf8_fail_including_identity(value):
    assert restore_protected_text(value, value) is None
    assert restore_protected_text(value, "safe") is None
    assert restore_protected_text("safe", value) is None
