"""Exploratory A/B (not pre-registered): stock Copilot CLI vs TokenMaster with Copilot CLI's default GitHub routing.

Every earlier real-CLI run (PRS-5, PRS-6, quick_copilot_ab.py, django_ab.py) used bring-your-own-model mode through
the evaluation relay. Here neither arm sets COPILOT_PROVIDER_BASE_URL: Copilot CLI signs in with the operator's stored
Copilot CLI login and sends every request to GitHub's Copilot API itself. Without a provider URL the TokenMaster
launcher applies only the lean tool set; tokenmaster-nav and the v6 view hook still load; the bridge does not run.

Measurement: no relay sees the traffic. Copilot CLI records every model call in <COPILOT_HOME>/session-store.db, table
assistant_usage_events: GitHub's token counts and GitHub's charge (total_nano_aiu; 1e9 nano = 1 AI credit = $0.01),
the store that tokenomics.py reads. After each session the harness copies the store into the session folder and writes
its numbers (no content) to calls.jsonl, before the next session clears Copilot's history.

Sign-in: each lane's config.json gets the account names from the operator's ~/.copilot/config.json (lastLoggedInUser,
loggedInUsers). The token stays in Windows Credential Manager; the harness never reads it.

Otherwise the machinery of run_prs5_study.py: one lane per arm, reset from a read-only template before each session,
an allowlisted environment with no Python on PATH, PRS-6's flags and graders, both arms at the same time.

  python default_routing_ab.py --suite repo --tasks P02,P03,... --output <new folder> --lanes <name> [--model M]
  python default_routing_ab.py --suite django --repo <django checkout> --tasks-file <tasks.json> --tasks D09,D01,...
                               --output <new folder> --lanes <name> [--model M]
  python default_routing_ab.py --self-test
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

EVALS = Path(__file__).resolve().parent
sys.path.insert(0, str(EVALS))
import quick_copilot_ab as q  # noqa: E402
import run_prs1_study as p1  # noqa: E402
import run_prs5_study as p5  # noqa: E402

import tokenomics  # noqa: E402  (SKILL is on sys.path through run_prs1_study)

PACKAGE = "1.0.104"  # the latest release on October 27, 2026; see cli_env for why an older pin does not hold
CLI_VERSION = f"GitHub Copilot CLI {PACKAGE}."
LAUNCHER = (Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
            / "GitHub.Copilot_Microsoft.Winget.Source_8wekyb3d8bbwe" / "copilot.exe")
MODEL = "gpt-6-astra"  # PRS-6's model; the operator's account runs it under default routing when --model names it
# Copilot CLI inherits instructions (CLAUDE.md) and skills from every ancestor folder of its working directory, and
# C:\Users\<name> holds the operator's .claude, .copilot and .agents folders. Lanes under %TEMP% loaded about 170 of
# the operator's skills and their CLAUDE.md into both arms' system prompts, so the lanes live outside the profile.
LANES_ROOT = Path(os.environ.get("TM_LANES_ROOT", r"C:\tm-lanes"))
NANO_PER_USD = tokenomics.NANO_PER_USD
USAGE_COLUMNS = ("session_id", "turn_index", "agent_id", "model", "copilot_usage_model", "api_endpoint", "initiator",
                 "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens",
                 "total_nano_aiu", "request_multiplier", "token_details_json", "created_at")
INFRA_TEXT = re.compile(r"\b(429|500|502|503|504)\b|rate.?limit|ECONNRESET|ETIMEDOUT|socket hang up", re.I)
ERROR_EVENTS = ("session.error", "model.call_failure")
BUDGET_ALLOWANCE = 60e9  # nano-AIU (60 AI credits) kept free for the next session before the budget stops the run
_BASE_ENV = p5.base_env


def base_env(home: Path, extra_path: tuple = ()) -> dict:
    env = _BASE_ENV(home, extra_path)
    env["GRAPHIFY_NO_AUTO_REFRESH"] = "1"  # graphify 0.9.91 rewrites ~/.claude/skills/graphify when it starts
    return env


def configure(model: str, lanes: str, graphify: Path | None = None) -> None:
    """Point run_prs5_study at default routing, the pinned package, the model, the lane folder and graphify."""
    p5.MODEL = model
    p5.FLAGS = ["--model", model, *p5.FLAGS[2:]]
    p5.LANES = LANES_ROOT / lanes
    p5.COPILOT = str(LAUNCHER)  # the WinGet package folder goes on the agents' PATH, not WindowsApps
    tokenizer = Path(os.environ.get("BRAINSPACE_TOKENIZER_FILE") or p5.TOKENIZER)
    if not tokenizer.is_file():
        raise SystemExit(f"tokenizer not found: {tokenizer}; set BRAINSPACE_TOKENIZER_FILE")
    p5.TOKENIZER = tokenizer
    if graphify:
        p1.GRAPHIFY_EXE = graphify  # install_tm puts its folder first on setup.py's PATH
    p5.base_env, p5.cli_env = base_env, cli_env


def operator_config() -> dict:
    text = (Path.home() / ".copilot" / "config.json").read_text(encoding="utf-8-sig")
    return json.loads("\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//")))


def sign_in(config: Path, source: dict | None = None) -> dict:
    """Write the operator's Copilot CLI account names (never a token) into a lane's config.json."""
    data = operator_config() if source is None else source
    user = data.get("lastLoggedInUser") or {}
    if not user.get("host") or not user.get("login"):
        raise SystemExit("no Copilot CLI sign-in in ~/.copilot/config.json; run `copilot login` first")
    names = {"lastLoggedInUser": {"host": user["host"], "login": user["login"]},
             "loggedInUsers": [{k: u[k] for k in ("host", "login", "kind") if k in u}
                               for u in data.get("loggedInUsers") or [] if isinstance(u, dict)]}
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps(names, indent=2) + "\n", encoding="utf-8")
    return names["lastLoggedInUser"]


def cli_env(home: Path, _base_url: str = "") -> dict:
    """Default GitHub routing: no provider variables. The pinned package runs from the lane's own profile.
    Auto-update stays on: with COPILOT_AUTO_UPDATE=false the launcher ignores COPILOT_CLI_DIST_DIR and runs its
    built-in 1.0.49. With it on, a session of an older pin (1.0.98-2 in the pilot) downloads the latest release, and
    the next launch runs that instead, so the pin is the latest release, and each session's version is checked."""
    env = base_env(home)
    env.update({"COPILOT_ALLOW_ALL": "true", "COPILOT_MODEL": p5.MODEL})
    target = Path(env["LOCALAPPDATA"]) / "copilot" / "pkg" / "win32-x64" / PACKAGE
    if not target.exists():
        shutil.copytree(p5.INSTALLED_PKG / "win32-x64" / PACKAGE, target)
    env["COPILOT_CLI_DIST_DIR"] = str(target)
    if not (home / "copilot" / "config.json").exists():
        sign_in(home / "copilot" / "config.json")
    return env


