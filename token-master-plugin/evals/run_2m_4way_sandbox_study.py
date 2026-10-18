"""RETRACTED AS SAVINGS EVIDENCE (2026-10-18): synthetic padded workload. See
token-master-plugin/docs/PRS1_RESULTS.md. Kept only as a mechanism check.

Large-scale (>2M token per baseline arm, >7M token total) 4-way live isolated sandbox study:
1. Baseline (optimizer off)
2. Ponytail (pinned full instructions export)
3. Headroom (actual installed headroom-ai v0.41.0 compress pipeline)
4. TokenMaster V5 (request-policy-v5 multi-format compact-root reducer)

All 4 arms run against live gpt-6-astra on https://api.githubcopilot.com/responses
inside a scrubbed isolated sandbox with all global Headroom/Ponytail env vars and
profile directories stripped.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from queue import Queue
import subprocess
import sys
import threading
import time
import urllib.request
from typing import Any

PLUGIN = Path(__file__).resolve().parents[1]
SKILL = PLUGIN / "skills" / "token-master"
EVALS = PLUGIN / "evals"
for p in (SKILL, EVALS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from brainspace import tokens  # noqa: E402
from brainspace.readonly_learning_host import ReadonlyGatewayHost  # noqa: E402
from brainspace.request_policy import RequestPolicy  # noqa: E402
from brainspace.runtime import RuntimeSession  # noqa: E402
from brainspace.runtime_io import parse_json  # noqa: E402
from brainspace.runtime_policy import RuntimePolicy  # noqa: E402
from brainspace.runtime_resources import RuntimeResources  # noqa: E402
from run_isolated_sandbox_savings import (  # noqa: E402
    _load_opencode_copilot_token,
    audit_session_directory,
    build_isolated_sandbox_env,
    verify_sandbox_isolation,
)


HEADROOM_PYTHON = Path(r"C:\Users\shyamsridhar\AppData\Roaming\uv\tools\headroom-ai\Scripts\python.exe")
PONYTAIL_EXPORT = PLUGIN.parent / "evidence/controlled-scorecard-20261008/batch-001/ponytail.json"
TOKENIZER_FILE = PLUGIN.parent / "evidence/controlled-scorecard-20261008/batch-001/cl100k_base.tiktoken"


def build_large_enterprise_manifest() -> dict[str, Any]:
    """Build 14 multi-file repository tasks (6 large files per task, 7 turns per task)
    so Baseline alone exceeds 2,000,000 provider-reported tokens."""
    engine_py = (
        "from __future__ import annotations\n\n"
        "DEFAULT_BATCH_LIMIT = 64\n"
        "MAX_RETRY_COUNT = 3\n"
        "PIPELINE_EPOCH = 2026\n\n"
        + "".join(
            f"class TelemetryStage{k}:\n"
            f'    """Deterministic stage {k} telemetry aggregator and window normalizer."""\n\n'
            f"    def evaluate_window_{k}(self, records: list[dict], scale: int = {k}) -> dict:\n"
            f'        """Aggregate window {k} metrics across bounded telemetry records."""\n'
            + "".join(
                f"        accum_{i} = sum(item.get('value', 0) * scale for item in records) + {i * k}\n"
                f"        if accum_{i} < 0:\n"
                f"            accum_{i} = 0\n"
                for i in range(26)
            )
            + f'        return {{"stage": {k}, "total": accum_25, "limit": DEFAULT_BATCH_LIMIT}}\n\n'
            for k in range(1, 10)
        )
    )

    router_rs = (
        "pub const DEFAULT_PORT: u16 = 9090;\n"
        "pub const MAX_FRAME_BYTES: usize = 4096;\n"
        "pub const HEARTBEAT_INTERVAL_MS: u64 = 2500;\n\n"
        + "".join(
            f"pub fn dispatch_partition_{k}(frame_id: u64, payload_len: usize, flags: u32) -> bool {{\n"
            + "".join(
                f"    let check_{i}: usize = payload_len.saturating_add({i * k}) ^ (flags as usize);\n"
                f"    if check_{i} == usize::MAX {{ return false; }}\n"
                for i in range(28)
            )
            + "    frame_id > 0 && payload_len <= MAX_FRAME_BYTES\n}\n\n"
            for k in range(1, 10)
        )
    )

    validator_py = (
        "from __future__ import annotations\n\n"
        "STRICT_SCHEMA_VERSION = 7\n"
        "ALLOWED_CLOCK_SKEW_SEC = 15\n\n"
        + "".join(
            f"def verify_envelope_v{k}(payload: dict, skew: int = ALLOWED_CLOCK_SKEW_SEC) -> bool:\n"
            f'    """Verify security envelope invariants for protocol revision {k}."""\n'
            + "".join(
                f"    digests_{i} = hash((payload.get('id', ''), {i}, {k}, skew))\n"
                f"    if digests_{i} == 0:\n"
                f"        return False\n"
                for i in range(26)
            )
            + "    return bool(payload.get('verified', True))\n\n"
            for k in range(1, 10)
        )
    )

    routes_json = json.dumps(
        {
            "service": "tokenmaster-gateway",
            "schema_version": 4,
            "region": "us-central-1",
            "limits": {"max_connections": 256, "timeout_seconds": 30, "burst_capacity": 1024},
            "routes": [
                {
                    "id": f"route-{i:03d}",
                    "path": f"/api/v1/cluster/shard-{i:03d}/dispatch",
                    "method": "POST",
                    "auth_required": True,
                    "rate_limit_rps": 200 + i,
                    "timeout_ms": 5000,
                    "retry_policy": "exponential_backoff",
                }
                for i in range(210)
            ],
        },
        indent=4,
    )

    handbook_md = (
        "# Enterprise Deployment & Recovery Handbook\n\n"
        + (
            "The deployment controller coordinates rolling updates across isolated worker cells during each rollout wave. "
            "Before traffic shifts to the next shard in the ring, background health probes verify that socket latencies, "
            "memory pressure, and error budgets remain strictly within nominal bounds across all availability zones.\n\n"
        )
        * 52
        + "| Parameter | Value | Scope |\n"
        + "| --- | --- | --- |\n"
        + "| `ROLLOUT_WINDOW` | `120s` | `cluster` |\n"
        + "| `DRAIN_GRACE` | `15s` | `worker` |\n"
        + "| `QUORUM_MIN` | `3` | `control-plane` |\n\n"
        + "1. Verify local tokenizer SHA-256 digest.\n"
        + "2. Run preflight health probe on loopback.\n"
        + "3. Commit atomic route table update.\n\n"
        + "```python\n"
        + "deploy_cluster(window=120, drain_grace=15, quorum=3)\n"
        + "```\n"
    )

    build_log = (
        "".join(
            f"[INFO] compiling target partition_shard_{i:03d} with optimization level 3 and LTO enabled\n"
            for i in range(340)
        )
        + "[INFO] build succeeded\n"
    )

    files = {
        "src/engine.py": engine_py,
        "src/router.rs": router_rs,
        "src/validator.py": validator_py,
        "config/routes.json": routes_json,
        "docs/handbook.md": handbook_md,
        "logs/build.log": build_log,
    }

    orders = [
        ["src/engine.py", "src/router.rs", "src/validator.py", "config/routes.json", "docs/handbook.md", "logs/build.log"],
        ["src/router.rs", "src/validator.py", "config/routes.json", "docs/handbook.md", "logs/build.log", "src/engine.py"],
        ["src/validator.py", "config/routes.json", "docs/handbook.md", "logs/build.log", "src/engine.py", "src/router.rs"],
        ["config/routes.json", "docs/handbook.md", "logs/build.log", "src/engine.py", "src/router.rs", "src/validator.py"],
        ["docs/handbook.md", "logs/build.log", "src/engine.py", "src/router.rs", "src/validator.py", "config/routes.json"],
        ["logs/build.log", "src/engine.py", "src/router.rs", "src/validator.py", "config/routes.json", "docs/handbook.md"],
        ["src/engine.py", "config/routes.json", "src/router.rs", "docs/handbook.md", "src/validator.py", "logs/build.log"],
        ["src/router.rs", "docs/handbook.md", "src/validator.py", "logs/build.log", "src/engine.py", "config/routes.json"],
        ["config/routes.json", "src/engine.py", "logs/build.log", "src/router.rs", "docs/handbook.md", "src/validator.py"],
        ["docs/handbook.md", "src/validator.py", "src/engine.py", "config/routes.json", "src/router.rs", "logs/build.log"],
        ["logs/build.log", "config/routes.json", "src/validator.py", "src/router.rs", "src/engine.py", "docs/handbook.md"],
        ["src/validator.py", "src/engine.py", "src/router.rs", "logs/build.log", "config/routes.json", "docs/handbook.md"],
        ["src/engine.py", "docs/handbook.md", "config/routes.json", "logs/build.log", "src/validator.py", "src/router.rs"],
        ["src/router.rs", "logs/build.log", "docs/handbook.md", "src/engine.py", "config/routes.json", "src/validator.py"],
    ]

    expected_variants = [
        {"batch_limit": 64, "default_port": 9090, "strict_schema": 7, "max_connections": 256, "rollout_window": "120s", "build_status": "succeeded"},
        {"default_port": 9090, "clock_skew": 15, "service": "tokenmaster-gateway", "drain_grace": "15s", "build_status": "succeeded", "retries": 3},
        {"strict_schema": 7, "schema_version": 4, "quorum_min": "3", "build_status": "succeeded", "pipeline_epoch": 2026, "max_frame_bytes": 4096},
        {"max_connections": 256, "rollout_window": "120s", "build_status": "succeeded", "batch_limit": 64, "heartbeat_ms": 2500, "clock_skew": 15},
        {"drain_grace": "15s", "build_status": "succeeded", "retries": 3, "default_port": 9090, "strict_schema": 7, "timeout_seconds": 30},
        {"build_status": "succeeded", "pipeline_epoch": 2026, "max_frame_bytes": 4096, "clock_skew": 15, "burst_capacity": 1024, "quorum_min": "3"},
        {"batch_limit": 64, "region": "us-central-1", "default_port": 9090, "rollout_window": "120s", "strict_schema": 7, "build_status": "succeeded"},
        {"heartbeat_ms": 2500, "drain_grace": "15s", "clock_skew": 15, "build_status": "succeeded", "retries": 3, "max_connections": 256},
        {"service": "tokenmaster-gateway", "batch_limit": 64, "build_status": "succeeded", "default_port": 9090, "quorum_min": "3", "strict_schema": 7},
        {"rollout_window": "120s", "clock_skew": 15, "pipeline_epoch": 2026, "timeout_seconds": 30, "max_frame_bytes": 4096, "build_status": "succeeded"},
        {"build_status": "succeeded", "burst_capacity": 1024, "strict_schema": 7, "default_port": 9090, "batch_limit": 64, "drain_grace": "15s"},
        {"clock_skew": 15, "retries": 3, "heartbeat_ms": 2500, "build_status": "succeeded", "schema_version": 4, "rollout_window": "120s"},
        {"pipeline_epoch": 2026, "quorum_min": "3", "max_connections": 256, "build_status": "succeeded", "strict_schema": 7, "default_port": 9090},
        {"max_frame_bytes": 4096, "build_status": "succeeded", "drain_grace": "15s", "batch_limit": 64, "region": "us-central-1", "clock_skew": 15},
    ]

    key_descriptions = {
        "batch_limit": "<int DEFAULT_BATCH_LIMIT from src/engine.py>",
        "retries": "<int MAX_RETRY_COUNT from src/engine.py>",
        "pipeline_epoch": "<int PIPELINE_EPOCH from src/engine.py>",
        "default_port": "<int DEFAULT_PORT from src/router.rs>",
        "max_frame_bytes": "<int MAX_FRAME_BYTES from src/router.rs>",
        "heartbeat_ms": "<int HEARTBEAT_INTERVAL_MS from src/router.rs>",
        "strict_schema": "<int STRICT_SCHEMA_VERSION from src/validator.py>",
        "clock_skew": "<int ALLOWED_CLOCK_SKEW_SEC from src/validator.py>",
        "service": "<str service from config/routes.json>",
        "schema_version": "<int schema_version from config/routes.json>",
        "region": "<str region from config/routes.json>",
        "max_connections": "<int limits.max_connections from config/routes.json>",
        "timeout_seconds": "<int limits.timeout_seconds from config/routes.json>",
        "burst_capacity": "<int limits.burst_capacity from config/routes.json>",
        "rollout_window": "<str ROLLOUT_WINDOW from docs/handbook.md>",
        "drain_grace": "<str DRAIN_GRACE from docs/handbook.md>",
        "quorum_min": "<str QUORUM_MIN from docs/handbook.md>",
        "build_status": '<str "succeeded" from final line of logs/build.log>',
    }

    tasks = []
    for idx, (order, exp) in enumerate(zip(orders, expected_variants), start=1):
        schema_str = "{" + ", ".join(f'"{k}": {key_descriptions[k]}' for k in exp) + "}"
        prompt = (
            f"Enterprise Audit Task {idx:02d}: Read these 6 files one by one in this exact order using read_file: "
            + ", ".join(f"{i}) {p}" for i, p in enumerate(order, start=1))
            + ". Do NOT call retrieve_original or headroom_retrieve when the needed constants, tables, and JSON fields "
            "are already visible in the file view. After reading all 6 files, call answer(content=...) with a JSON string "
            f"containing ONLY these exact keys and types: {schema_str}."
        )
        tasks.append(
            {
                "prompt": prompt,
                "intent": "navigation" if idx % 2 == 1 else "overview",
                "files": files,
                "expected": exp,
            }
        )
    return {"schema_version": 1, "tasks": tasks}


class _HeadroomWorkerPool:
    """Pool of persistent headroom-ai v0.41.0 worker processes with ONNX Kompress + SmartCrusher + CodeAware."""
    def __init__(self, size: int = 4):
        model_cache = str((PLUGIN.parent / "evidence/headroom-model-readiness-20261008/model-cache").resolve())
        code = f"""
