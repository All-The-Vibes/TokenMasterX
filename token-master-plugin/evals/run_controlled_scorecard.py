"""Frozen four-arm, repeated diagnostic plus executable coding scorecard.

No policy search, Jev, promotion, selected retries, or host-profile changes.
The two suites are reported separately; neither is a population certificate.
"""
import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import time
from typing import Any

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "skills/token-master"))
from brainspace import tokens  # noqa: E402
from brainspace.request_policy import RequestPolicy, policy_neighbors  # noqa: E402
from quality import runner  # noqa: E402
from quality.cases import digest  # noqa: E402
from quality.recovery_guidance import clarify_recovery_tools, absent_headroom_message  # noqa: E402
from quality.responses import ResponsesTransport, parse_json  # noqa: E402
from refinement.core import native_usage  # noqa: E402
from run_parity import recount, PONYTAIL_COMMIT, PONYTAIL_INSTRUCTIONS  # noqa: E402
from run_quality import child_environment, snapshot as quality_snapshot  # noqa: E402
from run_repository import BudgetClient  # noqa: E402
from source_read_adapter import SourceAwareArm, executor_source_reads  # noqa: E402

ARMS = ("baseline", "ponytail", "tokenmaster_old", "tokenmaster_updated")
SEEDS = (0, 1, 2)
PROTOCOL = "frozen-four-arm-repeated-scorecard-v1"


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False),
                          encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_schedule(cases, arms=ARMS):
    if len(set(cases)) != len(cases) or len(set(arms)) != len(arms):
        raise ValueError("duplicate schedule inventory")
    result = []
    for repeat, seed in enumerate(SEEDS):
        block = [(repeat, case, arm) for case in cases for arm in arms]
        random.Random(seed).shuffle(block)
        result.extend(block)
    return result


def _totals(rows, planned):
    complete = len(rows) == planned and all(
        r["primary_accounting_complete"] and r["comparator_complete"] for r in rows)

    def known_sum(field):
        values = [r.get(field) for r in rows]
        return sum(values) if complete and all(x is not None for x in values) else None

    return {
        "planned_tasks": planned, "attempted_tasks": len(rows),
        "correct_tasks": sum(r["correct"] is True for r in rows),
        "ungraded_tasks": sum(type(r["correct"]) is not bool for r in rows),
        "complete": complete, "primary_calls": sum(r["calls"] for r in rows),
        "bridge_reported_tokens": known_sum("bridge_reported_tokens"),
        "gateway_input_tokens": known_sum("gateway_input_tokens"),
        "gateway_output_tokens": known_sum("gateway_output_tokens"),
        "primary_reference_tokens": known_sum("primary_reference_tokens"),
        "known_primary_reference_tokens": sum(r["known_primary_reference_tokens"] for r in rows),
        "original_retrievals": sum(r.get("original_retrievals", 0) for r in rows)
        if complete and not any(r.get("recovery_and_transform_counts_unknown") for r in rows) else None,
        "transformed_requests": sum(r.get("transformed_requests", 0) for r in rows)
        if complete and not any(r.get("recovery_and_transform_counts_unknown") for r in rows) else None,
        "observed_wall_seconds": sum(r["all_in_case_seconds"] for r in rows),
    }


