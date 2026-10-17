"""JSONL worker for the actual pinned Headroom library and CCR handler.

Run only in the checked network-none container. One process owns
one task, including its recovery store. No provider/continuation callback is
given to Headroom; the caller owns every primary model call. Self-contained
when mounted as a single file: no product-package or evaluation imports.
Vendor originals can be fragments; a successful retrieval/audit is not an
assertion that the complete source file or a full root was recovered.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from enum import Enum
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import secrets
import sys
import threading
import time
from typing import Any, Callable


MAX_FRAME = 4_194_304
COMMIT = "1cf496612e781ef8d67ff87ee4f78037492f0bc7"
MODEL_REVISION = "b1563631b35bfdcee37587ad530147497d820d4c"
TOKENIZER_REVISION = "8949b909ec900327062f0ebf497f51aef5e6f0c8"
MODEL_SHA256 = "c47ddd764dec5cf91fd1f10cf69e5538dd2a49d913828da7f6a993931cc7904f"


@dataclass(frozen=True)
class ActivityEvent:
    event_id: str
    session_id: str
    revision: int
    start_revision: int
    started_ns: int
    phase_at_entry: str
    rpc_at_entry: str | None
    thread_id: int
    input_shapes: tuple[tuple[str, tuple[int, ...]], ...]
    input_dtypes: tuple[tuple[str, str], ...]
    metadata_complete: bool
    state: str = "started"
    start_state: str = "started"
    seconds: float | None = None
    error_type: str | None = None
    mask_counts: None = None


@dataclass(frozen=True)
class ActivitySnapshot:
    revision: int
    events: tuple[ActivityEvent, ...]
    attempts: int
    omitted_events: int
    pending_ids: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return self.omitted_events == 0 and not self.pending_ids


def _feed_metadata(feed: Any) -> tuple[
    tuple[tuple[str, tuple[int, ...]], ...], tuple[tuple[str, str], ...], bool,
]:
    """Shapes/dtypes only; no tensor values, iteration, copies or extra passes."""
    shapes: list[tuple[str, tuple[int, ...]]] = []
    dtypes: list[tuple[str, str]] = []
    if type(feed) is not dict:
        return (), (), False
    complete = len(feed) <= 32
    for index, (key, value) in enumerate(feed.items()):
        if index >= 32:
            break
        if type(key) is not str or len(key) > 128:
            complete = False
            continue
        try:
            shape = value.shape
            if (type(shape) is not tuple or len(shape) > 8
                    or any(type(n) is not int or not 0 <= n <= 2**63 - 1 for n in shape)):
                complete = False
                continue
            shapes.append((key, shape))
            dtype = str(value.dtype)
            if len(dtype) <= 64:
                dtypes.append((key, dtype))
            else:
                complete = False
        except Exception:
            complete = False
    return tuple(shapes), tuple(dtypes), complete


class ActivityLedger:
    """Bounded process-lifetime Python Session.run inventory.

    Revision cursors select latest-record upserts, not disjoint call counts.
    Context is sampled globally at entry and is explicitly NOT causal ownership
    of background work. No waits/joins or changes to upstream execution policy.
    """

    def __init__(self, max_events: int = 1024) -> None:
        if type(max_events) is not int or not 1 <= max_events <= 4096:
            raise ValueError("invalid activity event bound")
        self._limit = max_events
        self._lock = threading.Lock()
        self._events: dict[str, ActivityEvent] = {}
        # Strong references prevent Python object-ID reuse during the lifetime.
        # At most one new session per retained event, bounded by max_events.
        self._sessions: dict[int, tuple[Any, str]] = {}
        self._revision = self._attempts = self._omitted = 0
        self._phase, self._rpc = "startup", None  # type: tuple[str, str | None]

    def context(self, phase: str, rpc_id: str | None = None) -> None:
        if phase not in ("startup", "warmup", "between_rpcs", "rpc", "finalizing"):
            raise ValueError("invalid temporal phase")
        if rpc_id is not None and (type(rpc_id) is not str or not 0 < len(rpc_id) <= 128):
            raise ValueError("invalid temporal RPC identity")
        with self._lock:
            self._phase, self._rpc = phase, rpc_id

    def start(self, session: Any, feed: Any) -> str | None:
        # Capture entry context before potentially slow tensor introspection.
        with self._lock:
            self._attempts += 1
            self._revision += 1
            if len(self._events) >= self._limit:
                self._omitted += 1
                return None
            event_id = f"python-onnx-{self._attempts}"
            key = id(session)
            if key not in self._sessions:
                self._sessions[key] = (session, f"python-session-{len(self._sessions) + 1}")
            self._events[event_id] = ActivityEvent(
                event_id, self._sessions[key][1], self._revision, self._revision,
                time.monotonic_ns(), self._phase, self._rpc, threading.get_ident(), (), (), False)
        try:
            shapes, dtypes, complete = _feed_metadata(feed)
        except Exception:
            # Metadata-only inspection must not suppress the real graph API call
            # (e.g. a caller mutating its feed dictionary concurrently).
            shapes, dtypes, complete = (), (), False
        with self._lock:
            self._revision += 1
            self._events[event_id] = replace(
                self._events[event_id], revision=self._revision, input_shapes=shapes,
                input_dtypes=dtypes, metadata_complete=complete)
        return event_id

    def terminal(self, event_id: str | None, state: str, error_type: str | None = None) -> None:
        if event_id is None:
            return  # Omitted attempts remain explicitly unknown, never zero.
        if state not in ("completed", "failed"):
            raise ValueError("invalid terminal state")
        with self._lock:
            event = self._events[event_id]
            if event.state != "started":
                raise ValueError("activity already terminal")
            self._revision += 1
            self._events[event_id] = replace(
                event, revision=self._revision, state=state,
                seconds=(time.monotonic_ns() - event.started_ns) / 1_000_000_000,
                error_type=error_type[:128] if error_type is not None else None)

    def snapshot(self, since_revision: int = 0) -> ActivitySnapshot:
        with self._lock:
            if type(since_revision) is not int or not 0 <= since_revision <= self._revision:
                raise ValueError("invalid activity revision")
            pending = tuple(e.event_id for e in self._events.values() if e.state == "started")
            events = tuple(replace(e, state="pending") if e.state == "started" else e
                           for e in self._events.values() if e.revision > since_revision)
            return ActivitySnapshot(self._revision, events, self._attempts, self._omitted, pending)

    def inventory(self, since_revision: int = 0) -> dict[str, Any]:
        snap = self.snapshot(since_revision)
        return _inventory(snap, since_revision)


def _inventory(snap: ActivitySnapshot, since_revision: int = 0) -> dict[str, Any]:
    rows = []
    for event in snap.events:
        row = asdict(event)
        row["input_shapes"] = {key: list(shape) for key, shape in event.input_shapes}
        row["input_dtypes"] = dict(event.input_dtypes)
        rows.append(row)
    return {
        "version": "python-onnx-lifetime-ledger-v1", "revision": snap.revision,
        "since_revision": since_revision, "events": rows, "attempts": snap.attempts,
        "attempts_semantics": "cumulative_started_api_attempts_not_increment",
        "omitted_events": snap.omitted_events, "pending_ids": list(snap.pending_ids),
        "pending_count": len(snap.pending_ids), "complete": snap.complete,
        "incomplete_reasons": (["event_limit"] if snap.omitted_events else [])
        + (["pending_at_snapshot"] if snap.pending_ids else []),
        "semantics": "revision_upserts_not_additive_calls" if since_revision else "cumulative_latest_event_per_id",
        "attribution": "temporal_context_at_entry_not_causal",
        "scope": "Python InferenceSession.run entries only; session IDs do not identify model artifacts.",
        "cutoff": "snapshot_revision_not_process_quiescence",
        "local_inference_inventory_complete": False,
    }


def observe_run(original: Callable[..., Any], ledger: ActivityLedger) -> Callable[..., Any]:
    """Observe the existing run boundary once; preserve exact calling semantics."""
    def observed_run(session: Any, *args: Any, **kwargs: Any) -> Any:
        feed = args[1] if len(args) > 1 else kwargs.get("input_feed", {})
        event_id = ledger.start(session, feed)
        try:
            result = original(session, *args, **kwargs)
        except BaseException as error:
            ledger.terminal(event_id, "failed", type(error).__name__)
            raise
        ledger.terminal(event_id, "completed")
        return result
    return observed_run


def parse(text: str) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value
    def reject(_: str) -> Any:
        raise ValueError("nonfinite JSON")
    return json.loads(text, object_pairs_hook=unique, parse_constant=reject)


def emit(value: dict[str, Any], *, ledger: ActivityLedger | None = None) -> bool:
    text = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    fits = len(text.encode("utf-8")) + 1 <= MAX_FRAME
    if not fits:
        inventory = ledger.inventory() if ledger is not None else {}
        inventory["events_omitted_from_frame"] = len(inventory.pop("events", []))
        inventory.pop("pending_ids", None)
        inventory.update(complete=False, local_inference_inventory_complete=False)
        inventory["incomplete_reasons"] = [*inventory.get("incomplete_reasons", []), "frame_limit"]
        overflow = {"id": value.get("id"), "ok": False, "error_type": "ResponseFrameOverflow",
                    "python_onnx_inventory": inventory}
        validation = value.get("preparation_validation")
        if validation is None and type(value.get("result")) is dict:
            validation = value["result"].get("preparation_validation")
        if validation is not None:
            overflow["preparation_validation"] = validation
        text = json.dumps(overflow,
                          ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        if len(text.encode("utf-8")) + 1 > MAX_FRAME:
            raise ValueError("overflow receipt exceeds frame bound")
    sys.stdout.write(text + "\n")
    sys.stdout.flush()
    return fits


def diagnostic_rows(values: Any) -> list[dict[str, Any]]:
    """Upstream legitimate reversion results may omit per-message diagnostics."""
    return [asdict(item) for item in (values or [])]


DOCUMENT_STRATEGY = "native-documents-v1"
MAX_NATIVE_INTEGER = (1 << 53) - 1  # Native JavaScript-number boundary; worker is self-contained.
DOCUMENT_KEYS = {"id", "op", "model", "messages", "eligible_indices",
                 "frozen_message_count", "keep_recent_tool_results"}
PREPROTECTION_STRATEGY = "native-documents-structure-tags-v1"
SPAN_CONTRACT = "document-structure-v1-offsets-v1"
PREPROTECTION_KEYS = DOCUMENT_KEYS | {"span_contract", "message_spans"}
MAX_PREPROTECTION_SPANS = 256  # Total per RPC, never a truncation target.
MAX_PREPROTECTION_HANDLES = 128
MAX_PREPROTECTION_RETAINED_BYTES = 8 * 1024 * 1024  # Exact raw fragment UTF-8 bytes.
MAX_PREPROTECTION_FRAMES = 2048  # Task-lifetime occurrence identities, no body retention.
MAX_PREPROTECTION_VALIDATIONS = 1024  # Task-lifetime attempt records; no eviction.
_INTERNAL_FRAMING = ("<tm-", "</tm-", "tm-structure", "headroom_tag")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_VENDOR_HANDLE = re.compile(r"[0-9a-f]{6,64}")


def lock_strategy(current: str | None, requested: str) -> str:
    """A process owns one task; compression strategies cannot share its store."""
    if (requested not in ("legacy", DOCUMENT_STRATEGY, PREPROTECTION_STRATEGY)
            or current not in (None, requested)):
        raise ValueError("cannot mix task compression strategies")
    return requested


def _successful_metadata(value: Any) -> bool:
    """Check envelope flags only; document prose is never evidence of success."""
    if type(value) is list:
        return all(_successful_metadata(item) for item in value)
    if type(value) is not dict:
        return True
    for key, item in value.items():
        if key == "status" and item not in ("success", "ok", "completed"):
            return False
        if key in ("is_error", "isError", "interrupted", "is_interrupt", "isImage",
                   "is_image", "exact_answer", "preserve_exact") and item is not False:
            return False
        if key in ("ok", "success", "succeeded") and item is not True:
            return False
        if key in ("exit_code", "exitCode", "returncode", "return_code"):
            if type(item) is not int or item != 0:
                return False
        if key == "stderr" and (type(item) is not str or item):
            return False
        if key in ("error", "errors") and item:
            return False
        if not _successful_metadata(item):
            return False
    return True


def document_indices(request: Any) -> set[int]:
    """Validate canonical OpenAI history, not native receipt authenticity.

    API: exact DOCUMENT_KEYS; E is a nonempty list of unique message indices.
    The trusted parent must already have matched successful executor receipts
    to the exact call/path/result bytes and applied intent/source/fence guards.
    Native projection omits successful status, so its absence is permitted;
    explicit failure/unknown flags are not. No payload text can authorize E.
    Native view document strings allow optional view_range and a strict boolean
    forceReadLargeFiles. Range integers must fit the native safe-integer boundary.
    K must be a positive integer; if it exceeds history, every result is recent.
    Normalize path separators only for suffix checks in the Linux container.
    """
    if (type(request) is not dict or set(request) != DOCUMENT_KEYS
            or request["op"] != "compress_documents"
            or type(request["id"]) is not str or not request["id"].strip()
            or len(request["id"]) > 128 or "\0" in request["id"]
            or type(request["model"]) is not str or not request["model"].strip()):
        raise ValueError("invalid document request")
    messages, indices = request["messages"], request["eligible_indices"]
    if type(messages) is not list or not messages or type(indices) is not list or not indices:
        raise ValueError("document messages and eligibility required")
    if any(type(i) is not int or not 0 <= i < len(messages) for i in indices):
        raise ValueError("invalid document index")
    eligible = set(indices)
    if len(eligible) != len(indices):
        raise ValueError("duplicate document index")
    frozen, recent = request["frozen_message_count"], request["keep_recent_tool_results"]
    if (type(frozen) is not int or not 0 <= frozen <= len(messages)
            or type(recent) is not int or recent < 1):
        raise ValueError("invalid document protection bounds")
    pending: dict[str, tuple[dict, dict, dict]] = {}
    seen: set[str] = set()
    tools: list[int] = []
    for index, message in enumerate(messages):
        if (type(message) is not dict
                or message.get("role") not in ("system", "developer", "user", "assistant", "tool")
                or "function_call" in message):
            raise ValueError("unsupported document message")
        role, content = message["role"], message.get("content")
        if content is not None and type(content) not in (str, list):
            raise ValueError("unsupported document content")
        if type(content) is list and any(
                type(block) is not dict or block.get("type") != "text"
                or type(block.get("text")) is not str for block in content):
            raise ValueError("unsupported document content blocks")
        if role == "tool":
            call_id = message.get("tool_call_id")
            if (type(call_id) is not str or call_id not in pending
                    or content is None or "tool_calls" in message):
                raise ValueError("unpaired document result")
            call, arguments, call_message = pending.pop(call_id)
            tools.append(index)
            if index in eligible:
                path = arguments.get("path")
                if (type(content) is not str or not content
                        or call["function"]["name"] != "view"
                        or set(arguments) - {"path", "view_range", "forceReadLargeFiles"}
                        or ("forceReadLargeFiles" in arguments
                            and type(arguments["forceReadLargeFiles"]) is not bool)
                        or type(path) is not str or not path.strip() or len(path) > 4096 or "\0" in path
                        or Path(path.replace("\\", "/")).suffix.lower()
                        not in (".md", ".markdown", ".rst", ".txt")
                        or not _successful_metadata({k: v for k, v in message.items()
                                                     if k != "content"})
                        or not _successful_metadata(call_message)):
                    raise ValueError("ineligible document result")
                if "view_range" in arguments:
                    bounds = arguments["view_range"]
                    if (type(bounds) is not list or len(bounds) != 2
                            or any(type(n) is not int for n in bounds)
                            or not 1 <= bounds[0] <= MAX_NATIVE_INTEGER
                            or (bounds[1] != -1
                                and not bounds[0] <= bounds[1] <= MAX_NATIVE_INTEGER)):
                        raise ValueError("invalid document view range")
            continue
        if pending or "tool_call_id" in message:
            raise ValueError("incomplete document call sequence")
        if "tool_calls" not in message:
            if content is None:
                raise ValueError("empty document message")
            continue
        calls = message["tool_calls"]
        if role != "assistant" or type(calls) is not list or not calls:
            raise ValueError("invalid document calls")
        for call in calls:
            if type(call) is not dict or call.get("type") != "function":
                raise ValueError("unsupported document call")
            call_id, function = call.get("id"), call.get("function")
            if (type(call_id) is not str or not call_id.strip() or call_id in seen
                    or len(call_id) > 512 or "\0" in call_id
                    or type(function) is not dict
                    or type(function.get("name")) is not str or not function["name"].strip()
                    or len(function["name"]) > 256 or "\0" in function["name"]
                    or type(function.get("arguments")) is not str):
                raise ValueError("invalid document call identity")
            arguments = parse(function["arguments"])
            if type(arguments) is not dict:
                raise ValueError("invalid document arguments")
            seen.add(call_id)
            pending[call_id] = (call, arguments, message)
    if (pending or not eligible <= set(tools) or eligible & set(tools[-recent:])
            or any(i < frozen for i in eligible)):
        raise ValueError("protected or incomplete document history")
    return eligible


def _portable(value: Any) -> Any:
    """Canonical config data only: no repr/object addresses or vendor imports."""
    if isinstance(value, Enum):
        return _portable(value.value)
    if is_dataclass(value):
        return {f.name: _portable(getattr(value, f.name)) for f in fields(value)}
    if type(value) is dict:
        return {key: _portable(item) for key, item in value.items()}
    if type(value) in (list, tuple):
        return [_portable(item) for item in value]
    if type(value) in (set, frozenset):
        return sorted((_portable(item) for item in value), key=_canonical)
    if value is None or type(value) in (str, bool, int, float):
        return value
    raise ValueError("nonportable pipeline configuration")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def preprotection_indices(request: Any) -> set[int]:
    """Validate parent-owned descriptors mechanically, not Markdown/provenance.

    Offsets are end-exclusive Python code points over pristine UTF-8 text.
    Parent owns grammar/completeness and must reapply structure/fence/Root and
    whole-original-wire guards. Invalid metadata is a rejected RPC, not a
    truncated span plan. No product imports or source-file reads.
    """
    if (type(request) is not dict or set(request) != PREPROTECTION_KEYS
            or request["op"] != "compress_documents_preprotected"
            or request["span_contract"] != SPAN_CONTRACT):
        raise ValueError("invalid preprotection request")
    base = {key: request[key] for key in DOCUMENT_KEYS}
    base["op"] = "compress_documents"
    eligible = document_indices(base)
    if len(_canonical(request).encode("utf-8")) + 1 > MAX_FRAME:
        raise ValueError("preprotection request exceeds frame bound")
    entries = request["message_spans"]
    if type(entries) is not list or len(entries) != len(eligible):
        raise ValueError("one span entry per eligible message required")
    count = 0
    for entry, index in zip(entries, sorted(eligible)):
        if (type(entry) is not dict or set(entry) != {"index", "content_sha256", "spans"}
                or type(entry["index"]) is not int or entry["index"] != index
                or type(entry["content_sha256"]) is not str
                or not _SHA256.fullmatch(entry["content_sha256"])
                or type(entry["spans"]) is not list):
            raise ValueError("invalid message span descriptor")
        text = request["messages"][index]["content"]
        if _sha256(text) != entry["content_sha256"]:
            raise ValueError("stale span content")
        count += len(entry["spans"])
        if count > MAX_PREPROTECTION_SPANS:
            raise ValueError("preprotection span budget exceeded")
        previous_end = 0
        for span in entry["spans"]:
            if (type(span) is not dict or set(span) != {"kind", "start", "end", "sha256"}
                    or span["kind"] not in ("table", "ordered-list")
                    or type(span["start"]) is not int or type(span["end"]) is not int
                    or not previous_end <= span["start"] < span["end"] <= len(text)
                    or (span["start"] > 0 and text[span["start"] - 1] != "\n")
                    or (span["end"] < len(text) and text[span["end"] - 1] != "\n")
                    or type(span["sha256"]) is not str or not _SHA256.fullmatch(span["sha256"])
                    or _sha256(text[span["start"]:span["end"]]) != span["sha256"]):
                raise ValueError("invalid structural span")
            previous_end = span["end"]
    return eligible


@dataclass(frozen=True)
class _ProtectedFrame:
    opening: str
    body: str
    closing: str

    @property
    def encoded(self) -> str:
        return self.opening + self.body + self.closing


@dataclass(frozen=True)
class _ValidatedFragment:
    raw: str
    binding: str
    source_sha256: str
    start: int
    end: int
    utf8_bytes: int


def _internal_framing(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _INTERNAL_FRAMING)


def _unframe(text: str, frames: list[_ProtectedFrame], nonce: str) -> str | None:
    """Strip only exact once/in-order frames; never restore a lost/edited body."""
    pieces: list[str] = []
    offset = 0
    for frame in frames:
        if text.count(frame.opening) != 1 or text.count(frame.closing) != 1:
            return None
        start = text.find(frame.opening, offset)
        if start < 0 or not text.startswith(frame.encoded, start):
            return None
        body_start = start + len(frame.opening)
        pieces.extend((text[offset:start], text[body_start:body_start + len(frame.body)]))
        offset = start + len(frame.encoded)
    pieces.append(text[offset:])
    result = "".join(pieces)
    if _internal_framing(result) or nonce in result:
        return None
    try:
        result.encode("utf-8")
    except UnicodeEncodeError:
        return None
    return result


class _PreprotectionState:
    """Bounded task state. Validation reads intentionally update public feedback.

    Validated handles are candidates, NOT proof of parent publication. A handle
    has one immutable raw/source binding; conflicts never evict/rebind it.
    Failed/over-budget proposals do not erase completed validation attempts.
    """

    def __init__(self) -> None:
        from headroom.ccr import CCRToolInjector

        self.scanner = CCRToolInjector()
        self.nonce = secrets.token_hex(16)
        self.frames: dict[tuple[Any, ...], str] = {}
        self.fragments: dict[str, _ValidatedFragment] = {}
        self.events: list[dict[str, Any]] = []
        self.retained_bytes = 0
        self.bounds = {
            "max_spans_per_rpc": MAX_PREPROTECTION_SPANS,
            "max_handles": MAX_PREPROTECTION_HANDLES,
            "max_retained_bytes": MAX_PREPROTECTION_RETAINED_BYTES,
            "max_frame_identities": MAX_PREPROTECTION_FRAMES,
            "max_validation_attempts": MAX_PREPROTECTION_VALIDATIONS,
            "max_fragment_bytes": MAX_FRAME,
            "max_annotated_message_frame_bytes": MAX_FRAME,
        }

    def inventory(self, since: int = 0) -> dict[str, Any]:
        return {
            "version": "preparation-validation-v1",
            "attempts": len(self.events), "since_attempt": since,
            "events": deepcopy(self.events[since:]),
            "attempts_semantics": "cumulative_not_additive",
            "public_retrieve_entries": sum(event["public_retrieve_entered"] for event in self.events),
            "scope": "local_preparation_validation_not_native_or_model_recovery",
            "feedback": "public_retrieve_updates_access_feedback_telemetry_toin_even_if_projection_reverts",
            "publication": "unknown_no_parent_ack",
            "validated_handles": len(self.fragments), "retained_bytes": self.retained_bytes,
            "retained_frame_identities": len(self.frames),
            "retention_unit": "exact_raw_fragment_utf8_bytes",
        }

    def markers(self, text: str) -> list[str]:
        keys = self.scanner.scan_for_markers([{"role": "tool", "content": text}])
        if (type(keys) not in (list, tuple, set)
                or any(type(key) is not str or not _VENDOR_HANDLE.fullmatch(key) for key in keys)):
            raise ValueError("invalid vendor handles")
        return sorted(set(keys))

    def annotate(self, text: str, spans: list[dict[str, Any]], binding: str) -> tuple[str, list[_ProtectedFrame], str | None]:
        from headroom.transforms.tag_protector import protect_tags, restore_tags

        if _internal_framing(text) or self.nonce in text or self.markers(text):
            return text, [], "source_framing_or_preexisting_handle"
        keys = [(binding, span["kind"], span["start"], span["end"], span["sha256"]) for span in spans]
        if len(self.frames) + sum(key not in self.frames for key in keys) > self.bounds["max_frame_identities"]:
            return text, [], "frame_identity_limit"
        pieces: list[str] = []
        frames: list[_ProtectedFrame] = []
        offset = 0
        for span, key in zip(spans, keys):
            if key not in self.frames:
                self.frames[key] = f"tm-structure-{self.nonce}-{len(self.frames) + 1}"
            name = self.frames[key]
            frame = _ProtectedFrame(f"<{name}>", text[span["start"]:span["end"]], f"</{name}>")
            pieces.extend((text[offset:span["start"]], frame.encoded))
            frames.append(frame)
            offset = span["end"]
        pieces.append(text[offset:])
        annotated = "".join(pieces)
        try:
            cleaned, blocks = protect_tags(annotated, compress_tagged_content=False)
            if (type(cleaned) is not str or type(blocks) is not list
                    or any(type(pair) not in (list, tuple) or len(pair) != 2
                           or any(type(item) is not str for item in pair) for pair in blocks)
                    or restore_tags(cleaned, blocks) != annotated
                    or any(sum(body == frame.encoded for _, body in blocks) != 1 for frame in frames)
                    or any(cleaned.count(token) != 1 or body in cleaned
                           for token, body in blocks if any(body == frame.encoded for frame in frames))
                    or _unframe(annotated, frames, self.nonce) != text):
                return text, [], "tag_preflight_failed"
        except Exception:
            return text, [], "tag_preflight_failed"
        return annotated, frames, None

    def validate(self, handle: str, text: str, binding: str, rpc_id: str, index: int) -> str | None:
        if len(self.events) >= self.bounds["max_validation_attempts"]:
            return "validation_attempt_limit"
        prior = self.fragments.get(handle)
        if prior is None and len(self.fragments) >= self.bounds["max_handles"]:
            return "handle_limit"
        event: dict[str, Any] = {
            "id": f"preparation-validation-{len(self.events) + 1}", "rpc_id": rpc_id,
            "message_index": index, "handle": handle, "source_binding": binding,
            "source_sha256": _sha256(text), "outcome": "started",
            "public_retrieve_entered": False,
        }
        self.events.append(event)  # Before the side-effecting boundary, including exceptions.
        started = time.monotonic()
        try:
            from headroom.cache.compression_store import get_compression_store
            store = get_compression_store()
            event["public_retrieve_entered"] = True
            entry = store.retrieve(handle)
            if entry is None:
                return self._reject(event, "missing")
            raw = entry.original_content
            if type(raw) is not str or not raw or getattr(entry, "hash", None) != handle:
                return self._reject(event, "invalid_raw_fragment")
            try:
                size = len(raw.encode("utf-8"))
            except UnicodeEncodeError:
                return self._reject(event, "invalid_raw_fragment")
            event.update(raw_sha256=_sha256(raw), raw_utf8_bytes=size)
            if _internal_framing(raw) or self.nonce in raw:
                return self._reject(event, "contaminated")
            if size > self.bounds["max_fragment_bytes"]:
                return self._reject(event, "fragment_byte_limit")
            if prior is not None and (prior.raw != raw or prior.binding != binding):
                return self._reject(event, "binding_conflict")
            start = text.find(raw)
            if start < 0:
                return self._reject(event, "not_pristine_slice")
            if text.find(raw, start + 1) >= 0:
                return self._reject(event, "ambiguous_slice")
            if prior is None:
                if self.retained_bytes + size > self.bounds["max_retained_bytes"]:
                    return self._reject(event, "retained_byte_limit")
                self.fragments[handle] = _ValidatedFragment(
                    raw, binding, event["source_sha256"], start, start + len(raw), size)
                self.retained_bytes += size
            event.update(outcome="validated_candidate", source_start=start, source_end=start + len(raw))
            return None
        except BaseException as error:
            event.update(outcome="exception", error_type=type(error).__name__[:128])
            if not isinstance(error, Exception):
                raise
            return "validation_exception"
        finally:
            event["seconds"] = time.monotonic() - started

    @staticmethod
    def _reject(event: dict[str, Any], reason: str) -> str:
        event["outcome"] = reason
        return reason

    def recover(self, handle: str, call_id: str, handler: Any) -> dict[str, Any]:
        from headroom.ccr.tool_calls import CCRToolCall

        if (type(handle) is not str or not _VENDOR_HANDLE.fullmatch(handle)
                or type(call_id) is not str or not call_id.strip() or len(call_id) > 512 or "\0" in call_id):
            raise ValueError("invalid preprotected recovery identity")
        refused = {
            "tool_call_id": call_id, "tool_name": "headroom_retrieve", "success": False,
            "items_retrieved": 0,
            "content": '{"error":"preprotection_recovery_rejected"}',
        }
        prior = self.fragments.get(handle)
        if prior is None:
            return refused  # No public read or actual handler for unknown/unvalidated handles.
        try:
            result = handler._execute_retrieval(CCRToolCall(call_id, handle, "headroom_retrieve"))
            value = asdict(result)
            if (set(value) != {"tool_call_id", "tool_name", "success", "items_retrieved", "content"}
                    or value["tool_call_id"] != call_id or value["tool_name"] != "headroom_retrieve"
                    or value["success"] is not True or type(value["content"]) is not str
                    or len(value["content"].encode("utf-8")) > MAX_FRAME
                    or type(value["items_retrieved"]) is not int or value["items_retrieved"] < 0
                    or _internal_framing(value["content"]) or self.nonce in value["content"]):
                return refused
            payload = parse(value["content"])
            if (type(payload) is not dict or set(payload) != {"hash", "original_content", "original_item_count"}
                    or payload["hash"] != handle or type(payload["original_content"]) is not str
                    or payload["original_content"] != prior.raw
                    or type(payload["original_item_count"]) is not int
                    or payload["original_item_count"] != value["items_retrieved"]):
                return refused
            return value  # Actual handler content is NOT decoded, rewritten or reserialized.
        except Exception:
            return refused  # Never expose exception-derived vendor error text.


class DocumentPipeline:
    """Configured public pipeline, separate from the legacy facade singleton.

    ``compress(request)`` returns (CompressResult, receipt). The portable
    strategy_manifest and its sorted compact UTF-8 JSON SHA are task-stable.
    Top-level eligible_indices/protected_indices echo E and its complement;
    document_request records the frozen prefix and newest-K bound.
    It is configured Headroom, not unchanged-default Headroom or a shrink claim.
    The existing process-lifetime ONNX observer covers this path without new
    counters. Pipeline extensions/hooks are not selected (facade discover=False);
    upstream router inventory construction remains unchanged, no external
    compressors are selected.

    ``preprotect=True`` selects a separate strategy/RPC: mechanically verified
    parent spans get exact custom-tag frames, then the public tag preflight and
    the genuine pipeline. This mode explicitly reads the public CCR store for
    preparation validation, recording its access/feedback side effects. Raw
    entries/recovery results are never decoded or rewritten. Parent still owns
    structural/fence/Root/final-wire acceptance and publication evidence.
    """

    def __init__(self, preprotect: bool = False) -> None:
        from headroom import CompressConfig
        from headroom.config import DEFAULT_EXCLUDE_TOOLS, is_tool_excluded
        from headroom.telemetry.session import BeaconCompressionObserver
        from headroom.transforms import ContentRouter, TransformPipeline

        if type(preprotect) is not bool:
            raise ValueError("invalid preprotection selection")
        self.preprotection = _PreprotectionState() if preprotect else None
        prototype = TransformPipeline()
        positions = [i for i, stage in enumerate(prototype.transforms)
                     if isinstance(stage, ContentRouter)]
        if len(positions) != 1:
            raise ValueError("expected exactly one public ContentRouter")
        index = positions[0]
        original = prototype.transforms[index]
        exclusions = (DEFAULT_EXCLUDE_TOOLS if original.config.exclude_tools is None
                      else original.config.exclude_tools)
        router_config = replace(deepcopy(original.config), exclude_tools=set(exclusions) - {"view"})
        if preprotect:
            router_config = replace(router_config, compress_tagged_content=False)
        if is_tool_excluded("view", router_config.exclude_tools):
            raise ValueError("retained exclusion still protects view")
        if router_config.active_external_compressors or prototype.config.pipeline_extensions:
            raise ValueError("custom pipeline extensions are not selected")
        stages = list(prototype.transforms)
        stages[index] = ContentRouter(config=router_config, observer=BeaconCompressionObserver())
        self.pipeline = TransformPipeline(config=prototype.config, transforms=stages)
        self.config = CompressConfig(diagnostics=True, compress_system_messages=False)
        if self.config.savings_profile is not None:
            raise ValueError("document savings profile must remain unset")
        self.manifest = _portable({
            "strategy": PREPROTECTION_STRATEGY if preprotect else DOCUMENT_STRATEGY, "vendor_commit": COMMIT,
            "compress_config": self.config, "pipeline_config": self.pipeline.config,
            "stages": [{"class": type(stage).__module__ + "." + type(stage).__qualname__,
                        "name": stage.name,
                        "config": getattr(stage, "config", None)} for stage in stages],
            "router_index": index, "router_config": stages[index].config,
            "observer": "headroom.telemetry.session.BeaconCompressionObserver",
            "hooks": None, "extension_discovery": False, "external_compressors_selected": [],
            "apply": {"model": "request.model", "model_limit": 200000, "biases": None,
                      "context": "headroom.utils.extract_user_query",
                      "frozen_message_count": "document_request.frozen_message_count",
                      "protect": "complement_of_eligible_indices"},
            "guards": {"inflation": "revert_original_messages",
                       "failure": "reject_exception_or_nonpositive_token_sentinel",
                       "circuit": "preserved_public_pipeline_reject_circuit_open",
                       "protected_messages": "whole_message_equality_before_return",
                       "eligible_messages": "content_only_identity_preserved",
                       "eligibility": "parent_exact_bound_success_receipts_plus_worker_validation",
                       "eligible_tool": "view",
                       "view_arguments": {
                           "allowed_fields": ["path", "view_range", "forceReadLargeFiles"],
                           "forceReadLargeFiles": "optional_strict_boolean",
                           "view_range": {"optional": True, "integer_max": MAX_NATIVE_INTEGER,
                                          "start_min": 1, "end": "inclusive_gte_start_or_minus_one"},
                           "preserve_arguments": True,
                       },
                       "document_suffixes": [".md", ".markdown", ".rst", ".txt"],
                       "newest_tool_results": "document_request.keep_recent_tool_results",
                       "frozen_prefix": "document_request.frozen_message_count",
                       "fenced_interiors": "parent_acceptance_gate_not_zero_work",
                       "parent_acceptance": "typed_policy_whole_original_nonexpansion_fence_root_guards",
                       "strategy_lock": "first_compression_operation_for_task"},
        })
        if self.preprotection is not None:
            self.manifest["preprotection"] = {
                "span_contract": SPAN_CONTRACT, "codec": "task-owned-exact-custom-tag-frames-v1",
                "tag_protection": "public_protect_restore_roundtrip_then_original_pipeline",
                "compress_tagged_content": False, "reserved_families": list(_INTERNAL_FRAMING),
                "bounds": dict(self.preprotection.bounds),
                "span_authority": "trusted_parent_grammar_worker_mechanical_validation_only",
                "validation": "public_store_retrieve_before_return_access_feedback_side_effects",
                "vendor_content": "exact_nonempty_unique_pristine_slice_no_decoding_or_rekeying",
                "handle_binding": "immutable_raw_and_source_association_no_eviction",
                "recovery": "actual_handler_once_then_validate_unchanged_payload_no_preread",
                "publication": "unknown_no_parent_ack",
                "measurement": "annotated_upstream_counts_not_final_wire_savings",
                "parent_guards": "structure_fence_source_root_complete_original_nonexpansion",
            }
        self.manifest_sha256 = hashlib.sha256(_canonical(self.manifest).encode("utf-8")).hexdigest()

    def compress(self, request: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        if self.preprotection is not None:
            return self._compress_preprotected(request)
        from headroom import CompressResult
        from headroom.utils import extract_user_query

        eligible = document_indices(request)
        messages = deepcopy(request["messages"])
        protect = set(range(len(messages))) - eligible
        cfg = replace(self.config, frozen_message_count=request["frozen_message_count"])
        result = self.pipeline.apply(
            messages=deepcopy(messages), model=request["model"], model_limit=200000,
            context=extract_user_query(messages), biases=None, protect=protect,
            compress_user_messages=cfg.compress_user_messages,
            compress_system_messages=cfg.compress_system_messages, target_ratio=cfg.target_ratio,
            protect_recent=cfg.protect_recent, protect_analysis_context=cfg.protect_analysis_context,
            min_tokens_to_compress=cfg.min_tokens_to_compress, kompress_model=cfg.kompress_model,
            frozen_message_count=cfg.frozen_message_count, collect_diagnostics=cfg.diagnostics)
        if result.tokens_before <= 0 or result.tokens_after <= 0:
            raise ValueError("pipeline returned failure sentinel")
        if "pipeline:circuit_open" in result.transforms_applied:
            raise ValueError("pipeline circuit is open")
        if type(result.messages) is not list or len(result.messages) != len(messages):
            raise ValueError("pipeline changed protected message sequence")
        for index, (old, new) in enumerate(zip(messages, result.messages)):
            if index in protect:
                if _canonical(new) != _canonical(old):
                    raise ValueError("pipeline changed protected message")
            elif (type(new) is not dict or type(new.get("content")) is not str
                  or _canonical({k: v for k, v in new.items() if k != "content"})
                  != _canonical({k: v for k, v in old.items() if k != "content"})):
                raise ValueError("pipeline changed document identity")
        if result.tokens_after > result.tokens_before:
            compressed = CompressResult(
                messages=messages, tokens_before=result.tokens_before,
                tokens_after=result.tokens_before, transforms_applied=["inflation_guard:reverted"])
        else:
            saved = result.tokens_before - result.tokens_after
            compressed = CompressResult(
                messages=result.messages, tokens_before=result.tokens_before,
                tokens_after=result.tokens_after, tokens_saved=saved,
                compression_ratio=saved / result.tokens_before,
                transforms_applied=result.transforms_applied, diagnostics=result.message_decisions)
        return compressed, {
            "strategy": DOCUMENT_STRATEGY, "strategy_manifest": deepcopy(self.manifest),
            "strategy_manifest_sha256": self.manifest_sha256,
            "eligible_indices": sorted(eligible), "protected_indices": sorted(protect),
            "document_request": {"frozen_message_count": cfg.frozen_message_count,
                                 "keep_recent_tool_results": request["keep_recent_tool_results"]},
        }

    def _compress_preprotected(self, request: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        from headroom import CompressResult
        from headroom.utils import extract_user_query

        eligible = preprotection_indices(request)
        state = self.preprotection
        assert state is not None
        since = len(state.events)
        messages = deepcopy(request["messages"])
        annotated = deepcopy(messages)
        protect = set(range(len(messages))) - eligible
        effective_protect = protect.copy()
        frames: dict[int, list[_ProtectedFrame]] = {}
        bindings: dict[int, str] = {}
        decisions: dict[int, dict[str, Any]] = {}
        calls = {call["id"]: call for message in messages for call in message.get("tool_calls", [])}
        for entry in request["message_spans"]:
            index = entry["index"]
            original = messages[index]
            binding = _sha256(_canonical({
                "model": request["model"], "call": calls[original["tool_call_id"]],
                "result_metadata": {k: v for k, v in original.items() if k != "content"},
                "content_sha256": entry["content_sha256"],
            }))
            bindings[index] = binding
            text, message_frames, reason = state.annotate(original["content"], entry["spans"], binding)
            frames[index] = message_frames
            if reason is not None:
                effective_protect.add(index)
                decisions[index] = {"index": index, "status": "fallback", "reason": reason}
            annotated[index]["content"] = text
        if len(_canonical(annotated).encode("utf-8")) > MAX_FRAME:
            annotated = deepcopy(messages)
            effective_protect.update(eligible)
            decisions = {index: {"index": index, "status": "fallback", "reason": "annotated_frame_limit"}
                         for index in eligible}
        annotation = [{
            "index": index, "pristine_sha256": _sha256(messages[index]["content"]),
            "annotated_sha256": _sha256(annotated[index]["content"]),
            "pristine_chars": len(messages[index]["content"]),
            "annotated_chars": len(annotated[index]["content"]),
            "frame_count": 0 if index in effective_protect else len(frames[index]),
        } for index in sorted(eligible)]
        input_bytes = {
            "scope": "internal_canonical_message_json_not_native_model_wire",
            "pristine": len(_canonical(messages).encode("utf-8")),
            "annotated": len(_canonical(annotated).encode("utf-8")),
        }
        cfg = replace(self.config, frozen_message_count=request["frozen_message_count"])
        result = self.pipeline.apply(
            messages=annotated, model=request["model"], model_limit=200000,
            context=extract_user_query(messages), biases=None, protect=effective_protect.copy(),
            compress_user_messages=cfg.compress_user_messages,
            compress_system_messages=cfg.compress_system_messages, target_ratio=cfg.target_ratio,
            protect_recent=cfg.protect_recent, protect_analysis_context=cfg.protect_analysis_context,
            min_tokens_to_compress=cfg.min_tokens_to_compress, kompress_model=cfg.kompress_model,
            frozen_message_count=cfg.frozen_message_count, collect_diagnostics=cfg.diagnostics)
        if any(type(n) is not int or n <= 0 for n in (result.tokens_before, result.tokens_after)):
            raise ValueError("pipeline returned failure sentinel")
        if "pipeline:circuit_open" in result.transforms_applied:
            raise ValueError("pipeline circuit is open")
        if type(result.messages) is not list or len(result.messages) != len(messages):
            raise ValueError("pipeline changed protected message sequence")
        for index, (old, new) in enumerate(zip(messages, result.messages)):
            if index in effective_protect:
                if _canonical(new) != _canonical(old):
                    raise ValueError("pipeline changed protected message")
            elif (type(new) is not dict or type(new.get("content")) is not str
                  or _canonical({k: v for k, v in new.items() if k != "content"})
                  != _canonical({k: v for k, v in old.items() if k != "content"})):
                raise ValueError("pipeline changed document identity")

        inflated = result.tokens_after > result.tokens_before
        final = deepcopy(messages)
        for index in sorted(eligible):
            if index in decisions:
                continue
            if inflated:
                decisions[index] = {"index": index, "status": "fallback", "reason": "inflation_guard"}
                continue
            projected_text = _unframe(result.messages[index]["content"], frames[index], state.nonce)
            reason = None
            if projected_text is None:
                reason = "frame_integrity_failed"
            elif projected_text == messages[index]["content"]:
                decisions[index] = {"index": index, "status": "unchanged", "reason": "upstream_noop"}
                continue
            else:
                try:
                    handles = state.markers(projected_text)
                except Exception:
                    handles, reason = [], "marker_scan_failed"
                if len(handles) > state.bounds["max_handles"]:
                    reason = "handle_limit"
                if reason is None:
                    for handle in handles:
                        reason = state.validate(
                            handle, messages[index]["content"], bindings[index], request["id"], index)
                        if reason is not None:
                            break
            if reason is not None:
                decisions[index] = {"index": index, "status": "fallback", "reason": reason}
            else:
                final[index]["content"] = projected_text
                decisions[index] = {"index": index, "status": "validated_candidate", "reason": "checks_passed"}
        # These counters describe the actual annotated vendor pass, not the
        # deannotated/fallback result or any parent-approved complete wire.
        after = result.tokens_before if inflated else result.tokens_after
        saved = result.tokens_before - after
        return CompressResult(
            messages=final, tokens_before=result.tokens_before, tokens_after=after,
            tokens_saved=saved, compression_ratio=saved / result.tokens_before,
            transforms_applied=["inflation_guard:reverted"] if inflated else result.transforms_applied,
            diagnostics=None if inflated else result.message_decisions,
        ), {
            "strategy": PREPROTECTION_STRATEGY, "strategy_manifest": deepcopy(self.manifest),
            "strategy_manifest_sha256": self.manifest_sha256,
            "span_contract": SPAN_CONTRACT,
            "message_spans_sha256": _sha256(_canonical(request["message_spans"])),
            "eligible_indices": sorted(eligible), "protected_indices": sorted(protect),
            "document_request": {"frozen_message_count": cfg.frozen_message_count,
                                 "keep_recent_tool_results": request["keep_recent_tool_results"]},
            "preprotection": {
                "span_contract": SPAN_CONTRACT, "message_spans": deepcopy(request["message_spans"]),
                "decisions": [decisions[index] for index in sorted(decisions)],
                "effective_protected_indices": sorted(effective_protect),
                "annotation": annotation, "internal_input_bytes": input_bytes,
                "upstream_tokens_scope": "annotated_vendor_pass_before_adapter_fallback_not_final_wire",
                "candidate_publication": "unknown_no_parent_ack",
            },
            "preparation_validation": state.inventory(since),
        }

    def recover(self, handle: str, call_id: str, handler: Any) -> dict[str, Any]:
        if self.preprotection is None:
            raise ValueError("preprotection recovery requires its own strategy")
        return self.preprotection.recover(handle, call_id, handler)


def main() -> int:
    assert os.geteuid() == os.getegid() == 65532
    status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines()
                  if ":" in line)
    assert int(status["NoNewPrivs"].strip()) == 1
    assert all(int(status[key].strip(), 16) == 0 for key in
               ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"))
    assert sorted(path.name for path in Path("/sys/class/net").iterdir()) == ["lo"]
    assert not Path("/var/run/docker.sock").exists()
    assert os.environ["HF_HUB_OFFLINE"] == os.environ["TRANSFORMERS_OFFLINE"] == "1"
    assert not os.environ.get("HEADROOM_HF_PIN") and not os.environ.get("HF_TOKEN")
    Path("/tmp/headroom").mkdir(exist_ok=True)
    assets = parse(Path("/inputs/assets.json").read_text(encoding="utf-8"))
    if assets.get("complete") is not True:
        raise ValueError("asset receipt is incomplete")
    model_assets = [item for item in assets["verified_files"]
                    if item["repo_id"] == "chopratejas/kompress-v2-base"]
    assert len(model_assets) == 1
    assert model_assets[0]["revision"] == MODEL_REVISION
    assert model_assets[0]["file"] == "onnx/kompress-int8-wo.onnx"
    assert model_assets[0]["sha256"] == MODEL_SHA256
    for item in assets["verified_files"]:
        path = Path("/cache") / item["cache_path"]
        if not path.resolve().is_relative_to(Path("/cache").resolve()):
            raise ValueError("asset escaped cache")
        if (path.stat().st_size != item["bytes"]
                or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]):
            raise ValueError("model asset mismatch")
    tokenizer_ref = Path("/cache/hub/models--answerdotai--ModernBERT-base/refs/main")
    expected_tokenizer = next(item["revision"] for item in assets["verified_files"]
                              if item["repo_id"] == "answerdotai/ModernBERT-base")
    assert expected_tokenizer == TOKENIZER_REVISION
    assert tokenizer_ref.read_text() == expected_tokenizer
    import headroom
    from headroom.cache.compression_store import get_compression_store
    from headroom.ccr import CCRToolInjector
    from headroom.ccr.tool_injection import create_ccr_tool_definition
    from headroom.ccr.tool_calls import CCRToolCall
    from headroom.ccr.response_handler import CCRResponseHandler
    from headroom.onnx_runtime import _PINNED_REVISIONS
    from headroom.tokenizers.registry import get_tokenizer
    from headroom.transforms.kompress_compressor import KompressCompressor
    import onnxruntime as ort
    import tiktoken
    assert importlib.metadata.version("headroom-ai") == "0.39.1"
    assert _PINNED_REVISIONS["chopratejas/kompress-v2-base"] == MODEL_REVISION
    reference = tiktoken.get_encoding("cl100k_base")
    ledger = ActivityLedger()
    ort.InferenceSession.run = observe_run(ort.InferenceSession.run, ledger)
    ledger.context("warmup")
    started = time.monotonic()
    warmer = KompressCompressor()
    assert warmer.preload(allow_download=False) == "onnx"
    if warmer._canary_thread is not None:
        warmer._canary_thread.join(timeout=45)
        assert not warmer._canary_thread.is_alive()
    assert warmer._degraded_reason is None and warmer._inference_failures == 0
    warm = ledger.snapshot()
    cursor = warm.revision
    ledger.context("between_rpcs")
    config = headroom.CompressConfig(diagnostics=True)
    handler = CCRResponseHandler()
    scanner = CCRToolInjector()
    seen_hashes: set[str] = set()
    strategy: str | None = None
    documents: DocumentPipeline | None = None
    if not emit({
        "id": "ready", "ok": True, "protocol": "headroom-task-worker-v1",
        "worker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "commit": COMMIT, "model_revision": MODEL_REVISION,
        "tokenizer_revision": expected_tokenizer,
        "version": importlib.metadata.version("headroom-ai"), "config": asdict(config),
        "ccr_tool": create_ccr_tool_definition(provider="openai"),
        "warmup_seconds": time.monotonic() - started,
        "warmup_python_onnx_calls": _inventory(warm)["events"],
        "python_onnx_inventory": _inventory(warm),
        "python_onnx_calls_semantics": "compatibility_projection_deduplicate_by_event_id_and_revision",
        "warmup_protocol": "upstream-default-preload-and-canary-v1",
        "network_interfaces": ["lo"], "assets_verified": len(assets["verified_files"]),
        "local_inference_inventory_complete": False,
        "inference_scope": "Python ONNX run entries only; native detector/embedding internals remain unknown.",
    }, ledger=ledger):
        return 2
    identifier = None
    try:
        for _ in range(128):
            raw = sys.stdin.buffer.readline(MAX_FRAME + 1)
            if not raw:
                return 0
            if len(raw) > MAX_FRAME or not raw.endswith(b"\n"):
                raise ValueError("invalid request frame")
            request = parse(raw.decode("utf-8"))
            identifier = request.get("id")
            if type(identifier) is not str or not identifier or len(identifier) > 128:
                raise ValueError("request identity required")
            operation = request.get("op")
            ledger.context("finalizing" if operation == "finish" else "rpc", identifier)
            started = time.monotonic()
            try:
                if operation == "compress" and set(request) == {"id", "op", "model", "messages"}:
                    strategy = lock_strategy(strategy, "legacy")
                    model, messages = request["model"], request["messages"]
                    if type(model) is not str or type(messages) is not list:
                        raise ValueError("invalid materialized request")
                    result = headroom.compress(messages, model=model, model_limit=200000,
                                               optimize=True, config=config)
                    if result.tokens_before <= 0 or result.tokens_after <= 0:
                        raise ValueError("pipeline returned failure sentinel")
                    if "pipeline:circuit_open" in result.transforms_applied:
                        raise ValueError("pipeline circuit is open")
                    hashes = scanner.scan_for_markers(result.messages)
                    seen_hashes.update(hashes)
                    value = {"messages": result.messages, "transforms": result.transforms_applied,
                             "diagnostics": diagnostic_rows(result.diagnostics),
                             "reference_message_tokens": len(reference.encode_ordinary(
                                 json.dumps(result.messages, ensure_ascii=False, separators=(",", ":"),
                                            allow_nan=False))),
                             "upstream_counter": type(get_tokenizer(model)).__name__,
                             "upstream_tokens_before": result.tokens_before,
                             "upstream_tokens_after": result.tokens_after,
                             "references": sorted(hashes)}
                elif operation == "compress_documents" and set(request) == DOCUMENT_KEYS:
                    strategy = lock_strategy(strategy, DOCUMENT_STRATEGY)
                    document_indices(request)  # Reject before constructing vendor stages.
                    if documents is None:
                        documents = DocumentPipeline()
                    result, receipt = documents.compress(request)
                    hashes = scanner.scan_for_markers(result.messages)
                    seen_hashes.update(hashes)
                    value = {"messages": result.messages, "transforms": result.transforms_applied,
                             "diagnostics": diagnostic_rows(result.diagnostics),
                             "reference_message_tokens": len(reference.encode_ordinary(
                                 json.dumps(result.messages, ensure_ascii=False, separators=(",", ":"),
                                            allow_nan=False))),
                             "upstream_counter": type(get_tokenizer(request["model"])).__name__,
                             "upstream_tokens_before": result.tokens_before,
                             "upstream_tokens_after": result.tokens_after,
                             "references": sorted(hashes), **receipt}
                elif operation == "compress_documents_preprotected" and set(request) == PREPROTECTION_KEYS:
                    strategy = lock_strategy(strategy, PREPROTECTION_STRATEGY)
                    preprotection_indices(request)  # Reject malformed plans before vendor construction.
                    if documents is None:
                        documents = DocumentPipeline(preprotect=True)
                    result, receipt = documents.compress(request)
                    hashes = scanner.scan_for_markers(result.messages)
                    seen_hashes.update(hashes)
                    value = {"messages": result.messages, "transforms": result.transforms_applied,
                             "diagnostics": diagnostic_rows(result.diagnostics),
                             "reference_message_tokens": len(reference.encode_ordinary(
                                 json.dumps(result.messages, ensure_ascii=False, separators=(",", ":"),
                                            allow_nan=False))),
                             "upstream_counter": type(get_tokenizer(request["model"])).__name__,
                             "upstream_tokens_before": result.tokens_before,
                             "upstream_tokens_after": result.tokens_after,
                             "upstream_tokens_scope": "annotated_vendor_pass_not_final_wire",
                             "references": sorted(hashes), **receipt}
                elif operation == "retrieve" and set(request) == {"id", "op", "hash", "tool_call_id"}:
                    if type(request["hash"]) is not str or type(request["tool_call_id"]) is not str:
                        raise ValueError("invalid retrieval identity")
                    # The actual upstream handler creates the model-visible result;
                    # it receives no provider callback and cannot make extra LLM calls.
                    if strategy == PREPROTECTION_STRATEGY:
                        assert documents is not None
                        value = documents.recover(request["hash"], request["tool_call_id"], handler)
                    else:
                        result = handler._execute_retrieval(
                            CCRToolCall(request["tool_call_id"], request["hash"], "headroom_retrieve"))
                        value = asdict(result)
                elif operation == "finish" and set(request) == {"id", "op"}:
                    # Audit only after the primary task ended. Earlier audit reads
                    # would change the old strategies' upstream feedback policy.
                    # The new strategy explicitly records its earlier validation reads.
                    audit_hashes = set(seen_hashes)
                    if strategy == PREPROTECTION_STRATEGY and documents is not None:
                        assert documents.preprotection is not None
                        audit_hashes.update(event["handle"] for event in documents.preprotection.events)
                    recovered = {}
                    for key in sorted(audit_hashes):
                        entry = get_compression_store().retrieve(key)
                        recovered[key] = None if entry is None else entry.original_content
                    value = {"recoveries": recovered, "reference_count": len(audit_hashes),
                             "audit_after_task": True}
                    if strategy == PREPROTECTION_STRATEGY and documents is not None:
                        assert documents.preprotection is not None
                        value.update(
                            strategy=PREPROTECTION_STRATEGY,
                            recoveries_scope="raw_vendor_store_audit_may_contain_annotation_not_native_delivery",
                            audit_handle_scope="returned_markers_and_validation_attempts_not_complete_store",
                            preparation_validation=documents.preprotection.inventory(),
                        )
                else:
                    raise ValueError("unsupported worker operation")
                if operation == "finish":
                    # One consistent cutoff for the authoritative inventory AND its
                    # compatibility delta. Do not claim background quiescence or join
                    # additional work: unfinished attempts remain explicitly pending.
                    final = ledger.snapshot()
                    value["python_onnx_inventory"] = _inventory(final)
                    delta = replace(final, events=tuple(e for e in final.events if e.revision > cursor))
                else:
                    delta = ledger.snapshot(cursor)
                if not emit({"id": identifier, "ok": True, "result": value,
                      "seconds": time.monotonic() - started,
                      "python_onnx_calls": _inventory(delta, cursor)["events"],
                      "python_onnx_updates": _inventory(delta, cursor)},
                            ledger=ledger):
                    return 2
                cursor = delta.revision
                if operation == "finish":
                    return 0
            except Exception as error:
                delta = ledger.snapshot(cursor)
                validation_receipt = {}
                if (strategy == PREPROTECTION_STRATEGY and documents is not None
                        and documents.preprotection is not None):
                    validation_receipt["preparation_validation"] = documents.preprotection.inventory()
                emit({"id": identifier, "ok": False, "error_type": type(error).__name__,
                      "seconds": time.monotonic() - started,
                      "python_onnx_calls": _inventory(delta, cursor)["events"],
                      "python_onnx_updates": _inventory(delta, cursor),
                      "python_onnx_inventory": ledger.inventory(), **validation_receipt}, ledger=ledger)
                return 2
            finally:
                ledger.context("between_rpcs")
        raise ValueError("worker operation budget exhausted")
    except BaseException as error:
        if isinstance(error, Exception) or strategy != PREPROTECTION_STRATEGY:
            raise  # Preserve ordinary failures and old-mode cancellation behavior.
        try:
            # Best effort at the outer boundary, including between-RPC exits.
            # One current cutoff; no vendor reread, retry, join or quiescence claim.
            final = ledger.snapshot()
            delta = replace(final, events=tuple(e for e in final.events if e.revision > cursor))
            validation_receipt = {}
            if documents is not None and documents.preprotection is not None:
                validation_receipt["preparation_validation"] = documents.preprotection.inventory()
            emit({"id": identifier, "ok": False, "error_type": type(error).__name__,
                  "seconds": time.monotonic() - started,
                  "python_onnx_calls": _inventory(delta, cursor)["events"],
                  "python_onnx_updates": _inventory(delta, cursor),
                  "python_onnx_inventory": _inventory(final), **validation_receipt}, ledger=ledger)
        except BaseException:
            # Closed pipes or another interruption may prevent delivery. Never
            # replace the original cancellation with an inventory/emit failure.
            pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
