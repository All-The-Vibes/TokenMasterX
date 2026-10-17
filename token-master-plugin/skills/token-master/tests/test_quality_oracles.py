"""Held-out quality oracle tests: all workspaces and answers are synthetic."""
import dataclasses
import ast
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
from quality.cases import CASES, Case, materialize, validate_action  # noqa: E402
from quality.oracle import evaluate, execution_plan, oracle_identity  # noqa: E402


def case(name):
    return next(item for item in CASES if item.id == name)


@pytest.fixture
def workspace(tmp_path):
    def create(name):
        item = case(name)
        root = tmp_path / name
        materialize(item, root)
        return item, root
    return create


def test_corpus_is_frozen_diverse_and_public_payload_has_no_solutions():
    assert len(CASES) == 8
    assert len({item.identity for item in CASES}) == 8
    for item in CASES:
        payload = item.public_task()
        assert set(payload) == {"id", "version", "identity", "prompt", "paths", "allowed_changes"}
        assert "expected" not in payload and "tests" not in payload
        assert all(not path.startswith("tests/") for path, _ in item.fixtures)
        assert len(item.identity) == len(oracle_identity()) == 64
        with pytest.raises(dataclasses.FrozenInstanceError):
            item.version = "mutated"
        assert dataclasses.replace(item, prompt=item.prompt + " changed").identity != item.identity
        assert dataclasses.replace(item, fixtures=item.fixtures + (("extra.txt", "x"),)).identity != item.identity


@pytest.mark.parametrize("path", ["../outside.py", "/tmp/x", "C:/x", "a\\b", "x/../app.py",
                                  "app.py:stream", "./app.py", "CON", "a//b", "a."])
def test_action_rejects_unsafe_paths(path):
    with pytest.raises(ValueError):
        validate_action(case("small_fix"), {"type": "write", "path": path, "content": "x"})


@pytest.mark.parametrize("action", [
    {"type": "shell", "content": "whoami"},
    {"type": "read", "path": "app.py", "command": "x"},
    {"type": "answer", "path": "app.py", "content": {}},
    {"type": "answer", "content": float("nan")},
    {"type": "write", "path": "app.py", "content": {}},
])
def test_action_is_strict_whitelist(action):
    with pytest.raises(ValueError):
        validate_action(case("small_fix"), action)


def test_valid_actions_are_not_executed_or_mutated():
    action = {"type": "write", "path": "app.py", "content": "changed"}
    assert validate_action(case("small_fix"), action) == action
    assert validate_action(case("small_fix"), {"type": "read", "path": "README.txt"})
    assert validate_action(case("small_fix"), {"type": "answer", "content": {"done": True}})


def test_materialize_refuses_nonempty_workspace_and_duplicate_fixture_paths(tmp_path):
    tmp_path.joinpath("precious").write_text("keep")
    with pytest.raises(ValueError):
        materialize(case("small_fix"), tmp_path)
    assert tmp_path.joinpath("precious").read_text() == "keep"
    with pytest.raises(ValueError):
        Case("bad", "1", "x", (("a", "one"), ("a", "two")), ())


def test_explain_checks_exact_trace_and_unchanged_workspace(workspace):
    item, root = workspace("explain_only")
    correct = {"returns": [10, None, 10], "stored": {"x": 10}}
    assert evaluate(item, root, correct)["status"] == "passed"
    assert evaluate(item, root, {"returns": [10, 10, 10], "stored": {"x": 10}})["status"] == "failed"
    root.joinpath("cache.py").write_text("# even a harmless edit is forbidden")
    assert evaluate(item, root, correct)["status"] == "failed"


def test_extra_file_and_deletion_fail_even_when_answer_correct(workspace):
    item, root = workspace("explain_only")
    root.joinpath("tests").mkdir()
    root.joinpath("tests/test_fake.py").write_text("assert True")
    assert evaluate(item, root, {})["status"] == "failed"
    root.joinpath("cache.py").unlink()
    assert evaluate(item, root, {})["status"] == "failed"


def test_symlink_workspace_is_not_followed(workspace, tmp_path):
    item, root = workspace("explain_only")
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "escape").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    result = evaluate(item, root, {})
    assert result["status"] == "failed"
    assert "unsafe_workspace" in result["checks"]


