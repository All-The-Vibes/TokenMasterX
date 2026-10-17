"""Pure synthetic stdout fixtures; never launch a native host or read a profile."""
import copy
import json
from pathlib import Path
import threading
import time

import pytest

from brainspace.native_events import NativeEventCollector, validate_native_skills


MODEL = "gpt-6-astra"
TEXT = 'def example():\n    return "雪  error words are source data"\n'


def test_vendor_original_content_error_words_are_data_not_status():
    from brainspace.native_events import _mcp_text_result
    payload = {"hash": "a" * 24,
               "original_content": "The document explains what happens when a request is denied.",
               "original_item_count": 1}
    result = {"content": json.dumps(payload, separators=(",", ":")),
              "detailedContent": "",
              "contents": [{"type": "text", "text": json.dumps(payload)}]}
    assert _mcp_text_result(result, 65536)
    payload["isError"] = True
    result["content"] = json.dumps(payload, separators=(",", ":"))
    result["contents"][0]["text"] = json.dumps(payload)
    assert not _mcp_text_result(result, 65536)


def test_vendor_original_content_cannot_hide_a_structured_status():
    from brainspace.native_events import _mcp_text_result
    payload = {"original_content": {"error": "not source text"}}
    result = {"content": json.dumps(payload), "detailedContent": "",
              "contents": [{"type": "text", "text": json.dumps(payload)}]}
    assert not _mcp_text_result(result, 65536)


def skills_event(cache_root, version="1.0.95-0"):
    """Stock skills-loaded envelope; paths are synthetic and need no file reads."""
    return {"type": "session.skills_loaded", "ephemeral": True,
            "id": "native-skills-event", "timestamp": "2026-10-09T15:33:17.210Z",
            "parentId": "native-parent", "data": {"skills": [
                {"name": name, "commandName": name, "description": "Stock built-in skill.",
                 "source": "builtin", "userInvocable": False, "enabled": True,
                 "path": str(cache_root / "pkg" / "win32-x64" / version
                             / "builtin" / name / "SKILL.md")}
                for name in ("customize-cloud-agent", "github-pr-media")
            ]}}


@pytest.mark.parametrize("mode", ["stock", "reversed", "empty"])
def test_native_skills_accepts_only_stock_pair_or_empty_without_content_reads(
    tmp_path, monkeypatch, mode,
):
    cache_root = tmp_path / "copilot-cache"
    event = skills_event(cache_root)
    if mode == "reversed":
        event["data"]["skills"].reverse()
    elif mode == "empty":
        event["data"]["skills"] = []
    before = copy.deepcopy(event)
    def forbid_content_read(*args, **kwargs):
        raise AssertionError("skill content must not be read")
    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", forbid_content_read)
        patch.setattr(Path, "read_text", forbid_content_read)
        patch.setattr(Path, "read_bytes", forbid_content_read)
        assert validate_native_skills(event, cache_root=cache_root)
    assert event == before


@pytest.mark.parametrize("field,value", [
    ("source", "personal"), ("source", "project"), ("source", "inherited"),
    ("source", "Builtin"), ("source", "builtin "),
    ("name", "Customize-cloud-agent"), ("name", "CUSTOMIZE-CLOUD-AGENT"),
    ("name", "customize-cloud-agent "), ("name", "customize-cloud-аgent"),
    ("name", "../customize-cloud-agent"), ("name", "unrecognized"),
    ("commandName", "github-pr-media"), ("commandName", "Customize-cloud-agent"),
    ("userInvocable", True), ("userInvocable", 0), ("enabled", False), ("enabled", 1),
    ("description", None), ("description", ["text"]), ("description", "x" * 4097),
    ("description", "\ud800"), ("description", "hidden\0text"),
    ("path", None), ("path", "\ud800"), ("path", "x" * 4097),
])
def test_native_skills_rejects_spoofed_labels_and_malformed_fields(tmp_path, field, value):
    event = skills_event(tmp_path)
    event["data"]["skills"][0][field] = value
    assert not validate_native_skills(event, cache_root=tmp_path)


@pytest.mark.parametrize("description", ["", "x" * 4096, "Stock 雪 description"])
def test_native_skills_description_boundary(tmp_path, description):
    event = skills_event(tmp_path)
    event["data"]["skills"][0]["description"] = description
    assert validate_native_skills(event, cache_root=tmp_path)


@pytest.mark.parametrize("case", [
    "one", "duplicate", "three", "all_duplicate", "extra_field", "missing_field",
    "wrong_event", "extra_data", "extra_event", "bad_data", "not_list",
    "non_dict_entry", "bad_ephemeral", "oversized_id", "raw_json", "fake_assistant",
])
def test_native_skills_rejects_unexpected_shape_or_entries(tmp_path, case):
    event = skills_event(tmp_path)
    skills = event["data"]["skills"]
    if case == "one":
        skills.pop()
    elif case == "duplicate":
        skills[1] = copy.deepcopy(skills[0])
    elif case == "three":
        skills.append(copy.deepcopy(skills[0]))
    elif case == "all_duplicate":
        skills.extend(copy.deepcopy(skills))
    elif case == "extra_field":
        skills[0]["inherited"] = True
    elif case == "missing_field":
        del skills[0]["source"]
    elif case == "wrong_event":
        event["type"] = "assistant.message"
    elif case == "extra_data":
        event["data"]["inheritedSkills"] = []
    elif case == "extra_event":
        event["inheritedSkills"] = []
    elif case == "bad_data":
        event["data"] = []
    elif case == "not_list":
        event["data"]["skills"] = {}
    elif case == "non_dict_entry":
        skills[0] = "customize-cloud-agent"
    elif case == "bad_ephemeral":
        event["ephemeral"] = 1
    elif case == "oversized_id":
        event["id"] = "x" * 513
    elif case == "raw_json":
        event = json.dumps(event)
    else:
        event = {"type": "assistant.message", "data": {"content": json.dumps(event)}}
    assert not validate_native_skills(event, cache_root=tmp_path)


