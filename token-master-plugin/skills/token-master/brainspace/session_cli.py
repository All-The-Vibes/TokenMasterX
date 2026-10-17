"""Bounded JSONL control channel for an explicitly opted-in RuntimeSession.

The input stream MUST belong to the trusted host/executor. Never pipe model
output into it: observe-read is executor sideband, not a model-call tool.
Frames are newline-terminated UTF-8 JSON objects, at most 1 MiB including LF:
  {"op":"call","request":CHAT, "intent":..., "role":...,
   "stable_prefix_messages":0, "exact_message_indices":[]}
  {"op":"observe-read","receipt":SOURCE_READ_INFO}
  {"op":"recover","name":..., "args":{...}, "tool_call_id":...}
  {"op":"finish"}
Unknown fields/operations abort the protocol. Finish accepts no quality verdict.
Exit 0 means protocol, reference accounting and cleanup completed, NOT that an
answer is correct or even that all HTTP calls succeeded. Exit 2 is a protocol/
configuration error; exit 3 is incomplete final accounting/component/cleanup.
"""
from __future__ import annotations

import json
import sys

from .optimizer import Optimizer
from .ponytail import load_ponytail_export
from .request_policy import RequestPolicy, SourceReadInfo
from .runtime import RuntimeSession
from .runtime_io import parse_json, safe_root
from .task_mode import TaskContract, TaskModeStore, task_local_mode
from .transport import ResponsesTransport


MAX_FRAME_BYTES = 1_048_576
MAX_FRAMES = 4096
_INTENTS = {"conservative", "navigation", "overview", "aggregate", "edit", "debug", "task", "exact"}
_ROLES = {"primary", "auxiliary", "verification", "recovery", "retry"}


class ProtocolError(ValueError):
    """Only fixed, input-independent reason codes may be exposed."""


def _require(condition, reason):
    if not condition:
        raise ProtocolError(reason)


def _local_json(path):
    source = safe_root(path)
    _require(source.is_file(), "configuration_file_required")
    with source.open("rb") as stream:
        raw = stream.read(MAX_FRAME_BYTES + 1)
    _require(len(raw) <= MAX_FRAME_BYTES, "configuration_too_large")
    return parse_json(raw.decode("utf-8"))


