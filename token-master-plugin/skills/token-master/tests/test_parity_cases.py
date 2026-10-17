"""Offline oracle/fixture regressions, not evidence of live-model parity."""
import ast
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

EVALS = Path(__file__).resolve().parents[3] / "evals"
REPO = EVALS.parents[1]
sys.path.insert(0, str(EVALS))
import parity_cases as parity  # noqa: E402
from quality.cases import materialize  # noqa: E402


MANIFEST = json.loads((EVALS / "parity-cases.json").read_bytes())
CASES = parity.load_cases()
TASKS = {task["id"]: task for task in MANIFEST["tasks"]}
SOURCES = {source["path"]: source for source in MANIFEST["sources"]}
PREFIX = "token-master-plugin/skills/token-master/"


def events_for(case):
    tool = "fetch_artifact" if TASKS[case.id]["category"] == "document_retrieval" else "read_file"
    return [{"name": tool, "arguments": {"path": path}} for path, _ in case.fixtures]


def gold(case):
    return deepcopy(TASKS[case.id]["expected"])


def test_frozen_manifest_and_bounded_workload():
    assert hashlib.sha256(parity.MANIFEST_PATH.read_bytes()).hexdigest() == parity.MANIFEST_SHA256
    assert MANIFEST["source_commit"] == "426fc853389ddba4bc6e1dd35a28179a895c064f"
    assert len(CASES) == 6
    assert Counter(task["category"] for task in TASKS.values()) == {
        "code_navigation": 2, "document_retrieval": 2, "preservation_control": 2}
    assert Counter(case.intent for case in CASES) == {
        "navigation": 2, "task": 1, "overview": 1, "exact": 1, "debug": 1}
    prior = json.loads((EVALS / "repository-cases.json").read_bytes())
    assert not set(TASKS) & {task["id"] for task in prior["tasks"]}
    assert not {case.prompt for case in CASES} & {task["prompt"] for task in prior["tasks"]}
    assert "not_iid_or_production_certificate" in MANIFEST["scope"]
    assert "not independent" in " ".join(MANIFEST["limitations"])
    assert MANIFEST["artifact_tool"]["read_only"] is True
    assert all(case.allowed_changes == () and case.followups == () for case in CASES)


@pytest.mark.parametrize("source", MANIFEST["sources"], ids=lambda s: s["path"])
def test_fixture_bytes_match_original_git_commit(source):
    # Fetch raw bytes, not PowerShell/text-mode output that could normalize LF.
    original = subprocess.check_output(
        ["git", "show", f"{parity.SOURCE_COMMIT}:{source['path']}"], cwd=REPO)
    assert source["commit"] == parity.SOURCE_COMMIT
    assert source["encoding"] == "utf-8"
    assert original == source["text"].encode("utf-8")
    assert len(original) == source["byte_length"]
    assert hashlib.sha256(original).hexdigest() == source["sha256"]


def test_evidence_quotes_cover_every_gold_field_and_stay_private():
    for case in CASES:
        task = TASKS[case.id]
        public = case.public_task()
        assert set(public) == {"id", "version", "identity", "prompt", "paths", "allowed_changes"}
        assert "expected" not in public and "evidence" not in public
        assert "oracle" not in public and "source_paths" not in public
        assert case.global_hint == ""
        assert public["prompt"].endswith(task["prompt"])
        assert public["allowed_changes"] == []
        covered = set()
        for item in task["evidence"]:
            lines = SOURCES[item["path"]]["text"].splitlines(keepends=True)
            assert "".join(lines[item["start_line"] - 1:item["end_line"]]) == item["quote"]
            assert item["path"] in public["paths"]
            assert item["quote"] not in public["prompt"]
            covered.update(item["answer_keys"])
        assert covered == task["expected"].keys()
        assert len(case.fixtures) >= 2
        assert all(path in SOURCES and text == SOURCES[path]["text"] for path, text in case.fixtures)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_gold_passes_with_strict_runner_verdict(case, tmp_path):
    root = materialize(case, tmp_path / "workspace")
    def forbidden_runner(*args, **kwargs):
        pytest.fail("read-only oracle must never execute code")
    answer = gold(case)
    events = events_for(case)
    events.append({"name": "answer", "arguments": {"content": answer}})
    verdict = parity.grade(case, root, answer, events, sandbox_runner=forbidden_runner)
    assert set(verdict) == {
        "status", "success", "checks", "assertions", "changed_files", "unexpected_files",
        "missing_files", "oracle", "evidence_digest"}
    assert verdict["status"] == "passed" and verdict["success"] is True
    assert verdict["checks"] == []
    assert all(verdict["assertions"].values())
    assert verdict["changed_files"] == verdict["unexpected_files"] == verdict["missing_files"] == []
    assert len(verdict["evidence_digest"]) == 64
    assert verdict == parity.grade(case, root, answer, events)
    assert {p: (root / p).read_bytes() for p, _ in case.fixtures} == {
        p: text.encode("utf-8") for p, text in case.fixtures}


