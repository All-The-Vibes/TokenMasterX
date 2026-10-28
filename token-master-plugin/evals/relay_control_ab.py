"""Exploratory relay control for the default-routing A/B (not pre-registered): PRS-6's evaluation relay on Copilot
CLI 1.0.104, with everything else as in the default-routing study.

PRS-6's Django run (django_ab.py, October 26, 2026) and the default-routing study (default_routing_ab.py, October 27)
differ in routing, and also in Copilot CLI build (1.0.98 vs 1.0.104), account, day, lane location and TokenMaster
commit. Here both arms run in bring-your-own-model mode through run_prs5_study.Relay, as in PRS-6: the relay records
every model call (calls.jsonl, captures.jsonl), and the TokenMaster arm starts through the installed bridge, so the
cache-stable system prompt and v6 shaping are on. The rest comes from default_routing_ab.py: Copilot CLI 1.0.104
through the WinGet launcher, lanes under C:\\tm-lanes, graphify 0.9.91, the lane-source check, PRS-6's task orders
and the credit budget.

Sign-in: PRS-6's relay read an OpenCode sign-in, which is gone. This relay sends the account that the default-routing
study ran under: Copilot CLI's own stored sign-in for ~/.copilot/config.json's lastLoggedInUser, read from Windows
Credential Manager into memory (never printed or written), to the Copilot API that GitHub names for that account in
/copilot_internal/user. Request bodies pass unchanged, as in PRS-6.

  python relay_control_ab.py --repo <django checkout> --tasks-file <tasks.json> --tasks D09,D01,...
                             --output <new folder> --lanes <name> --graphify <exe> [--lanes-root <folder>
                             --allow-inherited] [--budget-credits N] [--prepare-only]
  python relay_control_ab.py --self-test
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from urllib.parse import urlsplit

EVALS = Path(__file__).resolve().parent
sys.path.insert(0, str(EVALS))
import default_routing_ab as dr  # noqa: E402
import quick_copilot_ab as q  # noqa: E402
import run_prs1_study as p1  # noqa: E402
import run_prs5_study as p5  # noqa: E402

RELAY_CLI_ENV = p5.cli_env  # PRS-6's bring-your-own-model environment; default_routing_ab.configure replaces it
ALLOWANCE = 40e9  # nano-AIU that each running session holds against the budget (PRS-6's relay sessions: under 30)
VERSION = re.compile(r"Version number:\s*([^\s<\\\"]+)")  # Copilot CLI writes its version into its system prompt
NANO_AIU = re.compile(r'"total_nano_aiu"\s*:\s*(\d+)')  # GitHub's charge, in each response's copilot_usage


def stored_token(host: str, login: str) -> str:
    """Copilot CLI's stored OAuth token for host/login, from Windows Credential Manager into memory."""
    import ctypes
    from ctypes import wintypes as w

    class Credential(ctypes.Structure):
        _fields_ = [("Flags", w.DWORD), ("Type", w.DWORD), ("TargetName", w.LPWSTR), ("Comment", w.LPWSTR),
                    ("LastWritten", w.FILETIME), ("CredentialBlobSize", w.DWORD),
                    ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", w.DWORD),
                    ("AttributeCount", w.DWORD), ("Attributes", ctypes.c_void_p), ("TargetAlias", w.LPWSTR),
                    ("UserName", w.LPWSTR)]

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi.CredReadW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.POINTER(ctypes.POINTER(Credential))]
    advapi.CredFree.argtypes = [ctypes.c_void_p]
    for target in (f"{host}:{login}:github.copilot-cli", f"{host}:{login}.copilot-cli"):
        found = ctypes.POINTER(Credential)()
        if advapi.CredReadW(target, 1, 0, ctypes.byref(found)):  # 1: CRED_TYPE_GENERIC
            try:
                blob = found.contents
                return bytes(blob.CredentialBlob[:blob.CredentialBlobSize]).decode("utf-16-le").strip()
            finally:
                advapi.CredFree(found)
    raise SystemExit(f"no Copilot CLI sign-in for {host} / {login} in Windows Credential Manager; run `copilot login`")


def api_base(host: str) -> str:
    domain = urlsplit(host).hostname or ""
    return "https://api.github.com" if domain == "github.com" else f"https://api.{domain}"


