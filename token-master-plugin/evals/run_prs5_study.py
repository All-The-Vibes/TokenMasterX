"""PRS-5: pre-registered live study of TokenMaster on the real GitHub Copilot CLI with heavy tasks.

Protocol: token-master-plugin/docs/PRS5_PROTOCOL.md (written before any study call).

  stock  real Copilot CLI 1.0.98 (default agent), no TokenMaster
  tm     the same CLI after the documented TokenMaster install for Copilot:
         setup.py --host copilot (tokenmaster-nav MCP server, graph and symbol index) and
         brainspace_setup.py --host copilot (brainspace MCP server, v6 view hook, bridge),
         launched through the installed brainspace_copilot_bridge.py (cache-stable system prompt + v6)

Both arms run Copilot CLI in bring-your-own-key mode against an evaluation relay. The relay adds the
GitHub Copilot credential in memory and records every model call, failed ones included. Each arm runs
its sessions back to back in one fixed repository folder, which is reset from the arm's template before
each session. Agents get an allowlisted environment with no Python on PATH; checks run afterwards.

Co-primary endpoints, per session and paired by task and repeat: raw tokens (input + output) and billed
cost at the provider's prices (new input 1, cache read 0.1, cache write 1.25, output 5).

Subcommands: self-test | prepare | smoke | run | analyze
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from unittest import mock
import urllib.error
import urllib.request

EVALS = Path(__file__).resolve().parent
if str(EVALS) not in sys.path:  # isolated child processes (-I) do not add the script folder
    sys.path.insert(0, str(EVALS))

import run_prs1_study as p1  # noqa: E402
import run_prs2_study as p2  # noqa: E402
import run_prs3_study as p3  # noqa: E402
from run_prs1_study import PLUGIN, REPO, SKILL, sha256_bytes, sha256_file, write_json  # noqa: E402

import brainspace_copilot_bridge as cb  # noqa: E402  (SKILL is on sys.path through run_prs1_study)

SEED = 20261022
REPEATS = 2
ARMS = ("stock", "tm")
MODEL = p1.MODEL
EFFORT = "low"
CLI_VERSION = "GitHub Copilot CLI 1.0.98."
SESSION_TIMEOUT = 1500
CHECK_TIMEOUT = 300
QUOTA = {"investigate": 3, "edit": 3, "feature": 2}
WORKLOAD_FLOOR = 2_000_000  # raw tokens per arm, over all graded sessions
INFRA_STATUSES = {429, 500, 502, 503, 504, 599}  # 599: no response from the provider
PRICES = {"input": 1.0, "cache_read": 0.1, "cache_write": 1.25, "output": 5.0}
TOKENIZER = REPO / "evidence/controlled-scorecard-20261008/batch-001/cl100k_base.tiktoken"
COPILOT = shutil.which("copilot") or str(Path(os.environ["LOCALAPPDATA"]) / "Microsoft/WinGet/Links/copilot.exe")
INSTALLED_PKG = Path(os.environ["LOCALAPPDATA"]) / "copilot" / "pkg"
LANES = Path(tempfile.gettempdir()) / "opencode" / "prs5-lanes"
LANE = {"stock": "l1", "tm": "l2"}  # neutral names: the model sees its working directory
UPSTREAM = "https://api.githubcopilot.com"
ENDPOINTS = {"raw_tokens": None, "billed": (0.1, 5.0, 0.25), "uncached_input": "uncached", "calls": "calls",
             "cost": (0.1, 8.0, 0.0)}
PRIMARY = ("raw_tokens", "billed")
IGNORED = ("graphify-out/",)  # graphify's own output; dot-folders (.git, .token-master) are never listed
FLAGS = ["--model", MODEL, "--reasoning-effort", EFFORT, "--allow-all-tools", "--no-ask-user",
         "--disable-builtin-mcps", "--output-format", "json"]
BASE_ENV = ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "OS", "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER",
            "NUMBER_OF_PROCESSORS", "SystemDrive", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData",
            "CommonProgramFiles", "CommonProgramFiles(x86)", "CommonProgramW6432", "PSModulePath", "USERNAME",
            "USERDOMAIN", "COMPUTERNAME")


# --------------------------------------------------------------------------- environment

def lane_root(arm: str, smoke: bool = False) -> Path:
    return LANES / (("s" if smoke else "") + LANE[arm])


def lane_package(arm: str, smoke: bool = False) -> Path:
    return lane_root(arm, smoke) / "home" / "profile" / "AppData" / "Local" / "copilot" / "pkg"


def base_env(home: Path, extra_path: tuple = ()) -> dict:
    """An allowlisted environment: no operator secrets, isolated profile folders, no Python on PATH."""
    windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    env = {k: os.environ[k] for k in BASE_ENV if k in os.environ}
    pwsh = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "PowerShell" / "7"
    path = [*extra_path, p1.GIT_EXE.parent, Path(COPILOT).parent, *([pwsh] if pwsh.is_dir() else []),
            windows / "System32", windows, windows / "System32" / "Wbem",
            windows / "System32" / "WindowsPowerShell" / "v1.0"]
    profile = home / "profile"
    env.update({"PATH": os.pathsep.join(map(str, path)), "TEMP": str(home / "tmp"), "TMP": str(home / "tmp"),
                "HOME": str(profile), "USERPROFILE": str(profile), "APPDATA": str(profile / "AppData/Roaming"),
                "LOCALAPPDATA": str(profile / "AppData/Local"), "COPILOT_HOME": str(home / "copilot"),
                "CLAUDE_CONFIG_DIR": str(profile / ".claude"), "CODEX_HOME": str(profile / ".codex"),
                "PYTHONUTF8": "1", "BRAINSPACE_TOKENIZER_FILE": str(TOKENIZER)})
    for key in ("TEMP", "APPDATA", "LOCALAPPDATA", "COPILOT_HOME"):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    return env


def cli_env(home: Path, base_url: str) -> dict:
    """Copilot CLI in offline BYOK mode; the installed package is copied in, so the launcher runs it."""
    env = base_env(home)
    env.update({"COPILOT_OFFLINE": "true", "COPILOT_ALLOW_ALL": "true", "COPILOT_MODEL": MODEL,
                "COPILOT_PROVIDER_BASE_URL": base_url, "COPILOT_PROVIDER_TYPE": "openai",
                "COPILOT_PROVIDER_WIRE_API": "responses", "COPILOT_PROVIDER_API_KEY": "relay-adds-the-credential",
                "COPILOT_PROVIDER_MODEL_ID": MODEL, "COPILOT_PROVIDER_WIRE_MODEL": MODEL,
                "COPILOT_PROVIDER_MAX_PROMPT_TOKENS": "200000", "COPILOT_PROVIDER_MAX_OUTPUT_TOKENS": "16000"})
    version = CLI_VERSION.split()[-1].rstrip(".")
    source = INSTALLED_PKG / "win32-x64" / version
    target = Path(env["LOCALAPPDATA"]) / "copilot" / "pkg" / "win32-x64" / version
    if not target.exists():
        shutil.copytree(source if source.is_dir() else INSTALLED_PKG, target if source.is_dir() else target.parents[1])
    if (target / "index.js").is_file():
        env["COPILOT_CLI_DIST_DIR"] = str(target)
    return env


def cli_version(home: Path) -> str:
    """The version that the sessions run. With --no-auto-update, the WinGet launcher runs its bundled build (1.0.78-3)
    even when a newer package is installed; `copilot --version` without the flag reports the package instead."""
    flags = [flag for flag in FLAGS if flag == "--no-auto-update"]
    out = subprocess.run([COPILOT, *flags, "--version"], env=cli_env(home, "http://127.0.0.1:9"), capture_output=True,
                         text=True, timeout=180, stdin=subprocess.DEVNULL).stdout
    return out.splitlines()[0].strip() if out else ""


def tree_manifest(root: Path) -> str:
    """One hash over every file below root, dot-files included, caches excluded."""
    rows = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted(filenames):
            path = Path(dirpath) / name
            rows.append(f"{path.relative_to(root).as_posix()} {sha256_file(path)}")
    return sha256_bytes("\n".join(rows).encode())


def install_manifest(home: Path) -> str:
    """The installed TokenMaster files and the Copilot configuration they wrote (not session state)."""
    copilot = home / "copilot"
    parts = [tree_manifest(copilot / "token-master")]
    for rel in ("mcp-config.json", "settings.json", "agents/token-master.agent.md"):
        parts.append(sha256_file(copilot / rel) if (copilot / rel).is_file() else f"missing:{rel}")
    return sha256_bytes("\n".join(parts).encode())


def product_files() -> list[Path]:
    """Every shipped file of the skill (tests, caches and dot-folders excluded)."""
    return sorted(p for p in SKILL.rglob("*") if p.is_file()
                  and not {"tests", "__pycache__"} & set(p.relative_to(SKILL).parts)
                  and not any(part.startswith(".") for part in p.relative_to(SKILL).parts))


def visible(manifest: dict) -> dict:
    return {k: v for k, v in manifest.items() if not k.startswith(IGNORED)}


def provider_bill(text: str):
    """A response's own bill (copilot_usage) in uncached-input-token units, and its price ratios."""
    at = text.rfind('"copilot_usage":')
    if at < 0:
        return None
    start = at + len('"copilot_usage":')
    while start < len(text) and text[start] in " \t\r\n":
        start += 1
    try:
        usage = json.JSONDecoder().raw_decode(text, start)[0]
        details = usage["token_details"]
        rate = {d["token_type"]: d["cost_per_batch"] / d["batch_size"] for d in details}
        units = sum(d["token_count"] * rate[d["token_type"]] for d in details) / rate["input"]
    except (ValueError, KeyError, TypeError, ZeroDivisionError):
        return None
    return {"units": units, "ratios": {k: round(v / rate["input"], 6) for k, v in rate.items()}}