@pytest.mark.parametrize("case", [
    "foreign_cache", "personal", "project", "other_skill", "wrong_version",
    "wrong_arch", "traversal_alias", "relative", "sibling_prefix", "upper_pkg",
    "upper_builtin", "upper_name", "lower_filename", "url", "alternate_stream",
])
def test_native_skills_requires_exact_pinned_path_and_case(tmp_path, case):
    cache_root = tmp_path / "copilot-cache"
    event = skills_event(cache_root)
    skill = event["data"]["skills"][0]
    tail = Path("pkg") / "win32-x64" / "1.0.95-0" / "builtin" / skill["name"] / "SKILL.md"
    bad_paths = {
        "foreign_cache": str(tmp_path / "foreign-cache" / tail),
        "personal": str(tmp_path / ".copilot" / "skills" / skill["name"] / "SKILL.md"),
        "project": str(tmp_path / "workspace" / ".github" / "skills" / skill["name"] / "SKILL.md"),
        "other_skill": event["data"]["skills"][1]["path"],
        "wrong_version": str(cache_root / tail).replace("1.0.95-0", "1.0.94-0"),
        "wrong_arch": str(cache_root / tail).replace("win32-x64", "linux-x64"),
        "traversal_alias": str(cache_root / "unused" / ".." / tail),
        "relative": str(tail),
        "sibling_prefix": str(tmp_path / "copilot-cache-other" / tail),
        "upper_pkg": str(cache_root / "PKG" / Path(*tail.parts[1:])),
        "upper_builtin": str(cache_root / tail).replace("builtin", "BUILTIN"),
        "upper_name": str(cache_root / tail).replace(skill["name"], skill["name"].upper()),
        "lower_filename": str(cache_root / tail).replace("SKILL.md", "skill.md"),
        "url": "file:///" + str(cache_root / tail),
        "alternate_stream": str(cache_root / tail) + ":extra",
    }
    skill["path"] = bad_paths[case]
    assert not validate_native_skills(event, cache_root=cache_root)


@pytest.mark.parametrize("link_check", ["is_symlink", "is_junction"])
@pytest.mark.parametrize("location", ["cache", "parent", "file"])
def test_native_skills_rejects_links_without_following_them(
    tmp_path, monkeypatch, link_check, location,
):
    cache_root = tmp_path / "copilot-cache"
    event = skills_event(cache_root)
    skill_path = Path(event["data"]["skills"][0]["path"])
    linked = {"cache": cache_root, "parent": skill_path.parent, "file": skill_path}[location]
    monkeypatch.setattr(Path, link_check, lambda self: self == linked)
    assert not validate_native_skills(event, cache_root=cache_root)


def test_native_skills_version_is_explicit_and_path_bound(tmp_path):
    event = skills_event(tmp_path, version="1.0.96-0")
    assert not validate_native_skills(event, cache_root=tmp_path)
    assert validate_native_skills(event, cache_root=tmp_path, version="1.0.96-0")
    for version in ("..", "", "../1.0.95-0", "1.0.95-0/extra", r"..\1.0.95-0", None):
        assert not validate_native_skills(event, cache_root=tmp_path, version=version)
    assert not validate_native_skills(event, cache_root="relative-cache")
    assert not validate_native_skills(event, cache_root=None)


def call(path="source.py", call_id="real-upstream-id", name="view", **arguments):
    return {"id": call_id, "type": "function", "function": {
        "name": name, "arguments": json.dumps({"path": path, **arguments})}}


def events(tool_call, content=TEXT):
    """Shape from installed-hook-002/before-native.json, without profile data."""
    start = {"type": "tool.execution_start", "id": "native-event-start", "data": {
        "toolCallId": tool_call["id"], "toolName": tool_call["function"]["name"],
        "arguments": json.loads(tool_call["function"]["arguments"]),
        "turnId": "0", "model": MODEL, "toolTitle": "Viewing file"}}
    complete = {"type": "tool.execution_complete", "id": "native-event-complete", "data": {
        "toolCallId": tool_call["id"], "model": MODEL, "interactionId": "interaction",
        "turnId": "0", "rte": False, "success": True,
        "result": {"content": content, "detailedContent": "PRIVATE UI DIFF"},
        "toolTelemetry": {"properties": {"viewType": "file"},
                          "metrics": {"resultLength": len(content)}}}}
    return start, complete


def request(tool_call, content=TEXT):
    return {"model": MODEL, "messages": [
        {"role": "assistant", "content": None, "tool_calls": [tool_call]},
        {"role": "tool", "tool_call_id": tool_call["id"], "content": content}]}


def collector(tmp_path, **kwargs):
    return NativeEventCollector(workspace=tmp_path, expected_model=MODEL, **kwargs)


def completed(tmp_path, tool_call=None, **kwargs):
    tool_call = tool_call or call()
    result = collector(tmp_path, **kwargs)
    result.register_expected_calls([tool_call], model=MODEL)
    for event in events(tool_call):
        result.observe(event)
    return result, tool_call


def test_success_exact_native_id_view_and_raw_content(tmp_path):
    result, tool_call = completed(tmp_path)
    receipts = result.source_reads(request(tool_call))
    assert len(receipts) == 1
    assert receipts[0].call_id == tool_call["id"]
    assert receipts[0].tool_name == "view"
    assert receipts[0].source_path == "source.py"
    assert receipts[0].matches(request(tool_call)["messages"][1], tool_call)
    assert result.wait_for_completed([tool_call["id"]], timeout=0)
    assert result.summary()["counts"]["success"] == 1
    assert "PRIVATE UI DIFF" not in json.dumps(result.summary())


@pytest.mark.parametrize("field,value", [
    ("toolCallId", "unregistered"), ("toolName", "read_file"),
    ("arguments", {"path": "other.py"}), ("model", "foreign"),
    ("turnId", None), ("arguments", {"path": "source.py", "range": [1, 2]}),
])
def test_start_binding_mismatch(tmp_path, field, value):
    result = collector(tmp_path)
    tool_call = call()
    result.register_expected_calls([tool_call], model=MODEL)
    start, complete = events(tool_call)
    start["data"][field] = value
    result.observe(start)
    result.observe(complete)
    assert result.source_reads(request(tool_call)) == ()
    assert result.summary()["diagnostics"]


