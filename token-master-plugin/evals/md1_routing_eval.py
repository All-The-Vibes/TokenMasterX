#!/usr/bin/env python
"""Compare --lean's regex routing with Microsoft-Decision-1 (MD-1) and their union on labelled prompts.

Each prompt is labelled with the tool families it needs. A family counts as kept when its CAPABILITY_GROUPS pattern
fires (regex), when MD-1 picks it (md1_families), or either (union, what select_excluded_tools does with MD-1 on).
Recall is over the needed families; a false keep is a family kept that the prompt does not need. Installed skill and
agent names are left out: they are the same with or without MD-1. MD1_QUESTIONS and MD1_THRESHOLD were chosen on CASES;
HELD_OUT was written afterwards and not used to choose them.

  TOKENMASTER_MD1_ENDPOINT=https://<resource>.services.ai.azure.com [TOKENMASTER_MD1_TENANT=...] \
      python evals/md1_routing_eval.py [--out results.json]
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "token-master"))
import brainspace_copilot_bridge as bridge  # noqa: E402

CASES: list[tuple[str, set[str]]] = [
    # agents
    ("have an agent review this diff", {"agents"}),
    ("get a second agent to double-check my migration", {"agents"}),
    ("hand the test writing off to a helper agent while you fix the bug", {"agents"}),
    ("split this refactor across a few workers running at the same time", {"agents"}),
    ("spawn a subagent to audit auth", {"agents"}),
    ("delegate to an agent the docs update", {"agents"}),
    ("ask a code-review agent to look over the PR before I merge", {"agents"}),
    # session history
    ("what did we decide about the cache in my last session?", {"session_history"}),
    ("find the conversation from yesterday where we fixed the login bug", {"session_history"}),
    ("look through my previous sessions for the deploy command", {"session_history"}),
    ("which files did I change in copilot last week?", {"session_history"}),
    # sql
    ("track these tasks as todos in a sql table", {"sql"}),
    ("run a sql query to count the rows we loaded", {"sql"}),
    ("load the csv into a scratch database table and group by region", {"sql"}),
    # background shell
    ("start the dev server in the background and check the logs", {"background_shell"}),
    ("run npm run dev and keep it going while you test the page", {"background_shell"}),
    ("kick off the watcher, then stop it when the build passes", {"background_shell"}),
    ("launch the api server and hit /health once it's up", {"background_shell"}),
    # copilot docs
    ("what copilot cli flags let me pick a model?", {"copilot_docs"}),
    ("how do I change the keybindings in copilot?", {"copilot_docs"}),
    ("check copilot cli documentation for the --resume flag", {"copilot_docs"}),
    ("is there a slash command in this cli to clear the context?", {"copilot_docs"}),
    # workflows
    ("run the nightly-audit workflow on this repo", {"workflows"}),
    ("write an orchestration that fans the review out to several agents", {"workflows", "agents"}),
    # skills
    ("use the tokenomics skill", {"skills"}),
    ("apply my changelog-generator skill to the last 20 commits", {"skills"}),
    # mixed
    ("start the server in the background and have an agent write e2e tests against it",
     {"background_shell", "agents"}),
    # none: everyday coding prompts
    ("fix the failing test in parser.py", set()),
    ("who calls validate_password? answer with json.", set()),
    ("rename user_id to account_id across the repo", set()),
    ("add a retry with exponential backoff to fetch_orders", set()),
    ("explain what this regex does", set()),
    ("why is the docker build slow?", set()),
    ("write unit tests for the date parser", set()),
    ("update the readme with the new install steps", set()),
    ("the sql injection in login.php, fix it", set()),
    ("review this function for off-by-one errors", set()),
    ("convert this class component to a react hook", set()),
    ("bump lodash to the latest version and run the tests", set()),
    ("make the session timeout configurable", set()),
    ("add a background color to the header", set()),
    ("what does the agent field in config.yaml control?", set()),
    ("document the workflow in CONTRIBUTING.md", set()),
]
# Written after the questions and threshold were chosen on CASES, and not used to choose them.
HELD_OUT: list[tuple[str, set[str]]] = [
    ("can another agent sanity-check this sql migration while you keep going?", {"agents"}),
    ("farm out the lint fixes to a couple of agents", {"agents"}),
    ("let a reviewer agent take a pass over src/auth", {"agents"}),
    ("pull up what I asked you on monday about the rate limiter", {"session_history"}),
    ("did we already try upgrading webpack in an older chat?", {"session_history"}),
    ("keep a todo table in sql as you go through the checklist", {"sql"}),
    ("query the scratch db for rows where status is failed", {"sql"}),
    ("boot the storybook server, leave it running and screenshot the button", {"background_shell"}),
    ("tail the worker logs in the background while I reproduce the bug", {"background_shell"}),
    ("what's the setting that turns off the banner in copilot cli?", {"copilot_docs"}),
    ("which copilot cli command shows token usage?", {"copilot_docs"}),
    ("kick off my release-check workflow", {"workflows"}),
    ("invoke the humanizer skill on the release notes", {"skills"}),
    ("fix the null check in OrderService.cs", set()),
    ("add pagination to the /users endpoint", set()),
    ("why does this sql query return duplicates?", set()),
    ("refactor the background job scheduler to use a queue", set()),
    ("rename the AgentConfig class to RunnerConfig", set()),
    ("write a github actions workflow that runs pytest", set()),
    ("speed up the session cache lookups", set()),
    ("add type hints to utils.py", set()),
    ("find where the docs site builds its sidebar", set()),
]


def regex_families(prompt: str) -> set[str]:
    return {family for family, (_, pattern) in bridge.CAPABILITY_GROUPS.items() if pattern.search(prompt)}


def score(picks: list[set[str]], cases: list[tuple[str, set[str]]] = CASES) -> dict:
    needed = sum(len(labels) for _, labels in cases)
    hits = sum(len(pick & labels) for pick, (_, labels) in zip(picks, cases))
    false = sum(len(pick - labels) for pick, (_, labels) in zip(picks, cases))
    clean = [pick for pick, (_, labels) in zip(picks, cases) if not labels]
    return {"recall": round(hits / needed, 3), "needed": needed, "kept": hits, "false_keeps": false,
            "no_need_prompts_kept_nothing": f"{sum(not pick for pick in clean)}/{len(clean)}"}


def run(cases: list[tuple[str, set[str]]], latencies: list[float]) -> tuple[dict, list[dict]]:
    rows = []
    for prompt, labels in cases:
        start = time.perf_counter()
        md1 = bridge.md1_families(prompt)
        latencies.append((time.perf_counter() - start) * 1000)
        rows.append({"prompt": prompt, "labels": sorted(labels), "regex": sorted(regex_families(prompt)),
                     "md1": sorted(md1)})
    picks = {name: [set(row[name]) for row in rows] for name in ("regex", "md1")}
    picks["union"] = [a | b for a, b in zip(picks["regex"], picks["md1"])]
    for row in rows:
        if set(row["md1"]) | set(row["regex"]) != set(row["labels"]):
            print(f"  {row['prompt']!r}: needs {row['labels']}, regex {row['regex']}, md1 {row['md1']}")
    return {name: score(value, cases) for name, value in picks.items()}, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if not os.environ.get("TOKENMASTER_MD1_ENDPOINT"):
        parser.error("set TOKENMASTER_MD1_ENDPOINT")
    bridge.md1_families("warm up")  # fetches and caches the token outside the timings
    latencies: list[float] = []
    summary, results = {}, {}
    for name, cases in (("tuning", CASES), ("held_out", HELD_OUT)):
        print(f"{name}: prompts where regex or MD-1 differ from the label")
        summary[name], results[name] = run(cases, latencies)
    latencies.sort()
    summary["md1_latency_ms"] = {"calls": len(latencies), "median": round(statistics.median(latencies)),
                                 "p90": round(latencies[int(len(latencies) * 0.9)]), "max": round(latencies[-1])}
    print(json.dumps(summary, indent=2))
    if args.out:
        args.out.write_text(json.dumps({"summary": summary, "cases": results}, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
