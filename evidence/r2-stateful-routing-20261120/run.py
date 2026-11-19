"""Live 4-arm stateful routing & pragmatic deixis benchmark runner (`r2-stateful-routing-20261120`).

Arms:
  - stock       : Stock Copilot CLI 1.0.112 across Turn 1 (start), Turn 2 (--resume <sid>), Turn 3 (--continue)
  - tm_locked   : TokenMaster --lean --router r2 --resume-escalate off (zero-network local R2 + strict resume lock)
  - tm_md1_v1   : TokenMaster --lean --router md1 --resume-escalate v1 (cloud MD-1 + stateless flat-0.50 escalation)
  - tm_r2       : TokenMaster --lean --router r2 --resume-escalate r2 (zero-network local R2 + deixis + warm-cache Bayes tau*)

Commands:
  python run.py self-test
  python run.py prepare
  python run.py run [--tasks S01,S05,...] [--budget-usd 35] [--fresh]
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PLUGIN = REPO / "token-master-plugin"
EVALS = PLUGIN / "evals"
SKILL = PLUGIN / "skills" / "token-master"
sys.path.insert(0, str(EVALS))
sys.path.insert(0, str(SKILL))

from brainspace import local_router_weights
import brainspace_copilot_bridge as bridge
import tokenomics
from tokenomics import NANO_PER_USD

CLI_PKG_VERSION = "1.0.112"
COPILOT = str(
    Path(os.environ.get("LOCALAPPDATA", ""))
    / "Microsoft"
    / "WinGet"
    / "Packages"
    / "GitHub.Copilot_Microsoft.Winget.Source_8wekyb3d8bbwe"
    / "copilot.exe"
)
INSTALLED_PKG = Path(os.environ.get("LOCALAPPDATA", "")) / "copilot" / "pkg" / "win32-x64" / CLI_PKG_VERSION
GIT = shutil.which("git") or "git"
ROBOCOPY = shutil.which("robocopy") or "robocopy"
MODEL = "gpt-6-astra"
REASONING = "low"
ARMS = ("stock", "tm_locked", "tm_md1_v1", "tm_r2")
TM_ARMS = ("tm_locked", "tm_md1_v1", "tm_r2")
OFFLINE_TM_ARMS = ("tm_locked", "tm_r2")
LANE_NAMES = {"stock": "l1", "tm_locked": "l2", "tm_md1_v1": "l3", "tm_r2": "l4"}

ARM_FLAGS: dict[str, tuple[str, ...]] = {
    "tm_locked": ("--lean", "--router", "r2", "--resume-escalate", "off"),
    "tm_md1_v1": ("--lean", "--router", "md1", "--resume-escalate", "v1"),
    "tm_r2": ("--lean", "--router", "r2", "--resume-escalate", "r2"),
}

DEFAULT_LANES = Path(r"C:\tm-lanes\r2-stateful-routing-20261120")
DEFAULT_PYTHON = Path(r"C:\tm-lanes\tm-runtime\Scripts\python.exe")
DEFAULT_TIKTOKEN = Path(r"C:\tm-lanes\tm-runtime\cl100k_base.tiktoken")
DEFAULT_MD1_ENDPOINT = os.environ.get("TOKENMASTER_MD1_ENDPOINT", "https://raifoundry.services.ai.azure.com")

PROTOCOL = HERE / "PROTOCOL.md"
PROTOCOL_HASH = HERE / "PROTOCOL.sha256"
TASKS_FILE = HERE / "tasks.json"
SETUP_FILE = HERE / "setup.json"
RUNS_FILE = HERE / "runs.jsonl"
SESSIONS_DIR = HERE / "sessions"


class StudyError(RuntimeError):
    pass


class BudgetCapExceeded(RuntimeError):
    pass


class UsdBudget:
    def __init__(self, cap_usd: float, initial_nano: int = 0):
        self.cap_nano = round(cap_usd * NANO_PER_USD)
        self.spent_nano = int(initial_nano)
        self._lock = threading.Lock()

    def check(self) -> None:
        with self._lock:
            if self.spent_nano >= self.cap_nano:
                raise BudgetCapExceeded(
                    f"USD budget cap reached: ${self.spent_nano / NANO_PER_USD:.4f} / "
                    f"${self.cap_nano / NANO_PER_USD:.2f}"
                )

    def add(self, nano: int) -> float:
        with self._lock:
            self.spent_nano += nano
            return self.spent_nano / NANO_PER_USD


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def ensure_git_exclude(work: Path) -> None:
    excl = work / ".git" / "info" / "exclude"
    excl.parent.mkdir(parents=True, exist_ok=True)
    existing = excl.read_text(encoding="utf-8") if excl.is_file() else ""
    extra = [".token-master/", "graphify-out/", "__pycache__/", ".pytest_cache/", "*.pyc"]
    lines = existing.splitlines()
    for item in extra:
        if item not in lines:
            lines.append(item)
    excl.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def git_status_lines(work: Path) -> list[str]:
    out = subprocess.run([GIT, "status", "--porcelain"], cwd=work, check=True, capture_output=True, text=True).stdout
    return [ln for ln in out.splitlines() if ln.strip()]


def git_clean(work: Path) -> bool:
    return len(git_status_lines(work)) == 0


def git_diff(work: Path) -> str:
    return subprocess.run([GIT, "--no-pager", "diff"], cwd=work, check=True, capture_output=True, text=True).stdout


def extract_json(text: str):
    if not text:
        return None
    stripped = text.strip()
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.S)
    candidates = [*reversed(fenced), stripped]
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except ValueError:
            pass
    dec = json.JSONDecoder()
    last_obj = None
    for idx, ch in enumerate(stripped):
        if ch == "{":
            try:
                obj, _ = dec.raw_decode(stripped, idx)
                if isinstance(obj, dict):
                    last_obj = obj
            except ValueError:
                continue
    return last_obj


def json_matches(got, expected: dict, unordered_keys=()) -> bool:
    if not isinstance(got, dict) or set(got.keys()) != set(expected.keys()):
        return False
    unordered = set(unordered_keys or ())
    for k, exp_v in expected.items():
        got_v = got[k]
        if k in unordered and isinstance(exp_v, list) and isinstance(got_v, list):
            if len(got_v) != len(exp_v) or sorted(map(str, got_v)) != sorted(map(str, exp_v)):
                return False
            continue
        if isinstance(exp_v, bool) or isinstance(got_v, bool):
            if type(got_v) is not type(exp_v) or got_v != exp_v:
                return False
        elif isinstance(exp_v, float):
            if not isinstance(got_v, (int, float)) or isinstance(got_v, bool) or abs(float(got_v) - exp_v) > 1e-6:
                return False
        elif got_v != exp_v:
            return False
    return True


def recharge_row(input_tokens: int, output_tokens: int, cache_read: int, cache_write: int, details_json: str) -> float:
    prices = tokenomics.prices_of(details_json)
    new = input_tokens - cache_read - cache_write
    return (
        new * prices.get("input", 0)
        + cache_read * prices.get("cache_read", 0)
        + cache_write * prices.get("cache_write", 0)
        + output_tokens * prices.get("output", 0)
    )


def load_tasks() -> list[dict]:
    return json.loads(TASKS_FILE.read_text(encoding="utf-8"))


def kept_groups_from_excluded(excluded: list[str] | tuple[str, ...]) -> list[str]:
    excl = set(excluded)
    kept = []
    for name, (tools, _) in bridge.CAPABILITY_GROUPS.items():
        if any(t not in excl for t in tools):
            kept.append(name)
    return sorted(kept)


def mirror(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [ROBOCOPY, str(src), str(dst), "/MIR", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/R:2", "/W:1"],
        capture_output=True,
        text=True,
    )
    if proc.returncode >= 8:
        raise StudyError(f"robocopy {src} -> {dst} failed ({proc.returncode}): {proc.stdout}\n{proc.stderr}")


_CACHED_GH_TOKEN: str | None = None
_GH_LOCK = threading.Lock()


def _resolve_gh_token() -> str:
    global _CACHED_GH_TOKEN
    with _GH_LOCK:
        if _CACHED_GH_TOKEN:
            return _CACHED_GH_TOKEN
        for tok_var in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
            if os.environ.get(tok_var):
                _CACHED_GH_TOKEN = os.environ[tok_var]
                return _CACHED_GH_TOKEN
        gh = shutil.which("gh")
        if not gh:
            raise StudyError("No GH_TOKEN/GITHUB_TOKEN/COPILOT_GITHUB_TOKEN in env and 'gh' CLI not found")
        proc = subprocess.run([gh, "auth", "token"], capture_output=True, text=True, timeout=15, check=True)
        tok = proc.stdout.strip()
        if not tok:
            raise StudyError("'gh auth token' returned empty token; run 'gh auth login'")
        _CACHED_GH_TOKEN = tok
        return tok


def find_graphify_dir() -> str:
    found = shutil.which("graphify")
    if found:
        return str(Path(found).resolve().parent)
    fallback = Path.home() / ".local" / "bin" / "graphify.exe"
    if fallback.is_file():
        return str(fallback.parent)
    raise StudyError("graphify executable not found; install graphifyy first")


def lane_env(
    home: Path,
    *,
    python_exe: Path,
    tiktoken_file: Path,
    md1_endpoint: str | None = None,
) -> dict[str, str]:
    system_root = os.environ.get("SystemRoot", r"C:\WINDOWS")
    path_dirs = [
        str(python_exe.parent),
        str(Path(COPILOT).resolve().parent),
        str(Path(GIT).resolve().parent),
        find_graphify_dir(),
        str(Path(system_root) / "System32"),
        system_root,
        str(Path(system_root) / "System32" / "Wbem"),
        str(Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0"),
    ]
    pwsh_dir = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "PowerShell" / "7"
    if pwsh_dir.is_dir():
        path_dirs.insert(4, str(pwsh_dir))

    appdata = home / "AppData" / "Roaming"
    localapp = home / "AppData" / "Local"
    temp = localapp / "Temp"
    for d in (home / "copilot", appdata, localapp, temp):
        d.mkdir(parents=True, exist_ok=True)
    # Pin Copilot CLI 1.0.112 inside the lane's isolated LOCALAPPDATA. Do NOT pass --no-auto-update or
    # COPILOT_AUTO_UPDATE=false, as WinGet's launcher ignores COPILOT_CLI_DIST_DIR when auto-update is disabled.
    lane_pkg = localapp / "copilot" / "pkg" / "win32-x64" / CLI_PKG_VERSION
    if not lane_pkg.is_dir():
        if not INSTALLED_PKG.is_dir():
            raise StudyError(f"expected Copilot CLI package {CLI_PKG_VERSION} at {INSTALLED_PKG}")
        mirror(INSTALLED_PKG, lane_pkg)

    env = {
        "PATH": os.pathsep.join(path_dirs),
        "PATHEXT": os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD"),
        "SystemRoot": system_root,
        "SystemDrive": os.environ.get("SystemDrive", "C:"),
        "WINDIR": os.environ.get("WINDIR", system_root),
        "COMSPEC": os.environ.get("COMSPEC", str(Path(system_root) / "System32" / "cmd.exe")),
        "PROCESSOR_ARCHITECTURE": os.environ.get("PROCESSOR_ARCHITECTURE", "AMD64"),
        "NUMBER_OF_PROCESSORS": os.environ.get("NUMBER_OF_PROCESSORS", "8"),
        "OS": os.environ.get("OS", "Windows_NT"),
        "USERPROFILE": str(home),
        "HOME": str(home),
        "HOMEDRIVE": home.drive or "C:",
        "HOMEPATH": str(home)[len(home.drive):] or "\\",
        "APPDATA": str(appdata),
        "LOCALAPPDATA": str(localapp),
        "TEMP": str(temp),
        "TMP": str(temp),
        "COPILOT_HOME": str(home / "copilot"),
        "COPILOT_CACHE_HOME": str(home / "copilot-cache"),
        "COPILOT_CLI_DIST_DIR": str(lane_pkg),
        "CLAUDE_CONFIG_DIR": str(home / ".claude"),
        "CODEX_HOME": str(home / ".codex"),
        "COPILOT_ALLOW_ALL": "true",
        "COPILOT_MODEL": MODEL,
        "NO_COLOR": "1",
        "PYTHONUTF8": "1",
        "BRAINSPACE_TOKENIZER_FILE": str(tiktoken_file),
        "TOKENMASTER_TOKENIZER_FILE": str(tiktoken_file),
        "TIKTOKEN_CACHE_DIR": str(tiktoken_file.parent),
        "GRAPHIFY_NO_AUTO_REFRESH": "1",
    }
    for tok_var in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(tok_var):
            env[tok_var] = os.environ[tok_var]
    if not any(k in env for k in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")):
        env["GH_TOKEN"] = _resolve_gh_token()
    if (home / "copilot" / "instructions").is_dir():
        env["COPILOT_CUSTOM_INSTRUCTIONS_DIRS"] = str(home / "copilot" / "instructions")
    if md1_endpoint:
        env["TOKENMASTER_MD1_ENDPOINT"] = md1_endpoint
    return env


def clear_lane_history(home: Path) -> None:
    ch = home / "copilot"
    for f in (
        "session-store.db",
        "session-store.db-wal",
        "session-store.db-shm",
        "command-history-state.json",
    ):
        (ch / f).unlink(missing_ok=True)
    for sub in ("session-state", "logs"):
        shutil.rmtree(ch / sub, ignore_errors=True)
    (ch / "token-master" / "launches.jsonl").unlink(missing_ok=True)
    (ch / "token-master" / "md1-token.json").unlink(missing_ok=True)


_MD1_TOKEN_LOCK = threading.Lock()
_CACHED_MD1_TOKEN: dict | None = None


def get_fresh_md1_token() -> dict:
    global _CACHED_MD1_TOKEN
    with _MD1_TOKEN_LOCK:
        now_ts = int(time.time())
        if _CACHED_MD1_TOKEN and int(_CACHED_MD1_TOKEN.get("expires_on", 0)) - now_ts > 600:
            return dict(_CACHED_MD1_TOKEN)
        az = shutil.which("az")
        if not az:
            raise StudyError("Azure CLI ('az') not found in parent environment to mint MD-1 token")
        proc = subprocess.run(
            [az, "account", "get-access-token", "--resource", "https://cognitiveservices.azure.com", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        raw = json.loads(proc.stdout)
        expires_on = int(raw.get("expires_on") or 0)
        if not expires_on and raw.get("expiresOn"):
            expires_on = int(datetime.fromisoformat(raw["expiresOn"]).timestamp())
        if not expires_on:
            expires_on = now_ts + 3300
        _CACHED_MD1_TOKEN = {"tenant": "", "token": raw["accessToken"], "expires_on": expires_on}
        return dict(_CACHED_MD1_TOKEN)


def write_lane_md1_token(home: Path, token_payload: dict) -> Path:
    tm_dir = home / "copilot" / "token-master"
    tm_dir.mkdir(parents=True, exist_ok=True)
    path = tm_dir / "md1-token.json"
    path.write_text(json.dumps(token_payload), encoding="utf-8")
    return path


def seed_prior_sessions(home: Path, template_db: Path, work: Path) -> None:
    dst = home / "copilot" / "session-store.db"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template_db, dst)
    con = sqlite3.connect(dst)
    try:
        for table in (
            "search_index",
            "turns",
            "checkpoints",
            "session_files",
            "session_refs",
            "assistant_usage_events",
            "sessions",
        ):
            try:
                con.execute(f"DELETE FROM {table}")
            except sqlite3.OperationalError:
                pass
        # Seed dates strictly in March 2026 so Turn 1's newly created session has the latest updated_at for --continue.
        # Note: 2026-03-09 is Monday, 2026-03-10 is Tuesday, 2026-03-11 is Wednesday, 2026-03-12 is Thursday.
        seeded = [
            (
                "11111111-1111-4111-8111-000000000001",
                "Monday rate-limiter burst cap decision",
                "2026-03-09T14:10:00.000Z",
                "2026-03-09T14:15:00.000Z",
                "Let's finalize the rate-limiter burst cap and response header in our Monday chat.",
                (
                    "Agreed in Monday's chat: set integer `burst_cap` to `48` and emit HTTP header "
                    "`X-TokenMaster-Burst`."
                ),
            ),
            (
                "22222222-2222-4222-8222-000000000002",
                "Tuesday fallback telemetry port sync",
                "2026-03-10T16:20:00.000Z",
                "2026-03-10T16:26:00.000Z",
                "For Tuesday's sync, which localhost fallback telemetry port and retry limit are we locking in?",
                (
                    "Locked in during Tuesday's sync: localhost fallback telemetry port `19420` and integer "
                    "retry limit `3`."
                ),
            ),
            (
                "33333333-3333-4333-8333-000000000003",
                "Canary rollout slice and Azure region",
                "2026-03-11T11:05:00.000Z",
                "2026-03-11T11:09:00.000Z",
                "What canary rollout percentage and Azure region did we select for stage one?",
                "We selected a `15` percent canary rollout slice in Azure region `eastus2`.",
            ),
            (
                "44444444-4444-4444-8444-000000000004",
                "Snapshot retention window and codec",
                "2026-03-12T09:30:00.000Z",
                "2026-03-12T09:35:00.000Z",
                "Let's confirm the snapshot retention window in days and compression codec.",
                "Confirmed: snapshot retention window is `14` days using compression codec `zstd`.",
            ),
        ]
        for sid, summary, created_at, updated_at, u_msg, a_msg in seeded:
            con.execute(
                "INSERT INTO sessions(id, cwd, repository, host_type, branch, summary, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (sid, str(work), "All-The-Vibes/TokenMasterX", "cli", "master", summary, created_at, updated_at),
            )
            con.execute(
                "INSERT INTO turns(session_id, turn_index, user_message, assistant_response, timestamp) "
                "VALUES (?, 0, ?, ?, ?)",
                (sid, u_msg, a_msg, updated_at),
            )
            con.execute(
                "INSERT INTO search_index(content, session_id, source_type, source_id) VALUES (?, ?, 'turn', ?)",
                (f"{u_msg}\n{a_msg}", sid, f"{sid}:turn:0"),
            )
        con.commit()
    finally:
        con.close()


def self_test(python_exe: Path) -> None:
    tasks = load_tasks()
    if len(tasks) != 16:
        raise StudyError(f"expected 16 workflows, got {len(tasks)}")
    buckets: dict[str, list[dict]] = {}
    for t in tasks:
        if len(t.get("turns") or []) != 3:
            raise StudyError(f"{t['id']} does not have 3 turns")
        if [x["mode"] for x in t["turns"]] != ["start", "resume", "continue"]:
            raise StudyError(f"{t['id']} turn modes must be ['start', 'resume', 'continue']")
        buckets.setdefault(t["bucket"], []).append(t)
    expected_buckets = {
        "A_stable_coding": 4,
        "B_escalation_and_intra_deixis": 4,
        "C_cross_session_recall": 4,
        "D_warm_cache_lookalikes": 4,
    }
    for b, cnt in expected_buckets.items():
        if len(buckets.get(b, [])) != cnt:
            raise StudyError(f"bucket {b} has {len(buckets.get(b, []))} workflows, expected {cnt}")

    # Verify all 4 edit workflows fail BEFORE reference_patch and pass AFTER git apply on clean HEAD.
    base_tmp = Path(r"C:\tm-lanes")
    base_tmp.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="r2_selftest_", dir=str(base_tmp)))
    try:
        archive = tmp / "head.tar"
        subprocess.run([GIT, "archive", "--format=tar", "-o", str(archive), "HEAD", "token-master-plugin"], cwd=REPO, check=True)
        work = tmp / "work"
        work.mkdir()
        subprocess.run(["tar", "-xf", str(archive), "-C", str(work)], check=True)
        subprocess.run([GIT, "init", "-q"], cwd=work, check=True)
        subprocess.run([GIT, "config", "core.autocrlf", "false"], cwd=work, check=True)
        ensure_git_exclude(work)
        subprocess.run([GIT, "add", "-A"], cwd=work, check=True)
        subprocess.run(
            [GIT, "-c", "user.name=tm", "-c", "user.email=tm@local", "commit", "-qm", "base"],
            cwd=work,
            check=True,
        )

        edit_count = 0
        for t in tasks:
            if t["kind"] != "edit":
                continue
            edit_count += 1
            subprocess.run([GIT, "checkout", "-q", "--", "."], cwd=work, check=True)
            subprocess.run([GIT, "clean", "-fdq"], cwd=work, check=True)
            code = "\n".join(t["check"])
            pre = subprocess.run([str(python_exe), "-c", code], cwd=work, capture_output=True, text=True)
            if pre.returncode == 0:
                raise StudyError(f"{t['id']} check unexpectedly passed BEFORE reference_patch")
            patch_file = tmp / f"{t['id']}.patch"
            patch_file.write_text(t["reference_patch"], encoding="utf-8", newline="\n")
            subprocess.run([GIT, "apply", "--check", str(patch_file)], cwd=work, check=True)
            subprocess.run([GIT, "apply", str(patch_file)], cwd=work, check=True)
            dirty = git_status_lines(work)
            touched = {line[3:].strip().replace("\\", "/") for line in dirty if line.strip()}
            if not touched or not touched.issubset(set(t["allowed_paths"])):
                raise StudyError(f"{t['id']} reference_patch touched {touched}, allowed {t['allowed_paths']}")
            post = subprocess.run([str(python_exe), "-c", code], cwd=work, capture_output=True, text=True)
            if post.returncode != 0:
                raise StudyError(f"{t['id']} check failed AFTER reference_patch:\n{post.stdout}\n{post.stderr}")
        if edit_count != 4:
            raise StudyError(f"expected 4 edit workflows, verified {edit_count}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(
        f"self-test passed: 16 workflows x 3 turns (4xA, 4xB, 4xC, 4xD), "
        f"4 edit patches verified, weights sha256={local_router_weights.WEIGHTS_SHA256[:16]}..."
    )


def install_tokenmaster(work: Path, home: Path, python_exe: Path, tiktoken_file: Path) -> dict:
    env = lane_env(home, python_exe=python_exe, tiktoken_file=tiktoken_file)
    p1 = subprocess.run(
        [str(python_exe), "-B", str(SKILL / "setup.py"), str(work), "--host", "copilot", "--python", str(python_exe)],
        cwd=SKILL,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
        check=True,
    )
    p2 = subprocess.run(
        [
            str(python_exe),
            "-B",
            str(SKILL / "brainspace_setup.py"),
            "--host",
            "copilot",
            "--python",
            str(python_exe),
            "--tokenizer-file",
            str(tiktoken_file),
        ],
        cwd=SKILL,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=True,
    )
    installed_bridge = home / "copilot" / "token-master" / "brainspace_copilot_bridge.py"
    installed_tok = home / "copilot" / "token-master" / "tokenomics.py"
    installed_lr = home / "copilot" / "token-master" / "brainspace" / "local_router.py"
    installed_lrw = home / "copilot" / "token-master" / "brainspace" / "local_router_weights.py"
    if sha256(installed_bridge) != sha256(SKILL / "brainspace_copilot_bridge.py"):
        raise StudyError("installed brainspace_copilot_bridge.py hash does not match working-tree SKILL")
    if sha256(installed_tok) != sha256(SKILL / "tokenomics.py"):
        raise StudyError("installed tokenomics.py hash does not match working-tree SKILL")
    if sha256(installed_lr) != sha256(SKILL / "brainspace" / "local_router.py"):
        raise StudyError("installed local_router.py hash does not match working-tree SKILL")
    if sha256(installed_lrw) != sha256(SKILL / "brainspace" / "local_router_weights.py"):
        raise StudyError("installed local_router_weights.py hash does not match working-tree SKILL")

    subprocess.run([GIT, "checkout", "-q", "--", ".gitignore"], cwd=work, check=True)
    shutil.rmtree(work / "graphify-out", ignore_errors=True)
    ensure_git_exclude(work)
    if not git_clean(work):
        raise StudyError(f"TokenMaster install dirtied git worktree at {work}: {git_status_lines(work)}")
    return {
        "setup_tail": (p1.stdout + p1.stderr).splitlines()[-5:],
        "brainspace_setup_tail": (p2.stdout + p2.stderr).splitlines()[-5:],
        "bridge_sha256": sha256(installed_bridge),
        "tokenomics_sha256": sha256(installed_tok),
        "local_router_sha256": sha256(installed_lr),
        "local_router_weights_sha256": sha256(installed_lrw),
    }


def prepare(lanes_dir: Path, python_exe: Path, tiktoken_file: Path, md1_endpoint: str) -> None:
    _resolve_gh_token()
    if sha256(tiktoken_file) != "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7":
        raise StudyError(f"tiktoken file hash mismatch: {tiktoken_file}")
    if not md1_endpoint:
        raise StudyError("MD-1 endpoint is required for tm_md1_v1 baseline arm")

    # Verify MD-1 live endpoint works for tm_md1_v1 before freezing setup.
    tok = get_fresh_md1_token()
    tmp_home = Path(tempfile.mkdtemp(prefix="r2_md1_prep_", dir=r"C:\tm-lanes"))
    prev_ep = os.environ.get("TOKENMASTER_MD1_ENDPOINT")
    prev_ch = os.environ.get("COPILOT_HOME")
    try:
        write_lane_md1_token(tmp_home, tok)
        os.environ["COPILOT_HOME"] = str(tmp_home / "copilot")
        os.environ["TOKENMASTER_MD1_ENDPOINT"] = md1_endpoint
        scores = bridge.md1_scores("spawn a subagent to check the diff")
        if not scores or scores.get("agents", 0.0) < 0.5:
            raise StudyError(f"MD-1 endpoint sanity probe failed: {scores}")
    finally:
        if prev_ep is None:
            os.environ.pop("TOKENMASTER_MD1_ENDPOINT", None)
        else:
            os.environ["TOKENMASTER_MD1_ENDPOINT"] = prev_ep
        if prev_ch is None:
            os.environ.pop("COPILOT_HOME", None)
        else:
            os.environ["COPILOT_HOME"] = prev_ch
        shutil.rmtree(tmp_home, ignore_errors=True)

    # Freeze PROTOCOL.sha256 BEFORE preparing lanes or running any workflow.
    proto_digest = sha256(PROTOCOL)
    PROTOCOL_HASH.write_text(f"{proto_digest}  PROTOCOL.md\n", encoding="utf-8", newline="\n")

    if lanes_dir.exists():
        shutil.rmtree(lanes_dir, onexc=lambda fn, p, _: (os.chmod(p, stat.S_IWRITE), fn(p)))
    lanes_dir.mkdir(parents=True)

    head_sha = subprocess.run([GIT, "rev-parse", "HEAD"], cwd=REPO, check=True, capture_output=True, text=True).stdout.strip()
    archive = lanes_dir / "head.tar"
    subprocess.run([GIT, "archive", "--format=tar", "-o", str(archive), head_sha], cwd=REPO, check=True)

    stock_tpl = lanes_dir / "templates" / "stock"
    (stock_tpl / "work").mkdir(parents=True)
    (stock_tpl / "home").mkdir(parents=True)
    subprocess.run(["tar", "-xf", str(archive), "-C", str(stock_tpl / "work")], check=True)
    archive.unlink()
    subprocess.run([GIT, "init", "-q"], cwd=stock_tpl / "work", check=True)
    subprocess.run([GIT, "config", "core.autocrlf", "false"], cwd=stock_tpl / "work", check=True)
    ensure_git_exclude(stock_tpl / "work")
    subprocess.run([GIT, "add", "-A"], cwd=stock_tpl / "work", check=True)
    subprocess.run(
        [GIT, "-c", "user.name=study", "-c", "user.email=study@local", "commit", "-qm", "base"],
        cwd=stock_tpl / "work",
        check=True,
    )

    # Materialize a clean 1.0.112 session-store.db schema for Bucket C seeding, and record exact CLI version.
    schema_home = lanes_dir / "_schema_probe_home"
    probe_env = lane_env(schema_home, python_exe=python_exe, tiktoken_file=tiktoken_file)
    ver_out = subprocess.run([COPILOT, "--version"], env=probe_env, check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(
        [
            COPILOT,
            "-p",
            "Reply with ONLY the word READY.",
            "--model",
            MODEL,
            "--reasoning-effort",
            REASONING,
            "--disable-builtin-mcps",
            "--allow-all-tools",
            "--no-ask-user",
            "--secret-env-vars=GH_TOKEN,GITHUB_TOKEN,COPILOT_GITHUB_TOKEN",
            "--output-format",
            "json",
        ],
        cwd=stock_tpl / "work",
        env=probe_env,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    src_db = schema_home / "copilot" / "session-store.db"
    tpl_db = lanes_dir / "session-store-template.db"
    src_con = sqlite3.connect(src_db)
    con = sqlite3.connect(tpl_db)
    src_con.backup(con)
    src_con.close()
    for table in (
        "search_index",
        "turns",
        "checkpoints",
        "session_files",
        "session_refs",
        "assistant_usage_events",
        "sessions",
    ):
        try:
            con.execute(f"DELETE FROM {table}")
        except sqlite3.OperationalError:
            pass
    con.commit()
    con.execute("VACUUM")
    con.close()
    shutil.rmtree(schema_home, ignore_errors=True)

    lane_env(stock_tpl / "home", python_exe=python_exe, tiktoken_file=tiktoken_file)
    clear_lane_history(stock_tpl / "home")

    # Install TokenMaster once into tm_base, then clone identically to tm_locked, tm_md1_v1, and tm_r2.
    tm_base = lanes_dir / "templates" / "tm_base"
    mirror(stock_tpl / "work", tm_base / "work")
    mirror(stock_tpl / "home", tm_base / "home")
    tm_install = install_tokenmaster(tm_base / "work", tm_base / "home", python_exe, tiktoken_file)
    clear_lane_history(tm_base / "home")

    for arm in TM_ARMS:
        tpl = lanes_dir / "templates" / arm
        mirror(tm_base / "work", tpl / "work")
        mirror(tm_base / "home", tpl / "home")
        ensure_git_exclude(tpl / "work")
    shutil.rmtree(tm_base, ignore_errors=True)

    for arm in ARMS:
        lane = lanes_dir / "lanes" / LANE_NAMES[arm]
        mirror(lanes_dir / "templates" / arm / "work", lane / "work")
        mirror(lanes_dir / "templates" / arm / "home", lane / "home")
        ensure_git_exclude(lane / "work")

    setup = {
        "prepared_at": now_iso(),
        "repo_commit": head_sha,
        "protocol_sha256": proto_digest,
        "tasks_sha256": sha256(TASKS_FILE),
        "weights_sha256": local_router_weights.WEIGHTS_SHA256,
        "copilot_cli_version": ver_out,
        "copilot_exe": COPILOT,
        "python_exe": str(python_exe),
        "python_version": subprocess.run(
            [str(python_exe), "--version"], check=True, capture_output=True, text=True
        ).stdout.strip(),
        "tiktoken_sha256": sha256(tiktoken_file),
        "model": MODEL,
        "reasoning_effort": REASONING,
        "md1_endpoint_for_tm_md1_v1": md1_endpoint,
        "offline_arms": list(OFFLINE_TM_ARMS),
        "arms": list(ARMS),
        "arm_flags": {k: list(v) for k, v in ARM_FLAGS.items()},
        "lane_names": LANE_NAMES,
        "lanes_dir": str(lanes_dir),
        "tm_install": tm_install,
    }
    SETUP_FILE.write_text(json.dumps(setup, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Prepared 4 isolated lanes at {lanes_dir} (CLI: {ver_out}, base commit: {head_sha[:7]}).")


def reset_lane(lanes_dir: Path, arm: str) -> tuple[Path, Path]:
    tpl = lanes_dir / "templates" / arm
    lane = lanes_dir / "lanes" / LANE_NAMES[arm]
    mirror(tpl / "work", lane / "work")
    mirror(tpl / "home" / "copilot", lane / "home" / "copilot")
    ensure_git_exclude(lane / "work")
    clear_lane_history(lane / "home")
    if not git_clean(lane / "work"):
        raise StudyError(f"lane {arm} dirty after reset: {git_status_lines(lane / 'work')}")
    return lane / "work", lane / "home"


def parse_stdout_telemetry(stdout_text: str) -> dict:
    events = []
    for line in stdout_text.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                events.append(obj)
        except ValueError:
            continue

    tool_starts = []
    llm_tool_requests = []
    cache_state = None
    final_answer = ""
    last_answer = ""
    copilot_version = None
    session_errors = []
    for ev in events:
        etype = ev.get("type")
        data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
        if etype in ("session.start", "session.resume"):
            copilot_version = data.get("copilotVersion") or copilot_version
        elif etype == "tool.execution_start":
            tool_starts.append(
                {
                    "name": data.get("toolName"),
                    "arguments": data.get("arguments") if isinstance(data.get("arguments"), dict) else {},
                }
            )
        elif etype == "assistant.message":
            if d_model := data.get("model"):
                for tr in data.get("toolRequests") or []:
                    if isinstance(tr, dict) and tr.get("name"):
                        llm_tool_requests.append(
                            {
                                "name": tr["name"],
                                "arguments": tr.get("arguments") if isinstance(tr.get("arguments"), dict) else {},
                                "model": d_model,
                            }
                        )
            if isinstance(data.get("content"), str) and data["content"].strip():
                last_answer = data["content"]
                if data.get("phase") == "final_answer":
                    final_answer = data["content"]
        elif etype == "session.error":
            session_errors.append(data)
        elif etype == "session.usage_checkpoint" and cache_state is None:
            pcs = data.get("promptCacheBreakState") or []
            if pcs and isinstance(pcs[0], dict):
                models = pcs[0].get("models") or {}
                m_info = models.get(MODEL) or (next(iter(models.values())) if models else None)
                if isinstance(m_info, dict):
                    raw_segs = m_info.get("system_segments") or []
                    if isinstance(raw_segs, list):
                        segs = {
                            s["segment"]: s.get("tokens", 0)
                            for s in raw_segs
                            if isinstance(s, dict) and "segment" in s
                        }
                    elif isinstance(raw_segs, dict):
                        segs = raw_segs
                    else:
                        segs = {}
                    raw_tools = m_info.get("tools") or []
                    tool_names = [
                        (t.get("name") if isinstance(t, dict) else str(t))
                        for t in raw_tools
                        if t
                    ]
                    cache_state = {
                        "tool_count": m_info.get("tool_count"),
                        "tool_tokens": m_info.get("tool_tokens"),
                        "tools": tool_names,
                        "tool_instructions_tokens": segs.get("tool_instructions"),
                        "system_total_tokens": sum(v for v in segs.values() if isinstance(v, (int, float))),
                        "system_segments": segs,
                    }
    return {
        "copilot_version": copilot_version,
        "final_answer": final_answer or last_answer,
        "tool_starts": tool_starts,
        "llm_tool_requests": llm_tool_requests,
        "cache_state": cache_state or {},
        "session_errors": session_errors,
    }


def harvest_new_store_calls(
    home: Path,
    seen_row_ids: set[int],
    *,
    turn_num: int,
    first_main_of_session_seen: list[bool],
    call_seq_start: int,
) -> dict:
    db = home / "copilot" / "session-store.db"
    if not db.is_file():
        return {"session_ids": [], "calls": []}
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT id, session_id, agent_id, model, api_endpoint, input_tokens, output_tokens, "
            "cache_read_tokens, cache_write_tokens, total_nano_aiu, token_details_json, created_at "
            "FROM assistant_usage_events ORDER BY created_at, id"
        ).fetchall()
    finally:
        con.close()

    calls = []
    sids = []
    for r in rows:
        rid = int(r["id"])
        if rid in seen_row_ids:
            continue
        seen_row_ids.add(rid)
        sid = r["session_id"]
        if sid and sid not in sids:
            sids.append(sid)
        raw_details = r["token_details_json"] or "[]"
        details = json.loads(raw_details)
        inp = int(r["input_tokens"] or 0)
        out = int(r["output_tokens"] or 0)
        cread = int(r["cache_read_tokens"] or 0)
        cwrite = int(r["cache_write_tokens"] or 0)
        billed = int(r["total_nano_aiu"] or 0)
        recharged = recharge_row(inp, out, cread, cwrite, raw_details)
        is_sub = bool(r["agent_id"])
        if turn_num == 1 and (not is_sub) and (not first_main_of_session_seen[0]):
            first_main_of_session_seen[0] = True
            prices = tokenomics.prices_of(raw_details)
            cold = billed + cread * (prices.get("cache_write", 0) - prices.get("cache_read", 0))
        else:
            cold = billed
        calls.append(
            {
                "row_id": rid,
                "call_index": call_seq_start + len(calls),
                "turn": turn_num,
                "session_id": sid,
                "agent_id": r["agent_id"],
                "is_subagent": is_sub,
                "model": r["model"],
                "api_endpoint": r["api_endpoint"],
                "input_tokens": inp,
                "output_tokens": out,
                "cache_read_tokens": cread,
                "cache_write_tokens": cwrite,
                "total_nano_aiu": billed,
                "recharged_nano_aiu": round(recharged),
                "cold_nano_aiu": round(cold),
                "token_details": details,
                "created_at": r["created_at"],
            }
        )
    return {"session_ids": sids, "calls": calls}


def harvest_latest_launch(home: Path) -> dict | None:
    p = home / "copilot" / "token-master" / "launches.jsonl"
    if not p.is_file():
        return None
    starts = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("event") == "start":
            starts.append(rec)
    return starts[-1] if starts else None


def detect_capability_behavior(task: dict, all_tool_starts: list[dict], escalated_turn_tool_starts: list[dict]) -> dict:
    all_names = [t["name"] for t in all_tool_starts if t.get("name")]
    esc_names = [t["name"] for t in escalated_turn_tool_starts if t.get("name")]
    target_tools = set(task.get("target_tools") or [])

    if task["id"] == "S06":
        async_ps = any(
            t["name"] == "powershell" and (t.get("arguments") or {}).get("mode") == "async"
            for t in escalated_turn_tool_starts
        )
        target_used = async_ps and any(n in ("read_powershell", "stop_powershell") for n in esc_names)
    else:
        async_ps = any(
            t["name"] == "powershell" and (t.get("arguments") or {}).get("mode") == "async"
            for t in all_tool_starts
        )
        target_used = any(n in target_tools for n in esc_names) if target_tools else False

    shell_workaround = False
    if task["bucket"] in ("B_escalation_and_intra_deixis", "C_cross_session_recall") and not target_used:
        if any(n == "powershell" for n in esc_names) or (task["id"] == "S05" and "task" not in esc_names):
            shell_workaround = True

    return {
        "called_tools": all_names,
        "escalated_turn_called_tools": esc_names,
        "target_tool_used": target_used,
        "async_powershell_used": async_ps,
        "shell_workaround": shell_workaround,
    }


def check_ports_closed(stdout_texts: list[str]) -> tuple[bool, list[int]]:
    combined = "\n".join(stdout_texts)
    ports = {int(m.group(1)) for m in re.finditer(r"READY:(\d{2,5})", combined)}
    still_open = []
    for port in sorted(ports):
        if port <= 0 or port > 65535:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                still_open.append(port)
    return (len(still_open) == 0), still_open


def grade_workflow(
    task: dict,
    work: Path,
    python_exe: Path,
    final_answer: str,
    stdout_texts: list[str],
    session_continuity_ok: bool,
) -> tuple[bool, str, str]:
    diff = git_diff(work)
    if not session_continuity_ok:
        return False, diff, "session_continuity_ok=False"

    if task["kind"] == "investigate":
        clean = git_clean(work)
        got = extract_json(final_answer)
        ok = clean and json_matches(got, task["expected"], task.get("unordered_keys", ()))
        note_obj = {"git_clean": clean, "parsed": got, "expected": task["expected"]}
        if task.get("check_ports_closed"):
            ports_closed, open_ports = check_ports_closed(stdout_texts)
            if not ports_closed:
                ok = False
            note_obj["open_ports"] = open_ports
        return ok, diff, json.dumps(note_obj, indent=2)

    dirty = git_status_lines(work)
    untracked = [ln for ln in dirty if ln.startswith("??")]
    touched = {line[3:].strip().replace("\\", "/") for line in dirty if line.strip() and not line.startswith("??")}
    allowed_ok = (not untracked) and bool(touched) and touched.issubset(set(task["allowed_paths"]))
    proc = subprocess.run(
        [str(python_exe), "-c", "\n".join(task["check"])],
        cwd=work,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        timeout=120,
    )
    ok = allowed_ok and proc.returncode == 0
    note = (
        f"touched={sorted(touched)}\nuntracked={untracked}\nallowed={task['allowed_paths']}\n"
        f"check_exit={proc.returncode}\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    return ok, diff, note


def evaluate_tokenomics_on_home(copilot_home: Path, session_id: str | None) -> dict:
    empty = {
        "tm_calls": 0,
        "calls": 0,
        "usd": 0.0,
        "tm_usd": 0.0,
        "saved_usd": 0.0,
        "lean_usd": 0.0,
        "first_usd": 0.0,
        "brief_usd": 0.0,
        "saved_tokens": 0,
        "saved_tokens_pct": None,
        "saved_usd_pct": None,
    }
    store = copilot_home / "session-store.db"
    if not store.is_file():
        return empty
    ns = argparse.Namespace(
        report="session",
        since=None,
        until=None,
        project=None,
        only=None,
        breakdown=False,
        order="asc",
        json=True,
        compact=False,
        full=False,
        ascii=False,
        no_color=True,
        copilot_home=str(copilot_home),
    )
    report = tokenomics.as_json("session", tokenomics.build(ns))
    row = None
    if session_id:
        for r in report.get("rows") or []:
            if r.get("session") == session_id:
                row = r
                break
    if row is None and report.get("rows"):
        row = report["rows"][-1]
    if not row:
        return empty
    return {
        "tm_calls": int(row.get("tm_calls") or 0),
        "calls": int(row.get("calls") or 0),
        "usd": float(row.get("usd") or 0.0),
        "tm_usd": float(row.get("tm_usd") or 0.0),
        "saved_usd": float(row.get("saved_usd") or 0.0),
        "lean_usd": float(row.get("lean_usd") or 0.0),
        "first_usd": float(row.get("first_usd") or 0.0),
        "brief_usd": float(row.get("brief_usd") or 0.0),
        "saved_tokens": int(row.get("saved_tokens") or 0),
        "saved_tokens_pct": row.get("saved_tokens_pct"),
        "saved_usd_pct": row.get("saved_usd_pct"),
    }


def run_one_workflow_arm(
    lanes_dir: Path,
    arm: str,
    task: dict,
    *,
    python_exe: Path,
    tiktoken_file: Path,
    md1_endpoint: str,
    budget: UsdBudget,
) -> dict:
    budget.check()
    work, home = reset_lane(lanes_dir, arm)
    if task.get("fixture") == "seeded_session_history":
        seed_prior_sessions(home, lanes_dir / "session-store-template.db", work)

    launches_path = home / "copilot" / "token-master" / "launches.jsonl"
    md1_token_path = home / "copilot" / "token-master" / "md1-token.json"
    out_dir = SESSIONS_DIR / task["id"] / arm
    out_dir.mkdir(parents=True, exist_ok=True)

    seen_row_ids: set[int] = set()
    first_main_of_session_seen = [False]
    turn_records: list[dict] = []
    all_calls: list[dict] = []
    all_tool_starts: list[dict] = []
    stdout_texts: list[str] = []
    active_sid: str | None = None
    prev_excluded: list[str] | None = None
    aborted = False

    env = lane_env(
        home,
        python_exe=python_exe,
        tiktoken_file=tiktoken_file,
        md1_endpoint=(md1_endpoint if arm == "tm_md1_v1" else None),
    )
    if arm in OFFLINE_TM_ARMS:
        if "TOKENMASTER_MD1_ENDPOINT" in env:
            raise StudyError(f"{arm} must run offline without TOKENMASTER_MD1_ENDPOINT")
        if md1_token_path.exists():
            raise StudyError(f"{arm} must not have md1-token.json")

    try:
        for turn_spec in task["turns"]:
            turn_num = int(turn_spec["turn"])
            mode = turn_spec["mode"]

            if arm == "tm_md1_v1":
                write_lane_md1_token(home, get_fresh_md1_token())

            if mode == "start":
                resume_args: list[str] = []
            elif mode == "resume":
                if not active_sid:
                    aborted = True
                    break
                resume_args = ["--resume", active_sid]
            elif mode == "continue":
                if not active_sid:
                    aborted = True
                    break
                resume_args = ["--continue"]
            else:
                raise StudyError(f"unknown turn mode: {mode}")

            cli_flags = [
                *resume_args,
                "-p",
                turn_spec["prompt"],
                "--model",
                MODEL,
                "--reasoning-effort",
                REASONING,
                "--disable-builtin-mcps",
                "--allow-all-tools",
                "--no-ask-user",
                "--secret-env-vars=GH_TOKEN,GITHUB_TOKEN,COPILOT_GITHUB_TOKEN",
                "--output-format",
                "json",
            ]
            if arm == "stock":
                cmd = [COPILOT, *cli_flags]
            else:
                bridge_py = home / "copilot" / "token-master" / "brainspace_copilot_bridge.py"
                cmd = [str(python_exe), "-B", str(bridge_py), *ARM_FLAGS[arm], "--", COPILOT, *cli_flags]

            t0 = time.perf_counter()
            timed_out = False
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=work,
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    stdin=subprocess.DEVNULL,
                    timeout=360,
                )
                exit_code = proc.returncode
                stdout_text = proc.stdout
                stderr_text = proc.stderr
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                exit_code = -9
                stdout_text = (
                    exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", "replace")
                )
                stderr_text = (
                    exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", "replace")
                )
            elapsed = time.perf_counter() - t0
            stdout_texts.append(stdout_text)

            (out_dir / f"turn{turn_num}.stdout.jsonl").write_text(stdout_text, encoding="utf-8", newline="\n")
            if stderr_text.strip():
                (out_dir / f"turn{turn_num}.stderr.txt").write_text(stderr_text, encoding="utf-8", newline="\n")

            telemetry = parse_stdout_telemetry(stdout_text)
            store_turn = harvest_new_store_calls(
                home,
                seen_row_ids,
                turn_num=turn_num,
                first_main_of_session_seen=first_main_of_session_seen,
                call_seq_start=len(all_calls),
            )
            turn_calls = store_turn["calls"]
            all_calls.extend(turn_calls)
            all_tool_starts.extend(telemetry["tool_starts"])

            if turn_num == 1 and store_turn["session_ids"]:
                active_sid = store_turn["session_ids"][0]

            launch = harvest_latest_launch(home) if arm in TM_ARMS else None
            excluded = list(launch.get("excluded") or []) if launch else []
            router_name = launch.get("router") if launch else None
            router_ms = launch.get("router_ms") if launch else None
            if arm in OFFLINE_TM_ARMS and router_name != "r2":
                raise StudyError(f"{arm} T{turn_num} expected router='r2', got {router_name!r}")
            if arm == "tm_md1_v1" and router_name != "md1":
                raise StudyError(f"{arm} T{turn_num} expected router='md1', got {router_name!r}")

            kept_groups = sorted(bridge.CAPABILITY_GROUPS) if arm == "stock" else kept_groups_from_excluded(excluded)
            kept_aux_tools = (
                list(bridge.LEAN_EXCLUDED_TOOLS)
                if arm == "stock"
                else [t for t in bridge.LEAN_EXCLUDED_TOOLS if t not in set(excluded)]
            )
            needed = set(turn_spec.get("needed_groups") or [])
            needed_recalled = needed.issubset(set(kept_groups))
            false_keep_tools = [
                t
                for g in kept_groups
                if g not in needed
                for t in bridge.CAPABILITY_GROUPS[g][0]
                if t in set(kept_aux_tools)
            ]
            tool_list_changed = (prev_excluded is not None) and (excluded != prev_excluded)
            unneeded_mutation = bool(tool_list_changed and not needed)
            prev_excluded = list(excluded)

            main_calls = [c for c in turn_calls if not c["is_subagent"]]
            first_main = main_calls[0] if main_calls else None
            fm_cr = first_main["cache_read_tokens"] if first_main else 0
            fm_cw = first_main["cache_write_tokens"] if first_main else 0
            fm_hit = (fm_cr / (fm_cr + fm_cw)) if (fm_cr + fm_cw) > 0 else 0.0

            cs = telemetry["cache_state"]
            tt_tok = cs.get("tool_tokens")
            ti_tok = cs.get("tool_instructions_tokens")
            schema_plus_instr = (
                (tt_tok + ti_tok) if isinstance(tt_tok, int) and isinstance(ti_tok, int) else None
            )

            turn_billed = sum(c["total_nano_aiu"] for c in turn_calls)
            turn_cold = sum(c["cold_nano_aiu"] for c in turn_calls)
            turn_inp = sum(c["input_tokens"] for c in turn_calls)
            turn_out = sum(c["output_tokens"] for c in turn_calls)
            turn_cr = sum(c["cache_read_tokens"] for c in turn_calls)
            turn_cw = sum(c["cache_write_tokens"] for c in turn_calls)

            turn_records.append(
                {
                    "turn": turn_num,
                    "mode": mode,
                    "exit_code": exit_code,
                    "timed_out": timed_out,
                    "seconds": round(elapsed, 3),
                    "copilot_version": telemetry["copilot_version"],
                    "session_ids": store_turn["session_ids"],
                    "launch_recorded": launch is not None,
                    "launch_session_field": launch.get("session") if launch else None,
                    "router": router_name,
                    "router_ms": router_ms,
                    "excluded_tools": excluded,
                    "kept_groups": kept_groups,
                    "needed_groups": sorted(needed),
                    "needed_recalled": needed_recalled,
                    "false_keep_tools": false_keep_tools,
                    "false_keep_tool_count": len(false_keep_tools),
                    "tool_list_changed": tool_list_changed,
                    "unneeded_mutation": unneeded_mutation,
                    "tool_count": cs.get("tool_count"),
                    "tool_tokens": tt_tok,
                    "tool_instructions_tokens": ti_tok,
                    "schema_plus_instr_tokens": schema_plus_instr,
                    "call_count": len(turn_calls),
                    "main_call_count": len(main_calls),
                    "subagent_calls": sum(1 for c in turn_calls if c["is_subagent"]),
                    "first_main_input_tokens": first_main["input_tokens"] if first_main else 0,
                    "first_main_cache_read_tokens": fm_cr,
                    "first_main_cache_write_tokens": fm_cw,
                    "first_main_cache_hit_rate": round(fm_hit, 6),
                    "first_main_billed_usd": round(
                        (first_main["total_nano_aiu"] if first_main else 0) / NANO_PER_USD, 6
                    ),
                    "input_tokens": turn_inp,
                    "output_tokens": turn_out,
                    "raw_tokens": turn_inp + turn_out,
                    "cache_read_tokens": turn_cr,
                    "cache_write_tokens": turn_cw,
                    "billed_nano": turn_billed,
                    "cold_nano": turn_cold,
                    "billed_usd": round(turn_billed / NANO_PER_USD, 6),
                    "cold_usd": round(turn_cold / NANO_PER_USD, 6),
                    "called_tools": [t["name"] for t in telemetry["tool_starts"] if t.get("name")],
                    "tool_starts": telemetry["tool_starts"],
                    "llm_tool_requests": telemetry["llm_tool_requests"],
                    "final_answer": telemetry["final_answer"],
                    "session_errors": telemetry["session_errors"],
                }
            )

            if exit_code != 0 or timed_out:
                aborted = True
                break
    finally:
        md1_token_path.unlink(missing_ok=True)

    if launches_path.is_file():
        shutil.copy2(launches_path, out_dir / "launches.jsonl")

    all_sids = []
    for c in all_calls:
        if c["session_id"] and c["session_id"] not in all_sids:
            all_sids.append(c["session_id"])

    session_continuity_ok = (
        not aborted
        and len(turn_records) == 3
        and len(all_sids) == 1
        and all(tr["call_count"] >= 1 and tr["session_ids"] == [all_sids[0]] for tr in turn_records)
    )
    final_ans = turn_records[-1]["final_answer"] if turn_records else ""
    passed, diff, check_note = (
        grade_workflow(task, work, python_exe, final_ans, stdout_texts, session_continuity_ok)
        if not aborted and len(turn_records) == 3
        else (False, git_diff(work), f"aborted={aborted} turns_completed={len(turn_records)}")
    )

    if diff:
        (out_dir / "git.diff").write_text(diff, encoding="utf-8", newline="\n")
    (out_dir / "check.txt").write_text(check_note, encoding="utf-8", newline="\n")

    esc_turn = task.get("escalated_turn")
    all_llm_reqs = [req for tr in turn_records for req in (tr.get("llm_tool_requests") or tr["tool_starts"])]
    esc_tool_starts = (
        (turn_records[esc_turn - 1].get("llm_tool_requests") or turn_records[esc_turn - 1]["tool_starts"])
        if isinstance(esc_turn, int) and 1 <= esc_turn <= len(turn_records)
        else all_llm_reqs
    )
    behavior = detect_capability_behavior(task, all_llm_reqs, esc_tool_starts)

    tok_audit = evaluate_tokenomics_on_home(home / "copilot", all_sids[0] if all_sids else None)

    billed_nano = sum(c["total_nano_aiu"] for c in all_calls)
    cold_nano = sum(c["cold_nano_aiu"] for c in all_calls)
    recharged_nano = sum(c["recharged_nano_aiu"] for c in all_calls)
    turn23_billed_nano = sum(tr["billed_nano"] for tr in turn_records if tr["turn"] in (2, 3))
    inp_tok = sum(c["input_tokens"] for c in all_calls)
    out_tok = sum(c["output_tokens"] for c in all_calls)
    cr_tok = sum(c["cache_read_tokens"] for c in all_calls)
    cw_tok = sum(c["cache_write_tokens"] for c in all_calls)
    uncached_inp = inp_tok - cr_tok

    resume_hits = [tr["first_main_cache_hit_rate"] for tr in turn_records if tr["turn"] in (2, 3)]
    mean_resume_hit = sum(resume_hits) / len(resume_hits) if resume_hits else 0.0
    router_latencies = [float(tr["router_ms"]) for tr in turn_records if tr.get("router_ms") is not None]
    mean_router_ms = round(sum(router_latencies) / len(router_latencies), 3) if router_latencies else None

    spent_usd = budget.add(billed_nano)

    record = {
        "recorded_at": now_iso(),
        "task_id": task["id"],
        "bucket": task["bucket"],
        "kind": task["kind"],
        "arm": arm,
        "lane": LANE_NAMES[arm],
        "passed": passed,
        "aborted": aborted,
        "session_continuity_ok": session_continuity_ok,
        "session_id": all_sids[0] if len(all_sids) == 1 else None,
        "session_ids": all_sids,
        "turns_completed": len(turn_records),
        "seconds": round(sum(tr["seconds"] for tr in turn_records), 3),
        "call_count": len(all_calls),
        "main_call_count": sum(1 for c in all_calls if not c["is_subagent"]),
        "subagent_calls": sum(1 for c in all_calls if c["is_subagent"]),
        "input_tokens": inp_tok,
        "uncached_input_tokens": uncached_inp,
        "output_tokens": out_tok,
        "raw_tokens": inp_tok + out_tok,
        "cache_read_tokens": cr_tok,
        "cache_write_tokens": cw_tok,
        "billed_nano": billed_nano,
        "recharged_nano": recharged_nano,
        "cold_nano": cold_nano,
        "turn23_billed_nano": turn23_billed_nano,
        "billed_usd": round(billed_nano / NANO_PER_USD, 6),
        "cold_usd": round(cold_nano / NANO_PER_USD, 6),
        "turn23_billed_usd": round(turn23_billed_nano / NANO_PER_USD, 6),
        "mean_resume_first_call_cache_hit_rate": round(mean_resume_hit, 6),
        "resume_tool_mutations": sum(1 for tr in turn_records if tr["turn"] > 1 and tr["tool_list_changed"]),
        "unneeded_tool_mutations": sum(1 for tr in turn_records if tr["turn"] > 1 and tr["unneeded_mutation"]),
        "all_turns_needed_recalled": all(tr["needed_recalled"] for tr in turn_records) and len(turn_records) == 3,
        "escalated_turn_recalled": (
            turn_records[esc_turn - 1]["needed_recalled"]
            if isinstance(esc_turn, int) and 1 <= esc_turn <= len(turn_records)
            else True
        ),
        "router_latencies_ms": router_latencies,
        "mean_router_ms": mean_router_ms,
        "behavior": behavior,
        "tokenomics": tok_audit,
        "turns": turn_records,
        "calls": all_calls,
        "cumulative_spent_usd": round(spent_usd, 6),
    }
    (out_dir / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    return record


def run_benchmark(
    lanes_dir: Path,
    python_exe: Path,
    tiktoken_file: Path,
    md1_endpoint: str,
    *,
    only_tasks: set[str] | None,
    budget_usd: float,
    fresh: bool,
) -> None:
    if not PROTOCOL_HASH.is_file():
        raise StudyError("PROTOCOL.sha256 missing; run prepare first")
    expected_proto = PROTOCOL_HASH.read_text(encoding="utf-8").split()[0]
    if sha256(PROTOCOL) != expected_proto:
        raise StudyError("PROTOCOL.md changed after prepare; aborting pre-registered run")

    tasks = load_tasks()
    if only_tasks:
        tasks = [t for t in tasks if t["id"] in only_tasks]
        if not tasks:
            raise StudyError(f"no tasks matched {sorted(only_tasks)}")

    if fresh and RUNS_FILE.is_file() and not only_tasks:
        RUNS_FILE.unlink()

    done_keys: set[tuple[str, str]] = set()
    initial_nano = 0
    if RUNS_FILE.is_file():
        for ln in RUNS_FILE.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln)
                done_keys.add((r["task_id"], r["arm"]))
                initial_nano += int(r.get("billed_nano") or 0)

    budget = UsdBudget(budget_usd, initial_nano=initial_nano)
    write_lock = threading.Lock()
    rng = random.Random(20261120)

    for idx, task in enumerate(tasks, 1):
        pending_arms = [a for a in ARMS if (task["id"], a) not in done_keys]
        if not pending_arms:
            print(f"[{idx:02d}/{len(tasks):02d}] {task['id']} already complete across all 4 arms; skipping.", flush=True)
            continue
        arm_order = list(pending_arms)
        rng.shuffle(arm_order)
        print(
            f"[{idx:02d}/{len(tasks):02d}] Running {task['id']} ({task['bucket']}, {task['kind']}) "
            f"arms={arm_order} ...",
            flush=True,
        )
        t_batch = time.perf_counter()
        with ThreadPoolExecutor(max_workers=len(arm_order)) as pool:
            futs = {
                arm: pool.submit(
                    run_one_workflow_arm,
                    lanes_dir,
                    arm,
                    task,
                    python_exe=python_exe,
                    tiktoken_file=tiktoken_file,
                    md1_endpoint=md1_endpoint,
                    budget=budget,
                )
                for arm in arm_order
            }
            results = {arm: futs[arm].result() for arm in arm_order}

        with write_lock:
            with RUNS_FILE.open("a", encoding="utf-8", newline="\n") as fh:
                for arm in ARMS:
                    if arm in results:
                        fh.write(json.dumps(results[arm]) + "\n")

        parts = []
        for arm in ARMS:
            if arm in results:
                r = results[arm]
                ms = f"{r['mean_router_ms']:.1f}ms" if r["mean_router_ms"] is not None else "-"
                parts.append(
                    f"{arm}:{'PASS' if r['passed'] else 'FAIL'}"
                    f"(${r['cold_usd']:.4f},hit={r['mean_resume_first_call_cache_hit_rate']:.0%},"
                    f"mut={r['resume_tool_mutations']},rt={ms})"
                )
        dt = time.perf_counter() - t_batch
        print(
            f"  -> done in {dt:.1f}s | " + " | ".join(parts) + f" | spent=${budget.spent_nano / NANO_PER_USD:.2f}",
            flush=True,
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_st = sub.add_parser("self-test")
    p_st.add_argument("--python", type=Path, default=DEFAULT_PYTHON)

    p_prep = sub.add_parser("prepare")
    p_prep.add_argument("--lanes-dir", type=Path, default=DEFAULT_LANES)
    p_prep.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    p_prep.add_argument("--tiktoken", type=Path, default=DEFAULT_TIKTOKEN)
    p_prep.add_argument("--md1-endpoint", default=DEFAULT_MD1_ENDPOINT)

    p_run = sub.add_parser("run")
    p_run.add_argument("--lanes-dir", type=Path, default=DEFAULT_LANES)
    p_run.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    p_run.add_argument("--tiktoken", type=Path, default=DEFAULT_TIKTOKEN)
    p_run.add_argument("--md1-endpoint", default=DEFAULT_MD1_ENDPOINT)
    p_run.add_argument("--tasks", default="")
    p_run.add_argument("--budget-usd", type=float, default=35.0)
    p_run.add_argument("--fresh", action="store_true")

    args = ap.parse_args()
    if args.cmd == "self-test":
        self_test(args.python)
    elif args.cmd == "prepare":
        prepare(args.lanes_dir, args.python, args.tiktoken, args.md1_endpoint)
    elif args.cmd == "run":
        only = {x.strip() for x in args.tasks.split(",") if x.strip()} or None
        run_benchmark(
            args.lanes_dir,
            args.python,
            args.tiktoken,
            args.md1_endpoint,
            only_tasks=only,
            budget_usd=args.budget_usd,
            fresh=args.fresh,
        )


if __name__ == "__main__":
    main()