def billed(usage: dict) -> float:
    return ((usage["input"] - usage["cached"] - usage["cache_write"]) + PRICES["cache_read"] * usage["cached"]
            + PRICES["cache_write"] * usage["cache_write"] + PRICES["output"] * usage["output"])


class Relay(cb.Bridge):
    """Evaluation upstream: adds the Copilot credential in memory and records every call of the current
    session, including calls that never got a response. Request bodies are not changed."""

    def __init__(self, token: str):
        super().__init__(UPSTREAM)
        self.token, self.session_dir, self.n, self.inflight = token, None, 0, 0
        self._local = threading.local()
        inner, relay = self.opener, self

        class Recording:
            def open(self, request, timeout=None):
                try:
                    return inner.open(request, timeout=timeout)
                except urllib.error.HTTPError:
                    raise  # the bridge streams the error response and records it
                except Exception:
                    receipt = getattr(relay._local, "receipt", None)
                    if receipt:
                        relay.record(request.full_url, 599, receipt, b"")
                    raise

        self.opener = Recording()

    def prepare(self, path, body):
        self._local.receipt = None
        if body is None or not path.split("?")[0].endswith("/responses") or self.session_dir is None:
            return body, {}
        with self._lock:
            self.n += 1
            self.inflight += 1
            n = self.n
        try:
            parsed = json.loads(body)
            prefix = cb._prefix_digest(parsed) if isinstance(parsed, dict) else None
        except ValueError:
            prefix = None
        receipt = {"n": n, "dir": self.session_dir, "prefix_sha256": prefix, "request": body.decode("utf-8", "replace")}
        self._local.receipt = receipt
        return body, receipt

    def upstream_headers(self, headers):
        out = {k: v for k, v in super().upstream_headers(headers).items()
               if k.lower() not in ("authorization", "x-api-key")}
        out.update({"Authorization": f"Bearer {self.token}", "Copilot-Integration-Id": "vscode-chat",
                    "Editor-Version": "vscode/1.100.0"})
        return out

    def record(self, path, status, receipt, tail):
        if not receipt:
            return
        self._local.receipt = None
        text = tail.decode("utf-8", "replace")
        row = {"n": receipt["n"], "t": round(time.time(), 3), "status": status,
               "prefix_sha256": receipt["prefix_sha256"], "usage": cb._usage(tail), "bill": provider_bill(text)}
        with self._lock:
            try:
                with (receipt["dir"] / "calls.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row) + "\n")
                with (receipt["dir"] / "captures.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"n": receipt["n"], "status": status, "input": receipt["request"],
                                             "output_tail": text[-200_000:]}) + "\n")
            finally:
                self.inflight -= 1

    def wait_idle(self, limit: float = 180) -> int:
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            with self._lock:
                if self.inflight <= 0:
                    return 0
            time.sleep(0.5)
        with self._lock:
            return self.inflight


# --------------------------------------------------------------------------- sessions and grading

def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue  # a writer killed mid-line
    return rows


def session_usage(run_dir: Path, *, from_captures: bool = False) -> dict:
    """Sum of provider-reported usage over a session's model calls."""
    usage = {"calls": 0, "input": 0, "cached": 0, "cache_write": 0, "output": 0, "http_errors": 0,
             "infra_statuses": 0, "missing_usage": 0}
    bills = []
    for call in read_jsonl(run_dir / ("captures.jsonl" if from_captures else "calls.jsonl")):
        got = cb._usage(call["output_tail"].encode("utf-8")) if from_captures else call["usage"]
        if call["status"] != 200:
            usage["http_errors"] += 1
            usage["infra_statuses"] += call["status"] in INFRA_STATUSES
            continue
        if not got or got.get("input") is None:
            usage["missing_usage"] += 1
            continue
        usage["calls"] += 1
        for key in ("input", "cached", "cache_write", "output"):
            usage[key] += got.get(key) or 0
        if not from_captures:
            bills.append(call.get("bill"))
    if not from_captures:
        usage["bill_units"] = sum(b["units"] for b in bills) if bills and None not in bills else None
        usage["bill_ratios"] = sorted({tuple(sorted(b["ratios"].items())) for b in bills if b}) or None
    return usage


