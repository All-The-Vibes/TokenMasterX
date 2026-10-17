"""Opt-in, stdlib-only Jev advisory decisions; no retries or fallback policy.

Network use discloses the supplied state and questions to TypeSafe. Callers must
explicitly enable network access AND label each request synthetic or sanitized.
This label is a caller attestation, not a sanitizer or a zero-retention promise.
Request/response bodies remain in process and are excluded from repr and errors.
Only a caller can choose to persist them or measure them with a reference tokenizer.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field, replace
from http.client import HTTPException
from typing import Any, Literal, TypedDict
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MODEL = "jev-1.13.0"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
PROBABILITY_TOLERANCE = 1e-6
Structured = str | dict[str, Any] | list[Any]


class Choice(TypedDict):
    type: Literal["choice"]
    instructions: Structured
    criteria: dict[str, Structured | None]


class Score(TypedDict):
    type: Literal["score"]
    instructions: Structured
    criteria: list[Structured]


class _NoulRequired(TypedDict):
    type: Literal["noul"]
    instructions: Structured


class Noul(_NoulRequired, total=False):
    criteria: dict[Literal["true", "false"], Structured]


Question = Choice | Score | Noul


class ChoiceAnswer(TypedDict):
    type: Literal["choice"]
    choice: str
    probabilities: dict[str, float]
    confidence: float


class ScoreAnswer(TypedDict):
    type: Literal["score"]
    score: float
    legend: dict[str, Structured]
    probabilities: dict[str, float]
    confidence: float


class NoulAnswer(TypedDict):
    type: Literal["noul"]
    noul: float


class Usage(TypedDict):
    input_tokens: int
    output_tokens: int


class Payload(TypedDict):
    model: str
    answers: dict[str, ChoiceAnswer | ScoreAnswer | NoulAnswer]
    usage: Usage


class ValidationError(ValueError):
    """A fixed reason code, never input content or provider error details."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValidationError(reason)


def _number(value: Any) -> bool:
    # Avoid float conversion overflow for untrusted, arbitrarily large integers.
    return type(value) is int or (type(value) is float and math.isfinite(value))


def _json_tree(value: Any, depth: int = 0) -> bool:
    """Require JSON-native types, finite floats, string keys and bounded nesting."""
    if depth > 64:
        return False
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is list:
        return all(_json_tree(item, depth + 1) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _json_tree(item, depth + 1)
                   for key, item in value.items())
    return False


def _structured(value: Any) -> bool:
    return type(value) in (str, dict, list)


def _copy_json(value: Any, reason: str) -> Any:
    try:
        _require(_json_tree(value), reason)
        return json.loads(json.dumps(value, allow_nan=False, ensure_ascii=True))
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise ValidationError(reason) from None


def validate_request(state: Structured, questions: dict[str, Question]) -> dict[str, Any]:
    """Return a detached, pinned wire request or raise a content-free error."""
    reason = "invalid_request"
    body = _copy_json({"state": state, "model": MODEL, "questions": questions}, reason)
    _require(_structured(body["state"]), reason)
    qmap = body["questions"]
    _require(type(qmap) is dict and bool(qmap), reason)
    for question in qmap.values():
        _require(type(question) is dict, reason)
        _require(set(question) <= {"type", "instructions", "criteria"}, reason)
        _require(_structured(question.get("instructions")), reason)
        kind = question.get("type")
        criteria = question.get("criteria")
        if kind == "choice":
            _require(type(criteria) is dict and 1 <= len(criteria) <= 255, reason)
            _require(all(item is None or _structured(item) for item in criteria.values()), reason)
        elif kind == "score":
            _require(type(criteria) is list and 2 <= len(criteria) <= 10, reason)
            _require(all(_structured(item) for item in criteria), reason)
        elif kind == "noul":
            if "criteria" in question:
                _require(type(criteria) is dict and set(criteria) <= {"true", "false"}, reason)
                _require(all(_structured(item) for item in criteria.values()), reason)
        else:
            raise ValidationError(reason)
    return body


def _probability(value: Any) -> bool:
    return _number(value) and 0 <= value <= 1


