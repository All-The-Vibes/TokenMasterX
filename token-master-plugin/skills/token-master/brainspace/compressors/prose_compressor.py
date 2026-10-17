"""Exact prose passthrough.

Unstructured text has no proven insignificant-whitespace boundary: Markdown
hard breaks, fences, indentation, quoted strings and patches are all meaningful.
Word-set equality is not an exactness test. No prose transform is currently
qualified, including for overview. Legacy rate/use_ml kwargs remain accepted
for callers, but do not load models, download assets or change text.
"""

from __future__ import annotations


def compress_prose(
    content: str,
    *,
    stash=None,
    rate: float = 0.5,
    use_ml: bool = False,
    intent: str = "conservative",
    **opts,
) -> str:
    """Return the original unchanged, including whitespace and unsupported types."""
    return content