# --------------------------------------------------------------------------- measurement

def harvest(home: Path, run_dir: Path, since: str = "") -> list[dict]:
    """Copilot CLI's own record of this session's model calls: copy the store (with its WAL), keep the numbers of
    the calls made since the session started (ISO times with milliseconds and Z compare as strings)."""
    store = home / "copilot" / "session-store.db"
    if not store.exists():
        return []
    copy = run_dir / "store"
    copy.mkdir(exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        if Path(f"{store}{suffix}").exists():
            shutil.copy2(f"{store}{suffix}", copy / f"session-store.db{suffix}")
    connection = sqlite3.connect(copy / "session-store.db")
    try:
        columns = {row[1] for row in connection.execute("pragma table_info(assistant_usage_events)")}
        if not columns:
            return []
        select = ", ".join(c if c in columns else f"null as {c}" for c in USAGE_COLUMNS)
        rows = [dict(zip(USAGE_COLUMNS, r)) for r in
                connection.execute(f"select {select} from assistant_usage_events order by created_at, rowid")
                if (r[USAGE_COLUMNS.index("created_at")] or "") >= since]
    finally:
        connection.close()
    with (run_dir / "calls.jsonl").open("w", encoding="utf-8") as handle:
        for n, row in enumerate(rows, 1):
            handle.write(json.dumps({"n": n, **row}) + "\n")
    return rows


def recharge(row: dict) -> float:
    """GitHub's charge for one call recomputed from its token counts and GitHub's own per-token prices."""
    prices = tokenomics.prices_of(row["token_details_json"])
    read, write = row["cache_read_tokens"] or 0, row["cache_write_tokens"] or 0
    new = (row["input_tokens"] or 0) - read - write
    return (new * prices.get("input", 0) + read * prices.get("cache_read", 0) + write * prices.get("cache_write", 0)
            + (row["output_tokens"] or 0) * prices.get("output", 0))


def session_usage(rows: list[dict]) -> dict:
    """Sums over all calls, subagents included (the relay counted those too), and the first main-agent call."""
    usage = {"calls": len(rows), "input": 0, "cached": 0, "cache_write": 0, "output": 0, "nano": 0,
             "nano_recount_max_diff": 0.0, "subagent_calls": sum(bool(r["agent_id"]) for r in rows),
             "models": sorted({r["model"] or "unknown" for r in rows}),
             "session_ids": sorted({r["session_id"] or "" for r in rows})}
    for r in rows:
        usage["input"] += r["input_tokens"] or 0
        usage["cached"] += r["cache_read_tokens"] or 0
        usage["cache_write"] += r["cache_write_tokens"] or 0
        usage["output"] += r["output_tokens"] or 0
        usage["nano"] += r["total_nano_aiu"] or 0
        usage["nano_recount_max_diff"] = max(usage["nano_recount_max_diff"],
                                             abs(recharge(r) - (r["total_nano_aiu"] or 0)))
    first = next((r for r in rows if not r["agent_id"]), None)
    prices = tokenomics.prices_of(first["token_details_json"]) if first else {}
    moved = (first["cache_read_tokens"] or 0) if first else 0
    usage["first_call"] = {"input": first["input_tokens"], "cached": first["cache_read_tokens"],
                           "cache_write": first["cache_write_tokens"], "output": first["output_tokens"]} if first else {}
    # cold: every first call misses the cache, so the tokens it read are written instead
    usage["nano_cold"] = usage["nano"] + moved * (prices.get("cache_write", 0) - prices.get("cache_read", 0))
    return usage


def session_events(home: Path, run_dir: Path) -> dict:
    """Copilot CLI's own event log of the session: its version and the tools it called."""
    version, tools = None, Counter()
    for events in (home / "copilot" / "session-state").glob("*/events.jsonl"):
        shutil.copy2(events, run_dir / f"events-{events.parent.name[:8]}.jsonl")
        for line in events.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            data = event.get("data") if isinstance(event, dict) else None
            if not isinstance(data, dict):
                continue
            if event.get("type") == "session.start":
                version = data.get("copilotVersion") or version
            elif event.get("type") == "tool.execution_start":
                tools[data.get("toolName") or "?"] += 1
    return {"version": version, "tools": dict(tools),
            "nav_calls": sum(n for name, n in tools.items() if name.startswith("tokenmaster-nav"))}


def stdout_events(stdout: str) -> dict:
    """Copilot CLI's JSON event stream: errors (JSON mode writes them here, not to stderr), whether the model gave a
    final answer, and the CLI's own running charge for the session (the last usage checkpoint)."""
    errors, answered, cli_nano = [], False, None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        kind = event.get("type")
        if kind in ERROR_EVENTS:
            errors.append(f"{kind}: {json.dumps(data)[:300]}")
        elif kind == "assistant.message" and data.get("phase") == "final_answer" and str(data.get("content")).strip():
            answered = True
        elif kind == "session.usage_checkpoint":
            cli_nano = data.get("totalNanoAiu", cli_nano)
    return {"errors": errors, "answered": answered, "cli_nano": cli_nano}


def classify(code, rows: list[dict], events: dict, verdict: dict) -> tuple[str, str]:
    """Infrastructure: no model call at all, or the session ended without an answer on a rate-limit or 5xx error."""
    if not rows:
        return "infra", f"infra:exit={code}:no_model_call"
    if not events["answered"] and any(INFRA_TEXT.search(e) for e in events["errors"]):
        return "infra", f"infra:exit={code}:provider_error"
    if code == "timeout":
        return "fail", "timeout"
    return ("pass" if verdict["pass"] else "fail"), verdict["why"]


def clear_history(home: Path) -> None:
    """run_prs5_study.clear_history, checked: a store left behind would merge two sessions' calls."""
    copilot = home / "copilot"
    for attempt in range(6):
        p5.clear_history(home)
        left = [p for p in [copilot / "session-state", *copilot.glob("session-store.db*")] if p.exists()]
        if not left:
            return
        time.sleep(2 * (attempt + 1))  # Windows: a process that is still exiting can hold a file for a moment
    raise RuntimeError(f"history not cleared: {left}")


# --------------------------------------------------------------------------- sessions

def run_session(out: Path, arm: str, task: dict, repeat: int, *, suffix: str = "") -> dict:
    sid = f"{task['id']}-{arm}-r{repeat}{suffix}"
    run_dir = out / "runs" / sid
    run_dir.mkdir(parents=True)
    root = p5.lane_root(arm)
    home, lane, template = root / "home", root / "tokenmaster", out / "templates" / arm
    p5.reset_lane(lane, template)
    clear_history(home)
    env = cli_env(home)
    args = [p5.COPILOT, "-p", task["prompt"], *p5.FLAGS]
    if arm == "tm":  # no provider URL: the launcher adds the lean tool set and starts Copilot CLI unchanged otherwise
        args = [sys.executable, "-B", str(home / "copilot" / "token-master" / "brainspace_copilot_bridge.py"), "--",
                *args]
    started = time.time()
    since = datetime.fromtimestamp(started, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    code, stdout, stderr = p5.run_copilot(args, lane, env)
    wall = round(time.time() - started, 1)
    (run_dir / "stdout.jsonl").write_text(stdout or "", encoding="utf-8")
    (run_dir / "stderr.txt").write_text(stderr or "", encoding="utf-8")
    rows = harvest(home, run_dir, since)
    events = {**session_events(home, run_dir), **stdout_events(stdout or "")}
    final = p5.final_answer(stdout or "")
    verdict = p5.grade(task, final, lane, template)
    status, why = classify(code, rows, events, verdict)
    for rel in verdict.get("changed", [])[:20]:
        if (lane / rel).is_file():
            keep = run_dir / "changed" / rel
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(lane / rel, keep)
    usage = session_usage(rows)
    return {"task": task["id"], "set": "primary", "category": task["category"], "arm": arm, "repeat": repeat,
            "session": sid, "status": status, "why": why, "exit": code, "answer": verdict.get("answer"),
            "final_text": (final or "")[:2000], "changed": verdict.get("changed", []),
            "check_tail": verdict.get("check_tail"), "usage": usage, "first_call": usage.pop("first_call"),
            "copilot_version": events["version"], "tools": events["tools"], "nav_calls": events["nav_calls"],
            "answered": events["answered"], "errors": events["errors"][:5], "cli_nano": events["cli_nano"],
            "wall_seconds": wall, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))}


