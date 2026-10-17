#!/usr/bin/env python
"""Durable token-efficiency controller with synthetic and real read-only hosts.

Examples:
  python token_efficiency.py --db experiment.sqlite initialize --synthetic
  python token_efficiency.py --db experiment.sqlite propose
  python token_efficiency.py --db experiment.sqlite confirm POLICY_ID --samples 256
  python token_efficiency.py --db experiment.sqlite promote TRIAL_ID
  python token_efficiency.py --db experiment.sqlite status
  python token_efficiency.py --db experiment.sqlite plan-feasibility --samples 8

initialize-runtime admits an enabled local policy after deterministic safety
checks, NOT a model-quality test. learn-runtime runs one bounded paired trial
through the installed RuntimeSession and fixed read-only gateway host. It never
promotes, runs shell commands, discovers credentials, or loads evaluator code.
Explicit loopback authority is required. Optional --jev discloses only generated
policy settings to TypeSafe; TYPESAFE_API_KEY must already be configured.

initialize-profile / learn-profile use closed full RuntimePolicy compositions
with explicitly pinned resources. Their default initial policy is truly off;
the existing local/synthetic commands and promotion gates remain unchanged.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any
import uuid

from brainspace.optimizer import Optimizer, OptimizerError


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise OptimizerError("invalid_arguments")


def _parser():
    parser = _Parser(description=__doc__)
    parser.add_argument("--db", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("initialize")
    initialize.add_argument("--synthetic", action="store_true")
    commands.add_parser("status")
    commands.add_parser("propose")
    feasibility = commands.add_parser(
        "plan-feasibility", help="Read-only necessary gate/budget bounds, not execution authority.")
    selection = feasibility.add_mutually_exclusive_group(required=True)
    selection.add_argument("--samples", type=int)
    selection.add_argument("--trial-id", type=int)
    feasibility.add_argument("--screening", action="store_true",
                             help="Include one prospective screening slot; never call a screener.")
    confirm = commands.add_parser("confirm")
    confirm.add_argument("candidate_id")
    confirm.add_argument("--samples", type=int, default=256)
    confirm.add_argument("--task-prefix")
    promote = commands.add_parser("promote")
    promote.add_argument("trial_id", type=int)
    cancel = commands.add_parser("cancel")
    cancel.add_argument("trial_id", type=int)
    rollback = commands.add_parser("rollback")
    rollback.add_argument("--expected-version", type=int, required=True)
    demo = commands.add_parser("demo")
    demo.add_argument("--synthetic", action="store_true")
    demo.add_argument("--samples", type=int, default=256)
    for name in ("initialize-runtime", "learn-runtime", "initialize-profile", "learn-profile"):
        runtime = commands.add_parser(name)
        runtime.add_argument("--manifest", required=True, help="Data-only read-only task manifest.")
        runtime.add_argument("--output", required=True, help="New private evidence directory.")
        runtime.add_argument("--base-url", required=True, help="Existing credential-free loopback bridge.")
        runtime.add_argument("--model", required=True)
        runtime.add_argument("--allow-network", action="store_true")
        runtime.add_argument("--max-calls-per-arm", type=int, default=8)
        runtime.add_argument("--max-tool-calls", type=int, default=16)
        runtime.add_argument("--max-output-tokens", type=int, default=2048)
        runtime.add_argument("--token-cap", type=int, default=100000)
        runtime.add_argument("--max-search-calls", type=int, default=256)
        runtime.add_argument("--max-candidates", type=int, default=6)
        runtime.add_argument("--order-seed", type=int, default=0)
        runtime.add_argument("--timeout", type=float, default=45)
        runtime.add_argument("--reasoning-effort",
                             choices=("none", "minimal", "low", "medium", "high", "xhigh"))
        if name in ("initialize-runtime", "initialize-profile"):
            runtime.add_argument("--policy", help=(
                "RuntimePolicy JSON file; default is true optimizer off."
                if name == "initialize-profile" else
                "Versioned RequestPolicy JSON file; default is conservative V3."))
        else:
            runtime.add_argument("--task-id", action="append", required=True,
                                 help="Single-use task ID returned by initialize-runtime; repeat for a batch.")
            runtime.add_argument("--jev", action="store_true",
                                 help="Authorize one external advisory screen of policy settings only.")
        if name.endswith("-profile"):
            runtime.add_argument("--ponytail-export", required=True)
            runtime.add_argument("--headroom-cache", required=True)
            runtime.add_argument("--headroom-assets", required=True)
            if name == "learn-profile":
                runtime.add_argument("--candidate-id",
                                     help="One declared neighbor instead of advisory selection; cannot combine with --jev.")
    return parser


def _digest(value):
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_data(path, limit=16777216):
    from brainspace.runtime_io import parse_json, safe_root

    with safe_root(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise OptimizerError("runtime_input_too_large")
    return parse_json(raw.decode("utf-8"))


def _write_data(path, value):
    from brainspace.runtime_io import safe_root

    with safe_root(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _runtime_setup(args, *, profile_resources=None):
    from brainspace import runtime as runtime_module
    from brainspace.learning_runtime import RuntimeLearningManifest
    from brainspace.optimizer import OptimizerConfig, reference_measurement
    from brainspace.readonly_learning_host import ORACLE, ReadonlyGatewayHost

    if not args.allow_network:
        raise OptimizerError("runtime_network_opt_in_required")
    data = _read_data(args.manifest)
    host = ReadonlyGatewayHost(
        data, base_url=args.base_url, model=args.model, allow_network=True,
        max_calls=args.max_calls_per_arm, max_tool_calls=args.max_tool_calls,
        max_output_tokens=args.max_output_tokens, timeout=args.timeout,
        reasoning_effort=args.reasoning_effort,
        **({"document_tools": True} if profile_resources is not None else {}),
    )
    root = Path(runtime_module.__file__).parent
    sources = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(root.rglob("*.py")) if "tests" not in p.relative_to(root).parts}
    sources["../token_efficiency.py"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    environment = {"host_id": host.identity, "sources": sources, "order_seed": args.order_seed}
    if profile_resources is not None:
        from brainspace.runtime_policy import EXECUTION_CONTRACT, VERSION
        environment.update(resources=profile_resources.to_manifest(),
                           policy_family=VERSION, execution_contract=EXECUTION_CONTRACT)
    config = OptimizerConfig(
        measurement=reference_measurement(), oracle_id=ORACLE,
        workload_id="declared-readonly-tasks:" + _digest(list(host.task_ids)),
        environment_id=("readonly-profile-runtime:" if profile_resources is not None
                        else "readonly-runtime:") + _digest(environment),
        model_id=args.model, token_cap=args.token_cap,
        max_candidates=args.max_candidates, max_calls=args.max_search_calls,
        calls_per_pair=2 * args.max_calls_per_arm, synthetic_only=False,
    )
    inputs = (config, host.identity, tuple((task, host.task_digest(task)) for task in host.task_ids),
              args.max_calls_per_arm, args.order_seed)
    manifest: RuntimeLearningManifest
    if profile_resources is not None:
        from brainspace.learning_runtime import ProfileLearningManifest
        manifest = ProfileLearningManifest(*inputs, resources_id=profile_resources.identity)
    else:
        manifest = RuntimeLearningManifest(*inputs)
    return data, host, manifest


def _admit_runtime_policy(policy, config, reservation):
    """Schema/protection admission only; no tasks, oracle calls or quality labels."""
    from brainspace import tokens
    from brainspace.optimizer import BaselineValidation
    from brainspace.request_policy import PROTOCOL, RequestPolicy, plan_request
    from brainspace.token_ledger import COMPLETE, TaskTrace

    request = {"model": config.model_id, "messages": [
        {"role": "system", "content": "Protected deterministic admission probe."},
        {"role": "user", "content": "Preserve exact instructions."},
    ]}
    plan = plan_request(request, policy=policy, protocol=PROTOCOL,
                        intent="exact", count=tokens.count_tokens)
    passed = (policy.enabled and RequestPolicy.from_json(policy.to_json()) == policy
              and plan.request == request and not plan.changed_message_indices)
    evidence = {"check": "schema-and-exact-passthrough-v1", "passed": passed,
                "policy": policy.to_dict(), "config_id": config.identity,
                "model_quality_tested": False, "model_calls": 0}
    return BaselineValidation(
        policy.policy_id, config.identity, config.oracle_id, passed, _digest(evidence),
        TaskTrace(reservation.task_id, policy.policy_id, config.measurement, "learning",
                  (), (), COMPLETE, reservation.learning_run_id),
    )


def _admit_profile_policy(policy, config, reservation, *, resources, host, output):
    """Exercise actual materialization with primary transport disabled.

    This is safety admission only. Exact intent deliberately bypasses lossy
    components; both selected workers are separately readied before a real pair.
    """
    from brainspace.learning_runtime import _trace
    from brainspace.optimizer import BaselineValidation
    from brainspace.runtime import RuntimeSession
    from brainspace.runtime_policy import RuntimePolicy

    if type(policy) is not RuntimePolicy:
        raise OptimizerError("runtime_profile_required")
    resources.validate(policy)
    output.mkdir()
    workspace = output / "workspace"
    workspace.mkdir()
    session = RuntimeSession(
        workspace=workspace, output=output / "runtime", session_id="profile-admission",
        task_id=reservation.task_id, transport=replace(host._transport, allow_network=False),
        runtime_policy=policy, runtime_resources=resources, phase="learning",
        learning_run_id=reservation.learning_run_id, harness_id="profile-safety-admission-v1",
        max_calls=1)
    request = {"model": config.model_id, "messages": [
        {"role": "system", "content": "Protected deterministic admission probe."},
        {"role": "user", "content": "Preserve exact instructions."}]}
    result = None
    try:
        reply = session.invoke(request, intent="exact", stable_prefix_messages=2)
        result = session.finish()
    finally:
        cleanup = session.close()
    preparation = _read_data(session.output / "preparations.jsonl")
    augmented, _ = session._augment(request)
    if preparation["prepared"] not in (request, augmented):
        raise OptimizerError("protected_admission_text_changed")
    off = policy.backend == policy.instruction == "none"
    passed = (
        reply.reason == "network_not_allowed" and result is not None
        and result["model_calls"] == 0 and result["trace_complete"]
        and result["component"]["complete"] and cleanup["complete"]
        and result["trace"]["policy_id"] == policy.policy_id
        and (not off or session.transport.encode(preparation["prepared"]) == session.transport.encode(request)))
    receipt = {
        "check": "actual-profile-materialization-no-primary-transport-v1",
        "policy_id": policy.policy_id, "resources_id": resources.identity,
        "passed": passed, "true_optimizer_off": off, "model_quality_tested": False,
        "model_calls": 0, "headroom_readiness_tested": False,
        "runtime_profile_id": session.profile_id,
    }
    _write_data(output / "admission.json", receipt)
    return BaselineValidation(
        policy.policy_id, config.identity, config.oracle_id, passed, _digest(receipt),
        _trace(result["trace"]))


class _PolicyScreen:
    """Record explicitly disclosed policy-only bodies, never auth headers."""

    def __init__(self, output):
        from brainspace.jev import JevClient

        self.client = JevClient(enabled=True, allow_network=True)
        self.output, self.capture_complete, self.result = output, False, None

    def decide(self, state, questions, *, data_classification):
        _write_data(self.output / "jev-disclosure.json", {
            "state": state, "questions": questions, "classification": data_classification})
        self.result = self.client.decide(state, questions, data_classification=data_classification)
        # No filesystem work after a completed response and before the
        # controller persists its accounting. Cancellation during later raw
        # receipt persistence cannot erase these already-recorded costs.
        return self.result

    def persist(self):
        result = self.result
        if result is None:
            return
        try:
            captured = asdict(result)
            key = os.getenv("TYPESAFE_API_KEY")
            raw = result.response_text
            if (not result.ok or raw is None or "\\" in raw
                    or key and key in json.dumps(captured, ensure_ascii=False)):
                # Error text and JSON-escaped metadata may reflect credentials.
                # Keep only bounded nonbody diagnostics/hash, never raw remote
                # error bodies or decoded arbitrary metadata. The controller
                # already counted the original exact bytes, not this receipt.
                captured = {
                    "ok": result.ok, "reason": result.reason,
                    "request_text": result.request_text,
                    "response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()
                        if raw is not None else None,
                    "diagnostics": asdict(result.diagnostics),
                    "raw_response_withheld": True,
                }
            _write_data(self.output / "jev-capture.json", captured)
            self.capture_complete = (
                captured.get("raw_response_withheld") is not True
                and result.request_text is not None and result.response_text is not None
                and result.diagnostics.response_complete)
        except (OSError, ValueError):
            # Do not lose already-incurred accounting because the extra raw
            # receipt failed. The controller already has the actual result.
            self.capture_complete = False


def _execute_runtime(args):
    from brainspace.learning_runtime import RuntimePairEvaluator, learn_once
    from brainspace.request_policy import RequestPolicy
    from brainspace.runtime_io import safe_root
    from brainspace.runtime_policy import ControllerPolicy

    profile = args.command in ("initialize-profile", "learn-profile")
    candidate_id = getattr(args, "candidate_id", None)
    if candidate_id is not None and args.jev:
        raise OptimizerError("candidate_and_screener_conflict")
    resources = None
    if profile:
        from brainspace.runtime_policy import RuntimePolicy
        from brainspace.runtime_resources import RuntimeResources
        if not args.allow_network:
            raise OptimizerError("runtime_network_opt_in_required")
        resources = RuntimeResources(
            ponytail_export=args.ponytail_export, headroom_cache=args.headroom_cache,
            headroom_assets=args.headroom_assets)
    data, host, manifest = _runtime_setup(args, profile_resources=resources)
    db, output = safe_root(args.db), safe_root(args.output)
    if output.exists():
        raise OptimizerError("new_runtime_output_required")
    disclosure: dict[str, Any] = {
        "synthetic_only": False, "policy_promoted": False,
        "comparison": "runtime_incumbent_vs_runtime_neighbor" if profile
                      else "enabled_local_incumbent_vs_local_neighbor",
        "sampling": "declared_fixed_tasks_not_a_population_certificate",
    }
    if profile:
        assert resources is not None
        disclosure.update(policy_family="runtime-policy-v1", resources=resources.to_manifest(),
                          composition="derived_from_frozen_policy")
    else:
        disclosure.update(not_optimizer_off_baseline=True, backend="local", ponytail=False, headroom=False)
    if args.command in ("initialize-runtime", "initialize-profile"):
        if db.exists():
            raise OptimizerError("new_runtime_registry_required")
        policy: ControllerPolicy
        if profile:
            policy = RuntimePolicy.from_dict(_read_data(args.policy, 65536)) if args.policy else RuntimePolicy()
            disclosure["initial_policy_is_optimizer_off"] = policy.backend == policy.instruction == "none"
        else:
            policy = (RequestPolicy.from_dict(_read_data(args.policy, 65536)) if args.policy
                      else RequestPolicy(version="request-policy-v3", enabled=True))
        if not profile:
            assert isinstance(policy, RequestPolicy)
            if not policy.enabled:
                raise OptimizerError("enabled_baseline_required")
        output.mkdir(parents=True)
        _write_data(output / "initialization-plan.json", {
            "manifest": manifest.to_dict(), "task_manifest": data, "policy": policy.to_dict(),
            "baseline_admission": "deterministic_safety_only_not_model_quality",
            **disclosure,
        })
        optimizer = Optimizer(db, config=manifest.config)
        validator = (lambda p, c, r: _admit_profile_policy(
            p, c, r, resources=resources, host=host, output=output / "safety-check")) \
            if profile else _admit_runtime_policy
        status = optimizer.initialize(
            policy, validator=validator, validation_call_limit=0)
        result = {**disclosure, "status": status, "task_ids": list(host.task_ids),
                  "baseline_admission": "deterministic_safety_only_not_model_quality",
                  "output": str(output)}
    else:
        task_ids = tuple(args.task_id)
        if (not task_ids or len(set(task_ids)) != len(task_ids)
                or any(task not in host.task_ids for task in task_ids)):
            raise OptimizerError("declared_unique_task_ids_required")
        feasibility = Optimizer.plan_feasibility_snapshot(
            db, sample_size=len(task_ids), screening=args.jev)
        if feasibility["config_id"] != manifest.config.identity or feasibility["synthetic_only"]:
            raise OptimizerError("runtime_configuration_mismatch")
        if feasibility["arithmetic"]["status"] == "mathematically_impossible":
            raise OptimizerError("plan_mathematically_impossible")
        if feasibility["arithmetic"]["status"] != "not_ruled_out":
            raise OptimizerError("plan_numerically_indeterminate")
        if feasibility["budget"]["status"] == "budget_exhausted":
            raise OptimizerError("call_budget_exhausted")
        if feasibility["candidate"]["status"] == "candidate_unavailable":
            raise OptimizerError("candidate_unavailable")
        if args.jev and not os.getenv("TYPESAFE_API_KEY"):
            raise OptimizerError("typesafe_api_key_required")
        existing = Optimizer.open(db)
        if existing.config != manifest.config or existing.config.synthetic_only:
            raise OptimizerError("runtime_configuration_mismatch")
        if profile:
            from brainspace.runtime_policy import decode_policy
            initial = decode_policy(json.dumps(existing.status()["champion"]["policy"]))
            if type(initial) is not RuntimePolicy:
                raise OptimizerError("runtime_profile_required")
            disclosure["incumbent_is_optimizer_off"] = initial.backend == initial.instruction == "none"
        preflight = existing.preflight_learning(task_ids, screening=args.jev)
        # This is an admission-time snapshot, not a reservation. Freeze remains
        # the authority for concurrent allocations; a later k only tightens the
        # gate. No old trial/evaluate/replay path is changed by this CLI check.
        disclosure["plan_feasibility"] = feasibility
        if candidate_id is not None and candidate_id not in preflight["available_candidate_ids"]:
            raise OptimizerError("explicit_candidate_not_proposed")
        current = Optimizer.plan_feasibility_snapshot(
            db, sample_size=len(task_ids), screening=args.jev)
        if current["snapshot_sha256"] != feasibility["snapshot_sha256"]:
            raise OptimizerError("plan_snapshot_changed")
        evaluator = RuntimePairEvaluator(
            manifest, host=host, output_root=output,
            **({"resources": resources} if profile else {}))
        _write_data(output / "task-manifest.json", data)
        optimizer = Optimizer.open(db, evaluator=evaluator)
        screener, summaries, classification = None, None, None
        if args.jev:
            screener = _PolicyScreen(output)
            summaries = {policy.policy_id: {
                "policy_settings": policy.to_dict(),
                "evidence": "Unmeasured settings only; quality and token savings are unknown.",
            } for policy in optimizer.propose()}
            classification = "sanitized"
        _write_data(output / "learning-plan.json", {
            **disclosure, "task_ids": list(task_ids), "samples": len(task_ids),
            "screening": "jev_advisory" if args.jev else
                         "explicit_declared_neighbor" if candidate_id else "deterministic_configuration_order",
            **({"candidate_id": candidate_id} if profile else {}),
            "jev_disclosure": "policy_settings_only" if args.jev else None,
            "auto_retry": False, "auto_promotion": False,
        })
        try:
            step = learn_once(
                optimizer, task_ids=task_ids, samples=len(task_ids),
                screener=screener, summaries=summaries, data_classification=classification,
                **({"candidate_id": candidate_id} if profile else {}))
        finally:
            # Even a failed/interrupted attempt has a durable accounting snapshot.
            _write_data(output / "controller-status.json", optimizer.status())
            if screener:
                screener.persist()
        result = {**disclosure, "step": step, "status": optimizer.status(),
                  "screening": "jev_advisory_with_deterministic_fallback" if args.jev
                               else "explicit_declared_neighbor" if candidate_id else "deterministic_configuration_order",
                  "jev_capture_complete": screener.capture_complete if screener else None,
                  "output": str(output)}
    _write_data(output / "command-result.json", result)
    return result


def _initialize(path):
    from evals.synthetic_efficiency import (
        BASELINE_TASK, baseline_policy, evaluate_pair, synthetic_config, validate_baseline,
    )
    optimizer = Optimizer(path, config=synthetic_config(), evaluator=evaluate_pair)
    result = optimizer.initialize(baseline_policy(), validator=validate_baseline,
                                  validation_call_limit=0, search_task_ids=[BASELINE_TASK])
    return optimizer, result


def execute(args):
    if args.command == "plan-feasibility":
        return Optimizer.plan_feasibility_snapshot(
            args.db, sample_size=args.samples, trial_id=args.trial_id, screening=args.screening)
    if args.command in ("initialize-runtime", "learn-runtime", "initialize-profile", "learn-profile"):
        return _execute_runtime(args)
    if args.command in ("initialize", "demo"):
        if not args.synthetic:
            raise OptimizerError("synthetic_opt_in_required")
        optimizer, status = _initialize(args.db)
        if args.command == "initialize":
            return status
        return optimizer.hill_climb(
            sample_size=args.samples,
            fresh_tasks=lambda trial: (
                f"synthetic-{uuid.uuid4().hex}-{i}" for i in range(trial.sample_size)),
        )
    if args.command == "confirm":
        from evals.synthetic_efficiency import ORACLE, evaluate_pair
        optimizer = Optimizer.open(args.db, evaluator=evaluate_pair)
        if not optimizer.config.synthetic_only or optimizer.config.oracle_id != ORACLE:
            raise OptimizerError("synthetic_configuration_required")
        trial = optimizer.freeze(args.candidate_id, sample_size=args.samples)
        prefix = args.task_prefix or "synthetic-" + uuid.uuid4().hex
        certificate = optimizer.evaluate(
            trial.trial_id, (f"{prefix}-{i}" for i in range(trial.sample_size)))
        return {"trial_id": trial.trial_id, "certificate": certificate.to_dict(),
                "synthetic_only": True}
    optimizer = Optimizer.open(args.db)
    if args.command == "status":
        return optimizer.status()
    if args.command == "propose":
        return {"candidates": [{"policy_id": p.policy_id, "policy": p.to_dict()}
                               for p in optimizer.propose()]}
    if args.command == "promote":
        return optimizer.promote(args.trial_id)
    if args.command == "cancel":
        return optimizer.cancel(args.trial_id)
    if args.command == "rollback":
        return optimizer.rollback(expected_version=args.expected_version)
    raise OptimizerError("invalid_arguments")


def main(argv=None):
    try:
        result = execute(_parser().parse_args(argv))
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "reason": "cancelled"}))
        return 130
    except OptimizerError as error:
        print(json.dumps({"ok": False, "reason": str(error)}))
        return 2
    except (ValueError, TypeError, OSError, sqlite3.Error):
        # Never echo filesystem, evaluator or provider errors/raw task content.
        print(json.dumps({"ok": False, "reason": "controller_operation_failed"}))
        return 2
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
