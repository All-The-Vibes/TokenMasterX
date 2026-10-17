"""Explicit synthetic Jev API check. Reads the key only from the process env."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import uuid

SKILL = Path(__file__).resolve().parents[1] / "skills" / "token-master"
sys.path.insert(0, str(SKILL))

from brainspace.jev import JevClient, MODEL  # noqa: E402
from brainspace.token_ledger import COMPLETE, TaskTrace, TokenLedger, measure_call  # noqa: E402
from brainspace.tokens import count_tokens, measurement_identity  # noqa: E402


def run():
    identity = measurement_identity("complete-visible-JSON-body-text-v1")
    questions = {
        "view": {"type": "choice", "instructions": "Select the view for this synthetic task.",
                 "criteria": {"navigation": "Read-only names or structure.",
                              "exact": "Editing, debugging, or exact quoted source.",
                              "unchanged": "No match."}},
        "relevance": {"type": "score", "instructions": "How relevant is code navigation?",
                      "criteria": ["Not relevant", "Somewhat relevant", "Directly relevant"]},
        "read_only": {"type": "noul", "instructions": "The task requests read-only navigation."},
    }
    result = JevClient(enabled=True, allow_network=True).decide(
        {"fixture": "synthetic", "task": "List module and function names without editing."},
        questions, data_classification="synthetic",
    )
    report = {
        "ok": result.ok, "reason": result.reason, "synthetic_only": True,
        "advisory_only": True, "task_quality_verified": False,
        "diagnostics": asdict(result.diagnostics),
        "coverage": "partial", "learning_ledger": None,
    }
    if result.request_text is not None and result.response_text is not None and result.diagnostics.response_complete:
        task = "jev-smoke-" + uuid.uuid4().hex
        call = measure_call(
            identity, count_tokens, input_text=result.request_text, output_text=result.response_text,
            call_id=task, task_id=task, attempt_id="1", phase="learning", role="auxiliary",
            model_id=MODEL, harness_id="synthetic-api-check", coverage=COMPLETE,
            completion_status="succeeded" if result.ok else "failed",
        )
        ledger = TokenLedger(identity)
        ledger.record(TaskTrace(task, "integration-check-v1", identity, "learning",
                                (call,), (call.call_id,), COMPLETE, "integration-check"))
        ledger.seal_learning_run("integration-check", (task,))
        report.update(coverage=COMPLETE, learning_ledger=ledger.summary())
    if result.ok:
        report["answers"] = result.payload["answers"]
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.allow_network:
        parser.error("explicit --allow-network is required; only synthetic state is sent")
    report = run()
    text = json.dumps(report, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    raise SystemExit(0 if report["ok"] else 1)