@pytest.mark.parametrize("field,value", [
    ("model", "foreign"), ("turnId", "different"), ("success", "true"),
    ("success", False), ("rte", True), ("result", {"content": ["mixed"]}),
    ("result", {"content": TEXT, "images": ["image"]}),
    ("result", {"content": None}), ("error", "denied"),
    ("toolTelemetry", {"properties": {"viewType": "unknown"}}),
    ("toolTelemetry", None), ("toolTelemetry", {"properties": []}),
])
def test_no_receipt_for_unsafe_completion(tmp_path, field, value):
    result = collector(tmp_path)
    tool_call = call()
    result.register_expected_calls([tool_call], model=MODEL)
    start, complete = events(tool_call)
    complete["data"][field] = value
    result.observe(start)
    result.observe(complete)
    assert result.source_reads(request(tool_call)) == ()
    if field == "success" and value is False:
        assert result.summary()["counts"]["failure"] == 1
    else:
        assert not result.summary()["coverage_complete"]
        assert result.summary()["diagnostics"]


def mcp_result(content=None, native_content=None):
    """Three-key native MCP result from installed-local-001, with synthetic text."""
    if content is None:
        content = json.dumps({
            "ok": True, "content": '{\r\n  "value": "literal  data 雪"\r\n}',
            "offset": 0, "next_offset": None, "complete": True, "error": None,
            "metadata": {"kind": "root", "source": "synthetic.json"}, "encoding": "utf-8",
        }, ensure_ascii=False)
        native_content = json.dumps(json.loads(content), ensure_ascii=False, separators=(",", ":"))
    if native_content is None:
        native_content = content
    return {"content": native_content, "detailedContent": native_content,
            "contents": [{"type": "text", "text": content}]}


@pytest.mark.parametrize("name", ["tokenmaster-retrieve_original", "tokenmaster-headroom_retrieve"])
@pytest.mark.parametrize("representation", ["json_whitespace", "literal", "split_text"])
def test_native_mcp_text_rendering_is_accounted_without_recovery_proof(
    tmp_path, name, representation,
):
    tool_call = call(name=name, call_id="native_root_recovery")
    result = collector(tmp_path)
    result.register_expected_calls([tool_call], model=MODEL)
    start, complete = events(tool_call)
    payload = mcp_result() if representation == "json_whitespace" else mcp_result(TEXT)
    if representation == "split_text":
        payload["contents"] = [
            {"type": "text", "text": TEXT[:12]}, {"type": "text", "text": TEXT[12:]}]
    complete["data"]["result"] = payload
    complete["data"]["toolTelemetry"] = {"metrics": {"mcp_result_content_bytes": 123}}
    original = copy.deepcopy(complete)
    result.observe(start)
    result.observe(complete)
    result.observe(copy.deepcopy(complete))
    assert result.wait_for_completed([tool_call["id"]], 0)
    assert result.summary()["counts"]["success"] == 1
    assert result.summary()["coverage_complete"]
    assert result.summary()["diagnostics"] == {}
    assert result.source_reads(request(tool_call, payload["content"])) == ()
    assert complete == original  # No content, whitespace, or source rewriting.


@pytest.mark.parametrize("native,original", [
    ('{"a":true,"b":"雪"}', '{ "b": "\\u96ea", "a": true }'),
    ('{"value":[true,null,{"a":"literal  data"}]}',
     '{ "value": [ true, null, { "a" : "literal  data" } ] }'),
])
def test_native_mcp_json_equivalence_is_structural(tmp_path, native, original):
    tool_call = call(name="tokenmaster-retrieve_original")
    result = collector(tmp_path)
    result.register_expected_calls([tool_call], model=MODEL)
    start, complete = events(tool_call)
    complete["data"]["result"] = mcp_result(original, native)
    result.observe(start)
    result.observe(complete)
    assert result.summary()["coverage_complete"]
    assert result.source_reads(request(tool_call, native)) == ()


@pytest.mark.parametrize("native,original", [
    ("one", "two"),
    ('{"content":"literal data"}', '{"content":"literal  data"}'),
    ('{"value":true}', '{"value":1}'),
    ('{"value":1}', '{"value":1.0}'),
    ('{"value":"1"}', '{"value":1}'),
    ('{"value":0.1}', '{"value":0.10000000000000000001}'),
    ('{"value":9007199254740992.0}', '{"value":9007199254740993.0}'),
    ('{"value":0}', '{"value":-0}'),
    ('{"value":2}', '{"value":1,"value":2}'),
    ('{"value":1,"value":2}', '{"value":1,"value":2}'),
    ('{"value":NaN}', '{"value":NaN}'),
    ('{"value":1e999}', '{"value":1e999}'),
    ('{"value":"\\ud800"}', '{"value":"\\ud800"}'),
    ('{"value":', '{"value":'),
    ('{"ok":false,"error":"denied"}', '{"ok":false,"error":"denied"}'),
])
def test_native_mcp_conflicting_or_ambiguous_json_stays_unknown(tmp_path, native, original):
    tool_call = call(name="tokenmaster-retrieve_original")
    result = collector(tmp_path)
    result.register_expected_calls([tool_call], model=MODEL)
    start, complete = events(tool_call)
    complete["data"]["result"] = mcp_result(original, native)
    result.observe(start)
    result.observe(complete)
    assert result.wait_for_completed([tool_call["id"]], 0)
    assert result.summary()["counts"]["unknown"] == 1
    assert result.summary()["diagnostics"]["unsafe_result"] == 1
    assert not result.summary()["coverage_complete"]
    assert result.source_reads(request(tool_call, native)) == ()


