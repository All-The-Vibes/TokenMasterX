"""Synthetic reference-token accounting checks; no tokenizer/model execution."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import subprocess

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]


def summarize(calls, phase="deployment"):
    if phase not in ("deployment", "learning") or any(
        item["phase"] not in ("deployment", "learning") for item in calls
    ):
        raise ValueError("unknown phase must not disappear from accounting")
    ids = [row["id"] for row in calls]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate model invocation")
    selected = [row for row in calls if row["phase"] == phase]
    protocols = {(row["tokenizer"], row["protocol"]) for row in selected}
    if len(protocols) > 1:
        raise ValueError("incompatible measurements")
    for row in selected:
        if row["coverage"] != "complete_for_declared_boundary":
            raise ValueError("incomplete trace")
        if any(type(row[k]) is not int or row[k] < 0 for k in ("input", "output")):
            raise ValueError("missing or invalid reference-token count")
    incoming = sum(row["input"] for row in selected)
    outgoing = sum(row["output"] for row in selected)
    return {
        "input": incoming,
        "output": outgoing,
        "total": incoming + outgoing,
        "peak_input": max((row["input"] for row in selected), default=0),
        "calls": len(selected),
    }


def row(identifier, incoming, outgoing, *, phase="deployment", role="primary"):
    return {
        "id": identifier, "input": incoming, "output": outgoing,
        "phase": phase, "role": role,
        "tokenizer": "synthetic-fixed-reference",
        "protocol": "example-v1",
        "coverage": "complete_for_declared_boundary",
    }


def per_success(total, successes):
    return total / successes if successes > 0 else None


def main():
    checks = []

    def check(name, condition):
        checks.append({"check": name, "passed": bool(condition)})

    def rejects(name, rows):
        try:
            summarize(rows)
        except ValueError:
            check(name, True)
        else:
            check(name, False)

    baseline = [row("a1", 1000, 100), row("a2", 1500, 200), row("a3", 2000, 300)]
    candidate = [
        row("b1", 1000, 100), row("b2", 1100, 100),
        row("jev", 200, 20, role="auxiliary"),
    ]
    learning = [
        row("s1", 400, 100, phase="learning"),
        row("s2", 600, 50, phase="learning", role="verification"),
    ]
    a, b = summarize(baseline), summarize(candidate)
    check("Cumulative input is the sum of invocations, not final context",
          a["input"] == 4500 and a["input"] != baseline[-1]["input"])
    check("All returned text is included", a["output"] == 600)
    check("Combined runtime footprint", a["total"] == 5100)
    check("Peak context remains a separate metric", a["peak_input"] == 2000)
    check("Runtime Jev is included rather than hidden",
          b == {"input": 2300, "output": 220, "total": 2520,
                "peak_input": 1100, "calls": 3})
    check("Learning and deployment invocations are disjoint",
          summarize(candidate + learning) == b)
    search = summarize(candidate + learning, phase="learning")
    check("Learning tokens are measured separately", search["total"] == 1150)
    check("Declared-horizon aggregate counts learning once",
          search["total"] + b["total"] == 3670)

    diagnostics = [dict(item, native_input=999999, cached_input=999999)
                   for item in candidate]
    check("Native/cache diagnostics do not discount or mix reference tokens",
          summarize(diagnostics) == b)
    check("Failures remain in the batch numerator",
          per_success(30000, 3) == 10000)
    check("Lower total with lower success can mean no efficiency improvement",
          per_success(20000, 2) == per_success(30000, 3))
    check("Zero successes is not reported as zero tokens per success",
          per_success(20000, 0) is None)

    rejects("Duplicate invocations cannot be counted twice", [candidate[0], candidate[0]])
    rejects("Partial coverage cannot produce a complete score",
            [dict(candidate[0], coverage="partial")])
    rejects("Unknown count is not silently zero", [dict(candidate[0], output=None)])
    rejects("Negative token count is rejected", [dict(candidate[0], input=-1)])
    rejects("Mixed tokenizer versions cannot be summed",
            [candidate[0], dict(candidate[1], tokenizer="other")])
    rejects("Mixed extraction protocols cannot be summed",
            [candidate[0], dict(candidate[1], protocol="other")])
    rejects("Unknown phases cannot silently hide invocations",
            [dict(candidate[0], phase="unclassified")])

    alpha = 0.05
    alpha_k = 6 * alpha / math.pi**2
    n = 1000
    radius = math.sqrt(2 * math.log(2 / alpha_k) / n)
    check("Token-difference specialization keeps the correct Hoeffding constant",
          math.isclose(2 * math.exp(-n * radius**2 / 2), alpha_k, rel_tol=1e-12))
    token_a, token_b, quality_a, quality_b = 5100, 2520, 0.8, 0.8
    check("Lower expected tokens with maintained quality lowers the ratio",
          token_b / quality_b < token_a / quality_a)

    status = subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--porcelain"], text=True
    ).strip()
    check("No production source changes", status == "")
    result = {
        "date": "2026-10-04",
        "passed": all(item["passed"] for item in checks),
        "check_count": len(checks),
        "checks": checks,
        "examples": {"baseline": a, "candidate": b, "learning": search},
        "framework_sha256": hashlib.sha256((BASE / "FRAMEWORK.md").read_bytes()).hexdigest(),
        "limitations": [
            "Synthetic counts, not model or tokenizer measurements.",
            "Coverage flags are asserted fixtures, not demonstrated instrumentation.",
            "No latency, hardware-efficiency, quality or token-saving benchmark was run.",
            "Mathematical guarantees still require the stated sampling and oracle assumptions.",
        ],
    }
    (BASE / "validation.json").write_bytes(
        (json.dumps(result, indent=2) + "\n").encode("utf-8")
    )
    print(json.dumps({
        "passed": result["passed"],
        "checks": len(checks),
        "failed": [item for item in checks if not item["passed"]],
    }, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
