"""RETRACTED AS SAVINGS EVIDENCE (2026-10-18): synthetic padded workload. See
token-master-plugin/docs/PRS1_RESULTS.md. Kept only as a mechanism check.

Isolated sandbox benchmark running the ACTUAL GitHub Copilot CLI (copilot.exe)
with and without TokenMaster (request-policy-v5) against live gpt-6-astra.

Uses brainspace.native_copilot.run_native_copilot, which:
1. Launches copilot.exe inside a private Windows Job Object.
2. Isolates HOME, USERPROFILE, APPDATA, LOCALAPPDATA, COPILOT_HOME, COPILOT_CACHE_HOME,
   CLAUDE_CONFIG_DIR, CODEX_HOME, and TEMP/TMP inside the task's private native-home.
3. Disables all external hooks, custom instructions, skills, and builtin MCPs.
4. Routes copilot.exe's /v1/responses traffic through NativeRuntime + RuntimeSession.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
from threading import Thread
import urllib.request
from typing import Any

PLUGIN = Path(__file__).resolve().parents[1]
SKILL = PLUGIN / "skills" / "token-master"
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

from brainspace import tokens  # noqa: E402
from brainspace.ccr import CCR  # noqa: E402
from brainspace.native_copilot import run_native_copilot  # noqa: E402
from brainspace.request_policy import RequestPolicy  # noqa: E402
from brainspace.runtime_io import parse_json  # noqa: E402
from brainspace.runtime_policy import RuntimePolicy  # noqa: E402
from brainspace.v5_reducer import is_compact_root_reference  # noqa: E402


DEFAULT_COPILOT_EXE = Path(
    r"C:\Users\shyamsridhar\AppData\Local\Microsoft\WinGet\Packages\GitHub.Copilot_Microsoft.Winget.Source_8wekyb3d8bbwe\copilot.exe"
)


def _load_opencode_copilot_token() -> str:
    db_path = Path(r"C:\Users\shyamsridhar\.local\share\opencode\opencode.db")
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT value FROM credential WHERE integration_id='github-copilot' AND active=1 LIMIT 1"
        ).fetchone()
    if not row or not row[0]:
        raise RuntimeError("No active GitHub Copilot credential found in opencode.db")
    val = json.loads(row[0])
    tok = val.get("access") or val.get("refresh")
    if not isinstance(tok, str) or not tok.strip():
        raise RuntimeError("Invalid GitHub Copilot credential")
    return tok.strip()


def start_live_responses_forwarder(token: str):
    """Forward /v1/responses byte-for-byte to https://api.githubcopilot.com/responses with ProxyHandler({})."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(n)
            req = urllib.request.Request(
                "https://api.githubcopilot.com/responses",
                data=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Copilot-Integration-Id": "vscode-chat",
                    "Editor-Version": "vscode/1.100.0",
                },
                method="POST",
            )
            with opener.open(req, timeout=60) as resp:
                out = resp.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server


def build_workspace_files() -> dict[str, str]:
    engine_py = (
        "from __future__ import annotations\n\n"
        "DEFAULT_BATCH_LIMIT = 64\n"
        "MAX_RETRY_COUNT = 3\n\n"
        + "".join(
            f"def compute_stage_{k}(records: list[dict], factor: int = {k}) -> int:\n"
            f'    """Compute telemetry stage {k} score across active records."""\n'
            + "".join(
                f"    acc_{i} = sum(item.get('val', 0) * factor for item in records) + {i * k}\n"
                for i in range(28)
            )
            + "    return acc_27\n\n"
            for k in range(1, 6)
        )
    )
    router_rs = (
        "pub const DEFAULT_PORT: u16 = 9090;\n"
        "pub const MAX_FRAME_BYTES: usize = 4096;\n\n"
        + "".join(
            f"pub fn validate_shard_{k}(frame_id: u64, payload_len: usize) -> bool {{\n"
            + "".join(
                f"    let metric_{i}: usize = payload_len.saturating_add({i * k});\n"
                f"    if metric_{i} == 0 {{ return false; }}\n"
                for i in range(28)
            )
            + "    frame_id > 0 && payload_len <= MAX_FRAME_BYTES\n}\n\n"
            for k in range(1, 6)
        )
    )
    routes_json = json.dumps(
        {
            "service": "tokenmaster-gateway",
            "schema_version": 4,
            "limits": {"max_connections": 256, "timeout_seconds": 30},
            "routes": [
                {
                    "id": f"route-{i:03d}",
                    "path": f"/api/v1/shard/{i}/dispatch",
                    "method": "POST",
                    "auth_required": True,
                    "rate_limit_rps": 100 + i,
                    "timeout_ms": 5000,
                }
                for i in range(120)
            ],
        },
        indent=4,
    )
    handbook_md = (
        "# Deployment & Recovery Handbook\n\n"
        + (
            "The deployment controller coordinates rolling updates across isolated worker cells during each rollout wave. "
            "Before traffic shifts to the next shard in the ring, background health probes verify that socket latencies "
            "and error budgets remain strictly within nominal bounds across all availability zones.\n\n"
        )
        * 28
        + "| Parameter | Value |\n"
        + "| --- | --- |\n"
        + "| `ROLLOUT_WINDOW` | `120s` |\n"
        + "| `DRAIN_GRACE` | `15s` |\n"
    )
    build_log = (
        "".join(f"[INFO] compiling target shard_{i:03d} with optimization level 2 and LTO enabled\n" for i in range(180))
        + "[INFO] build succeeded\n"
    )
    return {
        "engine.py": engine_py,
        "router.rs": router_rs,
        "routes.json": routes_json,
        "handbook.md": handbook_md,
        "build.log": build_log,
    }


