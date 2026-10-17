"""Opt-in same-boundary, source-pinned comparator study; never a promotion certificate."""
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
from quality import runner  # noqa: E402
from quality.cases import digest  # noqa: E402
from quality.responses import ResponsesTransport, parse_json  # noqa: E402
from refinement.core import native_usage  # noqa: E402
from run_quality import child_environment, snapshot as quality_snapshot  # noqa: E402
from run_repository import BudgetClient  # noqa: E402
from source_read_adapter import SourceAwareArm, executor_source_reads  # noqa: E402
from competitors.headroom_container import HeadroomContainer, IMAGE_ID, COMMIT, MODEL_REVISION  # noqa: E402
import parity_cases  # noqa: E402

PONYTAIL_COMMIT = "c982cd411abb53323c4baa1baa3c2f020b8d0b08"
PONYTAIL_INSTRUCTIONS = "da4fb09cff2f6726691ce6591cebc38c95597d79da132e49c6fa2665c4e8a3ff"
HARNESSES = "common-original-history-responses-parity-v1"


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False), encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class ParityArm(SourceAwareArm):
    artifact_identity: str = ""


class ParityBudget(BudgetClient):
    """Same transport/journals, a separately predeclared whole-study allowance."""
    def check_limits(self):
        remaining = 3600 - (time.monotonic() - self.start)
        if self.halt is None:
            if self.calls >= 241:
                self.halt = "call_limit"
            elif remaining <= 0:
                self.halt = "wall_time_limit"
            elif self.known_tokens >= 2_000_000:
                self.halt = "reference_limit"
        return remaining


def recount(result, directory):
    """Recount complete visible primary bodies; unresolved calls stay unknown."""
    path = directory / "captures.jsonl"
    captures = [parse_json(line) for line in path.read_text(encoding="utf-8").splitlines()] \
        if path.exists() else []
    journal_path = directory / "invocations.jsonl"
    journal = [parse_json(line) for line in journal_path.read_text(encoding="utf-8").splitlines()] \
        if journal_path.exists() else []
    expected_journal = [{"call_id": capture["call_id"], "state": state}
                        for capture in captures for state in ("pending", "captured")]
    if journal != expected_journal:
        raise ValueError("primary invocation journal mismatch")
    ids = [capture["call_id"] for capture in captures]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate primary capture")
    records = {row["call_id"]: row for row in result["trace"]["calls"]}
    missing = {row["call_id"]: row for row in result["incomplete_calls"]}
    expected = list(result["trace"]["expected_call_ids"])
    observed = [capture["call_id"] for capture in captures
                if capture["input"] is not None or capture["reason"] not in runner._NO_SUBMISSION]
    if (len(records) != len(result["trace"]["calls"]) or len(missing) != len(result["incomplete_calls"])
            or len(expected) != len(set(expected)) or observed != expected
            or set(records) | set(missing) != set(expected) or set(records) & set(missing)):
        raise ValueError("primary inventory mismatch")
    reference_input = reference_output = 0
    native_input = native_output = 0
    for capture in captures:
        record = records.get(capture["call_id"])
        if record is None:
            continue
        if not capture["complete"] or capture["input"] is None or capture["output"] is None:
            raise ValueError("incomplete primary record")
        request = parse_json(capture["input"])
        if request.get("model") != result["model"]:
            raise ValueError("primary request model mismatch")
        incoming, outgoing = tokens.count_tokens(capture["input"]), tokens.count_tokens(capture["output"])
        if (incoming != record["reference_input_tokens"] or outgoing != record["reference_output_tokens"]
                or hashlib.sha256(capture["input"].encode()).hexdigest() != record["input_sha256"]
                or hashlib.sha256(capture["output"].encode()).hexdigest() != record["output_sha256"]):
            raise ValueError("primary count or digest mismatch")
        reference_input += incoming
        reference_output += outgoing
        try:
            body = parse_json(capture["output"])
        except (ValueError, TypeError):
            body = {}
        if type(body) is not dict:
            body = {}
        if capture["reason"] == "ok" and body.get("model") != result["model"]:
            raise ValueError("primary response model mismatch")
        usage = native_usage(body)
        if usage is None:
            native_input = native_output = None
        elif native_input is not None:
            native_input += usage["input_tokens"]
            native_output += usage["output_tokens"]
    complete = not missing and result["regime_valid"]
    known_reference = reference_input + reference_output
    if not missing and (result["totals"] is None
                        or result["totals"]["total_tokens"] != known_reference):
        raise ValueError("trace total mismatch")
    return {
        "calls": len(expected), "complete_primary_calls": len(records),
        "primary_accounting_complete": complete,
        "primary_reference_tokens": known_reference if complete else None,
        "known_primary_reference_tokens": known_reference,
        "reference_input_tokens": reference_input if complete else None,
        "reference_output_tokens": reference_output if complete else None,
        "bridge_reported_tokens": native_input + native_output
        if complete and native_input is not None else None,
        "incomplete_calls": list(missing.values()),
    }


