"""Held-out, pinned-source challenge definitions and a non-executing oracle.

Only Case.public_task() and Case.fixtures belong in model context. The manifest,
expected answers, source-line evidence and grading results are operator-only.
Six purposively chosen cases are exploratory, not an IID or production certificate.
The parent runner owns fetch_artifact(path): it must return the same exact UTF-8
fixture text as read_file, without a wrapper or newline normalization.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from quality.cases import Case, digest, safe_path
from quality.oracle import _snapshot
from quality.responses import parse_json


SOURCE_COMMIT = "426fc853389ddba4bc6e1dd35a28179a895c064f"
MANIFEST_PATH = Path(__file__).with_name("parity-cases.json")
MANIFEST_SHA256 = "a61f595eb7c2657667291d8722689f30e718255bb909d91ffffe106f75770345"
ORACLE_ID = "source-backed-readonly-parity-v2:" + MANIFEST_SHA256


def _load_manifest():
    """Check the independently frozen byte digest BEFORE parsing/trusting gold.

    Return a fresh private object, not mutable shared oracle state. Recheck on
    every load/grade so an on-disk change cannot silently redefine the workload.
    """
    raw = MANIFEST_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError("parity manifest integrity mismatch")
    manifest = parse_json(raw.decode("utf-8"))
    if manifest["schema_version"] != 1 or manifest["source_commit"] != SOURCE_COMMIT:
        raise ValueError("parity manifest provenance mismatch")
    sources = {}
    for source in manifest["sources"]:
        path = safe_path(source["path"])
        content = source["text"].encode("utf-8")
        if (path in sources or source["commit"] != SOURCE_COMMIT
                or source["encoding"] != "utf-8"
                or type(source["byte_length"]) is not int
                or len(content) != source["byte_length"]
                or hashlib.sha256(content).hexdigest() != source["sha256"]):
            raise ValueError("parity source integrity mismatch")
        sources[path] = source
    ids = set()
    for task in manifest["tasks"]:
        if (task["id"] in ids or task["allowed_changes"] != []
                or len(set(task["source_paths"])) != len(task["source_paths"])
                or not set(task["source_paths"]) <= sources.keys()):
            raise ValueError("invalid parity task")
        ids.add(task["id"])
        covered = set()
        for evidence in task["evidence"]:
            path = evidence["path"]
            start, end = evidence["start_line"], evidence["end_line"]
            if path not in task["source_paths"]:
                raise ValueError("evidence outside task sources")
            lines = sources[path]["text"].splitlines(keepends=True)
            if (type(start) is not int or type(end) is not int
                    or not 1 <= start <= end <= len(lines)
                    or "".join(lines[start - 1:end]) != evidence["quote"]
                    or not evidence["rationale"]
                    or not set(evidence["answer_keys"]) <= task["expected"].keys()):
                raise ValueError("invalid source-line evidence")
            covered.update(evidence["answer_keys"])
        if covered != task["expected"].keys():
            raise ValueError("answer missing source-line evidence")
    return manifest


def _case(task, sources):
    return Case(
        id=task["id"], version=task["version"], prompt=task["prompt"],
        fixtures=tuple((path, sources[path]) for path in task["source_paths"]),
        allowed_changes=(), intent=task["intent"],
    )


def load_cases() -> list[Case]:
    """Public case objects contain source fixtures and questions, never gold."""
    manifest = _load_manifest()
    sources = {source["path"]: source["text"] for source in manifest["sources"]}
    return [_case(task, sources) for task in manifest["tasks"]]


def _exact_json(actual, expected):
    """JSON equality with exact recursive types (True != 1 != 1.0).

    Dict order is immaterial; list order, strings, fields and primitive types are
    exact. Tuples, subclasses and coerced values are not JSON substitutes.
    """
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return (all(type(key) is str for key in actual)
                and actual.keys() == expected.keys()
                and all(_exact_json(actual[key], value) for key, value in expected.items()))
    if type(expected) is list:
        return (len(actual) == len(expected)
                and all(_exact_json(a, b) for a, b in zip(actual, expected)))
    return actual == expected


def _readonly_events(events):
    """Fail closed on unknown/malformed actions; record attempts, not just bytes.

    Trusted parent events must include attempted tool calls, including rejected
    writes. This oracle cannot detect actions omitted by the supervising runner.
    Python/shell execution is not part of this read-only retrieval workload.
    """
    if type(events) not in (list, tuple):
        return False
    fields = {
        "list_files": set(), "read_file": {"path"}, "fetch_artifact": {"path"},
        "retrieve_original": {"ref", "offset"}, "search_original": {"ref", "query"},
        "headroom_retrieve": {"hash"},
        "answer": {"content"},
    }
    for event in events:
        if type(event) is not dict:
            return False
        name, args = event.get("name"), event.get("arguments")
        if (type(name) is not str or name not in fields or type(args) is not dict
                or set(args) != fields[name]):
            return False
        if name == "headroom_retrieve" and type(args["hash"]) is not str:
            return False
        if name in ("read_file", "fetch_artifact"):
            if type(args["path"]) is not str:
                return False
            try:
                safe_path(args["path"])
            except ValueError:
                return False
    return True


def grade(case, workspace, answer, events, *, sandbox_runner=None):
    """quality.runner verdict; never execute candidate or fixture source.

    sandbox_runner is accepted for the shared interface and deliberately unused.
    Whole-workspace byte comparisons catch edits, additions and deletions; event
    checks also catch same-byte writes and write-then-restore attempts.
    """
    checks = {
        "manifest_integrity": False, "known_case": False,
        "safe_workspace": False, "no_extra_files": False,
        "no_missing_files": False, "fixture_bytes_unchanged": False,
        "write_scope_respected": _readonly_events(events),
        "document_artifacts_fetched": False,
        "answer_matches_source_contract": False,
    }
    changed, unexpected, missing = [], [], []
    evidence = {}
    try:
        manifest = _load_manifest()
        checks["manifest_integrity"] = True
        sources = {source["path"]: source["text"] for source in manifest["sources"]}
        task = next((task for task in manifest["tasks"]
                     if type(case) is Case and task["id"] == case.id), None)
        trusted = _case(task, sources) if task else None
        checks["known_case"] = trusted is not None and case.identity == trusted.identity
        if checks["known_case"]:
            fetched = {event["arguments"]["path"] for event in events
                       if event["name"] == "fetch_artifact"} if checks["write_scope_respected"] else set()
            checks["document_artifacts_fetched"] = (
                task["category"] != "document_retrieval"
                or set(task["source_paths"]) <= fetched
            )
            originals = {path: text.encode("utf-8") for path, text in trusted.fixtures}
            files = _snapshot(workspace)
            checks["safe_workspace"] = True
            unexpected = sorted(files.keys() - originals.keys())
            missing = sorted(originals.keys() - files.keys())
            changed = sorted(path for path in originals.keys() & files.keys()
                             if files[path] != originals[path])
            checks.update(
                no_extra_files=not unexpected, no_missing_files=not missing,
                fixture_bytes_unchanged=not changed,
                answer_matches_source_contract=_exact_json(answer, task["expected"]),
            )
            evidence["case_identity"] = trusted.identity
            evidence["workspace"] = {path: hashlib.sha256(data).hexdigest()
                                     for path, data in sorted(files.items())}
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        evidence["validation_error"] = type(exc).__name__
    # Bind actual evidence, not only a verdict whose failed answers all hash alike.
    try:
        evidence["submission_digest"] = digest({"answer": answer, "events": events})
    except (ValueError, TypeError, RecursionError):
        checks["answer_matches_source_contract"] = False
        evidence["invalid_submission"] = True
    success = all(checks.values())
    result = dict(
        status="passed" if success else "failed", success=success,
        checks=[name for name, passed in checks.items() if not passed],
        assertions=checks, changed_files=changed, unexpected_files=unexpected,
        missing_files=missing, oracle=ORACLE_ID,
    )
    result["evidence_digest"] = digest({"verdict": result, "evidence": evidence})
    return result
