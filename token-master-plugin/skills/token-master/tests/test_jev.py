"""Offline, synthetic regressions for the bounded Jev HTTP contract."""
import copy
import io
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, build_opener
from urllib.response import addinfourl

import pytest

_SKILL = Path(__file__).resolve().parents[1]
if str(_SKILL) not in sys.path:
    sys.path.insert(0, str(_SKILL))

from brainspace import jev  # noqa: E402 - support repository-root pytest invocation


def questions():
    return {
        "route": {"type": "choice", "instructions": "Choose a route.",
                  "criteria": {"keep": None, "skip": "Not relevant"}},
        "quality": {"type": "score", "instructions": "Rate relevance.",
                    "criteria": ["Unrelated", "Relevant", "Essential"]},
        "safe": {"type": "noul", "instructions": "Is this synthetic?",
                 "criteria": {"true": "Invented data", "false": "Real data"}},
    }


def payload():
    return {
        "model": "jev-1.13.0",
        "answers": {
            "route": {"type": "choice", "choice": "keep",
                      "probabilities": {"keep": 0.8, "skip": 0.2},
                      "confidence": 0.6},
            "quality": {"type": "score", "score": 1.05,
                        "legend": {"0": "Unrelated", "1": "Relevant", "2": "Essential"},
                        "probabilities": {"0": 0.0, "1": 0.95, "2": 0.05},
                        "confidence": 0.92},
            "safe": {"type": "noul", "noul": 0.9},
        },
        "usage": {"input_tokens": 318, "output_tokens": 34},
    }


class Response(io.BytesIO):
    status = 200


