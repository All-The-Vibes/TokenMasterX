#!/usr/bin/env python
"""Opt-in versioned SessionStart adapters for Pillar 5 repository briefs.

Injects `.token-master/brief.md` once at the start of a NEW session (`source == "new"`
on Copilot CLI; `source in ("startup", "clear")` on Claude Code) and emits nothing
on resumed sessions (`source == "resume"`), outside indexed repositories, when
`TOKENMASTER_REPO_BRIEF=0`, or if any schema/budget invariant fails.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from brainspace import repo_brief, tokens  # noqa: E402
from brainspace.runtime_io import parse_json  # noqa: E402
from brainspace.tokens import serialize  # noqa: E402

CLAUDE_SESSIONSTART_CONTRACT = "claude-sessionstart-2026-11-17"
COPILOT_SESSIONSTART_CONTRACT = "copilot-sessionstart-2026-11-17"


def transform_session_start(
    payload: object,
    *,
    contract: str,
    budget: int = repo_brief.BRIEF_BUDGET,
    max_stdout_bytes: int = repo_brief.MAX_BRIEF_BYTES,
) -> dict | None:
    """Validate a host SessionStart payload and return the host envelope, or None."""
    if not isinstance(payload, dict) or type(budget) is not int or budget <= 0:
        return None
    if type(max_stdout_bytes) is not int or max_stdout_bytes <= 0:
        return None

    if contract == COPILOT_SESSIONSTART_CONTRACT:
        allowed = {"sessionId", "timestamp", "cwd", "source", "initialPrompt"}
        if (not set(payload).issubset(allowed)
                or not {"sessionId", "timestamp", "cwd", "source"}.issubset(payload)
                or not isinstance(payload["sessionId"], str) or not payload["sessionId"]
                or not isinstance(payload["cwd"], str) or not payload["cwd"]
                or type(payload["timestamp"]) is not int
                or payload["source"] != "new"):
            return None
        if "initialPrompt" in payload and payload["initialPrompt"] is not None \
                and not isinstance(payload["initialPrompt"], str):
            return None
        loaded = repo_brief.read_valid_brief(Path(payload["cwd"]), budget=budget)
        if loaded is None:
            return None
        envelope = {"additionalContext": loaded[0]}
    elif contract == CLAUDE_SESSIONSTART_CONTRACT:
        if (payload.get("hook_event_name") != "SessionStart"
                or not isinstance(payload.get("session_id"), str) or not payload["session_id"]
                or not isinstance(payload.get("cwd"), str) or not payload["cwd"]
                or payload.get("source") not in ("startup", "clear")):
            return None
        loaded = repo_brief.read_valid_brief(Path(payload["cwd"]), budget=budget)
        if loaded is None:
            return None
        envelope = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": loaded[0],
            }
        }
    else:
        return None

    encoded = serialize(envelope).encode("utf-8")
    if len(encoded) > max_stdout_bytes:
        return None
    return envelope


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("claude", "codex", "copilot"), default="")
    parser.add_argument("--contract", help="Explicit versioned host contract; required for Copilot")
    parser.add_argument("--tokenizer-file", help="Local pinned vocabulary; verified offline, never downloaded")
    args = parser.parse_args(argv)

    if os.environ.get("TOKENMASTER_REPO_BRIEF", "").strip() == "0":
        return 0

    contract = args.contract
    if args.host == "claude" and contract is None:
        contract = CLAUDE_SESSIONSTART_CONTRACT
    if (args.host, contract) not in (
        ("claude", CLAUDE_SESSIONSTART_CONTRACT),
        ("copilot", COPILOT_SESSIONSTART_CONTRACT),
    ):
        return 0

    try:
        in_buf = getattr(sys.stdin, "buffer", None)
        if in_buf is not None:
            raw = in_buf.read(1024 * 1024 + 1)
            if not raw or len(raw) > 1024 * 1024:
                return 0
            raw_text = raw.decode("utf-8")
        else:
            raw_text = sys.stdin.read(1024 * 1024 + 1)
            if not raw_text or len(raw_text.encode("utf-8")) > 1024 * 1024:
                return 0
        payload = (
            parse_json(raw_text)
            if contract == COPILOT_SESSIONSTART_CONTRACT
            else json.loads(raw_text)
        )
        if args.tokenizer_file is not None:
            os.environ["BRAINSPACE_TOKENIZER_FILE"] = args.tokenizer_file
            tokens._TRIED, tokens._ENCODER = False, None
        budget = int(os.environ.get("TOKENMASTER_REPO_BRIEF_BUDGET", str(repo_brief.BRIEF_BUDGET)))
        result = transform_session_start(payload, contract=contract, budget=budget)
        if result is not None:
            out_text = serialize(result)
            out_buf = getattr(sys.stdout, "buffer", None)
            if out_buf is not None:
                out_buf.write(out_text.encode("utf-8"))
                out_buf.flush()
            else:
                sys.stdout.write(out_text)
                sys.stdout.flush()
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