def execute(out: Path, tasks: list[dict], jobs: list[list], results: Path, budget_credits: float | None = None) -> None:
    """Both arms at the same time. With a budget, no session starts once the spend so far plus one session's
    allowance would pass it; the sessions not started are missing from the results."""
    by_id = {t["id"]: t for t in tasks}
    lock = threading.Lock()
    spent = [0.0]  # nano-AIU over every session of this run, failed ones included

    def affordable() -> bool:
        with lock:
            return budget_credits is None or spent[0] + BUDGET_ALLOWANCE <= budget_credits * 1e9

    def one(arm: str, task: dict, repeat: int, suffix: str = "") -> dict | None:
        if not affordable():
            print(f"[{task['id']}-{arm}-r{repeat}{suffix}] not started: budget of {budget_credits} credits", flush=True)
            return None
        try:
            row = run_session(out, arm, task, repeat, suffix=suffix)
        except Exception as error:  # recorded as infrastructure, never silently dropped
            row = p5.failed_row(task, arm, repeat, suffix, error)
        calls = p5.read_jsonl(out / "runs" / row["session"] / "calls.jsonl")
        with lock:
            spent[0] += sum(c.get("total_nano_aiu") or 0 for c in calls)
        p1.append_jsonl(results, row, lock)
        u = row.get("usage") or {"calls": 0, "input": 0, "output": 0, "nano": 0}
        print(f"[{row['session']:<22}] {row['status']:<5} calls={u['calls']:>3} raw={u['input'] + u['output']:>10,} "
              f"usd={u['nano'] / NANO_PER_USD:.4f} first_cached={row['first_call'].get('cached')} why={row['why']} "
              f"run_credits={spent[0] / 1e9:.1f}", flush=True)
        return row

    def lane(arm: str) -> None:
        rows = [row for repeat, task_id in jobs if (row := one(arm, by_id[task_id], repeat))]
        for row in [r for r in rows if r["status"] == "infra"]:  # one re-run per infrastructure failure
            one(arm, by_id[row["task"]], row["repeat"], "-rerun")

    with ThreadPoolExecutor(max_workers=len(p5.ARMS)) as pool:
        list(pool.map(lane, p5.ARMS))