@pytest.fixture(autouse=True)
def no_real_network_or_keys(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Tests must not access real network or credentials")
    monkeypatch.setattr(jev, "build_opener", forbidden)
    monkeypatch.setattr(jev.os, "getenv", forbidden)


def transport(monkeypatch, body=None, error=None):
    calls = []
    response = Response((body if body is not None else json.dumps(payload())).encode())

    class Opener:
        def open(self, request, timeout):
            calls.append((request, timeout))
            if error:
                raise error
            return response

    def build(*handlers):
        assert any(isinstance(h, ProxyHandler) and h.proxies == {} for h in handlers)
        redirect = next(h for h in handlers if isinstance(h, HTTPRedirectHandler))
        for code in (301, 302, 303, 307, 308):
            assert redirect.redirect_request(None, None, code, "", {}, "https://evil.invalid") is None
        return Opener()

    def getenv(name):
        assert name == "TYPESAFE_API_KEY"
        return "synthetic-test-key"

    monkeypatch.setattr(jev, "build_opener", build)
    monkeypatch.setattr(jev.os, "getenv", getenv)
    return calls, response


def enabled(**kwargs):
    return jev.JevClient(enabled=True, allow_network=True, **kwargs)


def test_defaults_never_read_key_or_open_network():
    result = jev.JevClient().decide("synthetic state", questions())
    assert not result.ok and result.reason == "disabled"
    assert result.request_text is None and result.response_text is None
    assert result.diagnostics.attempts == 0


@pytest.mark.parametrize("kwargs,classification,reason", [
    ({"enabled": True}, "synthetic", "network_not_allowed"),
    ({"allow_network": True}, "synthetic", "disabled"),
    ({"enabled": True, "allow_network": True}, None, "data_classification_required"),
    ({"enabled": True, "allow_network": True}, "private", "data_classification_required"),
])
def test_explicit_opt_ins(kwargs, classification, reason):
    result = jev.JevClient(**kwargs).decide("state", questions(), data_classification=classification)
    assert not result.ok and result.reason == reason
    assert result.diagnostics.attempts == 0


@pytest.mark.parametrize("classification", ["synthetic", "sanitized"])
def test_full_round_trip_and_separate_diagnostics(monkeypatch, classification):
    raw = json.dumps(payload(), indent=2)
    calls, response = transport(monkeypatch, body=raw)
    client = enabled(timeout=2.5)
    result = client.decide({"text": "invented café"}, questions(), data_classification=classification)
    assert result.ok and result.reason == "ok"
    assert result.payload == payload()
    assert result.response_text == raw
    request, timeout = calls[0]
    assert len(calls) == 1 and timeout == 2.5
    assert request.full_url == "https://api.typesafe.ai/v1/systemone"
    assert request.method == "POST"
    assert request.get_header("Authorization") == "Bearer synthetic-test-key"
    assert request.get_header("Content-type") == "application/json"
    assert request.data.decode("utf-8") == result.request_text
    assert json.loads(result.request_text) == {
        "model": "jev-1.13.0", "state": {"text": "invented café"}, "questions": questions(),
    }
    assert result.diagnostics.native_input_tokens == 318
    assert result.diagnostics.native_output_tokens == 34
    assert result.diagnostics.request_bytes == len(request.data)
    assert result.diagnostics.response_bytes == len(raw.encode())
    assert result.diagnostics.response_complete
    assert result.diagnostics.attempts == 1 and result.diagnostics.http_status == 200
    assert response.closed
    for secret in ("invented", "café", "synthetic-test-key", "Unrelated"):
        assert secret not in repr(client) + repr(result)
    assert result.validate(questions())


@pytest.mark.parametrize("change", [
    lambda q: q.clear(),
    lambda q: q.update({1: q.pop("safe")}),
    lambda q: q["safe"].update(type="other"),
    lambda q: q["safe"].update(instructions=None),
    lambda q: q["safe"].update(criteria={"yes": "wrong field"}),
    lambda q: q["route"].update(criteria={}),
    lambda q: q["route"].update(criteria={str(i): None for i in range(256)}),
    lambda q: q["route"].update(criteria={"keep": 42}),
    lambda q: q["quality"].update(criteria=["one"]),
    lambda q: q["quality"].update(criteria=["level"] * 11),
    lambda q: q["quality"].update(criteria=["ok", None]),
    lambda q: q["safe"].update(temperature=0),
])
def test_bad_questions_are_rejected_before_key_access(change):
    q = questions()
    change(q)
    result = enabled().decide("state", q, data_classification="synthetic")
    assert not result.ok and result.reason == "invalid_request"
    assert result.payload is None and result.diagnostics.attempts == 0


@pytest.mark.parametrize("state", [None, True, 123, {"x": float("nan")},
                                         {"x": float("inf")}, {1: "non-string key"}, {"x": object()}])
def test_invalid_states_rejected(state):
    result = enabled().decide(state, questions(), data_classification="synthetic")
    assert result.reason == "invalid_request"


def test_circular_state_is_safe():
    state = []
    state.append(state)
    assert enabled().decide(state, questions(), data_classification="synthetic").reason == "invalid_request"


def test_structured_instructions_and_criteria_supported():
    q = {
        "choice": {"type": "choice", "instructions": {"q": ["Choose"]},
                   "criteria": {"a": {"description": "A"}, "b": ["B"]}},
        "score": {"type": "score", "instructions": ["Rate"],
                  "criteria": [{"level": "low"}, ["high"]]},
        "noul": {"type": "noul", "instructions": "Yes?"},
    }
    request = jev.validate_request(["invented"], q)
    assert request["questions"] == q
    request["questions"]["choice"]["criteria"]["a"] = None
    assert q["choice"]["criteria"]["a"] == {"description": "A"}


@pytest.mark.parametrize("change", [
    lambda p: p.update(model="jev-latest"),
    lambda p: p.pop("usage"),
    lambda p: p["usage"].update(input_tokens=True),
    lambda p: p["usage"].update(output_tokens=-1),
    lambda p: p["usage"].update(input_tokens=1.5),
    lambda p: p["answers"].pop("safe"),
    lambda p: p["answers"].update(unexpected={"type": "noul", "noul": 1}),
    lambda p: p["answers"]["safe"].update(type="score"),
    lambda p: p["answers"]["safe"].update(noul=float("nan")),
    lambda p: p["answers"]["safe"].update(noul=float("inf")),
    lambda p: p["answers"]["safe"].update(noul=True),
    lambda p: p["answers"]["safe"].update(noul=1.01),
    lambda p: p["answers"]["route"].update(choice="unknown"),
    lambda p: p["answers"]["route"].update(choice="skip"),
    lambda p: p["answers"]["route"].update(confidence=-0.1),
    lambda p: p["answers"]["route"]["probabilities"].update(keep=0.5),
    lambda p: p["answers"]["route"]["probabilities"].update(keep=1.2, skip=-0.2),
    lambda p: p["answers"]["route"]["probabilities"].pop("skip"),
    lambda p: p["answers"]["quality"].update(score=2.1),
    lambda p: p["answers"]["quality"].update(score=0.5),
    lambda p: p["answers"]["quality"]["legend"].update({"0": "Changed"}),
    lambda p: p["answers"]["quality"]["probabilities"].update({"3": 0}),
])
def test_bad_responses_are_failures_not_decisions(monkeypatch, change):
    p = payload()
    change(p)
    raw = json.dumps(p)
    calls, _ = transport(monkeypatch, body=raw)
    result = enabled().decide("state", questions(), data_classification="synthetic")
    assert not result.ok and result.reason == "invalid_response" and result.payload is None
    assert result.request_text and result.response_text == raw
    assert result.diagnostics.response_complete and len(calls) == 1
    assert not result.validate(questions())


@pytest.mark.parametrize("body", ['not JSON', '[]', '{}', '{"model":"a","model":"b"}'])
def test_malformed_and_duplicate_json(monkeypatch, body):
    transport(monkeypatch, body=body)
    result = enabled().decide("state", questions(), data_classification="synthetic")
    assert result.reason == "invalid_response" and result.response_text == body


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308, 401, 422, 429, 529])
def test_http_errors_and_redirects_never_retry_or_echo(monkeypatch, status, capsys):
    raw = b'{"detail":"synthetic-secret state and key"}'
    stream = io.BytesIO(raw)
    error = HTTPError("https://api.typesafe.ai/v1/systemone", status,
                      "synthetic-secret", {"Location": "https://evil.invalid"}, stream)
    calls, _ = transport(monkeypatch, error=error)
    result = enabled().decide("state", questions(), data_classification="synthetic")
    assert result.reason == ("redirect_denied" if status < 400 else "http_error")
    assert not result.ok and result.payload is None
    assert result.response_text == raw.decode()
    assert result.diagnostics.http_status == status and len(calls) == 1
    assert stream.closed
    assert "synthetic-secret" not in repr(result)
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("error", [TimeoutError("secret"), URLError("secret"), OSError("secret")])
def test_transport_failure_is_safe_and_not_retried(monkeypatch, error):
    calls, _ = transport(monkeypatch, error=error)
    result = enabled().decide("synthetic-secret-state", questions(), data_classification="synthetic")
    assert result.reason == "transport_error" and not result.ok and len(calls) == 1
    assert result.request_text and result.response_text is None
    assert not result.diagnostics.response_complete
    assert "secret" not in repr(result)