@pytest.mark.parametrize("change", [
    "image", "mixed_image", "nonstring", "extra_block_field", "extra_result_field",
    "empty", "not_list", "too_many_blocks", "bad_details",
])
def test_native_mcp_rejects_mixed_and_unknown_result_shapes(tmp_path, change):
    tool_call = call(name="tokenmaster-headroom_retrieve")
    result = collector(tmp_path)
    result.register_expected_calls([tool_call], model=MODEL)
    start, complete = events(tool_call)
    payload = mcp_result()
    if change == "image":
        payload["contents"] = [{"type": "image", "data": "image"}]
    elif change == "mixed_image":
        payload["contents"].append({"type": "image", "data": "image"})
    elif change == "nonstring":
        payload["contents"][0]["text"] = None
    elif change == "extra_block_field":
        payload["contents"][0]["annotations"] = {}
    elif change == "extra_result_field":
        payload["isError"] = False
    elif change == "empty":
        payload["contents"] = []
    elif change == "not_list":
        payload["contents"] = {}
    elif change == "too_many_blocks":
        payload = mcp_result("x" * 65)
        payload["contents"] = [{"type": "text", "text": "x"} for _ in range(65)]
    else:
        payload["detailedContent"] = None
    complete["data"]["result"] = payload
    result.observe(start)
    result.observe(complete)
    assert result.summary()["counts"]["unknown"] == 1
    assert not result.summary()["coverage_complete"]
    assert result.source_reads(request(tool_call, payload["content"])) == ()


@pytest.mark.parametrize("name", [
    "view", "read_file", "retrieve_original", "headroom_retrieve",
    "other-retrieve_original", "tokenmaster-RETRIEVE_ORIGINAL",
])
def test_native_mcp_rendering_exception_is_exactly_name_scoped(tmp_path, name):
    tool_call = call(name=name)
    result = collector(tmp_path)
    result.register_expected_calls([tool_call], model=MODEL)
    start, complete = events(tool_call)
    payload = mcp_result()
    complete["data"]["result"] = payload
    result.observe(start)
    result.observe(complete)
    assert result.summary()["counts"]["unknown"] == 1
    assert not result.summary()["coverage_complete"]
    assert result.source_reads(request(tool_call, payload["content"])) == ()


def test_native_mcp_execution_failure_is_still_failure(tmp_path):
    tool_call = call(name="tokenmaster-retrieve_original")
    result = collector(tmp_path)
    result.register_expected_calls([tool_call], model=MODEL)
    start, complete = events(tool_call)
    complete["data"]["success"] = False
    complete["data"]["result"] = mcp_result()
    result.observe(start)
    result.observe(complete)
    assert result.summary()["counts"]["failure"] == 1
    assert result.summary()["counts"]["success"] == 0


@pytest.mark.parametrize("path,arguments,view_type,note", [
    (".", {}, "directory", "directory_view"),
    ("subdirectory", {}, "directory", "directory_view"),
    ("source.py", {"view_range": [1, 5]}, "file", "ranged_view"),
])
def test_successful_ineligible_views_preserve_coverage(
    tmp_path, path, arguments, view_type, note,
):
    journal: list[dict] = []
    result = collector(tmp_path, journal=journal.append)
    tool_call = call(path, **arguments)
    result.register_expected_calls([tool_call], model=MODEL)
    start, complete = events(tool_call)
    complete["data"]["toolTelemetry"]["properties"]["viewType"] = view_type
    result.observe(start)
    result.observe(complete)
    result.observe(copy.deepcopy(complete))
    assert result.wait_for_completed([tool_call["id"]], 0)
    assert result.source_reads(request(tool_call)) == ()
    summary = result.summary()
    assert summary["coverage_complete"]
    assert summary["counts"]["success"] == 1
    assert summary["diagnostics"] == {}
    assert summary["ineligibility_notes"] == {note: 1}
    summary["ineligibility_notes"].clear()
    assert result.close()["ineligibility_notes"] == {note: 1}
    assert journal[-1]["ineligibility_notes"] == {note: 1}
    assert journal[-1]["coverage_complete"]


@pytest.mark.parametrize("arguments,view_type", [
    ({}, "directory"), ({"view_range": [1, 5]}, "file"),
])
def test_ineligible_view_does_not_hide_foreign_paths(tmp_path, arguments, view_type):
    result = collector(tmp_path)
    tool_call = call("../foreign", **arguments)
    result.register_expected_calls([tool_call], model=MODEL)
    start, complete = events(tool_call)
    complete["data"]["toolTelemetry"]["properties"]["viewType"] = view_type
    result.observe(start)
    result.observe(complete)
    assert result.source_reads(request(tool_call)) == ()
    assert not result.summary()["coverage_complete"]
    assert result.summary()["diagnostics"]["ineligible_path"] == 1


@pytest.mark.parametrize("view_range", [None, "1:5", [1], [1, "5"], [True, 5]])
def test_malformed_view_range_is_not_a_benign_note(tmp_path, view_range):
    tool_call = call(view_range=view_range)
    result, _ = completed(tmp_path, tool_call)
    assert not result.summary()["coverage_complete"]
    assert result.summary()["diagnostics"]
    assert result.source_reads(request(tool_call)) == ()


def test_directory_then_file_keeps_accounting_and_source_receipts_separate(tmp_path):
    result = collector(tmp_path)
    directory = call(".", call_id="issued-directory")
    source = call(call_id="issued-source")
    result.register_expected_calls([directory, source], model=MODEL)
    start, complete = events(directory)
    complete["data"]["toolTelemetry"]["properties"]["viewType"] = "directory"
    for event in (start, complete, *events(source)):
        result.observe(event)
    canonical = request(directory)
    canonical["messages"].extend(request(source)["messages"])
    assert result.wait_for_completed([directory["id"], source["id"]], 0)
    assert result.summary()["coverage_complete"]
    assert [info.call_id for info in result.source_reads(canonical)] == [source["id"]]
    result.observe({"type": "tool.execution_start", "data": None})
    summary = result.close()
    assert summary["ineligibility_notes"] == {"directory_view": 1}
    assert summary["diagnostics"]["malformed_event"] == 1
    assert not summary["coverage_complete"]
    assert result.source_reads(canonical) == ()


@pytest.mark.parametrize("kind", ["content", "arguments", "name", "id", "model", "mixed",
                                 "duplicate", "order", "error"])
