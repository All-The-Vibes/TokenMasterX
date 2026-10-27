"""TokenMaster's `impact` recall on Django D01-D15 with the graph this study built. No model calls.

PRS-6 built its Django graph with graphify 0.9.91, which was deleted with %TEMP%\\opencode; with SCHEMA_VERSION = 4 it
found 56 of 56 answer-key callers. This machine's uv tool is graphify 0.9.17; the study installs 0.9.91 in its own
venv. Scored as in evidence/graphify-upgrade-20261022/compare.py.

  python impact_recall.py <copy of the study's TokenMaster template>
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "token-master-plugin/skills/token-master"))
from brainspace import symbol_index, tokens  # noqa: E402

TASKS = [t for t in json.loads((REPO / "evidence/django-scale-20261022/tasks.json").read_text(encoding="utf-8"))["tasks"]
         if int(t["id"][1:]) <= 15]
LINE = re.compile(r"^\s+(\S+?):(\d+) (\S+)(.*)$")  # "  path:line Caller [tags] | code"


def main() -> None:
    root = Path(sys.argv[1])
    graph = json.loads((root / ".token-master" / "graph.json").read_text(encoding="utf-8"))
    index = symbol_index.SymbolIndex(root)
    rows = []
    try:
        for task in TASKS:
            text = symbol_index.dispatch(index, "impact", {"symbol": task["symbol"]}) or ""
            listed = {f"{m.group(1)}::{m.group(3)}" for m in map(LINE.match, text.splitlines()) if m}
            expected = set(task["expected"]["callers"])
            rows.append({"task": task["id"], "expected": len(expected), "found": len(expected & listed),
                         "missing": sorted(expected - listed), "tokens": tokens.count_tokens(text)})
    finally:
        index.close()
    version = graph["token_master_index"]["supplier"]["version"]
    out = {"graphify": version,
           "recall": f"{sum(r['found'] for r in rows)}/{sum(r['expected'] for r in rows)}",
           "tasks_complete": sum(r["found"] == r["expected"] for r in rows),
           "impact_tokens": sum(r["tokens"] for r in rows), "tasks": rows}
    target = HERE / f"impact_recall-{version.split()[-1]}.json"
    target.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "tasks"}))


if __name__ == "__main__":
    main()