def _comparison(rows, schedule, control):
    """Predeclared descriptive gate, never a statistical promotion decision."""
    candidate = "tokenmaster_updated"
    names = (candidate, control)
    selected = [r for r in rows if r["arm"] in names]
    expected = {(repeat, case, arm) for repeat, case, arm in schedule if arm in names}
    found = {(r["repeat"], r["case"], r["arm"]): r for r in selected}
    report: dict[str, Any] = {
        "verdict": "inconclusive", "reason": "incomplete_or_unknown_usage",
        "reduction_percent": None, "quality_regressions": [], "by_repeat": []}
    if set(found) != expected or any(
        not r["primary_accounting_complete"] or not r["comparator_complete"]
        or r["bridge_reported_tokens"] is None or type(r["correct"]) is not bool
        for r in selected
    ):
        if any(type(r["correct"]) is not bool for r in selected):
            report["reason"] = "unknown_quality_outcome"
        return report
    pairs = {(repeat, case) for repeat, case, _ in expected}
    if any((repeat, case, name) not in found for repeat, case in pairs for name in names):
        return report
    for repeat, case in sorted(pairs):
        new, old = (found[repeat, case, name] for name in names)
        if old["correct"] is True and new["correct"] is not True:
            report["quality_regressions"].append({"repeat": repeat, "case": case})
    for repeat in sorted({x[0] for x in pairs}):
        amounts = {name: sum(r["bridge_reported_tokens"] for r in selected
                            if r["repeat"] == repeat and r["arm"] == name) for name in names}
        report["by_repeat"].append({"repeat": repeat, "candidate_tokens": amounts[candidate],
                                    "control_tokens": amounts[control],
                                    "difference": amounts[candidate] - amounts[control]})
    new_total = sum(r["candidate_tokens"] for r in report["by_repeat"])
    old_total = sum(r["control_tokens"] for r in report["by_repeat"])
    report["reduction_percent"] = 100 * (1 - new_total / old_total) if old_total else None
    equal_quality = all(found[repeat, case, candidate]["correct"]
                        == found[repeat, case, control]["correct"] for repeat, case in pairs)
    all_correct = all(found[repeat, case, candidate]["correct"] is True for repeat, case in pairs)
    differences = [r["difference"] for r in report["by_repeat"]]
    if report["quality_regressions"]:
        report.update(verdict="worse", reason="paired_quality_regression")
    elif all_correct and all(x < 0 for x in differences):
        report.update(verdict="better", reason="all_candidate_checks_pass_and_each_repeat_uses_less")
    elif equal_quality and all(x > 0 for x in differences):
        report.update(verdict="worse", reason="equal_paired_correctness_and_each_repeat_uses_more")
    else:
        report["reason"] = "tie_mixed_direction_or_quality_token_tradeoff"
    return report


def summarize(rows, schedule):
    planned = {tuple(x) for x in schedule}
    found = {(r["repeat"], r["case"], r["arm"]) for r in rows}
    if not planned or len(planned) != len(schedule) or len(found) != len(rows) or not found <= planned:
        raise ValueError("invalid planned/observed inventory")
    names = list(dict.fromkeys(x[2] for x in schedule))
    by_arm = {name: _totals([r for r in rows if r["arm"] == name],
                           sum(arm == name for _, _, arm in schedule)) for name in names}
    by_repeat = {}
    for repeat in sorted({x[0] for x in schedule}):
        by_repeat[str(repeat)] = {
            name: _totals([r for r in rows if r["arm"] == name and r["repeat"] == repeat],
                          sum(r == repeat and arm == name for r, _, arm in schedule))
            for name in names}
    return {
        "complete": found == planned and all(r["complete"] for r in by_arm.values()),
        "all_tasks_correct": found == planned and all(r["correct"] is True for r in rows),
        "expected_task_runs": len(schedule), "attempted_task_runs": len(rows),
        "missing_task_runs": [list(x) for x in sorted(planned - found)],
        "by_arm": by_arm, "by_repeat": by_repeat, "runs": rows,
        "comparisons": {name: _comparison(rows, schedule, name) for name in names
                        if name != "tokenmaster_updated" and "tokenmaster_updated" in names},
        "statistical_certificate": None, "policy_promoted": False,
        "primary_measurement": "gateway-reported input plus output, not authenticated serving usage",
        "secondary_measurement": "complete API-body reference tokenization, including metadata",
        "scope": "Task requests only; readiness separate; opaque upstream work not asserted zero.",
    }


@dataclass(frozen=True)
class ControlledArm(SourceAwareArm):
    policy_json: str = ""
    artifact_identity: str = ""

    @property
    def policy(self):
        return RequestPolicy.from_json(self.policy_json)


class ControlledBudget(BudgetClient):
    halt: str | None

    def __init__(self, base, output, planned_tasks, reference_limit):
        super().__init__(base, output)
        self.max_calls = planned_tasks * 10 + 1
        self.reference_limit = reference_limit

    def check_limits(self):
        remaining = 3600 - (time.monotonic() - self.start)
        if self.halt is None:
            if self.calls >= self.max_calls:
                self.halt = "call_limit"
            elif remaining <= 0:
                self.halt = "wall_time_limit"
            elif self.known_tokens >= self.reference_limit:
                self.halt = "reference_limit"
        return remaining

    def call(self, payload):
        reply = super().call(payload)
        if reply.http_status in (401, 403):
            self.halt = "authentication_required"
        return reply