def test_canonical_request_must_match(tmp_path, kind):
    result, tool_call = completed(tmp_path)
    canonical = request(copy.deepcopy(tool_call))
    assistant, tool = canonical["messages"]
    if kind == "content":
        tool["content"] += " "
    elif kind == "arguments":
        assistant["tool_calls"][0]["function"]["arguments"] = '{"path":"other.py"}'
    elif kind == "name":
        assistant["tool_calls"][0]["function"]["name"] = "read_file"
    elif kind == "id":
        tool["tool_call_id"] = assistant["tool_calls"][0]["id"] = "invented"
    elif kind == "model":
        canonical["model"] = "foreign"
    elif kind == "mixed":
        tool["content"] = [{"type": "text", "text": TEXT}]
    elif kind == "duplicate":
        canonical["messages"].extend(copy.deepcopy(canonical["messages"]))
    elif kind == "order":
        canonical["messages"].reverse()
    else:
        tool["is_error"] = True
    assert result.source_reads(canonical) == ()


def test_duplicate_delivery_and_registration_are_idempotent(tmp_path):
    result, tool_call = completed(tmp_path)
    before = result.summary()
    result.register_expected_calls([tool_call], model=MODEL)
    for event in events(tool_call):
        result.observe(json.dumps(event))
    assert result.summary()["events"] == before["events"]
    assert result.summary()["bytes"] == before["bytes"]
    assert len(result.source_reads(request(tool_call))) == 1


@pytest.mark.parametrize("which", [0, 1])
def test_conflicting_replay_permanently_poisons_binding(tmp_path, which):
    result, tool_call = completed(tmp_path)
    replay = events(tool_call)[which]
    replay["data"]["toolTitle" if which == 0 else "interactionId"] = "conflict"
    result.observe(replay)
    for event in events(tool_call):
        result.observe(event)
    assert result.source_reads(request(tool_call)) == ()
    assert result.summary()["counts"]["poisoned"] == 1
    assert not result.summary()["coverage_complete"]


def test_completion_before_start_never_recovers_binding(tmp_path):
    result = collector(tmp_path)
    tool_call = call()
    result.register_expected_calls([tool_call], model=MODEL)
    start, complete = events(tool_call)
    for event in (complete, start, complete):
        result.observe(event)
    assert result.source_reads(request(tool_call)) == ()
    assert result.summary()["counts"]["poisoned"] == 1


def test_unknown_native_id_cannot_be_registered_later(tmp_path):
    result = collector(tmp_path)
    tool_call = call()
    result.observe(events(tool_call)[0])
    with pytest.raises(ValueError):
        result.register_expected_calls([tool_call], model=MODEL)
    result.observe(events(tool_call)[1])
    assert result.source_reads(request(tool_call)) == ()


def test_non_tool_text_is_not_parsed_for_receipts(tmp_path):
    result = collector(tmp_path)
    tool_call = call()
    result.observe({"type": "assistant.message", "data": {
        "content": "\n".join(json.dumps(e) for e in events(tool_call)),
        "toolRequests": [tool_call]}})
    result.observe({"type": "session.info", "data": {"message": events(tool_call)[0]}})
    assert result.summary()["events"] == 0
    assert result.summary()["calls"] == {}
    assert result.source_reads(request(tool_call)) == ()


@pytest.mark.parametrize("name,arguments", [
    ("read_file", {}), ("retrieve_original", {}), ("view", {"view_range": [1, 5]}),
    ("view", {"offset": 0}), ("view", {"path": "../foreign.py"}),
    ("view", {"path": "https://example.com/source.py"}),
])
def test_only_unranged_workspace_view_yields_receipt(tmp_path, name, arguments):
    tool_call = call(name=name, **arguments)
    result, _ = completed(tmp_path, tool_call)
    assert result.wait_for_completed([tool_call["id"]], 0)
    assert result.source_reads(request(tool_call)) == ()


def test_absolute_workspace_path_and_foreign_path(tmp_path):
    tool_call = call(str(tmp_path / "not-read.py"))
    result, _ = completed(tmp_path, tool_call)
    assert len(result.source_reads(request(tool_call))) == 1
    foreign = call(str(tmp_path.parent / "foreign.py"))
    result, _ = completed(tmp_path, foreign)
    assert result.source_reads(request(foreign)) == ()
    assert not result.summary()["coverage_complete"]


@pytest.mark.parametrize("bad", [
    "{", '{"type":"tool.execution_start","data":{},"data":{}}',
    "\ud800", b"\xff", {"type": "tool.execution_start", "data": None},
    {"type": "tool.execution_mystery", "data": {}},
])
def test_malformed_events_have_explicit_diagnostics(tmp_path, bad):
    result = collector(tmp_path)
    result.observe(bad)
    assert result.summary()["diagnostics"]
    assert not result.summary()["coverage_complete"]


def test_bad_unicode_on_bound_completion_poisons_call(tmp_path):
    result, tool_call = completed(tmp_path)
    complete = events(tool_call)[1]
    complete["data"]["result"]["content"] = "\ud800"
    result.observe(complete)
    assert result.source_reads(request(tool_call)) == ()
    assert result.summary()["counts"]["poisoned"] == 1


@pytest.mark.parametrize("as_jsonl", [False, True])
def test_oversized_completion_invalidates_prior_receipts(tmp_path, as_jsonl):
    result, tool_call = completed(tmp_path, max_event_bytes=1024)
    complete = events(tool_call)[1]
    complete["data"]["result"]["content"] = "x" * 2048
    result.observe(json.dumps(complete) if as_jsonl else complete)
    assert result.summary()["limit_exceeded"]
    assert result.source_reads(request(tool_call)) == ()


@pytest.mark.parametrize("options", [
    {"max_events": 1}, {"max_bytes": 100}, {"max_event_bytes": 100},
])
def test_bounds_fail_closed_without_eviction_or_false_zero(tmp_path, options):
    result = collector(tmp_path, **options)
    tool_call = call()
    try:
        result.register_expected_calls([tool_call], model=MODEL)
    except ValueError:
        pass
    for event in events(tool_call):
        result.observe(event)
    summary = result.summary()
    assert summary["limit_exceeded"]
    assert not summary["coverage_complete"]
    assert summary["events"] <= options.get("max_events", 4096)
    assert summary["bytes"] <= options.get("max_bytes", 16 * 1024 * 1024)
    assert result.source_reads(request(tool_call)) == ()