def summarize(rows, schedule):
    expected = {tuple(item) for item in schedule}
    found = {(row["case"], row["arm"]) for row in rows}
    if not expected or len(expected) != len(schedule) or len(found) != len(rows) or not found <= expected:
        raise ValueError("invalid planned/observed inventory")
    by_arm = {}
    for arm in dict.fromkeys(item[1] for item in schedule):
        group = [row for row in rows if row["arm"] == arm]
        planned = sum(name == arm for _, name in schedule)
        complete = len(group) == planned and all(
            row["primary_accounting_complete"] and row["comparator_complete"] for row in group)
        by_arm[arm] = {
            "attempted_tasks": len(group), "planned_tasks": planned,
            "correct_tasks": sum(row["correct"] is True for row in group),
            "complete": complete,
            "primary_calls": sum(row["calls"] for row in group),
            "known_primary_reference_tokens": sum(row["known_primary_reference_tokens"] for row in group),
            "primary_reference_tokens": sum(row["primary_reference_tokens"] for row in group)
            if complete else None,
            "bridge_reported_tokens": sum(row["bridge_reported_tokens"] for row in group)
            if complete and all(row["bridge_reported_tokens"] is not None for row in group) else None,
            "observed_wall_seconds": sum(row["all_in_case_seconds"] for row in group),
        }
    return {
        "complete": found == expected and all(value["complete"] for value in by_arm.values()),
        "all_tasks_correct": found == expected and all(row["correct"] is True for row in rows),
        "expected_task_runs": len(schedule), "attempted_task_runs": len(rows),
        "missing_task_runs": [list(item) for item in sorted(expected - found)],
        "by_arm": by_arm, "runs": rows, "statistical_certificate": None,
        "policy_promoted": False, "monetary_objective": False,
        "scope": "Primary API-body reference usage. Local neural inference is separately observed, "
                 "not priced or asserted zero; native detector inference is not fully inventoried.",
    }


def snapshot(output, ponytail, assets):
    extra = [Path(__file__), PLUGIN / "evals/parity_cases.py", PLUGIN / "evals/parity-cases.json",
             PLUGIN / "evals/source_read_adapter.py", PLUGIN / "evals/run_repository.py",
             *sorted((PLUGIN / "evals/refinement").glob("*.py")),
             *sorted((PLUGIN / "evals/competitors").glob("*.py"))]
    original = {str(path.relative_to(PLUGIN)): sha(path) for path in extra}
    quality_snapshot(output)
    destination = output / "source/token-master-plugin"
    hashes = parse_json((output / "source-manifest.json").read_text())
    for source in extra:
        relative = str(source.relative_to(PLUGIN))
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        if sha(target) != original[relative] or sha(source) != original[relative]:
            raise ValueError("source changed while freezing")
    hashes.update(original)
    write(output / "source-manifest.json", hashes)
    (output / "ponytail.json").write_bytes(ponytail.read_bytes())
    (output / "headroom-assets.json").write_bytes(assets.read_bytes())
    (output / "docker-config").mkdir()
    (output / "docker-config/config.json").write_text("{}\n", encoding="utf-8")
    return destination / "evals/run_parity.py"


