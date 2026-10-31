"""Copilot CLI 1.0.105, real CLI, sandbox COPILOT_HOME, BYOK to a local server that records each request and answers
400. Two questions:

1. With the prompt piped on stdin and no -p, does --continue follow prompt mode (the session updated last anywhere) or
   interactive mode (the working folder's session)?
2. When does an interactive launch with no first prompt (its own console window) create its session in the store,
   counted from the moment the process starts?

  python continue_probe7.py [sandbox] > continue_probe7.json
"""
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\tm-lanes\continue-probe7")
HOME = ROOT / "home"
F = {name: ROOT / name for name in ("x", "y", "z")}
DIST = pathlib.Path(os.environ["LOCALAPPDATA"]) / "copilot" / "pkg" / "win32-x64" / "1.0.105"
SEEN = []
SESSION = re.compile(r"session-state[\/]+([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")


class Capture(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        SEEN.append(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8", "replace"))
        payload = b'{"error":{"message":"continue probe 7","type":"invalid_request_error"}}'
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
trusted = [str(folder) for folder in F.values()]
(HOME / "config.json").write_text(json.dumps({"trusted_folders": trusted, "trustedFolders": trusted}), encoding="utf-8")
env = {k: v for k, v in os.environ.items() if not k.startswith(("COPILOT_", "TOKENMASTER_"))}
env.update(COPILOT_HOME=str(HOME), COPILOT_PROVIDER_BASE_URL=f"http://127.0.0.1:{server.server_address[1]}/v1",
           COPILOT_PROVIDER_TYPE="openai", COPILOT_PROVIDER_WIRE_API="responses", COPILOT_MODEL="gpt-6-astra",
           COPILOT_CLI_DIST_DIR=str(DIST))
names, log = {}, {}


def resumed(marker, label):
    found = [text for text in SEEN if marker in text]
    ids = sorted(set(SESSION.findall(found[0]))) if found else []
    for i in ids:
        names.setdefault(i, label)
    return [names[i] for i in ids]


def prompt(marker, folder):
    subprocess.run(["copilot", "-p", marker, "--allow-all-tools"], cwd=F[folder], env=env, capture_output=True,
                   text=True, encoding="utf-8", errors="replace", timeout=300)
    resumed(marker, f"s-{marker}")
    time.sleep(2)


prompt("x1", "x")
prompt("y1", "y")  # updated last
piped = subprocess.run(["copilot", "--continue", "--allow-all-tools"], cwd=F["x"], env=env, input="piped-from-x\n",
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
log["piped --continue from x"] = {"exit": piped.returncode, "resumed": resumed("piped-from-x", "s-new-piped"),
                                  "prompt rule would give": "s-y1", "interactive rule would give": "s-x1"}
time.sleep(2)


def rows():
    try:
        db = sqlite3.connect(f"{(HOME / 'session-store.db').resolve().as_uri()}?mode=ro", uri=True)
        try:
            return db.execute("select id, cwd, created_at from sessions").fetchall()
        finally:
            db.close()
    except sqlite3.Error:
        return []


before = {row[0] for row in rows()}
started = datetime.now(timezone.utc)
tty = subprocess.Popen(["copilot", "--allow-all-tools"], cwd=F["z"], env=env, creationflags=subprocess.CREATE_NEW_CONSOLE)
seen_at, created = None, None
while time.time() - started.timestamp() < 45 and seen_at is None:
    new = [row for row in rows() if row[0] not in before]
    if new:
        seen_at, created = time.time(), new[0][2]
    time.sleep(0.5)
time.sleep(1)
subprocess.run(["taskkill", "/T", "/F", "/PID", str(tty.pid)], capture_output=True)
tty.wait(timeout=60)
folders = sorted(p.name for p in (HOME / "session-state").iterdir()) if (HOME / "session-state").is_dir() else []
log["interactive launch, no prompt"] = {
    "process started": started.isoformat(timespec="milliseconds"),
    "session created_at": created,
    "seconds from process start to created_at": (
        round((datetime.fromisoformat(created.replace("Z", "+00:00")) - started).total_seconds(), 1) if created else None),
    "row seen within 45 s": seen_at is not None, "session folders": len(folders)}
server.shutdown()
print(json.dumps({"results": log, "sessions": names}, indent=1))
