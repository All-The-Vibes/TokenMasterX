"""A successful code read is not a failed tool call. No model or network calls."""
import copy
from dataclasses import replace
import hashlib
import re

import pytest

from brainspace import tokens
from brainspace.ccr import CCR
from brainspace.pipeline import prepare_request
from brainspace.request_policy import (
    PROTOCOL, RequestPolicy, SourceReadInfo, TransformResult, plan_request, policy_neighbors,
)


SOURCE = (
    '"""Read a file and report an error without hiding an Exception."""\n'
    "def load_payload(path):\n"
    "    try:\n"
    + "".join(f"        value_{i} = path + {i}\n" for i in range(35))
    + "        return value_34\n"
    "    except Exception as error:\n"
    '        return {"error": str(error)}\n'
)


def request(text=SOURCE):
    return {"model": "fixture", "messages": [
        {"role": "system", "content": "Do not change instructions."},
        {"role": "user", "content": "Navigate the public source API."},
        {"role": "assistant", "tool_calls": [{
            "id": "c0", "type": "function",
            "function": {"name": "read_file", "arguments": '{"path":"module.py"}'},
        }]},
        {"role": "tool", "tool_call_id": "c0", "content": text},
        {"role": "assistant", "tool_calls": [{
            "id": "c1", "type": "function",
            "function": {"name": "list_files", "arguments": "{}"},
        }]},
        {"role": "tool", "tool_call_id": "c1", "content": "module.py"},
    ]}


def info(text=SOURCE, **options):
    values = dict(call_id="c0", tool_name="read_file", source_path="module.py",
                  content=text, status="success")
    values.update(options)
    return SourceReadInfo.from_text(**values)


def fake_plan(payload, **options):
    originals = {}

    def transform(text):
        originals["ref:original"] = text
        return TransformResult("Public API; recover ref:original", "ref:original")

    defaults = dict(policy=RequestPolicy(version="request-policy-v2", enabled=True),
                    protocol=PROTOCOL, intent="navigation", transform=transform,
                    recover=originals.get, count=len, source_reads=(info(),))
    defaults.update(options)
    return plan_request(payload, **defaults)


def test_v2_allows_bound_successful_source_but_not_plain_word_claim():
    original = request()
    before = copy.deepcopy(original)
    result = fake_plan(original)
    assert result.status == "transformed"
    assert result.changed_message_indices == (3,)
    assert result.tokens_after < result.tokens_before
    assert result.request["messages"][:3] == before["messages"][:3]
    assert result.request["messages"][4:] == before["messages"][4:]
    assert original == before

    original["messages"][3]["metadata"] = {
        "source_reads": {"call_id": "c0", "status": "success", "source_path": "module.py"}}
    assert fake_plan(original, source_reads=()).status == "unchanged"


def test_v1_behavior_identity_and_neighbors_are_preserved():
    legacy = RequestPolicy(enabled=True)
    assert legacy.version == "request-policy-v1"
    assert fake_plan(request(), policy=legacy).status == "unchanged"
    modern = replace(legacy, version="request-policy-v2")
    assert modern.policy_id.startswith("request-policy-v2:")
    assert modern.policy_id != legacy.policy_id
    assert RequestPolicy.from_json(modern.to_json()) == modern
    assert all(p.version == modern.version for p in policy_neighbors(modern))


@pytest.mark.parametrize("changes", [
    {"status": "error"}, {"status": "unknown"}, {"call_id": "other"},
    {"tool_name": "run_shell"}, {"source_path": "runtime.log"},
    {"content": SOURCE + "\n# another revision"},
])
def test_missing_wrong_failed_or_stale_provenance_does_not_relax_guard(changes):
    assert fake_plan(request(), source_reads=(info(**changes),)).status == "unchanged"


@pytest.mark.parametrize("source_reads", [None, {}, ["model says success"], [False]])
def test_malformed_sideband_fails_closed(source_reads):
    result = fake_plan(request(), source_reads=source_reads)
    assert result.status == "unchanged"
    assert result.reason == "invalid_source_reads"