from copy import deepcopy
from dataclasses import replace
import json, os, sys

os.environ["HF_HOME"] = {model_cache!r}
os.environ["HF_HUB_CACHE"] = os.path.join({model_cache!r}, "hub")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from headroom.telemetry.session import BeaconCompressionObserver
from headroom.transforms import ContentRouter, TransformPipeline
from headroom.transforms.kompress_compressor import KompressCompressor
from headroom.utils import extract_user_query

warmer = KompressCompressor()
warmer.preload(allow_download=False)
if warmer._canary_thread is not None:
    warmer._canary_thread.join(timeout=45)

prototype = TransformPipeline()
idx = [i for i, s in enumerate(prototype.transforms) if isinstance(s, ContentRouter)][0]
orig = prototype.transforms[idx]
router_cfg = replace(deepcopy(orig.config), exclude_tools=set(), enable_code_aware=True, prefer_code_aware_for_code=True)
stages = list(prototype.transforms)
stages[idx] = ContentRouter(config=router_cfg, observer=BeaconCompressionObserver())
pipeline = TransformPipeline(config=prototype.config, transforms=stages)

for line in sys.stdin:
    chat = json.loads(line)
    msgs = deepcopy(chat.get("messages", []))
    try:
        res = pipeline.apply(msgs, model="gpt-4o", model_limit=200000, context=extract_user_query(msgs))
        for orig_m, comp_m in zip(chat.get("messages", []), res.messages):
            if orig_m.get("role") == "tool" and isinstance(comp_m.get("content"), str):
                orig_m["content"] = comp_m["content"]
    except Exception:
        pass
    sys.stdout.write(json.dumps(chat, ensure_ascii=False, separators=(",", ":")) + "\\n")
    sys.stdout.flush()