def gateway_counts(directory):
    inputs = outputs = 0
    for line in (directory / "captures.jsonl").read_text(encoding="utf-8").splitlines():
        cap = parse_json(line)
        if not cap["complete"] or cap["output"] is None:
            return None, None
        try:
            body = parse_json(cap["output"])
            usage = native_usage(body)
            if usage is None:
                return None, None
            reported = body.get("usage", {}).get("total_tokens")
            if reported is not None and reported != usage["input_tokens"] + usage["output_tokens"]:
                return None, None
        except (ValueError, TypeError, AttributeError):
            return None, None
        inputs += usage["input_tokens"]
        outputs += usage["output_tokens"]
    return inputs, outputs


def snapshot(output, reference, candidate):
    extra = [Path(__file__), PLUGIN / "evals/run_parity.py", PLUGIN / "evals/run_repository.py",
             PLUGIN / "evals/source_read_adapter.py", PLUGIN / "evals/parity_cases.py",
             PLUGIN / "evals/parity-cases.json", PLUGIN / "evals/fresh-coding-cases.json",
             *sorted((PLUGIN / "evals").glob("fresh_coding*.py")),
             *sorted((PLUGIN / "evals/refinement").glob("*.py")),
             *sorted((PLUGIN / "evals/competitors").glob("*.py"))]
    original = {str(path.relative_to(PLUGIN)): sha(path) for path in extra}
    quality_snapshot(output)
    destination = output / "source/token-master-plugin"
    sources = parse_json((output / "source-manifest.json").read_text(encoding="utf-8"))
    for source in extra:
        name = str(source.relative_to(PLUGIN))
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        if sha(target) != original[name] or sha(source) != original[name]:
            raise ValueError("source changed while freezing")
    sources.update(original)
    write(output / "source-manifest.json", sources)
    for source, name in ((reference / "manifest.json", "reference-manifest.json"),
                         (reference / "ponytail.json", "ponytail.json"),
                         (candidate, "candidate.json")):
        (output / name).write_bytes(source.read_bytes())
    return destination / "evals/run_controlled_scorecard.py"


def _sandbox_preflight(directory):
    from quality.sandbox import run_program
    result = run_program({"probe.py": "def check():\n    return 17\n"},
                         "from probe import check\nassert check() == 17\nprint('ISOLATED_READY')\n")
    write(directory / "sandbox-preflight.json", result)
    boundary = result.get("boundary", {})
    return (result.get("exit_code") == 0 and "ISOLATED_READY" in result.get("stdout", "")
            and boundary.get("ready") is True and boundary.get("scoped_cleanup") is True)


def plan_suite(output, name, corpus):
    """Persist every planned task before either suite can send a request."""
    directory = output / name
    directory.mkdir()
    cases = corpus.load_cases()
    expected_cases = 6 if name == "six-task" else 4
    if len(cases) != expected_cases:
        raise ValueError("predeclared suite size changed")
    schedule = make_schedule([case.id for case in cases])
    write(directory / "manifest.json", {
        "protocol": PROTOCOL, "suite": name, "schedule": schedule, "order_seeds": SEEDS,
        "tasks": [asdict(case) | {"identity": case.identity} for case in cases],
        "oracle": corpus.ORACLE_ID, "common_manifest_sha256": sha(output / "manifest.json"),
        "sampling": "exposed six-task diagnostic" if name == "six-task"
                    else "independently authored fresh coding challenges, not population sampling",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    })
    write(directory / "summary.json", summarize([], schedule) | {"halt": "not_started"})
    return {"name": name, "corpus": corpus, "cases": cases, "schedule": schedule,
            "directory": directory}


