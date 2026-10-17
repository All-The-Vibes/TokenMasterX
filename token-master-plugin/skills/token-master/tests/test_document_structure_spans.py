"""One parser, exact code-point offsets; no file access, vendor or inference."""
import hashlib
from pathlib import Path

import pytest

from brainspace import document_structure as structure


TABLE = "| Setting | Value |\n|---|---|\n| 期限 | `42` |\n"
LIST = "1. Prefer config.\n2. Fall back to workspace.\n\n"


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("prefix", ["", "😀 雪\n\n", "Longer prose before data.\n\n"])
def test_offsets_address_exact_unicode_slices_not_first_text_occurrences(newline, prefix):
    table, ordered, prefix = (x.replace("\n", newline) for x in (TABLE, LIST, prefix))
    gap = newline + "Between the tables." + newline * 2
    source = prefix + table + gap + table + newline + ordered + "After the list."
    result = structure.document_structure_spans(source)
    assert type(result) is tuple and len(result) == 3
    starts = [len(prefix), len(prefix + table + gap),
              len(prefix + table + gap + table + newline)]
    values = [table, table, ordered]
    assert [span.kind for span in result] == ["table", "table", "ordered-list"]
    for span, start, text in zip(result, starts, values):
        assert type(span.start) is int and type(span.end) is int
        assert span.start == start and span.end == start + len(text)
        assert source[span.start:span.end] == text
        assert span.sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert span.to_dict() == {
            "kind": span.kind, "start": start, "end": start + len(text), "sha256": span.sha256,
        }
        with pytest.raises((AttributeError, TypeError)):
            span.start = 0
    assert all(a.end <= b.start for a, b in zip(result, result[1:]))
    assert structure.document_structure_preserved(source, source)


def test_plain_text_empty_and_only_fenced_structures_have_no_unfenced_spans():
    assert structure.SPAN_CONTRACT == "document-structure-v1-offsets-v1"
    for source in ("", "Ordinary prose.\n", "```md\n" + TABLE + LIST + "```\n"):
        assert structure.document_structure_spans(source) == ()


@pytest.mark.parametrize("source", [
    None, 1, True, [], {}, "\ud800", "bare\rseparator",
    "| malformed | table |\n|--|---|\n", "1. ordered\nlazy continuation\n",
    "1. ordered\n\n   ```txt\n   fenced\n   ```\n   continuation\n",
    "```md\nunfinished", "> quoted data\n", "\tindented\n", "indeterminate | prose",
])
def test_ambiguous_invalid_or_unsupported_is_none_not_empty_safe_set(source):
    assert structure.document_structure_spans(source) is None


def test_bounds_do_not_turn_unsupported_large_identity_into_safe_empty_spans():
    for source in ("x" * 1_048_577, "line\n" * 20_000):
        assert structure.document_structure_preserved(source, source)
        assert structure.document_structure_spans(source) is None


def test_eof_and_trailing_blank_lines_are_exact_span_content():
    for source in ("1. a\n2. b", "1. a\n2. b\n", "1. a\n2. b\n\n\n"):
        (span,) = structure.document_structure_spans(source)
        assert span.start == 0 and span.end == len(source)
        assert source[span.start:span.end] == source


def test_projection_offsets_can_move_without_changing_structure_equivalence():
    before = "Long initial background.\n\n" + TABLE + "\n" + LIST
    after = "Brief.\n\n" + TABLE + "\n" + LIST
    a, b = structure.document_structure_spans(before), structure.document_structure_spans(after)
    assert [x.start for x in a] != [x.start for x in b]
    assert [(x.kind, x.sha256) for x in a] == [(x.kind, x.sha256) for x in b]
    assert structure.document_structure_preserved(before, after)


def test_span_export_never_reads_or_reconstructs_files(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("offset extraction must use only its supplied observed text")
    for method in ("open", "read_text", "read_bytes"):
        monkeypatch.setattr(Path, method, deny)
    assert structure.document_structure_spans(TABLE + "\n" + LIST)
