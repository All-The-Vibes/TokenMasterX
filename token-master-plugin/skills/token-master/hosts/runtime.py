"""Explicit tested interpreter; no dependency resolution or network at launch.

Provision the existing dependencies separately, then pass --python PATH. The
installer probes imports and records the exact installed distribution inventory
in runtime.json. That receipt is evidence of the tested environment, not a claim
that an externally mutated interpreter is immutable or a portable lockfile.
"""
import json
import hashlib
from pathlib import Path
import shutil
import subprocess

DEPENDENCIES = ("mcp", "tree-sitter", "tree-sitter-python", "tree-sitter-rust", "tiktoken")
REQUIREMENTS = Path(__file__).resolve().parents[3] / "requirements-runtime.lock.txt"


def validate_runtime(python, dependencies=DEPENDENCIES):
    manifest = REQUIREMENTS.read_bytes()
    pins = dict(line.split("==", 1) for raw in manifest.decode("utf-8").splitlines()
                if (line := raw.strip()) and not line.startswith("#"))
    executable = shutil.which(python) or python
    # Keep a virtualenv's executable symlink path on POSIX. Resolving it to the
    # base interpreter silently discards that environment's installed packages.
    executable = str(Path(executable).expanduser().absolute())
    code = """
import importlib, importlib.metadata, json, sys
deps = json.loads(sys.argv[1])
for name in deps:
    importlib.import_module(name.replace('-', '_'))
print(json.dumps({'python': sys.executable, 'python_version': sys.version,
                  'versions': {name: importlib.metadata.version(name) for name in deps},
                  'inventory': {d.metadata['Name']: d.version for d in importlib.metadata.distributions()}}))
"""
    try:
        result = subprocess.run([executable, "-X", "utf8", "-c", code, json.dumps(dependencies)],
                                capture_output=True, encoding="utf-8", check=True, timeout=30)
        receipt = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ValueError("runtime preflight failed; provision the existing dependencies separately "
                         "and pass --python PATH. No configuration was installed.") from exc
    receipt["python"] = executable
    inventory = {name.lower().replace("_", "-"): version for name, version in receipt["inventory"].items()}
    for name, version in inventory.items():
        if name in pins and version != pins[name]:
            raise ValueError(f"runtime version mismatch for {name}; expected {pins[name]}. "
                             "Provision requirements-runtime.txt separately.")
    receipt["launch_network_required"] = False
    receipt["requirements_sha256"] = hashlib.sha256(manifest).hexdigest()
    receipt["requirements_path"] = str(REQUIREMENTS)
    receipt["dependency_contract"] = "exact runtime dependency pins; lock validated on Windows CPython 3.12"
    return receipt


def runtime_entry(python, script, extra=()):
    return {"command": str(Path(python).expanduser().absolute()),
            "args": ["-X", "utf8", str(Path(script).resolve()), *extra],
            "env": {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}}


def hook_entry(python, script, host="claude"):
    # Claude's documented exec form (args present) has no shell tokenization on
    # any platform. Do not construct shell strings for executable/script paths.
    entry = runtime_entry(python, script, ["--host", host])
    return {"type": "command", "command": entry["command"], "args": entry["args"]}


def copilot_hook_entry(python, script, tokenizer):
    from brainspace.host_output import COPILOT_CONTRACT

    entry = runtime_entry(python, script, [
        "--host", "copilot", "--contract", COPILOT_CONTRACT,
        "--tokenizer-file", str(Path(tokenizer).resolve()),
    ])
    return {"type": "command", "matcher": "view", "exec": entry["command"],
            "args": entry["args"], "timeoutSec": 20}
