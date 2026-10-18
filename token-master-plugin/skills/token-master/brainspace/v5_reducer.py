"""Multi-format compact-root context reducer for request-policy-v5.

Combines:
1. Exact visible reuse of identical reads (v3) when a full original remains visible.
2. Lexical JSON compaction + homogeneous-array overview with compact-root-v1 reference.
3. Single-root AST code skeletonization (Python/Rust + structural fallback) that
   preserves module imports/constants, class/function signatures, decorators,
   docstrings, and return/raise statements without per-function marker bloat.
4. Structure-preserving Markdown/prose compaction that keeps headings, tables,
   lists, code fences, and lead sentences.
5. Successful-log head/tail compaction with compact-root-v1 reference.

Every accepted transformation stores the complete original UTF-8 text under a
scoped ``compact-root-v1`` reference (``[[BR:<64-hex>|r=1]]``), verifies exact
byte-for-byte recovery before acceptance, and enforces strict whole-wire token
and UTF-8 byte reduction.
"""
from __future__ import annotations

import copy
import importlib
import json
import re
from typing import Any, Callable

from .ccr import _COMPACT_ROOT_RE
from .compressors.json_compressor import _compact as _compact_json, _has_alert, _shape
from .document_structure import document_structure_preserved, document_structure_spans
from .exact_reuse import find_exact_reuses, restore_exact_reuses
from .protected_text import _blocks as _fence_blocks, protected_text_preserved
from .request_policy import (
    QUALIFIED_SOURCE_TOOLS,
    RequestPlan,
    RequestPolicy,
    SourceReadInfo,
    TransformResult,
    _EXACT_TEXT,
    _fits,
    _measure,
    _protected,
    serialize_request,
)
from .router import ContentType, detect, lang_from_hint

_KEEP_STATEMENT_RE = re.compile(
    r"^\s*(?:return\b|raise\b|yield\b|@[A-Za-z_]|def\s+|async\s+def\s+|class\s+)"
)
_HEADING_OR_LIST_RE = re.compile(
    r"^\s*(?:#{1,6}\s+|\|.*\|(?:\s*)$|[-*+]\s+|\d+[.)]\s+|>\s+)"
)
_SENTENCE_END_RE = re.compile(r"^(.{24,180}?[.!?])(?:\s+|$)")
_VIEW_LINE_NUM_RE = re.compile(r"^\s*(\d+)\.\s?(.*)$")


def _strip_copilot_view_line_numbers(content: str) -> str:
    """If content is formatted by copilot.exe ranged view ('1. ...'), strip line numbers."""
    lines = content.splitlines(keepends=True)
    if len(lines) < 3:
        return content
    stripped_lines: list[str] = []
    expected_num: int | None = None
    for line in lines:
        eol = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
        body = line[:-len(eol)] if eol else line
        m = _VIEW_LINE_NUM_RE.match(body)
        if m is None:
            return content
        num = int(m.group(1))
        if expected_num is not None and num != expected_num:
            return content
        expected_num = num + 1
        stripped_lines.append(m.group(2) + eol)
    return "".join(stripped_lines)


def is_compact_root_reference(reference: str) -> bool:
    return type(reference) is str and _COMPACT_ROOT_RE.fullmatch(reference) is not None


def compress_code_v5(content: str, *, source_path: str | None = None) -> str:
    """Compact older source files using one root reference instead of per-function hashes.

    Preserves imports, module-level constants/assignments, class/function signatures,
    decorators, leading docstrings, short function bodies (<= 4 lines), and final
    return/raise statements in longer bodies.
    """
    if not isinstance(content, str) or not content.strip():
        return content
    lang = lang_from_hint(source_path) or "python"
    if lang in ("python", "rust"):
        view = _tree_sitter_compact_code(content, lang)
        if view != content:
            return view
    return _line_compact_code(content)


