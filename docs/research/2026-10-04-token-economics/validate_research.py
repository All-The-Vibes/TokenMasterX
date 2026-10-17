"""Validate research artifacts and provenance, not upstream software performance."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]


def load(relative):
    return json.loads((BASE / relative).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    checks = []

    def check(name, passed, detail=None):
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    audit = load("local-audit.json")
    source_index = load("local-source-index.json")
    papers = load("papers/sources.json")
    paper_validation = load("papers/verification.json")
    oss_validation = load("oss/validation.json")
    oss_files = load("oss/source-files.json")
    reducer_files = load("reducers/source-index.json")
    reducers = load("reducers/summary.json")
    oss = load("oss/evidence.json")
    report = (BASE / "FUNDAMENTAL-RESEARCH.md").read_text(encoding="utf-8")

    head = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--porcelain"], text=True
    ).strip()
    check("Pinned local source revision unchanged", head == audit["commit"] == source_index["commit"])
    check("Tracked/unignored working tree unchanged", status == "", status or "clean")
    check("All 13 local source hashes match", all(
        digest(row["absolute_path"]) == row["sha256"] for row in source_index["files"]
    ), len(source_index["files"]))
    check("All 93 OSS source-file hashes match", all(
        digest(row["local_path"]) == row["sha256"] for row in oss_files
    ), len(oss_files))
    check("All 21 reducer source-file hashes match", all(
        digest(row["local_path"]) == row["sha256"] for row in reducer_files
    ), len(reducer_files))
    check("Eleven distinct implementation repositories",
          len({row["repository"] for row in oss["candidates"]} |
              {row["repository"] for row in reducers}) == 11)
    check("16 core papers and 4 mechanism-boundary references",
          papers["core_publication_count"] == 16 and papers["boundary_reference_count"] == 4)

    pins = {row["arxiv_id"] + "v" + str(row["selected_version"])
            for row in papers["sources"]}
    mentioned = set(re.findall(r"\b\d{4}\.\d{4,5}v\d+\b", report))
    check("Every main-report paper pin exists in source metadata",
          mentioned.issubset(pins), sorted(mentioned - pins))
    check("Paper artifact checks passed", paper_validation["status"] == "passed")
    check("OSS artifact checks passed", oss_validation["passed"] and not oss_validation["errors"])
    check("OSS report still matches its verified hash",
          digest(BASE / "oss/REPORT.md") == oss_validation["report_sha256"])
    check("Recovery-validator false positive reproduced",
          audit["recovery_validator"]["finding_reproduced"])
    expansion = audit["final_response_expansion"]
    check("Both final emitted outputs expand in the declared estimator",
          expansion["mcp_expands"] and expansion["hook_expands"]
          and expansion["backend"] == "heuristic")
    check("Meaning-changing prose fixture reproduced",
          audit["prose_literal_preservation"]["finding_reproduced"])
    check("Direct recovery versus truncated MCP delivery distinguished",
          audit["retrieval_delivery"]["direct_CCR_exact"]
          and not audit["retrieval_delivery"]["MCP_exact"])
    check("Graph-refresh limitation reproduced",
          not audit["graph_freshness"]["reloads_after_file_change"])
    math = audit["illustrative_cache_economics"]
    check("Illustrative cost arithmetic consistent",
          abs(math["transition_cost_ratio"] - 5000 / 1900) < 1e-12
          and math["requests_until_total_cost_break_even"] == 5
          and math["synthetic_not_measured"])
    baseline = (BASE / "pytest-baseline.txt").read_text(encoding="utf-8")
    check("Baseline result is explicitly 110 passes / 10 failures",
          "10 failed, 110 passed" in baseline and "110 passed, 10 failed" in report)
    baseline_run = load("pytest-baseline-run.json")
    check("Baseline interpreter and command provenance recorded",
          bool(baseline_run["python_version"]) and bool(baseline_run["command"])
          and baseline_run["exit_code"] == 1
          and all(not baseline_run["dependencies_available"][name]
                  for name in ("tree_sitter", "tree_sitter_python", "tree_sitter_rust")))
    check("Main report has balanced fenced code blocks", report.count("```") % 2 == 0)
    ast.parse((BASE / "audit_local.py").read_text(encoding="utf-8"))
    check("Research probe source parses", True)

    artifacts = [
        "FUNDAMENTAL-RESEARCH.md", "FINAL-REVIEW.md", "audit_local.py", "local-audit.json",
        "local-source-index.json", "pytest-baseline.txt", "pytest-baseline-run.json",
        "papers/research-memo.md", "papers/sources.json", "papers/verification.json",
        "oss/REPORT.md", "oss/evidence.json", "oss/validation.json",
        "reducers/REVIEW.md", "reducers/summary.json", "reducers/source-index.json",
    ]
    result = {
        "review_date": "2026-10-04",
        "scope": "Research consistency and source provenance; not a model benchmark.",
        "passed": all(row["passed"] for row in checks),
        "check_count": len(checks),
        "checks": checks,
        "artifact_sha256": {name: digest(BASE / name) for name in artifacts},
        "limitations": [
            "No new paid model/provider benchmark.",
            "No upstream project execution or test run.",
            "Production unit tests have 10 dependency-limited failures.",
            "Local emitted-token probe uses the shipped heuristic fallback.",
            "Live Claude/Copilot hook acceptance was not tested.",
            "The parallel parity chat has its own validation.",
        ],
    }
    (BASE / "validation.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "passed": result["passed"],
        "check_count": len(checks),
        "failed_checks": [row for row in checks if not row["passed"]],
    }, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
