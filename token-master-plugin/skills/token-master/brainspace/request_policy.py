"""Opt-in request planning, not a host interceptor or a quality certificate.

Only explicitly materialized ``chat-completions-v1`` dictionaries are supported.
The adapter owns protocol selection, exact-answer annotations and cached-prefix
length. Unknown protocols/shapes pass through; there is no history deletion.
Only older paired tool *strings* may change. Legacy policies require
navigation/overview intent and round-trip recovery; V3 permits only exact reuse.
Arrays, schemas, instructions and metadata stay intact.
V2 can exempt a successful source read from the failure-word heuristic using
executor-supplied, hash-bound metadata. V1 semantics remain unchanged.
V3 never uses lossy views: it can reuse an exact duplicate read only while its
unchanged full original remains visible in the same request.
V4 conservatively compacts successful, bound JSON reads without changing any
JSON lexeme. Its fixed root-reference footer makes the whole result a view, not
standalone JSON. Exact/edit/debug intents and newest results remain protected.

``count`` receives the complete compact JSON string, never additive text chunks.
Its identity/exactness must be recorded and certified outside this module.
Pass ``tokens.count_tokens`` for the pinned reference; absence or failure of the
counter is passthrough, never an estimate. Accepted changes strictly reduce this
count and do not increase wire bytes.
Output caps check an existing request declaration; they do not enforce obedience
or inject provider parameters. Use the returned ``serialized`` as the wire form
or rerun the guard if an adapter adds wrappers or uses another serialization.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields, replace
from typing import Any, Callable
from urllib.parse import quote


PROTOCOL = "chat-completions-v1"
SERIALIZATION = "json-utf8-compact-v1"
_PROTECTED_ROLES = ("system", "developer")
_ERROR_TEXT = re.compile(r"\b(error|failed|denied|fatal|exception|traceback)\b", re.I)
_EXACT_TEXT = re.compile(r"```|~~~|<exact[-_]answer\b|BEGIN EXACT", re.I)
_VERSIONS = ("request-policy-v1", "request-policy-v2", "request-policy-v3", "request-policy-v4", "request-policy-v5",
             "request-policy-v6")
# These versions' contracts count every wrapper, recovery and guidance token, so the
# non-expanding whole-input guard is mandatory for them.
NONEXPANDING_VERSIONS = ("request-policy-v4", "request-policy-v5", "request-policy-v6")
_SOURCE_SUFFIXES = (".py", ".pyi", ".rs")


def _integer(value: Any, name: str, low: int, high: int | None = None) -> None:
    if type(value) is not int or value < low or (high is not None and value > high):
        raise ValueError(f"invalid {name}")


def serialize_request(request: Any) -> str:
    """Insertion-order-preserving JSON; UTF-8 bytes are the declared wire unit."""
    return json.dumps(request, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class RequestPolicy:
    version: str = "request-policy-v1"
    enabled: bool = False
    min_tool_chars: int = 1024
    keep_recent_tool_results: int = 1
    max_transforms: int = 4
    max_input_tokens: int | None = None
    max_wire_bytes: int | None = None
    max_output_tokens: int | None = None
    protected_roles: tuple[str, ...] = _PROTECTED_ROLES
    recovery_required: bool = True
    measurement_protocol: str = SERIALIZATION
    quality_gate: str = "external-certification-required"

    def __post_init__(self) -> None:
        if self.version not in _VERSIONS or type(self.enabled) is not bool:
            raise ValueError("unsupported policy version or enabled flag")
        if (type(self.protected_roles) is not tuple
                or self.protected_roles != _PROTECTED_ROLES
                or self.recovery_required is not True
                or self.measurement_protocol != SERIALIZATION
                or self.quality_gate != "external-certification-required"):
            raise ValueError("protected invariants cannot be changed")
        _integer(self.min_tool_chars, "min_tool_chars", 1, 1_000_000)
        _integer(self.keep_recent_tool_results, "keep_recent_tool_results", 1, 64)
        _integer(self.max_transforms, "max_transforms", 1, 64)
        for name in ("max_input_tokens", "max_wire_bytes", "max_output_tokens"):
            if getattr(self, name) is not None:
                _integer(getattr(self, name), name, 1)

    def to_dict(self) -> dict:
        value = asdict(self)
        value["protected_roles"] = list(self.protected_roles)
        return value

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)

    @classmethod
    def from_dict(cls, value: dict) -> RequestPolicy:
        if (type(value) is not dict or value.get("version") not in _VERSIONS
                or set(value) - {field.name for field in fields(cls)}):
            raise ValueError("invalid versioned policy")
        data = dict(value)
        if "protected_roles" in data:
            if not isinstance(data["protected_roles"], (list, tuple)):
                raise ValueError("invalid protected_roles")
            data["protected_roles"] = tuple(data["protected_roles"])
        return cls(**data)

    @classmethod
    def from_json(cls, value: str) -> RequestPolicy:
        return cls.from_dict(json.loads(value))

    @property
    def policy_id(self) -> str:
        return self.version + ":" + hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()


def policy_neighbors(policy: RequestPolicy) -> tuple[RequestPolicy, ...]:
    """At most six local proposals; never mutate consent, budgets or safety gates."""
    result = []
    for name, step, low, high in (
        ("min_tool_chars", 128, 1, 1_000_000),
        ("keep_recent_tool_results", 1, 1, 64),
        ("max_transforms", 1, 1, 64),
    ):
        current = getattr(policy, name)
        for value in (max(low, current - step), min(high, current + step)):
            if value != current:
                result.append(replace(policy, **{name: value}))
    return tuple(result)


@dataclass(frozen=True)
class SourceReadInfo:
    """Out-of-band executor observation, never a model/content assertion.

    Construct only after the real read's outcome is known. This is a trusted
    adapter contract, not authentication. Matching binds the observation to the
    ordered tool call, requested filename and exact UTF-8 result, not an index
    that can become stale after history changes.
    """
    call_id: str
    tool_name: str
    source_path: str
    content_sha256: str
    status: str

    def __post_init__(self):
        for key, limit in (("call_id", 512), ("tool_name", 256), ("source_path", 4096)):
            value = getattr(self, key)
            if type(value) is not str or not value.strip() or len(value) > limit or "\0" in value:
                raise ValueError("invalid source-read identity")
        if (type(self.content_sha256) is not str
                or re.fullmatch(r"[0-9a-f]{64}", self.content_sha256) is None
                or type(self.status) is not str or self.status not in ("success", "error", "unknown")):
            raise ValueError("invalid source-read status or digest")

    @classmethod
    def from_text(cls, *, call_id, tool_name, source_path, content, status):
        if type(content) is not str:
            raise ValueError("source-read result must be complete text")
        return cls(call_id, tool_name, source_path,
                   hashlib.sha256(content.encode("utf-8")).hexdigest(), status)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict or set(value) != {field.name for field in fields(cls)}:
            raise ValueError("invalid source-read fields")
        return cls(**value)

    def matches(self, message, call):
        if (type(message) is not dict or type(message.get("content")) is not str
                or message.get("tool_call_id") != self.call_id or type(call) is not dict
                or type(call.get("function")) is not dict or call["function"].get("name") != self.tool_name):
            return False

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate tool argument")
                result[key] = value
            return result

        try:
            if hashlib.sha256(message["content"].encode("utf-8")).hexdigest() != self.content_sha256:
                return False
            arguments = json.loads(call["function"]["arguments"], object_pairs_hook=unique)
            if type(arguments) is not dict:
                return False
            paths = [arguments[key] for key in ("path", "file_path", "filePath") if key in arguments]
            return len(paths) == 1 and type(paths[0]) is str and paths[0] == self.source_path
        except (ValueError, TypeError, KeyError, RecursionError):
            return False


# Native view is admitted only through the same exact call/path/content binding.
# The native adapter supplies real executor events; names are never rewritten to
# read_file/fetch_artifact to evade an upstream compressor's routing rules.
QUALIFIED_SOURCE_TOOLS = frozenset(("read_file", "fetch_artifact", "view"))


@dataclass(frozen=True)
class TransformResult:
    """Caller supplies the final text INCLUDING its usable recovery reference."""
    text: str
    recovery_reference: str


@dataclass(frozen=True)
class RequestPlan:
    request: Any
    serialized: str | None
    status: str
    reason: str
    policy_id: str
    changed_message_indices: tuple[int, ...] = ()
    tokens_before: int | None = None
    tokens_after: int | None = None
    wire_bytes_before: int | None = None
    wire_bytes_after: int | None = None
    measurement: str = "caller_supplied_uncertified"
    host_interception: str = "unsupported"


def _json_value(value: Any) -> bool:
    # Do not silently coerce tuples, integer keys, custom mappings, NaN or bytes.
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return value == value and value not in (float("inf"), -float("inf"))
    if type(value) is list:
        return all(_json_value(item) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _json_value(item) for key, item in value.items())
    return False


def _tool_indices(request: Any) -> list[int]:
    """Validate the supported envelope and complete ordered call/result pairing."""
    if type(request) is not dict or not _json_value(request):
        raise ValueError("not a JSON envelope")
    messages = request.get("messages")
    if type(messages) is not list or not messages:
        raise ValueError("missing messages")
    if "tools" in request and (type(request["tools"]) is not list
                              or any(type(tool) is not dict for tool in request["tools"])):
        raise ValueError("invalid tools")
    for tool in request.get("tools", []):
        function = tool.get("function")
        if (tool.get("type") != "function" or type(function) is not dict
                or type(function.get("name")) is not str or not function["name"]
                or ("parameters" in function and type(function["parameters"]) is not dict)):
            raise ValueError("unsupported tool schema")
    for name in ("max_tokens", "max_completion_tokens"):
        if name in request:
            _integer(request[name], name, 1)
    pending: set[str] = set()
    seen: set[str] = set()
    indices: list[int] = []
    for index, message in enumerate(messages):
        if type(message) is not dict:
            raise ValueError("invalid message")
        role = message.get("role")
        if role not in ("system", "developer", "user", "assistant", "tool"):
            raise ValueError("unknown role")
        content = message.get("content")
        if content is not None and type(content) not in (str, list):
            raise ValueError("unknown content shape")
        if type(content) is list:
            # The first version knows text blocks only. Mixed/multimodal or new
            # block schemas bypass the entire request, rather than guessing.
            if any(type(block) is not dict or block.get("type") != "text"
                   or type(block.get("text")) is not str for block in content):
                raise ValueError("unsupported content block")
        if role == "tool":
            call_id = message.get("tool_call_id")
            if type(call_id) is not str or call_id not in pending or content is None:
                raise ValueError("unpaired result")
            if "tool_calls" in message:
                raise ValueError("tool result with calls")
            pending.remove(call_id)
            indices.append(index)
            continue
        if pending or "tool_call_id" in message or "function_call" in message:
            raise ValueError("incomplete or unsupported call sequence")
        if "tool_calls" not in message:
            if content is None:
                raise ValueError("empty message")
            continue
        calls = message["tool_calls"]
        if role != "assistant" or type(calls) is not list or not calls:
            raise ValueError("invalid tool calls")
        for call in calls:
            if type(call) is not dict or call.get("type") != "function":
                raise ValueError("unsupported call")
            call_id, function = call.get("id"), call.get("function")
            if (type(call_id) is not str or not call_id or call_id in seen
                    or type(function) is not dict
                    or type(function.get("name")) is not str or not function["name"]
                    or type(function.get("arguments")) is not str):
                raise ValueError("invalid call")
            seen.add(call_id)
            pending.add(call_id)
    if pending:
        raise ValueError("missing call result")
    return indices


def _protected(value: Any, *, strict_status: bool = False) -> bool:
    """Conservatively retain exact blocks and error-bearing tool envelopes."""
    if type(value) is dict:
        for key, item in value.items():
            if strict_status:
                if key in ("exit_code", "exitCode", "returncode", "return_code"):
                    if type(item) is not int or item != 0:
                        return True
                if key in ("is_error", "isError", "interrupted", "is_interrupt", "isImage", "is_image"):
                    if item is not False:
                        return True
                if key in ("ok", "success", "succeeded") and item is not True:
                    return True
                if key == "stderr" and (type(item) is not str or item):
                    return True
                if key == "errors" and item:
                    return True
            if key in ("exact_answer", "preserve_exact", "is_error", "isError", "error", "stderr"):
                if item:
                    return True
            if key in ("exit_code", "exitCode", "returncode") and item not in (None, 0):
                return True
            if key == "status" and item not in ("success", "ok", "completed"):
                return True
            if _protected(item, strict_status=strict_status):
                return True
    elif type(value) is list:
        return any(_protected(item, strict_status=strict_status) for item in value)
    elif type(value) is str:
        return bool(_ERROR_TEXT.search(value) or _EXACT_TEXT.search(value))
    return False


def _measure(wire: str, count: Callable[[str], int]) -> tuple[int, int]:
    tokens = count(wire)
    _integer(tokens, "count result", 0)
    return tokens, len(wire.encode("utf-8"))


def _fits(request: dict, policy: RequestPolicy, tokens: int, wire_bytes: int) -> bool:
    if policy.max_input_tokens is not None and tokens > policy.max_input_tokens:
        return False
    if policy.max_wire_bytes is not None and wire_bytes > policy.max_wire_bytes:
        return False
    if policy.max_output_tokens is not None:
        declared = [request[name] for name in ("max_tokens", "max_completion_tokens")
                    if name in request]
        if not declared or any(value > policy.max_output_tokens for value in declared):
            return False
    return True


def _json_root_reference(reference: str, content: str, info: SourceReadInfo) -> bool:
    """The one v4 footer form: canonical scoped CCR v2 JSON root, no summary.

    Scope authenticity/storage remain recover()'s job. Bind the visible root
    declaration to the complete original bytes and executor-reported filename.
    """
    raw = content.encode("utf-8")
    prefix = "[[BR:" + hashlib.sha256(raw).hexdigest() + "|v=2;scope="
    suffix = (f";kind=root;source={quote(info.source_path, safe='/:._-')};type=json;summary=;"
              f"chars={len(content)};bytes={len(raw)}]]")
    return re.fullmatch(re.escape(prefix) + r"[0-9a-f]{64}" + re.escape(suffix), reference) is not None


def plan_request(
    request: Any, *, policy: RequestPolicy | None = None, protocol: str | None = None,
    intent: str | None = None, transform: Callable[[str], TransformResult] | None = None,
    recover: Callable[[str], str | None] | None = None, count: Callable[[str], int] | None = None,
    stable_prefix_messages: int = 0, exact_message_indices: tuple[int, ...] = (),
    source_reads: tuple[SourceReadInfo, ...] = (),
    source_transform: Callable[[str, SourceReadInfo], TransformResult] | None = None,
    json_transform: Callable[[str, SourceReadInfo], TransformResult] | None = None,
    v5_transform: Callable[[str, SourceReadInfo], TransformResult] | None = None,
) -> RequestPlan:
    """Return an unchanged input on any unsafe plan; never truncate by default.

    ``stable_prefix_messages`` protects [0, n). ``exact_message_indices`` protects
    caller-identified answer-bearing messages, in addition to marked exact blocks.
    Callbacks must be deterministic. They may store recovery data, but no implicit
    I/O, host discovery, token-counter fallback or interceptor exists here.
    ``source_reads`` is supplied separately by the executor, not read from the
    request or model text. V1 ignores it. V2 still requires source syntax checks
    in the transform, exact recovery and the final token/byte guard.
    ``source_transform`` receives only the receipt bound to this exact candidate,
    never a filename inferred from another message with identical text.
    V3 uses no transform/recover callback or additional model instructions.
    Its exact visible reuse is verified by expansion, not off-request storage.
    V4 calls only json_transform(content, bound_info), after independently finding
    a lexical change using conservative compress_json. Its only accepted text is
    compact_json + "\\n" + a canonical scoped CCR v2 JSON root reference (empty
    summary, bound filename). The payload preserves lexemes; the footer is NOT
    part of the JSON document. Generic transforms never drive this branch.
    V4 bounds callback/storage attempts by max_transforms, including proposals
    subsequently rejected by the final request guard.
    """
    policy = policy if policy is not None else RequestPolicy()
    original_wire = None
    before_tokens = before_bytes = None

    def unchanged(reason: str) -> RequestPlan:
        return RequestPlan(request, original_wire, "unchanged", reason, policy.policy_id,
                           tokens_before=before_tokens, tokens_after=before_tokens,
                           wire_bytes_before=before_bytes, wire_bytes_after=before_bytes)

    if not policy.enabled:
        return unchanged("not_enabled")
    if protocol != PROTOCOL:
        return unchanged("unsupported_protocol")
    source_by_call = {}
    if policy.version in ("request-policy-v2", "request-policy-v3", "request-policy-v4", "request-policy-v5"):
        if type(source_reads) not in (tuple, list):
            return unchanged("invalid_source_reads")
        for info in source_reads:
            if type(info) is not SourceReadInfo or info.call_id in source_by_call:
                return unchanged("invalid_source_reads")
            source_by_call[info.call_id] = info
    try:
        indices = _tool_indices(request)
        _integer(stable_prefix_messages, "stable_prefix_messages", 0, len(request["messages"]))
        if type(exact_message_indices) not in (tuple, list):
            raise ValueError("invalid exact indices")
        for index in exact_message_indices:
            _integer(index, "exact index", 0, len(request["messages"]) - 1)
        original_wire = serialize_request(request)
    except (ValueError, TypeError, RecursionError, OverflowError):
        return unchanged("invalid_envelope")
    if count is None:
        return unchanged("measurement_unavailable")
    try:
        before_tokens, before_bytes = _measure(original_wire, count)
    except Exception:
        return unchanged("measurement_unavailable")
    if policy.version == "request-policy-v6":
        from .v6_shaping import plan_v6_request

        return plan_v6_request(
            request, policy=policy, indices=indices, exact_message_indices=tuple(exact_message_indices),
            original_wire=original_wire, before_tokens=before_tokens, before_bytes=before_bytes, count=count,
        )
    if policy.version == "request-policy-v5":
        from .v5_reducer import plan_v5_request

        return plan_v5_request(
            request, policy=policy, intent=intent, indices=indices,
            source_by_call=source_by_call, stable_prefix_messages=stable_prefix_messages,
            exact_message_indices=exact_message_indices, original_wire=original_wire,
            before_tokens=before_tokens, before_bytes=before_bytes,
            count=count, recover=recover, v5_transform=v5_transform,
        )
    if policy.version == "request-policy-v4":
        if (intent not in ("conservative", "navigation", "overview", "aggregate", "task")
                or json_transform is None or recover is None):
            return unchanged("no_eligible_transform" if _fits(
                request, policy, before_tokens, before_bytes) else "cannot_safely_meet_budget")
        from .compressors.json_compressor import compress_json

        candidate = copy.deepcopy(request)
        calls = {call["id"]: call for message in candidate["messages"]
                 for call in message.get("tool_calls", [])}
        wire, measured_tokens, wire_bytes = original_wire, before_tokens, before_bytes
        accepted_json = []
        json_attempts = 0
        try:
            for index in indices[:-policy.keep_recent_tool_results]:
                if json_attempts >= policy.max_transforms:
                    break
                message = candidate["messages"][index]
                text = message["content"]
                json_info = source_by_call.get(message["tool_call_id"])
                if (index < stable_prefix_messages or index in exact_message_indices
                        or type(text) is not str or len(text) < policy.min_tool_chars
                        or json_info is None or json_info.status != "success"
                        or json_info.tool_name not in QUALIFIED_SOURCE_TOOLS
                        or not json_info.matches(message, calls.get(json_info.call_id))
                        or _protected({k: v for k, v in message.items() if k != "content"},
                                      strict_status=True)
                        or _EXACT_TEXT.search(text)):
                    continue
                compact = compress_json(text, intent="conservative")
                if compact == text:
                    continue  # Malformed/already compact: no callback or storage.
                json_attempts += 1
                result = json_transform(text, json_info)
                if (type(result) is not TransformResult or type(result.text) is not str
                        or type(result.recovery_reference) is not str
                        or not _json_root_reference(result.recovery_reference, text, json_info)
                        or result.text != compact + "\n" + result.recovery_reference):
                    return unchanged("json_verification_failed")
                restored = recover(result.recovery_reference)
                if type(restored) is not str or restored.encode("utf-8") != text.encode("utf-8"):
                    return unchanged("json_verification_failed")
                message["content"] = result.text
                proposed_wire = serialize_request(candidate)
                proposed_tokens, proposed_bytes = _measure(proposed_wire, count)
                if proposed_tokens >= measured_tokens or proposed_bytes > wire_bytes:
                    message["content"] = text
                    continue
                wire, measured_tokens, wire_bytes = proposed_wire, proposed_tokens, proposed_bytes
                accepted_json.append(index)
                if len(accepted_json) >= policy.max_transforms:
                    break
        except Exception:
            return unchanged("json_verification_failed")
        if not _fits(candidate, policy, measured_tokens, wire_bytes):
            return unchanged("cannot_safely_meet_budget")
        if not accepted_json:
            return unchanged("no_eligible_transform")
        return RequestPlan(
            candidate, wire, "transformed", "exact_json_compaction", policy.policy_id,
            tuple(accepted_json), before_tokens, measured_tokens, before_bytes, wire_bytes)
    if policy.version == "request-policy-v3":
        if intent not in ("conservative", "navigation", "overview", "aggregate", "edit", "debug", "task"):
            return unchanged("no_eligible_transform" if _fits(
                request, policy, before_tokens, before_bytes) else "cannot_safely_meet_budget")
        from .exact_reuse import find_exact_reuses, restore_exact_reuses

        candidate = copy.deepcopy(request)
        calls = {call["id"]: call for message in candidate["messages"]
                 for call in message.get("tool_calls", [])}
        verified = {}
        for index in indices:
            message = candidate["messages"][index]
            text = message["content"]
            read_info = source_by_call.get(message["tool_call_id"])
            if (type(text) is not str or read_info is None or read_info.status != "success"
                    or read_info.tool_name not in QUALIFIED_SOURCE_TOOLS
                    or not read_info.matches(message, calls.get(read_info.call_id))
                    or _protected({k: v for k, v in message.items() if k != "content"},
                                  strict_status=True)
                    or _EXACT_TEXT.search(text)):
                continue
            verified[index] = read_info
        targets = {i for i in indices[:-policy.keep_recent_tool_results] if i in verified
                   and i >= stable_prefix_messages and i not in exact_message_indices
                   and len(candidate["messages"][i]["content"]) >= policy.min_tool_chars}
        wire, measured_tokens, wire_bytes = original_wire, before_tokens, before_bytes
        accepted = []
        try:
            for reuse in find_exact_reuses(candidate["messages"], verified, targets):
                message = candidate["messages"][reuse.target_index]
                original = message["content"]
                message["content"] = reuse.marker
                proposed_wire = serialize_request(candidate)
                proposed_tokens, proposed_bytes = _measure(proposed_wire, count)
                if proposed_tokens >= measured_tokens or proposed_bytes > wire_bytes:
                    message["content"] = original
                    continue
                accepted.append(reuse)
                wire, measured_tokens, wire_bytes = proposed_wire, proposed_tokens, proposed_bytes
                if len(accepted) >= policy.max_transforms:
                    break
            if accepted and restore_exact_reuses(candidate["messages"], tuple(accepted)) != request["messages"]:
                return unchanged("reuse_verification_failed")
        except Exception:
            return unchanged("reuse_verification_failed")
        if not _fits(candidate, policy, measured_tokens, wire_bytes):
            return unchanged("cannot_safely_meet_budget")
        if not accepted:
            return unchanged("no_eligible_transform")
        return RequestPlan(
            candidate, wire, "transformed", "exact_visible_reuse", policy.policy_id,
            tuple(r.target_index for r in accepted), before_tokens, measured_tokens,
            before_bytes, wire_bytes)
    if intent not in ("navigation", "overview") or transform is None or recover is None:
        reason = "no_eligible_transform" if _fits(request, policy, before_tokens, before_bytes) \
            else "cannot_safely_meet_budget"
        return unchanged(reason)

    candidate = copy.deepcopy(request)
    calls = {call["id"]: call for message in candidate["messages"]
             for call in message.get("tool_calls", [])}
    wire, tokens, wire_bytes = original_wire, before_tokens, before_bytes
    changed = []
    for index in indices[:-policy.keep_recent_tool_results]:
        message = candidate["messages"][index]
        text = message["content"]
        protected = _protected(message, strict_status=policy.version == "request-policy-v2")
        candidate_info = source_by_call.get(message["tool_call_id"])
        bound_source = None
        if candidate_info is not None and candidate_info.matches(message, calls.get(candidate_info.call_id)):
            if candidate_info.status != "success":
                protected = True
            elif candidate_info.source_path.lower().endswith(_SOURCE_SUFFIXES):
                # Source payload words are data. Actual status/exactness flags
                # and exact markers remain authoritative and unchanged.
                protected = (
                    _protected({key: value for key, value in message.items() if key != "content"},
                               strict_status=True)
                    or bool(_EXACT_TEXT.search(text))
                )
                bound_source = candidate_info
        if (index < stable_prefix_messages or index in exact_message_indices
                or type(text) is not str or len(text) < policy.min_tool_chars
                or protected):
            continue
        try:
            result = (source_transform(text, bound_source)
                      if bound_source is not None and source_transform is not None else transform(text))
            if (not isinstance(result, TransformResult) or type(result.text) is not str
                    or type(result.recovery_reference) is not str
                    or not result.recovery_reference.strip()
                    or result.recovery_reference not in result.text
                    or result.text == text or recover(result.recovery_reference) != text):
                continue
            message["content"] = result.text
            proposed_wire = serialize_request(candidate)
            proposed_tokens, proposed_bytes = _measure(proposed_wire, count)
            if proposed_tokens >= tokens or proposed_bytes > wire_bytes:
                message["content"] = text
                continue
        except Exception:
            message["content"] = text
            continue
        wire, tokens, wire_bytes = proposed_wire, proposed_tokens, proposed_bytes
        changed.append(index)
        if len(changed) >= policy.max_transforms:
            break
    if not _fits(candidate, policy, tokens, wire_bytes):
        return unchanged("cannot_safely_meet_budget")
    if not changed:
        return unchanged("no_eligible_transform")
    return RequestPlan(candidate, wire, "transformed", "within_budget", policy.policy_id,
                       tuple(changed), before_tokens, tokens, before_bytes, wire_bytes)