def _tree_sitter_compact_code(content: str, lang: str) -> str:
    specs = {
        "python": ("tree_sitter_python", "function_definition"),
        "rust": ("tree_sitter_rust", "function_item"),
    }
    if lang not in specs:
        return content
    module_name, fn_type = specs[lang]
    try:
        from tree_sitter import Language, Parser

        grammar = importlib.import_module(module_name)
        parser = Parser(Language(grammar.language()))
        source = content.encode("utf-8")
        root = parser.parse(source).root_node
        if root.has_error:
            return content

        replacements: list[tuple[int, int, bytes]] = []
        _collect_fn_replacements(root, source, fn_type, replacements)
        if not replacements:
            return content

        parts: list[bytes] = []
        cursor = 0
        for start, end, summary_bytes in replacements:
            if start < cursor:
                continue
            parts.append(source[cursor:start])
            parts.append(summary_bytes)
            cursor = end
        parts.append(source[cursor:])
        out = b"".join(parts).decode("utf-8")
        return out if len(out) < len(content) else content
    except Exception:
        return content


def _collect_fn_replacements(
    node: Any,
    source: bytes,
    fn_type: str,
    replacements: list[tuple[int, int, bytes]],
) -> None:
    if node.type != fn_type:
        for child in node.children:
            _collect_fn_replacements(child, source, fn_type, replacements)
        return

    body = node.child_by_field_name("body")
    if body is None:
        return
    start, end = body.start_byte, body.end_byte
    if fn_type == "function_item":
        start += 1
        end -= 1
    else:
        for child in body.named_children:
            if child.type == "comment":
                continue
            if (
                child.type == "expression_statement"
                and len(child.named_children) == 1
                and child.named_children[0].type in ("string", "concatenated_string")
            ):
                start = child.end_byte
            break

    while start < end and source[start : start + 1] in b" \t\r\n":
        start += 1
    while end > start and source[end - 1 : end] in b" \t\r\n":
        end -= 1
    if start >= end:
        return

    segment = source[start:end].decode("utf-8", errors="replace")
    lines = segment.splitlines()
    if len(lines) <= 2 and len(segment) <= 120:
        return

    # Keep final return/raise single-line statement if short and informative.
    kept_tail = ""
    for line in reversed(lines):
        stripped = line.strip()
        if stripped.startswith(("return ", "raise ")) and len(stripped) <= 96:
            indent_match = re.match(r"^([ \t]*)", lines[0])
            indent = indent_match.group(1) if indent_match else "    "
            kept_tail = f"\n{indent}{stripped}"
            break

    replacement = f"# ... [{len(lines)} lines elided]{kept_tail}".encode("utf-8")
    if len(replacement) < (end - start):
        replacements.append((start, end, replacement))


def _line_compact_code(content: str) -> str:
    lines = content.splitlines(keepends=True)
    if len(lines) <= 20:
        return content
    out: list[str] = []
    elided = 0
    for line in lines:
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith(("#", "//", "import ", "from ", "export ", "const ", "let ", "type ", "interface ", "pub ", "use ", "struct ", "enum "))
            or _KEEP_STATEMENT_RE.match(line)
        ):
            if elided:
                out.append(f"    # ... [{elided} lines elided]\n")
                elided = 0
            out.append(line)
        else:
            elided += 1
    if elided:
        out.append(f"    # ... [{elided} lines elided]\n")
    view = "".join(out)
    return view if len(view) < len(content) else content


