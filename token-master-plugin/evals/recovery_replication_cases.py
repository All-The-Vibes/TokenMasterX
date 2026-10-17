"""Private bounded replication corpus, not source-independent or population proof.

Only Case.public_task() and exact source fixtures belong in model context. Keep
gold, evidence, and overlap metadata private. Candidate execution and recovery
tool descriptions remain parent-owned; this module changes no retention policy.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from quality.cases import Case


SOURCE_COMMIT = "426fc853389ddba4bc6e1dd35a28179a895c064f"
MANIFEST_PATH = Path(__file__).with_name("recovery-replication-cases.json")
MANIFEST_SHA256 = "f244085629b0c103f1a914609f485fbee8e0bbed6d8bcf23d4dcd4ed581277f9"
ORACLE_ID = "source-backed-readonly-recovery-replication-v1:" + MANIFEST_SHA256

# Load trusted evaluator code in a private namespace, not fixture/candidate code.
# Never modify the existing parity or retention modules or their constants.
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
    """Use the shared validator to check the immutable pin before trusting gold."""
    return _oracle.load_cases()


def grade(case, workspace, answer, events, *, sandbox_runner=None):
    """Delegate strict answer and read-only checks; never execute fixture code."""
    return _oracle.grade(case, workspace, answer, events, sandbox_runner=sandbox_runner)