def test_json_oracle_checks_middle_anomalies_order_types_and_aggregate(workspace):
    item, root = workspace("json_exact")
    rows = json.loads(root.joinpath("records.json").read_text())
    valid = [r for r in rows if r["status"] == "ready" and type(r.get("units")) is int]
    correct = {
        "row_count": 241, "valid_count": len(valid),
        "sum_units": sum(r["units"] for r in valid),
        "invalid_ids": ["r119", "r120", "r122", "r123"], "failed_ids": ["r121"],
        "failed_record": rows[121],
    }
    assert evaluate(item, root, correct)["status"] == "passed"
    for field, value in [("sum_units", correct["sum_units"] + 1),
                         ("invalid_ids", list(reversed(correct["invalid_ids"]))),
                         ("row_count", True), ("failed_record", {"id": "r121"})]:
        assert evaluate(item, root, dict(correct, **{field: value}))["status"] == "failed"


def test_log_oracle_rejects_missing_failure_and_wrong_causal_context(workspace):
    item, root = workspace("rare_failure")
    correct = {"failed_count": 1, "request": "R151", "code": "E28",
               "cause": "disk full", "sequence": [149, 150, 151, 152]}
    assert evaluate(item, root, correct)["status"] == "passed"
    assert evaluate(item, root, dict(correct, cause="timeout"))["status"] == "failed"
    assert evaluate(item, root, dict(correct, failed_count=0))["status"] == "failed"


def test_navigation_requires_both_stages_and_exact_later_fragment(workspace):
    item, root = workspace("navigation")
    first = {"path": "manual/part17.json", "first_key": "normalize.0", "marker": "VERIFY-ORBIT-731"}
    answer = {"key": "normalize.173", "retry": 7, "note": "keep α / β; do not trim"}
    assert "normalize.173" not in item.public_task()["prompt"]
    assert "normalize.173" in item.public_task(stage=1)["prompt"]
    assert evaluate(item, root, answer, stage_answers=[first])["status"] == "passed"
    assert evaluate(item, root, answer)["status"] == "failed"
    assert evaluate(item, root, dict(answer, retry=3), stage_answers=[first])["status"] == "failed"
    for incorrect in ({"path": first["path"]}, dict(first, first_key="normalize.1"),
                      dict(first, marker="wrong")):
        assert evaluate(item, root, answer, stage_answers=[incorrect])["status"] == "failed"


def test_graph_oracle_requires_source_edges_collision_and_stale_index(workspace):
    item, root = workspace("graph_freshness")
    correct = {"stale": True, "candidates": ["a.py:render", "b.py:render"],
               "actual_edges": [["app.py:run", "b.py:render"]],
               "obsolete_edges": [["app.py:run", "a.py:render"]]}
    assert evaluate(item, root, correct)["status"] == "passed"
    assert evaluate(item, root, dict(correct, stale=False))["status"] == "failed"


def test_proof_cannot_be_certified_by_schema_or_keyword_presence(workspace):
    item, root = workspace("deep_proof")
    assert evaluate(item, root, "integral harmonic logarithm proof")["status"] == "failed"
    for rationale in ["invented nonsense", "A full derivation supplied for blind assessment."]:
        answer = {"premises": ["n integer >= 1"], "inequalities": ["ln(n) <= H_n <= 1+ln(n)"],
                  "counterexample": {"n": 1, "lhs": 1, "rhs": 0}, "rationale": rationale}
        result = evaluate(item, root, answer)
        assert result["status"] == "needs_review"
        assert result["success"] is None
        assert result["review_rubric"]


def test_no_candidate_code_is_executed_without_sandbox(workspace):
    item, root = workspace("small_fix")
    root.joinpath("app.py").write_text("raise RuntimeError('must never execute here')\n")
    result = evaluate(item, root, {"done": True})
    assert result["status"] == "inconclusive"
    assert "sandbox_required" in result["checks"]


def test_execution_plan_is_held_out_and_bound_to_actual_final_sources(workspace):
    item, root = workspace("small_fix")
    plan = execution_plan(item, root)
    assert plan["sources"]["app.py"] == root.joinpath("app.py").read_text()
    assert "assert" in plan["test_code"]
    assert plan["timeout_seconds"] == 3
    assert len(plan["identity"]) == 64
    root.joinpath("app.py").write_text("def trailing_mean(values, width): return 0\n")
    assert execution_plan(item, root)["identity"] != plan["identity"]
    assert plan["test_code"] not in json.dumps(item.public_task())


