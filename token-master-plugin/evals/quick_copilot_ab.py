"""Exploratory A/B (not pre-registered): real Copilot CLI (1.0.78-3 in the October 2026 runs), stock vs the fixed
TokenMaster install.

Fixes under test (October 19, 2026), after PRS-5's first 10 sessions:
  1. brainspace_setup.py --host copilot no longer installs the brainspace MCP server (its 5 tools were never
     called and cost about 500 tokens per call);
  2. the tokenmaster-nav tool descriptions tell the model when to use them instead of grep, Get-Content or view.
Same machinery as PRS-5 (run_prs5_study.py): lanes, relay, isolation, graders and PRS-5's tasks, both arms at the
same time. Models: gpt-6-astra over the Responses API, or claude-opus-5.5 over Anthropic Messages (the only
formats GitHub Copilot's API offers for each). Cost uses each model's published GitHub Copilot price per 1M tokens.

  python quick_copilot_ab.py --output <new folder> [--model claude-opus-5.5] [--tasks H02,H03,H05] [--lanes name]
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import urllib.request

EVALS = Path(__file__).resolve().parent
sys.path.insert(0, str(EVALS))
import run_prs1_study as p1  # noqa: E402
import run_prs5_study as p5  # noqa: E402

DEFAULT_TASKS = ("H01", "H04", "H06", "H07", "H08")
SEED = 20261019
# PRS-4 edit tasks carry exact replacements; the grader compares the edited files with the expected result.
CHECK = """import ast, json, pathlib
expected = pathlib.Path(r'{expected}')
for name in {files!r}:
    got = pathlib.Path(name).read_text(encoding='utf-8')
    text = (expected / name).read_text(encoding='utf-8')
    if name.endswith('.py'):
        ok = ast.dump(ast.parse(got)) == ast.dump(ast.parse(text))
    elif name.endswith('.json'):
        ok = json.loads(got) == json.loads(text)
    else:
        ok = [line.rstrip() for line in got.strip().splitlines()] == [line.rstrip() for line in text.strip().splitlines()]
    assert ok, name
