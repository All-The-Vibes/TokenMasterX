"""Lossless native Responses projection for the existing message planner.

Only complete, text-only, stateless histories with ordinary function tools are
supported. Opaque reasoning stays in protected canonical metadata, never fake
assistant prose, and is replayed at its exact original native position.
Canonical message history excludes encoding-only annotations/IDs, so moving a
cache marker does not invalidate an otherwise append-only native conversation.
The planner representation is NOT a wire request: encode/render restore the native
envelope and reject every change except tool text, one marked guidance message,
and lowering an existing output cap. No tools are installed or injected here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from .request_policy import _json_value, _protected, _tool_indices

_OPAQUE = "_native_responses_opaque"
_GUIDANCE = "Optional execution guidance; the user's actual task and requested depth take precedence.\n"
_RECOVERY = {
    "retrieve_original": {"ref": "string", "offset": "integer"},
    "headroom_retrieve": {"hash": "string"},
}
# Status is checked before projection; completed/absent native lifecycle status
# is not a change to a historical tool call. All other tool metadata is exposed
# to the existing strict safety guards, rather than classified as an annotation.
_TOOL_ENCODING = {"type", "id", "status", "phase", "prompt_cache_breakpoint", "cache_control"}


def _wire(value: Any) -> str:
    try:
        if not _json_value(value):
            raise ValueError("native codec requires JSON values")
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        text.encode("utf-8")
        return text
    except (TypeError, RecursionError, UnicodeError) as exc:
        raise ValueError("native codec requires finite UTF-8 JSON") from exc


def _copy(value: Any) -> Any:
    return json.loads(_wire(value))


def _signature(function: dict, name: str) -> None:
    """Accept descriptive native differences, not incompatible constraints."""
    params = function.get("parameters")
    expected = _RECOVERY[name]
    if (type(params) is not dict or params.get("type") != "object"
            or set(params) - {"type", "properties", "required", "additionalProperties", "description", "title"}
            or type(params.get("properties")) is not dict or set(params["properties"]) != set(expected)
            or type(params.get("required")) is not list
            or any(type(key) is not str for key in params["required"])
            or sorted(params["required"]) != sorted(expected)
            or ("additionalProperties" in params and type(params["additionalProperties"]) is not bool)):
        raise ValueError("incompatible registered recovery parameters")
    for key, kind in expected.items():
        prop = params["properties"][key]
        if (type(prop) is not dict or prop.get("type") != kind
                or set(prop) - {"type", "description", "title"}):
            raise ValueError("incompatible registered recovery property")


def _tools(native: list, aliases: dict, standards: list) -> tuple[list, dict]:
    if (type(aliases) is not dict
            or any(key not in _RECOVERY or type(value) is not str or not value
                   for key, value in aliases.items())
            or len(set(aliases.values())) != len(aliases)
            or any(value in _RECOVERY and value != key for key, value in aliases.items())):
        raise ValueError("invalid or conflicting recovery aliases")
    by_name: dict[str, dict] = {}
    for tool in standards:
        if (type(tool) is not dict or set(tool) != {"type", "function"} or tool["type"] != "function"
                or type(tool["function"]) is not dict):
            raise ValueError("invalid canonical recovery schema")
        function = tool["function"]
        name = function.get("name")
        if type(name) is not str or name not in _RECOVERY or name in by_name:
            raise ValueError("duplicate or unknown canonical recovery schema")
        _signature(function, name)
        by_name[name] = tool
    if set(by_name) != set(aliases):
        raise ValueError("each recovery schema requires an explicit alias")
    reverse = {value: key for key, value in aliases.items()}
    seen: set[str] = set()
    projected = []
    for tool in native:
        if (type(tool) is not dict or tool.get("type") != "function"
                or type(tool.get("name")) is not str or not tool["name"]
                or ("parameters" in tool and type(tool["parameters"]) is not dict)
                or "function" in tool):
            raise ValueError("unsupported native tool schema")
        name = tool["name"]
        if name in seen or (name in _RECOVERY and reverse.get(name) != name):
            raise ValueError("duplicate or unqualified recovery registration")
        seen.add(name)
        if name in reverse:
            canonical_name = reverse[name]
            _signature(tool, canonical_name)
            projected.append(_copy(by_name[canonical_name]))
        else:
            projected.append({"type": "function", "function": {
                key: value for key, value in tool.items() if key != "type"}})
    if set(reverse) - seen:
        raise ValueError("recovery alias is not registered natively")
    return projected, reverse


@dataclass(frozen=True, slots=True, init=False)
class NativeResponsesEnvelope:
    """An immutable snapshot; properties/rendered dictionaries are detached.

    ``native_to_canonical`` maps each original input position to its baseline
    message index (parallel calls share an index; opaque reasoning maps to None).
    Recovery aliases map canonical names to already-registered native names.
    Each alias must have one supplied standard recovery schema, and vice versa.
    """

    native_to_canonical: tuple[int | None, ...]
    _native_json: str = field(repr=False)
    _canonical_json: str = field(repr=False)
    _results: tuple[tuple[int, int], ...] = field(repr=False)
    _guidance_native: int | None = field(repr=False)
    _guidance_canonical: int | None = field(repr=False)

    def __init__(self, native_body: dict, *, recovery_aliases: dict[str, str] | None = None,
                 recovery_tools: tuple | list = ()) -> None:
        native = _copy(native_body)
        if (type(native) is not dict or type(native.get("model")) is not str or not native["model"]
                or type(native.get("input")) is not list or not native["input"]
                or {"messages", "max_tokens", "max_completion_tokens", _OPAQUE,
                    "previous_response_id", "conversation"} & set(native)
                or native.get("background", False) is not False
                or native.get("truncation", "disabled") != "disabled"):
            raise ValueError("unsupported, ambiguous, or stateful native request")
        if "max_output_tokens" in native and (
                type(native["max_output_tokens"]) is not int or native["max_output_tokens"] <= 0):
            raise ValueError("native output cap must be a positive integer")
        if type(native.get("tools", [])) is not list or type(recovery_tools) not in (list, tuple):
            raise ValueError("tool schemas must be arrays")
        projected_tools, reverse = _tools(
            native.get("tools", []), _copy({} if recovery_aliases is None else recovery_aliases),
            _copy(list(recovery_tools)))
        canonical = {key: value for key, value in native.items()
                     if key not in ("input", "tools", "max_output_tokens")}
        if "tools" in native:
            canonical["tools"] = projected_tools
        if "max_output_tokens" in native:
            canonical["max_tokens"] = native["max_output_tokens"]
        messages: list[dict[str, Any]] = []
        opaque = []
        mapping: list[int | None] = []
        results = []
        ids: set[str] = set()
        previous_kind = None
        guidance_native = guidance_canonical = None
        for index, item in enumerate(native["input"]):
            if type(item) is not dict:
                raise ValueError("native input items must be objects")
            if "id" in item:
                if type(item["id"]) is not str or not item["id"] or item["id"] in ids:
                    raise ValueError("invalid or duplicate native item id")
                ids.add(item["id"])
            kind = item.get("type", "message" if "role" in item else None)
            if kind == "reasoning":
                opaque.append({"index": index, "item": item})
                mapping.append(None)
                continue
            if kind == "message":
                if (item.get("role") not in ("system", "developer", "user", "assistant")
                        or {"tool_calls", "tool_call_id", "function_call"} & set(item)):
                    raise ValueError("unsupported native message role or calls")
                content = item.get("content")
                if type(content) is list:
                    if any(type(block) is not dict or block.get("type") not in ("input_text", "output_text")
                           or type(block.get("text")) is not str for block in content):
                        raise ValueError("unsupported native content block")
                    # Text blocks may be resegmented when native cache markers
                    # move. Keep the exact character sequence in the planner;
                    # original blocks and ALL annotations remain in the snapshot.
                    content = "".join(block["text"] for block in content)
                elif type(content) is not str:
                    raise ValueError("native messages require text")
                if item["role"] == "user" and guidance_native is None:
                    guidance_native, guidance_canonical = index, len(messages)
                messages.append({"role": item["role"], "content": content})
            elif kind == "function_call":
                if (type(item.get("call_id")) is not str or not item["call_id"]
                        or type(item.get("name")) is not str or not item["name"]
                        or type(item.get("arguments")) is not str or "namespace" in item
                        or item.get("status", "completed") != "completed"):
                    raise ValueError("unsupported or incomplete native function call")
                name = item["name"]
                if name in _RECOVERY and reverse.get(name) != name:
                    raise ValueError("unqualified canonical recovery call")
                call = {"id": item["call_id"], "type": "function", "function": {
                    "name": reverse.get(name, name), "arguments": item["arguments"]}}
                metadata = {key: value for key, value in item.items()
                            if key not in _TOOL_ENCODING | {"call_id", "name", "arguments"}}
                if metadata:
                    call["_native_metadata"] = metadata
                if previous_kind == "function_call":
                    messages[-1]["tool_calls"].append(call)
                else:
                    messages.append({"role": "assistant", "content": None, "tool_calls": [call]})
            elif kind == "function_call_output":
                if (type(item.get("call_id")) is not str or type(item.get("output")) is not str
                        or {"role", "content", "tool_call_id", "tool_calls", "function_call",
                            "structuredContent", "resultType"} & set(item)
                        or item.get("status", "completed") != "completed"):
                    raise ValueError("unsupported native function output")
                result = {"role": "tool", "tool_call_id": item["call_id"], "content": item["output"]}
                metadata = {key: value for key, value in item.items()
                            if key not in _TOOL_ENCODING | {"call_id", "output"}}
                if metadata:
                    result["_native_metadata"] = metadata
                messages.append(result)
                results.append((index, len(messages) - 1))
            else:
                raise ValueError("unsupported native input item")
            mapping.append(len(messages) - 1)
            previous_kind = kind
        canonical["messages"] = messages
        if opaque:
            canonical[_OPAQUE] = opaque
        _tool_indices(canonical)  # Complete, unique, ordered call/result pairing.
        object.__setattr__(self, "_native_json", _wire(native))
        object.__setattr__(self, "_canonical_json", _wire(canonical))
        object.__setattr__(self, "_results", tuple(results))
        object.__setattr__(self, "native_to_canonical", tuple(mapping))
        object.__setattr__(self, "_guidance_native", guidance_native)
        object.__setattr__(self, "_guidance_canonical", guidance_canonical)

    @property
    def canonical_request(self) -> dict:
        return json.loads(self._canonical_json)

    def render(self, canonical: dict) -> dict:
        candidate = _copy(canonical)
        baseline = self.canonical_request
        if type(candidate) is not dict or type(candidate.get("messages")) is not list:
            raise ValueError("canonical messages required")
        messages = candidate["messages"]
        guidance = None
        if len(messages) == len(baseline["messages"]) + 1:
            if self._guidance_canonical is None:
                raise ValueError("guidance requires an original user message")
            guidance = messages.pop(self._guidance_canonical)
            if (type(guidance) is not dict or set(guidance) != {"role", "content"}
                    or guidance["role"] != "user" or type(guidance["content"]) is not str
                    or not guidance["content"].startswith(_GUIDANCE)
                    or not guidance["content"][len(_GUIDANCE):]):
                raise ValueError("only marked runtime guidance may be inserted")
        if len(messages) != len(baseline["messages"]):
            raise ValueError("native history cannot be deleted or extended")
        native = json.loads(self._native_json)
        for native_index, canonical_index in self._results:
            message = messages[canonical_index]
            if type(message) is not dict or type(message.get("content")) is not str:
                raise ValueError("tool replacements must be text")
            original = baseline["messages"][canonical_index]
            if message["content"] != original["content"] and _protected(
                    {key: value for key, value in original.items() if key != "content"}, strict_status=True):
                raise ValueError("failed or explicitly protected tool result cannot change")
            native["input"][native_index]["output"] = message["content"]
            message["content"] = original["content"]
        if "max_tokens" in baseline:
            cap = candidate.get("max_tokens")
            if type(cap) is not int or not 0 < cap <= baseline["max_tokens"]:
                raise ValueError("existing output cap may only be lowered")
            native["max_output_tokens"] = cap
            candidate["max_tokens"] = baseline["max_tokens"]
        if _wire(candidate) != self._canonical_json:
            raise ValueError("protected native request fields changed")
        if guidance is not None:
            assert self._guidance_native is not None
            native["input"].insert(self._guidance_native, {"type": "message", **guidance})
        return native

    def encode(self, canonical: dict) -> str:
        return _wire(self.render(canonical))