@pytest.mark.parametrize("reply,status", [
    ({"exit_code": 1, "stdout": "", "stderr": "AssertionError"}, "failed"),
    ({"exit_code": 0, "stdout": "", "stderr": ""}, "inconclusive"),
    ({"exit_code": 0, "stdout": "QUALITY_OK\n", "stderr": "", "timed_out": True}, "inconclusive"),
])
def test_sandbox_failure_or_missing_attestation_does_not_pass(workspace, reply, status):
    item, root = workspace("small_fix")
    def runner(plan):
        return dict(reply, plan_identity=plan["identity"])
    assert evaluate(item, root, {}, sandbox_runner=runner)["status"] == status


def test_sandbox_result_must_match_plan_and_exact_marker(workspace):
    item, root = workspace("small_fix")
    def runner(plan):
        return {"plan_identity": plan["identity"], "exit_code": 0,
                "stdout": "QUALITY_OK\n", "stderr": ""}
    assert evaluate(item, root, {}, sandbox_runner=runner)["status"] == "passed"
    def stale(plan):
        return dict(runner(plan), plan_identity="0" * 64)
    assert evaluate(item, root, {}, sandbox_runner=stale)["status"] == "inconclusive"


def test_sandbox_errors_and_source_mutation_fail_closed(workspace):
    item, root = workspace("small_fix")
    def timeout(plan):
        raise TimeoutError("synthetic timeout")
    assert evaluate(item, root, {}, sandbox_runner=timeout)["status"] == "inconclusive"
    def mutate(plan):
        root.joinpath("app.py").write_text("# changed during validation")
        return {"plan_identity": plan["identity"], "exit_code": 0,
                "stdout": "QUALITY_OK\n", "stderr": ""}
    assert evaluate(item, root, {}, sandbox_runner=mutate)["status"] == "failed"


def test_evidence_digest_binds_answer_workspace_case_oracle_and_execution(workspace):
    item, root = workspace("small_fix")
    first = evaluate(item, root, {})
    assert first["evidence_digest"] == evaluate(item, root, {})["evidence_digest"]
    assert first["case_identity"] == item.identity
    assert first["oracle_identity"] == oracle_identity()
    assert first["evidence_digest"] != evaluate(item, root, {"done": True})["evidence_digest"]
    root.joinpath("app.py").write_text("# new artifact")
    assert first["evidence_digest"] != evaluate(item, root, {})["evidence_digest"]


def test_reusable_abstraction_hidden_checks_cover_helper_reuse(workspace):
    item, root = workspace("reusable_abstraction")
    plan = execution_plan(item, root)
    assert "clamp" in plan["test_code"]
    assert "score" in plan["test_code"] and "percentage" in plan["test_code"]
    assert evaluate(item, root, {})["status"] == "inconclusive"


def test_every_python_fixture_parses_without_warnings():
    for item in CASES:
        for path, source in item.fixtures:
            if path.endswith(".py"):
                ast.parse(source, filename=path)


@pytest.mark.parametrize("stage_answers", [None, "x", {}, [float("nan")]])
def test_malformed_stage_evidence_is_rejected_not_raised(workspace, stage_answers):
    item, root = workspace("navigation")
    assert evaluate(item, root, {}, stage_answers=stage_answers)["status"] == "failed"


def test_prohibited_change_prevents_sandbox_call(workspace):
    item, root = workspace("small_fix")
    root.joinpath("README.txt").write_text("changed")
    def runner(plan):
        pytest.fail("must not validate an out-of-scope solution")
    assert evaluate(item, root, {}, sandbox_runner=runner)["status"] == "failed"


@pytest.mark.parametrize("changes", [
    {"id": []}, {"version": None}, {"prompt": []}, {"followups": ([],)},
])
def test_case_rejects_mutable_or_invalid_identity_fields(changes):
    with pytest.raises(ValueError):
        dataclasses.replace(case("small_fix"), **changes)