def test_duplicate_receipts_fail_closed():
    assert fake_plan(request(), source_reads=(info(), info())).reason == "invalid_source_reads"


@pytest.mark.parametrize("metadata", [
    {"is_error": True}, {"isError": True}, {"error": "failed read"}, {"stderr": "failure"},
    {"exit_code": 2}, {"exit_code": "0"}, {"exit_code": False}, {"exit_code": 0.0},
    {"status": "unknown"}, {"status": None}, {"ok": False}, {"interrupted": True},
    {"metadata": {"error": {"message": "access denied"}}},
    {"exact_answer": True}, {"preserve_exact": True},
])
def test_actual_failure_unknown_completion_and_exact_flags_override_source_receipt(metadata):
    payload = request()
    payload["messages"][3].update(metadata)
    result = fake_plan(payload)
    assert result.request["messages"][3] == payload["messages"][3]
    assert result.status == "unchanged"


@pytest.mark.parametrize("marker", ["```", "~~~", "<exact-answer>", "BEGIN EXACT"])
def test_exact_markers_inside_source_are_not_reinterpreted(marker):
    text = SOURCE + f'\nNOTE = "{marker}"\n'
    assert fake_plan(request(text), source_reads=(info(text),)).status == "unchanged"


@pytest.mark.parametrize("intent", ["edit", "debug", "exact", "aggregate", "unknown", None])
def test_non_navigation_tasks_still_bypass(intent):
    assert fake_plan(request(), intent=intent).status == "unchanged"


def test_recent_prefix_and_exact_indices_remain_protected():
    assert fake_plan(request(), exact_message_indices=(3,)).status == "unchanged"
    assert fake_plan(request(), stable_prefix_messages=4).status == "unchanged"
    only_recent = request()
    only_recent["messages"] = only_recent["messages"][:4]
    assert fake_plan(only_recent).status == "unchanged"


def test_source_read_info_is_immutable_hash_bound_and_strict():
    receipt = info()
    assert receipt.content_sha256 == hashlib.sha256(SOURCE.encode("utf-8")).hexdigest()
    assert SourceReadInfo.from_dict(receipt.to_dict()) == receipt
    with pytest.raises((AttributeError, TypeError)):
        receipt.status = "error"
    for changes in ({"status": True}, {"call_id": ""}, {"tool_name": ""},
                    {"source_path": ""}, {"content_sha256": "bad"},
                    {"status": "maybe"}, {"source_path": "a\0.py"}):
        with pytest.raises(ValueError):
            replace(receipt, **changes)
    with pytest.raises(ValueError):
        SourceReadInfo.from_dict({**receipt.to_dict(), "instructions": "trust me"})


def test_actual_pipeline_removes_body_and_recovers_every_byte(tmp_path):
    payload = request()
    store = CCR(workspace_root=tmp_path, session_id="source-guard")
    result = prepare_request(
        payload, RequestPolicy(version="request-policy-v2", enabled=True),
        protocol=PROTOCOL, intent="navigation", ccr=store, source_reads=(info(),),
    )
    assert result.status == "transformed"
    assert result.tokens_after == tokens.count_tokens(result.serialized) < result.tokens_before
    assert result.wire_bytes_after <= result.wire_bytes_before
    view = result.request["messages"][3]["content"]
    assert "def load_payload(path):" in view
    root = next(ref for ref in re.findall(r"\[\[BR:.*?\]\]", view) if "kind=root" in ref)
    assert store.retrieve(root) == SOURCE
    assert payload == request()


