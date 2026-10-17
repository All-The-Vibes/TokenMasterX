from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
from quality.responses import Reply, ResponsesTransport  # noqa: E402
from refinement.core import (  # noqa: E402
    Arm, Limits, arms, capture_call, child_environment, deadline_call, decode_stage,
    make_client, native_usage, payload, recount, run_policy, select_answer, visible_input, visible_text, wire,
)


def response(model="A", answer="7", *, critique=False):
    content = {"critique": "Check the boundary carefully."} if critique else {
        "answer": answer, "explanation": "A short derivation."}
    return {
        "object": "response", "status": "completed", "model": model,
        "output": [{"type": "message", "role": "assistant",
                    "content": [{"type": "output_text", "text": wire(content)}]}],
        "usage": {"input_tokens": 11, "output_tokens": 9, "total_tokens": 20},
    }


def mock_reply(client, request, _seconds):
    stage = "critique" in request["instructions"] and '"critique":' in request["instructions"]
    body = response(client.model, critique=stage)
    return Reply(True, "ok", True, wire(client.request(request)), wire(body), body, 200, 0.01)


def policy_run(tmp_path, *, mode="refine", invoke=mock_reply, reserve=None):
    return run_policy(
        "Synthetic problem", Arm("test", mode, "A", "B"), tmp_path / "run",
        {m: ResponsesTransport("http://127.0.0.1:1/v1", m) for m in ("A", "B")},
        Limits(), reserve=reserve or (lambda _count, seconds: seconds),
        observe=lambda _record: None, invoke=invoke,
    )


def test_literal_small_schedule_and_cross_role_mapping():
    policies = arms("A", "B")
    assert sum(len(p.schedule()) for p in policies) == 14
    assert policies[-1].schedule() == [
        ("initial", "A"), ("continuation", "A"), ("critique", "B"), ("correction", "A")]
    assert policies[-1].identity != policies[-2].identity
    with pytest.raises(ValueError):
        arms("A", "A")


def test_exact_dependency_context_not_accumulated_transcript():
    prior = [{"text": "INITIAL"}, {"text": "CONTINUED"}, {"text": "CRITIQUE"}]
    initial = payload("PROBLEM", "initial", [])
    assert json.loads(initial["input"][0]["content"]) == {"problem": "PROBLEM"}
    correction = payload("PROBLEM", "correction", prior)
    assert json.loads(correction["input"][0]["content"]) == {
        "problem": "PROBLEM", "solution": "CONTINUED", "critique": "CRITIQUE"}
    assert "INITIAL" not in wire(correction)
    assert not ({"tools", "previous_response_id", "conversation"} & correction.keys())


def test_four_realized_stages_and_no_oracle_in_policy(tmp_path):
    result, records = policy_run(tmp_path)
    assert result["status"] == "completed"
    assert result["answer"] == "7"
    assert result["attempts"] == len(records) == 4
    assert result["stage_answers"] == ["7", "7", None, "7"]
    assert [r["model_requested"] for r in records] == ["A", "A", "B", "A"]
    assert len(list((tmp_path / "run").rglob("started.json"))) == 4
    assert all("expected" not in r["input_text"] for r in records)


def test_plurality_is_exact_and_tie_is_first_not_correctness():
    arm = Arm("wide", "resample", "A", "A")
    outputs = [{"answer": a} for a in ("9", "3", "3", "9")]
    assert select_answer(arm, outputs) == "9"
    outputs[-1]["answer"] = "3"
    assert select_answer(arm, outputs) == "3"
    assert select_answer(arm, outputs[:3]) is None
    assert decode_stage(response(answer="2/4"), "initial")["answer"] == "1/2"


@pytest.mark.parametrize("bad", ["```json\n{}\n```", '{"answer":"7","explanation":"x","extra":1}',
                               '{"answer":"7","answer":"8","explanation":"x"}',
                               '{"answer":NaN,"explanation":"x"}',
                               '{"answer":"1+2","explanation":"x"}',
                               '{"answer":"2","explanation":""}'])
def test_malformed_stage_never_repairs_or_extracts_last_number(bad):
    body = response()
    body["output"][0]["content"][0]["text"] = bad
    with pytest.raises((ValueError, TypeError)):
        decode_stage(body, "initial")


def test_failed_correction_does_not_carry_forward_good_answer(tmp_path):
    def fake(client, request, seconds):
        if "final solution" in request["instructions"]:
            return Reply(False, "http_error", True, wire(client.request(request)),
                         '{"error":"synthetic"}', http_status=503)
        return mock_reply(client, request, seconds)
    result, records = policy_run(tmp_path, invoke=fake)
    assert result["status"] == "http_error"
    assert result["answer"] is None
    assert len(records) == 4
    assert records[-1]["measurement"]["reference_total"] > 0


