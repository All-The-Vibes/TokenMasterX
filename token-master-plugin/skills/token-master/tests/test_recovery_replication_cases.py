"""Offline corpus/oracle regressions; no inference or candidate-policy tuning."""
import ast
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib
import json
from pathlib import Path
import socket
import subprocess
import sys

import pytest

EVALS = Path(__file__).resolve().parents[3] / "evals"
REPO = EVALS.parents[1]
PREFIX = "token-master-plugin/skills/token-master/"
sys.path.insert(0, str(EVALS))
import parity_cases as parity  # noqa: E402
import retention_cases as retention  # noqa: E402
import recovery_replication_cases as replication  # noqa: E402
from quality.cases import Case, materialize  # noqa: E402


MANIFEST = json.loads(replication.MANIFEST_PATH.read_bytes())
CASES = replication.load_cases()
TASKS = {task["id"]: task for task in MANIFEST["tasks"]}
SOURCES = {source["path"]: source for source in MANIFEST["sources"]}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("network is forbidden in replication validation")
    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


def gold(case):
    return deepcopy(TASKS[case.id]["expected"])


def reads(case):
    return [{"name": "read_file", "arguments": {"path": path}} for path, _ in case.fixtures]


def test_frozen_shape_and_prespecified_readonly_scope():
    assert hashlib.sha256(replication.MANIFEST_PATH.read_bytes()).hexdigest() == replication.MANIFEST_SHA256
    assert MANIFEST["source_commit"] == replication.SOURCE_COMMIT
    assert MANIFEST["schema_version"] == 1
    assert len(CASES) == 4 and len(SOURCES) == 8
    assert [len(case.fixtures) for case in CASES] == [2, 2, 3, 1]
    assert Counter(case.intent for case in CASES) == {
        "navigation": 2, "overview": 1, "exact": 1}
    assert [task["category"] for task in TASKS.values()] == [
        "code_navigation", "code_navigation", "code_overview", "preservation_control"]
    assert MANIFEST["scope"].endswith("not_population_representative")
    assert all(type(case) is Case and case.allowed_changes == () and case.followups == ()
               and case.global_hint == "" for case in CASES)
    assert all("keep_recent" not in case.prompt and "bill" not in case.prompt.lower()
               for case in CASES)


