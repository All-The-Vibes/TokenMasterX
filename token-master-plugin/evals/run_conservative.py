"""One frozen baseline/V3 regression run plus explicit repeated-read probes.

No policy search, selective retries, coding sandbox, or automatic promotion.
The four probes reuse two existing questions and are not independent workloads.
"""
import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import subprocess
import sys
import time

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "skills/token-master"))
from brainspace import tokens  # noqa: E402
from quality import runner  # noqa: E402
from quality.cases import digest  # noqa: E402
from quality.recovery_guidance import absent_headroom_message  # noqa: E402
from quality.responses import ResponsesTransport, parse_json  # noqa: E402
from run_controlled_scorecard import (  # noqa: E402
    ControlledBudget, gateway_counts, interrupted_row, summarize, write, sha,
)
from run_parity import recount  # noqa: E402
from run_quality import child_environment, snapshot as quality_snapshot  # noqa: E402
from source_read_adapter import ConservativeArm, executor_source_reads  # noqa: E402
import parity_cases  # noqa: E402

PROTOCOL = "conservative-exact-reuse-check-v1"
ARM_NAMES = ("baseline", "tokenmaster_conservative")
# The first two are negative controls: literal recovery-marker syntax is
# protected by V3. The last two repeat eligible source. Nothing is padded.
PROBES = (
    ("repeat_recovery_entry", "parity_recovery_trace", (0, 0, 1), False),
    ("repeat_recovery_store", "parity_recovery_trace", (1, 1, 0), False),
    ("repeat_rust_hook", "parity_rust_dispatch_trace", (0, 0, 1, 2), True),
    ("repeat_rust_compressor", "parity_rust_dispatch_trace", (2, 2, 0, 1), True),
)


def probe_cases():
    originals = {case.id: case for case in parity_cases.load_cases()}
    result = []
    for name, parent, indices, _ in PROBES:
        original = originals[parent]
        order = [original.fixtures[i][0] for i in indices]
        prompt = (
            "This is a controlled repeated-read check. Before answering, call read_file "
            "in exactly this source order, including every deliberate repetition: "
            + json.dumps(order)
            + ". Then answer the following source question. Do not edit or run code.\n"
            + original.prompt
        )
        result.append(replace(original, id=name, version=PROTOCOL, prompt=prompt))
    return result


def grade(case, workspace, answer, events, *, sandbox_runner=None):
    spec = next((row for row in PROBES if row[0] == case.id), None)
    if spec is None:
        return parity_cases.grade(case, workspace, answer, events)
    trusted = next(c for c in probe_cases() if c.id == case.id)
    parent = next(c for c in parity_cases.load_cases() if c.id == spec[1])
    verdict = parity_cases.grade(parent, workspace, answer, events)
    expected = [parent.fixtures[i][0] for i in spec[2]]
    reads = [event["arguments"]["path"] for event in events
             if type(event) is dict and event.get("name") == "read_file"
             and type(event.get("arguments")) is dict and "path" in event["arguments"]]
    checks = {
        "derived_case_identity": type(case) is type(trusted) and case.identity == trusted.identity,
        "deliberate_read_order": reads[:len(expected)] == expected,
    }
    verdict["assertions"].update(checks)
    verdict["checks"].extend(key for key, passed in checks.items() if not passed)
    verdict["success"] = verdict["success"] and all(checks.values())
    verdict["status"] = "passed" if verdict["success"] else "failed"
    verdict["oracle"] = PROTOCOL + ":" + parity_cases.ORACLE_ID
    verdict["parent_case_identity"] = parent.identity
    verdict["derived_case_identity"] = trusted.identity
    verdict["evidence_digest"] = digest(verdict)
    return verdict


def make_schedule(cases, seed):
    """Adjacent pairs, counterbalanced arm order, one pass fixed before calls."""
    ids = [case.id for case in cases]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("invalid case inventory")
    random.Random(seed).shuffle(ids)
    return [(0, case_id, name) for i, case_id in enumerate(ids)
            for name in (ARM_NAMES if i % 2 == 0 else ARM_NAMES[::-1])]


def comparison(summary):
    baseline, candidate = (summary["by_arm"][name] for name in ARM_NAMES)
    complete = summary["complete"] and all(
        arm["bridge_reported_tokens"] is not None for arm in (baseline, candidate))
    result = {
        "usage_complete": complete, "all_tasks_correct": summary["all_tasks_correct"],
        "gateway_token_reduction_percent": None, "gateway_tokens_avoided": None,
        "additional_model_requests": candidate["primary_calls"] - baseline["primary_calls"]
        if complete else None,
        "statistical_certificate": None, "scope": "this single matched diagnostic only",
    }
    if complete:
        old, new = (arm["bridge_reported_tokens"] for arm in (baseline, candidate))
        result["gateway_tokens_avoided"] = old - new
        result["gateway_token_reduction_percent"] = 100 * (old - new) / old if old else None
    return result