@pytest.mark.parametrize("key,reason", [(None, "missing_api_key"), ("", "missing_api_key"),
                                     ("key\r\nInjected: x", "invalid_api_key")])
def test_missing_or_unsafe_key_never_opens_network(monkeypatch, key, reason):
    monkeypatch.setattr(jev.os, "getenv", lambda name: key)
    result = enabled().decide("state", questions(), data_classification="synthetic")
    assert result.reason == reason and result.diagnostics.attempts == 0
    assert result.request_text is not None


def test_response_size_limit_marks_incomplete(monkeypatch):
    calls, response = transport(monkeypatch, body="x" * 200)
    result = enabled(max_response_bytes=100).decide("state", questions(), data_classification="synthetic")
    assert result.reason == "response_too_large" and not result.ok
    assert result.response_text is None and result.diagnostics.response_bytes == 101
    assert not result.diagnostics.response_complete and len(calls) == 1
    assert response.closed


@pytest.mark.parametrize("kwargs", [
    {"timeout": 0}, {"timeout": 61}, {"timeout": float("inf")}, {"timeout": True},
    {"max_response_bytes": 0}, {"max_response_bytes": 4 * 1024 * 1024 + 1},
    {"max_response_bytes": True}, {"enabled": "yes"}, {"allow_network": 1},
])
def test_unsafe_client_configuration_rejected(kwargs):
    with pytest.raises(ValueError, match="invalid_client_configuration"):
        jev.JevClient(**kwargs)


def test_validator_errors_never_include_caller_content():
    with pytest.raises(jev.ValidationError) as exc:
        jev.validate_response({"secret": "do-not-echo"}, questions())
    assert str(exc.value) == "invalid_response"
    with pytest.raises(jev.ValidationError) as exc:
        jev.validate_request("secret", {"secret": {"type": "secret"}})
    assert str(exc.value) == "invalid_request"


def test_response_validator_does_not_mutate_inputs():
    q, p = questions(), payload()
    before = copy.deepcopy((q, p))
    assert jev.validate_response(p, q) == p
    assert (q, p) == before


def test_rejected_decision_retains_native_usage(monkeypatch):
    p = payload()
    p["answers"]["route"]["choice"] = "not-offered"
    transport(monkeypatch, body=json.dumps(p))
    result = enabled().decide("state", questions(), data_classification="synthetic")
    assert not result.ok and result.payload is None
    assert result.diagnostics.native_input_tokens == 318
    assert result.diagnostics.native_output_tokens == 34


