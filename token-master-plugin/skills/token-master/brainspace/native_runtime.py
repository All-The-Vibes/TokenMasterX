"""One native client, one real RuntimeSession, registered recovery and accounting.

This is a trusted-host adapter, not an arbitrary tool executor or quality oracle.
Only native stdout from the owned CLI may enter observe_event(). The HTTP layer
uses separate task-local authentication for inference and recovery, never provider
credentials. All actual upstream submissions still go through RuntimeSession.
"""
from __future__ import annotations

from copy import deepcopy
from concurrent.futures import Future, TimeoutError as FutureTimeout
from dataclasses import replace
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from queue import Empty, Full, Queue
import secrets
from threading import Condition, Event, Lock, Thread
import time
from urllib.parse import urlsplit
from typing import Any

from .native_events import DEFAULT_SOURCE_CONTRACT, NativeEventCollector, validate_source_contract
from .native_transport import NativeResponsesTransport
from .runtime import RuntimeSession
from .runtime_io import append_receipt, parse_json, safe_root
from .runtime_policy import RuntimePolicy
from .runtime_resources import RuntimeResources


VERSION = "copilot-native-runtime-v1"
RANGED_VERSION = "copilot-native-runtime-view-result-v2"
RECOVERY_ALIASES = {
    "retrieve_original": "tokenmaster-retrieve_original",
    "headroom_retrieve": "tokenmaster-headroom_retrieve",
}


def _wire(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":"))


def _require(condition, code):
    if not condition:
        raise ValueError(code)