def event_counts(events):
    """Optional read statistics cannot erase a malformed attempt's known usage."""
    reads, malformed, recoveries, originals = [], 0, 0, 0
    for event in events:
        if type(event) is not dict:
            continue
        name, args = event.get("name"), event.get("arguments")
        originals += name == "retrieve_original"
        recoveries += name in ("retrieve_original", "search_original", "headroom_retrieve")
        if name in ("read_file", "fetch_artifact"):
            if type(args) is dict and type(args.get("path")) is str:
                reads.append((name, args["path"]))
            else:
                malformed += 1
    return {
        "original_retrievals": originals, "recovery_tool_calls": recoveries,
        "source_read_attempts": len(reads) + malformed,
        "malformed_read_attempts": malformed,
        "repeated_source_reads": len(reads) - len(set(reads)),
    }


def freeze(output, reference):
    extra = [
        Path(__file__), PLUGIN / "evals/run_controlled_scorecard.py",
        PLUGIN / "evals/run_parity.py", PLUGIN / "evals/run_repository.py",
        PLUGIN / "evals/source_read_adapter.py", PLUGIN / "evals/parity_cases.py",
        PLUGIN / "evals/parity-cases.json", PLUGIN / "skills/token-master/brainspace_tools.py",
        *sorted((PLUGIN / "evals/refinement").glob("*.py")),
        *sorted((PLUGIN / "evals/competitors").glob("*.py")),
    ]
    hashes = {str(path.relative_to(PLUGIN)): sha(path) for path in extra}
    quality_snapshot(output)
    destination = output / "source/token-master-plugin"
    sources = parse_json((output / "source-manifest.json").read_text(encoding="utf-8"))
    for source in extra:
        name = str(source.relative_to(PLUGIN))
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        if sha(target) != hashes[name] or sha(source) != hashes[name]:
            raise ValueError("source changed while freezing")
    sources.update(hashes)
    write(output / "source-manifest.json", sources)
    (output / "reference-manifest.json").write_bytes((reference / "manifest.json").read_bytes())
    return destination / "evals/run_conservative.py"


