"""Opt-in source-pinned repository A/B diagnostic, not a parity certificate.

Uses the existing quality evaluator in a frozen private source copy. Unknown
responses remain unknown; no retry, credential discovery or host installation.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess
import sys
import time
import uuid

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "skills/token-master"))
from brainspace import tokens  # noqa: E402
from brainspace.ccr import CCR  # noqa: E402
from brainspace.pipeline import prepare_request  # noqa: E402
from brainspace.request_policy import RequestPolicy, SourceReadInfo, _protected  # noqa: E402
from quality import runner  # noqa: E402
from quality.cases import Case, digest  # noqa: E402
from quality.responses import Reply, ResponsesTransport, parse_json  # noqa: E402
from quality.measurement import input_context_text  # noqa: E402
from refinement.core import deadline_call, native_usage  # noqa: E402
from source_read_adapter import SourceAwareArm, executor_source_reads  # noqa: E402
from run_quality import child_environment, snapshot as quality_snapshot  # noqa: E402

FIXTURE_SHA256 = "f4ebd67e9b9f27a6f554fa379189699813d939b7a59ce429fa04a1d8c57b3140"
ORACLE_ID = "source-contract-and-exact-patch-behavior-v3"


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False), encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def trusted_router_tests(source):
    """Only operator-prepared trusted source, or an exact-match candidate, reaches exec."""
    namespace = {"__name__": "brainspace.pinned_repository_fixture", "__package__": "brainspace"}
    exec(compile(source, "<source-pinned-router>", "exec"), namespace)
    checks = {
        "short_stub": namespace["detect"]("answer: int", "contract.pyi").value == "code",
        "uppercase_stub": namespace["detect"]("answer: int", "CONTRACT.PYI").value == "code",
        "ordinary_python": namespace["detect"]("x = 1", "module.py").value == "code",
        "rust": namespace["detect"]("fn x() {}", "module.rs").value == "code",
        "markdown": namespace["detect"]("ordinary prose", "notes.md").value == "prose",
        "stub_language": namespace["lang_from_hint"]("contract.pyi") == "python",
    }
    return checks


class BudgetClient:
    def __init__(self, base, output):
        self.base, self.output = base, output
        self.start = time.monotonic()
        self.calls = self.known_tokens = 0
        self.halt = None
        self.study_id = uuid.uuid4().hex

    def __getattr__(self, name):
        return getattr(self.base, name)

    def request(self, payload):
        return self.base.request({**payload, "reasoning": {"effort": "low"}})

    def check_limits(self):
        remaining = 900 - (time.monotonic() - self.start)
        if self.halt is None:
            if self.calls >= 65:
                self.halt = "call_limit"
            elif remaining <= 0:
                self.halt = "wall_time_limit"
            elif self.known_tokens >= 500000:
                self.halt = "reference_limit"
        return remaining

    def call(self, payload):
        remaining = self.check_limits()
        if self.halt:
            return Reply(False, "study_limit_no_submission")
        self.calls += 1
        call_id = self.study_id + ":" + str(self.calls)
        runner.append_receipt(self.output / "study-invocations.jsonl",
                              {"call_id": call_id, "state": "pending"})
        reply = deadline_call(self.base, {**payload, "reasoning": {"effort": "low"}},
                              min(self.base.timeout + 30, remaining))
        runner.append_receipt(self.output / "study-invocations.jsonl", {
            "call_id": call_id, "state": "returned", "complete": reply.complete,
            "reason": reply.reason,
        })
        if reply.complete and reply.input_text is not None and reply.output_text is not None:
            self.known_tokens += tokens.count_tokens(reply.input_text) + tokens.count_tokens(reply.output_text)
        else:
            self.halt = "incomplete_capture"
        if reply.http_status == 429:
            self.halt = "rate_limited"
        if reply.reason == "model_mismatch":
            self.halt = "model_mismatch"
        return reply


def grade_repository(case, workspace, answer, events, *, sandbox_runner=None):
    spec = SPECS[case.id]
    found = {path.relative_to(workspace).as_posix(): path.read_bytes()
             for path in Path(workspace).rglob("*") if path.is_file()}
    originals = {path: content.encode("utf-8") for path, content in case.fixtures}
    unexpected = sorted(set(found) - set(originals))
    missing = sorted(set(originals) - set(found))
    changed = sorted(name for name in originals.keys() & found.keys()
                     if found[name] != originals[name])
    checks = {"no_extra_files": not unexpected, "no_missing_files": not missing,
              "changes_within_scope": not set(changed) - set(case.allowed_changes),
              "write_scope_respected": all(
                  event["name"] != "write_file"
                  or event["arguments"].get("path") in case.allowed_changes for event in events)}
    if spec["kind"] == "answer":
        checks["answer_matches_source_contract"] = (
            json.dumps(answer, sort_keys=True, allow_nan=False) ==
            json.dumps(spec["expected"], sort_keys=True, allow_nan=False))
    else:
        path = "brainspace/router.py"
        matches = path in found and found[path] == GOLD.encode("utf-8")
        checks["exact_requested_patch"] = matches
        # No arbitrary generated Python is parsed or executed. Equality to the
        # independently prepared trusted patch is required before behavior tests.
        if matches:
            checks.update(trusted_router_tests(found[path].decode("utf-8")))
    result = {"status": "passed" if all(checks.values()) else "failed",
              "success": all(checks.values()), "checks": [key for key, ok in checks.items() if not ok],
              "assertions": checks, "changed_files": changed,
              "unexpected_files": unexpected, "missing_files": missing,
               "oracle": ORACLE_ID}
    result["evidence_digest"] = digest(result)
    return result


def chat_from_request(body):
    messages = []
    for item in body["input"]:
        kind = item.get("type")
        if kind == "function_call":
            messages.append({"role": "assistant", "content": None, "tool_calls": [{
                "id": item["call_id"], "type": "function",
                "function": {"name": item["name"], "arguments": item["arguments"]}}]})
        elif kind == "function_call_output":
            messages.append({"role": "tool", "tool_call_id": item["call_id"], "content": item["output"]})
        else:
            messages.append({"role": item["role"], "content": item["content"]})
    chat = {"model": body["model"], "messages": messages}
    if runner.to_responses(chat)["input"] != body["input"]:
        raise ValueError("request history did not round-trip")
    return chat


def audit_run(case, result, directory, base):
    captures = [parse_json(line) for line in (directory / "captures.jsonl").read_text(
        encoding="utf-8").splitlines()]
    try:
        invocations = [parse_json(line) for line in (directory / "invocations.jsonl").read_text(
            encoding="utf-8").splitlines()]
    except (OSError, ValueError) as error:
        raise ValueError("missing or invalid invocation receipts") from error
    expected_invocations = [
        {"call_id": capture["call_id"], "state": state}
        for capture in captures for state in ("pending", "captured")
    ]
    if invocations != expected_invocations:
        raise ValueError("unresolved or inconsistent invocation receipt inventory")
    records = result["trace"]["calls"]
    expected = list(result["trace"]["expected_call_ids"])
    incomplete = result["incomplete_calls"]
    coverage = "partial" if incomplete else "complete_for_declared_boundary"
    if result["coverage"] != coverage or result["trace"]["coverage"] != coverage:
        raise ValueError("contradictory coverage")
    record_map = {record["call_id"]: record for record in records}
    incomplete_map = {item["call_id"]: item for item in incomplete}
    capture_ids = [capture["call_id"] for capture in captures]
    observed = [capture["call_id"] for capture in captures
                if capture["input"] is not None or capture["reason"] not in runner._NO_SUBMISSION]
    if (len(set(capture_ids)) != len(capture_ids) or len(set(expected)) != len(expected)
            or len(record_map) != len(records) or len(incomplete_map) != len(incomplete)
            or set(record_map) & set(incomplete_map)
            or set(record_map) | set(incomplete_map) != set(expected)
            or observed != expected
            or [key for key in expected if key in record_map] != list(record_map)):
        raise ValueError("call inventory mismatch")
    if incomplete and result["totals"] is not None:
        raise ValueError("incomplete coverage cannot have whole-task totals")
    totals = {"input_tokens": 0, "output_tokens": 0, "bridge_input": 0, "bridge_output": 0,
              "input_context_tokens": 0, "calls": len(expected)}
    counterfactual = []
    store = CCR(directory / "recovery.sqlite", workspace_root=Path(result["workspace"]),
                session_id=directory.name)
    info_path = directory / "source-read-info.json"
    infos = tuple(SourceReadInfo.from_dict(item) for item in
                  parse_json(info_path.read_text(encoding="utf-8")))
    by_call = {info.call_id: info for info in infos}
    if len(by_call) != len(infos):
        raise ValueError("duplicate executor source observation")
    for index, capture in enumerate(captures):
        call_id = capture["call_id"]
        if call_id not in record_map:
            if call_id in incomplete_map:
                item = incomplete_map[call_id]
                prepared = tokens.count_tokens(capture["input"]) if capture["input"] is not None else None
                if (capture["complete"] and capture["input"] is not None and capture["output"] is not None
                        or item["reason"] != capture["reason"]
                        or item["prepared_input_tokens"] != prepared
                        or item["output_tokens"] is not None):
                    raise ValueError("incomplete capture inventory mismatch")
            elif capture["input"] is not None or capture["reason"] not in runner._NO_SUBMISSION:
                raise ValueError("unaccounted capture")
            continue
        recorded = record_map[call_id]
        if not capture["complete"] or capture["input"] is None or capture["output"] is None:
            raise ValueError("incomplete capture")
        request = parse_json(capture["input"])
        try:
            response = parse_json(capture["output"])
        except ValueError:
            response = {}
        if type(response) is not dict:
            response = {}
        if request["model"] != base.model or (capture["reason"] == "ok"
                                             and response.get("model") != base.model):
            raise ValueError("model identity mismatch")
        if capture["call_id"] != recorded["call_id"]:
            raise ValueError("call identity mismatch")
        incoming, outgoing = tokens.count_tokens(capture["input"]), tokens.count_tokens(capture["output"])
        if incoming != recorded["reference_input_tokens"] or outgoing != recorded["reference_output_tokens"]:
            raise ValueError("saved count mismatch")
        if (hashlib.sha256(capture["input"].encode()).hexdigest() != recorded["input_sha256"]
                or hashlib.sha256(capture["output"].encode()).hexdigest() != recorded["output_sha256"]):
            raise ValueError("capture digest mismatch")
        totals["input_tokens"] += incoming
        totals["output_tokens"] += outgoing
        totals["input_context_tokens"] += tokens.count_tokens(input_context_text(request))
        usage = native_usage(response)
        if usage is None:
            totals["bridge_input"] = totals["bridge_output"] = None
        elif totals["bridge_input"] is not None:
            totals["bridge_input"] += usage["input_tokens"]
            totals["bridge_output"] += usage["output_tokens"]
        # Restore only executor-observed source results, holding this actual
        # model/tool trajectory fixed. This is input accounting, not a claim
        # that the model would choose the same trajectory without compression.
        materialized = chat_from_request(request)
        if canonical(base.request({**runner.to_responses(materialized), "reasoning": {"effort": "low"}})) \
                != capture["input"]:
            raise ValueError("request controls or native serialization changed")
        calls = {call["id"]: call for message in materialized["messages"]
                 for call in message.get("tool_calls", [])}
        recovered = 0
        for message in materialized["messages"]:
            observation = by_call.get(message.get("tool_call_id"))
            if observation is None:
                continue
            if not observation.matches(message, calls.get(observation.call_id)):
                roots = [ref for ref in re.findall(r"\[\[BR:.*?\]\]", message["content"])
                         if "kind=root" in ref]
                originals = [value for ref in roots if isinstance(value := store.retrieve(ref), str)
                             and hashlib.sha256(value.encode("utf-8")).hexdigest() == observation.content_sha256]
                if len(originals) != 1:
                    raise ValueError("a changed source result lacks its exact observed original")
                message["content"] = originals[0]
                recovered += 1
            if not observation.matches(message, calls.get(observation.call_id)):
                raise ValueError("source observation does not bind to the tool call")
        before = base.request({**runner.to_responses(materialized), "reasoning": {"effort": "low"}})
        restored_tokens = tokens.count_tokens(canonical(before))
        if restored_tokens < incoming:
            raise ValueError("captured source view expanded the native input")
        plan = prepare_request(
            materialized, RequestPolicy(version="request-policy-v2", enabled=True, min_tool_chars=512),
            ccr=store, intent=case.intent, protocol="chat-completions-v1",
            stable_prefix_messages=2, source_reads=infos)
        altered = base.request({**runner.to_responses(plan.request), "reasoning": {"effort": "low"}})
        planned = tokens.count_tokens(canonical(altered))
        counterfactual.append({
            "call": index, "status": plan.status, "reason": plan.reason,
            "actual_input_removed": restored_tokens - incoming,
            "uncompressed_same_history_input_tokens": restored_tokens,
            "recovered_source_results": recovered,
            "reference_input_removed": restored_tokens - planned
            if plan.status == "transformed" and planned < restored_tokens else 0,
        })
    totals["reference_total"] = totals["input_tokens"] + totals["output_tokens"]
    totals["bridge_total"] = (totals["bridge_input"] + totals["bridge_output"]
                               if totals["bridge_input"] is not None else None)
    if not incomplete and (result["totals"] is None
                           or totals["reference_total"] != result["totals"]["total_tokens"]):
        raise ValueError("whole-task recount mismatch")
    verdict = grade_repository(case, Path(result["workspace"]), result["answer"], result["events"])
    if result["failure"] is None and verdict != result["grade"]:
        raise ValueError("saved outcome mismatch")
    if result["failure"] is not None and result["grade"]["success"] is not False:
        raise ValueError("failed attempt cannot be graded successful")
    known = {"known_" + key: totals[key] for key in
             ("input_tokens", "output_tokens", "reference_total",
              "bridge_input", "bridge_output", "bridge_total")}
    if incomplete:
        for key in ("input_tokens", "output_tokens", "input_context_tokens",
                    "reference_total", "bridge_input", "bridge_output", "bridge_total"):
            totals[key] = None
    return {**totals, **known, "case": case.id, "arm": result["arm"]["name"],
             "correct": result["grade"]["success"], "failure": result["failure"],
             "accounting_status": "incomplete" if incomplete else "complete",
             "regime_valid": result["regime_valid"] and result["failure"] != "study_limit_no_submission",
             "complete_calls": len(records),
             "incomplete_calls": incomplete, "captured_invocations": len(captures),
             "transformed_requests": sum(c["actual_input_removed"] > 0 for c in counterfactual),
             "transformed_attempts": len(result["views"]), "wall_seconds": result["elapsed_seconds"],
             "counterfactual_input_removed": sum(c["reference_input_removed"] for c in counterfactual),
             "actual_same_history_input_removed": sum(c["actual_input_removed"] for c in counterfactual),
             "recovered_source_results": sum(c["recovered_source_results"] for c in counterfactual),
             "counterfactual_coverage": "captured_prefix" if incomplete else "complete",
             "counterfactual": counterfactual, "checks": verdict["assertions"]}


def summarize(rows, schedule):
    """Whole planned-arm totals stay unknown if any task is absent or partial."""
    expected = [tuple(item) for item in schedule]
    seen = [(row["case"], row["arm"]) for row in rows]
    if not expected:
        raise ValueError("empty planned run inventory")
    if len(set(expected)) != len(expected) or len(set(seen)) != len(seen):
        raise ValueError("duplicate run inventory")
    if not set(seen) <= set(expected):
        raise ValueError("unexpected run inventory")
    missing = [{"case": case, "arm": arm} for case, arm in expected if (case, arm) not in seen]
    by_arm = {}
    for arm in dict.fromkeys(arm for _, arm in expected):
        group = [row for row in rows if row["arm"] == arm]
        planned = sum(name == arm for _, name in expected)
        complete = len(group) == planned and all(
            row["accounting_status"] == "complete" and row["regime_valid"] for row in group)
        state = {"tasks": len(group), "planned_tasks": planned,
                 "correct": sum(row["correct"] is True for row in group),
                 "calls": sum(row["calls"] for row in group),
                 "complete_calls": sum(row["complete_calls"] for row in group),
                 "accounting_status": "complete" if complete else "incomplete"}
        for key in ("reference_total", "input_tokens", "output_tokens", "input_context_tokens",
                    "bridge_input", "bridge_output", "bridge_total"):
            state[key] = sum(row[key] for row in group) if complete and all(
                row[key] is not None for row in group) else None
        for key in ("known_reference_total", "known_bridge_total", "wall_seconds",
                    "transformed_requests", "actual_same_history_input_removed", "recovered_source_results"):
            state[key] = sum(row[key] for row in group) if all(row[key] is not None for row in group) else None
        by_arm[arm] = state
    return {
        "complete": not missing and all(row["accounting_status"] == "complete"
                                       and row["regime_valid"] for row in rows),
        "expected_task_runs": len(expected), "attempted_task_runs": len(rows),
        "successful_task_runs": sum(row["correct"] is True for row in rows),
        "all_tasks_correct": not missing and all(row["correct"] is True for row in rows),
        "missing_runs": missing, "by_arm": by_arm, "per_task": rows,
        "statistical_certificate": None, "policy_promoted": False,
    }


def load_cases(path):
    """Authenticate the fixed public fixture before compiling trusted source."""
    global SPECS, GOLD
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
        raise ValueError("fixed repository fixture integrity mismatch")
    data = parse_json(raw.decode("utf-8"))
    SPECS = {item["id"]: item for item in data["tasks"]}
    fixtures = tuple(tuple(item) for item in data["fixtures"])
    original = dict(fixtures)["brainspace/router.py"]
    GOLD = original.replace('(".py", ".js",', '(".py", ".pyi", ".js",', 1)
    if GOLD == original or trusted_router_tests(original)["short_stub"]:
        raise ValueError("the chosen regression is not present in the pinned baseline")
    if not all(trusted_router_tests(GOLD).values()):
        raise ValueError("trusted reference patch fails behavior checks")
    cases = [Case(item["id"], data["commit"], item["prompt"], fixtures,
                   ("brainspace/router.py",) if item["kind"] == "edit" else (),
                   intent=item["intent"]) for item in data["tasks"]]
    return data, cases


def execute(args):
    output = args.output.resolve()
    Path(__file__).resolve().relative_to(output / "source")
    if (output / "manifest.json").exists():
        raise ValueError("a live study is never overwritten or replayed in place")
    sources = parse_json((output / "source-manifest.json").read_text(encoding="utf-8"))
    if any(sha(PLUGIN / path) != expected for path, expected in sources.items()):
        raise ValueError("frozen source mismatch")
    data, cases = load_cases(PLUGIN / "evals/repository-cases.json")
    fixtures = tuple(tuple(item) for item in data["fixtures"])
    original = dict(fixtures)["brainspace/router.py"]
    runner.BASE_INSTRUCTIONS = runner.BASE_INSTRUCTIONS.replace(
        "supplied synthetic workspace", "isolated source-pinned repository snapshot")
    runner.TOOLS = [tool for tool in runner.TOOLS if tool["name"] != "run_python"]
    runner.grade = grade_repository
    base = ResponsesTransport(args.base_url, args.model,
                               allow_network=True, max_output_tokens=4096, timeout=args.timeout_seconds,
                              max_response_bytes=524288)
    client = BudgetClient(base, output)
    arms = [SourceAwareArm("baseline"),
            SourceAwareArm("tokenmaster", views=True, scope=args.task_discipline)]
    schedule = [(case.id, arm.name) for case in cases for arm in arms]
    random.Random(20261005).shuffle(schedule)
    manifest = {"protocol": "source-pinned-context-policy-ab-v4", "fixture_commit": data["commit"],
                "fixture_sha256": FIXTURE_SHA256,
                "oracle": ORACLE_ID,
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "tasks": [asdict(case) | {"identity": case.identity} for case in cases],
                "arms": [asdict(arm) | {"identity": arm.identity, "policy": arm.policy.to_dict()} for arm in arms],
                "schedule": schedule, "model": base.model, "base_url": base.base_url,
                "controls": {"max_calls_per_task": 8, "max_total_calls": 65, "max_seconds": 900,
                              "max_output_tokens_per_call": 4096, "reference_stop": 500000,
                              "socket_timeout_seconds": args.timeout_seconds,
                              "hard_deadline_seconds": args.timeout_seconds + 30,
                             "scope_instructions": args.task_discipline,
                             "jev": False, "refinement": False,
                             "network_tools": False, "generated_code_execution": "exact-trusted-patch-only"},
                "sampling": "four predeclared real-repository tasks, not IID or a production certificate",
                "host": "explicit stateless bridge adapter, not native Copilot CLI/Desktop",
                "treatment": "context-and-task-discipline" if args.task_discipline else "context-only",
                "adapter": "executor-source-read-info-v1",
                "invocation_receipts": {
                    "study": "study-invocations.jsonl",
                    "per_task": "invocations.jsonl",
                    "unresolved_dispatch": "unknown, never zero or silently retried",
                },
                "intent_correction": "navigate_architecture: overview -> navigation; same public prompt in both arms",
                "frozen_source_identity": digest(sources), "tokenizer": tokens.backend_info()}
    write(output / "manifest.json", manifest)
    survey = []
    for name, content in fixtures:
        survey.append({"path": name, "chars": len(content), "reference_tokens": tokens.count_tokens(content),
                       "protected_as_tool_text": _protected({"role": "tool", "content": content})})
    write(output / "source-eligibility.json", survey)
    # Cheap positive/negative controls exercise independent grading before inference.
    checks = {"original_stub_bug_reproduced": not trusted_router_tests(original)["short_stub"],
              "reference_patch_passes": all(trusted_router_tests(GOLD).values())}
    write(output / "oracle-preflight.json", checks)
    warm = client.call({"input": [{"role": "user", "content": "Return exactly READY."}]})
    write(output / "preflight.json", {key: value for key, value in asdict(warm).items() if key != "body"})
    if not warm.ok:
        write(output / "status.json", {"status": "preflight_failed", "reason": warm.reason})
        write(output / "summary.json", summarize([], schedule) | {"halt": warm.reason})
        return 2
    rows = []
    for case_id, arm_name in schedule:
        client.check_limits()
        if client.halt:
            break
        case = next(c for c in cases if c.id == case_id)
        arm = next(a for a in arms if a.name == arm_name)
        directory = output / "runs" / f"{case_id}-{arm_name}"
        plans = []
        def observe_plan(before, after):
            plans.append({"status": after.status, "reason": after.reason,
                          "changed_messages": list(after.changed_message_indices),
                          "policy_id": after.policy_id})
        with executor_source_reads(on_plan=observe_plan) as observations:
            result = runner.run_case(case, arm, directory, client, max_calls=8)
        write(directory / "source-read-info.json", [info.to_dict() for info in observations.values()])
        write(directory / "plan-events.json", plans)
        captures = (directory / "captures.jsonl").read_text(encoding="utf-8").splitlines()
        if arm.views and len(plans) != len(captures):
            raise ValueError("request-plan inventory did not match captured calls")
        row = audit_run(case, result, directory, base)
        rows.append(row)
        write(output / "summary.json", summarize(rows, schedule) | {
            "attempts_including_readiness": client.calls, "halt": client.halt})
        print(case_id, arm_name, "PASS" if row["correct"] else "FAIL", row["calls"],
              row["bridge_total"], "transformations", row["transformed_requests"], flush=True)
    final = summarize(rows, schedule) | {"attempts_including_readiness": client.calls,
              "execution_seconds": time.monotonic() - client.start, "known_reference_tokens_including_readiness": client.known_tokens,
              "halt": client.halt, "independent_recount_matches": True, "independent_grading_rechecked": True,
              "statistical_certificate": None, "production_settings_changed": False, "default_policy_changed": False}
    final["complete"] = final["complete"] and not client.halt
    final["reference_tokens_including_readiness"] = client.known_tokens if final["complete"] else None
    if any(sha(PLUGIN / path) != expected for path, expected in sources.items()):
        raise ValueError("frozen source changed during run")
    write(output / "summary.json", final)
    print(json.dumps(final["by_arm"], indent=2), flush=True)
    return 0 if final["complete"] else 3


def snapshot(output):
    """Reuse the quality freezer and add this diagnostic's exact dependencies."""
    extra = [Path(__file__), PLUGIN / "evals/repository-cases.json",
             PLUGIN / "evals/source_read_adapter.py", *sorted((PLUGIN / "evals/refinement").glob("*.py"))]
    original = {str(path.relative_to(PLUGIN)): sha(path) for path in extra}
    quality_snapshot(output)
    destination = output / "source" / "token-master-plugin"
    hashes = parse_json((output / "source-manifest.json").read_text(encoding="utf-8"))
    for source in extra:
        relative = str(source.relative_to(PLUGIN))
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        if sha(target) != original[relative] or sha(source) != original[relative]:
            raise ValueError("source changed while freezing")
    hashes.update(original)
    write(output / "source-manifest.json", hashes)
    return destination / "evals/run_repository.py"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:15721/v1")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--task-discipline", action="store_true",
                        help="Also enable the existing scoped-task instructions in the treatment arm.")
    parser.add_argument("--timeout-seconds", type=int, default=60,
                        help="Per-socket timeout (1-90); hard deadline adds 30 seconds. No retries.")
    parser.add_argument("--frozen", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.allow_network:
        parser.error("--allow-network is required; no model call was made")
    if not 1 <= args.timeout_seconds <= 90:
        parser.error("--timeout-seconds must be between 1 and 90")
    if args.frozen:
        return execute(args)
    output = args.output.resolve()
    entry = snapshot(output)
    command = [sys.executable, "-B", str(entry), "--output", str(output),
               "--model", args.model, "--base-url", args.base_url, "--allow-network", "--frozen",
               "--timeout-seconds", str(args.timeout_seconds)]
    if args.task_discipline:
        command.append("--task-discipline")
    return subprocess.run(command, env=child_environment(output), cwd=entry.parent,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
