"""Validate report citations and unchanged source evidence; writes only its JSON report."""
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent
REPO = BASE.parents[2]
TM_SHA = "426fc853389ddba4bc6e1dd35a28179a895c064f"
P_SHA = "c982cd411abb53323c4baa1baa3c2f020b8d0b08"
P_OLD = "356918eba965ee1eac64bd3a7f0dd02108350de5"
H_SHA = "1cf496612e781ef8d67ff87ee4f78037492f0bc7"
roots = {
    ("All-The-Vibes/TokenMasterX", TM_SHA): BASE / "tokenmaster/source",
    ("DietrichGebert/ponytail", P_SHA): BASE / "ponytail/source" / f"ponytail-{P_SHA}",
    ("DietrichGebert/ponytail", P_OLD): BASE / "ponytail/source" / f"ponytail-{P_OLD}",
    ("headroomlabs-ai/headroom", H_SHA): BASE / "headroom/source" / f"headroom-{H_SHA}",
}
reports = [
    BASE / "PARITY_REPORT.md",
    BASE / "GAP_BACKLOG.md",
    BASE / "BENCHMARK_PROTOCOL.md",
    BASE / "EVIDENCE_INDEX.md",
    BASE / "ponytail/REPORT.md",
    BASE / "headroom/REPORT.md",
    BASE / "tokenmaster/INDEPENDENT_REVIEW.md",
]
pattern = re.compile(
    r"https://github\.com/([^/\s)]+/[^/\s)]+)/blob/([0-9a-f]{40})/"
    r"([^\s)#]+)(?:#L(\d+)(?:-L(\d+))?)?"
)
errors = []
citations = {}
artifact_hashes = []
for report in reports:
    data = report.read_bytes()
    text = data.decode("utf-8")
    artifact_hashes.append({
        "path": str(report),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    })
    for match in pattern.finditer(text):
        repository, sha, relative, first, last = match.groups()
        url = match.group(0)
        if url in citations:
            continue
        source_root = roots.get((repository, sha))
        if source_root is None:
            errors.append(f"Unknown pin: {url}")
            continue
        source = source_root / unquote(relative)
        if not source.is_file():
            errors.append(f"Missing source: {url}")
            continue
        count = len(source.read_bytes().splitlines())
        start, end = (int(first), int(last or first)) if first else (None, None)
        if first and not (1 <= start <= end <= count):
            errors.append(f"Invalid line range ({count} source lines): {url}")
        citations[url] = {
            "url": url,
            "source": str(source),
            "line_count": count,
            "start": start,
            "end": end,
        }

main_text = (BASE / "PARITY_REPORT.md").read_text(encoding="utf-8")
definitions = set(re.findall(r"^\[([PHTO]\d{1,2}|I1)\]:", main_text, re.MULTILINE))
uses = set(re.findall(r"\[([PHTO]\d{1,2}|I1)\]", main_text))
missing_definitions = sorted(uses - definitions)
errors.extend("Missing reference definition: " + item for item in missing_definitions)
unexpanded = re.findall(r"\[[PHTO]\d+[–-][PHTO]\d+\]", main_text)
errors.extend("Unexpanded reference range: " + item for item in unexpanded)

tm_manifest = json.loads((BASE / "tokenmaster/source-manifest.json").read_text(encoding="utf-8"))
source_checks = []
for entry in tm_manifest["files"]:
    relative = entry["path"]
    snapshot = BASE / "tokenmaster/source" / relative
    snap_bytes = snapshot.read_bytes()
    pinned = subprocess.check_output(
        ["git", "cat-file", "blob", f"{TM_SHA}:{relative}"], cwd=REPO
    )
    current = (REPO / relative).read_bytes()
    record = {
        "path": relative,
        "snapshot_matches_pinned_git_bytes": snap_bytes == pinned,
        "snapshot_matches_manifest_sha256": hashlib.sha256(snap_bytes).hexdigest() == entry["sha256"],
        "current_matches_snapshot_exact_bytes": current == snap_bytes,
        "current_matches_snapshot_normalized_newlines":
            current.replace(b"\r\n", b"\n") == snap_bytes.replace(b"\r\n", b"\n"),
    }
    source_checks.append(record)
    if not record["snapshot_matches_pinned_git_bytes"] or not record["snapshot_matches_manifest_sha256"]:
        errors.append(f"Snapshot integrity failure: {relative}")
    if not record["current_matches_snapshot_normalized_newlines"]:
        errors.append(f"Tracked source content changed since baseline: {relative}")

installed_root = Path(
    r"C:\Users\shyamsridhar\.codex\plugins\cache\openai-curated-remote"
    r"\engineering-suite-ponytail\2.0.0"
)
installed_manifest = json.loads((BASE / "ponytail/installed-manifest.json").read_text(encoding="utf-8"))
installed_checks = []
for entry in installed_manifest:
    file = installed_root / entry["path"]
    data = file.read_bytes()
    valid = len(data) == entry["bytes"] and hashlib.sha256(data).hexdigest() == entry["sha256"]
    installed_checks.append({"path": str(file), "unchanged": valid})
    if not valid:
        errors.append(f"Installed snapshot changed: {file}")

head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
status = subprocess.check_output(["git", "status", "--short"], cwd=REPO, text=True).splitlines()
if head != TM_SHA:
    errors.append(f"Repository HEAD changed: {head}")
if status:
    errors.append("Tracked/non-ignored working-tree state no longer matches clean baseline.")

probe = json.loads((BASE / "tokenmaster/boundary-probe-results.json").read_text(encoding="utf-8"))
if len(probe["results"]) != 11 or not all(row["confirmed"] for row in probe["results"]):
    errors.append("Saved TokenMaster probe count/results differ from report.")

result = {
    "checked_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "as_of_date": "2026-10-04",
    "report_count": len(reports),
    "unique_pinned_repository_file_urls": len(citations),
    "unique_line_range_citations": sum(item["start"] is not None for item in citations.values()),
    "missing_reference_definitions": missing_definitions,
    "source_checks": source_checks,
    "installed_checks": installed_checks,
    "git_head": head,
    "git_status_short": status,
    "probe_count": len(probe["results"]),
    "artifact_hashes": artifact_hashes,
    "citation_checks": list(citations.values()),
    "errors": errors,
    "scope_note": "Checks reference existence/line bounds and integrity, not semantic truth of every claim or live host/model behavior.",
}
(BASE / "evidence-validation.json").write_text(
    json.dumps(result, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps({
    "reports": len(reports),
    "pinned_urls": len(citations),
    "line_ranges": result["unique_line_range_citations"],
    "tokenmaster_snapshots_verified": len(source_checks),
    "installed_files_verified_unchanged": len(installed_checks),
    "git_head": head,
    "git_status_short": status,
    "errors": errors,
}, indent=2))
raise SystemExit(1 if errors else 0)