def final_answer(stdout: str) -> str | None:
    """The last final-answer message from Copilot CLI's JSON event stream (else its last message)."""
    final, last = None, None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "assistant.message":
            data = event.get("data") or {}
            if isinstance(data.get("content"), str) and data["content"].strip():
                last = data["content"]
                if data.get("phase") == "final_answer":
                    final = data["content"]
    return final if final is not None else last


TEMPLATE_MANIFESTS: dict[str, dict] = {}


def same_content(first: Path, second: Path) -> bool:
    """True when two files differ only by CRLF vs LF line endings."""
    try:
        return first.read_bytes().replace(b"\r\n", b"\n") == second.read_bytes().replace(b"\r\n", b"\n")
    except OSError:
        return False


def changed_files(lane: Path, template: Path) -> list[str]:
    if str(template) not in TEMPLATE_MANIFESTS:
        TEMPLATE_MANIFESTS[str(template)] = p1.manifest(template)
    before, after = TEMPLATE_MANIFESTS[str(template)], p1.manifest(lane)
    changed = sorted(k for k in before.keys() & after.keys()
                     if before[k] != after[k] and not same_content(template / k, lane / k))
    changed += sorted(set(after) - set(before)) + sorted(set(before) - set(after))
    return [c for c in changed if not c.startswith(IGNORED)]


def run_check(task: dict, root: Path) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as home:  # checks never touch the operator's profile
        env = base_env(Path(home))
        env.update({"PYTHONPATH": str(root / "token-master-plugin/skills/token-master"),
                    "PYTHONDONTWRITEBYTECODE": "1"})
        try:
            proc = subprocess.run([sys.executable, "-B", "-c", task["check"]], cwd=root, env=env, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=CHECK_TIMEOUT,
                                  stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return False, "check timeout"
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-1500:]


def grade(task: dict, final_text: str | None, lane: Path, template: Path) -> dict:
    changed = changed_files(lane, template)
    if task["category"] == "investigate":
        if changed:
            return {"pass": False, "why": "modified_files_in_question_task", "changed": changed}
        answer = p1.extract_json_object(final_text or "", task["expected"])
        if answer is None:
            return {"pass": False, "why": "no_json_object", "changed": changed}
        unordered = set(task.get("unordered_list_keys", []))
        wrong = [k for k, exp in task["expected"].items()
                 if not p1.value_matches(answer.get(k, p1.MISSING), exp, k in unordered)]
        return {"pass": not wrong, "why": "ok" if not wrong else "wrong:" + ",".join(wrong), "answer": answer,
                "changed": changed}
    outside = [c for c in changed if not c.startswith(tuple(task["allowed_paths"]))]
    if outside:
        return {"pass": False, "why": "changes_outside_allowed_paths", "changed": changed}
    ok, detail = run_check(task, lane)
    return {"pass": ok, "why": "ok" if ok else "check_failed", "check_tail": detail, "changed": changed}


def run_copilot(args: list[str], cwd: Path, env: dict) -> tuple[object, str, str]:
    proc = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                            creationflags=p1.NO_WINDOW)
    try:
        out, err = proc.communicate(timeout=SESSION_TIMEOUT)
        return proc.returncode, out, err
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)  # the whole tree
        try:
            out, err = proc.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            out, err = "", "output lost after the timeout kill"
        return "timeout", out, err


def reset_lane(lane: Path, template: Path) -> None:
    for attempt in range(6):  # Windows: a process that is still exiting can hold a file for a moment
        proc = subprocess.run(["robocopy", str(template), str(lane), "/MIR", "/MT:16", "/R:2", "/W:1", "/NFL", "/NDL",
                               "/NJH", "/NJS", "/NP"], capture_output=True, text=True, errors="replace")
        if proc.returncode < 8:  # robocopy: 0-7 success, 8+ failure
            return
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"lane reset failed: {lane}")


def clear_history(home: Path) -> None:
    """Copilot CLI keeps transcripts in its home; no session may read an earlier session's work."""
    copilot = home / "copilot"
    for path in [copilot / "session-state", *copilot.glob("session-store.db*")]:
        try:
            if path.is_dir():
                p1.remove_tree(path)
            elif path.exists():
                path.unlink()
        except OSError:
            pass