def lean_excluded(task: dict) -> list[str]:
    """The built-in tools that the installed launcher removes for this prompt (capability-aware routing)."""
    home, lane = p5.lane_root("tm") / "home", p5.lane_root("tm") / "tokenmaster"
    code = ("import json, sys; sys.path.insert(0, sys.argv[1]); import brainspace_copilot_bridge as b; "
            "print(json.dumps(list(b.select_excluded_tools(sys.argv[2:]))))")
    proc = subprocess.run([sys.executable, "-B", "-c", code, str(home / "copilot" / "token-master"), "copilot", "-p",
                           task["prompt"], *p5.FLAGS], cwd=lane, env=cli_env(home), capture_output=True, text=True,
                          encoding="utf-8", timeout=120, stdin=subprocess.DEVNULL)
    if proc.returncode:
        raise SystemExit(f"lean tool selection failed: {proc.stderr[-800:]}")
    return json.loads(proc.stdout)


def lane_sources(arm: str) -> dict:
    """The skills and instruction files a session in this lane loads. Nothing may come from outside the study: stock
    sees Copilot CLI's built-in skills only, tm also the skills its own install added to COPILOT_HOME."""
    home, lane = p5.lane_root(arm) / "home", p5.lane_root(arm) / "tokenmaster"
    found = {}
    for name, args in (("skills", ["skill", "list"]), ("instructions", ["instruction", "list"])):
        proc = subprocess.run([p5.COPILOT, *args], cwd=lane, env=cli_env(home), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=180, stdin=subprocess.DEVNULL)
        found[name] = (proc.stdout + proc.stderr).strip().splitlines()
    if found["instructions"] != ["No instruction sources found."] or \
            skill_groups(found["skills"]).keys() - {"Builtin skills", "Personal skills"} or \
            skill_groups(found["skills"]).get("Personal skills", []) != \
            sorted(p.name for p in (home / "copilot" / "skills").glob("*") if p.is_dir()):
        raise SystemExit(f"{arm}: the lane loads skills or instructions from outside the study: {found}")
    return found


