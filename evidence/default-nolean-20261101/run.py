"""Default TokenMaster (no --lean) against stock Copilot CLI under default routing: one shard of default_routing_ab.py.

The harness starts the tm arm through the launcher with --lean. This wrapper drops that flag before the launch, so the
launcher passes Copilot CLI's command through unchanged, as it does by default since e28d1ad. It also pins Copilot CLI
1.0.105, the latest release, and records no lean exclusions. Everything else is the harness. See PROTOCOL.md.

  python run.py <default_routing_ab.py arguments>
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import types

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "token-master-plugin/evals"))
import default_routing_ab as dr  # noqa: E402
import run_prs5_study as p5  # noqa: E402

dr.PACKAGE = "1.0.105"
dr.CLI_VERSION = f"GitHub Copilot CLI {dr.PACKAGE}."
_run_copilot = p5.run_copilot
_subprocess_run = subprocess.run


def run_copilot(args: list[str], cwd: Path, env: dict):
    """Drop the launcher's --lean (only before the launcher's `--`); stock commands have no `--` and pass as they are."""
    if "--" in args:
        split = args.index("--")
        args = [arg for arg in args[:split] if arg != "--lean"] + args[split:]
    return _run_copilot(args, cwd, env)


def install_run(*args, **kwargs):
    """PROTOCOL.md amendment: install_tm's 900-second timeout becomes 2,700 seconds (graphify indexes Django in both
    shards at once). Every other subprocess call in the harness keeps its own timeout."""
    if kwargs.get("timeout") == 900:
        kwargs["timeout"] = 2700
    return _subprocess_run(*args, **kwargs)


p5.run_copilot = run_copilot
p5.subprocess = types.SimpleNamespace(**{**vars(subprocess), "run": install_run})
dr.lean_excluded = lambda task: []  # without --lean the launcher removes no tool

if __name__ == "__main__":
    raise SystemExit(dr.main(sys.argv[1:]))