"""


def load_tasks(task_ids: tuple, out: Path) -> list[dict]:
    """PRS-5 heavy tasks (H..) and PRS-4 simple tasks (P..), both verified against the 703aa20 snapshot."""
    known = {}
    for name in ("prs4_tasks.json", "prs5_tasks.json"):
        for task in json.loads((EVALS / name).read_text(encoding="utf-8"))["tasks"]:
            known[task["id"]] = task
    tasks = []
    for task_id in task_ids:
        task = dict(known[task_id])
        if task["category"] == "edit" and task.get("edit_oracle") and not task.get("check"):
            reps = task["edit_oracle"]["replacements"]
            files = sorted({r["file"] for r in reps})
            for name in files:
                target = out / "expected" / task_id / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(p1.expected_source(out / "templates" / "stock", name, reps), encoding="utf-8")
            task.update(check=CHECK.format(expected=str(out / "expected" / task_id), files=files), allowed_paths=files)
        elif task["category"] not in ("investigate", "edit", "feature"):
            task["category"] = "investigate"
        tasks.append(task)
    return tasks
# GitHub Copilot models-and-pricing, USD per 1M tokens: new input, cached input, cache write, output.
USD_PER_M = {"gpt-6-astra": (10.00, 1.00, 12.50, 50.00), "claude-opus-5.5": (4.00, 0.20, 5.00, 20.00)}
ANTHROPIC = ("claude-",)


def configure(model: str, lanes: str) -> None:
    """Point run_prs5_study at the chosen model, wire format and lane folder."""
    p5.MODEL = model
    p5.FLAGS = ["--model", model, *p5.FLAGS[2:]]
    p5.LANES = Path(tempfile.gettempdir()) / "opencode" / lanes
    if not model.startswith(ANTHROPIC):
        return
    original_env, original_relay = p5.cli_env, p5.Relay

    def cli_env(home, base_url):
        env = original_env(home, base_url)
        env["COPILOT_PROVIDER_TYPE"] = "anthropic"
        env.pop("COPILOT_PROVIDER_WIRE_API", None)
        return env

    class Relay(original_relay):
        def prepare(self, path, body):  # record Anthropic Messages calls too
            route = path.split("?")[0]
            return super().prepare("/responses" if route.endswith("/messages") else path, body)

    def warmup(relays, out):
        body = json.dumps({"model": model, "max_tokens": 64, "messages": [{"role": "user", "content": "Reply with OK."}]})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        receipt = {}
        for arm, relay in relays.items():
            request = urllib.request.Request(relay.url + "/v1/messages", data=body.encode(), method="POST",
                                             headers={"Content-Type": "application/json", "anthropic-version": "2023-06-01"})
            try:
                with opener.open(request, timeout=120) as response:
                    receipt[arm] = response.status
            except Exception as error:  # recorded and fatal below
                receipt[arm] = f"{type(error).__name__}: {getattr(error, 'code', '')}"
        p5.write_json(out / "warmup.json", receipt)
        if any(status != 200 for status in receipt.values()):
            raise SystemExit(f"relay warm-up failed: {receipt}")

    p5.cli_env, p5.Relay, p5.warmup = cli_env, Relay, warmup


def tool_calls(run_dir: Path) -> Counter:
    captures = p5.read_jsonl(run_dir / "captures.jsonl")
    if not captures:
        return Counter()
    last = json.loads(max(captures, key=lambda c: c["n"])["input"])
    names = Counter(i["name"] for i in last.get("input") or [] if isinstance(i, dict) and i.get("type") == "function_call")
    for message in last.get("messages") or []:  # Anthropic Messages
        if isinstance(message, dict) and message.get("role") == "assistant" and isinstance(message.get("content"), list):
            names.update(b["name"] for b in message["content"] if isinstance(b, dict) and b.get("type") == "tool_use")
    return names


def usd(usage: dict, model: str) -> float:
    new, cached, write, output = USD_PER_M[model]
    return ((usage["input"] - usage["cached"] - usage["cache_write"]) * new + usage["cached"] * cached
            + usage["cache_write"] * write + usage["output"] * output) / 1e6


def summarize(out: Path, model: str) -> dict:
    rows = [r for r in p5.read_jsonl(out / "results.jsonl") if r.get("usage")]
    chosen = p1.final_rows(rows)
    arms, prices_seen = {}, set()
    for arm in p5.ARMS:
        mine = [r for (t, a, _), r in chosen.items() if a == arm and r["status"] in ("pass", "fail")]
        nav = [sum(v for k, v in tool_calls(out / "runs" / r["session"]).items() if k.startswith("tokenmaster-nav"))
               for r in mine]
        for r in mine:
            prices_seen |= {tuple(pair) for group in r["usage"].get("bill_ratios") or [] for pair in group}
        arms[arm] = {"sessions": len(mine), "passes": sum(r["status"] == "pass" for r in mine),
                     "raw_tokens": sum(r["usage"]["input"] + r["usage"]["output"] for r in mine),
                     "cached_tokens": sum(r["usage"]["cached"] for r in mine),
                     "usd": round(sum(usd(r["usage"], model) for r in mine), 4),
                     "calls": sum(r["usage"]["calls"] for r in mine),
                     "sessions_using_nav": sum(n > 0 for n in nav), "nav_calls": sum(nav),
                     "warm_starts": sum((r["first_call"].get("cached") or 0) >= 0.5 * (r["first_call"].get("input") or 1)
                                        for r in mine),
                     "tools_sent": len(p5.request_tools(out / "runs" / mine[0]["session"])) if mine else None,
                     "infra": sum(r["status"] == "infra" for (t, a, _), r in chosen.items() if a == arm)}
    pairs = []
    for (t, a, r), row in chosen.items():
        other = chosen.get((t, "tm", r))
        if a == "stock" and other and {row["status"], other["status"]} <= {"pass", "fail"}:
            pairs.append({"task": t, "repeat": r, "stock_raw": row["usage"]["input"] + row["usage"]["output"],
                          "tm_raw": other["usage"]["input"] + other["usage"]["output"],
                          "stock_usd": round(usd(row["usage"], model), 4), "tm_usd": round(usd(other["usage"], model), 4),
                          "stock_pass": row["status"] == "pass", "tm_pass": other["status"] == "pass",
                          "stock_calls": row["usage"]["calls"], "tm_calls": other["usage"]["calls"],
                          "tm_nav_calls": sum(v for k, v in tool_calls(out / "runs" / other["session"]).items()
                                              if k.startswith("tokenmaster-nav"))})
    s, m = arms["stock"], arms["tm"]
    summary = {"kind": "exploratory, not pre-registered", "model": model, "usd_per_million": USD_PER_M[model],
               "provider_price_ratios_seen": sorted(prices_seen), "arms": arms,
               "pairs": sorted(pairs, key=lambda p: (p["task"], p["repeat"])),
               "raw_change": round(m["raw_tokens"] / s["raw_tokens"] - 1, 4) if s["raw_tokens"] else None,
               "usd_change": round(m["usd"] / s["usd"] - 1, 4) if s["usd"] else None,
               "pairs_lower_raw": sum(p["tm_raw"] < p["stock_raw"] for p in pairs), "pairs_total": len(pairs)}
    p5.write_json(out / "summary.json", summary)
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-6-astra", choices=sorted(USD_PER_M))
    parser.add_argument("--tasks", default=",".join(DEFAULT_TASKS))
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--lanes", default="prs5-lanes")
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args(argv)
    out = args.output.resolve()
    task_ids = tuple(args.tasks.split(","))
    if args.summarize_only:
        print(json.dumps(summarize(out, args.model), indent=1))
        return 0
    configure(args.model, args.lanes)
    if out.exists():
        raise SystemExit(f"output must be new: {out}")
    if p5.LANES.exists():
        p1.remove_tree(p5.LANES)
    out.mkdir(parents=True)
    tar = out / "snapshot.tar"
    subprocess.run([str(p1.GIT_EXE), "archive", "--format=tar", "-o", str(tar), p1.SNAPSHOT_COMMIT,
                    *p1.SNAPSHOT_PATHS], cwd=p1.REPO, check=True)
    p5.git_snapshot(out / "templates" / "stock", tar)
    versions = {arm: p5.cli_version(p5.lane_root(arm) / "home") for arm in p5.ARMS}
    if set(versions.values()) != {p5.CLI_VERSION}:
        raise SystemExit(f"Copilot CLI version must be {p5.CLI_VERSION!r}: {versions}")
    tm_repo = p5.lane_root("tm") / "tokenmaster"
    p5.git_snapshot(tm_repo, tar)
    install = p5.install_tm(p5.lane_root("tm") / "home", tm_repo)
    shutil.copytree(tm_repo, out / "templates" / "tm")
    tasks = load_tasks(task_ids, out)
    jobs = []
    for repeat in range(1, args.repeats + 1):
        order = list(task_ids)
        random.Random(SEED + repeat).shuffle(order)
        jobs += [[repeat, task_id] for task_id in order]
    p5.write_json(out / "setup.json", {"model": args.model, "versions": versions, "install": install, "jobs": jobs,
                                       "lanes": str(p5.LANES)})
    from brainspace import tokens
    tokens.count_tokens("warm-up")  # before worker threads (lazy init is not thread-safe)
    p5.execute(out, {"tasks": tasks}, jobs, out / "results.jsonl")
    print(json.dumps(summarize(out, args.model), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
