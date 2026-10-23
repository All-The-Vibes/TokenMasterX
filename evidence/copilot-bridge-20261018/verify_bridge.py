"""Live check of brainspace_copilot_bridge.py with the real GitHub Copilot CLI. A functional check, not a savings study.

Chain: Copilot CLI (BYOK) -> [TokenMaster bridge] -> relay -> api.githubcopilot.com. The relay adds the GitHub
Copilot credential in memory, as the PRS gateways did, and logs usage numbers per model call (relay-usage-<run>.jsonl).
Sessions run one after another in one temporary workspace and one temporary Copilot home:
  stock-1, stock-2      no bridge
  bridge-1, bridge-2    through the bridge (bridge-usage-<run>.jsonl)
  bridge-edit           through the bridge; a one-line edit, checked with git
  hook                  no bridge; the default install's v6 view hook (brainspace_setup.py --host copilot)
Request bodies and CLI output stay in captures/ (local only: they contain the Copilot CLI system prompt).
"""
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SKILL = REPO / "token-master-plugin/skills/token-master"
TOKENIZER = REPO / "evidence/controlled-scorecard-20261008/batch-001/cl100k_base.tiktoken"
os.environ.setdefault("BRAINSPACE_TOKENIZER_FILE", str(TOKENIZER))
sys.path.insert(0, str(REPO / "token-master-plugin/evals"))
sys.path.insert(0, str(SKILL))
import run_prs1_study as p1  # noqa: E402
import brainspace_copilot_bridge as cb  # noqa: E402
from brainspace import tokens  # noqa: E402
from brainspace.v6_shaping import shape_tool_result  # noqa: E402

RUN = sys.argv[1] if len(sys.argv) > 1 else "run2"
ROOT = Path(os.environ["TEMP"]) / "opencode" / f"bridge-live-{RUN}"
SNAPSHOT = Path(os.environ["TEMP"]) / "opencode" / "prs1" / "snapshot"
CAPTURES = HERE / "captures" / RUN
RELAY_LOG, BRIDGE_LOG = HERE / f"relay-usage-{RUN}.jsonl", HERE / f"bridge-usage-{RUN}.jsonl"
MODEL = "gpt-6-astra"
COPILOT = shutil.which("copilot") or str(Path(os.environ["LOCALAPPDATA"]) / "Microsoft/WinGet/Links/copilot.exe")
# The WinGet copilot.exe runs the newest package under %LOCALAPPDATA%\copilot\pkg; without one it runs its bundled
# build, 1.0.78-3. These runs isolated LOCALAPPDATA without the package, so they ran 1.0.78-3. Later runs copy the
# installed package into the isolated profile, but every run passes --no-auto-update, which also makes the launcher run
# the bundled build. So all runs here used 1.0.78-3 (corrected 2026-10-23; cli_version below omits that flag).
INSTALLED_PKG = Path(os.environ["LOCALAPPDATA"]) / "copilot" / "pkg"
BUNDLED_RUNS = {"run1", "run2", "hook3", "hook4", "hook5", "hook6", "tui"}
TARGET = "token-master-plugin/skills/token-master/brainspace/ccr.py"
TASKS = {
    "find": ("Which file under token-master-plugin/skills/token-master/brainspace defines the function "
             "`round_alpha`? Reply with the relative path only.", "certification.py"),
    "value": (f"What is the value of _METADATA_LIMIT in {TARGET}? Reply with the number only.", "4096"),
    "edit": (f"In {TARGET}, change _METADATA_LIMIT from 4096 to 8192. Change nothing else.", None),
}


class Relay(cb.Bridge):
    """Eval-only upstream: records each request locally and replaces the client's credential."""

    def __init__(self, token, **kwargs):
        super().__init__("https://api.githubcopilot.com", **kwargs)
        self.token, self.label, self.n = token, "none", 0

    def prepare(self, path, body):
        if body is None or not path.split("?")[0].endswith("/responses"):
            return body, {}
        with self._lock:
            self.n += 1
            n = self.n
        (CAPTURES / f"{self.label}-{n:03d}.json").write_bytes(body)
        try:
            request = json.loads(body)
        except ValueError:
            return body, {"label": self.label}
        items = request.get("input") if isinstance(request.get("input"), list) else []
        return body, {"label": self.label, "n": n, "prefix_sha256": cb._prefix_digest(request),
                      "tool_outputs": sum(isinstance(i, dict) and i.get("type") == "function_call_output" for i in items)}

    def upstream_headers(self, headers):
        out = {k: v for k, v in super().upstream_headers(headers).items()
               if k.lower() not in ("authorization", "x-api-key")}
        out.update({"Authorization": f"Bearer {self.token}", "Copilot-Integration-Id": "vscode-chat",
                    "Editor-Version": "vscode/1.100.0"})
        return out