def execute(args):
    output = args.output.resolve()
    Path(__file__).resolve().relative_to(output / "source")
    if (output / "manifest.json").exists():
        raise ValueError("a study is never replayed in place")
    sources = parse_json((output / "source-manifest.json").read_text())
    if any(sha(PLUGIN / name) != expected for name, expected in sources.items()):
        raise ValueError("frozen source mismatch")
    ponytail = parse_json((output / "ponytail.json").read_text(encoding="utf-8"))
    if (ponytail["source_commit"] != PONYTAIL_COMMIT or ponytail["mode"] != "full"
            or ponytail["fallback_used"] is not False
            or hashlib.sha256(ponytail["instructions"].encode()).hexdigest() != PONYTAIL_INSTRUCTIONS):
        raise ValueError("pinned Ponytail export mismatch")
    cases = parity_cases.load_cases()
    runner.grade = parity_cases.grade
    runner.BASE_INSTRUCTIONS = runner.BASE_INSTRUCTIONS.replace(
        "supplied synthetic workspace", "isolated source-pinned repository snapshot")
    runner.BASE_INSTRUCTIONS += (
        " fetch_artifact reads a repository document as exact text. "
        "headroom_retrieve resolves its matching compressed-content hash. "
        "Native recovery/document tools are permitted; no shell or Python execution is available."
    )
    runner.TOOLS = [tool for tool in runner.TOOLS if tool["name"] != "run_python"]
    runner.TOOLS.append(runner._tool("fetch_artifact", {"path": {"type": "string"}},
                                    "Read a repository document as exact UTF-8 text; no network."))
    label = "parity-" + hashlib.sha256(str(output).encode()).hexdigest()[:16]

    def new_worker(directory):
        return HeadroomContainer(directory, cache=args.headroom_cache,
                                 assets=output / "headroom-assets.json",
                                 docker_config=output / "docker-config", label=label)

    preflight = new_worker(output / "headroom-preflight")
    try:
        ready = preflight.start()
        preflight.finish()
    finally:
        cleanup = preflight.close()
        if not cleanup.get("container_removed"):
            raise ValueError("comparator preflight cleanup is incomplete")
    definition = ready["ccr_tool"]["function"]
    # Common strict Responses representation of the official hash-only tool,
    # supplied to every arm so schema overhead cannot secretly favor one arm.
    runner.TOOLS.append(runner._tool(
        definition["name"], definition["parameters"]["properties"], definition["description"]))
    artifacts = {
        "baseline": digest({"common_tools": runner.TOOLS}),
        "tokenmaster": digest({"source": sources, "scope": True, "request_policy": "v2"}),
        "ponytail": digest({"commit": PONYTAIL_COMMIT, "instruction_sha256": PONYTAIL_INSTRUCTIONS}),
        "headroom": digest({"commit": COMMIT, "image": IMAGE_ID, "model_revision": MODEL_REVISION,
                            "assets_sha256": sha(output / "headroom-assets.json"),
                            "config": ready["config"], "worker_source": sources}),
    }
    arms = [ParityArm(name, scope=name == "tokenmaster", views=name == "tokenmaster",
                      artifact_identity=artifacts[name])
            for name in ("baseline", "tokenmaster", "ponytail", "headroom")]
    schedule = [(case.id, arm.name) for case in cases for arm in arms]
    random.Random(20261008).shuffle(schedule)
    manifest = {
        "protocol": HARNESSES, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "tasks": [asdict(case) | {"identity": case.identity} for case in cases],
        "arms": [asdict(arm) | {"identity": arm.identity} for arm in arms],
        "schedule": schedule, "oracle": parity_cases.ORACLE_ID,
        "model": args.model, "base_url": args.base_url,
        "controls": {"max_calls_per_task": 10, "max_primary_attempts_including_readiness": 241,
                     "study_seconds": 3600, "reference_stopping_threshold": 2_000_000,
                     "max_output_tokens": 4096, "socket_timeout": 90, "hard_deadline": 120,
                     "retries": 0, "persist_transformed_client_history": False,
                     "common_tools": runner.TOOLS, "base_instructions": runner.BASE_INSTRUCTIONS},
        "sampling": "Six fresh purposive repository/document tasks, not an IID population certificate.",
        "headroom": {"image": IMAGE_ID, "config": ready["config"],
                     "warming": "upstream-default-preload-and-canary-v1", "model_limit": 200000,
                     "native_detector_inference_inventory_complete": False,
                     "alias_counter": "default upstream registry, may estimate; not primary measurement",
                     "ast_policy": "upstream default disabled", "optional_fastembed": "absent"},
        "measurements": {"primary": "Complete visible primary API JSON bodies under pinned cl100k_base",
                         "secondary": "Bridge-reported usage; not authenticated serving counters",
                         "local_auxiliary": "Recorded Python ONNX events, not all native detector work",
                         "wall_time": "Observed setup+task+cleanup; cross-runtime, not algorithm speed isolation"},
        "headroom_cache": str(args.headroom_cache), "frozen_source_identity": digest(sources),
        "tokenizer": tokens.backend_info(), "weights_modified": False, "jev": False,
        "refinement": False, "normal_profiles_changed": False,
    }
    write(output / "manifest.json", manifest)
    base = ResponsesTransport(args.base_url, args.model, allow_network=True,
                              max_output_tokens=4096, timeout=90, max_response_bytes=524288)
    client = ParityBudget(base, output)
    warm = client.call({"input": [{"role": "user", "content": "Return exactly READY."}]})
    write(output / "primary-preflight.json", {key: value for key, value in asdict(warm).items() if key != "body"})
    if not warm.ok:
        write(output / "summary.json", summarize([], schedule) | {"halt": warm.reason})
        return 2
    rows = []
    for case_id, name in schedule:
        client.check_limits()
        if client.halt:
            break
        case = next(item for item in cases if item.id == case_id)
        arm = next(item for item in arms if item.name == name)
        directory = output / "runs" / f"{case_id}-{name}"
        comparator = None
        started = time.monotonic()
        adapter_error = None
        final_audit = None
        try:
            if name == "headroom":
                comparator = new_worker(output / "comparators" / f"{case_id}-{name}")
                comparator.start()

            def execute_tool(root, store, tool, arguments, program_runner=None, *, tool_call_id):
                if tool == "fetch_artifact":
                    return runner._execute(root, store, "read_file", arguments, program_runner)
                if tool == "headroom_retrieve":
                    if comparator is None:
                        return json.dumps({"error": "No Headroom reference exists in this arm."})
                    return comparator.retrieve(arguments, tool_call_id)
                return runner._execute(root, store, tool, arguments, program_runner)

            with executor_source_reads() as observed:
                result = runner.run_case(
                    case, arm, directory, client, max_calls=10,
                    request_preparer=comparator.prepare if comparator else None,
                    tool_executor=execute_tool,
                    system_suffix=ponytail["instructions"] if name == "ponytail" else "",
                    persist_view_history=False, harness_id=HARNESSES,
                )
            write(directory / "source-read-info.json", [info.to_dict() for info in observed.values()])
            if comparator is not None:
                final_audit = comparator.finish()
                write(directory / "headroom-recovery-audit.json", final_audit)
        except Exception as error:
            adapter_error = type(error).__name__
            write(output / "adapter-error.json", {"case": case_id, "arm": name, "error_type": adapter_error})
        finally:
            if comparator is not None:
                cleanup = comparator.close()
                if not cleanup.get("container_removed"):
                    adapter_error = "comparator_cleanup_incomplete"
        if not (directory / "result.json").is_file():
            # An aborted setup/task stays missing in the planned inventory.
            client.halt = adapter_error or "missing_task_result"
            break
        result = parse_json((directory / "result.json").read_text())
        counted = recount(result, directory)
        regrade = parity_cases.grade(case, Path(result["workspace"]), result["answer"], result["events"])
        if result["failure"] is None and regrade != result["grade"]:
            raise ValueError("independent regrade mismatch")
        comparator_complete = adapter_error is None and (
            comparator is None or final_audit is not None
            and all(value is not None for value in final_audit["recoveries"].values()))
        row = {
            "case": case_id, "arm": name, "correct": result["grade"]["success"],
            "failure": result["failure"], **counted,
            "comparator_complete": comparator_complete, "adapter_error": adapter_error,
            "all_in_case_seconds": time.monotonic() - started,
            "model_output_checks": regrade["assertions"],
        }
        rows.append(row)
        write(output / "summary.json", summarize(rows, schedule) | {
            "primary_attempts_including_readiness": client.calls, "halt": client.halt,
            "known_primary_reference_tokens_including_readiness": client.known_tokens})
        print(case_id, name, "PASS" if row["correct"] else "FAIL",
              row["calls"], row["primary_reference_tokens"], flush=True)
        if not comparator_complete or not result["regime_valid"]:
            client.halt = adapter_error or result["failure"] or "invalid_task_regime"
            break
    if any(sha(PLUGIN / name) != expected for name, expected in sources.items()):
        raise ValueError("frozen implementation changed during the study")
    final = summarize(rows, schedule) | {
        "primary_attempts_including_readiness": client.calls, "halt": client.halt,
        "known_primary_reference_tokens_including_readiness": client.known_tokens,
        "execution_seconds": time.monotonic() - client.start,
    }
    final["complete"] = final["complete"] and client.halt is None
    write(output / "summary.json", final)
    print(json.dumps(final["by_arm"], indent=2), flush=True)
    return 0 if final["complete"] else 3


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:15721/v1")
    parser.add_argument("--headroom-cache", type=Path, required=True)
    parser.add_argument("--headroom-assets", type=Path, required=True)
    parser.add_argument("--ponytail-export", type=Path, required=True)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--frozen", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.allow_network:
        parser.error("--allow-network is required; no model call was made")
    if args.frozen:
        return execute(args)
    output = args.output.resolve()
    entry = snapshot(output, args.ponytail_export.resolve(), args.headroom_assets.resolve())
    command = [
        sys.executable, "-B", str(entry), "--output", str(output), "--model", args.model,
        "--base-url", args.base_url, "--headroom-cache", str(args.headroom_cache.resolve()),
        "--headroom-assets", str(output / "headroom-assets.json"),
        "--ponytail-export", str(output / "ponytail.json"), "--allow-network", "--frozen",
    ]
    return subprocess.run(command, env=child_environment(output), cwd=entry.parent,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