def skill_groups(lines: list[str]) -> dict:
    """`copilot skill list` output as {"Builtin skills": [names], ...}."""
    groups, current = {}, None
    for line in lines:
        if line.endswith(":") and not line.startswith(" "):
            current = groups.setdefault(line[:-1], [])
        elif line.startswith("  ") and current is not None:
            current.append(line.split(" - ")[0].strip())
    return {name: sorted(skills) for name, skills in groups.items()}


def summarize(out: Path) -> dict:
    chosen = p1.final_rows(p5.read_jsonl(out / "results.jsonl"))
    arms = {}
    for arm in p5.ARMS:
        mine = [r for (_, a, _), r in chosen.items() if a == arm and r["status"] in ("pass", "fail")]
        arms[arm] = {"sessions": len(mine), "passes": sum(r["status"] == "pass" for r in mine),
                     "raw_tokens": sum(r["usage"]["input"] + r["usage"]["output"] for r in mine),
                     "calls": sum(r["usage"]["calls"] for r in mine),
                     "usd_as_run": round(sum(r["usage"]["nano"] for r in mine) / NANO_PER_USD, 4),
                     "usd_cold": round(sum(r["usage"]["nano_cold"] for r in mine) / NANO_PER_USD, 4),
                     "nav_calls": sum(r["nav_calls"] for r in mine),
                     "warm_starts": sum((r["first_call"].get("cached") or 0) >= 0.5 * (r["first_call"].get("input") or 1)
                                        for r in mine),
                     "models": sorted({m for r in mine for m in r["usage"]["models"]}),
                     "versions": sorted({str(r["copilot_version"]) for r in mine}),
                     "infra": sum(r["status"] == "infra" for (_, a, _), r in chosen.items() if a == arm)}
    s, m = arms["stock"], arms["tm"]
    summary = {"kind": "exploratory, not pre-registered; default GitHub routing", "arms": arms,
               "raw_change": round(m["raw_tokens"] / s["raw_tokens"] - 1, 4) if s["raw_tokens"] else None,
               "usd_cold_change": round(m["usd_cold"] / s["usd_cold"] - 1, 4) if s["usd_cold"] else None,
               "usd_as_run_change": round(m["usd_as_run"] / s["usd_as_run"] - 1, 4) if s["usd_as_run"] else None}
    p5.write_json(out / "summary.json", summary)
    return summary


