"""Exploratory A/B (not pre-registered): real Copilot CLI 1.0.98, stock vs the fixed TokenMaster install.

Fixes under test (October 19, 2026), after PRS-5's first 10 sessions:
  1. brainspace_setup.py --host copilot no longer installs the brainspace MCP server (its 5 tools were never
     called and cost about 500 tokens per call);
  2. the tokenmaster-nav tool descriptions tell the model when to use them instead of grep, Get-Content or view.
Same machinery as PRS-5 (run_prs5_study.py): the same lanes, relay, isolation, graders and 5 of its tasks
(H01, H04, H06, H07, H08), 2 repeats, both arms at the same time.

  python quick_copilot_ab.py --output <new folder>
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

EVALS = Path(__file__).resolve().parent
sys.path.insert(0, str(EVALS))
import run_prs1_study as p1  # noqa: E402
import run_prs5_study as p5  # noqa: E402

TASKS = ("H01", "H04", "H06", "H07", "H08")
REPEATS = 2
SEED = 20261019


def tool_calls(run_dir: Path) -> Counter:
    captures = p5.read_jsonl(run_dir / "captures.jsonl")
    if not captures:
        return Counter()
    last = json.loads(max(captures, key=lambda c: c["n"])["input"])
    return Counter(i["name"] for i in last.get("input") or [] if isinstance(i, dict) and i.get("type") == "function_call")


def summarize(out: Path) -> dict:
    rows = [r for r in p5.read_jsonl(out / "results.jsonl") if r.get("usage")]
    chosen = p1.final_rows(rows)
    arms = {}
    for arm in p5.ARMS:
        mine = [r for (t, a, _), r in chosen.items() if a == arm and r["status"] in ("pass", "fail")]
        nav = [sum(v for k, v in tool_calls(out / "runs" / r["session"]).items() if k.startswith("tokenmaster-nav"))
               for r in mine]
        arms[arm] = {"sessions": len(mine), "passes": sum(r["status"] == "pass" for r in mine),
                     "raw_tokens": sum(r["usage"]["input"] + r["usage"]["output"] for r in mine),
                     "billed": round(sum(p5.billed(r["usage"]) for r in mine)),
                     "calls": sum(r["usage"]["calls"] for r in mine),
                     "sessions_using_nav": sum(n > 0 for n in nav), "nav_calls": sum(nav),
                     "tools_sent": len(p5.request_tools(out / "runs" / mine[0]["session"])) if mine else None}
    pairs = []
    for (t, a, r), row in chosen.items():
        other = chosen.get((t, "tm", r))
        if a == "stock" and other and {row["status"], other["status"]} <= {"pass", "fail"}:
            pairs.append({"task": t, "repeat": r, "stock_raw": row["usage"]["input"] + row["usage"]["output"],
                          "tm_raw": other["usage"]["input"] + other["usage"]["output"],
                          "stock_billed": round(p5.billed(row["usage"])), "tm_billed": round(p5.billed(other["usage"])),
                          "stock_pass": row["status"] == "pass", "tm_pass": other["status"] == "pass",
                          "tm_nav_calls": sum(v for k, v in tool_calls(out / "runs" / other["session"]).items()
                                              if k.startswith("tokenmaster-nav"))})
    s, m = arms["stock"], arms["tm"]
    summary = {"kind": "exploratory, not pre-registered", "arms": arms, "pairs": sorted(pairs, key=lambda p: (p["task"], p["repeat"])),
               "raw_change": round(m["raw_tokens"] / s["raw_tokens"] - 1, 4) if s["raw_tokens"] else None,
               "billed_change": round(m["billed"] / s["billed"] - 1, 4) if s["billed"] else None,
               "tasks_lower_raw": sum(p["tm_raw"] < p["stock_raw"] for p in pairs), "pairs_total": len(pairs)}
    p5.write_json(out / "summary.json", summary)
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args(argv)
    out = args.output.resolve()
    if args.summarize_only:
        print(json.dumps(summarize(out), indent=1))
        return 0
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
    tasks = [t for t in json.loads((EVALS / "prs5_tasks.json").read_text(encoding="utf-8"))["tasks"] if t["id"] in TASKS]
    jobs = []
    for repeat in range(1, REPEATS + 1):
        order = list(TASKS)
        random.Random(SEED + repeat).shuffle(order)
        jobs += [[repeat, task_id] for task_id in order]
    p5.write_json(out / "setup.json", {"versions": versions, "install": install, "jobs": jobs})
    from brainspace import tokens
    tokens.count_tokens("warm-up")  # before worker threads (lazy init is not thread-safe)
    p5.execute(out, {"tasks": tasks}, jobs, out / "results.jsonl")
    print(json.dumps(summarize(out), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