FIXED_MEAN = (
    "def trailing_mean(values, width):\n"
    "    if width <= 0: raise ValueError('width')\n"
    "    sample = values[-width:]\n"
    "    return sum(sample) / len(sample) if sample else None\n"
)
REUSED_CLAMP = (
    "def clamp(value, low, high):\n"
    "    if low > high: raise ValueError('bounds')\n"
    "    return max(low, min(high, value))\n"
    "def score(value):\n    return clamp(value, 0, 100)\n"
    "def percentage(value, total):\n    return clamp(value / total * 100, 0, 100)\n"
)
UNUSED_CLAMP = (
    "def clamp(value, low, high):\n"
    "    if low > high: raise ValueError('bounds')\n"
    "    return max(low, min(high, value))\n"
    "def score(value):\n    return max(0, min(100, value))\n"
    "def percentage(value, total):\n    return max(0, min(100, value / total * 100))\n"
)


@pytest.mark.parametrize("name,source,expected", [
    ("small_fix", None, "failed"),
    ("small_fix", FIXED_MEAN, "passed"),
    ("reusable_abstraction", None, "failed"),
    ("reusable_abstraction", UNUSED_CLAMP, "failed"),
    ("reusable_abstraction", REUSED_CLAMP, "passed"),
])
def test_hidden_tests_really_reject_regressions_and_accept_reference_fixtures(
        workspace, tmp_path, name, source, expected):
    """Execute ONLY these hand-authored source constants, never arbitrary model code.

    This local test adapter is deliberately not a reusable candidate sandbox.
    The production parent must provide an actual isolated sandbox for model code.
    """
    item, root = workspace(name)
    path = item.allowed_changes[0]
    if source is not None:
        root.joinpath(path).write_text(source, encoding="utf-8", newline="")
    trusted_sources = dict(item.fixtures)
    if source is not None:
        trusted_sources[path] = source
    def trusted_fixture_runner(plan):
        assert plan["sources"] == trusted_sources
        isolated = tmp_path / "trusted-fixture-only"
        isolated.mkdir()
        for filename, content in trusted_sources.items():
            isolated.joinpath(filename).write_text(content, encoding="utf-8", newline="")
        script = f"import sys\nsys.path.insert(0, {str(isolated)!r})\n" + plan["test_code"]
        completed = subprocess.run(
            [sys.executable, "-I", "-B", "-S", "-c", script], cwd=isolated,
            capture_output=True, text=True, encoding="utf-8", timeout=3, env={},
        )
        return dict(plan_identity=plan["identity"], exit_code=completed.returncode,
                    stdout=completed.stdout, stderr=completed.stderr)
    result = evaluate(item, root, {}, sandbox_runner=trusted_fixture_runner)
    assert result["status"] == expected, result


def test_parent_api_has_readonly_files_and_explicit_intent():
    item = case("small_fix")
    assert item.stratum == "small_fix"
    assert item.intent == "edit"
    assert item.files["app.py"] == dict(item.fixtures)["app.py"]
    with pytest.raises(TypeError):
        item.files["app.py"] = "mutated"


@pytest.mark.parametrize("path", ["cache.py", "tests/test_fake.py", "extra.txt"])
def test_explain_write_is_available_but_attempt_is_graded_wrong_even_after_revert(workspace, path):
    from quality.oracle import grade
    item, root = workspace("explain_only")
    action = {"type": "write", "path": path, "content": "attempt"}
    assert validate_action(item, action) == action
    answer = {"returns": [10, None, 10], "stored": {"x": 10}}
    result = grade(item, root, answer, [{"name": "write_file",
                                      "arguments": {"path": path, "content": "attempt"}}])
    assert result["status"] == "failed" and result["success"] is False
    assert "forbidden_write_attempt" in result["checks"]


def test_grade_reports_blind_review_not_false_success_for_unsandboxed_code(workspace):
    from quality.oracle import grade
    item, root = workspace("small_fix")
    result = grade(item, root, {}, [])
    assert result["status"] == "needs_blind_review"
    assert result["success"] is None


