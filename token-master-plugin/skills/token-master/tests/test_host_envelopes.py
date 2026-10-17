import copy
import json
from pathlib import Path

import pytest

from brainspace.host_output import CLAUDE_CONTRACT, transform_output


TEXT = json.dumps([{"item": i, "status": "ok"} for i in range(80)], indent=4)


def compress(text, *_):
    return json.dumps(json.loads(text), separators=(",", ":"))


def apply(name, response, **kwargs):
    return transform_output(
        {"hook_event_name": "PostToolUse", "tool_name": name,
         "tool_response": response, "tool_use_id": "stable-id"},
        compress, contract=CLAUDE_CONTRACT, min_chars=0, **kwargs,
    )


def test_bash_preserves_all_envelope_fields_and_no_footer():
    response = {"stdout": TEXT, "stderr": "", "interrupted": False,
                "isImage": False, "exitCode": 0, "tool_use_id": "same"}
    snapshot = copy.deepcopy(response)
    result = apply("Bash", response)
    output = result["hookSpecificOutput"]["updatedToolOutput"]
    assert isinstance(output, dict)
    assert output["stdout"] == compress(TEXT)
    assert {k: v for k, v in output.items() if k != "stdout"} == {
        k: v for k, v in response.items() if k != "stdout"
    }
    assert response == snapshot


@pytest.mark.parametrize("field,value", [
    ("stderr", "DENIED: permission"), ("interrupted", True),
    ("isImage", True), ("exitCode", 1), ("error", "failed"),
])
def test_error_and_image_bash_are_passthrough(field, value):
    response = {"stdout": TEXT, "stderr": "", "interrupted": False, "isImage": False}
    response[field] = value
    assert apply("Bash", response) is None


def test_read_text_file_preserves_file_metadata():
    response = {"type": "text", "file": {"filePath": "x.json", "content": TEXT,
                "numLines": 10, "startLine": 1, "totalLines": 10}}
    output = apply("Read", response)["hookSpecificOutput"]["updatedToolOutput"]
    assert output["file"]["content"] == compress(TEXT)
    assert output["file"]["filePath"] == "x.json"
    assert output["file"]["numLines"] == 10


def test_grep_text_and_glob_have_separate_capabilities():
    response = {"mode": "content", "content": TEXT, "numLines": 100}
    assert apply("Grep", response)["hookSpecificOutput"]["updatedToolOutput"]["content"] == compress(TEXT)
    assert apply("Glob", {"filenames": [TEXT], "numFiles": 1}) is None
    assert apply("Grep", {"mode": "count", "content": TEXT}) is None


def test_mcp_text_array_preserves_metadata():
    response = {"content": [{"type": "text", "text": TEXT, "annotations": {"audience": ["assistant"]}}],
                "isError": False, "_meta": {"id": "opaque"}}
    output = apply("mcp__fixture__read", response)["hookSpecificOutput"]["updatedToolOutput"]
    assert output["content"][0]["text"] == compress(TEXT)
    assert output["content"][0]["annotations"] == response["content"][0]["annotations"]
    assert output["_meta"] == response["_meta"]


@pytest.mark.parametrize("extra", [
    {"type": "image", "data": "not-really-an-image", "mimeType": "image/png"},
    {"type": "resource", "resource": {"uri": "opaque"}},
])
def test_mixed_mcp_content_is_passthrough(extra):
    assert apply("mcp__fixture__read", {
        "content": [{"type": "text", "text": TEXT}, extra],
    }) is None


def test_structured_mcp_duplicate_representation_bypasses():
    assert apply("mcp__fixture__read", {
        "content": [{"type": "text", "text": TEXT}], "structuredContent": {"raw": TEXT},
    }) is None


@pytest.mark.parametrize("name,response", [
    ("Bash", TEXT), ("PowerShell", {"stdout": TEXT}),
    ("UnknownTool", {"content": TEXT}),
    ("Read", {"type": "image", "file": {"content": TEXT}}),
])
def test_unknown_or_mismatched_host_shapes_are_passthrough(name, response):
    assert apply(name, response) is None


def test_unknown_contract_and_codex_are_not_assumed_claude():
    payload = {"tool_name": "Bash", "tool_response": {"stdout": TEXT, "stderr": "",
                                                    "interrupted": False, "isImage": False}}
    assert transform_output(payload, compress, contract="codex", min_chars=0) is None
    assert transform_output(payload, compress, contract="claude-future", min_chars=0) is None