def test_registration_staging_is_byte_bounded(tmp_path):
    result = collector(tmp_path, max_bytes=300)
    calls = [call(call_id=f"upstream-{index}") for index in range(10)]
    with pytest.raises(ValueError):
        result.register_expected_calls(calls, model=MODEL)
    assert result.summary()["limit_exceeded"]
    assert result.summary()["calls"] == {}


def test_tool_result_name_cannot_contradict_call(tmp_path):
    result, tool_call = completed(tmp_path)
    canonical = request(tool_call)
    canonical["messages"][1]["name"] = "shell"
    assert result.source_reads(canonical) == ()


def test_missing_completion_timeout_and_eof_preserve_pending(tmp_path):
    result = collector(tmp_path)
    tool_call = call()
    result.register_expected_calls([tool_call], model=MODEL)
    result.observe(events(tool_call)[0])
    assert not result.wait_for_completed([tool_call["id"]], 0.01)
    assert result.summary()["counts"]["pending"] == 1
    closed = result.close()
    assert closed["closed"]
    assert closed["counts"]["pending"] == 1
    assert not closed["coverage_complete"]
    assert not result.wait_for_completed([tool_call["id"]], 1)
    assert not result.wait_for_completed(["unknown"], 0)
    result.observe(events(tool_call)[1])
    assert result.source_reads(request(tool_call)) == ()


def test_waiter_wakes_on_completion_and_close(tmp_path):
    result = collector(tmp_path)
    tool_call = call()
    result.register_expected_calls([tool_call], model=MODEL)
    answers = []
    thread = threading.Thread(target=lambda: answers.append(
        result.wait_for_completed([tool_call["id"]], 2)))
    thread.start()
    for event in events(tool_call):
        result.observe(event)
    thread.join(1)
    assert answers == [True]
    thread = threading.Thread(target=lambda: answers.append(
        result.wait_for_completed(["missing"], 2)))
    thread.start()
    result.close()
    thread.join(1)
    assert answers == [True, False]


@pytest.mark.parametrize("method", ["wait_for_started", "wait_for_completed"])
@pytest.mark.parametrize("timeout", [-1, float("inf"), float("nan"), True,
                                     threading.TIMEOUT_MAX + 1])
def test_invalid_wait_timeout(tmp_path, timeout, method):
    with pytest.raises(ValueError):
        getattr(collector(tmp_path), method)(["id"], timeout)


def test_start_wait_releases_recovery_without_completion(tmp_path):
    result = collector(tmp_path)
    tool_call = call(name="retrieve_original")
    result.register_expected_calls([tool_call], model=MODEL)
    assert not result.wait_for_started([tool_call["id"]], 0)
    result.observe(events(tool_call)[0])
    assert result.wait_for_started([tool_call["id"]], 0)
    assert not result.wait_for_completed([tool_call["id"]], 0)
    assert result.summary()["counts"]["pending"] == 1
    assert result.source_reads(request(tool_call)) == ()


def test_start_wait_timeout_and_eof_preserve_pending(tmp_path):
    result = collector(tmp_path)
    tool_call = call()
    result.register_expected_calls([tool_call], model=MODEL)
    start = time.monotonic()
    assert not result.wait_for_started([tool_call["id"]], 0.01)
    assert time.monotonic() - start < 1
    result.close()
    assert not result.wait_for_started([tool_call["id"]], 1)
    assert not result.wait_for_started(["unknown"], 0)
    assert result.summary()["counts"]["pending"] == 1


def test_start_wait_duplicates_and_already_started_at_eof(tmp_path):
    result = collector(tmp_path)
    tool_call = call()
    result.register_expected_calls([tool_call], model=MODEL)
    result.observe(events(tool_call)[0])
    before = result.summary()
    result.observe(events(tool_call)[0])
    assert result.summary() == before
    assert result.wait_for_started([tool_call["id"]], 0)
    result.close()
    assert result.wait_for_started([tool_call["id"]], 0)
    assert not result.wait_for_completed([tool_call["id"]], 0)


@pytest.mark.parametrize("reason", ["mismatch", "conflict", "out_of_order", "unsafe"])
def test_start_wait_rejects_poison_and_unsafe_coverage(tmp_path, reason):
    result = collector(tmp_path)
    tool_call = call()
    result.register_expected_calls([tool_call], model=MODEL)
    start, complete = events(tool_call)
    if reason == "conflict":
        result.observe(start)
        start["data"]["arguments"]["path"] = "conflicting.py"
    elif reason == "mismatch":
        start["data"]["model"] = "foreign"
    elif reason == "out_of_order":
        result.observe(complete)
    else:
        result.observe("{")
    result.observe(start)
    assert not result.wait_for_started([tool_call["id"]], 0)


@pytest.mark.parametrize("outcome", ["start", "close", "poison"])
def test_start_waiter_wakes_without_completion(tmp_path, outcome):
    result = collector(tmp_path)
    tool_call = call()
    result.register_expected_calls([tool_call], model=MODEL)
    answers = []
    thread = threading.Thread(target=lambda: answers.append(
        result.wait_for_started([tool_call["id"]], 2)))
    thread.start()
    if outcome == "close":
        result.close()
    else:
        start = events(tool_call)[0]
        if outcome == "poison":
            start["data"]["toolName"] = "foreign"
        result.observe(start)
    thread.join(1)
    assert answers == [outcome == "start"]
    assert not result.wait_for_completed([tool_call["id"]], 0)


def test_start_wait_requires_every_registered_id(tmp_path):
    result = collector(tmp_path)
    calls = [call(call_id="issued-a"), call(call_id="issued-b")]
    ids = [tool_call["id"] for tool_call in calls]
    result.register_expected_calls(calls, model=MODEL)
    result.observe(events(calls[0])[0])
    assert not result.wait_for_started(ids, 0)
    result.observe(events(calls[1])[0])
    assert result.wait_for_started(ids, 0)
    assert not result.wait_for_started([*ids, "unregistered"], 0)


