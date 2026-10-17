"""Offline repository-diagnostic accounting; fabricated usage is not model evidence."""
import copy
import json
from pathlib import Path
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
import run_repository as trial  # noqa: E402
from quality import runner  # noqa: E402
from quality.cases import Case  # noqa: E402
from quality.responses import Reply, ResponsesTransport  # noqa: E402
from source_read_adapter import SourceAwareArm, executor_source_reads  # noqa: E402


class Scripted:
    model = "fixture"
    max_request_bytes = 524288

    def __init__(self, actions):
        self.actions = iter(actions)
        self.base = ResponsesTransport("http://127.0.0.1/v1", self.model)
        self.calls = 0

    def request(self, payload):
        return self.base.request({**payload, "reasoning": {"effort": "low"}})

    def call(self, payload):
        self.calls += 1
        action = next(self.actions)
        if isinstance(action, Reply):
            return action
        incoming = trial.canonical(self.request(payload))
        if action == "partial":
            return Reply(False, "transport_error", input_text=incoming)
        body = {
            "object": "response", "status": "completed", "model": self.model,
            "usage": {"input_tokens": 17, "output_tokens": 3, "total_tokens": 20},
            "output": [{"type": "function_call", "call_id": f"c{self.calls}",
                        "name": action[0], "arguments": json.dumps(action[1])}],
        }
        return Reply(True, "ok", True, incoming, trial.canonical(body), body, 200)


@pytest.fixture
def context(monkeypatch):
    case = Case(
        "fixture_navigation", "offline", "Find the function. Do not edit.",
        (("module.py", "def pick():\n    return 1\n"),), (), intent="navigation",
    )
    monkeypatch.setattr(trial, "SPECS", {
        case.id: {"kind": "answer", "expected": {"symbol": "pick"}},
    }, raising=False)
    monkeypatch.setattr(runner, "grade", trial.grade_repository)
    return case


def run_fixture(context, tmp_path, actions):
    client = Scripted(actions)
    directory = tmp_path / "run"
    with executor_source_reads() as observations:
        result = runner.run_case(
            context, SourceAwareArm("tokenmaster", views=True), directory, client, max_calls=4,
        )
    trial.write(directory / "source-read-info.json",
                [info.to_dict() for info in observations.values()])
    return result, directory, client


READ = ("read_file", {"path": "module.py"})
ANSWER = ("answer", {"content": '{"symbol":"pick"}'})


def test_complete_attempt_keeps_independent_recount(context, tmp_path):
    result, directory, client = run_fixture(context, tmp_path, [READ, ANSWER])
    row = trial.audit_run(context, result, directory, client.base)
    assert row["correct"] is True
    assert row["reference_total"] == result["totals"]["total_tokens"]
    assert row["bridge_total"] == 40
    assert row["accounting_status"] == "complete"
    assert row["calls"] == row["complete_calls"] == 2


@pytest.mark.parametrize("prefix", [[], [READ]])
@pytest.mark.parametrize("failure", [
    Reply(False, "deadline_submission_unknown", error_type="LocalDeadline"),
    Reply(False, "worker_failed_submission_unknown", error_type="WorkerExit"),
    "partial",
])
def test_unknown_attempt_is_retained_without_invented_totals(context, tmp_path, prefix, failure):
    result, directory, client = run_fixture(context, tmp_path, [*prefix, failure])
    row = trial.audit_run(context, result, directory, client.base)
    assert row["correct"] is False
    assert row["accounting_status"] == "incomplete"
    assert row["reference_total"] is row["bridge_total"] is None
    assert row["calls"] == len(prefix) + 1
    assert row["complete_calls"] == len(prefix)
    assert row["known_reference_total"] == sum(
        record["reference_input_tokens"] + record["reference_output_tokens"]
        for record in result["trace"]["calls"]
    )
    assert row["known_bridge_total"] == 20 * len(prefix)
    assert len(row["incomplete_calls"]) == 1


def test_explicit_no_submission_is_not_a_model_attempt(context, tmp_path):
    result, directory, client = run_fixture(
        context, tmp_path, [Reply(False, "study_limit_no_submission")],
    )
    row = trial.audit_run(context, result, directory, client.base)
    assert row["accounting_status"] == "complete"
    assert row["calls"] == row["complete_calls"] == 0
    assert row["reference_total"] == row["bridge_total"] == 0
    assert row["correct"] is False


