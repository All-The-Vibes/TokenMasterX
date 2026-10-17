"""Held out: never send this module/plans/results to models. No code executes here.
sandbox_runner(plan) is TRUSTED: execute exact sources/tests in an OS sandbox with
no host/network/credentials, resource limits and 3s timeout; attest plan_identity,
exit_code/stdout/stderr/optional timed_out. Supervisor must authenticate completion,
not trust spoofable candidate stdout. Never use unrestricted host exec/subprocess.
"""
import hashlib
import os
from pathlib import Path

from .cases import CASES, digest, safe_path, safe_root


def oracle_identity():
    return digest({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (Path(__file__), Path(__file__).with_name("cases.py"))})


def _snapshot(root):
    root = safe_root(root)
    if not root.is_dir():
        raise ValueError("missing workspace")
    files, size = {}, 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            path = Path(directory) / name
            if path.is_symlink() or path.is_junction():
                raise ValueError("linked workspace entry")
        for name in names:
            path = Path(directory) / name
            relative = safe_path(path.relative_to(root).as_posix())
            if not path.is_file() or path.stat().st_size > 524288:
                raise ValueError("nonregular or oversized file")
            data = path.read_bytes()
            size += len(data)
            if size > 4194304 or len(files) >= 256:
                raise ValueError("workspace budget exceeded")
            files[relative] = data
    return files


def _changes(case, files):
    original = {p: s.encode() for p, s in case.fixtures}
    return sorted(p for p in set(original) | set(files)
                  if (p not in files or p not in original or
                      (files[p] != original[p] and p not in case.allowed_changes)))


_TESTS = {
    "small_fix": """import app
for values, width, expected in [
    ([], 1, None), ([6], 3, 6), ([1, 5, 9], 2, 7), ([2, 4], 8, 3),
    ([-5, 3], 2, -1), ([0], 1, 0), ([1.5, 2.5], 3, 2), ([4, 8, 9], 1, 9)]:
    before = list(values)
    assert app.trailing_mean(values, width) == expected
    assert values == before
for values in ([], [1, 2]):
    for width in (0, -1):
        try: app.trailing_mean(values, width)
        except ValueError: pass
        else: raise AssertionError('nonpositive width accepted')
print('QUALITY_OK')
""",
    "reusable_abstraction": """import scores
for value, low, high, expected in [
    (-4, 0, 100, 0), (140, 0, 100, 100), (40, 0, 100, 40), (0.5, 0, 1, 0.5),
    (-5, -9, -1, -5), (8, 3, 3, 3)]:
    assert scores.clamp(value, low, high) == expected
try: scores.clamp(1, 3, 2)
except ValueError: pass
else: raise AssertionError('reversed bounds accepted')
for value, expected in [(-1, 0), (120, 100), (70, 70)]:
    assert scores.score(value) == expected
for value, total, expected in [(1, 4, 25), (-1, 4, 0), (8, 4, 100)]:
    assert scores.percentage(value, total) == expected
try: scores.percentage(1, 0)
except ZeroDivisionError: pass
else: raise AssertionError('zero total accepted')
calls = []
def replacement(*args):
    calls.append(args)
    return 73
scores.clamp = replacement
assert scores.score(200) == 73
assert scores.percentage(1, 4) == 73
assert calls == [(200, 0, 100), (25, 0, 100)]
print('QUALITY_OK')
""",
}


def execution_plan(case, root):
    """Caller-only immutable-identity plan; test files never enter model workspace."""
    if case not in CASES or case.id not in _TESTS:
        raise ValueError("no executable oracle for case")
    files = _snapshot(root)
    if _changes(case, files):
        raise ValueError("forbidden workspace changes")
    plan = dict(case_identity=case.identity, oracle_identity=oracle_identity(),
                sources={p: data.decode("utf-8") for p, data in sorted(files.items())},
                test_code=_TESTS[case.id], timeout_seconds=3)
    return dict(plan, identity=digest(plan))


