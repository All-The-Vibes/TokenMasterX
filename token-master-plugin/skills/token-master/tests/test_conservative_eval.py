"""Frozen regression/probe workload and its accounting, without model calls."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
from brainspace.request_policy import PROTOCOL, SourceReadInfo, plan_request  # noqa: E402
from quality.cases import materialize  # noqa: E402
from quality.responses import Reply  # noqa: E402
from run_quality import child_environment  # noqa: E402
import parity_cases  # noqa: E402
import run_conservative as study  # noqa: E402
from source_read_adapter import ConservativeArm  # noqa: E402


def expected_answer(parent):
    return next(t["expected"] for t in parity_cases._load_manifest()["tasks"] if t["id"] == parent)


def probe_inputs(spec):
    case = next(c for c in study.probe_cases() if c.id == spec[0])
    messages = [{"role": "system", "content": "Unchanged instructions."},
                {"role": "user", "content": case.prompt}]
    infos, events = [], []
    for n, index in enumerate(spec[2]):
        path, text = case.fixtures[index]
        call_id = "call-" + str(n)
        arguments = {"path": path}
        messages.extend([
            {"role": "assistant", "tool_calls": [{
                "id": call_id, "type": "function",
                "function": {"name": "read_file", "arguments": json.dumps(arguments)},
            }]},
            {"role": "tool", "tool_call_id": call_id, "content": text},
        ])
        infos.append(SourceReadInfo.from_text(
            call_id=call_id, tool_name="read_file", source_path=path,
            content=text, status="success"))
        events.append({"name": "read_file", "arguments": arguments})
    return case, {"model": "fixture", "messages": messages}, tuple(infos), events


@pytest.mark.parametrize("spec", study.PROBES, ids=[row[0] for row in study.PROBES])
def test_probe_eligibility_and_parent_gold_are_fixed_before_live_calls(tmp_path, spec):
    case, request, infos, events = probe_inputs(spec)
    assert case.fixtures == next(
        c.fixtures for c in parity_cases.load_cases() if c.id == spec[1])
    result = plan_request(
        request, policy=ConservativeArm("candidate").policy,
        protocol=PROTOCOL, intent=case.intent, count=len,
        source_reads=infos, stable_prefix_messages=2,
    )
    assert (result.status == "transformed") == spec[3]
    if spec[3]:
        assert result.changed_message_indices == (5,)
        assert result.request["messages"][3] == request["messages"][3]
    else:
        assert result.request == request
    workspace = materialize(case, tmp_path / "workspace")
    answer = expected_answer(spec[1])
    assert study.grade(case, workspace, answer, events)["success"]
    assert not study.grade(replace(case, prompt="changed"), workspace, answer, events)["success"]
    assert not study.grade(case, workspace, answer, events[1:])["success"]
    assert not study.grade(case, workspace, {"wrong": True}, events)["success"]


def test_probe_extra_reads_are_counted_not_hidden_or_erased(tmp_path):
    case, _, _, events = probe_inputs(study.PROBES[2])
    workspace = materialize(case, tmp_path / "workspace")
    # Additional recovery/rereads do not change gold or erase their accounting.
    events.append(events[0])
    assert study.grade(case, workspace, expected_answer(study.PROBES[2][1]), events)["success"]


def test_original_six_tasks_and_original_oracle_remain_unchanged(tmp_path):
    case = parity_cases.load_cases()[0]
    workspace = materialize(case, tmp_path / "workspace")
    answer = expected_answer(case.id)
    assert study.grade(case, workspace, answer, []) == parity_cases.grade(
        case, workspace, answer, [])


def test_schedule_is_single_pass_adjacent_and_counterbalanced():
    cases = parity_cases.load_cases()
    schedule = study.make_schedule(cases, 0)
    assert len(schedule) == 12 and len(set(schedule)) == 12
    assert schedule == study.make_schedule(cases, 0)
    first = []
    for i in range(0, len(schedule), 2):
        a, b = schedule[i:i+2]
        assert a[0] == b[0] == 0 and a[1] == b[1]
        assert {a[2], b[2]} == set(study.ARM_NAMES)
        first.append(a[2])
    assert first.count("baseline") == first.count("tokenmaster_conservative") == 3
    with pytest.raises(ValueError):
        study.make_schedule([cases[0], cases[0]], 0)
    with pytest.raises(ValueError):
        study.make_schedule([], 0)


@pytest.mark.parametrize("complete,tokens", [(False, 90), (True, None)])
def test_missing_results_or_usage_cannot_be_a_savings_claim(complete, tokens):
    summary = {"complete": complete, "all_tasks_correct": True, "by_arm": {
        "baseline": {"primary_calls": 10, "bridge_reported_tokens": 100},
        "tokenmaster_conservative": {"primary_calls": 10, "bridge_reported_tokens": tokens},
    }}
    assert study.comparison(summary)["gateway_token_reduction_percent"] is None
    assert study.comparison(summary)["usage_complete"] is False


def test_network_opt_in_is_required_before_creating_output(tmp_path):
    with pytest.raises(SystemExit) as error:
        study.main(["--output", str(tmp_path / "out"), "--reference-study", str(tmp_path)])
    assert error.value.code == 2 and not (tmp_path / "out").exists()


def test_frozen_runner_imports_without_reaching_back_into_checkout(tmp_path):
    reference = tmp_path / "reference"
    reference.mkdir()
    (reference / "manifest.json").write_text("{}", encoding="utf-8")
    output = tmp_path / "frozen"
    entry = study.freeze(output, reference)
    environment = child_environment(output)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-B", str(entry), "--help"],
        cwd=output, env=environment, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert b"--allow-network" in result.stdout
    manifest = json.loads((output / "source-manifest.json").read_text(encoding="utf-8"))
    assert any(name.endswith("exact_reuse.py") for name in manifest)
    assert not (output / "manifest.json").exists()


@pytest.mark.parametrize("name,args", [
    ("read_file", {}), ("read_file", {"path": []}),
    ("fetch_artifact", {}), ("fetch_artifact", {"path": []}),
])
def test_malformed_reads_keep_failed_grade_known_usage_and_remaining_schedule(
    tmp_path, monkeypatch, name, args,
):
    event = {"name": name, "arguments": args}
    assert study.event_counts([event])["malformed_read_attempts"] == 1
    assert study.event_counts([event])["source_read_attempts"] == 1
    assert study.event_counts([event])["repeated_source_reads"] == 0
    # Exercise the actual scheduling/row-writing path without any transport.
    output = tmp_path / "batch"
    output.mkdir()
    (output / "source-manifest.json").write_text("{}", encoding="utf-8")
    (output / "reference-manifest.json").write_text(json.dumps({
        "model": "fixture", "base_url": "http://127.0.0.1:1/v1",
        "controls": {"base_instructions": "Same instructions.", "common_tools": []},
    }), encoding="utf-8")
    monkeypatch.setattr(study, "__file__", str(output / "source/run_conservative.py"))
    # execute() intentionally installs these frozen settings process-locally.
    monkeypatch.setattr(study.runner, "BASE_INSTRUCTIONS", study.runner.BASE_INSTRUCTIONS)
    monkeypatch.setattr(study.runner, "TOOLS", study.runner.TOOLS)
    monkeypatch.setattr(study.runner, "grade", study.runner.grade)

    class NoNetwork:
        def __init__(self, *_, **__):
            self.start = time.monotonic()
            self.calls = self.known_tokens = 0
            self.halt = None

        def check_limits(self):
            return 3600

        def call(self, _):
            self.calls += 1
            return Reply(True, "ok", complete=True)

    attempted = []

    def fake_case(case, arm, directory, client, **_):
        directory.mkdir(parents=True)
        attempted.append((case.id, arm.name))
        client.calls += 1
        failed = len(attempted) == 1
        return {
            "grade": {"success": not failed, "status": "failed" if failed else "passed"},
            "failure": "invalid_tool_action" if failed else None,
            "regime_valid": True, "events": [event] if failed else [], "views": [],
        }

    monkeypatch.setattr(study, "ControlledBudget", NoNetwork)
    monkeypatch.setattr(study.runner, "run_case", fake_case)
    monkeypatch.setattr(study, "recount", lambda *_: {
        "calls": 1, "primary_accounting_complete": True,
        "primary_reference_tokens": 11, "known_primary_reference_tokens": 11,
    })
    monkeypatch.setattr(study, "gateway_counts", lambda _: (10, 1))
    assert study.execute(SimpleNamespace(output=output)) == 0
    report = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    rows = [row for suite in report["suites"].values() for row in suite["runs"]]
    assert len(rows) == len(attempted) == len(set(attempted)) == 20
    assert rows[0]["correct"] is False and rows[0]["failure"] == "invalid_tool_action"
    assert rows[0]["bridge_reported_tokens"] == rows[0]["primary_reference_tokens"] == 11
    assert rows[0]["malformed_read_attempts"] == 1
    assert all(row["correct"] is True for row in rows[1:])
    assert report["halt"] is None and report["primary_attempts_including_readiness"] == 21
