"""Pure, request-local exact-read reuse; no storage, recovery tools, or I/O.

The planner owns eligibility, protected prefixes/recent results, status/exactness,
budgets, and full-wire checks. Receipts are trusted executor observations, not
authentication. Only string tool results with unique visible call bindings are
supported. Find proposes replacements without applying them; restore validates
the entire supplied plan before returning a deep-copied expansion.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import re
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from .request_policy import SourceReadInfo


_PREFIX = "[[EXACT_READ_REUSE:"
_SUFFIX = "]] Identical content remains visible in the earlier tool result in this request."
_TOOLS = ("read_file", "fetch_artifact")


@dataclass(frozen=True)
class ExactReuse:
    source_index: int
    target_index: int
    marker: str
    content_sha256: str

    def __post_init__(self):
        if (type(self.source_index) is not int or type(self.target_index) is not int
                or not 0 <= self.source_index < self.target_index
                or type(self.marker) is not str
                or type(self.content_sha256) is not str
                or re.fullmatch(r"[0-9a-f]{64}", self.content_sha256) is None):
            raise ValueError("invalid exact reuse")


def _marker(data):
    return _PREFIX + json.dumps(data, ensure_ascii=True, sort_keys=True,
                                separators=(",", ":"), allow_nan=False) + _SUFFIX


def _marker_looking(text):
    # Conservatively exclude our markers, CCR references, and partial wrappers.
    return "[[" in text or "]]" in text or "EXACT_READ_REUSE" in text


def _contexts(messages):
    """Index only unambiguous, earlier function calls and unique tool results."""
    if type(messages) is not list or any(type(m) is not dict for m in messages):
        raise ValueError("invalid messages")
    calls, duplicate = {}, set()
    results = Counter(m.get("tool_call_id") for m in messages
                      if m.get("role") == "tool" and type(m.get("tool_call_id")) is str)
    for index, message in enumerate(messages):
        if message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls", []):
            if type(call) is not dict or type(call.get("id")) is not str:
                raise ValueError("invalid tool call")
            call_id = call["id"]
            if call_id in calls:
                duplicate.add(call_id)
            calls[call_id] = (index, call)
    contexts = {}
    for index, message in enumerate(messages):
        call_id = message.get("tool_call_id")
        if (message.get("role") != "tool" or type(call_id) is not str
                or results[call_id] != 1 or call_id in duplicate or call_id not in calls):
            continue
        call_index, call = calls[call_id]
        if call_index < index and call.get("type") == "function":
            contexts[index] = (message, call)
    return contexts


def _data(source, target, info, source_call_id):
    return dict(source_index=source, target_index=target, tool_name=info.tool_name,
                source_path=info.source_path, source_call_id=source_call_id,
                target_call_id=info.call_id, content_sha256=info.content_sha256)


def find_exact_reuses(
    messages, verified_reads: Mapping[int, SourceReadInfo], eligible_targets,
) -> tuple[ExactReuse, ...]:
    """Propose only eligible targets; every proposal references a retained root.

    Invalid/ambiguous receipts cannot anchor or receive reuse. Original strings
    must compare equal, even if their digests collide. Noneligible verified reads
    can anchor. This helper also rechecks visible call bindings defensively.
    """
    from .request_policy import SourceReadInfo

    try:
        contexts = _contexts(messages)
        eligible = tuple(eligible_targets)
        if any(type(i) is not int or not 0 <= i < len(messages) for i in eligible):
            return ()
        targets = set(eligible)
        indices = sorted(i for i in verified_reads if type(i) is int and i in contexts)
        roots, reuses = {}, []
        for index in indices:
            info = verified_reads[index]
            message, call = contexts[index]
            text = message.get("content")
            if (type(info) is not SourceReadInfo or info.status != "success"
                    or info.tool_name not in _TOOLS or type(text) is not str
                    or _marker_looking(text) or not info.matches(message, call)):
                continue
            # Revalidate receipt fields too, in case a frozen object was corrupted.
            SourceReadInfo.from_dict(info.to_dict())
            key = (info.tool_name, info.source_path, text)
            if key not in roots:
                roots[key] = index
            elif index in targets:
                source = roots[key]
                data = _data(source, index, info, messages[source]["tool_call_id"])
                reuses.append(ExactReuse(source, index, _marker(data), info.content_sha256))
        return tuple(reuses)
    except (ValueError, TypeError, AttributeError, KeyError, UnicodeError, RecursionError):
        return ()


def restore_exact_reuses(messages, reuses):
    """Expand from still-visible originals, or raise ValueError on any tampering.

    Pass messages with each selected target's content replaced by its marker.
    The immutable reuse descriptors are supervisor-owned. No external original
    content is accepted, and no caller-owned object is mutated on success/failure.
    """
    from .request_policy import SourceReadInfo

    try:
        contexts = _contexts(messages)
        reuses = tuple(reuses)
        if any(type(r) is not ExactReuse for r in reuses):
            raise ValueError("invalid reuse descriptor")
        targets = {r.target_index for r in reuses}
        if len(targets) != len(reuses):
            raise ValueError("duplicate target")
        replacements = {}
        for reuse in reuses:
            reuse.__post_init__()
            source, target = reuse.source_index, reuse.target_index
            if source in targets or source not in contexts or target not in contexts:
                raise ValueError("missing root or reuse chain")
            original, source_call = contexts[source]
            marked, target_call = contexts[target]
            text = original.get("content")
            if (type(text) is not str or _marker_looking(text)
                    or marked.get("content") != reuse.marker
                    or hashlib.sha256(text.encode("utf-8")).hexdigest() != reuse.content_sha256
                    or not reuse.marker.startswith(_PREFIX) or not reuse.marker.endswith(_SUFFIX)):
                raise ValueError("changed original or marker")
            data = json.loads(reuse.marker[len(_PREFIX):-len(_SUFFIX)])
            if type(data) is not dict or data.get("tool_name") not in _TOOLS:
                raise ValueError("unsupported marker")
            info = SourceReadInfo(
                marked["tool_call_id"], data["tool_name"], data["source_path"],
                reuse.content_sha256, "success",
            )
            expected = _data(source, target, info, original["tool_call_id"])
            if reuse.marker != _marker(expected):
                raise ValueError("changed marker identity")
            source_info = SourceReadInfo(
                original["tool_call_id"], info.tool_name, info.source_path,
                reuse.content_sha256, "success",
            )
            if (not source_info.matches(original, source_call)
                    or not info.matches(dict(marked, content=text), target_call)):
                raise ValueError("changed read binding")
            replacements[target] = text
        expanded = deepcopy(messages)
        for target, text in replacements.items():
            expanded[target]["content"] = text
        return expanded
    except (TypeError, AttributeError, KeyError, UnicodeError, RecursionError) as exc:
        raise ValueError("invalid exact reuse expansion") from exc
