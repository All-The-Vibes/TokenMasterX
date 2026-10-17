"""Explicit nonstreaming native Responses adapter over the existing HTTP I/O.

Native metadata stays in the envelope codec; the model, output cap, no-store,
nonstream and single-call controls are fixed transport settings shared by both
off and treatment. They are recorded, never credited as optimizer savings.
"""
from __future__ import annotations

from copy import deepcopy
import json

from .native_responses import NativeResponsesEnvelope
from .transport import Reply, ResponsesTransport, parse_json


VERSION = "native-responses-transport-v1"
_FIELDS = {
    "model", "input", "instructions", "tools", "tool_choice",
    "parallel_tool_calls", "reasoning", "include", "store", "stream",
    "prompt_cache_key", "prompt_cache_retention", "metadata", "text",
    "max_output_tokens", "temperature", "top_p", "safety_identifier", "service_tier",
}


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":"))


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
        body.update(store=False, stream=False, parallel_tool_calls=False)
        if self.reasoning_effort is not None:
            reasoning = body.get("reasoning", {})
            if type(reasoning) is not dict:
                raise ValueError("invalid_native_reasoning")
            if "effort" in reasoning and reasoning["effort"] != self.reasoning_effort:
                raise ValueError("native_reasoning_mismatch")
            body["reasoning"] = {**reasoning, "effort": self.reasoning_effort}
        encoded = _json(body)
        if len(encoded.encode("utf-8")) > self.max_request_bytes:
            raise ValueError("native_request_too_large")
        self._envelope = NativeResponsesEnvelope(
            body, recovery_aliases=self._aliases, recovery_tools=self._recovery_tools,
        )
        self._controls = {
            "version": VERSION,
            "changed_common_fields": sorted(key for key in body if body.get(key) != original.get(key)
                                           or key not in original),
            "scope": "common_transport_controls_not_optimizer_savings",
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
