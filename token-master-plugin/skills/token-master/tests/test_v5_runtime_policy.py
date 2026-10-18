"""Tests for request-policy-v5 multi-format compact-root reducer and RuntimeSession integration."""
from __future__ import annotations

import json
from pathlib import Path

from brainspace import tokens
from brainspace.ccr import CCR
from brainspace.pipeline import prepare_request
from brainspace.request_policy import PROTOCOL, RequestPolicy, SourceReadInfo
from brainspace.runtime import ExecutedToolResult, RuntimeSession
from brainspace.runtime_policy import RuntimePolicy
from brainspace.transport import Reply
from brainspace.v5_reducer import (
    compress_code_v5,
    compress_json_v5,
    compress_logs_v5,
    compress_prose_v5,
    is_compact_root_reference,
)


class _LoopbackMockTransport:
    model = "local-mock-v5"
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
        out = json.dumps(
            {
                "id": f"resp_{len(self.sent_wires)}",
                "model": self.model,
                "usage": {
                    "input_tokens": tokens.count_tokens(wire),
                    "output_tokens": 24,
                    "total_tokens": tokens.count_tokens(wire) + 24,
                },
                "output": [{"type": "message", "role": "assistant", "content": "ok"}],
            },
            separators=(",", ":"),
        )
        return Reply(True, "ok", complete=True, input_text=wire, output_text=out, http_status=200)


def test_v5_code_compaction_preserves_signatures_docstrings_and_returns():
    py_source = (
        "import os\n"
        "DEFAULT_LIMIT = 128\n\n"
        "def compute_total(items: list[int], factor: int = 2) -> int:\n"
        '    """Compute the scaled sum of positive items."""\n'
        "    acc = 0\n"
        "    for value in items:\n"
        "        if value > 0:\n"
        "            acc += value * factor\n"
        "        else:\n"
        "            acc -= 1\n"
        "    return acc\n"
    )
    compact = compress_code_v5(py_source, source_path="pkg/math_utils.py")
    assert compact != py_source
    assert len(compact) < len(py_source)
    assert "DEFAULT_LIMIT = 128" in compact
    assert "def compute_total(items: list[int], factor: int = 2) -> int:" in compact
    assert '"""Compute the scaled sum of positive items."""' in compact
    assert "return acc" in compact
    assert "lines elided" in compact


def test_v5_prose_compaction_preserves_tables_lists_and_fences():
    doc = (
        "# Service Configuration Guide\n\n"
        "This introductory paragraph explains how the configuration loader operates across multiple deployment environments. "
        "It includes additional background details that are purely narrative and can be shortened safely on subsequent turns without losing any key facts.\n\n"
        "| Key | Default | Description |\n"
        "| --- | --- | --- |\n"
        "| `PORT` | `8080` | HTTP listen port |\n"
        "| `RETRIES` | `3` | Max retry count |\n\n"
        "1. First check environment variables.\n"
        "2. Next read the local config file.\n\n"
        "```python\n"
        "cfg = load_config(strict=True)\n"
        "```\n"
    )
    compact = compress_prose_v5(doc)
    assert compact != doc
    assert len(compact) < len(doc)
    assert "| `PORT` | `8080` | HTTP listen port |" in compact
    assert "1. First check environment variables." in compact
    assert "2. Next read the local config file." in compact
    assert "cfg = load_config(strict=True)" in compact


def test_v5_prepare_request_reduces_multi_format_older_reads_and_recovers_exact_bytes(tmp_path: Path):
    ccr = CCR(tmp_path / "ccr.sqlite", workspace_root=tmp_path, session_id="s1")
    py_text = (
        "def process_batch(records: list[dict]) -> dict:\n"
        '    """Process all records and return status counts."""\n'
        + "".join(f"    step_{i} = len(records) + {i}\n" for i in range(40))
        + '    return {"ok": len(records), "last": step_39}\n'
    )
    json_text = json.dumps(
        {"service": "router", "routes": [{"path": f"/v1/item/{i}", "enabled": True} for i in range(25)]},
        indent=4,
    )
    latest_text = "Exact newest read stays untouched."

    r1 = SourceReadInfo.from_text(
        call_id="c1", tool_name="read_file", source_path="src/batch.py", content=py_text, status="success"
    )
    r2 = SourceReadInfo.from_text(
        call_id="c2", tool_name="read_file", source_path="config/routes.json", content=json_text, status="success"
    )
    r3 = SourceReadInfo.from_text(
        call_id="c3", tool_name="read_file", source_path="notes.txt", content=latest_text, status="success"
    )

    request = {
        "model": "local-mock-v5",
        "messages": [
            {"role": "system", "content": "You are a helpful coding assistant."},
            {"role": "user", "content": "Inspect src/batch.py and config/routes.json."},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"src/batch.py"}'}}],
            },
            {"role": "tool", "tool_call_id": "c1", "content": py_text},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "c2", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"config/routes.json"}'}}],
            },
            {"role": "tool", "tool_call_id": "c2", "content": json_text},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "c3", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"notes.txt"}'}}],
            },
            {"role": "tool", "tool_call_id": "c3", "content": latest_text},
        ],
    }

    policy = RequestPolicy(version="request-policy-v5", enabled=True, min_tool_chars=256, keep_recent_tool_results=1)
    plan = prepare_request(
        request,
        policy=policy,
        ccr=ccr,
        intent="navigation",
        protocol=PROTOCOL,
        stable_prefix_messages=2,
        source_reads=(r1, r2, r3),
    )
    assert plan.status == "transformed"
    assert plan.changed_message_indices == (3, 5)
    assert plan.tokens_after < plan.tokens_before * 0.55
    # Newest read (index 7) is untouched.
    assert plan.request["messages"][7]["content"] == latest_text

    # Both changed older messages end with a valid compact-root-v1 reference that recovers exact bytes.
    for idx, orig in ((3, py_text), (5, json_text)):
        transformed_text = plan.request["messages"][idx]["content"]
        ref_line = transformed_text.splitlines()[-1]
        assert is_compact_root_reference(ref_line)
        assert ccr.retrieve(ref_line) == orig


