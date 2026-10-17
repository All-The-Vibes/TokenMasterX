"""Freeze and run a bounded no-tools experiment through an existing local bridge."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import datetime
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import time

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "skills" / "token-master"))

from brainspace import tokens  # noqa: E402
from quality.responses import ResponsesTransport  # noqa: E402
from refinement.cases import generate_cases  # noqa: E402
from refinement.core import (  # noqa: E402
    PROTOCOL, Limits, arms, capture_call, child_environment, digest, make_client,
    run_policy, visible_text, wire, write_json,
)

READINESS = {
    "input": [{"role": "user", "content": "Return exactly READY, with no explanation."}],
    "reasoning": {"effort": "low"},
}


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def freeze(output):
    if output.exists():
        raise ValueError("output directory must be new; studies are never replayed in place")
    vocabulary = tokens._vocabulary_path()
    if vocabulary is None or file_hash(vocabulary) != tokens.VOCABULARY_SHA256:
        raise ValueError("verified offline vocabulary required")
    sources = [Path(__file__)]
    sources += list((PLUGIN / "evals" / "refinement").glob("*.py"))
    sources += [PLUGIN / "evals" / "quality" / name
                for name in ("__init__.py", "responses.py", "measurement.py")]
    # quality.responses is a shim: freeze its canonical production transport,
    # rather than depending on checkout imports or restoring a duplicate copy.
    sources += [PLUGIN / "skills" / "token-master" / "brainspace" / name
                for name in ("__init__.py", "tokens.py", "transport.py")]
    sources += [PLUGIN / "docs" / "REFINEMENT_EXPERIMENT.md"]
    hashes = {str(path.relative_to(PLUGIN)).replace("\\", "/"): file_hash(path) for path in sources}
    output.mkdir(parents=True)
    root = output / "source" / "token-master-plugin"
    for source in sources:
        destination = root / source.relative_to(PLUGIN)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        if file_hash(destination) != hashes[str(source.relative_to(PLUGIN)).replace("\\", "/")]:
            raise ValueError("source changed while freezing")
    for source in sources:
        if file_hash(source) != hashes[str(source.relative_to(PLUGIN)).replace("\\", "/")]:
            raise ValueError("source changed while freezing")
    (output / "cl100k_base.tiktoken").write_bytes(vocabulary.read_bytes())
    write_json(output / "source-manifest.json", hashes)
    return root / "evals" / "run_refinement.py"


class StudyBudget:
    def __init__(self, calls, seconds, reference_tokens):
        self.max_calls, self.max_seconds, self.max_reference = calls, seconds, reference_tokens
        self.started = time.monotonic()
        self.attempts = self.reference_known = self.incomplete = 0
        self.halt_reason = None

    def reserve(self, incoming, seconds):
        remaining = self.max_seconds - (time.monotonic() - self.started)
        if (self.attempts >= self.max_calls or self.incomplete or self.halt_reason or remaining <= 0
                or self.reference_known + incoming > self.max_reference):
            return 0
        self.attempts += 1
        return min(seconds, remaining)

    def observe(self, record):
        if record.get("http_status") == 429:
            self.halt_reason = "rate_limited"
        value = record["measurement"]["reference_total"]
        if value is None:
            self.incomplete += 1
        else:
            self.reference_known += value

    def snapshot(self):
        return {
            "attempts": self.attempts, "known_reference_tokens": self.reference_known,
            "incomplete_calls": self.incomplete,
            "elapsed_seconds": time.monotonic() - self.started,
            "reference_stop_threshold_exceeded": self.reference_known > self.max_reference,
            "halt_reason": self.halt_reason,
        }


def execute(args):
    output = args.output.resolve()
    Path(__file__).resolve().relative_to(output / "source")
    if (output / "manifest.json").exists():
        raise ValueError("existing frozen experiment cannot be resumed or overwritten")
    source_hashes = json.loads((output / "source-manifest.json").read_text(encoding="utf-8"))
    root = output / "source" / "token-master-plugin"
    if any(file_hash(root / key) != value for key, value in source_hashes.items()):
        raise ValueError("frozen source hash mismatch")
    if file_hash(output / "cl100k_base.tiktoken") != tokens.VOCABULARY_SHA256:
        raise ValueError("frozen vocabulary hash mismatch")
    cases = generate_cases(args.seed, args.tasks)
    secondary_api = getattr(args, "secondary_api", "responses")
    secondary_reported = getattr(args, "secondary_reported_model", None)
    transports = {args.primary: "responses", args.secondary: secondary_api}
    reported_models = {args.primary: args.primary, args.secondary: secondary_reported or args.secondary}
    policies = arms(args.primary, args.secondary, secondary_api, secondary_reported)
    selection = getattr(args, "arms", None)
    if selection is not None:
        if (not selection or len(set(selection)) != len(selection)
                or set(selection) - {arm.name for arm in policies}):
            raise ValueError("invalid predeclared arm selection")
        policies = [arm for arm in policies if arm.name in selection]
    limits = Limits(max_output_tokens=args.max_output_tokens,
                    call_seconds=args.call_seconds, policy_seconds=args.policy_seconds)
    schedule = [(case.id, arm.name) for case in cases for arm in policies]
    random.Random(args.seed ^ 0x51A7).shuffle(schedule)
    maximum = 2 + args.tasks * sum(len(arm.schedule()) for arm in policies)
    if maximum > args.max_total_calls:
        raise ValueError("scheduled experiment exceeds total call allowance")
    case_records = [dict(asdict(case), identity=case.identity) for case in cases]
    write_json(output / "cases.json", case_records)
    manifest = {
        "schema_version": 1, "protocol": PROTOCOL,
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "primary": args.primary, "secondary": args.secondary, "base_url": args.base_url,
        "seed": args.seed, "tasks": args.tasks, "source_identity": digest(source_hashes),
        "cases_sha256": file_hash(output / "cases.json"),
        "tokenizer": tokens.backend_info(), "limits": asdict(limits),
        "arms": [dict(asdict(arm), identity=arm.identity) for arm in policies],
        "selected_arms": [arm.name for arm in policies], "transports": transports,
        "expected_reported_models": reported_models,
        "secondary_reported_model_override": secondary_reported,
        "schedule": schedule, "maximum_attempts": maximum,
        "maximum_study_seconds": args.study_seconds,
        "observed_reference_stop_threshold": args.reference_stop,
        "preflight": {"request": READINESS, "max_output_tokens": 128, "attempts_per_model": 1},
        "unavailable_secondary_policy": "run-primary-only-controls-no-substitution",
        "sampling": "fresh-seeded-non-IID-development-challenges",
        "statistical_certificate": False, "automatic_promotion": False,
        "weights_modified": False, "host_profiles_modified": False,
        "monetary_objective": False, "network_opt_in": args.allow_network,
        "upstream_cancellation_guaranteed": False,
        "on_http_429": "stop-study-no-retry",
        "hidden_native_token_bound_proven": False,
        "excluded_components": [
            "earlier studies and coding/review model calls outside this scripted experiment",
            "unobserved upstream internal requests, proprietary templates and hidden computation",
        ],
        "python": sys.version,
    }
    write_json(output / "manifest.json", manifest)
    if not args.allow_network:
        write_json(output / "status.json", {"status": "prepared_only", "attempts": 0})
        print(f"Prepared only; no network calls: {output}", flush=True)
        return 0

    clients = {
        model: make_client(
            args.base_url, model, transports[model], allow_network=True, max_output_tokens=limits.max_output_tokens,
            expected_model=reported_models[model],
            max_request_bytes=limits.max_request_bytes, max_response_bytes=limits.max_response_bytes,
            timeout=limits.call_seconds,
        ) for model in (args.primary, args.secondary)
    }
    budget = StudyBudget(maximum, args.study_seconds, args.reference_stop)
    ready = {}
    for label, model in (("primary", args.primary), ("secondary", args.secondary)):
        client = make_client(
            args.base_url, model, transports[model], allow_network=True, max_output_tokens=128,
            expected_model=reported_models[model],
            max_request_bytes=limits.max_request_bytes, max_response_bytes=limits.max_response_bytes,
            timeout=limits.call_seconds,
        )
        seconds = budget.reserve(tokens.count_tokens(wire(client.request(READINESS))), limits.call_seconds)
        if not seconds:
            ready[label] = False
            continue
        reply, record = capture_call(client, READINESS, output / "preflight" / label,
                                     stage="readiness", seconds=seconds)
        budget.observe(record)
        try:
            ready[label] = reply.ok and visible_text(reply.body).strip() == "READY"
        except (ValueError, TypeError, KeyError):
            ready[label] = False
        reason = "passed" if ready[label] else record["reason"] if not reply.ok else "unexpected_readiness_text"
        print(f"Readiness {label}: {reason}", flush=True)
        if label == "primary" and not ready[label]:
            break
    write_json(output / "readiness.json", ready)
    if not ready.get("primary"):
        write_json(output / "status.json", {"status": "primary_unavailable", **budget.snapshot()})
        return 2

    enabled = {
        arm.name: arm for arm in policies
        if ready.get("secondary") or (arm.writer == args.primary and arm.critic == args.primary)
    }
    cases_by_id = {case.id: case for case in cases}
    completed = []
    stopped = False
    for case_id, name in schedule:
        if name not in enabled:
            continue
        case = cases_by_id[case_id]
        result, _ = run_policy(
            case.prompt, enabled[name], output / "runs" / case_id / name, clients, limits,
            reserve=budget.reserve, observe=budget.observe,
        )
        completed.append({"case_id": case_id, "arm": name, "status": result["status"]})
        write_json(output / "progress.json", {"runs": completed, **budget.snapshot()})
        print(f"{len(completed):02d} {case_id} {name}: {result['status']} "
              f"({result['attempts']} calls, {result['elapsed_seconds']:.2f}s)", flush=True)
        if result["status"] == "study_limit" or budget.incomplete or budget.halt_reason:
            stopped = True
            break
    write_json(output / "status.json", {
        "status": "stopped_at_limit" if stopped else "finished",
        "enabled_arms": list(enabled), "completed_runs": len(completed),
        "planned_enabled_runs": args.tasks * len(enabled), **budget.snapshot(),
    })
    from refinement.audit import audit_study
    audit = audit_study(output)
    write_json(output / "audit.json", audit)
    print(json.dumps(audit, indent=2, ensure_ascii=True), flush=True)
    return 0 if audit["audit_status"] == "consistent" else 3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--primary", default="gpt-6-astra")
    parser.add_argument("--secondary", default="claude-opus-5.5")
    parser.add_argument("--secondary-api", choices=("responses", "messages"), default="messages")
    parser.add_argument("--secondary-reported-model", help="Explicit exact native response model ID, if different")
    parser.add_argument("--arms", nargs="+", choices=(
        "single_primary", "single_secondary", "resample_primary", "refine_primary", "cross_refine"))
    parser.add_argument("--base-url", default="http://127.0.0.1:15721/v1")
    parser.add_argument("--seed", type=int, default=20261005)
    parser.add_argument("--tasks", type=int, default=8)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--max-total-calls", type=int, default=114)
    parser.add_argument("--call-seconds", type=float, default=60)
    parser.add_argument("--policy-seconds", type=float, default=240)
    parser.add_argument("--study-seconds", type=float, default=1200)
    parser.add_argument("--reference-stop", type=int, default=500000)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--audit-only", action="store_true", help="Recount saved evidence without network calls")
    parser.add_argument("--execute-frozen", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.audit_only:
        if args.allow_network or args.execute_frozen:
            parser.error("--audit-only cannot be combined with execution flags")
        from refinement.audit import audit_study
        report = audit_study(args.output.resolve())
        print(json.dumps(report, indent=2, ensure_ascii=True), flush=True)
        return 0 if report["audit_status"] == "consistent" else 3
    if args.execute_frozen:
        return execute(args)
    # Validate before creating output. Network remains disabled unless explicitly opted in.
    Limits(max_output_tokens=args.max_output_tokens, call_seconds=args.call_seconds,
           policy_seconds=args.policy_seconds)
    ResponsesTransport(args.base_url, args.primary)
    make_client(args.base_url, args.secondary, args.secondary_api, expected_model=args.secondary_reported_model)
    generate_cases(args.seed, args.tasks)
    if (args.primary == args.secondary or not 0 < args.study_seconds <= 3600
            or not 0 < args.reference_stop <= 10_000_000 or not 0 < args.max_total_calls <= 1000):
        raise ValueError("invalid experiment control")
    frozen_script = freeze(args.output.resolve())
    env = child_environment()
    env["BRAINSPACE_TOKENIZER_FILE"] = str(args.output.resolve() / "cl100k_base.tiktoken")
    forwarded = []
    for name, value in vars(args).items():
        if name == "execute_frozen":
            continue
        if value is None:
            continue
        flag = "--" + name.replace("_", "-")
        if type(value) is bool:
            if value:
                forwarded.append(flag)
        elif type(value) is list:
            forwarded.extend([flag, *value])
        else:
            forwarded.extend([flag, str(args.output.resolve() if name == "output" else value)])
    command = [sys.executable, str(frozen_script), *forwarded, "--execute-frozen"]
    # Per-call subprocess deadlines and StudyBudget enforce the runtime stop.
    return subprocess.call(command, env=env, cwd=frozen_script.parent,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


if __name__ == "__main__":
    raise SystemExit(main())