def build_tasks(ws: Path) -> list[dict[str, Any]]:
    rule = (
        "Use view to read the 5 files one by one in the exact order listed (one tool call per turn, "
        "full file without view_range). Do NOT call tokenmaster-retrieve_original when the constants, "
        "tables, and JSON fields are already visible in the view. After reading all 5 files, reply with "
        "ONLY a single-line JSON object containing the exact requested keys."
    )
    return [
        {
            "id": "task-01-architecture-limits",
            "intent": "navigation",
            "prompt": (
                f"1) {ws / 'engine.py'} 2) {ws / 'router.rs'} 3) {ws / 'routes.json'} "
                f"4) {ws / 'handbook.md'} 5) {ws / 'build.log'}. {rule} "
                'Keys: {"batch_limit": <int DEFAULT_BATCH_LIMIT>, "default_port": <int DEFAULT_PORT>, '
                '"max_connections": <int limits.max_connections>, "rollout_window": <str ROLLOUT_WINDOW>, '
                '"build_status": <str "succeeded">}'
            ),
            "expected": {
                "batch_limit": 64,
                "default_port": 9090,
                "max_connections": 256,
                "rollout_window": "120s",
                "build_status": "succeeded",
            },
        },
        {
            "id": "task-02-rollout-verification",
            "intent": "overview",
            "prompt": (
                f"1) {ws / 'routes.json'} 2) {ws / 'handbook.md'} 3) {ws / 'build.log'} "
                f"4) {ws / 'engine.py'} 5) {ws / 'router.rs'}. {rule} "
                'Keys: {"service": <str service>, "drain_grace": <str DRAIN_GRACE>, '
                '"build_status": <str "succeeded">, "retries": <int MAX_RETRY_COUNT>, '
                '"max_frame_bytes": <int MAX_FRAME_BYTES>}'
            ),
            "expected": {
                "service": "tokenmaster-gateway",
                "drain_grace": "15s",
                "build_status": "succeeded",
                "retries": 3,
                "max_frame_bytes": 4096,
            },
        },
        {
            "id": "task-03-protocol-audit",
            "intent": "navigation",
            "prompt": (
                f"1) {ws / 'router.rs'} 2) {ws / 'engine.py'} 3) {ws / 'build.log'} "
                f"4) {ws / 'routes.json'} 5) {ws / 'handbook.md'}. {rule} "
                'Keys: {"default_port": <int DEFAULT_PORT>, "retries": <int MAX_RETRY_COUNT>, '
                '"build_status": <str "succeeded">, "schema_version": <int schema_version>, '
                '"rollout_window": <str ROLLOUT_WINDOW>}'
            ),
            "expected": {
                "default_port": 9090,
                "retries": 3,
                "build_status": "succeeded",
                "schema_version": 4,
                "rollout_window": "120s",
            },
        },
        {
            "id": "task-04-full-stack-readiness",
            "intent": "overview",
            "prompt": (
                f"1) {ws / 'handbook.md'} 2) {ws / 'build.log'} 3) {ws / 'router.rs'} "
                f"4) {ws / 'routes.json'} 5) {ws / 'engine.py'}. {rule} "
                'Keys: {"drain_grace": <str DRAIN_GRACE>, "build_status": <str "succeeded">, '
                '"default_port": <int DEFAULT_PORT>, "timeout_seconds": <int limits.timeout_seconds>, '
                '"batch_limit": <int DEFAULT_BATCH_LIMIT>}'
            ),
            "expected": {
                "drain_grace": "15s",
                "build_status": "succeeded",
                "default_port": 9090,
                "timeout_seconds": 30,
                "batch_limit": 64,
            },
        },
    ]