def cli_env(home: Path, base_url: str) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith("COPILOT_") and k.upper() not in ("GH_TOKEN", "GITHUB_TOKEN")}
    profile = home / "profile"
    env.update({"HOME": str(profile), "USERPROFILE": str(profile), "APPDATA": str(profile / "AppData/Roaming"),
                "LOCALAPPDATA": str(profile / "AppData/Local"), "COPILOT_HOME": str(home / "copilot"),
                "COPILOT_OFFLINE": "true", "COPILOT_ALLOW_ALL": "true", "COPILOT_MODEL": MODEL,
                "COPILOT_PROVIDER_BASE_URL": base_url, "COPILOT_PROVIDER_TYPE": "openai",
                "COPILOT_PROVIDER_WIRE_API": "responses", "COPILOT_PROVIDER_API_KEY": "relay-adds-the-credential",
                "COPILOT_PROVIDER_MODEL_ID": MODEL, "COPILOT_PROVIDER_WIRE_MODEL": MODEL,
                "COPILOT_PROVIDER_MAX_PROMPT_TOKENS": "128000", "COPILOT_PROVIDER_MAX_OUTPUT_TOKENS": "4096",
                "BRAINSPACE_TOKENIZER_FILE": str(TOKENIZER)})
    for key in ("APPDATA", "LOCALAPPDATA", "COPILOT_HOME"):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    pkg = Path(env["LOCALAPPDATA"]) / "copilot" / "pkg"
    if RUN not in BUNDLED_RUNS and INSTALLED_PKG.is_dir() and not pkg.exists():
        shutil.copytree(INSTALLED_PKG, pkg)  # program files only; lets the isolated launcher run the installed CLI
    return env


def cli_version(home: Path) -> str:
    """The version that the isolated environment actually runs."""
    out = subprocess.run([COPILOT, "--version"], env=cli_env(home, "http://127.0.0.1:9"), capture_output=True,
                         text=True).stdout
    return out.splitlines()[0] if out else "unknown"


def run(label, prompt, *, bridge, home, ws, relay, expect=None):
    relay.label = label
    args = [COPILOT, "-p", prompt, "--model", MODEL, "--reasoning-effort", "low", "--allow-all-tools",
            "--no-ask-user", "--no-auto-update", "--disable-builtin-mcps", "--output-format", "json"]
    if bridge:
        args = [sys.executable, "-B", str(SKILL / "brainspace_copilot_bridge.py"),
                "--log", str(BRIDGE_LOG), "--", *args]
    start = time.time()
    try:
        proc = subprocess.run(args, cwd=ws, env=cli_env(home, relay.url), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=480)
        code, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as error:
        code, out, err = "timeout", str(error.stdout or ""), str(error.stderr or "")
    (CAPTURES / f"{label}-stdout.txt").write_text(out, encoding="utf-8")
    (CAPTURES / f"{label}-stderr.txt").write_text(err, encoding="utf-8")
    row = {"label": label, "bridge": bridge, "exit": code, "start": round(start, 3), "end": round(time.time(), 3)}
    if expect is not None:
        row["answer_found"] = expect in out
    print(json.dumps(row), flush=True)
    return row


def billed(r):
    return ((r.get("input") or 0) - (r.get("cached") or 0) - (r.get("cache_write") or 0) + 0.1 * (r.get("cached") or 0)
            + 1.25 * (r.get("cache_write") or 0) + 5 * (r.get("output") or 0))


