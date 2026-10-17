"""Credential-free, opt-in loopback Messages transport for refinement studies.

Captures native wire bodies; does not normalize usage or discover credentials.
Socket/byte limits and configuration validation match ResponsesTransport.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from quality.responses import Reply, ResponsesTransport, _json, _NoRedirect, parse_json


def message_reason(body, model) -> str:
    """Validate a native message independently of transport (including offline)."""
    if (type(body) is not dict or body.get("type") != "message"
            or body.get("role") != "assistant"):
        return "invalid_response"
    if body.get("model") != model:
        return "model_mismatch"
    if body.get("stop_reason") != "end_turn" or type(body.get("content")) is not list:
        return "incomplete_model_response"
    for block in body["content"]:
        if type(block) is not dict:
            return "invalid_response"
        kind = block.get("type")
        if kind not in ("text", "thinking", "redacted_thinking"):
            return "incomplete_model_response"
        key = {"text": "text", "thinking": "thinking", "redacted_thinking": "data"}[kind]
        if type(block.get(key)) is not str:
            return "invalid_response"
    return "ok"


@dataclass(frozen=True)
class MessagesTransport(ResponsesTransport):
    expected_model: str | None = None

    def __post_init__(self):
        super().__post_init__()
        if self.expected_model is not None and (
            type(self.expected_model) is not str or not self.expected_model.strip()
        ):
            raise ValueError("invalid expected response model")

    @property
    def api(self) -> str:
        return "messages"

    def request(self, payload: dict) -> dict:
        if (type(payload) is not dict
                or set(payload) - {"input", "instructions", "reasoning"}):
            raise ValueError("unsupported or stateful request")
        messages = payload.get("input")
        if (type(messages) is not list or len(messages) != 1
                or type(messages[0]) is not dict
                or set(messages[0]) != {"role", "content"}
                or messages[0]["role"] != "user"
                or type(messages[0]["content"]) is not str):
            raise ValueError("one user text required")
        result = {"model": self.model, "messages": messages,
                  "max_tokens": self.max_output_tokens, "stream": False}
        if "instructions" in payload:
            if type(payload["instructions"]) is not str:
                raise ValueError("system text required")
            result["system"] = payload["instructions"]
        if "reasoning" in payload:
            if type(payload["reasoning"]) is not dict or payload["reasoning"] != {"effort": "low"}:
                raise ValueError("only low reasoning effort is supported")
            result["output_config"] = {"effort": "low"}
        return parse_json(_json(result))

    def call(self, payload: dict) -> Reply:
        if not self.allow_network:
            return Reply(False, "network_not_allowed")
        try:
            text = _json(self.request(payload))
            raw_request = text.encode("utf-8")
        except (ValueError, TypeError, RecursionError, UnicodeError):
            return Reply(False, "invalid_request")
        if len(raw_request) > self.max_request_bytes:
            return Reply(False, "request_too_large")
        request = Request(self.base_url.rstrip("/") + "/messages", data=raw_request,
                          headers={"Content-Type": "application/json", "Accept": "application/json",
                                   "anthropic-version": "2023-06-01"}, method="POST")
        start = time.monotonic()
        status = None
        try:
            opener = build_opener(ProxyHandler({}), _NoRedirect())
        except Exception as error:
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
            reason = message_reason(body, self.expected_model or self.model)
        except (ValueError, TypeError, RecursionError):
            reason, body = "invalid_response", None
        return Reply(reason == "ok", reason, True, text, output,
                     body if type(body) is dict else None, status, elapsed)
