"""Private, frozen authored coding challenges; not representative production data.

Public interface:
    load_cases() -> list[quality.cases.Case]
    grade(case, root, answer, events, *, sandbox_runner=None) -> dict
    ORACLE_ID: str

Only Case.public_task() and Case.fixtures may enter model messages. This module,
the manifest's hidden_tests, validation patches, plans, and oracle results must
remain supervisor-only. Candidate code is never imported/evaluated on the host.
The parent supplies quality.sandbox.sandbox_runner; absence fails closed.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from quality.cases import Case, digest, safe_path
from quality.oracle import _changes, _snapshot
from quality.responses import parse_json


MANIFEST_PATH = Path(__file__).with_name("fresh-coding-cases.json")
CORPUS_SHA256 = "adac035584ead220b5bf9e9e359ff55febc38ab93de11e61f9f42d8da6c6834d"
MANIFEST_SHA256 = CORPUS_SHA256
SCOPE = "independently_authored_challenges_not_iid_or_representative_production_data"
MAX_TOOL_CALLS = 10
# Bind the grader and actual shared isolation contract as well as the corpus.
ORACLE_ID = "authored-fresh-coding-v1:" + digest({
    "corpus_sha256": CORPUS_SHA256,
    "implementation": {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (
            Path(__file__), Path(__file__).parent / "quality" / "cases.py",
            Path(__file__).parent / "quality" / "oracle.py",
            Path(__file__).parent / "quality" / "sandbox.py",
            Path(__file__).parent / "quality" / "sandbox_bootstrap.py",
        )
    },
})


def _load_manifest():
    """Recheck pinned bytes on every load/grade; return a fresh private object."""
    raw = MANIFEST_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CORPUS_SHA256:
        raise ValueError("fresh coding manifest integrity mismatch")
    manifest = parse_json(raw.decode("utf-8"))
    if (manifest["schema_version"] != 1 or manifest["corpus_id"] != "authored-fresh-coding-v1"
            or manifest["scope"] != SCOPE or manifest["max_tool_calls"] != MAX_TOOL_CALLS
            or len(manifest["tasks"]) != 4):
        raise ValueError("fresh coding manifest contract mismatch")
    cases = [_case(task) for task in manifest["tasks"]]
    if len({case.id for case in cases}) != 4:
        raise ValueError("duplicate task")
    for task, case in zip(manifest["tasks"], cases):
        if (len(case.fixtures) != 3 or len(case.allowed_changes) != 2
                or len(set(case.allowed_changes)) != 2 or case.intent != "edit"
                or any(not path.endswith(".py") for path in case.allowed_changes)
                or not isinstance(task["hidden_tests"], str) or not task["hidden_tests"]):
            raise ValueError("invalid coding task")
    return manifest


def _case(task):
    return Case(
        id=task["id"], version=task["version"], prompt=task["prompt"],
        fixtures=tuple(task["fixtures"].items()),
        allowed_changes=tuple(task["allowed_changes"]), intent=task["intent"],
    )


def load_cases() -> list[Case]:
    """Return exactly four public tasks, with no held-out tests or gold patches."""
    return [_case(task) for task in _load_manifest()["tasks"]]


def _events(case, events):
    """Audit all attempts, including rejected/restored writes; parent owns capture.

    Reading is evidenced by read_file/fetch_artifact requests, not comprehension.
    Recovery tools do not replace initial reads of the three known small files.
    Accept runner metadata but strictly validate the eight tools' arguments.
    """
    if type(events) not in (list, tuple) or len(events) > MAX_TOOL_CALLS:
        return False, False
    fields = {
        "list_files": set(), "read_file": {"path"}, "fetch_artifact": {"path"},
        "write_file": {"path", "content"}, "retrieve_original": {"ref", "offset"},
        "search_original": {"ref", "query"}, "headroom_retrieve": {"hash"},
        "answer": {"content"},
    }
    read, answered, read_before_edits = set(), False, True
    for event in events:
        if type(event) is not dict:
            return False, False
        name, args = event.get("name"), event.get("arguments")
        if (type(name) is not str or name not in fields or type(args) is not dict
                or set(args) != fields[name] or answered):
            return False, False
        if "path" in args:
            if safe_path(args["path"]) not in case.files:
                return False, False
        if name in ("read_file", "fetch_artifact"):
            read.add(args["path"])
        elif name == "write_file":
            if (args["path"] not in case.allowed_changes or type(args["content"]) is not str
                    or len(args["content"].encode("utf-8")) > 524288):
                return False, False
            if read != set(case.files):
                read_before_edits = False
        elif name in ("retrieve_original", "search_original"):
            if type(args["ref"]) is not str:
                return False, False
            if name == "retrieve_original" and (
                type(args["offset"]) is not int or args["offset"] < 0
            ):
                return False, False
            if name == "search_original" and type(args["query"]) is not str:
                return False, False
        elif name == "headroom_retrieve" and type(args["hash"]) is not str:
            return False, False
        elif name == "answer":
            answered = True
    return True, read_before_edits and read == set(case.files)


def _plan(case, files, tests):
    plan = dict(
        case_identity=case.identity, oracle_identity=digest(ORACLE_ID),
        sources={path: data.decode("utf-8") for path, data in sorted(files.items())},
        test_code=tests, timeout_seconds=3,
    )
    return dict(plan, identity=digest(plan))


def _boundary_ready(reply):
    """Require trusted supervisor receipts, never a candidate stdout assertion."""
    boundary = reply.get("boundary")
    return type(boundary) is dict and all(
        boundary.get(name) is True for name in (
            "ready", "executed", "host_canary_present", "host_canary_hidden",
            "host_listener_present", "host_listener_unreachable", "readonly_root",
            "no_host_proc", "no_new_privs", "process_reaped", "scoped_cleanup",
        )
    ) and (
        boundary.get("capabilities") == "zero"
        and boundary.get("seccomp") == "x86_64_allowlist"
        and boundary.get("completion") == "waitpid"
        and boundary.get("preflight_status") == "passed"
        and boundary.get("max_candidate_processes") == 1
        and boundary.get("memory_bytes") == 256 * 1024 * 1024
        and boundary.get("wall_seconds") == 3
    )


def grade(case, root, answer, events, *, sandbox_runner=None):
    """Runner-compatible final oracle, called only AFTER the model's answer.

    sandbox_runner(plan) must be the trusted quality.sandbox.sandbox_runner (or
    a trusted test double). Inconclusive/missing isolation yields success=None,
    never a pass. Plain summaries are accepted; executable behavior decides.
    """
    assertions = {
        "manifest_integrity": False, "known_case": False, "valid_submission": False,
        "safe_workspace": False, "source_scope_preserved": False,
        "tool_scope_respected": False, "all_files_read_before_edits": False,
        "workspace_stable": False, "isolated_behavior_passed": False,
    }
    evidence, changed, forbidden = {}, [], []
    status, reason = "failed", None
    try:
        manifest = _load_manifest()
        assertions["manifest_integrity"] = True
        task = next((t for t in manifest["tasks"] if type(case) is Case and t["id"] == case.id), None)
        trusted = _case(task) if task else None
        assertions["known_case"] = trusted is not None and trusted.identity == case.identity
        evidence["submission_digest"] = digest({"answer": answer, "events": events})
        assertions["valid_submission"] = True
        if assertions["known_case"] and trusted is not None and task is not None:
            assertions["tool_scope_respected"], assertions["all_files_read_before_edits"] = _events(
                trusted, events
            )
            files = _snapshot(root)
            assertions["safe_workspace"] = True
            forbidden = _changes(trusted, files)
            changed = sorted(path for path, text in trusted.fixtures
                             if files.get(path) != text.encode("utf-8"))
            assertions["source_scope_preserved"] = not forbidden
            evidence["workspace"] = {path: hashlib.sha256(data).hexdigest()
                                     for path, data in sorted(files.items())}
            prerequisites = all(value for key, value in assertions.items()
                                if key not in ("workspace_stable", "isolated_behavior_passed"))
            if prerequisites:
                if sandbox_runner is None:
                    status, reason = "inconclusive", "sandbox_required"
                else:
                    plan = _plan(trusted, files, task["hidden_tests"])
                    identity = plan["identity"]
                    try:
                        reply = sandbox_runner(plan)
                        evidence["execution_digest"] = digest(reply)
                        assertions["workspace_stable"] = _snapshot(root) == files
                        if not assertions["workspace_stable"]:
                            reason = "workspace_changed_during_validation"
                        elif type(reply) is not dict or reply.get("plan_identity") != identity:
                            status, reason = "inconclusive", "invalid_sandbox_attestation"
                        elif not _boundary_ready(reply):
                            boundary = reply.get("boundary", {})
                            # An authenticated, bounded AST-policy rejection is a
                            # candidate failure, not permission for a host fallback.
                            if (type(boundary) is dict and boundary.get("executed") is False
                                    and boundary.get("stage") == "preflight"
                                    and boundary.get("preflight_status") == "rejected"
                                    and boundary.get("process_reaped") is True
                                    and boundary.get("scoped_cleanup") is True):
                                reason = "candidate_rejected_by_sandbox_policy"
                            else:
                                status, reason = "inconclusive", "sandbox_boundary_unavailable"
                        elif (type(reply.get("exit_code")) is not int
                              or type(reply.get("timed_out")) is not bool):
                            status, reason = "inconclusive", "invalid_sandbox_completion"
                        elif reply["exit_code"] != 0 or reply["timed_out"] or reply.get("output_limit_exceeded"):
                            reason = "hidden_behavior_tests_failed"
                        elif reply.get("stdout") != "FRESH_CODING_OK\n" or reply.get("stderr") != "":
                            status, reason = "inconclusive", "missing_test_completion"
                        else:
                            assertions["isolated_behavior_passed"] = True
                            status = "passed"
                    except Exception as exc:
                        evidence["sandbox_error_type"] = type(exc).__name__
                        status, reason = "inconclusive", "sandbox_error"
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        evidence["validation_error_type"] = type(exc).__name__
    result = dict(
        status=status, success={"passed": True, "failed": False}.get(status),
        checks=[name for name, passed in assertions.items() if not passed],
        assertions=assertions, changed_files=changed, forbidden_files=forbidden,
        oracle=ORACLE_ID, corpus_sha256=CORPUS_SHA256, scope=SCOPE,
    )
    if reason:
        result["checks"].append(reason)
    # Store only hashes and generic verdicts, not hidden failure inputs/messages.
    result["evidence_digest"] = digest({"verdict": result, "evidence": evidence})
    return result
