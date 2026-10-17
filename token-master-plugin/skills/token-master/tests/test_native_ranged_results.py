"""Exact observed-result provenance; synthetic events/replies, no native process."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from brainspace.native_events import NativeEventCollector
from test_native_events import call, completed, events, request
from test_native_runtime import (
    body, call as native_call, done, fake_sender, runtime, start,
)


LEGACY = "native-full-view-v1"
RANGED = "native-view-result-v2"
PARTIAL = "L7: a partial document result\r\nL8: 雪, denied, and exact spacing  \n"


@pytest.mark.parametrize("arguments", [
    {}, {"view_range": [1, 1]}, {"view_range": [7, 11]},
    {"view_range": [3, -1]}, {"view_range": [1, 9007199254740991]},
    {"forceReadLargeFiles": True}, {"forceReadLargeFiles": False},
    {"view_range": [2, 9], "forceReadLargeFiles": False},
])
def test_v2_binds_complete_observed_result_without_reading_file(
    tmp_path, monkeypatch, arguments,
):
    collector = NativeEventCollector(
        workspace=tmp_path, expected_model="gpt-6-astra", source_contract=RANGED,
    )
    item = call("notes.md", **arguments)
    collector.register_expected_calls([item], model="gpt-6-astra")
    original = deepcopy(item)

    def forbidden(*args, **kwargs):
        pytest.fail("native source provenance must not reread a source file")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", forbidden)
        patch.setattr(Path, "read_text", forbidden)
        patch.setattr(Path, "read_bytes", forbidden)
        for event in events(item, PARTIAL):
            collector.observe(event)
        receipts = collector.source_reads(request(item, PARTIAL))
    assert item == original
    assert len(receipts) == 1
    assert receipts[0].source_path == "notes.md"
    assert receipts[0].content_sha256 == hashlib.sha256(PARTIAL.encode()).hexdigest()
    assert receipts[0].matches(request(item, PARTIAL)["messages"][-1], item)
    assert collector.source_reads(request(item, PARTIAL.strip())) == ()
    summary = collector.close()
    assert summary["coverage_complete"]
    assert summary["source_contract"] == RANGED
    assert summary["source_scope"] == "exact-observed-tool-result-not-full-file"


def test_default_contract_still_excludes_ranged_views(tmp_path):
    collector, item = completed(tmp_path, call(view_range=[1, 100]))
    assert collector.source_reads(request(item)) == ()
    assert collector.summary()["ineligibility_notes"] == {"ranged_view": 1}
    assert collector.summary()["coverage_complete"]


@pytest.mark.parametrize("arguments", [
    {"view_range": value} for value in (
        None, [], [1], [1, 2, 3], [0, 2], [-1, -1], [3, 2], [1, -2],
        [True, 5], [1, False], [1, 2.0], ["1", 3],
        [9007199254740992, -1], [1, 9007199254740992],
    )
] + [
    {"forceReadLargeFiles": value} for value in (None, 0, 1, "true", [], {})
] + [{"unknown": "not a native view argument"}])
def test_v2_invalid_arguments_never_become_source_authority(tmp_path, arguments):
    collector, item = completed(
        tmp_path, call("notes.md", **arguments), source_contract=RANGED,
    )
    assert collector.source_reads(request(item)) == ()
    assert not collector.summary()["coverage_complete"]
    assert collector.summary()["diagnostics"]["ineligible_view"] == 1


@pytest.mark.parametrize("change", ["directory", "foreign", "failure", "unknown", "poison"])
def test_v2_keeps_non_source_and_execution_protections(tmp_path, change):
    collector = NativeEventCollector(
        workspace=tmp_path, expected_model="gpt-6-astra", source_contract=RANGED,
    )
    item = call("../foreign.md" if change == "foreign" else "notes.md", view_range=[2, -1])
    collector.register_expected_calls([item], model="gpt-6-astra")
    begin, complete = events(item, PARTIAL)
    if change == "directory":
        complete["data"]["toolTelemetry"]["properties"]["viewType"] = "directory"
    if change == "failure":
        complete["data"]["success"] = False
    if change == "unknown":
        complete["data"]["status"] = "unknown"
    collector.observe(begin)
    collector.observe(complete)
    if change == "poison":
        changed = deepcopy(complete)
        changed["data"]["result"]["content"] = "conflicting replay"
        collector.observe(changed)
    assert collector.source_reads(request(item, PARTIAL)) == ()
    if change == "directory":
        assert collector.summary()["coverage_complete"]
        assert collector.summary()["ineligibility_notes"] == {"directory_view": 1}


@pytest.mark.parametrize("changed", [
    {"view_range": [3, 8]}, {"view_range": [2, -1], "forceReadLargeFiles": True},
    {"view_range": [2, -1], "path": "different.md"},
])
def test_v2_receipt_requires_exact_issued_arguments(tmp_path, changed):
    collector, item = completed(
        tmp_path, call("notes.md", view_range=[2, -1]), source_contract=RANGED,
    )
    assert collector.source_reads(request(item))
    modified = deepcopy(item)
    modified["function"]["arguments"] = json.dumps({"path": "notes.md", **changed})
    assert collector.source_reads(request(modified)) == ()


@pytest.mark.parametrize("contract", [None, True, "", "native-view-result-v1", [], {}])
def test_invalid_source_contract_rejects_before_output_io(tmp_path, contract):
    with pytest.raises(ValueError, match="invalid_native_source_contract"):
        runtime(tmp_path, source_contract=contract)
    assert not (tmp_path / "output").exists()


def test_explicit_contract_is_bound_to_native_harness_and_profile(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    legacy = runtime(first)
    ranged = runtime(second, source_contract=RANGED)
    try:
        assert legacy.runtime.harness_id == "copilot-native-runtime-v1"
        assert ranged.runtime.harness_id == "copilot-native-runtime-view-result-v2"
        assert legacy.runtime.profile_id != ranged.runtime.profile_id
        assert legacy.runtime.policy_id == ranged.runtime.policy_id
        assert ranged.events.source_contract == RANGED
        with pytest.raises(AttributeError):
            ranged.events.source_contract = LEGACY
    finally:
        legacy.finish(native_exit_code=0)
        ranged.finish(native_exit_code=0)


@pytest.mark.parametrize("mutation", ["new_range", "new_flag", "tool_name"])
def test_cached_receipt_cannot_authorize_mutated_historical_call(
    tmp_path, monkeypatch, mutation,
):
    native = runtime(tmp_path)
    item = native_call("view", {"path": str(native.workspace / "notes.md")})
    sent = fake_sender(monkeypatch, [[item], [], []])
    first = body()
    assert native.invoke(first).ok
    native.observe_event(start(item))
    native.observe_event(done(item, PARTIAL))
    second = deepcopy(first)
    second["input"] += [
        item, {"type": "function_call_output", "call_id": item["call_id"], "output": PARTIAL},
    ]
    assert native.invoke(second).ok
    assert len(native.runtime.source_reads) == 1
    third = deepcopy(second)
    historic = third["input"][-2]
    if mutation == "tool_name":
        historic["name"] = "tokenmaster-headroom_retrieve"
    else:
        arguments = json.loads(historic["arguments"])
        arguments.update({"view_range": [1, 3]} if mutation == "new_range"
                         else {"forceReadLargeFiles": True})
        historic["arguments"] = json.dumps(arguments)
    with pytest.raises(ValueError, match="native_history_call_mismatch|original_history_changed"):
        native.invoke(third)
    result = native.finish(native_exit_code=1)
    assert len(sent) == 2
    assert result["runtime"]["model_calls"] == 2
    assert not result["complete"]


@pytest.mark.parametrize("mutation", ["arguments", "name", "content"])
def test_first_history_result_must_match_issued_call_and_native_execution(
    tmp_path, monkeypatch, mutation,
):
    native = runtime(tmp_path)
    item = native_call("view", {"path": str(native.workspace / "notes.md")})
    sent = fake_sender(monkeypatch, [[item], []])
    first = body()
    native.invoke(first)
    native.observe_event(start(item))
    native.observe_event(done(item, PARTIAL))
    changed = deepcopy(item)
    output = PARTIAL
    if mutation == "arguments":
        changed["arguments"] = json.dumps({
            "path": str(native.workspace / "notes.md"), "view_range": [2, -1],
        })
    elif mutation == "name":
        changed["name"] = "tokenmaster-headroom_retrieve"
    else:
        output += "not observed by the executor"
    second = deepcopy(first)
    second["input"] += [
        changed, {"type": "function_call_output", "call_id": item["call_id"], "output": output},
    ]
    with pytest.raises(ValueError, match="native_history_(call|result)_mismatch"):
        native.invoke(second)
    result = native.finish(native_exit_code=1)
    assert len(sent) == 1
    assert result["runtime"]["model_calls"] == 1
    assert not result["complete"]


def test_first_history_call_accepts_semantically_identical_json_formatting(tmp_path, monkeypatch):
    native = runtime(tmp_path)
    item = native_call("view", {"path": str(native.workspace / "notes.md")})
    sent = fake_sender(monkeypatch, [[item], []])
    native.invoke(body())
    native.observe_event(start(item))
    native.observe_event(done(item, PARTIAL))
    reformatted = deepcopy(item)
    reformatted["arguments"] = json.dumps(json.loads(item["arguments"]), indent=4)
    second = body()
    second["input"] += [
        reformatted, {"type": "function_call_output", "call_id": item["call_id"], "output": PARTIAL},
    ]
    assert native.invoke(second).ok
    assert native.finish(native_exit_code=0)["complete"]
    assert len(sent) == 2


@pytest.mark.parametrize("success,view_type", [(False, "file"), (True, "directory")])
def test_bound_failed_or_directory_output_is_history_not_source_authority(
    tmp_path, monkeypatch, success, view_type,
):
    native = runtime(tmp_path)
    item = native_call("view", {"path": str(native.workspace / "subdirectory")})
    sent = fake_sender(monkeypatch, [[item], []])
    native.invoke(body())
    native.observe_event(start(item))
    event = done(item, PARTIAL, success=success)
    event["data"]["toolTelemetry"]["properties"]["viewType"] = view_type
    native.observe_event(event)
    second = body()
    second["input"] += [
        item, {"type": "function_call_output", "call_id": item["call_id"], "output": PARTIAL},
    ]
    assert native.invoke(second).ok
    result = native.finish(native_exit_code=0)
    assert result["complete"]
    assert result["runtime"]["source_read_receipts"] == 0
    assert result["native_executor"]["counts"]["success" if success else "failure"] == 1
    assert len(sent) == 2


@pytest.mark.parametrize("output_matches", [True, False])
def test_native_error_message_is_literal_failed_history_not_a_source(
    tmp_path, monkeypatch, output_matches,
):
    native = runtime(tmp_path)
    item = native_call("view", {"path": str(native.workspace / "missing.md")})
    sent = fake_sender(monkeypatch, [[item], []])
    native.invoke(body())
    native.observe_event(start(item))
    event = done(item, "", success=False)
    event["data"].pop("result")
    event["data"]["error"] = {"code": "failure", "message": "File does not exist: missing.md"}
    native.observe_event(event)
    second = body()
    text = event["data"]["error"]["message"]
    second["input"] += [
        item, {"type": "function_call_output", "call_id": item["call_id"],
               "output": text if output_matches else "Error: " + text},
    ]
    if output_matches:
        assert native.invoke(second).ok
    else:
        with pytest.raises(ValueError, match="native_history_result_mismatch"):
            native.invoke(second)
    result = native.finish(native_exit_code=0 if output_matches else 1)
    assert result["complete"] is output_matches
    assert result["runtime"]["source_read_receipts"] == 0
    assert result["native_executor"]["counts"]["failure"] == 1
    assert len(sent) == (2 if output_matches else 1)


@pytest.mark.parametrize("mutation", [
    None, "wrong_path", "prefix", "punctuation", "literal_only", "wrong_code",
    "wrong_message", "wrong_command", "wrong_view_type", "resolved_path",
])
def test_pinned_missing_path_renderer_matches_exact_failure_without_source_receipt(
    tmp_path, monkeypatch, mutation,
):
    native = runtime(tmp_path, source_contract=RANGED)
    path = str(native.workspace / "missing-status-control.md")
    item = native_call("view", {"path": path, "view_range": [1, -1]})
    sent = fake_sender(monkeypatch, [[item], []])
    native.invoke(body())
    native.observe_event(start(item))
    event = done(item, "", success=False)
    event["data"].pop("result")
    event["data"]["error"] = {"message": "Path does not exist", "code": "failure"}
    properties = {"command": "view", "viewType": "unknown", "resolvedPathAgainstCwd": "false"}
    event["data"]["toolTelemetry"] = {"properties": properties}
    if mutation == "wrong_code":
        event["data"]["error"]["code"] = "different"
    elif mutation == "wrong_message":
        event["data"]["error"]["message"] = "Another failure"
    elif mutation in ("wrong_command", "wrong_view_type", "resolved_path"):
        properties[{"wrong_command": "command", "wrong_view_type": "viewType",
                    "resolved_path": "resolvedPathAgainstCwd"}[mutation]] = {
                        "wrong_command": "other", "wrong_view_type": "file", "resolved_path": "true",
                    }[mutation]
    native.observe_event(event)
    output = f"Path {path} does not exist. Please provide a valid path."
    if mutation == "wrong_path":
        output = output.replace("missing-status-control.md", "different.md")
    elif mutation == "prefix":
        output = "Error: " + output
    elif mutation == "punctuation":
        output = output[:-1]
    elif mutation == "literal_only":
        output = "Path does not exist"
    second = body()
    second["input"] += [
        item, {"type": "function_call_output", "call_id": item["call_id"], "output": output},
    ]
    if mutation is None:
        assert native.invoke(second).ok
    else:
        with pytest.raises(ValueError, match="native_history_result_mismatch"):
            native.invoke(second)
    result = native.finish(native_exit_code=0 if mutation is None else 1)
    assert result["complete"] is (mutation is None)
    assert result["native_executor"]["counts"]["failure"] == 1
    assert result["runtime"]["source_read_receipts"] == 0
    assert result["runtime"]["transformations"] == 0
    assert len(sent) == (2 if mutation is None else 1)
    if mutation is None:
        journal = [json.loads(line) for line in
                   (native.output / "native-executor.jsonl").read_text("utf-8").splitlines()]
        assert any(row.get("error_rendering") == "native-view-missing-path-1.0.95-v1"
                   for row in journal)


@pytest.mark.parametrize("target", ["outside", "parent", "relative", "alternate_stream"])
def test_native_view_rejects_foreign_lexical_paths_before_filesystem_metadata(
    tmp_path, monkeypatch, target,
):
    from brainspace import native_runtime as module
    native = runtime(tmp_path)
    path = {
        "outside": str(tmp_path / "outside.md"),
        "parent": str(native.workspace / ".." / "outside.md"),
        "relative": "notes.md",
        "alternate_stream": str(native.workspace / "notes.md") + ":hidden",
    }[target]
    item = native_call("view", {"path": path})
    sent = fake_sender(monkeypatch, [[item]])
    with monkeypatch.context() as patch:
        patch.setattr(module, "safe_root", lambda *_: pytest.fail(
            "authorization must reject this path before filesystem metadata"))
        reply = native.invoke(body())
    assert not reply.ok and reply.reason == "native_output_rejected"
    assert len(sent) == 1  # The model reply is retained, but its tool is not forwarded.
    assert native.events.summary()["calls"] == {}
    native.finish(native_exit_code=1)


def test_native_v2_collects_partial_result_and_preserves_range_on_wire(tmp_path, monkeypatch):
    native = runtime(tmp_path, source_contract=RANGED)
    item = native_call("view", {
        "path": str(native.workspace / "notes.md"), "view_range": [7, 8],
        "forceReadLargeFiles": False,
    })
    sent = fake_sender(monkeypatch, [[item], []])
    first = body()
    native.invoke(first)
    native.observe_event(start(item))
    native.observe_event(done(item, PARTIAL))
    second = deepcopy(first)
    second["input"] += [
        item, {"type": "function_call_output", "call_id": item["call_id"], "output": PARTIAL},
    ]
    native.invoke(second)
    result = native.finish(native_exit_code=0)
    assert result["complete"]
    assert result["source_contract"] == RANGED
    assert result["runtime"]["source_read_receipts"] == 1
    assert sent[1]["input"] == second["input"]


@pytest.mark.parametrize("guard", [
    "overview", "exact", "edit", "debug", "code", "failure", "legacy",
    "unclosed_fence", "closing_fence_only", "changed_fenced_code",
    "compact", "compact_expansion",
])
def test_native_range_reaches_shared_document_guards_and_exact_observed_root(
    tmp_path, monkeypatch, guard,
):
    from brainspace import headroom, tokens
    from brainspace.runtime_policy import RuntimePolicy
    from brainspace.runtime_resources import RuntimeResources

    state = {"starts": 0, "requests": []}

    class Backend:
        def __init__(self, directory, **options):
            directory.mkdir()

        def start(self):
            state["starts"] += 1
            return {"ready": True}

        def prepare(self, value, **controls):
            state["requests"].append((deepcopy(value), deepcopy(controls)))
            messages = deepcopy(value["messages"])
            for index in controls["eligible_indices"]:
                messages[index]["content"] = (
                    messages[index]["content"] + "\nAn expanding proposal must not be accepted."
                    if guard == "compact_expansion" else "Short observed document projection."
                )
            return {"model": value["model"], "messages": messages}

        def finish(self):
            return {}

        def close(self):
            return {"container_removed": True}

    monkeypatch.setattr(headroom, "HeadroomContainer", Backend)
    monkeypatch.setattr(RuntimeResources, "resolve", lambda self, policy: {
        "ponytail": None, "headroom_options": {
            "cache": tmp_path / "cache", "assets": tmp_path / "assets",
            "docker_config": None, "strategy": "native-documents-v1",
        },
    })
    options = {"headroom_root_reference_style": "compact-root-v1"} \
        if guard.startswith("compact") else {}
    policy = RuntimePolicy(
        backend="headroom", headroom_strategy="native-documents-v1",
        require_nonexpanding_input=True, **options,
    )
    native = runtime(
        tmp_path, policy=policy, source_contract=LEGACY if guard == "legacy" else RANGED,
        intent=guard if guard in ("exact", "edit", "debug") else "overview",
    )
    observed = ("Document fragment: Unicode 雪 and literal spacing are observed bytes.  \r\n" * 80)
    if guard == "unclosed_fence":
        observed += "\n```python\nanswer = 42\n"
    elif guard == "closing_fence_only":
        observed += "\n```\n"
    elif guard == "changed_fenced_code":
        observed += "\n```python\nanswer = 42\n```\n"
    old = native_call("view", {
        "path": str(native.workspace / ("source.py" if guard == "code" else "notes.md")),
        "view_range": [7, 86],
    }, "old-range")
    latest = native_call("view", {
        "path": str(native.workspace / "latest.md"), "view_range": [2, -1],
    }, "latest-range")
    sent = fake_sender(monkeypatch, [[old], [latest], []])
    first = body()
    native.invoke(first)
    native.observe_event(start(old))
    native.observe_event(done(old, observed, success=guard != "failure"))
    second = deepcopy(first)
    second["input"] += [
        old, {"type": "function_call_output", "call_id": old["call_id"], "output": observed},
    ]
    native.invoke(second)
    assert state["starts"] == 0  # A valid ranged source is still the newest result.
    native.observe_event(start(latest))
    native.observe_event(done(latest, "Newest remains exact."))
    third = deepcopy(second)
    third["input"] += [
        latest, {"type": "function_call_output", "call_id": latest["call_id"],
                 "output": "Newest remains exact."},
    ]
    native.invoke(third)
    assert sent[-1]["input"][:2] == first["input"]
    assert sent[-1]["input"][-1] == third["input"][-1]
    assert sent[-1]["input"][2] == old  # Actual tool name and range stay unchanged.
    reduced = sent[-1]["input"][3]["output"]
    if guard in ("overview", "compact"):
        assert state["starts"] == 1 and len(state["requests"]) == 1
        assert state["requests"][0][1] == {
            "eligible_indices": [3], "frozen_message_count": 0, "keep_recent_tool_results": 1,
        }
        assert reduced != observed
        reference = reduced.split("\n", 1)[0]
        assert native.runtime.ccr.retrieve(reference) == observed
        if guard == "compact":
            annotated = native.runtime.ccr.stash(
                observed, ctype="source", source=str(native.workspace / "notes.md"), kind="root",
            )
            assert annotated != reference
            assert tokens.count_tokens(reference) < tokens.count_tokens(annotated)
            page = native.runtime.ccr.retrieve_page(reference)
            assert page["content"] == observed
            assert page["metadata"]["kind"] == "root"
            assert page["metadata"]["source"] == str(native.workspace / "notes.md")
            assert native.runtime.profile["runtime_policy"][
                "headroom_root_reference_style"] == "compact-root-v1"
            with pytest.raises(AttributeError):
                native.runtime._headroom_root_reference_style = "annotated-v1"
        assert tokens.count_tokens(tokens.serialize(sent[-1])) < tokens.count_tokens(
            tokens.serialize({**third, "parallel_tool_calls": False,
                              "stream": False, "max_output_tokens": 2048}))
    else:
        assert reduced == observed
    result = native.finish(native_exit_code=0)
    assert result["complete"]
    assert result["runtime"]["transformations"] == int(guard in ("overview", "compact"))
    if guard in ("exact", "edit", "debug", "code", "failure", "legacy"):
        assert state["starts"] == 0
