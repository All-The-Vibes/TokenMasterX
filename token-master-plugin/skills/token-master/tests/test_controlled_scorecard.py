"""Accounting and decisions must not convert partial or noisy runs into wins."""
from pathlib import Path
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
import run_controlled_scorecard as trial  # noqa: E402


def rows(candidate=(8, 8, 8), control=(10, 10, 10)):
    result = []
    for repeat in range(3):
        for arm, values in (("tokenmaster_updated", candidate), ("baseline", control)):
            result.append({
                "repeat": repeat, "case": "case", "arm": arm, "correct": True,
                "calls": 2, "primary_accounting_complete": True,
                "comparator_complete": True, "primary_reference_tokens": 20,
                "known_primary_reference_tokens": 20,
                "bridge_reported_tokens": values[repeat],
                "gateway_input_tokens": values[repeat] - 1,
                "gateway_output_tokens": 1, "original_retrievals": 0,
                "transformed_requests": 0, "all_in_case_seconds": 1,
            })
    return result


def schedule(items):
    return [(r["repeat"], r["case"], r["arm"]) for r in items]


def test_lower_tokens_and_all_quality_checks_pass_is_bounded_better():
    items = rows()
    report = trial.summarize(items, schedule(items))
    assert report["comparisons"]["baseline"]["verdict"] == "better"
    assert report["comparisons"]["baseline"]["reduction_percent"] == pytest.approx(20)
    assert report["policy_promoted"] is False
    assert report["statistical_certificate"] is None
    assert report["by_arm"]["tokenmaster_updated"]["primary_calls"] == 6


def test_missing_expected_attempt_cannot_be_a_savings_win():
    items = rows()
    report = trial.summarize(items[:-1], schedule(items))
    assert report["complete"] is False
    assert len(report["missing_task_runs"]) == 1
    assert report["comparisons"]["baseline"]["verdict"] == "inconclusive"
    assert report["by_arm"]["baseline"]["bridge_reported_tokens"] is None


def test_missing_gateway_usage_is_unknown_not_zero():
    items = rows()
    items[0]["bridge_reported_tokens"] = None
    items[0]["gateway_input_tokens"] = None
    items[0]["gateway_output_tokens"] = None
    report = trial.summarize(items, schedule(items))
    assert report["by_arm"]["tokenmaster_updated"]["bridge_reported_tokens"] is None
    assert report["comparisons"]["baseline"]["verdict"] == "inconclusive"


def test_quality_regression_is_worse_despite_fewer_tokens():
    items = rows()
    items[0]["correct"] = False
    report = trial.summarize(items, schedule(items))
    assert report["comparisons"]["baseline"]["verdict"] == "worse"
    assert report["by_arm"]["tokenmaster_updated"]["correct_tasks"] == 2
    assert report["by_arm"]["tokenmaster_updated"]["bridge_reported_tokens"] == 24


def test_unknown_oracle_outcome_is_not_a_quality_failure_or_a_win():
    items = rows()
    items[0]["correct"] = None
    report = trial.summarize(items, schedule(items))
    assert report["comparisons"]["baseline"]["verdict"] == "inconclusive"
    assert report["comparisons"]["baseline"]["reason"] == "unknown_quality_outcome"
    assert report["by_arm"]["tokenmaster_updated"]["ungraded_tasks"] == 1


def test_equal_quality_consistently_higher_tokens_is_worse():
    items = rows(candidate=(12, 12, 12))
    report = trial.summarize(items, schedule(items))
    assert report["comparisons"]["baseline"]["verdict"] == "worse"
    assert report["comparisons"]["baseline"]["reduction_percent"] == pytest.approx(-20)


def test_pooled_savings_with_mixed_repetitions_stays_inconclusive():
    items = rows(candidate=(6, 6, 11))
    report = trial.summarize(items, schedule(items))
    assert report["comparisons"]["baseline"]["verdict"] == "inconclusive"


