"""One declared learning pair through real RuntimeSession boundaries.

The directly supplied host is trusted application code, not a plugin loader or
sandbox. prepare must be local and deterministic; drive must be synchronous and
put ALL model work through its supplied session. check runs only after that
session is sealed/closed, must be independently grounded, and must not mutate
artifacts, workspace or captures. Gold belongs to the host's private checker,
never to model-visible preparation/drive data. These obligations cannot be
proved for arbitrary Python callbacks.

The legacy manifest compares only local RequestPolicy variants. The explicit
profile manifest binds RuntimePolicy/resources and readies both component
sessions before either primary arm. No self-grading, retries or promotion.
Gateway usage is not mixed into the pinned complete-body reference counter.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import random
import re
from threading import Lock
from typing import Any

from . import tokens
from .certification import PairedObservation, VerifiedOutcome
from .optimizer import (
    EvaluationAttemptFailed, EvaluationAttemptInterrupted, FrozenTrial,
    Optimizer, OptimizerConfig, reference_measurement,
)
from .runtime import RuntimeSession
from .runtime_io import parse_json, safe_root
from .request_policy import RequestPolicy
from .runtime_policy import RuntimePolicy, controller_policy_neighbors
from .runtime_resources import RuntimeResources
from .token_ledger import CallRecord, MeasurementIdentity, TaskTrace

VERSION = "runtime-learning-pair-v1"
PROFILE_VERSION = "profile-learning-pair-v1"
CATALOG_VERSION = "runtime-policy-neighbors-v4"
_TASK_ID = re.compile(r"[A-Za-z0-9._:-]{1,256}")
_SHA = re.compile(r"[0-9a-f]{64}")
_TRANSPORT_FIELDS = (
    "model", "allow_network", "base_url", "reasoning_effort", "max_output_tokens",
    "max_request_bytes", "max_response_bytes", "timeout",
)


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _wire(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_wire(value).encode("utf-8")).hexdigest()


def _sha(path):
    h = hashlib.sha256()
    with safe_root(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write(path, value):
    data = (_wire(value) + "\n").encode("utf-8")
    with safe_root(path).open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(data).hexdigest()


def _json(path):
    with safe_root(path).open("r", encoding="utf-8") as stream:
        return parse_json(stream.read())


def _lines(path, limit):
    if not path.exists():
        return
    with safe_root(path).open("rb") as stream:
        for index in range(limit + 1):
            raw = stream.readline(64 * 1024 * 1024 + 1)
            if not raw:
                return
            _require(index < limit and len(raw) <= 64 * 1024 * 1024 and raw.endswith(b"\n"),
                     "incomplete_runtime_journal")
            yield parse_json(raw.decode("utf-8"))


def _files(root):
    root = safe_root(root)
    _require(root.is_dir(), "workspace_unavailable")
    result = {}
    for path in sorted(root.rglob("*")):
        path = safe_root(path)
        _require(path.is_relative_to(root), "workspace_escape")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = _sha(path)
    return result


def _sources():
    root = Path(__file__).parent
    return {p.relative_to(root).as_posix(): _sha(p) for p in sorted(root.rglob("*.py"))}


def _trace(data) -> TaskTrace:
    values = dict(data)
    values["measurement"] = MeasurementIdentity(**values["measurement"])
    values["calls"] = tuple(CallRecord(**row) for row in values["calls"])
    return TaskTrace(**values)


@dataclass(frozen=True, slots=True)
class CheckedOutcome:
    """A trusted checker's binary result and independent evidence digest."""
    success: bool
    evidence_sha256: str

    def __post_init__(self):
        _require(type(self.success) is bool and type(self.evidence_sha256) is str
                 and _SHA.fullmatch(self.evidence_sha256) is not None, "invalid_checked_outcome")


