"""Live example for the README: /tokenomics on a small real session store. Exploratory, not a study.

Installs TokenMaster for Copilot into an isolated home, runs one stock session and two TokenMaster sessions (launcher:
lean tool set and bridge) in the same folder with the installed Copilot CLI, then prints the installed tokenomics.py
reports for that home. Same machinery as probe.py: relay, isolated profile, GitHub Copilot API.

  python readme_example.py <output file> [--report-only <earlier work folder>]
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "token-master-plugin/evals"))
import quick_copilot_ab as q  # noqa: E402
import run_prs5_study as p5  # noqa: E402

PROMPT = "Which function in hello.py returns a greeting? Reply with the function name only."


def install(home: Path) -> None:
    subprocess.run([sys.executable, "-B", str(p5.SKILL / "brainspace_setup.py"), "--host", "copilot", "--python",
                    sys.executable, "--tokenizer-file", str(p5.TOKENIZER)], cwd=p5.SKILL, env=p5.base_env(home),
                   capture_output=True, check=True)


def report(work: Path, out: Path, versions: list[str], note: str = "") -> None:
    home = work / "home"
    script = home / "copilot" / "token-master" / "tokenomics.py"
    reports = []
    for args in (["session", "--compact"], ["daily", "--full"]):
        result = subprocess.run([sys.executable, "-B", str(script), *args, "--no-color", "--copilot-home",
                                 str(home / "copilot")], capture_output=True, text=True, encoding="utf-8")
        reports.append(f"$ tokenomics.py {' '.join(args)}\n{result.stdout}")
    text = (f"Copilot CLI versions in the captured system prompts: {versions}\nPrompt: {PROMPT}\n"
            "Session 1: stock Copilot CLI. Sessions 2 and 3: through the TokenMaster launcher (lean tool set, bridge)."
            f"\n{note}\n" + "\n".join(reports))
    out.write_text(text.replace(str(work.resolve()), "<work>").replace(str(work), "<work>"), encoding="utf-8")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out = Path(sys.argv[1]).resolve()
    if sys.argv[2:3] == ["--report-only"]:  # reinstall the current TokenMaster into an earlier run's home and report
        work = Path(sys.argv[3])
        install(work / "home")
        versions = [re.search(r"Version number: ([0-9][0-9.\-]*[0-9])",
                              (work / f"run{index}" / "captures.jsonl").read_text(encoding="utf-8")).group(1)
                    for index in (1, 2, 3)]
        report(work, out, versions, "Reports regenerated after the October 23 attribution fix, on the same session "
                                    "store, with TokenMaster reinstalled.\n")
        print(out.read_text(encoding="utf-8"))
        return 0
    q.configure("gpt-6-astra", "tokenomics-readme")
    work = Path(tempfile.mkdtemp(prefix="tokenomics-readme-"))
    home, repo = work / "home", work / "repo"
    repo.mkdir()
    (repo / "hello.py").write_text("def greet(name):\n    return f'hello {name}'\n", encoding="utf-8")
    install(home)
    flags = [flag for flag in p5.FLAGS if flag != "--no-auto-update"]  # the installed build, as users run it
    launcher = home / "copilot" / "token-master" / "brainspace_copilot_bridge.py"
    versions = []
    with p5.Relay(p5.p1.load_copilot_token()) as relay:
        env = p5.cli_env(home, relay.url)
        for index, launched in enumerate((False, True, True), 1):
            command = [p5.COPILOT, "-p", PROMPT, *flags]
            if launched:
                command = [sys.executable, "-B", str(launcher), "--", *command]
            run_dir = work / f"run{index}"
            run_dir.mkdir()
            relay.session_dir = run_dir
            subprocess.run(command, cwd=repo, env=env, capture_output=True, timeout=600, stdin=subprocess.DEVNULL)
            relay.session_dir = None
            relay.wait_idle()
            found = re.search(r"Version number: ([0-9][0-9.\-]*[0-9])",
                              (run_dir / "captures.jsonl").read_text(encoding="utf-8"))
            versions.append(found.group(1) if found else "unknown")
    report(work, out, versions)
    print(out.read_text(encoding="utf-8"))
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
