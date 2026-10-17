"""Token-only, harness-neutral accounting; no model/provider dependencies.

Public API:
  MeasurementIdentity pins tokenizer/version/vocabulary, extraction/version and
  the materialized textual boundary; ``identity`` is its canonical SHA-256.
  measure_call(identity, count_reference, input_text=..., output_text=...,
               **CallRecord metadata) counts each FULL serialized string once.
  CallRecord accepts exact reference counts from a trusted measurement adapter.
  TaskTrace(..., expected_call_ids=..., coverage=...) seals one whole task,
  including ALL attempts, auxiliaries, failures and recovery. ``totals()``
  validates completeness before returning TokenTotals. A declared complete
  empty inventory is a valid zero-call task, unlike unknown/partial capture.
  TokenLedger(identity, horizon=None).record(trace, success=True|False|None)
  records each task/call once; ``summary()`` returns JSON-safe phase totals.
  DeploymentHorizon(id, deployment_task_ids, learning_run_ids) is declared at
  ledger creation, never selected after seeing favorable deployment results.
  seal_learning_run(run_id, expected_task_ids) closes an exact run inventory
  before its overhead can enter a defined all-in ratio. Later appends reject.

No raw payload is retained. IDs must be opaque/non-sensitive; hashes do not
make low-entropy secrets anonymous. The caller implements the pinned extraction
and tokenizer. Software cannot infer omitted calls, authenticate counts, or
prove a supplied inventory complete. Coverage means complete for the declared
observable boundary, NEVER hidden reasoning or opaque provider internals.
Native counts, estimates, cache discounts and raw-tool-size additions have no
place in this ledger. Outcome truth is the configured evaluator's responsibility.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from threading import RLock
from typing import Callable, Iterable


COMPLETE = "complete_for_declared_boundary"
_PHASES = ("deployment", "learning")
_ROLES = ("primary", "auxiliary", "verification", "recovery", "retry")


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty identity")


def _integer(value: int, name: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _strings(values: Iterable[str], name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be a sequence, not text")
    try:
        result = tuple(values)
    except TypeError as exc:
        raise ValueError(f"{name} must be a sequence") from exc
    for item in result:
        _text(item, name)
    return result


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _digest(value: str | None, name: str) -> None:
    if value is not None and (
        not isinstance(value, str) or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


@dataclass(frozen=True, slots=True)
class MeasurementIdentity:
    tokenizer_id: str
    tokenizer_version: str
    vocabulary_id: str
    extraction_protocol_id: str
    extraction_protocol_version: str
    boundary: str
    schema_version: int = 1

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("unsupported measurement schema_version")
        for name in (
            "tokenizer_id", "tokenizer_version", "vocabulary_id",
            "extraction_protocol_id", "extraction_protocol_version", "boundary",
        ):
            _text(getattr(self, name), name)

    @property
    def identity(self) -> str:
        return _hash(_canonical(asdict(self)))


@dataclass(frozen=True, slots=True)
class CallRecord:
    call_id: str
    task_id: str
    attempt_id: str
    phase: str
    role: str
    model_id: str
    harness_id: str
    measurement_id: str
    reference_input_tokens: int
    reference_output_tokens: int
    coverage: str
    completion_status: str
    parent_call_id: str | None = None
    count_kind: str = "reference_exact"
    input_kind: str = "materialized"
    missing_or_opaque_components: tuple[str, ...] = ()
    input_sha256: str | None = None
    output_sha256: str | None = None

    def __post_init__(self):
        for name in (
            "call_id", "task_id", "attempt_id", "model_id", "harness_id", "measurement_id",
        ):
            _text(getattr(self, name), name)
        _integer(self.reference_input_tokens, "reference_input_tokens")
        _integer(self.reference_output_tokens, "reference_output_tokens")
        if self.phase not in _PHASES:
            raise ValueError("phase must be deployment or learning")
        if self.role not in _ROLES:
            raise ValueError(f"role must be one of {_ROLES}")
        if self.coverage not in (COMPLETE, "partial", "unknown"):
            raise ValueError("invalid coverage")
        if self.completion_status not in ("succeeded", "failed", "cancelled"):
            raise ValueError("calls must have a terminal completion_status")
        if self.parent_call_id is not None:
            _text(self.parent_call_id, "parent_call_id")
        object.__setattr__(self, "missing_or_opaque_components",
                           _strings(self.missing_or_opaque_components, "missing components"))
        _digest(self.input_sha256, "input_sha256")
        _digest(self.output_sha256, "output_sha256")

    def validate_complete(self) -> None:
        if self.coverage != COMPLETE or self.missing_or_opaque_components:
            raise ValueError("incomplete call coverage")
        if self.count_kind != "reference_exact":
            raise ValueError("only exact reference counts are admissible")
        if self.input_kind != "materialized":
            raise ValueError("input must be fully materialized, not a transport delta")

    def to_dict(self) -> dict:
        return asdict(self)


def measure_call(
    measurement: MeasurementIdentity,
    count_reference: Callable[[str], int],
    *,
    input_text: str,
    output_text: str,
    **metadata,
) -> CallRecord:
    """Count full protocol-extracted strings once each, retaining only hashes.

    The function must be the exact pinned reference tokenizer, not an estimator.
    Do not join separately counted chunks: tokenization need not be additive.
    Empty output is valid for a fully observed failure; unseen output is not.
    """
    if not isinstance(measurement, MeasurementIdentity):
        raise ValueError("measurement must be a MeasurementIdentity")
    if not isinstance(input_text, str) or not isinstance(output_text, str):
        raise ValueError("fully captured input_text and output_text are required")
    return CallRecord(
        measurement_id=measurement.identity,
        reference_input_tokens=count_reference(input_text),
        reference_output_tokens=count_reference(output_text),
        input_sha256=_hash(input_text), output_sha256=_hash(output_text),
        **metadata,
    )


@dataclass(frozen=True, slots=True)
class TokenTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    peak_input_tokens: int = 0
    calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict:
        return dict(asdict(self), total_tokens=self.total_tokens)


def _totals(calls: Iterable[CallRecord]) -> TokenTotals:
    inputs = outputs = peak = count = 0
    for call in calls:
        inputs += call.reference_input_tokens
        outputs += call.reference_output_tokens
        peak = max(peak, call.reference_input_tokens)
        count += 1
    return TokenTotals(inputs, outputs, peak, count)


@dataclass(frozen=True, slots=True)
class TaskTrace:
    task_id: str
    policy_id: str
    measurement: MeasurementIdentity
    phase: str
    calls: tuple[CallRecord, ...]
    expected_call_ids: tuple[str, ...]
    coverage: str
    learning_run_id: str | None = None
    missing_or_opaque_components: tuple[str, ...] = ()

    def __post_init__(self):
        _text(self.task_id, "task_id")
        _text(self.policy_id, "policy_id")
        if not isinstance(self.measurement, MeasurementIdentity):
            raise ValueError("measurement must be a MeasurementIdentity")
        if self.phase not in _PHASES:
            raise ValueError("phase must be deployment or learning")
        if self.coverage not in (COMPLETE, "partial", "unknown"):
            raise ValueError("invalid task coverage")
        if self.phase == "learning":
            _text(self.learning_run_id, "learning_run_id")
        elif self.learning_run_id is not None:
            raise ValueError("deployment calls cannot also belong to a learning run")
        try:
            calls = tuple(self.calls)
        except TypeError as exc:
            raise ValueError("calls must be a sequence") from exc
        if any(not isinstance(c, CallRecord) for c in calls):
            raise ValueError("calls must contain CallRecord values")
        object.__setattr__(self, "calls", calls)
        object.__setattr__(self, "expected_call_ids",
                           _strings(self.expected_call_ids, "expected_call_ids"))
        object.__setattr__(self, "missing_or_opaque_components",
                           _strings(self.missing_or_opaque_components, "missing components"))

    def validate_complete(self) -> None:
        if self.coverage != COMPLETE or self.missing_or_opaque_components:
            raise ValueError("incomplete task coverage")
        by_id = {c.call_id: c for c in self.calls}
        if len(by_id) != len(self.calls):
            raise ValueError("duplicate call IDs")
        if len(set(self.expected_call_ids)) != len(self.expected_call_ids):
            raise ValueError("duplicate expected call IDs")
        if set(by_id) != set(self.expected_call_ids):
            raise ValueError("call inventory does not match expected calls")
        for call in self.calls:
            call.validate_complete()
            if call.task_id != self.task_id or call.phase != self.phase:
                raise ValueError("call task/phase mismatch")
            if call.measurement_id != self.measurement.identity:
                raise ValueError("call measurement mismatch")
            if call.parent_call_id is not None and call.parent_call_id not in by_id:
                raise ValueError("missing parent call")
        # Parent links are diagnostics, never an excuse to omit a child.
        checked = set()
        for call_id in by_id:
            path = set()
            current: str | None = call_id
            while current is not None and current not in checked:
                if current in path:
                    raise ValueError("cyclic parent calls")
                path.add(current)
                current = by_id[current].parent_call_id
            checked.update(path)

    def totals(self) -> TokenTotals:
        self.validate_complete()
        return _totals(self.calls)

    @property
    def evidence_sha256(self) -> str:
        """Digest of metadata/counts, not raw model payload."""
        self.validate_complete()
        return _hash(_canonical(asdict(self)))


@dataclass(frozen=True, slots=True)
class DeploymentHorizon:
    horizon_id: str
    deployment_task_ids: tuple[str, ...]
    learning_run_ids: tuple[str, ...]

    def __post_init__(self):
        _text(self.horizon_id, "horizon_id")
        for name in ("deployment_task_ids", "learning_run_ids"):
            values = _strings(getattr(self, name), name)
            if len(set(values)) != len(values):
                raise ValueError(f"duplicate {name}")
            object.__setattr__(self, name, values)
        if not self.deployment_task_ids:
            raise ValueError("a horizon requires deployment tasks")


class TokenLedger:
    """In-memory append-only complete-task ledger; use a single shared instance.

    Durability of capture is adapter-owned. This ledger provides process-local
    duplicate exclusion; confirmation durability is in CertificationRegistry.
    """

    def __init__(self, measurement: MeasurementIdentity, *, horizon: DeploymentHorizon | None = None):
        if not isinstance(measurement, MeasurementIdentity):
            raise ValueError("measurement must be a MeasurementIdentity")
        if horizon is not None and not isinstance(horizon, DeploymentHorizon):
            raise ValueError("horizon must be a DeploymentHorizon")
        self._measurement = measurement
        self._horizon = horizon
        self._tasks: dict[str, tuple[TaskTrace, bool | None]] = {}
        self._calls: set[str] = set()
        self._sealed_runs: dict[str, tuple[str, ...]] = {}
        self._lock = RLock()

    @property
    def measurement(self) -> MeasurementIdentity:
        return self._measurement

    @property
    def horizon(self) -> DeploymentHorizon | None:
        return self._horizon

    def record(self, trace: TaskTrace, *, success: bool | None = None) -> None:
        if not isinstance(trace, TaskTrace):
            raise ValueError("trace must be a TaskTrace")
        if success is not None and type(success) is not bool:
            raise ValueError("success must be an independently verified boolean or None")
        trace.validate_complete()
        if trace.measurement != self.measurement:
            raise ValueError("incompatible measurement identity")
        if self.horizon is not None:
            if trace.phase == "deployment" and trace.task_id not in self.horizon.deployment_task_ids:
                raise ValueError("task outside predeclared deployment horizon")
            if trace.phase == "learning" and trace.learning_run_id not in self.horizon.learning_run_ids:
                raise ValueError("learning run outside predeclared horizon")
        with self._lock:
            if trace.phase == "learning" and trace.learning_run_id in self._sealed_runs:
                raise ValueError("cannot append to a sealed learning run")
            if trace.task_id in self._tasks:
                raise ValueError("duplicate task ID")
            ids = {c.call_id for c in trace.calls}
            if self._calls.intersection(ids):
                raise ValueError("duplicate call ID across tasks")
            self._tasks[trace.task_id] = (trace, success)
            self._calls.update(ids)

    def seal_learning_run(self, run_id: str, expected_task_ids: Iterable[str]) -> None:
        """Attest a completed run's exact task inventory, including rejected work.

        Each task already has a checked call inventory. This is an explicit
        adapter attestation, not proof that an external unobserved call did not
        occur. Empty runs require the same explicit seal; presence is never
        mistaken for completeness. An identical repeated seal is idempotent.
        """
        _text(run_id, "learning run")
        expected = _strings(expected_task_ids, "expected learning task IDs")
        if len(set(expected)) != len(expected):
            raise ValueError("duplicate expected learning task IDs")
        if self.horizon is not None and run_id not in self.horizon.learning_run_ids:
            raise ValueError("learning run outside predeclared horizon")
        with self._lock:
            actual = {trace.task_id for trace, _ in self._tasks.values()
                      if trace.phase == "learning" and trace.learning_run_id == run_id}
            if actual != set(expected):
                raise ValueError("learning run inventory does not match recorded tasks")
            frozen = tuple(sorted(expected))
            if run_id in self._sealed_runs and self._sealed_runs[run_id] != frozen:
                raise ValueError("learning run is already sealed with another inventory")
            self._sealed_runs[run_id] = frozen

    def _phase_summary(self, phase: str) -> dict:
        entries = [(t, q) for t, q in self._tasks.values() if t.phase == phase]
        calls = [c for t, _ in entries for c in t.calls]
        successes = sum(q is True for _, q in entries)
        observed = sum(q is not None for _, q in entries)
        result = _totals(calls).to_dict()
        status = (
            "incomplete_outcomes" if observed != len(entries)
            else "no_verified_successes" if successes == 0 else "defined"
        )
        result.update(
            tasks=len(entries), verified_successes=successes,
            verified_outcomes=observed,
            success_rate=successes / len(entries) if entries and observed == len(entries) else None,
            tokens_per_verified_success=result["total_tokens"] / successes if status == "defined" else None,
            ratio_status=status,
            by_role={role: _totals(c for c in calls if c.role == role).to_dict()
                     for role in sorted({c.role for c in calls})},
            by_status={status: _totals(c for c in calls if c.completion_status == status).to_dict()
                       for status in sorted({c.completion_status for c in calls})},
        )
        if phase == "learning":
            result["by_run"] = {
                run: {
                    **_totals(c for t, _ in entries if t.learning_run_id == run
                              for c in t.calls).to_dict(),
                    "inventory_sealed": run in self._sealed_runs,
                    "task_inventory_sha256": (
                        _hash(_canonical(self._sealed_runs[run])) if run in self._sealed_runs else None
                    ),
                }
                for run in sorted({t.learning_run_id for t, _ in entries
                                   if t.learning_run_id is not None} | set(self._sealed_runs))
            }
        return result

    def summary(self) -> dict:
        """Snapshot totals; None ratios explicitly mean undefined, never zero."""
        with self._lock:
            deployment = self._phase_summary("deployment")
            learning = self._phase_summary("learning")
            all_in = None
            if self.horizon is not None:
                seen_tasks = {t.task_id for t, _ in self._tasks.values() if t.phase == "deployment"}
                unsealed = set(self.horizon.learning_run_ids) - set(self._sealed_runs)
                complete = (
                    seen_tasks == set(self.horizon.deployment_task_ids)
                    and not unsealed
                )
                total = deployment["total_tokens"] + learning["total_tokens"]
                defined = complete and deployment["ratio_status"] == "defined"
                all_in = dict(
                    horizon_id=self.horizon.horizon_id,
                    declared_deployment_tasks=len(self.horizon.deployment_task_ids),
                    total_tokens=total,
                    tokens_per_verified_success=total / deployment["verified_successes"] if defined else None,
                    status=deployment["ratio_status"] if complete else "incomplete_horizon",
                    unsealed_learning_runs=sorted(unsealed),
                    scope="sealed learning inventories and predeclared deployment tasks; faithful capture is adapter-owned",
                )
            return dict(
                schema_version=1, measurement=asdict(self.measurement),
                measurement_id=self.measurement.identity,
                deployment=deployment, learning=learning, all_in=all_in,
            )
