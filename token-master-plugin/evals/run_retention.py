"""Fresh paired retention-neighbor trial; never automatically promotes a policy."""
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

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "skills/token-master"))
from brainspace import tokens  # noqa: E402
from brainspace.request_policy import RequestPolicy, policy_neighbors  # noqa: E402
from quality import runner  # noqa: E402
from quality.cases import digest  # noqa: E402
from quality.responses import ResponsesTransport, parse_json  # noqa: E402
from quality.recovery_guidance import clarify_recovery_tools, absent_headroom_message  # noqa: E402
from run_parity import recount, summarize, snapshot as parity_snapshot  # noqa: E402
from run_repository import BudgetClient  # noqa: E402
from run_quality import child_environment  # noqa: E402
from source_read_adapter import SourceAwareArm, executor_source_reads  # noqa: E402
import retention_cases  # noqa: E402


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class PolicyArm(SourceAwareArm):
    policy_json: str = ""

    @property
    def policy(self):
        return RequestPolicy.from_json(self.policy_json)


class RetentionBudget(BudgetClient):
    def check_limits(self):
        remaining = 1800 - (time.monotonic() - self.start)
        if self.halt is None:
            if self.calls >= 81:
                self.halt = "call_limit"
            elif remaining <= 0:
                self.halt = "wall_time_limit"
            elif self.known_tokens >= 1_000_000:
                self.halt = "reference_limit"
        return remaining


