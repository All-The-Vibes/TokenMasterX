"""Zero-cost probe (no model call) for the skill-trigger change, on Copilot CLI 1.0.104 in BYOK mode (gpt-6-astra,
Responses API). Copilot CLI sends each request to a relay whose upstream is a closed local port, so the request is
captured and goes nowhere, as in evidence/skill-agents-cost-20261029/probe.py. The lane is a small git repository
under C:\\tm-lanes, outside the operator's profile, with one personal skill (demo-skill) in its Copilot home.

A. Built-in commands in prompt mode: what the first requests of /review, /security-review, /research, /rubber-duck,
   /fleet and --fleet ask for, with every tool sent and with the 13 lean tools excluded.
B. Per-family weights for /tokenomics: the first request with the 13 lean tools excluded, with each family kept
   alone, and with nothing excluded. Whole requests as captured; tool definitions as compact JSON.
C. Slash expansion: where Copilot CLI puts demo-skill's text for a slash at the start, mid-input, in another case
   with trailing punctuation, without the `skill` tool, and for a bare name or a path.

  python probe.py <output json>
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BRIDGE = REPO / "token-master-plugin/skills/token-master/brainspace_copilot_bridge.py"
sys.path.insert(0, str(REPO / "token-master-plugin/evals"))
sys.path.insert(0, str(BRIDGE.parent))
import brainspace_copilot_bridge as bridge  # noqa: E402
import default_routing_ab as dr  # noqa: E402
import run_prs1_study as p1  # noqa: E402
import run_prs5_study as p5  # noqa: E402
from brainspace import tokens  # noqa: E402

PACKAGE = "1.0.104"
ROOT = dr.LANES_ROOT / "skill-trigger"
MARKER = "DEMO-SKILL-BODY-7731"
SKILL = f"""---
name: demo-skill
description: Reports the first line of a file. Use when asked to run demo-skill.
---
{MARKER}: read the named file and report its first line.
"""
APP = "def parse(text):\n    return text.split(',')\n\n\ndef total(values):\n    return sum(int(v) for v in values)\n"
PLAIN = "Add a docstring to every function in src/app.py."
LEAN = list(bridge.LEAN_EXCLUDED_TOOLS)
SETTLE = 8  # seconds to keep capturing after the first request


def compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def git(*args: str, cwd: Path) -> None:
    subprocess.run([str(p1.GIT_EXE), "-c", "user.name=probe", "-c", "user.email=probe@example.invalid", *args],
                   cwd=cwd, check=True, capture_output=True)


def make_template() -> Path:
    template = ROOT / "template"
    if not (template / ".git").is_dir():
        (template / "src").mkdir(parents=True, exist_ok=True)
        (template / "README.md").write_text("# demo\n\nA two-function parser.\n", encoding="utf-8")
        (template / "src" / "app.py").write_text(APP, encoding="utf-8")
        git("init", "-q", cwd=template)
        git("add", "-A", cwd=template)
        git("commit", "-q", "-m", "init", cwd=template)
    return template


def facts(body: str) -> dict:
    """Sizes and where things sit in one captured request: no operator content, the lane is synthetic."""
    request = json.loads(body)
    items = [i for i in request.get("input") or [] if isinstance(i, dict)]
    system = (request.get("instructions") or "") + "".join(compact(i) for i in items
                                                            if i.get("role") in ("system", "developer"))
    users = [compact(i.get("content")) for i in items if i.get("role") == "user"]
    listed = re.search(r"<available_skills>(.*?)</available_skills>", system, re.S)
    return {"request_cl100k_tokens": tokens.count_tokens(body),
            "system_cl100k_tokens": tokens.count_tokens(system),
            "available_skills_cl100k_tokens": tokens.count_tokens(listed.group(0)) if listed else 0,
            "skills_listed": listed.group(1).count("<name>") if listed else 0,
            "tool_cl100k_tokens": {t.get("name") or "?": tokens.count_tokens(compact(t))
                                   for t in request.get("tools") or []},
            "roles": [i.get("role") or i.get("type") for i in items],
            "marker_in": sorted({"system" if MARKER in system else "", *("user" for u in users if MARKER in u)} - {""}),
            "system_head": system[:240],
            "last_user_text": users[-1][:3000] if users else ""}


def capture(name: str, args: list[str], *, excluded: list[str] | None, edit: bool = False) -> dict:
    """One Copilot CLI start in a fresh lane; returns the facts of every request captured within SETTLE seconds of the
    first, then kills the process tree."""
    home, lane, run_dir = ROOT / "home", ROOT / "lane", ROOT / "run" / name
    p5.reset_lane(lane, make_template())
    p5.clear_history(home)
    run_dir.mkdir(parents=True, exist_ok=True)
    for stale in run_dir.glob("*"):
        stale.unlink()
    if edit:
        with (lane / "src" / "app.py").open("a", encoding="utf-8") as handle:
            handle.write("\n\ndef mean(values):\n    return total(values) / len(values)\n")
    env = p5.cli_env(home, "http://127.0.0.1:9")
    skill = Path(env["COPILOT_HOME"]) / "skills" / "demo-skill" / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(SKILL, encoding="utf-8")
    argv = [p5.COPILOT, *args, *p5.FLAGS, *(["--excluded-tools", *excluded] if excluded else [])]
    p5.UPSTREAM = "http://127.0.0.1:9"
    with p5.Relay("not-sent") as relay:
        env["COPILOT_PROVIDER_BASE_URL"] = relay.url
        relay.session_dir = run_dir
        with (run_dir / "stdout.txt").open("w") as out, (run_dir / "stderr.txt").open("w") as err:
            proc = subprocess.Popen(argv, cwd=lane, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                    creationflags=p1.NO_WINDOW)
            started, first = time.monotonic(), None
            while proc.poll() is None and time.monotonic() - started < 150:
                if first is None and p5.read_jsonl(run_dir / "captures.jsonl"):
                    first = time.monotonic()
                if first is not None and time.monotonic() - first > SETTLE:
                    break
                time.sleep(0.5)
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
            proc.wait(timeout=60)
        relay.session_dir = None
    captures = sorted(p5.read_jsonl(run_dir / "captures.jsonl"), key=lambda c: c["n"])
    tail = (run_dir / "stderr.txt").read_text(errors="replace")[-600:] + (run_dir / "stdout.txt").read_text(
        errors="replace")[-600:]
    return {"args": args, "excluded": excluded or [], "edited": edit, "captured": len(captures),
            "requests": [facts(c["input"]) for c in captures[:3]], "exit_tail": "" if captures else tail}


def main() -> None:
    output = Path(sys.argv[1])
    p5.CLI_VERSION = f"GitHub Copilot CLI {PACKAGE}."
    p5.COPILOT, p5.base_env, p5.MODEL, p5.SESSION_TIMEOUT = str(dr.LAUNCHER), dr.base_env, dr.MODEL, 150
    results: dict = {"A": {}, "B": {}, "C": {}}
    commands = {"review": (["-p", "/review"], True), "security-review": (["-p", "/security-review"], True),
                "research": (["-p", "/research how does src/app.py split its input"], False),
                "rubber-duck": (["-p", "/rubber-duck critique src/app.py"], False),
                "fleet-slash": (["-p", f"/fleet {PLAIN}"], False), "fleet-flag": (["--fleet", "-p", PLAIN], False),
                "plain": (["-p", PLAIN], False)}
    for name, (args, edit) in commands.items():
        for variant, excluded in (("all-tools", None), ("lean", LEAN)):
            results["A"][f"{name}/{variant}"] = capture(f"A-{name}-{variant}", args, excluded=excluded, edit=edit)
            print(name, variant, results["A"][f"{name}/{variant}"]["captured"], flush=True)
    results["B"]["stock"] = capture("B-stock", ["-p", PLAIN], excluded=None)
    results["B"]["lean"] = capture("B-lean", ["-p", PLAIN], excluded=LEAN)
    for family, (tools, _) in bridge.CAPABILITY_GROUPS.items():
        results["B"][f"keep-{family}"] = capture(f"B-keep-{family}", ["-p", PLAIN],
                                                 excluded=[t for t in LEAN if t not in tools])
        print("B", family, results["B"][f"keep-{family}"]["captured"], flush=True)
    keep_skill = [t for t in LEAN if t != "skill"]
    for name, prompt, excluded in (("start", "/demo-skill README.md", keep_skill),
                                   ("mid", "Please run /demo-skill on README.md", keep_skill),
                                   ("case-punct", "/Demo-Skill, README.md", keep_skill),
                                   ("no-skill-tool", "/demo-skill README.md", LEAN),
                                   ("bare-verb", "Run demo-skill on README.md", keep_skill),
                                   ("path", "Fix the bug in /src/app.py", keep_skill)):
        results["C"][name] = capture(f"C-{name}", ["-p", prompt], excluded=excluded)
        print("C", name, results["C"][name]["captured"], results["C"][name]["requests"][:1] and
              results["C"][name]["requests"][0]["marker_in"], flush=True)
    output.write_text(json.dumps({"probe": "first requests to a closed upstream, Copilot CLI " + PACKAGE,
                                  "version": p5.cli_version(ROOT / "home"), "model": dr.MODEL,
                                  "bridge_sha256": hashlib.sha256(BRIDGE.read_bytes()).hexdigest(),
                                  "tokenizer": tokens.backend_info(), "results": results}, indent=1) + "\n",
                      encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
