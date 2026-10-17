"""Artifact checks only; does not claim to establish theorem hypotheses."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import subprocess

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]
REVIEWED_SHA = "90153cfa2415659970b3286b40e7d2159192f987dff869a0d8a109d150eb257c"
PRECEDENT_PARAGRAPH = (
    "**Direct precedent:** TypeSafe's autoresearch feature-discovery cookbook\n"
    "combines generated questions, Jev features and a supervised learner without\n"
    "updating Jev's weights. It is an empirical example, not the certificate\n"
    "developed here. `COOKBOOK-ADAPTATION.md` separates that precedent from a\n"
    "proposed TokenMaster implementation, including a no-extra-model-training option.\n\n"
).encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    checks = []

    def check(name, passed, detail=None):
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    proof = (BASE / "PROOFS-AND-CONTINUOUS-IMPROVEMENT.md").read_bytes()
    check("Mathematical content matches independently reviewed snapshot",
          proof.count(PRECEDENT_PARAGRAPH) == 1
          and digest(proof.replace(PRECEDENT_PARAGRAPH, b"", 1)) == REVIEWED_SHA)

    math = json.loads((BASE / "math-checks.json").read_text(encoding="utf-8"))
    check("All 35 supplementary numerical checks passed",
          math["passed"] and math["check_count"] == 35
          and all(row["passed"] for row in math["checks"]))
    ast.parse((BASE / "math_checks.py").read_text(encoding="utf-8"))
    check("Numerical checker parses", True)

    meta = json.loads((BASE / "jev/source-metadata.json").read_text(encoding="utf-8"))
    matched = []
    for source in meta["sources"]:
        raw = (BASE / "jev" / source["snapshot"]).read_bytes()
        matched.append(digest(raw) == source["sha256"].lower())
    check("All 19 cited Jev source hashes match",
          len(matched) == 19 and all(matched))
    check("Corrected Jev paper is in source metadata",
          meta["paper"]["related_paper_id"] == "2609.29769")

    head = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--porcelain"], text=True
    ).strip()
    check("Production source remains at the studied revision",
          head == "426fc853389ddba4bc6e1dd35a28179a895c064f")
    check("Tracked/unignored checkout remains clean", not status, status or "clean")

    files = (
        "PROOFS-AND-CONTINUOUS-IMPROVEMENT.md",
        "COOKBOOK-ADAPTATION.md",
        "REVIEW-AND-VALIDATION.md",
        "math_checks.py",
        "math-checks.json",
        "jev/evidence-memo.md",
        "jev/source-metadata.json",
        "references/foundational-reference-memo.md",
        "references/foundational-reference-metadata.json",
    )
    result = {
        "date": "2026-10-04",
        "passed": all(row["passed"] for row in checks),
        "checks": checks,
        "artifacts_sha256": {
            name: digest((BASE / name).read_bytes()) for name in files
        },
        "reviewed_mathematics_sha256": REVIEWED_SHA,
        "limitations": [
            "Written mathematics was reviewed, not mechanically proved.",
            "Numerical checks do not establish deployment assumptions.",
            "No model inference, production optimizer or performance benchmark was run.",
            "The source-only cookbook paragraph was added after mathematical review.",
        ],
    }
    (BASE / "validation.json").write_bytes(
        (json.dumps(result, indent=2) + "\n").encode("utf-8")
    )
    print(json.dumps({
        "passed": result["passed"],
        "checks": len(checks),
        "failed": [row for row in checks if not row["passed"]],
    }, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
