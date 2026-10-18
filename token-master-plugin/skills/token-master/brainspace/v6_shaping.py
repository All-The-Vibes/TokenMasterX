"""Cache-native tool-result shaping for request-policy-v6.

Every tool result is shaped by a pure function of (tool name, arguments, content).
Applying it again on any later request yields identical bytes, so messages the
provider has already cached never change. v5 rewrote older results after they had
been sent; the provider then re-read them at full price, which cost more than it
saved (PRS-1).

* Search output (``path:line:text``) is folded under one header per file.
* Path lists (glob, files-with-matches, counts, directory views) are folded by
  directory. Both folds are lossless.
* A result still larger than its budget becomes a bounded digest that states what
  was left out and how to fetch it: a narrower search, ``view_range``, or
  ``forceReadLargeFiles``. Explicit ranged or forced reads are never shortened, and
  every tool notice (for example "[File truncated ...]") is kept verbatim.
* A shaped result is used only if it is strictly smaller on its own, so whether a
  message is shaped never depends on the rest of the request.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any, Callable

from .request_policy import RequestPlan, RequestPolicy, serialize_request

SEARCH_BUDGET = 1500
READ_BUDGET = 4000
OTHER_BUDGET = 3000

_SEARCH_TOOLS = frozenset({"grep", "rg", "ripgrep", "search", "search_files"})
_LIST_TOOLS = frozenset({"glob", "ls", "list_files", "list_dir", "find_files"})
_READ_TOOLS = frozenset({"view", "read", "read_file"})

_MATCH = re.compile(r"^((?:[A-Za-z]:)?[^:\r\n]+?):(\d+):(.*)$")
_TAIL = re.compile(r"^(\d+)([:-])(.*)$")
_SUSPECT_PATH = re.compile(r"[\"'=(){}<>]|\s{2,}|^\s")
_NOTICE = re.compile(r"^\[.*\]$")
_PATH = re.compile(r"^(?:[A-Za-z]:)?[^\s:*?\"<>|]+(?: [^\s:*?\"<>|]+)*(?::\d+)?$")
_CODE_OUTLINE = re.compile(
    r"^\s*(?:(?:async\s+)?def\s|class\s|@[\w.]+|(?:pub(?:\(crate\))?\s+)?(?:fn|struct|enum|trait|impl|mod)\s"
    r"|(?:export\s+)?(?:function|interface|type)\s)")
_CONSTANT = re.compile(r"^[A-Z][A-Z0-9_]*\s*[:=]")
_JSON_KEY = re.compile(r'^\s{0,4}"[^"\n]+"\s*:')
_HEADING = re.compile(r"^#{1,6}\s")
_DOC_SUFFIXES = (".md", ".markdown", ".rst")


def tool_kind(name: str) -> str:
    lowered = name.lower() if isinstance(name, str) else ""
    if lowered in _SEARCH_TOOLS:
        return "search"
    if lowered in _LIST_TOOLS:
        return "list"
    if lowered in _READ_TOOLS:
        return "read"
    return "other"


def _owner(path: str, line: str) -> bool:
    if not line.startswith(path) or len(line) <= len(path) or line[len(path)] not in ":-":
        return False
    tail = _TAIL.match(line[len(path) + 1:])
    return bool(tail) and tail.group(2) == line[len(path)]


def fold_search(text: str) -> str | None:
    """Group ``path:line:text`` (match) and ``path-line-text`` (context) lines by path.

    Headers come only from match lines whose path looks like a path, so a context
    line such as ``a.py-9-t = "10:30:00"`` can never invent a file.
    """
    lines = text.split("\n")
    paths = {m.group(1) for m in map(_MATCH.match, lines) if m and not _SUSPECT_PATH.search(m.group(1))}
    if not paths:
        return None
    longest_first = sorted(paths, key=len, reverse=True)
    out: list[str] = []
    current: str | None = None
    folded = 0
    for line in lines:
        owner = current if current is not None and _owner(current, line) else next(
            (path for path in longest_first if _owner(path, line)), None)
        if owner is None:
            current = None
            out.append(line)
            continue
        if owner != current:
            out.append(owner)
            current = owner
        tail = _TAIL.match(line[len(owner) + 1:])
        assert tail is not None
        out.append(f"  {tail.group(1)}{tail.group(2)} {tail.group(3)}")
        folded += 1
    if folded < 2:
        return None
    result = "\n".join(out)
    return result if len(result) < len(text) else None


def fold_paths(text: str) -> str | None:
    """Group a newline-separated path list by parent directory; refuse anything not lossless."""
    lines = text.split("\n")
    while lines and not lines[-1]:
        lines.pop()
    entries: list[str] = []
    notices: list[str] = []
    for line in lines:
        if not line:
            return None
        if _NOTICE.match(line):
            notices.append(line)
        elif notices or not (_PATH.match(line) and ("\\" in line or "/" in line)):
            return None
        else:
            entries.append(line)
    if len(entries) < 3:
        return None
    out: list[str] = []
    current: str | None = None
    for entry in entries:
        bare = entry.rstrip("\\/")
        cut = max(bare.rfind("\\"), bare.rfind("/"))
        head, name = entry[:cut + 1], entry[cut + 1:]
        if head != current:
            out.append(head or ".")
            current = head
        out.append("  " + name)
    result = "\n".join(out + notices)
    return result if len(result) < len(text) else None


def _digest_lines(text: str, budget: int, count: Callable[[str], int], total: int, kind: str,
                  folded: bool) -> str:
    lines = text.split("\n")
    notices = [line for line in lines if _NOTICE.match(line)]
    body = [line for line in lines if not _NOTICE.match(line)]
    kept: list[str] = []
    used = 0
    for line in body:
        cost = count(line) + 1
        if used + cost > int(budget * 0.85):
            break
        kept.append(line)
        used += cost
    rest = body[len(kept):]
    if not rest:
        return text
    parts = [f"{len(rest)} more lines not shown ({total} tokens in full)"]
    if folded:
        continuation = 0
        groups: list[list[Any]] = []
        for line in rest:
            if line.startswith("  "):
                if groups:
                    groups[-1][1] += 1
                else:
                    continuation += 1
            else:
                groups.append([line, 0])
        last = next((line for line in reversed(kept) if not line.startswith("  ")), None)
        if continuation and last:
            parts.append(f"{continuation} more under {last[:120]}")
        if groups:
            named = ", ".join(f"{head[:120]} ({n})" for head, n in groups[:12]) + (", ..." if len(groups) > 12 else "")
            parts.append(f"{len(groups)} more {'files' if kind == 'search' else 'folders'}: {named}")
    how = ("Narrow `pattern`, `path` or `glob`, or use output_mode=\"count\""
           if kind == "search" else "Narrow `pattern` or `path`")
    return "\n".join(kept + [f"[{'; '.join(parts)}. {how} to see them.]"] + notices)


def _outline_line(line: str, path: str) -> bool:
    if _CODE_OUTLINE.match(line) or _CONSTANT.match(line) or _JSON_KEY.match(line):
        return True
    return bool(_HEADING.match(line)) and path.lower().endswith(_DOC_SUFFIXES)


def _digest_read(text: str, budget: int, count: Callable[[str], int], total: int, path: str) -> str:
    lines = text.split("\n")
    notices = [line for line in lines if _NOTICE.match(line)]
    out: list[str] = []
    used = 0
    stopped = None
    for number, line in enumerate(lines, 1):
        if _NOTICE.match(line) or (number > 25 and not _outline_line(line, path)):
            continue
        width = 200 if number <= 25 else 160
        entry = f"{number}. {line[:width]}" + (" [cut]" if len(line) > width else "")
        cost = count(entry) + 1
        if used + cost > int(budget * 0.9):
            stopped = number
            break
        out.append(entry)
        used += cost
    shown = len(lines) - len(notices)
    note = (f"[Outline only: {shown} lines ({total} tokens) exceed the {budget}-token read budget. Numbers are "
            "original line numbers; lines marked [cut] are shortened. "
            + (f"The outline stops before line {stopped}. " if stopped else "")
            + "Call view with view_range=[start, end] for exact text, or forceReadLargeFiles=true for everything.]")
    return "\n".join(out + notices + [note])


def _digest_other(text: str, budget: int, count: Callable[[str], int], total: int) -> str:
    lines = text.split("\n")
    head: list[str] = []
    used = 0
    for line in lines:
        cost = count(line) + 1
        if used + cost > int(budget * 0.6):
            break
        head.append(line)
        used += cost
    tail: list[str] = []
    used = 0
    for line in reversed(lines[len(head):]):
        cost = count(line) + 1
        if used + cost > int(budget * 0.3):
            break
        tail.append(line)
        used += cost
    tail.reverse()
    how = "Re-run the tool with narrower arguments to see them."
    if head or tail:
        if len(head) + len(tail) >= len(lines):
            return text
        first, last = len(head) + 1, len(lines) - len(tail)
        return "\n".join(head + [f"[Lines {first}-{last} of {len(lines)} omitted ({total} tokens in full). {how}]"]
                         + tail)
    start, end = text[:budget * 2], text[-budget:]  # one enormous line: keep both ends, bounded by tokens
    while start and count(start) > int(budget * 0.6):
        start = start[:len(start) * 4 // 5]
    while end and count(end) > int(budget * 0.3):
        end = end[len(end) // 5:]
    note = (f"[Characters {len(start) + 1}-{len(text) - len(end)} of {len(text)} omitted "
            f"({total} tokens in full). {how}]")
    return start + "\n" + note + "\n" + end


def _wire_size(text: str) -> int:
    return len(json.dumps(text, ensure_ascii=False).encode("utf-8"))


def shape_tool_result(name: str, arguments: dict[str, Any], content: Any, count: Callable[[str], int]) -> Any:
    """Pure and deterministic: the same input always yields the same output."""
    if type(content) is not str or not content or content.startswith("Error"):
        return content
    kind = tool_kind(name)
    path = str(arguments.get("path") or arguments.get("file_path") or "")
    if kind == "read" and (arguments.get("view_range") is not None or arguments.get("forceReadLargeFiles") is True
                           or "offset" in arguments or "limit" in arguments):
        return content
    text, folded = content, False
    if kind == "search":
        candidate = fold_search(content) or fold_paths(content)
        if candidate is not None:
            text, folded = candidate, True
    elif kind in ("list", "read"):
        candidate = fold_paths(content)
        if candidate is not None:
            text, folded, kind = candidate, True, "list"
    if not (kind == "search" and "head_limit" in arguments):
        budget = {"search": SEARCH_BUDGET, "list": SEARCH_BUDGET, "read": READ_BUDGET}.get(kind, OTHER_BUDGET)
        if count(text) > budget:
            total = count(content)
            if kind in ("search", "list"):
                digest = _digest_lines(text, budget, count, total, kind, folded)
            elif kind == "read":
                digest = _digest_read(text, budget, count, total, path)
            else:
                digest = _digest_other(text, budget, count, total)
            if len(digest) < len(text):
                text = digest
    # Accept only a strict saving of this message alone, so the request-level guards
    # never need to revert it and its bytes never depend on other messages.
    if text != content and count(text) < count(content) and _wire_size(text) <= _wire_size(content):
        return text
    return content


def plan_v6_request(
    request: Any, *, policy: RequestPolicy, indices: list[int], exact_message_indices: tuple[int, ...],
    original_wire: str, before_tokens: int, before_bytes: int, count: Callable[[str], int],
) -> RequestPlan:
    """Shape every tool result; position-independent, so earlier bytes never change."""
    def unchanged(reason: str) -> RequestPlan:
        return RequestPlan(request, original_wire, "unchanged", reason, policy.policy_id,
                           tokens_before=before_tokens, tokens_after=before_tokens,
                           wire_bytes_before=before_bytes, wire_bytes_after=before_bytes)

    candidate = copy.deepcopy(request)
    calls = {call["id"]: call["function"] for message in candidate["messages"]
             for call in message.get("tool_calls") or []}
    changed: list[int] = []
    for index in indices:
        if index in exact_message_indices:
            continue
        message = candidate["messages"][index]
        function = calls.get(message.get("tool_call_id"))
        if function is None or type(message.get("content")) is not str:
            continue
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except ValueError:
            arguments = {}
        shaped = shape_tool_result(function.get("name", ""), arguments if type(arguments) is dict else {},
                                   message["content"], count)
        if shaped != message["content"]:
            message["content"] = shaped
            changed.append(index)
    if not changed:
        return unchanged("no_oversized_or_foldable_results")
    wire = serialize_request(candidate)
    after_tokens, after_bytes = count(wire), len(wire.encode("utf-8"))
    if after_tokens >= before_tokens or after_bytes > before_bytes:
        return unchanged("shaping_not_smaller")
    return RequestPlan(candidate, wire, "transformed", "cache_native_shaping_v6", policy.policy_id,
                       changed_message_indices=tuple(changed), tokens_before=before_tokens,
                       tokens_after=after_tokens, wire_bytes_before=before_bytes, wire_bytes_after=after_bytes)
