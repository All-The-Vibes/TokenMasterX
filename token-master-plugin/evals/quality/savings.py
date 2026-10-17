"""Offline evidence audit for the explicit stateless quality-study adapter.

Recounts literal captured bodies, never summary totals; executes no archived
source, generated code, models, or graders. Saved outcome evidence is hash-bound,
not authenticated by this checker. A previously retained evidence digest detects
later changes; an attacker rewriting an entire unsigned corpus is out of scope.

Reference-body, explicit-context and bridge-reported units remain separate.
Non-IID challenge repetitions do not become independent confirmation tasks.
This module cannot issue a statistical certificate or change a policy.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import re

from brainspace import tokens
from brainspace.optimizer import reference_measurement
from brainspace.token_ledger import COMPLETE, CallRecord, MeasurementIdentity, TaskTrace, measure_call

from .cases import digest, safe_path, safe_root
from .measurement import context_texts, input_context_text
from .responses import parse_json
from .runner import _native_actions

PROTOCOL = "offline-paired-savings-audit-v1"
HARNESS = "stateless-loopback-responses-eval-v1"
METRICS = ("api_body_reference", "explicit_context_reference", "provider_reported")


class AuditError(ValueError):
    """Content-free failure reason; never include raw responses or credentials."""


def _require(condition, reason):
    if not condition:
        raise AuditError(reason)


def _count(value):
    return type(value) is int and value >= 0


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _same(left, right):
    """JSON type preserving: unlike Python ==, 1, 1.0 and True differ."""
    return digest(left) == digest(right)


def _json(text):
    try:
        return parse_json(text)
    except (ValueError, TypeError, RecursionError) as error:
        raise AuditError("invalid_json_artifact") from error


def _sum(values):
    values = list(values)
    return None if any(v is None for v in values) else sum(values)


def reported_usage(response):
    """Validate arithmetic only, NOT the bridge's upstream provenance.

    Missing counters/breakdowns are unknown. Reasoning and cached counts are
    subsets of output/input respectively; never add or discount them.
    """
    usage = response.get("usage") if type(response) is dict else None
    if usage is None:
        return None
    _require(type(usage) is dict, "invalid_reported_usage")
    incoming, outgoing, total = (usage.get(k) for k in ("input_tokens", "output_tokens", "total_tokens"))
    _require(all(_count(x) for x in (incoming, outgoing, total)), "invalid_reported_counts")
    _require(total == incoming + outgoing, "inconsistent_reported_total")
    result = {"input_tokens": incoming, "output_tokens": outgoing, "total_tokens": total}
    for key, field, bound, target in (
        ("input_tokens_details", "cached_tokens", incoming, "cached_input_tokens"),
        ("output_tokens_details", "reasoning_tokens", outgoing, "reasoning_tokens"),
    ):
        details = usage.get(key)
        _require(details is None or type(details) is dict, "invalid_usage_breakdown")
        value = details.get(field) if details is not None else None
        _require(value is None or _count(value) and value <= bound, "invalid_usage_subset")
        result[target] = value
    return result


def _totals(rows):
    rows = list(rows)
    result = {key: _sum(r.get(key) for r in rows) for key in
              ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens")}
    result["total_tokens"] = _sum([result["input_tokens"], result["output_tokens"]])
    incoming = [r.get("peak_input_tokens", r.get("input_tokens")) for r in rows]
    result["peak_input_tokens"] = None if any(v is None for v in incoming) else max(incoming, default=0)
    result["calls"] = sum(r.get("calls", 1) for r in rows)
    return result


class _Artifacts:
    def __init__(self, root):
        self.root = safe_root(root)
        _require(self.root.is_dir(), "study_directory_missing")
        self.hashes = {}

    def path(self, relative):
        relative = safe_path(relative.replace("\\", "/"))
        path = safe_root(self.root / relative)
        path.resolve().relative_to(self.root.resolve())
        return path

    def read(self, relative):
        path = self.path(relative)
        _require(path.is_file(), "artifact_missing")
        with path.open("rb") as stream:
            data = stream.read(64 * 1024 * 1024 + 1)
        _require(len(data) <= 64 * 1024 * 1024, "artifact_size_limit")
        key = path.relative_to(self.root).as_posix()
        fingerprint = _sha(data)
        _require(self.hashes.get(key, fingerprint) == fingerprint, "artifact_changed_during_audit")
        self.hashes[key] = fingerprint
        return data

    def json(self, relative):
        return _json(self.read(relative).decode("utf-8"))

    def workspace(self, relative):
        root = self.path(relative)
        _require(root.is_dir(), "workspace_missing")
        files = {}
        for path in root.rglob("*"):
            safe_root(path)  # Includes directory junctions; never follow them.
            if path.is_file():
                _require(len(files) < 256, "workspace_file_limit")
                data = self.read(path.relative_to(self.root).as_posix())
                files[path.relative_to(root).as_posix()] = _sha(data)
        return files

    def recheck(self):
        # Bind one stable read of each input; not a filesystem snapshot or signature.
        for relative in tuple(self.hashes):
            self.read(relative)


def _frozen_sources(files, manifest):
    _require(manifest.get("source_manifest") == "source-manifest.json", "unsupported_source_manifest")
    raw_sources = files.json("source-manifest.json")
    _require(type(raw_sources) is dict and 1 <= len(raw_sources) <= 512, "invalid_source_inventory")
    # The original Windows snapshot used str(Path), not portable POSIX paths.
    sources = {safe_path(key.replace("\\", "/")): value for key, value in raw_sources.items()}
    _require(len({key.casefold() for key in sources}) == len(raw_sources), "duplicate_source_path")
    for relative, expected in sources.items():
        _require(_sha(files.read("source/token-master-plugin/" + safe_path(relative))) == expected,
                 "frozen_source_mismatch")
    for required in ("evals/run_quality.py", "evals/quality/runner.py", "evals/quality/responses.py",
                     "evals/quality/measurement.py", "evals/quality/oracle.py", "evals/quality/cases.py"):
        _require(required in sources, "incomplete_source_inventory")
    oracle = digest({name: sources["evals/quality/" + name] for name in ("oracle.py", "cases.py")})
    _require(manifest.get("oracle_id") == oracle, "oracle_source_identity_mismatch")
    _require(_sha(files.read("cl100k_base.tiktoken")) == tokens.VOCABULARY_SHA256,
             "vocabulary_mismatch")


def _grid(files, manifest):
    _require(manifest.get("schema_version") == 1 and type(manifest["schema_version"]) is int,
             "unsupported_study_schema")
    _require(manifest.get("status") == "complete" and manifest.get("capture_complete") is True,
             "study_not_complete")
    _require(manifest.get("metrics_predeclared", {}).get("primary") ==
             "complete-json-body-text/utf8-ordinary", "unsupported_primary_protocol")
    cases, arms, repeats = manifest.get("case_identities"), manifest.get("arms"), manifest.get("repeats")
    _require(type(cases) is dict and cases and type(arms) is dict and len(arms) >= 2, "invalid_study_grid")
    _require(type(repeats) is int and 1 <= repeats <= 1000 and
             len(cases) * len(arms) * repeats <= 10000, "invalid_repetition_count")
    _require(all(re.fullmatch(r"[A-Za-z0-9_-]{1,80}", name) for name in (*cases, *arms)),
             "invalid_case_or_arm_name")
    expected = {(rep, case, arm) for rep in range(repeats) for case in cases for arm in arms}
    order = manifest.get("order")
    _require(type(order) is list and len(order) == len(expected), "incomplete_run_inventory")
    actual = []
    for item in order:
        _require(type(item) is dict and type(item.get("rep")) is int, "invalid_run_inventory")
        key = (item["rep"], item.get("case"), item.get("arm"))
        _require(key in expected, "unexpected_run")
        _require(item.get("task_id") == f'{manifest["study_id"]}:{key[0]}:{key[1]}',
                 "pair_task_identity_mismatch")
        actual.append(key)
    _require(len(set(actual)) == len(actual) and set(actual) == expected, "duplicate_or_missing_run")
    _require(type(manifest.get("completed_runs")) is int and manifest["completed_runs"] == len(expected),
             "completed_run_count_mismatch")
    expected_names = {f"r{rep}-{case}-{arm}" for rep, case, arm in expected}
    runs = files.path("runs")
    _require(runs.is_dir() and {p.name for p in runs.iterdir()} == expected_names, "run_directory_mismatch")
    _require(type(manifest.get("max_calls_per_task")) is int and
             1 <= manifest["max_calls_per_task"] <= 1000, "invalid_call_limit")
    return order


def _reviews(files, enabled):
    if not enabled:
        return {}, None
    mapping = files.json("blind-review/mapping.json")
    document = files.json("blind-review/verdicts.json")
    answers = files.json("blind-review/answers.json")
    verdicts = document.get("verdicts")
    _require(type(mapping) is dict and type(verdicts) is dict and set(mapping) == set(verdicts),
             "review_inventory_mismatch")
    _require(type(answers) is list, "invalid_blinded_answer_inventory")
    answer_map = {entry["review_id"]: entry["answer"] for entry in answers}
    _require(len(answer_map) == len(answers) and set(answer_map) == set(mapping), "blinded_answer_inventory_mismatch")
    resolved = {}
    for review_id, entry in mapping.items():
        relative = safe_path(entry["result"].replace("\\", "/"))
        verdict = verdicts[review_id]
        _require(relative not in resolved and type(verdict.get("success")) is bool,
                 "invalid_review_verdict")
        _require(verdict.get("status") in ("correct", "incorrect", "not_attempted") and
                 verdict["success"] == (verdict["status"] == "correct"), "invalid_review_status")
        _require(verdict.get("answer_sha256") == entry.get("answer_sha256"), "review_hash_mismatch")
        # The saved blinded-review artifact used sorted json.dumps with default
        # separators, unlike cases.digest's compact JSON. Pin that ONE protocol.
        original_hash = _sha(json.dumps(answer_map[review_id], sort_keys=True, ensure_ascii=True,
                                       allow_nan=False).encode("utf-8"))
        _require(verdict.get("answer_sha256") == original_hash, "blinded_answer_hash_mismatch")
        resolved[relative] = {"id": review_id, **verdict,
                              "canonical_answer_sha256": digest(answer_map[review_id])}
    metadata = {k: document.get(k) for k in (
        "reviewer", "method", "scope", "not_human_review", "not_formal_proof_checker",
        "not_jev_score", "independent_model_weights_claimed")}
    metadata["answer_hash_protocol"] = "json-sorted-ensure-ascii-default-separators-v1"
    return resolved, metadata


def _capture(capture, expected_model):
    _require(type(capture) is dict and capture.get("complete") is True and
             type(capture.get("input")) is str and type(capture.get("output")) is str,
             "incomplete_capture")
    request = _json(capture["input"])
    _require(type(request) is dict and request.get("model") == expected_model, "request_model_mismatch")
    _require(not request.get("previous_response_id") and not request.get("conversation") and
             request.get("stream") is False and request.get("store") is False, "unmaterialized_protocol")
    try:
        response = parse_json(capture["output"])
    except (ValueError, TypeError, RecursionError):
        response = None  # Fully captured HTTP failures can have non-JSON bodies.
    if type(response) is dict and response.get("object") == "response":
        _require(response.get("model") == expected_model, "response_model_mismatch")
    if capture.get("reason") == "ok":
        _require(type(response) is dict and response.get("object") == "response" and
                 response.get("status") == "completed" and type(response.get("output")) is list,
                 "invalid_completed_response")
    incoming = input_context_text(request)  # Fails on opaque/multimodal inputs.
    explicit = {"input_tokens": tokens.count_tokens(incoming), "output_tokens": None}
    try:
        _, outgoing = context_texts(request, response)
        explicit["output_tokens"] = tokens.count_tokens(outgoing)
    except (ValueError, TypeError, KeyError, AttributeError):
        pass  # Complete explicit output is unknown, not empty, for encrypted reasoning.
    metrics = {
        "api_body_reference": {"input_tokens": tokens.count_tokens(capture["input"]),
                               "output_tokens": tokens.count_tokens(capture["output"])},
        "explicit_context_reference": explicit,
        "provider_reported": reported_usage(response) or {"input_tokens": None, "output_tokens": None},
    }
    return request, response, metrics


def _history(request, previous, action, provider_call_id):
    """Account for every replayed action, allowing only tool-output text views.

    The pinned runner keeps protected messages and complete call/result pairs.
    It appends either one call/result pair or one final answer/new user stage.
    A later history cannot be used to hide an omitted earlier invocation.
    """
    incoming = request.get("input")
    _require(type(incoming) is list, "unsupported_history")
    current, call_ids = [], set()
    for item in incoming:
        _require(type(item) is dict, "invalid_history_item")
        if item.get("type") == "function_call":
            _require(set(item) == {"type", "call_id", "name", "arguments"} and
                     type(item["call_id"]) is str and item["call_id"] and
                     item["call_id"] not in call_ids and type(item["arguments"]) is str,
                     "invalid_or_duplicate_history_call")
            call_ids.add(item["call_id"])
            current.append({**item, "arguments": _json(item["arguments"])})
        elif item.get("type") == "function_call_output":
            _require(set(item) == {"type", "call_id", "output"} and type(item["output"]) is str and
                     current and current[-1].get("type") == "function_call" and
                     item["call_id"] == current[-1]["call_id"], "orphaned_history_output")
            # Safe views can rewrite earlier tool text, but not its pair/position.
            current.append({**item, "output": None})
        else:
            _require(set(item) == {"role", "content"} and item["role"] in
                     ("system", "developer", "user", "assistant") and type(item["content"]) is str,
                     "unsupported_history_message")
            current.append(item)
    if previous is None:
        _require(len(current) == 2 and current[0].get("role") == "system" and
                 current[1].get("role") == "user", "orphaned_initial_history")
        return current
    _require(action is not None and len(current) == len(previous) + 2 and
             _same(current[:len(previous)], previous), "history_progression_mismatch")
    if action["name"] == "answer":
        answer_message = {"role": "assistant",
                          "content": json.dumps(action["arguments"]["content"], ensure_ascii=False)}
        _require(_same(current[-2], answer_message) and current[-1].get("role") == "user",
                 "answer_stage_progression_mismatch")
    else:
        call, output = current[-2:]
        _require(call.get("type") == "function_call" and output.get("type") == "function_call_output" and
                 call.get("name") == action["name"] and _same(call.get("arguments"), action["arguments"]),
                 "captured_action_history_mismatch")
        # Plain-text fallback actions have a locally minted ID, absent from the
        # response. Its first observed pair is still bound on subsequent replays.
        _require(provider_call_id is None or call.get("call_id") == provider_call_id,
                 "captured_call_id_history_mismatch")
    return current


def _grade(files, relative, result, manifest, reviews, events):
    grade = result["grade"]
    _require(grade.get("case_identity") == result["case_identity"] and
             grade.get("oracle_identity") == manifest["oracle_id"], "grade_identity_mismatch")
    _require(grade.get("evidence_digest") == digest(
        {k: v for k, v in grade.items() if k != "evidence_digest"}), "grade_evidence_digest_mismatch")
    evidence = grade.get("evidence", {})
    _require(_same(evidence.get("answer"), result.get("answer")) and
             _same(evidence.get("events"), result.get("events")) and
             _same(result.get("events"), events), "answer_or_event_mismatch")
    _require(evidence.get("workspace") == files.workspace(relative + "/workspace"), "workspace_digest_mismatch")
    answers = [e["arguments"]["content"] for e in events if e["name"] == "answer"]
    _require(_same(result.get("stage_answers"), answers), "stage_answer_mismatch")
    _require(_same(result.get("answer"), answers[-1] if answers else None), "final_answer_not_emitted")
    prior = answers[:-1] if answers else []
    _require(_same(evidence.get("stage_answers"), prior), "grade_stage_mismatch")
    outcome = grade.get("success")
    _require(outcome is None or type(outcome) is bool, "invalid_outcome")
    _require(outcome == {"passed": True, "failed": False}.get(grade.get("status")), "outcome_status_mismatch")
    if result.get("failure") is not None:
        _require(outcome is False, "runner_failure_not_graded_failed")
    review = reviews.get(relative + "/result.json")
    if review is not None:
        _require(outcome is None and grade["status"] == "needs_blind_review",
                 "review_overrides_graded_outcome")
        _require(review.get("canonical_answer_sha256") == digest(result.get("answer")), "review_answer_mismatch")
        outcome = review["success"]
    return outcome, review.get("id") if review is not None else None


def _run(files, manifest, item, measurement, reviews, seen_calls, seen_responses, seen_outputs):
    rep, case, arm = item["rep"], item["case"], item["arm"]
    relative = f"runs/r{rep}-{case}-{arm}"
    result = files.json(relative + "/result.json")
    _require(result.get("case_id") == case and result.get("case_identity") == manifest["case_identities"][case]
             and result.get("arm", {}).get("name") == arm and result.get("task_id") == item["task_id"],
             "run_identity_mismatch")
    _require(result.get("model") == manifest["model_requested"], "run_model_mismatch")
    _require(result.get("coverage") == COMPLETE and result.get("regime_valid") is True and
             result.get("incomplete_calls") == [], "run_coverage_or_environment_invalid")
    raw = result["trace"]
    trace = TaskTrace(**{**raw, "measurement": MeasurementIdentity(**raw["measurement"]),
                         "calls": tuple(CallRecord(**c) for c in raw["calls"])})
    trace.validate_complete()
    _require(trace.measurement == measurement and trace.policy_id == manifest["arms"][arm]["policy_id"]
             and trace.task_id == item["task_id"] and trace.phase == "learning" and
             trace.learning_run_id == manifest["study_id"], "trace_identity_mismatch")
    _require(result.get("totals") == trace.totals().to_dict(), "stored_totals_mismatch")
    captures = [_json(line) for line in files.read(relative + "/captures.jsonl").decode("utf-8").splitlines()]
    _require(1 <= len(captures) <= manifest["max_calls_per_task"] and
             [c.get("call_id") for c in captures] == list(trace.expected_call_ids) ==
             [c.call_id for c in trace.calls], "capture_inventory_mismatch")
    rows, events, controls, call_seconds, system_prompts = [], [], set(), 0.0, set()
    history, action, provider_call_id, parse_failed = None, None, None, False
    user_stages = []
    for index, (capture, call) in enumerate(zip(captures, trace.calls)):
        _require(call.call_id == f"{trace.task_id}:{trace.policy_id}:{index}" and
                 call.call_id not in seen_calls, "duplicate_or_out_of_order_call")
        seen_calls.add(call.call_id)
        _require(call.model_id == manifest["model_requested"] and call.harness_id == HARNESS and
                 call.role == "primary" and call.attempt_id == "1", "unsupported_call_adapter")
        counted = measure_call(measurement, tokens.count_tokens,
                               input_text=capture.get("input"), output_text=capture.get("output"),
                               **{k: v for k, v in asdict(call).items() if k not in (
                                   "measurement_id", "reference_input_tokens", "reference_output_tokens",
                                   "input_sha256", "output_sha256")})
        _require(counted == call, "captured_body_count_or_hash_mismatch")
        request, response, metrics = _capture(capture, call.model_id)
        _require(capture.get("reason") in ("ok", "http_error", "incomplete_model_response", "invalid_response"),
                 "unsupported_capture_reason")
        _require(call.completion_status == ("succeeded" if capture.get("reason") == "ok" else "failed"),
                 "call_status_mismatch")
        if capture["reason"] != "ok":
            _require(index == len(captures) - 1 and result.get("failure") == capture["reason"] and
                     result["grade"].get("success") is False, "terminal_capture_failure_mismatch")
        history = _history(request, history, action, provider_call_id)
        controls.add(digest({k: v for k, v in request.items() if k not in ("input", "instructions")}))
        _require("instructions" not in request, "unsupported_instruction_surface")
        user_stages = [digest(i) for i in request["input"] if i.get("role") == "user"]
        system_prompts.add(digest([i for i in request["input"] if i.get("role") in ("system", "developer")]))
        response_id = response.get("id") if type(response) is dict else None
        if response_id is not None:
            _require(type(response_id) is str and response_id and response_id not in seen_responses,
                     "duplicate_or_invalid_response_id")
            seen_responses.add(response_id)
        seen_outputs.add(call.output_sha256)
        seconds = capture.get("elapsed_seconds")
        _require(type(seconds) in (int, float) and math.isfinite(seconds) and seconds >= 0, "invalid_call_time")
        call_seconds += seconds
        rows.append(metrics)
        if capture.get("reason") == "ok":
            try:
                name, args, _ = _native_actions(response)
                if name == "answer":
                    _require(set(args) == {"content"}, "invalid_answer_arguments")
                    content = args["content"]
                    if type(content) is str:
                        try:
                            content = parse_json(content)
                        except ValueError:
                            pass
                    args = {"content": content}
                action = {"name": name, "arguments": args}
                events.append(action)
                native = [entry for entry in response["output"] if entry.get("type") == "function_call"]
                provider_call_id = native[0]["call_id"] if native else None
            except (ValueError, TypeError, KeyError, AttributeError):
                parse_failed = True
                _require(index == len(captures) - 1 and result.get("failure") == "invalid_model_action",
                         "unrecorded_invalid_model_action")
    failure = result.get("failure")
    if failure is None:
        _require(action is not None and action["name"] == "answer", "missing_terminal_answer")
    elif failure == "call_limit_reached":
        _require(len(captures) == manifest["max_calls_per_task"] and captures[-1]["reason"] == "ok",
                 "call_limit_failure_mismatch")
    elif failure == "invalid_model_action":
        _require(parse_failed, "model_action_failure_mismatch")
    elif failure == "invalid_tool_action":
        _require(action is not None and action["name"] != "answer" and captures[-1]["reason"] == "ok",
                 "tool_action_failure_mismatch")
    else:
        _require(failure == captures[-1]["reason"] and failure != "ok", "unknown_terminal_failure")
    _require(len(controls) == len(system_prompts) == 1, "within_run_regime_changed")
    outcome, review = _grade(files, relative, result, manifest, reviews, events)
    wall = result.get("elapsed_seconds")
    _require(type(wall) in (int, float) and math.isfinite(wall) and wall >= 0, "invalid_recorded_wall_time")
    return {
        "rep": rep, "case": case, "arm": arm, "task_id": trace.task_id, "outcome": outcome,
        "review_id": review, "calls": len(captures), "captured_call_seconds": call_seconds,
        "recorded_task_wall_seconds": wall, "controls_digest": next(iter(controls)),
        "task_prompt_digest": digest(user_stages), "user_stage_digests": user_stages,
        "system_prompt_digest": next(iter(system_prompts)), "failure": failure,
        "metrics": {key: _totals(r[key] for r in rows) for key in METRICS},
        "recovery_tool_calls": sum(e["name"] in ("retrieve_original", "search_original") for e in events),
        "view_transformations": len(result.get("views", [])),
    }


def _aggregate(runs):
    by_arm = {}
    for name in sorted({run["arm"] for run in runs}):
        arm = [r for r in runs if r["arm"] == name]
        known = all(r["outcome"] is not None for r in arm)
        successes = sum(r["outcome"] is True for r in arm)
        state = {
            "tasks": len(arm), "successes": successes,
            "failures": sum(r["outcome"] is False for r in arm),
            "ungraded": sum(r["outcome"] is None for r in arm),
            "calls": sum(r["calls"] for r in arm),
            "captured_call_seconds": sum(r["captured_call_seconds"] for r in arm),
            "recorded_task_wall_seconds": sum(r["recorded_task_wall_seconds"] for r in arm),
            "recovery_tool_calls": sum(r["recovery_tool_calls"] for r in arm),
            "view_transformations": sum(r["view_transformations"] for r in arm),
        }
        for key in METRICS:
            state[key] = _totals(r["metrics"][key] for r in arm)
            total = state[key]["total_tokens"]
            state[key]["tokens_per_verified_success"] = (
                total / successes if known and successes and total is not None else None)
        by_arm[name] = state
    return by_arm


def _learning(files, manifest, measurement, seen_responses, seen_outputs):
    _require(type(manifest.get("reserved_preflight_calls")) is int and
             manifest["reserved_preflight_calls"] == 1, "unsupported_preflight_inventory")
    setup = files.json("model-preflight.json")
    _require(setup.get("ok") is True and setup.get("phase") == "learning" and
             setup.get("role") == "verification", "invalid_shared_preflight")
    _, response, metrics = _capture({**setup, "reason": "ok"}, manifest["model_requested"])
    response_id = response.get("id")
    _require(_sha(setup["output"].encode("utf-8")) not in seen_outputs and
             (response_id is None or type(response_id) is str and response_id and response_id not in seen_responses),
             "preflight_reuses_primary_response")
    report = {
        "task_runs_are_evaluation_learning_not_deployment": True,
        "shared_setup_recomputed": {key: _totals([metrics[key]]) for key in METRICS},
        "auxiliary_runtime_calls": 0,
        "auxiliary_scope": "This pinned runner has no runtime auxiliary-model route; hidden bridge calls unobserved.",
        "all_in_tokens_per_success": None,
        "all_in_status": "no_deployment_horizon_and_incomplete_project_learning_inventory",
        "development_and_review_chat_tokens_observed": False,
    }
    # A prior screener retained counts but not raw bodies. Do NOT promote that
    # receipt into a recomputed total or silently amortize it over this pilot.
    if files.path("jev-next-experiment.json").exists():
        receipt = files.json("jev-next-experiment.json")
        ledger = receipt["learning_ledger"]
        _require(MeasurementIdentity(**ledger["measurement"]) == measurement and
                 ledger.get("measurement_id") == measurement.identity, "learning_receipt_identity_mismatch")
        learning = ledger["learning"]
        _require(all(_count(learning.get(k)) for k in ("input_tokens", "output_tokens", "total_tokens", "calls"))
                 and learning["total_tokens"] == learning["input_tokens"] + learning["output_tokens"],
                 "invalid_learning_receipt")
        _require(receipt.get("reference_input_tokens") == learning["input_tokens"] and
                 receipt.get("reference_output_tokens") == learning["output_tokens"], "learning_count_mismatch")
        _require(learning.get("by_run") and all(run.get("inventory_sealed") is True
                                              for run in learning["by_run"].values()), "unsealed_learning_receipt")
        report["jev_screening_receipt"] = {
            "reference_input_tokens": learning["input_tokens"],
            "reference_output_tokens": learning["output_tokens"],
            "reference_total_tokens": learning["total_tokens"], "calls": learning["calls"],
            "raw_bodies_recomputed": False, "included_in_task_comparison": False,
            "status": "reported_sealed_learning_receipt_only",
        }
    return report


def verify_study(root, *, baseline="baseline", candidate="combined",
                 use_recorded_reviews=False, expected_evidence_digest=None):
    """Return descriptive evidence or raise a content-free AuditError.

    Exit/audit success means consistency with the declared visible inventory,
    NOT that every task passed, savings occurred, or a population claim passed.
    Unknown outcomes/counters block efficiency wins but preserve other metrics.
    """
    try:
        return _verify(root, baseline, candidate, use_recorded_reviews, expected_evidence_digest)
    except AuditError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        raise AuditError("malformed_or_unavailable_study_artifact") from error


def _verify(root, baseline, candidate, use_reviews, expected_digest):
    files = _Artifacts(root)
    manifest = files.json("manifest.json")
    order = _grid(files, manifest)
    _require(baseline != candidate and baseline in manifest["arms"] and candidate in manifest["arms"],
             "comparison_arm_missing")
    _frozen_sources(files, manifest)
    measurement = reference_measurement()
    reviews, reviewer = _reviews(files, use_reviews)
    seen_calls, seen_responses, seen_outputs = set(), set(), set()
    runs = [_run(files, manifest, item, measurement, reviews, seen_calls, seen_responses, seen_outputs) for item in order]
    _require(len({r["controls_digest"] for r in runs}) == 1, "between_run_controls_or_tools_mismatch")
    _require(_count(manifest.get("maximum_primary_calls")) and
             len(seen_calls) <= manifest["maximum_primary_calls"], "study_call_allowance_exceeded")
    for arm in manifest["arms"]:
        _require(len({r["system_prompt_digest"] for r in runs if r["arm"] == arm}) == 1,
                 "arm_instruction_regime_mismatch")
    _require({v["id"] for v in reviews.values()} == {r["review_id"] for r in runs if r["review_id"]},
             "unused_or_missing_review")
    indexed = {(r["rep"], r["case"], r["arm"]): r for r in runs}
    pairs = []
    for rep in range(manifest["repeats"]):
        for case in sorted(manifest["case_identities"]):
            left, right = (indexed[rep, case, arm] for arm in (baseline, candidate))
            a_stages, b_stages = left["user_stage_digests"], right["user_stage_digests"]
            common = min(len(a_stages), len(b_stages))
            _require(a_stages[:common] == b_stages[:common], "paired_task_prompt_mismatch")
            if len(a_stages) != len(b_stages):
                shorter = left if len(a_stages) < len(b_stages) else right
                _require(shorter["failure"] is not None and shorter["outcome"] is False,
                         "paired_task_stage_count_mismatch")
            pairs.append({
                "rep": rep, "case": case, "baseline_success": left["outcome"], "candidate_success": right["outcome"],
                "baseline_calls": left["calls"], "candidate_calls": right["calls"],
                "saved_tokens": {key: (left["metrics"][key]["total_tokens"] - right["metrics"][key]["total_tokens"]
                                      if left["metrics"][key]["total_tokens"] is not None and
                                      right["metrics"][key]["total_tokens"] is not None else None) for key in METRICS},
            })
    by_arm = _aggregate(runs)
    known = all(p[k] is not None for p in pairs for k in ("baseline_success", "candidate_success"))
    regressions = sum(p["baseline_success"] is True and p["candidate_success"] is False for p in pairs)
    successes = by_arm[baseline]["successes"] > 0 and by_arm[candidate]["successes"] > 0
    comparison = {}
    for key in METRICS:
        a, b = by_arm[baseline][key], by_arm[candidate][key]
        saved = a["total_tokens"] - b["total_tokens"] if (
            a["total_tokens"] is not None and b["total_tokens"] is not None) else None
        comparison[key] = {
            "baseline": a, "candidate": b, "saved_tokens": saved,
            "saved_percent": 100 * saved / a["total_tokens"] if saved is not None and a["total_tokens"] else None,
            "predeclared_primary": key == "api_body_reference",
            "observed_efficiency_win": known and successes and regressions == 0 and saved is not None and saved > 0,
            "pairs_using_fewer_tokens": sum(p["saved_tokens"][key] is not None and p["saved_tokens"][key] > 0 for p in pairs),
            "pairs_using_more_tokens": sum(p["saved_tokens"][key] is not None and p["saved_tokens"][key] < 0 for p in pairs),
            "pairs_with_unknown_total": sum(p["saved_tokens"][key] is None for p in pairs),
            "interpretation": "descriptive_on_these_tasks_only_not_a_certified_or_generalized_gain",
        }
    learning = _learning(files, manifest, measurement, seen_responses, seen_outputs)
    files.recheck()
    evidence_digest = digest(files.hashes)
    if expected_digest is not None:
        _require(type(expected_digest) is str and re.fullmatch(r"[0-9a-f]{64}", expected_digest),
                 "invalid_expected_evidence_digest")
        _require(expected_digest == evidence_digest, "evidence_receipt_mismatch")
    return {
        "schema_version": 1, "protocol": PROTOCOL, "audit_status": "consistent_with_declared_inventory",
        "study_id": manifest["study_id"], "requested_and_reported_model": manifest["model_requested"],
        "underlying_weights_identity_verified": False, "harness_adapter": HARNESS,
        "reference_measurement": asdict(measurement),
        "baseline_arm": baseline, "candidate_arm": candidate,
        "by_arm": by_arm, "comparison": comparison, "pairs": pairs, "runs": runs,
        "quality": {
            "all_outcomes_known": known, "new_failures": regressions,
            "observed_pairwise_nonregression": known and regressions == 0,
            "outcomes_reexecuted_by_checker": False, "recorded_review_used": use_reviews, "reviewer": reviewer,
            "basis": "Saved separate oracle receipts bound to actual responses and workspace hashes; not an authenticated truth oracle.",
        },
        "statistical": {
            "eligible": False, "certificate": None, "confidence_interval": None,
            "reason": "This adapter audits a non-IID challenge suite, not fresh independent registry confirmation.",
            "unique_cases": len(manifest["case_identities"]), "repeats_per_case": manifest["repeats"],
            "paired_runs": len(pairs), "independent_task_sample_size": None,
            "reported_native_metric": "post_hoc_diagnostic_not_substituted_for_predeclared_body_metric",
            "required_next_step": "Freeze the policy, sampler, cap and metric; use fresh paired tasks and the existing strict registry gate.",
        },
        "learning": learning,
        "limitations": [
            "API-body reference counts include metadata/ciphertext and are not native model tokens.",
            "Bridge-reported usage is arithmetically checked, not independently measured or authenticated upstream usage.",
            "Encrypted reasoning makes explicit-context output totals unavailable; no unknown count is replaced with zero.",
            "All declared visible calls and failed tasks are counted; unrecorded bridge-internal calls remain outside the boundary.",
            "No cache discount, reasoning double-count, additive component savings, model-weight change, or monetary calculation.",
            "A consistent receipt cannot establish oracle truth, absent hidden calls, identical weights, IID sampling or production parity.",
        ],
        "evidence_hashes": files.hashes, "evidence_digest": evidence_digest,
        "checker_source_sha256": _sha(Path(__file__).read_bytes()),
    }
