"""Diagnostic shim for the temporary hook home only: log Copilot CLI's hook input and the real hook's output."""
import json
from pathlib import Path
import subprocess
import sys
import time

LOG = Path(__file__).resolve().parent / "hook-shim-log"
LOG.mkdir(exist_ok=True)
data = sys.stdin.buffer.read()
stamp = time.time_ns()
(LOG / f"{stamp}-in.json").write_bytes(data)
proc = subprocess.run([sys.executable, "-X", "utf8", *sys.argv[1:]], input=data, capture_output=True)
(LOG / f"{stamp}-out.json").write_bytes(proc.stdout)
(LOG / f"{stamp}-meta.json").write_text(json.dumps({"exit": proc.returncode, "stdout_bytes": len(proc.stdout),
                                                    "stderr_tail": proc.stderr.decode("utf-8", "replace")[-1500:]}))
sys.stdout.buffer.write(proc.stdout)
sys.exit(proc.returncode)
