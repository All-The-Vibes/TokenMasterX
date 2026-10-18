"""Explicit nonstreaming native Responses adapter over the existing HTTP I/O.

Native metadata stays in the envelope codec; the model, output cap, no-store,
nonstream and single-call controls are fixed transport settings shared by both
off and treatment. They are recorded, never credited as optimizer savings.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re

from .native_responses import NativeResponsesEnvelope
from .transport import Reply, ResponsesTransport, parse_json


VERSION = "native-responses-transport-v2"
_FIELDS = {
    "model", "input", "instructions", "tools", "tool_choice",
    "parallel_tool_calls", "reasoning", "include", "store", "stream",
    "prompt_cache_key", "prompt_cache_retention", "metadata", "text",
    "max_output_tokens", "temperature", "top_p", "safety_identifier", "service_tier",
}
_SESSION_FOLDER = re.compile(r"^Session folder: (.*session-state.*)$", re.MULTILINE)
SESSION_FOLDER_MOVED = "Session folder: stated in the first user message"


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":"))


def _texts(item):
    """(holder, key) for each text of a message, in order."""
    content = item.get("content")
    if type(content) is str:
        return [(item, "content")]
    if type(content) is list:
        return [(block, "text") for block in content if type(block) is dict and type(block.get("text")) is str]
    return []


def _replace_span(parts, start, end, new):
    """Replace characters start..end of the parts' joined text with ``new``; every part keeps its metadata."""
    texts = [holder[key] for holder, key in parts]
    joined = "".join(texts)
    result, delta, cuts, offset = joined[:start] + new + joined[end:], len(new) - (end - start), [], 0
    for text in texts[:-1]:
        offset += len(text)
        cuts.append(offset if offset <= start else offset + delta if offset >= end else start + len(new))
    bounds = [0, *cuts, len(result)]
    for (holder, key), low, high in zip(parts, bounds, bounds[1:]):
        holder[key] = result[low:high]


def stable_session_prefix(body):
    """Move Copilot CLI's per-session folder line from the system prompt to the first user message.

    The provider caches exact prompt prefixes. Copilot CLI writes each session's own folder into
    its system prompt, so a new session never reuses another session's cached prefix. With the
    line moved, the system prompt is the same for every session in a repository, and a new
    session's first call can read it from the cache. Every call of a session gets the same
    rewrite, so earlier messages stay byte-identical. The line is matched on each message's
    joined text, because clients may split text blocks differently from call to call. Returns
    ``body`` itself (unchanged) unless exactly one such line precedes the first user message.
    """
    items = body.get("input") if type(body) is dict else None
    if type(items) is not list:
        return body
    sources, user = [], None
    if type(body.get("instructions")) is str:
        sources.append((None, [(body, "instructions")]))
    for index, item in enumerate(items):
        if type(item) is not dict:
            continue
        if item.get("role") == "user":
            user = index
            break
        if item.get("role") in ("system", "developer"):
            sources.append((index, _texts(item)))
    found = [(index, match) for index, parts in sources
             for match in _SESSION_FOLDER.finditer("".join(holder[key] for holder, key in parts))]
    if user is None or len(found) != 1 or not _texts(items[user]):
        return body
    index, match = found[0]
    moved = deepcopy(body)
    parts = [(moved, "instructions")] if index is None else _texts(moved["input"][index])
    _replace_span(parts, match.start(), match.end(), SESSION_FOLDER_MOVED)
    holder, key = _texts(moved["input"][user])[0]
    holder[key] = f"Session folder: {match.group(1).strip()}\n\n" + holder[key]
    return moved


class NativeResponsesTransport:
    def __init__(self, *, recovery_aliases=None, recovery_tools=(), **configuration):
        self._base = ResponsesTransport(**configuration)
        self._aliases = deepcopy(recovery_aliases)
        self._recovery_tools = deepcopy(recovery_tools)
        self._envelope = None
        self._admitted = set()
        self._used = True
        self._controls = None

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._base, name)

    def bind(self, native):
        """Bind one caller-owned request before RuntimeSession invokes encode."""
        self._used, self._envelope = True, None
        self._admitted.clear()
        self._controls = None
        if type(native) is not dict or set(native) - _FIELDS:
            raise ValueError("unsupported_native_request_fields")
        # Also rejects non-JSON values, duplicate keys after decoding elsewhere,
        # nonfinite numbers and escaped invalid UTF-8 before network submission.
        original = parse_json(_json(native))
        _json(original).encode("utf-8")
        if original.get("model") != self.model:
            raise ValueError("native_model_mismatch")
        if original.get("store", False) is not False:
            raise ValueError("native_no_store_required")
        if original.get("stream", False) is not False:
            raise ValueError("native_nonstream_required")
        if "parallel_tool_calls" in original and type(original["parallel_tool_calls"]) is not bool:
            raise ValueError("invalid_native_parallel_control")
        body = deepcopy(original)
        cap = body.get("max_output_tokens", self.max_output_tokens)
        if type(cap) is not int or cap < 1:
            raise ValueError("invalid_native_output_limit")
        body["max_output_tokens"] = min(cap, self.max_output_tokens)
        # Keep the client's parallel tool calls (default on); v6 was measured with them on.
        body.update(store=False, stream=False, parallel_tool_calls=original.get("parallel_tool_calls", True))
        if self.reasoning_effort is not None:
            reasoning = body.get("reasoning", {})
            if type(reasoning) is not dict:
                raise ValueError("invalid_native_reasoning")
            if "effort" in reasoning and reasoning["effort"] != self.reasoning_effort:
                raise ValueError("native_reasoning_mismatch")
            body["reasoning"] = {**reasoning, "effort": self.reasoning_effort}
        native = stable_session_prefix(body)
        encoded = _json(native)
        if len(encoded.encode("utf-8")) > self.max_request_bytes:
            raise ValueError("native_request_too_large")
        self._envelope = NativeResponsesEnvelope(
            native, recovery_aliases=self._aliases, recovery_tools=self._recovery_tools,
        )
        self._controls = {
            "version": VERSION,
            "changed_common_fields": sorted(key for key in body if body.get(key) != original.get(key)
                                           or key not in original),
            "scope": "common_transport_controls_not_optimizer_savings",
            "stable_session_prefix": native is not body,
        }
        self._used = False
        return self._envelope.canonical_request

    @property
    def controls(self):
        return deepcopy(self._controls)

    def encode(self, canonical):
        if self._envelope is None or self._used:
            raise ValueError("native_request_not_bound")
        wire = self._envelope.encode(canonical)
        if type(wire) is not str or len(wire.encode("utf-8")) > self.max_request_bytes:
            raise ValueError("native_wire_too_large")
        if len(self._admitted) >= 16 and wire not in self._admitted:
            raise ValueError("native_materialization_limit")
        self._admitted.add(wire)
        return wire

    def send(self, wire):
        if not self.allow_network:
            return Reply(False, "network_not_allowed")
        if self._used or type(wire) is not str or wire not in self._admitted:
            return Reply(False, "invalid_request")
        self._used = True
        self._admitted.clear()
        return self._base._send_validated_wire(wire)
