"""Offline held-out-data checks. No model, network, install, or policy changes."""
import ast
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib
import json
from pathlib import Path
import re
import socket
import subprocess
import sys

import pytest

EVALS = Path(__file__).resolve().parents[3] / "evals"
REPO = EVALS.parents[1]
sys.path.insert(0, str(EVALS))
import parity_cases as parity  # noqa: E402
import retention_cases as retention  # noqa: E402
from quality.cases import Case, materialize  # noqa: E402


MANIFEST = json.loads(retention.MANIFEST_PATH.read_bytes())
CASES = retention.load_cases()
TASKS = {task["id"]: task for task in MANIFEST["tasks"]}
SOURCES = {source["path"]: source for source in MANIFEST["sources"]}
PREFIX = "token-master-plugin/skills/token-master/"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("network is forbidden in holdout validation")
    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


def answer_for(case):
    return deepcopy(TASKS[case.id]["expected"])


def read_events(case):
    return [{"name": "read_file", "arguments": {"path": path}} for path, _ in case.fixtures]


def test_schema_counts_and_frozen_manifest():
    assert hashlib.sha256(retention.MANIFEST_PATH.read_bytes()).hexdigest() == retention.MANIFEST_SHA256
    assert MANIFEST["schema_version"] == 1
    assert MANIFEST["source_commit"] == retention.SOURCE_COMMIT
    assert len(CASES) == 4 and len(SOURCES) == 6
    assert Counter(task["category"] for task in TASKS.values()) == {
        "code_navigation": 2, "code_overview": 1, "preservation_control": 1}
    assert [len(case.fixtures) for case in CASES] == [2, 2, 3, 1]
    assert [case.intent for case in CASES] == ["navigation", "navigation", "overview", "exact"]
    assert "prespecified_small_retention_policy_validation_stratum" in MANIFEST["scope"]
    assert "not_population_representative" in MANIFEST["scope"]
    assert all(type(case) is Case and case.allowed_changes == () and case.followups == ()
               and case.global_hint == "" for case in CASES)


def test_prior_corpora_have_no_source_question_or_gold_overlap():
    previous = parity._load_manifest()
    repository = json.loads((EVALS / "repository-cases.json").read_bytes())
    assert not SOURCES.keys() & {source["path"] for source in previous["sources"]}
    # Older corpus stores skill-relative fixture paths rather than repository paths.
    assert not SOURCES.keys() & {PREFIX + path for path, _ in repository["fixtures"]}
    previous_tasks = previous["tasks"] + repository["tasks"]
    assert not TASKS.keys() & {task["id"] for task in previous_tasks}
    assert not {task["prompt"] for task in TASKS.values()} & {
        task["prompt"] for task in previous_tasks}
    previous_gold = [task["expected"] for task in previous_tasks if "expected" in task]
    assert all(task["expected"] not in previous_gold for task in TASKS.values())


def test_reuse_is_isolated_and_cannot_change_live_parity():
    constants = (parity.MANIFEST_PATH, parity.MANIFEST_SHA256, parity.ORACLE_ID, parity.SOURCE_COMMIT)
    identities = [case.identity for case in parity.load_cases()]
    private = retention._oracle
    assert private is not parity
    assert private.grade.__code__.co_filename == parity.grade.__code__.co_filename
    assert private.grade.__code__.co_code == parity.grade.__code__.co_code
    assert private.grade.__globals__ is not parity.grade.__globals__
    assert private.__name__ not in sys.modules
    importlib.reload(retention)
    assert retention._oracle is not private
    assert constants == (parity.MANIFEST_PATH, parity.MANIFEST_SHA256, parity.ORACLE_ID, parity.SOURCE_COMMIT)
    assert identities == [case.identity for case in parity.load_cases()]
    assert retention.ORACLE_ID != parity.ORACLE_ID


@pytest.mark.parametrize("source", MANIFEST["sources"], ids=lambda s: s["path"])
def test_every_fixture_is_exact_original_git_bytes(source):
    raw = subprocess.check_output(
        ["git", "show", f"{retention.SOURCE_COMMIT}:{source['path']}"], cwd=REPO)
    assert source["encoding"] == "utf-8" and source["commit"] == retention.SOURCE_COMMIT
    assert raw == source["text"].encode("utf-8")
    assert source["byte_length"] == len(raw)
    assert source["sha256"] == hashlib.sha256(raw).hexdigest()