@pytest.mark.parametrize("recovery_tool", ["retrieve_original", "read_file"])
def test_grade_consumes_native_answer_events_for_navigation(workspace, recovery_tool):
    from quality.oracle import grade
    item, root = workspace("navigation")
    answer = {"key": "normalize.173", "retry": 7, "note": "keep α / β; do not trim"}
    events = [
        {"name": "read_file", "arguments": {"path": "catalog.json"}},
        {"name": "read_file", "arguments": {"path": "manual/part17.json"}},
        {"name": "read_file", "arguments": {"path": "verification.txt"}},
        {"name": "answer", "arguments": {"content": {
            "path": "manual/part17.json", "first_key": "normalize.0", "marker": "VERIFY-ORBIT-731"}}},
        {"name": recovery_tool, "arguments": {"path": "manual/part17.json"}},
        {"name": "answer", "arguments": {"content": answer}},
    ]
    result = grade(item, root, answer, events)
    assert result["status"] == "passed"
    assert result["evidence"]["events"] == events


def test_grade_fails_closed_for_missing_or_malformed_event_inventory(workspace):
    from quality.oracle import grade
    item, root = workspace("explain_only")
    answer = {"returns": [10, None, 10], "stored": {"x": 10}}
    for events in (None, [{"name": "write_file", "arguments": "not parsed"}],
                   [{"name": "unexpected_shell", "arguments": {}}]):
        assert grade(item, root, answer, events)["status"] == "needs_blind_review"


def test_grade_binds_even_malformed_json_event_inventory(workspace):
    from quality.oracle import grade
    item, root = workspace("explain_only")
    first = grade(item, root, {}, [{"name": "unknown_one", "arguments": {}}])
    second = grade(item, root, {}, [{"name": "unknown_two", "arguments": {}}])
    assert first["evidence_digest"] != second["evidence_digest"]


def test_grade_nonfinite_answer_event_fails_closed(workspace):
    from quality.oracle import grade
    item, root = workspace("navigation")
    events = [{"name": "answer", "arguments": {"content": float("nan")}}]
    assert grade(item, root, {}, events)["status"] == "needs_blind_review"


def test_intents_are_explicit_frozen_case_data_not_model_inference():
    assert {item.id: item.intent for item in CASES} == {
        "explain_only": "exact", "small_fix": "edit", "reusable_abstraction": "edit",
        "deep_proof": "exact", "json_exact": "aggregate", "rare_failure": "debug",
        "navigation": "overview", "graph_freshness": "exact",
    }
    assert {"intent", "global_hint"} <= {f.name for f in dataclasses.fields(Case)}
    for item in CASES:
        assert item.version == ("3" if item.id in ("explain_only", "navigation") else "2")
        assert isinstance(item.global_hint, str)
        assert dataclasses.replace(item, intent="task").identity != item.identity
        assert dataclasses.replace(item, global_hint="other").identity != item.identity
    with pytest.raises(ValueError):
        dataclasses.replace(case("json_exact"), intent="model_guessed")


def test_corpus_has_no_monetary_task_vocabulary():
    import quality.cases as module
    for item in CASES:
        payload = json.dumps(dataclasses.asdict(item)).lower()
        assert not any(term in payload for term in ("cents", "settled", "transaction", "payment"))
    assert "non-IID" in module.__doc__
    assert "population certification" in module.__doc__


def test_source_atoms_map_whole_classes_methods_nested_and_collision_paths():
    from quality.cases import source_atoms
    text = ("@tag\nclass Cache:\n    def get(self):\n"
            "        def nested(): return 3\n        return nested()\n")
    atoms = source_atoms({"new/cache.py": text, "a.py": "def render(): return 1\n",
                         "b.py": "def render(): return 2\n", "readme.txt": "no code"})
    assert set(atoms) == {"new/cache.py:Cache@1", "new/cache.py:Cache.get@3",
                          "new/cache.py:Cache.get.nested@4", "a.py:render@1", "b.py:render@1"}
    whole = atoms["new/cache.py:Cache@1"]
    assert whole == {"path": "new/cache.py", "symbol": "Cache", "kind": "class",
                     "start_line": 1, "end_line": 5, "source": text}
    assert atoms["new/cache.py:Cache.get@3"]["source"] == "".join(text.splitlines(True)[2:5])
    assert atoms["a.py:render@1"]["path"] != atoms["b.py:render@1"]["path"]


