#!/usr/bin/env python
"""Opt-in versioned PostToolUse adapters. Unknown hosts/shapes pass through.

Claude updatedToolOutput and Copilot modifiedResult retain the original schema.
Copilot requires its explicit contract; its whole-file view results get
request-policy-v6 shaping. Codex is a no-op.
Only safe text leaves change; errors, IDs, status and mixed media stay intact.
The byte cap is a configurable local safety limit, not a claimed universal host
limit. Actual host acceptance must be separately tested for the installed host.
No network, marketing footer, history rewrite or root-only forced truncation.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from brainspace.ccr import CCR  # noqa: E402
from brainspace import tokens  # noqa: E402
from brainspace.host_output import CLAUDE_CONTRACT, COPILOT_CONTRACT, transform_output  # noqa: E402
from brainspace.router import route_typed  # noqa: E402
from brainspace.runtime_io import parse_json  # noqa: E402
from brainspace.tokens import serialize  # noqa: E402
from brainspace.v6_shaping import shape_tool_result  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("claude", "codex", "copilot"), default="")
    parser.add_argument("--contract", help="Explicit versioned host contract; required for Copilot")
    parser.add_argument("--tokenizer-file", help="Local pinned vocabulary; verified offline, never downloaded")
    args = parser.parse_args(argv)
    # Installation opts into a named host. Merely piping arbitrary JSON here
    # must not silently assert another harness implements Claude's contract.
    contract = args.contract
    if args.host == "claude" and contract is None:
        contract = CLAUDE_CONTRACT
    if (args.host, contract) not in (("claude", CLAUDE_CONTRACT), ("copilot", COPILOT_CONTRACT)):
        return 0
    try:
        raw = sys.stdin.buffer.read(8 * 1024 * 1024 + 1)
        if not raw or len(raw) > 8 * 1024 * 1024:
            return 0
        payload = (parse_json(raw.decode("utf-8")) if contract == COPILOT_CONTRACT
                   else json.loads(raw.decode("utf-8")))
        if contract == COPILOT_CONTRACT and isinstance(payload, dict) and isinstance(payload.get("toolArgs"), str):
            # Copilot CLI 1.0.78-3 sends toolArgs as a JSON string; the build observed on 2026-10-09 sent an object.
            payload["toolArgs"] = parse_json(payload["toolArgs"])
        intent = os.environ.get("BRAINSPACE_INTENT", "conservative")
        if contract == COPILOT_CONTRACT and intent != "conservative":
            return 0
        if args.tokenizer_file is not None:
            # This single-invocation CLI trusts argv, not tool payloads. Reset
            # cached selection so an explicit bad file cannot reuse an earlier
            # encoder; tokens._encoder retains the authoritative digest guard.
            os.environ["BRAINSPACE_TOKENIZER_FILE"] = args.tokenizer_file
            tokens._TRIED, tokens._ENCODER = False, None
        ccr = None if contract == COPILOT_CONTRACT else CCR(
            workspace_root=os.environ.get("BRAINSPACE_WORKSPACE_ROOT") or Path.cwd(),
            session_id=os.environ.get("BRAINSPACE_SESSION_ID") or None,
            scope=os.environ.get("BRAINSPACE_SCOPE") or None,
            shared=os.environ.get("BRAINSPACE_SHARED") == "1",
        )
        def compress(text, hint):
            if contract == COPILOT_CONTRACT:  # request-policy-v6 (PRS-2, PRS-3): shape a whole-file view once
                return shape_tool_result("view", {"path": hint}, text, tokens.count_tokens)
            return route_typed(text, hint, stash=ccr.stash, intent=intent)[0]
        result = transform_output(
            payload, compress, contract=contract,
            min_chars=int(os.environ.get("BRAINSPACE_HOOK_MIN_CHARS", "800")),
            max_stdout_bytes=int(os.environ.get("BRAINSPACE_HOOK_STDOUT_CAP", "9000")),
        )
        if result is not None:
            sys.stdout.buffer.write(serialize(result).encode("utf-8"))
        return 0
    except Exception:
        # No diagnostic text in the tool-result channel and no raw-error logging.
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