def leaves(value, path=()):
    if type(value) is dict:
        for key, child in value.items():
            yield from leaves(child, (*path, key))
    elif type(value) is list and value:
        for index, child in enumerate(value):
            yield from leaves(child, (*path, index))
    else:
        yield path, value


MUTATIONS = [(case, path, value) for case in CASES for path, value in leaves(gold(case))]


@pytest.mark.parametrize("case,path,value", MUTATIONS,
                         ids=[c.id + ":" + ".".join(map(str, p)) for c, p, _ in MUTATIONS])
def test_every_gold_leaf_is_load_bearing(case, path, value, tmp_path):
    answer = gold(case)
    parent = answer
    for key in path[:-1]:
        parent = parent[key]
    # In particular, bool->int and int->float compare equal in normal Python.
    wrong = {bool: lambda x: int(x), int: lambda x: float(x), float: lambda x: str(x),
             str: lambda x: x + " ", list: lambda x: (), type(None): lambda x: "null"}
    parent[path[-1]] = wrong[type(value)](value)
    verdict = parity.grade(case, materialize(case, tmp_path / "workspace"), answer, events_for(case))
    assert verdict["success"] is False
    assert "answer_matches_source_contract" in verdict["checks"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
@pytest.mark.parametrize("mutation", ["missing", "extra", "unstructured"])
def test_answer_shape_is_exact(case, mutation, tmp_path):
    answer = gold(case)
    if mutation == "missing":
        answer.pop(next(iter(answer)))
    elif mutation == "extra":
        answer["rationale"] = "Looks correct"
    else:
        answer = json.dumps(answer)
    result = parity.grade(case, materialize(case, tmp_path / "workspace"), answer, events_for(case))
    assert result["success"] is False


@pytest.mark.parametrize("mutation", ["edit", "crlf", "missing", "extra"])
def test_all_workspace_bytes_and_files_are_protected(mutation, tmp_path):
    case = CASES[0]
    root = materialize(case, tmp_path / "workspace")
    path = case.fixtures[0][0]
    target = root / path
    if mutation == "missing":
        target.unlink()
    elif mutation == "extra":
        (root / "unexpected.txt").write_bytes(b"extra")
    elif mutation == "crlf":
        target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n"))
    else:
        target.write_bytes(target.read_bytes() + b"# change\n")
    result = parity.grade(case, root, gold(case), events_for(case))
    assert result["success"] is False
    if mutation == "extra":
        assert result["unexpected_files"] == ["unexpected.txt"]
    elif mutation == "missing":
        assert result["missing_files"] == [path]
    else:
        assert result["changed_files"] == [path]


@pytest.mark.parametrize("kind", ["same_bytes", "restore", "rejected"])
def test_write_attempt_fails_even_with_unchanged_final_bytes(kind, tmp_path):
    case = CASES[0]
    root = materialize(case, tmp_path / "workspace")
    path, text = case.fixtures[0]
    events = events_for(case)
    events.append({"name": "write_file", "arguments": {
        "path": path, "content": text if kind == "same_bytes" else "changed"}})
    if kind == "restore":
        (root / path).write_bytes(b"changed")
        (root / path).write_bytes(text.encode("utf-8"))
        events.append({"name": "write_file", "arguments": {"path": path, "content": text}})
    result = parity.grade(case, root, gold(case), events)
    assert result["success"] is False
    assert result["changed_files"] == []
    assert "write_scope_respected" in result["checks"]


@pytest.mark.parametrize("events", [
    None, {}, [None], [{"name": "write", "arguments": {}}],
    [{"name": "run_python", "arguments": {"code": "print('ok')"}}],
    [{"name": "read_file", "arguments": {"path": "../outside"}}],
    [{"name": "read_file", "arguments": {"path": "safe", "content": "bad"}}],
    [{"name": "read_file", "arguments": {"path": ["bad"]}}],
    [{"name": [], "arguments": {}}],
])
def test_malformed_or_non_readonly_events_fail_closed(events, tmp_path):
    case = CASES[0]
    result = parity.grade(case, materialize(case, tmp_path / "workspace"), gold(case), events)
    assert result["success"] is False
    assert "write_scope_respected" in result["checks"]


@pytest.mark.parametrize("case", CASES[2:4], ids=lambda c: c.id)
def test_documents_require_all_four_fetches_but_not_an_order(case, tmp_path):
    root = materialize(case, tmp_path / "workspace")
    events = events_for(case)
    assert len(events) == 4
    assert parity.grade(case, root, gold(case), list(reversed(events)))["success"]
    for omitted in range(len(events)):
        assert not parity.grade(case, root, gold(case),
                                events[:omitted] + events[omitted + 1:])["success"]
    reads = [{"name": "read_file", "arguments": event["arguments"]} for event in events]
    assert not parity.grade(case, root, gold(case), reads)["success"]
    assert [event["arguments"]["path"] for event in events] == list(case.files)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_headroom_recovery_is_readonly_and_preserves_parent_call_ids(case, tmp_path):
    root = materialize(case, tmp_path / "workspace")
    events = events_for(case) + [{
        "name": "headroom_retrieve", "arguments": {"hash": "abcdef012345"},
        "call_id": "upstream-recovery-call-17",
    }]
    original = deepcopy(events)
    result = parity.grade(case, root, gold(case), events)
    assert result["success"] is True
    assert result["assertions"]["write_scope_respected"] is True
    assert events == original
    events[-1]["call_id"] = "upstream-recovery-call-18"
    assert parity.grade(case, root, gold(case), events)["evidence_digest"] != result["evidence_digest"]


@pytest.mark.parametrize("arguments", [
    {}, {"ref": "abcdef"}, {"hash": 123}, {"hash": None}, {"hash": True},
    {"hash": ["abcdef"]}, {"hash": "abcdef", "path": "extra"},
])
def test_headroom_recovery_requires_exact_hash_string_schema(arguments, tmp_path):
    case = CASES[0]
    result = parity.grade(case, materialize(case, tmp_path / "workspace"), gold(case),
                          [{"name": "headroom_retrieve", "arguments": arguments}])
    assert not result["success"]
    assert "write_scope_respected" in result["checks"]


def test_no_billing_questions_or_gold_and_source_prose_is_unchanged():
    operations = TASKS["parity_document_operations"]
    assert "resume_rebills" not in json.dumps(operations)
    assert "precision_estimates" not in operations["expected"]
    assert "re-billed" in SOURCES[PREFIX + "SKILL.md"]["text"]
    for task in TASKS.values():
        assert "bill" not in task["prompt"].lower()
        assert "bill" not in json.dumps(task["expected"]).lower()
        assert all("re-bill" not in item["quote"] for item in task["evidence"])


def test_document_templates_are_needed_for_distinct_source_grounded_answers():
    delivery = gold(CASES[2])["routing_templates"]
    operations = gold(CASES[3])
    assert CASES[3].intent == "overview"
    assert delivery["claude"]["inline_mcp_servers"] is False
    assert delivery["copilot"]["inline_mcp_servers"] is True
    assert delivery["claude"]["native_tools"] == ["Read", "Grep", "Glob", "Bash"]
    assert delivery["copilot"]["native_tools"] == ["read", "search", "execute"]
    claude = SOURCES[PREFIX + "agent.template.claude.md"]["text"]
    copilot = SOURCES[PREFIX + "agent.template.copilot.md"]["text"]
    assert "mcp-servers:" not in claude.split("---")[1]
    assert "mcp-servers:" in copilot.split("---")[1]
    assert "Read, Grep, Glob, Bash" in claude
    assert "'read', 'search', 'execute'" in copilot
    assert delivery["copilot"]["server_names"] == ["graphify-nav", "codegraph"]
    assert delivery["copilot"]["graph_path_environment"] == "GRAPH_PATH"
    assert operations["routing"]["precision_fallback"] == [
        "codegraph_callers", "graphify-nav callers", "grep"]
    assert operations["routing"]["exclude_test_spec_callbacks"] is True
    assert "grep (and DROP test/spec callbacks" in claude
    assert operations["continuity"]["claude_recall"] == "saved_transcript_keyword_search"
    assert operations["continuity"]["copilot_recall"] == "FTS5_keyword_search"
    assert operations["continuity"]["copilot_interactive_command"] == "/chronicle"
    assert "search your saved transcripts for the keyword" in claude
    assert "in an FTS5 table" in copilot and "`/chronicle`" in copilot
    for case in CASES[2:4]:
        evidence = TASKS[case.id]["evidence"]
        assert set(case.files) == {item["path"] for item in evidence}


@pytest.mark.parametrize("mutation", ["gold", "source", "hash", "evidence", "prompt", "commit"])
def test_manifest_tampering_rejected_before_gold_is_trusted(mutation, tmp_path, monkeypatch):
    bad = deepcopy(MANIFEST)
    if mutation == "gold":
        bad["tasks"][0]["expected"]["entrypoint"] = "forged"
    elif mutation == "source":
        bad["sources"][0]["text"] += "\n"
        raw = bad["sources"][0]["text"].encode()
        bad["sources"][0].update(sha256=hashlib.sha256(raw).hexdigest(), byte_length=len(raw))
    elif mutation == "hash":
        bad["sources"][0]["sha256"] = "0" * 64
    elif mutation == "evidence":
        bad["tasks"][0]["evidence"][0]["start_line"] += 1
    elif mutation == "prompt":
        bad["tasks"][0]["prompt"] += " forged"
    else:
        bad["source_commit"] = "0" * 40
    path = tmp_path / "untrusted.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setattr(parity, "MANIFEST_PATH", path)
    with pytest.raises(ValueError, match="integrity mismatch"):
        parity.load_cases()
    case = CASES[0]
    result = parity.grade(case, materialize(case, tmp_path / "workspace"), gold(case), [])
    assert result["success"] is False
    assert "manifest_integrity" in result["checks"]


@pytest.mark.parametrize("field", ["prompt", "fixtures", "intent", "allowed_changes"])
def test_case_substitution_cannot_redefine_originals(field, tmp_path):
    case = CASES[0]
    replacements = {
        "prompt": case.prompt + " forged", "intent": "overview",
        "fixtures": ((case.fixtures[0][0], "forged"), *case.fixtures[1:]),
        "allowed_changes": (case.fixtures[0][0],),
    }
    changed = replace(case, **{field: replacements[field]})
    result = parity.grade(changed, materialize(changed, tmp_path / "workspace"), gold(case), [])
    assert result["success"] is False
    assert "known_case" in result["checks"]


def test_reloads_do_not_share_mutable_gold_or_case_state():
    private = parity._load_manifest()
    private["tasks"][0]["expected"].clear()
    loaded = parity.load_cases()
    loaded.clear()
    assert len(parity.load_cases()) == 6
    assert parity._load_manifest()["tasks"][0]["expected"] == gold(CASES[0])


def test_distinct_wrong_answers_produce_distinct_evidence(tmp_path):
    case = CASES[0]
    root = materialize(case, tmp_path / "workspace")
    first = parity.grade(case, root, {"wrong": 1}, [])
    second = parity.grade(case, root, {"wrong": 2}, [])
    assert first["evidence_digest"] != second["evidence_digest"]
    assert not parity.grade(case, root, {"wrong": float("nan")}, [])["success"]


def test_missing_and_linked_workspace_fail_closed(tmp_path):
    case = CASES[0]
    assert not parity.grade(case, tmp_path / "absent", gold(case), [])["success"]
    root = materialize(case, tmp_path / "workspace")
    link = root / "linked"
    try:
        link.symlink_to(root / case.fixtures[0][0])
    except OSError:
        pytest.skip("OS does not permit symlink creation")
    result = parity.grade(case, root, gold(case), [])
    assert "safe_workspace" in result["checks"]


def tree(path):
    return ast.parse(SOURCES[PREFIX + path]["text"])


def test_source_literal_and_dispatch_gold_independently_matches_ast():
    # Only literal_eval on source literals; no exec/import of historical code.
    ccr = tree("brainspace/ccr.py")
    regex = next(node.value.args[0].value for node in ccr.body
                 if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "PLACEHOLDER_RE" for t in node.targets))
    assert regex == gold(CASES[4])["placeholder_regex"]
    source = tree("brainspace/compressors/code_compressor.py")
    spec = ast.literal_eval(next(node.value for node in source.body
                                if isinstance(node, ast.AnnAssign)
                                and node.target.id == "_LANG_SPECS"))["rust"]
    expected = gold(CASES[1])
    assert expected["dispatch"]["grammar_module"] == spec["module"]
    assert expected["rust_nodes"] == {
        key: list(spec[key]) if isinstance(spec[key], tuple) else spec[key]
        for key in ("elide", "recurse", "wrapper", "docstring")}
    lookup = gold(CASES[0])["lookup"]
    assert lookup == {"match": "hash_prefix", "maximum_matches": 2,
                      "ambiguous_result": None, "missing_result": None}
    assert "SQL" not in TASKS[CASES[0].id]["prompt"]
    assert "parameter_suffix" not in TASKS[CASES[0].id]["prompt"]
    sql_literals = {node.value for node in ast.walk(ccr)
                    if isinstance(node, ast.Constant) and type(node.value) is str}
    assert "SELECT hash, blob FROM ccr WHERE hash LIKE ? LIMIT 2" in sql_literals


def test_debug_gold_matches_actual_fallback_not_its_comment():
    source = tree("brainspace/compressors/code_compressor.py")
    helper = next(node for node in source.body if isinstance(node, ast.FunctionDef)
                  and node.name == "_make_stub")
    fallback = helper.body[-1]
    assert isinstance(fallback, ast.Return) and isinstance(fallback.value, ast.JoinedStr)
    assert [node.value for node in fallback.value.values if isinstance(node, ast.Constant)] == [
        "... <", " lines elided>\n"]
    assert [node.value.id for node in fallback.value.values if isinstance(node, ast.FormattedValue)] == [
        "pad", "n_lines"]
    expected = gold(CASES[5])
    literal_result = " " * 4 + "... <1 lines elided>\n"
    assert expected["without_stash"] == expected["failed_stash"] == expected["raising_stash"] == literal_result
    assert "return 7" not in literal_result and "[[BR:" not in literal_result
    assert expected["original_body_preserved"] is expected["implementation_meets_contract"] is False
    assert expected["contract_requires_lossless_without_stash"] is True
    assert "compressor must stay\n    lossless" in SOURCES[
        PREFIX + "brainspace/compressors/__init__.py"]["text"]
