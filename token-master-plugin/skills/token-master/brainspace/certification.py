"""Durable, strict token-improvement certification, not a Jev quality oracle.

Integration (all IDs identify immutable/versioned content, not mutable names):
  registry = CertificationRegistry(path, alpha=.05, trusted_oracle_id=oracle_id)
  registry.exclude_tasks(search_task_ids)       # register exposed search data
  k = registry.start_round(spec, sample_size=n) # freeze BEFORE drawing tasks
  registry.reserve_tasks(k, spec, fresh_ids)    # BEFORE evaluating those tasks
  registry.submit(k, spec, paired_observations) # independent evaluator outcomes
  certificate = registry.certify(k, spec)       # certificate.to_dict() is JSON
  # Count BOTH policy runs once in the learning ledger:
  ledger.record(observation.learning_trace(spec))

ComparisonSpec pins candidate/incumbent, MeasurementIdentity, oracle, workload,
environment (models/tools/conditions), positive integer token_cap and positive
minimum_token_reduction. Traces are complete LEARNING-phase whole-task runs;
their roles/retries/failures all count. VerifiedOutcome requires binary success
and an evidence digest. Labels are supplied by the configured trusted evaluator,
not accepted as model confidence or Jev score. The controller owns promotion
and must check certificate.comparison against its CURRENT immutable identities.

Only the strict success-preserving gate is implemented:
  alpha_k = 6 alpha / (pi^2 k^2)
  r = sqrt(2 log(2/alpha_k) / n)
  mean(Q_b-Q_a)-r >= 0 and mean((T_b-T_a)/B)+r <= -eta/B.
``mode="anytime"`` (no sample_size) uses alpha_k/[n(n+1)] at look n.
Fixed rounds require the predeclared n and close at the first complete look.
An anytime stream may continue after an inconclusive look, never after passing.
No tolerated noninferiority loss, quality floor, or ratio alternative is hidden
in this gate. Ratio improvement is conditional on positive incumbent success.

SQLite BEGIN IMMEDIATE transactions reserve round budgets and holdouts, reject
duplicate submissions, and atomically save results. Restarts use the SAME file
and configuration. Reported call IDs commit separately before validation, even
for rejected batches; only their original valid reservation may retry them.
Abandoned reservations/rounds are never recycled. Use one
registry for the entire error-budget family, including concurrent controllers;
do not fork/delete/restore older copies to reset its history. Filesystem and
evaluator integrity are trust boundaries, not an adversarial security sandbox.

Software cannot prove external labels true, task independence/freshness outside
this registry, a cap on unseen future runs, faithful identity pins, or complete
capture. Callers must enforce the cap WITHOUT clipping observations, maintain a
stable regime, and draw genuinely fresh independent task pairs after freezing.
IDs/hashes and aggregate evidence are persisted, never raw model payloads.
"""
from __future__ import annotations

import json
import math
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .token_ledger import (
    MeasurementIdentity, TaskTrace, _canonical, _digest, _hash, _integer,
    _strings, _text,
)


_MAX_SQLITE_INT = 2**63 - 1
_ASSUMPTIONS = (
    "Candidate, incumbent, oracle, tokenizer, extraction, boundary, workload and environment are fixed.",
    "Task pairs are fresh after freezing and independent across tasks, conditional on prior search history.",
    "All model calls and failures at the declared boundary are captured without clipping or native-count mixing.",
    "The declared positive token cap is enforced for every full task under both policies, not just observed samples.",
    "Binary success labels come from the configured independent evaluator, never the optimized model score.",
    "One intact registry covers the entire error-budget family; predeclared fixed looks or the anytime rule are respected.",
)
_LIMITS = (
    "Software cannot prove external labels true; correctness authority belongs to the configured evaluator.",
    "No universal truth, per-task correctness, global optimum, hidden-compute, or future-drift guarantee.",
    "Not certified means inconclusive, not proof that improvement is absent.",
    "Strict equal-quality observations generally cannot pass this finite-sample zero-regression gate.",
    "Tokens per success improve only conditional on positive true incumbent success probability.",
    "Freshness outside registered task IDs, capture completeness and immutable identity fidelity remain caller responsibilities.",
)


def _positive_sqlite_integer(value: int, name: str) -> None:
    _integer(value, name, 1)
    if value > _MAX_SQLITE_INT:
        raise ValueError(f"{name} exceeds the supported signed 64-bit integer range")