def execute(args):
    output = args.output.resolve()
    Path(__file__).resolve().relative_to(output / "source")
    if (output / "manifest.json").exists():
        raise ValueError("recorded runs cannot be overwritten")
    sources = parse_json((output / "source-manifest.json").read_text(encoding="utf-8"))
    if any(sha(PLUGIN / name) != value for name, value in sources.items()):
        raise ValueError("frozen source mismatch")
    reference = parse_json((output / "reference-manifest.json").read_text(encoding="utf-8"))
    runner.BASE_INSTRUCTIONS = reference["controls"]["base_instructions"]
    runner.TOOLS = reference["controls"]["common_tools"]
    runner.grade = grade
    arms = {name: ConservativeArm(name, views=name != "baseline") for name in ARM_NAMES}
    suites = {"six-task": parity_cases.load_cases(), "repeated-read-probes": probe_cases()}
    schedules = {name: make_schedule(cases, i) for i, (name, cases) in enumerate(suites.items())}
    planned = sum(len(schedule) for schedule in schedules.values())
    manifest = {
        "protocol": PROTOCOL, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": reference["model"], "base_url": reference["base_url"],
        "reference_manifest_sha256": sha(output / "reference-manifest.json"),
        "frozen_source_identity": digest(sources), "tokenizer": tokens.backend_info(),
        "arms": [asdict(arm) | {"identity": arm.identity, "policy": arm.policy.to_dict()}
                 for arm in arms.values()],
        "controls": {
            "base_instructions": runner.BASE_INSTRUCTIONS, "common_tools": runner.TOOLS,
            "max_calls_per_task": 10, "max_attempts_including_readiness": planned * 10 + 1,
            "repetitions": 1, "retries": 0, "max_output_tokens": 4096,
            "reasoning": "low", "socket_timeout_seconds": 90,
            "call_deadline_seconds": 120, "total_seconds": 3600,
            "reference_token_limit": 2_000_000, "persist_transformed_client_history": False,
            "task_mode_instructions_added": False,
        },
        "schedules": schedules,
        "cases": {name: [{"id": c.id, "identity": c.identity, "intent": c.intent,
                         "public_task": c.public_task()} for c in cases]
                  for name, cases in suites.items()},
        "probes": [{"id": name, "parent_case": parent, "fixture_order_indices": indices,
                    "expected_eligible_duplicate": eligible}
                   for name, parent, indices, eligible in PROBES],
        "sampling": "Six existing questions once, plus four deliberate probes from two of them.",
        "decision": "Report complete-task gateway input plus output, correctness, all requests "
                    "and recovery. No general savings inference from forced repeated reads. "
                    "A payload reduction alone is not a task-token saving.",
        "policy_promoted": False, "normal_profiles_changed": False,
        "weights_modified": False, "monetary_objective": False,
    }
    write(output / "manifest.json", manifest)
    rows: dict[str, list[dict]] = {name: [] for name in suites}
    for name in suites:
        (output / name).mkdir()
        write(output / name / "manifest.json", {
            "schedule": schedules[name], "common_manifest_sha256": sha(output / "manifest.json"),
            "cases": manifest["cases"][name]})

    client = ControlledBudget(ResponsesTransport(
        reference["base_url"], reference["model"], allow_network=True,
        max_output_tokens=4096, timeout=90, max_response_bytes=524288),
        output, planned, 2_000_000)

    def save():
        reports = {}
        for name in suites:
            report = summarize(rows[name], schedules[name])
            report["comparison"] = comparison(report)
            report["halt"] = client.halt
            write(output / name / "summary.json", report)
            reports[name] = report
        report = {
            "protocol": PROTOCOL, "suites": reports, "halt": client.halt,
            "complete": client.halt is None and all(
                r["complete"] and r["comparison"]["usage_complete"] for r in reports.values()),
            "primary_attempts_including_readiness": client.calls,
            "known_reference_tokens_including_readiness": client.known_tokens,
            "elapsed_seconds": time.monotonic() - client.start,
            "policy_promoted": False, "statistical_certificate": None,
        }
        write(output / "summary.json", report)
        return report

    warm = client.call({"input": [{"role": "user", "content": "Return exactly READY."}]})
    write(output / "primary-preflight.json", {k: v for k, v in asdict(warm).items() if k != "body"})
    if not warm.ok:
        client.halt = "model_preflight:" + warm.reason
        save()
        return 2

    def execute_tool(root, store, tool, arguments, program_runner=None, *, tool_call_id):
        if tool == "fetch_artifact":
            return runner._execute(root, store, "read_file", arguments, program_runner)
        if tool == "headroom_retrieve":
            return json.dumps(absent_headroom_message())
        return runner._execute(root, store, tool, arguments, program_runner)

    for suite, cases in suites.items():
        by_id = {case.id: case for case in cases}
        for repeat, case_id, arm_name in schedules[suite]:
            client.check_limits()
            if client.halt:
                break
            directory = output / suite / "runs" / (case_id + "-" + arm_name)
            started = time.monotonic()
            observed = {}
            try:
                def on_plan(before, plan):
                    runner.append_receipt(directory / "plan-audit.jsonl",
                                          {"before": before, "plan": asdict(plan)})

                with executor_source_reads(on_plan=on_plan) as observed:
                    result = runner.run_case(
                        by_id[case_id], arms[arm_name], directory, client, max_calls=10,
                        tool_executor=execute_tool, system_suffix="", persist_view_history=False,
                        harness_id=PROTOCOL,
                    )
                counted = recount(result, directory)
                incoming, outgoing = gateway_counts(directory)
                known_usage = incoming is not None and outgoing is not None
                counted["bridge_reported_tokens"] = incoming + outgoing if known_usage else None
                row = {
                    "repeat": repeat, "case": case_id, "arm": arm_name,
                    "correct": result["grade"]["success"], "failure": result["failure"],
                    "quality_status": result["grade"]["status"], **counted,
                    "comparator_complete": True, "gateway_input_tokens": incoming,
                    "gateway_output_tokens": outgoing,
                    "all_in_case_seconds": time.monotonic() - started,
                    **event_counts(result["events"]),
                    "transformed_requests": len(result["views"]),
                    "model_output_checks": result["grade"].get("assertions", {}),
                    "run_directory": str(directory.relative_to(output)),
                }
                rows[suite].append(row)
                print(suite, case_id, arm_name, "PASS" if row["correct"] else "FAIL",
                      "requests", row["calls"], "gateway_tokens", row["bridge_reported_tokens"],
                      "transformed", row["transformed_requests"], flush=True)
                if not result["regime_valid"]:
                    client.halt = result["failure"] or "invalid_regime"
            except Exception as error:
                rows[suite].append(interrupted_row(
                    directory, repeat, case_id, arm_name, time.monotonic() - started))
                write(output / "execution-error.json", {
                    "suite": suite, "case": case_id, "arm": arm_name,
                    "error_type": type(error).__name__})
                client.halt = "execution_error:" + type(error).__name__
            finally:
                if directory.exists():
                    write(directory / "source-read-info.json", [x.to_dict() for x in observed.values()])
            save()
        if client.halt:
            break
    if any(sha(PLUGIN / name) != value for name, value in sources.items()):
        client.halt = "frozen_source_changed"
    final = save()
    print(json.dumps({name: report["comparison"] for name, report in final["suites"].items()},
                     indent=2), flush=True)
    return 0 if final["complete"] else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-study", type=Path, required=True)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--execute-frozen", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.allow_network:
        parser.error("explicit --allow-network is required for the existing loopback gateway")
    if args.execute_frozen:
        return execute(args)
    output = args.output.resolve()
    entry = freeze(output, args.reference_study.resolve())
    environment = child_environment(output)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-B", str(entry), "--output", str(output),
         "--reference-study", str(args.reference_study.resolve()),
         "--allow-network", "--execute-frozen"],
        cwd=output, env=environment, check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
