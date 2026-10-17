"""Offline audit regressions; fixture usage is fabricated, not model evidence."""
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
from quality.cases import CASES, digest  # noqa: E402
from quality.oracle import grade, oracle_identity  # noqa: E402
from quality.responses import Reply, ResponsesTransport  # noqa: E402
from quality.runner import Arm, run_case  # noqa: E402
from quality.savings import AuditError, reported_usage, verify_study  # noqa: E402
from run_quality import snapshot  # noqa: E402

from brainspace.optimizer import reference_measurement  # noqa: E402
from brainspace.token_ledger import CallRecord, MeasurementIdentity, TaskTrace, measure_call  # noqa: E402
from brainspace.tokens import count_tokens  # noqa: E402


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2), encoding="utf-8")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class FixtureClient:
    model = "fixture-not-a-real-model"
    max_request_bytes = 524288

    def __init__(self, arm, *, wrong=False, output=30, failure=False, followup=False):
        answer = {"returns": [10, None, 10], "stored": {"x": 10}}
        if wrong:
            answer = {"returns": [], "stored": {}}
        actions = [("read_file", {"path": "cache.py"}), ("answer", {"content": json.dumps(answer)})]
        if followup:
            actions.append(("answer", {"content": json.dumps(answer)}))
        self.actions = iter(actions)
        self.arm, self.calls, self.session = arm, 0, uuid.uuid4().hex
        self.output = output
        self.failure = failure

    def request(self, payload):
        return ResponsesTransport("http://127.0.0.1/v1", self.model).request(payload)

    def call(self, payload):
        if self.failure:
            return Reply(False, "http_error", True, json.dumps(self.request(payload)),
                         "Fully received fixture error", None, 500, 0.1)
        self.calls += 1
        name, args = next(self.actions)
        incoming = 100 if self.arm == "baseline" else 80
        outgoing = 20 if self.arm == "baseline" else self.output
        body = {
            "id": f"fixture-{self.session}-{self.calls}", "object": "response",
            "model": self.model, "status": "completed",
            "output": [{"type": "function_call", "call_id": f"c{self.calls}",
                        "name": name, "arguments": json.dumps(args)}],
            "usage": {"input_tokens": incoming, "output_tokens": outgoing,
                      "total_tokens": incoming + outgoing,
                      "input_tokens_details": {"cached_tokens": incoming // 2},
                      "output_tokens_details": {"reasoning_tokens": outgoing // 2}},
        }
        return Reply(True, "ok", True, json.dumps(self.request(payload)),
                     json.dumps(body), body, 200, 0.1)


def study(tmp_path, *, wrong=False, output=30, repeats=1, failure=False, followup=False):
    root = tmp_path / "study"
    snapshot(root)
    case = next(c for c in CASES if c.id == "explain_only")
    if followup:
        case = replace(case, followups=("Return the same result once more.",))
    arms = [Arm("baseline"), Arm("combined", scope=True, views=True)]
    order = []
    for rep in range(repeats):
        for arm in arms:
            task_id = f"fixture-study:{rep}:{case.id}"
            destination = root / "runs" / f"r{rep}-{case.id}-{arm.name}"
            run_case(case, arm, destination,
                     FixtureClient(arm.name, wrong=wrong and arm.name == "combined", output=output,
                                   failure=failure and arm.name == "combined", followup=followup),
                     task_id=task_id, learning_run_id="fixture-study", max_calls=4)
            order.append({"rep": rep, "case": case.id, "arm": arm.name, "task_id": task_id})
    write(root / "manifest.json", {
        "schema_version": 1, "study_id": "fixture-study", "status": "complete",
        "model_requested": FixtureClient.model, "harness": "explicit stateless tool-loop, not CLI/Desktop",
        "oracle_id": oracle_identity(), "source_manifest": "source-manifest.json",
        "case_identities": {case.id: case.identity},
        "arms": {a.name: {"policy_id": a.identity} for a in arms},
        "repeats": repeats, "max_calls_per_task": 4, "maximum_primary_calls": 8 * repeats,
        "reserved_preflight_calls": 1, "completed_runs": 2 * repeats, "capture_complete": True,
        "sampling": "predeclared non-IID challenge suite; order randomized only",
        "statistical_promotion_eligible": False,
        "metrics_predeclared": {"primary": "complete-json-body-text/utf8-ordinary",
                                "supplementary": "explicit-context-fields-json-v1; not a promotion metric"},
        "order": order,
    })
    reply = FixtureClient("setup").call({"input": [{"role": "user", "content": "ready"}]})
    write(root / "model-preflight.json", {
        "ok": True, "complete": True, "input": reply.input_text, "output": reply.output_text,
        "phase": "learning", "role": "verification",
    })
    # Deliberately false legacy summary: the checker must not use these totals.
    write(root / "summary.json", {"by_arm": {"combined": {"total_tokens": 0}}})
    return root


def run_path(root, arm="combined"):
    return root / "runs" / f"r0-explain_only-{arm}"


def edit_capture(root, edit, *, index=0, arm="combined", reseal=False):
    directory = run_path(root, arm)
    path = directory / "captures.jsonl"
    captures = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    edit(captures[index])
    path.write_text("".join(json.dumps(c) + "\n" for c in captures), encoding="utf-8")
    if reseal:
        result = load(directory / "result.json")
        old = result["trace"]["calls"][index]
        measured = measure_call(
            reference_measurement(), count_tokens,
            input_text=captures[index]["input"], output_text=captures[index]["output"],
            **{k: v for k, v in old.items() if k not in (
                "measurement_id", "reference_input_tokens", "reference_output_tokens",
                "input_sha256", "output_sha256")},
        )
        result["trace"]["calls"][index] = asdict(measured)
        trace = result["trace"]
        value = TaskTrace(**{**trace, "measurement": MeasurementIdentity(**trace["measurement"]),
                             "calls": tuple(CallRecord(**c) for c in trace["calls"])})
        result["totals"] = value.totals().to_dict()
        write(directory / "result.json", result)


def body_change(key, value):
    def change(capture):
        body = json.loads(capture["output"])
        body[key] = value
        capture["output"] = json.dumps(body)
    return change


def test_recomputes_raw_totals_keeps_units_separate_and_never_certifies(tmp_path):
    report = verify_study(study(tmp_path))
    assert report["audit_status"] == "consistent_with_declared_inventory"
    native = report["comparison"]["provider_reported"]
    assert native["baseline"]["total_tokens"] == 240
    assert native["candidate"]["total_tokens"] == 220
    assert native["saved_tokens"] == 20
    # Neither cached input nor reasoning is added/subtracted a second time.
    assert native["candidate"]["cached_input_tokens"] == 80
    assert native["candidate"]["reasoning_tokens"] == 30
    assert report["by_arm"]["combined"]["api_body_reference"]["total_tokens"] > 0
    assert report["statistical"]["certificate"] is None
    assert report["statistical"]["eligible"] is False
    assert report["statistical"]["confidence_interval"] is None
    assert report["comparison"]["provider_reported"]["predeclared_primary"] is False
    assert report["learning"]["all_in_tokens_per_success"] is None


def test_lower_inputs_but_higher_total_is_not_reported_as_a_win(tmp_path):
    report = verify_study(study(tmp_path, output=100))
    native = report["comparison"]["provider_reported"]
    assert native["candidate"]["input_tokens"] < native["baseline"]["input_tokens"]
    assert native["saved_tokens"] < 0
    assert native["observed_efficiency_win"] is False


def test_lower_total_with_quality_regression_is_not_a_win(tmp_path):
    report = verify_study(study(tmp_path, wrong=True))
    assert report["comparison"]["provider_reported"]["saved_tokens"] > 0
    assert report["quality"]["new_failures"] == 1
    assert report["comparison"]["provider_reported"]["observed_efficiency_win"] is False
    assert report["by_arm"]["combined"]["provider_reported"]["tokens_per_verified_success"] is None
    # Wrong tasks still consume tokens; they do not disappear from the numerator.
    assert report["by_arm"]["combined"]["provider_reported"]["total_tokens"] == 220


def test_all_failed_outcomes_do_not_manufacture_efficiency(tmp_path):
    root = study(tmp_path, wrong=True)
    path = run_path(root, "baseline") / "result.json"
    value = load(path)
    value["grade"].update(status="failed", success=False)
    value["grade"]["evidence_digest"] = digest(
        {k: v for k, v in value["grade"].items() if k != "evidence_digest"})
    write(path, value)
    report = verify_study(root)
    assert report["quality"]["new_failures"] == 0
    assert report["comparison"]["provider_reported"]["observed_efficiency_win"] is False


@pytest.mark.parametrize("filename", ["captures.jsonl", "result.json"])
def test_missing_run_artifacts_fail_closed(tmp_path, filename):
    root = study(tmp_path)
    (run_path(root) / filename).unlink()
    with pytest.raises(AuditError):
        verify_study(root)


def test_partial_capture_is_not_a_zero_cost_task(tmp_path):
    root = study(tmp_path)
    edit_capture(root, lambda c: c.update(complete=False, output=None))
    with pytest.raises(AuditError):
        verify_study(root)


def test_duplicate_and_omitted_calls_are_detected(tmp_path):
    root = study(tmp_path)
    path = run_path(root) / "captures.jsonl"
    lines = path.read_text().splitlines()
    path.write_text(lines[0] + "\n" + lines[0] + "\n")
    with pytest.raises(AuditError):
        verify_study(root)


@pytest.mark.parametrize("mutation", [
    lambda m: m["order"].pop(),
    lambda m: m.update(repeats=2),
    lambda m: m.update(status="interrupted"),
    lambda m: m.update(completed_runs=0),
])
def test_predeclared_complete_pair_grid_is_required(tmp_path, mutation):
    root = study(tmp_path)
    manifest = load(root / "manifest.json")
    mutation(manifest)
    write(root / "manifest.json", manifest)
    with pytest.raises(AuditError):
        verify_study(root)


def test_changed_frozen_source_rejected(tmp_path):
    root = study(tmp_path)
    source = root / "source/token-master-plugin/evals/quality/runner.py"
    source.write_text("print('not executed')\n")
    with pytest.raises(AuditError):
        verify_study(root)


def test_count_identity_and_payload_hashes_are_checked(tmp_path):
    root = study(tmp_path)
    edit_capture(root, lambda c: c.update(input=c["input"] + " "))
    with pytest.raises(AuditError):
        verify_study(root)


def test_response_model_mismatch_rejected_even_with_resealed_counts(tmp_path):
    root = study(tmp_path)
    edit_capture(root, body_change("model", "another-model"), reseal=True)
    with pytest.raises(AuditError):
        verify_study(root)


def test_opaque_server_state_rejected_even_with_resealed_counts(tmp_path):
    root = study(tmp_path)
    def change(capture):
        request = json.loads(capture["input"])
        request["previous_response_id"] = "unobserved"
        capture["input"] = json.dumps(request)
    edit_capture(root, change, reseal=True)
    with pytest.raises(AuditError):
        verify_study(root)


def test_missing_usage_keeps_reference_counts_but_native_total_unknown(tmp_path):
    root = study(tmp_path)
    edit_capture(root, body_change("usage", None), reseal=True)
    report = verify_study(root)
    assert report["by_arm"]["combined"]["api_body_reference"]["total_tokens"] > 0
    assert report["by_arm"]["combined"]["provider_reported"]["total_tokens"] is None
    assert report["comparison"]["provider_reported"]["saved_tokens"] is None
    assert report["comparison"]["provider_reported"]["observed_efficiency_win"] is False


@pytest.mark.parametrize("usage", [
    {"input_tokens": True, "output_tokens": 1, "total_tokens": 2},
    {"input_tokens": -1, "output_tokens": 1, "total_tokens": 0},
    {"input_tokens": 10, "output_tokens": 1, "total_tokens": 12},
    {"input_tokens": 10, "output_tokens": 1, "total_tokens": 11,
     "output_tokens_details": {"reasoning_tokens": 2}},
    {"input_tokens": 10, "output_tokens": 1, "total_tokens": 11,
     "input_tokens_details": {"cached_tokens": 11}},
])
def test_impossible_provider_counters_rejected(usage):
    with pytest.raises(AuditError):
        reported_usage({"usage": usage})


def test_missing_breakdowns_are_not_assumed_zero():
    value = reported_usage({"usage": {"input_tokens": 10, "output_tokens": 1, "total_tokens": 11}})
    assert value["total_tokens"] == 11
    assert value["cached_input_tokens"] is None
    assert value["reasoning_tokens"] is None


def test_encrypted_reasoning_has_unknown_explicit_output_not_native_zero(tmp_path):
    root = study(tmp_path)
    def change(capture):
        response = json.loads(capture["output"])
        response["output"].append({"type": "reasoning", "encrypted_content": "opaque"})
        capture["output"] = json.dumps(response)
    edit_capture(root, change, reseal=True)
    report = verify_study(root)
    assert report["by_arm"]["combined"]["explicit_context_reference"]["total_tokens"] is None
    assert report["by_arm"]["combined"]["provider_reported"]["total_tokens"] == 220


def test_unknown_quality_blocks_the_efficiency_claim(tmp_path):
    root = study(tmp_path)
    path = run_path(root) / "result.json"
    value = load(path)
    value["grade"].update(status="needs_blind_review", success=None)
    value["grade"]["evidence_digest"] = digest(
        {k: v for k, v in value["grade"].items() if k != "evidence_digest"})
    write(path, value)
    report = verify_study(root)
    assert report["quality"]["all_outcomes_known"] is False
    assert report["comparison"]["provider_reported"]["observed_efficiency_win"] is False


def test_workspace_and_grade_evidence_cannot_silently_change(tmp_path):
    root = study(tmp_path)
    (run_path(root) / "workspace/cache.py").write_text("edited = True\n")
    with pytest.raises(AuditError):
        verify_study(root)


def test_answer_events_must_match_the_actual_model_responses(tmp_path):
    root = study(tmp_path)
    edit_capture(root, body_change("output", [{
        "type": "function_call", "call_id": "changed", "name": "answer",
        "arguments": json.dumps({"content": "not the recorded answer"}),
    }]), index=1, reseal=True)
    with pytest.raises(AuditError):
        verify_study(root)


def test_repeated_cases_are_not_treated_as_independent_new_tasks(tmp_path):
    report = verify_study(study(tmp_path, repeats=2))
    assert report["statistical"]["independent_task_sample_size"] is None
    assert report["statistical"]["unique_cases"] == 1
    assert report["statistical"]["repeats_per_case"] == 2
    assert len(report["pairs"]) == 2


def test_prior_digest_detects_subsequent_changes_without_trusting_summary(tmp_path):
    root = study(tmp_path)
    first = verify_study(root)
    again = verify_study(root, expected_evidence_digest=first["evidence_digest"])
    assert first["evidence_digest"] == again["evidence_digest"]
    # Coordinated raw-body + ledger edit still cannot match a previously kept receipt.
    edit_capture(root, body_change("id", "changed-metadata"), reseal=True)
    with pytest.raises(AuditError, match="evidence_receipt_mismatch"):
        verify_study(root, expected_evidence_digest=first["evidence_digest"])


def test_source_manifest_cannot_escape_study_root(tmp_path):
    root = study(tmp_path)
    manifest = load(root / "source-manifest.json")
    manifest["../../outside.py"] = "0" * 64
    write(root / "source-manifest.json", manifest)
    with pytest.raises(AuditError):
        verify_study(root)


def add_review(root):
    path = run_path(root) / "result.json"
    result = load(path)
    result["grade"].update(status="needs_blind_review", success=None)
    result["grade"]["evidence_digest"] = digest(
        {k: v for k, v in result["grade"].items() if k != "evidence_digest"})
    write(path, result)
    answer_sha = hashlib.sha256(json.dumps(result["answer"], sort_keys=True).encode()).hexdigest()
    review = root / "blind-review"
    review.mkdir()
    write(review / "mapping.json", {"fixture-review": {
        "result": str(path.relative_to(root)), "answer_sha256": answer_sha}})
    write(review / "answers.json", [{"review_id": "fixture-review", "answer": result["answer"]}])
    write(review / "verdicts.json", {
        "reviewer": "fixture-only", "method": "fixture", "not_human_review": True,
        "not_formal_proof_checker": True, "not_jev_score": True,
        "independent_model_weights_claimed": False,
        "verdicts": {"fixture-review": {"success": True, "status": "correct", "answer_sha256": answer_sha}},
    })


def test_blinded_review_requires_explicit_opt_in_and_exact_answer_binding(tmp_path):
    root = study(tmp_path)
    add_review(root)
    assert verify_study(root)["quality"]["all_outcomes_known"] is False
    report = verify_study(root, use_recorded_reviews=True)
    assert report["quality"]["all_outcomes_known"] is True
    assert report["quality"]["reviewer"]["not_human_review"] is True
    assert report["quality"]["outcomes_reexecuted_by_checker"] is False
    assert report["quality"]["reviewer"]["answer_hash_protocol"] == "json-sorted-ensure-ascii-default-separators-v1"


def test_changed_blinded_answer_is_not_the_answer_reviewed(tmp_path):
    root = study(tmp_path)
    add_review(root)
    path = root / "blind-review/answers.json"
    answers = load(path)
    answers[0]["answer"] = "other answer"
    write(path, answers)
    with pytest.raises(AuditError, match="blinded_answer_hash_mismatch"):
        verify_study(root, use_recorded_reviews=True)


def test_review_cannot_turn_a_known_failure_into_a_win(tmp_path):
    root = study(tmp_path)
    add_review(root)
    path = run_path(root) / "result.json"
    result = load(path)
    result["grade"].update(status="failed", success=False)
    result["grade"]["evidence_digest"] = digest(
        {k: v for k, v in result["grade"].items() if k != "evidence_digest"})
    write(path, result)
    with pytest.raises(AuditError, match="review_overrides_graded_outcome"):
        verify_study(root, use_recorded_reviews=True)


def test_complete_failed_calls_are_still_counted(tmp_path):
    report = verify_study(study(tmp_path, failure=True))
    failed = report["by_arm"]["combined"]
    assert failed["calls"] == 1
    assert failed["failures"] == 1
    assert failed["api_body_reference"]["input_tokens"] > 0
    assert failed["api_body_reference"]["output_tokens"] > 0
    assert failed["provider_reported"]["total_tokens"] is None
    assert report["comparison"]["api_body_reference"]["observed_efficiency_win"] is False


def test_changed_generation_controls_cannot_be_compared(tmp_path):
    root = study(tmp_path)
    def change(capture):
        request = json.loads(capture["input"])
        request["max_output_tokens"] = 20
        capture["input"] = json.dumps(request)
    for i in range(2):
        edit_capture(root, change, index=i, reseal=True)
    with pytest.raises(AuditError, match="between_run_controls_or_tools_mismatch"):
        verify_study(root)


def test_changed_task_prompt_cannot_be_compared(tmp_path):
    root = study(tmp_path)
    def change(capture):
        request = json.loads(capture["input"])
        next(item for item in request["input"] if item.get("role") == "user")["content"] = "Different task."
        capture["input"] = json.dumps(request)
    for i in range(2):
        edit_capture(root, change, index=i, reseal=True)
    with pytest.raises(AuditError, match="paired_task_prompt_mismatch"):
        verify_study(root)


def test_duplicate_provider_response_id_rejected(tmp_path):
    root = study(tmp_path)
    first = json.loads((run_path(root) / "captures.jsonl").read_text().splitlines()[0])
    response_id = json.loads(first["output"])["id"]
    edit_capture(root, body_change("id", response_id), index=1, reseal=True)
    with pytest.raises(AuditError, match="duplicate_or_invalid_response_id"):
        verify_study(root)


def test_actual_offline_cli_returns_receipt_and_preserves_existing_output(tmp_path):
    root = study(tmp_path)
    output = tmp_path / "receipt.json"
    cli = Path(__file__).resolve().parents[3] / "evals/verify_savings.py"
    command = [sys.executable, "-X", "utf8", str(cli), "--study", str(root), "--output", str(output)]
    first = subprocess.run(command, capture_output=True, text=True, timeout=45)
    assert first.returncode == 0, first.stdout + first.stderr
    receipt = output.read_bytes()
    second = subprocess.run(command, capture_output=True, text=True, timeout=45)
    assert second.returncode == 2
    assert output.read_bytes() == receipt
    assert json.loads(first.stdout)["statistical_certificate"] is None


def recompute_totals_and_grade(directory, result):
    trace = result["trace"]
    measured = TaskTrace(**{**trace, "measurement": MeasurementIdentity(**trace["measurement"]),
                            "calls": tuple(CallRecord(**c) for c in trace["calls"])})
    result["totals"] = measured.totals().to_dict()
    case = next(c for c in CASES if c.id == "explain_only")
    result["grade"] = grade(case, directory / "workspace", result["answer"], result["events"])
    write(directory / "result.json", result)


def test_omitted_invocation_still_visible_in_history_is_rejected(tmp_path):
    root = study(tmp_path)
    directory = run_path(root)
    captures = [json.loads(line) for line in (directory / "captures.jsonl").read_text().splitlines()]
    result = load(directory / "result.json")
    trace = result["trace"]
    # Omit the read, but leave its replayed assistant/tool pair in the next input.
    call_id = f'{trace["task_id"]}:{trace["policy_id"]}:0'
    captures = [{**captures[1], "call_id": call_id}]
    trace["calls"] = [{**trace["calls"][1], "call_id": call_id}]
    trace["expected_call_ids"] = [call_id]
    result["events"] = result["events"][1:]
    (directory / "captures.jsonl").write_text(json.dumps(captures[0]) + "\n")
    recompute_totals_and_grade(directory, result)
    with pytest.raises(AuditError):
        verify_study(root)


def test_unaccounted_user_continuation_is_rejected(tmp_path):
    root = study(tmp_path)
    def change(capture):
        request = json.loads(capture["input"])
        request["input"].append({"role": "user", "content": "Do an easier task instead."})
        capture["input"] = json.dumps(request)
    edit_capture(root, change, index=1, reseal=True)
    with pytest.raises(AuditError):
        verify_study(root)


def test_actual_later_task_stage_is_paired_not_only_the_initial_prompt(tmp_path):
    root = study(tmp_path, followup=True)
    assert verify_study(root)["quality"]["all_outcomes_known"] is True
    def change(capture):
        request = json.loads(capture["input"])
        users = [i for i in request["input"] if i.get("role") == "user"]
        assert len(users) == 2
        users[1]["content"] = "Different follow-up requirement."
        capture["input"] = json.dumps(request)
    edit_capture(root, change, index=2, reseal=True)
    with pytest.raises(AuditError):
        verify_study(root)


@pytest.mark.parametrize("reviewed", [False, True])
def test_captured_integer_to_float_change_cannot_reuse_exact_outcome(tmp_path, reviewed):
    root = study(tmp_path)
    if reviewed:
        add_review(root)
    def change(capture):
        response = json.loads(capture["output"])
        answer = {"returns": [10.0, None, 10.0], "stored": {"x": 10.0}}
        response["output"][0]["arguments"] = json.dumps({"content": json.dumps(answer)})
        capture["output"] = json.dumps(response)
    edit_capture(root, change, index=1, reseal=True)
    with pytest.raises(AuditError):
        verify_study(root, use_recorded_reviews=reviewed)


def test_final_answer_must_have_been_emitted_not_just_match_a_receipt(tmp_path):
    root = study(tmp_path)
    path = run_path(root) / "result.json"
    result = load(path)
    result["answer"] = "This final answer was never emitted."
    result["grade"]["evidence"]["answer"] = result["answer"]
    result["grade"]["evidence"]["stage_answers"] = result["stage_answers"]
    result["grade"]["evidence_digest"] = digest(
        {k: v for k, v in result["grade"].items() if k != "evidence_digest"})
    write(path, result)
    with pytest.raises(AuditError):
        verify_study(root)


def test_no_calls_after_failure_in_this_no_retry_runner(tmp_path):
    root = study(tmp_path)
    directory = run_path(root)
    edit_capture(root, lambda c: c.update(reason="http_error"))
    result = load(directory / "result.json")
    result["trace"]["calls"][0]["completion_status"] = "failed"
    result["events"] = result["events"][1:]
    recompute_totals_and_grade(directory, result)
    with pytest.raises(AuditError):
        verify_study(root)


def test_terminal_transport_failure_requires_matching_failure_flag(tmp_path):
    root = study(tmp_path, failure=True)
    path = run_path(root) / "result.json"
    result = load(path)
    result["failure"] = None
    write(path, result)
    with pytest.raises(AuditError):
        verify_study(root)


def test_preflight_cannot_reuse_a_primary_response(tmp_path):
    root = study(tmp_path)
    primary = json.loads((run_path(root) / "captures.jsonl").read_text().splitlines()[0])
    path = root / "model-preflight.json"
    setup = load(path)
    setup.update(input=primary["input"], output=primary["output"])
    write(path, setup)
    with pytest.raises(AuditError):
        verify_study(root)


@pytest.mark.parametrize("left,right", [(True, 1), (False, 0), (1, 1.0), (-0.0, 0.0)])
def test_outcome_json_comparison_preserves_types(left, right):
    from quality.savings import _same
    assert not _same({"value": left}, {"value": right})


def test_history_allows_tool_output_views_without_allowing_dropped_calls(tmp_path):
    root = study(tmp_path)
    def change(capture):
        request = json.loads(capture["input"])
        tool = next(i for i in request["input"] if i.get("type") == "function_call_output")
        tool["output"] = "Synthetic shorter tool view; call and result pair unchanged."
        capture["input"] = json.dumps(request)
    edit_capture(root, change, index=1, reseal=True)
    assert verify_study(root)["by_arm"]["combined"]["calls"] == 2
