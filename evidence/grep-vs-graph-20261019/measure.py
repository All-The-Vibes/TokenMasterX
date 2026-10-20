"""grep vs graph lookups: tokens an agent receives for the same question, small repo vs large repo.

No model calls. For a fixed random sample of real functions and classes in each repository, it compares:
  "Where is X defined?"  rg -n "(def|class) X\\b"   vs  locate X   (TokenMaster symbol index)
  "Who uses X?"          rg -n "\\bX\\b"            vs  impact X   (graphify call graph + name matches)
rg is the ripgrep binary that ships with Copilot CLI 1.0.98 (its grep tool). Tokens are cl100k counts of the exact
text each command returns. Copilot's grep tool may cut very long output; the raw rg size is reported.
"""
import json
import os
import random
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "token-master-plugin/skills/token-master"))
from brainspace import symbol_index, tokens  # noqa: E402

RG = Path(os.environ["LOCALAPPDATA"]) / "copilot/pkg/win32-x64/1.0.98/ripgrep/bin/win32-x64/rg.exe"
REPOS = {"tokenmaster (small)": REPO / "evidence/prs5-20261019/study/templates/tm",
         "django 5.2 (large)": Path(os.environ["TEMP"]) / "opencode" / "django"}
SAMPLE = 40


def rg(root: Path, pattern: str) -> str:
    # graphify-out/ holds graphify's own multi-megabyte graph.json; exclude it to measure the repository itself.
    out = subprocess.run([str(RG), "-n", "--no-heading", "--color", "never", "-g", "!graphify-out", pattern, "."],
                         cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return out.stdout


def main() -> None:
    rows = {}
    for label, root in REPOS.items():
        index = symbol_index.SymbolIndex(root)
        try:
            names = sorted({row[0] for row in index.db.execute(
                "SELECT name FROM symbols WHERE kind IN ('function', 'method', 'class') AND path NOT LIKE '%test%'")
                if len(row[0]) >= 6 and not row[0].startswith("__")})
            sample = random.Random(20261019).sample(names, min(SAMPLE, len(names)))
            totals = {"define_grep": 0, "define_graph": 0, "uses_grep": 0, "uses_graph": 0}
            per = []
            for name in sample:
                sizes = {"define_grep": tokens.count_tokens(rg(root, rf"(def|class) {name}\b")),
                         "define_graph": tokens.count_tokens(symbol_index.dispatch(index, "locate", {"query": name}) or ""),
                         "uses_grep": tokens.count_tokens(rg(root, rf"\b{name}\b")),
                         "uses_graph": tokens.count_tokens(symbol_index.dispatch(index, "impact", {"symbol": name}) or "")}
                per.append({"name": name, **sizes})
                for key, value in sizes.items():
                    totals[key] += value
        finally:
            index.close()
        files = sum(1 for _ in root.rglob("*.py"))
        rows[label] = {"python_files": files, "symbols_sampled": len(sample), "totals": totals, "per_symbol": per}
        print(f"{label}: {files:,} .py files, {len(sample)} symbols | where-defined: grep {totals['define_grep']:,} vs "
              f"locate {totals['define_graph']:,} tokens | who-uses: grep {totals['uses_grep']:,} vs impact "
              f"{totals['uses_graph']:,} tokens", flush=True)
    (HERE / "results.json").write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
