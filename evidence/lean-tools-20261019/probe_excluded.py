"""Probe: does Copilot CLI's --excluded-tools shrink every request, and does a simple task still succeed?

Real Copilot CLI (isolated, BYOK through the PRS-5 relay), models gpt-6-astra and claude-opus-5.5. Labeled 1.0.98
when it ran; it ran 1.0.78-3, because p5.FLAGS pass --no-auto-update (corrected 2026-10-23).
One simple lookup task per model, run with the default tools and with 11 built-in tools excluded that no
session called in the A/B runs. Records usage numbers, tool counts and system-prompt size; no content.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "token-master-plugin/evals"))
import run_prs1_study as p1  # noqa: E402
import run_prs5_study as p5  # noqa: E402
import quick_copilot_ab as q  # noqa: E402
from brainspace import tokens  # noqa: E402

EXCLUDED = ["session_store_sql", "task", "read_agent", "write_agent", "list_agents", "skill", "sql",
            "read_powershell", "stop_powershell", "list_powershell", "fetch_copilot_cli_documentation"]
PROMPT = ("Which file under token-master-plugin/skills/token-master/brainspace defines the function "
          "`round_alpha`? Reply with the relative path only.")
SNAPSHOT = Path(p5.tempfile.gettempdir()) / "opencode" / "prs1" / "snapshot"


def system_tokens(request: dict) -> int:
    if isinstance(request.get("instructions"), str):
        return tokens.count_tokens(request["instructions"])
    system = request.get("system")
    if isinstance(system, list):
        system = "".join(b.get("text", "") for b in system if isinstance(b, dict))
    return tokens.count_tokens(system) if isinstance(system, str) else 0


def main() -> None:
    tokens.count_tokens("warm-up")
    token = p1.load_copilot_token()
    rows = []
    for model in ("gpt-6-astra", "claude-opus-5.5"):
        q.configure(model, f"lean-probe-{model}")
        if p5.LANES.exists():
            p1.remove_tree(p5.LANES)
        lane = p5.LANES / "repo"
        shutil.copytree(SNAPSHOT, lane)
        for command in (["init", "-q"], ["add", "-A"], ["-c", "user.name=p", "-c", "user.email=p@example.invalid",
                                                        "commit", "-qm", "s"]):
            subprocess.run([str(p1.GIT_EXE), *command], cwd=lane, check=True, capture_output=True)
        relay = p5.Relay(token)
        relay.__enter__()
        try:
            for variant in ("default", "lean"):
                run_dir = HERE / f"{model}-{variant}"
                if run_dir.exists():
                    p1.remove_tree(run_dir)
                run_dir.mkdir(parents=True)
                args = [p5.COPILOT, "-p", PROMPT, *p5.FLAGS] + (["--excluded-tools", *EXCLUDED] if variant == "lean" else [])
                p5.clear_history(p5.LANES / "home")
                relay.session_dir = run_dir
                code, stdout, _ = p5.run_copilot(args, lane, p5.cli_env(p5.LANES / "home", relay.url))
                relay.session_dir = None
                relay.wait_idle()
                calls = sorted(p5.read_jsonl(run_dir / "calls.jsonl"), key=lambda c: c["n"])
                first = json.loads(p5.read_jsonl(run_dir / "captures.jsonl")[0]["input"])
                ok = [c["usage"] for c in calls if c["status"] == 200 and c["usage"]]
                row = {"model": model, "variant": variant, "exit": code, "calls": len(ok),
                       "tools_sent": len(first.get("tools") or []), "system_prompt_tokens_cl100k": system_tokens(first),
                       "first_call_input": ok[0]["input"] if ok else None,
                       "raw_tokens": sum(u["input"] + u["output"] for u in ok),
                       "answer_ok": "certification.py" in (p5.final_answer(stdout) or "")}
                rows.append(row)
                print(json.dumps(row), flush=True)
        finally:
            relay.__exit__()
    (HERE / "results.json").write_text(json.dumps({"excluded_tools": EXCLUDED, "prompt": PROMPT, "rows": rows},
                                                  indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
