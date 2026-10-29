"""Task-scoped production integration over caller-owned encode/send transport.

One session owns instruction selection, one reducer, recovery and a complete
observed call journal. The host retains its original full history and owns tool
permissions. No shell executor, global interception, model self-grading, policy
search or automatic promotion is hidden inside request preparation.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
from threading import Lock
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
import uuid

from . import tokens
from .ccr import CCR
from .optimizer import Optimizer, reference_measurement
from .pipeline import prepare_request
from .protected_text import protected_text_preserved, restore_protected_text
from .request_policy import (
    NONEXPANDING_VERSIONS, PROTOCOL, QUALIFIED_SOURCE_TOOLS, RequestPolicy, SourceReadInfo, _protected,
    _tool_indices,
)
from .runtime_io import append_receipt, parse_json, safe_root
from .task_mode import ModeStatus, render_task_mode
from .token_ledger import COMPLETE, CallRecord, TaskTrace, TokenLedger, measure_call
from .transport import Reply

if TYPE_CHECKING:
    from .headroom import HeadroomContainer


RUNTIME_VERSION = "tokenmaster-task-runtime-v1"
_NO_SUBMISSION = {
    "network_not_allowed", "invalid_request", "request_too_large", "transport_setup_error",
}
_ROLES = ("primary", "auxiliary", "verification", "recovery", "retry")
_RECOVERY_TOOLS: list[dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "retrieve_original",
        "description": "TokenMaster [[BR:...]] recovery: return an exact 32768-character page.",
        "parameters": {"type": "object", "properties": {
            "ref": {"type": "string"}, "offset": {"type": "integer"}},
            "required": ["ref", "offset"], "additionalProperties": False}, "strict": True}},
    {"type": "function", "function": {
        "name": "headroom_retrieve",
        "description": "Headroom recovery only: retrieve the hash from a Headroom marker.",
        "parameters": {"type": "object", "properties": {"hash": {"type": "string"}},
                       "required": ["hash"], "additionalProperties": False}, "strict": True}},
]


def _digest(value):
    return hashlib.sha256(tokens.serialize(value).encode("utf-8")).hexdigest()


def _wire_metrics(wire: str, reference_tokens: int) -> dict[str, Any]:
    """Use the same wire-text digest convention as invocation/preparation receipts."""
    return {"reference_tokens": reference_tokens, "utf8_bytes": len(wire.encode("utf-8")),
            "wire_sha256": _digest(wire)}


def _write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2, allow_nan=False)
        stream.write("\n")


def _usage(output):
    """Reported Responses-style usage only; absent/inconsistent is unknown."""
    try:
        body = parse_json(output)
        usage = body.get("usage") if type(body) is dict else None
        keys = ("input_tokens", "output_tokens", "total_tokens")
        if type(usage) is not dict or any(
                type(usage.get(k)) is not int or usage[k] < 0 for k in keys):
            return None
        if usage["input_tokens"] + usage["output_tokens"] != usage["total_tokens"]:
            return None
        return {key: usage[key] for key in keys}
    except (ValueError, TypeError, AttributeError):
        return None


@dataclass(frozen=True)
class ExecutedToolResult:
    """Explicit executor outcome; bare strings do not attest successful reads."""
    content: str
    status: str

    def __post_init__(self):
        if type(self.content) is not str or self.status not in ("success", "error", "unknown"):
            raise ValueError("invalid_executor_result")
        self.content.encode("utf-8")


class RuntimeSession:
    """Single-caller task session. Only invoke() submits model requests.

    transport.encode(chat) returns the final UTF-8 wire; transport.send(wire)
    submits that exact wire and returns Reply. It must not hide retries or
    auxiliary model calls. The builtin transport is loopback/opt-in only.
    Other adapters and Python executors are trusted application code, not a
    sandbox. No success is inferred from an assistant answer or test exit text.
    """
    _FROZEN_FIELDS = frozenset((
        "workspace", "output", "measurement", "policy", "mode", "ponytail",
        "backend", "transport", "session_id", "task_id", "run_id", "phase", "learning_run_id",
        "harness_id", "max_calls", "policy_id", "profile_id",
        "require_nonexpanding_input", "runtime_policy", "runtime_resources",
        "_headroom_strategy", "_headroom_root_reference_style", "_headroom_structure_guard",
    ))

    def __setattr__(self, name, value):
        if name in self._FROZEN_FIELDS and name in self.__dict__:
            raise AttributeError("runtime_configuration_is_frozen")
        super().__setattr__(name, value)

    def __init__(
        self, *, workspace, session_id, output, transport, backend="none",
        policy=None, mode=None, ponytail=None, headroom_options=None,
        harness_id=RUNTIME_VERSION, phase="deployment", learning_run_id=None,
        max_calls=64, optimizer=None, optimizer_version=None,
        workload_id=None, environment_id=None, task_id=None,
        require_nonexpanding_input: bool = False,
        runtime_policy=None, runtime_resources=None,
    ):
        # A closed full-runtime policy owns its composition. Never accept a
        # caller-supplied identity label for independently selected execution.
        if runtime_policy is not None:
            from .runtime_policy import RuntimePolicy
            from .runtime_resources import RuntimeResources
            if (type(runtime_policy) is not RuntimePolicy
                    or backend != "none" or policy is not None or mode is not None
                    or ponytail is not None or headroom_options is not None
                    or optimizer is not None or optimizer_version is not None
                    or workload_id is not None or environment_id is not None
                    or require_nonexpanding_input is not False):
                raise ValueError("runtime_policy_composition_conflict")
            runtime_policy.__post_init__()
            if runtime_resources is None:
                runtime_resources = RuntimeResources()
            if type(runtime_resources) is not RuntimeResources:
                raise ValueError("typed_runtime_resources_required")
            resolved = runtime_resources.resolve(runtime_policy)
            backend, policy = runtime_policy.backend, runtime_policy.request_policy
            ponytail, headroom_options = resolved["ponytail"], resolved["headroom_options"]
            require_nonexpanding_input = runtime_policy.require_nonexpanding_input
        elif runtime_resources is not None:
            raise ValueError("unused_runtime_resources")
        self.runtime_policy, self.runtime_resources = runtime_policy, runtime_resources
        # Reject optional component regimes before filesystem/tokenizer/output I/O.
        if backend == "headroom":
            from .headroom import (
                DEFAULT_STRATEGY, DOCUMENT_STRATEGY, PREPROTECTION_STRATEGY, validate_strategy,
            )
            required = {"cache", "assets", "docker_config"}
            if (type(headroom_options) is not dict or not required <= set(headroom_options)
                    or set(headroom_options) - required - {"time_budget_seconds", "strategy"}):
                raise ValueError("explicit_headroom_assets_required")
            strategy = headroom_options.get("strategy", DEFAULT_STRATEGY)
            validate_strategy(strategy)
            if strategy in (DOCUMENT_STRATEGY, PREPROTECTION_STRATEGY) and (
                    runtime_policy is None or require_nonexpanding_input is not True):
                raise ValueError("document_strategy_requires_guarded_runtime_policy")
            if strategy == PREPROTECTION_STRATEGY and (
                    runtime_policy.headroom_strategy != PREPROTECTION_STRATEGY
                    or runtime_policy.headroom_structure_guard != "document-structure-v1"):
                raise ValueError("preprotection_requires_typed_structure_guard")
            if "time_budget_seconds" in headroom_options:
                from .headroom import validate_time_budget_seconds
                validate_time_budget_seconds(headroom_options["time_budget_seconds"])
        elif headroom_options is not None:
            raise ValueError("unused_headroom_configuration")
        self._headroom_strategy = (headroom_options.get("strategy", "upstream-default-v1")
                                   if headroom_options is not None else "upstream-default-v1")
        self._headroom_root_reference_style = (
            runtime_policy.headroom_root_reference_style if runtime_policy is not None
            else "annotated-v1")
        self._headroom_structure_guard = (
            runtime_policy.headroom_structure_guard if runtime_policy is not None else "none")
        self.workspace, self.output = safe_root(workspace), safe_root(output)
        if (not self.workspace.is_dir() or self.output.is_relative_to(self.workspace)
                or type(session_id) is not str
                or re.fullmatch(r"[A-Za-z0-9._-]{1,128}", session_id) is None):
            raise ValueError("explicit_private_session_scope_required")
        if (backend not in ("none", "local", "headroom")
                or type(max_calls) is not int or not 1 <= max_calls <= 4096
                or type(harness_id) is not str or not harness_id.strip()
                or phase not in ("deployment", "learning")
                or (phase == "learning" and not learning_run_id)
                or (phase == "deployment" and learning_run_id is not None)):
            raise ValueError("invalid_runtime_configuration")
        if type(require_nonexpanding_input) is not bool:
            raise ValueError("invalid_nonexpanding_input")
        if require_nonexpanding_input and optimizer is not None:
            # Registry certificates currently bind the existing selection regime,
            # not this additional whole-composition fallback behavior.
            raise ValueError("nonexpanding_input_optimizer_selection_unsupported")
        if task_id is not None and (
                type(task_id) is not str or re.fullmatch(r"[A-Za-z0-9._:-]{1,256}", task_id) is None):
            raise ValueError("invalid_reserved_task_identity")
        if (not callable(getattr(transport, "encode", None))
                or not callable(getattr(transport, "send", None))
                or type(getattr(transport, "model", None)) is not str
                or not transport.model.strip()
                or type(getattr(transport, "max_request_bytes", None)) is not int
                or transport.max_request_bytes <= 0):
            raise ValueError("explicit_final_wire_transport_required")
        if mode is not None:
            if (not isinstance(mode, ModeStatus) or mode.reason == "invalid_state"
                    or (mode.scope == "session" and mode.session_id != session_id)):
                raise ValueError("invalid_or_foreign_task_mode")
            render_task_mode(mode)
        if ponytail is not None:
            from .ponytail import PonytailInstructions
            if not isinstance(ponytail, PonytailInstructions):
                raise ValueError("verified_ponytail_export_required")
            ponytail.__post_init__()
            if mode is not None and mode.enabled:
                raise ValueError("choose_one_instruction_component")
        self.measurement = reference_measurement()
        self._selection = None
        if optimizer is not None:
            if type(optimizer) is not Optimizer or policy is not None or backend != "local":
                raise ValueError("invalid_optimizer_selection")
            policy = optimizer.deployment_policy(
                expected_version=optimizer_version, model_id=transport.model,
                workload_id=workload_id, environment_id=environment_id,
                measurement=self.measurement)
            self._selection = {"source": "validated_registry", "config_id": optimizer.config.identity,
                               "version": optimizer_version, "policy_id": policy.policy_id}
        elif optimizer_version is not None or workload_id is not None or environment_id is not None:
            raise ValueError("unused_optimizer_configuration")
        if policy is None:
            policy = RequestPolicy(version="request-policy-v3", enabled=backend == "local",
                                   min_tool_chars=512)
        if (type(policy) is not RequestPolicy or (backend != "local" and policy.enabled)
                or (backend == "local" and not policy.enabled)):
            raise ValueError("choose_one_transform_backend")
        if backend == "local" and policy.version in NONEXPANDING_VERSIONS:
            # V4/V5/V6's contract includes every wrapper/recovery/guidance token.
            # Neither a raw-policy caller nor a registry selection can turn
            # that versioned guarantee off with the legacy optional flag. V6
            # measures every call too, but keeps its per-message shaping when
            # only the whole request's token count is not smaller (see _prepare).
            require_nonexpanding_input = True
        self.policy, self.mode, self.ponytail = policy, mode, ponytail
        self.require_nonexpanding_input = require_nonexpanding_input
        self.backend, self.transport = backend, transport
        self.session_id, self.run_id = session_id, uuid.uuid4().hex
        self.task_id = self.run_id if task_id is None else task_id
        self.phase, self.learning_run_id = phase, learning_run_id
        self.harness_id, self.max_calls = harness_id, max_calls
        self._source_reads: dict[str, SourceReadInfo] = {}
        self._tool_ids: set[str] = set()
        self._tool_events: list[dict[str, Any]] = []
        self._tool_journal_complete = True
        self._previous_messages: list[dict[str, Any]] = []
        self._records: list[CallRecord] = []
        self._expected: list[str] = []
        self._missing: list[dict[str, Any]] = []
        self._usages: list[dict[str, int] | None] = []
        self._attempts = self._transformed = 0
        self._headroom: HeadroomContainer | None = None
        self._headroom_ready: dict[str, Any] | None = None
        self._component_error: dict[str, str] | None = None
        self._headroom_options = deepcopy(headroom_options)
        self._final: dict[str, Any] | None = None
        self._cleanup: dict[str, Any] | None = None
        self._cleanup_attempts = 0
        self._cleanup_persisted = False
        self._closed, self._finished = False, False
        self._interrupted = False
        self._lock = Lock()
        self.ledger = TokenLedger(self.measurement)
        self._transport_declaration = self._transport_config()
        self._profile = {
            "version": RUNTIME_VERSION, "backend": backend, "policy": policy.to_dict(),
            "mode": mode.to_dict() if mode else None,
            "ponytail": ponytail.to_dict() if ponytail else None,
            "optimizer_selection": self.selection,
            "require_nonexpanding_input": self.require_nonexpanding_input,
            "model": transport.model, "harness_id": harness_id,
            "transport_declaration": self._transport_declaration,
            "headroom_protection": "source-root-verbatim-fences-v2" if backend == "headroom" else None,
        }
        if self.require_nonexpanding_input:
            self._profile["composition_guard_version"] = "optional-guidance-selection-v1"
            if backend == "headroom":
                self._profile["headroom_admission_strategy"] = "bound-source-eligibility-before-start-v1"
        if headroom_options is not None and "time_budget_seconds" in headroom_options:
            self._profile["headroom_time_budget_seconds"] = headroom_options["time_budget_seconds"]
        if self._headroom_strategy in ("native-documents-v1", "native-documents-structure-tags-v1"):
            self._profile["headroom_strategy"] = self._headroom_strategy
            self._profile["headroom_admission_strategy"] = "bound-native-document-eligibility-v1"
        if self._headroom_strategy == "native-documents-structure-tags-v1":
            from .document_structure import SPAN_CONTRACT
            self._profile["headroom_preprotection_contract"] = SPAN_CONTRACT
            self._profile["headroom_admission_strategy"] = "bound-parsed-native-document-spans-v1"
        if self._headroom_root_reference_style != "annotated-v1":
            self._profile["headroom_root_reference_style"] = self._headroom_root_reference_style
        if self._headroom_structure_guard != "none":
            self._profile["headroom_structure_guard"] = self._headroom_structure_guard
        if backend == "local" and policy.version == "request-policy-v4":
            self._profile["json_projection_contract"] = "lexical-json-whitespace-with-root-footer-v1"
        if backend == "local" and policy.version == "request-policy-v5":
            self._profile["v5_projection_contract"] = "multi-format-compact-root-v1"
        if backend == "local" and policy.version == "request-policy-v6":
            self._profile["v6_projection_contract"] = "cache-native-content-deterministic-v1"
        if runtime_policy is not None:
            self._profile["runtime_policy"] = runtime_policy.to_dict()
            self._profile["runtime_resources_id"] = runtime_resources.identity
        self.profile_id = RUNTIME_VERSION + ":" + _digest(self.profile)
        # Optimizer certificates bind the actual RequestPolicy ID. The wider
        # runtime composition is separately frozen as part of its environment.
        self.policy_id = (runtime_policy.policy_id if runtime_policy is not None else
                          policy.policy_id if backend == "local" else self.profile_id)
        self.output.mkdir(parents=True, exist_ok=False)
        self.ccr = CCR(self.output / "recovery.sqlite", workspace_root=self.workspace,
                       session_id=session_id)
        _write_new(self.output / "session.json", {
            "task_id": self.task_id, "run_id": self.run_id, "session_id": session_id, "profile": self.profile,
            "policy_id": self.policy_id, "profile_id": self.profile_id,
            "measurement": asdict(self.measurement),
            "phase": phase, "learning_run_id": learning_run_id,
            "max_calls": max_calls, "quality_source": "external_evaluator_only",
        })

    @property
    def source_reads(self):
        return MappingProxyType(dict(self._source_reads))

    @property
    def profile(self):
        return deepcopy(self._profile)

    @property
    def selection(self):
        return deepcopy(self._selection)

    def _transport_config(self):
        return {key: getattr(self.transport, key, None) for key in (
            "model", "max_request_bytes", "max_output_tokens", "base_url", "reasoning_effort")}

    def _open(self):
        if self._closed or self._finished:
            raise ValueError("runtime_session_closed")
        if self._interrupted:
            raise ValueError("runtime_session_interrupted")
        if self._transport_config() != self._transport_declaration:
            raise ValueError("transport_configuration_changed")
        if self.runtime_policy is not None:
            try:
                if (self.runtime_policy.to_dict() != self._profile["runtime_policy"]
                        or self.runtime_resources.identity != self._profile["runtime_resources_id"]):
                    raise ValueError("runtime_policy_configuration_changed")
                self.runtime_resources.resolve(self.runtime_policy)
            except BaseException as error:
                self._component_error = {"phase": "runtime_resources", "error_type": type(error).__name__}
                raise

    def prepare_components(self):
        """Explicit learning readiness; no primary call, no disposable worker.

        Evaluators can ready BOTH arms before dispatch. Ordinary invoke keeps
        its eligibility-based lazy behavior. Local neural work is retained in
        this same session's receipts and is never asserted free.
        """
        return self._exclusive(self._prepare_components)

    def _prepare_components(self):
        self._open()
        try:
            if self.runtime_resources is not None:
                self.runtime_resources.validate(self.runtime_policy)
            if self.backend == "headroom":
                self._start_headroom()
        except BaseException as error:
            if self._component_error is None:
                self._component_error = {"phase": "component_readiness", "error_type": type(error).__name__}
            raise
        return {"backend": self.backend, "policy_id": self.policy_id,
                "headroom_executed": self._headroom_ready is not None,
                "primary_calls": len(self._expected)}

    def _exclusive(self, operation, *args, **kwargs):
        if not self._lock.acquire(blocking=False):
            raise ValueError("runtime_operation_in_progress")
        try:
            return operation(*args, **kwargs)
        except BaseException as error:
            if not isinstance(error, Exception):
                self._interrupted = True
            raise
        finally:
            self._lock.release()

    def observe_source_read(self, info):
        """Trusted executor sideband, never parsed out of model/request text."""
        return self._exclusive(self._observe_source_read, info)

    def _observe_source_read(self, info):
        self._open()
        if type(info) is not SourceReadInfo:
            raise ValueError("typed_executor_receipt_required")
        SourceReadInfo.from_dict(info.to_dict())
        old = self._source_reads.get(info.call_id)
        if old is not None and old != info:
            raise ValueError("conflicting_executor_receipt")
        if old is None:
            append_receipt(self.output / "source-reads.jsonl", info.to_dict())
            self._source_reads[info.call_id] = info

    def execute_tool(self, call, executor):
        """Wrap host-authorized execution; do not grant permissions or run shell."""
        return self._exclusive(self._execute_tool, call, executor)

    def _tool_receipt(self, value):
        try:
            append_receipt(self.output / "tools.jsonl", value)
        except BaseException:
            self._tool_journal_complete = False
            raise

    def _execute_tool(self, call, executor):
        self._open()
        if (type(call) is not dict or set(call) != {"id", "type", "function"}
                or call["type"] != "function" or type(call["id"]) is not str
                or not call["id"] or call["id"] in self._tool_ids
                or type(call["function"]) is not dict
                or set(call["function"]) != {"name", "arguments"}
                or type(call["function"]["name"]) is not str or not call["function"]["name"].strip()
                or not callable(executor)):
            raise ValueError("invalid_or_repeated_tool_execution")
        name, call_id = call["function"]["name"], call["id"]
        arguments = parse_json(call["function"]["arguments"])
        if type(arguments) is not dict:
            raise ValueError("invalid_tool_arguments")
        self._tool_ids.add(call_id)
        event = {"call_id": call_id, "name": name, "status": "pending", "executed": False}
        self._tool_events.append(event)
        try:
            self._tool_receipt({
                "call_id": call_id, "name": name, "state": "pending",
                "arguments_sha256": _digest(arguments)})
            event["executed"] = True
            result = (self._recover_content(name, arguments, call_id)
                      if name in ("retrieve_original", "headroom_retrieve")
                      else executor(name, deepcopy(arguments)))
            content = result.content if type(result) is ExecutedToolResult else result
            if type(content) is not str:
                raise ValueError("text_tool_result_required")
            content.encode("utf-8")
            status = result.status if type(result) is ExecutedToolResult else "unknown"
            if name in QUALIFIED_SOURCE_TOOLS and status != "unknown":
                paths = [arguments[k] for k in ("path", "file_path", "filePath") if k in arguments]
                if len(paths) == 1:
                    self._observe_source_read(SourceReadInfo.from_text(
                        call_id=call_id, tool_name=name, source_path=paths[0],
                        content=content, status=status))
            event["status"] = status
            self._tool_receipt({
                "call_id": call_id, "name": name, "state": "returned",
                "status": status, "content_sha256": _digest(content)})
            return content
        except BaseException as error:
            if not isinstance(error, Exception):
                self._interrupted = True
            if event["status"] == "pending":
                event["status"] = "error"
            event["wrapper_error_type"] = type(error).__name__
            try:
                self._tool_receipt({
                    "call_id": call_id, "name": name, "state": "failed",
                    "error_type": type(error).__name__, "executed": event["executed"]})
            except BaseException:
                pass  # Poisoned journal state is retained; never retry the operation.
            raise

    def _start_headroom(self):
        if self._component_error is not None:
            raise ValueError("headroom_component_unavailable")
        if self._headroom is not None:
            return
        from .headroom import HeadroomContainer
        try:
            options = deepcopy(self._headroom_options)
            if options["docker_config"] is None:
                configuration = self.output / "docker-config"
                configuration.mkdir()
                _write_new(configuration / "config.json", {})
                options["docker_config"] = configuration
            self._headroom = HeadroomContainer(
                self.output / "headroom", **options, label="runtime-" + self.run_id)
            self._headroom_ready = self._headroom.start()
            _write_new(self.output / "headroom-component.json", self._headroom_ready)
        except BaseException as error:
            if not isinstance(error, Exception):
                self._interrupted = True
            self._component_error = {"phase": "headroom_start", "error_type": type(error).__name__}
            raise

    @staticmethod
    def recovery_tools():
        """Common schemas callers may include in both control and treatment."""
        return deepcopy(_RECOVERY_TOOLS)

    def _augment(self, original):
        request = deepcopy(original)
        guidance = self.ponytail.text if self.ponytail else (
            render_task_mode(self.mode) if self.mode else "")
        insertion = None
        if guidance:
            insertion = next((i for i, m in enumerate(request["messages"]) if m["role"] == "user"), None)
            if insertion is None:
                raise ValueError("task_message_required_for_guidance")
            request["messages"].insert(insertion, {
                "role": "user", "content":
                "Optional execution guidance; the user's actual task and requested depth take precedence.\n"
                + guidance})
        # Headroom's pipeline owns fragment references. The runtime also exposes
        # exact whole-root recovery for every accepted changed source result.
        # V6 hides nothing (lossless folds; digests name their own fetch path), so it
        # adds no recovery schema.
        if self.backend == "headroom":
            needed = _RECOVERY_TOOLS
        elif self.backend == "local" and self.policy.version not in ("request-policy-v3", "request-policy-v6"):
            needed = _RECOVERY_TOOLS[:1]
        else:
            needed = []
        if needed:
            tools = request.setdefault("tools", [])
            for recovery in needed:
                name = recovery["function"]["name"]
                found = [t for t in tools if t["function"]["name"] == name]
                if found and found != [recovery]:
                    raise ValueError("recovery_tool_schema_conflict")
                if not found:
                    tools.append(deepcopy(recovery))
        return request, insertion

    def _headroom_plan(
        self, request: dict[str, Any], intent: str, prefix: int,
        exact: tuple[int, ...] | list[int],
    ) -> tuple[dict[str, Any], tuple[int, ...], str]:
        if intent not in ("navigation", "overview"):
            return request, (), "headroom_intent_bypass"
        preprotected = self._headroom_strategy == "native-documents-structure-tags-v1"
        documents = self._headroom_strategy in ("native-documents-v1", "native-documents-structure-tags-v1")
        message_spans: list[dict[str, Any]] = []

        def source_candidates() -> dict[int, SourceReadInfo]:
            # Necessary conditions only: leave source content (including native
            # failure/exact text) unchanged for the real upstream pipeline.
            indices = _tool_indices(request)
            calls = {c["id"]: c for m in request["messages"] for c in m.get("tool_calls", [])}
            sources: dict[int, SourceReadInfo] = {}
            for index in indices[:-self.policy.keep_recent_tool_results]:
                old = request["messages"][index]
                if (index < prefix or index in exact or type(old.get("content")) is not str
                        or len(old["content"]) < self.policy.min_tool_chars
                        or _protected({k: v for k, v in old.items() if k != "content"}, strict_status=True)):
                    continue
                info = self._source_reads.get(old.get("tool_call_id"))
                if documents and (info is None or info.tool_name != "view"
                                  or PureWindowsPath(info.source_path).suffix.casefold()
                                  not in (".md", ".markdown", ".rst", ".txt")):
                    continue
                if (info is not None and info.status == "success"
                        and info.tool_name in QUALIFIED_SOURCE_TOOLS
                        and info.matches(old, calls.get(info.call_id))):
                    if preprotected:
                        from .document_structure import document_structure_spans
                        spans = document_structure_spans(old["content"])
                        if spans is None:
                            continue  # Unsupported syntax is not an empty safe span set.
                        message_spans.append({
                            "index": index, "content_sha256": _digest(old["content"]),
                            "spans": [span.to_dict() for span in spans],
                        })
                    sources[index] = info
            return sources

        # Opt-in admission changes cold/warm timing. Its profile pin deliberately
        # differs from legacy; no startup, prepare, or recovery claims on a skip.
        eligible_sources = source_candidates() if self.require_nonexpanding_input else None
        if eligible_sources == {}:
            return request, (), "headroom_no_eligible_sources"
        if preprotected:
            from .headroom_worker import MAX_PREPROTECTION_SPANS
            if sum(len(entry["spans"]) for entry in message_spans) > MAX_PREPROTECTION_SPANS:
                return request, (), "headroom_preprotection_span_bound_bypass"
        self._start_headroom()
        if self._headroom is None:
            raise ValueError("headroom_start_missing")
        try:
            if documents:
                if eligible_sources is None:
                    raise ValueError("document_eligibility_required_before_prepare")
                controls: dict[str, Any] = {
                    "eligible_indices": sorted(eligible_sources), "frozen_message_count": prefix,
                    "keep_recent_tool_results": self.policy.keep_recent_tool_results,
                }
                if preprotected:
                    controls["message_spans"] = message_spans
                proposed = self._headroom.prepare(deepcopy(request), **controls)
            else:
                proposed = self._headroom.prepare(deepcopy(request))
        except BaseException as error:
            if not isinstance(error, Exception):
                self._interrupted = True
            self._component_error = {"phase": "headroom_prepare", "error_type": type(error).__name__}
            raise
        if (type(proposed) is not dict or set(proposed) != {"model", "messages"}
                or proposed["model"] != request["model"]
                or type(proposed["messages"]) is not list
                or len(proposed["messages"]) != len(request["messages"])):
            self._component_error = {"phase": "headroom_projection", "error_type": "invalid_shape"}
            raise ValueError("invalid_headroom_projection")
        if eligible_sources is None:
            # Keep legacy startup/prepare ordering when admission is disabled.
            eligible_sources = source_candidates()
        if documents and any(
                old != new for i, (old, new) in enumerate(zip(request["messages"], proposed["messages"]))
                if i not in eligible_sources):
            self._component_error = {"phase": "headroom_prepare",
                                     "error_type": "protected_document_projection_changed"}
            raise ValueError("headroom_protected_document_projection_changed")
        candidate = deepcopy(request)
        changed: list[int] = []
        structure_rejected = False
        for index, (old, new) in enumerate(zip(request["messages"], proposed["messages"])):
            if old == new:
                continue
            if (type(new) is not dict or set(new) != set(old)
                    or {k: v for k, v in old.items() if k != "content"}
                    != {k: v for k, v in new.items() if k != "content"}):
                return request, (), "headroom_structure_reversion"
            if (index not in eligible_sources or type(new.get("content")) is not str
                    or len(changed) >= self.policy.max_transforms):
                # Keep this original exactly. One protected/newest result must
                # not prevent safe reductions in other, independently bound results.
                continue
            view = restore_protected_text(old["content"], new["content"])
            if view is None or view == old["content"]:
                continue
            if self._headroom_structure_guard == "document-structure-v1":
                from .document_structure import document_structure_preserved
                if not document_structure_preserved(old["content"], view):
                    structure_rejected = True
                    continue
            info = eligible_sources[index]
            root_options = ({"reference_style": self._headroom_root_reference_style}
                            if self._headroom_root_reference_style != "annotated-v1" else {})
            reference = self.ccr.stash(
                old["content"], source=info.source_path, ctype="source", kind="root", **root_options)
            if not reference or self.ccr.retrieve(reference) != old["content"]:
                return request, (), "exact_root_recovery_unavailable"
            # Prefix, rather than append: an EOF closing fence's missing final
            # newline is itself protected. Validate the ACTUAL annotated view.
            visible = reference + "\n" + view
            if not protected_text_preserved(old["content"], visible):
                continue
            candidate["messages"][index]["content"] = visible
            changed.append(index)
        return candidate, tuple(changed), (
            "headroom_with_exact_root_recovery" if changed else
            "headroom_structure_guard_reversion" if structure_rejected else "headroom_no_eligible_reduction")

    def _prepare(
        self, original: dict[str, Any], intent: str, prefix: int,
        exact: tuple[int, ...] | list[int],
    ) -> tuple[str, tuple[int, ...]]:
        _tool_indices(original)
        if original.get("model") != self.transport.model:
            raise ValueError("transport_model_mismatch")
        if (type(prefix) is not int or not 0 <= prefix <= len(original["messages"])
                or type(exact) not in (tuple, list) or any(
                    type(i) is not int or not 0 <= i < len(original["messages"]) for i in exact)):
            raise ValueError("invalid_request_protection")
        # Opt-in only: preserve legacy encode behavior when disabled. Measure the
        # complete caller-owned baseline BEFORE guidance or recovery schemas exist.
        original_wire: str | None = None
        original_tokens = 0
        if self.require_nonexpanding_input:
            original_wire = self.transport.encode(deepcopy(original))
            if type(original_wire) is not str:
                raise ValueError("complete_wire_text_required")
            original_tokens = tokens.count_tokens(original_wire)
        augmented, insertion = self._augment(original)
        mapped_prefix = prefix + (insertion is not None and insertion < prefix)
        mapped_exact = tuple(i + (insertion is not None and i >= insertion) for i in exact)
        baseline_wire = self.transport.encode(deepcopy(augmented))
        candidate, reason = augmented, "optimizer_off"
        changed: tuple[int, ...] = ()
        if self.backend == "local":
            plan = prepare_request(
                augmented, self.policy, ccr=self.ccr, intent=intent, protocol=PROTOCOL,
                stable_prefix_messages=mapped_prefix, exact_message_indices=mapped_exact,
                source_reads=tuple(self._source_reads.values()))
            candidate, changed, reason = plan.request, plan.changed_message_indices, plan.reason
        elif self.backend == "headroom":
            candidate, changed, reason = self._headroom_plan(
                augmented, intent, mapped_prefix, mapped_exact)
        wire = self.transport.encode(deepcopy(candidate)) if changed else baseline_wire
        if type(baseline_wire) is not str or type(wire) is not str:
            raise ValueError("complete_wire_text_required")
        before, after = tokens.count_tokens(baseline_wire), tokens.count_tokens(wire)
        # Retain the already validated/protected projection before the legacy
        # augmented-wire guard can discard it. No second reducer invocation.
        projection, projection_changed, projection_reason = candidate, changed, reason
        projection_metrics = _wire_metrics(wire, after) if original_wire is not None else None
        # v6 decides each message on its own (v6_shaping). Reverting it on the whole request's token
        # count would change earlier messages and miss the provider's cached prefix, so under v6 only
        # the byte check applies; a shaped v6 message never adds bytes. A guidance message is not shaping:
        # with one inserted (RuntimePolicy rejects v6 with guidance), the usual guard applies. It also
        # applies when the shaped request would exceed max_input_tokens, so the unshaped one goes out if it fits.
        cache_native = (self.backend == "local" and self.policy.version == "request-policy-v6" and insertion is None
                        and (self.policy.max_input_tokens is None or after <= self.policy.max_input_tokens))
        if changed and ((after >= before and not cache_native)
                        or len(wire.encode("utf-8")) > len(baseline_wire.encode("utf-8"))):
            candidate, wire, after, changed = augmented, baseline_wire, before, ()
            reason = "final_wire_guard_reversion"
        candidate_reason = reason
        composition_decision = "disabled"
        elided_metrics = None
        removed_guidance_index = None
        if original_wire is not None:
            if wire == original_wire:
                composition_decision = "original_unchanged"
            elif ((after < original_tokens or cache_native)
                  and len(wire.encode("utf-8")) <= len(original_wire.encode("utf-8"))):
                composition_decision = ("nonexpanding_composition" if after < original_tokens
                                        else "cache_native_composition")
            else:
                # Delete ONLY the message inserted by this _augment invocation,
                # never a matching original message or required recovery schema.
                if (projection_changed and insertion is not None
                        and insertion not in projection_changed
                        and len(projection["messages"]) == len(augmented["messages"])
                        and projection["messages"][insertion] == augmented["messages"][insertion]):
                    alternative = deepcopy(projection)
                    del alternative["messages"][insertion]
                    _tool_indices(alternative)
                    alternative_wire = self.transport.encode(deepcopy(alternative))
                    if type(alternative_wire) is not str:
                        raise ValueError("complete_wire_text_required")
                    alternative_tokens = tokens.count_tokens(alternative_wire)
                    elided_metrics = _wire_metrics(alternative_wire, alternative_tokens)
                    removed_guidance_index = insertion
                    if (alternative_tokens < original_tokens
                            and len(alternative_wire.encode("utf-8")) <= len(original_wire.encode("utf-8"))):
                        candidate, wire, after = alternative, alternative_wire, alternative_tokens
                        changed = tuple(i - (i > insertion) for i in projection_changed)
                        reason = composition_decision = "optional_guidance_elided"
                if composition_decision != "optional_guidance_elided":
                    # Atomic whole-request fallback: no guidance, schema, reference
                    # annotation, shifted index, or transform credit survives it.
                    candidate, wire, after, changed = original, original_wire, original_tokens, ()
                    reason = "input_composition_guard_reversion"
                    composition_decision = "whole_request_reversion"
        configured_instruction = ("ponytail" if self.ponytail else
                                  "local" if self.mode and self.mode.enabled else "none")
        applied_instruction = configured_instruction if (
            insertion is not None and composition_decision not in (
                "whole_request_reversion", "optional_guidance_elided")
            and (original_wire is None or wire != original_wire)) else "none"
        cap = self.policy.max_output_tokens
        if cap is not None and (type(getattr(self.transport, "max_output_tokens", None)) is not int
                                or self.transport.max_output_tokens > cap):
            raise ValueError("output_budget_not_enforced_by_transport")
        limits = [self.transport.max_request_bytes]
        if self.policy.max_wire_bytes is not None:
            limits.append(self.policy.max_wire_bytes)
        if (len(wire.encode("utf-8")) > min(limits)
                or self.policy.max_input_tokens is not None and after > self.policy.max_input_tokens):
            raise ValueError("final_request_budget_exceeded")
        append_receipt(self.output / "preparations.jsonl", {
            "attempt": self._attempts + 1, "original": original,
            "prepared": candidate, "changed_messages": list(changed), "reason": reason,
            "wire_sha256": _digest(wire), "reference_before": before, "reference_after": after,
            "instruction_component": applied_instruction,
            "instruction_component_configured": configured_instruction,
            "instruction_component_applied": applied_instruction,
            "input_composition": {
                "required_nonexpanding": self.require_nonexpanding_input,
                "decision": composition_decision, "candidate_reason": candidate_reason,
                "projection_reason": projection_reason, "candidate": projection_metrics,
                "optional_guidance_elided": elided_metrics,
                "optional_guidance_removed_index": removed_guidance_index,
                "original": _wire_metrics(original_wire, original_tokens)
                if original_wire is not None else None,
                "augmented": _wire_metrics(baseline_wire, before),
                "final": _wire_metrics(wire, after),
                "scope": "input_wire_only_not_output_calls_quality_or_all_in_savings",
            },
        })
        return wire, changed

    def invoke(self, request, *, intent="conservative", role="primary",
               stable_prefix_messages=0, exact_message_indices=(), parent_call_id=None):
        """Prepare, submit and capture one attempt. Never retry or infer quality."""
        if not self._lock.acquire(blocking=False):
            raise ValueError("concurrent_runtime_invocation")
        try:
            self._open()
            if self._attempts >= self.max_calls:
                raise ValueError("call_budget_exhausted")
            if role not in _ROLES or parent_call_id is not None and parent_call_id not in self._expected:
                raise ValueError("invalid_call_metadata")
            original = deepcopy(request)
            if (type(original) is not dict or type(original.get("messages")) is not list
                    or original["messages"][:len(self._previous_messages)] != self._previous_messages):
                raise ValueError("original_history_changed")
            wire, changed = self._prepare(
                original, intent, stable_prefix_messages, exact_message_indices)
            self._attempts += 1
            call_id = self.run_id + ":" + str(self._attempts)
            self._previous_messages = deepcopy(original["messages"])
            # Reserve unknown work BEFORE entering transport. Cancellation at
            # any point after this cannot collapse a possible submission to zero.
            self._expected.append(call_id)
            unresolved = {"call_id": call_id, "reason": "submission_unresolved"}
            self._missing.append(unresolved)
            usage_index = len(self._usages)
            self._usages.append(None)
            try:
                append_receipt(self.output / "invocations.jsonl", {
                    "call_id": call_id, "state": "pending", "wire_sha256": _digest(wire)})
            except BaseException as error:
                unresolved.update(reason="invocation_persistence_failed", error_type=type(error).__name__)
                if not isinstance(error, Exception):
                    self._interrupted = True
                raise
            interruption = None
            try:
                reply = self.transport.send(wire)
                if type(reply) is not Reply:
                    raise ValueError("invalid_transport_reply")
            except BaseException as error:
                if not isinstance(error, Exception):
                    interruption, self._interrupted = error, True
                reply = Reply(False, "transport_interrupted" if interruption else "transport_exception",
                              input_text=wire,
                              error_type=type(error).__name__)
            if reply.input_text is not None and reply.input_text != wire:
                reply = replace(reply, ok=False, complete=False, reason="wire_capture_mismatch")
            if reply.ok and (not reply.complete or reply.input_text is None or reply.output_text is None):
                reply = replace(reply, ok=False, complete=False, reason="incomplete_capture")
            submitted = reply.input_text is not None or reply.reason not in _NO_SUBMISSION
            complete_call = False
            if submitted:
                if reply.complete and reply.input_text is not None and reply.output_text is not None:
                    try:
                        record = measure_call(
                            self.measurement, tokens.count_tokens, input_text=reply.input_text,
                            output_text=reply.output_text, call_id=call_id, task_id=self.task_id,
                            attempt_id=str(self._attempts), phase=self.phase, role=role,
                            model_id=self.transport.model, harness_id=self.harness_id, coverage=COMPLETE,
                            completion_status="succeeded" if reply.ok else "failed",
                            parent_call_id=parent_call_id)
                        self._records.append(record)
                        self._usages[usage_index] = _usage(reply.output_text)
                        complete_call = True
                    except (ValueError, TypeError):
                        unresolved["reason"] = "measurement_unavailable"
                else:
                    unresolved["reason"] = reply.reason
                self._transformed += bool(changed)
            try:
                append_receipt(self.output / "captures.jsonl", {
                    "call_id": call_id, "input": reply.input_text, "output": reply.output_text,
                    "complete": reply.complete, "ok": reply.ok, "reason": reply.reason,
                    "error_type": reply.error_type, "http_status": reply.http_status,
                    "elapsed_seconds": reply.elapsed_seconds, "submitted_or_unknown": submitted})
                append_receipt(self.output / "invocations.jsonl", {"call_id": call_id, "state": "captured"})
            except BaseException as error:
                # A missing durable capture/ack cannot be repaired by claiming
                # the in-memory counters alone prove a complete inventory.
                unresolved.update(reason="capture_persistence_failed", error_type=type(error).__name__)
                if not isinstance(error, Exception):
                    self._interrupted = True
                raise
            if not submitted:
                # A durable no-submission receipt resolves the reservation.
                self._expected.remove(call_id)
                self._missing.remove(unresolved)
                self._usages.pop(usage_index)
            elif complete_call:
                self._missing.remove(unresolved)
            if interruption is not None:
                raise interruption
            return reply
        except BaseException as error:
            if not isinstance(error, Exception):
                self._interrupted = True
            raise
        finally:
            self._lock.release()

    def recover(self, name, arguments, *, tool_call_id):
        self._open()
        if type(arguments) is not dict or type(tool_call_id) is not str or not tool_call_id:
            raise ValueError("invalid_recovery_call")
        if name not in ("retrieve_original", "headroom_retrieve"):
            raise ValueError("unsupported_recovery_namespace")
        call = {"id": tool_call_id, "type": "function", "function": {
            "name": name, "arguments": json.dumps(arguments, ensure_ascii=False, allow_nan=False)}}
        return self.execute_tool(call, lambda *_: None)

    def _recover_content(self, name, arguments, tool_call_id):
        if name == "retrieve_original" and set(arguments) == {"ref", "offset"}:
            page = self.ccr.retrieve_page(arguments["ref"], arguments["offset"])
            return ExecutedToolResult(json.dumps(page, ensure_ascii=False),
                                      "success" if page["ok"] else "error")
        if name == "headroom_retrieve" and set(arguments) == {"hash"}:
            if self.backend != "headroom" or self._headroom is None:
                raise ValueError("headroom_not_active_in_session")
            if (type(arguments["hash"]) is not str or not arguments["hash"].strip()
                    or len(arguments["hash"]) > 4096):
                raise ValueError("invalid_headroom_reference")
            # The upstream string alone is not a verified complete-root result.
            return ExecutedToolResult(self._headroom.retrieve(arguments, tool_call_id), "unknown")
        raise ValueError("unsupported_recovery_namespace")

    def finish(self, *, success=None):
        """Trusted external evaluator may supply outcome; CLI leaves it ungraded."""
        return self._exclusive(self._finish, success=success)

    def _finish(self, *, success=None):
        if self._final is not None:
            if success != self._final["external_outcome_supplied"]:
                raise ValueError("sealed_outcome_changed")
            return deepcopy(self._final)
        if self._closed or success is not None and type(success) is not bool:
            raise ValueError("invalid_session_finalization")
        component: dict[str, Any] = {
            "complete": self._component_error is None and self._tool_journal_complete and not self._interrupted,
            "tool_journal_complete": self._tool_journal_complete,
            "interrupted": self._interrupted,
            "headroom_executed": self._headroom_ready is not None}
        if self._headroom_ready is not None:
            component["local_neural_inference_inventory_complete"] = (
                self._headroom_ready.get("local_inference_inventory_complete") is True)
        if self._component_error is not None:
            component["failure"] = self._component_error
        if self._headroom is not None and self._component_error is None and not self._interrupted:
            try:
                component["headroom"] = self._headroom.finish()
            except Exception as error:
                component.update(complete=False, error_type=type(error).__name__)
        trace = TaskTrace(
            self.task_id, self.policy_id, self.measurement, self.phase, tuple(self._records),
            tuple(self._expected), "partial" if self._missing else COMPLETE,
            self.learning_run_id, tuple(row["call_id"] for row in self._missing))
        complete = not self._missing
        totals = None
        accepted_outcome = success if component["complete"] else None
        if complete:
            totals = trace.totals().to_dict()
            self.ledger.record(trace, success=accepted_outcome)
        known = sum(c.reference_input_tokens + c.reference_output_tokens for c in self._records)
        usage_complete = complete and all(u is not None for u in self._usages)
        known_usage = [u for u in self._usages if u is not None]
        result = {
            "version": RUNTIME_VERSION, "task_id": self.task_id, "policy_id": self.policy_id,
            "profile_id": self.profile_id,
            "trace": asdict(trace), "trace_complete": complete, "component": component,
            "incomplete_calls": self._missing, "model_calls": len(self._expected),
            "model_calls_scope": "submitted or unresolved attempts; known unsubmitted rejections excluded",
            "attempts": self._attempts, "reference_totals": totals,
            "known_reference_subtotal": known,
            "known_gateway_subtotal": sum(u["total_tokens"] for u in known_usage),
            "gateway_reported_tokens": sum(u["total_tokens"] for u in known_usage)
            if usage_complete else None,
            "gateway_input_tokens": sum(u["input_tokens"] for u in known_usage)
            if usage_complete else None,
            "gateway_output_tokens": sum(u["output_tokens"] for u in known_usage)
            if usage_complete else None,
            "gateway_usage_complete": usage_complete, "transformations": self._transformed,
            "wrapped_tool_attempts": len(self._tool_events),
            "recovery_tool_attempts": sum(e["name"] in ("retrieve_original", "headroom_retrieve")
                                          for e in self._tool_events),
            "source_read_receipts": len(self._source_reads),
            "tool_inventory_complete": self._tool_journal_complete,
            "tool_inventory_scope": "runtime-wrapped operations only; executor receipts are separate",
            "quality_verified": accepted_outcome, "external_outcome_supplied": success,
            "ledger": self.ledger.summary(),
            "ledger_contains_complete_traces_only": True,
            "scope": "Observed complete API bodies; hidden upstream calls/compute not asserted zero.",
            "policy_promoted": False,
            "all_in_compute_savings": None,
            "local_neural_work": "Reported separately in Headroom receipts; not assumed free or fully inventoried."
                if self._headroom_ready is not None else "No local neural component invoked by this runtime.",
        }
        _write_new(self.output / "result.json", result)
        self._finished, self._final = True, result
        return deepcopy(result)

    def close(self):
        return self._exclusive(self._close)

    @property
    def cleanup_settled(self):
        """Closed plus a successfully persisted complete cleanup receipt."""
        return bool(self._closed and self._cleanup_persisted
                    and self._cleanup is not None and self._cleanup.get("complete") is True)

    def _close(self):
        if self.cleanup_settled or self._closed and self._cleanup_attempts >= 2:
            return deepcopy(self._cleanup)
        previously_closed = self._closed
        self._cleanup_attempts += 1
        self._cleanup_persisted = False
        cleanup: dict[str, Any] = {"complete": True}
        if self._cleanup_attempts > 1:
            cleanup["cleanup_attempt"] = self._cleanup_attempts
        error: BaseException | None = None

        def remember(failure):
            nonlocal error
            if error is None or isinstance(error, Exception) and not isinstance(failure, Exception):
                error = failure
            if not isinstance(failure, Exception):
                self._interrupted = True
                cleanup["interrupted"] = True

        try:
            # A cleanup-only retry must never repeat a component audit/model
            # operation, even when earlier finalization did not persist.
            if not previously_closed and not self._finished:
                self._finish()
        except BaseException as failure:
            remember(failure)
            cleanup["finalization_error_type"] = type(failure).__name__
        finally:
            try:
                if self._headroom is not None:
                    cleanup["headroom"] = self._headroom.close()
                    receipt = cleanup["headroom"]
                    if (receipt.get("complete") is False
                            or receipt.get("container_id") is not None and receipt.get("container_removed") is not True):
                        raise RuntimeError("headroom_cleanup_unconfirmed")
            except BaseException as failure:
                remember(failure)
                cleanup.update(complete=False, headroom_error_type=type(failure).__name__)
            try:
                if (self.output / "recovery.sqlite").exists():
                    cleanup["released_leases"] = self.ccr.release_session()
                    # release_session's compatibility API returns zero on a
                    # storage error as well as on an empty scope. Confirm this
                    # session only; never release another session's leases.
                    with self.ccr._connect() as connection:
                        remaining = connection.execute(
                            "SELECT COUNT(*) FROM ccr_leases WHERE scope=? AND session=?",
                            (self.ccr._scope_key, self.ccr._session_key(None))).fetchone()[0]
                    cleanup["remaining_session_leases"] = remaining
                    if remaining != 0:
                        raise RuntimeError("recovery_lease_release_unconfirmed")
            except BaseException as failure:
                remember(failure)
                cleanup.update(complete=False, recovery_error_type=type(failure).__name__)
            finally:
                self._closed, self._cleanup = True, cleanup
                name = "cleanup.json" if self._cleanup_attempts == 1 \
                    else f"cleanup-retry-{self._cleanup_attempts}.json"
                try:
                    _write_new(self.output / name, cleanup)
                    self._cleanup_persisted = True
                except BaseException as failure:
                    remember(failure)
                    cleanup.update(complete=False, receipt_error_type=type(failure).__name__)
                    # Preserve an interrupted/partial first file; never overwrite
                    # it or suppress the original interruption to manufacture a pass.
                    try:
                        _write_new(self.output / f"cleanup-unconfirmed-{self._cleanup_attempts}.json", cleanup)
                        self._cleanup_persisted = True
                    except BaseException as receipt_failure:
                        remember(receipt_failure)
        if error is not None:
            raise error
        return deepcopy(cleanup)
