"""Copilot CLI 1.0.105: which session does interactive --continue (-i, own console window) resume? Real CLI, sandbox
COPILOT_HOME, BYOK to a local server that records each request and answers 400. Each request names its session in its
"Session folder" line. Folders: x, y, w, z (no repository) and repo with a GitHub remote, plus repo/sub.

  python continue_probe4.py [sandbox] > continue_probe4.json
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\tm-lanes\continue-probe4")
HOME = ROOT / "home"
F = {name: ROOT / name for name in ("x", "y", "w", "z", "repo")}
F["sub"] = ROOT / "repo" / "sub"
DIST = pathlib.Path(os.environ["LOCALAPPDATA"]) / "copilot" / "pkg" / "win32-x64" / "1.0.105"
SEEN = []
SESSION = re.compile(r"session-state[\/]+([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")


class Capture(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        SEEN.append(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8", "replace"))
        payload = b'{"error":{"message":"continue probe 4","type":"invalid_request_error"}}'
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


server = ThreadingHTTPServer(("127.0.0.1", 0), Capture)
threading.Thread(target=server.serve_forever, daemon=True).start()
if ROOT.exists():
    shutil.rmtree(ROOT)
for folder in (HOME, *F.values()):
    folder.mkdir(parents=True, exist_ok=True)
for args in (["init", "-q", "-b", "main"], ["remote", "add", "origin", "https://github.com/octo-probe/gamma.git"],
             ["-c", "user.email=p@example.com", "-c", "user.name=p", "commit", "-q", "--allow-empty", "-m", "init"]):
    subprocess.run(["git", *args], cwd=F["repo"], check=True, capture_output=True)
trusted = [str(folder) for folder in F.values()]
(HOME / "config.json").write_text(json.dumps({"trusted_folders": trusted, "trustedFolders": trusted}), encoding="utf-8")
env = {k: v for k, v in os.environ.items() if not k.startswith(("COPILOT_", "TOKENMASTER_"))}
env.update(COPILOT_HOME=str(HOME), COPILOT_PROVIDER_BASE_URL=f"http://127.0.0.1:{server.server_address[1]}/v1",
           COPILOT_PROVIDER_TYPE="openai", COPILOT_PROVIDER_WIRE_API="responses", COPILOT_MODEL="gpt-6-astra",
           COPILOT_CLI_DIST_DIR=str(DIST))
names, log = {}, []


def session_of(marker):
    found = [text for text in SEEN if marker in text]
    ids = sorted(set(SESSION.findall(found[0]))) if found else []
    return [names.get(i, i) for i in ids]


def prompt(marker, folder, *flags):
    subprocess.run(["copilot", *flags, "-p", marker, "--allow-all-tools"], cwd=F[folder], env=env,
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    found = [text for text in SEEN if marker in text]
    for i in (sorted(set(SESSION.findall(found[0]))) if found else []):
        names.setdefault(i, f"s-{marker}")
    log.append({"marker": marker, "mode": "prompt", "from": folder, "flags": list(flags), "resumed": session_of(marker)})
    time.sleep(2)


def interactive(marker, folder):
    began = time.time()
    proc = subprocess.Popen(["copilot", "--continue", "-i", marker, "--allow-all-tools"], cwd=F[folder], env=env,
                            creationflags=subprocess.CREATE_NEW_CONSOLE)
    while proc.poll() is None and time.time() - began < 120 and not any(marker in text for text in SEEN):
        time.sleep(0.5)
    time.sleep(3)
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    proc.wait(timeout=60)
    found = [text for text in SEEN if marker in text]
    for i in (sorted(set(SESSION.findall(found[0]))) if found else []):
        names.setdefault(i, f"s-new-from-{marker}")
    log.append({"marker": marker, "mode": "interactive --continue", "from": folder, "resumed": session_of(marker)})
    time.sleep(2)


prompt("x1", "x")
prompt("r1", "repo")
prompt("y1", "y")                    # updated last
interactive("i-from-z", "z")         # no session in z, no repository
interactive("i-from-sub", "sub")     # no session in repo/sub; one at the repository root
interactive("i-from-x", "x")         # x has a session, others are newer
prompt("w1", "w")                    # updated last
prompt("p-from-x", "x", "--continue")  # prompt mode, for comparison
prompt("x2", "x")                    # a second session in x, created last
prompt("x1-again", "x", "--resume", next(i for i, n in names.items() if n == "s-x1"))
interactive("i-from-x-2", "x")       # x1 updated last in x, x2 created last in x
server.shutdown()
print(json.dumps({"steps": log, "sessions": names}, indent=1))