def copilot_api(host: str, token: str) -> str:
    """The Copilot API that GitHub names for the account, where Copilot CLI sends it under default routing."""
    request = urllib.request.Request(f"{api_base(host)}/copilot_internal/user", headers={
        "Authorization": f"token {token}", "Accept": "application/json", "X-GitHub-Api-Version": "2025-05-01",
        "User-Agent": "tokenmaster-relay-control"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.load(response)
    url = (data.get("endpoints") or {}).get("api") if isinstance(data, dict) else None
    if not url:
        raise SystemExit(f"/copilot_internal/user named no Copilot API (keys: {sorted(data)[:20]})")
    return url.rstrip("/")


def configure(model: str, lanes: str, lanes_root: Path, graphify: Path) -> dict:
    """default_routing_ab's package, launcher, model and graphify, with PRS-6's relay environment and sign-in."""
    dr.configure(model, lanes, graphify)
    p5.cli_env = RELAY_CLI_ENV
    dr.cli_env = lambda home, _url="": RELAY_CLI_ENV(home, "http://127.0.0.1:9")  # lane_sources, lean_excluded
    dr.BUDGET_ALLOWANCE = ALLOWANCE
    p5.CLI_VERSION = dr.CLI_VERSION  # RELAY_CLI_ENV copies this package into the lane and pins it
    p5.LANES = lanes_root / lanes
    user = dr.operator_config().get("lastLoggedInUser") or {}
    if not user.get("host") or not user.get("login"):
        raise SystemExit("no Copilot CLI sign-in in ~/.copilot/config.json; run `copilot login` first")
    token = stored_token(user["host"], user["login"])
    p5.UPSTREAM = copilot_api(user["host"], token)
    p1.load_copilot_token = lambda: token
    return {"host": user["host"], "login": user["login"]}


def captured(run_dir: Path) -> dict:
    """From the relay's captures of one session: the Copilot CLI version in its system prompt and GitHub's charge
    (copilot_usage.total_nano_aiu) over its answered calls."""
    captures = p5.read_jsonl(run_dir / "captures.jsonl")
    charges = [int(found[-1]) for c in captures
               if c.get("status") == 200 and (found := NANO_AIU.findall(c.get("output_tail") or ""))]
    return {"copilot_versions": sorted({m.group(1) for c in captures if (m := VERSION.search(c.get("input") or ""))}),
            "nano": sum(charges), "charged_calls": len(charges)}


def classify(row: dict, run_dir: Path) -> dict:
    """default_routing_ab's infrastructure rule on top of run_prs5_study's: a session with no answered call, or one
    that ended without a final answer after an HTTP 429/5xx or no response, is re-run, not graded."""
    usage = row.get("usage")
    if row["status"] == "infra" or not usage:
        return row
    stdout = run_dir / "stdout.jsonl"
    events = dr.stdout_events(stdout.read_text(encoding="utf-8", errors="replace") if stdout.is_file() else "")
    if not usage["calls"]:
        row.update(status="infra", why=f"infra:exit={row['exit']}:no_answered_call")
    elif usage["infra_statuses"] and not events["answered"]:
        row.update(status="infra", why=f"infra:exit={row['exit']}:provider_error")
    return row


def execute(out: Path, tasks: list[dict], jobs: list[list], results: Path, budget_credits: float | None) -> None:
    """run_prs5_study.execute (one relay per arm, both arms at the same time, one re-run per infrastructure failure)
    with default_routing_ab's budget. Three things stop both arms for the rest of the run: the budget cannot hold
    another session, the Copilot API refuses the sign-in, or a session ran another Copilot CLI version."""
    by_id = {t["id"]: t for t in tasks}
    lock, budget, stopped = threading.Lock(), dr.Budget(budget_credits), []
    relays = {arm: p5.Relay(p1.load_copilot_token()) for arm in p5.ARMS}
    for relay in relays.values():
        relay.__enter__()
    try:
        p5.warmup(relays, out)

        def one(arm: str, task: dict, repeat: int, suffix: str = "") -> dict | None:
            with lock:
                if not stopped and not budget.reserve():
                    stopped.append(f"budget of {budget_credits} credits")
                reason = stopped[0] if stopped else None
            if reason:
                print(f"[{task['id']}-{arm}-r{repeat}{suffix}] not started: {reason}", flush=True)
                return None
            try:
                row = p5.run_session(out, arm, task, repeat, relays[arm], suffix=suffix)
            except Exception as error:  # recorded as infrastructure, never silently dropped
                row = p5.failed_row(task, arm, repeat, suffix, error)
            run_dir = out / "runs" / row["session"]
            try:  # Copilot CLI's own event log, read as default_routing_ab does: version, tools, nav calls
                row.update(captured(run_dir), **dr.session_events(p5.lane_root(arm) / "home", run_dir))
                classify(row, run_dir)
            except Exception as error:  # a record this code cannot read must not end the arm's thread
                row.update(status="infra", why=f"harness:record:{type(error).__name__}:{str(error)[:200]}")
            row.setdefault("nano", 0)
            with lock:
                if any(c.get("status") in (401, 403) for c in p5.read_jsonl(run_dir / "calls.jsonl")):
                    stopped.append("the Copilot API refused the sign-in (HTTP 401 or 403)")
                if row.get("version") not in (None, dr.PACKAGE):
                    stopped.append(f"{row['session']} ran Copilot CLI {row['version']}")
            # GitHub's charge from the captures; the token count at GitHub's prices if a response carried none
            budget.settle(max(row["nano"], q.usd(row["usage"], p5.MODEL) * dr.NANO_PER_USD if row["usage"] else 0))
            p1.append_jsonl(results, row, lock)
            u = row.get("usage") or {"calls": 0, "input": 0, "output": 0}
            print(f"[{row['session']:<22}] {row['status']:<5} calls={u['calls']:>3} "
                  f"raw={u['input'] + u['output']:>10,} credits={row['nano'] / 1e9:.2f} "
                  f"first_cached={row['first_call'].get('cached')} why={row['why']} "
                  f"run_credits={budget.spent / 1e9:.1f}", flush=True)
            return row

        def lane(arm: str) -> None:
            rows = [row for repeat, task_id in jobs if (row := one(arm, by_id[task_id], repeat))]
            for row in [r for r in rows if r["status"] == "infra"]:
                one(arm, by_id[row["task"]], row["repeat"], "-rerun")

        with ThreadPoolExecutor(max_workers=len(p5.ARMS)) as pool:
            list(pool.map(lane, p5.ARMS))
    finally:
        for relay in relays.values():
            relay.__exit__()
        if stopped:
            p5.write_json(out / "stopped.json", {"reasons": stopped})


def lane_sources(arm: str, allow_inherited: bool) -> dict:
    """default_routing_ab.lane_sources. A lane meant to inherit (the %TEMP% lane test) is recorded as counts, so the
    operator's skill names stay out of setup.json."""
    if not allow_inherited:
        return dr.lane_sources(arm)
    home, lane = p5.lane_root(arm) / "home", p5.lane_root(arm) / "tokenmaster"
    found = {}
    for name, args in (("skills", ["skill", "list"]), ("instructions", ["instruction", "list"])):
        proc = subprocess.run([p5.COPILOT, *args], cwd=lane, env=dr.cli_env(home), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=180, stdin=subprocess.DEVNULL)
        found[name] = (proc.stdout + proc.stderr).strip().splitlines()
    return {"skills_per_group": {group: len(names) for group, names in dr.skill_groups(found["skills"]).items()},
            "instruction_groups": [line for line in found["instructions"] if line and not line.startswith(" ")]}


def git_head(root: Path) -> str:
    return subprocess.run([str(p1.GIT_EXE), "rev-parse", "HEAD"], cwd=root, capture_output=True,
                          text=True).stdout.strip()


def self_test() -> None:
    assert api_base("https://microsoft.ghe.com") == "https://api.microsoft.ghe.com"
    assert api_base("https://github.com") == "https://api.github.com"
    try:
        stored_token("https://example.invalid", "nobody")
        raise AssertionError("a missing sign-in must stop the run")
    except SystemExit:
        pass
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        assert captured(run_dir) == {"copilot_versions": [], "nano": 0, "charged_calls": 0}
        request = {"instructions": "<version_information>Version number: 1.0.104</version_information>", "input": []}
        usage = '"copilot_usage": {"token_details": [], "total_nano_aiu": 1234500}'
        rows = [{"n": 1, "status": 200, "input": json.dumps(request), "output_tail": "data: {" + usage + "}"},
                {"n": 2, "status": 502, "input": json.dumps(request), "output_tail": usage},  # failed: no charge
                {"n": 3, "status": 200, "input": json.dumps(request), "output_tail": "no usage"}]
        (run_dir / "captures.jsonl").write_text("\n".join(map(json.dumps, rows)) + "\n", encoding="utf-8")
        assert captured(run_dir) == {"copilot_versions": ["1.0.104"], "nano": 1234500, "charged_calls": 1}
        graded = {"status": "pass", "why": "ok", "exit": 0, "usage": {"calls": 2, "infra_statuses": 0}}
        assert classify(dict(graded), run_dir)["status"] == "pass"
        assert classify({**graded, "usage": {"calls": 0, "infra_statuses": 0}}, run_dir)["why"] == \
               "infra:exit=0:no_answered_call"  # a refused or empty session is not a graded fail
        died = {**graded, "status": "fail", "usage": {"calls": 1, "infra_statuses": 1}}
        assert classify(dict(died), run_dir)["why"] == "infra:exit=0:provider_error"  # no final answer after a 5xx
        (run_dir / "stdout.jsonl").write_text(json.dumps({"type": "assistant.message", "data": {
            "content": '{"callers": []}', "phase": "final_answer"}}) + "\n", encoding="utf-8")
        assert classify(dict(died), run_dir)["status"] == "fail"  # it answered: graded
        failed = {"status": "infra", "why": "harness:x", "exit": None, "usage": None}
        assert classify(dict(failed), run_dir) == failed
    saved = dr.BUDGET_ALLOWANCE
    try:
        dr.BUDGET_ALLOWANCE = ALLOWANCE
        budget = dr.Budget(80)  # credits: both arms of a two-session pilot start, a third session does not
        assert budget.reserve() and budget.reserve() and not budget.reserve()
    finally:
        dr.BUDGET_ALLOWANCE = saved
    for jobs, budget_credits, ran, reason in (
            (["T1", "V", "T2"], None, ["T1", "V"], "V-stock-r1 ran Copilot CLI 1.0.98"),
            (["E", "T1"], None, ["E"], "the Copilot API refused the sign-in (HTTP 401 or 403)"),  # no re-run either
            (["T1", "T2", "T3", "T4", "T5"], 100, ["T1", "T2", "T3"], "budget of 100 credits")):  # 30 credits each
        assert stops(jobs, budget_credits) == (ran, [reason]), (jobs, stops(jobs, budget_credits))
    print("self-test passed")


def stops(jobs: list[str], budget_credits: float | None) -> tuple[list[str], list[str]]:
    """execute() on one arm with stand-ins for the relay and the sessions: the tasks that ran and why the run stopped.
    Task V runs another Copilot CLI version; task E gets HTTP 401 and no answer; every other task costs 30 credits."""
    import contextlib
    import io
    from unittest import mock

    class Relay:
        def __init__(self, token):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    def run_session(out, arm, task, repeat, relay, *, suffix=""):
        run_dir = out / "runs" / f"{task['id']}-{arm}-r{repeat}{suffix}"
        run_dir.mkdir(parents=True)
        refused = task["id"] == "E"
        (run_dir / "calls.jsonl").write_text(json.dumps({"n": 1, "status": 401 if refused else 200}) + "\n",
                                             encoding="utf-8")
        usage = {"calls": 0 if refused else 1, "input": 0 if refused else 30_000, "cached": 0, "cache_write": 0,
                 "output": 0, "infra_statuses": 0}
        return {"task": task["id"], "arm": arm, "repeat": repeat, "session": run_dir.name, "status": "pass",
                "why": "ok", "exit": 0, "usage": usage, "first_call": {}}

    def session_events(home, run_dir):
        return {"version": "1.0.98" if run_dir.name.startswith("V-") else dr.PACKAGE, "tools": {}, "nav_calls": 0}

    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), \
            mock.patch.multiple(p5, ARMS=("stock",), Relay=Relay, warmup=lambda relays, out: None,
                                run_session=run_session, MODEL="gpt-6-astra"), \
            mock.patch.multiple(dr, BUDGET_ALLOWANCE=ALLOWANCE, session_events=session_events), \
            mock.patch.object(p1, "load_copilot_token", lambda: "not-a-token"):
        out = Path(tmp)
        execute(out, [{"id": j} for j in jobs], [[1, j] for j in jobs], out / "results.jsonl", budget_credits)
        ran = [row["task"] for row in p5.read_jsonl(out / "results.jsonl")]
        return ran, json.loads((out / "stopped.json").read_text(encoding="utf-8"))["reasons"]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--repo", type=Path, help="Django checkout; its HEAD is archived")
    parser.add_argument("--tasks-file", type=Path)
    parser.add_argument("--tasks", help="comma-separated task ids, in the order the sessions run")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--lanes")
    parser.add_argument("--lanes-root", type=Path, default=dr.LANES_ROOT)
    parser.add_argument("--allow-inherited", action="store_true",
                        help="record the skills and instructions the lanes inherit instead of stopping (lane test)")
    parser.add_argument("--model", default=dr.MODEL, choices=sorted(q.USD_PER_M))
    parser.add_argument("--graphify", type=Path, help="graphify executable for the TokenMaster install")
    parser.add_argument("--budget-credits", type=float, help="stop starting sessions before this run spends more")
    parser.add_argument("--prepare-only", action="store_true", help="stop before the first model call")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    if not (args.repo and args.tasks_file and args.tasks and args.output and args.lanes and args.graphify):
        parser.error("--repo, --tasks-file, --tasks, --output, --lanes and --graphify are required")
    out = args.output.resolve()
    if out.exists():
        raise SystemExit(f"output must be new: {out}")
    account = configure(args.model, args.lanes, args.lanes_root, args.graphify)
    if p5.LANES.exists():
        p1.remove_tree(p5.LANES)
    out.mkdir(parents=True)
    tar = out / "snapshot.tar"
    subprocess.run([str(p1.GIT_EXE), "archive", "--format=tar", "-o", str(tar), "HEAD"], cwd=args.repo, check=True)
    p5.git_snapshot(out / "templates" / "stock", tar)
    versions = {arm: p5.cli_version(p5.lane_root(arm) / "home") for arm in p5.ARMS}
    if set(versions.values()) != {dr.CLI_VERSION}:
        raise SystemExit(f"Copilot CLI version must be {dr.CLI_VERSION!r}: {versions}")
    tm_repo, tm_home = p5.lane_root("tm") / "tokenmaster", p5.lane_root("tm") / "home"
    p5.git_snapshot(tm_repo, tar)
    install = p5.install_tm(tm_home, tm_repo)
    shutil.copytree(tm_repo, out / "templates" / "tm")
    if p5.visible(p1.manifest(out / "templates" / "tm")) != p1.manifest(out / "templates" / "stock"):
        raise SystemExit("the TokenMaster install changed visible repository files")
    ids = args.tasks.split(",")
    known = {t["id"]: t for t in json.loads(args.tasks_file.read_text(encoding="utf-8"))["tasks"]}
    tasks = [known[i] for i in ids]
    jobs = [[1, task_id] for task_id in ids]
    p5.reset_lane(p5.lane_root("stock") / "tokenmaster", out / "templates" / "stock")
    sources = {arm: lane_sources(arm, args.allow_inherited) for arm in p5.ARMS}
    probe = p5.Relay("not-sent")
    headers = {k: v for k, v in probe.upstream_headers({}).items() if k.lower() != "authorization"}
    probe.server.server_close()
    p5.write_json(out / "setup.json", {
        "kind": "exploratory, not pre-registered; PRS-6's evaluation relay on Copilot CLI 1.0.104",
        "routing": "bring-your-own-model through run_prs5_study.Relay", "suite": "django", "model": args.model,
        "account": account, "copilot_api": p5.UPSTREAM, "relay_headers": headers, "versions": versions,
        "package": dr.PACKAGE, "launcher": p5.COPILOT, "launcher_sha256": p1.sha256_file(Path(p5.COPILOT)),
        "package_sha256": p5.tree_manifest(p5.lane_package("stock")), "flags": p5.FLAGS, "install": install,
        "install_manifest_sha256": p5.install_manifest(tm_home), "tokenizer_sha256": p1.sha256_file(p5.TOKENIZER),
        "jobs": jobs, "lanes": str(p5.LANES), "lanes_inherit_allowed": args.allow_inherited,
        "graphify": subprocess.run([str(p1.GRAPHIFY_EXE), "--version"], env=dr.base_env(tm_home),
                                   capture_output=True, text=True, timeout=120).stdout.strip(),
        "budget_credits": args.budget_credits, "budget_allowance_credits": ALLOWANCE / 1e9,
        "lean_excluded_tools": {t["id"]: dr.lean_excluded(t) for t in tasks}, "lane_sources": sources,
        "harness_sha256": p1.sha256_file(Path(__file__)), "default_routing_harness_sha256": p1.sha256_file(
            Path(dr.__file__)), "tokenmaster_head": git_head(p1.REPO), "tasks_file": str(args.tasks_file),
        "django_head": git_head(args.repo)})
    if args.prepare_only:
        return 0
    from brainspace import tokens
    tokens.count_tokens("warm-up")  # before worker threads (lazy init is not thread-safe)
    execute(out, tasks, jobs, out / "results.jsonl", args.budget_credits)
    print(json.dumps(q.summarize(out, args.model), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
