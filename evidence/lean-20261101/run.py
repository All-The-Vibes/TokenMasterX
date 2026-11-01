"""TokenMaster with --lean against stock Copilot CLI under default routing: one shard of default_routing_ab.py.

The harness already starts the tm arm through the launcher with --lean. This wrapper pins Copilot CLI 1.0.105, the
build of the default-setup run (evidence/default-nolean-20261101), and raises the install step's timeout from 900 to
2,700 seconds. Everything else is the harness. See PROTOCOL.md.

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
_subprocess_run = subprocess.run


def install_run(*args, **kwargs):
    """install_tm's 900-second timeout becomes 2,700 seconds (graphify indexes Django in both shards at once). Every
    other subprocess call in the harness keeps its own timeout."""
    if kwargs.get("timeout") == 900:
        kwargs["timeout"] = 2700
    return _subprocess_run(*args, **kwargs)


p5.subprocess = types.SimpleNamespace(**{**vars(subprocess), "run": install_run})

if __name__ == "__main__":
    raise SystemExit(dr.main(sys.argv[1:]))
