"""How often the skill trigger fires before (PR #18, commit defabef) and after this change, on this machine's installed
skills (COPILOT_HOME unset, run from the repository root, as a launch here would be).

Prompts: the 145 real coding prompts in the repository's evals (PRS-1 to PRS-5, fresh coding, repository cases, the
45 Django tasks), none of which needs a skill; and prompts written for this check, which show behavior, not rates:
WANT start a skill that is installed here, AVOID do not.

  python corpus_check.py <output json>
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SKILL = REPO / "token-master-plugin/skills/token-master"
sys.path.insert(0, str(SKILL))

WANT = ["/phoenix-review the diff in HEAD~1", "Please run /humanizer on README.md", "/pdf extract the tables from report.pdf",
        "/document-skills:claude-api how do I stream?", "Use the humanizer skill to clean up README.md",
        "Review this change using the phoenix-review skill", "Load the pptx skill and build a deck from notes.md",
        "Don't forget to use the humanizer skill", "Run phoenix-ship on this branch", "Run humanizer on the README",
        "humanizer pass over the docs, please", "/Humanizer README.md"]
AVOID = ["Fix the bug in /src/app.py", "POST /users returns 400", "the /login route is broken",
         "fix the infinite loop in parser.py", "Do not use the review skill", "Export the report as pdf",
         "Check the capacity of the queue", "Update the preset values in config.yaml", "customize the theme colors",
         "the phoenix server crashed on startup", "never run the humanizer skill on code comments",
         "Update the token-master skill's description", "see https://example.com/docs/api for the /v1 spec",
         "the asyncio run loop hangs on shutdown", "use pdf export for the quarterly report"]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prompts(value, key=None):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from prompts(v, k)
    elif isinstance(value, list):
        for v in value:
            yield from prompts(v, key)
    elif isinstance(value, str) and key == "prompt":
        yield value


def main() -> None:
    corpus = []
    for name in ("prs1_tasks", "prs2_tasks", "prs3_tasks", "prs4_tasks", "prs5_tasks", "fresh-coding-cases",
                 "repository-cases"):
        corpus += prompts(json.loads((REPO / f"token-master-plugin/evals/{name}.json").read_text(encoding="utf-8")))
    corpus += prompts(json.loads((REPO / "evidence/django-scale-20261022/tasks.json").read_text(encoding="utf-8")))
    with tempfile.TemporaryDirectory() as tmp:
        old_path = Path(tmp) / "bridge_before.py"
        old_path.write_bytes(subprocess.run(
            ["git", "show", "defabef:token-master-plugin/skills/token-master/brainspace_copilot_bridge.py"],
            cwd=REPO, capture_output=True, check=True).stdout)
        rules = {"before (defabef)": load("bridge_before", old_path), "after": load("bridge_after",
                                                                                  SKILL / "brainspace_copilot_bridge.py")}
    results = {}
    for label, bridge in rules.items():
        fires = lambda text: "skill" not in bridge.select_excluded_tools(["copilot", "-p", text])  # noqa: E731
        results[label] = {"corpus_fired": sum(map(fires, corpus)), "corpus": len(corpus),
                          "want_kept": [p for p in WANT if fires(p)], "avoid_fired": [p for p in AVOID if fires(p)]}
        row = results[label]
        print(f"{label:17} real prompts fired {row['corpus_fired']}/{len(corpus)}  want kept {len(row['want_kept'])}/"
              f"{len(WANT)}  avoid fired {len(row['avoid_fired'])}/{len(AVOID)}: {row['avoid_fired']}")
        print(f"{'':17} want missed: {[p for p in WANT if p not in row['want_kept']]}")
    Path(sys.argv[1]).write_text(json.dumps({"check": "skill trigger on real and written prompts",
                                             "installed_skills_here": len(rules["after"]._installed_names("skills")),
                                             "want": WANT, "avoid": AVOID, "results": results}, indent=1) + "\n",
                                 encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
