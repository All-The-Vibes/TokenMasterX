"""Expand and validate pinned source citations; write inspectable evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
SHA = "1cf496612e781ef8d67ff87ee4f78037492f0bc7"
SOURCE = ROOT / "source" / f"headroom-{SHA}"
pattern = re.compile(r"\[\[([^:\]\n]+):(\d+)-(\d+)\|([^\]\n]+)\]\]")
references = {}


def expand(match):
    relative, first, last, label = match.groups()
    a, b = int(first), int(last)
    path = (SOURCE / relative).resolve()
    assert path.is_relative_to(SOURCE.resolve()), relative
    lines = path.read_text(encoding="utf-8").splitlines()
    assert 1 <= a <= b <= len(lines), (relative, a, b, len(lines))
    url = f"https://github.com/headroomlabs-ai/headroom/blob/{SHA}/{relative}#L{a}-L{b}"
    references[url] = {
        "path": relative, "first_line": a, "last_line": b, "file_lines": len(lines),
        "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "excerpt": "\n".join(f"{i}: {lines[i-1]}" for i in range(a, b + 1)),
    }
    return f"[{label}]({url})"


template = (ROOT / "report.source.md").read_text(encoding="utf-8")
report = pattern.sub(expand, template)
assert "[[" not in report, "Unresolved source citation"
(ROOT / "REPORT.md").write_text(report, encoding="utf-8")
(ROOT / "citation-validation.json").write_text(
    json.dumps({"sha": SHA, "unique_citations": len(references), "all_ranges_exist": True,
                "citations": {u: {k: v for k, v in entry.items() if k != "excerpt"}
                              for u, entry in references.items()}}, indent=2),
    encoding="utf-8",
)
(ROOT / "cited-excerpts.txt").write_text(
    "\n\n".join(f"{url}\n{entry['excerpt']}" for url, entry in references.items()),
    encoding="utf-8",
)
history = {}
for file in [ROOT / "history-50.json", *ROOT.glob("*.history.json")]:
    for item in json.loads(file.read_text(encoding="utf-8-sig")):
        history[item["sha"]] = item
rows = ["# Pinned-ancestor history evidence", "", "Retrieved October 4, 2026.",
        "", "| Commit | Committer date (UTC) | Subject |", "|---|---|---|"]
for key, item in sorted(history.items(), key=lambda x: x[1]["commit"]["committer"]["date"], reverse=True):
    subject = item["commit"]["message"].splitlines()[0].replace("|", "\\|")
    rows.append(f"| [{key}](https://github.com/headroomlabs-ai/headroom/commit/{key}) | "
                f"{item['commit']['committer']['date']} | {subject} |")
(ROOT / "history-evidence.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
manifest = {
    "retrieval_date": "2026-10-04",
    "repository": "headroomlabs-ai/headroom",
    "commit": SHA,
    "source_archive_url": f"https://codeload.github.com/headroomlabs-ai/headroom/zip/{SHA}",
    "source_archive_sha256": hashlib.sha256((ROOT / "source.zip").read_bytes()).hexdigest(),
    "report_sha256": hashlib.sha256((ROOT / "REPORT.md").read_bytes()).hexdigest(),
    "source_files": sum(1 for p in SOURCE.rglob("*") if p.is_file()),
    "unique_cited_ranges": len(references),
    "history_unique_commits": len(history),
    "fresh_check_result": json.loads((ROOT / "pure-checks.json").read_text(encoding="utf-8")),
    "scope": "Read-only upstream research. All researcher-created artifacts stay under this folder.",
}
supplement_path = ROOT / "supplemental-openai-cache-write.json"
if supplement_path.exists():
    manifest["supplemental_openai_cache_write"] = json.loads(
        supplement_path.read_text(encoding="utf-8")
    )
(ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps({k: manifest[k] for k in ("source_files", "unique_cited_ranges", "history_unique_commits")}, indent=2))
