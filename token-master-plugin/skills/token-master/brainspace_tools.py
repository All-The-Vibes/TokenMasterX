#!/usr/bin/env python
"""Explicit local tools. Global flags precede the command; no host discovery.

compress reads literal UTF-8 stdin and writes literal text without a footer.
request reads a JSON request; default is disabled. --conservative selects V3
exact in-context reuse; --source-reads supplies trusted executor receipts.
mode-task/enable require --contract FILE. Persistent modes require --session.
session streams trusted JSONL host-control frames; --allow-network is mandatory.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from brainspace.ccr import CCR
from brainspace.pipeline import prepare_request, request_measurement_identity
from brainspace.request_policy import RequestPolicy, SourceReadInfo
from brainspace.router import route_typed
from brainspace.task_mode import TaskContract, TaskModeStore, task_local_mode
from brainspace.tokens import prepare_tokenizer

MAX_INPUT_BYTES = 1_048_576


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("invalid_arguments")


def _parser():
    parser = _Parser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--session")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("compress", "request"):
        command = commands.add_parser(name)
        command.add_argument("--intent", default="conservative")
        command.add_argument("--hint")
        if name == "request":
            command.add_argument("--protocol")
            policy = command.add_mutually_exclusive_group()
            policy.add_argument("--policy")
            policy.add_argument("--conservative", action="store_true")
            command.add_argument("--source-reads", help="JSON receipt array from the trusted tool executor")
            command.add_argument("--stable-prefix-messages", type=int, default=0)
            command.add_argument("--exact-message-indices", type=int, nargs="*", default=[])
    for name, limit in (("retrieve", 32768), ("search", 20)):
        command = commands.add_parser(name)
        command.add_argument("ref")
        if name == "search":
            command.add_argument("query")
        command.add_argument("--offset", type=int, default=0)
        command.add_argument("--limit", type=int, default=limit)
    for name in ("mode-task", "mode-enable", "mode-status", "mode-off"):
        command = commands.add_parser(name)
        if name in ("mode-task", "mode-enable"):
            command.add_argument("--contract", required=True)
    command = commands.add_parser("prepare-tokenizer")
    command.add_argument("path")
    command.add_argument("--allow-download", action="store_true")
    command = commands.add_parser("session", help="Persistent trusted-host JSONL runtime")
    command.add_argument("--output", required=True, help="New private directory outside the workspace")
    command.add_argument("--task-id", help="Optional opaque identity reserved by a trusted host/controller")
    command.add_argument("--base-url", required=True)
    command.add_argument("--model", required=True)
    command.add_argument("--allow-network", action="store_true")
    command.add_argument("--backend", choices=("none", "local", "headroom", "profile"), required=True)
    command.add_argument("--max-calls", type=int, default=64)
    command.add_argument("--require-nonexpanding-input", action="store_true",
                         help="Opt in to whole-request input-wire fallback; not an all-in savings claim. "
                              "Not supported with optimizer registry selection.")
    command.add_argument("--max-frames", type=int, default=1024)
    command.add_argument("--phase", choices=("deployment", "learning"), default="deployment")
    command.add_argument("--learning-run-id")
    command.add_argument("--reasoning-effort", default="low",
                         choices=("none", "minimal", "low", "medium", "high", "xhigh"))
    command.add_argument("--timeout", type=float, default=45)
    command.add_argument("--max-output-tokens", type=int, default=2048)
    command.add_argument("--max-request-bytes", type=int, default=524288)
    command.add_argument("--max-response-bytes", type=int, default=524288)
    command.add_argument("--ponytail-export")
    mode = command.add_mutually_exclusive_group()
    mode.add_argument("--contract")
    mode.add_argument("--use-session-mode", action="store_true")
    policy = command.add_mutually_exclusive_group()
    policy.add_argument("--policy", help="Explicit RequestPolicy JSON, not an executable/plugin")
    policy.add_argument("--optimizer-db")
    policy.add_argument("--runtime-policy", help="RuntimePolicy JSON file; requires --backend profile")
    command.add_argument("--optimizer-version", type=int)
    command.add_argument("--workload-id")
    command.add_argument("--environment-id")
    command.add_argument("--headroom-cache")
    command.add_argument("--headroom-assets")
    command.add_argument("--headroom-time-budget-seconds", type=int,
                         help="Explicit Headroom cooperative budget, 1..60 seconds; "
                              "sets both local deadlines, not a hard wall-clock guarantee")
    command.add_argument("--headroom-docker-config",
                         help="Explicit empty config directory; otherwise task-owned, never discovered")
    # Keep parsing stdlib-only: an offline command in a minimal installation
    # must not import optional native/MCP support.
    native = commands.add_parser("native-copilot", help="One isolated native task through RuntimeSession")
    native.add_argument("--native-executable", required=True)
    native.add_argument("--output", required=True)
    native.add_argument("--base-url", required=True)
    native.add_argument("--model", required=True)
    native.add_argument("--allow-network", action="store_true")
    prompt = native.add_mutually_exclusive_group(required=True)
    prompt.add_argument("--prompt")
    prompt.add_argument("--prompt-file")
    for name in ("runtime-policy", "ponytail-export", "headroom-cache", "headroom-assets"):
        native.add_argument("--" + name)
    native.add_argument("--tokenizer-file", required=True)
    native.add_argument("--source-contract", default="native-full-view-v1",
                        choices=("native-full-view-v1", "native-view-result-v2"),
                        help="Native source receipt contract; v2 binds observed file-view results")
    native.add_argument("--intent", default="conservative",
                        choices=("conservative", "overview", "navigation", "exact",
                                 "edit", "debug", "aggregate", "task"))
    for name, default in (("max-calls", 64), ("max-output-tokens", 2048),
                          ("max-request-bytes", 524288), ("max-response-bytes", 524288)):
        native.add_argument("--" + name, type=int, default=default)
    native.add_argument("--timeout", type=float, default=45)
    native.add_argument("--native-timeout", type=float, default=180)
    native.add_argument("--reasoning-effort", default="low",
                        choices=("none", "minimal", "low", "medium", "high", "xhigh"))
    native.add_argument("--phase", choices=("deployment", "learning"), default="deployment")
    native.add_argument("--learning-run-id")
    native.add_argument("--task-id")
    return parser


def _read(stream) -> str:
    raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("input_too_large")
    return raw.decode("utf-8")


def _json(text):
    def reject(value):
        raise ValueError("non_finite_json")
    return json.loads(text, parse_constant=reject)


def execute(args):
    workspace = Path(args.workspace).resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("workspace_not_directory")
    if args.session is not None and not args.session.strip():
        raise ValueError("invalid_session")
    if args.command.startswith("mode-"):
        if args.command != "mode-task" and not args.session:
            raise ValueError("session_required")
        mode_store = TaskModeStore(workspace / ".token-master")
        if args.command in ("mode-task", "mode-enable"):
            with Path(args.contract).resolve(strict=True).open("rb") as handle:
                contract = TaskContract.from_dict(_json(_read(handle)))
            status = task_local_mode(contract) if args.command == "mode-task" else \
                mode_store.enable(args.session, contract)
        elif args.command == "mode-status":
            status = mode_store.status(args.session)
        else:
            status = mode_store.off(args.session)
        return status.to_dict()
    if args.command == "prepare-tokenizer":
        return prepare_tokenizer(Path(args.path).resolve(), allow_download=args.allow_download)
    store = CCR(workspace_root=workspace, session_id=args.session)
    if args.command == "retrieve":
        return store.retrieve_page(args.ref, args.offset, args.limit)
    if args.command == "search":
        return store.search(args.ref, args.query, args.offset, args.limit)
    content = _read(sys.stdin.buffer)
    if args.command == "compress":
        return route_typed(content, args.hint, stash=store.stash,
                           intent=args.intent, diagnostics={})[0]
    if args.policy is not None and len(args.policy.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError("policy_too_large")
    policy = (RequestPolicy.from_dict(_json(args.policy)) if args.policy is not None else
              RequestPolicy(version="request-policy-v3", enabled=True, min_tool_chars=512)
              if args.conservative else
              RequestPolicy())
    source_reads = ()
    if args.source_reads is not None:
        with Path(args.source_reads).resolve(strict=True).open("rb") as handle:
            observations = _json(_read(handle))
        if type(observations) is not list:
            raise ValueError("invalid_source_reads")
        source_reads = tuple(SourceReadInfo.from_dict(row) for row in observations)
    plan = prepare_request(
        _json(content), policy, ccr=store, intent=args.intent, protocol=args.protocol,
        stable_prefix_messages=args.stable_prefix_messages,
        exact_message_indices=tuple(args.exact_message_indices), hint=args.hint,
        source_reads=source_reads,
    )
    return {"plan": asdict(plan), "measurement_identity": request_measurement_identity()}


def main(argv=None):
    try:
        args = _parser().parse_args(argv)
        if args.command == "session":
            from brainspace.session_cli import run_session
            return run_session(args)
        if args.command == "native-copilot":
            from brainspace.native_cli import run_native_cli
            return run_native_cli(args)
        result = execute(args)
        output = result if isinstance(result, str) else json.dumps(
            result, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
        sys.stdout.buffer.write(output.encode("utf-8"))
        return 2 if isinstance(result, dict) and result.get("ok") is False else 0
    except Exception as error:
        # Never echo input, parser arguments, paths, keys or exception messages.
        diagnostic = {"ok": False, "error": "operation_failed", "error_type": type(error).__name__}
        sys.stderr.buffer.write((json.dumps(diagnostic) + "\n").encode("utf-8"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
