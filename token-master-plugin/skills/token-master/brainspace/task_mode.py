"""Explicit task-local contracts and opt-in, session-owned durable mode state.

No environment-derived session identity, global enable switch, model obedience
claim, request interception or automatic instruction injection. Callers provide
an explicit workspace state directory and session key. One atomic file per key
avoids read/modify/write races between unrelated sessions. Concurrent operations
on the *same* session are last-writer-wins; callers must serialize those if needed.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path


def _text(value, name: str) -> None:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be nonempty text")


@dataclass(frozen=True)
class TaskContract:
    required_result: str
    non_goals: tuple[str, ...]
    evidence: tuple[str, ...]
    stop_condition: str
    output_budget: int | None = None
    version: str = "task-contract-v1"

    def __post_init__(self) -> None:
        if self.version != "task-contract-v1":
            raise ValueError("unsupported task contract version")
        _text(self.required_result, "required_result")
        _text(self.stop_condition, "stop_condition")
        for name in ("non_goals", "evidence"):
            values = getattr(self, name)
            if type(values) is not tuple:
                raise ValueError(f"{name} must be an immutable tuple")
            for value in values:
                _text(value, name)
        if self.output_budget is not None and (
                type(self.output_budget) is not int or self.output_budget < 1):
            raise ValueError("output_budget must be a positive advisory token budget")

    def to_dict(self) -> dict:
        result = asdict(self)
        result["non_goals"] = list(self.non_goals)
        result["evidence"] = list(self.evidence)
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))

    @classmethod
    def from_dict(cls, value: dict) -> TaskContract:
        if (type(value) is not dict or value.get("version") != "task-contract-v1"
                or set(value) - {field.name for field in fields(cls)}):
            raise ValueError("invalid versioned task contract")
        data = dict(value)
        for name in ("non_goals", "evidence"):
            if type(data.get(name)) not in (list, tuple):
                raise ValueError(f"invalid {name}")
            data[name] = tuple(data[name])
        try:
            return cls(**data)
        except TypeError as exc:
            raise ValueError("incomplete task contract") from exc

    @classmethod
    def from_json(cls, value: str) -> TaskContract:
        return cls.from_dict(json.loads(value))


@dataclass(frozen=True)
class ModeStatus:
    enabled: bool
    scope: str
    session_id: str | None
    contract: TaskContract | None
    reason: str
    obedience_guaranteed: bool = False

    def to_dict(self) -> dict:
        result = asdict(self)
        result["contract"] = self.contract.to_dict() if self.contract is not None else None
        return result


def render_task_mode(mode: ModeStatus) -> str:
    """Render an explicitly selected contract, not storage/session telemetry.

    The caller must respect instruction priority and may not promote untrusted
    file text to authority. This does not inject itself into any host. An off
    mode adds nothing to future requests; it cannot erase existing history.
    """
    if not isinstance(mode, ModeStatus) or type(mode.enabled) is not bool:
        raise ValueError("validated mode status required")
    if not mode.enabled:
        return ""
    if mode.scope not in ("task", "session") or not isinstance(mode.contract, TaskContract):
        raise ValueError("enabled mode requires a validated task contract")
    contract = mode.contract
    lines = ["Task contract:", "Required: " + contract.required_result]
    if contract.non_goals:
        lines.append("Avoid: " + " ".join(contract.non_goals))
    if contract.evidence:
        lines.append("Evidence: " + " ".join(contract.evidence))
    lines.append("Stop: " + contract.stop_condition)
    if contract.output_budget is not None:
        lines.append(f"Advisory response budget: {contract.output_budget} reference tokens; "
                     "retain requested depth, correctness and safety.")
    return "\n".join(lines)


def task_local_mode(contract: TaskContract) -> ModeStatus:
    """Return an ephemeral task invocation without reading/writing session state."""
    if not isinstance(contract, TaskContract):
        raise ValueError("a validated TaskContract is required")
    return ModeStatus(True, "task", None, contract, "task_local")


class TaskModeStore:
    """Own only token-master-task-mode-<session-sha256>.json in the given root."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()

    def path_for_session(self, session_id: str) -> Path:
        _text(session_id, "session_id")
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        return self.root / f"token-master-task-mode-{digest}.json"

    def _read(self, session_id: str) -> TaskContract | None:
        path = self.path_for_session(session_id)
        if path.is_symlink():
            raise ValueError("refusing symlinked mode state")
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        try:
            data = json.loads(raw)
            if (type(data) is not dict or set(data) != {
                    "version", "session_id", "scope", "enabled", "contract"}
                    or data["version"] != "task-mode-state-v1"
                    or data["session_id"] != session_id
                    or data["scope"] != "session" or data["enabled"] is not True):
                raise ValueError("invalid state or session ownership")
            return TaskContract.from_dict(data["contract"])
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid state or session ownership") from exc

    def status(self, session_id: str) -> ModeStatus:
        self.path_for_session(session_id)  # Validate identity even with no state.
        try:
            contract = self._read(session_id)
        except (ValueError, OSError, UnicodeError):
            return ModeStatus(False, "session", session_id, None, "invalid_state")
        return ModeStatus(contract is not None, "session", session_id, contract,
                          "enabled" if contract is not None else "off")

    def enable(self, session_id: str, contract: TaskContract) -> ModeStatus:
        if not isinstance(contract, TaskContract):
            raise ValueError("a validated TaskContract is required")
        path = self.path_for_session(session_id)
        self._read(session_id)  # Never overwrite corrupt/foreign state.
        self.root.mkdir(parents=True, exist_ok=True)
        data = {"version": "task-mode-state-v1", "session_id": session_id,
                "scope": "session", "enabled": True, "contract": contract.to_dict()}
        text = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            # Only this invocation's temp path; never glob-clean another writer's.
            Path(temporary).unlink(missing_ok=True)
        return ModeStatus(True, "session", session_id, contract, "enabled")

    def off(self, session_id: str) -> ModeStatus:
        path = self.path_for_session(session_id)
        self._read(session_id)  # Verify exact ownership before unlinking.
        path.unlink(missing_ok=True)
        return ModeStatus(False, "session", session_id, None, "off")