def _probability(alpha: float) -> None:
    if type(alpha) not in (float, int) or not 0 < alpha < 1 or not math.isfinite(alpha):
        raise ValueError("alpha must be finite and strictly between zero and one")


def round_alpha(alpha: float, k: int) -> float:
    _probability(alpha)
    _positive_sqlite_integer(k, "round index")
    value = 6 * alpha / (math.pi**2 * k**2)
    if not 0 < value < 1:
        raise ValueError("round error allocation is outside floating-point range")
    return value


def radius(alpha: float, k: int, n: int, *, anytime: bool = False) -> float:
    _positive_sqlite_integer(n, "sample size")
    if type(anytime) is not bool:
        raise ValueError("anytime must be boolean")
    a = round_alpha(alpha, k)
    # Log-domain arithmetic avoids overflow in 2*n*(n+1)/alpha_k.
    log_term = math.log(2) - math.log(a)
    if anytime:
        log_term += math.log(n) + math.log(n + 1)
    return math.sqrt(2 * log_term / n)


@dataclass(frozen=True, slots=True)
class ComparisonSpec:
    candidate_id: str
    incumbent_id: str
    measurement: MeasurementIdentity
    oracle_id: str
    workload_id: str
    environment_id: str
    token_cap: int
    minimum_token_reduction: float

    def __post_init__(self):
        for name in ("candidate_id", "incumbent_id", "oracle_id", "workload_id", "environment_id"):
            _text(getattr(self, name), name)
        if self.candidate_id == self.incumbent_id:
            raise ValueError("candidate and incumbent must be distinct immutable identities")
        if not isinstance(self.measurement, MeasurementIdentity):
            raise ValueError("measurement must be a MeasurementIdentity")
        _positive_sqlite_integer(self.token_cap, "token_cap")
        eta = self.minimum_token_reduction
        if (type(eta) not in (float, int) or not 0 < eta <= self.token_cap
                or not math.isfinite(eta)):
            raise ValueError("minimum_token_reduction must be finite, positive and <= token_cap")

    @property
    def identity(self) -> str:
        return _hash(_canonical(asdict(self)))

    @classmethod
    def from_dict(cls, data: dict) -> ComparisonSpec:
        values = dict(data)
        values["measurement"] = MeasurementIdentity(**values["measurement"])
        return cls(**values)


@dataclass(frozen=True, slots=True)
class VerifiedOutcome:
    task_id: str
    policy_id: str
    oracle_id: str
    success: bool
    evidence_sha256: str

    def __post_init__(self):
        for name in ("task_id", "policy_id", "oracle_id"):
            _text(getattr(self, name), name)
        if type(self.success) is not bool:
            raise ValueError("success must be a verified binary boolean, not a score")
        if self.evidence_sha256 is None:
            raise ValueError("evaluator evidence digest is required")
        _digest(self.evidence_sha256, "evidence_sha256")