def run_session(out: Path, arm: str, task: dict, repeat: int, relay: Relay, *, suffix: str = "",
                smoke: bool = False) -> dict:
    sid = f"{task['id']}-{arm}-r{repeat}{suffix}"
    run_dir = out / "runs" / sid
    run_dir.mkdir(parents=True)
    root = lane_root(arm, smoke)
    lane, template = root / "tokenmaster", out / "templates" / arm
    reset_lane(lane, template)
    clear_history(root / "home")
    env = cli_env(root / "home", relay.url)
    args = [COPILOT, "-p", task["prompt"], *FLAGS]
    if arm == "tm":
        bridge = root / "home" / "copilot" / "token-master" / "brainspace_copilot_bridge.py"
        args = [sys.executable, "-B", str(bridge), "--log", str(run_dir / "bridge.jsonl"), "--", *args]
    relay.session_dir = run_dir
    started = time.time()
    try:
        code, stdout, stderr = run_copilot(args, lane, env)
    finally:
        relay.session_dir = None
    still_open = relay.wait_idle()
    wall = round(time.time() - started, 1)
    (run_dir / "stdout.jsonl").write_text(stdout or "", encoding="utf-8")
    (run_dir / "stderr.txt").write_text(stderr or "", encoding="utf-8")
    final = final_answer(stdout or "")
    usage = session_usage(run_dir)
    verdict = grade(task, final, lane, template)
    finished = code == 0
    if usage["infra_statuses"] and not finished:
        status, why = "infra", f"infra:exit={code}:infra_statuses={usage['infra_statuses']}"
    elif code == "timeout":
        status, why = "fail", "timeout"
    else:
        status, why = ("pass" if verdict["pass"] else "fail"), verdict["why"]
    bridge_rows = read_jsonl(run_dir / "bridge.jsonl")
    calls = read_jsonl(run_dir / "calls.jsonl")
    first = next((c["usage"] for c in sorted(calls, key=lambda c: c["n"]) if c["status"] == 200 and c["usage"]), {})
    for rel in verdict.get("changed", [])[:20]:
        if (lane / rel).is_file():
            keep = run_dir / "changed" / rel
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(lane / rel, keep)
    return {"task": task["id"], "set": "primary", "category": task["category"], "arm": arm, "repeat": repeat,
            "session": sid, "status": status, "why": why, "exit": code, "answer": verdict.get("answer"),
            "final_text": (final or "")[:2000], "changed": verdict.get("changed", []),
            "check_tail": verdict.get("check_tail"), "usage": usage, "wall_seconds": wall,
            "requests_open_after_wait": still_open,
            "first_call": {k: first.get(k) for k in ("input", "cached", "cache_write", "output")},
            "prefixes": sorted({c["prefix_sha256"] for c in calls if c.get("prefix_sha256")}),
            "bridge": {"calls": len(bridge_rows), "stable_prefix": sum(bool(r.get("stable_prefix")) for r in bridge_rows),
                       "shaped": sum(r.get("shaped", 0) for r in bridge_rows)} if arm == "tm" else None,
            "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))}


def failed_row(task: dict, arm: str, repeat: int, suffix: str, error: Exception) -> dict:
    return {"task": task["id"], "set": "primary", "category": task["category"], "arm": arm, "repeat": repeat,
            "session": f"{task['id']}-{arm}-r{repeat}{suffix}", "status": "infra",
            "why": f"harness:{type(error).__name__}:{str(error)[:300]}", "exit": None, "usage": None,
            "first_call": {}, "bridge": None}


def warmup(relays: dict[str, Relay], out: Path) -> None:
    body = json.dumps({"model": MODEL, "input": [{"role": "user", "content": "Reply with OK."}],
                       "max_output_tokens": 64, "store": False, "stream": False}).encode("utf-8")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    receipt = {}
    for arm, relay in relays.items():
        request = urllib.request.Request(relay.url + "/responses", data=body, method="POST",
                                         headers={"Content-Type": "application/json"})
        try:
            with opener.open(request, timeout=120) as response:
                receipt[arm] = response.status
        except Exception as error:  # recorded and fatal below
            receipt[arm] = type(error).__name__
    write_json(out / "warmup.json", receipt)
    if any(status != 200 for status in receipt.values()):
        raise SystemExit(f"relay warm-up failed: {receipt}")


def execute(out: Path, protocol: dict, jobs: list[list], results: Path, *, smoke: bool = False) -> None:
    token = p1.load_copilot_token()
    tasks = {t["id"]: t for t in protocol["tasks"]}
    lock = threading.Lock()
    relays = {arm: Relay(token) for arm in ARMS}
    for relay in relays.values():
        relay.__enter__()
    try:
        warmup(relays, out)

        def one(arm: str, task: dict, repeat: int, suffix: str = "") -> dict:
            try:
                row = run_session(out, arm, task, repeat, relays[arm], suffix=suffix, smoke=smoke)
            except Exception as error:  # recorded as infrastructure, never silently dropped
                row = failed_row(task, arm, repeat, suffix, error)
            p1.append_jsonl(results, row, lock)
            u = row.get("usage") or {"calls": 0, "input": 0, "output": 0}
            print(f"[{row['session']:<22}] {row['status']:<5} calls={u['calls']:>3} raw={u['input'] + u['output']:>10,} "
                  f"first_cached={row['first_call'].get('cached')} why={row['why']}", flush=True)
            return row

        def lane(arm: str) -> None:
            rows = [one(arm, tasks[task_id], repeat) for repeat, task_id in jobs]
            for row in [r for r in rows if r["status"] == "infra"]:  # pre-declared: one re-run per infra failure
                one(arm, tasks[row["task"]], row["repeat"], "-rerun")

        with ThreadPoolExecutor(max_workers=len(ARMS)) as pool:
            list(pool.map(lane, ARMS))
    finally:
        for relay in relays.values():
            relay.__exit__()


# --------------------------------------------------------------------------- prepare and freeze

def apply_patch(copy: Path, patch_text: str) -> None:
    patch = copy.parent / "reference.patch"
    patch.write_text(patch_text, encoding="utf-8", newline="\n")
    subprocess.run([str(p1.GIT_EXE), "apply", "--whitespace=nowarn", str(patch)], cwd=copy, check=True,
                   capture_output=True)


def validate_tasks(tasks: list[dict], templates: dict[str, Path]) -> None:
    ids = [t["id"] for t in tasks]
    if len(set(ids)) != len(ids):
        raise SystemExit("task ids must be unique")
    if Counter(t["category"] for t in tasks) != Counter(QUOTA) or {t["set"] for t in tasks} != {"primary"}:
        raise SystemExit(f"task quota must be {QUOTA}, all primary")
    for task in tasks:
        if task["category"] == "investigate":
            if not isinstance(task.get("expected"), dict) or task.get("check"):
                raise SystemExit(f"{task['id']}: investigate tasks need expected JSON and no check")
            continue
        if not task.get("check") or not task.get("allowed_paths") or not task.get("reference_patch"):
            raise SystemExit(f"{task['id']}: edit and feature tasks need check, allowed_paths and reference_patch")
        for arm, template in templates.items():  # each check must judge both arms' workspaces the same way
            with tempfile.TemporaryDirectory() as tmp:
                copy = Path(tmp) / "repo"
                shutil.copytree(template, copy)
                if run_check(task, copy)[0]:
                    raise SystemExit(f"{task['id']}: check passes on the untouched {arm} workspace")
                apply_patch(copy, task["reference_patch"])
                outside = [c for c in changed_files(copy, template) if not c.startswith(tuple(task["allowed_paths"]))]
                if outside:
                    raise SystemExit(f"{task['id']}: the reference patch changes files outside allowed_paths: {outside}")
                ok, detail = run_check(task, copy)
                if not ok:
                    raise SystemExit(f"{task['id']}: check fails with the reference patch ({arm}): {detail[-600:]}")


def git_snapshot(root: Path, tar: Path) -> None:
    root.mkdir(parents=True)
    with tarfile.open(tar) as archive:
        archive.extractall(root, filter="data")
    for command in (["init", "-q"], ["add", "-A"], ["-c", "user.name=prs5", "-c", "user.email=prs5@example.invalid",
                                                    "commit", "-qm", "snapshot"]):
        subprocess.run([str(p1.GIT_EXE), *command], cwd=root, check=True, capture_output=True)


def install_tm(home: Path, repo: Path) -> dict:
    """The documented TokenMaster install for Copilot CLI, into an isolated home."""
    env = base_env(home, extra_path=(p1.GRAPHIFY_EXE.parent,))
    receipts = {}
    for name, argv in (("setup.py", [sys.executable, "-B", str(SKILL / "setup.py"), str(repo), "--host", "copilot",
                                     "--python", sys.executable]),
                       ("brainspace_setup.py", [sys.executable, "-B", str(SKILL / "brainspace_setup.py"), "--host",
                                                "copilot", "--python", sys.executable, "--tokenizer-file",
                                                str(TOKENIZER)])):
        proc = subprocess.run(argv, cwd=SKILL, env=env, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=900, stdin=subprocess.DEVNULL)
        receipts[name] = {"exit": proc.returncode, "tail": (proc.stdout + proc.stderr)[-1500:]}
        if proc.returncode:
            raise SystemExit(f"{name} failed: {receipts[name]['tail']}")
    return receipts


def prepare(out: Path, tasks_file: Path) -> None:
    if out.exists():
        raise SystemExit(f"output must be new: {out}")
    if LANES.exists():
        p1.remove_tree(LANES)
    out.mkdir(parents=True)
    tar = out / "snapshot.tar"
    subprocess.run([str(p1.GIT_EXE), "archive", "--format=tar", "-o", str(tar), p1.SNAPSHOT_COMMIT,
                    *p1.SNAPSHOT_PATHS], cwd=REPO, check=True)
    git_snapshot(out / "templates" / "stock", tar)
    versions = {arm: cli_version(lane_root(arm) / "home") for arm in ARMS}
    if set(versions.values()) != {CLI_VERSION}:
        raise SystemExit(f"Copilot CLI version must be {CLI_VERSION!r}: {versions}")
    package_sha256 = tree_manifest(lane_package("stock"))
    if tree_manifest(lane_package("tm")) != package_sha256:
        raise SystemExit("the two lanes run different Copilot CLI packages")
    tm_repo = lane_root("tm") / "tokenmaster"  # install where the sessions run, then keep it as the template
    git_snapshot(tm_repo, tar)
    install = install_tm(lane_root("tm") / "home", tm_repo)
    shutil.copytree(tm_repo, out / "templates" / "tm")
    templates = {arm: out / "templates" / arm for arm in ARMS}
    stock_manifest = p1.manifest(templates["stock"])
    if visible(p1.manifest(templates["tm"])) != stock_manifest:
        raise SystemExit("the TokenMaster install changed visible repository files")
    tasks = json.loads(tasks_file.read_text(encoding="utf-8"))["tasks"]
    validate_tasks(tasks, templates)
    texts = [(templates["stock"] / rel).read_text(encoding="utf-8", errors="replace") for rel in stock_manifest]
    for task in tasks:  # leak tripwire: no task text inside the workspace
        if any(task["prompt"][:80] in text for text in texts):
            raise SystemExit(f"{task['id']}: task text is readable inside the workspace")
    ignored_by_git = subprocess.run([str(p1.GIT_EXE), "check-ignore", "-q", "graphify-out/graph.json"],
                                    cwd=templates["tm"]).returncode == 0
    from brainspace import tokens
    jobs = []
    for repeat in range(1, REPEATS + 1):
        order = [t["id"] for t in tasks]
        random.Random(SEED + repeat).shuffle(order)
        jobs += [[repeat, task_id] for task_id in order]
    protocol = {
        "study": "PRS-5", "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "model": MODEL,
        "reasoning_effort": EFFORT, "copilot_cli": {"version": CLI_VERSION, "launcher": COPILOT,
                                                    "launcher_sha256": sha256_file(Path(COPILOT).resolve()),
                                                    "package_manifest_sha256": package_sha256},
        "flags": FLAGS, "session_timeout_seconds": SESSION_TIMEOUT, "seed": SEED, "repeats": REPEATS,
        "arms": list(ARMS), "lanes": {arm: str(lane_root(arm) / "tokenmaster") for arm in ARMS},
        "endpoints": ENDPOINTS, "primary_endpoints": list(PRIMARY), "workload_floor_raw_tokens": WORKLOAD_FLOOR,
        "prices_relative_to_input": PRICES, "infra_statuses": sorted(INFRA_STATUSES),
        "snapshot": {"commit": p1.SNAPSHOT_COMMIT, "tar_sha256": sha256_file(tar), "visible_files": len(stock_manifest),
                     "manifest_sha256": sha256_bytes(json.dumps(stock_manifest, sort_keys=True).encode())},
        "templates_sha256": {arm: tree_manifest(path) for arm, path in templates.items()},
        "tm_install": {"receipts": install, "install_manifest_sha256": install_manifest(lane_root("tm") / "home"),
                       "graphify_out_left_in_repo": (templates["tm"] / "graphify-out").exists(),
                       "graphify_out_ignored_by_git": ignored_by_git},
        "tasks": tasks, "tasks_file": str(tasks_file), "tasks_sha256": sha256_file(tasks_file), "schedule": jobs,
        "task_prompt_tokens_cl100k": {t["id"]: tokens.count_tokens(t["prompt"]) for t in tasks},
        "harness_sha256": sha256_file(Path(__file__)), "shared_harness_sha256": sha256_file(Path(p1.__file__)),
        "shared_harness2_sha256": sha256_file(Path(p2.__file__)),
        "shared_harness3_sha256": sha256_file(Path(p3.__file__)),
        "protocol_doc_sha256": sha256_file(PLUGIN / "docs/PRS5_PROTOCOL.md"),
        "product_sha256": {p.relative_to(REPO).as_posix(): sha256_file(p) for p in product_files()},
    }
    write_json(out / "protocol.json", protocol)
    digest = sha256_file(out / "protocol.json")
    (out / "protocol.sha256").write_text(digest + "\n", encoding="utf-8")
    print(f"prepared {out}: {len(tasks)} tasks x {len(ARMS)} arms x {REPEATS} repeats = {2 * len(jobs)} sessions; "
          f"protocol.json sha256 {digest}")


def verify_frozen(out: Path, protocol: dict, *, live: bool) -> None:
    if sha256_file(out / "protocol.json") != (out / "protocol.sha256").read_text(encoding="utf-8").strip():
        raise SystemExit("protocol.json changed after prepare")
    frozen = {"harness": (Path(__file__), protocol["harness_sha256"]),
              "shared harness": (Path(p1.__file__), protocol["shared_harness_sha256"]),
              "shared harness 2": (Path(p2.__file__), protocol["shared_harness2_sha256"]),
              "shared harness 3": (Path(p3.__file__), protocol["shared_harness3_sha256"]),
              "protocol document": (PLUGIN / "docs/PRS5_PROTOCOL.md", protocol["protocol_doc_sha256"]),
              "tasks": (Path(protocol["tasks_file"]), protocol["tasks_sha256"])}
    frozen.update({rel: (REPO / rel, digest) for rel, digest in protocol["product_sha256"].items()})
    if {p.relative_to(REPO).as_posix() for p in product_files()} != set(protocol["product_sha256"]):
        raise SystemExit("product files were added or removed after prepare")
    for name, (path, digest) in frozen.items():
        if not path.is_file() or sha256_file(path) != digest:
            raise SystemExit(f"{name} changed after prepare ({path}); re-run prepare and disclose it")
    for arm, digest in protocol["templates_sha256"].items():
        if tree_manifest(out / "templates" / arm) != digest:
            raise SystemExit(f"{arm} template changed after prepare")
    if live:  # what the sessions will run: launcher, package and TokenMaster install
        if sha256_file(Path(COPILOT).resolve()) != protocol["copilot_cli"]["launcher_sha256"]:
            raise SystemExit("the Copilot CLI launcher changed after prepare")
        if install_manifest(lane_root("tm") / "home") != protocol["tm_install"]["install_manifest_sha256"]:
            raise SystemExit("the TokenMaster install changed after prepare")


def verify_packages(protocol: dict, smoke: bool) -> None:
    for arm in ARMS:
        if tree_manifest(lane_package(arm, smoke)) != protocol["copilot_cli"]["package_manifest_sha256"]:
            raise SystemExit(f"{arm}: the Copilot CLI package differs from the one frozen at prepare")


def request_tools(run_dir: Path) -> set[str]:
    for capture in read_jsonl(run_dir / "captures.jsonl"):
        try:
            return {t.get("name") or (t.get("function") or {}).get("name") or ""
                    for t in json.loads(capture["input"]).get("tools") or []}
        except (ValueError, AttributeError):
            continue
    return set()


def smoke_gate(out: Path) -> dict:
    """Pre-declared: run starts only if the smoke sessions show a working setup in both arms."""
    rows = read_jsonl(out / "smoke" / "results.jsonl")
    problems = []
    for arm in ARMS:
        mine = sorted((r for r in rows if r["arm"] == arm), key=lambda r: r["repeat"])
        if len(mine) < 2 or any(r["status"] != "pass" for r in mine):
            problems.append(f"{arm}: smoke sessions did not all pass")
    tm = sorted((r for r in rows if r["arm"] == "tm" and r.get("usage")), key=lambda r: r["repeat"])
    tools = request_tools(out / "smoke" / "runs" / tm[-1]["session"]) if tm else set()
    if tm:
        if not tm[-1]["bridge"] or not tm[-1]["bridge"]["stable_prefix"]:
            problems.append("tm: the bridge did not apply the cache-stable system prompt")
        first = tm[-1]["first_call"]
        if not first.get("input") or (first.get("cached") or 0) < 0.5 * first["input"]:
            problems.append("tm: the second smoke session did not start warm")
        if not any("read_symbol" in name for name in tools):
            problems.append("tm: the tokenmaster-nav tools are missing from the requests")
    if problems:
        raise SystemExit("smoke gate failed: " + "; ".join(problems))
    return {"tm_request_tools": sorted(tools)}


def child_main(out: Path, mode: str) -> int:
    protocol = json.loads((out / "protocol.json").read_text(encoding="utf-8"))
    verify_frozen(out, protocol, live=True)
    from brainspace import tokens
    tokens.count_tokens("warm-up")  # load once before worker threads (lazy init is not thread-safe)
    if mode == "smoke":
        smoke = out / "smoke"
        if smoke.exists():
            p1.remove_tree(smoke)
        smoke.mkdir()
        for arm in ARMS:  # smoke lanes use other folders, so their prompts differ from the study's
            home = lane_root(arm, smoke=True) / "home"
            if arm == "tm" and not home.exists():
                shutil.copytree(lane_root("tm") / "home", home)
            cli_env(home, "http://127.0.0.1:9")  # copies the package if it is missing
        verify_packages(protocol, smoke=True)
        shutil.copytree(out / "templates", smoke / "templates")
        task = {**p1.SMOKE_TASK, "set": "primary", "category": "investigate"}
        execute(smoke, {**protocol, "tasks": [task]}, [[0, "SMOKE"], [1, "SMOKE"]], smoke / "results.jsonl",
                smoke=True)
        print(json.dumps(smoke_gate(out)))
    else:
        if (out / "results.jsonl").exists():
            raise SystemExit("results already exist; a study is never re-run in place")
        write_json(out / "smoke-gate.json", smoke_gate(out))
        verify_packages(protocol, smoke=False)
        execute(out, protocol, protocol["schedule"], out / "results.jsonl")
    return 0


# --------------------------------------------------------------------------- analysis

def change_per_finished_task(chosen: dict, tasks: list[str], repeats: list[int], endpoint: str, seed: int,
                             rounds: int = 2000) -> dict:
    by_task = {}
    for t in tasks:
        for r in repeats:
            a, b = chosen.get((t, "tm", r)), chosen.get((t, "stock", r))
            if a and b and a["status"] in ("pass", "fail") and b["status"] in ("pass", "fail"):
                by_task.setdefault(t, []).append((p2.endpoint_value(a["usage"], endpoint), a["status"] == "pass",
                                                  p2.endpoint_value(b["usage"], endpoint), b["status"] == "pass"))

    def change(groups) -> float:
        va, pa, vb, pb = (sum(row[i] for group in groups for row in group) for i in range(4))
        if pa == 0 and pb == 0:
            return math.nan
        if pb == 0:
            return -1.0  # stock finished nothing: its cost per finished task is unbounded
        if pa == 0 or not vb:
            return math.inf
        return (va / pa) / (vb / pb) - 1

    groups = list(by_task.values())
    if not groups:
        return {"change": None, "ci95": [None, None], "undefined_draws": 0}
    rng = random.Random(seed)
    draws = [change([[rng.choice(g) for _ in g] for g in (rng.choice(groups) for _ in groups)]) for _ in range(rounds)]
    kept = sorted(d for d in draws if not math.isnan(d))
    point = change(groups)
    return {"change": None if math.isnan(point) else round(point, 4),
            "ci95": [round(kept[int(0.025 * len(kept))], 4), round(kept[int(0.975 * len(kept)) - 1], 4)] if kept else [None, None],
            "undefined_draws": len(draws) - len(kept)}


def leak_hits(run_dir: Path, markers: list[str]) -> int:
    """Tool calls or results that mention the study's own files (answers, other lanes)."""
    hits = 0
    for capture in read_jsonl(run_dir / "captures.jsonl"):
        try:
            items = json.loads(capture["input"]).get("input") or []
        except (ValueError, AttributeError):
            continue
        text = " ".join(str(i.get("arguments", "")) + str(i.get("output", "")) for i in items if isinstance(i, dict)
                        and i.get("type") in ("function_call", "function_call_output")).lower()
        hits += any(m.lower() in text for m in markers)
    return hits


def analyze(out: Path) -> dict:
    protocol = json.loads((out / "protocol.json").read_text(encoding="utf-8"))
    verify_frozen(out, protocol, live=False)
    rows = read_jsonl(out / "results.jsonl")
    keys = ("calls", "input", "cached", "cache_write", "output")
    worst, ratios = 0.0, set()
    for row in rows:  # recount every session from its raw captures, and check it against the provider's bill
        if row.get("usage") is None:
            continue
        recount = session_usage(out / "runs" / row["session"], from_captures=True)
        if {k: recount[k] for k in keys} != {k: row["usage"][k] for k in keys}:
            raise SystemExit(f"recount mismatch for {row['session']}")
        if row["usage"].get("bill_units") is not None:
            worst = max(worst, abs(row["usage"]["bill_units"] - billed(row["usage"])))
        ratios |= {tuple(pair) for group in row["usage"].get("bill_ratios") or [] for pair in group}
    if worst > 0.5 or ratios - set(PRICES.items()):
        raise SystemExit(f"provider bills differ from the frozen price table: worst {worst:.2f}, prices {sorted(ratios)}")
    chosen = p1.final_rows(rows)
    repeats = sorted({r["repeat"] for r in rows})
    tasks = [t["id"] for t in protocol["tasks"]]
    expected = {(t, a, r) for t in tasks for a in ARMS for r in range(1, REPEATS + 1)}
    missing = sorted(map(list, expected - set(chosen)))
    excluded = sorted([list(k) for k, r in chosen.items() if r["status"] == "infra"])
    markers = [str(out), out.name, "protocol.json", "prs5_tasks", "reference_patch", "smoke-gate",
               *[str(lane_root(a)) for a in ARMS]]
    with mock.patch.dict(p2.ENDPOINTS, ENDPOINTS), mock.patch.object(p1, "wilcoxon_exact", p3.wilcoxon_exact):
        arms = {}
        for arm in ARMS:
            group = [r for (t, a, _), r in chosen.items() if a == arm and t in tasks]
            valid = [r for r in group if r["status"] in ("pass", "fail")]
            passes = sum(r["status"] == "pass" for r in valid)
            totals = {e: round(sum(p2.endpoint_value(r["usage"], e) for r in valid), 1) for e in ENDPOINTS}
            firsts = [r["first_call"] for r in valid if r["first_call"].get("input")]
            arms[arm] = {"graded": len(valid), "passes": passes, "success_ci95": p1.wilson(passes, len(valid)),
                         "infra_excluded": sum(r["status"] == "infra" for r in group),
                         "failure_reasons": dict(Counter(r["why"].split(":")[0] for r in group if r["status"] != "pass")),
                         "totals": totals,
                         "per_finished_task": {e: round(totals[e] / passes, 1) if passes else None for e in ENDPOINTS},
                         "per_session": {e: round(totals[e] / max(1, len(valid)), 1) for e in ENDPOINTS},
                         "warm_starts": sum((f.get("cached") or 0) >= 0.5 * f["input"] for f in firsts),
                         "workload_floor_met": totals["raw_tokens"] >= WORKLOAD_FLOOR,
                         "leak_hits": sum(leak_hits(out / "runs" / r["session"], markers) for r in valid),
                         "bridge": {k: sum((r.get("bridge") or {}).get(k, 0) for r in valid)
                                    for k in ("calls", "stable_prefix", "shaped")} if arm == "tm" else None}
        comparisons, seed = {}, SEED
        for endpoint in ENDPOINTS:
            comparisons[endpoint] = p2.compare(chosen, tasks, repeats, "tm", "stock", endpoint, seed)
            comparisons[endpoint]["per_finished_task"] = change_per_finished_task(chosen, tasks, repeats, endpoint,
                                                                                  seed + 1)
            seed += 2
    for endpoint, adjusted in zip(PRIMARY, p1.holm([comparisons[e]["wilcoxon_p"] for e in PRIMARY]), strict=True):
        entry = comparisons[endpoint]
        entry["holm_p"] = round(adjusted, 5)
        lower = entry["change_ci95"][1] < 0 and adjusted < 0.05
        higher = entry["change_ci95"][0] > 0 and adjusted < 0.05
        entry["verdict"] = "lower" if lower else "higher" if higher else "no significant difference"
    per_task = {}
    for t in tasks:
        for arm in ARMS:
            group = [r for (task, a, _), r in chosen.items() if task == t and a == arm and r["status"] in ("pass", "fail")]
            per_task.setdefault(t, {})[arm] = {"passes": sum(r["status"] == "pass" for r in group),
                                               "raw_tokens": sum(r["usage"]["input"] + r["usage"]["output"] for r in group),
                                               "calls": sum(r["usage"]["calls"] for r in group)}
    summary = {"study": "PRS-5", "protocol_sha256": sha256_file(out / "protocol.json"),
               "harness_sha256": protocol["harness_sha256"], "copilot_cli": protocol["copilot_cli"]["version"],
               "model": MODEL, "sessions_recorded": len(rows), "tasks": tasks, "missing_sessions": missing,
               "excluded_infra_sessions": excluded, "billing_check": {"max_abs_diff": round(worst, 3),
                                                                      "prices_seen": sorted(ratios)},
               "arms": arms, "comparisons": comparisons, "per_task": per_task}
    lines = ["# PRS-5 results (generated by `run_prs5_study.py analyze`)", "",
             f"Real {protocol['copilot_cli']['version'].rstrip('.')}, model {MODEL}. {len(tasks)} heavy tasks x "
             f"{len(repeats)} repeats per arm, run back to back in one folder per arm.", "",
             "| Arm | Passed | Raw tokens (total) | Raw tokens per finished task | Uncached input | Calls | "
             "Billed per finished task | Warm starts |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for arm, a in arms.items():
        lines.append(f"| {arm} | {a['passes']}/{a['graded']} | {a['totals']['raw_tokens']:,.0f} | "
                     f"{a['per_finished_task']['raw_tokens'] or 0:,.0f} | {a['totals']['uncached_input']:,.0f} | "
                     f"{a['totals']['calls']:,.0f} | {a['per_finished_task']['billed'] or 0:,.0f} | {a['warm_starts']} |")
    lines += ["", "| Endpoint | tm vs stock, paired (95% CI) | Per finished task (95% CI) | Holm p | Tasks lower | Verdict |",
              "| --- | ---: | ---: | ---: | ---: | --- |"]
    for endpoint in ENDPOINTS:
        c, f = comparisons[endpoint], comparisons[endpoint]["per_finished_task"]
        ci = f["ci95"] if f["ci95"][0] is not None else [math.nan, math.nan]
        lines.append(f"| {endpoint}{' (primary)' if endpoint in PRIMARY else ''} | {c['change'] * 100:+.1f}% "
                     f"[{c['change_ci95'][0] * 100:+.1f}%, {c['change_ci95'][1] * 100:+.1f}%] | "
                     f"{(f['change'] if f['change'] is not None else math.nan) * 100:+.1f}% "
                     f"[{ci[0] * 100:+.1f}%, {ci[1] * 100:+.1f}%] | {c.get('holm_p', '-')} | "
                     f"{c['tasks_lower']} of {len(tasks)} | {c.get('verdict', 'secondary')} |")
    lines += ["", f"Workload floor ({WORKLOAD_FLOOR:,} raw tokens per arm): "
              + ", ".join(f"{arm} {'met' if a['workload_floor_met'] else 'NOT met'}" for arm, a in arms.items())
              + f". Missing sessions: {len(missing)}. Pairs lost to infrastructure: {len(excluded)}. "
              f"Leak audit hits: stock {arms['stock']['leak_hits']}, tm {arms['tm']['leak_hits']}. "
              f"Provider-bill check: largest session difference {worst:.3f} units."]
    write_json(out / "summary.json", summary)
    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return summary


# --------------------------------------------------------------------------- self-test

def _fake_session(out: Path, task: str, arm: str, repeat: int, status: str, calls: list[tuple]) -> dict:
    run_dir = out / "runs" / f"{task}-{arm}-r{repeat}"
    run_dir.mkdir(parents=True)
    for n, (code, inp, cached, write, output) in enumerate(calls, 1):
        tail = (f'data: {{"response":{{"usage":{{"input_tokens":{inp},"input_tokens_details":{{"cached_tokens":{cached},'
                f'"cache_write_tokens":{write}}},"output_tokens":{output}}}}}}}') if code == 200 else ""
        bill = {"units": billed({"input": inp, "cached": cached, "cache_write": write, "output": output}),
                "ratios": dict(PRICES)} if code == 200 else None
        with (run_dir / "calls.jsonl").open("a", encoding="utf-8") as h:
            h.write(json.dumps({"n": n, "status": code, "prefix_sha256": "p", "usage": cb._usage(tail.encode()),
                                "bill": bill}) + "\n")
        with (run_dir / "captures.jsonl").open("a", encoding="utf-8") as h:
            h.write(json.dumps({"n": n, "status": code, "input": json.dumps({"input": []}), "output_tail": tail}) + "\n")
    usage = session_usage(run_dir)
    return {"task": task, "set": "primary", "category": "investigate", "arm": arm, "repeat": repeat,
            "session": run_dir.name, "status": status, "why": "ok" if status == "pass" else "wrong:x", "usage": usage,
            "first_call": {"input": calls[0][1], "cached": calls[0][2]},
            "bridge": {"calls": len(calls), "stable_prefix": len(calls), "shaped": 0} if arm == "tm" else None}


def self_test() -> None:
    events = [{"type": "assistant.message", "data": {"content": "thinking", "phase": "commentary"}},
              {"type": "assistant.message", "data": {"content": '{"a": 1}', "phase": "final_answer"}},
              {"type": "result", "exitCode": 0}]
    assert final_answer("\n".join(json.dumps(e) for e in events) + "\nnot json") == '{"a": 1}'
    assert final_answer(json.dumps(events[0])) == "thinking" and final_answer("") is None
    details = [{"token_type": k, "token_count": c, "cost_per_batch": int(p * 1e12), "batch_size": 1000000}
               for k, c, p in (("input", 100, 1), ("cache_read", 600, 0.1), ("cache_write", 300, 1.25), ("output", 50, 5))]
    bill = provider_bill('x "copilot_usage": ' + json.dumps({"token_details": details, "total_nano_aiu": 1}) + "}")
    assert abs(bill["units"] - (100 + 60 + 375 + 250)) < 1e-9 and bill["ratios"] == PRICES
    assert provider_bill('"copilot_usage": 123,"n":45') is None and provider_bill("none") is None
    usage = {"calls": 2, "input": 1000, "cached": 600, "cache_write": 300, "output": 50}
    with mock.patch.dict(p2.ENDPOINTS, ENDPOINTS):
        assert p2.endpoint_value(usage, "billed") == billed(usage) == 100 + 60 + 375 + 250
        assert p2.endpoint_value(usage, "raw_tokens") == 1050 and p2.endpoint_value(usage, "uncached_input") == 400
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        row = _fake_session(Path(tmp), "Q", "stock", 1, "pass", [(200, 900, 600, 290, 7), (502, 0, 0, 0, 0)])
        assert (row["usage"]["calls"], row["usage"]["input"], row["usage"]["http_errors"],
                row["usage"]["infra_statuses"]) == (1, 900, 1, 1)
        run_dir = Path(tmp) / "runs" / "Q-stock-r1"
        recount = session_usage(run_dir, from_captures=True)
        assert {k: recount[k] for k in ("calls", "input", "cached", "cache_write", "output")} == \
               {k: row["usage"][k] for k in ("calls", "input", "cached", "cache_write", "output")}
        (run_dir / "calls.jsonl").open("a", encoding="utf-8").write('{"n": 9, "status": 2')  # killed mid-line
        assert session_usage(run_dir)["calls"] == 1
        template, lane = Path(tmp) / "template", Path(tmp) / "lane"
        (template / "pkg").mkdir(parents=True)
        (template / "pkg/a.py").write_text("X = 1\n", encoding="utf-8")
        shutil.copytree(template, lane)
        (lane / "graphify-out").mkdir()
        (lane / "graphify-out/graph.json").write_text("{}", encoding="utf-8")
        ask = {"id": "Q", "category": "investigate", "expected": {"x": 1}, "unordered_list_keys": []}
        assert grade(ask, 'Answer: {"x": 1}', lane, template)["pass"] is True
        assert grade(ask, '{"x": 2}', lane, template)["why"] == "wrong:x"
        edit = {"id": "E", "category": "edit", "allowed_paths": ["pkg/"],
                "check": "import os, pathlib, sys\nassert 'operator' not in os.environ.get('HOME', '')\n"
                         "sys.exit(0 if 'X = 2' in pathlib.Path('pkg/a.py').read_text() else 1)"}
        assert grade(edit, None, lane, template)["why"] == "check_failed"
        (lane / "pkg/a.py").write_text("X = 2\n", encoding="utf-8")
        assert grade(edit, None, lane, template)["pass"] is True
        (lane / "other.py").write_text("", encoding="utf-8")
        assert grade(edit, None, lane, template)["why"] == "changes_outside_allowed_paths"
        assert grade(ask, '{"x": 1}', lane, template)["why"] == "modified_files_in_question_task"
        env = base_env(Path(tmp) / "home")
        assert "python" not in env["PATH"].lower() and env["HOME"].startswith(tmp) and "OPENAI_BASE_URL" not in env
        out = Path(tmp) / "study"  # an end-to-end analysis on synthetic sessions
        rows = []
        for t_index, task in enumerate(("A", "B", "C")):
            for repeat in (1, 2):
                rows.append(_fake_session(out, task, "stock", repeat, "pass", [(200, 14000, 0, 13900, 60), (200, 15000, 14000, 900, 80)]))
                rows.append(_fake_session(out, task, "tm", repeat, "pass" if t_index else "fail",
                                          [(200, 14500, 14000, 400, 50), (200, 15400, 14500, 800, 70)]))
        rows.append({**rows[-1], "status": "infra", "session": "C-tm-r2-rerun"})  # an infra re-run is not chosen
        out.mkdir(exist_ok=True)
        (out / "results.jsonl").write_text("\n".join(json.dumps(r) for r in rows[:-1]) + "\n", encoding="utf-8")
        fake = {"tasks": [{"id": t} for t in ("A", "B", "C")], "harness_sha256": "x",
                "copilot_cli": {"version": CLI_VERSION}}
        (out / "protocol.json").write_text(json.dumps(fake), encoding="utf-8")
        with mock.patch.object(sys.modules[__name__], "verify_frozen", lambda *a, **k: None), \
                mock.patch("builtins.print"):
            summary = analyze(out)
        assert summary["comparisons"]["raw_tokens"]["change"] > 0 and summary["comparisons"]["billed"]["change"] < 0
        assert summary["arms"]["tm"]["passes"] == 4 and summary["missing_sessions"] == [] and "verdict" in \
               summary["comparisons"]["billed"]
    relay = Relay("secret-token")
    try:
        headers = relay.upstream_headers({"Authorization": "Bearer client", "Content-Type": "application/json",
                                          "Host": "x", "Content-Length": "5"})
        assert headers["Authorization"] == "Bearer secret-token" and "Host" not in headers
        assert relay.prepare("/responses", b"{}") == (b"{}", {})  # no session: nothing recorded
    finally:
        relay.server.server_close()
    assert LANE["stock"] != LANE["tm"] and "tm" not in LANE.values() and "stock" not in LANE.values()
    print("self-test passed")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("self-test", "prepare", "smoke", "run", "analyze"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tasks", type=Path, default=PLUGIN / "evals/prs5_tasks.json")
    args = parser.parse_args(argv)
    if args.command == "self-test":
        self_test()
        return 0
    if args.output is None:
        parser.error("--output is required")
    out = args.output.resolve()
    if args.command == "prepare":
        prepare(out, args.tasks.resolve())
        return 0
    if args.command in ("smoke", "run"):
        return child_main(out, args.command)
    analyze(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