def test_private_evidence_covers_all_gold_and_every_fixture_is_relevant():
    for case in CASES:
        task = TASKS[case.id]
        public = case.public_task()
        assert set(public) == {"id", "version", "identity", "prompt", "paths", "allowed_changes"}
        assert public["prompt"].endswith(task["prompt"])
        assert public["allowed_changes"] == []
        assert "bill" not in task["prompt"].lower()
        assert "bill" not in json.dumps(task["expected"]).lower()
        covered = set()
        cited_paths = set()
        for item in task["evidence"]:
            lines = SOURCES[item["path"]]["text"].splitlines(keepends=True)
            assert "".join(lines[item["start_line"] - 1:item["end_line"]]) == item["quote"]
            assert item["quote"] not in public["prompt"]
            assert item["rationale"]
            covered.update(item["answer_keys"])
            cited_paths.add(item["path"])
        assert covered == task["expected"].keys()
        assert cited_paths == set(case.files)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_gold_passes_and_never_invokes_sandbox(case, tmp_path):
    root = materialize(case, tmp_path / "workspace")
    def forbidden(*args, **kwargs):
        pytest.fail("holdout oracle must not execute fixture or candidate code")
    events = list(reversed(read_events(case)))
    result = retention.grade(case, root, answer_for(case), events, sandbox_runner=forbidden)
    assert set(result) == {
        "status", "success", "checks", "assertions", "changed_files", "unexpected_files",
        "missing_files", "oracle", "evidence_digest"}
    assert result["status"] == "passed" and result["success"] is True
    assert result["checks"] == [] and all(result["assertions"].values())
    assert result["changed_files"] == result["unexpected_files"] == result["missing_files"] == []
    assert result["oracle"] == retention.ORACLE_ID
    assert len(result["evidence_digest"]) == 64
    assert result == retention.grade(case, root, answer_for(case), events)


def leaves(value, path=()):
    if type(value) is dict:
        for key, child in value.items():
            yield from leaves(child, (*path, key))
    elif type(value) is list:
        for index, child in enumerate(value):
            yield from leaves(child, (*path, index))
    else:
        yield path, value


MUTATIONS = [(case, path, value) for case in CASES for path, value in leaves(answer_for(case))]


@pytest.mark.parametrize("case,path,value", MUTATIONS,
                         ids=[case.id + ":" + ".".join(map(str, path))
                              for case, path, _ in MUTATIONS])
