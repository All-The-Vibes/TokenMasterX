"""Opt-in production transport for an existing loopback Responses bridge.

No credential discovery, headers, account setup, proxy env, redirects or retries.
Captures complete visible HTTP bodies, NOT provider internals or hidden calls.
Per-socket timeout is not a hard process deadline. Oversized/undecodable replies
are explicitly incomplete and cannot enter a complete reference-token ledger.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import time
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


@dataclass(frozen=True)
class Reply:
    ok: bool
    reason: str
    complete: bool = False
    input_text: str | None = field(default=None, repr=False)
    output_text: str | None = field(default=None, repr=False)
    body: dict | None = field(default=None, repr=False)
    http_status: int | None = None
    elapsed_seconds: float = 0
    error_type: str | None = None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"), sort_keys=True)


def parse_json(text):
    def reject_constant(_):
        raise ValueError("nonfinite JSON")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    return json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique)


@dataclass(frozen=True)
class ResponsesTransport:
    base_url: str
    model: str
    allow_network: bool = False
    max_output_tokens: int = 2048
    max_request_bytes: int = 524288
    max_response_bytes: int = 524288
    timeout: float = 45
    reasoning_effort: str | None = None
    parallel_tool_calls: bool = False

    def __post_init__(self):
        if type(self.parallel_tool_calls) is not bool:
            raise ValueError("parallel_tool_calls must be boolean")
        url = urlparse(self.base_url)
        if (url.scheme != "http" or url.hostname not in ("localhost", "127.0.0.1", "::1")
                or url.username or url.password or url.query or url.fragment):
            raise ValueError("only explicit credential-free loopback bridges are supported")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("model identity required")
        if type(self.allow_network) is not bool:
            raise ValueError("network opt-in must be boolean")
        for name in ("max_output_tokens", "max_request_bytes", "max_response_bytes"):
            if type(getattr(self, name)) is not int or not 0 < getattr(self, name) <= 4_194_304:
                raise ValueError("invalid transport bound")
        if type(self.timeout) not in (int, float) or not math.isfinite(self.timeout) or not 0 < self.timeout <= 90:
            raise ValueError("invalid timeout")
        if self.reasoning_effort is not None and self.reasoning_effort not in (
                "none", "minimal", "low", "medium", "high", "xhigh"):
            raise ValueError("invalid reasoning effort")

    def request(self, payload: dict) -> dict:
        allowed = {"input", "tools", "tool_choice", "parallel_tool_calls", "reasoning", "instructions"}
        if type(payload) is not dict or set(payload) - allowed or "input" not in payload:
            raise ValueError("unsupported or stateful request")
        if self.reasoning_effort is not None:
            expected = {"effort": self.reasoning_effort}
            if "reasoning" in payload and payload["reasoning"] != expected:
                raise ValueError("reasoning configuration mismatch")
            payload = {**payload, "reasoning": expected}
        # A detached body prevents caller mutation during a captured invocation.
        return json.loads(_json({
            **payload, "model": self.model, "max_output_tokens": self.max_output_tokens,
            "stream": False, "store": False,
        }))

    def encode(self, chat: dict) -> str:
        """Materialize final wire without dropping unknown fields.

        This builtin adapter supports text-only complete Chat Completions
        histories with native function calls. A different harness can supply
        its own encode/send adapter; unknown native envelopes are not guessed.
        """
        from .request_policy import _tool_indices

        if (type(chat) is not dict or chat.get("model") != self.model
                or set(chat) - {"model", "messages", "tools", "max_tokens", "max_completion_tokens"}):
            raise ValueError("unsupported canonical request")
        _tool_indices(chat)
        for key in ("max_tokens", "max_completion_tokens"):
            if key in chat and chat[key] != self.max_output_tokens:
                raise ValueError("output declaration differs from transport")
        items = []
        for message in chat["messages"]:
            role, content = message["role"], message.get("content")
            if set(message) - {"role", "content", "tool_calls", "tool_call_id"}:
                raise ValueError("unsupported message metadata")
            if content is not None and type(content) is not str:
                raise ValueError("unsupported nontext message")
            if role == "tool":
                items.append({"type": "function_call_output", "call_id": message["tool_call_id"],
                              "output": content})
            elif message.get("tool_calls"):
                if content is not None:
                    items.append({"role": role, "content": content})
                for call in message["tool_calls"]:
                    if (set(call) != {"id", "type", "function"}
                            or set(call["function"]) != {"name", "arguments"}):
                        raise ValueError("unsupported call metadata")
                    items.append({"type": "function_call", "call_id": call["id"],
                                  "name": call["function"]["name"],
                                  "arguments": call["function"]["arguments"]})
            else:
                items.append({"role": role, "content": content})
        tools = []
        for tool in chat.get("tools", []):
            function = tool["function"]
            if (set(tool) != {"type", "function"} or set(function)
                    - {"name", "description", "parameters", "strict"}):
                raise ValueError("unsupported function schema")
            tools.append({"type": "function", **function})
        payload = {"input": items, "parallel_tool_calls": self.parallel_tool_calls}
        if tools:
            payload["tools"] = tools
        return _json(self.request(payload))

    def call(self, payload: dict) -> Reply:
        if not self.allow_network:
            return Reply(False, "network_not_allowed")
        try:
            text = _json(self.request(payload))
        except (ValueError, TypeError, RecursionError, UnicodeError):
            return Reply(False, "invalid_request")
        return self.send(text)

    def send(self, text: str) -> Reply:
        """Submit exactly a previously checked encode() wire, never rewrap it."""
        if not self.allow_network:
            return Reply(False, "network_not_allowed")
        try:
            if type(text) is not str:
                raise ValueError("complete wire required")
            body = parse_json(text)
            allowed = {"input", "tools", "tool_choice", "parallel_tool_calls", "reasoning", "instructions"}
            if type(body) is not dict:
                raise ValueError("request object required")
            if _json(self.request({k: v for k, v in body.items() if k in allowed})) != text:
                raise ValueError("wire differs from configured transport")
            raw_request = text.encode("utf-8")
        except (ValueError, TypeError, RecursionError, UnicodeError):
            return Reply(False, "invalid_request")
        if len(raw_request) > self.max_request_bytes:
            return Reply(False, "request_too_large")
        return self._send_validated_wire(text)

    def _send_validated_wire(self, text: str) -> Reply:
        """Shared bounded HTTP I/O after an adapter validates its exact wire.

        The legacy public send() retains its existing canonical schema check.
        A native-envelope adapter must independently admit the entire wire;
        this private method is not a new permissive public request interface.
        """
        if not self.allow_network:
            return Reply(False, "network_not_allowed")
        try:
            raw_request = text.encode("utf-8")
        except (AttributeError, UnicodeError):
            return Reply(False, "invalid_request")
        if len(raw_request) > self.max_request_bytes:
            return Reply(False, "request_too_large")
        request = Request(self.base_url.rstrip("/") + "/responses", data=raw_request,
                          headers={"Content-Type": "application/json", "Accept": "application/json"},
                          method="POST")
        start = time.monotonic()
        status = None
        try:
            opener = build_opener(ProxyHandler({}), _NoRedirect())
        except Exception as error:
            # No network attempt occurred. Do not label a prepared request sent.
            return Reply(False, "transport_setup_error", error_type=type(error).__name__)
        try:
            try:
                response = opener.open(request, timeout=self.timeout)
            except HTTPError as error:
                response = error
            with response:
                status = response.status
                raw = response.read(self.max_response_bytes + 1)
        except Exception as error:
            return Reply(False, "transport_error", input_text=text, http_status=status,
                         elapsed_seconds=time.monotonic() - start, error_type=type(error).__name__)
        elapsed = time.monotonic() - start
        if len(raw) > self.max_response_bytes:
            return Reply(False, "response_too_large", input_text=text, http_status=status,
                         elapsed_seconds=elapsed)
        try:
            output = raw.decode("utf-8")
        except UnicodeError:
            return Reply(False, "invalid_utf8", input_text=text, http_status=status,
                         elapsed_seconds=elapsed)
        if status != 200:
            return Reply(False, "http_error", True, text, output, http_status=status,
                         elapsed_seconds=elapsed)
        try:
            body = parse_json(output)
            if type(body) is not dict or body.get("object") != "response":
                raise ValueError("invalid envelope")
            if body.get("model") != self.model:
                return Reply(False, "model_mismatch", True, text, output, body, status, elapsed)
            if body.get("status") != "completed" or type(body.get("output")) is not list:
                return Reply(False, "incomplete_model_response", True, text, output, body, status, elapsed)
        except (ValueError, TypeError, RecursionError):
            return Reply(False, "invalid_response", True, text, output, http_status=status,
                         elapsed_seconds=elapsed)
        return Reply(True, "ok", True, text, output, body, status, elapsed)