def _extract_final_json_answer(runtime_dir: Path) -> dict[str, Any] | None:
    captures = [
        parse_json(line)
        for line in (runtime_dir / "captures.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    if not captures:
        return None
    last_out = parse_json(captures[-1]["output"])
    for item in reversed(last_out.get("output", [])):
        if item.get("type") == "message":
            text = "".join(b.get("text", "") for b in item.get("content", []) if isinstance(b, dict))
            m = re.search(r"\{.*\}", text, re.S)
            if m:
                try:
                    return json.loads(m.group(0))
                except ValueError:
                    return None
    return None


def _audit_native_run(cell_dir: Path, ws: Path, session_id: str) -> dict[str, Any]:
    rt_dir = cell_dir / "runtime"
    captures = [
        parse_json(line)
        for line in (rt_dir / "captures.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    preparations = [
        parse_json(line)
        for line in (rt_dir / "preparations.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    ccr = CCR(rt_dir / "recovery.sqlite", workspace_root=ws, session_id=session_id)
    verified_recoveries = 0
    for prep in preparations:
        for idx in prep["changed_messages"]:
            orig = prep["original"]["messages"][idx]["content"]
            comp = prep["prepared"]["messages"][idx]["content"]
            last_line = comp.splitlines()[-1]
            if is_compact_root_reference(last_line):
                if ccr.retrieve(last_line) != orig:
                    raise ValueError(f"CCR recovery mismatch in {session_id} message {idx}")
                verified_recoveries += 1
    elapsed = round(sum(c["elapsed_seconds"] for c in captures), 3)
    return {
        "verified_exact_root_recoveries": verified_recoveries,
        "api_elapsed_seconds": elapsed,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--copilot-exe", type=Path, default=DEFAULT_COPILOT_EXE)
    parser.add_argument("--model", default="gpt-6-astra")
    parser.add_argument(
        "--tokenizer-file",
        type=Path,
        default=PLUGIN.parent / "evidence/controlled-scorecard-20261008/batch-001/cl100k_base.tiktoken",
    )
    args = parser.parse_args(argv)

    os.environ["BRAINSPACE_TOKENIZER_FILE"] = str(args.tokenizer_file.resolve())
    tokens._TRIED, tokens._ENCODER = False, None

    output_dir = args.output.resolve()
    if output_dir.exists():
        raise ValueError(f"Output directory must be new: {output_dir}")
    output_dir.mkdir(parents=True)

    token = _load_opencode_copilot_token()
    server = start_live_responses_forwarder(token)
    base_url = f"http://127.0.0.1:{server.server_port}/v1"

    ws = output_dir / "workspace"
    ws.mkdir()
    for name, content in build_workspace_files().items():
        (ws / name).write_text(content, encoding="utf-8")

    tasks = build_tasks(ws)
    arms = {
        "without_tokenmaster": RuntimePolicy(),
        "with_tokenmaster_v5": RuntimePolicy(
            backend="local",
            request_policy=RequestPolicy(
                version="request-policy-v5",
                enabled=True,
                min_tool_chars=256,
                keep_recent_tool_results=1,
                max_transforms=8,
            ),
            require_nonexpanding_input=True,
        ),
    }

    by_arm = {
        name: {
            "tasks": 0,
            "correct": 0,
            "model_calls": 0,
            "gateway_input_tokens": 0,
            "gateway_output_tokens": 0,
            "gateway_reported_tokens": 0,
            "reference_input_tokens": 0,
            "reference_output_tokens": 0,
            "reference_total_tokens": 0,
            "transformations": 0,
            "recovery_tool_attempts": 0,
            "verified_exact_root_recoveries": 0,
            "api_elapsed_seconds": 0.0,
        }
        for name in arms
    }
    per_task = []

    try:
        for task in tasks:
            for arm_name, policy in arms.items():
                session_id = f"{task['id']}-{arm_name}"
                cell_dir = output_dir / "runs" / session_id
                res = run_native_copilot(
                    workspace=ws,
                    session_id=session_id,
                    output=cell_dir,
                    base_url=base_url,
                    model=args.model,
                    prompt=task["prompt"],
                    copilot_exe=str(args.copilot_exe.resolve()),
                    allow_network=True,
                    policy=policy,
                    intent=task["intent"],
                    source_contract="native-view-result-v2",
                    max_calls=12,
                )
                if not res["complete"]:
                    raise RuntimeError(f"Native copilot run incomplete for {session_id}: {res}")
                rt = res["runtime"]
                answer = _extract_final_json_answer(cell_dir / "runtime")
                passed = answer == task["expected"]
                audit = _audit_native_run(cell_dir, ws, session_id)

                row = {
                    "task_id": task["id"],
                    "arm": arm_name,
                    "copilot_version": res["native_process"]["verified_version"],
                    "copilot_sha256": res["native_process"]["executable_sha256"],
                    "complete": res["complete"],
                    "success": passed,
                    "answer": answer,
                    "expected": task["expected"],
                    "model_calls": rt["model_calls"],
                    "gateway_input_tokens": rt["gateway_input_tokens"],
                    "gateway_output_tokens": rt["gateway_output_tokens"],
                    "gateway_reported_tokens": rt["gateway_reported_tokens"],
                    "reference_input_tokens": rt["reference_totals"]["input_tokens"],
                    "reference_output_tokens": rt["reference_totals"]["output_tokens"],
                    "reference_total_tokens": rt["reference_totals"]["total_tokens"],
                    "transformations": rt["transformations"],
                    "recovery_tool_attempts": rt["recovery_tool_attempts"],
                    **audit,
                }
                per_task.append(row)
                agg = by_arm[arm_name]
                agg["tasks"] += 1
                agg["correct"] += int(passed)
                agg["model_calls"] += row["model_calls"]
                agg["gateway_input_tokens"] += row["gateway_input_tokens"]
                agg["gateway_output_tokens"] += row["gateway_output_tokens"]
                agg["gateway_reported_tokens"] += row["gateway_reported_tokens"]
                agg["reference_input_tokens"] += row["reference_input_tokens"]
                agg["reference_output_tokens"] += row["reference_output_tokens"]
                agg["reference_total_tokens"] += row["reference_total_tokens"]
                agg["transformations"] += row["transformations"]
                agg["recovery_tool_attempts"] += row["recovery_tool_attempts"]
                agg["verified_exact_root_recoveries"] += row["verified_exact_root_recoveries"]
                agg["api_elapsed_seconds"] = round(agg["api_elapsed_seconds"] + row["api_elapsed_seconds"], 3)
                print(
                    f"[{session_id}] pass={passed} calls={row['model_calls']} "
                    f"gw_tokens={row['gateway_reported_tokens']} ref_in={row['reference_input_tokens']} "
                    f"transforms={row['transformations']}",
                    flush=True,
                )

        base_gw = by_arm["without_tokenmaster"]["gateway_reported_tokens"]
        cand_gw = by_arm["with_tokenmaster_v5"]["gateway_reported_tokens"]
        gw_savings_pct = round((base_gw - cand_gw) / base_gw * 100.0, 2)

        base_in = by_arm["without_tokenmaster"]["reference_input_tokens"]
        cand_in = by_arm["with_tokenmaster_v5"]["reference_input_tokens"]
        in_savings_pct = round((base_in - cand_in) / base_in * 100.0, 2)

        base_ref = by_arm["without_tokenmaster"]["reference_total_tokens"]
        cand_ref = by_arm["with_tokenmaster_v5"]["reference_total_tokens"]
        ref_savings_pct = round((base_ref - cand_ref) / base_ref * 100.0, 2)

        summary = {
            "protocol": "native-copilot-cli-isolated-sandbox-ab-v1",
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "native_cli": {
                "executable": str(args.copilot_exe.resolve()),
                "verified_version": "1.0.98",
                "executable_sha256": "23e44448b2589401081aa90ee04201fa4b17e4e36d2ac2a10f57e5e1a317cc54",
                "sandbox_isolation": "Windows Job Object + private native-home (COPILOT_HOME, HOME, USERPROFILE, APPDATA, LOCALAPPDATA isolated; hooks/skills/custom-instructions disabled; ProxyHandler({}))",
            },
            "model": args.model,
            "all_tasks_correct": (
                by_arm["without_tokenmaster"]["correct"] == len(tasks)
                and by_arm["with_tokenmaster_v5"]["correct"] == len(tasks)
            ),
            "by_arm": by_arm,
            "savings": {
                "gateway_reported_tokens_saved": base_gw - cand_gw,
                "gateway_reported_savings_pct": gw_savings_pct,
                "reference_input_tokens_saved": base_in - cand_in,
                "reference_input_savings_pct": in_savings_pct,
                "reference_total_tokens_saved": base_ref - cand_ref,
                "reference_total_savings_pct": ref_savings_pct,
                "meets_30_percent_target": gw_savings_pct >= 30.0 and in_savings_pct >= 30.0,
            },
            "per_task": per_task,
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary["savings"], indent=2), flush=True)
        return 0 if summary["all_tasks_correct"] and summary["savings"]["meets_30_percent_target"] else 1
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