_ANSWERS = {
    "explain_only": {"returns": [10, None, 10], "stored": {"x": 10}},
    "json_exact": {"row_count": 241, "valid_count": 236, "sum_units": 35615,
                   "invalid_ids": ["r119", "r120", "r122", "r123"], "failed_ids": ["r121"],
                   "failed_record": {"id": "r121", "status": "FAILED", "units": 999999}},
    "rare_failure": {"failed_count": 1, "request": "R151", "code": "E28",
                     "cause": "disk full", "sequence": [149, 150, 151, 152]},
    "navigation": {"key": "normalize.173", "retry": 7, "note": "keep α / β; do not trim"},
    "graph_freshness": {"stale": True, "candidates": ["a.py:render", "b.py:render"],
                        "actual_edges": [["app.py:run", "b.py:render"]],
                        "obsolete_edges": [["app.py:run", "a.py:render"]]},
}
_PROOF_RUBRIC = [
    "Blind review labels: not_attempted / incorrect / correct; preserve the complete answer.",
    "Verify n is a positive integer, H_n definition, natural log and 1/x monotonicity.",
    "Check each interval comparison, integration limits, summation indices and both bounds.",
    "Check n=1, strictness for n>1, and numerical counterexample to H_n<=log(n).",
    "Reject gaps/circular reasoning; schema, keywords, length and confidence cannot prove depth.",
]


def _proof_shape(answer):
    return (type(answer) is dict and set(answer) == {
        "premises", "inequalities", "counterexample", "rationale"}
        and all(type(answer[k]) is list and answer[k] and
                all(type(x) is str and x.strip() for x in answer[k])
                for k in ("premises", "inequalities"))
        and type(answer["counterexample"]) is dict
        and set(answer["counterexample"]) == {"n", "lhs", "rhs"}
        and type(answer["rationale"]) is str and bool(answer["rationale"].strip()))


def evaluate(case, root, answer, *, stage_answers=(), sandbox_runner=None):
    """Independent evidence; success=None is ungraded; stage_answers excludes final.
    Parent orders stages and retains all calls/recovery latency. Not qualification."""
    result = dict(case_identity=case.identity, oracle_identity=oracle_identity(),
                  status="failed", success=False, checks=[], review_rubric=[], scope="non_iid_challenge_suite")
    evidence = dict(answer=answer, stage_answers=stage_answers)
    try:
        digest(evidence)
    except (TypeError, ValueError):
        evidence = {"invalid_answer_type": type(answer).__name__}
        result["checks"].append("non_json_answer")
        return _finish(result, evidence)
    try:
        files = _snapshot(root)
        evidence["workspace"] = {p: hashlib.sha256(v).hexdigest() for p, v in sorted(files.items())}
    except (OSError, ValueError) as exc:
        result["checks"].append("unsafe_workspace")
        evidence["workspace_error"] = str(exc)
        return _finish(result, evidence)
    forbidden = _changes(case, files)
    if case not in CASES or forbidden:
        result["checks"].append("unknown_case" if case not in CASES else "forbidden_changes")
        evidence["forbidden_paths"] = forbidden
    elif type(stage_answers) not in (tuple, list) or len(stage_answers) != len(case.followups):
        result["checks"].append("missing_or_extra_stages")
    elif case.id == "deep_proof":
        if _proof_shape(answer):
            result.update(status="needs_review", review_rubric=_PROOF_RUBRIC.copy())
            result["checks"].append("structure_only_not_proof")
        else:
            result["checks"].append("missing_structured_proof")
    elif case.id in _ANSWERS:
        exact = digest(answer) == digest(_ANSWERS[case.id])
        if case.id == "navigation":
            exact = exact and digest(stage_answers[0]) == digest({
                "path": "manual/part17.json", "first_key": "normalize.0", "marker": "VERIFY-ORBIT-731"})
        result["status"] = "passed" if exact else "failed"
        result["checks"].append("exact_answer" if exact else "answer_mismatch")
    elif sandbox_runner is None:
        result.update(status="inconclusive")
        result["checks"].append("sandbox_required")
    else:
        try:
            plan = execution_plan(case, root)
            identity = plan["identity"]
            reply = sandbox_runner(plan)
            evidence["execution"] = reply
            digest(reply)
            if _snapshot(root) != files:
                result["checks"].append("workspace_changed_during_validation")
            elif (type(reply) is not dict or reply.get("plan_identity") != identity or
                  reply.get("timed_out", False) or type(reply.get("exit_code")) is not int):
                result.update(status="inconclusive")
                result["checks"].append("invalid_sandbox_attestation")
            elif reply["exit_code"] != 0:
                result["checks"].append("hidden_tests_failed")
            elif reply.get("stdout") != "QUALITY_OK\n" or reply.get("stderr") != "":
                result.update(status="inconclusive")
                result["checks"].append("missing_test_completion")
            else:
                result.update(status="passed")
                result["checks"].append("hidden_tests_passed")
        except Exception as exc:
            evidence["execution"] = {"error_type": type(exc).__name__}
            result.update(status="inconclusive")
            result["checks"].append("sandbox_error")
    return _finish(result, evidence)