def test_each_gold_leaf_is_required_with_exact_json_types(case, path, value, tmp_path):
    answer = answer_for(case)
    node = answer
    for key in path[:-1]:
        node = node[key]
    wrong = {str: lambda v: v + " ", bool: int, int: float}
    node[path[-1]] = wrong[type(value)](value)
    result = retention.grade(case, materialize(case, tmp_path / "workspace"), answer, [])
    assert result["success"] is False
    assert "answer_matches_source_contract" in result["checks"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
@pytest.mark.parametrize("mutation", ["missing", "extra", "encoded"])
def test_gold_shape_is_not_coerced(case, mutation, tmp_path):
    answer = answer_for(case)
    if mutation == "missing":
        answer.pop(next(iter(answer)))
    elif mutation == "extra":
        answer["extra"] = True
    else:
        answer = json.dumps(answer)
    assert not retention.grade(case, materialize(case, tmp_path / "workspace"), answer, [])["success"]


@pytest.mark.parametrize("mutation", ["edit", "crlf", "missing", "extra"])
def test_readonly_bytes_and_file_inventory(mutation, tmp_path):
    case = CASES[0]
    root = materialize(case, tmp_path / "workspace")
    path, original = case.fixtures[0]
    file = root / path
    if mutation == "missing":
        file.unlink()
    elif mutation == "extra":
        (root / "unrequested.txt").write_bytes(b"extra")
    elif mutation == "crlf":
        file.write_bytes(original.replace("\n", "\r\n").encode())
    else:
        file.write_bytes(original.encode() + b"# changed\n")
    result = retention.grade(case, root, answer_for(case), [])
    assert not result["success"]
    key = {"missing": "missing_files", "extra": "unexpected_files"}.get(mutation, "changed_files")
    assert result[key] == ["unrequested.txt" if mutation == "extra" else path]


@pytest.mark.parametrize("mutation", ["same_bytes", "restored", "rejected"])
def test_attempted_writes_fail_even_when_bytes_match(mutation, tmp_path):
    case = CASES[0]
    root = materialize(case, tmp_path / "workspace")
    path, original = case.fixtures[0]
    events = [{"name": "write_file", "arguments": {"path": path, "content": original}}]
    if mutation == "restored":
        (root / path).write_bytes(b"changed")
        (root / path).write_bytes(original.encode())
        events.insert(0, {"name": "write_file", "arguments": {"path": path, "content": "changed"}})
    if mutation == "rejected":
        events[0]["arguments"]["path"] = "not-allowed.txt"
    result = retention.grade(case, root, answer_for(case), events)
    assert not result["success"]
    assert result["changed_files"] == []
    assert "write_scope_respected" in result["checks"]


@pytest.mark.parametrize("event", [
    None, {"name": "run_python", "arguments": {"code": "pass"}},
    {"name": "headroom_retrieve", "arguments": {"hash": 123}},
    {"name": "headroom_retrieve", "arguments": {"hash": "abc", "extra": True}},
    {"name": "read_file", "arguments": {"path": "../escape"}},
])
def test_nonreadonly_or_malformed_events_fail(event, tmp_path):
    case = CASES[0]
    result = retention.grade(case, materialize(case, tmp_path / "workspace"),
                             answer_for(case), [event])
    assert not result["success"]
    assert "write_scope_respected" in result["checks"]


def test_common_readonly_recovery_and_call_ids_are_preserved(tmp_path):
    case = CASES[0]
    root = materialize(case, tmp_path / "workspace")
    events = [
        {"name": "headroom_retrieve", "arguments": {"hash": "abc123"}, "call_id": "heldout-1"},
        {"name": "retrieve_original", "arguments": {"ref": "abc123", "offset": 0}},
        {"name": "search_original", "arguments": {"ref": "abc123", "query": "main"}},
        {"name": "fetch_artifact", "arguments": {"path": case.fixtures[0][0]}},
    ]
    before = deepcopy(events)
    result = retention.grade(case, root, answer_for(case), events)
    assert result["success"] and events == before
    events[0]["call_id"] = "heldout-2"
    assert retention.grade(case, root, answer_for(case), events)["evidence_digest"] != result["evidence_digest"]


@pytest.mark.parametrize("mutation", ["gold", "source", "commit", "evidence", "prompt"])
def test_tampering_cannot_redefine_manifest_or_live_parity(mutation, tmp_path, monkeypatch):
    original_parity = [case.identity for case in parity.load_cases()]
    manifest = deepcopy(MANIFEST)
    if mutation == "gold":
        manifest["tasks"][0]["expected"] = {}
    elif mutation == "source":
        source = manifest["sources"][0]
        source["text"] += "\n"
        raw = source["text"].encode()
        source.update(byte_length=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    elif mutation == "commit":
        manifest["source_commit"] = "0" * 40
    elif mutation == "evidence":
        manifest["tasks"][0]["evidence"][0]["start_line"] += 1
    else:
        manifest["tasks"][0]["prompt"] += " forged"
    file = tmp_path / "tampered.json"
    file.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(retention._oracle, "MANIFEST_PATH", file)
    with pytest.raises(ValueError, match="integrity mismatch"):
        retention.load_cases()
    case = CASES[0]
    result = retention.grade(case, materialize(case, tmp_path / "workspace"), answer_for(case), [])
    assert not result["success"] and "manifest_integrity" in result["checks"]
    assert original_parity == [case.identity for case in parity.load_cases()]


@pytest.mark.parametrize("field", ["prompt", "fixtures", "allowed_changes", "intent"])
def test_forged_case_is_not_a_new_authority(field, tmp_path):
    case = CASES[0]
    values = {"prompt": case.prompt + " changed",
              "fixtures": ((case.fixtures[0][0], "changed"), *case.fixtures[1:]),
              "allowed_changes": (case.fixtures[0][0],), "intent": "exact"}
    fake = replace(case, **{field: values[field]})
    result = retention.grade(fake, materialize(fake, tmp_path / "workspace"), answer_for(case), [])
    assert not result["success"] and "known_case" in result["checks"]


def test_missing_and_linked_workspace_fail(tmp_path):
    case = CASES[0]
    result = retention.grade(case, tmp_path / "missing", answer_for(case), [])
    assert not result["success"] and "safe_workspace" in result["checks"]
    root = materialize(case, tmp_path / "workspace")
    try:
        (root / "link").symlink_to(root / case.fixtures[0][0])
    except OSError:
        pytest.skip("OS does not permit symlink creation")
    assert "safe_workspace" in retention.grade(case, root, answer_for(case), [])["checks"]


def test_gold_is_fresh_private_state_and_nonjson_is_rejected(tmp_path):
    retention._oracle._load_manifest()["tasks"][0]["expected"].clear()
    assert retention._oracle._load_manifest()["tasks"][0]["expected"] == answer_for(CASES[0])
    case = CASES[0]
    root = materialize(case, tmp_path / "workspace")
    first = retention.grade(case, root, {"bad": 1}, [])
    second = retention.grade(case, root, {"bad": 2}, [])
    assert first["evidence_digest"] != second["evidence_digest"]
    assert not retention.grade(case, root, {"bad": float("nan")}, [])["success"]


def test_oracles_do_not_accept_each_others_case_authority(tmp_path):
    heldout = CASES[0]
    root = materialize(heldout, tmp_path / "heldout")
    assert "known_case" in parity.grade(heldout, root, answer_for(heldout), [])["checks"]
    prior = parity.load_cases()[0]
    root = materialize(prior, tmp_path / "prior")
    assert "known_case" in retention.grade(prior, root, {}, [])["checks"]


@pytest.mark.parametrize("mutation", ["tuple", "reversed"])
def test_list_types_and_order_are_exact(mutation, tmp_path):
    case = CASES[3]
    answer = answer_for(case)
    values = answer["leading_space_counts"]
    answer["leading_space_counts"] = tuple(values) if mutation == "tuple" else values[::-1]
    result = retention.grade(case, materialize(case, tmp_path / "workspace"), answer, [])
    assert "answer_matches_source_contract" in result["checks"]


def source_function(path, name):
    tree = ast.parse(SOURCES[PREFIX + path]["text"])
    return next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == name)


def test_trace_gold_has_independent_static_control_flow_support():
    main = source_function("brainspace/benchmark.py", "main")
    selection = next(node for node in main.body if isinstance(node, ast.If)
                     and isinstance(node.test, ast.Name) and node.test.id == "use_stdin")
    assert isinstance(selection.orelse[0], ast.If)
    assert selection.orelse[0].test.id == "paths"
    assert any(isinstance(node, ast.IfExp) for node in ast.walk(selection.body[-1]))
    empty = next(node for node in main.body if isinstance(node, ast.If)
                 and isinstance(node.test, ast.UnaryOp)
                 and isinstance(node.test.operand, ast.Name)
                 and node.test.operand.id == "items")
    expected = answer_for(CASES[0])
    assert empty.body[-1].value.value == expected["blank"]["exit_code"]
    assert main.body.index(empty) > main.body.index(selection)
    final = main.body[-1].value
    assert isinstance(final, ast.IfExp)
    assert final.body.value == expected["row_exit_codes"]["all_lossless"]
    assert final.orelse.value == expected["row_exit_codes"]["one_nonlossless"]
    install = source_function("brainspace_setup.py", "_install_files")
    ignore = next(node for node in ast.walk(install) if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Attribute) and node.func.attr == "ignore_patterns")
    assert [ast.literal_eval(arg) for arg in ignore.args] == answer_for(CASES[1])[
        "installation"]["ignored_patterns"]
    demo = source_function("brainspace/benchmark.py", "demo_inputs")
    modules = next(node for node in demo.body if isinstance(node, ast.For)
                   and isinstance(node.target, ast.Name) and node.target.id == "rel")
    assert list(ast.literal_eval(modules.iter)) == answer_for(CASES[1])["demo"]["code_modules"]