def test_v5_runtime_session_achieves_over_30_percent_whole_task_savings(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    files = {
        "src/engine.py": (
            "class QueryEngine:\n"
            '    """Execute bounded queries over indexed records."""\n'
            "    def execute(self, query: str, limit: int = 25) -> list[dict]:\n"
            '        """Run query and return up to limit matching records."""\n'
            + "".join(f"        intermediate_{i} = query.strip() + str({i})\n" for i in range(60))
            + "        return [{'query': query, 'limit': limit, 'count': 60}]\n"
        ),
        "config/settings.json": json.dumps(
            {
                "version": 2,
                "limits": {"max_rows": 60, "max_defs": 8, "timeout_ms": 5000},
                "endpoints": [{"id": f"ep-{i}", "host": f"10.0.0.{i}", "port": 8080 + i} for i in range(30)],
            },
            indent=4,
        ),
        "docs/architecture.md": (
            "# Architecture Overview\n\n"
            + (
                "The query engine processes incoming requests by first validating the schema and then dispatching "
                "to the local storage index. This paragraph contains extended background commentary that is only needed "
                "during initial reading and can be compacted on subsequent turns without losing structural facts.\n\n"
            )
            * 6
            + "| Component | Role | Limit |\n| --- | --- | --- |\n| `QueryEngine` | Executor | `25` |\n"
        ),
        "logs/build.log": "".join(f"[INFO] compiled module_{i}.py\n" for i in range(40)) + "[INFO] build succeeded\n",
    }

    def run_arm(arm_name: str, runtime_policy: RuntimePolicy) -> dict:
        transport = _LoopbackMockTransport()
        session = RuntimeSession(
            workspace=workspace,
            session_id=f"sess-{arm_name}",
            output=tmp_path / f"out-{arm_name}",
            transport=transport,
            runtime_policy=runtime_policy,
        )
        history = [
            {"role": "system", "content": "Complete the repository inspection task accurately."},
            {"role": "user", "content": "Inspect engine.py, settings.json, architecture.md, and build.log, then summarize."},
        ]
        ordered = ["src/engine.py", "config/settings.json", "docs/architecture.md", "logs/build.log"]
        try:
            for step, path in enumerate(ordered, start=1):
                call_id = f"call_{step}"
                args_json = json.dumps({"path": path}, separators=(",", ":"))
                content = session.execute_tool(
                    {"id": call_id, "type": "function", "function": {"name": "read_file", "arguments": args_json}},
                    lambda _name, a: ExecutedToolResult(files[a["path"]], "success"),
                )
                history.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{"id": call_id, "type": "function", "function": {"name": "read_file", "arguments": args_json}}],
                    }
                )
                history.append({"role": "tool", "tool_call_id": call_id, "content": content})
                reply = session.invoke({"model": transport.model, "messages": history}, intent="navigation", stable_prefix_messages=2)
                assert reply.ok
            # Final turn after all reads are in history
            history.append({"role": "assistant", "content": "Ready to verify final summary."})
            history.append({"role": "user", "content": "Confirm final answer JSON."})
            reply = session.invoke({"model": transport.model, "messages": history}, intent="navigation", stable_prefix_messages=2)
            assert reply.ok
            return session.finish(success=True)
        finally:
            session.close()

    baseline_res = run_arm("baseline", RuntimePolicy())
    v5_policy = RuntimePolicy(
        backend="local",
        request_policy=RequestPolicy(version="request-policy-v5", enabled=True, min_tool_chars=256, keep_recent_tool_results=1),
        require_nonexpanding_input=True,
    )
    v5_res = run_arm("v5", v5_policy)

    base_tokens = baseline_res["gateway_reported_tokens"]
    cand_tokens = v5_res["gateway_reported_tokens"]
    savings_pct = (base_tokens - cand_tokens) / base_tokens * 100.0
    assert savings_pct >= 30.0, f"Expected >=30% savings, got {savings_pct:.2f}% ({base_tokens} -> {cand_tokens})"
