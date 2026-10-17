"""Test-only observer: capture synthetic hook IO and forward it byte-for-byte."""
import json
import subprocess
import sys
from pathlib import Path

destination, hook, python = sys.argv[1:4]
raw = sys.stdin.buffer.read()
result = subprocess.run([python, "-X", "utf8", hook, "--host", "claude"],
                        input=raw, capture_output=True, timeout=20)
with Path(destination).open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({"input": json.loads(raw), "output": result.stdout.decode("utf-8"),
                             "exit_code": result.returncode,
                             "stderr": result.stderr.decode("utf-8", errors="replace")}) + "\n")
sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
raise SystemExit(result.returncode)