# --------------------------------------------------------------------------- self-test

def _store(path: Path, rows: list[tuple]) -> None:
    connection = sqlite3.connect(path)
    connection.execute("create table assistant_usage_events (id text, session_id text, agent_id text, model text, "
                       "input_tokens int, output_tokens int, cache_read_tokens int, cache_write_tokens int, "
                       "total_nano_aiu int, token_details_json text, created_at text)")
    for i, (agent, model, inp, read, write, out, at) in enumerate(rows):
        prices = {"input": 2e5, "cache_read": 1e4, "cache_write": 2.5e5, "output": 1e6}  # gpt-6.1-sol, nano per token
        counts = {"input": inp - read - write, "cache_read": read, "cache_write": write, "output": out}
        details = [{"batchSize": 1000000, "costPerBatch": int(prices[k] * 1e6), "tokenCount": counts[k], "tokenType": k}
                   for k in prices]
        nano = sum(prices[k] * counts[k] for k in prices)
        connection.execute("insert into assistant_usage_events values (?,?,?,?,?,?,?,?,?,?,?)",
                           (f"c{i}", "s1", agent, model, inp, out, read, write, int(nano), json.dumps(details), at))
    connection.commit()
    connection.close()


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home, run_dir = Path(tmp) / "home", Path(tmp) / "run"
        (home / "copilot").mkdir(parents=True)
        run_dir.mkdir()
        assert harvest(home, run_dir) == []  # no store: the session made no model call
        _store(home / "copilot" / "session-store.db", [
            (None, "gpt-6.1-sol", 9000, 0, 8990, 10, "2026-10-27T00:59:59.999Z"),  # an earlier session's call
            (None, "gpt-6.1-sol", 15000, 6000, 8900, 100, "2026-10-27T01:00:02.000Z"),
            ("sub1", "gpt-6.1-sol", 4000, 0, 3900, 50, "2026-10-27T01:00:03.000Z"),  # a subagent call still counts
            (None, "gpt-6.1-sol", 16000, 15000, 900, 200, "2026-10-27T01:00:04.000Z")])
        assert len(harvest(home, run_dir)) == 4
        rows = harvest(home, run_dir, "2026-10-27T01:00:00.000Z")  # only calls since the session started
        assert [r["input_tokens"] for r in rows] == [15000, 4000, 16000]
        assert len(p5.read_jsonl(run_dir / "calls.jsonl")) == 3 and (run_dir / "store" / "session-store.db").exists()
        usage = session_usage(rows)
        assert (usage["calls"], usage["input"], usage["cached"], usage["cache_write"], usage["output"]) == \
               (3, 35000, 21000, 13700, 350)
        assert usage["subagent_calls"] == 1 and usage["models"] == ["gpt-6.1-sol"] and usage["session_ids"] == ["s1"]
        assert usage["nano_recount_max_diff"] < 1 and usage["first_call"]["cached"] == 6000
        assert abs(usage["nano_cold"] - usage["nano"] - 6000 * (2.5e5 - 1e4)) < 1  # first-call reads repriced as writes
        assert session_usage([])["nano_cold"] == 0
        config = Path(tmp) / "lane" / "config.json"
        user = sign_in(config, {"lastLoggedInUser": {"host": "https://example.ghe.com", "login": "me", "token": "x"},
                                "loggedInUsers": [{"host": "https://example.ghe.com", "login": "me", "kind": "proxima",
                                                   "token": "secret"}], "staff": True})
        written = json.loads(config.read_text(encoding="utf-8"))
        assert user == {"host": "https://example.ghe.com", "login": "me"} and "secret" not in config.read_text()
        assert set(written) == {"lastLoggedInUser", "loggedInUsers"} and written["loggedInUsers"][0]["kind"] == "proxima"
        try:
            sign_in(config, {"loggedInUsers": []})
            raise AssertionError("a missing sign-in must stop the run")
        except SystemExit:
            pass
        state = home / "copilot" / "session-state" / "abcdef0123"
        state.mkdir(parents=True)
        (state / "events.jsonl").write_text("\n".join(json.dumps(e) for e in [
            {"type": "session.start", "data": {"copilotVersion": PACKAGE}},
            {"type": "tool.execution_start", "data": {"toolName": "tokenmaster-nav-impact"}},
            {"type": "tool.execution_start", "data": {"toolName": "view"}},
            {"type": "tool.execution_start", "data": {"toolName": "tokenmaster-nav-impact"}}]) + "\nnot json\n",
            encoding="utf-8")
        events = session_events(home, run_dir)
        assert events == {"version": PACKAGE, "tools": {"tokenmaster-nav-impact": 2, "view": 1}, "nav_calls": 2}
        assert (run_dir / "events-abcdef01.jsonl").exists()
        stream = "\n".join(json.dumps(e) for e in [
            {"type": "assistant.message", "data": {"content": "looking", "phase": None}},
            {"type": "session.error", "data": {"errorType": "model_call", "message": "429 Too Many Requests"}},
            {"type": "session.usage_checkpoint", "data": {"totalNanoAiu": 123}}])
        died = stdout_events(stream)
        assert died["errors"] and not died["answered"] and died["cli_nano"] == 123
        done = stdout_events(stream + "\n" + json.dumps({"type": "assistant.message",
                                                          "data": {"content": '{"callers": []}', "phase": "final_answer"}}))
        assert done["answered"]
        quiet = {"errors": [], "answered": True}
        ok, bad = {"pass": True, "why": "ok"}, {"pass": False, "why": "wrong:callers"}
        assert classify(0, rows, quiet, ok) == ("pass", "ok") and classify(0, rows, quiet, bad) == ("fail", "wrong:callers")
        assert classify("timeout", rows, quiet, ok) == ("fail", "timeout")
        assert classify("timeout", [], quiet, bad)[0] == "infra"  # no model call: nothing to grade
        assert classify(1, rows, died, bad)[0] == "infra"  # ended on a rate limit, without an answer
        assert classify(0, rows, died, bad)[0] == "infra"  # the CLI can exit 0 after a failed model call
        assert classify(1, rows, {**done, "errors": died["errors"]}, bad) == ("fail", "wrong:callers")  # it answered
        assert classify(1, rows, {"errors": ["session.error: model refused"], "answered": False}, bad)[0] == "fail"
        assert skill_groups(["Personal skills:", "  tokenomics - x", "", "Builtin skills:", "  b - y", "  a - z"]) == \
               {"Personal skills": ["tokenomics"], "Builtin skills": ["a", "b"]}
        (home / "copilot" / "session-state" / "abcdef0123" / "events.jsonl").unlink()
        clear_history(home)
        assert not (home / "copilot" / "session-store.db").exists() and not (home / "copilot" / "session-state").exists()
        p5.LANES = Path(tmp) / "lanes"
        env = base_env(Path(tmp) / "envhome")
        assert "COPILOT_PROVIDER_BASE_URL" not in env and "COPILOT_OFFLINE" not in env
        assert "python" not in env["PATH"].lower() and env["GRAPHIFY_NO_AUTO_REFRESH"] == "1"
    print("self-test passed")