def test_complete_serialized_wire_byte_cap_is_enforced():
    result = apply("Bash", {"stdout": TEXT, "stderr": "", "interrupted": False, "isImage": False})
    wire = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert apply("Bash", {"stdout": TEXT, "stderr": "", "interrupted": False, "isImage": False},
                 max_stdout_bytes=len(wire.encode("utf-8")) - 1) is None


def test_failed_transform_or_larger_final_envelope_is_noop():
    response = {"stdout": TEXT, "stderr": "", "interrupted": False, "isImage": False}
    payload = {"tool_name": "Bash", "tool_response": response}
    assert transform_output(payload, lambda *_: "larger" * 10000,
                            contract=CLAUDE_CONTRACT, min_chars=0) is None
    assert transform_output(payload, lambda *_: (_ for _ in ()).throw(OSError()),
                            contract=CLAUDE_CONTRACT, min_chars=0) is None


def native_fixture(name):
    path = (Path(__file__).resolve().parents[3] / "evals" / "hosts" / "fixtures"
            / f"claude-2.1.289-{name}.json")
    return json.loads(path.read_text(encoding="utf-8"))["payload"]


def test_captured_native_mcp_array_is_compacted_without_changing_shape():
    payload = native_fixture("mcp-json")
    assert type(payload["tool_response"]) is list
    original = copy.deepcopy(payload)
    result = transform_output(payload, compress, contract=CLAUDE_CONTRACT)
    assert result is not None
    updated = result["hookSpecificOutput"]["updatedToolOutput"]
    assert type(updated) is list
    assert updated[0]["text"] == compress(payload["tool_response"][0]["text"])
    assert payload == original


def test_native_mcp_array_preserves_every_block_and_metadata():
    payload = native_fixture("mcp-json")
    payload["tool_response"][0]["annotations"] = {"audience": ["assistant"], "priority": 0.5}
    payload["tool_response"].append({"type": "text", "text": TEXT, "_meta": {"source": "second"}})
    result = transform_output(payload, compress, contract=CLAUDE_CONTRACT)
    assert result is not None
    updated = result["hookSpecificOutput"]["updatedToolOutput"]
    assert len(updated) == 2
    for before, after in zip(payload["tool_response"], updated):
        assert after["text"] == compress(before["text"])
        assert {k: v for k, v in before.items() if k != "text"} == {
            k: v for k, v in after.items() if k != "text"}


def test_captured_native_mcp_mixed_media_remains_passthrough():
    payload = native_fixture("mcp-mixed")
    assert any(block["type"] == "image" for block in payload["tool_response"])
    assert transform_output(payload, compress, contract=CLAUDE_CONTRACT) is None


def test_captured_native_mcp_failure_remains_passthrough():
    payload = native_fixture("mcp-error")
    assert payload["hook_event_name"] == "PostToolUseFailure"
    assert transform_output(payload, compress, contract=CLAUDE_CONTRACT) is None


def test_captured_native_structured_mcp_string_is_not_guessed_to_be_an_array():
    payload = native_fixture("mcp-structured")
    assert type(payload["tool_response"]) is str
    assert type(json.loads(payload["tool_response"])) is dict
    assert transform_output(payload, compress, contract=CLAUDE_CONTRACT) is None


def test_older_declared_contract_does_not_silently_gain_native_array_support():
    payload = native_fixture("mcp-json")
    assert transform_output(payload, compress, contract="claude-posttooluse-2026-10-04") is None


@pytest.mark.parametrize("field,value", [("error", "failure"), ("is_interrupt", True)])
def test_native_top_level_failure_flags_block_an_array_override(field, value):
    payload = native_fixture("mcp-json")
    payload[field] = value
    assert transform_output(payload, compress, contract=CLAUDE_CONTRACT) is None


def test_native_mcp_array_requires_an_explicit_success_event_and_known_tool():
    payload = native_fixture("mcp-json")
    payload.pop("hook_event_name")
    assert transform_output(payload, compress, contract=CLAUDE_CONTRACT) is None
    payload["hook_event_name"] = "PostToolUse"
    payload["tool_name"] = "Read"
    assert transform_output(payload, compress, contract=CLAUDE_CONTRACT) is None
