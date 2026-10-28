"""Zero-cost probe (no model call): the first request that Copilot CLI sends in PRS-6's relay environment, by client
build and lane location. The relay's upstream is a closed local port, so the request is captured and goes nowhere.

For Copilot CLI 1.0.98-2 (the closest build left to PRS-6's 1.0.98) and 1.0.104, a stock D01 session starts from a
copy of the study's Django lane in C:\\tm-lanes and in %TEMP% written in its 8.3 form (PRS-6's lanes). The probe
records sizes and flags only: request and system-prompt characters, cl100k tokens of the request and of each tool
definition, whether the operator's CLAUDE.md is in the request, and how many skills the available_skills list names.
An optional launcher runs the same probe through another copilot.exe (the WinGet launcher that PRS-6 ran, which
auto-update replaced on October 27).

  python dead_upstream_probe.py <stock lane template> <8.3 temp folder> <output json> [<launcher exe>]
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "token-master-plugin/evals"))
sys.path.insert(0, str(HERE))
import analyze  # noqa: E402
import default_routing_ab as dr  # noqa: E402
import run_prs1_study as p1  # noqa: E402
import run_prs5_study as p5  # noqa: E402

PACKAGES = ("1.0.98-2", "1.0.104")


def probe(template: Path, root: Path, package: str, prompt: str) -> dict:
    p5.CLI_VERSION = f"GitHub Copilot CLI {package}."
    home, lane, run_dir = root / "home", root / "tokenmaster", root / "run"
    p5.reset_lane(lane, template)
    p5.clear_history(home)
    run_dir.mkdir(parents=True, exist_ok=True)
    for stale in run_dir.glob("*.jsonl"):
        stale.unlink()
    env = p5.cli_env(home, "http://127.0.0.1:9")
    version = p5.cli_version(home)
    p5.UPSTREAM = "http://127.0.0.1:9"  # closed port: the relay records the request, then answers 502
    with p5.Relay("not-sent") as relay:
        env["COPILOT_PROVIDER_BASE_URL"] = relay.url
        relay.session_dir = run_dir
        p5.run_copilot([p5.COPILOT, "-p", prompt, *p5.FLAGS], lane, env)  # Copilot CLI gives up, or is killed
        relay.session_dir = None
    captures = p5.read_jsonl(run_dir / "captures.jsonl")
    if not captures:
        return {"version": version, "captured": 0}
    first = min(captures, key=lambda c: c["n"])["input"]
    from brainspace import tokens
    tools = {t.get("name") or "?": tokens.count_tokens(json.dumps(t, ensure_ascii=False))
             for t in json.loads(first).get("tools") or []}
    return {"version": version, "captured": len(captures), "statuses": sorted({c["status"] for c in captures}),
            "request_cl100k_tokens": tokens.count_tokens(first), "tool_cl100k_tokens": tools,
            **analyze.request_facts(first, analyze.operator_heading())}


def main() -> None:
    template, short_temp, output = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    launcher = Path(sys.argv[4]) if len(sys.argv) > 4 else dr.LAUNCHER
    p5.COPILOT, p5.base_env, p5.MODEL, p5.SESSION_TIMEOUT = str(launcher), dr.base_env, dr.MODEL, 240
    prompt = next(t for t in json.loads((REPO / "evidence/django-scale-20261022/tasks.json").read_text(
        encoding="utf-8"))["tasks"] if t["id"] == "D01")["prompt"]
    results = {}
    for package in PACKAGES:
        for name, base in (("C:\\tm-lanes", dr.LANES_ROOT / "rc-probe"), ("%TEMP% (8.3 form)", short_temp / "rc-probe")):
            results[f"{package} {name}"] = probe(template, base / package, package, prompt)
            print(json.dumps({f"{package} {name}": results[f"{package} {name}"]}), flush=True)
    output.write_text(json.dumps({"probe": "first relay request, closed upstream, stock D01",
                                  "launcher_sha256": p1.sha256_file(launcher), "results": results},
                                 indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
