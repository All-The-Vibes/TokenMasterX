"""Measure Copilot CLI 1.0.112 fixed-prompt calibrations for tokenomics.py under default GitHub routing.

Runs one fixed prompt ("Reply with the single word OK. Do not use any tools.") per model (gpt-6-astra,
claude-opus-5.5) in an isolated C:\\tm-lanes workspace with no inherited CLAUDE.md, skills or agents:
  - four back-to-back stock sessions across two folders (one cold + three warm -> stock_first_cached),
  - one lean session (--excluded-tools with all 13 LEAN_EXCLUDED_TOOLS -> lean = stock - lean_only),
  - one lean+nav session (same --excluded-tools plus tokenmaster-nav MCP -> nav = lean_nav - lean_only).
All token counts come directly from Copilot CLI's session-store.db assistant_usage_events.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import statistics
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SKILL = REPO / "token-master-plugin" / "skills" / "token-master"
sys.path.insert(0, str(SKILL))
import brainspace_copilot_bridge as bridge  # noqa: E402

PROMPT = "Reply with the single word OK. Do not use any tools."
MODELS = (("responses", "gpt-6-astra"), ("messages", "claude-opus-5.5"))
COPILOT = Path(os.environ["LOCALAPPDATA"]) / (
    "Microsoft/WinGet/Packages/GitHub.Copilot_Microsoft.Winget.Source_8wekyb3d8bbwe/copilot.exe"
)
PYTHON = Path(sys.executable)


def read_session_calls(db_path: Path, seen_ids: set[int]) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, session_id, agent_id, model, api_endpoint, input_tokens, output_tokens, "
            "cache_read_tokens, cache_write_tokens, total_nano_aiu, created_at "
            "FROM assistant_usage_events ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    fresh = []
    for row in rows:
        if row["id"] not in seen_ids:
            seen_ids.add(row["id"])
            fresh.append(dict(row))
    return fresh


def main() -> int:
    work = Path(r"C:\tm-lanes\cal-1.0.112")
    shutil.rmtree(work, ignore_errors=True)
    home = work / "copilot-home"
    home.mkdir(parents=True)
    for folder_name in ("repo-a", "repo-b"):
        folder = work / folder_name
        folder.mkdir(parents=True)
        (folder / "hello.py").write_text("def greet(name):\n    return f'hello {name}'\n", encoding="utf-8")

    nav_cfg = work / "nav-mcp.json"
    nav_cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "tokenmaster-nav": {
                        "type": "local",
                        "command": str(PYTHON),
                        "args": [str(SKILL / "graphify_mcp.py")],
                        "tools": ["*"],
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    env = dict(os.environ)
    env["COPILOT_HOME"] = str(home)
    for key in ("COPILOT_PROVIDER_BASE_URL", "COPILOT_PROVIDER_TYPE", "COPILOT_PROVIDER_API_KEY"):
        env.pop(key, None)

    ver = subprocess.run(
        [str(COPILOT), "--no-auto-update", "--version"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
    ).stdout.strip()

    db_path = home / "session-store.db"
    seen_ids: set[int] = set()
    runs = []
    calibrations = {}

    specs = [
        ("stock-a1", "repo-a", []),
        ("stock-a2", "repo-a", []),
        ("stock-b1", "repo-b", []),
        ("stock-b2", "repo-b", []),
        ("lean", "repo-a", ["--excluded-tools", *bridge.LEAN_EXCLUDED_TOOLS]),
        (
            "lean-nav",
            "repo-a",
            ["--excluded-tools", *bridge.LEAN_EXCLUDED_TOOLS, "--additional-mcp-config", f"@{nav_cfg}"],
        ),
    ]

    for api_key, model in MODELS:
        model_runs = {}
        for label, folder_name, extra in specs:
            cmd = [
                str(COPILOT),
                "--no-auto-update",
                "--disable-builtin-mcps",
                "--no-custom-instructions",
                "--allow-all-tools",
                "--reasoning-effort",
                "low",
                "--model",
                model,
                "-p",
                PROMPT,
                *extra,
            ]
            proc = subprocess.run(
                cmd,
                cwd=work / folder_name,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
                stdin=subprocess.DEVNULL,
            )
            calls = read_session_calls(db_path, seen_ids) if db_path.is_file() else []
            main_calls = [c for c in calls if not c.get("agent_id")]
            first = main_calls[0] if main_calls else None
            entry = {
                "api": api_key,
                "model": model,
                "label": label,
                "folder": folder_name,
                "exit": proc.returncode,
                "calls": len(main_calls),
                "first_call": first,
                "stderr_tail": proc.stderr[-300:] if proc.returncode else "",
            }
            runs.append(entry)
            model_runs[label] = entry
            print(
                json.dumps(
                    {
                        "model": model,
                        "label": label,
                        "exit": proc.returncode,
                        "input": first["input_tokens"] if first else None,
                        "cache_read": first["cache_read_tokens"] if first else None,
                        "cache_write": first["cache_write_tokens"] if first else None,
                        "endpoint": first["api_endpoint"] if first else None,
                    }
                ),
                flush=True,
            )

        stock_inputs = [
            model_runs[k]["first_call"]["input_tokens"]
            for k in ("stock-a1", "stock-a2", "stock-b1", "stock-b2")
        ]
        warm_cached = [
            model_runs[k]["first_call"]["cache_read_tokens"]
            for k in ("stock-a2", "stock-b1", "stock-b2")
        ]
        lean_in = model_runs["lean"]["first_call"]["input_tokens"]
        lean_nav_in = model_runs["lean-nav"]["first_call"]["input_tokens"]
        stock_in = round(statistics.median(stock_inputs))
        calibrations[api_key] = {
            "model": model,
            "lean": stock_in - lean_in,
            "nav": lean_nav_in - lean_in,
            "stock_first_cached": round(statistics.median(warm_cached)),
            "stock_first_call_input": stock_in,
            "lean_first_call_input": lean_in,
            "lean_nav_first_call_input": lean_nav_in,
            "warm_stock_cache_reads": warm_cached,
        }

    out_path = HERE / "calibration_1_0_112.json"
    out_path.write_text(
        json.dumps(
            {
                "kind": "calibration probe",
                "copilot_version": ver.splitlines()[0],
                "prompt": PROMPT,
                "excluded_tools": list(bridge.LEAN_EXCLUDED_TOOLS),
                "calibrations": calibrations,
                "runs": runs,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("CALIBRATIONS 1.0.112:", json.dumps(calibrations, indent=2), flush=True)
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
