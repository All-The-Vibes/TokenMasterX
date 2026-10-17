"""Exact-JSON v4 safety/mechanics, not workload selection or quality evidence."""
from copy import deepcopy
from dataclasses import replace
import json
import random
import socket
from typing import Any

import pytest

from brainspace import pipeline, tokens
from brainspace.ccr import CCR
from brainspace.compressors.json_compressor import compress_json
from brainspace.pipeline import prepare_request
from brainspace.request_policy import (
    PROTOCOL, RequestPolicy, SourceReadInfo, TransformResult, plan_request,
    policy_neighbors, serialize_request,
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("no network or model calls in JSON policy tests")
    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def spaced(compact, seed=0):
    """Independent fixture authoring: insert JSON whitespace only at punctuation."""
    rng = random.Random(seed)
    result, quoted, escaped = [" \r\n"], False, False
    for char in compact:
        result.append(char)
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "{}[]:,":
            result.append(rng.choice(("\r\n        ", "\n\t    ", "          ")))
    result.append("\r\n ")
    return "".join(result)


COMPACT = (
    r'{"duplicate":-0,"duplicate":1.2300e+04,"negative":-0.0,"small":1E-09,'
    r'"string":"spaces  \t \n \r \/ \\ \" \u0041","unicode":"漢 café",'
    '"rows":[' + ",".join('{"id":' + str(i) + ',"value":true}' for i in range(40)) + "]}"
)
TEXT = spaced(COMPACT)


def policy(**changes):
    return RequestPolicy(version="request-policy-v4", enabled=True, min_tool_chars=1, **changes)


def payload(contents=None, paths=None, tool="read_file"):
    contents = [TEXT, '{"newest":true}'] if contents is None else contents
    paths = [f"data-{i}.json" for i in range(len(contents))] if paths is None else paths
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "Preserve instructions exactly."},
        {"role": "developer", "content": "No writes or execution."},
        {"role": "user", "content": "Report the JSON facts."},
    ]
    infos = []
    for index, (text, path) in enumerate(zip(contents, paths)):
        call_id = "read-" + str(index)
        messages.extend([
            {"role": "assistant", "content": None, "tool_calls": [{
                "id": call_id, "type": "function",
                "function": {"name": tool, "arguments": json.dumps({"path": path})}}]},
            {"role": "tool", "tool_call_id": call_id, "content": text, "ok": True,
             "metadata": {"opaque": [3, 1, 2]}},
        ])
        infos.append(SourceReadInfo.from_text(call_id=call_id, tool_name=tool,
                     source_path=path, content=text, status="success"))
    return {"model": "offline-json", "messages": messages, "max_tokens": 128,
            "metadata": {"preserve": "漢\r\n"},
            "tools": [{"type": "function", "function": {"name": tool,
                       "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}]}, tuple(infos)


def store(tmp_path):
    return CCR(tmp_path / "recovery.sqlite", workspace_root=tmp_path, session_id="json-v4")


def transform_for(ccr, calls):
    def transform(content, info):
        calls.append((content, info))
        reference = ccr.stash(content, ctype="json", source=info.source_path, kind="root")
        return TransformResult(compress_json(content, intent="conservative") + "\n" + reference, reference)
    return transform


def forbidden(*args, **kwargs):
    pytest.fail("generic lossy transform/router or duplicate-reuse route must not drive v4")


def plan(tmp_path, request=None, infos=None, **changes):
    if request is None:
        request, infos = payload()
    ccr = store(tmp_path)
    calls: list[tuple[str, SourceReadInfo]] = []
    options = dict(policy=policy(), protocol=PROTOCOL, intent="conservative",
                   count=tokens.count_tokens, source_reads=infos, recover=ccr.retrieve,
                   json_transform=transform_for(ccr, calls), transform=forbidden, source_transform=forbidden)
    options.update(changes)
    result = plan_request(request, **options)
    return result, ccr, calls


def test_unique_json_compacts_without_reserialization_and_preserves_every_other_field(tmp_path):
    original, infos = payload()
    before = deepcopy(original)
    result, ccr, calls = plan(tmp_path, original, infos)
    assert result.status == "transformed" and result.reason == "exact_json_compaction"
    assert result.changed_message_indices == (4,) and len(calls) == 1
    view = result.request["messages"][4]["content"]
    compact, reference = view.rsplit("\n", 1)
    assert compact == COMPACT
    assert compact.count('"duplicate":') == 2
    assert '1.2300e+04' in compact and '-0.0' in compact and '"duplicate":-0,' in compact
    assert r'\u0041' in compact and r'\/' in compact and r'\\' in compact
    assert len(json.loads(compact)["rows"]) == 40
    assert ";kind=root;" in reference and ";type=json;" in reference
    assert ccr.retrieve(reference).encode("utf-8") == TEXT.encode("utf-8")
    with pytest.raises(json.JSONDecodeError):
        json.loads(view)  # Payload exactness does not mean the footer is JSON.
    expected = deepcopy(original)
    expected["messages"][4]["content"] = view
    assert result.request == expected and original == before
    assert result.serialized == serialize_request(expected)
    assert result.tokens_after == tokens.count_tokens(result.serialized) < result.tokens_before
    assert result.wire_bytes_after == len(result.serialized.encode("utf-8")) <= result.wire_bytes_before


@pytest.mark.parametrize("intent", ["conservative", "navigation", "overview", "aggregate", "task"])
def test_all_semantic_intents_use_conservative_json_not_overview_sampling(tmp_path, monkeypatch, intent):
    monkeypatch.setattr(pipeline, "route_typed", forbidden)
    request, infos = payload()
    result = prepare_request(request, policy(), ccr=store(tmp_path), protocol=PROTOCOL,
                             intent=intent, source_reads=infos, hint="misleading.py")
    assert result.status == "transformed"
    assert result.request["messages"][4]["content"].rsplit("\n", 1)[0] == COMPACT
    assert "_brainspace_view" not in result.request["messages"][4]["content"]


@pytest.mark.parametrize("intent", [None, "exact", "edit", "debug", "unknown", "patch"])
def test_nonsemantic_intents_never_call_storage_or_transform(tmp_path, intent):
    result, _, calls = plan(tmp_path, intent=intent, json_transform=forbidden)
    assert result.status == "unchanged" and not calls


@pytest.mark.parametrize("options", [
    {"stable_prefix_messages": 5}, {"exact_message_indices": (4,)},
    {"source_reads": ()}, {"json_transform": None}, {"recover": None}, {"count": None},
    {"protocol": "unknown"},
])
def test_missing_authority_protection_or_prerequisite_keeps_original(tmp_path, options):
    result, _, calls = plan(tmp_path, **options)
    assert result.status == "unchanged" and result.request == payload()[0] and calls == []


@pytest.mark.parametrize("change", [
    {"status": "error"}, {"status": "unknown"}, {"call_id": "foreign"},
    {"tool_name": "get_json"}, {"source_path": "wrong.json"}, {"content_sha256": "0" * 64},
])
def test_invalid_or_mismatched_source_receipt_cannot_authorize_compaction(tmp_path, change):
    request, infos = payload()
    modified = (replace(infos[0], **change), infos[1])
    result, _, calls = plan(tmp_path, request, modified, json_transform=forbidden)
    assert result.request is request and calls == []


@pytest.mark.parametrize("metadata", [
    {"isError": True}, {"interrupted": True}, {"is_interrupt": True},
    {"ok": False}, {"success": False}, {"status": "unknown"}, {"exit_code": 1},
    {"exit_code": False}, {"stderr": "reported failure"}, {"errors": ["failed"]},
    {"preserve_exact": True}, {"exact_answer": True}, {"metadata": {"preserve_exact": True}},
])
def test_authoritative_error_interruption_and_exact_metadata_override_success_receipt(tmp_path, metadata):
    request, infos = payload()
    request["messages"][4].update(metadata)
    result, _, _ = plan(tmp_path, request, infos, json_transform=forbidden)
    assert result.request is request


@pytest.mark.parametrize("marker", ["```", "~~~", "<exact-answer", "BEGIN EXACT"])
def test_exact_markers_even_inside_json_strings_remain_protected(tmp_path, marker):
    compact = json.dumps({"literal": marker, "rows": list(range(100))}, separators=(",", ":"))
    request, infos = payload([spaced(compact), "{}"])
    result, _, _ = plan(tmp_path, request, infos, json_transform=forbidden)
    assert result.request is request


def test_error_words_inside_successful_json_are_data_not_transport_failure(tmp_path):
    compact = '{"status":"error","error":"Exception FAILED fatal","rows":[' + ",".join(map(str, range(100))) + "]}"
    request, infos = payload([spaced(compact), "{}"], tool="fetch_artifact")
    result, _, calls = plan(tmp_path, request, infos)
    assert result.status == "transformed" and len(calls) == 1
    assert result.request["messages"][4]["content"].rsplit("\n", 1)[0] == compact


@pytest.mark.parametrize("content", [
    COMPACT, '{"bad":}', '{"nonfinite":NaN}', '{"infinite":Infinity}', '{"value":1} trailing',
    "\ufeff" + TEXT, "plain prose", '{"control":"\x01"}',
])
def test_no_lexical_change_or_invalid_json_never_calls_transform(tmp_path, content):
    request, infos = payload([content, "{}"])
    result, _, calls = plan(tmp_path, request, infos, json_transform=forbidden)
    assert result.request is request and calls == []


def test_newest_result_is_never_compacted_even_when_unique_and_profitable(tmp_path):
    request, infos = payload([TEXT])
    result, _, calls = plan(tmp_path, request, infos, json_transform=forbidden)
    assert result.request is request and calls == []


def test_duplicate_json_is_compacted_not_replaced_by_v3_reuse(tmp_path, monkeypatch):
    from brainspace import exact_reuse
    monkeypatch.setattr(exact_reuse, "find_exact_reuses", forbidden)
    request, infos = payload([TEXT, TEXT, "{}"])
    result, _, calls = plan(tmp_path, request, infos)
    assert result.changed_message_indices == (4, 6) and len(calls) == 2
    assert all(result.request["messages"][i]["content"].rsplit("\n", 1)[0] == COMPACT for i in (4, 6))
    assert "EXACT_READ_REUSE" not in result.serialized


def test_transform_limit_is_also_a_callback_and_storage_limit(tmp_path):
    request, infos = payload([TEXT, TEXT, TEXT, "{}"])
    result, _, calls = plan(tmp_path, request, infos, policy=policy(max_transforms=1))
    assert result.changed_message_indices == (4,) and len(calls) == 1
    assert result.request["messages"][6:] == request["messages"][6:]


def test_rejected_footer_proposals_also_consume_the_bounded_attempt_limit(tmp_path):
    request, infos = payload([' { "small" : 1 } ', TEXT, "{}"])
    result, _, calls = plan(tmp_path, request, infos, policy=policy(max_transforms=1))
    assert result.request is request and len(calls) == 1


@pytest.mark.parametrize("change", ["sample", "round", "escape", "reorder", "prefix", "fragment", "wrong_hash", "missing_ref"])
def test_planner_rejects_lexical_or_presentation_changes_despite_exact_recovery(tmp_path, change):
    ccr = store(tmp_path)

    def untrusted(content, info):
        ref = ccr.stash(content, ctype="json", source=info.source_path, kind="fragment" if change == "fragment" else "root")
        compact = compress_json(content, intent="conservative")
        if change == "sample":
            compact = '{"sample":[1]}'
        elif change == "round":
            compact = compact.replace("1.2300e+04", "12300")
        elif change == "escape":
            compact = compact.replace(r"\u0041", "A")
        elif change == "reorder":
            compact = json.dumps(json.loads(compact), sort_keys=True, separators=(",", ":"))
        elif change == "wrong_hash":
            ref = "[[BR:" + "0" * 64 + ref[69:]
        text = compact + "\n" + ref
        if change == "prefix":
            text = ref + "\n" + compact
        elif change == "missing_ref":
            text = compact
        return TransformResult(text, ref)

    result, _, _ = plan(tmp_path, json_transform=untrusted, recover=lambda _: TEXT)
    assert result.status == "unchanged" and result.request == payload()[0]


@pytest.mark.parametrize("failure", ["missing", "wrong", "bytes", "normalization", "exception"])
def test_recovery_must_return_the_exact_original_utf8_bytes(tmp_path, failure):
    def recover(_):
        if failure == "exception":
            raise OSError("unavailable")
        return {"missing": None, "wrong": COMPACT, "bytes": TEXT.encode(),
                "normalization": TEXT.replace("\r\n", "\n")}[failure]
    result, _, _ = plan(tmp_path, recover=recover)
    assert result.status == "unchanged" and result.request == payload()[0]


@pytest.mark.parametrize("failure", ["none", "exception"])
def test_pipeline_root_storage_failure_returns_exact_original(tmp_path, monkeypatch, failure):
    ccr = store(tmp_path)

    def stash(*args, **kwargs):
        if failure == "exception":
            raise OSError("unavailable")
        return None

    monkeypatch.setattr(ccr, "stash", stash)
    request, infos = payload()
    result = prepare_request(request, policy(), ccr=ccr, protocol=PROTOCOL,
                             intent="overview", source_reads=infos)
    assert result.request is request and result.changed_message_indices == ()


def test_pipeline_does_not_store_unchanged_or_ineligible_results(tmp_path, monkeypatch):
    ccr = store(tmp_path)
    monkeypatch.setattr(ccr, "stash", forbidden)
    for contents in ([COMPACT, "{}"], [TEXT]):
        request, infos = payload(contents)
        result = prepare_request(request, policy(), ccr=ccr, protocol=PROTOCOL,
                                 intent="conservative", source_reads=infos)
        assert result.request is request


def test_final_footer_cost_and_whole_canonical_request_are_measured(tmp_path):
    request, infos = payload([' { "a" : 1 } ', "{}"], paths=["deep/" + "x" * 1500 + ".json", "new.json"])
    result, _, calls = plan(tmp_path, request, infos)
    assert calls and result.status == "unchanged"  # A lexically shorter payload is insufficient.
    seen = []

    def count(full_wire):
        value = json.loads(full_wire)
        assert "tools" in value and "metadata" in value
        seen.append(full_wire)
        return tokens.count_tokens(full_wire)

    result, _, _ = plan(tmp_path, count=count)
    assert result.status == "transformed" and result.serialized in seen
    assert "[[BR:" in seen[-1]


@pytest.mark.parametrize("counter", [None, lambda _: True, lambda _: -1, lambda _: 1.5])
def test_unavailable_or_invalid_counter_cannot_start_storage(tmp_path, counter):
    result, _, calls = plan(tmp_path, count=counter, json_transform=forbidden)
    assert result.status == "unchanged" and calls == []


def test_equal_reference_cost_or_byte_growth_rejects_candidate(tmp_path):
    result, _, _ = plan(tmp_path, count=lambda _: 100)
    assert result.status == "unchanged"
    request, infos = payload([' { "a" : 1 } ', "{}"])
    result, _, _ = plan(tmp_path, request, infos, count=lambda text: 1 if "[[BR:" in text else 1000)
    assert result.status == "unchanged"  # Even a favorable counter cannot excuse byte growth.


@pytest.mark.parametrize("bound", ["max_input_tokens", "max_wire_bytes", "max_output_tokens"])
def test_all_caps_still_revert_the_complete_plan(tmp_path, bound):
    result, _, _ = plan(tmp_path, policy=policy(**{bound: 1}))
    assert result.request == payload()[0] and result.changed_message_indices == ()
    assert result.reason == "cannot_safely_meet_budget"


def test_later_callback_failure_rolls_back_earlier_accepted_change(tmp_path):
    request, infos = payload([TEXT, TEXT, "{}"])
    ccr = store(tmp_path)
    calls: list[tuple[str, SourceReadInfo]] = []
    valid = transform_for(ccr, calls)

    def fails_second(content, info):
        if calls:
            raise OSError("second failed")
        return valid(content, info)

    result, _, _ = plan(tmp_path, request, infos, json_transform=fails_second)
    assert result.request is request and result.changed_message_indices == ()


def test_final_counter_exception_rolls_back_without_estimator_fallback(tmp_path):
    def count(text):
        if "[[BR:" in text:
            raise ValueError("exact measurement unavailable")
        return tokens.count_tokens(text)

    result, _, _ = plan(tmp_path, count=count)
    assert result.request == payload()[0] and result.changed_message_indices == ()


def test_bounded_random_whitespace_preserves_independent_known_token_stream(tmp_path):
    for seed in range(12):
        rng = random.Random(seed)
        lexemes = [rng.choice(("-0", "0.00", "1e+09", "1.2300E-3", "true", "null", '"a  b\\t\\u0063"'))
                   for _ in range(90)]
        compact = '{"duplicate":1,"duplicate":2,"values":[' + ",".join(lexemes) + "]}"
        text = spaced(compact, seed)
        request, infos = payload([text, "{}"])
        result, ccr, _ = plan(tmp_path, request, infos)
        assert result.status == "transformed"
        actual, reference = result.request["messages"][4]["content"].rsplit("\n", 1)
        assert actual == compact and ccr.retrieve(reference).encode() == text.encode()


def test_legacy_ids_defaults_neighbor_order_and_v4_callback_isolation():
    expected = {
        "request-policy-v1": "546fd58e95c1ec5316431c011de37a942612243f5377f562c89df892fb3e3a81",
        "request-policy-v2": "b8714485319c118d2e4c3f8beaa03a0fec50442c301511c0090d395be6cb5dc4",
        "request-policy-v3": "6da46d8f6c20b7abca6f9f4c32937ffa099935d5d9bb1fe4b1801d691fb5146c",
    }
    request, infos = payload()
    for version, suffix in expected.items():
        old = RequestPolicy(version=version, enabled=True, min_tool_chars=512)
        assert old.policy_id == version + ":" + suffix
        assert RequestPolicy.from_json(old.to_json()) == old
        assert [(p.min_tool_chars, p.keep_recent_tool_results, p.max_transforms) for p in policy_neighbors(old)] == [
            (384, 1, 4), (640, 1, 4), (512, 2, 4), (512, 1, 3), (512, 1, 5)]
        result = plan_request(request, policy=old, protocol=PROTOCOL, intent="conservative",
                              count=tokens.count_tokens, source_reads=infos, json_transform=forbidden)
        assert result.status == "unchanged"
    assert RequestPolicy().version == "request-policy-v1" and RequestPolicy().enabled is False
    assert policy().policy_id.startswith("request-policy-v4:")
