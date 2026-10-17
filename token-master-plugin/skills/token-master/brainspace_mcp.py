#!/usr/bin/env python
"""Model-invoked, offline-by-default compression and complete scoped recovery.

This server does not intercept a host's other tools or model requests. Views
are advisory representations, not task-quality certificates. Exact/edit/debug
intents bypass; navigation/overview must be explicitly requested. Recovery is
paged with digests and completion flags, never silently truncated.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402
from brainspace.ccr import CCR  # noqa: E402
from brainspace.router import route_typed  # noqa: E402
from brainspace import tokens  # noqa: E402


def _env_limit(name, default, ceiling):
    try:
        return min(ceiling, max(1, int(os.environ.get(name, str(default)))))
    except ValueError:
        return default


MAX_COMPRESS_BYTES = _env_limit("BRAINSPACE_MAX_COMPRESS_BYTES", 1_048_576, 8_388_608)
MAX_RETRIEVE_CHARS = _env_limit("BRAINSPACE_MAX_RETRIEVE", 32768, 32768)
_STATE: dict[str, Any] = {"ccr": None, "last_transform": None}


def _ccr() -> CCR:
    if _STATE["ccr"] is None:
        _STATE["ccr"] = CCR(
            workspace_root=os.environ.get("BRAINSPACE_WORKSPACE_ROOT") or Path.cwd(),
            session_id=os.environ.get("BRAINSPACE_SESSION_ID") or None,
            scope=os.environ.get("BRAINSPACE_SCOPE") or None,
            shared=os.environ.get("BRAINSPACE_SHARED") == "1",
        )
    return _STATE["ccr"]


def _text_envelope(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": False}


mcp = FastMCP("brainspace")


@mcp.tool(structured_output=False)
def brainspace_compress(content: str, hint: str = "", intent: str = "conservative") -> str:
    """Return a guarded text view; no footer is appended. Default preserves code.

    Use navigation only for code structure, overview only for non-exhaustive
    structured/log views. Exact/edit/debug/aggregate/security intents bypass.
    References identify scoped originals: brainspace_retrieve pages or
    brainspace_search finds exact text. Diagnostics live in brainspace_stats.
    """
    try:
        diagnostics: dict[str, Any] = {}
        view, ctype = route_typed(content, hint or None, stash=_ccr().stash,
                                 intent=intent, diagnostics=diagnostics)
        accepted = view != content and tokens.guard_replacement(
            _text_envelope(content), _text_envelope(view), max_bytes=MAX_COMPRESS_BYTES,
        )
        result = view if accepted else content
        _STATE["last_transform"] = {
            "policy": "safe-views-v1", "decision": "transformed" if accepted else "unchanged",
            "type": ctype.value, "intent": intent,
            "diagnostics": diagnostics,
            "bytes_before": len(content.encode("utf-8")),
            "bytes_after": len(result.encode("utf-8")),
            **tokens.reduction(content, result),
            "task_quality_verified": False, "whole_task_tokens_measured": False,
        }
        return result
    except Exception:
        _STATE["last_transform"] = {"policy": "safe-views-v1", "decision": "unchanged",
                                    "reason": "compression_unavailable"}
        return content


@mcp.tool(structured_output=False)
def brainspace_retrieve(ref: str, offset: int = 0, limit: int = 32768) -> dict:
    """Retrieve an exact page; repeat at next_offset until complete is true.

    Offsets count Unicode characters. Each page includes full-content SHA-256,
    page SHA-256, byte/character lengths and explicit errors. Never infer an
    unknown original is empty. References are workspace/session scoped.
    """
    try:
        if type(limit) is int and limit > 0:
            limit = min(limit, MAX_RETRIEVE_CHARS)
        return _ccr().retrieve_page(ref, offset, limit)
    except Exception:
        return {"ok": False, "content": "", "complete": False,
                "error": "recovery_unavailable", "next_offset": None}


@mcp.tool(structured_output=False)
def brainspace_search(ref: str, query: str, offset: int = 0, limit: int = 20,
                      context_lines: int = 1) -> dict:
    """Bounded case-sensitive exact search of a verified original; page matches.

    Context snippets may be truncated and are labeled; retrieve pages for exact
    full context. This is not semantic search or an exhaustive answer oracle.
    """
    try:
        return _ccr().search(ref, query, offset, limit, context_lines)
    except Exception:
        return {"ok": False, "results": [], "complete": False, "error": "search_unavailable"}


@mcp.tool(structured_output=False)
def brainspace_release(ref: str) -> dict:
    """Release this scope/session's lease only when the reference is no longer needed.

    Does not delete the original. Explicit later garbage collection may evict
    unpinned content; active session leases remain protected.
    """
    try:
        return {"released": _ccr().release(ref), "deleted": False}
    except Exception:
        return {"released": False, "deleted": False, "error": "release_unavailable"}


@mcp.tool(structured_output=False)
def brainspace_stats() -> dict:
    """Scoped storage/retention and last-view diagnostics, not a task saving claim."""
    try:
        return {**_ccr().stats(), "last_transform": _STATE["last_transform"],
                "measurement": tokens.backend_info(), "host_interception": False}
    except Exception:
        return {"error": "statistics_unavailable", "host_interception": False}


if __name__ == "__main__":
    mcp.run()