def compress_json_v5(content: str, *, intent: str = "conservative") -> str:
    """Compact JSON whitespace and summarize large homogeneous arrays in overview/navigation."""
    if not isinstance(content, str) or not content.strip():
        return content
    try:
        duplicate_members = False

        def object_pairs(pairs):
            nonlocal duplicate_members
            obj = dict(pairs)
            duplicate_members |= len(obj) != len(pairs)
            return obj

        decoder = json.JSONDecoder(object_pairs_hook=object_pairs)
        data = decoder.decode(content)
        compact = _compact_json(content)
        if duplicate_members or _has_alert(data):
            return compact
        if intent in ("overview", "navigation", "task"):
            if isinstance(data, list) and len(data) > 6:
                shape = _shape(data[0])
                if all(_shape(item) == shape for item in data[1:]):
                    items = []
                    cursor = 1
                    for _ in data:
                        _, end = decoder.raw_decode(compact, cursor)
                        items.append(compact[cursor:end])
                        cursor = end + 1
                    indices = [0, 1, len(data) - 1]
                    meta = {
                        "_brainspace_view": "overview",
                        "lossy": True,
                        "total_items": len(data),
                        "omitted_items": len(data) - len(indices),
                        "indices": indices,
                    }
                    view = (
                        json.dumps(meta, separators=(",", ":"))[:-1]
                        + ',"items":['
                        + ",".join(items[i] for i in indices)
                        + "]}"
                    )
                    if len(view) < len(compact):
                        return view
            elif isinstance(data, dict):
                changed_dict = False
                summarized: dict[str, Any] = {}
                for k, v in data.items():
                    if isinstance(v, list) and len(v) > 6 and v:
                        item_shape = _shape(v[0])
                        if all(_shape(item) == item_shape for item in v[1:]):
                            summarized[k] = [
                                v[0],
                                v[1],
                                {"_brainspace_elided_items": len(v) - 3, "total_items": len(v)},
                                v[-1],
                            ]
                            changed_dict = True
                            continue
                    summarized[k] = v
                if changed_dict:
                    view = json.dumps(summarized, ensure_ascii=False, separators=(",", ":"))
                    if len(view) < len(compact):
                        return view
        return compact
    except Exception:
        return content


def compress_prose_v5(content: str) -> str:
    """Compact older Markdown/prose while preserving fences, tables, lists, and headings."""
    if not isinstance(content, str) or len(content) < 256:
        return content
    if document_structure_spans(content) is None:
        return content

    # Protect fenced blocks from any line compaction.
    fences = _fence_blocks(content)
    if fences is None:
        return content
    protected_char_ranges = [(b.start, b.end) for b in fences]
    spans = document_structure_spans(content) or ()
    for span in spans:
        protected_char_ranges.append((span.start, span.end))

    def is_protected_range(start_pos: int, end_pos: int) -> bool:
        return any(s < end_pos and e > start_pos for s, e in protected_char_ranges)

    lines = content.splitlines(keepends=True)
    out: list[str] = []
    pos = 0
    consecutive_blank = 0
    for line in lines:
        line_start = pos
        line_end = pos + len(line)
        pos = line_end
        if is_protected_range(line_start, line_end):
            consecutive_blank = 0
            out.append(line)
            continue
        stripped = line.strip()
        if not stripped:
            consecutive_blank += 1
            if consecutive_blank <= 1:
                out.append("\n")
            continue
        consecutive_blank = 0
        if _HEADING_OR_LIST_RE.match(line) or "**" in stripped or len(stripped) <= 110:
            out.append(line)
            continue
        eol = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
        match = _SENTENCE_END_RE.match(stripped)
        if match:
            shortened = match.group(1) + " .." + eol
            out.append(shortened if len(shortened) < len(line) else line)
        elif len(stripped) > 140:
            out.append(stripped[:120].rstrip() + " .." + eol)
        else:
            out.append(line)

    view = "".join(out)
    if (
        view == content
        or len(view) >= len(content)
        or not protected_text_preserved(content, view)
        or not document_structure_preserved(content, view)
    ):
        return content
    return view


