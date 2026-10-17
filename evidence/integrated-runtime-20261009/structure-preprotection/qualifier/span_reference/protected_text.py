"""Conservative string-span protection, not Markdown rendering or semantic parity.

Changed text may alter prose, but not ordered complete fenced blocks. Recognized
fences use zero to three ASCII spaces, at least three identical backticks or
tildes, and LF/CRLF line boundaries. Closing fences use the same character,
at least the opening length, and only trailing spaces/tabs. Every protected
span includes indentation, info string, content, closing line and its line
ending (if present). Nothing is normalized, parsed as source, or executed.

Runs of three or more backticks/tildes, including mixed runs, are fence-like.
Outside a complete block, unsupported/inline forms are rejected. Inside a
block, shorter fences, other-character fences and inline delimiters are literal
protected content. Single/double inline delimiters are not fenced blocks.
"""
from __future__ import annotations

import re
from typing import NamedTuple


_EXACT = re.compile(r"</?exact[-_]answer\b|BEGIN\s+EXACT\b", re.IGNORECASE)
_FENCE_LIKE = re.compile(r"[`~]{3,}")
_FENCE_LINE = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")


class _Block(NamedTuple):
    start: int
    end: int
    text: str
    interior: str


def _blocks(text: str) -> list[_Block] | None:
    """Return exact ordered block spans, or None for unsupported fence syntax."""
    blocks = []
    start = None
    character, length, offset, interior_start = "", 0, 0, 0
    # Do not use splitlines(): Unicode separators are literal text, not LF/CRLF.
    for part in text.split("\n"):
        end = offset + len(part)
        has_lf = end < len(text)
        line = part[:-1] if has_lf and part.endswith("\r") else part
        end += int(has_lf)
        if "\r" in line:
            return None  # Bare CR boundaries are deliberately unsupported.
        match = _FENCE_LINE.fullmatch(line)
        if start is not None:
            if match is not None:
                fence, suffix = match.groups()
                if fence[0] == character and len(fence) >= length and not suffix.strip(" \t"):
                    blocks.append(_Block(start, end, text[start:end], text[interior_start:offset]))
                    start = None
        elif _FENCE_LIKE.search(line):
            if match is None:
                return None
            fence, info = match.groups()
            # Backtick info strings cannot contain backticks; additional fence-
            # like runs in any info string are ambiguous inline forms to us.
            if (info.startswith(("`", "~")) or (fence[0] == "`" and "`" in info)
                    or _FENCE_LIKE.search(info)):
                return None
            start, character, length = offset, fence[0], len(fence)
            interior_start = end
        offset = end
    return blocks if start is None else None


def _valid_texts(original: str, projected: str) -> bool:
    if type(original) is not str or type(projected) is not str:
        return False
    try:
        original.encode("utf-8")
        projected.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def protected_text_preserved(original: str, projected: str) -> bool:
    """Whether a projection preserves this narrow protected-text contract.

    Valid UTF-8-encodable plain-string identity passes even for unsupported
    markup. Invalid types/surrogates always fail. For changed text, explicit
    exact-answer markers in either input forbid the change; complete fenced
    spans must match byte-for-byte, in order and with the same multiplicity.
    A True result says nothing about the meaning or quality of changed prose.
    """
    if not _valid_texts(original, projected):
        return False
    if original == projected:
        return True
    if _EXACT.search(original) or _EXACT.search(projected):
        return False
    before, after = _blocks(original), _blocks(projected)
    return (before is not None and after is not None
            and [b.text for b in before] == [b.text for b in after])


def restore_protected_text(original: str, projected: str) -> str | None:
    """Restore fence formatting only when corresponding interiors are exact.

    Return an already-safe projection unchanged. Otherwise both inputs must
    parse completely with equal block counts and ordered UTF-8-exact interiors.
    Replace full projected fence spans with originals, preserving projected
    prose; never repair code content. If the same interior belongs to distinct
    original fence spans, that group must already match exactly in place: its
    changed members cannot safely be reassociated by content alone. Identical
    duplicate spans are interchangeable, but their multiplicity is mandatory.

    This optional formatting repair does not establish semantic equivalence,
    model quality or savings. The existing strict guard must accept the result.
    """
    if protected_text_preserved(original, projected):
        return projected
    if not _valid_texts(original, projected) or _EXACT.search(original) or _EXACT.search(projected):
        return None
    before, after = _blocks(original), _blocks(projected)
    if before is None or after is None or len(before) != len(after):
        return None
    variants: dict[str, set[str]] = {}
    for block in before:
        variants.setdefault(block.interior, set()).add(block.text)
    pieces: list[str] = []
    offset = 0
    for old, new in zip(before, after):
        if old.interior != new.interior:
            return None
        if old.text != new.text and len(variants[old.interior]) > 1:
            return None
        pieces.extend((projected[offset:new.start], old.text))
        offset = new.end
    pieces.append(projected[offset:])
    repaired = "".join(pieces)
    return repaired if protected_text_preserved(original, repaired) else None