def execute(args):
    output = args.output.resolve()
    Path(__file__).resolve().relative_to(output / "source")
    if (output / "manifest.json").exists():
        raise ValueError("a held-out study is never replayed in place")
    sources = parse_json((output / "source-manifest.json").read_text(encoding="utf-8"))
    if any(sha(PLUGIN / name) != expected for name, expected in sources.items()):
        raise ValueError("frozen source mismatch")
    reference = parse_json((output / "reference-manifest.json").read_text(encoding="utf-8"))
    candidate = RequestPolicy.from_json((output / "candidate.json").read_text(encoding="utf-8"))
    incumbent = RequestPolicy(version="request-policy-v2", enabled=True, min_tool_chars=512)
    if candidate not in policy_neighbors(incumbent):
        raise ValueError("candidate is not a bounded local neighbor")
    corpus = retention_cases
    if args.replication:
        import recovery_replication_cases
        corpus = recovery_replication_cases
    cases = corpus.load_cases()
    if len(cases) != 4:
        raise ValueError("the planned four-task holdout changed")
    if args.mechanism_case:
        cases = [case for case in cases if case.id == args.mechanism_case]
        if len(cases) != 1:
            raise ValueError("unknown exposed mechanism case")
    clarified = args.replication or bool(args.mechanism_case)
    if {case.id for case in cases} & {case["id"] for case in reference["tasks"]}:
        raise ValueError("search tasks cannot be used as confirmation")
    runner.BASE_INSTRUCTIONS = reference["controls"]["base_instructions"]
    runner.TOOLS = (clarify_recovery_tools(reference["controls"]["common_tools"])
                    if clarified else reference["controls"]["common_tools"])
    runner.grade = corpus.grade
    arms = [PolicyArm(name, scope=True, views=True, policy_json=policy.to_json())
            for name, policy in (("incumbent", incumbent), ("candidate", candidate))]
    schedule = [(case.id, arm.name) for case in cases for arm in arms]
    random.Random(args.order_seed).shuffle(schedule)
    manifest = {
        "protocol": ("common-original-history-retention-mechanism-v1" if args.mechanism_case else
                     "common-original-history-retention-replication-v1" if args.replication
                     else "common-original-history-retention-v1"),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": reference["model"], "base_url": reference["base_url"],
        "reference_manifest_sha256": sha(output / "reference-manifest.json"),
        "candidate_sha256": sha(output / "candidate.json"),
        "tasks": [asdict(case) | {"identity": case.identity} for case in cases],
        "arms": [asdict(arm) | {"identity": arm.identity} for arm in arms],
        "schedule": schedule,
        "order_seed": args.order_seed,
        "exposed_mechanism_case": args.mechanism_case,
        "oracle": corpus.ORACLE_ID,
        "controls": {
            "max_calls_per_task": 10, "max_primary_attempts_including_readiness": 81,
            "seconds": 1800, "reference_stopping_threshold": 1_000_000,
            "max_output_tokens": 4096, "socket_timeout": 90, "hard_deadline": 120,
            "reasoning": "low", "retries": 0, "persist_transformed_client_history": False,
            "base_instructions": runner.BASE_INSTRUCTIONS, "common_tools": runner.TOOLS,
            "task_scope_in_both_arms": True,
            "recovery_guidance": "namespaced-v1" if clarified else "as-recorded",
            "planned_max_primary_attempts": len(schedule) * 10 + 1,
        },
        "candidate_selection": "Deterministic first activating neighbor after Jev abstention; not a Jev recommendation.",
        "sampling": ("Repeated already-exposed active case, mechanism check only; NOT fresh confirmation."
                     if args.mechanism_case else
                     "Four independently prepared new replication questions with declared source overlap; "
                     "not an IID population certificate." if args.replication else
                     "Four independently prepared, source-disjoint held-out challenges, not an IID population certificate."),
        "model_calls_used_to_choose_holdout_answers": 0,
        "tokenizer": tokens.backend_info(), "frozen_source_identity": digest(sources),
        "policy_promoted": False, "normal_profiles_changed": False, "weights_modified": False,
    }
    write(output / "manifest.json", manifest)
    client = RetentionBudget(ResponsesTransport(
        reference["base_url"], reference["model"], allow_network=True,
        max_output_tokens=4096, timeout=90, max_response_bytes=524288), output)
    warm = client.call({"input": [{"role": "user", "content": "Return exactly READY."}]})
    write(output / "primary-preflight.json", {key: value for key, value in asdict(warm).items() if key != "body"})
    if not warm.ok:
        write(output / "summary.json", summarize([], schedule) | {"halt": warm.reason})
        return 2

    def execute_tool(root, store, tool, arguments, program_runner=None, *, tool_call_id):
        if tool == "fetch_artifact":
            return runner._execute(root, store, "read_file", arguments, program_runner)
        if tool == "headroom_retrieve":
            return json.dumps(absent_headroom_message() if clarified else
                              {"error": "No Headroom reference exists in this arm."})
        return runner._execute(root, store, tool, arguments, program_runner)

    rows = []
    for case_id, arm_name in schedule:
        client.check_limits()
        if client.halt:
            break
        case = next(case for case in cases if case.id == case_id)
        arm = next(arm for arm in arms if arm.name == arm_name)
        directory = output / "runs" / (case_id + "-" + arm_name)
        started = time.monotonic()
        with executor_source_reads() as observed:
            result = runner.run_case(
                case, arm, directory, client, max_calls=10, tool_executor=execute_tool,
                persist_view_history=False, harness_id=manifest["protocol"])
        write(directory / "source-read-info.json", [item.to_dict() for item in observed.values()])
        counted = recount(result, directory)
        regrade = corpus.grade(case, Path(result["workspace"]), result["answer"], result["events"])
        if result["failure"] is None and regrade != result["grade"]:
            raise ValueError("held-out independent regrade mismatch")
        row = {"case": case_id, "arm": arm_name, "correct": result["grade"]["success"],
               "failure": result["failure"], **counted, "comparator_complete": True,
               "all_in_case_seconds": time.monotonic() - started,
               "model_output_checks": regrade["assertions"],
               "original_retrievals": sum(event["name"] == "retrieve_original" for event in result["events"])}
        rows.append(row)
        write(output / "summary.json", summarize(rows, schedule) | {
            "primary_attempts_including_readiness": client.calls, "halt": client.halt})
        print(case_id, arm_name, "PASS" if row["correct"] else "FAIL",
              row["calls"], row["primary_reference_tokens"], flush=True)
        if not result["regime_valid"]:
            client.halt = result["failure"] or "invalid_task_regime"
            break
    if any(sha(PLUGIN / name) != expected for name, expected in sources.items()):
        raise ValueError("frozen source changed")
    result = summarize(rows, schedule) | {
        "primary_attempts_including_readiness": client.calls, "halt": client.halt,
        "known_primary_reference_tokens_including_readiness": client.known_tokens,
        "execution_seconds": time.monotonic() - client.start,
    }
    result["complete"] = result["complete"] and client.halt is None
    write(output / "summary.json", result)
    print(json.dumps(result["by_arm"], indent=2), flush=True)
    return 0 if result["complete"] else 3


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-study", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--replication", action="store_true",
                        help="Use the fresh replication corpus and shared namespaced recovery descriptions.")
    parser.add_argument("--mechanism-case",
                        help="Test one already-exposed retention case with clarified recovery; not a holdout.")
    parser.add_argument("--order-seed", type=int, default=20261009)
    parser.add_argument("--frozen", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.allow_network:
        parser.error("--allow-network is required; no model call was made")
    if args.replication and args.mechanism_case:
        parser.error("replication and exposed mechanism modes are distinct")
    if not 0 <= args.order_seed < 2**32:
        parser.error("--order-seed must be an unsigned 32-bit integer")
    if args.frozen:
        return execute(args)
    output, reference = args.output.resolve(), args.reference_study.resolve()
    extra = [Path(__file__), PLUGIN / "evals/retention_cases.py", PLUGIN / "evals/retention-cases.json"]
    if args.replication:
        extra += [PLUGIN / "evals/recovery_replication_cases.py",
                  PLUGIN / "evals/recovery-replication-cases.json"]
    hashes = {str(path.relative_to(PLUGIN)): sha(path) for path in extra}
    parity_snapshot(output, reference / "ponytail.json", reference / "headroom-assets.json")
    destination = output / "source/token-master-plugin"
    sources = parse_json((output / "source-manifest.json").read_text(encoding="utf-8"))
    for source in extra:
        relative = str(source.relative_to(PLUGIN))
        target = destination / relative
        target.write_bytes(source.read_bytes())
        if sha(source) != hashes[relative] or sha(target) != hashes[relative]:
            raise ValueError("holdout changed while freezing")
    sources.update(hashes)
    write(output / "source-manifest.json", sources)
    (output / "reference-manifest.json").write_bytes((reference / "manifest.json").read_bytes())
    (output / "candidate.json").write_bytes(args.candidate.read_bytes())
    command = [
        sys.executable, "-B", str(destination / "evals/run_retention.py"),
        "--output", str(output), "--reference-study", str(reference),
        "--candidate", str(output / "candidate.json"), "--allow-network", "--frozen",
        "--order-seed", str(args.order_seed),
    ]
    if args.replication:
        command.append("--replication")
    if args.mechanism_case:
        command += ["--mechanism-case", args.mechanism_case]
    return subprocess.run(command, env=child_environment(output), cwd=destination / "evals",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