def test_missing_capture_still_rejects_the_inventory(context, tmp_path):
    result, directory, client = run_fixture(
        context, tmp_path, [READ, Reply(False, "deadline_submission_unknown")],
    )
    path = directory / "captures.jsonl"
    path.write_text(path.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory"):
        trial.audit_run(context, result, directory, client.base)


def test_partial_attempt_cannot_claim_complete_coverage(context, tmp_path):
    result, directory, client = run_fixture(
        context, tmp_path, [Reply(False, "deadline_submission_unknown")],
    )
    result["coverage"] = "complete_for_declared_boundary"
    result["trace"]["coverage"] = "complete_for_declared_boundary"
    with pytest.raises(ValueError, match="coverage"):
        trial.audit_run(context, result, directory, client.base)


def test_complete_record_cannot_be_dropped_from_partial_attempt(context, tmp_path):
    result, directory, client = run_fixture(
        context, tmp_path, [READ, Reply(False, "deadline_submission_unknown")],
    )
    result["trace"]["calls"] = []
    with pytest.raises(ValueError, match="inventory"):
        trial.audit_run(context, result, directory, client.base)


def test_summary_preserves_missing_tasks_and_unknown_totals(context, tmp_path):
    result, directory, client = run_fixture(
        context, tmp_path, [READ, Reply(False, "deadline_submission_unknown")],
    )
    row = trial.audit_run(context, result, directory, client.base)
    schedule = [(context.id, "tokenmaster"), (context.id, "baseline")]
    summary = trial.summarize([row], schedule)
    assert summary["complete"] is False
    assert summary["missing_runs"] == [{"case": context.id, "arm": "baseline"}]
    assert summary["by_arm"]["tokenmaster"]["reference_total"] is None
    assert summary["by_arm"]["baseline"]["reference_total"] is None
    assert summary["by_arm"]["baseline"]["tasks"] == 0
    assert summary["by_arm"]["tokenmaster"]["known_reference_total"] == row["known_reference_total"]


def test_summary_rejects_duplicate_runs(context, tmp_path):
    result, directory, client = run_fixture(context, tmp_path, [READ, ANSWER])
    row = trial.audit_run(context, result, directory, client.base)
    with pytest.raises(ValueError, match="duplicate"):
        trial.summarize([row, copy.deepcopy(row)], [(context.id, "tokenmaster")])


def test_fixture_integrity_is_checked_before_any_source_execution(tmp_path, monkeypatch):
    bad = tmp_path / "repository-cases.json"
    bad.write_text('{"fixtures":[["brainspace/router.py","raise RuntimeError()"]]}', encoding="utf-8")
    monkeypatch.setattr(trial, "trusted_router_tests",
                        lambda _source: pytest.fail("unverified source must not execute"))
    with pytest.raises(ValueError, match="fixture"):
        trial.load_cases(bad)


@pytest.mark.parametrize("limit,halt", [
    ("tokens", "reference_limit"), ("calls", "call_limit"), ("time", "wall_time_limit"),
])
def test_budget_exhaustion_sets_durable_study_halt(tmp_path, monkeypatch, limit, halt):
    client = trial.BudgetClient(Scripted([]).base, tmp_path)
    if limit == "tokens":
        client.known_tokens = 500000
    elif limit == "calls":
        client.calls = 65
    else:
        client.start = time.monotonic() - 901
    before = client.calls
    monkeypatch.setattr(trial, "deadline_call",
                        lambda *_: pytest.fail("exhausted study must not submit a request"))
    assert client.call({"input": []}).reason == "study_limit_no_submission"
    assert client.halt == halt
    assert client.calls == before


def test_budget_truncated_task_cannot_complete_planned_comparison(context, tmp_path):
    result, directory, client = run_fixture(
        context, tmp_path, [Reply(False, "study_limit_no_submission")],
    )
    row = trial.audit_run(context, result, directory, client.base)
    summary = trial.summarize([row], [(context.id, "tokenmaster")])
    assert summary["complete"] is False
    assert summary["by_arm"]["tokenmaster"]["reference_total"] is None
    assert summary["by_arm"]["tokenmaster"]["known_reference_total"] == 0


def test_read_only_oracle_rejects_a_write_even_when_final_bytes_are_unchanged(context, tmp_path):
    result, directory, client = run_fixture(context, tmp_path, [
        ("write_file", {"path": "module.py", "content": dict(context.fixtures)["module.py"]}),
        ANSWER,
    ])
    assert result["grade"]["success"] is False
    assert result["grade"]["assertions"]["write_scope_respected"] is False
    assert trial.audit_run(context, result, directory, client.base)["correct"] is False


@pytest.mark.parametrize("alter", [
    lambda text: text + "\n" * 10,
    lambda text: text.rstrip("\n"),
    lambda text: text.replace("\n", "\r\n"),
])
def test_exact_patch_rejects_newline_changes(tmp_path, monkeypatch, alter):
    _, cases = trial.load_cases(trial.PLUGIN / "evals/repository-cases.json")
    case = next(case for case in cases if case.id == "fix_stub_routing")
    workspace = runner.materialize(case, tmp_path / "workspace")
    (workspace / "brainspace/router.py").write_bytes(alter(trial.GOLD).encode("utf-8"))
    monkeypatch.setattr(trial, "trusted_router_tests",
                        lambda _: pytest.fail("nonexact source must not execute"))
    verdict = trial.grade_repository(case, workspace, None, [])
    assert verdict["success"] is False
    assert verdict["assertions"]["exact_requested_patch"] is False


def test_exact_patch_accepts_only_the_original_byte_preserving_change(tmp_path):
    _, cases = trial.load_cases(trial.PLUGIN / "evals/repository-cases.json")
    case = next(case for case in cases if case.id == "fix_stub_routing")
    workspace = runner.materialize(case, tmp_path / "workspace")
    (workspace / "brainspace/router.py").write_bytes(trial.GOLD.encode("utf-8"))
    assert trial.grade_repository(case, workspace, None, [])["success"] is True


def test_interrupted_dispatch_retains_a_durable_pending_invocation(context, tmp_path):
    class Interrupted(Scripted):
        def call(self, payload):
            if self.calls == 1:
                self.calls += 1
                raise KeyboardInterrupt
            return super().call(payload)

    client = Interrupted([READ])
    directory = tmp_path / "interrupted"
    with pytest.raises(KeyboardInterrupt), executor_source_reads():
        runner.run_case(context, SourceAwareArm("baseline"), directory, client, max_calls=4)
    journal = [json.loads(line) for line in
               (directory / "invocations.jsonl").read_text(encoding="utf-8").splitlines()]
    pending = [event["call_id"] for event in journal if event["state"] == "pending"]
    captured = [event["call_id"] for event in journal if event["state"] == "captured"]
    assert client.calls == len(pending) == 2
    assert captured == pending[:1]
    assert not (directory / "result.json").exists()
    captures = [json.loads(line) for line in
                (directory / "captures.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [capture["call_id"] for capture in captures] == captured


def test_budget_dispatch_records_readiness_exposure_before_transport(tmp_path, monkeypatch):
    client = trial.BudgetClient(Scripted([]).base, tmp_path)

    def interrupted(*_):
        journal = [json.loads(line) for line in
                   (tmp_path / "study-invocations.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(journal) == 1 and journal[0]["state"] == "pending"
        raise KeyboardInterrupt

    monkeypatch.setattr(trial, "deadline_call", interrupted)
    with pytest.raises(KeyboardInterrupt):
        client.call({"input": []})
    assert client.calls == 1


@pytest.mark.parametrize("missing", [False, True])
def test_audit_rejects_unresolved_or_missing_invocation_receipts(context, tmp_path, missing):
    result, directory, client = run_fixture(context, tmp_path, [READ, ANSWER])
    journal = directory / "invocations.jsonl"
    if missing:
        journal.unlink(missing_ok=True)
    else:
        with journal.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"call_id": "unaccounted", "state": "pending"}) + "\n")
    with pytest.raises(ValueError, match="invocation"):
        trial.audit_run(context, result, directory, client.base)


@pytest.mark.parametrize("flags,scope,timeout", [
    ([], False, 60),
    (["--task-discipline", "--timeout-seconds", "90"], True, 90),
])
def test_live_profile_is_explicit_and_timeout_is_preserved(monkeypatch, tmp_path, flags, scope, timeout):
    observed = []
    monkeypatch.setattr(trial, "execute", lambda args: observed.append(args) or 0)
    assert trial.main([
        "--output", str(tmp_path / "study"), "--model", "fixture",
        "--allow-network", "--frozen", *flags,
    ]) == 0
    assert len(observed) == 1
    assert observed[0].task_discipline is scope
    assert observed[0].timeout_seconds == timeout


@pytest.mark.parametrize("timeout", ["0", "91"])
def test_invalid_timeout_rejects_before_any_freeze_or_model_call(monkeypatch, tmp_path, timeout):
    monkeypatch.setattr(trial, "snapshot", lambda _: pytest.fail("invalid controls must not freeze"))
    with pytest.raises(SystemExit) as error:
        trial.main(["--output", str(tmp_path / "study"), "--model", "fixture",
                    "--allow-network", "--timeout-seconds", timeout])
    assert error.value.code == 2