def _distribution(value: Any, keys: set[str]) -> None:
    reason = "invalid_response"
    _require(type(value) is dict and set(value) == keys, reason)
    _require(all(_probability(item) for item in value.values()), reason)
    _require(math.isclose(math.fsum(value.values()), 1.0, rel_tol=0,
                          abs_tol=PROBABILITY_TOLERANCE), reason)


def validate_response(payload: Any, questions: dict[str, Question]) -> Payload:
    """Validate expected IDs, types, distributions, model and native usage.

    Unknown JSON metadata is retained. Confidence is range-checked, not treated
    as calibrated correctness. Structured Score legends may echo the requested
    JSON or use the HTTP reference's string form, whose serialization is unspecified.
    """
    reason = "invalid_response"
    qmap = validate_request("", questions)["questions"]
    body = _copy_json(payload, reason)
    _require(type(body) is dict and body.get("model") == MODEL, reason)
    answers, usage = body.get("answers"), body.get("usage")
    _require(type(answers) is dict and set(answers) == set(qmap), reason)
    _require(type(usage) is dict, reason)
    for name in ("input_tokens", "output_tokens"):
        _require(type(usage.get(name)) is int and usage[name] >= 0, reason)
    for qid, question in qmap.items():
        answer = answers[qid]
        kind = question["type"]
        _require(type(answer) is dict and answer.get("type") == kind, reason)
        if kind == "noul":
            _require(_probability(answer.get("noul")), reason)
            continue
        _require(_probability(answer.get("confidence")), reason)
        if kind == "choice":
            keys = set(question["criteria"])
            probabilities = answer.get("probabilities")
            _distribution(probabilities, keys)
            choice = answer.get("choice")
            _require(type(choice) is str and choice in keys, reason)
            _require(probabilities[choice] + PROBABILITY_TOLERANCE >=
                     max(probabilities.values()), reason)
        else:
            criteria = question["criteria"]
            keys = {str(i) for i in range(len(criteria))}
            probabilities, legend = answer.get("probabilities"), answer.get("legend")
            _distribution(probabilities, keys)
            _require(type(legend) is dict and set(legend) == keys, reason)
            for i, description in enumerate(criteria):
                value = legend[str(i)]
                if type(description) is str:
                    _require(type(value) is str and value == description, reason)
                elif type(value) is not str:
                    # Structured examples/SDK types preserve the rubric JSON.
                    # JSON comparison distinguishes true from 1, unlike Python ==.
                    _require(type(value) is type(description), reason)
                    _require(json.dumps(value, sort_keys=True, ensure_ascii=False) ==
                             json.dumps(description, sort_keys=True, ensure_ascii=False), reason)
            score = answer.get("score")
            _require(_number(score) and 0 <= score <= len(criteria) - 1, reason)
            expectation = math.fsum(i * probabilities[str(i)] for i in range(len(criteria)))
            _require(math.isclose(score, expectation, rel_tol=0,
                                  abs_tol=PROBABILITY_TOLERANCE), reason)
    return body


@dataclass(frozen=True)
class Diagnostics:
    """Native counts/transport facts, NOT reference-token ledger measurements."""

    attempts: int = 0
    http_status: int | None = None
    request_bytes: int = 0
    response_bytes: int = 0
    response_complete: bool = False
    native_input_tokens: int | None = None
    native_output_tokens: int | None = None


@dataclass(frozen=True)
class Result:
    ok: bool
    reason: str
    request_text: str | None = field(default=None, repr=False)
    response_text: str | None = field(default=None, repr=False)
    payload: Payload | None = field(default=None, repr=False)
    diagnostics: Diagnostics = field(default_factory=Diagnostics)

    def validate(self, questions: dict[str, Question]) -> bool:
        """Recheck an accepted payload (including after caller-side mutation)."""
        if not self.ok:
            return False
        try:
            validate_response(self.payload, questions)
            return True
        except ValidationError:
            return False


class _DenyRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, "invalid_response")
        result[key] = value
    return result


