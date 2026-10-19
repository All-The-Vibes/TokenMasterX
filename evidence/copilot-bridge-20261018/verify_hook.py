"""Live check of the default install's v6 view hook with Copilot CLI 1.0.98. A functional check, not a savings study.

Run 2's hook check chose a 37.3 KB file. Copilot CLI's view tool refused to read that file whole, so the hook had no
result to shape. This check asks for whole-file views of two smaller files that are still above v6's read budget.
hook4 ran with a logging shim, installed by hand in the temporary hook home, to record the hook's input and output.
"""
import json
import os
import subprocess
import sys

RUN_NAME = sys.argv[1] if len(sys.argv) > 1 else "hook3"
sys.argv = [sys.argv[0], RUN_NAME]  # verify_bridge takes its run name from argv when it is imported
import verify_bridge as vb  # noqa: E402

SHIM = os.environ.get("TM_HOOK_SHIM")  # diagnostic: route the installed hook through a logging shim (hook4, hook8)
TASK = os.environ.get("TM_HOOK_TASK", "summary")

# hook3 and hook4 used run 2's hook home and asked for "the whole file (no view_range)"; the model then added
# forceReadLargeFiles, which v6 never shapes. hook5 asked for the first line of each file; the model read line ranges,
# which v6 never shapes either. Later runs install the hook into a fresh home and ask for a summary of each file.
FRESH = RUN_NAME not in ("hook3", "hook4")
WS = vb.ROOT.parent / "bridge-live-run2" / "ws"
HOOK_HOME = vb.ROOT / "hook-home" if FRESH else vb.ROOT.parent / "bridge-live-run2" / "hook-home"


def candidates():
    """The smallest file above v6's read budget, plus setup.py (22.4 KB)."""
    rows = []
    for path in sorted(WS.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "tests" in path.parts or not 12000 < len(text.encode()) < 30000:
            continue
        size = vb.tokens.count_tokens(text)
        if size > 4100 and vb.shape_tool_result("view", {"path": str(path)}, text, vb.tokens.count_tokens) != text:
            rows.append((len(text.encode()), path.relative_to(WS).as_posix(), size))
    rows.sort()
    return [rows[0], next(r for r in rows if r[1] == "token-master-plugin/skills/token-master/setup.py")]


def main():
    vb.tokens.count_tokens("warm-up")  # before any server thread
    vb.CAPTURES.mkdir(parents=True, exist_ok=True)
    vb.RELAY_LOG.unlink(missing_ok=True)
    files = candidates()
    if FRESH and not (HOOK_HOME / "copilot" / "settings.json").exists():
        install = subprocess.run([sys.executable, "-B", str(vb.SKILL / "brainspace_setup.py"), "--host", "copilot",
                                  "--python", sys.executable, "--tokenizer-file", str(vb.TOKENIZER)], cwd=vb.SKILL,
                                 env=vb.cli_env(HOOK_HOME, "http://127.0.0.1:9"), capture_output=True, text=True)
        if install.returncode:
            raise SystemExit(install.stdout + install.stderr)
    if SHIM:
        settings = HOOK_HOME / "copilot" / "settings.json"
        data = json.loads(settings.read_text(encoding="utf-8"))
        entry = data["hooks"]["postToolUse"][0]
        if SHIM not in entry["args"]:
            entry["args"] = [*entry["args"][:2], SHIM, *entry["args"][2:]]
            settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    ask = {"summary": "Then summarize each file in one sentence.",
           "functions": "Then list the names of the top-level functions in each file."}[TASK]
    prompt = (f"Read {files[0][1]} and {files[1][1]} with the view tool. {ask}"
              if FRESH else "Use the view tool once on each of these files, on the whole file (no view_range): "
              + " and ".join(f[1] for f in files) + ". Then reply with the first line of each file.")
    with vb.Relay(vb.p1.load_copilot_token(), log=vb.RELAY_LOG) as relay:
        session = vb.run("hook", prompt, bridge=False, home=HOOK_HOME, ws=WS, relay=relay)
    rows = [json.loads(line) for line in vb.RELAY_LOG.read_text(encoding="utf-8").splitlines()]
    result = {"run": RUN_NAME, "kind": "functional live check of the default install's v6 view hook",
              "copilot_version": vb.cli_version(HOOK_HOME), "prompt": prompt, "fresh_install": FRESH,
              "task": TASK, "logging_shim": bool(SHIM),
              "files": [{"file": f[1], "bytes": f[0], "tokens_cl100k": f[2]} for f in files],
              "session": {**session, "calls": len(rows), "billed": round(sum(vb.billed(r) for r in rows), 1)},
              "views": vb.hook_check([f[1] for f in files]),
              "run2_views_rechecked": vb.hook_check(["token-master-plugin/docs/ACTIVE_EVALUATION_GOAL.md"],
                                                    vb.HERE / "captures" / "run2")}
    (vb.HERE / f"results-{RUN_NAME}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("files", "views", "run2_views_rechecked")}, indent=1))


if __name__ == "__main__":
    main()