def pick_doc(ws):
    """A doc above v6's read budget whose digest fits the hook's 9,000-byte output cap."""
    best = None
    for path in sorted((ws / "token-master-plugin/docs").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        size = tokens.count_tokens(text)
        shaped = shape_tool_result("view", {"path": str(path)}, text, tokens.count_tokens)
        if size > 4500 and shaped != text and len(shaped.encode()) < 6000 and (best is None or size > best[1]):
            best = (path.relative_to(ws).as_posix(), size, len(shaped.encode()))
    return best


def hook_check(docs, directory=None):
    """Whole-file view results in the session's last request, and whether the hook's v6 digest replaced them."""
    views = []
    for capture in sorted((directory or CAPTURES).glob("hook-*.json"))[-1:]:
        items = json.loads(capture.read_bytes()).get("input") or []
        calls = {i.get("call_id"): i for i in items if isinstance(i, dict) and i.get("type") == "function_call"}
        for item in items:
            if not isinstance(item, dict) or item.get("type") != "function_call_output":
                continue
            call = calls.get(item.get("call_id")) or {}
            name = next((doc for doc in docs if doc.split("/")[-1] in (call.get("arguments") or "")), None)
            if call.get("name") == "view" and name:
                output = item.get("output") or ""
                try:
                    keys = sorted(json.loads(call.get("arguments") or "{}"))
                except (TypeError, ValueError):
                    keys = None
                views.append({"capture": capture.name, "file": name, "arg_keys": keys, "chars": len(output),
                              "shaped_by_hook": "[Outline only" in output,
                              "refused_as_too_large": output.startswith("File too large")})
    return views


def main():
    tokens.count_tokens("warm-up")  # before any server thread
    CAPTURES.mkdir(parents=True, exist_ok=True)
    for path in (RELAY_LOG, BRIDGE_LOG):
        path.unlink(missing_ok=True)
    if ROOT.exists():
        p1.remove_tree(ROOT)
    ws = ROOT / "ws"
    shutil.copytree(SNAPSHOT, ws)
    for command in (["init", "-q"], ["add", "-A"], ["-c", "user.name=check", "-c", "user.email=check@example.invalid",
                                                    "commit", "-qm", "snapshot"]):
        subprocess.run([str(p1.GIT_EXE), *command], cwd=ws, check=True, capture_output=True)
    version = cli_version(ROOT / "home")
    sessions = []
    with Relay(p1.load_copilot_token(), log=RELAY_LOG) as relay:
        home = ROOT / "home"
        for label, task, bridge in (("stock-1", "find", False), ("stock-2", "value", False),
                                    ("bridge-1", "find", True), ("bridge-2", "value", True),
                                    ("bridge-edit", "edit", True)):
            sessions.append(run(label, TASKS[task][0], bridge=bridge, home=home, ws=ws, relay=relay,
                                expect=TASKS[task][1]))
        diff = subprocess.run([str(p1.GIT_EXE), "diff", "--numstat"], cwd=ws, capture_output=True, text=True).stdout
        status = subprocess.run([str(p1.GIT_EXE), "status", "--porcelain"], cwd=ws, capture_output=True, text=True).stdout
        edit = {"numstat": diff.split(), "status_paths": [line[3:] for line in status.splitlines()],
                "target_changed": "_METADATA_LIMIT = 8192" in (ws / TARGET).read_text(encoding="utf-8")}
        edit["correct"] = edit["numstat"] == ["1", "1", TARGET] and edit["target_changed"]
        hook_home = ROOT / "hook-home"
        install = subprocess.run([sys.executable, "-B", str(SKILL / "brainspace_setup.py"), "--host", "copilot",
                                  "--python", sys.executable, "--tokenizer-file", str(TOKENIZER)],
                                 cwd=SKILL, env=cli_env(hook_home, "http://127.0.0.1:9"), capture_output=True, text=True)
        doc = pick_doc(ws)
        hook = {"install_exit": install.returncode, "doc": doc}
        if install.returncode == 0 and doc:
            prompt = f"Open {doc[0]} with one view call on the whole file (no view_range). Then reply with its first line only."
            sessions.append(run("hook", prompt, bridge=False, home=hook_home, ws=ws, relay=relay))
            hook["views"] = hook_check([doc[0]])
        else:
            hook["install_tail"] = (install.stdout + install.stderr)[-800:]
    rows = [json.loads(line) for line in RELAY_LOG.read_text(encoding="utf-8").splitlines()]
    bridge_rows = [json.loads(line) for line in BRIDGE_LOG.read_text(encoding="utf-8").splitlines()] \
        if BRIDGE_LOG.exists() else []
    for s in sessions:
        mine = [r for r in rows if r.get("label") == s["label"]]
        main_prefix = Counter(r.get("prefix_sha256") for r in mine).most_common(1)[0][0] if mine else None
        first = next((r for r in mine if r.get("prefix_sha256") == main_prefix), None)
        s.update(calls=len(mine), prefix_sha256=main_prefix, billed=round(sum(billed(r) for r in mine), 1),
                 first_call={k: first.get(k) for k in ("input", "cached", "cache_write", "output")} if first else None)
        if s["bridge"]:
            seen = [r for r in bridge_rows if s["start"] <= r["t"] <= s["end"]]
            s["bridge_rows"] = {"calls": len(seen), "stable_prefix": sum(r["stable_prefix"] for r in seen),
                                "shaped_results": sum(r["shaped"] for r in seen)}
    result = {"date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "run": RUN, "copilot_version": version,
              "model": MODEL, "kind": "functional live check, not a savings study", "sessions": sessions,
              "edit": edit, "hook": hook}
    (HERE / f"results-{RUN}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("copilot_version", "edit", "hook")}, indent=1))


if __name__ == "__main__":
    main()