"""
        self._procs = []
        self._queue: Queue = Queue()
        for _ in range(size):
            p = subprocess.Popen(
                [str(HEADROOM_PYTHON), "-c", code],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
            )
            self._procs.append(p)
            self._queue.put(p)

    def compress_chat(self, chat: dict[str, Any]) -> dict[str, Any]:
        tool_msgs = [m for m in chat.get("messages", []) if m.get("role") == "tool"]
        if len(tool_msgs) <= 1:
            return chat
        p = self._queue.get()
        try:
            assert p.stdin is not None and p.stdout is not None
            p.stdin.write(json.dumps(chat, ensure_ascii=False, separators=(",", ":")) + "\n")
            p.stdin.flush()
            return json.loads(p.stdout.readline().strip())
        finally:
            self._queue.put(p)

    def close(self):
        for p in self._procs:
            try:
                p.terminate()
            except Exception:
                pass


def start_gateway(token: str, headroom_pool: _HeadroomWorkerPool | None = None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(n).decode("utf-8")
            last_err = None
            for attempt in range(3):
                try:
                    req = urllib.request.Request(
                        "https://api.githubcopilot.com/responses",
                        data=raw.encode("utf-8"),
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
                    return
                except Exception as exc:
                    last_err = exc
                    time.sleep(1.0 * (attempt + 1))
            raise RuntimeError(f"Upstream call failed after retries: {last_err}")

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _run_sandbox_child(output_dir: Path, model_name: str, workers: int) -> int:
    sandbox_root = output_dir / "sandbox-env"
    isolation_receipt = verify_sandbox_isolation(sandbox_root)
    (output_dir / "sandbox-isolation-audit.json").write_text(
        json.dumps(isolation_receipt, indent=2) + "\n", encoding="utf-8"
    )
    token = sys.stdin.readline().strip()
    if not token:
        raise RuntimeError("Missing live token on stdin")

    manifest = build_large_enterprise_manifest()
    hr_pool = _HeadroomWorkerPool(size=min(4, workers))
    srv_plain = start_gateway(token, headroom_pool=None)
    srv_hr = start_gateway(token, headroom_pool=hr_pool)

    url_plain = f"http://127.0.0.1:{srv_plain.server_port}/v1"
    url_hr = f"http://127.0.0.1:{srv_hr.server_port}/v1"

    pony_resources = RuntimeResources(ponytail_export=PONYTAIL_EXPORT)
    empty_resources = RuntimeResources()

    arm_configs = {
        "baseline": (url_plain, RuntimePolicy(), empty_resources),
        "ponytail": (url_plain, RuntimePolicy(instruction="ponytail"), pony_resources),
        "headroom": (url_hr, RuntimePolicy(), empty_resources),
        "tokenmaster_v5": (
            url_plain,
            RuntimePolicy(
                backend="local",
                request_policy=RequestPolicy(
                    version="request-policy-v5",
                    enabled=True,
                    min_tool_chars=256,
                    keep_recent_tool_results=1,
                    max_transforms=12,
                ),
                require_nonexpanding_input=True,
            ),
            empty_resources,
        ),
    }

    # Discover canonical task_ids once
    probe_host = ReadonlyGatewayHost(
        manifest, base_url=url_plain, model=model_name, allow_network=True,
        max_calls=12, max_tool_calls=24, timeout=90, reasoning_effort="low",
    )
    task_ids = list(probe_host.task_ids)

    jobs = [
        (t_idx, task_id, arm_name)
        for t_idx, task_id in enumerate(task_ids, start=1)
        for arm_name in arm_configs
    ]

    def execute_cell(job):
        t_idx, task_id, arm_name = job
        base_url, policy, res_obj = arm_configs[arm_name]
        host = ReadonlyGatewayHost(
            manifest, base_url=base_url, model=model_name, allow_network=True,
            max_calls=12, max_tool_calls=24, timeout=90, reasoning_effort="low",
        )
        cell_root = output_dir / "runs" / f"task-{t_idx:02d}-{arm_name}"
        prepared = host.prepare(task_id, cell_root / "host")
        session_out = cell_root / "session"
        session_id = f"task-{t_idx:02d}-{arm_name}"
        session = RuntimeSession(
            workspace=prepared.workspace,
            session_id=session_id,
            output=session_out,
            transport=prepared.transport,
            runtime_policy=policy,
            runtime_resources=res_obj,
            task_id=task_id,
            max_calls=12,
        )
        t0 = time.monotonic()
        try:
            artifacts = host.drive(task_id, session, prepared)
            session.finish()
        finally:
            session.close()
        wall_sec = round(time.monotonic() - t0, 3)
        outcome = host.check(task_id, artifacts, prepared)
        audit = audit_session_directory(session_out, prepared.workspace, session_id)
        return {
            "task_index": t_idx,
            "task_id": task_id,
            "arm": arm_name,
            "success": outcome.success,
            "wall_seconds": wall_sec,
            **audit,
        }

    per_task_rows = []
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(execute_cell, job): job for job in jobs}
            for fut in as_completed(futs):
                row = fut.result()
                per_task_rows.append(row)
                print(
                    f"[task-{row['task_index']:02d} {row['arm']:15s}] "
                    f"pass={row['success']} calls={row['captures_recounted']} "
                    f"gw_tokens={row['gateway_reported_tokens']} ref_in={row['reference_input_tokens']} "
                    f"sec={row['wall_seconds']}",
                    flush=True,
                )

        per_task_rows.sort(key=lambda r: (r["task_index"], list(arm_configs).index(r["arm"])))
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
                "wall_seconds": 0.0,
            }
            for name in arm_configs
        }
        for row in per_task_rows:
            agg = by_arm[row["arm"]]
            agg["tasks"] += 1
            agg["correct"] += int(row["success"] is True)
            agg["model_calls"] += row["captures_recounted"]
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
        v5_gw = by_arm["tokenmaster_v5"]["gateway_reported_tokens"]
        pony_gw = by_arm["ponytail"]["gateway_reported_tokens"]
        hr_gw = by_arm["headroom"]["gateway_reported_tokens"]

        total_study_gw_tokens = sum(a["gateway_reported_tokens"] for a in by_arm.values())
        total_study_ref_tokens = sum(a["reference_total_tokens"] for a in by_arm.values())

        comparisons = {
            "tokenmaster_v5_vs_baseline": {
                "gateway_tokens_saved": base_gw - v5_gw,
                "gateway_savings_pct": round((base_gw - v5_gw) / base_gw * 100.0, 2),
                "reference_input_tokens_saved": by_arm["baseline"]["reference_input_tokens"] - by_arm["tokenmaster_v5"]["reference_input_tokens"],
                "reference_input_savings_pct": round(
                    (by_arm["baseline"]["reference_input_tokens"] - by_arm["tokenmaster_v5"]["reference_input_tokens"])
                    / by_arm["baseline"]["reference_input_tokens"]
                    * 100.0,
                    2,
                ),
            },
            "ponytail_vs_baseline": {
                "gateway_tokens_saved": base_gw - pony_gw,
                "gateway_savings_pct": round((base_gw - pony_gw) / base_gw * 100.0, 2),
            },
            "headroom_vs_baseline": {
                "gateway_tokens_saved": base_gw - hr_gw,
                "gateway_savings_pct": round((base_gw - hr_gw) / base_gw * 100.0, 2),
            },
            "tokenmaster_v5_vs_ponytail": {
                "gateway_tokens_saved": pony_gw - v5_gw,
                "gateway_savings_pct": round((pony_gw - v5_gw) / pony_gw * 100.0, 2),
            },
            "tokenmaster_v5_vs_headroom": {
                "gateway_tokens_saved": hr_gw - v5_gw,
                "gateway_savings_pct": round((hr_gw - v5_gw) / hr_gw * 100.0, 2),
            },
        }

        summary = {
            "protocol": "isolated-sandbox-2m-4way-live-study-v1",
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "model": model_name,
            "upstream_endpoint": "https://api.githubcopilot.com/responses",
            "sandbox_isolation": isolation_receipt,
            "total_live_api_calls": sum(a["model_calls"] for a in by_arm.values()),
            "total_study_gateway_tokens": total_study_gw_tokens,
            "total_study_reference_tokens": total_study_ref_tokens,
            "baseline_exceeds_2m_tokens": base_gw >= 2_000_000,
            "all_tasks_correct_in_all_arms": all(a["correct"] == len(task_ids) for a in by_arm.values()),
            "by_arm": by_arm,
            "comparisons": comparisons,
            "per_task": per_task_rows,
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"total_study_gateway_tokens": total_study_gw_tokens, "by_arm": by_arm, "comparisons": comparisons}, indent=2), flush=True)
        return 0
    finally:
        hr_pool.close()
        srv_plain.shutdown()
        srv_hr.shutdown()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-6-astra")
    parser.add_argument("--workers", type=int, default=6)
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