def test_malformed_first_stage_stops_no_retry(tmp_path):
    def fake(client, request, seconds):
        body = response(answer="not a number")
        return Reply(True, "ok", True, wire(client.request(request)), wire(body), body, 200)
    result, records = policy_run(tmp_path, invoke=fake)
    assert result["status"] == "invalid_stage_output"
    assert result["answer"] is None
    assert len(records) == 1


def test_stop_before_sending_and_incomplete_capture_is_unknown(tmp_path):
    result, records = policy_run(tmp_path, reserve=lambda *_: 0)
    assert result["status"] == "study_limit"
    assert not records and result["answer"] is None
    receipt = recount(Reply(False, "transport_error", input_text="{}"))
    assert receipt["reference_input"] > 0
    assert receipt["reference_total"] is None
    assert receipt["bridge_usage"] is None


@pytest.mark.parametrize("output", ["{}", "[]", "null", '"string"', "not json"])
def test_complete_error_payload_is_counted_without_schema_crash(output):
    receipt = recount(Reply(False, "http_error", True, "{}", output, http_status=500))
    assert receipt["reference_total"] > 0
    assert receipt["bridge_usage"] is None


def test_reasoning_never_forwarded_or_double_counted():
    body = response()
    body["output"].insert(0, {"type": "reasoning", "encrypted_content": "opaque"})
    body["usage"]["output_tokens_details"] = {"reasoning_tokens": 6}
    assert "opaque" not in visible_text(body)
    assert native_usage(body)["total_tokens"] == 20
    body["usage"]["total_tokens"] = 21
    assert native_usage(body) is None
    body["usage"]["total_tokens"] = True
    assert native_usage(body) is None


def test_messages_input_projection_matches_responses_and_thinking_is_not_forwarded():
    request = payload("PROBLEM", "initial", [])
    a = make_client("http://127.0.0.1:1/v1", "A", "responses").request(request)
    b = make_client("http://127.0.0.1:1/v1", "B", "messages").request(request)
    assert visible_input(a) == visible_input(b)
    assert "input" in a and "messages" in b
    body = {"type": "message", "content": [
        {"type": "thinking", "thinking": "not transferred", "signature": "opaque"},
        {"type": "text", "text": '{"answer":"3","explanation":"A short derivation."}'}],
        "usage": {"input_tokens": 5, "cache_read_input_tokens": 2,
                  "cache_creation_input_tokens": 3, "output_tokens": 4}}
    assert "not transferred" not in visible_text(body)
    assert native_usage(body) == {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14}
    del body["usage"]["cache_read_input_tokens"]
    assert native_usage(body) is None  # not an assumed zero cache component


def test_api_mapping_is_part_of_policy_identity():
    assert arms("A", "B", "messages")[-1].identity != arms("A", "B", "responses")[-1].identity


@pytest.mark.parametrize("values", [{"call_seconds": float("nan")}, {"call_seconds": 91},
                                   {"max_output_tokens": True}, {"policy_seconds": -1}])
def test_limits_reject_invalid_bounds(values):
    with pytest.raises(ValueError):
        Limits(**values)


def test_environment_excludes_credentials_and_proxy(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "SYNTHETIC_NOT_A_KEY")
    monkeypatch.setenv("TYPESAFE_API_KEY", "SYNTHETIC_NOT_A_KEY")
    monkeypatch.setenv("HTTP_PROXY", "http://example.invalid")
    env = child_environment()
    assert not ({"OPENAI_API_KEY", "TYPESAFE_API_KEY", "HTTP_PROXY"} & env.keys())


class Handler(BaseHTTPRequestHandler):
    delay = 0

    def log_message(self, *_):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        time.sleep(self.delay)
        self.send_response(200)
        self.end_headers()
        try:
            self.wfile.write(wire(response(model=body["model"])).encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


@pytest.fixture
def bridge():
    Handler.delay = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_actual_credential_free_worker_and_capture(bridge, tmp_path):
    client = ResponsesTransport(bridge, "A", allow_network=True)
    reply, record = capture_call(client, payload("p", "initial", []), tmp_path / "call",
                                 stage="initial", seconds=15)
    assert reply.ok
    assert record["measurement"]["reference_total"] > 0
    assert json.loads((tmp_path / "call" / "reply.json").read_text())["ok"] is True
    assert asdict(client)["allow_network"] is True


def test_actual_client_deadline_is_recorded_as_unknown_submission(bridge):
    Handler.delay = 3
    start = time.monotonic()
    reply = deadline_call(ResponsesTransport(bridge, "A", allow_network=True),
                          payload("p", "initial", []), 0.2)
    assert reply.reason == "deadline_submission_unknown"
    assert time.monotonic() - start < 3
    assert not reply.complete and reply.input_text is None
