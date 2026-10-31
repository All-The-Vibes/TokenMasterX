"""Copilot CLI 1.0.105: in interactive mode, does --continue take a newer session from another clone of the same
GitHub repository (another folder, same remote)? Real CLI, sandbox COPILOT_HOME, BYOK to a local server that records
each request and answers 400.

  python continue_probe6.py [sandbox] > continue_probe6.json
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

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\tm-lanes\continue-probe6")
HOME = ROOT / "home"
F = {"repo": ROOT / "repo", "clone": ROOT / "clone", "o": ROOT / "o"}
DIST = pathlib.Path(os.environ["LOCALAPPDATA"]) / "copilot" / "pkg" / "win32-x64" / "1.0.105"
SEEN = []
SESSION = re.compile(r"session-state[\/]+([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")


class Capture(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        SEEN.append(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8", "replace"))
        payload = b'{"error":{"message":"continue probe 6","type":"invalid_request_error"}}'
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
for args in (["init", "-q", "-b", "main"], ["remote", "add", "origin", "https://github.com/octo-probe/epsilon.git"],
             ["-c", "user.email=p@example.com", "-c", "user.name=p", "commit", "-q", "--allow-empty", "-m", "init"]):
    for clone in ("repo", "clone"):
        subprocess.run(["git", *args], cwd=F[clone], check=True, capture_output=True)
trusted = [str(folder) for folder in F.values()]
(HOME / "config.json").write_text(json.dumps({"trusted_folders": trusted, "trustedFolders": trusted}), encoding="utf-8")
env = {k: v for k, v in os.environ.items() if not k.startswith(("COPILOT_", "TOKENMASTER_"))}
env.update(COPILOT_HOME=str(HOME), COPILOT_PROVIDER_BASE_URL=f"http://127.0.0.1:{server.server_address[1]}/v1",
           COPILOT_PROVIDER_TYPE="openai", COPILOT_PROVIDER_WIRE_API="responses", COPILOT_MODEL="gpt-6-astra",
           COPILOT_CLI_DIST_DIR=str(DIST))
names, log = {}, []


def resumed(marker, label):
    found = [text for text in SEEN if marker in text]
    ids = sorted(set(SESSION.findall(found[0]))) if found else []
    for i in ids:
        names.setdefault(i, label)
    return [names[i] for i in ids]


def captured(marker, folder, *flags):
    subprocess.run(["copilot", *flags, "-p", marker, "--allow-all-tools"], cwd=F[folder], env=env,
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    log.append({"marker": marker, "how": "prompt, output captured", "from": folder, "flags": list(flags),
                "resumed": resumed(marker, f"s-{marker}")})
    time.sleep(2)


def console(marker, folder, *args):
    began = time.time()
    proc = subprocess.Popen(["copilot", "--continue", *args, marker, "--allow-all-tools"], cwd=F[folder], env=env,
                            creationflags=subprocess.CREATE_NEW_CONSOLE)
    while proc.poll() is None and time.time() - began < 120 and not any(marker in text for text in SEEN):
        time.sleep(0.5)
    time.sleep(3)
    if proc.poll() is None:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    proc.wait(timeout=60)
    log.append({"marker": marker, "how": f"{args[0]} in a console window", "from": folder, "flags": ["--continue"],
                "resumed": resumed(marker, f"s-new-{marker}")})
    time.sleep(2)


captured("repo1", "repo")
captured("clone1", "clone")             # same GitHub repository, another folder; updated last
console("tty-i-from-repo", "repo", "-i")  # interactive: its own folder's repo1, or the other clone's newer clone1?
server.shutdown()
print(json.dumps({"steps": log, "sessions": names}, indent=1))
