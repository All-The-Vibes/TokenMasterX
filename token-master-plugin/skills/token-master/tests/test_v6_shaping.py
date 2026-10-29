"""request-policy-v6: deterministic, cache-safe tool-result shaping."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from brainspace import tokens
from brainspace.request_policy import PROTOCOL, RequestPolicy, plan_request
from brainspace.runtime import ExecutedToolResult, RuntimeSession
from brainspace.runtime_policy import RuntimePolicy
from brainspace.transport import Reply
from brainspace.v6_shaping import READ_BUDGET, SEARCH_BUDGET, fold_paths, fold_search, shape_tool_result

count = tokens.count_tokens
V6 = RequestPolicy(version="request-policy-v6", enabled=True)
DIR = "token-master-plugin\\skills\\token-master\\brainspace\\"


def _unfold_search(folded: str) -> list[str]:
    lines, current = [], None
    for line in folded.split("\n"):
        if line.startswith("  ") and current is not None:
            number, _, rest = line[2:].partition(" ")
            lines.append(f"{current}{number[-1]}{number[:-1]}{number[-1]}{rest}")
        else:
            current = line
    return lines


def test_fold_search_is_lossless_and_smaller():
    raw = "\n".join([f"{DIR}mod.py:{i}:value_{i} = {i}" for i in range(1, 6)]
                    + [f"{DIR}other.py:3:x = 1", f"{DIR}other.py-4-y = 2", f"{DIR}other.py:5:"])
    folded = fold_search(raw)
    assert folded is not None and len(folded) < len(raw)
    assert _unfold_search(folded) == raw.split("\n")


def test_fold_paths_groups_by_directory_losslessly():
    raw = "\n".join([f"{DIR}one.py", f"{DIR}two.py", f"{DIR}compressors\\three.py:4",
                     "[Output truncated: showing 3 of 9 results. Narrow the search.]"])
    folded = fold_paths(raw)
    assert folded == (f"{DIR}\n  one.py\n  two.py\n{DIR}compressors\\\n  three.py:4\n"
                      "[Output truncated: showing 3 of 9 results. Narrow the search.]")
    assert fold_paths("No matches found.") is None
    assert fold_paths("x = 1\ny = 2\nz = 3") is None


def test_oversized_search_becomes_a_digest_that_says_how_to_narrow():
    raw = "\n".join(f"src\\module_{i // 20}.py:{i}:def handler_{i}(request, context): return dispatch(request)"
                    for i in range(400))
    shaped = shape_tool_result("grep", {"pattern": "def "}, raw, count)
    assert count(raw) > SEARCH_BUDGET >= count(shaped) - 150
    assert "more lines not shown" in shaped and "Narrow `pattern`" in shaped
    assert re.search(r"src\\module_\d+\.py \(20\)", shaped)
    assert shaped == shape_tool_result("grep", {"pattern": "def "}, raw, count)
    assert shape_tool_result("grep", {"pattern": "def ", "head_limit": 400}, raw, count) == fold_search(raw)


def test_large_full_read_becomes_an_outline_but_ranged_and_forced_reads_stay_exact():
    body = "".join(f"def function_{i}(value):\n    total = value * {i}\n    return total + {i}\n\n" for i in range(600))
    content = '"""Module docstring."""\nLIMIT = 5\n\n' + body
    shaped = shape_tool_result("view", {"path": "C:\\w\\big.py"}, content, count)
    assert count(content) > READ_BUDGET >= count(shaped)
    assert '1. """Module docstring."""' in shaped and "2. LIMIT = 5" in shaped
    assert "44. def function_10(value):" in shaped and "view_range" in shaped
    assert shape_tool_result("view", {"path": "big.py", "view_range": [1, 900]}, content, count) == content
    assert shape_tool_result("view", {"path": "big.py", "forceReadLargeFiles": True}, content, count) == content


def test_other_tools_keep_head_and_tail():
    content = "\n".join(f"line {i}: " + "x" * 40 for i in range(2000))
    shaped = shape_tool_result("codegraph-codegraph_explore", {}, content, count)
    assert shaped.startswith("line 0:") and shaped.endswith("line 1999: " + "x" * 40)
    assert re.search(r"\[Lines \d+-\d+ of 2000 omitted \(\d+ tokens in full\)", shaped)


def test_errors_and_small_results_are_untouched():
    assert shape_tool_result("grep", {}, "Error: invalid regex", count) == "Error: invalid regex"
    assert shape_tool_result("view", {"path": "a.py"}, "x = 1\n", count) == "x = 1\n"
    assert shape_tool_result("edit", {}, "Edited a.py.", count) == "Edited a.py."


def test_digests_keep_tool_notices_verbatim():
    notice = "[File truncated at 20KB: showing lines 1-2100 of 6000. Use view_range to read more.]"
    content = "".join(f"def f{i}(x):\n    return x + {i}\n\n" for i in range(700)) + notice
    shaped = shape_tool_result("view", {"path": "big.py"}, content, count)
    assert notice in shaped and "Outline only" in shaped
    grep_notice = "[Output truncated: showing 200 of 950 results. Narrow the search.]"
    raw = "\n".join(f"src\\m{i // 20}.py:{i}:value_{i} = compute({i}) + offset" for i in range(200))
    assert grep_notice in shape_tool_result("grep", {"pattern": "value_"}, raw + "\n" + grep_notice, count)


def test_context_lines_with_colon_numbers_never_invent_files():
    raw = "\n".join([f'{DIR}a.py-9-    t = "10:30:00"', f"{DIR}a.py:10:    run(t)", f"{DIR}a.py-11-    done()",
                     f"{DIR}b.py:3:x = 1", f"{DIR}b.py:4:y = 2"])
    folded = fold_search(raw)
    assert folded is not None
    assert [line for line in folded.split("\n") if not line.startswith("  ")] == [f"{DIR}a.py", f"{DIR}b.py"]
    assert _unfold_search(folded) == raw.split("\n")


def test_fold_paths_refuses_anything_it_cannot_keep_exactly():
    assert fold_paths(f"{DIR}one.py\n\n{DIR}two.py\n{DIR}three.py") is None
    assert fold_paths(f"{DIR}one.py\n[section]\n{DIR}two.py\n{DIR}three.py") is None


def test_digests_ignore_a_trailing_newline():
    listing = "\n".join(f"pkg{i % 4}/file_{i:04}.py" for i in sorted(range(1200), key=lambda i: i % 4)) + "\n"
    shaped = shape_tool_result("glob", {"pattern": "**/*.py"}, listing, count)
    assert "more folders" in shaped and " (0)" not in shaped
    search = "\n".join(f"src\\m{i // 100}.py:{i}:result_{i} = compute({i}) + offset" for i in range(700)) + "\n"
    shaped = shape_tool_result("grep", {"pattern": "result_"}, search, count)
    assert "6 more files" in shaped and " (0)" not in shaped


def test_outline_skips_comments_and_uses_headings_only_for_docs():
    code = "".join(f"def f{i}(x):\n    # comment {i}\n    return x + {i}\n\n" for i in range(600))
    shaped = shape_tool_result("view", {"path": "big.py"}, code, count)
    assert "# comment 300" not in shaped and "def f100(x):" in shaped
    doc = "".join(f"# Section {i}\n\n" + "Body text that goes on for a while. " * 12 + "\n\n" for i in range(150))
    assert "# Section 140" in shape_tool_result("view", {"path": "guide.md"}, doc, count)
    assert "# Section 140" not in shape_tool_result("view", {"path": "guide.py"}, doc, count)


def test_v6_rejects_prompt_guidance_that_would_shift_cached_history():
    with pytest.raises(ValueError, match="v6_rejects_instruction_guidance"):
        RuntimePolicy(backend="local", request_policy=V6, require_nonexpanding_input=True, instruction="ponytail")


def _conversation(steps):
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "task"}]
    for i, (name, args, content) in enumerate(steps):
        call = {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
        messages += [{"role": "assistant", "content": None, "tool_calls": [call]},
                     {"role": "tool", "tool_call_id": f"c{i}", "content": content}]
    return {"model": "m", "messages": messages}


def test_shaping_never_changes_earlier_messages_as_the_conversation_grows():
    steps = [
        ("grep", {"pattern": "result_"}, "\n".join(f"src\\m{i % 7}.py:{i}:result_{i} = compute({i}) + offset"
                                                    for i in range(500))),
        ("view", {"path": "big.py"}, "".join(f"def f{i}(x):\n    return x + {i}\n\n" for i in range(900))),
        ("glob", {"pattern": "**/*.py"}, "\n".join(f"{DIR}mod_{i}.py" for i in range(60))),
        ("view", {"path": "big.py", "view_range": [1, 2]}, "1. def f0(x):\n2.     return x + 0"),
    ]
    previous = None
    for n in range(1, len(steps) + 1):
        plan = plan_request(_conversation(steps[:n]), policy=V6, protocol=PROTOCOL, count=count)
        messages = plan.request["messages"]
        if previous is not None:
            assert messages[:len(previous)] == previous  # byte-identical history keeps the provider cache valid
        previous = messages
    assert plan.status == "transformed" and plan.tokens_after < plan.tokens_before
    assert plan.request["messages"][-1]["content"] == steps[-1][2]


class _MockTransport:
    model = "local-mock-v6"
    max_request_bytes = 524288
    max_output_tokens = 2048
    base_url = "http://127.0.0.1:9999/v1"
    reasoning_effort = "low"

    def __init__(self):
        self.sent_wires: list[str] = []

    def encode(self, chat: dict) -> str:
        return json.dumps(chat, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    def send(self, wire: str) -> Reply:
        self.sent_wires.append(wire)
        out = json.dumps({"id": f"resp_{len(self.sent_wires)}", "model": self.model,
                          "usage": {"input_tokens": count(wire), "output_tokens": 8, "total_tokens": count(wire) + 8},
                          "output": [{"type": "message", "role": "assistant", "content": "ok"}]})
        return Reply(True, "ok", complete=True, input_text=wire, output_text=out, http_status=200)


def test_runtime_session_v6_adds_no_recovery_tool_and_keeps_history_stable(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    transport = _MockTransport()
    session = RuntimeSession(
        workspace=workspace, session_id="v6", output=tmp_path / "out", transport=transport,
        runtime_policy=RuntimePolicy(backend="local", request_policy=V6, require_nonexpanding_input=True))
    history = [{"role": "system", "content": "sys"}, {"role": "user", "content": "task"}]
    outputs = ["\n".join(f"src\\m{i % 5}.py:{i}:item_{i} = load({i})" for i in range(400)), "small result"]
    try:
        for step, output in enumerate(outputs):
            call = {"id": f"c{step}", "type": "function",
                    "function": {"name": "grep", "arguments": "{\"pattern\":\"item\"}"}}
            content = session.execute_tool(call, lambda _n, _a, output=output: ExecutedToolResult(output, "success"))
            history += [{"role": "assistant", "content": None, "tool_calls": [call]},
                        {"role": "tool", "tool_call_id": f"c{step}", "content": content}]
            assert session.invoke({"model": transport.model, "messages": history}, stable_prefix_messages=2).ok
        session.finish(success=True)
    finally:
        session.close()
    sent = [json.loads(wire) for wire in transport.sent_wires]
    assert all("tools" not in body for body in sent)
    assert sent[1]["messages"][:len(sent[0]["messages"])] == sent[0]["messages"]
    assert "more lines not shown" in sent[0]["messages"][3]["content"]