def _finish(result, evidence):
    result["success"] = {"passed": True, "failed": False}.get(result["status"])
    result["evidence"] = evidence
    result["evidence_digest"] = digest(result)
    return result


def grade(case, workspace, answer, events, *, sandbox_runner=None):
    """Native {name,arguments:dict} events include ALL attempts; answer uses content.
    Navigation requires ordered initial reads and both answers; final optional otherwise. Missing/malformed
    inventories are ungraded; full events are bound in evidence. run_python accepts
    exactly {code:string}: parent executes only in isolated readonly workspace copies,
    without hidden graders. Its output is untrusted data, never test attestation."""
    names = {"list_files", "read_file", "write_file", "retrieve_original", "search_original",
             "run_python", "answer"}
    malformed, forbidden, answers = False, [], []
    initial_sources = []
    event_digest = None
    try:
        event_digest = digest(events)
        if type(events) not in (list, tuple):
            raise ValueError("missing event inventory")
        for event in events:
            if type(event) is not dict or event.get("name") not in names:
                raise ValueError("unknown event")
            args = event.get("arguments")
            if type(args) is not dict:
                raise ValueError("unparsed tool arguments")
            if event["name"] == "run_python" and (set(args) != {"code"} or type(args["code"]) is not str):
                raise ValueError("run_python requires exactly code:string")
            if not answers and event["name"] in ("read_file", "retrieve_original", "search_original", "run_python"):
                initial_sources.append(args.get("path") if event["name"] == "read_file" else event["name"])
            if event["name"] == "write_file":
                if safe_path(args.get("path")) not in case.allowed_changes:
                    forbidden.append(args["path"])
            if event["name"] == "answer":
                answers.append(args["content"])
    except (TypeError, ValueError, KeyError):
        malformed = True
    prior = answers[:-1] if not malformed and answers and answers[-1] == answer else answers
    result = evaluate(case, workspace, answer, stage_answers=prior,
                      sandbox_runner=None if malformed or forbidden else sandbox_runner)
    evidence = result.pop("evidence")
    result.pop("evidence_digest")
    evidence["events"] = events if event_digest else {"unserializable_inventory": True}
    if case.id == "navigation" and not malformed and initial_sources != [
        "catalog.json", "manual/part17.json", "verification.txt"
    ]:
        result.update(status="failed")
        result["checks"].append("navigation_source_order_mismatch")
    if forbidden:
        result.update(status="failed")
        result["checks"].append("forbidden_write_attempt")
    elif malformed or result["status"] in ("inconclusive", "needs_review"):
        result.update(status="needs_blind_review")
        result["checks"].append("automatic_evidence_insufficient")
        if not result["review_rubric"]:
            result["review_rubric"] = ["Independently check requirements and full action inventory; "
                                      "execute hidden tests only in a caller-provided OS sandbox."]
    return _finish(result, evidence)