def test_disclosed_overlap_and_fresh_questions_match_prior_frozen_corpora():
    metadata = MANIFEST["source_overlap"]
    previous_tasks, all_previous_paths = [], set()
    for name, expected_overlap in metadata["by_prior_corpus"].items():
        raw = (EVALS / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == metadata["prior_manifest_sha256"][name]
        previous = json.loads(raw)
        paths = ({source["path"] for source in previous["sources"]}
                 if "sources" in previous else {PREFIX + p for p, _ in previous["fixtures"]})
        assert sorted(SOURCES.keys() & paths) == expected_overlap
        all_previous_paths.update(paths)
        previous_tasks.extend(previous["tasks"])
    assert sorted(SOURCES.keys() - all_previous_paths) == metadata["new_paths"]
    assert len(metadata["new_paths"]) == 6
    assert metadata["by_prior_corpus"]["repository-cases.json"] == []
    assert metadata["by_prior_corpus"]["parity-cases.json"] == []
    assert metadata["by_prior_corpus"]["retention-cases.json"] == [
        PREFIX + "brainspace/compressors/json_compressor.py",
        PREFIX + "brainspace/compressors/logs_compressor.py"]
    counts = Counter(path for case in CASES for path, _ in case.fixtures)
    assert sorted(path for path, count in counts.items() if count > 1) == metadata["within_corpus_reused_paths"] == []
    assert metadata["source_independence_claimed"] is False
    assert not TASKS.keys() & {task["id"] for task in previous_tasks}
    assert not {case.prompt for case in CASES} & {task["prompt"] for task in previous_tasks}
    previous_gold = [task["expected"] for task in previous_tasks if "expected" in task]
    assert all(task["expected"] not in previous_gold for task in TASKS.values())


@pytest.mark.parametrize("source", MANIFEST["sources"], ids=lambda s: s["path"])
def test_every_source_is_verbatim_at_original_commit(source):
    data = subprocess.check_output(
        ["git", "show", f"{replication.SOURCE_COMMIT}:{source['path']}"], cwd=REPO)
    assert data == source["text"].encode("utf-8")
    assert source["encoding"] == "utf-8" and source["commit"] == replication.SOURCE_COMMIT
    assert len(data) == source["byte_length"]
    assert hashlib.sha256(data).hexdigest() == source["sha256"]


def test_all_gold_has_exact_line_evidence_and_stays_private():
    for case in CASES:
        task = TASKS[case.id]
        public = case.public_task()
        assert set(public) == {"id", "version", "identity", "prompt", "paths", "allowed_changes"}
        assert public["prompt"].endswith(task["prompt"])
        assert public["allowed_changes"] == []
        fields, paths = set(), set()
        for item in task["evidence"]:
            lines = SOURCES[item["path"]]["text"].splitlines(keepends=True)
            assert "".join(lines[item["start_line"] - 1:item["end_line"]]) == item["quote"]
            assert item["quote"] not in public["prompt"]
            assert item["rationale"]
            fields.update(item["answer_keys"])
            paths.add(item["path"])
        assert fields == task["expected"].keys()
        assert paths == set(case.files)


def test_shared_oracle_is_reused_without_mutating_live_corpora():
    before = [(module.MANIFEST_PATH, module.MANIFEST_SHA256, module.ORACLE_ID,
               [case.identity for case in module.load_cases()]) for module in (parity, retention)]
    private = replication._oracle
    assert private is not parity and private is not retention._oracle
    assert private.grade.__code__.co_code == parity.grade.__code__.co_code
    assert private.grade.__code__.co_filename == parity.grade.__code__.co_filename
    assert private.grade.__globals__ is not parity.grade.__globals__
    assert private.__name__ not in sys.modules
    importlib.reload(replication)
    assert replication._oracle is not private
    after = [(module.MANIFEST_PATH, module.MANIFEST_SHA256, module.ORACLE_ID,
              [case.identity for case in module.load_cases()]) for module in (parity, retention)]
    assert before == after
    assert replication.ORACLE_ID not in {parity.ORACLE_ID, retention.ORACLE_ID}


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_gold_passes_in_any_read_order_without_code_execution(case, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("replication oracle must not execute code")
    root = materialize(case, tmp_path / "workspace")
    events = list(reversed(reads(case)))
    result = replication.grade(case, root, gold(case), events, sandbox_runner=forbidden)
    assert set(result) == {
        "status", "success", "checks", "assertions", "changed_files", "unexpected_files",
        "missing_files", "oracle", "evidence_digest"}
    assert result["status"] == "passed" and result["success"] is True
    assert result["checks"] == [] and all(result["assertions"].values())
    assert result["changed_files"] == result["unexpected_files"] == result["missing_files"] == []
    assert result["oracle"] == replication.ORACLE_ID and len(result["evidence_digest"]) == 64
    assert result == replication.grade(case, root, gold(case), events)
    # Correctness does not require activation or a prescribed tool trajectory.
    assert replication.grade(case, root, gold(case), [])["success"]


def leaves(value, path=()):
    if type(value) is dict:
        for key, child in value.items():
            yield from leaves(child, (*path, key))
    elif type(value) is list:
        for index, child in enumerate(value):
            yield from leaves(child, (*path, index))
    else:
        yield path, value


LEAVES = [(case, path, value) for case in CASES for path, value in leaves(gold(case))]


@pytest.mark.parametrize("case,path,value", LEAVES,
                         ids=[case.id + ":" + ".".join(map(str, path))
                              for case, path, _ in LEAVES])
def test_every_gold_leaf_requires_exact_value_and_json_type(case, path, value, tmp_path):
    answer = gold(case)
    parent = answer
    for key in path[:-1]:
        parent = parent[key]
    wrong = {str: lambda v: v + " ", int: float, bool: int}
    parent[path[-1]] = wrong[type(value)](value)
    result = replication.grade(case, materialize(case, tmp_path / "workspace"), answer, [])
    assert not result["success"] and "answer_matches_source_contract" in result["checks"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
@pytest.mark.parametrize("mutation", ["missing", "extra", "text"])
def test_answer_shape_is_exact(case, mutation, tmp_path):
    answer = gold(case)
    if mutation == "missing":
        answer.pop(next(iter(answer)))
    elif mutation == "extra":
        answer["extra"] = True
    else:
        answer = json.dumps(answer)
    assert not replication.grade(case, materialize(case, tmp_path / "workspace"), answer, [])["success"]


@pytest.mark.parametrize("mutation", ["tuple", "order"])
def test_list_types_and_order_are_checked(mutation, tmp_path):
    case = CASES[0]
    answer = gold(case)
    head = answer["visible"]["head"]
    answer["visible"]["head"] = tuple(head) if mutation == "tuple" else head[::-1]
    assert not replication.grade(case, materialize(case, tmp_path / "workspace"), answer, [])["success"]


@pytest.mark.parametrize("mutation", ["edit", "crlf", "missing", "extra"])
def test_readonly_source_bytes_and_file_inventory(mutation, tmp_path):
    case = CASES[0]
    root = materialize(case, tmp_path / "workspace")
    path, text = case.fixtures[0]
    target = root / path
    if mutation == "edit":
        target.write_bytes(text.encode() + b"# changed\n")
    elif mutation == "crlf":
        target.write_bytes(text.replace("\n", "\r\n").encode())
    elif mutation == "missing":
        target.unlink()
    else:
        (root / "extra.txt").write_bytes(b"extra")
    result = replication.grade(case, root, gold(case), [])
    assert not result["success"]
    key = {"missing": "missing_files", "extra": "unexpected_files"}.get(mutation, "changed_files")
    assert result[key] == ["extra.txt" if mutation == "extra" else path]


@pytest.mark.parametrize("mutation", ["same_bytes", "restore", "rejected"])
def test_write_attempts_fail_despite_matching_final_bytes(mutation, tmp_path):
    case = CASES[0]
    root = materialize(case, tmp_path / "workspace")
    path, text = case.fixtures[0]
    events = [{"name": "write_file", "arguments": {"path": path, "content": text}}]
    if mutation == "restore":
        (root / path).write_bytes(b"changed")
        (root / path).write_bytes(text.encode())
        events.insert(0, {"name": "write_file", "arguments": {"path": path, "content": "changed"}})
    elif mutation == "rejected":
        events[0]["arguments"]["path"] = "forbidden.txt"
    result = replication.grade(case, root, gold(case), events)
    assert not result["success"] and result["changed_files"] == []
    assert "write_scope_respected" in result["checks"]


@pytest.mark.parametrize("events", [
    None, {}, [None], [{"name": "run_python", "arguments": {"code": "pass"}}],
    [{"name": "read_file", "arguments": {"path": "../escape"}}],
    [{"name": "headroom_retrieve", "arguments": {"hash": 123}}],
    [{"name": "headroom_retrieve", "arguments": {"hash": "abc", "extra": True}}],
])
def test_invalid_or_nonreadonly_events_fail(events, tmp_path):
    case = CASES[0]
    result = replication.grade(case, materialize(case, tmp_path / "workspace"), gold(case), events)
    assert not result["success"] and "write_scope_respected" in result["checks"]


def test_both_readonly_recovery_tools_and_call_ids_are_preserved(tmp_path):
    case = CASES[0]
    root = materialize(case, tmp_path / "workspace")
    events = [
        {"name": "headroom_retrieve", "arguments": {"hash": "abc123"}, "call_id": "replication-1"},
        {"name": "retrieve_original", "arguments": {"ref": "abc123", "offset": 0}, "call_id": "replication-2"},
        {"name": "search_original", "arguments": {"ref": "abc123", "query": "content"}},
        {"name": "fetch_artifact", "arguments": {"path": case.fixtures[0][0]}},
    ]
    before = deepcopy(events)
    result = replication.grade(case, root, gold(case), events)
    assert result["success"] and events == before
    events[0]["call_id"] = "replication-3"
    assert replication.grade(case, root, gold(case), events)["evidence_digest"] != result["evidence_digest"]


@pytest.mark.parametrize("mutation", ["gold", "source", "evidence", "commit", "overlap"])
def test_manifest_changes_cannot_redefine_trust(mutation, tmp_path, monkeypatch):
    changed = deepcopy(MANIFEST)
    if mutation == "gold":
        changed["tasks"][0]["expected"] = {}
    elif mutation == "source":
        source = changed["sources"][0]
        source["text"] += "\n"
        raw = source["text"].encode()
        source.update(byte_length=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    elif mutation == "evidence":
        changed["tasks"][0]["evidence"][0]["start_line"] += 1
    elif mutation == "commit":
        changed["source_commit"] = "0" * 40
    else:
        changed["source_overlap"]["source_independence_claimed"] = True
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    monkeypatch.setattr(replication._oracle, "MANIFEST_PATH", path)
    with pytest.raises(ValueError, match="integrity mismatch"):
        replication.load_cases()
    case = CASES[0]
    result = replication.grade(case, materialize(case, tmp_path / "workspace"), gold(case), [])
    assert not result["success"] and "manifest_integrity" in result["checks"]


@pytest.mark.parametrize("field", ["prompt", "fixtures", "allowed_changes", "intent"])
def test_case_substitution_is_rejected(field, tmp_path):
    case = CASES[0]
    values = {"prompt": case.prompt + " changed", "fixtures": ((case.fixtures[0][0], "changed"), *case.fixtures[1:]),
              "allowed_changes": (case.fixtures[0][0],), "intent": "exact"}
    changed = replace(case, **{field: values[field]})
    result = replication.grade(changed, materialize(changed, tmp_path / "workspace"), gold(case), [])
    assert not result["success"] and "known_case" in result["checks"]


def test_old_cases_and_missing_or_linked_workspaces_fail(tmp_path):
    prior = retention.load_cases()[0]
    root = materialize(prior, tmp_path / "prior")
    assert "known_case" in replication.grade(prior, root, {}, [])["checks"]
    case = CASES[0]
    assert "safe_workspace" in replication.grade(case, tmp_path / "missing", gold(case), [])["checks"]
    root = materialize(case, tmp_path / "workspace")
    try:
        (root / "linked").symlink_to(root / case.fixtures[0][0])
    except OSError:
        pytest.skip("OS does not permit symlink creation")
    assert "safe_workspace" in replication.grade(case, root, gold(case), [])["checks"]


def test_invalid_submissions_fail_and_evidence_binds_answer(tmp_path):
    case = CASES[0]
    root = materialize(case, tmp_path / "workspace")
    one = replication.grade(case, root, {"wrong": 1}, [])
    two = replication.grade(case, root, {"wrong": 2}, [])
    assert one["evidence_digest"] != two["evidence_digest"]
    assert not replication.grade(case, root, {"wrong": float("nan")}, [])["success"]
    replication._oracle._load_manifest()["tasks"][0]["expected"].clear()
    assert replication._oracle._load_manifest()["tasks"][0]["expected"] == gold(case)


def function(path, name):
    return next(node for node in ast.walk(ast.parse(SOURCES[path]["text"]))
                if isinstance(node, ast.FunctionDef) and node.name == name)


def test_reconstruction_gold_independently_matches_original_test_constants():
    method = function(PREFIX + "brainspace/tests/test_json_compressor.py",
                      "test_elided_list_lossless_roundtrip_full_reconstruction")
    assignments = {node.targets[0].id: node.value for node in method.body
                   if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
    count = ast.literal_eval(assignments["items"].args[0].args[0])
    opts = {kw.arg: ast.literal_eval(kw.value) for kw in assignments["result"].keywords
            if kw.arg in ("sample", "tail")}
    items = list(range(count))
    head, middle, tail = items[:opts["sample"]], items[opts["sample"]:-opts["tail"]], items[-opts["tail"]:]
    expected = gold(CASES[0])
    assert expected["input_count"] == count
    assert expected["visible"] == dict(head=head, tail=tail, marker_index=len(head),
                                      element_count=len(head) + 1 + len(tail))
    assert [expected["stored_middle"][key] for key in ("first", "last", "count")] == [
        middle[0], middle[-1], len(middle)]
    assert head + middle + tail == items
    assertions = [node.test for node in method.body if isinstance(node, ast.Assert)]
    assert ast.unparse(assertions[-1]) == "head + middle + tail == items"


def test_recovery_test_assertion_scope_is_not_inferred_from_docstring():
    method = function(PREFIX + "brainspace/tests/test_logs_compressor.py", "test_recovery_line_appended")
    assertions = [ast.unparse(node.test) for node in method.body if isinstance(node, ast.Assert)]
    assert assertions == ["recovery_lines", "ph in store", "store[ph] == original"]
    expected = gold(CASES[1])["assertion_scope"]
    assert all(expected[key] for key in (
        "checks_recovery_line_presence", "checks_key_membership", "checks_original_equality"))
    assert expected["explicitly_asserts_last_line"] is False


def test_overview_gold_agrees_with_parsed_manifests_and_initializer():
    market = json.loads(SOURCES[".claude-plugin/marketplace.json"]["text"])
    plugin = json.loads(SOURCES["token-master-plugin/.claude-plugin/plugin.json"]["text"])
    package = ast.parse(SOURCES[PREFIX + "brainspace/__init__.py"]["text"])
    literals = {node.targets[0].id: ast.literal_eval(node.value)
                for node in package.body if isinstance(node, ast.Assign)}
    expected = gold(CASES[2])
    assert expected["catalog"] == dict(
        plugin_count=len(market["plugins"]), name=market["name"], version=market["metadata"]["version"],
        plugin_source=market["plugins"][0]["source"], strict=market["plugins"][0]["strict"],
        skill_paths=market["plugins"][0]["skills"])
    assert expected["plugin"] == dict(
        name=plugin["name"], version=plugin["version"], skill_roots=plugin["skills"],
        license_identifier=plugin["license"], repository_matches_homepage=plugin["repository"] == plugin["homepage"])
    assert expected["package"]["version"] == literals["__version__"]
    assert expected["package"]["wildcard_exports"] == literals["__all__"]
    assert expected["versions_agree"] is (
        market["metadata"]["version"] == plugin["version"] == literals["__version__"])
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in package.body)
    assert expected["package"]["documented_interfaces_reexported"] is False


def test_exact_gold_matches_static_fstring_without_executing_generator():
    method = function("assets/generate_art.py", "_cubic")
    result = method.body[-1].value
    assert isinstance(result, ast.JoinedStr)
    values = {"a.x": 10, "a.y": 20, "b.x": 40, "b.y": 60, "mx": (10 + 40) / 2}
    pieces = []
    for node in result.values:
        if isinstance(node, ast.Constant):
            pieces.append(node.value)
        else:
            assert isinstance(node, ast.FormattedValue)
            spec = "".join(part.value for part in node.format_spec.values)
            pieces.append(format(values[ast.unparse(node.value)], spec))
    expected = gold(CASES[3])
    assert "".join(pieces) == expected["path"]
    attributes = {node.attr for node in ast.walk(method) if isinstance(node, ast.Attribute)}
    assert expected["uses_node_column"] is ("col" in attributes)
    assert expected["uses_node_row"] is ("row" in attributes)
    assert not any(isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store)
                   for node in ast.walk(method))
    assert expected["mutates_nodes"] is False
