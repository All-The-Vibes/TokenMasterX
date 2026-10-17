"""Versioned host result adapters; unknown hosts and shapes are passthrough.

Source contract reviewed 2026-10-05: code.claude.com/docs/en/hooks and
captured Claude Code 2.1.289 native hook payloads.
Copilot 1.0.95-0: observed native postToolUse view payload on 2026-10-09.
Configuration support is NOT evidence that a host accepted a replacement.
This module changes eligible text leaves only, never error/status/image/ID
fields. Tool output remains untrusted tool output, not an instruction channel.
"""
from __future__ import annotations

import copy
from typing import Any, Callable

from .tokens import guard_replacement, serialize

CLAUDE_CONTRACT = "claude-posttooluse-2026-10-05"
COPILOT_CONTRACT = "copilot-posttooluse-2026-10-09"


def _copilot_output(payload: dict, compress: Callable[[str, str], str],
                    min_chars: int, max_stdout_bytes: int) -> dict | None:
    """Only the observed successful, pure-text view schema is qualified.

    The callback is trusted to preserve content semantics; the native CLI uses
    conservative JSON only. Extra fields/range reads require new qualification,
    not guesses about whether an unknown field represents an error or media.
    """
    if (set(payload) != {"sessionId", "timestamp", "cwd", "toolName", "toolArgs", "toolResult"}
            or payload["toolName"] != "view"
            or not isinstance(payload["sessionId"], str) or not payload["sessionId"]
            or not isinstance(payload["cwd"], str) or not payload["cwd"]
            or type(payload["timestamp"]) is not int):
        return None
    inputs, original = payload["toolArgs"], payload["toolResult"]
    if (not isinstance(inputs, dict) or set(inputs) != {"path"}
            or not isinstance(inputs["path"], str) or not inputs["path"]
            or not isinstance(original, dict)
            or set(original) != {"resultType", "textResultForLlm"}
            or original["resultType"] != "success"
            or not isinstance(original["textResultForLlm"], str)
            or type(min_chars) is not int or min_chars < 0):
        return None
    text = original["textResultForLlm"]
    if len(text) < min_chars:
        return None
    view = compress(text, inputs["path"])
    if not isinstance(view, str) or view == text:
        return None
    replacement = copy.deepcopy(original)
    replacement["textResultForLlm"] = view
    # Guard the whole result, not just its inner string. Both reference tokens
    # and UTF-8 bytes must strictly decrease, independently of the stdout cap.
    original_bytes = len(serialize(original).encode("utf-8"))
    if not guard_replacement(original, replacement, max_bytes=original_bytes - 1):
        return None
    envelope = {"modifiedResult": replacement}
    if (type(max_stdout_bytes) is not int or max_stdout_bytes <= 0
            or len(serialize(envelope).encode("utf-8")) > max_stdout_bytes):
        return None
    return envelope


def _failed(response: dict) -> bool:
    if any(response.get(key) for key in
           ("isError", "error", "errors", "stderr", "interrupted", "isImage")):
        return True
    for key in ("exitCode", "exit_code", "returncode", "return_code"):
        if key in response and (type(response[key]) is not int or response[key] != 0):
            return True
    return False


def _leaves(tool: str, response: object) -> list[tuple]:
    """Supported result schemas. An empty list means do not rewrite."""
    if tool.startswith("mcp__") and isinstance(response, list):
        # Claude 2.1.289 exposes successful unstructured MCP results as the
        # content array itself, not a CallToolResult-shaped dictionary.
        if response and all(
            isinstance(block, dict) and block.get("type") == "text"
            and isinstance(block.get("text"), str) and not _failed(block)
            for block in response
        ):
            return [(index, "text") for index in range(len(response))]
        return []
    if not isinstance(response, dict) or _failed(response):
        return []
    if tool == "Bash":
        if (isinstance(response.get("stdout"), str)
                and isinstance(response.get("stderr"), str)):
            return [("stdout",)]
    elif tool == "Read":
        file = response.get("file")
        if (response.get("type") == "text" and isinstance(file, dict)
                and isinstance(file.get("content"), str)):
            return [("file", "content")]
    elif tool == "Grep":
        if response.get("mode") == "content" and isinstance(response.get("content"), str):
            return [("content",)]
    elif tool.startswith("mcp__"):
        blocks = response.get("content")
        if response.get("structuredContent") is not None:
            return []
        if (isinstance(blocks, list) and blocks
                and all(isinstance(block, dict) and block.get("type") == "text"
                        and isinstance(block.get("text"), str) for block in blocks)):
            return [("content", index, "text") for index in range(len(blocks))]
    return []


def _hint(payload: dict) -> str:
    inputs = payload.get("tool_input")
    if isinstance(inputs, dict):
        for key in ("file_path", "filePath", "path"):
            if isinstance(inputs.get(key), str):
                return inputs[key]
    return payload["tool_name"]


def transform_output(
    payload: dict, compress: Callable[[str, str], str], *,
    contract: str, min_chars: int = 800, max_stdout_bytes: int = 9000,
) -> dict | None:
    """Return schema-matching hook JSON, or None (leave original untouched).

    No root-only replacement is forced when the final wire envelope exceeds the
    cap. Recovery availability alone does not prove a blind omission useful.
    """
    try:
        if not isinstance(payload, dict):
            return None
        if contract == COPILOT_CONTRACT:
            return _copilot_output(payload, compress, min_chars, max_stdout_bytes)
        if contract != CLAUDE_CONTRACT:
            return None
        if payload.get("hook_event_name", "PostToolUse") != "PostToolUse":
            return None
        if _failed(payload) or payload.get("is_interrupt"):
            return None
        name, original = payload.get("tool_name"), payload.get("tool_response")
        if not isinstance(name, str) or not isinstance(original, (dict, list)):
            return None
        if isinstance(original, list) and payload.get("hook_event_name") != "PostToolUse":
            return None
        paths = _leaves(name, original)
        if not paths:
            return None
        replacement = copy.deepcopy(original)
        changed = False
        for path in paths:
            parent: Any = replacement
            for key in path[:-1]:
                parent = parent[key]
            text = parent[path[-1]]
            if len(text) < min_chars:
                continue
            view = compress(text, _hint(payload))
            if not isinstance(view, str):
                return None
            if view != text:
                parent[path[-1]] = view
                changed = True
        if not changed or not guard_replacement(original, replacement):
            return None
        envelope = {"hookSpecificOutput": {
            "hookEventName": "PostToolUse", "updatedToolOutput": replacement,
        }}
        if (type(max_stdout_bytes) is not int or max_stdout_bytes <= 0
                or len(serialize(envelope).encode("utf-8")) > max_stdout_bytes):
            return None
        return envelope
    except Exception:
        return None