@dataclass(frozen=True, slots=True)
class PairedObservation:
    task_id: str
    incumbent: TaskTrace
    candidate: TaskTrace
    incumbent_outcome: VerifiedOutcome
    candidate_outcome: VerifiedOutcome

    def __post_init__(self):
        _text(self.task_id, "task_id")
        if not isinstance(self.incumbent, TaskTrace) or not isinstance(self.candidate, TaskTrace):
            raise ValueError("paired observations require TaskTrace values")
        if (not isinstance(self.incumbent_outcome, VerifiedOutcome)
                or not isinstance(self.candidate_outcome, VerifiedOutcome)):
            raise ValueError("paired observations require VerifiedOutcome values")

    def validate(self, spec: ComparisonSpec) -> None:
        call_ids: set[str] = set()
        for trace, outcome, policy_id in (
            (self.incumbent, self.incumbent_outcome, spec.incumbent_id),
            (self.candidate, self.candidate_outcome, spec.candidate_id),
        ):
            total = trace.totals().total_tokens
            if total > spec.token_cap:
                raise ValueError("full task exceeds token cap; clipping is forbidden")
            if trace.task_id != self.task_id or outcome.task_id != self.task_id:
                raise ValueError("paired task identity mismatch")
            if trace.policy_id != policy_id or outcome.policy_id != policy_id:
                raise ValueError("stale or mismatched policy identity")
            if trace.measurement != spec.measurement:
                raise ValueError("incompatible measurement")
            if trace.phase != "learning":
                raise ValueError("confirmation must be accounted as learning, not deployment")
            if outcome.oracle_id != spec.oracle_id:
                raise ValueError("untrusted outcome oracle")
            ids = {c.call_id for c in trace.calls}
            if call_ids.intersection(ids):
                raise ValueError("paired runs cannot reuse model call IDs")
            call_ids.update(ids)

    def learning_trace(self, spec: ComparisonSpec) -> TaskTrace:
        """Combine both runs for the learning ledger, not the per-policy cap.

        The comparison identity is the policy of this composite experiment.
        Record this composite trace once, not the individual runs: the paired
        runs share a task ID, while TokenLedger records a task exactly once.
        The aggregate may
        exceed spec.token_cap: that cap bounds each policy's deployment task,
        not the sum of two runs needed for one confirmation experiment.
        """
        self.validate(spec)
        if self.incumbent.learning_run_id != self.candidate.learning_run_id:
            raise ValueError("paired learning accounting requires one learning_run_id")
        calls = self.incumbent.calls + self.candidate.calls
        return TaskTrace(
            task_id=self.task_id, policy_id=spec.identity, measurement=spec.measurement,
            phase="learning", learning_run_id=self.incumbent.learning_run_id,
            calls=calls, expected_call_ids=tuple(c.call_id for c in calls),
            coverage="complete_for_declared_boundary",
        )


@dataclass(frozen=True, slots=True)
class Certificate:
    schema_version: int
    registry_id: str
    round_id: int
    comparison: ComparisonSpec
    mode: str
    decision: str
    sample_size: int
    alpha_total: float
    alpha_round: float
    alpha_look: float
    radius: float
    mean_quality_difference: float
    mean_normalized_token_difference: float
    quality_difference_lower: float
    normalized_token_difference_upper: float
    required_normalized_token_reduction: float
    task_set_sha256: str
    evidence_sha256: str
    assumptions: tuple[str, ...] = _ASSUMPTIONS
    limits: tuple[str, ...] = _LIMITS

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Certificate:
        values = dict(data)
        values["comparison"] = ComparisonSpec.from_dict(values["comparison"])
        values["assumptions"] = tuple(values["assumptions"])
        values["limits"] = tuple(values["limits"])
        return cls(**values)