def compress_logs_v5(content: str) -> str:
    """Compact older successful logs to head + tail lines."""
    from .compressors.logs_compressor import _ALERT, _RECORD, _SUCCESS

    if not isinstance(content, str):
        return content
    lines = content.splitlines(keepends=True)
    if len(lines) <= 8 or _ALERT.search(content):
        return content
    records = []
    for line in lines:
        match = _RECORD.fullmatch(line.rstrip("\r\n"))
        if match is None:
            return content
        records.append(match[1])
    if not _SUCCESS.fullmatch(records[-1]):
        return content
    if any(
        re.search(r"\b(?:exit|exited|status|state|returncode|code)\b", r, re.I)
        and not _SUCCESS.fullmatch(r)
        for r in records
    ):
        return content
    window = 2
    omitted = len(lines) - 2 * window
    view = (
        "".join(lines[:window])
        + f"... overview (lossy): {omitted} lines elided ...\n"
        + "".join(lines[-window:])
    )
    return view if len(view) < len(content) else content


def transform_v5_content(
    content: str,
    info: SourceReadInfo,
    *,
    stash_compact_root: Callable[[str, str, str], str | None],
    intent: str = "conservative",
) -> TransformResult:
    """Produce a compact view + single compact-root-v1 reference for an older read."""
    unnumbered = _strip_copilot_view_line_numbers(content)
    ctype = detect(unnumbered, info.source_path)
    if ctype is ContentType.JSON:
        body = compress_json_v5(unnumbered, intent=intent)
        ctype_name = "json"
    elif ctype is ContentType.CODE:
        body = compress_code_v5(unnumbered, source_path=info.source_path)
        ctype_name = "code"
    elif ctype is ContentType.LOG:
        body = compress_logs_v5(unnumbered)
        ctype_name = "log"
    else:
        body = compress_prose_v5(unnumbered)
        ctype_name = "prose"

    if not isinstance(body, str) or body == content or len(body) >= len(content):
        return TransformResult(content, "")
    reference = stash_compact_root(content, info.source_path, ctype_name)
    if not reference or not is_compact_root_reference(reference):
        return TransformResult(content, "")
    sep = "" if body.endswith("\n") else "\n"
    return TransformResult(f"{body}{sep}{reference}", reference)