# --------------------------------------------------------------------------- prepare and run

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--suite", choices=("repo", "django"))
    parser.add_argument("--repo", type=Path, help="Django checkout (suite django); its HEAD is archived")
    parser.add_argument("--tasks-file", type=Path, help="task file (suite django)")
    parser.add_argument("--tasks", help="comma-separated task ids, in the order the sessions run (SMOKE: the smoke task)")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--lanes")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--graphify", type=Path, help="graphify executable for the TokenMaster install")
    parser.add_argument("--budget-credits", type=float, help="stop starting sessions before this run spends more")
    parser.add_argument("--prepare-only", action="store_true", help="stop before the first session (no model calls)")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    if not (args.suite and args.tasks and args.output and args.lanes) or (args.suite == "django" and not
                                                                          (args.repo and args.tasks_file)):
        parser.error("--suite, --tasks, --output and --lanes are required (django also needs --repo and --tasks-file)")
    out = args.output.resolve()
    if out.exists():
        raise SystemExit(f"output must be new: {out}")
    configure(args.model, args.lanes, args.graphify)
    if p5.LANES.exists():
        p1.remove_tree(p5.LANES)
    out.mkdir(parents=True)
    tar = out / "snapshot.tar"
    if args.suite == "repo":
        subprocess.run([str(p1.GIT_EXE), "archive", "--format=tar", "-o", str(tar), p1.SNAPSHOT_COMMIT,
                        *p1.SNAPSHOT_PATHS], cwd=p1.REPO, check=True)
    else:
        subprocess.run([str(p1.GIT_EXE), "archive", "--format=tar", "-o", str(tar), "HEAD"], cwd=args.repo, check=True)
    p5.git_snapshot(out / "templates" / "stock", tar)
    versions = {arm: p5.cli_version(p5.lane_root(arm) / "home") for arm in p5.ARMS}
    if set(versions.values()) != {CLI_VERSION}:
        raise SystemExit(f"Copilot CLI version must be {CLI_VERSION!r}: {versions}")
    tm_repo, tm_home = p5.lane_root("tm") / "tokenmaster", p5.lane_root("tm") / "home"
    p5.git_snapshot(tm_repo, tar)
    install = p5.install_tm(tm_home, tm_repo)
    shutil.copytree(tm_repo, out / "templates" / "tm")
    if p5.visible(p1.manifest(out / "templates" / "tm")) != p1.manifest(out / "templates" / "stock"):
        raise SystemExit("the TokenMaster install changed visible repository files")
    ids = args.tasks.split(",")
    if args.suite == "repo":
        tasks = [{**p1.SMOKE_TASK, "category": "investigate"}] * ("SMOKE" in ids) + q.load_tasks(
            tuple(i for i in ids if i != "SMOKE"), out)
    else:
        known = {t["id"]: t for t in json.loads(args.tasks_file.read_text(encoding="utf-8"))["tasks"]}
        tasks = [known[i] for i in ids]
    jobs = [[1, task_id] for task_id in ids]
    p5.reset_lane(p5.lane_root("stock") / "tokenmaster", out / "templates" / "stock")
    sources = {arm: lane_sources(arm) for arm in p5.ARMS}
    account = (json.loads((tm_home / "copilot" / "config.json").read_text(encoding="utf-8"))["lastLoggedInUser"])
    p5.write_json(out / "setup.json", {
        "kind": "exploratory, not pre-registered; default GitHub routing", "suite": args.suite, "model": args.model,
        "account": account, "versions": versions, "package": PACKAGE, "launcher": str(LAUNCHER),
        "launcher_sha256": p1.sha256_file(LAUNCHER), "package_sha256": p5.tree_manifest(p5.lane_package("stock")),
        "flags": p5.FLAGS, "install": install, "install_manifest_sha256": p5.install_manifest(tm_home),
        "tokenizer_sha256": p1.sha256_file(p5.TOKENIZER), "jobs": jobs, "lanes": str(p5.LANES),
        "graphify": subprocess.run([str(p1.GRAPHIFY_EXE), "--version"], env=base_env(tm_home), capture_output=True,
                                   text=True, timeout=120).stdout.strip(),
        "budget_credits": args.budget_credits,
        "lean_excluded_tools": {t["id"]: lean_excluded(t) for t in tasks}, "lane_sources": sources,
        "harness_sha256": p1.sha256_file(Path(__file__)), "tasks_file": str(args.tasks_file or ""),
        "django_head": subprocess.run([str(p1.GIT_EXE), "rev-parse", "HEAD"], cwd=args.repo, capture_output=True,
                                      text=True).stdout.strip() if args.repo else None})
    if args.prepare_only:
        return 0
    from brainspace import tokens
    tokens.count_tokens("warm-up")  # before worker threads (lazy init is not thread-safe)
    execute(out, tasks, jobs, out / "results.jsonl", args.budget_credits)
    print(json.dumps(summarize(out), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
