"""Which Copilot CLI build did the real-CLI A/B runs use, and does the lean tool set remove the same overhead on 1.0.98?

The A/B harnesses pass --no-auto-update. With that flag, the WinGet launcher runs its bundled build, 1.0.78-3, even
when the installed package, 1.0.98, is present. `copilot --version` without the flag prints 1.0.98, and the harnesses
recorded that value. This probe runs one fixed prompt per model, build and tool set. It records each first call's
input tokens, the tools sent, and the version number that Copilot CLI writes into its own system prompt. With
claude-opus-5.5, 1.0.98 refuses an advertised output limit below 32,000 tokens, so the probe sets 32,000 for both
builds; the A/B runs used 16,000. The limit does not change the input tokens.

  python probe.py <new output folder>
"""
import json
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

PROMPT = "Reply with the single word OK. Do not use any tools."
MODELS = (("astra", "gpt-6-astra"), ("opus", "claude-opus-5.5"))
BUILDS = ("bundled", "installed")  # bundled: with --no-auto-update, as in the A/B runs; installed: without it


def version_of(run_dir: Path) -> str:
    for line in (run_dir / "captures.jsonl").read_text(encoding="utf-8").splitlines():
        found = re.search(r"Version number: ([0-9][0-9.\-]*[0-9])", line)
        if found:
            return found.group(1)
    return ""


def run_env(home: Path, url: str, model: str) -> dict:
    env = p5.cli_env(home, url)  # copies the installed package into the isolated profile once
    if model.startswith("claude"):
        env["COPILOT_PROVIDER_MAX_OUTPUT_TOKENS"] = "32000"  # 1.0.98 refuses claude-opus-5.5 below 32000
    return env


def main() -> int:
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True)
    work = Path(tempfile.gettempdir()) / "opencode" / "version-probe-work"
    shutil.rmtree(work, ignore_errors=True)
    home, repo = work / "home", work / "repo"  # the same paths for every run, so the prompts differ only by build
    token = p5.p1.load_copilot_token()
    rows = []
    for short, model in MODELS:
        q.configure(model, "version-probe")
        with p5.Relay(token) as relay:
            env = run_env(home, relay.url, model)
            versions = {flag: subprocess.run([p5.COPILOT, *flag, "--version"], env=env, capture_output=True, text=True,
                                             timeout=180, stdin=subprocess.DEVNULL).stdout.strip()
                        for flag in ((), ("--no-auto-update",))}
            for build in BUILDS:
                for arm in ("stock", "lean"):
                    run_dir = out / f"{short}-{build}-{arm}"
                    run_dir.mkdir()
                    shutil.rmtree(repo, ignore_errors=True)
                    repo.mkdir(parents=True)
                    (repo / "hello.py").write_text("def greet(name):\n    return f'hello {name}'\n", encoding="utf-8")
                    flags = [flag for flag in p5.FLAGS if build == "bundled" or flag != "--no-auto-update"]
                    if arm == "lean":
                        flags += ["--excluded-tools", *p5.cb.LEAN_EXCLUDED_TOOLS]
                    relay.session_dir = run_dir
                    proc = subprocess.run([p5.COPILOT, "-p", PROMPT, *flags], cwd=repo, env=env,
                                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                                          timeout=600, stdin=subprocess.DEVNULL)
                    relay.session_dir = None
                    relay.wait_idle()
                    (run_dir / "stdout.jsonl").write_text(proc.stdout, encoding="utf-8")
                    log = run_dir / "calls.jsonl"
                    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] \
                        if log.is_file() else []
                    rows.append({"model": model, "build": build, "arm": arm, "exit": proc.returncode,
                                 "version_in_system_prompt": version_of(run_dir) if calls else "",
                                 "first_call": calls[0]["usage"] if calls else None, "calls": len(calls),
                                 "tools_sent": sorted(p5.request_tools(run_dir)) if calls else [],
                                 "stderr_tail": proc.stderr[-400:]})
                    print(json.dumps({k: rows[-1][k] for k in ("model", "build", "arm", "exit",
                                                               "version_in_system_prompt", "first_call")}), flush=True)
        rows.append({"model": model, "version_flag_check": {"copilot --version": versions[()],
                                                            "copilot --no-auto-update --version":
                                                                versions[("--no-auto-update",)]}})
    summary = []
    for short, model in MODELS:
        for build in BUILDS:
            arms = {r["arm"]: r for r in rows if r.get("model") == model and r.get("build") == build}
            stock, lean = (arms[a]["first_call"] or {} for a in ("stock", "lean"))
            summary.append({"model": model, "build": build,
                            "version_in_system_prompt": arms["stock"]["version_in_system_prompt"],
                            "stock_first_call_input": stock.get("input"), "lean_first_call_input": lean.get("input"),
                            "removed_by_lean": (stock.get("input") or 0) - (lean.get("input") or 0),
                            "stock_tools": len(arms["stock"]["tools_sent"]),
                            "lean_tools": len(arms["lean"]["tools_sent"])})
    (out / "results.json").write_text(json.dumps({"kind": "exploratory probe", "prompt": PROMPT, "summary": summary,
                                                  "runs": rows}, indent=1) + "\n", encoding="utf-8")
    for row in summary:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