class CertificationRegistry:
    """SQLite-backed holdout exclusion and cumulative error-budget accounting.

    Opening an existing path with different alpha/oracle/schema fails closed.
    Each method uses a separate connection, so instances are safe across threads
    and processes on a filesystem with SQLite's ordinary locking guarantees.
    """

    def __init__(self, path: str | Path, *, alpha: float, trusted_oracle_id: str):
        _probability(alpha)
        round_alpha(alpha, 1)  # reject underflow before creating persistent state
        _text(trusted_oracle_id, "trusted_oracle_id")
        if str(path) == ":memory:":
            raise ValueError("confirmation registry must be durable, not :memory:")
        self._path = Path(path).expanduser().resolve()
        self._alpha = float(alpha)
        self._oracle = trusted_oracle_id
        self._config = _canonical(dict(
            schema_version=1, alpha=self._alpha, trusted_oracle_id=self._oracle,
            gate="strict-paired-hoeffding-v1",
        ))
        with self._transaction(initialize=True) as db:
            for statement in (
                """CREATE TABLE IF NOT EXISTS config (
                    id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL,
                    registry_id TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS rounds (
                    k INTEGER PRIMARY KEY AUTOINCREMENT,
                    spec TEXT NOT NULL, mode TEXT NOT NULL, sample_size INTEGER,
                    state TEXT NOT NULL DEFAULT 'open')""",
                """CREATE TABLE IF NOT EXISTS tasks (
                    task_hash TEXT PRIMARY KEY,
                    round_id INTEGER REFERENCES rounds(k), kind TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS observations (
                    task_hash TEXT PRIMARY KEY REFERENCES tasks(task_hash),
                    round_id INTEGER NOT NULL REFERENCES rounds(k),
                    incumbent_tokens INTEGER NOT NULL, candidate_tokens INTEGER NOT NULL,
                    incumbent_success INTEGER NOT NULL, candidate_success INTEGER NOT NULL,
                    evidence_hash TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS calls (
                    call_hash TEXT PRIMARY KEY, task_hash TEXT NOT NULL REFERENCES tasks(task_hash))""",
                """CREATE TABLE IF NOT EXISTS reported_calls (
                    call_hash TEXT PRIMARY KEY, task_hash TEXT REFERENCES tasks(task_hash))""",
                """CREATE TABLE IF NOT EXISTS looks (
                    round_id INTEGER NOT NULL REFERENCES rounds(k),
                    n INTEGER NOT NULL, certificate TEXT NOT NULL,
                    PRIMARY KEY (round_id,n))""",
            ):
                db.execute(statement)
            db.execute("INSERT OR IGNORE INTO config(id,value,registry_id) VALUES(1,?,?)",
                       (self._config, uuid.uuid4().hex))
            self._check_config(db)
            self._registry_id = db.execute("SELECT registry_id FROM config WHERE id=1").fetchone()[0]

    @contextmanager
    def _transaction(self, *, initialize: bool = False):
        db = sqlite3.connect(str(self._path), timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            if not initialize:
                self._check_config(db)
            yield db
            db.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise ValueError("duplicate or inconsistent persistent confirmation evidence") from exc
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def _check_config(self, db) -> None:
        row = db.execute("SELECT value,registry_id FROM config WHERE id=1").fetchone()
        if row is None or row["value"] != self._config:
            raise ValueError("registry alpha/oracle/schema configuration mismatch")
        if hasattr(self, "_registry_id") and row["registry_id"] != self._registry_id:
            raise ValueError("registry identity changed while in use")

    def _round(self, db, k: int, spec: ComparisonSpec, *, require_open=False):
        _positive_sqlite_integer(k, "round index")
        if not isinstance(spec, ComparisonSpec):
            raise ValueError("spec must be a ComparisonSpec")
        row = db.execute("SELECT * FROM rounds WHERE k=?", (k,)).fetchone()
        if row is None:
            raise ValueError("unknown confirmation round")
        if row["spec"] != _canonical(asdict(spec)):
            raise ValueError("stale or changed comparison spec")
        if require_open and row["state"] != "open":
            raise ValueError("confirmation round is closed")
        return row

    def start_round(
        self, spec: ComparisonSpec, *, sample_size: int | None = None, mode: str = "fixed",
    ) -> int:
        if not isinstance(spec, ComparisonSpec):
            raise ValueError("spec must be a ComparisonSpec")
        if spec.oracle_id != self._oracle:
            raise ValueError("comparison oracle is not the configured trusted evaluator")
        if mode == "fixed":
            if sample_size is None:
                raise ValueError("fixed rounds require a positive sample_size")
            _positive_sqlite_integer(sample_size, "sample_size")
        elif mode == "anytime":
            if sample_size is not None:
                raise ValueError("anytime rounds do not take a fixed sample_size")
        else:
            raise ValueError("mode must be fixed or anytime")
        with self._transaction() as db:
            k = db.execute(
                "INSERT INTO rounds(spec,mode,sample_size) VALUES(?,?,?)",
                (_canonical(asdict(spec)), mode, sample_size),
            ).lastrowid
            round_alpha(self._alpha, k)
            return k

    def exclude_tasks(self, task_ids: Iterable[str]) -> None:
        """Permanently exclude search/training/already-exposed tasks before search."""
        ids = self._task_ids(task_ids)
        with self._transaction() as db:
            db.executemany(
                "INSERT INTO tasks(task_hash,round_id,kind) VALUES(?,NULL,'excluded')",
                [(_hash(t),) for t in ids],
            )

    @staticmethod
    def _task_ids(task_ids: Iterable[str]) -> tuple[str, ...]:
        ids = _strings(task_ids, "task_ids")
        if not ids or len(set(ids)) != len(ids):
            raise ValueError("task IDs must be nonempty and unique")
        return ids

    def reserve_tasks(self, k: int, spec: ComparisonSpec, task_ids: Iterable[str]) -> None:
        """Reserve fresh task IDs before evaluation; reservations are never released."""
        ids = self._task_ids(task_ids)
        with self._transaction() as db:
            row = self._round(db, k, spec, require_open=True)
            reserved = db.execute("SELECT COUNT(*) FROM tasks WHERE round_id=?", (k,)).fetchone()[0]
            if row["mode"] == "fixed" and reserved + len(ids) > row["sample_size"]:
                raise ValueError("reservation exceeds predeclared fixed sample size")
            db.executemany(
                "INSERT INTO tasks(task_hash,round_id,kind) VALUES(?,?,'confirmation')",
                [(_hash(t), k) for t in ids],
            )

    def _consume_reported_calls(self, k, spec, observations) -> str | None:
        """Commit exposure, not accepted evidence; never transfer an existing owner.

        NULL ownership burns IDs reported without a valid frozen reservation.
        The additive table leaves legacy calls/certificates unchanged; legacy
        accepted calls still participate in exclusion through the calls table.
        Return rejection AFTER committing all valid IDs, including siblings.
        """
        rejection = None
        with self._transaction() as db:
            try:
                self._round(db, k, spec, require_open=True)
                valid_round = True
            except ValueError as exc:
                valid_round = False
                rejection = str(exc)
            for obs in observations:
                if not isinstance(obs, PairedObservation):
                    continue
                owner = None
                try:
                    task_hash = _hash(obs.task_id)
                except UnicodeError:
                    rejection = "invalid reported task ID"
                else:
                    reservation = db.execute(
                        "SELECT round_id,kind FROM tasks WHERE task_hash=?", (task_hash,),
                    ).fetchone()
                    if (valid_round and reservation is not None
                            and reservation["round_id"] == k
                            and reservation["kind"] == "confirmation"):
                        owner = task_hash
                for trace in (obs.incumbent, obs.candidate):
                    for call in trace.calls:
                        try:
                            digest = _hash(call.call_id)
                        except UnicodeError:
                            rejection = "invalid reported call ID"
                            continue
                        accepted = db.execute(
                            "SELECT task_hash FROM calls WHERE call_hash=?", (digest,),
                        ).fetchone()
                        reported = db.execute(
                            "SELECT task_hash FROM reported_calls WHERE call_hash=?", (digest,),
                        ).fetchone()
                        if (accepted is not None and accepted["task_hash"] != owner
                                or reported is not None
                                and (owner is None or reported["task_hash"] != owner)):
                            rejection = "reused reported model call ID"
                        if reported is None:
                            # A legacy accepted owner must never be overwritten by
                            # a rejected relabeling, even in this new exposure table.
                            db.execute(
                                "INSERT INTO reported_calls(call_hash,task_hash) VALUES(?,?)",
                                (digest, accepted["task_hash"] if accepted is not None else owner),
                            )
        return rejection

    def submit(self, k: int, spec: ComparisonSpec, observations: Iterable[PairedObservation]) -> None:
        """Consume reported IDs, then append accepted observations atomically.

        Rejection retains exposure but never partial accepted observations.
        Corrections under the same original valid reservation remain supported.
        """
        reported = []
        try:
            for obs in observations:
                reported.append(obs)
        except TypeError as exc:
            raise ValueError("observations must be a sequence") from exc
        finally:
            # Also retain the yielded prefix if an evaluator's iterable raises.
            rejection = self._consume_reported_calls(k, spec, reported)
        observations = tuple(reported)
        if rejection is not None:
            raise ValueError(rejection)
        if not observations or any(not isinstance(o, PairedObservation) for o in observations):
            raise ValueError("a nonempty sequence of PairedObservation is required")
        if not isinstance(spec, ComparisonSpec):
            raise ValueError("spec must be a ComparisonSpec")
        self._task_ids(o.task_id for o in observations)
        for obs in observations:
            obs.validate(spec)
        with self._transaction() as db:
            self._round(db, k, spec, require_open=True)
            for obs in observations:
                task_hash = _hash(obs.task_id)
                reservation = db.execute(
                    "SELECT round_id,kind FROM tasks WHERE task_hash=?", (task_hash,),
                ).fetchone()
                if (reservation is None or reservation["round_id"] != k
                        or reservation["kind"] != "confirmation"):
                    raise ValueError("task was not reserved for this confirmation round")
                evidence_hash = _hash(_canonical(dict(
                    incumbent_trace=obs.incumbent.evidence_sha256,
                    candidate_trace=obs.candidate.evidence_sha256,
                    incumbent_outcome=asdict(obs.incumbent_outcome),
                    candidate_outcome=asdict(obs.candidate_outcome),
                )))
                db.execute(
                    "INSERT INTO observations VALUES(?,?,?,?,?,?,?)",
                    (task_hash, k, obs.incumbent.totals().total_tokens,
                     obs.candidate.totals().total_tokens,
                     int(obs.incumbent_outcome.success), int(obs.candidate_outcome.success),
                     evidence_hash),
                )
                db.executemany(
                    "INSERT INTO calls(call_hash,task_hash) VALUES(?,?)",
                    [(_hash(c.call_id), task_hash)
                     for trace in (obs.incumbent, obs.candidate) for c in trace.calls],
                )

    def certify(self, k: int, spec: ComparisonSpec) -> Certificate:
        """Return a persisted machine-readable result at the allowed sample size."""
        with self._transaction() as db:
            row = self._round(db, k, spec)
            observations = db.execute(
                "SELECT * FROM observations WHERE round_id=? ORDER BY task_hash", (k,),
            ).fetchall()
            n = len(observations)
            if not n:
                raise ValueError("no complete paired observations")
            reserved = db.execute("SELECT COUNT(*) FROM tasks WHERE round_id=?", (k,)).fetchone()[0]
            if n != reserved:
                raise ValueError("reserved tasks are still incomplete; cannot select only submitted outcomes")
            if row["mode"] == "fixed" and n != row["sample_size"]:
                raise ValueError("fixed round cannot be inspected before predeclared sample size")
            saved = db.execute(
                "SELECT certificate FROM looks WHERE round_id=? AND n=?", (k, n),
            ).fetchone()
            if saved is not None:
                return Certificate.from_dict(json.loads(saved["certificate"]))
            if row["state"] != "open":
                raise ValueError("confirmation round is closed")
            # Defense in depth: corrupted persisted scalars must not reach arithmetic.
            for obs in observations:
                for name in ("incumbent_tokens", "candidate_tokens"):
                    _integer(obs[name], name)
                    if obs[name] > spec.token_cap:
                        raise ValueError("persisted observation exceeds token cap")
                for name in ("incumbent_success", "candidate_success"):
                    if type(obs[name]) is not int or obs[name] not in (0, 1):
                        raise ValueError("persisted success is not binary")
            anytime = row["mode"] == "anytime"
            a = round_alpha(self._alpha, k)
            alpha_look = a / (n * (n + 1)) if anytime else a
            if alpha_look <= 0:
                raise ValueError("look error allocation underflow")
            r = radius(self._alpha, k, n, anytime=anytime)
            x = math.fsum(o["candidate_success"] - o["incumbent_success"] for o in observations) / n
            z = math.fsum((o["candidate_tokens"] - o["incumbent_tokens"]) / spec.token_cap
                          for o in observations) / n
            lower = x - r
            upper = z + r
            required = spec.minimum_token_reduction / spec.token_cap
            promoted = lower >= 0 and upper <= -required
            result = Certificate(
                schema_version=1, registry_id=self._registry_id,
                round_id=k, comparison=spec, mode=row["mode"],
                decision="certified" if promoted else "not_certified", sample_size=n,
                alpha_total=self._alpha, alpha_round=a, alpha_look=alpha_look, radius=r,
                mean_quality_difference=x, mean_normalized_token_difference=z,
                quality_difference_lower=lower, normalized_token_difference_upper=upper,
                required_normalized_token_reduction=required,
                task_set_sha256=_hash(_canonical([o["task_hash"] for o in observations])),
                evidence_sha256=_hash(_canonical([dict(o) for o in observations])),
            )
            db.execute(
                "INSERT INTO looks(round_id,n,certificate) VALUES(?,?,?)",
                (k, n, _canonical(result.to_dict())),
            )
            if promoted or not anytime:
                db.execute("UPDATE rounds SET state='closed' WHERE k=?", (k,))
            return result

    def budget(self) -> dict:
        """Every started round spends its allocation, even if abandoned/incomplete."""
        with self._transaction() as db:
            ks = [row[0] for row in db.execute("SELECT k FROM rounds ORDER BY k")]
            allocated = math.fsum(round_alpha(self._alpha, k) for k in ks)
            return dict(
                registry_id=self._registry_id,
                alpha=self._alpha, rounds=len(ks), allocated_alpha=allocated,
                remaining_alpha=max(0.0, self._alpha - allocated),
                next_round_alpha=round_alpha(self._alpha, (max(ks) if ks else 0) + 1),
            )
