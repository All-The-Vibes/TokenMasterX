"""Recompute a quality study offline. Exit 0 means audit consistency, not savings."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "skills" / "token-master"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--baseline", default="baseline")
    parser.add_argument("--candidate", default="combined")
    parser.add_argument("--use-recorded-reviews", action="store_true",
                        help="Explicitly include hash-matched saved blinded-review verdicts.")
    parser.add_argument("--expect-evidence-digest",
                        help="Reject any change from an externally retained prior evidence digest.")
    parser.add_argument("--output", type=Path, help="Write a NEW JSON receipt; existing files are never overwritten.")
    args = parser.parse_args()
    # No downloads or ambient tokenizer selection: verify the study's frozen bytes.
    os.environ["BRAINSPACE_TOKENIZER_FILE"] = str(args.study.absolute() / "cl100k_base.tiktoken")
    from quality.savings import AuditError, verify_study
    try:
        report = verify_study(
            args.study, baseline=args.baseline, candidate=args.candidate,
            use_recorded_reviews=args.use_recorded_reviews,
            expected_evidence_digest=args.expect_evidence_digest,
        )
        text = json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False)
        if args.output is None:
            print(text)
        else:
            # No parent creation or replace: cannot silently overwrite source/evidence.
            from quality.cases import safe_root
            target = safe_root(args.output)
            with target.open("x", encoding="utf-8") as stream:
                stream.write(text + "\n")
            print(json.dumps({
                "audit_status": report["audit_status"], "receipt": str(target),
                "evidence_digest": report["evidence_digest"],
                "body_reference_saved_percent": report["comparison"]["api_body_reference"]["saved_percent"],
                "bridge_reported_saved_percent": report["comparison"]["provider_reported"]["saved_percent"],
                "all_outcomes_known": report["quality"]["all_outcomes_known"],
                "new_failures": report["quality"]["new_failures"],
                "statistical_certificate": None,
            }, indent=2))
        return 0
    except (AuditError, OSError, ValueError) as error:
        print(json.dumps({"audit_status": "rejected",
                          "reason": str(error) if isinstance(error, AuditError) else type(error).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