def test_pending_native_call_can_be_claimed_once_without_changing_status(tmp_path):
    journal: list[dict] = []
    result = collector(tmp_path, journal=journal.append)
    tool_call = call(name="retrieve_original")
    result.register_expected_calls([tool_call], model=MODEL)
    start, complete = events(tool_call)
    result.observe(start)
    assert result.wait_for_started([tool_call["id"]], 0)
    before = result.summary()
    assert result.claim_pending_call(tool_call["id"])
    claimed = result.summary()
    assert claimed["counts"] == before["counts"]
    assert claimed["calls"][tool_call["id"]]["claimed"]
    assert claimed["events"] == before["events"] + 1
    assert claimed["bytes"] > before["bytes"]
    assert not result.wait_for_completed([tool_call["id"]], 0)
    result.observe(copy.deepcopy(start))
    result.register_expected_calls([tool_call], model=MODEL)
    assert not result.claim_pending_call(tool_call["id"])
    claims = [row for row in journal if row["kind"] == "claimed"]
    assert len(claims) == 1
    assert claims[0]["call_id"] == tool_call["id"]
    assert claims[0]["name"] == "retrieve_original"
    assert claims[0]["status"] == "pending"
    assert "arguments" not in claims[0] and "content" not in claims[0]
    result.observe(complete)
    assert result.wait_for_completed([tool_call["id"]], 0)
    assert result.summary()["counts"]["success"] == 1
    assert not result.claim_pending_call(tool_call["id"])


@pytest.mark.parametrize("success", [True, False])
def test_native_completion_before_claim_rejects_dispatch(tmp_path, success):
    journal: list[dict] = []
    result = collector(tmp_path, journal=journal.append)
    tool_call = call(name="retrieve_original")
    result.register_expected_calls([tool_call], model=MODEL)
    start, complete = events(tool_call)
    complete["data"]["success"] = success
    result.observe(start)
    result.observe(complete)
    assert result.wait_for_started([tool_call["id"]], 0)
    assert result.wait_for_completed([tool_call["id"]], 0)
    before = result.summary()
    assert not result.claim_pending_call(tool_call["id"])
    assert result.summary() == before
    assert before["calls"][tool_call["id"]]["status"] == ("success" if success else "failure")
    assert not any(row["kind"] == "claimed" for row in journal)


@pytest.mark.parametrize("state", [
    "unknown", "unstarted", "closed", "poison", "unsafe", "unknown_result", "unregistered_start",
])
def test_native_claim_rejects_non_pending_or_untrusted_calls(tmp_path, state):
    result = collector(tmp_path)
    tool_call = call(name="retrieve_original")
    start, complete = events(tool_call)
    if state != "unknown" and state != "unregistered_start":
        result.register_expected_calls([tool_call], model=MODEL)
    if state not in ("unknown", "unstarted"):
        result.observe(start)
    if state == "closed":
        result.close()
    elif state == "poison":
        start["data"]["arguments"]["path"] = "conflict"
        result.observe(start)
    elif state == "unsafe":
        result.observe("{")
    elif state == "unknown_result":
        complete["data"]["result"]["content"] = None
        result.observe(complete)
    before = result.summary()
    assert not result.claim_pending_call(tool_call["id"])
    assert result.summary() == before


@pytest.mark.parametrize("call_id", [None, [], {}, "", "\ud800", "x" * 513])
def test_native_claim_rejects_invalid_ids_without_mutation(tmp_path, call_id):
    result = collector(tmp_path)
    before = result.summary()
    assert not result.claim_pending_call(call_id)
    assert result.summary() == before


def test_native_claim_journal_failure_consumes_claim_and_fails_closed(tmp_path):
    journal: list[dict] = []
    def append_then_fail(row):
        journal.append(row)
        if row["kind"] == "claimed":
            raise OSError("partial journal write")
    result = collector(tmp_path, journal=append_then_fail)
    tool_call = call(name="retrieve_original")
    result.register_expected_calls([tool_call], model=MODEL)
    start, _ = events(tool_call)
    result.observe(start)
    assert not result.claim_pending_call(tool_call["id"])
    snapshot = result.summary()
    assert snapshot["calls"][tool_call["id"]]["claimed"]
    assert snapshot["calls"][tool_call["id"]]["status"] == "pending"
    assert not snapshot["journal_complete"] and not snapshot["coverage_complete"]
    assert not result.claim_pending_call(tool_call["id"])
    result.observe(start)
    assert not result.claim_pending_call(tool_call["id"])
    assert len([row for row in journal if row["kind"] == "claimed"]) == 1


@pytest.mark.parametrize("limit", ["events", "bytes"])
def test_native_claim_metadata_respects_collector_bounds(tmp_path, limit):
    tool_call = call(name="retrieve_original")
    start, _ = events(tool_call)
    baseline = collector(tmp_path)
    baseline.register_expected_calls([tool_call], model=MODEL)
    baseline.observe(start)
    options = {"max_" + limit: baseline.summary()[limit]}
    result = collector(tmp_path, **options)
    result.register_expected_calls([tool_call], model=MODEL)
    result.observe(start)
    assert result.wait_for_started([tool_call["id"]], 0)
    assert not result.claim_pending_call(tool_call["id"])
    assert not result.claim_pending_call(tool_call["id"])
    assert result.summary()["limit_exceeded"]
    assert result.summary()["counts"]["pending"] == 1
    assert result.summary()[limit] == baseline.summary()[limit]


def test_concurrent_native_claims_allow_one_dispatch(tmp_path):
    journal: list[dict] = []
    result = collector(tmp_path, journal=journal.append)
    tool_call = call(name="retrieve_original")
    result.register_expected_calls([tool_call], model=MODEL)
    result.observe(events(tool_call)[0])
    barrier = threading.Barrier(9)
    answers = []
    def claim():
        barrier.wait(timeout=2)
        answers.append(result.claim_pending_call(tool_call["id"]))
    threads = [threading.Thread(target=claim) for _ in range(8)]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=2)
    for thread in threads:
        thread.join(2)
        assert not thread.is_alive()
    assert len(answers) == 8 and sum(answers) == 1
    assert len([row for row in journal if row["kind"] == "claimed"]) == 1
    assert result.summary()["counts"]["pending"] == 1


