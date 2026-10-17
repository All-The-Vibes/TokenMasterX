import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
from quality.cases import CASES  # noqa: E402
from quality.responses import Reply, ResponsesTransport  # noqa: E402
from quality.runner import Arm, run_case, to_responses  # noqa: E402
from quality import runner  # noqa: E402


class Scripted:
    model = "fixture"
    max_request_bytes = 524288

    def __init__(self, actions):
        self.actions = iter(actions)
        self.inputs = []

    def request(self, payload):
        return ResponsesTransport("http://127.0.0.1/v1", self.model).request(payload)

    def call(self, payload):
        self.inputs.append(payload)
        action = next(self.actions)
        body = {"object": "response", "status": "completed", "model": self.model,
                "output": [{"type": "function_call", "call_id": f"c{len(self.inputs)}",
                            "name": action[0], "arguments": json.dumps(action[1])}]}
        return Reply(True, "ok", True, json.dumps(self.request(payload)),
                     json.dumps(body), body, 200, 0)


def example():
    return next(case for case in CASES if case.id == "explain_only")


def test_complete_real_function_protocol_is_materialized(tmp_path):
    client = Scripted([
        ("read_file", {"path": "cache.py"}),
        ("answer", {"content": json.dumps({"returns": [10, None, 10], "stored": {"x": 10}})}),
    ])
    result = run_case(example(), Arm("baseline"), tmp_path / "run", client, max_calls=4)
    assert result["grade"]["success"] is True
    assert result["coverage"] == "complete_for_declared_boundary"
    assert result["totals"]["calls"] == 2
    assert any(item["type"] == "function_call_output"
               for item in client.inputs[1]["input"] if "type" in item)
    assert (tmp_path / "run" / "captures.jsonl").is_file()


def test_explain_only_forbidden_write_is_executed_then_graded_wrong(tmp_path):
    client = Scripted([
        ("write_file", {"path": "cache.py", "content": "changed = True\n"}),
        ("answer", {"content": json.dumps({"returns": [10, None, 10], "stored": {"x": 10}})}),
    ])
    result = run_case(example(), Arm("combined", scope=True, views=True),
                      tmp_path / "run", client, max_calls=4)
    assert result["grade"]["success"] is False
    assert "forbidden_write_attempt" in result["grade"]["checks"]
    assert (tmp_path / "run/workspace/cache.py").read_text() == "changed = True\n"


def test_model_cannot_write_outside_fresh_workspace(tmp_path):
    client = Scripted([
        ("write_file", {"path": "../escaped.txt", "content": "never"}),
        ("answer", {"content": "{}"}),
    ])
    result = run_case(example(), Arm("baseline"), tmp_path / "run", client, max_calls=4)
    assert not (tmp_path / "run/escaped.txt").exists()
    assert result["grade"]["success"] is False


def test_partial_model_reply_is_not_a_zero_output_total(tmp_path):
    class Broken(Scripted):
        def call(self, payload):
            return Reply(False, "transport_error", False,
                         input_text=json.dumps(self.request(payload)))
    result = run_case(example(), Arm("baseline"), tmp_path / "run", Broken([]), max_calls=4)
    assert result["coverage"] == "partial"
    assert result["totals"] is None
    assert result["incomplete_calls"][0]["output_tokens"] is None


@pytest.mark.parametrize("reason", [
    "deadline_submission_unknown", "worker_failed_submission_unknown", "unknown_transport_state",
])
def test_missing_request_capture_is_unknown_not_a_zero_call_success(tmp_path, reason):
    class Broken(Scripted):
        def call(self, payload):
            return Reply(False, reason, error_type="LocalDeadline")
    result = run_case(example(), Arm("baseline"), tmp_path / "run", Broken([]), max_calls=4)
    assert result["coverage"] == "partial"
    assert result["totals"] is None
    assert not result["regime_valid"]
    assert len(result["trace"]["expected_call_ids"]) == 1
    assert not result["trace"]["calls"]
    assert result["incomplete_calls"][0]["prepared_input_tokens"] is None
    assert result["incomplete_calls"][0]["output_tokens"] is None
    assert result["context_projection"]["input_tokens"] is None
    assert result["context_projection"]["total_tokens"] is None
    assert result["grade"]["success"] is False


@pytest.mark.parametrize("reason", [
    "network_not_allowed", "invalid_request", "request_too_large",
    "transport_setup_error", "study_limit_no_submission",
])
def test_explicit_no_submission_can_still_report_zero_model_calls(tmp_path, reason):
    class NotSent(Scripted):
        def call(self, payload):
            return Reply(False, reason)
    result = run_case(example(), Arm("baseline"), tmp_path / "run", NotSent([]), max_calls=4)
    assert result["coverage"] == "complete_for_declared_boundary"
    assert result["totals"]["calls"] == result["totals"]["total_tokens"] == 0
    assert not result["trace"]["expected_call_ids"]
    assert result["grade"]["success"] is False