def test_unknown_json_metadata_is_preserved(monkeypatch):
    p = payload()
    p["metadata"] = {"request_id": "synthetic-id"}
    p["usage"]["extra_diagnostic"] = 2
    transport(monkeypatch, body=json.dumps(p))
    result = enabled().decide("state", questions(), data_classification="synthetic")
    assert result.payload == p
    result.payload["answers"]["safe"]["noul"] = 2
    assert not result.validate(questions())


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_actual_urllib_redirect_dispatch_cannot_forward_bearer(monkeypatch, status):
    # Exercise urllib's real handler chain, replacing only its HTTPS transport.
    calls = []

    class OfflineHTTPS(HTTPSHandler):
        def https_open(self, request):
            calls.append(request)
            response = addinfourl(io.BytesIO(b'{"redirect":true}'),
                                  {"Location": "https://other.invalid/steal"},
                                  request.full_url, status)
            response.msg = "Redirect"
            return response

    monkeypatch.setattr(jev.os, "getenv", lambda name: "synthetic-key")
    monkeypatch.setattr(jev, "build_opener",
                        lambda *handlers: build_opener(*handlers, OfflineHTTPS()))
    result = enabled().decide("state", questions(), data_classification="synthetic")
    assert result.reason == "redirect_denied" and len(calls) == 1
    assert calls[0].full_url == jev.ENDPOINT
    assert result.diagnostics.http_status == status


def test_invalid_utf8_never_claims_complete_text(monkeypatch):
    _, response = transport(monkeypatch, body="")
    response.write(b"\xff")
    response.seek(0)
    result = enabled().decide("state", questions(), data_classification="synthetic")
    assert result.reason == "invalid_response_encoding"
    assert result.response_text is None and not result.diagnostics.response_complete
    assert result.diagnostics.response_bytes == 1 and response.closed


def test_response_exactly_at_byte_limit_succeeds(monkeypatch):
    raw = json.dumps(payload())
    transport(monkeypatch, body=raw)
    result = enabled(max_response_bytes=len(raw.encode())).decide(
        "state", questions(), data_classification="synthetic")
    assert result.ok and result.response_text == raw


def test_read_timeout_closes_response(monkeypatch):
    _, response = transport(monkeypatch)

    def fail_read(size):
        raise TimeoutError("synthetic-secret-state")

    monkeypatch.setattr(response, "read", fail_read)
    result = enabled().decide("state", questions(), data_classification="synthetic")
    assert result.reason == "transport_error" and response.closed
    assert result.response_text is None and not result.diagnostics.response_complete


def test_single_choice_ties_and_float_tolerance():
    q = {"x": {"type": "choice", "instructions": "Choose", "criteria": {"a": None}}}
    p = {"model": jev.MODEL, "usage": {"input_tokens": 0, "output_tokens": 0},
         "answers": {"x": {"type": "choice", "choice": "a",
                           "probabilities": {"a": 1}, "confidence": 1}}}
    assert jev.validate_response(p, q) == p
    q["x"]["criteria"]["b"] = None
    p["answers"]["x"]["probabilities"] = {"a": 0.5, "b": 0.5}
    assert jev.validate_response(p, q) == p
    p["answers"]["x"]["probabilities"]["a"] += 1e-8
    assert jev.validate_response(p, q) == p


def test_structured_score_legend_does_not_invent_serialization_contract():
    q = {"s": {"type": "score", "instructions": "Rate",
               "criteria": [{"label": "low"}, ["high"]]}}
    p = {"model": jev.MODEL, "usage": {"input_tokens": 0, "output_tokens": 0},
         "answers": {"s": {"type": "score", "score": 0.5, "confidence": 0,
                          "probabilities": {"0": 0.5, "1": 0.5},
                          "legend": {"0": '{"label":"low"}', "1": '["high"]'}}}}
    assert jev.validate_response(p, q) == p


def test_documented_structured_score_legend_is_preserved_and_detached():
    q = {"s": {"type": "score", "instructions": "Rate",
               "criteria": [{"label": "low", "enabled": True}, ["high"]]}}
    p = {"model": jev.MODEL, "usage": {"input_tokens": 0, "output_tokens": 0},
         "answers": {"s": {"type": "score", "score": 0.5, "confidence": 0,
                          "probabilities": {"0": 0.5, "1": 0.5},
                          "legend": {"0": {"enabled": True, "label": "low"}, "1": ["high"]}}}}
    accepted = jev.validate_response(p, q)
    assert accepted == p
    accepted["answers"]["s"]["legend"]["0"]["label"] = "changed"
    assert p["answers"]["s"]["legend"]["0"]["label"] == "low"


@pytest.mark.parametrize("wrong", [
    {"label": "different", "enabled": True},
    {"label": "low", "enabled": 1},
    ["low"],
    None,
    0,
])
def test_structured_score_legend_must_match_the_requested_json(wrong):
    q = {"s": {"type": "score", "instructions": "Rate",
               "criteria": [{"label": "low", "enabled": True}, ["high"]]}}
    p = {"model": jev.MODEL, "usage": {"input_tokens": 0, "output_tokens": 0},
         "answers": {"s": {"type": "score", "score": 0.5, "confidence": 0,
                          "probabilities": {"0": 0.5, "1": 0.5},
                          "legend": {"0": wrong, "1": ["high"]}}}}
    with pytest.raises(jev.ValidationError, match="invalid_response"):
        jev.validate_response(p, q)
