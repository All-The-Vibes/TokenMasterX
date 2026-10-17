"""Bounded, executor-observed native tool receipts, not a stdout authenticator.

The parent MUST register canonical tool calls extracted from the actual upstream
response *before* forwarding it, and feed observe() only trusted native JSONL
stdout. Never feed tool output, assistant text, hooks, or inferred call IDs here.
Transport, process ownership, execution and recovery invocation belong to the
parent. This module performs no inference or tool/file-content reads.

register_expected_calls(calls, model=...) accepts chat-shaped function calls
with real upstream IDs. observe(event) accepts a parsed event or one JSONL line.
wait_for_started(ids, timeout) waits for matching trusted starts, not completion;
use it before servicing recovery RPCs that must finish before completion arrives.
Then claim_pending_call(id) atomically reserves a still-pending native operation
once, before dispatch. A claim does not report execution success or completion.
wait_for_completed(ids, timeout) returns whether every ID has an observed,
non-poisoned completion (including failed executions), not whether tools passed.
close() signals EOF and wakes waiters; missing completions remain pending.
summary() separates source-receipt ineligibility notes from coverage diagnostics.
Known successful directories yield no source receipt. The default source
contract also excludes ranged views. Explicit native-view-result-v2 accepts
qualified range/force options and binds only the exact observed result, never
full-file or requested-range completeness. matches_view_result() validates
completed view text separately from its eligibility for compression.
The two native recovery tools also accept the observed pure-text MCP rendering
envelope. Rendering equivalence accounts for execution only, never successful
full-original recovery; the parent separately verifies model-facing page bytes.

Limits cover registrations, claims and unique admitted tool events together. Saturation
fails closed for the collector; nothing is evicted and no ID can become fresh
again. Journals contain bounded metadata/digests, never raw or detailed content.
A trusted journal callback runs synchronously under the condition lock and must
not block on another collector thread. Its failure also fails closed.
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .request_policy import SourceReadInfo, _json_value, _protected, _tool_indices
from .runtime_io import append_receipt, parse_json, safe_root


_START = "tool.execution_start"
_COMPLETE = "tool.execution_complete"
_NATIVE_RECOVERY_NAMES = ("tokenmaster-retrieve_original", "tokenmaster-headroom_retrieve")
DEFAULT_SOURCE_CONTRACT = "native-full-view-v1"
RANGED_SOURCE_CONTRACT = "native-view-result-v2"
_MAX_NATIVE_INTEGER = (1 << 53) - 1


def validate_source_contract(value):
    if type(value) is not str or value not in (DEFAULT_SOURCE_CONTRACT, RANGED_SOURCE_CONTRACT):
        raise ValueError("invalid_native_source_contract")


def _valid_observed_view_arguments(arguments):
    if (type(arguments) is not dict or "path" not in arguments
            or set(arguments) - {"path", "view_range", "forceReadLargeFiles"}
            or ("forceReadLargeFiles" in arguments
                and type(arguments["forceReadLargeFiles"]) is not bool)):
        return False
    if "view_range" not in arguments:
        return True
    value = arguments["view_range"]
    return (type(value) is list and len(value) == 2
            and all(type(item) is int for item in value)
            and 1 <= value[0] <= _MAX_NATIVE_INTEGER
            and (value[1] == -1 or value[0] <= value[1] <= _MAX_NATIVE_INTEGER))


class _Limit(ValueError):
    pass


def _identity(value, limit=512):
    if (type(value) is not str or not value.strip() or len(value) > limit
            or "\0" in value):
        raise ValueError("invalid identity")
    value.encode("utf-8")
    return value


def _wire(value, limit):
    if not _json_value(value):
        raise ValueError("not JSON")
    chunks = []
    size = 0
    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, sort_keys=True,
                               separators=(",", ":"))
    for chunk in encoder.iterencode(value):
        if len(chunk) > limit:
            raise _Limit("record too large")
        raw = chunk.encode("utf-8")
        size += len(raw)
        if size > limit:
            raise _Limit("record too large")
        chunks.append(raw)
    return b"".join(chunks)


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _mcp_text_result(result, limit):
    """Check the bounded native rendering, without rewriting or certifying payloads."""
    if (type(result) is not dict or set(result) != {"content", "detailedContent", "contents"}
            or type(result["content"]) is not str or type(result["detailedContent"]) is not str
            or type(result["contents"]) is not list or not 1 <= len(result["contents"]) <= 64
            or any(type(block) is not dict or set(block) != {"type", "text"}
                   or block["type"] != "text" or type(block["text"]) is not str
                   for block in result["contents"])):
        return False
    content = result["content"]
    text = "".join(block["text"] for block in result["contents"])
    # observe() already bounded the complete event's UTF-8 bytes, including both
    # representations. Never fall back to literal equality after ambiguous JSON.
    try:
        native = parse_json(content)
        mcp = parse_json(text)
    except json.JSONDecodeError:
        stripped = content.lstrip()
        json_like = stripped.startswith(("{", "[", '"', "true", "false", "null", "-")) \
            or (bool(stripped) and stripped[0].isdigit())
        return content == text and not json_like
    except (ValueError, RecursionError, OverflowError):
        return False
    try:
        if _wire(native, limit) != _wire(mcp, limit):
            return False  # Unlike Python equality, JSON serialization separates true from 1.
        if type(native) is dict:
            if "original_content" in native and type(native["original_content"]) is not str:
                return False
            if _protected(
                {key: value for key, value in native.items()
                 if key not in ("content", "original_content", "metadata")},
                strict_status=True,
            ):
                return False
        # A second comparison preserves numeric lexemes, preventing float-parser
        # rounding from making different payloads appear structurally identical.
        # The strict parse above has already rejected duplicate keys/nonfinite JSON.
        return json.loads(content, parse_int=str, parse_float=str) == \
            json.loads(text, parse_int=str, parse_float=str)
    except (ValueError, RecursionError, OverflowError):
        return False


def validate_native_skills(event, *, cache_root, version="1.0.95-0") -> bool:
    """Allow empty skills or the pinned stock pair from parent-owned stdout.

    Names/flags alone are not trusted: paths must have the exact pinned spelling
    (including case) beneath the supplied absolute cache root, with no symlinks
    or junctions. Only path metadata is inspected; no skill contents are read.
    This validates bootstrap metadata, not cache-file integrity or stdout origin.
    """
    names = {"customize-cloud-agent", "github-pr-media"}
    fields = {"name", "commandName", "description", "source", "userInvocable", "enabled", "path"}
    try:
        if (type(event) is not dict or event.get("type") != "session.skills_loaded"
                or set(event) - {"type", "data", "ephemeral", "id", "timestamp", "parentId"}
                or type(event.get("data")) is not dict or set(event["data"]) != {"skills"}):
            return False
        skills = event["data"]["skills"]
        if type(skills) is not list or len(skills) not in (0, 2):
            return False
        if "ephemeral" in event and type(event["ephemeral"]) is not bool:
            return False
        for key, limit in (("id", 512), ("parentId", 512), ("timestamp", 128)):
            if key in event:
                _identity(event[key], limit)
        _wire(event, 32 * 1024)
        _identity(version, 64)
        if version in (".", "..") or any(char in version for char in "/\\:"):
            return False
        root = Path(cache_root)
        _identity(str(root), 4096)
        if not root.is_absolute():
            return False
        root = safe_root(root)
        seen = set()
        for skill in skills:
            if type(skill) is not dict or set(skill) != fields:
                return False
            name = _identity(skill["name"], 256)
            description = skill["description"]
            if (name not in names or name in seen or skill["commandName"] != name
                    or skill["source"] != "builtin" or skill["userInvocable"] is not False
                    or skill["enabled"] is not True or type(description) is not str
                    or len(description) > 4096 or "\0" in description):
                return False
            candidate = Path(_identity(skill["path"], 4096))
            expected = root / "pkg" / "win32-x64" / version / "builtin" / name / "SKILL.md"
            # Path equality is case-insensitive on Windows; compare exact parts.
            if (not candidate.is_absolute() or candidate.parts != expected.parts
                    or safe_root(candidate).parts != expected.parts):
                return False
            seen.add(name)
        return not skills or seen == names
    except (ValueError, TypeError, OSError, RuntimeError, OverflowError):
        return False


@dataclass
class _Binding:
    name: str | None = None
    arguments: bytes | None = None
    status: str = "pending"
    start: str | None = None
    complete: str | None = None
    turn_id: str | None = None
    content_digest: str | None = None
    source_path: str | None = None
    error_rendering: str | None = None
    claimed: bool = False


class NativeEventCollector:
    def __init__(
        self, *, workspace, expected_model, max_events=4096,
        max_bytes=16 * 1024 * 1024, max_event_bytes=2 * 1024 * 1024,
        journal=None, journal_path=None, source_contract=DEFAULT_SOURCE_CONTRACT,
    ):
        validate_source_contract(source_contract)
        self._source_contract = source_contract
        self.expected_model = _identity(expected_model)
        self.workspace = safe_root(workspace)
        for value in (max_events, max_bytes, max_event_bytes):
            if type(value) is not int or value < 1:
                raise ValueError("positive integer limits required")
        if ((journal is not None and not callable(journal))
                or (journal is not None and journal_path is not None)):
            raise ValueError("choose one trusted journal sink")
        self._journal = journal
        self._journal_path = Path(journal_path) if journal_path is not None else None
        self._max_events = max_events
        self._max_bytes = max_bytes
        self._max_event_bytes = max_event_bytes
        self._condition = threading.Condition()
        self._calls: dict[str, _Binding] = {}
        self._diagnostics: Counter[str] = Counter()
        self._ineligibility_notes: Counter[str] = Counter()
        self._events = self._bytes = 0
        self._closed = self._limit_exceeded = self._unsafe = False
        self._journal_complete = True

    @property
    def source_contract(self):
        return self._source_contract

    def _problem(self, reason, call_id=None):
        first = reason not in self._diagnostics
        self._diagnostics[reason] += 1
        if call_id in self._calls:
            binding = self._calls[call_id]
            first = first or binding.status != "poisoned"
            binding.status = "poisoned"
            binding.source_path = None
            record = {"kind": "diagnostic", "call_id": call_id,
                      "reason": reason, "status": "poisoned"}
        else:
            # An unattributable tool event could invalidate any receipt.
            self._unsafe = True
            record = {"kind": "diagnostic", "reason": reason, "status": "unknown"}
        if first:
            self._write(record)
        self._condition.notify_all()

    def _admit(self, raw):
        if (self._events >= self._max_events
                or self._bytes + len(raw) > self._max_bytes):
            self._limit_exceeded = True
            self._problem("limit_exceeded")
            return False
        self._events += 1
        self._bytes += len(raw)
        return True

    def _record(self, kind, call_id, raw):
        binding = self._calls[call_id]
        record = {"kind": kind, "call_id": call_id, "name": binding.name,
                  "model": self.expected_model, "status": binding.status,
                  "sha256": _digest(raw), "bytes": len(raw)}
        if binding.error_rendering is not None:
            record["error_rendering"] = binding.error_rendering
        if self.source_contract == RANGED_SOURCE_CONTRACT:
            record.update(
                source_contract=self.source_contract,
                source_scope="exact-observed-tool-result-not-full-file",
                arguments_sha256=_digest(binding.arguments) if binding.arguments is not None else None,
                content_sha256=binding.content_digest,
            )
        self._write(record)
        self._condition.notify_all()

    def _write(self, record):
        if not self._journal_complete:
            return
        try:
            if self._journal is not None:
                self._journal(record)
            elif self._journal_path is not None:
                append_receipt(self._journal_path, record)
        except Exception:
            self._journal_complete = False
            self._unsafe = True
            self._diagnostics["journal_failed"] += 1
            self._condition.notify_all()

    def _call(self, call):
        if (type(call) is not dict or set(call) != {"id", "type", "function"}
                or call["type"] != "function" or type(call["function"]) is not dict
                or set(call["function"]) != {"name", "arguments"}):
            raise ValueError("invalid canonical tool call")
        call_id = _identity(call["id"])
        name = _identity(call["function"]["name"], 256)
        text = call["function"]["arguments"]
        if type(text) is not str:
            raise ValueError("arguments must be JSON text")
        if len(text) > self._max_event_bytes:
            raise _Limit("arguments too large")
        arguments = parse_json(text)
        if type(arguments) is not dict:
            raise ValueError("arguments must be an object")
        return call_id, name, _wire(arguments, self._max_event_bytes)

    def register_expected_calls(self, calls, *, model):
        """Register upstream calls; on ValueError the parent must not forward.

        Exact re-registration is idempotent. An observed unknown ID or a
        conflicting registration can never be rehabilitated.
        """
        with self._condition:
            if self._closed or self._unsafe:
                raise ValueError("collector closed or unsafe")
            call_id = None
            try:
                if model != self.expected_model or type(calls) not in (list, tuple):
                    raise ValueError("invalid registration model or calls")
                if len(calls) > self._max_events:
                    raise _Limit("too many calls")
                staged = {}
                staged_bytes = 0
                for call in calls:
                    call_id = None
                    if type(call) is dict and type(call.get("id")) is str:
                        call_id = call["id"]
                    call_id, name, arguments = self._call(call)
                    raw = _wire(call, self._max_event_bytes)
                    staged_bytes += len(raw)
                    if staged_bytes > self._max_bytes:
                        raise _Limit("registration batch too large")
                    old = self._calls.get(call_id)
                    if (call_id in staged or (old is not None and (
                            old.name != name or old.arguments != arguments
                            or old.status == "poisoned"))):
                        raise ValueError("conflicting registration")
                    staged[call_id] = (name, arguments, raw)
                for call_id, (name, arguments, raw) in staged.items():
                    if call_id in self._calls:
                        continue
                    if not self._admit(raw):
                        raise ValueError("collector limit exceeded")
                    self._calls[call_id] = _Binding(name=name, arguments=arguments)
                    self._record("registered", call_id, raw)
                    if self._unsafe:
                        raise ValueError("journal unavailable")
                return tuple(staged)
            except (ValueError, TypeError, RecursionError, OverflowError) as error:
                if isinstance(error, _Limit):
                    self._limit_exceeded = True
                    self._problem("limit_exceeded")
                self._problem("invalid_registration", call_id)
                raise ValueError("invalid native call registration") from error

    def observe(self, event):
        """Consume only an event directly obtained from parent-owned stdout.

        Malformed tool events are diagnostic, never exceptions in the stdout
        reader thread. Non-tool event data is never inspected recursively.
        """
        with self._condition:
            call_id = None
            try:
                if type(event) in (str, bytes):
                    if len(event) > self._max_event_bytes:
                        raise _Limit("event too large")
                    event = parse_json(event)
                if type(event) is not dict or type(event.get("type")) is not str:
                    raise ValueError("invalid event envelope")
                kind = event["type"]
                if not kind.startswith("tool."):
                    return
                data = event.get("data")
                if type(data) is dict and type(data.get("toolCallId")) is str:
                    call_id = data["toolCallId"]
                if self._closed:
                    self._problem("event_after_close", call_id)
                    return
                if self._unsafe:
                    return
                raw = _wire(event, self._max_event_bytes)
                if kind not in (_START, _COMPLETE) or type(data) is not dict:
                    raise ValueError("unknown tool event")
                call_id = _identity(data.get("toolCallId"))
                binding = self._calls.get(call_id)
                fingerprint = _digest(raw)
                if binding is not None:
                    previous = binding.start if kind == _START else binding.complete
                    if previous == fingerprint:
                        return
                    if previous is not None:
                        self._problem("conflicting_replay", call_id)
                        return
                if not self._admit(raw):
                    return
                if binding is None:
                    self._calls[call_id] = _Binding(status="poisoned")
                    self._problem("unregistered_call", call_id)
                    self._record(kind, call_id, raw)
                    return
                if binding.status == "poisoned":
                    return
                if data.get("model") != self.expected_model:
                    raise ValueError("foreign model")
                turn_id = _identity(data.get("turnId"))
                if kind == _START:
                    if (data.get("toolName") != binding.name
                            or type(data.get("arguments")) is not dict
                            or _wire(data["arguments"], self._max_event_bytes) != binding.arguments):
                        raise ValueError("start does not match registration")
                    binding.start = fingerprint
                    binding.turn_id = turn_id
                else:
                    if binding.start is None or turn_id != binding.turn_id:
                        raise ValueError("completion without matching start")
                    _identity(data.get("interactionId"))
                    if type(data.get("success")) is not bool or data.get("rte") is not False:
                        raise ValueError("unknown completion status")
                    binding.complete = fingerprint
                    binding.status = "failure" if not data["success"] else "success"
                    if binding.status == "success":
                        self._complete(binding, data)
                    elif binding.name == "view":
                        # Failure text may remain valid history, but never grants
                        # source authority. Do not infer a rendered error string.
                        result = data.get("result")
                        if (type(result) is dict and not set(result) - {"content", "detailedContent"}
                                and type(result.get("content")) is str
                                and ("detailedContent" not in result
                                     or type(result["detailedContent"]) is str)):
                            binding.content_digest = _digest(result["content"].encode("utf-8"))
                        elif result is None and type(data.get("error")) is dict:
                            # Native error completions may carry error.message
                            # instead of a success result. Match that literal
                            # message only; never add a guessed "Error:" wrapper.
                            error_text = data["error"].get("message")
                            if type(error_text) is str:
                                telemetry = data.get("toolTelemetry")
                                properties = telemetry.get("properties") \
                                    if type(telemetry) is dict else None
                                if (data["error"].get("code") == "failure"
                                        and error_text == "Path does not exist"
                                        and type(properties) is dict
                                        and properties.get("command") == "view"
                                        and properties.get("viewType") == "unknown"
                                        and properties.get("resolvedPathAgainstCwd") == "false"):
                                    # Pinned 1.0.95-0 native-003 evidence: this
                                    # failure renders the issued absolute path,
                                    # not error.message alone. No filesystem read
                                    # or source authority follows from rendering.
                                    path = parse_json(binding.arguments).get("path")
                                    if (type(path) is str and 0 < len(path) <= 4096
                                            and "\0" not in path and Path(path).is_absolute()):
                                        error_text = (f"Path {path} does not exist. "
                                                      "Please provide a valid path.")
                                        binding.error_rendering = "native-view-missing-path-1.0.95-v1"
                                binding.content_digest = _digest(error_text.encode("utf-8"))
                self._record(kind, call_id, raw)
            except (ValueError, TypeError, RecursionError, OverflowError) as error:
                # UTF-8/JSON errors inherit ValueError; never retain their text.
                if isinstance(error, _Limit):
                    self._limit_exceeded = True
                    self._problem("limit_exceeded")
                self._problem("malformed_event", call_id)

    def _complete(self, binding, data):
        result = data.get("result")
        metadata = {key: value for key, value in data.items()
                    if key not in ("result", "toolTelemetry")}
        allowed = {"content", "detailedContent"}
        if binding.name in _NATIVE_RECOVERY_NAMES and _mcp_text_result(result, self._max_event_bytes):
            allowed.add("contents")
        if (type(result) is not dict or set(result) - allowed
                or type(result.get("content")) is not str
                or ("detailedContent" in result and type(result["detailedContent"]) is not str)
                or _protected(metadata, strict_status=True)):
            binding.status = "unknown"
            self._diagnostics["unsafe_result"] += 1
            return
        binding.content_digest = _digest(result["content"].encode("utf-8"))
        if binding.name != "view":
            return
        telemetry = data.get("toolTelemetry")
        properties = telemetry.get("properties") if type(telemetry) is dict else None
        arguments = parse_json(binding.arguments)
        arguments_valid = (
            _valid_observed_view_arguments(arguments)
            if self.source_contract == RANGED_SOURCE_CONTRACT
            else set(arguments) in ({"path"}, {"path", "view_range"})
        )
        if (type(properties) is not dict or properties.get("viewType") not in ("file", "directory")
                or not arguments_valid):
            self._diagnostics["ineligible_view"] += 1
            return
        view_type = properties["viewType"]
        if "view_range" in arguments:
            view_range = arguments["view_range"]
            if (type(view_range) is not list or len(view_range) != 2
                    or any(type(value) is not int for value in view_range)):
                self._diagnostics["ineligible_view"] += 1
                return
        try:
            path = _identity(arguments["path"], 4096)
            # Reject URLs, drive-relative paths and Windows alternate streams.
            local = Path(path)
            if ("://" in path or ":" in path.replace(local.drive, "", 1)
                    or (local.drive and not local.is_absolute())):
                raise ValueError("nonlocal path")
            target = self.workspace / local
            if (not target.is_relative_to(self.workspace) or ".." in local.parts
                    or (target == self.workspace and view_type != "directory")):
                raise ValueError("foreign path")
            target = safe_root(target)
            if (not target.is_relative_to(self.workspace)
                    or (target == self.workspace and view_type != "directory")):
                raise ValueError("foreign path")
        except (ValueError, OSError, RuntimeError):
            self._diagnostics["ineligible_path"] += 1
            return
        if view_type == "directory":
            self._ineligibility_notes["directory_view"] += 1
        elif "view_range" in arguments and self.source_contract == DEFAULT_SOURCE_CONTRACT:
            self._ineligibility_notes["ranged_view"] += 1
        else:
            binding.source_path = path

    def matches_view_result(self, call_id, content) -> bool:
        """Validate observed history text, not successful-file source eligibility."""
        with self._condition:
            if type(call_id) is not str:
                return False
            binding = self._calls.get(call_id)
            if (self._unsafe or not self._journal_complete
                    or binding is None or binding.name != "view"
                    or binding.status not in ("success", "failure")
                    or binding.start is None or binding.complete is None
                    or binding.content_digest is None or type(content) is not str
                    or len(content) > self._max_event_bytes):
                return False
            try:
                raw = content.encode("utf-8")
            except UnicodeEncodeError:
                return False
            return len(raw) <= self._max_event_bytes and _digest(raw) == binding.content_digest

    def wait_for_started(self, call_ids, timeout):
        """Wait for trusted matching starts, without waiting for tool completion."""
        return self._wait_for(call_ids, timeout, completed=False)

    def wait_for_completed(self, call_ids, timeout):
        """Finite seconds only. False on timeout, EOF, poison or unsafe coverage."""
        return self._wait_for(call_ids, timeout, completed=True)

    def claim_pending_call(self, call_id) -> bool:
        """Reserve one dispatch only while this registered native call is pending.

        The parent must first match the issued recovery name and arguments.
        Journal failure consumes the claim but returns False; never retry it.
        Later native completion or timeout remains a separate observation.
        """
        with self._condition:
            try:
                _identity(call_id)
            except ValueError:
                return False
            binding = self._calls.get(call_id)
            if (self._closed or self._unsafe or not self._journal_complete
                    or binding is None or binding.name is None or binding.arguments is None
                    or binding.start is None or binding.status != "pending"
                    or binding.complete is not None or binding.claimed):
                return False
            try:
                raw = _wire({"kind": "claimed", "call_id": call_id,
                             "start_sha256": binding.start}, self._max_event_bytes)
            except _Limit:
                self._limit_exceeded = True
                self._problem("limit_exceeded")
                return False
            if not self._admit(raw):
                return False
            binding.claimed = True
            self._record("claimed", call_id, raw)
            return not self._unsafe and self._journal_complete

    def _wait_for(self, call_ids, timeout, *, completed):
        if (type(timeout) not in (int, float) or not math.isfinite(timeout)
                or timeout < 0 or timeout > threading.TIMEOUT_MAX):
            raise ValueError("finite bounded timeout required")
        if type(call_ids) not in (tuple, list, set) or len(call_ids) > self._max_events:
            raise ValueError("bounded call IDs required")
        ids = tuple(_identity(call_id) for call_id in call_ids)
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                if self._unsafe or any(
                    call_id in self._calls and self._calls[call_id].status == "poisoned"
                    for call_id in ids
                ):
                    return False
                if all(
                    call_id in self._calls and (
                        self._calls[call_id].complete if completed else self._calls[call_id].start
                    ) is not None for call_id in ids
                ):
                    return True
                remaining = deadline - time.monotonic()
                if self._closed or remaining <= 0:
                    return False
                self._condition.wait(remaining)

    def source_reads(self, canonical_request) -> tuple[SourceReadInfo, ...]:
        """Return only receipts matching this complete canonical request exactly."""
        with self._condition:
            if self._unsafe:
                return ()
            try:
                if (type(canonical_request) is not dict
                        or canonical_request.get("model") != self.expected_model):
                    return ()
                indices = _tool_indices(canonical_request)
                calls = {call["id"]: call for message in canonical_request["messages"]
                         for call in message.get("tool_calls", [])}
                receipts = []
                for index in indices:
                    message = canonical_request["messages"][index]
                    binding = self._calls.get(message["tool_call_id"])
                    if (binding is None or binding.status != "success"
                            or binding.source_path is None or binding.content_digest is None):
                        continue
                    call_id, name, arguments = self._call(calls[message["tool_call_id"]])
                    if (name != binding.name or arguments != binding.arguments
                            or ("name" in message and message["name"] != name)
                            or _protected({k: v for k, v in message.items() if k != "content"},
                                          strict_status=True)):
                        continue
                    info = SourceReadInfo(call_id, name, binding.source_path,
                                          binding.content_digest, "success")
                    if info.matches(message, calls[call_id]):
                        receipts.append(info)
                return tuple(receipts)
            except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
                return ()

    def summary(self):
        """Metadata-only native executor coverage; never an execution certificate."""
        with self._condition:
            counts = {status: 0 for status in ("pending", "success", "failure", "unknown", "poisoned")}
            for binding in self._calls.values():
                counts[binding.status] += 1
            result = {
                "scope": "native-executor-observed-only", "closed": self._closed,
                "events": self._events, "bytes": self._bytes, "counts": counts,
                "limit_exceeded": self._limit_exceeded,
                "journal_complete": self._journal_complete,
                "coverage_complete": not self._unsafe and not self._diagnostics
                and not counts["pending"] and not counts["unknown"] and not counts["poisoned"],
                "diagnostics": dict(self._diagnostics),
                "ineligibility_notes": dict(self._ineligibility_notes),
                "calls": {call_id: {"name": binding.name, "status": binding.status,
                                    "started": binding.start is not None,
                                    "completed": binding.complete is not None,
                                    "claimed": binding.claimed}
                          for call_id, binding in self._calls.items()},
            }
            if self.source_contract == RANGED_SOURCE_CONTRACT:
                result.update(source_contract=self.source_contract,
                              source_scope="exact-observed-tool-result-not-full-file")
            return result

    def close(self):
        """Mark native stdout EOF; do not convert pending/unknown/failure to zero."""
        with self._condition:
            if not self._closed:
                self._closed = True
                snapshot = self.summary()
                record = {"kind": "closed", "counts": snapshot["counts"],
                          "diagnostics": snapshot["diagnostics"],
                          "ineligibility_notes": snapshot["ineligibility_notes"],
                          "coverage_complete": snapshot["coverage_complete"]}
                if self.source_contract == RANGED_SOURCE_CONTRACT:
                    record.update(source_contract=self.source_contract,
                                  source_scope="exact-observed-tool-result-not-full-file")
                self._write(record)
            self._condition.notify_all()
            return self.summary()