def test_converter_preserves_roles_tools_calls_and_outputs():
    chat = {"messages": [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "task"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "opaque", "type": "function",
             "function": {"name": "read_file", "arguments": '{"path":"x"}'}}]},
        {"role": "tool", "tool_call_id": "opaque", "content": "tool text"},
    ]}
    result = to_responses(chat)
    assert result["input"][0] == {"role": "system", "content": "rules"}
    assert result["input"][2] == {"type": "function_call", "call_id": "opaque",
                                 "name": "read_file", "arguments": '{"path":"x"}'}
    assert result["input"][3] == {"type": "function_call_output", "call_id": "opaque",
                                 "output": "tool text"}


def test_external_transform_keeps_original_client_history_when_declared(tmp_path):
    observed = []

    def prepare(chat):
        tools = [message for message in chat["messages"] if message["role"] == "tool"]
        observed.append([message["content"] for message in tools])
        for message in tools:
            message["content"] = "MODEL VIEW"
        return chat

    client = Scripted([
        ("read_file", {"path": "cache.py"}), ("read_file", {"path": "cache.py"}),
        ("answer", {"content": json.dumps({"returns": [10, None, 10], "stored": {"x": 10}})}),
    ])
    result = run_case(example(), Arm("external"), tmp_path / "run", client,
                      request_preparer=prepare, persist_view_history=False,
                      harness_id="original-history-test-v1")
    assert result["grade"]["success"] is True
    assert observed[0] == []
    assert all(text != "MODEL VIEW" for group in observed for text in group)
    assert len(observed[-1]) == 2
    assert any(item.get("output") == "MODEL VIEW" for item in client.inputs[-1]["input"])
    assert all(call["harness_id"] == "original-history-test-v1" for call in result["trace"]["calls"])
    receipts = [json.loads(line) for line in
                (tmp_path / "run/preparations.jsonl").read_text().splitlines()]
    assert [row["state"] for row in receipts] == ["pending", "prepared"] * 3


@pytest.mark.parametrize("prepare", [
    lambda chat: (_ for _ in ()).throw(RuntimeError("unavailable")),
    lambda chat: {"model": "wrong", "messages": chat["messages"]},
    lambda chat: {"model": chat["model"], "messages": None},
])
def test_external_failure_is_not_a_successful_zero_call_comparison(tmp_path, prepare):
    client = Scripted([])
    result = run_case(example(), Arm("external"), tmp_path / "run", client,
                      request_preparer=prepare, persist_view_history=False)
    assert not client.inputs
    assert result["failure"] == "external_preparation_error"
    assert result["regime_valid"] is False and result["grade"]["success"] is False
    assert result["totals"]["calls"] == 0  # No primary submission; external state is not certified.
    receipts = [json.loads(line) for line in
                (tmp_path / "run/preparations.jsonl").read_text().splitlines()]
    assert [row["state"] for row in receipts] == ["pending", "failed"]


def test_two_transformers_cannot_be_silently_stacked(tmp_path):
    with pytest.raises(ValueError, match="cannot be combined"):
        run_case(example(), Arm("invalid", views=True), tmp_path / "run", Scripted([]),
                 request_preparer=lambda chat: chat)
    assert not (tmp_path / "run").exists()


def test_external_recovery_tool_is_executed_and_keeps_call_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "TOOLS", [
        *runner.TOOLS, runner._tool("headroom_retrieve", {"hash": {"type": "string"}}, "fixture"),
    ])
    executed = []

    def execute(root, store, name, args, program_runner=None, *, tool_call_id):
        if name == "headroom_retrieve":
            executed.append((tool_call_id, args))
            return '{"original_content":"EXACT ORIGINAL"}'
        return runner._execute(root, store, name, args, program_runner)

    client = Scripted([
        ("headroom_retrieve", {"hash": "abc"}),
        ("answer", {"content": json.dumps({"returns": [10, None, 10], "stored": {"x": 10}})}),
    ])
    result = run_case(example(), Arm("external"), tmp_path / "run", client, tool_executor=execute)
    assert result["failure"] is None and executed == [("c1", {"hash": "abc"})]
    outputs = [item for item in client.inputs[1]["input"] if item.get("type") == "function_call_output"]
    assert outputs == [{"type": "function_call_output", "call_id": "c1",
                        "output": '{"original_content":"EXACT ORIGINAL"}'}]


def test_declared_instruction_suffix_is_in_model_request_not_a_profile(tmp_path):
    client = Scripted([("answer", {"content": "{}"})])
    run_case(example(), Arm("instruction"), tmp_path / "run", client,
             system_suffix="PINNED INSTRUCTION FIXTURE")
    assert client.inputs[0]["input"][0]["content"].endswith("\nPINNED INSTRUCTION FIXTURE")