class NativeRuntime:
    def __init__(
        self, *, workspace, session_id, output, base_url, model,
        allow_network=False, policy=None, resources=None, intent="conservative",
        max_calls=64, max_output_tokens=2048, max_request_bytes=524288,
        max_response_bytes=524288, timeout=45, reasoning_effort="low",
        event_wait_seconds=5, phase="deployment", learning_run_id=None, task_id=None,
        source_contract=DEFAULT_SOURCE_CONTRACT,
    ):
        _require(allow_network is True, "explicit_network_opt_in_required")
        validate_source_contract(source_contract)
        _require(intent in ("conservative", "overview", "navigation", "exact", "edit",
                            "debug", "aggregate", "task"), "invalid_native_intent")
        _require(type(event_wait_seconds) in (int, float) and 0 <= event_wait_seconds <= 30,
                 "invalid_native_event_wait")
        self.workspace, self.output = safe_root(workspace), safe_root(output)
        _require(self.workspace.is_dir() and not self.output.exists()
                 and not self.output.is_relative_to(self.workspace), "new_private_output_required")
        self.output.mkdir(parents=True)
        self.intent, self.event_wait_seconds = intent, event_wait_seconds
        self._copilot_version = "1.0.95-0"
        self.transport = NativeResponsesTransport(
            base_url=base_url, model=model, allow_network=allow_network,
            max_output_tokens=max_output_tokens, max_request_bytes=max_request_bytes,
            max_response_bytes=max_response_bytes, timeout=timeout,
            reasoning_effort=reasoning_effort, recovery_aliases=RECOVERY_ALIASES,
            recovery_tools=RuntimeSession.recovery_tools(),
        )
        self.runtime = RuntimeSession(
            workspace=self.workspace, session_id=session_id, output=self.output / "runtime",
            transport=self.transport, runtime_policy=policy or RuntimePolicy(),
            runtime_resources=resources or RuntimeResources(), max_calls=max_calls,
            harness_id=VERSION if source_contract == DEFAULT_SOURCE_CONTRACT else RANGED_VERSION,
            phase=phase, learning_run_id=learning_run_id, task_id=task_id,
        )
        self.events = NativeEventCollector(
            workspace=self.workspace, expected_model=model,
            journal_path=self.output / "native-executor.jsonl",
            source_contract=source_contract,
        )
        self._lock = Lock()
        self._issued = {}
        self._recovery_claimed = set()
        self._ingress = self._rejections = self._delivery_failures = 0
        self._last_failure = None
        self._finished = False
        self._bootstrap = Event()
        self._bootstrap_valid = False
        self._http_lock = Lock()
        self._http_records = {}
        self._http_total = self._http_overflow = 0
        self._http_primary = self._http_control = 0
        self._http_journal_complete = True

    def observe_event(self, event):
        """Feed ONLY the native process stdout stream; never recursively parse text."""
        if type(event) is dict and event.get("type") == "session.skills_loaded":
            # Keep stock native context, but do not silently import a personal
            # catalog. The exact builtin names and owned cache paths are checked.
            self._bootstrap_valid = self.validate_bootstrap_event(event)
            self._bootstrap.set()
        self.events.observe(event)

    def validate_bootstrap_event(self, event):
        from .native_events import validate_native_skills
        return validate_native_skills(
            event, cache_root=self.output / "native-home" / "copilot-cache",
            version=getattr(self, "_copilot_version", "1.0.95-0"),
        )

    def begin_http_request(self, route):
        """Content-free inventory BEFORE an authenticated body is parsed."""
        with self._http_lock:
            self._http_total += 1
            self._http_primary += route == "/v1/responses"
            self._http_control += route == "/control/recover"
            if len(self._http_records) >= self.runtime.max_calls * 8 + 32:
                self._http_overflow += 1
                raise ValueError("native_http_inventory_limit")
            request_id = str(self._http_total)
            self._http_records[request_id] = {
                "route": route, "dispatched": False, "handled": False,
                "rejected_before_dispatch": False, "operation_error": False,
                "state": "received",
            }
            self._http_record(request_id)
            return request_id

    def _http_record(self, request_id):
        try:
            append_receipt(self.output / "native-http.jsonl", {
                "http_request_id": request_id, **self._http_records[request_id],
                "scope": "authenticated_ingress_metadata_only_not_a_model_call",
            })
        except BaseException:
            self._http_journal_complete = False
            raise

    def note_http_state(self, request_id, state):
        with self._http_lock:
            row = self._http_records[request_id]
            if state == "dispatched":
                row["dispatched"] = True
            if state in ("rejected", "cancelled", "waiter_timeout"):
                if not row["dispatched"]:
                    row["rejected_before_dispatch"] = True
                else:
                    row["operation_error"] = True
            if state == "responded":
                row["handled"] = True
            row["state"] = state
            self._http_record(request_id)

    def http_summary(self):
        with self._http_lock:
            rows = tuple(self._http_records.values())
            return {
                "authenticated_requests": self._http_total,
                "primary_requests": self._http_primary,
                "control_requests": self._http_control,
                "dispatched": sum(row["dispatched"] for row in rows),
                "rejected_before_dispatch": sum(row["rejected_before_dispatch"] for row in rows),
                "control_operation_errors": sum(row["operation_error"]
                    and row["route"] == "/control/recover" for row in rows),
                "operation_errors": sum(row["operation_error"] for row in rows),
                "unhandled": sum(not row["handled"] for row in rows),
                "overflow": self._http_overflow,
                "journal_complete": self._http_journal_complete,
                "scope": "HTTP/control attempts; no invented token or model-call records",
            }

    def _model_calls(self, body, native):
        tools = {item["name"] for item in native.get("tools", [])
                 if type(item) is dict and item.get("type") == "function"}
        calls = []
        for item in body.get("output", []):
            if type(item) is not dict:
                raise ValueError("invalid_native_model_output")
            if item.get("type") != "function_call":
                _require(item.get("type") in ("message", "reasoning"), "unsupported_native_output_item")
                continue
            _require(item.get("name") in tools and item.get("status", "completed") == "completed"
                     and "namespace" not in item, "unregistered_native_tool_call")
            call_id = item.get("call_id")
            arguments = parse_json(item.get("arguments"))
            _require(type(arguments) is dict and type(call_id) is str and bool(call_id)
                     and call_id not in self._issued, "invalid_or_reused_native_tool_id")
            if item["name"] == "view":
                _require(set(arguments) <= {"path", "view_range", "forceReadLargeFiles"}
                         and type(arguments.get("path")) is str, "unsupported_native_view_arguments")
                lexical = Path(arguments["path"])
                _require(lexical.is_absolute() and lexical.is_relative_to(self.workspace)
                         and ".." not in lexical.parts
                         and ":" not in str(lexical).replace(lexical.drive, "", 1),
                         "native_view_outside_workspace")
                # Do not probe foreign/UNC paths while deciding authorization.
                path = safe_root(lexical)
                _require(path.is_relative_to(self.workspace), "native_view_outside_workspace")
            else:
                _require(item["name"] in RECOVERY_ALIASES.values(),
                         "native_readonly_tool_boundary")
            calls.append({"id": call_id, "type": "function", "function": {
                "name": item["name"], "arguments": item["arguments"],
            }})
        _require(len(calls) <= 1, "native_single_call_contract")
        return calls

    def _validate_history_calls(self, native):
        # Use native names, not the codec's internal recovery aliases. _issued
        # records the real response before delivery; argument formatting may
        # differ but names and strictly parsed JSON values may not.
        for item in native["input"]:
            if item.get("type") != "function_call":
                continue
            issued = self._issued.get(item["call_id"])
            if issued is None:
                raise ValueError("unobserved_preexisting_native_history")
            try:
                equal = (item["name"] == issued["function"]["name"]
                         and _wire(parse_json(item["arguments"]))
                         == _wire(parse_json(issued["function"]["arguments"])))
            except (ValueError, TypeError, RecursionError, OverflowError):
                equal = False
            _require(equal, "native_history_call_mismatch")

    def _validate_history_results(self, native):
        for item in native["input"]:
            if item.get("type") != "function_call_output":
                continue
            issued = self._issued[item["call_id"]]
            if issued["function"]["name"] == "view":
                _require(self.events.matches_view_result(item["call_id"], item["output"]),
                         "native_history_result_mismatch")

    def invoke(self, native):
        if not self._lock.acquire(blocking=False):
            raise ValueError("native_operation_in_progress")
        try:
            _require(not self._finished, "native_runtime_finished")
            _require(self._bootstrap.wait(self.event_wait_seconds) and self._bootstrap_valid,
                     "native_bootstrap_not_qualified")
            self._ingress += 1
            _require(self._ingress <= self.runtime.max_calls * 4, "native_ingress_limit")
            append_receipt(self.output / "native-ingress.jsonl", {
                "index": self._ingress, "state": "received", "request": native,
            })
            canonical = self.transport.bind(native)
            ids = tuple(message["tool_call_id"] for message in canonical["messages"]
                        if message["role"] == "tool")
            _require(all(call_id in self._issued for call_id in ids),
                     "unobserved_preexisting_native_history")
            self._validate_history_calls(native)
            _require(self.events.wait_for_completed(ids, self.event_wait_seconds),
                     "native_execution_observation_incomplete")
            self._validate_history_results(native)
            for info in self.events.source_reads(canonical):
                self.runtime.observe_source_read(info)
            fingerprint = hashlib.sha256(_wire(native).encode("utf-8")).hexdigest()
            role = "retry" if self._last_failure == fingerprint else "primary"
            reply = self.runtime.invoke(canonical, intent=self.intent, role=role)
            self._last_failure = fingerprint if not reply.ok else None
            if reply.ok:
                try:
                    calls = self._model_calls(reply.body, native)
                    self.events.register_expected_calls(calls, model=self.transport.model)
                    for call in calls:
                        self._issued[call["id"]] = deepcopy(call)
                except (ValueError, TypeError, KeyError, RecursionError):
                    # The complete upstream call is already captured/accounted.
                    # Do not forward an unsupported or unauthorized tool action.
                    self._rejections += 1
                    reply = replace(reply, ok=False, reason="native_output_rejected")
            append_receipt(self.output / "native-ingress.jsonl", {
                "index": self._ingress, "state": "handled", "ok": reply.ok,
                "reason": reply.reason, "controls": self.transport.controls,
            })
            return reply
        except BaseException as error:
            self._rejections += 1
            append_receipt(self.output / "native-ingress.jsonl", {
                "index": self._ingress, "state": "rejected", "error_type": type(error).__name__,
            })
            raise
        finally:
            self._lock.release()

    def recover(self, name, arguments):
        """The owned native MCP requests an already-issued real recovery call."""
        if not self._lock.acquire(blocking=False):
            raise ValueError("native_operation_in_progress")
        try:
            _require(not self._finished and name in RECOVERY_ALIASES
                     and type(arguments) is dict, "invalid_native_recovery")
            key = _wire(arguments)
            observed = self.events.summary()["calls"]
            matches = [
                call_id for call_id, call in self._issued.items()
                if call_id not in self._recovery_claimed
                and observed.get(call_id, {}).get("status") == "pending"
                and observed.get(call_id, {}).get("completed") is False
                and call["function"]["name"] == RECOVERY_ALIASES[name]
                and _wire(parse_json(call["function"]["arguments"])) == key
            ]
            _require(len(matches) == 1, "native_recovery_call_not_unique")
            call_id = matches[0]
            _require(self.events.wait_for_started((call_id,), self.event_wait_seconds),
                     "native_recovery_execution_not_observed")
            _require(self.events.claim_pending_call(call_id), "native_recovery_not_pending")
            self._recovery_claimed.add(call_id)
            # Actual upstream ID, not a new ID manufactured by the MCP worker.
            return self.runtime.recover(name, arguments, tool_call_id=call_id)
        finally:
            self._lock.release()

    def note_delivery_failure(self):
        self._delivery_failures += 1

    def finish(self, *, native_exit_code=None, native_io_complete=True):
        """Only after native EOF and no in-flight operation; never infer quality."""
        if not self._lock.acquire(blocking=False):
            raise ValueError("native_operation_in_progress")
        try:
            _require(not self._finished, "native_runtime_finished")
            result, cleanup, final_error, interruption = None, None, None, None
            observed: dict[str, Any] = {"coverage_complete": False, "observation_close_failed": True}
            try:
                observed = self.events.close()
            except BaseException as error:
                final_error = type(error).__name__
                observed["error_type"] = final_error
                if not isinstance(error, Exception):
                    interruption = error
            try:
                result = self.runtime.finish()
            except BaseException as error:
                final_error = final_error or type(error).__name__
                if not isinstance(error, Exception) and interruption is None:
                    interruption = error
            for _ in range(2):
                if self.runtime.cleanup_settled:
                    break
                try:
                    cleanup = self.runtime.close()
                except BaseException as error:
                    final_error = final_error or type(error).__name__
                    if not isinstance(error, Exception) and interruption is None:
                        interruption = error
            self._finished = True
            http = self.http_summary()
            http_rejections = http["rejected_before_dispatch"] + http["control_operation_errors"] \
                + http["overflow"]
            summary = {
                "version": self.runtime.harness_id, "runtime": result, "native_executor": observed,
                "native_ingress_requests": http["primary_requests"]
                    if http["authenticated_requests"] else self._ingress,
                "native_runtime_invocations": self._ingress,
                "native_rejections": self._rejections + http_rejections,
                "native_runtime_rejections": self._rejections, "native_http": http,
                "native_delivery_failures": self._delivery_failures,
                "native_exit_code": native_exit_code, "cleanup": cleanup,
                "native_io_complete": native_io_complete is True,
                "finalization_error": final_error,
                "complete": result is not None and final_error is None
                and native_io_complete is True and native_exit_code == 0 and self._rejections == 0
                and http_rejections == 0 and http["operation_errors"] == 0
                and http["unhandled"] == 0 and http["journal_complete"]
                and self._delivery_failures == 0 and observed["coverage_complete"]
                and result["trace_complete"] and result["component"]["complete"]
                and self.runtime.cleanup_settled,
                "quality_verified": None, "policy_promoted": False,
                "scope": "observed native/HTTP execution; not a quality or savings certificate",
            }
            if self.events.source_contract != DEFAULT_SOURCE_CONTRACT:
                summary["source_contract"] = self.events.source_contract
            try:
                with (self.output / "result.json").open("x", encoding="utf-8") as handle:
                    json.dump(summary, handle, ensure_ascii=False, allow_nan=False, indent=2)
                    handle.write("\n")
            except BaseException as error:
                if interruption is not None:
                    interruption.add_note("native_summary_persistence_failed:" + type(error).__name__)
                    raise interruption from None
                raise
            if interruption is not None:
                raise interruption
            return summary
        finally:
            self._lock.release()