def plan_v5_request(
    request: Any,
    *,
    policy: RequestPolicy,
    intent: str | None,
    indices: list[int],
    source_by_call: dict[str, SourceReadInfo],
    stable_prefix_messages: int,
    exact_message_indices: tuple[int, ...] | list[int],
    original_wire: str,
    before_tokens: int,
    before_bytes: int,
    count: Callable[[str], int],
    recover: Callable[[str], str | None] | None,
    v5_transform: Callable[[str, SourceReadInfo], TransformResult] | None,
) -> RequestPlan:
    """Execute request-policy-v5 planning: exact reuse first, then multi-format compact root."""
    def unchanged(reason: str) -> RequestPlan:
        return RequestPlan(
            request,
            original_wire,
            "unchanged",
            reason,
            policy.policy_id,
            tokens_before=before_tokens,
            tokens_after=before_tokens,
            wire_bytes_before=before_bytes,
            wire_bytes_after=before_bytes,
        )

    if intent not in ("conservative", "navigation", "overview", "aggregate", "edit", "debug", "task"):
        return unchanged(
            "no_eligible_transform"
            if _fits(request, policy, before_tokens, before_bytes)
            else "cannot_safely_meet_budget"
        )

    candidate = copy.deepcopy(request)
    calls = {
        call["id"]: call
        for message in candidate["messages"]
        for call in message.get("tool_calls", [])
    }
    verified: dict[int, SourceReadInfo] = {}
    for index in indices:
        message = candidate["messages"][index]
        text = message["content"]
        read_info = source_by_call.get(message["tool_call_id"])
        if (
            type(text) is not str
            or read_info is None
            or read_info.status != "success"
            or read_info.tool_name not in QUALIFIED_SOURCE_TOOLS
            or not read_info.matches(message, calls.get(read_info.call_id))
            or _protected({k: v for k, v in message.items() if k != "content"}, strict_status=True)
        ):
            continue
        verified[index] = read_info

    older_indices = indices[: -policy.keep_recent_tool_results]
    targets = {
        i
        for i in older_indices
        if i in verified
        and i >= stable_prefix_messages
        and i not in exact_message_indices
        and len(candidate["messages"][i]["content"]) >= policy.min_tool_chars
    }
    wire, measured_tokens, wire_bytes = original_wire, before_tokens, before_bytes
    changed_indices: list[int] = []

    # Step 1: Exact visible reuse (zero information loss when identical read is visible).
    reused_indices: set[int] = set()
    try:
        non_exact_verified = {
            i: info
            for i, info in verified.items()
            if not _EXACT_TEXT.search(candidate["messages"][i]["content"])
        }
        reuse_targets = targets & set(non_exact_verified)
        accepted_reuses = []
        for reuse in find_exact_reuses(candidate["messages"], non_exact_verified, reuse_targets):
            if len(changed_indices) >= policy.max_transforms:
                break
            message = candidate["messages"][reuse.target_index]
            original_text = message["content"]
            message["content"] = reuse.marker
            proposed_wire = serialize_request(candidate)
            proposed_tokens, proposed_bytes = _measure(proposed_wire, count)
            if proposed_tokens >= measured_tokens or proposed_bytes > wire_bytes:
                message["content"] = original_text
                continue
            accepted_reuses.append(reuse)
            reused_indices.add(reuse.target_index)
            changed_indices.append(reuse.target_index)
            wire, measured_tokens, wire_bytes = proposed_wire, proposed_tokens, proposed_bytes
        if accepted_reuses and restore_exact_reuses(candidate["messages"], tuple(accepted_reuses)) != request["messages"]:
            return unchanged("reuse_verification_failed")
    except Exception:
        return unchanged("reuse_verification_failed")

    # Step 2: Multi-format compact-root reduction for remaining older bound reads.
    if v5_transform is not None and recover is not None and intent in (
        "conservative", "navigation", "overview", "aggregate", "task"
    ):
        attempts = 0
        try:
            for index in older_indices:
                if len(changed_indices) >= policy.max_transforms or attempts >= policy.max_transforms:
                    break
                if index not in targets or index in reused_indices:
                    continue
                message = candidate["messages"][index]
                text = message["content"]
                info = verified[index]
                ctype = detect(text, info.source_path)
                # For non-prose types, protect explicit fenced/exact markers.
                if ctype is not ContentType.PROSE and _EXACT_TEXT.search(text):
                    continue
                if ctype is ContentType.PROSE and re.search(r"<exact[-_]answer\b|BEGIN EXACT", text, re.I):
                    continue
                attempts += 1
                result = v5_transform(text, info)
                if (
                    type(result) is not TransformResult
                    or type(result.text) is not str
                    or type(result.recovery_reference) is not str
                    or not result.recovery_reference
                    or not is_compact_root_reference(result.recovery_reference)
                    or not result.text.endswith(result.recovery_reference)
                    or result.text == text
                ):
                    continue
                restored = recover(result.recovery_reference)
                if type(restored) is not str or restored.encode("utf-8") != text.encode("utf-8"):
                    return unchanged("v5_verification_failed")
                message["content"] = result.text
                proposed_wire = serialize_request(candidate)
                proposed_tokens, proposed_bytes = _measure(proposed_wire, count)
                if proposed_tokens >= measured_tokens or proposed_bytes > wire_bytes:
                    message["content"] = text
                    continue
                wire, measured_tokens, wire_bytes = proposed_wire, proposed_tokens, proposed_bytes
                changed_indices.append(index)
        except Exception:
            return unchanged("v5_verification_failed")

    if not _fits(candidate, policy, measured_tokens, wire_bytes):
        return unchanged("cannot_safely_meet_budget")
    if not changed_indices:
        return unchanged("no_eligible_transform")
    return RequestPlan(
        candidate,
        wire,
        "transformed",
        "multi_format_compact_root_v5",
        policy.policy_id,
        tuple(changed_indices),
        before_tokens,
        measured_tokens,
        before_bytes,
        wire_bytes,
    )
