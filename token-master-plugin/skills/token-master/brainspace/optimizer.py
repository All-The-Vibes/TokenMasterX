"""Bounded local policy search with durable, registry-only confirmation.

The independent evaluator is a trusted Python callable, not user JSON, Jev
scores, or shell commands. Measurement uses the verified local reference counter
and one complete-body-text protocol, not a caller-claimed exact counter.
A single intact SQLite file owns the
whole error-budget family; do not fork/restore it to reset spending. Filesystem
integrity, truthful oracle/model pins, capture completeness, enforced callback
call limits, and fresh independent task sampling remain adapter obligations.

This controller extends certification schema v1 using its transaction boundary.
Promotion and rollback read registry-saved certificates under BEGIN IMMEDIATE,
not a certificate supplied by a caller. The private transaction/schema coupling
is deliberate: separate databases/locks would permit stale promotion races.
No live requests occur unless a caller explicitly supplies an opted-in screener.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
import json
import math
from itertools import islice
from pathlib import Path
import uuid
from typing import Callable, Iterable

from . import tokens
from .certification import (
    Certificate, CertificationRegistry, ComparisonSpec, PairedObservation, radius, round_alpha,
)
from .jev import MODEL as JEV_MODEL, Result as JevResult
from .request_policy import RequestPolicy, policy_neighbors
from .runtime_policy import (
    ControllerPolicy, RuntimePolicy, baseline_policy_admissible,
    controller_policy_neighbors, controller_policy_sort_key, decode_policy,
)
from .token_ledger import (
    COMPLETE, CallRecord, MeasurementIdentity, TaskTrace, TokenLedger,
    _canonical, _digest, _hash, measure_call,
)


class OptimizerError(ValueError):
    """Content-free controller reason code."""


def _require(condition, reason):
    if not condition:
        raise OptimizerError(reason)


def _positive(value, maximum=2**63 - 1):
    return type(value) is int and 0 < value <= maximum


def _same_policy_family(incumbent, candidate):
    _require(type(incumbent) in (RequestPolicy, RuntimePolicy)
             and type(candidate) in (RequestPolicy, RuntimePolicy), "invalid_policy_type")
    _require(type(incumbent) is type(candidate), "policy_family_mismatch")


def _policy_neighbors(policy):
    """Closed dispatch; retain the legacy public monkeypatch/caller surface."""
    _same_policy_family(policy, policy)
    neighbors = tuple(policy_neighbors(policy) if type(policy) is RequestPolicy
                      else controller_policy_neighbors(policy))
    for candidate in neighbors:
        _same_policy_family(policy, candidate)
    return neighbors


def _trace_from_dict(value):
    data = dict(value)
    data["measurement"] = MeasurementIdentity(**data["measurement"])
    data["calls"] = tuple(CallRecord(**call) for call in data["calls"])
    return TaskTrace(**data)


@dataclass(frozen=True)
class _AttemptEvidence:
    traces: tuple[TaskTrace, ...]
    reason: str
    receipt_sha256s: tuple[str, ...]


class _EvaluationAttempt(BaseException):
    """Immutable detached evidence payload; normal exception traceback semantics."""
    _default_reason = "runtime_failed"
    _reasons = frozenset({
        "runtime_failed", "transport_error", "transport_incomplete", "executor_failed",
        "oracle_failed", "cleanup_failed", "call_budget_exhausted", "interrupted",
    })

    def __init__(self, *, traces: tuple[TaskTrace, ...], reason: str | None = None,
                 receipt_sha256s: tuple[str, ...] = ()):
        traces = tuple(traces)
        _require(all(isinstance(t, TaskTrace) for t in traces), "typed_attempt_traces_required")
        reason = reason if type(reason) is str and reason in self._reasons else self._default_reason
        # Invalid receipt metadata is rejected AFTER IDs have been consumed.
        # Do not let a bad receipt erase otherwise exposed calls at construction.
        if isinstance(receipt_sha256s, (str, bytes)) or receipt_sha256s is None:
            receipts = ("invalid_receipt",)
        else:
            receipts = tuple(v if type(v) is str else "invalid_receipt" for v in receipt_sha256s)
        self._evidence = _AttemptEvidence(deepcopy(traces), reason, receipts)
        super().__init__(reason)

    @property
    def traces(self) -> tuple[TaskTrace, ...]:
        return self._evidence.traces

    @property
    def reason(self) -> str:
        return self._evidence.reason

    @property
    def receipt_sha256s(self) -> tuple[str, ...]:
        return self._evidence.receipt_sha256s


class EvaluationAttemptFailed(_EvaluationAttempt, OptimizerError):
    """Trusted evaluator failure with partial traces, never outcomes/certificates.

    Counts are considered only after registry identity and call ownership checks.
    Reason is a fixed allowlisted code; unknown text becomes ``runtime_failed``.
    Receipt digests identify host-owned evidence; no receipt files are opened.
    Nonempty valid receipt digests are required to trust counts. Missing/invalid
    receipts still consume exposed IDs and retain untrusted trace metadata.
    """


class EvaluationAttemptInterrupted(_EvaluationAttempt, KeyboardInterrupt):
    """Cancellation carrying the same evidence, preserving KeyboardInterrupt."""
    _default_reason = "interrupted"


def reference_measurement() -> MeasurementIdentity:
    """Pin complete submitted/received JSON-body TEXT, unchanged, per call.

    Decode complete bodies as UTF-8 and count their ordinary text independently:
    preserve the primary planner's insertion-order serialized request, the
    primary response as actually received, and auxiliary Jev request/response
    strings verbatim. Do not parse/reserialize, normalize whitespace/Unicode,
    or separately add wrappers already in the body. Fully received non-JSON
    HTTP error bodies are also counted unchanged; missing bodies stay unknown.

    This is the same logical observable for primary and auxiliary calls, NOT
    proprietary chat templates, HTTP headers, server additions or hidden tokens.
    The fixture generates canonical response JSON, but measurement does not
    canonicalize received responses. Only locally verified tokenizer bytes are
    admissible; no download, custom tokenizer identity or estimator fallback.
    """
    return replace(
        tokens.measurement_identity("logical-model-call-json-bodies"),
        extraction_protocol_id="complete-json-body-text/utf8-ordinary",
        extraction_protocol_version="1",
    )


@dataclass(frozen=True)
class OptimizerConfig:
    measurement: MeasurementIdentity
    oracle_id: str
    workload_id: str
    model_id: str
    environment_id: str
    token_cap: int
    minimum_token_reduction: float = 1
    alpha: float = 0.05
    max_candidates: int = 6
    max_calls: int = 4096
    calls_per_pair: int = 2
    synthetic_only: bool = False

    def __post_init__(self):
        _require(isinstance(self.measurement, MeasurementIdentity), "invalid_measurement")
        for name in ("oracle_id", "workload_id", "model_id", "environment_id"):
            _require(type(getattr(self, name)) is str and bool(getattr(self, name).strip()),
                     "invalid_regime_identity")
        _require(_positive(self.max_candidates, 1000) and _positive(self.max_calls, 1_000_000)
                 and _positive(self.calls_per_pair, 1000), "invalid_search_bounds")
        _require(type(self.synthetic_only) is bool, "invalid_synthetic_flag")
        self.comparison("candidate", "incumbent")
        round_alpha(self.alpha, 1)

    @property
    def identity(self):
        return _hash(_canonical(asdict(self)))

    def comparison(self, candidate_id, incumbent_id):
        return ComparisonSpec(
            candidate_id, incumbent_id, self.measurement, self.oracle_id,
            self.workload_id, _hash(_canonical({
                "environment": self.environment_id, "model": self.model_id,
            })), self.token_cap, self.minimum_token_reduction,
        )

    @classmethod
    def from_dict(cls, value):
        data = dict(value)
        data["measurement"] = MeasurementIdentity(**data["measurement"])
        return cls(**data)


@dataclass(frozen=True)
class BaselineValidation:
    policy_id: str
    config_id: str
    oracle_id: str
    passed: bool
    evidence_sha256: str
    trace: TaskTrace = field(repr=False)

    def __post_init__(self):
        _require(type(self.passed) is bool, "invalid_baseline_validation")
        _require(type(self.evidence_sha256) is str, "invalid_baseline_validation")
        _require(isinstance(self.trace, TaskTrace), "baseline_trace_required")
        _digest(self.evidence_sha256, "baseline_evidence")

    @classmethod
    def from_dict(cls, value):
        data = dict(value)
        data["trace"] = _trace_from_dict(data["trace"])
        return cls(**data)


@dataclass(frozen=True)
class BaselineReservation:
    """Persisted before the validator runs; declared slots are never refunded."""

    task_id: str
    learning_run_id: str
    call_limit: int


@dataclass(frozen=True)
class FrozenTrial:
    trial_id: int
    round_id: int
    incumbent_version: int
    comparison: ComparisonSpec
    incumbent: ControllerPolicy
    candidate: ControllerPolicy
    sample_size: int
    calls_per_pair: int

    def __post_init__(self):
        _same_policy_family(self.incumbent, self.candidate)

    @property
    def learning_run_id(self):
        return f"trial-{self.trial_id}"


Evaluator = Callable[[FrozenTrial, str], PairedObservation]


class Optimizer:
    """One durable controller family with fixed bounds and regime.

    ``evaluator(trial, fresh_task_id)`` must execute both full bounded policy
    runs, measure actual captured strings, and independently verify outcomes.
    ``freeze`` spends candidate/call slots permanently. IDs are opaque,
    nonsensitive dataset identities, not prompts or credentials.
    ``config.measurement`` must equal ``reference_measurement()``.
    ``count_reference`` is an optional explicit assertion of ``tokens.count_tokens``,
    not a custom-counter extension point. Old measurement regimes fail closed;
    stored comparisons/certificates are never silently relabeled.
    """

    def __init__(
        self, path: str | Path, *, config: OptimizerConfig,
        evaluator: Evaluator | None = None, count_reference: Callable[[str], int] | None = None,
    ):
        _require(isinstance(config, OptimizerConfig), "invalid_configuration")
        _require(evaluator is None or callable(evaluator), "invalid_evaluator")
        self.path = Path(path).expanduser().resolve()
        _require(str(path) != ":memory:", "durable_registry_required")
        self.config = config
        self._config_text = _canonical(asdict(config))
        self._evaluator = evaluator
        _require(count_reference is None or count_reference is tokens.count_tokens,
                 "unsupported_reference_counter")
        _require(config.measurement == reference_measurement(), "counter_identity_mismatch")
        self._count = tokens.count_tokens
        self._registry = CertificationRegistry(
            self.path, alpha=config.alpha, trusted_oracle_id=config.oracle_id,
        )
        with self._registry._transaction() as db:
            existing = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if "opt_config" in existing:
                _require("opt_accounting" in existing, "accounting_schema_mismatch")
                version = db.execute("SELECT version FROM opt_accounting WHERE id=1").fetchone()
                _require(version is not None and version[0] == 2, "accounting_schema_mismatch")
            for sql in (
                """CREATE TABLE IF NOT EXISTS opt_accounting (
                    id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS opt_config (
                    id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS opt_policies (
                    policy_id TEXT PRIMARY KEY, policy_json TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS opt_history (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL,
                    policy_id TEXT NOT NULL, previous_id TEXT, parent_seq INTEGER,
                    trial_id INTEGER, validation_json TEXT)""",
                """CREATE TABLE IF NOT EXISTS opt_champion (
                    id INTEGER PRIMARY KEY CHECK(id=1), policy_id TEXT NOT NULL,
                    version INTEGER NOT NULL, validated_seq INTEGER NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS opt_trials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, round_id INTEGER UNIQUE,
                    spec_json TEXT NOT NULL, incumbent_version INTEGER NOT NULL,
                    candidate_id TEXT NOT NULL, incumbent_id TEXT NOT NULL,
                    sample_size INTEGER NOT NULL, state TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS opt_search_tasks (
                    task_id TEXT PRIMARY KEY)""",
                """CREATE TABLE IF NOT EXISTS opt_learning (
                    event_id TEXT PRIMARY KEY, kind TEXT NOT NULL, trial_id INTEGER,
                    task_id TEXT NOT NULL, state TEXT NOT NULL, coverage TEXT NOT NULL,
                    input_tokens INTEGER, output_tokens INTEGER, calls_count INTEGER,
                    records_json TEXT, diagnostics_json TEXT)""",
                """CREATE TABLE IF NOT EXISTS opt_learning_runs (
                    run_id TEXT PRIMARY KEY, kind TEXT NOT NULL, trial_id INTEGER UNIQUE,
                    expected_tasks_json TEXT, state TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS opt_call_ids (
                    call_hash TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL REFERENCES opt_learning(event_id))""",
                """CREATE TABLE IF NOT EXISTS opt_baseline_attempts (
                    task_id TEXT PRIMARY KEY, policy_id TEXT NOT NULL,
                    call_limit INTEGER NOT NULL, reported_calls INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL)""",
            ):
                db.execute(sql)
            db.execute("INSERT OR IGNORE INTO opt_accounting VALUES(1,2)")
            db.execute("INSERT OR IGNORE INTO opt_config VALUES(1,?)", (self._config_text,))
            self._check(db)

    @classmethod
    def open(cls, path, *, evaluator=None, count_reference=None):
        """Open an existing controller; never initialize from absent state."""
        import sqlite3
        resolved = Path(path).expanduser().resolve()
        _require(resolved.is_file(), "not_initialized")
        try:
            with sqlite3.connect(resolved.as_uri() + "?mode=ro", uri=True) as db:
                row = db.execute("SELECT value FROM opt_config WHERE id=1").fetchone()
            _require(row is not None, "not_initialized")
            config = OptimizerConfig.from_dict(json.loads(row[0]))
        except (sqlite3.Error, TypeError, ValueError):
            raise OptimizerError("invalid_controller_state") from None
        return cls(resolved, config=config, evaluator=evaluator, count_reference=count_reference)

    @staticmethod
    def plan_feasibility_snapshot(path, *, sample_size=None, trial_id=None, screening=False) -> dict:
        """Read-only diagnostic, never a reservation or future budget guarantee.

        Refuse WAL/SHM/rollback sidecars explicitly: opening even mode=ro can
        create/update WAL shared memory. Only a sidecar-free, digest-stable main
        file is read with immutable=1; never ignore WAL or checkpoint it. This
        bounded snapshot detects ordinary concurrent changes and refuses them
        without retry. It is not protection against hostile change-and-restore.
        No controller/registry constructor or schema/identity migration runs.
        """
        import hashlib
        import sqlite3

        from .plan_feasibility import MAX_CONTROLLER_SAMPLES, fixed_plan_feasibility
        from .runtime_io import parse_json

        _require(type(screening) is bool, "invalid_screening_flag")
        _require((sample_size is None) != (trial_id is None), "invalid_plan_selection")
        _require(trial_id is None or (_positive(trial_id) and not screening), "invalid_trial")
        _require(sample_size is None or _positive(sample_size, MAX_CONTROLLER_SAMPLES),
                 "invalid_sample_size")
        resolved = Path(path).expanduser().resolve()
        _require(resolved.is_file(), "not_initialized")

        def fingerprint():
            _require(not any(Path(str(resolved) + suffix).exists()
                             for suffix in ("-wal", "-shm", "-journal")),
                     "active_sqlite_sidecar_snapshot_unsupported")
            stat = resolved.stat()
            # Bound total I/O even if another process grows the file while read.
            _require(0 < stat.st_size <= 256 * 1024 * 1024, "snapshot_size_unsupported")
            with resolved.open("rb") as source:
                hasher = hashlib.sha256()
                remaining = stat.st_size
                while remaining:
                    block = source.read(min(remaining, 1024 * 1024))
                    _require(bool(block), "snapshot_changed")
                    hasher.update(block)
                    remaining -= len(block)
                _require(not source.read(1), "snapshot_changed")
                digest = hasher.hexdigest()
            after = resolved.stat()
            def signature(s):
                return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns

            _require(signature(stat) == signature(after), "snapshot_changed")
            return signature(after), digest

        try:
            before = fingerprint()
            db = sqlite3.connect(resolved.as_uri() + "?mode=ro&immutable=1", uri=True)
            db.row_factory = sqlite3.Row
            try:
                db.execute("PRAGMA query_only=ON")
                db.execute("PRAGMA trusted_schema=OFF")
                db.execute("BEGIN")
                row = db.execute("SELECT value FROM opt_config WHERE id=1").fetchone()
                _require(row is not None, "not_initialized")
                config = OptimizerConfig.from_dict(parse_json(row[0]))
                accounting = db.execute("SELECT version FROM opt_accounting WHERE id=1").fetchone()
                _require(accounting is not None and accounting[0] == 2, "accounting_schema_mismatch")
                registry = db.execute("SELECT value,registry_id FROM config WHERE id=1").fetchone()
                _require(registry is not None, "not_initialized")
                # Canonical JSON preserves scalar types: Python equality would
                # silently equate True, 1 and 1.0 in persisted identities.
                _require(_canonical(parse_json(registry["value"])) == _canonical({
                    "schema_version": 1, "alpha": config.alpha,
                    "trusted_oracle_id": config.oracle_id, "gate": "strict-paired-hoeffding-v1",
                }), "configuration_changed")
                trials = db.execute("SELECT * FROM opt_trials").fetchall()
                _require(all(_positive(t["sample_size"], MAX_CONTROLLER_SAMPLES) for t in trials),
                         "invalid_controller_state")
                baselines = db.execute(
                    "SELECT call_limit,reported_calls FROM opt_baseline_attempts").fetchall()
                _require(all(type(v) is int and 0 <= v <= 2**63 - 1
                             for b in baselines for v in b), "invalid_controller_state")
                screens = db.execute(
                    "SELECT COUNT(*) FROM opt_learning WHERE kind='screening'").fetchone()[0]
                allocated = (sum(t["sample_size"] for t in trials) * config.calls_per_pair
                             + screens + sum(max(b) for b in baselines))
                champion = db.execute("SELECT policy_id,version FROM opt_champion WHERE id=1").fetchone()
                _require(champion is not None, "not_initialized")
                policy_row = db.execute("SELECT policy_json FROM opt_policies WHERE policy_id=?",
                                        (champion["policy_id"],)).fetchone()
                _require(policy_row is not None, "unknown_policy")
                policy = decode_policy(policy_row[0])
                _require(policy.policy_id == champion["policy_id"]
                         and policy.to_json() == policy_row[0], "policy_identity_mismatch")
                tried = {t["candidate_id"] for t in trials
                         if t["incumbent_id"] == policy.policy_id}
                available = sorted(p.policy_id for p in _policy_neighbors(policy) if p.policy_id not in tried)
                candidate_slots = max(0, config.max_candidates - len(trials))
                comparison: dict | None = None
                comparison_id: str | None = None
                incumbent_id, incumbent_version = policy.policy_id, champion["version"]
                candidate_id: str | None = None
                version_source = "current_champion_snapshot"
                if trial_id is None:
                    maximum = db.execute("SELECT COALESCE(MAX(k),0) FROM rounds").fetchone()[0]
                    sequence = db.execute(
                        "SELECT seq FROM sqlite_sequence WHERE name='rounds'").fetchone()
                    seq = sequence[0] if sequence else 0
                    _require(type(seq) is int and 0 <= maximum <= seq < 2**63 - 1,
                             "invalid_round_sequence")
                    k, n = seq + 1, sample_size
                else:
                    trial = next((t for t in trials if t["id"] == trial_id), None)
                    _require(trial is not None and _positive(trial["round_id"]), "unknown_trial")
                    assert trial is not None
                    saved = db.execute("SELECT * FROM rounds WHERE k=?", (trial["round_id"],)).fetchone()
                    _require(saved is not None and saved["mode"] == "fixed", "unsupported_round")
                    frozen_spec = parse_json(trial["spec_json"])
                    expected = config.comparison(trial["candidate_id"], trial["incumbent_id"])
                    _require(saved["sample_size"] == trial["sample_size"]
                             and _canonical(parse_json(saved["spec"])) == _canonical(frozen_spec)
                             == _canonical(asdict(expected)),
                             "invalid_trial")
                    k, n = trial["round_id"], trial["sample_size"]
                    comparison, comparison_id = frozen_spec, expected.identity
                    incumbent_id, candidate_id = expected.incumbent_id, expected.candidate_id
                    # Older/partial diagnostic schemas may lack the version.
                    # Never substitute the current champion's later version.
                    incumbent_version = (trial["incumbent_version"]
                                         if "incumbent_version" in trial.keys() else None)
                    _require(incumbent_version is None or _positive(incumbent_version),
                             "invalid_trial")
                    version_source = "frozen_trial" if incumbent_version is not None else "unknown"
                arithmetic = fixed_plan_feasibility(
                    alpha=config.alpha, round_index=k, sample_size=n, token_cap=config.token_cap,
                    minimum_token_reduction=config.minimum_token_reduction)
                required = n * config.calls_per_pair + int(screening) if trial_id is None else 0
                affordable = min(MAX_CONTROLLER_SAMPLES, max(
                    0, (config.max_calls - allocated - int(screening)) // config.calls_per_pair))
                minimum = arithmetic["minimum_samples"]
                result = {
                    "schema_version": 1, "diagnostic_only": True,
                    "config_id": config.identity, "registry_id": registry["registry_id"],
                    "synthetic_only": config.synthetic_only,
                    "round_index": k, "sample_size": n, "trial_id": trial_id,
                    "round_source": "next_autoincrement_snapshot" if trial_id is None else "existing_trial",
                    "arithmetic": arithmetic,
                    "budget": {
                        "status": ("within_snapshot_allocation" if allocated + required <= config.max_calls
                                   else "budget_exhausted"),
                        "allocated_call_slots": allocated, "additional_required_call_slots": required,
                        "max_calls": config.max_calls, "calls_per_pair": config.calls_per_pair,
                        "screening": screening, "affordable_samples": affordable,
                        "necessary_minimum_fits_remaining_slots": (
                            minimum <= affordable if minimum is not None and trial_id is None else None),
                    },
                    "candidate": {
                        "scope": "current_champion_snapshot",
                        "status": ("existing_trial_no_new_admission" if trial_id is not None else
                                   "available_at_snapshot" if candidate_slots and available else
                                   "candidate_unavailable"),
                        "slots_remaining": candidate_slots, "available_candidate_ids": available,
                    },
                    "incumbent_id": incumbent_id, "incumbent_version": incumbent_version,
                    "incumbent_version_source": version_source, "candidate_id": candidate_id,
                    "comparison": comparison, "comparison_id": comparison_id,
                    "current_champion": {"policy_id": policy.policy_id, "version": champion["version"]},
                    "freshness": "UNVERIFIED", "native_comparability": "UNVERIFIED",
                    "reservation": False, "authority": False, "certificate": False,
                    "future_budget_guarantee": False, "snapshot_sha256": before[1],
                    "snapshot_contract": "sidecar_free_immutable_read_with_before_after_digest",
                    "concurrency": "changes_rejected_no_retry_not_a_reservation",
                }
            finally:
                db.close()
            _require(fingerprint() == before, "snapshot_changed")
            return result
        except OptimizerError:
            raise
        except (OSError, sqlite3.Error, TypeError, ValueError, KeyError, OverflowError):
            raise OptimizerError("invalid_feasibility_snapshot") from None

    def _check(self, db):
        accounting = db.execute("SELECT version FROM opt_accounting WHERE id=1").fetchone()
        _require(accounting is not None and accounting[0] == 2, "accounting_schema_mismatch")
        row = db.execute("SELECT value FROM opt_config WHERE id=1").fetchone()
        _require(row is not None and row[0] == self._config_text
                 and _canonical(asdict(self.config)) == self._config_text,
                 "configuration_changed")

    @contextmanager
    def _transaction(self):
        with self._registry._transaction() as db:
            self._check(db)
            yield db

    def _policy(self, db, policy_id):
        row = db.execute("SELECT policy_json FROM opt_policies WHERE policy_id=?",
                         (policy_id,)).fetchone()
        _require(row is not None, "unknown_policy")
        try:
            policy = decode_policy(row[0])
            _require(policy.policy_id == policy_id and policy.to_json() == row[0],
                     "policy_identity_mismatch")
            return policy
        except (TypeError, ValueError):
            raise OptimizerError("policy_identity_mismatch") from None

    def _champion(self, db):
        row = db.execute("SELECT * FROM opt_champion WHERE id=1").fetchone()
        _require(row is not None, "not_initialized")
        policy = self._policy(db, row["policy_id"])
        # A registry owns one closed policy family, including inactive branches
        # after rollback. Never reinterpret history as a cross-family promotion.
        for saved in db.execute(
            """SELECT policy_id FROM opt_history
               UNION SELECT previous_id FROM opt_history WHERE previous_id IS NOT NULL"""
        ):
            _same_policy_family(policy, self._policy(db, saved[0]))
        return row

    def _slots(self, db):
        pairs = db.execute("SELECT COALESCE(SUM(sample_size),0) FROM opt_trials").fetchone()[0]
        screens = db.execute("SELECT COUNT(*) FROM opt_learning WHERE kind='screening'").fetchone()[0]
        baseline = db.execute(
            """SELECT COALESCE(SUM(MAX(call_limit,reported_calls)),0)
               FROM opt_baseline_attempts""").fetchone()[0]
        return pairs * self.config.calls_per_pair + screens + baseline

    def preflight_learning(self, task_ids: Iterable[str], *, screening: bool = False) -> dict:
        """Read-only admission snapshot, NOT a reservation or model authority.

        Check ID syntax/non-reuse and the full batch plus optional single screen
        against current candidate/call allocations in one checked transaction.
        Corpus membership remains the host's responsibility. The bounded input
        iterable is consumed once; the receipt carries its materialized IDs.
        Nothing is proposed, reserved or spent. State may change after return:
        existing freeze/evaluate reservations remain the final race gates.
        """
        _require(type(screening) is bool, "invalid_screening_flag")
        _require(not isinstance(task_ids, (str, bytes)), "invalid_task_ids")
        with self._transaction() as db:
            champion = self._champion(db)
            max_tasks = self.config.max_calls // self.config.calls_per_pair
            try:
                ids = self._registry._task_ids(tuple(islice(task_ids, max_tasks + 1)))
                hashes = tuple(_hash(task) for task in ids)
            except (TypeError, ValueError):
                raise OptimizerError("invalid_task_ids") from None
            trial_count = db.execute("SELECT COUNT(*) FROM opt_trials").fetchone()[0]
            _require(trial_count < self.config.max_candidates, "candidate_budget_exhausted")
            spent = self._slots(db)
            required = len(ids) * self.config.calls_per_pair + int(screening)
            _require(spent + required <= self.config.max_calls, "call_budget_exhausted")
            _require(not any(db.execute("SELECT 1 FROM tasks WHERE task_hash=?", (digest,)).fetchone()
                             for digest in hashes), "task_already_consumed")
            incumbent = self._policy(db, champion["policy_id"])
            tried = {row[0] for row in db.execute(
                "SELECT candidate_id FROM opt_trials WHERE incumbent_id=?", (incumbent.policy_id,))}
            available = tuple(p.policy_id for p in sorted(
                (p for p in _policy_neighbors(incumbent) if p.policy_id not in tried),
                key=controller_policy_sort_key,
            ))
            _require(bool(available), "no_available_candidates")
            return {
                "reservation": False, "config_id": self.config.identity,
                "incumbent_id": incumbent.policy_id, "incumbent_version": champion["version"],
                "task_ids": ids, "samples": len(ids), "screening": screening,
                "required_call_slots": required, "calls_budget_spent": spent,
                "candidate_slots_remaining": self.config.max_candidates - trial_count,
                "available_candidate_ids": available,
            }

    def initialize(
        self, baseline: ControllerPolicy, *, validator, validation_call_limit: int,
        search_task_ids=(),
    ):
        """Reserve baseline learning BEFORE ``validator(policy, config, reservation)``.

        Return BaselineValidation with a complete TaskTrace using the reserved
        task/run IDs. Deterministic checks declare limit=0 and return an explicit
        complete empty trace. Unknown/failed attempts spend their full allowance;
        capture is never inferred from a passed boolean or an evidence digest.
        """
        _require(type(baseline) in (RequestPolicy, RuntimePolicy) and callable(validator),
                 "invalid_baseline")
        _require(baseline_policy_admissible(baseline), "enabled_baseline_required")
        _require(type(validation_call_limit) is int
                 and 0 <= validation_call_limit <= self.config.max_calls,
                 "invalid_validation_call_limit")
        _require(not isinstance(search_task_ids, (str, bytes)), "invalid_task_ids")
        search_ids = tuple(search_task_ids)
        if search_ids:
            self._registry._task_ids(search_ids)
        wire = baseline.to_json()
        policy = decode_policy(wire)
        event = "baseline-" + uuid.uuid4().hex
        reservation = BaselineReservation(event, event, validation_call_limit)
        with self._transaction() as db:
            _require(db.execute("SELECT 1 FROM opt_champion").fetchone() is None,
                     "already_initialized")
            _require(self._slots(db) + validation_call_limit <= self.config.max_calls,
                     "call_budget_exhausted")
            # Exclude the baseline task and supplied exposed tasks atomically
            # with its call allowance, before invoking any validator code.
            db.executemany("INSERT INTO tasks(task_hash,round_id,kind) VALUES(?,NULL,'excluded')",
                           [(_hash(t),) for t in (event, *search_ids)])
            db.executemany("INSERT INTO opt_search_tasks VALUES(?)", [(t,) for t in search_ids])
            db.execute("""INSERT INTO opt_baseline_attempts(task_id,policy_id,call_limit,state)
                          VALUES(?,?,?,'pending')""",
                       (event, policy.policy_id, validation_call_limit))
            db.execute("""INSERT INTO opt_learning(event_id,kind,task_id,state,coverage)
                          VALUES(?,'baseline',?,'pending','unknown')""", (event, event))
            db.execute("INSERT INTO opt_learning_runs VALUES(?,'baseline',NULL,?,'pending')",
                       (event, _canonical([event])))
        try:
            reservation_text = _canonical(asdict(reservation))
            validation = validator(policy, self.config, reservation)
            if isinstance(validation, BaselineValidation):
                # A misbehaving adapter cannot hide reported over-budget calls.
                # Still reject the baseline; no clipping to the declared limit.
                with self._transaction() as db:
                    db.execute("UPDATE opt_baseline_attempts SET reported_calls=? WHERE task_id=?",
                               (len(validation.trace.calls), event))
                # Exposure is irreversible even when metadata/coverage/limits
                # later invalidate this returned evidence.
                self._consume_reported_calls(event, validation.trace.calls)
            _require(isinstance(validation, BaselineValidation)
                     and validation.policy_id == baseline.policy_id
                     and validation.config_id == self.config.identity
                     and validation.oracle_id == self.config.oracle_id
                     and policy.to_json() == wire and baseline.to_json() == wire
                     and _canonical(asdict(reservation)) == reservation_text,
                     "baseline_validation_failed")
            trace = validation.trace
            _require(trace.task_id == event and trace.learning_run_id == event
                     and trace.policy_id == policy.policy_id
                     and len(trace.calls) <= validation_call_limit, "invalid_baseline_trace")
            self._stage_event(event, trace)
            self._complete_event(event)
            self.seal_learning_run(event)
            with self._transaction() as db:
                if validation.passed and db.execute("SELECT 1 FROM opt_champion").fetchone() is None:
                    db.execute("INSERT INTO opt_policies VALUES(?,?)", (policy.policy_id, wire))
                    seq = db.execute(
                        """INSERT INTO opt_history(action,policy_id,validation_json)
                           VALUES('initialize',?,?)""",
                        (policy.policy_id, _canonical(asdict(validation))),
                    ).lastrowid
                    db.execute("INSERT INTO opt_champion VALUES(1,?,1,?)", (policy.policy_id, seq))
                    db.execute("UPDATE opt_baseline_attempts SET state='accepted' WHERE task_id=?",
                               (event,))
                    accepted = True
                else:
                    db.execute("UPDATE opt_baseline_attempts SET state='rejected' WHERE task_id=?",
                               (event,))
                    accepted = False
            _require(accepted, "baseline_validation_failed")
        except BaseException as error:
            with self._transaction() as db:
                db.execute("""UPDATE opt_baseline_attempts SET state=?
                              WHERE task_id=? AND state='pending'""",
                           ("failed" if isinstance(error, Exception) else "cancelled", event))
                self._invalidate_event(db, event)
            if not isinstance(error, Exception):
                raise
            raise OptimizerError("baseline_validation_failed") from None
        return self.status()

    def exclude_search_tasks(self, task_ids: Iterable[str]):
        _require(not isinstance(task_ids, (str, bytes)), "invalid_task_ids")
        ids = tuple(task_ids)
        if not ids:
            return
        # Registry reserves globally before anything is exposed to ranking.
        self._registry.exclude_tasks(ids)
        with self._transaction() as db:
            db.executemany("INSERT INTO opt_search_tasks VALUES(?)", [(t,) for t in ids])

    def propose(
        self, *, search_task_ids=(), screener=None, summaries=None, data_classification=None,
    ) -> tuple[ControllerPolicy, ...]:
        """Deterministic neighbor ordering, optionally reordered by advisory Jev.

        Only supplied summaries are disclosed, never automatic repository/task
        capture. Expose/exclude their source task IDs before passing a screener.
        A failed/abstaining screener preserves the deterministic order.
        """
        self.exclude_search_tasks(search_task_ids)
        with self._transaction() as db:
            champion = self._champion(db)
            policy = self._policy(db, champion["policy_id"])
            tried = {row[0] for row in db.execute(
                "SELECT candidate_id FROM opt_trials WHERE incumbent_id=?", (policy.policy_id,))}
            candidates = tuple(sorted(
                (p for p in _policy_neighbors(policy) if p.policy_id not in tried),
                key=controller_policy_sort_key,
            ))
            for candidate in candidates:
                db.execute("INSERT OR IGNORE INTO opt_policies VALUES(?,?)",
                           (candidate.policy_id, candidate.to_json()))
                self._policy(db, candidate.policy_id)
        if screener is None or not candidates:
            return candidates
        _require(data_classification in ("synthetic", "sanitized")
                 and type(summaries) is dict
                 and set(summaries) == {p.policy_id for p in candidates},
                 "screening_disclosure_required")
        event = "screen-" + uuid.uuid4().hex
        with self._transaction() as db:
            _require(self._slots(db) < self.config.max_calls, "call_budget_exhausted")
            db.execute("INSERT INTO tasks(task_hash,round_id,kind) VALUES(?,NULL,'excluded')",
                       (_hash(event),))
            db.execute("""INSERT INTO opt_learning(event_id,kind,task_id,state,coverage)
                          VALUES(?,'screening',?,'pending','unknown')""", (event, event))
            # The screening call ID is known before any network side effect.
            db.execute("INSERT INTO opt_call_ids VALUES(?,?)", (_hash(event), event))
            db.execute("""INSERT INTO opt_learning_runs VALUES(?,'screening',NULL,?,'pending')""",
                       (event, _canonical([event])))
        questions = {"proposal": {
            "type": "choice",
            "instructions": "Rank supplied candidate summaries for fewer total tokens while "
                            "preserving independently verified success; abstain if unclear.",
            "criteria": {**{p.policy_id: None for p in candidates}, "abstain": None},
        }}
        try:
            result = screener.decide(summaries, questions, data_classification=data_classification)
            _require(isinstance(result, JevResult), "invalid_screening_result")
            self._capture_screen(event, result)
            if result.ok and result.validate(questions):
                choice = result.payload["answers"]["proposal"]["choice"]
                if choice != "abstain":
                    return tuple(sorted(candidates, key=lambda p: p.policy_id != choice))
        except Exception:
            self._failed_event(event)
        except BaseException:
            self._failed_event(event)
            raise
        return candidates

    @staticmethod
    def _invalidate_event(db, event):
        """Never turn a rejected/pending capture into a sealable completed event."""
        row = db.execute("SELECT coverage,trial_id FROM opt_learning WHERE event_id=?",
                         (event,)).fetchone()
        _require(row is not None, "unknown_learning_event")
        if row["coverage"] == COMPLETE:
            return  # Already accepted measurement (e.g. a rejected baseline).
        db.execute("""UPDATE opt_learning SET state='invalid',coverage='unknown',
                      input_tokens=NULL,output_tokens=NULL,calls_count=NULL,records_json=NULL
                      WHERE event_id=?""", (event,))
        run_id = f"trial-{row['trial_id']}" if row["trial_id"] is not None else event
        db.execute("UPDATE opt_learning_runs SET state='incomplete' WHERE run_id=?", (run_id,))

    def _check_trace_ownership(self, db, event, trace):
        trace.validate_complete()
        _require(trace.measurement == self.config.measurement and trace.phase == "learning",
                 "invalid_learning_measurement")
        owned = {r[0] for r in db.execute(
            "SELECT call_hash FROM opt_call_ids WHERE event_id=?", (event,))}
        _require(owned == {_hash(c.call_id) for c in trace.calls}, "invalid_call_ownership")

    def _expose_call_ids(self, db, event, call_ids):
        """Consume all valid IDs in the caller's transaction; return rejection."""
        rejection = None
        seen = set()
        row = db.execute("SELECT state,coverage FROM opt_learning WHERE event_id=?",
                         (event,)).fetchone()
        _require(row is not None and row["coverage"] != COMPLETE, "event_not_pending")
        if row["state"] != "pending":
            rejection = "event_not_pending"
        for call_id in call_ids:
            if not isinstance(call_id, str) or not call_id.strip():
                rejection = "invalid_reported_call_id"
                continue
            try:
                digest = _hash(call_id)
            except UnicodeError:
                rejection = "invalid_reported_call_id"
                continue
            if digest in seen:
                rejection = "repeated_reported_call_id"
            seen.add(digest)
            owner = db.execute("SELECT event_id FROM opt_call_ids WHERE call_hash=?",
                               (digest,)).fetchone()
            if owner is not None and owner[0] != event:
                rejection = "reused_call_id"
            if db.execute("SELECT 1 FROM calls WHERE call_hash=?", (digest,)).fetchone() is not None:
                rejection = "reused_registry_call_id"
            if owner is None:
                db.execute("INSERT INTO opt_call_ids VALUES(?,?)", (digest, event))
        return rejection

    def _consume_reported_calls(self, event, calls):
        """Commit every new reported ID before raising any batch rejection.

        This is exposure bookkeeping, NOT accepted learning evidence. Collisions
        preserve their original owner; unseen siblings become owned by this
        event even when any sibling is invalid. Later rejection/cancellation
        never releases them. No schema rewrite or registry reset is involved.
        """
        with self._transaction() as db:
            rejection = self._expose_call_ids(
                db, event, (c.call_id if isinstance(c, CallRecord) else None for c in calls))
            if rejection is not None:
                self._invalidate_event(db, event)
        # Raising INSIDE the transaction would resurrect all inserted siblings.
        if rejection is not None:
            raise OptimizerError(rejection)

    def _partial_trace_counts(self, trial, task_id, traces):
        """Validate metadata before summing individually complete captured calls.

        An incomplete TaskTrace is never relabelled complete. Partial CallRecords
        remain diagnostic data, not accepted counts or invented zero-output calls.
        """
        _require(1 <= len(traces) <= 2, "invalid_runtime_trace")
        clean = tuple(_trace_from_dict(asdict(t)) for t in traces)
        policies: set[str] = set()
        expected: set[str] = set()
        measured = []
        for trace in clean:
            _require(trace.task_id == task_id and trace.phase == "learning"
                     and trace.learning_run_id == trial.learning_run_id
                     and trace.measurement == trial.comparison.measurement == self.config.measurement
                     and trace.policy_id in (trial.incumbent.policy_id, trial.candidate.policy_id)
                     and trace.policy_id not in policies, "invalid_runtime_trace")
            policies.add(trace.policy_id)
            declared = set(trace.expected_call_ids)
            observed = {c.call_id: c for c in trace.calls}
            _require(len(declared) == len(trace.expected_call_ids)
                     and len(observed) == len(trace.calls)
                     and not expected.intersection(declared)
                     and set(observed) <= declared, "invalid_runtime_trace")
            expected.update(declared)
            if trace.coverage == COMPLETE:
                trace.validate_complete()
            checked = set()
            for call in trace.calls:
                _require(call.task_id == task_id and call.phase == "learning"
                         and call.measurement_id == self.config.measurement.identity
                         and call.model_id == self.config.model_id
                         and (call.parent_call_id is None or call.parent_call_id in declared),
                         "invalid_runtime_trace")
                path, current = set(), call.call_id
                while current in observed and current not in checked:
                    _require(current not in path, "invalid_runtime_trace")
                    path.add(current)
                    current = observed[current].parent_call_id
                checked.update(path)
                if call.coverage == COMPLETE:
                    call.validate_complete()
                    _require(call.input_sha256 is not None and call.output_sha256 is not None,
                             "invalid_runtime_trace")
                    measured.append(call)
        return clean, measured

    def _record_failed_evaluation(self, event, trial, task_id, attempt, current, frozen_text):
        # Union expected and observed IDs for exposure; their normal overlap is
        # not a collision. Duplicate/mismatched trace inventories still reject
        # trust below, after every identifiable ID has been durably claimed.
        call_ids, malformed_ids, reported_traces = {}, False, []
        trace_hashes: list[str | None] = []
        for trace in attempt.traces:
            calls = trace.calls if isinstance(trace.calls, (tuple, list)) else ()
            expected = trace.expected_call_ids if isinstance(trace.expected_call_ids, (tuple, list)) else ()
            if calls is not trace.calls or expected is not trace.expected_call_ids:
                malformed_ids = True
            for call_id in (*expected, *(getattr(c, "call_id", None) for c in calls)):
                if not isinstance(call_id, str) or not call_id.strip():
                    malformed_ids = True
                    continue
                try:
                    call_ids[call_id] = _hash(call_id)
                except UnicodeError:
                    malformed_ids = True
            try:
                text = _canonical(asdict(trace))
                trace_hashes.append(_hash(text))
                reported_traces.append(json.loads(text))
            except (ValueError, TypeError, AttributeError, RecursionError):
                trace_hashes.append(None)
                reported_traces.append(None)
        valid_receipts = []
        for digest in attempt.receipt_sha256s:
            if type(digest) is not str:
                continue
            try:
                _digest(digest, "runtime_receipt")
                valid_receipts.append(digest)
            except ValueError:
                pass
        payload = {
            "kind": "runtime_evaluation_attempt", "version": 1,
            "state": "interrupted" if isinstance(attempt, EvaluationAttemptInterrupted) else "failed",
            "reason": (attempt.reason if type(attempt.reason) is str
                       and attempt.reason in _EvaluationAttempt._reasons else
                       "interrupted" if isinstance(attempt, EvaluationAttemptInterrupted)
                       else "runtime_failed"),
            "receipt_sha256s": valid_receipts,
            "reported_trace_sha256s": trace_hashes, "traces": reported_traces,
            "trace_scope": "Rejected-attempt metadata only; never accepted observations or outcomes.",
            "counts_trusted": False, "metadata_rejection": None,
            "exposed_call_hashes": list(call_ids.values()),
            "unresolved_call_hashes": list(call_ids.values()),
            "known_input_tokens": None, "known_output_tokens": None,
            "known_reference_tokens": None, "known_calls": None,
            "complete_arm_policy_ids": [],
            "missing_arm_policy_ids": [trial.incumbent.policy_id, trial.candidate.policy_id],
            "exceeded_call_bound": len(call_ids) > trial.calls_per_pair,
        }
        with self._transaction() as db:
            rejection = self._expose_call_ids(db, event, call_ids)
            try:
                _require(rejection is None and not malformed_ids, "invalid_runtime_call_ownership")
                _require(valid_receipts and len(valid_receipts) == len(attempt.receipt_sha256s),
                         "invalid_runtime_receipts")
                _require(_canonical(asdict(current)) == frozen_text, "evaluator_mutated_trial")
                clean, measured = self._partial_trace_counts(trial, task_id, attempt.traces)
                known_ids = {_hash(c.call_id) for c in measured}
                inputs = sum(c.reference_input_tokens for c in measured)
                outputs = sum(c.reference_output_tokens for c in measured)
                payload.update(
                    counts_trusted=True, traces=[asdict(t) for t in clean],
                    known_input_tokens=inputs, known_output_tokens=outputs,
                    known_reference_tokens=inputs + outputs, known_calls=len(measured),
                    unresolved_call_hashes=[h for h in call_ids.values() if h not in known_ids],
                    complete_arm_policy_ids=[t.policy_id for t in clean if t.coverage == COMPLETE],
                    missing_arm_policy_ids=[p for p in (trial.incumbent.policy_id, trial.candidate.policy_id)
                                            if p not in {t.policy_id for t in clean}],
                )
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
                payload["metadata_rejection"] = rejection or "invalid_runtime_attempt_metadata"
            # Invalidation clears accepted columns, but intentionally leaves this
            # separate rejected-attempt evidence. No success flag or observation.
            self._invalidate_event(db, event)
            db.execute("UPDATE opt_learning SET diagnostics_json=? WHERE event_id=?",
                       (_canonical(payload), event))

    def _failed_evaluations(self, db):
        """Separate diagnostic inventory; never exported as complete TaskTraces."""
        attempts, tokens_known, calls_known = [], 0, 0
        for row in db.execute(
            """SELECT event_id,task_id,trial_id,diagnostics_json FROM opt_learning
               WHERE kind='confirmation' AND coverage!=? AND diagnostics_json IS NOT NULL
               ORDER BY event_id""", (COMPLETE,),
        ):
            value = json.loads(row["diagnostics_json"])
            if value.get("kind") != "runtime_evaluation_attempt":
                continue
            _require(value.get("version") == 1, "invalid_runtime_attempt_diagnostics")
            if value["counts_trusted"] is True:
                _require(all(type(value[k]) is int and value[k] >= 0 for k in (
                    "known_input_tokens", "known_output_tokens", "known_reference_tokens", "known_calls"))
                    and value["known_reference_tokens"]
                    == value["known_input_tokens"] + value["known_output_tokens"],
                    "invalid_runtime_attempt_diagnostics")
                tokens_known += value["known_reference_tokens"]
                calls_known += value["known_calls"]
            attempts.append({**value, "event_id": row["event_id"],
                             "task_id": row["task_id"], "trial_id": row["trial_id"]})
        return {"failed_evaluations": attempts, "known_partial_reference_tokens": tokens_known,
                "known_partial_calls": calls_known, "unresolved_evaluation_attempts": len(attempts),
                "partial_accounting_scope": "Typed runtime failure receipts only; other unknown events remain unknown."}

    def _stage_event(self, event, trace):
        """Reserve GLOBAL call IDs atomically; capture is not yet accepted evidence."""
        self._consume_reported_calls(event, trace.calls)
        trace.validate_complete()
        _require(trace.measurement == self.config.measurement and trace.phase == "learning"
                 and all(c.input_sha256 is not None and c.output_sha256 is not None
                         for c in trace.calls), "invalid_learning_measurement")
        with self._transaction() as db:
            row = db.execute("SELECT * FROM opt_learning WHERE event_id=?", (event,)).fetchone()
            _require(row is not None and row["state"] == "pending"
                     and row["task_id"] == trace.task_id, "event_not_pending")
            run_id = f"trial-{row['trial_id']}" if row["trial_id"] is not None else event
            _require(trace.learning_run_id == run_id, "learning_run_mismatch")
            self._check_trace_ownership(db, event, trace)
            db.execute("UPDATE opt_learning SET state='captured',records_json=? WHERE event_id=?",
                       (_canonical(asdict(trace)), event))

    def _complete_event(self, event, *, state="complete"):
        """Accept globally unique capture; confirmation additionally requires registry acceptance."""
        _require(state in ("complete", "failed"), "invalid_capture_state")
        with self._transaction() as db:
            row = db.execute("SELECT * FROM opt_learning WHERE event_id=?", (event,)).fetchone()
            _require(row is not None and row["state"] == "captured", "event_not_captured")
            trace = self._trace(row["records_json"])
            self._check_trace_ownership(db, event, trace)
            totals = trace.totals()
            if row["kind"] == "confirmation":
                trial = self._trial(db, row["trial_id"], "evaluating")
                task_hash = _hash(trace.task_id)
                accepted = db.execute(
                    "SELECT * FROM observations WHERE task_hash=? AND round_id=?",
                    (task_hash, trial.round_id),
                ).fetchone()
                _require(accepted is not None and
                         accepted["incumbent_tokens"] + accepted["candidate_tokens"]
                         == totals.total_tokens, "registry_observation_required")
                registry_calls = {r[0] for r in db.execute(
                    "SELECT call_hash FROM calls WHERE task_hash=?", (task_hash,))}
                _require(registry_calls == {_hash(c.call_id) for c in trace.calls},
                         "registry_calls_mismatch")
            db.execute("""UPDATE opt_learning SET state=?,coverage=?,input_tokens=?,
                          output_tokens=?,calls_count=? WHERE event_id=?""",
                       (state, COMPLETE, totals.input_tokens, totals.output_tokens,
                        totals.calls, event))

    def _failed_event(self, event):
        with self._transaction() as db:
            self._invalidate_event(db, event)

    def _capture_screen(self, event, result):
        input_count = output_count = None
        record = None
        complete = (result.request_text is not None and result.response_text is not None
                    and result.diagnostics.response_complete)
        if complete:
            record = measure_call(
                self.config.measurement, self._count,
                input_text=result.request_text, output_text=result.response_text,
                call_id=event, task_id=event, attempt_id=event, phase="learning",
                role="auxiliary", model_id=JEV_MODEL, harness_id="optimizer-screen-v1",
                coverage=COMPLETE, completion_status="succeeded" if result.ok else "failed",
            )
            input_count, output_count = record.reference_input_tokens, record.reference_output_tokens
        else:
            if result.request_text is not None:
                input_count = self._count(result.request_text)
                _require(type(input_count) is int and input_count >= 0, "invalid_reference_count")
            if result.response_text is not None:
                output_count = self._count(result.response_text)
                _require(type(output_count) is int and output_count >= 0, "invalid_reference_count")
        if complete:
            assert record is not None  # A complete body pair was measured above.
            trace = TaskTrace(
                event, "jev-screening-v1", self.config.measurement, "learning",
                (record,), (event,), COMPLETE, event,
            )
            self._stage_event(event, trace)
            self._complete_event(event, state="complete" if result.ok else "failed")
        with self._transaction() as db:
            db.execute("UPDATE opt_learning SET diagnostics_json=? WHERE event_id=?",
                       (_canonical(asdict(result.diagnostics)), event))
            if not complete:
                db.execute("""UPDATE opt_learning SET state='partial',input_tokens=?,
                              output_tokens=? WHERE event_id=?""",
                           (input_count, output_count, event))
                db.execute("UPDATE opt_learning_runs SET state='incomplete' WHERE run_id=?", (event,))
        if complete:
            self.seal_learning_run(event)

    def freeze(self, candidate_id: str, *, sample_size: int) -> FrozenTrial:
        """Freeze all identities/bounds before requesting any confirmation tasks."""
        _require(type(candidate_id) is str and _positive(sample_size, 1_000_000),
                 "invalid_trial")
        with self._transaction() as db:
            champion = self._champion(db)
            incumbent = self._policy(db, champion["policy_id"])
            candidate = self._policy(db, candidate_id)
            _same_policy_family(incumbent, candidate)
            _require(candidate_id in {p.policy_id for p in _policy_neighbors(incumbent)},
                     "not_current_neighbor")
            _require(db.execute("SELECT COUNT(*) FROM opt_trials").fetchone()[0]
                     < self.config.max_candidates, "candidate_budget_exhausted")
            _require(self._slots(db) + sample_size * self.config.calls_per_pair
                     <= self.config.max_calls, "call_budget_exhausted")
            _require(db.execute("SELECT 1 FROM opt_trials WHERE candidate_id=? AND incumbent_id=?",
                                (candidate_id, incumbent.policy_id)).fetchone() is None,
                     "candidate_already_attempted")
            spec = self.config.comparison(candidate.policy_id, incumbent.policy_id)
            trial_id = db.execute(
                """INSERT INTO opt_trials(spec_json,incumbent_version,candidate_id,
                   incumbent_id,sample_size,state) VALUES(?,?,?,?,?,'freezing')""",
                (_canonical(asdict(spec)), champion["version"], candidate.policy_id,
                 incumbent.policy_id, sample_size),
            ).lastrowid
            db.execute("INSERT INTO opt_learning_runs VALUES(?,'confirmation',?,NULL,'pending')",
                       (f"trial-{trial_id}", trial_id))
        # A crash in this interval spends the reserved slots. Any orphan registry
        # round also remains spent; no recovery path resets or recycles it.
        try:
            round_id = self._registry.start_round(spec, sample_size=sample_size)
            with self._transaction() as db:
                row = db.execute("SELECT state FROM opt_trials WHERE id=?", (trial_id,)).fetchone()
                if row[0] != "freezing":
                    db.execute("UPDATE rounds SET state='closed' WHERE k=?", (round_id,))
                    raise OptimizerError("trial_cancelled")
                db.execute("UPDATE opt_trials SET round_id=?,state='frozen' WHERE id=?",
                           (round_id, trial_id))
                return self._trial(db, trial_id)
        except BaseException:
            self._end_trial(trial_id, "failed")
            raise

    def _trial(self, db, trial_id, required_state=None):
        _require(_positive(trial_id), "invalid_trial_id")
        row = db.execute("SELECT * FROM opt_trials WHERE id=?", (trial_id,)).fetchone()
        _require(row is not None and row["round_id"] is not None, "unknown_trial")
        _require(required_state is None or row["state"] == required_state, "trial_not_ready")
        incumbent, candidate = self._policy(db, row["incumbent_id"]), self._policy(db, row["candidate_id"])
        _same_policy_family(incumbent, candidate)
        expected = self.config.comparison(candidate.policy_id, incumbent.policy_id)
        _require(row["spec_json"] == _canonical(asdict(expected)), "comparison_changed")
        self._registry._round(db, row["round_id"], expected)
        return FrozenTrial(row["id"], row["round_id"], row["incumbent_version"],
                           expected, incumbent, candidate, row["sample_size"],
                           self.config.calls_per_pair)

    def _current(self, db, trial):
        champion = self._champion(db)
        _require(champion["policy_id"] == trial.incumbent.policy_id
                 and champion["version"] == trial.incumbent_version, "stale_incumbent")

    def _end_trial(self, trial_id, state):
        with self._transaction() as db:
            row = db.execute("SELECT round_id,state FROM opt_trials WHERE id=?", (trial_id,)).fetchone()
            _require(row is not None, "unknown_trial")
            if row["state"] not in ("promoted", "cancelled", "failed", "inconclusive"):
                db.execute("UPDATE opt_trials SET state=? WHERE id=?", (state, trial_id))
                if row["round_id"] is not None:
                    db.execute("UPDATE rounds SET state='closed' WHERE k=?", (row["round_id"],))
            for event in db.execute(
                "SELECT event_id FROM opt_learning WHERE trial_id=? AND coverage!=?",
                (trial_id, COMPLETE),
            ).fetchall():
                self._invalidate_event(db, event[0])
            db.execute("UPDATE opt_learning_runs SET state='incomplete' WHERE trial_id=? AND state!='sealed'",
                       (trial_id,))

    def cancel(self, trial_id: int):
        _require(_positive(trial_id), "invalid_trial_id")
        self._end_trial(trial_id, "cancelled")
        return self.status()

    def evaluate(self, trial_id: int, fresh_task_ids: Iterable[str]) -> Certificate:
        """Claim once, reserve ALL tasks before the first independent callback.

        Interrupted/failed trials cannot replay, even after restart. Recovery is a
        new candidate/round on genuinely fresh tasks, within the original bounds.
        Trusted adapters may raise EvaluationAttemptFailed/Interrupted with
        partial traces and receipt digests. Their known costs remain diagnostics,
        never a completed paired observation or an outcome.
        """
        evaluator = self._evaluator
        if evaluator is None:
            raise OptimizerError("independent_evaluator_required")
        with self._transaction() as db:
            trial = self._trial(db, trial_id, "frozen")
            self._current(db, trial)
            db.execute("UPDATE opt_trials SET state='reserving' WHERE id=?", (trial_id,))
        try:
            # Registry validates IDs and uniqueness before evaluation. Generators
            # are consumed only after the frozen round exists.
            _require(not isinstance(fresh_task_ids, (str, bytes)), "invalid_task_ids")
            ids = tuple(islice(fresh_task_ids, trial.sample_size + 1))
            _require(len(ids) == trial.sample_size, "sample_size_mismatch")
            self._registry.reserve_tasks(trial.round_id, trial.comparison, ids)
            with self._transaction() as db:
                self._trial(db, trial_id, "reserving")
                db.execute("UPDATE opt_trials SET state='evaluating' WHERE id=?", (trial_id,))
                db.execute("UPDATE opt_learning_runs SET expected_tasks_json=? WHERE run_id=?",
                           (_canonical(ids), trial.learning_run_id))
                db.executemany(
                    """INSERT INTO opt_learning(event_id,kind,trial_id,task_id,state,coverage)
                       VALUES(?,'confirmation',?,?,'pending','unknown')""",
                    [(f"trial-{trial_id}:{t}", trial_id, t) for t in ids],
                )
            for task_id in ids:
                with self._transaction() as db:
                    current = self._trial(db, trial_id, "evaluating")
                    self._current(db, current)
                    event = f"trial-{trial_id}:{task_id}"
                frozen_text = _canonical(asdict(current))
                try:
                    observation = evaluator(current, task_id)
                except (EvaluationAttemptFailed, EvaluationAttemptInterrupted) as attempt:
                    self._record_failed_evaluation(event, trial, task_id, attempt, current, frozen_text)
                    raise
                if isinstance(observation, PairedObservation):
                    # Consume both arms before any validation can reject the
                    # pair (including stale IDs, bad coverage or policy mutation).
                    self._consume_reported_calls(
                        event, observation.incumbent.calls + observation.candidate.calls,
                    )
                _require(_canonical(asdict(current)) == frozen_text, "evaluator_mutated_trial")
                _require(isinstance(observation, PairedObservation)
                         and observation.task_id == task_id, "invalid_paired_observation")
                observation.validate(trial.comparison)
                calls = observation.incumbent.calls + observation.candidate.calls
                _require(len(calls) <= trial.calls_per_pair, "evaluator_exceeded_call_bound")
                _require(all(c.model_id == self.config.model_id and c.input_sha256 is not None
                             and c.output_sha256 is not None for c in calls),
                         "uncaptured_or_unpinned_model_calls")
                trace = observation.learning_trace(trial.comparison)
                _require(trace.learning_run_id == trial.learning_run_id, "learning_run_mismatch")
                self._stage_event(event, trace)
                with self._transaction() as db:
                    self._trial(db, trial_id, "evaluating")
                    self._current(db, current)
                self._registry.submit(trial.round_id, trial.comparison, [observation])
                self._complete_event(event)
            self.seal_learning_run(trial.learning_run_id)
            certificate = self._registry.certify(trial.round_id, trial.comparison)
            with self._transaction() as db:
                self._trial(db, trial_id, "evaluating")
                db.execute("UPDATE opt_trials SET state=? WHERE id=?",
                           ("certified" if certificate.decision == "certified" else "inconclusive",
                            trial_id))
            return certificate
        except BaseException as error:
            self._end_trial(trial_id, "cancelled" if not isinstance(error, Exception) else "failed")
            if not isinstance(error, Exception):
                raise
            raise OptimizerError("evaluation_failed") from None

    def _saved_certificate(self, db, trial):
        rows = db.execute("SELECT certificate FROM looks WHERE round_id=?", (trial.round_id,)).fetchall()
        _require(len(rows) == 1, "registry_certificate_required")
        certificate = Certificate.from_dict(json.loads(rows[0][0]))
        _require(certificate.registry_id == self._registry._registry_id
                 and certificate.round_id == trial.round_id
                 and certificate.comparison == trial.comparison
                 and certificate.mode == "fixed"
                 and certificate.sample_size == trial.sample_size
                 and certificate.decision == "certified"
                 and certificate.quality_difference_lower >= 0
                 and certificate.normalized_token_difference_upper
                     <= -certificate.required_normalized_token_reduction,
                 "registry_certificate_required")
        return certificate

    def promote(self, trial_id: int):
        """No certificate argument: read only the saved registry decision."""
        with self._transaction() as db:
            trial = self._trial(db, trial_id, "certified")
            self._current(db, trial)
            self._saved_certificate(db, trial)
            champion = self._champion(db)
            seq = db.execute("""INSERT INTO opt_history(action,policy_id,previous_id,parent_seq,trial_id)
                                VALUES('promote',?,?,?,?)""",
                             (trial.candidate.policy_id, trial.incumbent.policy_id,
                              champion["validated_seq"], trial_id)).lastrowid
            changed = db.execute("""UPDATE opt_champion SET policy_id=?,version=version+1,validated_seq=?
                                    WHERE id=1 AND policy_id=? AND version=?""",
                                 (trial.candidate.policy_id, seq, trial.incumbent.policy_id,
                                  trial.incumbent_version)).rowcount
            _require(changed == 1, "stale_incumbent")
            db.execute("UPDATE opt_trials SET state='promoted' WHERE id=?", (trial_id,))
        return self.status()

    def _validated_history_policy(self, db, prior):
        """Shared rollback/selection checks on one authoritative validation row."""
        _require(prior is not None, "unvalidated_rollback_target")
        policy = self._policy(db, prior["policy_id"])
        if prior["action"] == "initialize":
            _require(baseline_policy_admissible(policy), "unvalidated_rollback_target")
            validation = BaselineValidation.from_dict(json.loads(prior["validation_json"]))
            _require(validation.passed and validation.policy_id == policy.policy_id
                     and validation.config_id == self.config.identity
                     and validation.oracle_id == self.config.oracle_id,
                     "unvalidated_rollback_target")
            event = validation.trace.task_id
            saved = db.execute(
                """SELECT l.records_json,l.coverage,b.state FROM opt_learning l
                   JOIN opt_baseline_attempts b ON b.task_id=l.event_id WHERE l.event_id=?""",
                (event,),
            ).fetchone()
            _require(saved is not None and saved["coverage"] == COMPLETE
                     and saved["state"] == "accepted"
                     and saved["records_json"] == _canonical(asdict(validation.trace)),
                     "unvalidated_rollback_target")
            self._check_trace_ownership(db, event, validation.trace)
        else:
            _require(prior["action"] == "promote", "unvalidated_rollback_target")
            trial = self._trial(db, prior["trial_id"])
            _require(trial.candidate.policy_id == policy.policy_id, "unvalidated_rollback_target")
            self._saved_certificate(db, trial)
        return policy

    def _deployment_run(self, db, run_id, *, trial=None):
        """Revalidate sealed inventory and accepted trace ownership without sealing."""
        run = db.execute("SELECT * FROM opt_learning_runs WHERE run_id=?", (run_id,)).fetchone()
        kind = "confirmation" if trial else "baseline"
        _require(run is not None and run["kind"] == kind and run["state"] == "sealed"
                 and run["trial_id"] == (trial.trial_id if trial else None),
                 "invalid_deployment_evidence")
        expected = json.loads(run["expected_tasks_json"])
        _require(isinstance(expected, list) and expected and len(set(expected)) == len(expected),
                 "invalid_deployment_evidence")
        rows = db.execute(
            "SELECT * FROM opt_learning WHERE trial_id=?" if trial else
            "SELECT * FROM opt_learning WHERE event_id=?",
            (trial.trial_id if trial else run_id,),
        ).fetchall()
        _require(len(rows) == len(expected) and {r["task_id"] for r in rows} == set(expected),
                 "invalid_deployment_evidence")
        traces = {}
        for row in rows:
            _require(row["kind"] == kind and row["state"] == "complete"
                     and row["coverage"] == COMPLETE, "invalid_deployment_evidence")
            trace = self._trace(row["records_json"])
            self._check_trace_ownership(db, row["event_id"], trace)
            _require(trace.task_id == row["task_id"] and trace.learning_run_id == run_id
                     and row["event_id"] == (f"{run_id}:{trace.task_id}" if trial else run_id)
                     and all(c.input_sha256 is not None and c.output_sha256 is not None
                             for c in trace.calls), "invalid_deployment_evidence")
            totals = trace.totals()
            _require((row["input_tokens"], row["output_tokens"], row["calls_count"])
                     == (totals.input_tokens, totals.output_tokens, totals.calls),
                     "invalid_deployment_evidence")
            if trial:
                _require(trace.policy_id == trial.comparison.identity
                         and len(trace.calls) <= trial.calls_per_pair
                         and all(c.model_id == self.config.model_id for c in trace.calls),
                         "invalid_deployment_evidence")
            traces[_hash(trace.task_id)] = trace
        return traces

    def _deployment_certificate(self, db, trial):
        """Recompute the saved fixed gate from its registry-owned observations."""
        saved = self._saved_certificate(db, trial)
        spec = trial.comparison
        look = db.execute("SELECT n FROM looks WHERE round_id=?", (trial.round_id,)).fetchone()
        _require(look["n"] == trial.sample_size, "invalid_deployment_evidence")
        row = self._registry._round(db, trial.round_id, spec)
        _require(row["state"] == "closed" and row["mode"] == "fixed"
                 and row["sample_size"] == trial.sample_size, "invalid_deployment_evidence")
        observations = db.execute(
            "SELECT * FROM observations WHERE round_id=? ORDER BY task_hash",
            (trial.round_id,),
        ).fetchall()
        tasks = db.execute("SELECT * FROM tasks WHERE round_id=?", (trial.round_id,)).fetchall()
        traces = self._deployment_run(db, trial.learning_run_id, trial=trial)
        n = len(observations)
        _require(n == trial.sample_size and n == len(tasks) and n == len(traces)
                 and {o["task_hash"] for o in observations} == set(traces)
                 and {t["task_hash"] for t in tasks} == set(traces)
                 and all(t["kind"] == "confirmation" for t in tasks),
                 "invalid_deployment_evidence")
        for obs in observations:
            _require(all(type(obs[k]) is int and 0 <= obs[k] <= spec.token_cap
                         for k in ("incumbent_tokens", "candidate_tokens"))
                     and all(type(obs[k]) is int and obs[k] in (0, 1)
                             for k in ("incumbent_success", "candidate_success")),
                     "invalid_deployment_evidence")
            _digest(obs["evidence_hash"], "observation_evidence")
            trace = traces[obs["task_hash"]]
            _require(trace.totals().total_tokens
                     == obs["incumbent_tokens"] + obs["candidate_tokens"],
                     "invalid_deployment_evidence")
            owned = {r[0] for r in db.execute(
                "SELECT call_hash FROM calls WHERE task_hash=?", (obs["task_hash"],))}
            _require(owned == {_hash(c.call_id) for c in trace.calls},
                     "invalid_deployment_evidence")
        a = round_alpha(self.config.alpha, trial.round_id)
        r = radius(self.config.alpha, trial.round_id, n, anytime=False)
        x = math.fsum(o["candidate_success"] - o["incumbent_success"] for o in observations) / n
        z = math.fsum((o["candidate_tokens"] - o["incumbent_tokens"]) / spec.token_cap
                      for o in observations) / n
        required = spec.minimum_token_reduction / spec.token_cap
        expected = Certificate(
            schema_version=1, registry_id=self._registry._registry_id,
            round_id=trial.round_id, comparison=spec, mode="fixed",
            decision="certified" if x - r >= 0 and z + r <= -required else "not_certified",
            sample_size=n, alpha_total=self.config.alpha, alpha_round=a, alpha_look=a,
            radius=r, mean_quality_difference=x, mean_normalized_token_difference=z,
            quality_difference_lower=x - r, normalized_token_difference_upper=z + r,
            required_normalized_token_reduction=required,
            task_set_sha256=_hash(_canonical([o["task_hash"] for o in observations])),
            evidence_sha256=_hash(_canonical([dict(o) for o in observations])),
        )
        _require(_canonical(saved.to_dict()) == _canonical(expected.to_dict())
                 and expected.decision == "certified",
                 "invalid_deployment_certificate")

    def deployment_policy(
        self, *, expected_version: int, model_id: str, workload_id: str,
        environment_id: str, measurement: MeasurementIdentity,
    ) -> ControllerPolicy:
        """Freeze one validated champion for a task; no evaluation or state writes.

        Revalidate authoritative initialize/promote ancestry, including after a
        rollback. Registry filesystem integrity and truthful evaluator evidence
        remain the existing trust boundary; this is not an independent oracle.
        """
        _require(_positive(expected_version), "invalid_champion_version")
        try:
            with self._transaction() as db:
                _require(not self.config.synthetic_only, "synthetic_deployment_forbidden")
                _require(measurement == self.config.measurement
                         and model_id == self.config.model_id
                         and workload_id == self.config.workload_id
                         and environment_id == self.config.environment_id,
                         "deployment_regime_mismatch")
                champion = self._champion(db)
                _require(champion["version"] == expected_version, "stale_incumbent")
                selected = self._policy(db, champion["policy_id"])
                # History records each version transition, but rollback's target
                # remains its original initialize/promote row, not the rollback row.
                history = db.execute("SELECT * FROM opt_history ORDER BY seq").fetchall()
                ancestry, versions = {}, {}
                active = None
                for version, entry in enumerate(history, 1):
                    versions[entry["seq"]] = version
                    if active is None:
                        _require(entry["action"] == "initialize", "invalid_deployment_lineage")
                    else:
                        _require(entry["previous_id"] == active["policy_id"],
                                 "invalid_deployment_lineage")
                        if entry["action"] == "rollback":
                            _require(entry["parent_seq"] == active["parent_seq"]
                                     and entry["parent_seq"] in ancestry,
                                     "invalid_deployment_lineage")
                            active = ancestry[entry["parent_seq"]]
                            _require(entry["policy_id"] == active["policy_id"],
                                     "invalid_deployment_lineage")
                            continue
                        _require(entry["action"] == "promote"
                                 and entry["parent_seq"] == active["seq"],
                                 "invalid_deployment_lineage")
                    active = entry
                    ancestry[entry["seq"]] = entry
                _require(len(history) == expected_version and active is not None
                         and active["seq"] == champion["validated_seq"]
                         and active["policy_id"] == selected.policy_id,
                         "invalid_deployment_lineage")
                seq, policy_id = champion["validated_seq"], selected.policy_id
                while True:
                    _require(_positive(seq), "invalid_deployment_lineage")
                    prior = db.execute("SELECT * FROM opt_history WHERE seq=?", (seq,)).fetchone()
                    policy = self._validated_history_policy(db, prior)
                    _same_policy_family(selected, policy)
                    _require(policy.policy_id == policy_id and baseline_policy_admissible(policy),
                             "invalid_deployment_lineage")
                    if prior["action"] == "initialize":
                        _require(prior["parent_seq"] is None and prior["previous_id"] is None
                                 and prior["trial_id"] is None, "invalid_deployment_lineage")
                        validation = BaselineValidation.from_dict(json.loads(prior["validation_json"]))
                        event = validation.trace.task_id
                        traces = self._deployment_run(db, event)
                        baseline = db.execute(
                            "SELECT * FROM opt_baseline_attempts WHERE task_id=?", (event,),
                        ).fetchone()
                        reservation = db.execute(
                            "SELECT kind,round_id FROM tasks WHERE task_hash=?", (_hash(event),),
                        ).fetchone()
                        _require(baseline is not None and baseline["policy_id"] == policy_id
                                 and reservation is not None and reservation["kind"] == "excluded"
                                 and reservation["round_id"] is None
                                 and traces == {_hash(event): validation.trace}
                                 and validation.trace.policy_id == policy_id
                                 and len(validation.trace.calls) <= baseline["call_limit"]
                                 and len(validation.trace.calls) == baseline["reported_calls"],
                                 "invalid_deployment_lineage")
                        return selected
                    trial = self._trial(db, prior["trial_id"], "promoted")
                    _require(prior["previous_id"] == trial.incumbent.policy_id
                             and trial.incumbent_version == versions[seq] - 1
                             and prior["validation_json"] is None
                             and _positive(prior["parent_seq"]) and prior["parent_seq"] < seq,
                             "invalid_deployment_lineage")
                    self._deployment_certificate(db, trial)
                    seq, policy_id = prior["parent_seq"], trial.incumbent.policy_id
        except OptimizerError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            raise OptimizerError("invalid_deployment_evidence") from None

    def rollback(self, *, expected_version: int):
        """CAS rollback along the validated ancestry; never choose arbitrary JSON."""
        _require(_positive(expected_version), "invalid_champion_version")
        with self._transaction() as db:
            champion = self._champion(db)
            _require(champion["version"] == expected_version, "stale_incumbent")
            previous_seq = db.execute("SELECT parent_seq FROM opt_history WHERE seq=?",
                                      (champion["validated_seq"],)).fetchone()[0]
            _require(previous_seq is not None, "no_previous_champion")
            prior = db.execute("SELECT * FROM opt_history WHERE seq=?", (previous_seq,)).fetchone()
            policy = self._validated_history_policy(db, prior)
            _same_policy_family(self._policy(db, champion["policy_id"]), policy)
            db.execute("""INSERT INTO opt_history(action,policy_id,previous_id,parent_seq)
                          VALUES('rollback',?,?,?)""",
                       (policy.policy_id, champion["policy_id"], previous_seq))
            changed = db.execute("""UPDATE opt_champion SET policy_id=?,version=version+1,validated_seq=?
                                    WHERE id=1 AND version=?""",
                                 (policy.policy_id, previous_seq, expected_version)).rowcount
            _require(changed == 1, "stale_incumbent")
        return self.status()

    def status(self):
        with self._transaction() as db:
            champion = db.execute("SELECT * FROM opt_champion WHERE id=1").fetchone()
            if champion is not None:
                champion = self._champion(db)
            events = db.execute("SELECT * FROM opt_learning ORDER BY event_id").fetchall()
            runs = db.execute("SELECT * FROM opt_learning_runs ORDER BY run_id").fetchall()
            unknown = sum(e["coverage"] != COMPLETE for e in events)
            unsealed = sum(run["state"] != "sealed" for run in runs)
            known = sum((e["input_tokens"] or 0) + (e["output_tokens"] or 0) for e in events)
            partial = self._failed_evaluations(db)
            known += partial["known_partial_reference_tokens"]
            ks = [row[0] for row in db.execute("SELECT k FROM rounds ORDER BY k")]
            allocated = math.fsum(round_alpha(self.config.alpha, k) for k in ks)
            complete_calls = sum(e["calls_count"] or 0 for e in events if e["coverage"] == COMPLETE)
            unique_complete_calls = db.execute(
                """SELECT COUNT(*) FROM opt_call_ids c JOIN opt_learning l
                   ON l.event_id=c.event_id WHERE l.coverage=?""", (COMPLETE,),
            ).fetchone()[0]
            _require(complete_calls == unique_complete_calls, "invalid_call_ownership")
            return {
                "accounting_schema_version": 2,
                "initialized": champion is not None,
                "config_id": self.config.identity, "synthetic_only": self.config.synthetic_only,
                "champion": {"policy_id": champion["policy_id"], "version": champion["version"],
                             "policy": self._policy(db, champion["policy_id"]).to_dict()}
                    if champion is not None else None,
                "baseline_attempts": [dict(r) for r in db.execute(
                    "SELECT * FROM opt_baseline_attempts ORDER BY rowid")],
                "history": [dict(row) for row in db.execute("SELECT * FROM opt_history ORDER BY seq")],
                "trials": [dict(row) for row in db.execute(
                    """SELECT id,round_id,candidate_id,incumbent_id,incumbent_version,
                       sample_size,state FROM opt_trials ORDER BY id""")],
                "search_task_ids": [row[0] for row in db.execute(
                    "SELECT task_id FROM opt_search_tasks ORDER BY task_id")],
                "calls_budget_spent": self._slots(db),
                "max_calls": self.config.max_calls, "max_candidates": self.config.max_candidates,
                "budget": {"registry_id": self._registry._registry_id, "rounds": len(ks),
                           "alpha": self.config.alpha, "allocated_alpha": allocated,
                           "remaining_alpha": max(0.0, self.config.alpha - allocated)},
                "learning": {**partial, "events": len(events), "unknown_events": unknown, "deployments": 0,
                             "unsealed_runs": unsealed,
                             "coverage": "complete" if not unsealed and not unknown else "incomplete",
                             "runs": [{
                                 "run_id": r["run_id"], "state": r["state"],
                                 "expected_tasks": len(json.loads(r["expected_tasks_json"]))
                                     if r["expected_tasks_json"] is not None else None,
                             } for r in runs],
                             "complete_calls": complete_calls,
                             "unique_complete_calls": unique_complete_calls,
                             "reference_tokens": None if unknown or unsealed else known,
                             "known_reference_tokens": known},
                "limits": ["Local bounded search, not a global optimum or real-model quality promise.",
                           "Incomplete learning coverage is not a zero-cost observation."],
            }

    @staticmethod
    def _trace(text):
        return _trace_from_dict(json.loads(text))

    def seal_learning_run(self, run_id):
        """Seal only a complete predeclared inventory, never infer it from presence."""
        with self._transaction() as db:
            run = db.execute("SELECT * FROM opt_learning_runs WHERE run_id=?", (run_id,)).fetchone()
            _require(run is not None and run["expected_tasks_json"] is not None,
                     "unknown_learning_inventory")
            expected = json.loads(run["expected_tasks_json"])
            rows = db.execute(
                "SELECT * FROM opt_learning WHERE trial_id=?" if run["kind"] == "confirmation"
                else "SELECT * FROM opt_learning WHERE event_id=?",
                (run["trial_id"] if run["kind"] == "confirmation" else run_id,),
            ).fetchall()
            _require(expected and len(set(expected)) == len(expected)
                     and {r["task_id"] for r in rows} == set(expected)
                     and len(rows) == len(expected)
                     and all(r["coverage"] == COMPLETE and r["records_json"]
                             and r["state"] in ("complete", "failed") for r in rows),
                     "incomplete_learning_inventory")
            ledger = TokenLedger(self.config.measurement)
            for row in rows:
                trace = self._trace(row["records_json"])
                self._check_trace_ownership(db, row["event_id"], trace)
                _require(trace.learning_run_id == run_id, "learning_run_mismatch")
                ledger.record(trace)
            ledger.seal_learning_run(run_id, expected)
            db.execute("UPDATE opt_learning_runs SET state='sealed' WHERE run_id=?", (run_id,))

    def learning_inventory(self):
        """Accepted combined traces plus separate rejected-attempt diagnostics.

        ``known_partial_reference_tokens`` is a known subtotal, not total usage.
        Failed arm traces live only in ``failed_evaluations``, never ``traces``.
        Plain unexpected errors retain the existing unknown-event semantics.
        """
        with self._transaction() as db:
            traces = []
            for row in db.execute(
                "SELECT * FROM opt_learning WHERE coverage=? ORDER BY event_id", (COMPLETE,),
            ).fetchall():
                trace = self._trace(row["records_json"])
                self._check_trace_ownership(db, row["event_id"], trace)
                traces.append(trace)
            return {
                "runs": [{
                    "run_id": r["run_id"], "kind": r["kind"], "state": r["state"],
                    "expected_task_ids": json.loads(r["expected_tasks_json"])
                        if r["expected_tasks_json"] is not None else None,
                } for r in db.execute("SELECT * FROM opt_learning_runs ORDER BY run_id")],
                "traces": traces,
                **self._failed_evaluations(db),
            }

    def export_learning(self, ledger: TokenLedger):
        """Export ONCE to a fresh/shared ledger, then seal only complete runs.

        Requires the ledger's explicit seal_learning_run API. Unknown inventories
        remain unsealed; do not record individual paired arms as well as these
        combined traces. A predeclared horizon must include all reported run IDs.
        """
        inventory = self.learning_inventory()
        _require(isinstance(ledger, TokenLedger) and ledger.measurement == self.config.measurement,
                 "ledger_measurement_mismatch")
        if ledger.horizon is not None:
            _require({r["run_id"] for r in inventory["runs"]}
                     <= set(ledger.horizon.learning_run_ids), "learning_run_outside_horizon")
        for trace in inventory["traces"]:
            ledger.record(trace)
        for run in inventory["runs"]:
            if run["state"] == "sealed":
                ledger.seal_learning_run(run["run_id"], run["expected_task_ids"])

    def hill_climb(self, *, sample_size: int, fresh_tasks: Callable[[FrozenTrial], Iterable[str]]):
        """Bounded deterministic local search; every candidate goes through the registry."""
        _require(callable(fresh_tasks) and _positive(sample_size, 1_000_000),
                 "fresh_task_sampler_required")
        while True:
            status = self.status()
            if (len(status["trials"]) >= self.config.max_candidates
                    or status["calls_budget_spent"] + sample_size * self.config.calls_per_pair
                    > self.config.max_calls):
                return status
            candidates = self.propose()
            if not candidates:
                return status
            trial = self.freeze(candidates[0].policy_id, sample_size=sample_size)
            try:
                certificate = self.evaluate(trial.trial_id, fresh_tasks(trial))
            except BaseException:
                self._end_trial(trial.trial_id, "cancelled")
                raise
            if certificate.decision == "certified":
                self.promote(trial.trial_id)