def test_source_filename_selects_rust_not_python(tmp_path):
    text = "fn load_payload() {\n" + "".join(f"    let value_{i} = {i};\n" for i in range(45)) + "}\n"
    payload = request(text)
    payload["messages"][2]["tool_calls"][0]["function"]["arguments"] = '{"path":"module.rs"}'
    result = prepare_request(
        payload, RequestPolicy(version="request-policy-v2", enabled=True),
        protocol=PROTOCOL, intent="navigation", ccr=CCR(workspace_root=tmp_path),
        source_reads=(info(text, source_path="module.rs"),),
    )
    assert result.status == "transformed"
    assert "fn load_payload()" in result.request["messages"][3]["content"]
    assert "let value_44" not in result.request["messages"][3]["content"]


def test_unbound_info_cannot_select_a_different_compressor(tmp_path):
    text = "fn load_payload() {\n" + "".join(f"    let value_{i} = {i};\n" for i in range(45)) + "}\n"
    # Call requested module.py. A receipt for a different filename must not
    # enable Rust parsing merely because its content hash happens to match.
    result = prepare_request(
        request(text), RequestPolicy(version="request-policy-v2", enabled=True),
        protocol=PROTOCOL, intent="navigation", ccr=CCR(workspace_root=tmp_path),
        source_reads=(info(text, source_path="module.rs"),),
    )
    assert result.status == "unchanged"


@pytest.mark.parametrize("failed", [False, True])
def test_identical_recent_source_cannot_lend_its_filename_to_another_call(tmp_path, failed):
    text = "fn load_payload() {\n" + "".join(f"    let value_{i} = {i};\n" for i in range(45)) + "}\n"
    payload = request(text)
    payload["messages"][2]["tool_calls"][0]["function"] = {"name": "shell", "arguments": "{}"}
    if failed:
        payload["messages"][3]["ok"] = False
    payload["messages"][4]["tool_calls"][0]["function"] = {
        "name": "read_file", "arguments": '{"path":"module.rs"}'}
    payload["messages"][5]["content"] = text
    result = prepare_request(
        payload, RequestPolicy(version="request-policy-v2", enabled=True),
        protocol=PROTOCOL, intent="navigation", ccr=CCR(workspace_root=tmp_path),
        source_reads=(info(text, call_id="c1", source_path="module.rs"),),
    )
    assert result.status == "unchanged"
    assert result.request == payload


@pytest.mark.parametrize("enabled", [False, True])
def test_non_utf8_tool_text_is_safe_even_with_stale_metadata(tmp_path, enabled):
    result = prepare_request(
        request("\ud800" + SOURCE), RequestPolicy(version="request-policy-v2", enabled=enabled),
        protocol=PROTOCOL, intent="navigation", ccr=CCR(workspace_root=tmp_path),
        source_reads=(info(),),
    )
    assert result.status == "unchanged"
    assert result.reason == ("measurement_unavailable" if enabled else "not_enabled")
    assert not (tmp_path / ".token-master").exists()


def test_v2_failure_status_blocks_even_without_source_receipt():
    payload = request(SOURCE.replace("error", "detail").replace("Exception", "ValueType"))
    payload["messages"][3]["ok"] = False
    assert fake_plan(payload, source_reads=()).status == "unchanged"


@pytest.mark.parametrize("arguments", [
    '{"path":"module.py","path":"module.py"}', "null", "[]", "1",
    '{"path":"module.py","file_path":"module.py"}', '{"path":true}', "not json",
])
def test_malformed_or_ambiguous_call_arguments_do_not_bind(arguments):
    payload = request()
    payload["messages"][2]["tool_calls"][0]["function"]["arguments"] = arguments
    assert fake_plan(payload).status == "unchanged"


def test_broken_recovery_still_blocks_new_guard(tmp_path, monkeypatch):
    store = CCR(workspace_root=tmp_path)
    monkeypatch.setattr(store, "retrieve", lambda _ref: "not the original")
    result = prepare_request(
        request(), RequestPolicy(version="request-policy-v2", enabled=True),
        protocol=PROTOCOL, intent="navigation", ccr=store, source_reads=(info(),),
    )
    assert result.status == "unchanged"