def test_source_atoms_retain_redefined_names_and_never_execute_unsafe_source(tmp_path):
    from quality.cases import source_atoms
    sentinel = tmp_path / "must_not_exist"
    source = (f"open({str(sentinel)!r}, 'w').write('unsafe')\n"
              "class Risk:\n    raise RuntimeError('class body must not execute')\n"
              "def f(): return 1\n"
              "def f(): return 2\n")
    atoms = source_atoms({"new.py": source})
    assert set(atoms) == {"new.py:Risk@2", "new.py:f@4", "new.py:f@5"}
    assert not sentinel.exists()
    with pytest.raises(ValueError):
        source_atoms({"../escape.py": "def f(): pass"})
    with pytest.raises(ValueError):
        source_atoms({"large.py": "#" * 524289})


def test_source_atom_metadata_has_no_hidden_grader_files_or_answers():
    from quality.cases import source_atoms
    for item in CASES:
        atoms = source_atoms(item.files)
        for atom in atoms.values():
            assert atom["path"] in item.files
            assert atom["source"] in item.files[atom["path"]]
        assert not any("oracle.py" in atom["path"] or "test_" in atom["path"]
                       for atom in atoms.values())


def test_source_atoms_keep_multiline_decorators_and_async_methods():
    from quality.cases import source_atoms
    source = "@(\n    decorate\n)\nclass Example:\n    async def run(self): return 1\n"
    atoms = source_atoms({"new.py": source})
    assert atoms["new.py:Example@1"]["source"] == source
    assert atoms["new.py:Example.run@5"]["kind"] == "function"


def test_grade_evidence_labels_challenge_scope_not_population_certificate(workspace):
    from quality.oracle import grade
    item, root = workspace("explain_only")
    result = grade(item, root, {"returns": [10, None, 10], "stored": {"x": 10}}, [])
    assert result["status"] == "passed"
    assert result["scope"] == "non_iid_challenge_suite"


def test_navigation_constructed_stress_fixture_requires_older_manual_then_marker():
    item = case("navigation")
    assert item.intent == "overview"
    assert "constructed recovery stress case" in item.prompt.lower()
    assert "not performance-representative" in item.prompt.lower()
    assert item.prompt.index("First") < item.prompt.index("Then") < item.prompt.index("Finally")
    catalog = json.loads(item.files["catalog.json"])
    owning = next(row["path"] for row in catalog if row["stage"] == "normalize")
    manual = json.loads(item.files[owning])
    assert manual[0]["key"] == "normalize.0"
    assert item.files["verification.txt"] == "VERIFY-ORBIT-731\n"
    assert manual[173] == {"key": "normalize.173", "retry": 7, "note": "keep α / β; do not trim"}
    assert "normalize.173" not in item.public_task(stage=0)["prompt"]
    assert "normalize.173" in item.public_task(stage=1)["prompt"]


@pytest.mark.parametrize("paths", [
    ["catalog.json"], ["catalog.json", "verification.txt", "manual/part17.json"],
    ["catalog.json", "manual/part17.json", "verification.txt", "manual/part17.json"],
])
def test_navigation_grade_rejects_bypassed_or_wrong_initial_source_order(workspace, paths):
    from quality.oracle import grade
    item, root = workspace("navigation")
    first = {"path": "manual/part17.json", "first_key": "normalize.0", "marker": "VERIFY-ORBIT-731"}
    answer = {"key": "normalize.173", "retry": 7, "note": "keep α / β; do not trim"}
    events = [{"name": "read_file", "arguments": {"path": p}} for p in paths] + [
        {"name": "answer", "arguments": {"content": first}},
        {"name": "read_file", "arguments": {"path": "manual/part17.json"}},
        {"name": "answer", "arguments": {"content": answer}},
    ]
    result = grade(item, root, answer, events)
    assert result["status"] == "failed"
    assert "navigation_source_order_mismatch" in result["checks"]


def test_run_python_event_allows_aggregate_calculation_without_becoming_quality_evidence(workspace):
    from quality.oracle import grade
    item, root = workspace("json_exact")
    answer = {"row_count": 241, "valid_count": 236, "sum_units": 35615,
              "invalid_ids": ["r119", "r120", "r122", "r123"], "failed_ids": ["r121"],
              "failed_record": {"id": "r121", "status": "FAILED", "units": 999999}}
    events = [{"name": "run_python", "arguments": {"code": "import json\nprint('public calculation')"},
               "output": {"stdout": "arbitrary untrusted calculation output", "success": False}}]
    result = grade(item, root, answer, events)
    assert result["status"] == "passed"
    assert result["scope"] == "non_iid_challenge_suite"
    assert result["evidence"]["events"] == events


