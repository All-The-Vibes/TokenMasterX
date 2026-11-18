"""Pre-registered 72-session live benchmark runner for R1 Submodular Brief Synthesis (`repo-brief-r1-20261118`).

Design: 24 paired tasks (12 TokenMasterX @ 204d388 + 12 pallets/click @ 934813e4, balanced 8xA / 8xB / 8xC)
across 3 matched TokenMaster arms executed concurrently per task on Copilot CLI 1.0.112 (`gpt-6-astra`):
  - tm_lean      : TokenMaster MCP navigation + PostToolUse + --lean launcher (no sessionStart brief)
  - tm_v1_recall : tm_lean + hooks.sessionStart injecting frozen PR-#36 --brief-algorithm v1 brief (<=320t)
  - tm_r1_recall : tm_lean + hooks.sessionStart injecting R1 --brief-algorithm r1 submodular brief (<=320t)
                   built from the EXACT IDENTICAL multi-session recall.jsonl and 320-token budget.

Commands:
  python run.py self-test
  python run.py prepare
  python run.py run [--tasks T01,C01,...] [--budget-usd 25]
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
import stat
import subprocess
import sys
import tempfile
import threading
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PLUGIN = REPO / "token-master-plugin"
SKILL = PLUGIN / "skills" / "token-master"
sys.path.insert(0, str(SKILL))

from brainspace import repo_brief, symbol_index
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

ARMS = ("tm_lean", "tm_v1_recall", "tm_r1_recall")
BRIEF_ARMS = ("tm_v1_recall", "tm_r1_recall")
LANE_NAMES = {"tm_lean": "l1", "tm_v1_recall": "l2", "tm_r1_recall": "l3"}
BUCKETS = (
    "A_warm_crowdout_recovery",
    "B_noisy_recall_filtering",
    "C_prefix_folding_and_direct_control",
)

DEFAULT_LANES = Path(r"C:\tm-lanes\repo-brief-r1-20261118")
DEFAULT_REPOS_DIR = Path(r"C:\tm-lanes\repos")
DEFAULT_PYTHON = Path(r"C:\tm-lanes\tm-runtime\Scripts\python.exe")
DEFAULT_TIKTOKEN = Path(r"C:\tm-lanes\tm-runtime\cl100k_base.tiktoken")

PROTOCOL = HERE / "PROTOCOL.md"
PROTOCOL_HASH = HERE / "PROTOCOL.sha256"
TASKS_FILE = HERE / "tasks.json"
SETUP_FILE = HERE / "setup.json"
WARMUP_FILE = HERE / "warmup.json"
RUNS_FILE = HERE / "runs.jsonl"
BRIEFS_FILE = HERE / "briefs.json"
SESSIONS_DIR = HERE / "sessions"

ORIENTATION_TOOLS = frozenset({
    "rg",
    "grep",
    "glob",
    "view",
    "tokenmaster-nav-locate",
})
DIRECT_SYMBOL_TOOLS = frozenset({
    "tokenmaster-nav-read_symbol",
    "tokenmaster-nav-impact",
})


class StudyError(RuntimeError):
    pass


class BudgetCapExceeded(RuntimeError):
    pass


class UsdBudget:
    def __init__(self, cap_usd: float):
        self.cap_nano = round(cap_usd * NANO_PER_USD)
        self.spent_nano = 0
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


def load_spec() -> dict:
    return json.loads(TASKS_FILE.read_text(encoding="utf-8"))


def git_status_lines(work: Path) -> list[str]:
    out = subprocess.run([GIT, "status", "--porcelain"], cwd=work, check=True, capture_output=True, text=True).stdout
    return [ln for ln in out.splitlines() if ln.strip()]


def git_clean(work: Path) -> bool:
    return len(git_status_lines(work)) == 0


def ensure_git_exclude(work: Path, entries: tuple[str, ...] = (".token-master/", "graphify-out/")) -> None:
    exclude = work / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    lines = existing.splitlines()
    missing = [e for e in entries if e not in lines]
    if missing:
        prefix = "" if (not existing or existing.endswith("\n")) else "\n"
        exclude.write_text(existing + prefix + "\n".join(missing) + "\n", encoding="utf-8", newline="\n")


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


def json_matches(got, expected: dict) -> bool:
    if not isinstance(got, dict) or set(got.keys()) != set(expected.keys()):
        return False
    for k, exp_v in expected.items():
        got_v = got[k]
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


def lane_env(home: Path, *, python_exe: Path, tiktoken_file: Path) -> dict[str, str]:
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
        "GRAPHIFY_NO_AUTO_REFRESH": "1",
    }
    for tok_var in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(tok_var):
            env[tok_var] = os.environ[tok_var]
    if not any(k in env for k in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")):
        env["GH_TOKEN"] = _resolve_gh_token()
    if (home / "copilot" / "instructions").is_dir():
        env["COPILOT_CUSTOM_INSTRUCTIONS_DIRS"] = str(home / "copilot" / "instructions")
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


def run_edit_verifier(work: Path, repo_key: str, task: dict, python_exe: Path, spec: dict, tiktoken_file: Path) -> tuple[bool, str]:
    rinfo = spec["repositories"][repo_key]
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["BRAINSPACE_TOKENIZER_FILE"] = str(tiktoken_file)
    env["TOKENMASTER_TOKENIZER_FILE"] = str(tiktoken_file)
    env["PYTHONPATH"] = str(work / rinfo["pythonpath"])

    p_behav = subprocess.run(
        [str(python_exe), "-c", task["verify_code"]],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if p_behav.returncode != 0:
        return False, f"behavioral_check_failed: {(p_behav.stdout + p_behav.stderr).strip()[:500]}"

    pytest_cmd = [str(python_exe), "-m", "pytest", *task["pytest_targets"], "-q", "-p", "no:cacheprovider"]
    p_test = subprocess.run(pytest_cmd, cwd=work, env=env, capture_output=True, text=True, timeout=180)
    if p_test.returncode != 0:
        return False, f"pytest_regression_failed: {(p_test.stdout + p_test.stderr).strip()[-500:]}"

    return True, "ok"


def grade_task(
    task: dict,
    work: Path,
    python_exe: Path,
    spec: dict,
    tiktoken_file: Path,
    final_answer: str,
    returncode: int,
) -> tuple[bool, str, dict | None]:
    if returncode != 0:
        return False, f"nonzero_exit:{returncode}", None
    status = git_status_lines(work)
    if task["kind"] == "trace":
        if status:
            return False, f"trace_mutated_repo:{status[:3]}", None
        parsed = extract_json(final_answer)
        if parsed is None:
            return False, "no_json_in_answer", None
        if not json_matches(parsed, task["expected"]):
            return False, f"json_mismatch:got={parsed}", parsed
        return True, "ok", parsed

    if not status:
        return False, "no_files_modified", None
    untracked = [ln for ln in status if ln.startswith("??")]
    if untracked:
        return False, f"untracked_files_left:{untracked[:3]}", None
    touched = {ln[3:].strip().replace("\\", "/") for ln in status}
    allowed = set(task["allowed_paths"])
    if not touched.issubset(allowed):
        return False, f"disallowed_paths_modified:{sorted(touched - allowed)}", None
    ok, detail = run_edit_verifier(work, task["repo"], task, python_exe, spec, tiktoken_file)
    return ok, detail, {"touched": sorted(touched)}


def materialize_clean_repo(src_repo: Path, expected_commit: str, dst: Path) -> None:
    if not src_repo.is_dir():
        raise StudyError(f"missing source clone at {src_repo}")
    actual = subprocess.run([GIT, "rev-parse", "HEAD"], cwd=src_repo, check=True, capture_output=True, text=True).stdout.strip()
    if actual != expected_commit:
        raise StudyError(f"{src_repo} is at {actual}, expected {expected_commit}")
    dst.mkdir(parents=True, exist_ok=True)
    archive = dst.parent / f"{dst.name}.tar"
    subprocess.run([GIT, "archive", "--format=tar", "-o", str(archive), expected_commit], cwd=src_repo, check=True)
    subprocess.run(["tar", "-xf", str(archive), "-C", str(dst)], check=True)
    archive.unlink()
    subprocess.run([GIT, "init", "-q"], cwd=dst, check=True)
    subprocess.run([GIT, "config", "core.autocrlf", "false"], cwd=dst, check=True)
    ensure_git_exclude(dst)
    subprocess.run([GIT, "add", "-A"], cwd=dst, check=True)
    subprocess.run([GIT, "-c", "user.name=study", "-c", "user.email=study@local", "commit", "-qm", "pinned"], cwd=dst, check=True)


def seed_prior_recall(work: Path, queries: list[dict]) -> None:
    """Execute genuine SymbolIndex MCP dispatches + record_recall into .token-master/recall.jsonl."""
    idx = symbol_index.SymbolIndex(work)
    try:
        for q in queries:
            for _ in range(int(q.get("repeats", 1))):
                res = symbol_index.dispatch(idx, q["tool"], dict(q["arguments"]))
                if res.startswith("Error:"):
                    raise StudyError(f"prior_recall query failed on {work}: {q} -> {res}")
                repo_brief.record_recall(idx, q["tool"], dict(q["arguments"]), res)
    finally:
        idx.close()


def refresh_brief_with_algorithm(work: Path, algorithm: str, python_exe: Path, env: dict[str, str]) -> dict:
    subprocess.run(
        [str(python_exe), "-B", str(SKILL / "setup.py"), str(work), "--refresh-brief", "--brief-algorithm", algorithm],
        cwd=SKILL,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    meta = json.loads((work / ".token-master" / "brief.json").read_text(encoding="utf-8"))
    text = (work / ".token-master" / "brief.md").read_text(encoding="utf-8")
    return {"text": text, "meta": meta}


def verify_brief_symbol_targets(work: Path, brief_text: str) -> int:
    """Verify every Recall/Hub/Entry target in brief_text resolves in 1 step via SymbolIndex.read."""
    idx = symbol_index.SymbolIndex(work)
    checked = 0
    try:
        for ln in brief_text.splitlines():
            m = re.match(r"^(?:Recall|Hub|Entry): ([^\s]+::[^\s]+)", ln)
            if not m:
                continue
            target = m.group(1)
            res = idx.read(target)
            if res.startswith("Error:") or res.startswith("Ambiguous"):
                raise StudyError(f"1-step read_symbol({target!r}) failed on {work}: {res}")
            checked += 1
    finally:
        idx.close()
    return checked


def self_test(repos_dir: Path, python_exe: Path, tiktoken_file: Path) -> None:
    os.environ["BRAINSPACE_TOKENIZER_FILE"] = str(tiktoken_file)
    os.environ["TOKENMASTER_TOKENIZER_FILE"] = str(tiktoken_file)
    spec = load_spec()
    tasks = spec["tasks"]
    if len(tasks) != 24:
        raise StudyError(f"expected 24 tasks, got {len(tasks)}")

    by_bucket: dict[str, int] = {}
    by_repo: dict[str, int] = {}
    for t in tasks:
        by_bucket[t["bucket"]] = by_bucket.get(t["bucket"], 0) + 1
        by_repo[t["repo"]] = by_repo.get(t["repo"], 0) + 1
    if by_bucket != {b: 8 for b in BUCKETS}:
        raise StudyError(f"unexpected bucket counts: {by_bucket}")
    if by_repo != {"tokenmasterx": 12, "click": 12}:
        raise StudyError(f"unexpected repo counts: {by_repo}")

    tmp = Path(tempfile.mkdtemp(prefix="tm_brief_r1_selftest_"))
    try:
        env = lane_env(tmp / "probe_home", python_exe=python_exe, tiktoken_file=tiktoken_file)
        for repo_key, rinfo in spec["repositories"].items():
            work = tmp / f"work_{repo_key}"
            materialize_clean_repo(repos_dir / repo_key, rinfo["commit"], work)

            subprocess.run(
                [str(python_exe), "-B", str(SKILL / "setup.py"), str(work), "--host", "copilot", "--python", str(python_exe)],
                cwd=SKILL,
                env=env,
                check=True,
                capture_output=True,
                text=True,
                timeout=900,
            )
            subprocess.run([GIT, "checkout", "-q", "--", "."], cwd=work, check=True)
            shutil.rmtree(work / "graphify-out", ignore_errors=True)
            if not git_clean(work):
                raise StudyError(f"{repo_key} dirty after setup.py")

            seed_prior_recall(work, rinfo["prior_recall_queries"])
            v1_doc = refresh_brief_with_algorithm(work, "v1", python_exe, env)
            r1_doc = refresh_brief_with_algorithm(work, "r1", python_exe, env)

            for algo, doc in (("v1", v1_doc), ("r1", r1_doc)):
                meta = doc["meta"]
                txt = doc["text"]
                if meta["algorithm"] != algo or meta["tokens"] > 320 or meta["estimated_tokens"] > 320:
                    raise StudyError(f"{repo_key} {algo} invalid brief metadata: {meta}")
                n_targets = verify_brief_symbol_targets(work, txt)
                if n_targets != meta["hub_count"] + meta["entrypoint_count"] + meta["recall_count"]:
                    raise StudyError(f"{repo_key} {algo} target count mismatch: {n_targets} vs {meta}")

                # Zero answer leakage across all trace expected string values >= 4 chars.
                for t in tasks:
                    if t["repo"] == repo_key and t["kind"] == "trace":
                        for k, v in t["expected"].items():
                            if isinstance(v, str) and len(v) >= 4 and v in txt:
                                raise StudyError(f"answer string {v!r} ({t['id']}.{k}) leaked into {algo} brief!")

            if r1_doc["meta"]["covered_modules"] <= v1_doc["meta"]["hub_count"] + v1_doc["meta"]["recall_count"]:
                pass  # checked explicitly below:
            v1_mods = {
                re.match(r"^(?:Recall|Hub|Entry): ([^\s]+)::", ln).group(1)
                for ln in v1_doc["text"].splitlines()
                if re.match(r"^(?:Recall|Hub|Entry): ", ln)
            }
            if r1_doc["meta"]["covered_modules"] <= len(v1_mods):
                raise StudyError(
                    f"{repo_key}: expected r1 covered_modules ({r1_doc['meta']['covered_modules']}) > v1 ({len(v1_mods)})"
                )

            repo_edits = [t for t in tasks if t["repo"] == repo_key and t["kind"] == "edit"]
            if len(repo_edits) != 4:
                raise StudyError(f"expected 4 edit tasks for {repo_key}, got {len(repo_edits)}")
            for t in repo_edits:
                subprocess.run([GIT, "checkout", "-q", "--", "."], cwd=work, check=True)
                subprocess.run([GIT, "clean", "-fdq"], cwd=work, check=True)
                ok_pre, _ = run_edit_verifier(work, repo_key, t, python_exe, spec, tiktoken_file)
                if ok_pre:
                    raise StudyError(f"{t['id']} verifier passed BEFORE reference_patch!")
                patch_path = tmp / f"{t['id']}.patch"
                patch_path.write_text(t["reference_patch"], encoding="utf-8", newline="\n")
                subprocess.run([GIT, "apply", "--ignore-whitespace", "--check", str(patch_path)], cwd=work, check=True)
                subprocess.run([GIT, "apply", "--ignore-whitespace", str(patch_path)], cwd=work, check=True)
                ok_post, detail = grade_task(t, work, python_exe, spec, tiktoken_file, "DONE", 0)[:2]
                if not ok_post:
                    raise StudyError(f"{t['id']} verifier failed AFTER reference_patch: {detail}")
            subprocess.run([GIT, "checkout", "-q", "--", "."], cwd=work, check=True)
            subprocess.run([GIT, "clean", "-fdq"], cwd=work, check=True)

            print(
                f"[self-test:{repo_key}] v1={v1_doc['meta']['tokens']}t ({len(v1_mods)} modules, "
                f"entries={v1_doc['meta']['entrypoint_count']}), "
                f"r1={r1_doc['meta']['tokens']}t ({r1_doc['meta']['covered_modules']} modules, "
                f"entries={r1_doc['meta']['entrypoint_count']}, @root={r1_doc['meta']['root_prefix']!r}), "
                f"4 edit checks verified."
            )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("self-test PASSED: all 24 tasks, 8 pytest/behavioral edit checks, 1-step symbol callability, and v1/r1 briefs verified.")


def prepare(lanes_dir: Path, repos_dir: Path, python_exe: Path, tiktoken_file: Path) -> None:
    _resolve_gh_token()
    if sha256(tiktoken_file) != "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7":
        raise StudyError(f"tiktoken file hash mismatch: {tiktoken_file}")
    os.environ["BRAINSPACE_TOKENIZER_FILE"] = str(tiktoken_file)
    os.environ["TOKENMASTER_TOKENIZER_FILE"] = str(tiktoken_file)

    spec = load_spec()
    proto_digest = sha256(PROTOCOL)
    PROTOCOL_HASH.write_text(f"{proto_digest}  PROTOCOL.md\n", encoding="utf-8", newline="\n")

    if lanes_dir.exists():
        shutil.rmtree(lanes_dir, onexc=lambda fn, p, _: (os.chmod(p, stat.S_IWRITE), fn(p)))
    lanes_dir.mkdir(parents=True)

    base_repos = lanes_dir / "templates" / "repos"
    brief_records: dict[str, dict] = {}
    probe_home = lanes_dir / "_prep_home"
    prep_env = lane_env(probe_home, python_exe=python_exe, tiktoken_file=tiktoken_file)
    ver_out = subprocess.run([COPILOT, "--version"], env=prep_env, check=True, capture_output=True, text=True).stdout.strip()

    for repo_key, rinfo in spec["repositories"].items():
        clean_work = base_repos / repo_key / "clean_work"
        materialize_clean_repo(repos_dir / repo_key, rinfo["commit"], clean_work)

        subprocess.run(
            [str(python_exe), "-B", str(SKILL / "setup.py"), str(clean_work), "--host", "copilot", "--python", str(python_exe)],
            cwd=SKILL,
            env=prep_env,
            check=True,
            capture_output=True,
            text=True,
            timeout=900,
        )
        subprocess.run([GIT, "checkout", "-q", "--", "."], cwd=clean_work, check=True)
        shutil.rmtree(clean_work / "graphify-out", ignore_errors=True)
        if not git_clean(clean_work):
            raise StudyError(f"clean_work dirty after indexing {repo_key}")

        # Snapshot cold .token-master for tm_lean (sessionStart hook disabled on tm_lean).
        cold_tm = base_repos / repo_key / "tm_cold"
        mirror(clean_work / ".token-master", cold_tm)
        cold_text = (cold_tm / "brief.md").read_text(encoding="utf-8")
        cold_meta = json.loads((cold_tm / "brief.json").read_text(encoding="utf-8"))

        # Seed shared multi-session recall.jsonl ONCE, then synthesize BOTH v1 and r1 from that exact recall.jsonl!
        seed_prior_recall(clean_work, rinfo["prior_recall_queries"])
        recall_sha = sha256(clean_work / ".token-master" / "recall.jsonl")

        v1_warm = refresh_brief_with_algorithm(clean_work, "v1", python_exe, prep_env)
        mirror(clean_work / ".token-master", base_repos / repo_key / "tm_v1_warm")

        r1_warm = refresh_brief_with_algorithm(clean_work, "r1", python_exe, prep_env)
        mirror(clean_work / ".token-master", base_repos / repo_key / "tm_r1_warm")

        if sha256(base_repos / repo_key / "tm_v1_warm" / "recall.jsonl") != recall_sha:
            raise StudyError(f"{repo_key} recall.jsonl mutated during v1 refresh")
        if sha256(base_repos / repo_key / "tm_r1_warm" / "recall.jsonl") != recall_sha:
            raise StudyError(f"{repo_key} recall.jsonl mutated during r1 refresh")

        shutil.rmtree(clean_work / ".token-master")
        if not git_clean(clean_work):
            raise StudyError(f"clean_work dirty after removing .token-master on {repo_key}")

        brief_records[repo_key] = {
            "commit": rinfo["commit"],
            "recall_jsonl_sha256": recall_sha,
            "cold_r1": {"meta": cold_meta, "text": cold_text},
            "v1_warm": {"meta": v1_warm["meta"], "text": v1_warm["text"]},
            "r1_warm": {"meta": r1_warm["meta"], "text": r1_warm["text"]},
        }

    BRIEFS_FILE.write_text(json.dumps(brief_records, indent=2) + "\n", encoding="utf-8", newline="\n")
    shutil.rmtree(probe_home, ignore_errors=True)

    arm_install_meta: dict[str, dict] = {}
    for arm in ARMS:
        lane_dir = lanes_dir / "lanes" / LANE_NAMES[arm]
        home = lane_dir / "home"
        env = lane_env(home, python_exe=python_exe, tiktoken_file=tiktoken_file)

        tmp_click = lanes_dir / f"_wire_click_{arm}"
        mirror(base_repos / "click" / "clean_work", tmp_click)
        subprocess.run(
            [str(python_exe), "-B", str(SKILL / "setup.py"), str(tmp_click), "--host", "copilot", "--python", str(python_exe)],
            cwd=SKILL,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
        shutil.rmtree(tmp_click, ignore_errors=True)

        brief_flag = "--copilot-repo-brief" if arm in BRIEF_ARMS else "--no-copilot-repo-brief"
        p_bs = subprocess.run(
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
                brief_flag,
            ],
            cwd=SKILL,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
        m_bs = re.search(r"\{.*\}", p_bs.stdout, re.S)
        if not m_bs:
            raise StudyError(f"could not parse brainspace_setup JSON: {p_bs.stdout!r}")
        bs_json = json.loads(m_bs.group(0))
        expected_hook = arm in BRIEF_ARMS
        if bool(bs_json.get("repo_brief_hook_installed")) != expected_hook:
            raise StudyError(f"{arm} repo_brief_hook_installed mismatch: {bs_json}")
        arm_install_meta[arm] = bs_json

        clear_lane_history(home)
        mirror(home / "copilot", lanes_dir / "templates" / "homes" / arm / "copilot")

        for repo_key in spec["repositories"]:
            work = lane_dir / "repos" / repo_key
            mirror(base_repos / repo_key / "clean_work", work)
            ensure_git_exclude(work)

    setup_doc = {
        "prepared_at": now_iso(),
        "study_id": spec["study_id"],
        "protocol_sha256": proto_digest,
        "tasks_sha256": sha256(TASKS_FILE),
        "briefs_sha256": sha256(BRIEFS_FILE),
        "copilot_cli_version": ver_out,
        "copilot_exe": COPILOT.replace(str(Path.home()), "<USERPROFILE>"),
        "python_exe": str(python_exe),
        "tiktoken_sha256": sha256(tiktoken_file),
        "model": MODEL,
        "reasoning_effort": REASONING,
        "arms": list(ARMS),
        "lane_names": LANE_NAMES,
        "lanes_dir": str(lanes_dir),
        "arm_install_meta": arm_install_meta,
    }
    SETUP_FILE.write_text(json.dumps(setup_doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Prepared 3 isolated lanes x 2 repos at {lanes_dir} ({ver_out}).")


def restore_task_state(lanes_dir: Path, arm: str, repo_key: str) -> tuple[Path, Path]:
    lane_dir = lanes_dir / "lanes" / LANE_NAMES[arm]
    home = lane_dir / "home"
    work = lane_dir / "repos" / repo_key

    subprocess.run([GIT, "checkout", "-q", "--", "."], cwd=work, check=True)
    subprocess.run([GIT, "clean", "-fdq"], cwd=work, check=True)
    ensure_git_exclude(work)

    tm_dst = work / ".token-master"
    if arm == "tm_lean":
        mirror(lanes_dir / "templates" / "repos" / repo_key / "tm_cold", tm_dst)
    elif arm == "tm_v1_recall":
        mirror(lanes_dir / "templates" / "repos" / repo_key / "tm_v1_warm", tm_dst)
    elif arm == "tm_r1_recall":
        mirror(lanes_dir / "templates" / "repos" / repo_key / "tm_r1_warm", tm_dst)
    else:
        raise StudyError(f"unknown arm: {arm}")

    if not git_clean(work):
        raise StudyError(f"dirty worktree before launch: {arm} / {repo_key}")
    return work, home


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
    final_answer = ""
    last_answer = ""
    copilot_version = None
    session_errors = []
    cache_state = {}
    for ev in events:
        etype = ev.get("type")
        data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
        if etype in ("session.start", "session.resume"):
            copilot_version = data.get("copilotVersion") or copilot_version
        elif etype == "tool.execution_start":
            tool_starts.append({
                "name": data.get("toolName"),
                "arguments": data.get("arguments") if isinstance(data.get("arguments"), dict) else {},
            })
        elif etype == "assistant.message":
            if isinstance(data.get("content"), str) and data["content"].strip():
                last_answer = data["content"]
                if data.get("phase") == "final_answer":
                    final_answer = data["content"]
        elif etype == "session.error":
            session_errors.append(data)
        elif etype == "session.usage_checkpoint" and not cache_state:
            pcs = data.get("promptCacheBreakState") or []
            if pcs and isinstance(pcs[0], dict):
                models = pcs[0].get("models") or {}
                m_info = models.get(MODEL) or (next(iter(models.values())) if models else None)
                if isinstance(m_info, dict):
                    cache_state = {
                        "tool_count": m_info.get("tool_count"),
                        "tool_tokens": m_info.get("tool_tokens"),
                    }
    return {
        "copilot_version": copilot_version,
        "final_answer": final_answer or last_answer,
        "tool_starts": tool_starts,
        "session_errors": session_errors,
        "cache_state": cache_state,
    }


def harvest_store_usage(home: Path, seen_row_ids: set[int]) -> dict:
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
    first_main_seen = False
    for r in rows:
        rid = int(r["id"])
        if rid in seen_row_ids:
            continue
        seen_row_ids.add(rid)
        sid = r["session_id"]
        if sid and sid not in sids:
            sids.append(sid)
        raw_details = r["token_details_json"] or "[]"
        inp = int(r["input_tokens"] or 0)
        out = int(r["output_tokens"] or 0)
        cread = int(r["cache_read_tokens"] or 0)
        cwrite = int(r["cache_write_tokens"] or 0)
        billed = int(r["total_nano_aiu"] or 0)
        recharged = recharge_row(inp, out, cread, cwrite, raw_details)
        is_sub = bool(r["agent_id"])
        if (not is_sub) and (not first_main_seen):
            first_main_seen = True
            prices = tokenomics.prices_of(raw_details)
            cold = billed + cread * (prices.get("cache_write", 0) - prices.get("cache_read", 0))
        else:
            cold = billed
        calls.append({
            "row_id": rid,
            "session_id": sid,
            "is_subagent": is_sub,
            "model": r["model"],
            "input_tokens": inp,
            "uncached_input_tokens": inp - cread - cwrite,
            "output_tokens": out,
            "cache_read_tokens": cread,
            "cache_write_tokens": cwrite,
            "total_nano_aiu": billed,
            "recharged_nano_aiu": round(recharged),
            "cold_nano_aiu": round(cold),
            "created_at": r["created_at"],
        })
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


def count_sessionstart_hooks_in_logs(home: Path) -> int:
    logs_dir = home / "copilot" / "logs"
    if not logs_dir.is_dir():
        return 0
    count = 0
    for log_file in logs_dir.glob("process-*.log"):
        txt = log_file.read_text(encoding="utf-8", errors="replace")
        count += len(re.findall(r"Executing hook\b.*sessionStart|sessionStart.*additionalContext|brainspace_sessionstart", txt))
    return count


def compute_tokenomics_session_summary(home: Path, session_id: str | None) -> dict | None:
    if not session_id:
        return None
    store_db = home / "copilot" / "session-store.db"
    if not store_db.is_file():
        return None
    calls, sessions = tokenomics.load_store(store_db)
    if not calls:
        return None
    launches = tokenomics.load_launches(home / "copilot" / "token-master" / "launches.jsonl")
    tokenomics.estimate(calls, sessions, launches)
    scalls = [c for c in calls if c["session"] == session_id]
    if not scalls:
        return None
    first_main = next((c for c in scalls if c.get("main")), scalls[0])
    return {
        "tm": any(c.get("launch") for c in scalls),
        "per_call_fixed_saved": int(first_main.get("saved_tokens", 0)),
        "fixed_saved": round(sum(c.get("saved_tokens", 0) for c in scalls), 2),
        "saved_usd": round(sum(c.get("saved_nano", 0.0) for c in scalls) / NANO_PER_USD, 6),
        "lean_usd": round(sum(c.get("lean_nano", 0.0) for c in scalls) / NANO_PER_USD, 6),
        "first_usd": round(sum(c.get("first_nano", 0.0) for c in scalls) / NANO_PER_USD, 6),
        "brief_tokens_recorded": max((int((c.get("launch") or {}).get("brief") or 0) for c in scalls), default=0),
    }


def build_copilot_cmd(home: Path, python_exe: Path, prompt: str) -> list[str]:
    copilot_args = [
        COPILOT,
        "-p",
        prompt,
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
    installed_bridge = home / "copilot" / "token-master" / "brainspace_copilot_bridge.py"
    return [str(python_exe), "-B", str(installed_bridge), "--lean", "--", *copilot_args]


def run_single_arm_task(
    *,
    lanes_dir: Path,
    arm: str,
    task: dict,
    spec: dict,
    python_exe: Path,
    tiktoken_file: Path,
    seen_rows: set[int],
    budget: UsdBudget,
) -> dict:
    budget.check()
    repo_key = task["repo"]
    work, home = restore_task_state(lanes_dir, arm, repo_key)
    shutil.rmtree(home / "copilot" / "logs", ignore_errors=True)
    env = lane_env(home, python_exe=python_exe, tiktoken_file=tiktoken_file)
    cmd = build_copilot_cmd(home, python_exe, task["prompt"])

    t0 = time.monotonic()
    started_at = now_iso()
    proc = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=420)
    wall_s = round(time.monotonic() - t0, 3)

    parsed = parse_stdout_telemetry(proc.stdout)
    usage = harvest_store_usage(home, seen_rows)
    calls = usage["calls"]
    sid = usage["session_ids"][-1] if usage["session_ids"] else None
    launch_rec = harvest_latest_launch(home)
    hook_hits = count_sessionstart_hooks_in_logs(home)

    passed, grade_reason, grade_detail = grade_task(
        task, work, python_exe, spec, tiktoken_file, parsed["final_answer"], proc.returncode
    )
    tok_summary = compute_tokenomics_session_summary(home, sid)

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    (SESSIONS_DIR / f"{task['id']}_{arm}.json").write_text(
        json.dumps(
            {
                "task_id": task["id"],
                "arm": arm,
                "session_id": sid,
                "returncode": proc.returncode,
                "wall_seconds": wall_s,
                "passed": passed,
                "grade_reason": grade_reason,
                "grade_detail": grade_detail,
                "final_answer": parsed["final_answer"],
                "tool_starts": parsed["tool_starts"],
                "calls": calls,
                "launch": launch_rec,
                "tokenomics": tok_summary,
                "stderr_tail": proc.stderr.splitlines()[-10:],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    subprocess.run([GIT, "checkout", "-q", "--", "."], cwd=work, check=True)
    subprocess.run([GIT, "clean", "-fdq"], cwd=work, check=True)

    tool_names = [t["name"] for t in parsed["tool_starts"] if t.get("name")]
    orient_calls = sum(1 for n in tool_names if n in ORIENTATION_TOOLS)
    shell_search_calls = 0
    for t in parsed["tool_starts"]:
        if t.get("name") == "powershell":
            cmd_str = str((t.get("arguments") or {}).get("command") or "")
            if "pytest" not in cmd_str:
                shell_search_calls += 1
    direct_sym_calls = sum(1 for n in tool_names if n in DIRECT_SYMBOL_TOOLS)

    inp_tok = sum(c["input_tokens"] for c in calls)
    uncached_tok = sum(c["uncached_input_tokens"] for c in calls)
    cread_tok = sum(c["cache_read_tokens"] for c in calls)
    cwrite_tok = sum(c["cache_write_tokens"] for c in calls)
    out_tok = sum(c["output_tokens"] for c in calls)
    billed_nano = sum(c["total_nano_aiu"] for c in calls)
    recharged_nano = sum(c["recharged_nano_aiu"] for c in calls)
    cold_nano = sum(c["cold_nano_aiu"] for c in calls)
    first_main = next((c for c in calls if not c["is_subagent"]), None)

    budget.add(billed_nano)

    return {
        "task_id": task["id"],
        "repo": repo_key,
        "bucket": task["bucket"],
        "kind": task["kind"],
        "arm": arm,
        "session_id": sid,
        "started_at": started_at,
        "wall_seconds": wall_s,
        "returncode": proc.returncode,
        "passed": passed,
        "grade_reason": grade_reason,
        "model_calls": len(calls),
        "first_call_input_tokens": first_main["input_tokens"] if first_main else 0,
        "first_call_cache_read_tokens": first_main["cache_read_tokens"] if first_main else 0,
        "first_call_uncached_tokens": first_main["uncached_input_tokens"] if first_main else 0,
        "input_tokens": inp_tok,
        "uncached_input_tokens": uncached_tok,
        "cache_read_tokens": cread_tok,
        "cache_write_tokens": cwrite_tok,
        "output_tokens": out_tok,
        "total_tokens": inp_tok + out_tok,
        "billed_nano_aiu": billed_nano,
        "billed_cost_usd": round(billed_nano / NANO_PER_USD, 6),
        "recharged_nano_aiu": recharged_nano,
        "recharged_cost_usd": round(recharged_nano / NANO_PER_USD, 6),
        "cold_nano_aiu": cold_nano,
        "cold_cost_usd": round(cold_nano / NANO_PER_USD, 6),
        "tool_call_count": len(tool_names),
        "tool_names": tool_names,
        "orientation_calls": orient_calls + shell_search_calls,
        "builtin_orientation_calls": sum(1 for n in tool_names if n in ("rg", "grep", "glob", "view")) + shell_search_calls,
        "mcp_orientation_calls": sum(1 for n in tool_names if n == "tokenmaster-nav-locate"),
        "direct_symbol_calls": direct_sym_calls,
        "first_tool": tool_names[0] if tool_names else None,
        "sessionstart_hook_log_hits": hook_hits,
        "brief_tokens_recorded": int((launch_rec or {}).get("brief") or 0),
        "tokenomics": tok_summary,
        "cache_state": parsed["cache_state"],
    }


def run_study(lanes_dir: Path, python_exe: Path, tiktoken_file: Path, selected_ids: set[str] | None, budget_usd: float) -> None:
    if not PROTOCOL_HASH.is_file():
        raise StudyError("PROTOCOL.sha256 missing; run prepare first")
    expected_proto = PROTOCOL_HASH.read_text(encoding="utf-8").split()[0]
    if sha256(PROTOCOL) != expected_proto:
        raise StudyError("PROTOCOL.md changed after PROTOCOL.sha256 was frozen!")

    spec = load_spec()
    tasks = [t for t in spec["tasks"] if (not selected_ids or t["id"] in selected_ids)]
    if not tasks:
        raise StudyError("no tasks matched selection")

    completed_pairs: set[tuple[str, str]] = set()
    if RUNS_FILE.is_file() and selected_ids:
        for line in RUNS_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                completed_pairs.add((r["task_id"], r["arm"]))
    else:
        RUNS_FILE.unlink(missing_ok=True)
        for arm in ARMS:
            home = lanes_dir / "lanes" / LANE_NAMES[arm] / "home"
            mirror(lanes_dir / "templates" / "homes" / arm / "copilot", home / "copilot")
            clear_lane_history(home)

    seen_rows: dict[str, set[int]] = {arm: set() for arm in ARMS}
    for arm in ARMS:
        home = lanes_dir / "lanes" / LANE_NAMES[arm] / "home"
        harvest_store_usage(home, seen_rows[arm])

    budget = UsdBudget(budget_usd)

    if not completed_pairs:
        warmups = []
        print("Running pre-study cache warmups across 3 lanes x 2 repos...")
        for repo_key in spec["repositories"]:
            def _warm(arm: str) -> dict:
                work, home = restore_task_state(lanes_dir, arm, repo_key)
                env = lane_env(home, python_exe=python_exe, tiktoken_file=tiktoken_file)
                cmd = build_copilot_cmd(home, python_exe, "Reply with ONLY the word READY.")
                t0 = time.monotonic()
                proc = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
                wall = round(time.monotonic() - t0, 3)
                usage = harvest_store_usage(home, seen_rows[arm])
                billed = sum(c["total_nano_aiu"] for c in usage["calls"])
                budget.add(billed)
                return {
                    "arm": arm,
                    "repo": repo_key,
                    "returncode": proc.returncode,
                    "wall_seconds": wall,
                    "calls": len(usage["calls"]),
                    "billed_cost_usd": round(billed / NANO_PER_USD, 6),
                }

            with ThreadPoolExecutor(max_workers=len(ARMS)) as pool:
                futs = [pool.submit(_warm, arm) for arm in ARMS]
                for fut in futs:
                    warmups.append(fut.result())
        WARMUP_FILE.write_text(json.dumps(warmups, indent=2) + "\n", encoding="utf-8", newline="\n")

    for idx, task in enumerate(tasks, 1):
        pending_arms = [a for a in ARMS if (task["id"], a) not in completed_pairs]
        if not pending_arms:
            continue
        print(f"[{idx:02d}/{len(tasks):02d}] {task['id']} ({task['repo']} / {task['bucket']} / {task['kind']}) -> {pending_arms}", flush=True)
        with ThreadPoolExecutor(max_workers=len(pending_arms)) as pool:
            fut_map = {
                arm: pool.submit(
                    run_single_arm_task,
                    lanes_dir=lanes_dir,
                    arm=arm,
                    task=task,
                    spec=spec,
                    python_exe=python_exe,
                    tiktoken_file=tiktoken_file,
                    seen_rows=seen_rows[arm],
                    budget=budget,
                )
                for arm in pending_arms
            }
            arm_records = {arm: fut_map[arm].result() for arm in pending_arms}

        with RUNS_FILE.open("a", encoding="utf-8", newline="\n") as fh:
            for arm in ARMS:
                if arm in arm_records:
                    fh.write(json.dumps(arm_records[arm], ensure_ascii=False) + "\n")

        summary_bits = [
            f"{arm}:{'PASS' if arm_records[arm]['passed'] else 'FAIL(' + arm_records[arm]['grade_reason'][:24] + ')'} "
            f"{arm_records[arm]['total_tokens']}t/{arm_records[arm]['model_calls']}c/"
            f"orient={arm_records[arm]['orientation_calls']}"
            for arm in pending_arms
        ]
        print(f"    " + " | ".join(summary_bits) + f" | spent=${budget.spent_nano / NANO_PER_USD:.3f}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_self = sub.add_parser("self-test")
    p_self.add_argument("--repos-dir", type=Path, default=DEFAULT_REPOS_DIR)
    p_self.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    p_self.add_argument("--tiktoken", type=Path, default=DEFAULT_TIKTOKEN)

    p_prep = sub.add_parser("prepare")
    p_prep.add_argument("--lanes-dir", type=Path, default=DEFAULT_LANES)
    p_prep.add_argument("--repos-dir", type=Path, default=DEFAULT_REPOS_DIR)
    p_prep.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    p_prep.add_argument("--tiktoken", type=Path, default=DEFAULT_TIKTOKEN)

    p_run = sub.add_parser("run")
    p_run.add_argument("--lanes-dir", type=Path, default=DEFAULT_LANES)
    p_run.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    p_run.add_argument("--tiktoken", type=Path, default=DEFAULT_TIKTOKEN)
    p_run.add_argument("--tasks", default="", help="Comma-separated subset of task IDs")
    p_run.add_argument("--budget-usd", type=float, default=25.0)

    args = parser.parse_args()
    if args.cmd == "self-test":
        self_test(args.repos_dir, args.python, args.tiktoken)
    elif args.cmd == "prepare":
        prepare(args.lanes_dir, args.repos_dir, args.python, args.tiktoken)
    elif args.cmd == "run":
        selected = {s.strip() for s in args.tasks.split(",") if s.strip()} or None
        run_study(args.lanes_dir, args.python, args.tiktoken, selected, args.budget_usd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