@dataclass(frozen=True, slots=True)
class RuntimeLearningManifest:
    config: OptimizerConfig
    host_id: str
    task_digests: tuple[tuple[str, str], ...]
    max_calls_per_arm: int
    order_seed: int = 0

    def __post_init__(self):
        _require(type(self.config) is OptimizerConfig, "optimizer_config_required")
        self.config.__post_init__()
        _require(type(self.host_id) is str and bool(self.host_id.strip()), "host_identity_required")
        _require(type(self.order_seed) is int, "invalid_order_seed")
        _require(type(self.max_calls_per_arm) is int and 1 <= self.max_calls_per_arm <= 4096
                 and self.config.calls_per_pair == 2 * self.max_calls_per_arm,
                 "both_arm_call_allocation_mismatch")
        _require(type(self.task_digests) is tuple and bool(self.task_digests), "immutable_task_digests_required")
        ids, hashes = set(), set()
        for pair in self.task_digests:
            _require(type(pair) is tuple and len(pair) == 2, "immutable_task_digest_pair_required")
            task, digest = pair
            _require(type(task) is str and _TASK_ID.fullmatch(task) is not None
                     and type(digest) is str and _SHA.fullmatch(digest) is not None,
                     "invalid_task_digest")
            _require(task not in ids and digest not in hashes, "duplicate_task_or_source_digest")
            ids.add(task)
            hashes.add(digest)

    @property
    def identity(self):
        return _digest({"version": VERSION, **asdict(self)})

    def to_dict(self):
        return {"version": VERSION, **asdict(self)}

    def arm_order(self, task_id):
        ids = [task for task, _ in self.task_digests]
        random.Random(self.order_seed).shuffle(ids)
        _require(task_id in ids, "undeclared_task")
        return ("incumbent", "candidate") if ids.index(task_id) % 2 == 0 else ("candidate", "incumbent")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProfileLearningManifest(RuntimeLearningManifest):
    """Explicit profile regime; legacy manifest bytes/identity stay unchanged."""
    resources_id: str
    version: str = PROFILE_VERSION
    catalog_version: str = CATALOG_VERSION

    def __post_init__(self):
        RuntimeLearningManifest.__post_init__(self)
        _require(type(self.resources_id) is str
                 and re.fullmatch(r"runtime-resources-v1:[0-9a-f]{64}", self.resources_id) is not None,
                 "invalid_runtime_resources_identity")
        _require(type(self.version) is str and self.version == PROFILE_VERSION
                 and type(self.catalog_version) is str and self.catalog_version == CATALOG_VERSION,
                 "unsupported_profile_learning_contract")

    def to_dict(self):
        return asdict(self)

    @property
    def identity(self):
        return _digest(self.to_dict())