def test_run_python_success_claim_cannot_override_wrong_independent_answer(workspace):
    from quality.oracle import grade
    item, root = workspace("json_exact")
    events = [{"name": "run_python", "arguments": {"code": "print('QUALITY_OK')"},
               "output": {"success": True, "status": "passed", "stdout": "QUALITY_OK\n"}}]
    result = grade(item, root, {"row_count": 1}, events)
    assert result["status"] == "failed"
    assert result["success"] is False
    assert "answer_mismatch" in result["checks"]


def test_run_python_public_test_claim_cannot_replace_hidden_sandbox_grader(workspace):
    from quality.oracle import grade
    item, root = workspace("small_fix")
    events = [{"name": "run_python", "arguments": {"code": "print('all public tests passed')"},
               "output": {"success": True, "stdout": "QUALITY_OK\n"}}]
    result = grade(item, root, {"done": True}, events)
    assert result["status"] == "needs_blind_review"
    assert result["success"] is None
    assert "sandbox_required" in result["checks"]


@pytest.mark.parametrize("args", [
    None, [], "unparsed", {}, {"code": None}, {"code": 12}, {"code": False},
    {"code": "print(1)", "path": "records.json"},
    {"code": "print(1)", "content": "persistent write"},
    {"command": "print(1)"},
])
def test_run_python_event_rejects_unknown_argument_shapes(workspace, args):
    from quality.oracle import grade
    item, root = workspace("explain_only")
    answer = {"returns": [10, None, 10], "stored": {"x": 10}}
    result = grade(item, root, answer, [{"name": "run_python", "arguments": args}])
    assert result["status"] == "needs_blind_review"
    assert result["success"] is None


def test_run_python_grade_never_executes_code_or_accepts_persistent_workspace_changes(workspace, tmp_path):
    from quality.oracle import grade
    item, root = workspace("explain_only")
    sentinel = tmp_path / "must_not_be_created"
    events = [{"name": "run_python", "arguments": {
        "code": f"open({str(sentinel)!r}, 'w').write('never run on host')"}}]
    answer = {"returns": [10, None, 10], "stored": {"x": 10}}
    assert grade(item, root, answer, events)["status"] == "passed"
    assert not sentinel.exists()
    root.joinpath("cache.py").write_text("# changed outside write_file")
    assert grade(item, root, answer, events)["status"] == "failed"


def test_run_python_does_not_bypass_navigation_initial_source_order(workspace):
    from quality.oracle import grade
    item, root = workspace("navigation")
    first = {"path": "manual/part17.json", "first_key": "normalize.0", "marker": "VERIFY-ORBIT-731"}
    answer = {"key": "normalize.173", "retry": 7, "note": "keep α / β; do not trim"}
    events = [{"name": "read_file", "arguments": {"path": path}} for path in
              ["catalog.json", "manual/part17.json", "verification.txt"]] + [
        {"name": "run_python", "arguments": {"code": "print(open('manual/part17.json').read())"}},
        {"name": "answer", "arguments": {"content": first}},
        {"name": "read_file", "arguments": {"path": "manual/part17.json"}},
        {"name": "answer", "arguments": {"content": answer}},
    ]
    result = grade(item, root, answer, events)
    assert result["status"] == "failed"
    assert "navigation_source_order_mismatch" in result["checks"]


def test_explain_prompt_excludes_put_return_after_invalid_instrument_preflight():
    """V2 preflight ambiguity: counting put was legitimate, not a model defect.

    That exposed preflight is instrument diagnosis, not confirmation data or
    evidence of quality decline. V3 clarifies the task without changing its oracle.
    """
    item = case("explain_only")
    assert item.version == "3"
    assert "report returns from only the three get calls; exclude put return" in item.public_task()["prompt"].lower()
    old_prompt = (
        "Explain cache.py without editing. For a new Cache, put('x',10), "
        "get('x',0), get('x',1), get('x',0) in order; answer exact JSON "
        "{returns:[...],stored:{...}}. Distinguish expiry from deletion."
    )
    previous = dataclasses.replace(item, version="2", prompt=old_prompt)
    assert previous.identity == "34a60892823b88b604722bd8183e8466a1f9484f31d3047980e188966669eda5"
    assert item.identity != previous.identity