def interrupted_row(run_dir, repeat, case_id, arm_name, elapsed):
    """Retain submitted/possibly submitted calls even if no result was written."""
    pending, captured, read_errors = [], {}, []
    for filename in ("invocations.jsonl", "captures.jsonl"):
        path = run_dir / filename
        if not path.exists():
            continue
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            try:
                record = parse_json(line)
                if filename == "invocations.jsonl" and record.get("state") == "pending":
                    pending.append(record["call_id"])
                elif filename == "captures.jsonl":
                    if record["call_id"] in captured:
                        raise ValueError("duplicate capture")
                    captured[record["call_id"]] = record
            except (ValueError, TypeError, KeyError):
                read_errors.append({"file": filename, "line": index + 1})
    submitted = {call for call in pending if call not in captured
                 or captured[call].get("input") is not None
                 or captured[call].get("reason") not in runner._NO_SUBMISSION}
    submitted.update(call for call, cap in captured.items() if cap.get("input") is not None
                     or cap.get("reason") not in runner._NO_SUBMISSION)
    known = 0
    for cap in captured.values():
        if cap.get("complete") and cap.get("input") is not None and cap.get("output") is not None:
            try:
                known += tokens.count_tokens(cap["input"]) + tokens.count_tokens(cap["output"])
            except Exception:
                read_errors.append({"file": "captures.jsonl", "reason": "reference_recount_failed"})
    row = {
        "repeat": repeat, "case": case_id, "arm": arm_name, "correct": None,
        "quality_status": "interrupted", "failure": "interrupted_attempt",
        "calls": len(submitted), "primary_accounting_complete": False,
        "comparator_complete": False, "primary_reference_tokens": None,
        "known_primary_reference_tokens": known, "bridge_reported_tokens": None,
        "gateway_input_tokens": None, "gateway_output_tokens": None,
        "all_in_case_seconds": elapsed, "original_retrievals": 0,
        "transformed_requests": 0, "run_directory": str(run_dir),
        "possibly_submitted_call_ids": sorted(submitted),
        "unreturned_call_ids": sorted(submitted - captured.keys()),
        "receipt_read_errors": read_errors,
        "recovery_and_transform_counts_unknown": True,
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    write(run_dir / "interrupted-attempt.json", row)
    return row


def run_planned_suites(plans, run_one):
    """An early halt leaves the other suite explicitly planned and unstarted."""
    summaries = {p["name"]: summarize([], p["schedule"]) | {"halt": "not_started"}
                 for p in plans}
    halted = None
    for plan in plans:
        if halted is not None:
            result = summaries[plan["name"]] | {"halt": "not_started_after:" + halted}
            write(plan["directory"] / "summary.json", result)
        else:
            result = run_one(plan)
            if not result["complete"]:
                halted = plan["name"]
        summaries[plan["name"]] = result
    return summaries


def _run_suite(output, plan, arms, reference, ponytail):
    name, corpus, cases = plan["name"], plan["corpus"], plan["cases"]
    directory, schedule = plan["directory"], plan["schedule"]
    rows: list[dict[str, Any]] = []
    if name == "fresh-coding" and not _sandbox_preflight(directory):
        final = summarize(rows, schedule) | {"halt": "sandbox_preflight_failed"}
        write(directory / "summary.json", final)
        return final
    from quality.sandbox import sandbox_runner
    runner.grade = corpus.grade
    client = ControlledBudget(ResponsesTransport(
        reference["base_url"], reference["model"], allow_network=True,
        max_output_tokens=4096, timeout=90, max_response_bytes=524288),
        directory, len(schedule), 3_500_000 if name == "six-task" else 2_500_000)
    warm = client.call({"input": [{"role": "user", "content": "Return exactly READY."}]})
    write(directory / "primary-preflight.json",
          {k: v for k, v in asdict(warm).items() if k != "body"})
    if not warm.ok:
        final = summarize(rows, schedule) | {"halt": "model_preflight:" + warm.reason,
                "primary_attempts_including_readiness": client.calls,
                "known_primary_reference_tokens_including_readiness": client.known_tokens}
        write(directory / "summary.json", final)
        return final

    def execute_tool(root, store, tool, arguments, program_runner=None, *, tool_call_id):
        if tool == "fetch_artifact":
            return runner._execute(root, store, "read_file", arguments, program_runner)
        if tool == "headroom_retrieve":
            return json.dumps(absent_headroom_message())
        return runner._execute(root, store, tool, arguments, program_runner)

    for repeat, case_id, arm_name in schedule:
        client.check_limits()
        if client.halt:
            break
        case = next(case for case in cases if case.id == case_id)
        arm = next(arm for arm in arms if arm.name == arm_name)
        run_dir = directory / "runs" / f"r{repeat}-{case_id}-{arm_name}"
        started = time.monotonic()
        try:
            with executor_source_reads() as observed:
                result = runner.run_case(
                    case, arm, run_dir, client, max_calls=10, tool_executor=execute_tool,
                    system_suffix=ponytail["instructions"] if arm_name == "ponytail" else "",
                    persist_view_history=False, harness_id=PROTOCOL,
                    sandbox_runner=sandbox_runner if name == "fresh-coding" else None)
            write(run_dir / "source-read-info.json", [x.to_dict() for x in observed.values()])
            counted = recount(result, run_dir)
            incoming, outgoing = gateway_counts(run_dir)
            counted["bridge_reported_tokens"] = (incoming + outgoing
                                                  if incoming is not None else None)
            row = {
                "repeat": repeat, "case": case_id, "arm": arm_name,
                "correct": result["grade"]["success"], "failure": result["failure"],
                "quality_status": result["grade"]["status"],
                **counted, "comparator_complete": True,
                "gateway_input_tokens": incoming, "gateway_output_tokens": outgoing,
                "all_in_case_seconds": time.monotonic() - started,
                "model_output_checks": result["grade"].get("assertions", {}),
                "original_retrievals": sum(e["name"] == "retrieve_original" for e in result["events"]),
                "transformed_requests": len(result["views"]),
                "run_directory": str(run_dir.relative_to(output)),
            }
            rows.append(row)
        except Exception as error:
            rows.append(interrupted_row(
                run_dir, repeat, case_id, arm_name, time.monotonic() - started))
            write(directory / "execution-error.json", {
                "repeat": repeat, "case": case_id, "arm": arm_name,
                "error_type": type(error).__name__, "run_directory": str(run_dir)})
            client.halt = "execution_error:" + type(error).__name__
            break
        write(directory / "summary.json", summarize(rows, schedule) | {
            "halt": client.halt, "primary_attempts_including_readiness": client.calls,
            "known_primary_reference_tokens_including_readiness": client.known_tokens})
        print(name, repeat, case_id, arm_name, "PASS" if row["correct"] else "FAIL",
              "calls", row["calls"], "gateway_tokens", row["bridge_reported_tokens"], flush=True)
        if type(row["correct"]) is not bool:
            client.halt = "oracle_unavailable"
            break
        if not result["regime_valid"]:
            client.halt = result["failure"] or "invalid_regime"
            break
    final = summarize(rows, schedule) | {
        "halt": client.halt, "primary_attempts_including_readiness": client.calls,
        "known_primary_reference_tokens_including_readiness": client.known_tokens,
        "execution_seconds": time.monotonic() - client.start}
    final["complete"] = final["complete"] and client.halt is None
    write(directory / "summary.json", final)
    return final


def execute(args):
    import parity_cases
    import fresh_coding_cases
    output = args.output.resolve()
    Path(__file__).resolve().relative_to(output / "source")
    if (output / "manifest.json").exists():
        raise ValueError("a recorded batch is never overwritten or selectively replayed")
    sources = parse_json((output / "source-manifest.json").read_text(encoding="utf-8"))
    if any(sha(PLUGIN / name) != value for name, value in sources.items()):
        raise ValueError("frozen source mismatch")
    reference = parse_json((output / "reference-manifest.json").read_text(encoding="utf-8"))
    ponytail = parse_json((output / "ponytail.json").read_text(encoding="utf-8"))
    if (ponytail["source_commit"] != PONYTAIL_COMMIT or ponytail["mode"] != "full"
            or ponytail["fallback_used"] is not False
            or hashlib.sha256(ponytail["instructions"].encode()).hexdigest() != PONYTAIL_INSTRUCTIONS):
        raise ValueError("pinned Ponytail export mismatch")
    old = RequestPolicy(version="request-policy-v2", enabled=True, min_tool_chars=512)
    candidate = RequestPolicy.from_json((output / "candidate.json").read_text(encoding="utf-8"))
    if candidate not in policy_neighbors(old) or candidate.keep_recent_tool_results != 2:
        raise ValueError("the already-selected candidate changed")
    difference = {key for key, value in candidate.to_dict().items() if value != old.to_dict()[key]}
    if difference != {"keep_recent_tool_results"}:
        raise ValueError("candidate must change only recent-result retention")
    runner.BASE_INSTRUCTIONS = reference["controls"]["base_instructions"]
    runner.TOOLS = clarify_recovery_tools(reference["controls"]["common_tools"])
    arms = [ControlledArm(
        name, scope=name.startswith("tokenmaster"), views=name.startswith("tokenmaster"),
        policy_json=(candidate if name == "tokenmaster_updated" else old if name == "tokenmaster_old"
                     else RequestPolicy(version="request-policy-v2", enabled=False)).to_json(),
        artifact_identity=digest({"sources": sources, "ponytail": PONYTAIL_INSTRUCTIONS
                                 if name == "ponytail" else None}))
        for name in ARMS]
    write(output / "manifest.json", {
        "protocol": PROTOCOL, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": reference["model"], "base_url": reference["base_url"],
        "reference_manifest_sha256": sha(output / "reference-manifest.json"),
        "candidate_sha256": sha(output / "candidate.json"),
        "frozen_source_identity": digest(sources), "tokenizer": tokens.backend_info(),
        "arms": [asdict(arm) | {"identity": arm.identity} for arm in arms],
        "controls": {"max_calls_per_task": 10, "repetitions": 3, "order_seeds": SEEDS,
                     "max_output_tokens": 4096, "reasoning": "low", "retries": 0,
                     "socket_timeout_seconds": 90, "call_hard_deadline_seconds": 120,
                     "per_suite_seconds": 3600, "six_task_reference_limit": 3_500_000,
                     "fresh_coding_reference_limit": 2_500_000,
                     "max_attempts_six_task_including_readiness": 721,
                     "max_attempts_fresh_coding_including_readiness": 481,
                     "persist_transformed_client_history": False,
                     "common_tools": runner.TOOLS, "base_instructions": runner.BASE_INSTRUCTIONS,
                     "recovery_guidance": "namespaced-v1"},
        "decision": "Complete known usage; no paired quality loss; all candidate checks pass and "
                    "less gateway usage in every repeat => better. Paired quality loss, or equal "
                    "quality and consistently more usage => worse. Otherwise inconclusive. "
                    "Suite-descriptive only, never a population or promotion certificate.",
        "jev": False, "policy_search": False, "policy_promoted": False,
        "normal_profiles_changed": False, "weights_modified": False,
        "fresh_corpus_frozen_before_any_study_calls": True,
    })
    plans = [plan_suite(output, name, corpus) for name, corpus in
             (("six-task", parity_cases), ("fresh-coding", fresh_coding_cases))]
    summaries = run_planned_suites(
        plans, lambda plan: _run_suite(output, plan, arms, reference, ponytail))
    if any(sha(PLUGIN / name) != value for name, value in sources.items()):
        raise ValueError("frozen implementation changed during the batch")
    final = {"suites": summaries, "complete": len(summaries) == 2 and all(
             s["complete"] for s in summaries.values()), "policy_promoted": False,
             "statistical_certificate": None, "normal_profiles_changed": False}
    write(output / "scorecard.json", final)
    print(json.dumps({name: s["comparisons"] for name, s in summaries.items()}, indent=2), flush=True)
    return 0 if final["complete"] else 3


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-study", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--frozen", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.allow_network:
        parser.error("--allow-network is required; no model calls made")
    if args.frozen:
        return execute(args)
    output = args.output.resolve()
    entry = snapshot(output, args.reference_study.resolve(), args.candidate.resolve())
    command = [sys.executable, "-B", str(entry), "--output", str(output),
               "--reference-study", str(args.reference_study.resolve()),
               "--candidate", str(output / "candidate.json"), "--allow-network", "--frozen"]
    return subprocess.run(command, cwd=entry.parent, env=child_environment(output),
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
