"""graphify 0.9.84 vs 0.9.91 under TokenMaster, on Django 5.2. No model calls.

For each graphify version: graph size, and TokenMaster's `impact` answer for the 15 Django "who calls X?" tasks
(D01-D10 rare names, D11-D15 common names), scored against their AST answer keys. A key caller counts as found
when an impact line names the same "<path>::<function or Class.method>".

  python compare.py
"""
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "token-master-plugin/skills/token-master"))
from brainspace import symbol_index, tokens  # noqa: E402

TEMP = Path(os.environ["TEMP"]) / "opencode"
BUILDS = {"0.9.84": TEMP / "django", "0.9.91": TEMP / "django-g091"}  # same Django commit, built by build_nav_index
TASKS = [task for name in ("django-impact-20261019", "django-common-20261022")
         for task in json.loads((REPO / "evidence" / name / "tasks.json").read_text(encoding="utf-8"))["tasks"]]
LINE = re.compile(r"^\s+(\S+?):(\d+) (\S+)(.*)$")  # "  path:line Caller [tags] | code"


def graph_stats(root: Path) -> dict:
    graph = json.loads((root / ".token-master" / "graph.json").read_text(encoding="utf-8"))  # TokenMaster's stamped copy
    links = [link for link in graph.get("links") or graph.get("edges") or [] if isinstance(link, dict)]
    return {"nodes": len(graph["nodes"]), "links": len(links),
            "calls_links": sum((link.get("relation") or link.get("type")) == "calls" for link in links)}


def main() -> None:
    out = {}
    for version, root in BUILDS.items():
        index = symbol_index.SymbolIndex(root)
        rows = []
        try:
            for task in TASKS:
                text = symbol_index.dispatch(index, "impact", {"symbol": task["symbol"]}) or ""
                listed = {}
                for line in text.splitlines():
                    match = LINE.match(line)
                    if match:
                        listed[f"{match.group(1)}::{match.group(3)}"] = "[name]" in match.group(4) or (
                            "[inferred]" in match.group(4))
                expected = set(task["expected"]["callers"])
                found = expected & set(listed)
                rows.append({"task": task["id"], "symbol": task["symbol"], "expected": len(expected),
                             "found": len(found), "missing": sorted(expected - found),
                             "found_unverified": sum(listed[key] for key in found),
                             "extra_non_test": sorted(k for k in listed if k not in expected and not k.startswith("tests/")),
                             "tokens": tokens.count_tokens(text)})
        finally:
            index.close()
        out[version] = {"graph": graph_stats(root), "recall": f"{sum(r['found'] for r in rows)}/"
                                                              f"{sum(r['expected'] for r in rows)}",
                        "tasks_complete": sum(r["found"] == r["expected"] for r in rows),
                        "impact_tokens": sum(r["tokens"] for r in rows), "tasks": rows}
    (HERE / "results.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    for version, data in out.items():
        print(version, data["graph"], "| recall", data["recall"], "| tasks complete", data["tasks_complete"], "of",
              len(TASKS), "| impact tokens", data["impact_tokens"])
    for old, new in zip(out["0.9.84"]["tasks"], out["0.9.91"]["tasks"]):
        print(f"  {old['task']}: {old['found']}/{old['expected']} -> {new['found']}/{new['expected']}, "
              f"tokens {old['tokens']} -> {new['tokens']}" + (f", missing: {new['missing']}" if new["missing"] else ""))


if __name__ == "__main__":
    main()
