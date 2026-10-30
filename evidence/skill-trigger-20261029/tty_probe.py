"""Interactive-mode check for probe.py: Copilot CLI 1.0.104 started with -i in its own console window (a real TTY), so
its interactive command handling runs. Same lane, relay and closed upstream as probe.py.

  python tty_probe.py <output json>
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time

import probe as pr


def capture_tty(name: str, args: list[str], edit: bool = False) -> dict:
    home, lane, run_dir = pr.ROOT / "home", pr.ROOT / "lane", pr.ROOT / "run" / name
    pr.p5.reset_lane(lane, pr.make_template())
    pr.p5.clear_history(home)
    run_dir.mkdir(parents=True, exist_ok=True)
    for stale in run_dir.glob("*"):
        stale.unlink()
    if edit:
        with (lane / "src" / "app.py").open("a", encoding="utf-8") as handle:
            handle.write("\n\ndef mean(values):\n    return total(values) / len(values)\n")
    env = pr.p5.cli_env(home, "http://127.0.0.1:9")
    skill = Path(env["COPILOT_HOME"]) / "skills" / "demo-skill" / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(pr.SKILL, encoding="utf-8")
    config = Path(env["COPILOT_HOME"]) / "config.json"
    config.write_text(json.dumps({"trusted_folders": [str(lane)]}), encoding="utf-8")  # no trust prompt
    flags = [f for f in pr.p5.FLAGS if f not in ("--output-format", "json")]
    argv = [pr.p5.COPILOT, *args, *flags]
    pr.p5.UPSTREAM = "http://127.0.0.1:9"
    with pr.p5.Relay("not-sent") as relay:
        env["COPILOT_PROVIDER_BASE_URL"] = relay.url
        relay.session_dir = run_dir
        proc = subprocess.Popen(argv, cwd=lane, env=env, creationflags=subprocess.CREATE_NEW_CONSOLE)
        started, first = time.monotonic(), None
        while proc.poll() is None and time.monotonic() - started < 90:
            if first is None and pr.p5.read_jsonl(run_dir / "captures.jsonl"):
                first = time.monotonic()
            if first is not None and time.monotonic() - first > pr.SETTLE:
                break
            time.sleep(0.5)
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        proc.wait(timeout=60)
        relay.session_dir = None
    captures = sorted(pr.p5.read_jsonl(run_dir / "captures.jsonl"), key=lambda c: c["n"])
    return {"args": args, "edited": edit, "captured": len(captures),
            "requests": [pr.facts(c["input"]) for c in captures[:3]]}


def main() -> None:
    pr.p5.CLI_VERSION = f"GitHub Copilot CLI {pr.PACKAGE}."
    pr.p5.COPILOT, pr.p5.base_env, pr.p5.MODEL = str(pr.dr.LAUNCHER), pr.dr.base_env, pr.dr.MODEL
    results = {}
    for name, args, edit in (("tty-fleet", ["-i", f"/fleet {pr.PLAIN}"], False),
                             ("tty-demo", ["-i", "/demo-skill README.md"], False),
                             ("tty-review", ["-i", "/review"], True),
                             ("tty-security-review", ["-i", "/security-review"], True),
                             ("tty-research", ["-i", "/research how does src/app.py split its input"], False),
                             ("tty-rubber-duck", ["-i", "/rubber-duck critique src/app.py"], False)):
        results[name] = capture_tty(name, args, edit)
        request = results[name]["requests"][0] if results[name]["requests"] else {}
        print(name, results[name]["captured"], request.get("marker_in"), repr(request.get("last_user_text", "")[:300]),
              flush=True)
    Path(sys.argv[1]).write_text(json.dumps({"probe": "first requests of -i sessions in a console window, Copilot CLI "
                                             + pr.PACKAGE, "results": results}, indent=1) + "\n",
                                 encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
