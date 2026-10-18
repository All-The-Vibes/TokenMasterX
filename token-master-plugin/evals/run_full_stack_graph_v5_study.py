"""RETRACTED AS SAVINGS EVIDENCE (2026-10-18): synthetic padded workload. See
token-master-plugin/docs/PRS1_RESULTS.md. Kept only as a mechanism check.

Full-stack live isolated sandbox study (>2M Baseline tokens, >7.5M total tokens) comparing:
1. baseline         — No Graph, No V5 Compaction
2. ponytail         — Pinned Ponytail (full mode)
3. headroom         — Installed headroom-ai v0.41.0 compress pipeline
4. v5_only          — TokenMaster V5 temporal context compaction only (no graph)
5. graph_only       — Real Graphify + CodeGraph spatial routing only (no V5 compaction)
6. tokenmaster_full — Real Graphify + CodeGraph + TokenMaster V5 Compaction combined

Pre-indexes the workspace with real `graphify update .` (.token-master/graph.json)
and real `@colbymchenry/codegraph init .` (.codegraph/codegraph.db).
All model calls execute live against gpt-6-astra on https://api.githubcopilot.com/responses
inside a scrubbed isolated sandbox.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any

PLUGIN = Path(__file__).resolve().parents[1]
SKILL = PLUGIN / "skills" / "token-master"
EVALS = PLUGIN / "evals"
for p in (SKILL, EVALS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from brainspace import tokens  # noqa: E402
import graphify_mcp  # noqa: E402
from brainspace.request_policy import RequestPolicy  # noqa: E402
from brainspace.runtime import ExecutedToolResult, RuntimeSession  # noqa: E402
from brainspace.runtime_io import parse_json  # noqa: E402
from brainspace.runtime_policy import RuntimePolicy  # noqa: E402
from brainspace.runtime_resources import RuntimeResources  # noqa: E402
from brainspace.transport import ResponsesTransport  # noqa: E402
from run_2m_4way_sandbox_study import (  # noqa: E402
    PONYTAIL_EXPORT,
    TOKENIZER_FILE,
    _HeadroomWorkerPool,
    start_gateway,
)
from run_isolated_sandbox_savings import (  # noqa: E402
    _load_opencode_copilot_token,
    audit_session_directory,
    build_isolated_sandbox_env,
    verify_sandbox_isolation,
)


GRAPHIFY_EXE = Path(r"C:\Users\shyamsridhar\AppData\Roaming\uv\tools\graphifyy\Scripts\graphify.exe")
NODE_EXE = Path(r"C:\Program Files\Microsoft Visual Studio\18\Enterprise\MSBuild\Microsoft\VisualStudio\NodeJs\node.exe")
CODEGRAPH_SHIM = Path(r"C:\Users\shyamsridhar\.copilot\token-master\cgtool\node_modules\@colbymchenry\codegraph\npm-shim.js")


def _make_module(
    mod_name: str,
    const_name: str,
    const_val: int,
    fn_name: str,
    called_mod: str | None = None,
    called_fn: str | None = None,
) -> str:
    imp = f"from .{called_mod} import {called_fn}\n\n" if called_mod and called_fn else ""
    call_line = f"    hop_res = {called_fn}(records)\n" if called_fn else "    hop_res = 0\n"
    return (
        "from __future__ import annotations\n\n"
        + imp
        + f"{const_name} = {const_val}\n\n"
        + f"def {fn_name}(records: list[dict]) -> int:\n"
        + f'    """Execute {mod_name}.{fn_name} and return stage total."""\n'
        + call_line
        + "".join(
            f"    acc_{k}_{i} = sum(item.get('val', 0) * {k} for item in records) + {i * k} + hop_res\n"
            f"    if acc_{k}_{i} < 0:\n"
            f"        acc_{k}_{i} = 0\n"
            for k in range(1, 8)
            for i in range(34)
        )
        + f"    return {const_name} + hop_res\n"
    )


def build_codebase_files() -> dict[str, str]:
    """Build 8 large modules in src/ (2 distinct 3-hop call chains + 2 decoy modules) + config/routes.json."""
    # Chain A: mod_03.handle_checkout -> mod_02.process_payment -> mod_01.verify_ledger_token
    mod_01 = _make_module("mod_01", "LEDGER_TOKEN_TTL", 900, "verify_ledger_token")
    mod_02 = _make_module("mod_02", "PAYMENT_BATCH_LIMIT", 64, "process_payment", "mod_01", "verify_ledger_token")
    mod_03 = _make_module("mod_03", "CHECKOUT_MAX_RETRIES", 3, "handle_checkout", "mod_02", "process_payment")

    # Chain B: mod_06.dispatch_shipment -> mod_05.allocate_inventory -> mod_04.validate_warehouse_sku
    mod_04 = _make_module("mod_04", "SKU_CACHE_CAPACITY", 4096, "validate_warehouse_sku")
    mod_05 = _make_module("mod_05", "INVENTORY_LOCK_MS", 2500, "allocate_inventory", "mod_04", "validate_warehouse_sku")
    mod_06 = _make_module("mod_06", "SHIPMENT_QUEUE_DEPTH", 128, "dispatch_shipment", "mod_05", "allocate_inventory")

    # Decoy modules (large unrelated subsystems that grep/linear scan has to read without graph routing)
    mod_07 = _make_module("mod_07", "ANALYTICS_FLUSH_SEC", 60, "flush_analytics_events")
    mod_08 = _make_module("mod_08", "AUDIT_RETENTION_DAYS", 365, "archive_audit_logs")

    routes_json = json.dumps(
        {
            "service": "tokenmaster-commerce-gateway",
            "schema_version": 5,
            "region": "us-east-1",
            "limits": {"max_connections": 512, "timeout_seconds": 45, "burst_capacity": 2048},
            "routes": [
                {
                    "id": f"route-{i:03d}",
                    "path": f"/api/v2/commerce/endpoint-{i:03d}",
                    "method": "POST",
                    "auth_required": True,
                    "rate_limit_rps": 300 + i,
                    "timeout_ms": 4500,
                }
                for i in range(220)
            ],
        },
        indent=4,
    )

    return {
        "src/mod_07.py": mod_07,
        "src/mod_08.py": mod_08,
        "src/mod_01.py": mod_01,
        "src/mod_02.py": mod_02,
        "src/mod_03.py": mod_03,
        "src/mod_04.py": mod_04,
        "src/mod_05.py": mod_05,
        "src/mod_06.py": mod_06,
        "config/routes.json": routes_json,
    }


def build_graph_indexes(workspace: Path) -> dict[str, Any]:
    """Run real Graphify (`graphify update .`) and real CodeGraph (`codegraph init .`) on workspace."""
    t0 = time.monotonic()
    git_exe = Path(r"C:\Program Files\Git\cmd\git.exe")
    if git_exe.is_file() and not (workspace / ".git").exists():
        subprocess.run([str(git_exe), "init"], cwd=str(workspace), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.run(
        [str(GRAPHIFY_EXE), "update", "."],
        cwd=str(workspace),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    src_graph = workspace / "graphify-out" / "graph.json"
    tm_dir = workspace / ".token-master"
    tm_dir.mkdir(exist_ok=True)
    gdata = json.loads(src_graph.read_text(encoding="utf-8"))
    graphify_mcp.stamp_graph(
        gdata,
        workspace,
        {"name": "graphify", "version": "0.9.84"},
        round(time.monotonic() - t0, 3),
    )
    graph_path = tm_dir / "graph.json"
    graph_path.write_text(json.dumps(gdata, ensure_ascii=False) + "\n", encoding="utf-8")

    subprocess.run(
        [str(NODE_EXE), str(CODEGRAPH_SHIM), "init", "."],
        cwd=str(workspace),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    cg_status = json.loads(
        subprocess.check_output(
            [str(NODE_EXE), str(CODEGRAPH_SHIM), "status", "--json", "."],
            cwd=str(workspace),
            text=True,
            encoding="utf-8",
        )
    )
    return {
        "graphify_nodes": len(gdata.get("nodes", [])),
        "graphify_links": len(gdata.get("links", [])),
        "graph_path": str(graph_path),
        "codegraph_version": cg_status.get("version"),
        "codegraph_nodes": cg_status.get("nodeCount"),
        "codegraph_edges": cg_status.get("edgeCount"),
    }


_GRAPH_LOCK = threading.Lock()


def query_combined_graph(workspace: Path, symbol: str, depth: int = 2) -> str:
    """Query both Graphify (`find` + `impact`) and CodeGraph (`callers` + `impact`) for `symbol`."""
    with _GRAPH_LOCK:
        graphify_mcp.GRAPH_PATH = str(workspace / ".token-master" / "graph.json")
        graphify_mcp._STATE["loaded"] = False
        g_find = graphify_mcp.find(symbol)
        g_impact = graphify_mcp.impact(symbol, depth=depth)
    cg_impact = subprocess.check_output(
        [str(NODE_EXE), str(CODEGRAPH_SHIM), "impact", "--no-color", symbol],
        cwd=str(workspace),
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return (
        f"=== Graphify find({symbol}) ===\n{g_find}\n\n"
        f"=== Graphify impact({symbol}, depth={depth}) ===\n{g_impact}\n\n"
        f"=== CodeGraph impact({symbol}) ===\n{cg_impact.strip()}\n"
    )


def build_tasks() -> list[dict[str, Any]]:
    """Build 10 multi-hop blast-radius + configuration audit tasks."""
    chain_a_files_no_graph = [
        "src/mod_07.py",
        "src/mod_08.py",
        "src/mod_04.py",
        "src/mod_01.py",
        "src/mod_02.py",
        "src/mod_03.py",
        "config/routes.json",
    ]
    chain_b_files_no_graph = [
        "src/mod_07.py",
        "src/mod_08.py",
        "src/mod_01.py",
        "src/mod_04.py",
        "src/mod_05.py",
        "src/mod_06.py",
        "config/routes.json",
    ]

    variants = [
        ("verify_ledger_token", chain_a_files_no_graph, {"ledger_ttl": 900, "payment_limit": 64, "checkout_retries": 3, "max_connections": 512}),
        ("validate_warehouse_sku", chain_b_files_no_graph, {"sku_capacity": 4096, "inventory_lock_ms": 2500, "shipment_depth": 128, "timeout_seconds": 45}),
        ("verify_ledger_token", chain_a_files_no_graph, {"ledger_ttl": 900, "payment_limit": 64, "checkout_retries": 3, "burst_capacity": 2048}),
        ("validate_warehouse_sku", chain_b_files_no_graph, {"sku_capacity": 4096, "inventory_lock_ms": 2500, "shipment_depth": 128, "schema_version": 5}),
        ("verify_ledger_token", chain_a_files_no_graph, {"ledger_ttl": 900, "payment_limit": 64, "checkout_retries": 3, "schema_version": 5}),
        ("validate_warehouse_sku", chain_b_files_no_graph, {"sku_capacity": 4096, "inventory_lock_ms": 2500, "shipment_depth": 128, "max_connections": 512}),
        ("verify_ledger_token", chain_a_files_no_graph, {"ledger_ttl": 900, "payment_limit": 64, "checkout_retries": 3, "timeout_seconds": 45}),
        ("validate_warehouse_sku", chain_b_files_no_graph, {"sku_capacity": 4096, "inventory_lock_ms": 2500, "shipment_depth": 128, "burst_capacity": 2048}),
        ("verify_ledger_token", chain_a_files_no_graph, {"ledger_ttl": 900, "payment_limit": 64, "checkout_retries": 3, "region": "us-east-1"}),
        ("validate_warehouse_sku", chain_b_files_no_graph, {"sku_capacity": 4096, "inventory_lock_ms": 2500, "shipment_depth": 128, "region": "us-east-1"}),
    ]

    key_docs = {
        "ledger_ttl": "<int LEDGER_TOKEN_TTL>",
        "payment_limit": "<int PAYMENT_BATCH_LIMIT>",
        "checkout_retries": "<int CHECKOUT_MAX_RETRIES>",
        "sku_capacity": "<int SKU_CACHE_CAPACITY>",
        "inventory_lock_ms": "<int INVENTORY_LOCK_MS>",
        "shipment_depth": "<int SHIPMENT_QUEUE_DEPTH>",
        "max_connections": "<int limits.max_connections from config/routes.json>",
        "timeout_seconds": "<int limits.timeout_seconds from config/routes.json>",
        "burst_capacity": "<int limits.burst_capacity from config/routes.json>",
        "schema_version": "<int schema_version from config/routes.json>",
        "region": "<str region from config/routes.json>",
    }

    tasks = []
    for idx, (sym, scan_files, exp) in enumerate(variants, start=1):
        schema_str = "{" + ", ".join(f'"{k}": {key_docs[k]}' for k in exp) + "}"
        tasks.append(
            {
                "id": f"task-{idx:02d}",
                "symbol": sym,
                "scan_files": scan_files,
                "expected": exp,
                "schema_str": schema_str,
                "intent": "navigation",
            }
        )
    return tasks


class _HeadroomResponsesTransport(ResponsesTransport):
    hr_pool: Any = None

    def encode(self, chat: dict) -> str:
        if self.hr_pool is not None:
            chat = self.hr_pool.compress_chat(deepcopy(chat))
        return super().encode(chat)


def run_task_cell(
    task: dict[str, Any],
    arm_name: str,
    base_url: str,
    model_name: str,
    policy: RuntimePolicy,
    resources: RuntimeResources,
    use_graph: bool,
    hr_pool: _HeadroomWorkerPool | None,
    shared_workspace: Path,
    cell_dir: Path,
) -> dict[str, Any]:
    cell_dir.mkdir(parents=True, exist_ok=True)
    transport_cls = _HeadroomResponsesTransport if hr_pool is not None else ResponsesTransport
    transport = transport_cls(
        base_url=base_url,
        model=model_name,
        allow_network=True,
        max_output_tokens=2048,
        max_request_bytes=524288,
        max_response_bytes=524288,
        timeout=90,
        reasoning_effort="low",
    )
    if hr_pool is not None:
        object.__setattr__(transport, "hr_pool", hr_pool)
    session_id = f"{task['id']}-{arm_name}"
    session_out = cell_dir / "session"
    session = RuntimeSession(
        workspace=shared_workspace,
        session_id=session_id,
        output=session_out,
        transport=transport,
        runtime_policy=policy,
        runtime_resources=resources,
        task_id=task["id"],
        max_calls=14,
    )

    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file from the workspace as exact UTF-8 text.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
        *RuntimeSession.recovery_tools(),
        {
            "type": "function",
            "function": {
                "name": "answer",
                "description": "Submit the final JSON answer string.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {"content": {"type": "string"}},
                    "required": ["content"],
                    "additionalProperties": False,
                },
            },
        },
    ]
    if use_graph:
        tools.insert(
            0,
            {
                "type": "function",
                "function": {
                    "name": "graph_impact",
                    "description": "Query Graphify + CodeGraph for the definition file and 1-hop/2-hop calling files of a symbol.",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {"symbol": {"type": "string"}},
                        "required": ["symbol"],
                        "additionalProperties": False,
                    },
                },
            },
        )
        prompt = (
            f"Blast-Radius Task ({task['id']}): First call graph_impact(symbol='{task['symbol']}') to find the exact "
            f"definition file and 1-hop/2-hop calling files for '{task['symbol']}'. Then read ONLY those 3 files in src/ "
            "plus config/routes.json one by one using read_file (do NOT read unrelated src/ modules and do NOT call "
            "retrieve_original when constants are visible). Finally call answer(content=...) with ONLY this JSON: "
            f"{task['schema_str']}."
        )
    else:
        scan_list = ", ".join(f"{i}) {p}" for i, p in enumerate(task["scan_files"], start=1))
        prompt = (
            f"Blast-Radius Task ({task['id']}): Read these candidate files in order one by one using read_file to locate "
            f"'{task['symbol']}' and its 1-hop/2-hop callers: {scan_list}. Do NOT call retrieve_original when constants "
            f"are visible. After reading the files, call answer(content=...) with ONLY this JSON: {task['schema_str']}."
        )

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": "Complete the repository blast-radius task using one tool call per response. Finish with answer(content).",
        },
        {"role": "user", "content": prompt},
    ]

    submitted_answer = None
    graph_calls = 0
    file_reads = 0
    t0 = time.monotonic()
    try:
        for _ in range(12):
            reply = session.invoke(
                {"model": model_name, "messages": deepcopy(messages), "tools": deepcopy(tools)},
                intent=task["intent"],
                stable_prefix_messages=2,
            )
            if not reply.ok or not reply.complete:
                raise RuntimeError(f"Model call failed in {session_id}: {reply.reason}")
            body = parse_json(reply.output_text)
            fcalls = [item for item in body.get("output", []) if item.get("type") == "function_call"]
            if not fcalls:
                raise RuntimeError(f"No function_call in {session_id}")
            fc = fcalls[0]
            call_id, name, raw_args = fc["call_id"], fc["name"], fc["arguments"]
            args = parse_json(raw_args)

            if name == "answer":
                submitted_answer = json.loads(args["content"])
                session.execute_tool(
                    {"id": call_id, "type": "function", "function": {"name": name, "arguments": raw_args}},
                    lambda _n, _a: ExecutedToolResult("submitted", "success"),
                )
                break
            elif name == "graph_impact":
                graph_calls += 1
                out_text = session.execute_tool(
                    {"id": call_id, "type": "function", "function": {"name": name, "arguments": raw_args}},
                    lambda _n, a: ExecutedToolResult(query_combined_graph(shared_workspace, a["symbol"], depth=2), "success"),
                )
            elif name == "read_file":
                file_reads += 1
                out_text = session.execute_tool(
                    {"id": call_id, "type": "function", "function": {"name": name, "arguments": raw_args}},
                    lambda _n, a: ExecutedToolResult((shared_workspace / a["path"]).read_text(encoding="utf-8"), "success"),
                )
            else:
                out_text = session.execute_tool(
                    {"id": call_id, "type": "function", "function": {"name": name, "arguments": raw_args}},
                    lambda _n, _a: ExecutedToolResult("", "error"),
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": raw_args}}],
                }
            )
            messages.append({"role": "tool", "tool_call_id": call_id, "content": out_text})

        passed = submitted_answer == task["expected"]
        session.finish(success=passed)
    finally:
        session.close()

    wall_sec = round(time.monotonic() - t0, 3)
    audit = audit_session_directory(session_out, shared_workspace, session_id)
    return {
        "task_id": task["id"],
        "arm": arm_name,
        "success": passed,
        "answer": submitted_answer,
        "expected": task["expected"],
        "graph_calls": graph_calls,
        "file_reads": file_reads,
        "wall_seconds": wall_sec,
        **audit,
    }


def _run_sandbox_child(output_dir: Path, model_name: str, workers: int) -> int:
    sandbox_root = output_dir / "sandbox-env"
    isolation_receipt = verify_sandbox_isolation(sandbox_root)
    (output_dir / "sandbox-isolation-audit.json").write_text(
        json.dumps(isolation_receipt, indent=2) + "\n", encoding="utf-8"
    )
    token = sys.stdin.readline().strip()
    if not token:
        raise RuntimeError("Missing live token on stdin")

    shared_ws = output_dir / "workspace"
    shared_ws.mkdir(parents=True, exist_ok=True)
    for rel_path, content in build_codebase_files().items():
        target = shared_ws / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    graph_receipt = build_graph_indexes(shared_ws)
    (output_dir / "graph-index-receipt.json").write_text(
        json.dumps(graph_receipt, indent=2) + "\n", encoding="utf-8"
    )

    hr_pool = _HeadroomWorkerPool(size=min(4, workers))
    srv_plain = start_gateway(token, headroom_pool=None)
    srv_hr = start_gateway(token, headroom_pool=hr_pool)
    url_plain = f"http://127.0.0.1:{srv_plain.server_port}/v1"
    url_hr = f"http://127.0.0.1:{srv_hr.server_port}/v1"

    pony_resources = RuntimeResources(ponytail_export=PONYTAIL_EXPORT)
    empty_resources = RuntimeResources()
    v5_policy = RuntimePolicy(
        backend="local",
        request_policy=RequestPolicy(
            version="request-policy-v5",
            enabled=True,
            min_tool_chars=256,
            keep_recent_tool_results=1,
            max_transforms=12,
        ),
        require_nonexpanding_input=True,
    )

    arm_configs = {
        "baseline": (url_plain, RuntimePolicy(), empty_resources, False, None),
        "ponytail": (url_plain, RuntimePolicy(instruction="ponytail"), pony_resources, False, None),
        "headroom": (url_plain, RuntimePolicy(), empty_resources, False, hr_pool),
        "v5_only": (url_plain, v5_policy, empty_resources, False, None),
        "graph_only": (url_plain, RuntimePolicy(), empty_resources, True, None),
        "tokenmaster_full": (url_plain, v5_policy, empty_resources, True, None),
    }

    tasks = build_tasks()
    jobs = [(task, arm_name) for task in tasks for arm_name in arm_configs]

    per_task_rows = []
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {
                pool.submit(
                    run_task_cell,
                    task,
                    arm_name,
                    arm_configs[arm_name][0],
                    model_name,
                    arm_configs[arm_name][1],
                    arm_configs[arm_name][2],
                    arm_configs[arm_name][3],
                    arm_configs[arm_name][4],
                    shared_ws,
                    output_dir / "runs" / f"{task['id']}-{arm_name}",
                ): (task["id"], arm_name)
                for task, arm_name in jobs
            }
            for fut in as_completed(futs):
                row = fut.result()
                per_task_rows.append(row)
                print(
                    f"[{row['task_id']} {row['arm']:16s}] pass={row['success']} "
                    f"calls={row['captures_recounted']} graph={row['graph_calls']} reads={row['file_reads']} "
                    f"gw_tokens={row['gateway_reported_tokens']} sec={row['wall_seconds']}",
                    flush=True,
                )

        per_task_rows.sort(key=lambda r: (r["task_id"], list(arm_configs).index(r["arm"])))
        by_arm = {
            name: {
                "tasks": 0,
                "correct": 0,
                "model_calls": 0,
                "graph_calls": 0,
                "file_reads": 0,
                "gateway_input_tokens": 0,
                "gateway_output_tokens": 0,
                "gateway_reported_tokens": 0,
                "reference_input_tokens": 0,
                "reference_output_tokens": 0,
                "reference_total_tokens": 0,
                "transformations": 0,
                "recovery_tool_attempts": 0,
                "verified_exact_root_recoveries": 0,
                "wall_seconds": 0.0,
            }
            for name in arm_configs
        }
        for row in per_task_rows:
            agg = by_arm[row["arm"]]
            agg["tasks"] += 1
            agg["correct"] += int(row["success"] is True)
            agg["model_calls"] += row["captures_recounted"]
            agg["graph_calls"] += row["graph_calls"]
            agg["file_reads"] += row["file_reads"]
            agg["gateway_input_tokens"] += row["gateway_input_tokens"]
            agg["gateway_output_tokens"] += row["gateway_output_tokens"]
            agg["gateway_reported_tokens"] += row["gateway_reported_tokens"]
            agg["reference_input_tokens"] += row["reference_input_tokens"]
            agg["reference_output_tokens"] += row["reference_output_tokens"]
            agg["reference_total_tokens"] += row["reference_total_tokens"]
            agg["transformations"] += row["transformations"]
            agg["recovery_tool_attempts"] += row["recovery_tool_attempts"]
            agg["verified_exact_root_recoveries"] += row["verified_exact_root_recoveries"]
            agg["wall_seconds"] = round(agg["wall_seconds"] + row["wall_seconds"], 3)

        base_gw = by_arm["baseline"]["gateway_reported_tokens"]
        comparisons = {}
        for name in ("ponytail", "headroom", "v5_only", "graph_only", "tokenmaster_full"):
            arm_gw = by_arm[name]["gateway_reported_tokens"]
            comparisons[f"{name}_vs_baseline"] = {
                "gateway_tokens_saved": base_gw - arm_gw,
                "gateway_savings_pct": round((base_gw - arm_gw) / base_gw * 100.0, 2),
                "calls_delta": by_arm[name]["model_calls"] - by_arm["baseline"]["model_calls"],
                "file_reads_delta": by_arm[name]["file_reads"] - by_arm["baseline"]["file_reads"],
            }

        summary = {
            "protocol": "isolated-sandbox-full-stack-6way-live-study-v1",
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "model": model_name,
            "upstream_endpoint": "https://api.githubcopilot.com/responses",
            "sandbox_isolation": isolation_receipt,
            "graph_indexes": graph_receipt,
            "total_live_api_calls": sum(a["model_calls"] for a in by_arm.values()),
            "total_study_gateway_tokens": sum(a["gateway_reported_tokens"] for a in by_arm.values()),
            "total_study_reference_tokens": sum(a["reference_total_tokens"] for a in by_arm.values()),
            "all_tasks_correct_in_all_arms": all(a["correct"] == len(tasks) for a in by_arm.values()),
            "by_arm": by_arm,
            "comparisons": comparisons,
            "per_task": per_task_rows,
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "total_study_gateway_tokens": summary["total_study_gateway_tokens"],
                    "graph_indexes": graph_receipt,
                    "by_arm": by_arm,
                    "comparisons": comparisons,
                },
                indent=2,
            ),
            flush=True,
        )
        return 0
    finally:
        hr_pool.close()
        srv_plain.shutdown()
        srv_hr.shutdown()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-6-astra")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--sandbox-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.sandbox_child:
        os.environ["BRAINSPACE_TOKENIZER_FILE"] = str(TOKENIZER_FILE.resolve())
        tokens._TRIED, tokens._ENCODER = False, None
        tokens.count_tokens("warmup")
        return _run_sandbox_child(args.output.resolve(), args.model, args.workers)

    output_dir = args.output.resolve()
    if output_dir.exists():
        raise ValueError(f"Output directory must be new: {output_dir}")
    sandbox_root = output_dir / "sandbox-env"
    sandbox_root.mkdir(parents=True, exist_ok=False)
    env = build_isolated_sandbox_env(sandbox_root, TOKENIZER_FILE)
    token = _load_opencode_copilot_token()
    cmd = [
        sys.executable,
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        "--output",
        str(output_dir),
        "--model",
        args.model,
        "--workers",
        str(args.workers),
        "--sandbox-child",
    ]
    proc = subprocess.run(
        cmd,
        env=env,
        cwd=str(sandbox_root),
        input=token + "\n",
        text=True,
        encoding="utf-8",
        timeout=900,
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
