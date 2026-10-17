"""Explicit installed native entrypoint; no profile/credential discovery."""
from __future__ import annotations

import json
import os

from .runtime_io import parse_json, safe_root


def _text(path, limit=1_048_576):
    source = safe_root(path)
    with source.open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("native_input_file_bound")
    return raw.decode("utf-8")


def run_native_cli(args):
    from .native_events import validate_source_contract

    validate_source_contract(args.source_contract)
    from . import tokens
    from .native_copilot import run_native_copilot
    from .runtime_policy import RuntimePolicy
    from .runtime_resources import RuntimeResources

    if args.allow_network is not True or not args.session:
        raise ValueError("explicit_native_network_and_session_required")
    os.environ["BRAINSPACE_TOKENIZER_FILE"] = str(safe_root(args.tokenizer_file))
    tokens._TRIED, tokens._ENCODER = False, None
    if not tokens.backend_info().get("exact_reference"):
        raise ValueError("verified_native_tokenizer_required")
    prompt = args.prompt if args.prompt is not None else _text(args.prompt_file, 65536)
    if type(prompt) is not str or len(prompt.encode("utf-8")) > 65536:
        raise ValueError("native_prompt_bound")
    policy = RuntimePolicy.from_dict(parse_json(_text(args.runtime_policy))) \
        if args.runtime_policy else RuntimePolicy()
    resources = RuntimeResources(
        ponytail_export=args.ponytail_export, headroom_cache=args.headroom_cache,
        headroom_assets=args.headroom_assets,
    )
    result = run_native_copilot(
        workspace=args.workspace, session_id=args.session, output=args.output,
        base_url=args.base_url, model=args.model, prompt=prompt,
        copilot_exe=args.native_executable, allow_network=True,
        policy=policy, resources=resources, intent=args.intent, max_calls=args.max_calls,
        max_output_tokens=args.max_output_tokens, max_request_bytes=args.max_request_bytes,
        max_response_bytes=args.max_response_bytes, timeout=args.timeout,
        native_timeout=args.native_timeout, reasoning_effort=args.reasoning_effort,
        phase=args.phase, learning_run_id=args.learning_run_id, task_id=args.task_id,
        source_contract=args.source_contract,
    )
    # Full native event/source data remains in the explicit private output,
    # not a giant terminal dump. Exit 0 is operational completion, not correctness.
    runtime = result.get("runtime") or {}
    print(json.dumps({
        "output": str(safe_root(args.output)), "complete": result.get("complete") is True,
        "model_calls": runtime.get("model_calls"),
        "gateway_reported_tokens": runtime.get("gateway_reported_tokens"),
        "reference_totals": runtime.get("reference_totals"),
        "quality_verified": None, "policy_promoted": False,
        "scope": "native runtime execution; outcome requires an independent check",
    }, ensure_ascii=False, allow_nan=False))
    return 0 if result.get("complete") is True else 3