def _session(args):
    # This gate precedes registry access, recovery initialization and mkdir.
    _require(args.allow_network is True, "explicit_network_opt_in_required")
    profile_path = getattr(args, "runtime_policy", None)
    profile_mode = args.backend == "profile"
    _require(profile_mode == (profile_path is not None), "explicit_profile_selection_required")
    time_budget_seconds = getattr(args, "headroom_time_budget_seconds", None)
    if time_budget_seconds is not None:
        _require(args.backend == "headroom", "unused_headroom_configuration")
        _require(type(time_budget_seconds) is int and 1 <= time_budget_seconds <= 60,
                 "invalid_headroom_time_budget_seconds")
    require_nonexpanding_input = getattr(args, "require_nonexpanding_input", False)
    _require(type(require_nonexpanding_input) is bool, "invalid_nonexpanding_input")
    _require(not (require_nonexpanding_input and args.optimizer_db is not None),
             "nonexpanding_input_optimizer_selection_unsupported")
    _require(args.session is not None, "explicit_session_required")
    _require(type(args.max_frames) is int and 1 <= args.max_frames <= MAX_FRAMES,
             "invalid_frame_limit")
    _require(type(args.max_calls) is int and 1 <= args.max_calls <= 4096, "invalid_call_limit")
    _require((args.phase == "learning" and type(args.learning_run_id) is str
              and bool(args.learning_run_id.strip()))
             or (args.phase == "deployment" and args.learning_run_id is None),
             "invalid_learning_scope")
    workspace, output = safe_root(args.workspace), safe_root(args.output)
    _require(workspace.is_dir() and not output.exists(), "new_private_output_required")
    if profile_mode:
        from .runtime_policy import RuntimePolicy
        from .runtime_resources import RuntimeResources
        _require(args.policy is None and args.optimizer_db is None and args.optimizer_version is None
                 and args.workload_id is None and args.environment_id is None
                 and args.contract is None and not args.use_session_mode
                 and require_nonexpanding_input is False and time_budget_seconds is None
                 and args.headroom_docker_config is None, "profile_owns_composition")
        selected = RuntimePolicy.from_dict(_local_json(profile_path))
        resources = RuntimeResources(
            ponytail_export=args.ponytail_export, headroom_cache=args.headroom_cache,
            headroom_assets=args.headroom_assets)
        transport = ResponsesTransport(
            base_url=args.base_url, model=args.model, allow_network=True,
            reasoning_effort=args.reasoning_effort, timeout=args.timeout,
            max_output_tokens=args.max_output_tokens, max_request_bytes=args.max_request_bytes,
            max_response_bytes=args.max_response_bytes)
        return RuntimeSession(
            workspace=workspace, session_id=args.session, output=output, transport=transport,
            runtime_policy=selected, runtime_resources=resources,
            max_calls=args.max_calls, phase=args.phase, learning_run_id=args.learning_run_id,
            task_id=getattr(args, "task_id", None))
    options = None
    if args.backend == "headroom":
        _require(args.headroom_cache is not None and args.headroom_assets is not None,
                 "explicit_headroom_assets_required")
        cache, assets = safe_root(args.headroom_cache), safe_root(args.headroom_assets)
        _require(cache.is_dir() and assets.is_file(), "headroom_assets_unavailable")
        config = safe_root(args.headroom_docker_config) if args.headroom_docker_config else None
        if config is not None:
            _require(_local_json(config / "config.json") == {}, "empty_docker_config_required")
        options = {"cache": cache, "assets": assets, "docker_config": config}
        if time_budget_seconds is not None:
            options["time_budget_seconds"] = time_budget_seconds
    else:
        _require(all(v is None for v in (
            args.headroom_cache, args.headroom_assets, args.headroom_docker_config,
        )), "unused_headroom_configuration")
    regime = (args.optimizer_version, args.workload_id, args.environment_id)
    if args.optimizer_db is not None:
        _require(args.backend == "local" and args.policy is None
                 and type(args.optimizer_version) is int and args.optimizer_version > 0
                 and all(type(v) is str and v.strip() for v in regime[1:]),
                 "explicit_optimizer_regime_required")
    else:
        _require(all(v is None for v in regime), "unused_optimizer_configuration")
    policy = None
    if args.policy is not None:
        _require(len(args.policy.encode("utf-8")) <= MAX_FRAME_BYTES, "policy_too_large")
        policy = RequestPolicy.from_dict(parse_json(args.policy))
    mode = None
    if args.contract is not None:
        mode = task_local_mode(TaskContract.from_dict(_local_json(args.contract)))
    elif args.use_session_mode:
        mode = TaskModeStore(safe_root(workspace / ".token-master")).status(args.session)
    ponytail = load_ponytail_export(safe_root(args.ponytail_export)) if args.ponytail_export else None
    transport = ResponsesTransport(
        base_url=args.base_url, model=args.model, allow_network=True,
        reasoning_effort=args.reasoning_effort, timeout=args.timeout,
        max_output_tokens=args.max_output_tokens, max_request_bytes=args.max_request_bytes,
        max_response_bytes=args.max_response_bytes,
    )
    optimizer = Optimizer.open(safe_root(args.optimizer_db)) if args.optimizer_db else None
    return RuntimeSession(
        workspace=workspace, session_id=args.session, output=output, transport=transport,
        backend=args.backend, policy=policy, mode=mode, ponytail=ponytail,
        headroom_options=options, max_calls=args.max_calls, phase=args.phase,
        learning_run_id=args.learning_run_id, optimizer=optimizer,
        optimizer_version=args.optimizer_version, workload_id=args.workload_id,
        environment_id=args.environment_id, task_id=getattr(args, "task_id", None),
        require_nonexpanding_input=require_nonexpanding_input,
    )


