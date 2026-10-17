"""document-structure-v1: narrow necessary-condition guard, not Markdown semantics.

API: document_structure_preserved(original, projected) -> bool. Plain, valid
UTF-8-encodable string identity passes, including unsupported syntax. Changed
inputs are each limited to 1,048,576 characters and 20,000 LF-delimited lines
(including a terminal empty line, if present).
LF and CRLF are recognized; bare CR and invalid/ambiguous fences fail closed.
Unicode separators remain literal characters, not line boundaries.
document_structure_spans(text) exports immutable end-exclusive code-point
offsets and UTF-8 slice digests from this same parser. None means unsupported;
an empty tuple means supported text with no recognized structures.

Grammar outside properly closed fences (reused protected_text._blocks):
* Pipe tables: a header and immediately following delimiter row, each with
  >=2 cells; delimiter cells contain >=3 hyphens with optional endpoint colons.
  Optional outer pipes and 0..3 leading ASCII spaces are allowed. Header cells
  must be nonempty. Following contiguous pipe rows must have the same cell
  count and indentation; empty data cells are allowed. Blank lines terminate
  tables and are not part of them. Every pipe-bearing line must belong to such
  a table. Paired single-backtick spans confined to one cell are allowed;
  backslashes, unmatched/repeated backticks and code spans crossing pipes are
  unsupported, not unescaped.
* Ordered lists: an unindented 1..9 ASCII-digit marker, '.' or ')', exactly one
  separating ASCII space, then nonblank item text. A block contains subsequent
  unindented ordered items, indented continuations/subitems, and intervening/
  trailing blank lines. Continuations must indent at least to the current
  root item's content column; nested ordered/bullet markers use the same
  one-space rule. Subitems are retained as whole lines, not semantically parsed.
  A blank separator followed by unindented nonlist prose terminates the block.
  A blank separator followed by a fence opening at column zero also terminates
  it. An indented fence never establishes that boundary: it is unsupported
  while parsing a list, even after blank lines, and rejects changed text.
  Without a blank separator, unindented nonlist text could be a lazy list
  continuation and is rejected. EOF terminates a block. Root unordered-list
  switches, nested tables, quotes and fences in an unterminated list are
  unsupported. List-like malformed markers or orphan indented list markers
  fail closed. Leading tabs outside fences are unsupported.
* Blockquote-prefixed lines are unsupported outside fences. Closed fenced
  blocks are opaque/skipped; this guard DOES NOT verify their content equality.
  Callers must also apply protected_text_preserved for exact fence protection.

Both parses must succeed and produce equal ordered (kind, exact block text)
sequences, preserving bytes, line endings, order and multiplicity. This is
line-boundary anchoring, never normalized equality or a substring search.
Ordinary prose may change arbitrarily. No source reread, query/filename rules,
semantic detector, repair, or dependency is used. Pipe-bearing prose, decimal-
like line starts, quoted examples and valid Markdown outside this grammar can
be conservative false positives. Preserving these spans does not prove query
coverage, surrounding precedence prose, answer correctness or model quality.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re

from .protected_text import _blocks, _valid_texts


CONTRACT = "document-structure-v1"
SPAN_CONTRACT = "document-structure-v1-offsets-v1"
_MAX_CHARS = 1_048_576
_MAX_LINES = 20_000
_ORDERED = re.compile(r"([0-9]{1,9}[.)] )([^ \t].*)")
_ORDER_LIKE = re.compile(r"[0-9]+[.)]")
_BULLET = re.compile(r"[-+*] [^ \t].*")
_BULLET_LIKE = re.compile(r"[-+*](?:[ \t]|$)")
_DELIMITER = re.compile(r":?-{3,}:?")


@dataclass(frozen=True, slots=True)
class DocumentStructureSpan:
    """End-exclusive Python code-point positions over the supplied observed text."""
    kind: str
    start: int
    end: int
    sha256: str

    def to_dict(self) -> dict:
        return asdict(self)


def _cells(line: str) -> list[str] | None:
    """Validate only the declared pipe-row grammar; return stripped cells for syntax."""
    if "|" not in line or "\\" in line or "``" in line:
        return None
    body = line.strip(" \t")
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    cells = [cell.strip(" \t") for cell in body.split("|")]
    if len(cells) < 2 or any(cell.count("`") % 2 for cell in cells):
        return None
    return cells


def _structure_ranges(text: str) -> list[tuple[str, int, int]] | None:
    fences = _blocks(text)
    if fences is None:
        return None
    # Keep exact LF/CRLF slices. Unicode line separators are not Markdown lines.
    raw = [part + "\n" for part in text.split("\n")[:-1]]
    if not text.endswith("\n"):
        raw.append(text.rsplit("\n", 1)[-1])
    lines: list[str | None] = []
    line_starts: list[int] = []
    offset, fence_index = 0, 0
    for raw_line in raw:
        line_starts.append(offset)
        while fence_index < len(fences) and offset >= fences[fence_index].end:
            fence_index += 1
        inside = fence_index < len(fences) and fences[fence_index].start <= offset
        lines.append(None if inside else raw_line.removesuffix("\n").removesuffix("\r"))
        offset += len(raw_line)
    line_starts.append(offset)

    # Reject unsupported wrappers before scanning, including inside a list.
    if any(line is not None and line.lstrip(" ").startswith(("\t", ">")) for line in lines):
        return None
    spans: list[tuple[str, int, int]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line is None:
            i += 1
            continue
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if "|" in line:
            start = i
            header = _cells(line)
            if (indent > 3 or header is None or any(not cell for cell in header)
                    or i + 1 >= len(lines) or _ORDER_LIKE.match(stripped)
                    or _BULLET_LIKE.match(stripped)):
                return None
            delimiter = lines[i + 1]
            if delimiter is None or len(delimiter) - len(delimiter.lstrip(" ")) != indent:
                return None
            cells = _cells(delimiter)
            if (cells is None or len(cells) != len(header)
                    or any(_DELIMITER.fullmatch(cell) is None for cell in cells)):
                return None
            i += 2
            while i < len(lines):
                row = lines[i]
                if row is None or "|" not in row:
                    break
                cells = _cells(row)
                if (len(row) - len(row.lstrip(" ")) != indent
                        or cells is None or len(cells) != len(header)
                        or all(_DELIMITER.fullmatch(cell) for cell in cells)):
                    return None  # A second delimiter/header boundary is ambiguous.
                i += 1
            spans.append(("table", line_starts[start], line_starts[i]))
            continue
        if _ORDER_LIKE.match(stripped):
            item = _ORDERED.fullmatch(line)
            if indent or item is None:
                return None
            start, content_column, blank = i, len(item[1]), False
            i += 1
            while i < len(lines):
                row = lines[i]
                if row is None:
                    # The opaque sentinel hides nesting. Only a column-zero
                    # opening after a blank line proves our top-level boundary.
                    if not blank or not raw[i].startswith(("`", "~")):
                        return None
                    break
                if not row.strip(" \t"):
                    blank = True
                    i += 1
                    continue
                body = row.lstrip(" ")
                spaces = len(row) - len(body)
                if not spaces:
                    if _ORDER_LIKE.match(row):
                        item = _ORDERED.fullmatch(row)
                        if item is None:
                            return None
                        content_column, blank = len(item[1]), False
                        i += 1
                        continue
                    if not blank or _BULLET_LIKE.match(row):
                        return None
                    break
                if (spaces < content_column or "|" in row
                        or (_ORDER_LIKE.match(body) and _ORDERED.fullmatch(body) is None)
                        or (_BULLET_LIKE.match(body) and _BULLET.fullmatch(body) is None)):
                    return None
                blank = False
                i += 1
            spans.append(("ordered-list", line_starts[start], line_starts[i]))
            continue
        i += 1
    return spans


def _structures(text: str) -> list[tuple[str, str]] | None:
    ranges = _structure_ranges(text)
    return None if ranges is None else [(kind, text[start:end]) for kind, start, end in ranges]


def document_structure_spans(text: str) -> tuple[DocumentStructureSpan, ...] | None:
    """Export the same parser's slices; None is ambiguous, () has no structures.

    This does not read a file, infer full-file completeness, or authorize a tool
    result. Callers still need executor provenance and separate fence/final-wire
    guards. Unlike unchanged-string acceptance, unsupported input never becomes
    an empty, supposedly safe set of offsets.
    """
    if (not _valid_texts(text, text) or len(text) > _MAX_CHARS
            or text.count("\n") + 1 > _MAX_LINES):
        return None
    ranges = _structure_ranges(text)
    if ranges is None:
        return None
    return tuple(DocumentStructureSpan(
        kind, start, end, hashlib.sha256(text[start:end].encode("utf-8")).hexdigest(),
    ) for kind, start, end in ranges)


def document_structure_preserved(original: str, projected: str) -> bool:
    """Check exact recognized structures, not query completeness or model quality.

    This does not restore/repair text. A caller must separately require fence,
    source, recovery, eligibility and full-input nonexpansion guards.
    """
    if not _valid_texts(original, projected):
        return False
    if original == projected:
        return True
    if any(len(text) > _MAX_CHARS or text.count("\n") + 1 > _MAX_LINES
           for text in (original, projected)):
        return False
    before, after = _structures(original), _structures(projected)
    return before is not None and after is not None and before == after
