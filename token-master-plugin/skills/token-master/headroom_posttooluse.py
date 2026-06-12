#!/usr/bin/env python
"""Headroom PostToolUse hook — the auto-compress half, at the append boundary.

This is the piece an MCP server structurally cannot be: blanket, automatic
compression of tool output *before* it is appended to the transcript and cached.
MCP tools are model-invoked (they fire only when the model elects to call them),
and by then the raw output is already in context. A PostToolUse hook runs at the
moment the host has a tool result in hand but has not yet committed it, so it is
the correct — and only — place to compress every output once, deterministically,
before it can perturb the provider's prompt-cache prefix.

THE CACHE-SAFETY RULE this hook exists to honor: compress each piece of content
exactly once, here, at first entry. Never rewrite history. Because the CCR
placeholder is a deterministic function of the content, the compressed block is
byte-identical on every future turn, so it never changes the cumulative prefix
hash that Anthropic/OpenAI prompt caching depends on.

Contract (Claude Code PostToolUse hooks — verified against code.claude.com/docs/en/hooks):
  * stdin: a JSON object describing the tool call + its result.
  * stdout: a JSON object, processed ONLY on exit 0. To REPLACE what the model
    sees, emit ``hookSpecificOutput`` with ``hookEventName: "PostToolUse"`` and
    ``updatedToolOutput`` (the documented field that "replaces the tool's result").
    stdout must contain ONLY that JSON — no extra text.
  * Host stdout cap: hook output is capped at 10,000 chars; anything larger is
    spilled to a file and replaced with a preview. A *compression* hook must
    therefore guarantee its replacement lands UNDER the cap, or the host re-truncates
    it and the recoverable-placeholder footer is lost. We enforce this explicitly:
    if the compressed text would exceed the cap we stash the whole original and
    return a compact placeholder-only result instead.
  * Failure policy: ANY error, or nothing gained → emit nothing, exit 0 (the docs'
    "no decision": original output is used). A compression hook must be invisible
    when it cannot help.

Configurable via env:
  * HEADROOM_HOOK_MIN_CHARS — only compress outputs larger than this (default 800).
  * HEADROOM_HOOK_TOOLS — comma-separated allowlist of tool names to compress
    (default: a sensible set of read/exec tools). "*" means all.

Run by the host as: uv run --with mcp python headroom_posttooluse.py
"""
import json
import os
import sys
from pathlib import Path

# Resolve `import headroom` regardless of the host's working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

MIN_CHARS = int(os.environ.get("HEADROOM_HOOK_MIN_CHARS", "800"))
# Host caps hook stdout at 10k chars; stay safely under so our replacement (and its
# recoverable footer) is never re-truncated by the host.
STDOUT_CAP = int(os.environ.get("HEADROOM_HOOK_STDOUT_CAP", "9000"))
_TOOLS_ENV = os.environ.get("HEADROOM_HOOK_TOOLS", "Bash,Read,Grep,Glob,WebFetch,view,read,execute,search")
_TOOL_ALLOW = {t.strip() for t in _TOOLS_ENV.split(",") if t.strip()}


def _noop_exit():
    """Emit nothing and succeed — the safe degrade for every failure path."""
    sys.exit(0)


def _extract(payload: dict):
    """Pull (tool_name, output_text, output_key) from the host's PostToolUse JSON.

    Claude Code nests the result under ``tool_response``; some shapes use
    ``tool_result``/``output``. We read defensively and report which key held the
    text so we can write the replacement back into the same shape.
    """
    tool_name = payload.get("tool_name") or payload.get("toolName") or ""
    resp = payload.get("tool_response", payload.get("tool_result", payload.get("output")))
    # tool_response may be a plain string or a dict carrying the text.
    if isinstance(resp, str):
        return tool_name, resp, ("tool_response", None)
    if isinstance(resp, dict):
        for k in ("content", "output", "stdout", "text"):
            v = resp.get(k)
            if isinstance(v, str) and v:
                return tool_name, v, ("tool_response", k)
    return tool_name, None, (None, None)


def main() -> None:
    try:
        raw = sys.stdin.read()
        if not raw:
            _noop_exit()
        payload = json.loads(raw)
    except (ValueError, OSError):
        _noop_exit()

    try:
        tool_name, text, _key = _extract(payload)
        if not text or len(text) < MIN_CHARS:
            _noop_exit()
        if "*" not in _TOOL_ALLOW and tool_name and tool_name not in _TOOL_ALLOW:
            _noop_exit()

        # Compress with the CCR stash wired in, so the original is recoverable via
        # headroom_retrieve. Lazy imports: a missing dep => no-op, never a crash.
        from headroom.ccr import CCR
        from headroom.router import route_typed
        from headroom import tokens

        ccr = CCR()
        compressed, ctype = route_typed(text, tool_name or None, stash=ccr.stash)
        if compressed == text or len(compressed) >= len(text):
            _noop_exit()  # nothing gained — leave the output untouched

        rep = tokens.reduction(text, compressed)
        note = (
            f"{compressed}\n\n— headroom[{ctype.value}] auto-compressed "
            f"{rep['tokens_before']}→{rep['tokens_after']} tok ({rep['pct_reduction']}%); "
            f"headroom_retrieve to expand —"
        )

        # Enforce the host's 10k stdout cap. If our replacement is still too big,
        # stash the WHOLE original and return a compact placeholder-only result, so
        # the model always gets a recoverable reference instead of a host-truncated
        # blob with the footer chopped off.
        if len(note) > STDOUT_CAP:
            ref = ccr.stash(text, ctype=ctype.value, source=tool_name or "tool output")
            if ref:
                note = (
                    f"— headroom[{ctype.value}]: output too large to inline "
                    f"({len(text):,} chars); stashed. Expand with headroom_retrieve {ref} —"
                )
            else:
                _noop_exit()  # could not stash → must not lose data; keep original

        # PostToolUse output-rewriting contract (verified field name).
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "updatedToolOutput": note,
            }
        }
        sys.stdout.write(json.dumps(out))
        sys.exit(0)
    except Exception:
        _noop_exit()


if __name__ == "__main__":
    main()
