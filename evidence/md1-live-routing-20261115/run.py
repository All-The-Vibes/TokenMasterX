"""Live 3-arm routing study runner: stock vs. TokenMaster --lean (regex) vs. TokenMaster --lean + MD-1.

Commands:
  python run.py self-test
  python run.py prepare
  python run.py run [--tasks A01,B01,...] [--credit-cap 30]
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
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

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PLUGIN = REPO / "token-master-plugin"
EVALS = PLUGIN / "evals"
SKILL = PLUGIN / "skills" / "token-master"
sys.path.insert(0, str(EVALS))
sys.path.insert(0, str(SKILL))

import brainspace_copilot_bridge as bridge
import tokenomics
from tokenomics import NANO_PER_USD

CREDIT_NANO = 1_000_000_000  # 1 AI credit = $0.01 = 1e9 nano_aiu
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
ARMS = ("stock", "tm_regex", "tm_md1")
LANE_NAMES = {"stock": "l1", "tm_regex": "l2", "tm_md1": "l3"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def git_clean(work: Path) -> bool:
    out = subprocess.run([GIT, "status", "--porcelain"], cwd=work, check=True, capture_output=True, text=True).stdout
    return out.strip() == ""


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
            if not isinstance(got_v, (int, float)) or abs(float(got_v) - exp_v) > 1e-6:
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

DEFAULT_LANES = Path(r"C:\tm-lanes\md1-live-routing-20261115")
DEFAULT_PYTHON = Path(r"C:\tm-lanes\tm-runtime\Scripts\python.exe")
DEFAULT_TIKTOKEN = Path(r"C:\tm-lanes\tm-runtime\cl100k_base.tiktoken")
DEFAULT_MD1_ENDPOINT = os.environ.get("TOKENMASTER_MD1_ENDPOINT", "")

PROTOCOL = HERE / "PROTOCOL.md"
PROTOCOL_HASH = HERE / "PROTOCOL.sha256"
TASKS_FILE = HERE / "tasks.json"
SETUP_FILE = HERE / "setup.json"
RUNS_FILE = HERE / "runs.jsonl"
MD1_SCORES_FILE = HERE / "md1_prompt_scores.json"
SESSIONS_DIR = HERE / "sessions"


class StudyError(RuntimeError):
    pass


class CreditCapExceeded(RuntimeError):
    pass


class CreditBudget:
    def __init__(self, cap_credits: float):
        self.cap_nano = round(cap_credits * CREDIT_NANO)
        self.spent_nano = 0
        self._lock = threading.Lock()

    def check(self) -> None:
        with self._lock:
            if self.spent_nano >= self.cap_nano:
                raise CreditCapExceeded(
                    f"credit cap reached: {self.spent_nano / CREDIT_NANO:.2f} / "
                    f"{self.cap_nano / CREDIT_NANO:.2f} credits"
                )

    def add(self, nano: int) -> float:
        with self._lock:
            self.spent_nano += nano
            return self.spent_nano / CREDIT_NANO


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


def _resolve_gh_token() -> str:
    global _CACHED_GH_TOKEN
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


def lane_env(home: Path, *, python_exe: Path, tiktoken_file: Path, md1_endpoint: str | None = None) -> dict[str, str]:
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
    appdata = home / "AppData" / "Roaming"
    localapp = home / "AppData" / "Local"
    temp = localapp / "Temp"
    for d in (home / "copilot", appdata, localapp, temp):
        d.mkdir(parents=True, exist_ok=True)
    # Pin Copilot CLI 1.0.112 inside the lane's isolated LOCALAPPDATA. Do NOT set COPILOT_AUTO_UPDATE=false
    # or --no-auto-update, as WinGet's launcher ignores COPILOT_CLI_DIST_DIR when auto-update is disabled.
    lane_pkg = localapp / "copilot" / "pkg" / "win32-x64" / CLI_PKG_VERSION
    if not lane_pkg.is_dir():
        if not INSTALLED_PKG.is_dir():
            raise StudyError(f"expected Copilot CLI package {CLI_PKG_VERSION} at {INSTALLED_PKG}")
        mirror(INSTALLED_PKG, lane_pkg)

    pwsh_dir = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "PowerShell" / "7"
    if pwsh_dir.is_dir():
        path_dirs.insert(4, str(pwsh_dir))

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
    launches = ch / "token-master" / "launches.jsonl"
    launches.unlink(missing_ok=True)


def fetch_entra_md1_token() -> dict:
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
        expires_on = int(time.time()) + 3300
    return {"tenant": "", "token": raw["accessToken"], "expires_on": expires_on}


def write_lane_md1_token(home: Path, token_payload: dict) -> Path:
    tm_dir = home / "copilot" / "token-master"
    tm_dir.mkdir(parents=True, exist_ok=True)
    path = tm_dir / "md1-token.json"
    path.write_text(json.dumps(token_payload), encoding="utf-8")
    return path


def seed_b02_session_history(home: Path, template_db: Path, work: Path) -> None:
    dst = home / "copilot" / "session-store.db"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template_db, dst)
    con = sqlite3.connect(dst)
    try:
        for table in ("search_index", "turns", "checkpoints", "session_files", "session_refs", "assistant_usage_events", "sessions"):
            try:
                con.execute(f"DELETE FROM {table}")
            except sqlite3.OperationalError:
                pass
        seeded = [
            (
                "10101010-1111-4111-8111-000000000001",
                "Symbol index schema v5 notes",
                "2026-11-10T15:10:00.000Z",
                "2026-11-10T15:14:00.000Z",
                "Should we bump symbol_index SCHEMA_VERSION from 5 right now?",
                "No, keep SCHEMA_VERSION at 5; .py, .pyi, .rs, .md, .markdown, and .json are already covered.",
            ),
            (
                "20202020-2222-4222-8222-000000000002",
                "Brainspace cache TTL header contract",
                "2026-11-11T16:20:00.000Z",
                "2026-11-11T16:26:00.000Z",
                "Let's lock down the Brainspace cache TTL header contract for our Tuesday sync.",
                (
                    "Confirmed for the Tuesday contract: use HTTP header `X-Brainspace-TTL-Seconds`, "
                    "integer max-age `1800` seconds, and fallback policy `bypass-on-stale`."
                ),
            ),
            (
                "30303030-3333-4333-8333-000000000003",
                "Tokenomics compact width behavior",
                "2026-11-12T10:05:00.000Z",
                "2026-11-12T10:09:00.000Z",
                "Remind me when tokenomics switches to compact mode automatically.",
                "When stdout is a TTY, neither --compact nor --full was passed, and rendered width exceeds terminal columns.",
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
    if len(tasks) != 15:
        raise StudyError(f"expected 15 tasks, got {len(tasks)}")
    buckets: dict[str, list[dict]] = {}
    for t in tasks:
        buckets.setdefault(t["bucket"], []).append(t)
    expected_buckets = {"A_pure_coding": 5, "B_multi_capability": 5, "C_adversarial_lookalike": 5}
    for b, cnt in expected_buckets.items():
        if len(buckets.get(b, [])) != cnt:
            raise StudyError(f"bucket {b} has {len(buckets.get(b, []))} tasks, expected {cnt}")

    # Verify regex-only exclusions WITHOUT probing MD-1 (preserving zero post-hoc MD-1 tuning).
    empty_home = Path(tempfile.mkdtemp(prefix="tm_regex_check_"))
    prev_ch = os.environ.get("COPILOT_HOME")
    prev_ep = os.environ.get("TOKENMASTER_MD1_ENDPOINT")
    prev_kt = os.environ.get("TOKENMASTER_KEEP_TOOLS")
    try:
        os.environ["COPILOT_HOME"] = str(empty_home)
        os.environ.pop("TOKENMASTER_MD1_ENDPOINT", None)
        os.environ.pop("TOKENMASTER_KEEP_TOOLS", None)
        for t in tasks:
            excl = bridge.select_excluded_tools(["copilot", "-p", t["prompt"]])
            kept = kept_groups_from_excluded(excl)
            if t["bucket"] in ("A_pure_coding", "B_multi_capability"):
                if len(excl) != len(bridge.LEAN_EXCLUDED_TOOLS):
                    raise StudyError(f"{t['id']} unexpectedly triggered regex groups {kept}")
            else:
                if sorted(kept) != sorted(t["trap_groups"]):
                    raise StudyError(f"{t['id']} regex kept {kept}, expected trap_groups {t['trap_groups']}")
    finally:
        if prev_ch is None:
            os.environ.pop("COPILOT_HOME", None)
        else:
            os.environ["COPILOT_HOME"] = prev_ch
        if prev_ep is not None:
            os.environ["TOKENMASTER_MD1_ENDPOINT"] = prev_ep
        if prev_kt is not None:
            os.environ["TOKENMASTER_KEEP_TOOLS"] = prev_kt
        shutil.rmtree(empty_home, ignore_errors=True)

    # Verify edit tasks fail before reference_patch and pass after git apply.
    tmp = Path(tempfile.mkdtemp(prefix="tm_edit_selftest_"))
    try:
        archive = tmp / "head.tar"
        subprocess.run([GIT, "archive", "--format=tar", "-o", str(archive), "HEAD"], cwd=REPO, check=True)
        work = tmp / "work"
        work.mkdir()
        subprocess.run(["tar", "-xf", str(archive), "-C", str(work)], check=True)
        subprocess.run([GIT, "init", "-q"], cwd=work, check=True)
        subprocess.run([GIT, "config", "core.autocrlf", "false"], cwd=work, check=True)
        subprocess.run([GIT, "add", "-A"], cwd=work, check=True)
        subprocess.run([GIT, "-c", "user.name=tm", "-c", "user.email=tm@local", "commit", "-qm", "base"], cwd=work, check=True)

        for t in tasks:
            if t["kind"] != "edit":
                continue
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
            dirty = subprocess.run(
                [GIT, "status", "--porcelain"], cwd=work, check=True, capture_output=True, text=True
            ).stdout.splitlines()
            touched = {line[3:].strip().replace("\\", "/") for line in dirty if line.strip()}
            if not touched or not touched.issubset(set(t["allowed_paths"])):
                raise StudyError(f"{t['id']} reference_patch touched {touched}, allowed {t['allowed_paths']}")
            post = subprocess.run([str(python_exe), "-c", code], cwd=work, capture_output=True, text=True)
            if post.returncode != 0:
                raise StudyError(f"{t['id']} check failed AFTER reference_patch:\n{post.stdout}\n{post.stderr}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("self-test passed: 15 tasks (5xA, 5xB, 5xC), regex triggers verified, 3 edit checks verified.")


def install_tokenmaster(work: Path, home: Path, python_exe: Path, tiktoken_file: Path) -> dict:
    skill = work / "token-master-plugin" / "skills" / "token-master"
    env = lane_env(home, python_exe=python_exe, tiktoken_file=tiktoken_file)
    p1 = subprocess.run(
        [str(python_exe), "-B", str(skill / "setup.py"), str(work), "--host", "copilot", "--python", str(python_exe)],
        cwd=skill,
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
            str(skill / "brainspace_setup.py"),
            "--host",
            "copilot",
            "--python",
            str(python_exe),
            "--tokenizer-file",
            str(tiktoken_file),
        ],
        cwd=skill,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=True,
    )
    probe = subprocess.run(
        [
            str(python_exe),
            "-c",
            (
                "import json, sys; from pathlib import Path; "
                f"sys.path.insert(0, {str(skill)!r}); "
                "from brainspace import symbol_index; "
                f"idx = symbol_index.SymbolIndex(Path({str(work)!r})); "
                "res = symbol_index.dispatch(idx, 'locate', {'query': 'select_excluded_tools'}); idx.close(); "
                "assert 'brainspace_copilot_bridge.py' in res, res; "
                "print(json.dumps({'ok': True, 'sample': res.splitlines()[0]}))"
            ),
        ],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    # graphify update appends `graphify-out/` to .gitignore, which is already ignored by root `/*`;
    # restore .gitignore and remove raw graphify-out/ so the visible repository tree matches stock 1:1.
    subprocess.run([GIT, "checkout", "-q", "--", ".gitignore"], cwd=work, check=True)
    shutil.rmtree(work / "graphify-out", ignore_errors=True)
    if not git_clean(work):
        raise StudyError(f"TokenMaster install dirtied git worktree at {work}")
    return {
        "setup_tail": (p1.stdout + p1.stderr).splitlines()[-5:],
        "brainspace_setup_tail": (p2.stdout + p2.stderr).splitlines()[-5:],
        "nav_probe": json.loads(probe.stdout),
    }


def prepare(lanes_dir: Path, python_exe: Path, tiktoken_file: Path, md1_endpoint: str) -> None:
    if not os.environ.get("GH_TOKEN") and not os.environ.get("COPILOT_GITHUB_TOKEN"):
        raise StudyError("GH_TOKEN or COPILOT_GITHUB_TOKEN must be present in environment")
    if sha256(tiktoken_file) != "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7":
        raise StudyError(f"tiktoken file hash mismatch: {tiktoken_file}")
    # Verify MD-1 live endpoint works before freezing setup.
    tok = fetch_entra_md1_token()
    tmp_home = Path(tempfile.mkdtemp(prefix="tm_md1_prep_"))
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

    # Freeze PROTOCOL.sha256 BEFORE preparing lanes or running any task.
    proto_digest = sha256(PROTOCOL)
    PROTOCOL_HASH.write_text(f"{proto_digest}  PROTOCOL.md\n", encoding="utf-8", newline="\n")

    if lanes_dir.exists():
        import stat
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
    subprocess.run([GIT, "add", "-A"], cwd=stock_tpl / "work", check=True)
    subprocess.run(
        [GIT, "-c", "user.name=study", "-c", "user.email=study@local", "commit", "-qm", "base"],
        cwd=stock_tpl / "work",
        check=True,
    )

    # Run a single minimal CLI probe in a disposable home to materialize a clean 1.0.112 session-store.db schema
    # for seeding B02, and capture exact CLI version.
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
    for table in ("search_index", "turns", "checkpoints", "session_files", "session_refs", "assistant_usage_events", "sessions"):
        try:
            con.execute(f"DELETE FROM {table}")
        except sqlite3.OperationalError:
            pass
    con.commit()
    con.execute("VACUUM")
    con.close()
    shutil.rmtree(schema_home, ignore_errors=True)

    # Ensure stock_tpl/home has pre-populated winget copilot pkg cache so all lanes start warm on disk.
    lane_env(stock_tpl / "home", python_exe=python_exe, tiktoken_file=tiktoken_file)
    clear_lane_history(stock_tpl / "home")

    # Install TokenMaster once into tm_base, then clone identically to tm_regex and tm_md1.
    tm_base = lanes_dir / "templates" / "tm_base"
    mirror(stock_tpl / "work", tm_base / "work")
    mirror(stock_tpl / "home", tm_base / "home")
    tm_install = install_tokenmaster(tm_base / "work", tm_base / "home", python_exe, tiktoken_file)
    clear_lane_history(tm_base / "home")

    for arm in ("tm_regex", "tm_md1"):
        tpl = lanes_dir / "templates" / arm
        mirror(tm_base / "work", tpl / "work")
        mirror(tm_base / "home", tpl / "home")
    shutil.rmtree(tm_base, ignore_errors=True)

    for arm in ARMS:
        lane = lanes_dir / "lanes" / LANE_NAMES[arm]
        mirror(lanes_dir / "templates" / arm / "work", lane / "work")
        mirror(lanes_dir / "templates" / arm / "home", lane / "home")

    setup = {
        "prepared_at": now_iso(),
        "repo_commit": head_sha,
        "protocol_sha256": proto_digest,
        "tasks_sha256": sha256(TASKS_FILE),
        "copilot_cli_version": ver_out,
        "copilot_exe": COPILOT,
        "python_exe": str(python_exe),
        "python_version": subprocess.run([str(python_exe), "--version"], check=True, capture_output=True, text=True).stdout.strip(),
        "tiktoken_sha256": sha256(tiktoken_file),
        "model": MODEL,
        "reasoning_effort": REASONING,
        "md1_endpoint": md1_endpoint,
        "md1_threshold": bridge.MD1_THRESHOLD,
        "arms": list(ARMS),
        "lane_names": LANE_NAMES,
        "lanes_dir": str(lanes_dir),
        "tm_install": tm_install,
    }
    SETUP_FILE.write_text(json.dumps(setup, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Prepared 3 isolated lanes at {lanes_dir} (CLI: {ver_out}, commit: {head_sha[:7]}).")


def reset_lane(lanes_dir: Path, arm: str) -> tuple[Path, Path]:
    tpl = lanes_dir / "templates" / arm
    lane = lanes_dir / "lanes" / LANE_NAMES[arm]
    mirror(tpl / "work", lane / "work")
    mirror(tpl / "home" / "copilot", lane / "home" / "copilot")
    clear_lane_history(lane / "home")
    if not git_clean(lane / "work"):
        raise StudyError(f"lane {arm} dirty after reset")
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
    cache_state = None
    final_answer = ""
    last_answer = ""
    copilot_version = None
    session_errors = []
    for ev in events:
        etype = ev.get("type")
        data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
        if etype == "session.start":
            copilot_version = data.get("copilotVersion") or copilot_version
        elif etype == "tool.execution_start":
            tool_starts.append(
                {
                    "name": data.get("toolName"),
                    "arguments": data.get("arguments") if isinstance(data.get("arguments"), dict) else {},
                }
            )
        elif etype == "assistant.message" and isinstance(data.get("content"), str) and data["content"].strip():
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
        "cache_state": cache_state or {},
        "session_errors": session_errors,
    }


def harvest_store(home: Path, since: str) -> dict:
    db = home / "copilot" / "session-store.db"
    if not db.is_file():
        return {"session_ids": [], "calls": []}
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT id, session_id, agent_id, model, api_endpoint, input_tokens, output_tokens, "
            "cache_read_tokens, cache_write_tokens, total_nano_aiu, token_details_json, created_at "
            "FROM assistant_usage_events WHERE created_at >= ? ORDER BY created_at, id",
            (since,),
        ).fetchall()
    finally:
        con.close()
    calls = []
    sids = []
    first_main_seen = False
    for idx, r in enumerate(rows):
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
        is_first_main = (not is_sub) and (not first_main_seen)
        if is_first_main:
            first_main_seen = True
            prices = tokenomics.prices_of(raw_details)
            cold = billed + cread * (prices.get("cache_write", 0) - prices.get("cache_read", 0))
        else:
            cold = billed
        calls.append(
            {
                "call_index": idx,
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


def harvest_launch(home: Path) -> dict | None:
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


def detect_capability_behavior(task: dict, tool_starts: list[dict]) -> dict:
    names = [t["name"] for t in tool_starts if t.get("name")]
    target_tools = set(task.get("target_tools") or [])
    target_used = any(n in target_tools for n in names)
    async_ps = any(
        t["name"] == "powershell" and (t.get("arguments") or {}).get("mode") == "async"
        for t in tool_starts
    )
    if task["id"] == "B03":
        # Genuine background-shell workflow uses async powershell PLUS read_powershell or stop_powershell.
        target_used = async_ps and any(n in ("read_powershell", "stop_powershell") for n in names)

    shell_workaround = False
    if task["bucket"] == "B_multi_capability" and not target_used:
        if any(n == "powershell" for n in names) or (task["id"] == "B01" and "task" not in names):
            shell_workaround = True

    return {
        "called_tools": names,
        "target_tool_used": target_used,
        "async_powershell_used": async_ps,
        "shell_workaround": shell_workaround,
    }


def check_b03_ports_closed(stdout_text: str) -> tuple[bool, list[int]]:
    ports = {int(m.group(1)) for m in re.finditer(r"READY:(\d{2,5})", stdout_text)}
    still_open = []
    import socket

    for port in sorted(ports):
        if port <= 0 or port > 65535:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                still_open.append(port)
    return (len(still_open) == 0), still_open


def grade_task(task: dict, work: Path, python_exe: Path, final_answer: str, stdout_text: str) -> tuple[bool, str, str]:
    diff = git_diff(work)
    if task["kind"] == "investigate":
        clean = git_clean(work)
        got = extract_json(final_answer)
        ok = clean and json_matches(got, task["expected"], task.get("unordered_keys", ()))
        note = json.dumps({"git_clean": clean, "parsed": got, "expected": task["expected"]}, indent=2)
        if task["id"] == "B03" and ok:
            ports_closed, open_ports = check_b03_ports_closed(stdout_text)
            if not ports_closed:
                ok = False
            note = json.dumps(
                {"git_clean": clean, "parsed": got, "expected": task["expected"], "open_ports": open_ports},
                indent=2,
            )
        return ok, diff, note

    # Edit task
    dirty = subprocess.run(
        [GIT, "status", "--porcelain"], cwd=work, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    touched = {line[3:].strip().replace("\\", "/") for line in dirty if line.strip()}
    allowed_ok = bool(touched) and touched.issubset(set(task["allowed_paths"]))
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
        f"touched={sorted(touched)}\nallowed={task['allowed_paths']}\n"
        f"check_exit={proc.returncode}\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    return ok, diff, note


def run_one_session(
    lanes_dir: Path,
    arm: str,
    task: dict,
    *,
    python_exe: Path,
    tiktoken_file: Path,
    md1_endpoint: str,
    md1_token_payload: dict | None,
    budget: CreditBudget,
) -> dict:
    budget.check()
    work, home = reset_lane(lanes_dir, arm)
    if task.get("fixture") == "seeded_session_history":
        seed_b02_session_history(home, lanes_dir / "session-store-template.db", work)
    if arm == "tm_md1":
        if not md1_token_payload:
            raise StudyError("missing MD-1 token payload for tm_md1")
        write_lane_md1_token(home, md1_token_payload)

    env = lane_env(
        home,
        python_exe=python_exe,
        tiktoken_file=tiktoken_file,
        md1_endpoint=(md1_endpoint if arm == "tm_md1" else None),
    )
    cli_flags = [
        "-p",
        task["prompt"],
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
        if not bridge_py.is_file():
            bridge_py = work / "token-master-plugin" / "skills" / "token-master" / "brainspace_copilot_bridge.py"
        cmd = [str(python_exe), "-B", str(bridge_py), "--lean", "--", COPILOT, *cli_flags]

    since = now_iso()
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
            timeout=420,
        )
        exit_code = proc.returncode
        stdout_text = proc.stdout
        stderr_text = proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = -9
        stdout_text = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", "replace")
        stderr_text = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", "replace")
    elapsed = time.perf_counter() - t0

    # Ensure md1-token.json is removed immediately after the session completes.
    (home / "copilot" / "token-master" / "md1-token.json").unlink(missing_ok=True)

    telemetry = parse_stdout_telemetry(stdout_text)
    store_data = harvest_store(home, since)
    launch = harvest_launch(home)
    calls = store_data["calls"]

    passed, diff, check_note = (
        grade_task(task, work, python_exe, telemetry["final_answer"], stdout_text)
        if exit_code == 0 and not timed_out
        else (False, git_diff(work), f"exit_code={exit_code} timed_out={timed_out}")
    )
    cap_behavior = detect_capability_behavior(task, telemetry["tool_starts"])

    excluded = list(launch.get("excluded") or []) if launch else []
    kept_aux_tools = (
        list(bridge.LEAN_EXCLUDED_TOOLS)
        if arm == "stock"
        else [t for t in bridge.LEAN_EXCLUDED_TOOLS if t not in set(excluded)]
    )
    kept_groups = sorted(bridge.CAPABILITY_GROUPS) if arm == "stock" else kept_groups_from_excluded(excluded)
    needed = set(task.get("needed_groups") or [])
    needed_recalled = needed.issubset(set(kept_groups))
    false_keep_tools = [
        t
        for g in kept_groups
        if g not in needed
        for t in bridge.CAPABILITY_GROUPS[g][0]
        if t in set(kept_aux_tools)
    ]

    billed_nano = sum(c["total_nano_aiu"] for c in calls)
    cold_nano = sum(c["cold_nano_aiu"] for c in calls)
    input_tokens = sum(c["input_tokens"] for c in calls)
    output_tokens = sum(c["output_tokens"] for c in calls)
    cache_read_tokens = sum(c["cache_read_tokens"] for c in calls)
    cache_write_tokens = sum(c["cache_write_tokens"] for c in calls)
    subagent_calls = sum(1 for c in calls if c["is_subagent"])
    spent_credits = budget.add(billed_nano)

    out_dir = SESSIONS_DIR / task["id"] / arm
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "stdout.jsonl").write_text(stdout_text, encoding="utf-8")
    (out_dir / "stderr.txt").write_text(stderr_text, encoding="utf-8")
    (out_dir / "patch.diff").write_text(diff, encoding="utf-8")
    (out_dir / "check.txt").write_text(check_note, encoding="utf-8")
    launches_src = home / "copilot" / "token-master" / "launches.jsonl"
    if launches_src.is_file():
        shutil.copy2(launches_src, out_dir / "launches.jsonl")
    for sid in store_data["session_ids"]:
        ev_file = home / "copilot" / "session-state" / sid / "events.jsonl"
        if ev_file.is_file():
            shutil.copy2(ev_file, out_dir / f"events-{sid}.jsonl")

    cs = telemetry["cache_state"]
    first_main = next((c for c in calls if not c["is_subagent"]), calls[0] if calls else None)
    rec = {
        "task_id": task["id"],
        "bucket": task["bucket"],
        "kind": task["kind"],
        "arm": arm,
        "lane": LANE_NAMES[arm],
        "copilot_version": telemetry["copilot_version"],
        "session_ids": store_data["session_ids"],
        "started_at": since,
        "seconds": round(elapsed, 3),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "passed": passed,
        "call_count": len(calls),
        "subagent_calls": subagent_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "raw_tokens": input_tokens + output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
        "first_call_input_tokens": first_main["input_tokens"] if first_main else 0,
        "billed_nano_aiu": billed_nano,
        "billed_usd": billed_nano / NANO_PER_USD,
        "cold_nano_aiu": cold_nano,
        "cold_usd": cold_nano / NANO_PER_USD,
        "tool_count": cs.get("tool_count"),
        "tool_tokens": cs.get("tool_tokens"),
        "tool_instructions_tokens": cs.get("tool_instructions_tokens"),
        "schema_plus_instr_tokens": (
            (cs.get("tool_tokens") or 0) + (cs.get("tool_instructions_tokens") or 0)
            if cs.get("tool_tokens") is not None
            else None
        ),
        "active_tools": cs.get("tools") or [],
        "launch_recorded": bool(launch),
        "excluded_tools": excluded,
        "kept_aux_tools": kept_aux_tools,
        "kept_groups": kept_groups,
        "needed_groups": list(needed),
        "needed_recalled": needed_recalled,
        "false_keep_tool_count": len(false_keep_tools),
        "false_keep_tools": false_keep_tools,
        **cap_behavior,
        "calls": calls,
        "cumulative_credits": round(spent_credits, 4),
    }
    (out_dir / "result.json").write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8", newline="\n")
    return rec


def record_md1_prompt_scores(tasks: list[dict], md1_endpoint: str, token_payload: dict) -> list[dict]:
    tmp_home = Path(tempfile.mkdtemp(prefix="tm_md1_audit_"))
    rows = []
    prev_ep = os.environ.get("TOKENMASTER_MD1_ENDPOINT")
    prev_ch = os.environ.get("COPILOT_HOME")
    prev_kt = os.environ.get("TOKENMASTER_KEEP_TOOLS")
    try:
        write_lane_md1_token(tmp_home, token_payload)
        os.environ["COPILOT_HOME"] = str(tmp_home / "copilot")
        os.environ["TOKENMASTER_MD1_ENDPOINT"] = md1_endpoint
        os.environ.pop("TOKENMASTER_KEEP_TOOLS", None)
        for t in tasks:
            t0 = time.perf_counter()
            scores = bridge.md1_scores(t["prompt"])
            dt_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            md1_only = sorted(k for k, v in (scores or {}).items() if v >= bridge.MD1_THRESHOLD)
            if "skills" in md1_only:
                md1_only = sorted(set(md1_only) | {"agents", "workflows"})
            excl = bridge.select_excluded_tools(["copilot", "-p", t["prompt"]])
            rows.append(
                {
                    "task_id": t["id"],
                    "bucket": t["bucket"],
                    "needed_groups": t["needed_groups"],
                    "trap_groups": t.get("trap_groups", []),
                    "md1_latency_ms": dt_ms,
                    "scores": {k: round(v, 4) for k, v in (scores or {}).items()},
                    "md1_only_kept_groups": md1_only,
                    "md1_kept_groups": kept_groups_from_excluded(excl),
                    "md1_excluded_count": len(excl),
                }
            )
    finally:
        if prev_ep is None:
            os.environ.pop("TOKENMASTER_MD1_ENDPOINT", None)
        else:
            os.environ["TOKENMASTER_MD1_ENDPOINT"] = prev_ep
        if prev_ch is None:
            os.environ.pop("COPILOT_HOME", None)
        else:
            os.environ["COPILOT_HOME"] = prev_ch
        if prev_kt is not None:
            os.environ["TOKENMASTER_KEEP_TOOLS"] = prev_kt
        shutil.rmtree(tmp_home, ignore_errors=True)
    MD1_SCORES_FILE.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8", newline="\n")
    return rows


def run_study(
    lanes_dir: Path,
    python_exe: Path,
    tiktoken_file: Path,
    md1_endpoint: str,
    *,
    task_filter: set[str] | None,
    credit_cap: float,
) -> None:
    if not PROTOCOL_HASH.is_file():
        raise StudyError("PROTOCOL.sha256 missing; run prepare first")
    expected_proto = PROTOCOL_HASH.read_text(encoding="utf-8").split()[0]
    if sha256(PROTOCOL) != expected_proto:
        raise StudyError("PROTOCOL.md changed after freeze!")

    all_tasks = load_tasks()
    tasks = [t for t in all_tasks if not task_filter or t["id"] in task_filter]
    budget = CreditBudget(credit_cap)
    done = set()
    if RUNS_FILE.is_file():
        for line in RUNS_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["task_id"], r["arm"]))
                budget.add(int(r.get("billed_nano_aiu") or 0))

    token_payload = fetch_entra_md1_token()
    if not MD1_SCORES_FILE.is_file():
        print("Recording MD-1 per-prompt score and latency profile across all 15 frozen prompts...")
        record_md1_prompt_scores(all_tasks, md1_endpoint, token_payload)

    write_lock = threading.Lock()
    try:
        for idx, task in enumerate(tasks, 1):
            pending_arms = [a for a in ARMS if (task["id"], a) not in done]
            if not pending_arms:
                print(f"[{idx:02d}/{len(tasks):02d}] {task['id']} already complete; skipping.")
                continue
            # Refresh Entra token if within 15 minutes of expiry.
            if token_payload["expires_on"] - time.time() < 900:
                token_payload = fetch_entra_md1_token()

            # Rotate arm start order slightly across tasks even under parallel execution.
            ordered_arms = pending_arms[idx % len(pending_arms):] + pending_arms[: idx % len(pending_arms)]
            print(f"[{idx:02d}/{len(tasks):02d}] Running {task['id']} ({task['bucket']}) across {ordered_arms}...", flush=True)
            with ThreadPoolExecutor(max_workers=3) as pool:
                futs = {
                    arm: pool.submit(
                        run_one_session,
                        lanes_dir,
                        arm,
                        task,
                        python_exe=python_exe,
                        tiktoken_file=tiktoken_file,
                        md1_endpoint=md1_endpoint,
                        md1_token_payload=token_payload,
                        budget=budget,
                    )
                    for arm in ordered_arms
                }
                results = {arm: futs[arm].result() for arm in ordered_arms}

            with write_lock:
                with RUNS_FILE.open("a", encoding="utf-8", newline="\n") as fh:
                    for arm in ARMS:
                        if arm in results:
                            fh.write(json.dumps(results[arm]) + "\n")
            for arm in ARMS:
                if arm in results:
                    r = results[arm]
                    print(
                        f"    {arm:8s} | pass={str(r['passed']):5s} | calls={r['call_count']:2d} "
                        f"| raw={r['raw_tokens']:7,d} | cold=${r['cold_usd']:.4f} "
                        f"| tools={str(r['tool_count']):>2s} ({str(r['tool_tokens']):>4s}t) "
                        f"| kept={r['kept_groups']} | {r['seconds']:.1f}s",
                        flush=True,
                    )
    finally:
        # Defensive cleanup: ensure no md1-token.json remains in any lane.
        for lane_name in LANE_NAMES.values():
            (lanes_dir / "lanes" / lane_name / "home" / "copilot" / "token-master" / "md1-token.json").unlink(
                missing_ok=True
            )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
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
    p_run.add_argument("--tasks", help="comma-separated task IDs (default: all 15)")
    p_run.add_argument("--credit-cap", type=float, default=1200.0)

    args = ap.parse_args()
    if args.cmd == "self-test":
        self_test(args.python)
    elif args.cmd == "prepare":
        prepare(args.lanes_dir, args.python, args.tiktoken, args.md1_endpoint)
    elif args.cmd == "run":
        filt = {x.strip() for x in args.tasks.split(",") if x.strip()} if args.tasks else None
        run_study(
            args.lanes_dir,
            args.python,
            args.tiktoken,
            args.md1_endpoint,
            task_filter=filt,
            credit_cap=args.credit_cap,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