@dataclass(frozen=True)
class JevClient:
    """Fixed HTTPS destination; one attempt; no proxy-env or credential discovery.

    ``timeout`` bounds each blocking socket operation, not total elapsed time.
    HTTP response bodies are bounded before decoding. Oversized/undecodable
    responses return no response_text rather than masquerading as complete text.
    """

    enabled: bool = False
    allow_network: bool = False
    timeout: float = 10.0
    max_response_bytes: int = 1024 * 1024
    max_request_bytes: int = 1024 * 1024

    def __post_init__(self) -> None:
        if not (type(self.enabled) is bool and type(self.allow_network) is bool
                and _number(self.timeout) and 0 < self.timeout <= 60
                and type(self.max_response_bytes) is int
                and 0 < self.max_response_bytes <= 4 * 1024 * 1024
                and type(self.max_request_bytes) is int
                and 0 < self.max_request_bytes <= 4 * 1024 * 1024):
            raise ValueError("invalid_client_configuration")

    def decide(
        self,
        state: Structured,
        questions: dict[str, Question],
        *,
        data_classification: Literal["synthetic", "sanitized"] | None = None,
    ) -> Result:
        """Disclose only explicitly approved synthetic/sanitized input to TypeSafe.

        Reads only TYPESAFE_API_KEY, at call time after gates and validation.
        Never logs, persists bodies, retries, or substitutes a fallback decision.
        """
        if not self.enabled:
            return Result(False, "disabled")
        if not self.allow_network:
            return Result(False, "network_not_allowed")
        if data_classification not in ("synthetic", "sanitized"):
            return Result(False, "data_classification_required")
        try:
            body = validate_request(state, questions)
            request_text = json.dumps(body, ensure_ascii=True, allow_nan=False,
                                      separators=(",", ":"))
        except ValidationError:
            return Result(False, "invalid_request")
        request_bytes = request_text.encode("utf-8")
        diagnostic = Diagnostics(request_bytes=len(request_bytes))
        if len(request_bytes) > self.max_request_bytes:
            return Result(False, "request_too_large", diagnostics=diagnostic)
        key = os.getenv("TYPESAFE_API_KEY")
        if not key:
            return Result(False, "missing_api_key", request_text, diagnostics=diagnostic)
        if not key.isascii() or any(ord(char) <= 32 or ord(char) == 127 for char in key):
            return Result(False, "invalid_api_key", request_text, diagnostics=diagnostic)
        request = Request(ENDPOINT, data=request_bytes, method="POST", headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        })
        status = None
        try:
            opener = build_opener(ProxyHandler({}), _DenyRedirects())
            try:
                response = opener.open(request, timeout=self.timeout)
            except HTTPError as error:
                response = error
            with response:
                status = response.status
                raw = response.read(self.max_response_bytes + 1)
        except (OSError, HTTPException, ValueError):
            return Result(False, "transport_error", request_text, diagnostics=Diagnostics(
                attempts=1, http_status=status, request_bytes=len(request_bytes)))
        diagnostic = Diagnostics(attempts=1, http_status=status,
                                 request_bytes=len(request_bytes), response_bytes=len(raw))
        if len(raw) > self.max_response_bytes:
            return Result(False, "response_too_large", request_text, diagnostics=diagnostic)
        try:
            response_text = raw.decode("utf-8")
        except UnicodeError:
            return Result(False, "invalid_response_encoding", request_text, diagnostics=diagnostic)
        diagnostic = Diagnostics(attempts=1, http_status=status, request_bytes=len(request_bytes),
                                 response_bytes=len(raw), response_complete=True)
        if 300 <= status < 400:
            return Result(False, "redirect_denied", request_text, response_text,
                          diagnostics=diagnostic)
        if status != 200:
            return Result(False, "http_error", request_text, response_text, diagnostics=diagnostic)
        try:
            decoded = json.loads(response_text, object_pairs_hook=_unique_object)
            # A rejected decision can still consume provider tokens. Preserve
            # well-formed native counts independently of decision acceptance.
            usage = decoded.get("usage") if type(decoded) is dict else None
            if type(usage) is dict and all(
                type(usage.get(name)) is int and usage[name] >= 0
                for name in ("input_tokens", "output_tokens")
            ):
                diagnostic = replace(
                    diagnostic, native_input_tokens=usage["input_tokens"],
                    native_output_tokens=usage["output_tokens"],
                )
            payload = validate_response(decoded, body["questions"])
        except (ValueError, TypeError, RecursionError, OverflowError):
            return Result(False, "invalid_response", request_text, response_text,
                          diagnostics=diagnostic)
        return Result(True, "ok", request_text, response_text, payload, diagnostic)
