"""Private, prespecified retention-policy holdout; no population certificate.

Only returned Case.public_task() and fixtures may enter model context. Gold and
source-line evidence remain in the operator-only manifest. Reuse the completed
parity oracle in a separate module namespace, never patch its live module.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from quality.cases import Case


SOURCE_COMMIT = "426fc853389ddba4bc6e1dd35a28179a895c064f"
MANIFEST_PATH = Path(__file__).with_name("retention-cases.json")
MANIFEST_SHA256 = "b6467635053b67d5e704e6b6de167291050b3db0969641c04b0dae6b079bd990"
ORACLE_ID = "source-backed-readonly-retention-v1:" + MANIFEST_SHA256

# This loads trusted evaluator code, NOT candidate/fixture source. Do not insert
# it into sys.modules or mutate the public parity_cases module's constants.
_spec = importlib.util.spec_from_file_location(
    __name__ + "._shared_oracle", Path(__file__).with_name("parity_cases.py"))
if _spec is None or _spec.loader is None:
    raise ImportError("shared parity oracle is unavailable")
_oracle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_oracle)
for _name, _value in (
    ("SOURCE_COMMIT", SOURCE_COMMIT), ("MANIFEST_PATH", MANIFEST_PATH),
    ("MANIFEST_SHA256", MANIFEST_SHA256), ("ORACLE_ID", ORACLE_ID),
):
    setattr(_oracle, _name, _value)


def load_cases() -> list[Case]:
    """Load holdout cases only after the shared validator checks the frozen pin."""
    return _oracle.load_cases()


def grade(case, workspace, answer, events, *, sandbox_runner=None):
    """Use the shared strict, read-only oracle without executing fixture code."""
    return _oracle.grade(case, workspace, answer, events, sandbox_runner=sandbox_runner)