class RuntimePairEvaluator:
    """Optimizer evaluator with durable single-use task claims and no hidden calls.

    Construct once with a NEW private output_root, then pass this callable to
    Optimizer(evaluator=...). Both prepare results must expose workspace and
    transport attributes. Each workspace must be an isolated child of its arm
    root; both start byte-identically. transport.allow_network must be explicitly
    True even for a caller-supplied fake transport. The adapter never changes it.
    Artifacts returned by drive must be JSON data. check returns CheckedOutcome.
    """

    def __init__(self, manifest: RuntimeLearningManifest, *, host, output_root,
                 resources: RuntimeResources | None = None):
        _require(type(manifest) in (RuntimeLearningManifest, ProfileLearningManifest), "learning_manifest_required")
        manifest.__post_init__()
        self._profile_learning = type(manifest) is ProfileLearningManifest
        if self._profile_learning:
            assert isinstance(manifest, ProfileLearningManifest)
            _require(type(resources) is RuntimeResources and resources.identity == manifest.resources_id,
                     "matching_runtime_resources_required")
            assert resources is not None
            resources.validate()
        else:
            _require(resources is None, "unused_runtime_resources")
        self.resources = resources
        self._resource_manifest = resources.to_manifest() if resources is not None else None
        self._version = PROFILE_VERSION if self._profile_learning else VERSION
        _require(host is not None and not isinstance(host, (str, bytes))
                 and getattr(host, "identity", None) == manifest.host_id
                 and all(callable(getattr(host, name, None)) for name in
                         ("task_digest", "prepare", "drive", "check")), "trusted_host_required")
        _require(manifest.config.measurement == reference_measurement(), "measurement_regime_mismatch")
        self.manifest, self.host = manifest, host
        self.output_root = safe_root(output_root)
        self._manifest_id = manifest.identity
        self._counter = tokens.count_tokens
        self._source_hashes = _sources()
        self._callbacks = {name: getattr(getattr(host, name), "__func__", getattr(host, name))
                           for name in ("task_digest", "prepare", "drive", "check")}
        self._transport_declaration: dict[str, Any] | None = None
        self._transport_receipt = None
        self._lock = Lock()
        self.output_root.mkdir(parents=True, exist_ok=False)
        self._manifest_receipt = _write(self.output_root / "learning-manifest.json", {
            "manifest": manifest.to_dict(), "identity": self._manifest_id,
            "source_fingerprints": self._source_hashes,
            "orders": {task: manifest.arm_order(task) for task, _ in manifest.task_digests},
            **self._labels(), "promotion": False,
            **({"resources": self._resource_manifest} if self._profile_learning else {}),
        })

    def _labels(self):
        if self._profile_learning:
            assert self.resources is not None
            return {"kind": "profile", "backend": "per_policy", "instruction_components": "per_policy",
                    "resources_id": self.resources.identity, "catalog_version": CATALOG_VERSION}
        return {"instruction_components": None, "backend": "local"}

    def _guard(self, task_id=None):
        _require(self.manifest.identity == self._manifest_id
                 and self.host.identity == self.manifest.host_id
                 and reference_measurement() == self.manifest.config.measurement
                 and tokens.count_tokens is self._counter,
                 "frozen_regime_changed")
        _require(_sha(self.output_root / "learning-manifest.json") == self._manifest_receipt,
                 "frozen_manifest_changed")
        if self._transport_receipt is not None:
            _require(_sha(self.output_root / "transport-declaration.json") == self._transport_receipt,
                     "frozen_transport_receipt_changed")
        _require(_sources() == self._source_hashes, "runtime_source_changed")
        if self._profile_learning:
            assert isinstance(self.manifest, ProfileLearningManifest)
            _require(type(self.resources) is RuntimeResources
                     and self.resources.to_manifest() == self._resource_manifest
                     and self.resources.identity == self.manifest.resources_id,
                     "runtime_resource_regime_changed")
        for name, callback in self._callbacks.items():
            _require(getattr(getattr(self.host, name), "__func__", getattr(self.host, name)) is callback,
                     "host_callback_changed")
        if task_id is not None:
            expected = dict(self.manifest.task_digests).get(task_id)
            _require(expected is not None and self.host.task_digest(task_id) == expected,
                     "task_source_changed")

    def _prepared(self, prepared, arm_root):
        workspace = safe_root(getattr(prepared, "workspace", arm_root))
        transport = getattr(prepared, "transport", None)
        _require(workspace.is_dir() and workspace != arm_root
                 and workspace.is_relative_to(arm_root)
                 and not workspace.is_relative_to(arm_root / "runtime")
                 and not (arm_root / "runtime").is_relative_to(workspace), "isolated_workspace_required")
        _require(transport is not None and getattr(transport, "allow_network", None) is True,
                 "explicit_transport_authority_required")
        declaration: dict[str, Any] = {key: getattr(transport, key, None) for key in _TRANSPORT_FIELDS}
        declaration["adapter"] = type(transport).__module__ + "." + type(transport).__qualname__
        _require(declaration["model"] == self.manifest.config.model_id
                 and callable(getattr(transport, "encode", None)) and callable(getattr(transport, "send", None)),
                 "model_transport_mismatch")
        for field in ("max_request_bytes", "max_response_bytes", "max_output_tokens"):
            _require(type(declaration[field]) is int and 0 < declaration[field] <= 4_194_304,
                     "bounded_transport_required")
        _wire(declaration)
        return workspace, transport, declaration

    def _native_trace(self, session, result):
        if result is not None:
            return _trace(result["trace"])
        # Failure-only snapshot of native runtime values. IDs/counts are never
        # relabeled, recomputed into a new regime, or turned into false outcomes.
        return TaskTrace(
            session.task_id, session.policy_id, session.measurement, session.phase,
            tuple(session._records), tuple(session._expected), "partial", session.learning_run_id,
            tuple(row["call_id"] for row in session._missing))

    def _record_cleanup_attempt(self, session, name, cleanup, state, *, phase, close_error):
        """An attempted close is not proof of release. Retain each receipt cutoff."""
        reported = cleanup if type(cleanup) is dict else getattr(session, "_cleanup", None)
        attempt = {
            "phase": phase, "error_type": type(close_error).__name__ if close_error is not None else None,
            "closed": getattr(session, "_closed", False) is True,
            "runtime_cleanup_settled": session.cleanup_settled is True,
            "durable_receipt_verified": False, "settled": False,
        }
        verification_error = None
        try:
            number = reported.get("cleanup_attempt", 1) if type(reported) is dict else 1
            _require(type(number) is int and number in (1, 2), "invalid_cleanup_attempt")
            path = session.output / ("cleanup.json" if number == 1 else "cleanup-retry-2.json")
            attempt["receipt_file"] = path.name
            if path.is_file():
                raw = path.read_bytes()
                attempt["receipt_sha256"] = hashlib.sha256(raw).hexdigest()
                saved = parse_json(raw.decode("utf-8"))
                attempt["receipt"] = saved
                attempt["durable_receipt_verified"] = type(reported) is dict and saved == reported
            attempt["settled"] = (
                attempt["runtime_cleanup_settled"] and type(reported) is dict and reported.get("complete") is True
                and attempt["durable_receipt_verified"])
        except BaseException as failure:
            verification_error = failure
            attempt["verification_error_type"] = type(failure).__name__
        state["cleanup_attempts"].setdefault(name, []).append(attempt)
        if attempt["settled"]:
            state["settled"].add(name)
        else:
            state["settled"].discard(name)
        return verification_error

    def _recount(self, session, result, trial, task_id, policy):
        root = session.output
        saved = _json(root / "result.json")
        _require(_digest(saved) == _digest(result), "changed_runtime_result")
        trace = _trace(saved["trace"])
        _require(trace.task_id == task_id and trace.policy_id == policy.policy_id
                 and trace.measurement == self.manifest.config.measurement
                 and trace.phase == "learning" and trace.learning_run_id == trial.learning_run_id,
                 "runtime_trace_identity_mismatch")
        metadata = _json(root / "session.json")
        _require(metadata["task_id"] == task_id and metadata["run_id"] == session.run_id
                 and metadata["policy_id"] == policy.policy_id
                 and metadata["profile_id"] == session.profile_id
                 and metadata["measurement"] == asdict(trace.measurement)
                 and metadata["phase"] == "learning"
                 and metadata["learning_run_id"] == trial.learning_run_id
                 and metadata["max_calls"] == self.manifest.max_calls_per_arm
                 and metadata["profile"] == session.profile,
                 "runtime_profile_mismatch")
        profile = metadata["profile"]
        if self._profile_learning:
            assert self.resources is not None
            _require(type(policy) is RuntimePolicy and profile["runtime_policy"] == policy.to_dict()
                     and profile["runtime_resources_id"] == self.resources.identity
                     and profile["backend"] == policy.backend
                     and profile["policy"] == policy.request_policy.to_dict()
                     and profile["mode"] is None
                     and profile["require_nonexpanding_input"] == policy.require_nonexpanding_input
                     and profile.get("headroom_time_budget_seconds") == policy.headroom_time_budget_seconds,
                     "runtime_policy_execution_mismatch")
            resolved = self.resources.resolve(policy)
            _require(profile["ponytail"] == (resolved["ponytail"].to_dict()
                     if resolved["ponytail"] is not None else None), "runtime_instruction_mismatch")
            _require(result["component"]["headroom_executed"] is (policy.backend == "headroom"),
                     "runtime_component_activation_mismatch")
            if policy.backend == "headroom":
                final_component = result["component"].get("headroom")
                _require(type(final_component) is dict, "missing_component_finalization")
                inventory = final_component.get("python_onnx_inventory")
                _require(type(inventory) is dict and inventory.get("complete") is True
                         and inventory.get("version") == "python-onnx-lifetime-ledger-v1"
                         and inventory.get("since_revision") == 0
                         and inventory.get("pending_count") == 0 and inventory.get("pending_ids") == []
                         and inventory.get("omitted_events") == 0, "incomplete_observed_component_inventory")
                # Complete observed Python API inventory is not a statement
                # about uninstrumented native detector/embedding computation.
        else:
            _require(profile["backend"] == "local" and profile["mode"] is None and profile["ponytail"] is None,
                     "runtime_profile_mismatch")
        records = {call.call_id: call for call in trace.calls}
        _require(len(records) == len(trace.calls), "duplicate_runtime_call")
        journal: list[dict[str, Any]] = []
        expected: list[str] = []
        observed: set[str] = set()
        for i, cap in enumerate(_lines(root / "captures.jsonl", self.manifest.max_calls_per_arm), 1):
            call_id = session.run_id + ":" + str(i)
            _require(cap["call_id"] == call_id, "native_call_identity_mismatch")
            journal.extend(({"call_id": call_id, "state": "pending",
                             "wire_sha256": hashlib.sha256(cap["input"].encode("utf-8")).hexdigest()
                             if cap["input"] is not None else None},
                            {"call_id": call_id, "state": "captured"}))
            if cap["submitted_or_unknown"]:
                expected.append(call_id)
            if not cap["complete"] or cap["input"] is None or cap["output"] is None:
                continue
            record = records.get(call_id)
            if record is None:
                raise ValueError("unreported_complete_capture")
            _require(record.task_id == task_id and record.model_id == self.manifest.config.model_id
                     and record.phase == "learning" and record.measurement_id == trace.measurement.identity
                     and record.harness_id == self._version + ":" + self._manifest_id,
                     "unbound_runtime_capture")
            _require(parse_json(cap["input"])["model"] == self.manifest.config.model_id, "wire_model_mismatch")
            # A transport's rejected model cannot become an incumbent quality
            # failure under the *requested* model. Costs stay in the failed
            # attempt, but no paired observation may cross this regime boundary.
            _require(cap["reason"] != "model_mismatch", "response_model_mismatch")
            try:
                response = parse_json(cap["output"])
            except (ValueError, TypeError):
                response = None  # Complete HTTP errors may be plain text.
            if cap["ok"] or type(response) is dict and "model" in response:
                _require(type(response) is dict
                         and response.get("model") == self.manifest.config.model_id,
                         "response_model_mismatch")
            _require(record.input_sha256 == hashlib.sha256(cap["input"].encode("utf-8")).hexdigest()
                     and record.output_sha256 == hashlib.sha256(cap["output"].encode("utf-8")).hexdigest()
                     and record.reference_input_tokens == tokens.count_tokens(cap["input"])
                     and record.reference_output_tokens == tokens.count_tokens(cap["output"])
                     and record.completion_status == ("succeeded" if cap["ok"] else "failed"),
                     "capture_recount_mismatch")
            observed.add(call_id)
        actual_journal = list(_lines(root / "invocations.jsonl", 2 * self.manifest.max_calls_per_arm))
        _require(len(actual_journal) == len(journal) and len(journal) // 2 == result["attempts"],
                 "incomplete_runtime_journal")
        # Pending wires are still declared for known no-submission rejections.
        for actual, wanted in zip(actual_journal, journal):
            if wanted["state"] == "pending" and wanted["wire_sha256"] is None:
                _require(set(actual) == set(wanted) and type(actual["wire_sha256"]) is str
                         and _SHA.fullmatch(actual["wire_sha256"]) is not None, "invalid_pending_receipt")
                wanted = dict(wanted, wire_sha256=actual["wire_sha256"])
            _require(actual == wanted, "runtime_journal_mismatch")
        _require(set(records) == observed and tuple(expected) == trace.expected_call_ids,
                 "runtime_inventory_mismatch")
        _require(result["trace_complete"] is True and result["component"]["complete"] is True
                 and result["tool_inventory_complete"] is True
                 and result["quality_verified"] is None and result["external_outcome_supplied"] is None,
                 "incomplete_or_self_graded_runtime")
        trace.validate_complete()
        _require(0 < len(trace.calls) <= self.manifest.max_calls_per_arm, "submitted_model_work_required")
        _require(trace.totals().to_dict() == result["reference_totals"]
                 and trace.totals().total_tokens <= self.manifest.config.token_cap,
                 "full_task_token_bound_exceeded")
        return trace

    def _arm(self, trial, task_id, name, prepared, root, frozen, traces, state, native_session=None):
        workspace, transport, declaration = frozen
        session, result, cleanup = native_session, None, None
        error, reason = None, "executor_failed"
        state["reason"] = reason
        artifacts = None
        try:
            self._guard(task_id)
            _require(self._prepared(prepared, root) == frozen, "prepared_configuration_changed")
            policy = getattr(trial, name)
            if session is None:
                session = RuntimeSession(
                    workspace=workspace, output=root / "runtime", session_id=f"learn-{name}-{_digest(task_id)[:20]}",
                    task_id=task_id, transport=transport, backend="local", policy=policy,
                    phase="learning", learning_run_id=trial.learning_run_id,
                    max_calls=self.manifest.max_calls_per_arm, harness_id=VERSION + ":" + self._manifest_id)
            state["sessions"][name] = session
            if self.resources is not None:
                self.resources.resolve(policy)
            artifacts = self.host.drive(task_id, session, prepared)
            # JSON-only detached data, not executable/model-generated evaluator objects.
            artifacts = parse_json(_wire(artifacts))
            self._guard(task_id)
            _require(self._prepared(prepared, root) == frozen, "prepared_configuration_changed")
            _write(root / "drive-artifacts.json", artifacts)
        except BaseException as failure:
            error = failure
        finally:
            if session is not None:
                if error is not None and not isinstance(error, Exception):
                    session._interrupted = True  # Also covers cancellation outside invoke().
                try:
                    result = session.finish()
                except BaseException as failure:
                    if error is None or isinstance(error, Exception) and not isinstance(failure, Exception):
                        error, reason = failure, "transport_incomplete"
                close_error = None
                try:
                    cleanup = session.close()
                except BaseException as failure:
                    close_error = failure
                    if error is None or isinstance(error, Exception) and not isinstance(failure, Exception):
                        error, reason = failure, "cleanup_failed"
                verification_error = self._record_cleanup_attempt(
                    session, name, cleanup, state, phase="arm", close_error=close_error)
                if verification_error is not None and (
                        error is None or isinstance(error, Exception) and not isinstance(verification_error, Exception)):
                    error, reason = verification_error, "cleanup_failed"
                try:
                    traces[name] = self._native_trace(session, result)
                except BaseException as failure:
                    if error is None or isinstance(error, Exception) and not isinstance(failure, Exception):
                        error, reason = failure, "transport_incomplete"
        if error is not None:
            state["reason"] = reason
            raise error
        state["reason"] = "cleanup_failed"
        _require(session is not None and result is not None and type(cleanup) is dict
                 and cleanup.get("complete") is True and name in state["settled"], "cleanup_failed")
        state["reason"] = "transport_incomplete"
        if self.resources is not None:
            self.resources.validate(getattr(trial, name))
        trace = self._recount(session, result, trial, task_id, getattr(trial, name))
        traces[name] = trace
        _require(_json(root / "runtime/cleanup.json") == cleanup, "cleanup_receipt_changed")
        before_workspace, before_runtime = _files(workspace), _files(root / "runtime")
        artifact_identity = _digest(artifacts)
        state["reason"] = "oracle_failed"
        checked = self.host.check(task_id, artifacts, prepared)
        _require(type(checked) is CheckedOutcome, "independent_checked_outcome_required")
        checked.__post_init__()
        self._guard(task_id)
        if self.resources is not None:
            self.resources.validate(getattr(trial, name))
        _require(_digest(artifacts) == artifact_identity
                 and _files(workspace) == before_workspace and _files(root / "runtime") == before_runtime
                 and self._prepared(prepared, root) == frozen, "oracle_mutated_evidence")
        evidence = _write(root / "checked-outcome.json", {
            "task_id": task_id, "task_digest": dict(self.manifest.task_digests)[task_id],
            "policy_id": trace.policy_id, "oracle_id": self.manifest.config.oracle_id,
            "host_id": self.manifest.host_id, "host_outcome": asdict(checked),
            "artifact_sha256": artifact_identity, "workspace_fingerprints": before_workspace,
            "runtime_receipt_fingerprints": before_runtime, "trace_sha256": trace.evidence_sha256,
        })
        return VerifiedOutcome(task_id, trace.policy_id, self.manifest.config.oracle_id, checked.success, evidence)

    def __call__(self, trial: FrozenTrial, reserved_task_id: str) -> PairedObservation:
        _require(self._lock.acquire(blocking=False), "pair_evaluation_in_progress")
        try:
            return self._evaluate(trial, reserved_task_id)
        finally:
            self._lock.release()

    def _evaluate(self, trial, task_id):
        self._guard(task_id)
        _require(type(trial) is FrozenTrial
                 and all(type(v) is int and v > 0 for v in (
                     trial.trial_id, trial.round_id, trial.incumbent_version, trial.sample_size))
                 and trial.comparison == self.manifest.config.comparison(
                     trial.candidate.policy_id, trial.incumbent.policy_id)
                 and trial.calls_per_pair == 2 * self.manifest.max_calls_per_arm,
                 "frozen_trial_regime_mismatch")
        catalog = None
        if self._profile_learning:
            _require(type(trial.incumbent) is RuntimePolicy and type(trial.candidate) is RuntimePolicy,
                     "profile_policy_family_required")
            assert isinstance(trial.incumbent, RuntimePolicy) and isinstance(trial.candidate, RuntimePolicy)
            trial.incumbent.__post_init__()
            trial.candidate.__post_init__()
            catalog = [p.to_dict() for p in controller_policy_neighbors(trial.incumbent)]
            _require(trial.candidate.to_dict() in catalog, "profile_candidate_not_current_neighbor")
        else:
            _require(type(trial.incumbent) is RequestPolicy and type(trial.candidate) is RequestPolicy
                     and trial.incumbent.enabled and trial.candidate.enabled, "frozen_trial_regime_mismatch")
        frozen_trial = _digest(asdict(trial))
        order = self.manifest.arm_order(task_id)
        pair_root = self.output_root / ("task-" + _digest(task_id))
        pair_root.mkdir()  # A failed/consumed task is never silently replayed.
        receipt = _write(pair_root / "pair-plan.json", {
            "manifest_id": self._manifest_id, "trial": asdict(trial), "task_id": task_id,
            "task_digest": dict(self.manifest.task_digests)[task_id], "arm_order": order,
            "max_calls_per_arm": self.manifest.max_calls_per_arm, **self._labels(),
            **({"catalog": catalog} if self._profile_learning else {}),
        })
        traces: dict[str, TaskTrace] = {}
        outcomes: dict[str, VerifiedOutcome] = {}
        prepared, frozen, arm_receipts = {}, {}, {}
        sessions: dict[str, RuntimeSession] = {}
        state: dict[str, Any] = {
            "reason": "runtime_failed", "settled": set(), "cleanup_attempts": {}, "sessions": sessions,
        }
        component_receipt = None
        try:
            if self.resources is not None:
                self.resources.validate()
                for policy in (trial.incumbent, trial.candidate):
                    assert isinstance(policy, RuntimePolicy)
                    self.resources.resolve(policy)
            # Prepare and authorize BOTH arms before either can dispatch.
            for name in ("incumbent", "candidate"):
                root = pair_root / name
                root.mkdir()
                prepared[name] = self.host.prepare(task_id, root)
                frozen[name] = self._prepared(prepared[name], root)
                self._guard(task_id)
            _require(frozen["incumbent"][2] == frozen["candidate"][2], "nonpolicy_transport_mismatch")
            if self._transport_declaration is None:
                self._transport_declaration = deepcopy(frozen["incumbent"][2])
                self._transport_receipt = _write(
                    self.output_root / "transport-declaration.json", self._transport_declaration)
            _require(frozen["incumbent"][2] == self._transport_declaration, "frozen_transport_changed")
            initial_workspace = _files(frozen["incumbent"][0])
            _require(initial_workspace == _files(frozen["candidate"][0]), "initial_workspaces_differ")
            prepared_receipt = _write(pair_root / "prepared.json", {
                "transport": frozen["incumbent"][2], "workspace_fingerprints": initial_workspace})
            if self._profile_learning:
                # Construct both before starting either component; retain the
                # same workers through drive, finalization and exact cleanup.
                for name in ("incumbent", "candidate"):
                    workspace, transport, _ = frozen[name]
                    sessions[name] = RuntimeSession(
                        workspace=workspace, output=pair_root / name / "runtime",
                        session_id=f"learn-{name}-{_digest(task_id)[:20]}", task_id=task_id,
                        transport=transport, runtime_policy=getattr(trial, name),
                        runtime_resources=self.resources, phase="learning",
                        learning_run_id=trial.learning_run_id, max_calls=self.manifest.max_calls_per_arm,
                        harness_id=self._version + ":" + self._manifest_id)
                readiness = {}
                for name in order:
                    readiness[name] = sessions[name].prepare_components()
                    self._guard(task_id)
                component_receipt = _write(pair_root / "components-ready.json", readiness)
            for name in order:
                _require(_sha(pair_root / "pair-plan.json") == receipt
                         and _sha(pair_root / "prepared.json") == prepared_receipt, "frozen_pair_plan_changed")
                if component_receipt is not None:
                    _require(_sha(pair_root / "components-ready.json") == component_receipt,
                             "component_readiness_receipt_changed")
                _require(_files(frozen[name][0]) == initial_workspace, "unstarted_workspace_changed")
                outcomes[name] = self._arm(trial, task_id, name, prepared[name],
                                           pair_root / name, frozen[name], traces, state,
                                           native_session=sessions.get(name))
                arm_receipts[name] = _files(pair_root / name)
                _require(_digest(asdict(trial)) == frozen_trial, "frozen_trial_changed")
            # A later callback must not invalidate an earlier recount/check.
            self._guard(task_id)
            _require(_sha(pair_root / "pair-plan.json") == receipt
                     and _sha(pair_root / "prepared.json") == prepared_receipt, "frozen_pair_plan_changed")
            if component_receipt is not None:
                _require(_sha(pair_root / "components-ready.json") == component_receipt,
                         "component_readiness_receipt_changed")
            _require(all(_files(pair_root / name) == arm_receipts[name] for name in order),
                     "completed_arm_evidence_changed")
            first = []
            for name in ("incumbent", "candidate"):
                prep = next(_lines(pair_root / name / "runtime/preparations.jsonl",
                                   self.manifest.max_calls_per_arm))
                first.append(prep["original"])
            _require(first[0] == first[1], "nonpolicy_initial_request_mismatch")
            observation = PairedObservation(task_id, traces["incumbent"], traces["candidate"],
                                            outcomes["incumbent"], outcomes["candidate"])
            observation.validate(trial.comparison)
            _write(pair_root / "observation.json", asdict(observation))
            return observation
        except BaseException as error:
            # Failure/cancellation can precede drive (including second-worker
            # warmup). Give each unconfirmed owned session ONE unwind attempt;
            # never restart components, drive hosts, or substitute new sessions.
            for name, session in sessions.items():
                if name in state["settled"]:
                    continue
                if not isinstance(error, Exception):
                    session._interrupted = True  # Suppress post-cancel Headroom audit.
                result = None
                if not state["cleanup_attempts"].get(name):
                    try:
                        result = session.finish()
                    except BaseException as failure:
                        if isinstance(error, Exception) and not isinstance(failure, Exception):
                            error = failure
                cleanup, close_error = None, None
                try:
                    cleanup = session.close()
                except BaseException as failure:
                    close_error = failure
                    state["reason"] = "cleanup_failed"
                    if isinstance(error, Exception) and not isinstance(failure, Exception):
                        error = failure
                verification_error = self._record_cleanup_attempt(
                    session, name, cleanup, state, phase="pair_unwind", close_error=close_error)
                if verification_error is not None:
                    state["reason"] = "cleanup_failed"
                    if isinstance(error, Exception) and not isinstance(verification_error, Exception):
                        error = verification_error
                try:
                    if result is not None or name not in traces:
                        traces[name] = self._native_trace(session, result)
                except BaseException as failure:
                    state["reason"] = "transport_incomplete"
                    if isinstance(error, Exception) and not isinstance(failure, Exception):
                        error = failure
            reason = "interrupted" if not isinstance(error, Exception) else state["reason"]
            if isinstance(error, Exception) and str(error) in ("cleanup_failed",):
                reason = "cleanup_failed"
            # Retain both completed and partial native traces; no invented label.
            failure_receipt = {"reason": reason, "error_type": type(error).__name__,
                               "traces": [asdict(t) for t in traces.values()],
                               "completed_outcome_arms": list(outcomes),
                               "cleanup": {
                                   name: {"attempts": state["cleanup_attempts"].get(name, []),
                                          "settled": name in state["settled"],
                                          "resource_state": "released" if name in state["settled"] else "unknown"}
                                   for name in sessions},
                               "unknown_cleanup_arms": [name for name in sessions if name not in state["settled"]]}
            receipts = [receipt]
            try:
                receipts.append(_write(pair_root / "attempt-failed.json", failure_receipt))
                for name in ("incumbent", "candidate"):
                    for filename in ("session.json", "result.json", "cleanup.json", "captures.jsonl", "invocations.jsonl"):
                        path = pair_root / name / "runtime" / filename
                        if path.is_file():
                            receipts.append(_sha(path))
                    if self._profile_learning:
                        runtime_root = pair_root / name / "runtime"
                        if runtime_root.is_dir():
                            receipts.extend(_files(runtime_root).values())
            except BaseException as evidence_error:
                # Even cancellation while saving failure evidence must not
                # erase native partial traces or replace an earlier interrupt.
                if isinstance(error, Exception) and not isinstance(evidence_error, Exception):
                    error, reason = evidence_error, "interrupted"
            exception = EvaluationAttemptInterrupted if not isinstance(error, Exception) else EvaluationAttemptFailed
            raise exception(traces=tuple(traces.values()), reason=reason,
                            receipt_sha256s=tuple(dict.fromkeys(receipts))) from None


