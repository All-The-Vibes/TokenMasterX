#!/usr/bin/env python
"""Benchmark guarded views and actual recovery, not whole-task model quality.

Use the already provisioned pinned Python runtime and a verified local tokenizer:
  python brainspace_benchmark.py data.json --intent overview --json
  python brainspace_benchmark.py ./logs
  python brainspace_benchmark.py --stdin --hint=fixture.log --intent=overview

No arguments use installed source as a demo corpus. --turns supplies only an
illustrative replay projection, not a captured whole-task total. --max-files
limits directory walking. Missing exact tokenization makes transforms no-ops;
estimates remain labeled. Recovery results distinguish unchanged, root_exact,
fragments_exact, unverified and failed. Failed/unverified required recovery exits
nonzero. Conservative JSON whitespace changes may be unverified for exact-text
recovery, even though their literal values are retained. No dependency resolving
or downloads occur at launch.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from brainspace.benchmark import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
