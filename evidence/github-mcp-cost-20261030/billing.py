"""Paid check (four model calls, about $1): what GitHub bills for the built-in GitHub MCP server under default routing.

probe.py showed that Copilot CLI 1.0.105 sends the GitHub server's 18 functions with defer_loading behind a tool-search
tool: about 0.9k to 1.1k cl100k tokens reach the model up front if the backend honors deferral, about 7k if not. This
runs one default-routing session per arm (with and without --disable-builtin-mcps) per model, each in its own
signed-in lane, and reads every call's input tokens and charge from Copilot CLI's own store (assistant_usage_events),
as default_routing_ab.py does. The prompt asks for a one-word reply, so each session should make one main call.

  python billing.py <output json>
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "token-master-plugin/evals"))
import default_routing_ab as dr  # noqa: E402
import run_prs5_study as p5  # noqa: E402

PACKAGE = "1.0.105"
MODELS = ("gpt-6-astra", "claude-opus-5.5")
PROMPT = "Reply with the single word ok."
ROOT = dr.LANES_ROOT / "gh-mcp-billing"  # outside the profile: nothing inherited from ancestor folders
KEEP = ("model", "copilot_usage_model", "api_endpoint", "initiator", "agent_id", "input_tokens", "output_tokens",
        "cache_read_tokens", "cache_write_tokens", "reasoning_tokens", "total_nano_aiu")


def shutdown(home: Path) -> dict:
    """Copilot CLI's own size estimate for the session (it counts deferred definitions)."""
    for log in (home / "copilot" / "session-state").glob("*/events.jsonl"):
        for line in log.open(encoding="utf-8", errors="replace"):
            if '"session.shutdown"' in line:
                data = json.loads(line)["data"]
                return {k: data.get(k) for k in ("toolDefinitionsTokens", "systemTokens", "currentTokens")}
    return {}


def run(model: str, arm: str) -> dict:
    base = ROOT / model / arm
    home, lane, run_dir = base / "home", base / "lane", base / "run"
    shutil.rmtree(base, ignore_errors=True)
    lane.mkdir(parents=True)
    run_dir.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(lane)], check=True)
    (lane / "README.md").write_text("probe lane\n", encoding="utf-8")
    dr.PACKAGE, p5.MODEL = PACKAGE, model
    env = dr.cli_env(home)  # default routing: signed in, no provider variables
    assert "COPILOT_PROVIDER_BASE_URL" not in env and "COPILOT_OFFLINE" not in env
    version = subprocess.run([dr.LAUNCHER, "--version"], env=env, capture_output=True, text=True, timeout=180,
                             stdin=subprocess.DEVNULL).stdout.strip().splitlines()[0]
    p5.SESSION_TIMEOUT = 300
    args = ["-p", PROMPT, "--model", model, "--reasoning-effort", "low", "--allow-all-tools", "--no-ask-user",
            "--output-format", "json"] + (["--disable-builtin-mcps"] if arm == "builtin-mcps-off" else [])
    code, out, err = p5.run_copilot([str(dr.LAUNCHER), *args], lane, env)
    rows = dr.harvest(home, run_dir)
    return {"version": version, "exit": code, "calls": [{k: row[k] for k in KEEP} for row in rows],
            "usd": sum(row["total_nano_aiu"] or 0 for row in rows) / dr.NANO_PER_USD, "shutdown": shutdown(home),
            "replied_ok": '"ok' in out.lower(), "stderr_tail": err[-300:]}


def main() -> None:
    output = Path(sys.argv[1])
    results = {}
    for model in MODELS:
        for arm in ("builtin-mcps-on", "builtin-mcps-off"):
            key = f"{model} {arm}"
            results[key] = run(model, arm)
            first = (results[key]["calls"] or [{}])[0]
            print(json.dumps({key: {k: first.get(k) for k in ("model", "input_tokens", "cache_read_tokens",
                                                              "cache_write_tokens", "output_tokens")}
                              | {"calls": len(results[key]["calls"]), "usd": round(results[key]["usd"], 4)}}),
                  flush=True)
    output.write_text(json.dumps({"check": "default-routing sessions, one per arm and model", "package": PACKAGE,
                                  "prompt": PROMPT, "results": results}, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
