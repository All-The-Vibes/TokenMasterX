"""Live check: does /tokenomics work inside the real Copilot CLI, with TokenMaster's lean tool set? Exploratory.

Sets up an isolated Copilot home, installs TokenMaster for Copilot with brainspace_setup.py (which writes the
/tokenomics skill), and runs `copilot -p "/tokenomics"` through the TokenMaster launcher in bring-your-own-model mode.
The launcher's lean tool set excludes Copilot CLI's `skill` tool, so this also checks that a user-typed /SKILL-NAME
still works without it. Same machinery as run_prs5_study.py: relay, isolated profile, GitHub Copilot API.

  python check.py <output folder> [--model gpt-6-astra]
"""
import argparse
import json
import re
import shutil
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
    parser.add_argument("--all-tools", action="store_true", help="launch without the lean tool set")
    parser.add_argument("--prompt", default="/tokenomics")
    parser.add_argument("--build", choices=("installed", "bundled"), default="installed",
                        help="installed: the newest installed package, as users run it; bundled: --no-auto-update, "
                             "which runs the WinGet launcher's bundled build (1.0.78-3; runs 1 and 2)")
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise SystemExit(f"output must be new: {out}")
    out.mkdir(parents=True)
    q.configure(args.model, "tokenomics-check")
    work = Path(tempfile.mkdtemp(prefix="tokenomics-check-"))
    home, repo = work / "home", work / "repo"
    repo.mkdir()
    (repo / "hello.py").write_text("def greet(name):\n    return f'hello {name}'\n", encoding="utf-8")
    env = p5.base_env(home)
    setup = subprocess.run([sys.executable, "-B", str(p5.SKILL / "brainspace_setup.py"), "--host", "copilot",
                            "--python", sys.executable, "--tokenizer-file", str(p5.TOKENIZER)],
                           cwd=p5.SKILL, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    skill = home / "copilot" / "skills" / "tokenomics" / "SKILL.md"
    receipt = {"model": args.model, "all_tools": args.all_tools, "prompt": args.prompt, "build": args.build,
               "setup_exit": setup.returncode, "skill_installed": skill.is_file()}
    token = p5.p1.load_copilot_token()
    with p5.Relay(token) as relay:
        relay.session_dir = out
        launcher = home / "copilot" / "token-master" / "brainspace_copilot_bridge.py"
        flags = [flag for flag in p5.FLAGS if args.build == "bundled" or flag != "--no-auto-update"]
        argv = [sys.executable, "-B", str(launcher), *(["--all-tools"] if args.all_tools else []), "--", p5.COPILOT,
                "-p", args.prompt, *flags]
        started = time.time()
        proc = subprocess.run(argv, cwd=repo, env=p5.cli_env(home, relay.url), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=900, stdin=subprocess.DEVNULL)
        relay.session_dir = None
        relay.wait_idle()
    events = [json.loads(line) for line in proc.stdout.splitlines() if line.startswith("{")]
    tools = [(data.get("toolName") or data.get("name"), json.dumps(data.get("arguments"))[:300])
             for data in ((e.get("data") or {}) for e in events if "tool" in str(e.get("type")))
             if (data.get("toolName") or data.get("name")) and data.get("arguments") is not None]
    final = p5.final_answer(proc.stdout) or ""
    launches = (home / "copilot" / "token-master" / "launches.jsonl")
    captured = (out / "captures.jsonl").read_text(encoding="utf-8") if (out / "captures.jsonl").is_file() else ""
    version = re.search(r"Version number: ([0-9][0-9.\-]*[0-9])", captured)
    receipt.update(exit=proc.returncode, seconds=round(time.time() - started, 1),
                   version_in_system_prompt=version.group(1) if version else None, tool_calls=tools,
                   event_types=sorted({str(e.get("type")) for e in events}),
                   skills_loaded=[e.get("data") for e in events if e.get("type") == "session.skills_loaded"][:1],
                   ran_tokenomics=any("tokenomics.py" in arguments for _, arguments in tools),
                   dashboard_in_answer="TokenMaster Tokenomics" in final,
                   tools_sent_to_model=sorted(p5.request_tools(out)),
                   launch_records=launches.read_text(encoding="utf-8").splitlines() if launches.is_file() else [],
                   usage=p5.session_usage(out))
    (out / "final_answer.txt").write_text(final, encoding="utf-8")
    (out / "stderr.txt").write_text(proc.stderr[-4000:], encoding="utf-8")
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in receipt.items() if k != "usage"}, indent=1))
    print(final)
    shutil.rmtree(work, ignore_errors=True)
    return 0 if receipt["dashboard_in_answer"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
