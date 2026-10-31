"""Copilot CLI 1.0.105, real CLI, sandbox COPILOT_HOME, BYOK to a local server that records each request and answers
400 (nothing leaves the machine). Which session does --continue resume:

1. in interactive mode (-i, in its own console window, so Copilot CLI has a real terminal), and
2. while the session updated last is still in use by another Copilot CLI process (the server holds that process's
   request open)?

Each request names its session in its "Session folder: ...session-state/<id>" line. Also saved: the role of each
request's first input item.

  python continue_probe3.py [sandbox] > continue_probe3.json
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

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\tm-lanes\continue-probe3")
HOME, A, B = ROOT / "home", ROOT / "alpha", ROOT / "beta"
DIST = pathlib.Path(os.environ["LOCALAPPDATA"]) / "copilot" / "pkg" / "win32-x64" / "1.0.105"
SEEN, RELEASE = [], threading.Event()
SESSION = re.compile(r"session-state[\/]+([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")


class Capture(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        text = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8", "replace")
        try:
            body = json.loads(text)
        except ValueError:
            body = {}
        first = (body.get("input") or [{}])[0] if isinstance(body.get("input"), list) else {}
        SEEN.append({"at": time.time(), "text": text, "first_role": first.get("role") if isinstance(first, dict) else None,
                     "sessions": sorted(set(SESSION.findall(text)))})
        if "p3-hold" in text and "p3-while-held" not in text:
            RELEASE.wait(timeout=180)  # keep that Copilot CLI process, and its session, busy
        payload = b'{"error":{"message":"continue probe 3","type":"invalid_request_error"}}'
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


server = ThreadingHTTPServer(("127.0.0.1", 0), Capture)
threading.Thread(target=server.serve_forever, daemon=True).start()
if ROOT.exists():
    shutil.rmtree(ROOT)
for folder in (HOME, A, B):
    folder.mkdir(parents=True)
(HOME / "config.json").write_text(json.dumps({"trusted_folders": [str(A), str(B)], "trustedFolders": [str(A), str(B)]}),
                                  encoding="utf-8")
env = {k: v for k, v in os.environ.items() if not k.startswith(("COPILOT_", "TOKENMASTER_"))}
env.update(COPILOT_HOME=str(HOME), COPILOT_PROVIDER_BASE_URL=f"http://127.0.0.1:{server.server_address[1]}/v1",
           COPILOT_PROVIDER_TYPE="openai", COPILOT_PROVIDER_WIRE_API="responses", COPILOT_MODEL="gpt-6-astra",
           COPILOT_CLI_DIST_DIR=str(DIST))


def requests_with(marker):
    return [r for r in SEEN if marker in r["text"]]


def session_of(marker):
    found = requests_with(marker)
    return found[0]["sessions"] if found else None


def run(marker, cwd, *flags):
    began = time.time()
    done = subprocess.run(["copilot", *flags, "-p", marker, "--allow-all-tools"], cwd=cwd, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=300)
    time.sleep(2)
    return {"marker": marker, "cwd": cwd.name, "flags": list(flags), "exit": done.returncode,
            "seconds": round(time.time() - began, 1), "session": session_of(marker)}


log = [run("p3-one", A), run("p3-two", B)]
one, two = log[0]["session"][0], log[1]["session"][0]

# 1. Interactive --continue from alpha, where p3-one ran; p3-two (beta) is the session updated last.
began = time.time()
tty = subprocess.Popen(["copilot", "--continue", "-i", "p3-tty-continue", "--allow-all-tools"], cwd=A, env=env,
                       creationflags=subprocess.CREATE_NEW_CONSOLE)
while tty.poll() is None and time.time() - began < 120 and not requests_with("p3-tty-continue"):
    time.sleep(0.5)
time.sleep(3)
subprocess.run(["taskkill", "/T", "/F", "/PID", str(tty.pid)], capture_output=True)
tty.wait(timeout=60)
log.append({"marker": "p3-tty-continue", "cwd": A.name, "flags": ["--continue", "-i"], "interactive": True,
            "seconds": round(time.time() - began, 1), "session": session_of("p3-tty-continue")})
time.sleep(2)

# 2. Resume p3-one and hold its request, so that session is in use and updated last; then --continue elsewhere.
held = subprocess.Popen(["copilot", "--resume", one, "-p", "p3-hold", "--allow-all-tools"], cwd=A, env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
began = time.time()
while time.time() - began < 120 and not requests_with("p3-hold"):
    time.sleep(0.5)
log.append({"marker": "p3-hold", "cwd": A.name, "flags": ["--resume", one], "held": bool(requests_with("p3-hold")),
            "session": session_of("p3-hold")})
log.append(run("p3-while-held", B, "--continue"))
RELEASE.set()
held.wait(timeout=180)
time.sleep(2)
log.append(run("p3-after-release", B, "--continue"))
server.shutdown()
print(json.dumps({"sessions": {"one (alpha)": one, "two (beta)": two}, "steps": log,
                  "first_input_roles": sorted({str(r["first_role"]) for r in SEEN})}, indent=1))