def test_more_correct_but_more_tokens_is_a_tradeoff_not_a_win():
    items = rows(candidate=(12, 12, 12))
    items[1]["correct"] = False
    report = trial.summarize(items, schedule(items))
    assert report["comparisons"]["baseline"]["verdict"] == "inconclusive"


def test_ties_do_not_become_wins():
    items = rows(candidate=(10, 10, 10))
    report = trial.summarize(items, schedule(items))
    assert report["comparisons"]["baseline"]["verdict"] == "inconclusive"


def test_duplicate_attempt_is_rejected():
    items = rows()
    with pytest.raises(ValueError, match="inventory"):
        trial.summarize(items + [items[0]], schedule(items))


def test_unplanned_attempt_is_rejected():
    items = rows()
    planned = schedule(items)
    items[0] = dict(items[0], case="unplanned")
    with pytest.raises(ValueError, match="inventory"):
        trial.summarize(items, planned)


def test_schedule_is_deterministic_complete_and_varied():
    first = trial.make_schedule(["a", "b"], ["baseline", "tokenmaster_updated"])
    assert first == trial.make_schedule(["a", "b"], ["baseline", "tokenmaster_updated"])
    assert len(first) == len(set(first)) == 12
    assert {r for r, _, _ in first} == {0, 1, 2}
    assert [x[1:] for x in first if x[0] == 0] != [
        x[1:] for x in first if x[0] == 1]


def test_network_permission_is_explicit_and_checked_before_work(tmp_path, monkeypatch):
    monkeypatch.setattr(trial, "execute", lambda args: pytest.fail("must not execute"))
    with pytest.raises(SystemExit) as result:
        trial.main(["--output", str(tmp_path / "out"),
                    "--reference-study", str(tmp_path / "reference"),
                    "--candidate", str(tmp_path / "candidate.json")])
    assert result.value.code == 2


def test_interrupted_grading_keeps_captured_and_unreturned_attempts(tmp_path, monkeypatch):
    run = tmp_path / "run"
    run.mkdir()
    pending = [{"call_id": "one", "state": "pending"}, {"call_id": "one", "state": "captured"},
               {"call_id": "two", "state": "pending"}]
    (run / "invocations.jsonl").write_text(
        "\n".join(json.dumps(x) for x in pending), encoding="utf-8")
    (run / "captures.jsonl").write_text(json.dumps({
        "call_id": "one", "complete": True, "input": "abc", "output": "defg", "reason": "ok"
    }) + "\n", encoding="utf-8")
    monkeypatch.setattr(trial.tokens, "count_tokens", len)
    record = trial.interrupted_row(run, 0, "case", "baseline", 2)
    assert record["calls"] == 2
    assert record["unreturned_call_ids"] == ["two"]
    assert record["known_primary_reference_tokens"] == 7
    assert record["primary_reference_tokens"] is None
    assert record["bridge_reported_tokens"] is None
    assert record["correct"] is None
    assert (run / "interrupted-attempt.json").is_file()
    report = trial.summarize([record], [(0, "case", "baseline")])
    assert report["attempted_task_runs"] == 1
    assert report["missing_task_runs"] == []
    assert report["complete"] is False


def test_early_halt_preserves_the_entire_second_suite_inventory(tmp_path):
    plans = []
    for name in ("six-task", "fresh-coding"):
        directory = tmp_path / name
        directory.mkdir()
        plans.append({"name": name, "directory": directory,
                      "schedule": trial.make_schedule(["case"], ["baseline", "tokenmaster_updated"])})
    invoked = []

    def run_one(plan):
        invoked.append(plan["name"])
        return trial.summarize([], plan["schedule"]) | {"halt": "model_unavailable"}

    report = trial.run_planned_suites(plans, run_one)
    assert invoked == ["six-task"]
    assert set(report) == {"six-task", "fresh-coding"}
    assert report["fresh-coding"]["expected_task_runs"] == 6
    assert report["fresh-coding"]["attempted_task_runs"] == 0
    assert len(report["fresh-coding"]["missing_task_runs"]) == 6
    assert report["fresh-coding"]["halt"] == "not_started_after:six-task"