def test_claim_without_later_completion_stays_pending_at_eof(tmp_path):
    result = collector(tmp_path)
    tool_call = call(name="retrieve_original")
    result.register_expected_calls([tool_call], model=MODEL)
    result.observe(events(tool_call)[0])
    assert result.claim_pending_call(tool_call["id"])
    assert not result.wait_for_completed([tool_call["id"]], 0.01)
    summary = result.close()
    assert summary["counts"]["pending"] == 1
    assert summary["calls"][tool_call["id"]]["claimed"]
    assert not summary["coverage_complete"]
    assert not result.claim_pending_call(tool_call["id"])


def test_registration_conflicts_and_foreign_model(tmp_path):
    result, tool_call = completed(tmp_path)
    with pytest.raises(ValueError):
        result.register_expected_calls([call("different.py")], model=MODEL)
    assert result.source_reads(request(tool_call)) == ()
    result = collector(tmp_path)
    with pytest.raises(ValueError):
        result.register_expected_calls([tool_call], model="foreign")
    assert result.summary()["diagnostics"]


@pytest.mark.parametrize("arguments", ['{"path":"a","path":"b"}', '{"path":NaN}',
                                     '{"path":"\\ud800"}', '[]'])
def test_registration_rejects_ambiguous_arguments(tmp_path, arguments):
    tool_call = call()
    tool_call["function"]["arguments"] = arguments
    with pytest.raises(ValueError):
        collector(tmp_path).register_expected_calls([tool_call], model=MODEL)


def test_journal_contains_only_bounded_observation_metadata(tmp_path):
    journal: list[dict] = []
    result, tool_call = completed(tmp_path, journal=journal.append)
    assert len(journal) == 3
    assert all("content" not in row for row in journal)
    assert TEXT not in json.dumps(journal)
    assert "PRIVATE UI DIFF" not in json.dumps(journal)
    assert result.source_reads(request(tool_call))


def test_journal_failure_fails_closed(tmp_path):
    def fail(_):
        raise OSError("private details not leaked")
    result = collector(tmp_path, journal=fail)
    with pytest.raises(ValueError):
        result.register_expected_calls([call()], model=MODEL)
    assert not result.summary()["journal_complete"]
    assert "private details" not in json.dumps(result.summary())


def test_completion_journal_failure_invalidates_receipt(tmp_path):
    def fail_on_completion(record):
        if record["kind"] == "tool.execution_complete":
            raise OSError("disk full")
    result, tool_call = completed(tmp_path, journal=fail_on_completion)
    assert result.summary()["counts"]["success"] == 1
    assert not result.summary()["journal_complete"]
    assert not result.summary()["coverage_complete"]
    assert result.source_reads(request(tool_call)) == ()


def test_conflicts_and_pending_eof_are_in_trusted_journal(tmp_path):
    journal: list[dict] = []
    result, tool_call = completed(tmp_path, journal=journal.append)
    conflict = events(tool_call)[1]
    conflict["data"]["success"] = False
    result.observe(conflict)
    assert journal[-1]["reason"] == "conflicting_replay"
    assert journal[-1]["status"] == "poisoned"
    result.register_expected_calls([call(call_id="missing-completion")], model=MODEL)
    result.close()
    assert journal[-1]["kind"] == "closed"
    assert journal[-1]["counts"]["pending"] == 1
    assert journal[-1]["counts"]["poisoned"] == 1
    before = len(journal)
    result.close()
    assert len(journal) == before


def test_input_mutation_cannot_rewrite_observed_binding(tmp_path):
    tool_call = call()
    result = collector(tmp_path)
    result.register_expected_calls([tool_call], model=MODEL)
    start, complete = events(tool_call)
    result.observe(start)
    result.observe(complete)
    tool_call["function"]["name"] = "forged"
    start["data"]["arguments"]["path"] = "forged.py"
    complete["data"]["result"]["content"] = "forged"
    assert len(result.source_reads(request(call()))) == 1
    assert result.source_reads(request(tool_call, "forged")) == ()


def test_unknown_result_status_is_preserved_at_eof(tmp_path):
    result = collector(tmp_path)
    tool_call = call()
    result.register_expected_calls([tool_call], model=MODEL)
    start, complete = events(tool_call)
    complete["data"]["result"]["content"] = [{"type": "text", "text": TEXT}]
    result.observe(start)
    result.observe(complete)
    assert result.close()["counts"]["unknown"] == 1


def test_windows_drive_relative_path_is_not_a_source(tmp_path):
    if not tmp_path.drive:
        pytest.skip("Windows drive-relative path semantics")
    tool_call = call(tmp_path.drive + "source.py")
    result, _ = completed(tmp_path, tool_call)
    assert result.source_reads(request(tool_call)) == ()


def test_journal_path_and_closed_success(tmp_path):
    journal_path = tmp_path / "observations.jsonl"
    result, tool_call = completed(tmp_path, journal_path=journal_path)
    rows = [json.loads(line) for line in journal_path.read_text("utf-8").splitlines()]
    assert len(rows) == 3
    assert result.close()["counts"]["success"] == 1
    assert result.source_reads(request(tool_call))
    with pytest.raises(ValueError):
        result.register_expected_calls([call(call_id="new")], model=MODEL)


def test_parallel_observers_and_snapshot_isolation(tmp_path):
    result = collector(tmp_path)
    calls = [call(call_id=f"actual-upstream-{index}") for index in range(12)]
    result.register_expected_calls(calls, model=MODEL)
    def observe(tool_call):
        for event in events(tool_call):
            result.observe(event)
            result.observe(copy.deepcopy(event))
    threads = [threading.Thread(target=observe, args=(tool_call,)) for tool_call in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert result.wait_for_completed([tool_call["id"] for tool_call in calls], 0)
    snapshot = result.summary()
    assert snapshot["counts"]["success"] == 12
    snapshot["calls"].clear()
    assert len(result.summary()["calls"]) == 12


def test_timeout_is_bounded(tmp_path):
    start = time.monotonic()
    assert not collector(tmp_path).wait_for_completed(["missing"], 0.01)
    assert time.monotonic() - start < 1