def _frame(raw):
    _require(len(raw) <= MAX_FRAME_BYTES, "frame_too_large")
    _require(raw.endswith(b"\n"), "unterminated_frame")
    try:
        value = parse_json(raw.decode("utf-8"))
        # Reject escaped lone surrogates too, before invoking runtime methods.
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ProtocolError("invalid_json_frame") from None
    _require(type(value) is dict and type(value.get("op")) is str, "invalid_operation")
    schemas = {
        "call": ({"op", "request"}, {"intent", "role", "stable_prefix_messages", "exact_message_indices"}),
        "observe-read": ({"op", "receipt"}, set()),
        "recover": ({"op", "name", "args", "tool_call_id"}, set()),
        "finish": ({"op"}, set()),
    }
    _require(value["op"] in schemas, "unknown_operation")
    required, optional = schemas[value["op"]]
    _require(required <= value.keys() and value.keys() <= required | optional, "invalid_operation_fields")
    if value["op"] == "call":
        _require(type(value["request"]) is dict, "invalid_call_request")
        _require(type(value.get("intent", "conservative")) is str
                 and value.get("intent", "conservative") in _INTENTS, "invalid_intent")
        _require(type(value.get("role", "primary")) is str
                 and value.get("role", "primary") in _ROLES, "invalid_role")
        prefix, exact = value.get("stable_prefix_messages", 0), value.get("exact_message_indices", [])
        _require(type(prefix) is int and prefix >= 0 and type(exact) is list
                 and all(type(i) is int and i >= 0 for i in exact), "invalid_protection_indices")
    elif value["op"] == "observe-read":
        _require(type(value["receipt"]) is dict, "invalid_receipt")
    elif value["op"] == "recover":
        _require(type(value["name"]) is str and type(value["args"]) is dict
                 and type(value["tool_call_id"]) is str and value["tool_call_id"].strip(),
                 "invalid_recovery_request")
        allowed = {"retrieve_original": {"ref", "offset"}, "headroom_retrieve": {"hash"}}
        _require(value["name"] in allowed and set(value["args"]) == allowed[value["name"]],
                 "invalid_recovery_namespace")
        args = value["args"]
        if value["name"] == "retrieve_original":
            _require(type(args["ref"]) is str and type(args["offset"]) is int and args["offset"] >= 0,
                     "invalid_recovery_arguments")
        else:
            _require(type(args["hash"]) is str, "invalid_recovery_arguments")
    return value


def run_session(args, *, input_stream=None, output_stream=None):
    """Run one bounded trusted JSONL session; binary streams support embedding/tests."""
    incoming = sys.stdin.buffer if input_stream is None else input_stream
    outgoing = sys.stdout.buffer if output_stream is None else output_stream

    def emit(value):
        outgoing.write((json.dumps(value, ensure_ascii=True, allow_nan=False,
                                   separators=(",", ":")) + "\n").encode("utf-8"))
        outgoing.flush()

    try:
        session = _session(args)
    except Exception as error:
        code = str(error) if type(error) is ProtocolError else "session_setup_failed"
        emit({"op": "error", "ok": False, "error": code})
        return 2
    protocol_error = None
    finished = False
    result, cleanup = None, None
    try:
        for _ in range(args.max_frames):
            raw = incoming.readline(MAX_FRAME_BYTES + 1)
            _require(bool(raw), "finish_required")
            value = _frame(raw)
            operation = value["op"]
            if operation == "finish":
                finished = True
                break
            if operation == "call":
                reply = session.invoke(
                    value["request"], intent=value.get("intent", "conservative"),
                    role=value.get("role", "primary"),
                    stable_prefix_messages=value.get("stable_prefix_messages", 0),
                    exact_message_indices=tuple(value.get("exact_message_indices", [])),
                )
                # Never dispatch response tools or consume receipts from model text.
                emit({"op": operation, "ok": reply.ok, "reason": reply.reason,
                      "complete": reply.complete, "http_status": reply.http_status,
                      "body": reply.body if reply.ok else None})
            elif operation == "observe-read":
                session.observe_source_read(SourceReadInfo.from_dict(value["receipt"]))
                emit({"op": operation, "ok": True})
            else:
                content = session.recover(value["name"], value["args"], tool_call_id=value["tool_call_id"])
                emit({"op": operation, "ok": True, "content": content})
        _require(finished, "frame_limit_exceeded")
    except (Exception, KeyboardInterrupt) as error:
        protocol_error = str(error) if type(error) is ProtocolError else "operation_failed"
        try:
            emit({"op": "error", "ok": False, "error": protocol_error})
        except OSError:
            pass
    finally:
        try:
            result = session.finish()  # Never forward a success/quality argument.
        except Exception:
            result = None
        finally:
            try:
                cleanup = session.close()
            except Exception:
                cleanup = {"complete": False}
    accounted = (
        type(result) is dict and result.get("trace_complete") is True
        and result.get("component", {}).get("complete") is True
        and type(cleanup) is dict and cleanup.get("complete") is True
    )
    exit_code = 2 if protocol_error else (0 if accounted else 3)
    try:
        emit({"op": "finish", "ok": exit_code == 0, "protocol_complete": finished and not protocol_error,
              "result": result, "cleanup": cleanup})
    except OSError:
        return 2
    return exit_code
