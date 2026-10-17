"""Live synthetic-workspace challenge study; never a promotion certificate.

Freezes a private copy of source before execution. Requires an existing loopback
model bridge, exact local tokenizer and verified WSL sandbox. All captures and
model edits remain in a fresh output directory. No real host profile is changed.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import uuid

PLUGIN = Path(__file__).resolve().parents[1]
SKILL = PLUGIN / "skills" / "token-master"
sys.path.insert(0, str(SKILL))

from brainspace import tokens  # noqa: E402


def child_environment(output):
    # Windows os.environ iteration uppercases SYSTEMROOT; explicit lookup is
    # case-insensitive there and preserves the OS dependency without credentials.
    environment = {key: os.environ[key] for key in
                   ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "PATHEXT")
                   if key in os.environ}
    environment.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
                       BRAINSPACE_TOKENIZER_FILE=str(output / "cl100k_base.tiktoken"))
    return environment


def _write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False), encoding="utf-8")


def _fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(output):
    if output.exists():
        raise ValueError("output directory must be new")
    vocabulary = tokens._vocabulary_path()
    data = vocabulary.read_bytes() if vocabulary else b""
    if hashlib.sha256(data).hexdigest() != tokens.VOCABULARY_SHA256:
        raise ValueError("verified local tokenizer required")
    sources = [Path(__file__)]
    sources += list((PLUGIN / "evals" / "quality").glob("*.py"))
    sources += list((SKILL / "brainspace").glob("*.py"))
    sources += list((SKILL / "brainspace" / "compressors").glob("*.py"))
    hashes = {str(path.relative_to(PLUGIN)): _fingerprint(path) for path in sources}
    output.mkdir(parents=True)
    destination = output / "source" / "token-master-plugin"
    for source in sources:
        target = destination / source.relative_to(PLUGIN)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        if _fingerprint(target) != hashes[str(source.relative_to(PLUGIN))]:
            raise ValueError("source changed while freezing")
    if any(_fingerprint(path) != hashes[str(path.relative_to(PLUGIN))] for path in sources):
        raise ValueError("source changed while freezing")
    (output / "cl100k_base.tiktoken").write_bytes(data)
    _write(output / "source-manifest.json", hashes)
    return destination / "evals" / "run_quality.py"


def summarize(results):
    by_arm = {}
    for result in results:
        name = result["arm"]["name"]
        state = by_arm.setdefault(name, {
            "tasks": 0, "successes": 0, "failures": 0, "ungraded": 0, "incomplete_traces": 0,
            "input_tokens": 0, "output_tokens": 0, "calls": 0, "peak_input_tokens": 0,
            "wall_seconds": 0,
            "context_projection_tokens": 0,
            "context_projection_input_tokens": 0,
            "invalid_environment_runs": 0,
        })
        state["tasks"] += 1
        state["successes"] += result["grade"]["success"] is True
        state["failures"] += result["grade"]["success"] is False
        state["ungraded"] += result["grade"]["success"] is None
        state["wall_seconds"] += result["elapsed_seconds"]
        state["invalid_environment_runs"] += not result.get("regime_valid", True)
        projected = result.get("context_projection", {}).get("total_tokens")
        if projected is None:
            state["context_projection_tokens"] = None
        elif state["context_projection_tokens"] is not None:
            state["context_projection_tokens"] += projected
        incoming = result.get("context_projection", {}).get("input_tokens")
        if incoming is None:
            state["context_projection_input_tokens"] = None
        elif state["context_projection_input_tokens"] is not None:
            state["context_projection_input_tokens"] += incoming
        if result["totals"] is None:
            state["incomplete_traces"] += 1
        else:
            for key in ("input_tokens", "output_tokens", "calls"):
                state[key] += result["totals"][key]
            state["peak_input_tokens"] = max(state["peak_input_tokens"], result["totals"]["peak_input_tokens"])
    for state in by_arm.values():
        if state["incomplete_traces"]:
            for key in ("input_tokens", "output_tokens", "calls", "peak_input_tokens"):
                state[key] = None
        state["total_tokens"] = (
            state["input_tokens"] + state["output_tokens"] if not state["incomplete_traces"] else None)
        eligible = (not state["incomplete_traces"] and not state["ungraded"]
                    and not state["invalid_environment_runs"] and state["successes"] > 0)
        state["tokens_per_verified_success"] = state["total_tokens"] / state["successes"] if eligible else None
        state["ratio_status"] = (
            "invalid_environment" if state["invalid_environment_runs"] else
            "incomplete_capture" if state["incomplete_traces"] else
            "ungraded_outcomes" if state["ungraded"] else
            "no_successes" if not state["successes"] else "descriptive_only")
    return by_arm


def execute(args):
    from quality.cases import CASES
    from quality.oracle import oracle_identity
    from quality.responses import ResponsesTransport
    from quality.runner import Arm, run_case
    from quality.sandbox import run_program, sandbox_runner

    output = args.output.resolve()
    Path(__file__).resolve().relative_to(output / "source")
    if (output / "manifest.json").exists():
        raise ValueError("a study is never replayed or overwritten")
    available = {
        "baseline": Arm("baseline"), "scope": Arm("scope", scope=True),
        "views": Arm("views", views=True), "combined": Arm("combined", scope=True, views=True),
    }
    cases = [case for case in CASES if not args.cases or case.id in args.cases]
    if args.cases and set(args.cases) != {case.id for case in cases}:
        raise ValueError("unknown case")
    if len(cases) * len(args.arms) * args.repeats * args.max_calls + 1 > args.max_total_calls:
        raise ValueError("declared study exceeds the call allowance")
    study_id = uuid.uuid4().hex
    manifest = {
        "schema_version": 1, "study_id": study_id, "status": "preflight",
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model_requested": args.model, "bridge": args.base_url, "python": sys.version,
        "sampling": "predeclared non-IID challenge suite; order randomized only",
        "statistical_promotion_eligible": False, "weights_modified": False,
        "monetary_objective": False, "real_host_profiles_modified": False,
        "harness": "explicit stateless tool-loop, not CLI/Desktop",
        "oracle_id": oracle_identity(), "source_manifest": "source-manifest.json",
        "case_identities": {case.id: case.identity for case in cases},
        "arms": {name: {"policy_id": available[name].identity} for name in args.arms},
        "repeats": args.repeats, "max_calls_per_task": args.max_calls,
        "maximum_primary_calls": len(cases) * len(args.arms) * args.repeats * args.max_calls,
        "reserved_preflight_calls": 1,
        "excluded_components": ["upstream internal calls/compute and proprietary model templates",
                                "earlier development/preflight work outside this study"],
        "metrics_predeclared": {
            "primary": "complete-json-body-text/utf8-ordinary",
            "supplementary": "explicit-context-fields-json-v1; not a promotion metric",
        },
    }
    _write(output / "manifest.json", manifest)
    probe = run_program({"probe.txt": "synthetic"}, "print('QUALITY_SANDBOX_READY')")
    _write(output / "sandbox-preflight.json", probe)
    if not (probe.get("exit_code") == 0 and probe.get("stdout") == "QUALITY_SANDBOX_READY\n"
            and probe.get("boundary", {}).get("ready") is True
            and probe.get("boundary", {}).get("scoped_cleanup") is True):
        manifest.update(status="blocked", blocker="sandbox_preflight_failed")
        _write(output / "manifest.json", manifest)
        return 2
    client = ResponsesTransport(args.base_url, args.model, allow_network=True,
                                max_output_tokens=args.max_output_tokens)
    from dataclasses import replace
    from quality.runner import _native_actions
    warm = replace(client, max_output_tokens=128).call({
        "input": [{"role": "user", "content": "Synthetic readiness check: return exactly QUALITY_MODEL_READY."}],
    })
    _write(output / "model-preflight.json", {
        "ok": warm.ok, "reason": warm.reason, "error_type": warm.error_type,
        "input": warm.input_text, "output": warm.output_text, "complete": warm.complete,
        "reference_input_tokens": tokens.count_tokens(warm.input_text) if warm.complete else None,
        "reference_output_tokens": tokens.count_tokens(warm.output_text) if warm.complete else None,
        "phase": "learning", "role": "verification", "scope": "shared study setup, not an arm's runtime",
    })
    try:
        _, answer, _ = _native_actions(warm.body)
        ready = warm.ok and answer.get("content") == "QUALITY_MODEL_READY"
    except (ValueError, TypeError, KeyError, AttributeError):
        ready = False
    if not ready:
        manifest.update(status="blocked", blocker="model_preflight_failed", completed_runs=0)
        _write(output / "manifest.json", manifest)
        return 2
    order, rng = [], random.Random(args.seed)
    for repetition in range(args.repeats):
        shuffled = list(cases)
        rng.shuffle(shuffled)
        for case in shuffled:
            arms = list(args.arms)
            rng.shuffle(arms)
            task_id = f"{study_id}:{repetition}:{case.id}"
            order.extend((repetition, case, name, task_id) for name in arms)
    manifest.update(status="running", order=[
        {"rep": rep, "case": case.id, "arm": name, "task_id": tid} for rep, case, name, tid in order])
    _write(output / "manifest.json", manifest)
    results = []
    try:
        for rep, case, name, task_id in order:
            destination = output / "runs" / f"r{rep}-{case.id}-{name}"
            result = run_case(
                case, available[name], destination, client, max_calls=args.max_calls,
                task_id=task_id, learning_run_id=study_id, sandbox_runner=sandbox_runner,
                program_runner=run_program,
            )
            results.append(result)
            print(json.dumps({"case": case.id, "arm": name, "status": result["grade"]["status"],
                              "calls": result["totals"]["calls"] if result["totals"] else None,
                              "view_transforms": len(result["views"])}), flush=True)
            _write(output / "summary.json", {"complete": False, "by_arm": summarize(results)})
    except BaseException:
        manifest.update(status="interrupted", completed_runs=len(results))
        _write(output / "manifest.json", manifest)
        raise
    source_hashes = json.loads((output / "source-manifest.json").read_text(encoding="utf-8"))
    if any(_fingerprint(PLUGIN / relative) != expected for relative, expected in source_hashes.items()):
        raise ValueError("frozen source changed")
    summary = {
        "complete": all(result["coverage"] == "complete_for_declared_boundary"
                        and result["regime_valid"] for result in results),
        "collection_finished": True, "runs": len(results), "by_arm": summarize(results),
        "comparison_regime_valid": all(result["regime_valid"] for result in results),
        "coverage": "complete observed bridge bodies per successful capture, never upstream internals",
        "statistical_certificate": None, "promotion": "not_attempted_non_iid_challenge_suite",
        "proof_review_pending": [
            str(Path(result["workspace"]).parent.relative_to(output) / "result.json")
            for result in results if result["grade"]["status"] == "needs_blind_review"],
    }
    _write(output / "summary.json", summary)
    manifest.update(status="complete", completed_runs=len(results), capture_complete=summary["complete"])
    _write(output / "manifest.json", manifest)
    print(json.dumps(summary, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--arms", choices=("baseline", "scope", "views", "combined"), nargs="+",
                        default=["baseline", "combined"])
    parser.add_argument("--cases", nargs="+")
    parser.add_argument("--repeats", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--max-calls", type=int, choices=range(4, 17), default=12)
    parser.add_argument("--max-total-calls", type=int, default=256)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--seed", type=int, default=104)
    parser.add_argument("--execute-snapshot", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.allow_network:
        parser.error("explicit --allow-network required; only synthetic data is sent")
    from quality.responses import ResponsesTransport
    # Validate before recording URL/configuration anywhere.
    ResponsesTransport(args.base_url, args.model, max_output_tokens=args.max_output_tokens)
    if len(set(args.arms)) != len(args.arms) or args.max_total_calls <= 0:
        parser.error("arms must be unique and the call allowance positive")
    if args.execute_snapshot:
        return execute(args)
    output = args.output.resolve()
    target = snapshot(output)
    environment = child_environment(output)
    result = subprocess.run([sys.executable, "-X", "utf8", str(target),
                             *sys.argv[1:], "--execute-snapshot"], env=environment)
    return result.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        print(json.dumps({"ok": False, "error": type(error).__name__,
                          "reason": "quality_study_precondition_failed"}))
        raise SystemExit(2) from None
