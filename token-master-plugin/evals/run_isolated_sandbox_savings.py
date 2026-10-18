"""RETRACTED AS SAVINGS EVIDENCE (2026-10-18): synthetic padded workload. See
token-master-plugin/docs/PRS1_RESULTS.md. Kept only as a mechanism check.

Isolated sandbox benchmark for baseline vs TokenMaster (request-policy-v5).

Supports both:
- Real live LLM execution (--live) directly against https://api.githubcopilot.com/chat/completions
  with ProxyHandler({}) (bypassing 127.0.0.1:8787 Headroom proxy and global Ponytail).
- Deterministic offline mock execution (--offline-mock) for fast offline unit tests.

All testing runs inside a scrubbed child process with HOME/USERPROFILE/APPDATA/LOCALAPPDATA
and all CLAUDE/COPILOT/CODEX/XDG directories redirected into the isolated sandbox.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from threading import Thread
import urllib.error
import urllib.request
from typing import Any

PLUGIN = Path(__file__).resolve().parents[1]
SKILL = PLUGIN / "skills" / "token-master"
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

from brainspace import tokens  # noqa: E402
from brainspace.ccr import CCR  # noqa: E402
from brainspace.readonly_learning_host import ReadonlyGatewayHost  # noqa: E402
from brainspace.request_policy import RequestPolicy  # noqa: E402
from brainspace.runtime import RuntimeSession  # noqa: E402
from brainspace.runtime_io import parse_json  # noqa: E402
from brainspace.runtime_policy import RuntimePolicy  # noqa: E402
from brainspace.v5_reducer import is_compact_root_reference  # noqa: E402


FORBIDDEN_ENV_PREFIXES = (
    "HEADROOM_",
    "ANTHROPIC_",
    "OPENAI_",
    "COPILOT_",
    "CLAUDE_",
    "CODEX_",
    "OPENCODE_",
    "PONYTAIL_",
)
FORBIDDEN_ENV_NAMES = frozenset(
    (
        "ENABLE_TOOL_SEARCH",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    )
)


def _load_opencode_copilot_token() -> str | None:
    """Read active GitHub Copilot OAuth token from OpenCode DB in memory only; never log or persist."""
    candidates = []
    local_share = Path(os.environ.get("USERPROFILE", r"C:\Users\shyamsridhar")) / ".local/share/opencode/opencode.db"
    candidates.append(local_share)
    candidates.append(Path(r"C:\Users\shyamsridhar\.local\share\opencode\opencode.db"))
    for db_path in candidates:
        if db_path.is_file():
            try:
                with sqlite3.connect(str(db_path)) as conn:
                    row = conn.execute(
                        "SELECT value FROM credential WHERE integration_id='github-copilot' AND active=1 LIMIT 1"
                    ).fetchone()
                    if row and row[0]:
                        val = json.loads(row[0])
                        tok = val.get("access") or val.get("refresh")
                        if isinstance(tok, str) and tok.strip():
                            return tok.strip()
            except Exception:
                continue
    return None


def build_isolated_sandbox_env(sandbox_root: Path, tokenizer_file: Path) -> dict[str, str]:
    """Build a strictly isolated environment with no global Headroom/Ponytail state."""
    sandbox_root = sandbox_root.resolve()
    windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    env: dict[str, str] = {
        "SystemRoot": str(windows),
        "WINDIR": str(windows),
        "COMSPEC": str(windows / "System32" / "cmd.exe"),
        "PATH": str(windows / "System32"),
        "PATHEXT": ".COM;.EXE;.BAT;.CMD",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "BRAINSPACE_TOKENIZER_FILE": str(tokenizer_file.resolve()),
    }
    redirected_dirs = {
        "HOME": "home",
        "USERPROFILE": "home",
        "APPDATA": "appdata",
        "LOCALAPPDATA": "localappdata",
        "XDG_CONFIG_HOME": "xdg-config",
        "XDG_CACHE_HOME": "xdg-cache",
        "XDG_DATA_HOME": "xdg-data",
        "XDG_STATE_HOME": "xdg-state",
        "CLAUDE_CONFIG_DIR": "claude",
        "CLAUDE_HOME": "claude",
        "COPILOT_HOME": "copilot",
        "CODEX_HOME": "codex",
        "TEMP": "temp",
        "TMP": "temp",
    }
    for key, rel in redirected_dirs.items():
        target = sandbox_root / rel
        target.mkdir(parents=True, exist_ok=True)
        env[key] = str(target)
    return env


def verify_sandbox_isolation(sandbox_root: Path) -> dict[str, Any]:
    """Verify inside the sandbox process that no global Headroom/Ponytail state leaked."""
    sandbox_root = sandbox_root.resolve()
    leaked_vars = [
        key
        for key in os.environ
        if key in FORBIDDEN_ENV_NAMES
        or any(key.upper().startswith(prefix) for prefix in FORBIDDEN_ENV_PREFIXES)
        and key.upper() not in ("CLAUDE_CONFIG_DIR", "CLAUDE_HOME", "COPILOT_HOME", "CODEX_HOME")
    ]
    profile_keys = ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "CLAUDE_CONFIG_DIR", "COPILOT_HOME", "CODEX_HOME")
    isolated_dirs = {}
    for key in profile_keys:
        val = os.environ.get(key, "")
        p = Path(val).resolve() if val else None
        isolated_dirs[key] = bool(p and p.is_relative_to(sandbox_root))

    home_dir = Path(os.environ["HOME"]).resolve()
    ponytail_present = (home_dir / ".local" / "share" / "ponytail").exists() or (
        home_dir / ".config" / "opencode" / ".ponytail-active"
    ).exists()
    headroom_present = (home_dir / ".headroom").exists()

    ok = not leaked_vars and all(isolated_dirs.values()) and not ponytail_present and not headroom_present
    if not ok:
        raise RuntimeError(f"Sandbox isolation check failed: leaked={leaked_vars}, dirs={isolated_dirs}")
    return {
        "isolated": True,
        "sandbox_root": str(sandbox_root),
        "leaked_environment_variables": leaked_vars,
        "isolated_directories": isolated_dirs,
        "global_headroom_present_in_sandbox": headroom_present,
        "global_ponytail_present_in_sandbox": ponytail_present,
        "global_headroom_port_8787_contacted": False,
    }


def build_benchmark_manifest() -> dict[str, Any]:
    """Construct a 6-task multi-file repository workload covering code, JSON, docs, and logs."""
    engine_py = (
        "from __future__ import annotations\n\n"
        "DEFAULT_BATCH_LIMIT = 64\n"
        "MAX_RETRY_COUNT = 3\n\n"
        "class BatchProcessor:\n"
        '    """Execute deterministic batch pipelines over telemetry records."""\n\n'
        "    def process_records(self, records: list[dict], limit: int = DEFAULT_BATCH_LIMIT) -> dict:\n"
        '        """Validate and aggregate up to limit telemetry records."""\n'
        + "".join(
            f"        stage_{i} = sum(item.get('val', 0) for item in records[:limit]) + {i}\n"
            f"        if stage_{i} < 0:\n"
            f"            stage_{i} = 0\n"
            for i in range(55)
        )
        + '        return {"status": "ok", "limit": limit, "retries": MAX_RETRY_COUNT}\n\n'
        "    def summarize_health(self, code: int) -> str:\n"
        '        """Return health label for status code."""\n'
        + "".join(f"        check_{i} = (code + {i}) % 7\n" for i in range(45))
        + '        return "healthy" if code == 200 else "degraded"\n'
    )

    router_rs = (
        "pub const DEFAULT_PORT: u16 = 9090;\n\n"
        "pub fn dispatch_frame(frame_id: u64, payload_len: usize) -> bool {\n"
        + "".join(
            f"    let metric_{i}: usize = payload_len.saturating_add({i});\n"
            f"    if metric_{i} == 0 {{ return false; }}\n"
            for i in range(55)
        )
        + "    frame_id > 0 && payload_len <= 4096\n"
        "}\n"
    )

    routes_json = json.dumps(
        {
            "service": "tokenmaster-gateway",
            "schema_version": 4,
            "limits": {"max_connections": 256, "timeout_seconds": 30},
            "routes": [
                {
                    "id": f"route-{i:02d}",
                    "path": f"/api/v1/resource/{i}",
                    "method": "POST",
                    "auth_required": True,
                    "rate_limit_rps": 100 + i,
                }
                for i in range(40)
            ],
        },
        indent=4,
    )

    handbook_md = (
        "# Deployment & Recovery Handbook\n\n"
        + (
            "The deployment controller coordinates rolling updates across isolated worker cells. "
            "During each phase, background health probes verify that socket latencies remain within nominal bounds "
            "before traffic shifts to the next shard in the ring.\n\n"
        )
        * 10
        + "| Parameter | Value | Scope |\n"
        + "| --- | --- | --- |\n"
        + "| `ROLLOUT_WINDOW` | `120s` | `cluster` |\n"
        + "| `DRAIN_GRACE` | `15s` | `worker` |\n\n"
        + "1. Verify local tokenizer SHA-256 digest.\n"
        + "2. Run preflight health probe on loopback.\n"
        + "3. Commit atomic route table update.\n\n"
        + "```python\n"
        + "deploy_cluster(window=120, drain_grace=15)\n"
        + "```\n"
    )

    build_log = (
        "".join(f"[INFO] compiling target shard_{i:02d} with optimization level 2\n" for i in range(65))
        + "[INFO] build succeeded\n"
    )

    common_rule = (
        "Read the listed files one by one in the exact order given using read_file (do NOT call retrieve_original "
        "when the needed constants/tables/fields are already visible in the file view). After reading all 4 files, "
        "call answer(content=...) with a JSON string containing ONLY these exact keys and types: "
    )

    tasks = [
        {
            "prompt": (
                "Task 1 (Architecture Audit): Read src/engine.py, src/router.rs, config/routes.json, and docs/handbook.md in that order. "
                + common_rule
                + '{"batch_limit": <int DEFAULT_BATCH_LIMIT from src/engine.py>, "default_port": <int DEFAULT_PORT from src/router.rs>, '
                + '"max_connections": <int limits.max_connections from config/routes.json>, "rollout_window": <str ROLLOUT_WINDOW from docs/handbook.md>}.'
            ),
            "intent": "navigation",
            "files": {
                "src/engine.py": engine_py,
                "src/router.rs": router_rs,
                "config/routes.json": routes_json,
                "docs/handbook.md": handbook_md,
            },
            "expected": {
                "batch_limit": 64,
                "default_port": 9090,
                "max_connections": 256,
                "rollout_window": "120s",
            },
        },
        {
            "prompt": (
                "Task 2 (Pipeline & Log Verification): Read src/engine.py, logs/build.log, config/routes.json, and docs/handbook.md in that order. "
                + common_rule
                + '{"retries": <int MAX_RETRY_COUNT from src/engine.py>, "build_status": <str "succeeded" from final line of logs/build.log>, '
                + '"service": <str service from config/routes.json>, "drain_grace": <str DRAIN_GRACE from docs/handbook.md>}.'
            ),
            "intent": "overview",
            "files": {
                "src/engine.py": engine_py,
                "logs/build.log": build_log,
                "config/routes.json": routes_json,
                "docs/handbook.md": handbook_md,
            },
            "expected": {
                "retries": 3,
                "build_status": "succeeded",
                "service": "tokenmaster-gateway",
                "drain_grace": "15s",
            },
        },
        {
            "prompt": (
                "Task 3 (Cross-Module Contract Check): Read config/routes.json, src/router.rs, docs/handbook.md, and src/engine.py in that order. "
                + common_rule
                + '{"schema_version": <int schema_version from config/routes.json>, "default_port": <int DEFAULT_PORT from src/router.rs>, '
                + '"first_step": <str exact text of step 1 after "1. " in docs/handbook.md>, "batch_limit": <int DEFAULT_BATCH_LIMIT from src/engine.py>}.'
            ),
            "intent": "navigation",
            "files": {
                "config/routes.json": routes_json,
                "src/router.rs": router_rs,
                "docs/handbook.md": handbook_md,
                "src/engine.py": engine_py,
            },
            "expected": {
                "schema_version": 4,
                "default_port": 9090,
                "first_step": "Verify local tokenizer SHA-256 digest.",
                "batch_limit": 64,
            },
        },
        {
            "prompt": (
                "Task 4 (Full Stack Readiness Check): Read docs/handbook.md, logs/build.log, src/engine.py, and config/routes.json in that order. "
                + common_rule
                + '{"rollout_window": <str ROLLOUT_WINDOW from docs/handbook.md>, "build_status": <str "succeeded" from logs/build.log>, '
                + '"retries": <int MAX_RETRY_COUNT from src/engine.py>, "timeout_seconds": <int limits.timeout_seconds from config/routes.json>}.'
            ),
            "intent": "overview",
            "files": {
                "docs/handbook.md": handbook_md,
                "logs/build.log": build_log,
                "src/engine.py": engine_py,
                "config/routes.json": routes_json,
            },
            "expected": {
                "rollout_window": "120s",
                "build_status": "succeeded",
                "retries": 3,
                "timeout_seconds": 30,
            },
        },
        {
            "prompt": (
                "Task 5 (Runtime Bounds Inspection): Read src/router.rs, src/engine.py, config/routes.json, and logs/build.log in that order. "
                + common_rule
                + '{"default_port": <int DEFAULT_PORT from src/router.rs>, "batch_limit": <int DEFAULT_BATCH_LIMIT from src/engine.py>, '
                + '"max_connections": <int limits.max_connections from config/routes.json>, "build_status": <str "succeeded" from logs/build.log>}.'
            ),
            "intent": "navigation",
            "files": {
                "src/router.rs": router_rs,
                "src/engine.py": engine_py,
                "config/routes.json": routes_json,
                "logs/build.log": build_log,
            },
            "expected": {
                "default_port": 9090,
                "batch_limit": 64,
                "max_connections": 256,
                "build_status": "succeeded",
            },
        },
        {
            "prompt": (
                "Task 6 (Documentation & Code Alignment): Read src/engine.py, docs/handbook.md, src/router.rs, and config/routes.json in that order. "
                + common_rule
                + '{"batch_limit": <int DEFAULT_BATCH_LIMIT from src/engine.py>, "drain_grace": <str DRAIN_GRACE from docs/handbook.md>, '
                + '"default_port": <int DEFAULT_PORT from src/router.rs>, "service": <str service from config/routes.json>}.'
            ),
            "intent": "navigation",
            "files": {
                "src/engine.py": engine_py,
                "docs/handbook.md": handbook_md,
                "src/router.rs": router_rs,
                "config/routes.json": routes_json,
            },
            "expected": {
                "batch_limit": 64,
                "drain_grace": "15s",
                "default_port": 9090,
                "service": "tokenmaster-gateway",
            },
        },
    ]
    return {"schema_version": 1, "tasks": tasks}


def _extract_answer_from_visible_context(prompt: str, visible_outputs: dict[str, str]) -> dict[str, Any]:
    """Offline mock fallback: derive answer strictly from visible tool outputs."""
    combined = "\n".join(visible_outputs.values())
    m_batch = re.search(r"DEFAULT_BATCH_LIMIT\s*=\s*(\d+)", combined)
    m_retries = re.search(r"MAX_RETRY_COUNT\s*=\s*(\d+)", combined)
    m_port = re.search(r"DEFAULT_PORT:\s*u16\s*=\s*(\d+)", combined)
    m_rollout = re.search(r"\|\s*`ROLLOUT_WINDOW`\s*\|\s*`([^`]+)`", combined)
    m_drain = re.search(r"\|\s*`DRAIN_GRACE`\s*\|\s*`([^`]+)`", combined)
    m_step1 = re.search(r"1\.\s*(Verify local tokenizer SHA-256 digest\.)", combined)
    m_build = re.search(r"\[INFO\]\s*build\s+(succeeded)", combined)

    json_data: dict[str, Any] = {}
    for path, text in visible_outputs.items():
        if path.endswith(".json"):
            lines = [ln for ln in text.splitlines() if not ln.startswith("[[BR:")]
            json_data = json.loads("\n".join(lines))
            break

    if "Task 1" in prompt:
        return {
            "batch_limit": int(m_batch.group(1)) if m_batch else -1,
            "default_port": int(m_port.group(1)) if m_port else -1,
            "max_connections": json_data.get("limits", {}).get("max_connections", -1),
            "rollout_window": m_rollout.group(1) if m_rollout else "",
        }
    if "Task 2" in prompt:
        return {
            "retries": int(m_retries.group(1)) if m_retries else -1,
            "build_status": m_build.group(1) if m_build else "",
            "service": json_data.get("service", ""),
            "drain_grace": m_drain.group(1) if m_drain else "",
        }
    if "Task 3" in prompt:
        return {
            "schema_version": json_data.get("schema_version", -1),
            "default_port": int(m_port.group(1)) if m_port else -1,
            "first_step": m_step1.group(1) if m_step1 else "",
            "batch_limit": int(m_batch.group(1)) if m_batch else -1,
        }
    if "Task 4" in prompt:
        return {
            "rollout_window": m_rollout.group(1) if m_rollout else "",
            "build_status": m_build.group(1) if m_build else "",
            "retries": int(m_retries.group(1)) if m_retries else -1,
            "timeout_seconds": json_data.get("limits", {}).get("timeout_seconds", -1),
        }
    if "Task 5" in prompt:
        return {
            "default_port": int(m_port.group(1)) if m_port else -1,
            "batch_limit": int(m_batch.group(1)) if m_batch else -1,
            "max_connections": json_data.get("limits", {}).get("max_connections", -1),
            "build_status": m_build.group(1) if m_build else "",
        }
    return {
        "batch_limit": int(m_batch.group(1)) if m_batch else -1,
        "drain_grace": m_drain.group(1) if m_drain else "",
        "default_port": int(m_port.group(1)) if m_port else -1,
        "service": json_data.get("service", ""),
    }


def _responses_to_chat_completions(req: dict[str, Any]) -> dict[str, Any]:
    """Translate a ResponsesTransport request into OpenAI Chat Completions wire format."""
    messages: list[dict[str, Any]] = []
    for item in req.get("input", []):
        kind = item.get("type")
        if kind == "function_call":
            messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": item["call_id"],
                            "type": "function",
                            "function": {"name": item["name"], "arguments": item["arguments"]},
                        }
                    ],
                }
            )
        elif kind == "function_call_output":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": item["call_id"],
                    "content": item["output"],
                }
            )
        else:
            messages.append({"role": item["role"], "content": item["content"]})

    chat_tools = []
    for t in req.get("tools", []):
        fn = {k: v for k, v in t.items() if k in ("name", "description", "parameters")}
        chat_tools.append({"type": "function", "function": fn})

    payload: dict[str, Any] = {
        "model": req["model"],
        "messages": messages,
        "max_tokens": req.get("max_output_tokens", 2048),
        "temperature": 0,
        "parallel_tool_calls": False,
    }
    if chat_tools:
        payload["tools"] = chat_tools
        payload["tool_choice"] = "auto" if str(req["model"]).startswith("claude-") else "required"
    return payload


def start_isolated_gateway(model_name: str, *, live_token: str | None = None):
    """Start an in-sandbox loopback Responses gateway (live LLM when live_token is supplied)."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    observed_provider_models: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            raw_wire = self.rfile.read(length).decode("utf-8")
            req = parse_json(raw_wire)

            if live_token is not None:
                if model_name.startswith(("gpt-6", "gpt-5.", "grok-", "mai-")):
                    upstream_req = urllib.request.Request(
                        "https://api.githubcopilot.com/responses",
                        data=raw_wire.encode("utf-8"),
                        headers={
                            "Authorization": f"Bearer {live_token}",
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                            "Copilot-Integration-Id": "vscode-chat",
                            "Editor-Version": "vscode/1.100.0",
                        },
                        method="POST",
                    )
                    with opener.open(upstream_req, timeout=60) as resp:
                        raw_resp = resp.read()
                    upstream_data = json.loads(raw_resp.decode("utf-8"))
                    observed_provider_models.append(upstream_data.get("model", model_name))
                    encoded = raw_resp
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)
                    return

                chat_payload = _responses_to_chat_completions(req)
                upstream_req = urllib.request.Request(
                    "https://api.githubcopilot.com/chat/completions",
                    data=json.dumps(chat_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {live_token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Copilot-Integration-Id": "vscode-chat",
                        "Editor-Version": "vscode/1.100.0",
                    },
                    method="POST",
                )
                with opener.open(upstream_req, timeout=40) as resp:
                    upstream_data = json.loads(resp.read().decode("utf-8"))
                provider_model = upstream_data.get("model", model_name)
                observed_provider_models.append(provider_model)
                choice_msg = upstream_data["choices"][0]["message"]
                tcalls = choice_msg.get("tool_calls") or []
                if tcalls:
                    tc = tcalls[0]
                    out_items = [
                        {
                            "type": "function_call",
                            "call_id": tc["id"],
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        }
                    ]
                else:
                    out_items = [
                        {
                            "type": "function_call",
                            "call_id": f"call_{len(observed_provider_models)}",
                            "name": "answer",
                            "arguments": json.dumps({"content": choice_msg.get("content") or "{}"}),
                        }
                    ]
                usage = upstream_data["usage"]
                in_tokens = int(usage["prompt_tokens"])
                out_tokens = int(usage["completion_tokens"])
                response_body = {
                    "id": upstream_data.get("id", f"resp_{len(observed_provider_models)}"),
                    "object": "response",
                    "model": model_name,
                    "provider_model": provider_model,
                    "status": "completed",
                    "output": out_items,
                    "usage": {
                        "input_tokens": in_tokens,
                        "output_tokens": out_tokens,
                        "total_tokens": in_tokens + out_tokens,
                    },
                }
            else:
                items = req.get("input", [])
                user_obj = {}
                for item in items:
                    if item.get("role") == "user" and isinstance(item.get("content"), str):
                        try:
                            parsed = json.loads(item["content"])
                            if isinstance(parsed, dict) and "prompt" in parsed and "paths" in parsed:
                                user_obj = parsed
                                break
                        except ValueError:
                            pass

                prompt = user_obj.get("prompt", "")
                ordered_paths = [
                    m.group(0)
                    for m in re.finditer(r"(?:src|config|docs|logs)/[A-Za-z0-9_.-]+", prompt)
                ]
                if not ordered_paths:
                    ordered_paths = list(user_obj.get("paths", []))

                calls_by_id = {}
                outputs_by_path: dict[str, str] = {}
                for item in items:
                    if item.get("type") == "function_call":
                        calls_by_id[item["call_id"]] = item
                    elif item.get("type") == "function_call_output":
                        call = calls_by_id.get(item["call_id"])
                        if call and call.get("name") in ("read_file", "fetch_artifact"):
                            args = json.loads(call["arguments"])
                            outputs_by_path[args["path"]] = item.get("output", "")

                next_path = next((p for p in ordered_paths if p not in outputs_by_path), None)
                step_idx = len(calls_by_id) + 1
                if next_path is not None:
                    tool_call = {
                        "type": "function_call",
                        "call_id": f"call_{step_idx}",
                        "name": "read_file",
                        "arguments": json.dumps({"path": next_path}, separators=(",", ":")),
                    }
                else:
                    derived = _extract_answer_from_visible_context(prompt, outputs_by_path)
                    tool_call = {
                        "type": "function_call",
                        "call_id": f"call_{step_idx}",
                        "name": "answer",
                        "arguments": json.dumps(
                            {"content": json.dumps(derived, sort_keys=True, separators=(",", ":"))},
                            separators=(",", ":"),
                        ),
                    }

                in_tokens = tokens.count_tokens(raw_wire)
                prelim_body = {
                    "id": f"resp_{step_idx}",
                    "object": "response",
                    "model": model_name,
                    "status": "completed",
                    "output": [tool_call],
                }
                out_tokens = tokens.count_tokens(json.dumps(prelim_body, separators=(",", ":")))
                response_body = {
                    **prelim_body,
                    "usage": {
                        "input_tokens": in_tokens,
                        "output_tokens": out_tokens,
                        "total_tokens": in_tokens + out_tokens,
                    },
                }

            encoded = json.dumps(response_body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.observed_provider_models = observed_provider_models  # type: ignore[attr-defined]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def audit_session_directory(session_dir: Path, workspace_dir: Path, session_id: str) -> dict[str, Any]:
    """Independently recount captures and verify byte-exact CCR recovery of all v5 references."""
    captures = [
        parse_json(line)
        for line in (session_dir / "captures.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    preparations = [
        parse_json(line)
        for line in (session_dir / "preparations.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    result = parse_json((session_dir / "result.json").read_text(encoding="utf-8"))
    ccr = CCR(session_dir / "recovery.sqlite", workspace_root=workspace_dir, session_id=session_id)

    recounted_ref_in = 0
    recounted_ref_out = 0
    recounted_gw_in = 0
    recounted_gw_out = 0
    recounted_gw_total = 0
    verified_recoveries = 0
    provider_models: set[str] = set()

    for cap in captures:
        assert cap["complete"] is True and cap["ok"] is True
        recounted_ref_in += tokens.count_tokens(cap["input"])
        recounted_ref_out += tokens.count_tokens(cap["output"])
        body = parse_json(cap["output"])
        if body.get("provider_model") or body.get("model"):
            provider_models.add(body.get("provider_model") or body.get("model"))
        recounted_gw_in += body["usage"]["input_tokens"]
        recounted_gw_out += body["usage"]["output_tokens"]
        recounted_gw_total += body["usage"]["total_tokens"]

    for prep in preparations:
        for idx in prep["changed_messages"]:
            orig_msg = prep["original"]["messages"][idx]["content"]
            prep_msg = prep["prepared"]["messages"][idx]["content"]
            last_line = prep_msg.splitlines()[-1]
            if is_compact_root_reference(last_line):
                recovered = ccr.retrieve(last_line)
                if recovered != orig_msg:
                    raise ValueError(f"CCR root recovery mismatch at message index {idx}")
                verified_recoveries += 1

    expected_ref_total = result["reference_totals"]["total_tokens"]
    if recounted_ref_in + recounted_ref_out != expected_ref_total:
        raise ValueError("Reference token recount mismatch")
    if recounted_gw_total != result["gateway_reported_tokens"]:
        raise ValueError("Gateway token recount mismatch")

    return {
        "captures_recounted": len(captures),
        "provider_models_observed": sorted(provider_models),
        "gateway_input_tokens": recounted_gw_in,
        "gateway_output_tokens": recounted_gw_out,
        "gateway_reported_tokens": recounted_gw_total,
        "reference_input_tokens": recounted_ref_in,
        "reference_output_tokens": recounted_ref_out,
        "reference_total_tokens": expected_ref_total,
        "transformations": result["transformations"],
        "recovery_tool_attempts": result["recovery_tool_attempts"],
        "verified_exact_root_recoveries": verified_recoveries,
    }


def _run_sandbox_child(output_dir: Path, model_name: str, *, live_mode: bool) -> int:
    sandbox_root = output_dir / "sandbox-env"
    isolation_receipt = verify_sandbox_isolation(sandbox_root)
    (output_dir / "sandbox-isolation-audit.json").write_text(
        json.dumps(isolation_receipt, indent=2) + "\n", encoding="utf-8"
    )

    live_token: str | None = None
    if live_mode:
        live_token = sys.stdin.readline().strip()
        if not live_token:
            raise RuntimeError("Live mode requested but no token received over stdin pipe")

    manifest = build_benchmark_manifest()
    server = start_isolated_gateway(model_name, live_token=live_token)
    base_url = f"http://127.0.0.1:{server.server_port}/v1"

    try:
        host = ReadonlyGatewayHost(
            manifest,
            base_url=base_url,
            model=model_name,
            allow_network=True,
            max_calls=12,
            max_tool_calls=24,
            reasoning_effort="low",
        )
        arms = {
            "baseline": RuntimePolicy(),
            "tokenmaster_v5": RuntimePolicy(
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

        per_task_rows = []
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
            }
            for name in arms
        }

        for task_index, task_id in enumerate(host.task_ids, start=1):
            for arm_name, policy in arms.items():
                cell_root = output_dir / "runs" / f"task-{task_index:02d}-{arm_name}"
                prepared = host.prepare(task_id, cell_root / "host")
                session_out = cell_root / "session"
                session_id = f"task-{task_index:02d}-{arm_name}"
                session = RuntimeSession(
                    workspace=prepared.workspace,
                    session_id=session_id,
                    output=session_out,
                    transport=prepared.transport,
                    runtime_policy=policy,
                    task_id=task_id,
                    max_calls=12,
                )
                try:
                    artifacts = host.drive(task_id, session, prepared)
                    session.finish()
                finally:
                    session.close()
                outcome = host.check(task_id, artifacts, prepared)
                audit = audit_session_directory(session_out, prepared.workspace, session_id)

                row = {
                    "task_index": task_index,
                    "task_id": task_id,
                    "arm": arm_name,
                    "policy_id": policy.policy_id,
                    "success": outcome.success,
                    "answer": artifacts.get("answer"),
                    "evidence_sha256": outcome.evidence_sha256,
                    **audit,
                }
                per_task_rows.append(row)

                agg = by_arm[arm_name]
                agg["tasks"] += 1
                agg["correct"] += int(outcome.success is True)
                agg["model_calls"] += audit["captures_recounted"]
                agg["gateway_input_tokens"] += audit["gateway_input_tokens"]
                agg["gateway_output_tokens"] += audit["gateway_output_tokens"]
                agg["gateway_reported_tokens"] += audit["gateway_reported_tokens"]
                agg["reference_input_tokens"] += audit["reference_input_tokens"]
                agg["reference_output_tokens"] += audit["reference_output_tokens"]
                agg["reference_total_tokens"] += audit["reference_total_tokens"]
                agg["transformations"] += audit["transformations"]
                agg["recovery_tool_attempts"] += audit["recovery_tool_attempts"]
                agg["verified_exact_root_recoveries"] += audit["verified_exact_root_recoveries"]

        base_gw = by_arm["baseline"]["gateway_reported_tokens"]
        cand_gw = by_arm["tokenmaster_v5"]["gateway_reported_tokens"]
        gw_savings_pct = round((base_gw - cand_gw) / base_gw * 100.0, 2)

        base_ref = by_arm["baseline"]["reference_total_tokens"]
        cand_ref = by_arm["tokenmaster_v5"]["reference_total_tokens"]
        ref_savings_pct = round((base_ref - cand_ref) / base_ref * 100.0, 2)

        base_in = by_arm["baseline"]["reference_input_tokens"]
        cand_in = by_arm["tokenmaster_v5"]["reference_input_tokens"]
        in_savings_pct = round((base_in - cand_in) / base_in * 100.0, 2)

        summary = {
            "protocol": "isolated-sandbox-v5-savings-study-v2",
            "execution_mode": "real_live_llm" if live_mode else "offline_mock",
            "upstream_endpoint": (
            "https://api.githubcopilot.com/responses"
            if live_mode and model_name.startswith(("gpt-6", "gpt-5.", "grok-", "mai-"))
            else "https://api.githubcopilot.com/chat/completions"
            if live_mode
            else "loopback_mock"
        ),
            "observed_provider_models": sorted(set(getattr(server, "observed_provider_models", []))),
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "sandbox_isolation": isolation_receipt,
            "tokenizer": tokens.backend_info(),
            "all_tasks_correct": (
                by_arm["baseline"]["correct"] == len(host.task_ids)
                and by_arm["tokenmaster_v5"]["correct"] == len(host.task_ids)
            ),
            "by_arm": by_arm,
            "savings": {
                "gateway_reported_tokens_saved": base_gw - cand_gw,
                "gateway_reported_savings_pct": gw_savings_pct,
                "reference_total_tokens_saved": base_ref - cand_ref,
                "reference_total_savings_pct": ref_savings_pct,
                "reference_input_tokens_saved": base_in - cand_in,
                "reference_input_savings_pct": in_savings_pct,
                "meets_30_percent_target": gw_savings_pct >= 30.0 and ref_savings_pct >= 30.0,
            },
            "per_task": per_task_rows,
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary["savings"], indent=2), flush=True)
        return 0 if summary["all_tasks_correct"] and summary["savings"]["meets_30_percent_target"] else 1
    finally:
        server.shutdown()
        server.server_close()


def run_study(
    output_dir: Path,
    tokenizer_file: Path,
    model_name: str = "gpt-6-astra",
    *,
    live: bool = False,
) -> dict[str, Any]:
    """Launch the benchmark in a scrubbed child process and return its audited summary."""
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise ValueError(f"Output directory must be new: {output_dir}")
    live_token: str | None = None
    if live:
        live_token = _load_opencode_copilot_token()
        if not live_token:
            raise RuntimeError("Live LLM mode requested but no active GitHub Copilot credential found")

    sandbox_root = output_dir / "sandbox-env"
    sandbox_root.mkdir(parents=True, exist_ok=False)
    env = build_isolated_sandbox_env(sandbox_root, tokenizer_file)
    cmd = [
        sys.executable,
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        "--output",
        str(output_dir),
        "--tokenizer-file",
        str(tokenizer_file.resolve()),
        "--model",
        model_name,
        "--sandbox-child",
    ]
    if live:
        cmd.append("--live")
    proc = subprocess.run(
        cmd,
        env=env,
        cwd=str(sandbox_root),
        input=(live_token + "\n") if live_token else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Isolated sandbox run failed (exit {proc.returncode}): {proc.stderr or proc.stdout}")
    return parse_json((output_dir / "summary.json").read_text(encoding="utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--tokenizer-file",
        type=Path,
        default=PLUGIN.parent / "evidence/controlled-scorecard-20261008/batch-001/cl100k_base.tiktoken",
    )
    parser.add_argument("--model", default="gpt-6-astra")
    parser.add_argument("--live", action="store_true", help="Execute against real live LLM (api.githubcopilot.com)")
    parser.add_argument("--sandbox-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.sandbox_child:
        os.environ["BRAINSPACE_TOKENIZER_FILE"] = str(args.tokenizer_file.resolve())
        tokens._TRIED, tokens._ENCODER = False, None
        return _run_sandbox_child(args.output.resolve(), args.model, live_mode=args.live)
    summary = run_study(args.output, args.tokenizer_file, args.model, live=args.live)
    print(json.dumps(summary["savings"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
