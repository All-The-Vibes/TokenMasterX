"""Copilot CLI 1.0.98: how much of a session's first call does GitHub's prompt cache already serve, with and without the
TokenMaster bridge? Exploratory probe.

For each model, three stock sessions run back to back: folder X, folder X again, then folder Y. Then three TokenMaster
sessions run the same way through the launcher (lean tool set and bridge). The record is each first call's input,
cache-read and cache-write tokens.

  python cache_probe.py <new output folder>
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from probe import MODELS, PROMPT, p5, q, run_env, version_of  # noqa: E402

SEQUENCE = (("stock", "x"), ("stock", "x"), ("stock", "y"), ("tm", "x"), ("tm", "x"), ("tm", "y"))


def main() -> int:
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True)
    work = Path(tempfile.gettempdir()) / "opencode" / "cache-probe-work"
    shutil.rmtree(work, ignore_errors=True)
    home = work / "home"
    token = p5.p1.load_copilot_token()
    flags = [flag for flag in p5.FLAGS if flag != "--no-auto-update"]  # the installed build, as users run it
    launcher = p5.SKILL / "brainspace_copilot_bridge.py"
    rows = []
    for short, model in MODELS:
        q.configure(model, "cache-probe")
        model_flags = ["--model", model, *flags[2:]]
        with p5.Relay(token) as relay:
            env = run_env(home, relay.url, model)
            for index, (arm, folder) in enumerate(SEQUENCE, 1):
                repo = work / f"repo-{folder}"
                shutil.rmtree(repo, ignore_errors=True)
                repo.mkdir(parents=True)
                (repo / "hello.py").write_text("def greet(name):\n    return f'hello {name}'\n", encoding="utf-8")
                run_dir = out / f"{short}-{index}-{arm}-{folder}"
                run_dir.mkdir()
                command = [p5.COPILOT, "-p", PROMPT, *model_flags]
                if arm == "tm":
                    command = [sys.executable, "-B", str(launcher), "--log", str(run_dir / "bridge.jsonl"), "--",
                               *command]
                relay.session_dir = run_dir
                proc = subprocess.run(command, cwd=repo, env=env, capture_output=True, text=True, encoding="utf-8",
                                      errors="replace", timeout=600, stdin=subprocess.DEVNULL)
                relay.session_dir = None
                relay.wait_idle()
                log = run_dir / "calls.jsonl"
                calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.is_file() \
                    else []
                bridge = run_dir / "bridge.jsonl"
                bridge_rows = [json.loads(line) for line in bridge.read_text(encoding="utf-8").splitlines()] \
                    if bridge.is_file() else []
                rows.append({"model": model, "order": index, "arm": arm, "folder": folder, "exit": proc.returncode,
                             "version_in_system_prompt": version_of(run_dir) if calls else "",
                             "first_call": calls[0]["usage"] if calls else None,
                             "first_prefix_sha256": calls[0].get("prefix_sha256") if calls else None,
                             "bridge_stable_prefix": [row.get("stable_prefix") for row in bridge_rows][:1],
                             "stderr_tail": proc.stderr[-300:]})
                print(json.dumps({k: rows[-1][k] for k in ("model", "order", "arm", "folder", "exit",
                                                           "version_in_system_prompt", "first_call",
                                                           "bridge_stable_prefix")}), flush=True)
    (out / "results.json").write_text(json.dumps({"kind": "exploratory probe", "prompt": PROMPT, "runs": rows},
                                                 indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
