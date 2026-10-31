"""Which session does Copilot CLI's --continue resume? Real CLI, sandbox COPILOT_HOME, BYOK with a closed upstream,
so every model call fails locally and nothing leaves the machine. Each run's prompt is a marker; the session whose
events.jsonl holds the marker is the one that run used.

  python continue_probe.py [sandbox] > continue_probe.json
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\tm-lanes\continue-probe")
HOME, REPO, OTHER, EMPTY = ROOT / "home", ROOT / "repo", ROOT / "other", ROOT / "empty"
SUB = REPO / "sub"
DIST = pathlib.Path(os.environ["LOCALAPPDATA"]) / "copilot" / "pkg" / "win32-x64" / "1.0.105"
if ROOT.exists():
    shutil.rmtree(ROOT)
for folder in (HOME, SUB, OTHER, EMPTY):
    folder.mkdir(parents=True)
subprocess.run(["git", "init", "-q", str(REPO)], check=True)
env = {k: v for k, v in os.environ.items() if not k.startswith(("COPILOT_", "TOKENMASTER_"))}
env.update(COPILOT_HOME=str(HOME), COPILOT_PROVIDER_BASE_URL="http://127.0.0.1:9", COPILOT_PROVIDER_TYPE="openai",
           COPILOT_PROVIDER_WIRE_API="responses", COPILOT_MODEL="gpt-6-astra", COPILOT_CLI_DIST_DIR=str(DIST))


def sessions():
    out = {}
    state = HOME / "session-state"
    for folder in sorted(state.iterdir()) if state.is_dir() else []:
        events = []
        try:
            events = [json.loads(line) for line in (folder / "events.jsonl").read_text(encoding="utf-8").splitlines()
                      if line.strip()]
        except (OSError, ValueError):
            pass
        start = next((e["data"] for e in events if e.get("type") == "session.start"), {})
        out[folder.name] = {"cwd": (start.get("context") or {}).get("cwd"), "version": start.get("copilotVersion"),
                            "start": start.get("startTime"),
                            "markers": [e["data"].get("content") for e in events if e.get("type") == "user.message"],
                            "resumes": sum(e.get("type") == "session.resume" for e in events)}
    return out


steps = [("m1", REPO, []), ("m2", SUB, []), ("m3", REPO, ["--continue"]), ("m4", OTHER, []),
         ("m5", REPO, ["--continue"]), ("m6", EMPTY, ["--continue"]), ("m7", REPO, []),
         ("m8", REPO, ["--resume", "@m1"]), ("m9", REPO, ["--continue"]), ("m10", SUB, ["--continue"])]
log = []
for marker, cwd, flags in steps:
    flags = [next((sid for sid, s in sessions().items() if f[1:] in s["markers"]), f) if f.startswith("@") else f
             for f in flags]
    began = time.time()
    run = subprocess.run(["copilot", *flags, "-p", marker, "--allow-all-tools"], cwd=cwd, env=env,
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    used = [sid for sid, s in sessions().items() if marker in s["markers"]]
    log.append({"marker": marker, "cwd": str(cwd), "flags": flags, "exit": run.returncode,
                "seconds": round(time.time() - began, 1), "session": used, "stderr_tail": run.stderr[-300:]})
    print(f"{marker} {flags} in {cwd.name}: {used} exit {run.returncode}", file=sys.stderr, flush=True)
    time.sleep(2)
print(json.dumps({"steps": log, "sessions": sessions()}, indent=1))
