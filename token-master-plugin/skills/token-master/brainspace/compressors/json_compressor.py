"""Exact JSON compaction and explicit, recoverable homogeneous-array overviews.

Conservative mode removes only JSON whitespace outside strings. It does not
round numeric values, collapse duplicate members, reorder keys, truncate strings
or sample arrays. Protected/unknown intents and malformed input are passthrough.
Overview samples only homogeneous top-level arrays, with original indices,
cardinality and a full-root recovery reference in a visibly lossy view envelope.
Nested documents and heterogeneous arrays retain every value.
"""

from __future__ import annotations

from decimal import Decimal
import json
import re

from . import report_failure, require_stash


_LEXICAL_WS = re.compile(r'"(?:\\.|[^"\\])*"|[ \t\r\n]+')
_ALERT = re.compile(r"\b(?:DENIED|FAILED|FAILURE|ERROR|FATAL|XPASS|EXCEPTION|WARN(?:ING)?)\b", re.I)
_SUCCESS_STATES = {"ok", "success", "succeeded", "passed", "allowed", "active", "ready", "completed"}


def _invalid_constant(value):
    raise ValueError(f"Non-JSON constant: {value}")


def _compact(content: str) -> str:
    # Preserve string escapes and numeric lexemes, not just parsed equality.
    return _LEXICAL_WS.sub(lambda match: match[0] if match[0][0] == '"' else "", content)


def compress_json(
    content: str,
    *,
    stash=None,
    sample: int = 2,
    tail: int = 1,
    max_str: int = 200,
    intent: str = "conservative",
    **opts,
) -> str:
    """Compact exact JSON, or explicitly sample a recoverable overview.

    ``max_str`` remains accepted for compatibility but strings are never clipped.
    ``sample``/``tail`` apply only to overview; invalid options bypass. Recovery
    failure returns the original input, including its formatting. Unknown kwargs
    cannot force truncation to meet a budget.
    """
    if not isinstance(content, str) or intent not in ("conservative", "overview"):
        return content
    if intent == "overview" and stash is None:
        return content
    try:
        duplicate_members = False

        def object_pairs(pairs):
            nonlocal duplicate_members
            obj = dict(pairs)
            duplicate_members |= len(obj) != len(pairs)
            return obj

        decoder = json.JSONDecoder(parse_float=Decimal, parse_constant=_invalid_constant,
                                   object_pairs_hook=object_pairs)
        data = decoder.decode(content)
        compact = _compact(content)
        if intent == "conservative":
            return compact
        if (type(sample) is not int or type(tail) is not int or
                sample < 0 or tail < 0 or sample + tail == 0):
            return content
        if duplicate_members or _has_alert(data):
            return content
        if not isinstance(data, list) or len(data) <= sample + tail + 1:
            return compact
        shape = _shape(data[0])
        if any(_shape(item) != shape for item in data[1:]):
            return compact

        # Read exact top-level item spans. Do not reserialize retained values:
        # floats, escape spellings, member order and negative zero stay exact.
        items = []
        cursor = 1
        for _ in data:
            _, end = decoder.raw_decode(compact, cursor)
            items.append(compact[cursor:end])
            cursor = end + 1
        indices = list(range(sample)) + list(range(len(data) - tail, len(data)))
        metadata = {
            "_brainspace_view": "overview",
            "lossy": True,
            "total_items": len(data),
            "omitted_items": len(data) - len(indices),
            "indices": indices,
        }
        reference = require_stash(content, stash=stash, ctype="json",
                                  source="full original", kind="root")
        metadata["original"] = reference
        view = (json.dumps(metadata, separators=(",", ":"))[:-1] + ',"items":[' +
                ",".join(items[i] for i in indices) + "]}")
        return view if len(view) < len(content) else content
    except Exception as exc:
        report_failure(opts, exc)
        return content


def _shape(value):
    """Compare all keys, types, nested shapes and array lengths; null != missing."""
    if isinstance(value, dict):
        return (dict, tuple((key, _shape(item)) for key, item in value.items()))
    if isinstance(value, list):
        return (list, tuple(_shape(item) for item in value))
    return type(value)


def _has_alert(value) -> bool:
    """Refuse sampling when failure or unknown status could be answer-bearing."""
    if isinstance(value, dict):
        for key, item in value.items():
            field = key.lower()
            if field in ("status", "state", "outcome", "result"):
                if not isinstance(item, str) or item.lower() not in _SUCCESS_STATES:
                    return True
            if field in ("exit_code", "returncode", "return_code") and item != 0:
                return True
            if field in ("error", "errors", "stderr") and item:
                return True
            if _has_alert(item):
                return True
        return False
    if isinstance(value, list):
        return any(_has_alert(item) for item in value)
    return isinstance(value, str) and bool(_ALERT.search(value))
