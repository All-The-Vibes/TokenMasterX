"""Interactive /tokenomics check: prepare an isolated Copilot home with TokenMaster installed and serve the relay.

`-p "/tokenomics"` passes the text to the model; slash commands only run in an interactive session (check.py, runs 1
and 2). This script prepares the home, starts the relay and writes `session.json` (environment, launcher, repository).
A terminal session then runs the launcher interactively and types /tokenomics. Stop the script to stop the relay.

  python interactive.py <output folder> [--model gpt-6-astra] [--build installed|bundled] [--ask]

The first run (interactive/) predates these options; it ran the equivalent of --build bundled, without --ask.
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "token-master-plugin/evals"))
import quick_copilot_ab as q  # noqa: E402
import run_prs5_study as p5  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", default="gpt-6-astra")
    parser.add_argument("--build", choices=("installed", "bundled"), default="installed",
                        help="installed: the newest installed package, as users run it; bundled: --no-auto-update, "
                             "which runs the WinGet launcher's bundled build (1.0.78-3)")
    parser.add_argument("--ask", action="store_true", help="no --allow-all-tools: Copilot CLI asks for each permission")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True)
    q.configure(args.model, "tokenomics-interactive")
    work = Path(tempfile.mkdtemp(prefix="tokenomics-interactive-"))
    home, repo = work / "home", work / "repo"
    repo.mkdir()
    (repo / "hello.py").write_text("def greet(name):\n    return f'hello {name}'\n", encoding="utf-8")
    setup = subprocess.run([sys.executable, "-B", str(p5.SKILL / "brainspace_setup.py"), "--host", "copilot",
                            "--python", sys.executable, "--tokenizer-file", str(p5.TOKENIZER)],
                           cwd=p5.SKILL, env=p5.base_env(home), capture_output=True, text=True)
    if setup.returncode:
        raise SystemExit(setup.stdout + setup.stderr)
    with p5.Relay(p5.p1.load_copilot_token()) as relay:
        relay.session_dir = out
        env = p5.cli_env(home, relay.url)
        if args.ask:
            env.pop("COPILOT_ALLOW_ALL", None)
        launcher = home / "copilot" / "token-master" / "brainspace_copilot_bridge.py"
        flags = [*([] if args.ask else ["--allow-all-tools"]), *(["--no-auto-update"] if args.build == "bundled" else []),
                 "--disable-builtin-mcps"]
        (out / "session.json").write_text(json.dumps({
            "env": env, "repo": str(repo), "home": str(home), "python": sys.executable,
            "args": ["-B", str(launcher), "--", p5.COPILOT, "--model", args.model, *flags]}, indent=1),
            encoding="utf-8")
        print(f"ready: {out / 'session.json'}", flush=True)
        while True:
            time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