def test_source_derived_control_independently_uses_only_literal_regexes():
    # Parse trusted source and apply only its three literal regex substitutions;
    # never import or execute the candidate/fixture module (including its ML path).
    source = SOURCES[PREFIX + "brainspace/compressors/prose_compressor.py"]["text"]
    tree = ast.parse(source)
    patterns = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "compile":
                patterns[node.targets[0].id] = ast.literal_eval(node.value.args[0])
    text = "  alpha  beta \t\n\n\n\n    gamma   delta\t\n"
    text = re.sub(patterns["_TRAILING_WS_RE"], "", text, flags=re.MULTILINE)
    text = re.sub(patterns["_BLANK_RUN_RE"], "\n\n", text)
    text = re.sub(patterns["_INTERIOR_MULTI_SPACE_RE"], " ", text)
    expected = answer_for(CASES[3])
    assert expected["normalised"] == text
    nonblank = [line for line in text.splitlines() if line.strip()]
    assert expected["leading_space_counts"] == [len(line) - len(line.lstrip(" ")) for line in nonblank]
    assert expected["blank_lines_between"] == text.count("\n\n")
    assert expected["trailing_tabs_retained"] is ("\t" in text)


def test_wrapper_has_no_second_validator_or_grader_implementation():
    wrapper = ast.parse(Path(retention.__file__).read_text(encoding="utf-8"))
    public = {node.name: node for node in wrapper.body if isinstance(node, ast.FunctionDef)}
    assert set(public) == {"load_cases", "grade"}
    for name, function in public.items():
        body = function.body[1:]  # skip docstring
        assert len(body) == 1 and isinstance(body[0], ast.Return)
        assert isinstance(body[0].value, ast.Call)
        assert body[0].value.func.value.id == "_oracle" and body[0].value.func.attr == name
