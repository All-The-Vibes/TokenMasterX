"""Zero-cost probe (no model call): what keeping the subagent tools costs on each call of a session whose prompt
starts a skill.

The launcher's own `lean_command` builds Copilot CLI's argv for one prompt that starts a skill, with no installed
skills or agents and no TOKENMASTER_KEEP_TOOLS. Copilot CLI 1.0.104 then starts a stock lane and sends its first
request to a relay whose upstream is a closed local port, so the request is captured and goes nowhere, as in
`evidence/relay-control-20261027/dead_upstream_probe.py`. It runs from `C:\\tm-lanes`, where Copilot CLI inherits
nothing, and from `%TEMP%` written in its 8.3 form, where it inherits the operator's CLAUDE.md, skills and agents.
Run it before and after the launcher change. Each run records the excluded tools, the request's cl100k tokens, each
tool definition's and the system text's cl100k tokens as sent (compact JSON, which is what Copilot CLI sends), and the
bridge file's SHA-256.

  python probe.py <stock lane template> <8.3 temp folder> <output json>
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BRIDGE = REPO / "token-master-plugin/skills/token-master/brainspace_copilot_bridge.py"
sys.path.insert(0, str(REPO / "token-master-plugin/evals"))
sys.path.insert(0, str(BRIDGE.parent))
sys.path.insert(0, str(REPO / "evidence/relay-control-20261027"))
import analyze  # noqa: E402
import brainspace_copilot_bridge as bridge  # noqa: E402
import default_routing_ab as dr  # noqa: E402
import run_prs1_study as p1  # noqa: E402
import run_prs5_study as p5  # noqa: E402
from brainspace import tokens  # noqa: E402

PACKAGE = "1.0.104"
PROMPT = "Use the code-review skill to check the change in django/utils/text.py."


def lean_argv(home: Path, lane: Path) -> list[str]:
    """The launcher's argv for PROMPT, with an empty Copilot home and no keep list, from the lane folder."""
    saved, cwd = {k: os.environ.get(k) for k in ("COPILOT_HOME", "TOKENMASTER_KEEP_TOOLS")}, Path.cwd()
    os.environ["COPILOT_HOME"] = str(home / "copilot")
    os.environ.pop("TOKENMASTER_KEEP_TOOLS", None)
    os.chdir(lane)
    try:
        return bridge.lean_command([p5.COPILOT, "-p", PROMPT, *p5.FLAGS])
    finally:
        os.chdir(cwd)
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def probe(template: Path, root: Path) -> dict:
    p5.CLI_VERSION = f"GitHub Copilot CLI {PACKAGE}."
    home, lane, run_dir = root / "home", root / "tokenmaster", root / "run"
    p5.reset_lane(lane, template)
    p5.clear_history(home)
    run_dir.mkdir(parents=True, exist_ok=True)
    for stale in run_dir.glob("*.jsonl"):
        stale.unlink()
    env = p5.cli_env(home, "http://127.0.0.1:9")
    version = p5.cli_version(home)
    argv = lean_argv(home, lane)
    excluded = argv[argv.index("--excluded-tools") + 1:] if "--excluded-tools" in argv else []
    p5.UPSTREAM = "http://127.0.0.1:9"  # closed port: the relay records the request, then answers 502
    with p5.Relay("not-sent") as relay:
        env["COPILOT_PROVIDER_BASE_URL"] = relay.url
        relay.session_dir = run_dir
        p5.run_copilot(argv, lane, env)  # Copilot CLI gives up, or is killed
        relay.session_dir = None
    captures = p5.read_jsonl(run_dir / "captures.jsonl")
    sent = {"model": env.get("COPILOT_MODEL"), "wire_api": env.get("COPILOT_PROVIDER_WIRE_API")}
    if not captures:
        return {"version": version, **sent, "excluded": excluded, "captured": 0}
    first = min(captures, key=lambda c: c["n"])["input"]
    body = json.loads(first)

    def compact(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    tools = {t.get("name") or "?": tokens.count_tokens(compact(t)) for t in body.get("tools") or []}
    system = (body.get("instructions") or "") + "".join(
        compact(i) for i in body.get("input") or [] if isinstance(i, dict) and i.get("role") in ("system", "developer"))
    return {"version": version, **sent, "excluded": excluded, "captured": len(captures),
            "statuses": sorted({c["status"] for c in captures}), "request_cl100k_tokens": tokens.count_tokens(first),
            "tool_cl100k_tokens": tools, "system_cl100k_tokens": tokens.count_tokens(system),
            **analyze.request_facts(first, analyze.operator_heading())}


def main() -> None:
    template, short_temp, output = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    bridge_sha256 = hashlib.sha256(BRIDGE.read_bytes()).hexdigest()  # the code this run imported
    p5.COPILOT, p5.base_env, p5.MODEL, p5.SESSION_TIMEOUT = str(dr.LAUNCHER), dr.base_env, dr.MODEL, 240
    results = {}
    for name, base in (("C:\\tm-lanes", dr.LANES_ROOT / "skill-agents"), ("%TEMP% (8.3 form)", short_temp / "skill-agents")):
        results[name] = probe(template, base)
        print(json.dumps({name: results[name]}), flush=True)
    output.write_text(json.dumps({"probe": "first relay request, closed upstream, a prompt that starts a skill",
                                  "prompt": PROMPT, "template": str(template), "bridge_sha256": bridge_sha256,
                                  "launcher_sha256": p1.sha256_file(dr.LAUNCHER), "tokenizer": tokens.backend_info(),
                                  "results": results}, indent=1) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
