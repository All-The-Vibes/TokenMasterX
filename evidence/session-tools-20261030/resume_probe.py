"""Copilot CLI 1.0.105, real CLI, sandbox COPILOT_HOME, BYOK pointed at a local server that records each request and
answers 400, so nothing leaves the machine. Two questions:

1. With the same --excluded-tools, does a resumed session send the same tools, instructions and history prefix as its
   first launch? (The premise of reusing a session's tool list.) And with a different list, do the tools differ?
2. Which session does --continue pick when folders belong to GitHub repositories (a remote), on two branches, or to
   no repository?

  python resume_probe.py [sandbox] > resume_probe.json
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\tm-lanes\resume-probe")
HOME, A, B, OTHER, OTHER2 = ROOT / "home", ROOT / "alpha", ROOT / "beta", ROOT / "other", ROOT / "other2"
DIST = pathlib.Path(os.environ["LOCALAPPDATA"]) / "copilot" / "pkg" / "win32-x64" / "1.0.105"
LEAN = ["session_store_sql", "task", "read_agent", "write_agent", "list_agents", "skill", "sql", "read_powershell",
        "stop_powershell", "list_powershell", "fetch_copilot_cli_documentation", "run_dynamic_workflow",
        "dynamic_workflows_manage"]
SEEN = []


class Capture(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            SEEN.append({"path": self.path, "body": json.loads(body)})
        except ValueError:
            SEEN.append({"path": self.path, "body": None})
        payload = b'{"error":{"message":"resume probe: no model here","type":"invalid_request_error"}}'
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()


server = ThreadingHTTPServer(("127.0.0.1", 0), Capture)
threading.Thread(target=server.serve_forever, daemon=True).start()
if ROOT.exists():
    shutil.rmtree(ROOT)
for folder in (HOME, A / "sub", B / "sub", OTHER, OTHER2):
    folder.mkdir(parents=True)


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.email=probe@example.com", "-c", "user.name=probe", *args], cwd=cwd, check=True,
                   capture_output=True)


for repo, name in ((A, "alpha"), (B, "beta")):
    git(repo, "init", "-q", "-b", "main")
    git(repo, "remote", "add", "origin", f"https://github.com/octo-probe/{name}.git")
    git(repo, "commit", "-q", "--allow-empty", "-m", "init")
env = {k: v for k, v in os.environ.items() if not k.startswith(("COPILOT_", "TOKENMASTER_"))}
env.update(COPILOT_HOME=str(HOME), COPILOT_PROVIDER_BASE_URL=f"http://127.0.0.1:{server.server_address[1]}/v1",
           COPILOT_PROVIDER_TYPE="openai", COPILOT_PROVIDER_WIRE_API="responses", COPILOT_MODEL="gpt-6-astra",
           COPILOT_CLI_DIST_DIR=str(DIST))


def sessions():
    out = {}
    state = HOME / "session-state"
    for folder in sorted(state.iterdir()) if state.is_dir() else []:
        try:
            events = [json.loads(line) for line in (folder / "events.jsonl").read_text(encoding="utf-8").splitlines()
                      if line.strip()]
        except (OSError, ValueError):
            continue
        start = next((e["data"] for e in events if e.get("type") == "session.start"), {})
        out[folder.name] = {"cwd": (start.get("context") or {}).get("cwd"), "start": start.get("startTime"),
                            "markers": [e["data"].get("content") for e in events if e.get("type") == "user.message"]}
    return out


def session_of(marker):
    return next((sid for sid, s in sessions().items() if marker in s["markers"]), None)


def text_of(body):
    return json.dumps(body.get("input") if body else None)


log = []


def launch(marker, cwd, *flags, excluded=LEAN):
    flags = [session_of(f[1:]) if f.startswith("@") else f for f in flags]
    began, first = time.time(), len(SEEN)
    run = subprocess.run(["copilot", *flags, "-p", marker, "--allow-all-tools", "--excluded-tools", *excluded],
                         cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                         timeout=300)
    mine = [r for r in SEEN[first:] if r["body"] and marker in text_of(r["body"])]
    body = mine[0]["body"] if mine else None
    entry = {"marker": marker, "cwd": str(cwd.relative_to(ROOT)), "flags": flags, "excluded": len(excluded),
             "exit": run.returncode, "seconds": round(time.time() - began, 1), "session": session_of(marker),
             "requests": len(SEEN) - first,
             "tools": sorted(t.get("name") or t.get("type") for t in body.get("tools", [])) if body else None,
             "instructions": body.get("instructions") if body else None, "input": body.get("input") if body else None}
    log.append(entry)
    print(f"{marker} {flags} in {entry['cwd']}: session {str(entry['session'])[:8]}, {entry['requests']} requests, "
          f"{len(entry['tools'] or [])} tools, {entry['seconds']} s", file=sys.stderr, flush=True)
    time.sleep(2)
    return entry


a1 = launch("alpha-one", A)
a2 = launch("alpha-two", A, "--resume", "@alpha-one")
a3 = launch("alpha-three", A, "--resume", "@alpha-one", excluded=[t for t in LEAN if t != "session_store_sql"])
b1 = launch("beta-one", B)
o1 = launch("other-one", OTHER)
c1 = launch("cont-alpha-root", A, "--continue")
c2 = launch("cont-beta-sub", B / "sub", "--continue")
c3 = launch("cont-other2", OTHER2, "--continue")
git(A, "checkout", "-q", "-b", "feature")
f1 = launch("alpha-feature", A)
git(A, "checkout", "-q", "main")
c4 = launch("cont-alpha-main", A, "--continue")
s1 = launch("alpha-sub", A / "sub")
c5 = launch("cont-alpha-root-2", A, "--continue")


def same_prefix(first, later):
    a, b = first["input"] or [], later["input"] or []
    return len(b) >= len(a) and b[:len(a)] == a


premise = {
    "resume_same_list_same_tools": a1["tools"] == a2["tools"],
    "resume_same_list_same_instructions": a1["instructions"] == a2["instructions"],
    "resume_history_prefix_kept": same_prefix(a1, a2),
    "resume_other_list_other_tools": a1["tools"] != a3["tools"],
    "tool_difference": sorted(set(a3["tools"] or []) ^ set(a1["tools"] or [])),
}
if a1["instructions"] != a2["instructions"] and a1["instructions"] and a2["instructions"]:
    x, y = a1["instructions"], a2["instructions"]
    at = next((i for i, (p, q) in enumerate(zip(x, y)) if p != q), min(len(x), len(y)))
    premise["instructions_first_difference"] = {"at": at, "first": x[max(0, at - 80):at + 120],
                                                "resume": y[max(0, at - 80):at + 120]}
for entry in log:
    entry.pop("input", None)
    entry["instructions"] = (entry["instructions"] or "")[:0] + f"<{len(entry['instructions'] or '')} chars>"
print(json.dumps({"premise": premise, "steps": log, "sessions": sessions()}, indent=1))
server.shutdown()
