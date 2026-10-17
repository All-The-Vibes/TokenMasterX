"""Offline-only tests. Never import installed production modules or start provider."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from checks import (CONTRACT, DOCUMENTS, Script, accepted_smaller, actions, assess,
                    digest, exact_root, loads, observed, same_json, source_contract_recorded)

ANNOTATED_REF = ("[[BR:" + "a" * 64 + "|v=2;scope=" + "b" * 64
                 + ";kind=root;source=C:/owned/filesystem-contract.md;type=source;summary=;chars=23;bytes=23]]")


def action():
    return actions(Path("C:/owned/workspace"), "overview")[0]


def events(call=None, *, text="native range line", success=True):
    call = call or action()
    return [
        {"type": "tool.execution_start", "data": {
            "toolCallId": call["call_id"], "toolName": call["name"],
            "arguments": deepcopy(call["arguments"]), "turnId": "turn"}},
        {"type": "tool.execution_complete", "data": {
            "toolCallId": call["call_id"], "success": success, "rte": False,
            "turnId": "turn", "result": {"content": text},
            "toolTelemetry": {"properties": {"viewType": "file"}}}},
    ]


def body(**values):
    return {"input": [{"type": "function_call_output", "call_id": key, "output": value}
                      for key, value in values.items()]}


def test_schedule_preserves_real_native_names_and_exact_arguments():
    planned = actions(Path("C:/owned/workspace"), "overview")
    assert [a["name"] for a in planned] == ["view", "view"]
    assert planned[0]["arguments"]["view_range"] == [3, 159]
    assert planned[0]["arguments"]["forceReadLargeFiles"] is True
    assert planned[1]["arguments"]["view_range"] == [30, -1]
    script = Script(planned, "overview")
    assert script.next(body()) == planned[0]
    assert script.next(body(overview_partial="observed partial")) == planned[1]


def test_full_script_including_both_recoveries_uses_five_requests():
    script = Script(actions(Path("C:/owned"), "overview"), "overview")
    script.next(body())
    script.next(body(overview_partial="observed partial"))
    transformed = ANNOTATED_REF + "\nshort <<ccr:abcdef123456>>"
    root = script.next(body(overview_partial=transformed, overview_eof="EOF result"))
    assert root["name"] == "tokenmaster-retrieve_original"
    assert root["arguments"] == {"ref": ANNOTATED_REF, "offset": 0}
    fragment = script.next(body(overview_partial=transformed, range_root_recovery="root page"))
    assert fragment["name"] == "tokenmaster-headroom_retrieve"
    assert fragment["arguments"] == {"hash": "abcdef123456"}
    assert script.next(body(overview_partial=transformed, range_fragment_recovery="fragment page")) is None
    assert script.requests == 5
    with pytest.raises(ValueError, match="budget"):
        script.next(body())


def test_no_fragment_emission_does_not_fabricate_fragment_recovery():
    script = Script(actions(Path("C:/owned"), "overview"), "overview")
    script.next(body())
    script.next(body(overview_partial="observed partial"))
    assert script.next(body(overview_partial=ANNOTATED_REF + "\nshort"))["name"] == "tokenmaster-retrieve_original"
    assert script.next(body(overview_partial=ANNOTATED_REF + "\nshort")) is None
    assert script.fragment_called is False


def test_source_marker_not_mistaken_for_emitted_vendor_marker():
    script = Script(actions(Path("C:/owned"), "overview"), "overview")
    script.next(body())
    script.next(body(overview_partial="original hash=abcdef123456"))
    script.next(body(overview_partial=ANNOTATED_REF + "\nshort hash=abcdef123456"))
    assert script.fragment is None


def test_exact_status_session_finishes_in_three_requests():
    planned = actions(Path("C:/owned"), "exact")
    script = Script(planned, "exact")
    assert script.next(body()) == planned[0]
    assert script.next(body(exact_partial="source")) == planned[1]
    assert planned[1]["arguments"]["path"].endswith("missing-status-control.md")
    assert script.next(body(exact_partial="source", exact_missing="not found")) is None
    assert script.requests == 3


def test_no_accepted_root_means_no_recovery_retries_or_whole_file_fallback():
    script = Script(actions(Path("C:/owned"), "overview"), "overview")
    script.next(body())
    script.next(body(overview_partial="native"))
    assert script.next(body(overview_partial="native", overview_eof="native EOF")) is None
    assert len(script.emitted) == 2


def test_native_observation_is_exact_and_nonempty():
    assert observed(events(text="3. original\r\n"), action()) == "3. original\r\n"


@pytest.mark.parametrize("mutation", ["name", "arguments", "boolean_integer", "float_range",
                                     "status", "turn", "directory", "empty"])
def test_native_binding_rejects_mismatched_source_authority(mutation):
    values = events()
    if mutation == "name":
        values[0]["data"]["toolName"] = "read_file"
    elif mutation == "arguments":
        values[0]["data"]["arguments"]["view_range"] = [1, -1]
    elif mutation == "boolean_integer":
        values[0]["data"]["arguments"]["forceReadLargeFiles"] = 1
    elif mutation == "float_range":
        values[0]["data"]["arguments"]["view_range"] = [3.0, 159]
    elif mutation == "status":
        values[1]["data"]["success"] = False
    elif mutation == "turn":
        values[1]["data"]["turnId"] = "foreign"
    elif mutation == "directory":
        values[1]["data"]["toolTelemetry"]["properties"]["viewType"] = "directory"
    else:
        values[1]["data"]["result"]["content"] = ""
    with pytest.raises(ValueError):
        observed(values, action())


def test_canonical_json_is_order_independent_but_type_strict():
    assert same_json({"a": True, "b": [1, -1]}, {"b": [1, -1], "a": True})
    assert not same_json({"a": True}, {"a": 1})
    assert not same_json({"a": [1, -1]}, {"a": [1.0, -1]})


def test_root_oracle_is_observed_native_text_not_fresh_file_text():
    original = "3. alpha\n4. beta\n"
    assert exact_root(json.dumps({"ok": True, "complete": True, "content": original}), original)
    assert not exact_root(json.dumps({"ok": True, "complete": True, "content": "alpha\nbeta\n"}), original)
    assert not exact_root(json.dumps({"ok": True, "complete": False, "content": original}), original)


def evidence():
    wire = '{"input":[]}'
    metric = {"reference_tokens": 5, "utf8_bytes": len(wire), "wire_sha256": digest(wire.encode())}
    prep = {"changed_messages": [1], "wire_sha256": metric["wire_sha256"], "input_composition": {
        "original": {"reference_tokens": 10, "utf8_bytes": 100}, "final": metric}}
    capture = {"input": wire, "ok": True, "complete": True}
    return prep, capture, {"body": loads(wire)}


def test_smaller_complete_wire_requires_matching_accepted_capture():
    assert accepted_smaller(*evidence())


@pytest.mark.parametrize("mutation", ["failed", "incomplete", "same_tokens", "same_bytes", "wrong_digest", "wrong_upstream", "unchanged"])
def test_small_inner_projection_or_failed_wire_is_not_acceptance(mutation):
    prep, capture, request = evidence()
    if mutation == "failed":
        capture["ok"] = False
    elif mutation == "incomplete":
        capture["complete"] = False
    elif mutation == "same_tokens":
        prep["input_composition"]["final"]["reference_tokens"] = 10
    elif mutation == "same_bytes":
        prep["input_composition"]["original"]["utf8_bytes"] = len(capture["input"])
    elif mutation == "wrong_digest":
        prep["wire_sha256"] = "wrong"
    elif mutation == "wrong_upstream":
        request["body"] = {"input": ["different"]}
    else:
        prep["changed_messages"] = []
    assert not accepted_smaller(prep, capture, request)


def test_unrecorded_contract_and_missing_evidence_do_not_pass():
    assert source_contract_recorded({"native_executor": {"source_contract": CONTRACT}})
    assert not source_contract_recorded({"source_contract": "native-full-view-v1"})
    with pytest.raises(ValueError, match="native_not_complete"):
        assess("overview", [], [], [], {}, [], [], [], [], [], {})


def test_no_subprocess_runtime_wrapper_and_no_top_level_production_imports():
    source = Path(__file__).with_name("qualify_ranges.py").read_text("utf-8")
    tree = ast.parse(source)
    assert "subprocess" not in source
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("brainspace")
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "run_native"]
    assert len(calls) == 1
    assert any(k.arg == "source_contract" and isinstance(k.value, ast.Name)
               and k.value.id == "CONTRACT" for k in calls[0].keywords)


def test_pinned_public_sources_are_original_small_complete_documents():
    root = Path(__file__).resolve().parents[4]
    source = root / "docs/research/2026-10-04-parity/headroom/source/headroom-1cf496612e781ef8d67ff87ee4f78037492f0bc7/wiki"
    for name, expected in DOCUMENTS.items():
        assert digest((source / name).read_bytes()) == expected


@pytest.mark.parametrize("text", ['{"x":1,"x":1}', '{"x":NaN}'])
def test_malformed_evidence_json_is_rejected(text):
    with pytest.raises(ValueError):
        loads(text)


def overview_evidence():
    """Tiny synthetic checker unit data, NOT native-run or measurement evidence."""
    planned = actions(Path("C:/owned"), "overview")
    root = {"name": "tokenmaster-retrieve_original", "call_id": "range_root_recovery",
            "arguments": {"ref": ANNOTATED_REF, "offset": 0}, "namespace": None}
    partial, eof = "3. exact native partial\n", "30. exact native EOF\n"
    page = json.dumps({"ok": True, "complete": True, "content": partial})
    contents = [[], [("overview_partial", partial)],
                [("overview_partial", partial), ("overview_eof", eof)],
                [("overview_partial", partial), ("overview_eof", eof), ("range_root_recovery", page)]]
    preparations, captures, requests = [], [], []
    for i, entries in enumerate(contents):
        before = [{"role": "tool", "tool_call_id": key, "content": value} for key, value in entries]
        after = deepcopy(before)
        if i >= 2:
            after[0]["content"] = ANNOTATED_REF + "\nshort"
        request = body(**{m["tool_call_id"]: m["content"] for m in after})
        wire = json.dumps(request)
        metric = {"reference_tokens": 5, "utf8_bytes": len(wire), "wire_sha256": digest(wire.encode())}
        preparations.append({
            "original": {"messages": before}, "prepared": {"messages": after},
            "changed_messages": [0] if i >= 2 else [], "wire_sha256": metric["wire_sha256"],
            "input_composition": {"original": {"reference_tokens": 10, "utf8_bytes": len(wire) + 50},
                                  "final": metric},
        })
        captures.append({"ok": True, "complete": True, "input": wire})
        requests.append({"body": request})
    process = {key: True for key in ("io_complete", "process_tree_settled", "reader_threads_stopped",
                                    "queue_settled", "stdout_eof", "stderr_eof", "secret_config_removed")}
    process.update(errors=[], stdout="")
    native = {"complete": True, "source_contract": CONTRACT,
              "version": "copilot-native-runtime-view-result-v2",
              "native_executor": {"source_contract": CONTRACT}, "native_process": process,
              "runtime": {"model_calls": 4, "source_read_receipts": 2,
                          "component": {"headroom_executed": True}}}
    manifest = {"strategy": "native-documents-v1",
                "vendor_commit": "1cf496612e781ef8d67ff87ee4f78037492f0bc7",
                "compress_config": {"compress_system_messages": False}}
    rpc = [{"request": {"id": "1", "op": "compress_documents", "eligible_indices": [0],
                        "messages": preparations[2]["original"]["messages"]}}]
    received = [{"response": {"id": "1", "result": {
        "strategy_manifest": manifest, "messages": preparations[2]["prepared"]["messages"]}}}]
    ev = events(planned[0], text=partial) + events(planned[1], text=eof) + events(root, text=page)
    return {"intent": "overview", "planned": planned, "emitted": [*planned, root],
            "requests": requests, "native": native, "preparations": preparations,
            "captures": captures, "events": ev, "rpc": rpc, "received": received,
            "cleanup": {"complete": True}}


def test_complete_evidence_chain_passes_without_claiming_unemitted_fragment():
    result = assess(**overview_evidence())
    assert result["passed"]
    assert result["root_exact_observed_range"]
    assert result["fragment_recovery"] == "not_emitted_not_claimed"


@pytest.mark.parametrize("mutation", [
    "no_pipeline", "empty_eligible", "not_settled", "legacy_contract",
    "newest_changed", "original_is_fresh_file", "whole_file_root", "fragment_without_recovery",
])
def test_complete_chain_rejects_each_missing_mechanism(mutation):
    data = overview_evidence()
    if mutation == "no_pipeline":
        data["rpc"] = []
    elif mutation == "empty_eligible":
        data["rpc"][0]["request"]["eligible_indices"] = []
    elif mutation == "not_settled":
        data["cleanup"]["complete"] = False
    elif mutation == "legacy_contract":
        data["native"]["source_contract"] = "native-full-view-v1"
    elif mutation == "newest_changed":
        data["preparations"][2]["prepared"]["messages"][1]["content"] = "wrong"
    elif mutation == "original_is_fresh_file":
        data["preparations"][2]["original"]["messages"][0]["content"] = "unformatted whole file"
    elif mutation == "whole_file_root":
        page = json.dumps({"ok": True, "complete": True, "content": "fresh whole-file contents"})
        data["requests"][-1]["body"]["input"][-1]["output"] = page
    else:
        data["preparations"][2]["prepared"]["messages"][0]["content"] += " <<ccr:abcdef123456>>"
    with pytest.raises(ValueError):
        assess(**data)


def fragment_evidence():
    data = overview_evidence()
    fragment = {"name": "tokenmaster-headroom_retrieve", "call_id": "range_fragment_recovery",
                "arguments": {"hash": "abcdef123456"}, "namespace": None}
    fragment_text = json.dumps({"hash": "abcdef123456", "original_content": "stored upstream fragment"})
    data["emitted"].append(fragment)
    data["events"] += events(fragment, text=fragment_text)
    final = deepcopy(data["preparations"][-1])
    for key in ("original", "prepared"):
        final[key]["messages"].append({"role": "tool", "tool_call_id": "range_fragment_recovery",
                                       "content": fragment_text})
    data["preparations"].append(final)
    data["captures"].append({})
    data["requests"].append({})
    for i in range(2, 5):
        prep = data["preparations"][i]
        prep["prepared"]["messages"][0]["content"] = ANNOTATED_REF + "\nshort <<ccr:abcdef123456>>"
        request = body(**{m["tool_call_id"]: m["content"] for m in prep["prepared"]["messages"]})
        wire = json.dumps(request)
        data["requests"][i] = {"body": request}
        data["captures"][i] = {"input": wire, "ok": True, "complete": True}
        metric = {"reference_tokens": 5, "utf8_bytes": len(wire), "wire_sha256": digest(wire.encode())}
        prep["wire_sha256"] = metric["wire_sha256"]
        prep["input_composition"] = {"original": {"reference_tokens": 10, "utf8_bytes": len(wire) + 50},
                                    "final": metric}
    data["native"]["runtime"]["model_calls"] = 5
    data["native"]["runtime"]["component"]["headroom"] = {"recoveries": {
        "abcdef123456": "stored upstream fragment"}}
    data["received"].append({"response": {"id": "2", "result": {
        "tool_call_id": "range_fragment_recovery", "content": fragment_text}}})
    return data


def test_emitted_fragment_requires_actual_worker_and_native_recovery_delivery():
    result = assess(**fragment_evidence())
    assert result["primary_requests"] == 5
    assert result["fragment_recovery"] == "verified_first_emitted"


def test_fragment_delivery_without_matching_worker_receipt_fails():
    data = fragment_evidence()
    data["received"].pop()
    with pytest.raises(ValueError, match="vendor_recovery_not_exercised"):
        assess(**data)


def exact_evidence():
    data = overview_evidence()
    planned = actions(Path("C:/owned"), "exact")
    partial, error = "3. exact native partial\n", "File not found"
    data.update(intent="exact", planned=planned, emitted=planned, rpc=[], received=[], cleanup={},
                events=events(planned[0], text=partial) + events(planned[1], text=error, success=False))
    contents = [[], [("exact_partial", partial)],
                [("exact_partial", partial), ("exact_missing", error)]]
    data["preparations"], data["captures"], data["requests"] = [], [], []
    for entries in contents:
        messages = [{"role": "tool", "tool_call_id": k, "content": v} for k, v in entries]
        request = body(**dict(entries))
        data["preparations"].append({"original": {"messages": messages}, "prepared": {"messages": deepcopy(messages)},
                                     "changed_messages": []})
        data["requests"].append({"body": request})
        data["captures"].append({"input": json.dumps(request), "ok": True, "complete": True})
    data["native"]["runtime"].update(model_calls=3, source_read_receipts=1)
    return data


def test_exact_old_result_and_genuine_failure_control_pass_without_pipeline():
    data = exact_evidence()
    assert assess(**data)["controls"] == ["exact", "status"]


def failed_text_evidence(shape, delivered=None):
    data = exact_evidence()
    text = "Missing file: café.md\r\nNo such file"
    completion = data["events"][-1]["data"]
    if shape == "plain":
        completion["result"] = {"content": text, "detailedContent": "native diagnostic"}
    elif shape == "omitted":
        completion.pop("result")
    else:
        completion["result"] = None
    completion["error"] = {"message": text}
    delivered = text if delivered is None else delivered
    for prep in data["preparations"]:
        for key in ("original", "prepared"):
            for message in prep[key]["messages"]:
                if message["tool_call_id"] == "exact_missing":
                    message["content"] = delivered
    for request, capture in zip(data["requests"], data["captures"]):
        for item in request["body"]["input"]:
            if item["call_id"] == "exact_missing":
                item["output"] = delivered
        capture["input"] = json.dumps(request["body"])
    return data, text


@pytest.mark.parametrize("shape", ["omitted", "null"])
def test_failed_view_observed_text_uses_literal_error_message(shape):
    data, text = failed_text_evidence(shape)
    assert observed(data["events"], data["planned"][1], success=False) == text
    assert data["events"][-1]["data"]["success"] is False


@pytest.mark.parametrize("shape", ["omitted", "null"])
def test_error_only_failed_history_passes_exact_binding_without_source_authority(shape):
    data, _ = failed_text_evidence(shape)
    assert assess(**data)["controls"] == ["exact", "status"]
    assert data["native"]["runtime"]["source_read_receipts"] == 1  # Only the successful partial.
    data["native"]["runtime"]["source_read_receipts"] = 2
    with pytest.raises(ValueError, match="unexpected_ranged_or_failure_source_receipts"):
        assess(**data)


@pytest.mark.parametrize("shape", ["plain", "omitted", "null"])
@pytest.mark.parametrize("mutation", ["changed", "prefixed"])
def test_altered_or_prefixed_error_only_native_delivery_is_rejected(shape, mutation):
    _, literal = failed_text_evidence(shape)
    delivered = "A different native failure" if mutation == "changed" else "Error: " + literal
    data, _ = failed_text_evidence(shape, delivered=delivered)
    # Preparation, capture and upstream agree with each other. Only native
    # completion evidence exposes this alteration; no other mismatch may mask it.
    with pytest.raises(ValueError, match="ingress_not_observed_result"):
        assess(**data)


@pytest.mark.parametrize("representation", [
    {}, {"result": None}, {"error": None}, {"error": "plain error"},
    {"error": {"message": None}}, {"error": {"message": 1}},
    {"result": {}}, {"result": []}, {"result": False}, {"result": "not a result"},
    {"result": {"content": None}}, {"result": {"content": 123}},
    {"result": {"content": "text", "detailedContent": None}},
    {"result": {"content": "text", "extra": "unknown"}},
    {"result": {"content": "text", "contents": [{"type": "text", "text": "text"}]}},
])
def test_missing_or_unsupported_failed_result_is_rejected(representation):
    call = actions(Path("C:/owned"), "exact")[1]
    values = events(call, success=False)
    values[-1]["data"].pop("result")
    values[-1]["data"].update(deepcopy(representation))
    with pytest.raises(ValueError):
        observed(values, call, success=False)


@pytest.mark.parametrize("result", [{}, [], False, "bad", {"content": None}, {"content": "text", "extra": True}])
def test_malformed_nonnull_failed_result_cannot_fall_back_to_error_message(result):
    call = actions(Path("C:/owned"), "exact")[1]
    values = events(call, success=False)
    values[-1]["data"].update(result=result, error={"message": "valid literal fallback"})
    with pytest.raises(ValueError):
        observed(values, call, success=False)


@pytest.mark.parametrize("text", ["", "  exact \r\n failure\t", "Error: already in native message"])
def test_failed_text_is_never_trimmed_or_prefixed(text):
    call = actions(Path("C:/owned"), "exact")[1]
    values = events(call, success=False)
    values[-1]["data"].update(result=None, error={"message": text})
    assert observed(values, call, success=False) == text


def test_plain_failed_result_content_takes_precedence_over_other_error_message():
    call = actions(Path("C:/owned"), "exact")[1]
    values = events(call, text="original result.content", success=False)
    values[-1]["data"]["error"] = {"message": "do not substitute this"}
    assert observed(values, call, success=False) == "original result.content"


def test_successful_error_only_result_is_not_reinterpreted_as_failure_text():
    values = events()
    values[-1]["data"].update(result=None, error={"message": "not a successful result"})
    with pytest.raises(ValueError):
        observed(values, action(), success=True)


@pytest.mark.parametrize("name", ["tokenmaster-retrieve_original", "tokenmaster-headroom_retrieve"])
def test_successful_native_mcp_rendering_keeps_exact_content(name):
    arguments = {"ref": "fixed", "offset": 0} if name == "tokenmaster-retrieve_original" else {"hash": "abcdef123456"}
    call = {"name": name, "call_id": "successful_recovery", "arguments": arguments}
    content = '{"ok":true,"content":"native\\r\\ntext"}'
    values = events(call, text=content)
    values[-1]["data"]["result"].update(
        detailedContent="native diagnostic rendering",
        contents=[{"type": "text", "text": '{ "ok": true, "content": "native\\r\\ntext" }'}],
    )
    assert observed(values, call) == content