class NativeBridge:
    """Owned loopback-only HTTP surface; credentials never enter model bodies."""
    def __init__(self, runtime: NativeRuntime):
        self.runtime = runtime
        self.primary_token = secrets.token_urlsafe(32)
        self.control_token = secrets.token_urlsafe(32)
        self._queue: Queue[tuple[str, Any, Future[Any], str]] = Queue(maxsize=32)
        self._stopping = Event()
        self._queue_cancelled = 0
        self._handler_condition = Condition()
        self._active_handlers = 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, body):
                raw = body.encode("utf-8") if type(body) is str else _wire(body).encode("utf-8")
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except OSError:
                    owner.runtime.note_delivery_failure()

            def authorized(self, token):
                value = self.headers.get("Authorization", "")
                return hmac.compare_digest(value, "Bearer " + token)

            def read_body(self):
                _require(self.headers.get("Transfer-Encoding") is None, "chunked_native_body_unsupported")
                length = self.headers.get("Content-Length")
                if not isinstance(length, str) or not length.isascii() or not length.isdecimal():
                    raise ValueError("native_content_length_required")
                size = int(length)
                _require(0 < size <= owner.runtime.transport.max_request_bytes, "native_http_body_bound")
                self.connection.settimeout(15)
                raw = self.rfile.read(size)
                _require(len(raw) == size, "incomplete_native_http_body")
                # Native credentials are HTTP/control material, never model
                # content or captured source. Reject accidental client leakage.
                _require(owner.primary_token.encode() not in raw
                         and owner.control_token.encode() not in raw,
                         "native_credential_in_body")
                decoded = parse_json(raw.decode("utf-8"))
                decoded_wire = _wire(decoded)
                decoded_wire.encode("utf-8")
                _require(owner.primary_token not in decoded_wire
                         and owner.control_token not in decoded_wire,
                         "native_credential_in_decoded_body")
                return decoded

            def do_CONNECT(self):
                self.reply(403, {"error": {"message": "external_proxy_disabled"}})

            def do_GET(self):
                if self.path == "/v1/models" and self.authorized(owner.primary_token):
                    self.reply(200, {"object": "list", "data": [
                        {"id": owner.runtime.transport.model, "object": "model"},
                    ]})
                else:
                    self.reply(404, {"error": {"message": "unsupported_native_route"}})

            def do_POST(self):
                path = urlsplit(self.path)
                if path.scheme or path.netloc or path.query or path.fragment:
                    self.reply(400, {"error": {"message": "invalid_native_route"}})
                    return
                token = owner.primary_token if self.path == "/v1/responses" else owner.control_token
                if self.path not in ("/v1/responses", "/control/recover") or not self.authorized(token):
                    self.reply(403, {"error": {"message": "native_route_not_authorized"}})
                    return
                request_id = None
                with owner._handler_condition:
                    owner._active_handlers += 1
                try:
                    request_id = owner.runtime.begin_http_request(self.path)
                    body = self.read_body()
                    if self.path == "/control/recover":
                        _require(type(body) is dict and set(body) == {"name", "arguments"},
                                 "invalid_recovery_control")
                        content = owner._dispatch("recover", body, request_id)
                        self.reply(200, {"ok": True, "content": content})
                    else:
                        result = owner._dispatch("invoke", body, request_id)
                        if result.ok:
                            self.reply(200, result.output_text)
                        elif result.reason == "http_error" and result.complete:
                            self.reply(result.http_status or 502, result.output_text)
                        else:
                            self.reply(502, {"error": {"message": result.reason}})
                except (OSError, ValueError, TypeError, KeyError, RecursionError, FutureTimeout):
                    if request_id is not None:
                        owner.runtime.note_http_state(request_id, "rejected")
                    self.reply(400, {"error": {"message": "native_request_rejected"}})
                finally:
                    try:
                        if request_id is not None:
                            owner.runtime.note_http_state(request_id, "responded")
                    finally:
                        with owner._handler_condition:
                            owner._active_handlers -= 1
                            owner._handler_condition.notify_all()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self._thread = Thread(target=self.server.serve_forever, daemon=True)

    def _dispatch(self, operation, body, request_id):
        _require(not self._stopping.is_set(), "native_bridge_stopping")
        future: Future[Any] = Future()
        try:
            self.runtime.note_http_state(request_id, "queued")
            self._queue.put_nowait((operation, body, future, request_id))
        except Full:
            raise ValueError("native_bridge_queue_full") from None
        try:
            # This bounds the HTTP waiter, not a false hard deadline on local
            # neural work or the upstream socket. Main-thread dispatch retains
            # RuntimeSession's existing interruption/cleanup semantics.
            return future.result(timeout=180)
        except FutureTimeout:
            future.cancel()
            self.runtime.note_http_state(request_id, "waiter_timeout")
            raise

    def pump_once(self, timeout=0.05):
        """Run a queued operation on the owning MAIN thread, never an HTTP worker."""
        if self._stopping.is_set():
            return False
        try:
            operation, body, future, request_id = self._queue.get(timeout=timeout)
        except Empty:
            return False
        if not future.set_running_or_notify_cancel():
            self._queue_cancelled += 1
            self.runtime.note_http_state(request_id, "cancelled")
            self._queue.task_done()
            return False
        try:
            self.runtime.note_http_state(request_id, "dispatched")
            result = self.runtime.invoke(body) if operation == "invoke" else \
                self.runtime.recover(body["name"], body["arguments"])
            self.runtime.note_http_state(request_id, "operation_finished")
            future.set_result(result)
        except BaseException as error:
            future.set_exception(ValueError("native_runtime_operation_failed"))
            if not isinstance(error, Exception):
                raise
        finally:
            self._queue.task_done()
        return True

    def cancel_pending(self):
        """Reject not-yet-dispatched work; never relaunch or cancel another task."""
        self._stopping.set()
        while True:
            try:
                _, _, future, request_id = self._queue.get_nowait()
            except Empty:
                break
            if not future.done():
                future.set_exception(ValueError("native_bridge_stopping"))
                self._queue_cancelled += 1
                self.runtime.note_http_state(request_id, "cancelled")
            self._queue.task_done()
        return {"cancelled_unsubmitted_operations": self._queue_cancelled}

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *args):
        self.cancel_pending()
        self.server.shutdown()
        self.server.server_close()
        self._thread.join(timeout=5)
        # Only HTTP waiters run in these threads; runtime operations were
        # already dispatched on the owner. Let their admission/delivery
        # receipts settle before the launcher seals the runtime summary.
        deadline = time.monotonic() + 20
        with self._handler_condition:
            while self._active_handlers:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError("native_http_handlers_not_settled")
                self._handler_condition.wait(remaining)