def learn_once(optimizer, *, task_ids, samples, screener=None, summaries=None,
               search_task_ids=(), data_classification=None, candidate_id=None) -> dict:
    """Propose, freeze ONE candidate, then reserve/evaluate supplied fresh IDs.

    Does not initialize a baseline, recycle tasks, retry a candidate, promote,
    modify the registry's strict gate, or acquire any network/model authority.
    The optimizer must already have this adapter as its configured evaluator.
    An explicit candidate ID selects only an existing returned neighbor, before
    freezing/evaluation, and cannot be combined with advisory screening.
    """
    _require(type(optimizer) is Optimizer and type(getattr(optimizer, "_evaluator", None)) is RuntimePairEvaluator,
             "runtime_pair_evaluator_required")
    evaluator = optimizer._evaluator
    evaluator._guard()
    _require(optimizer.config == evaluator.manifest.config, "optimizer_manifest_mismatch")
    _require(type(samples) is int and samples > 0 and not isinstance(task_ids, (str, bytes)),
             "invalid_learning_sample")
    if candidate_id is not None:
        _require(type(candidate_id) is str, "invalid_explicit_candidate_id")
        _require(screener is None and summaries is None and data_classification is None,
                 "explicit_candidate_screening_conflict")
    if screener is not None:
        _require(callable(getattr(screener, "decide", None)) and type(summaries) is dict
                 and data_classification in ("synthetic", "sanitized"), "explicit_screening_disclosure_required")
    else:
        _require(summaries is None and data_classification is None, "unused_screening_disclosure")
    candidates = optimizer.propose(
        screener=screener, summaries=summaries, search_task_ids=search_task_ids,
        data_classification=data_classification)
    if candidate_id is not None:
        _require(candidate_id in {p.policy_id for p in candidates}, "explicit_candidate_not_proposed")
    if not candidates:
        return {"status": "no_candidates", "policy_promoted": False}
    trial = optimizer.freeze(candidates[0].policy_id if candidate_id is None else candidate_id, sample_size=samples)
    certificate = optimizer.evaluate(trial.trial_id, task_ids)
    return {"status": certificate.decision, "trial_id": trial.trial_id,
            "incumbent_id": trial.incumbent.policy_id, "candidate_id": trial.candidate.policy_id,
            "certificate": certificate.to_dict(), "policy_promoted": False}
