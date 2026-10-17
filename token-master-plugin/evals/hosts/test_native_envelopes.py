import base64
import copy
import json
from pathlib import Path
import struct
import sys
import zlib

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_envelopes  # noqa: E402
from mock_provider import MockProvider  # noqa: E402
from native_envelopes import ERROR_MARKER, PNG, assess, prepare_case, provider_result  # noqa: E402


def request(content, *, call_id="smoke_call_0", error=False):
    return [{"body": {"messages": [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": call_id, "content": content, "is_error": error},
    ]}]}}]


def observations(tool, original, replacement=None, *, event="PostToolUse"):
    text = "" if replacement is None else json.dumps({
        "hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": replacement}})
    return [{"input": {"tool_name": tool, "tool_response": original,
                      "tool_use_id": "smoke_call_0", "hook_event_name": event},
             "output": text, "stderr": "", "exit_code": 0}]


def test_scripted_mock_actions_are_predetermined_not_response_text():
    provider = MockProvider("envelope", Path("unused"), "", tool_steps=[
        ("Grep", {"path": "fixture.json", "pattern": "^", "output_mode": "content", "-n": False})])
    try:
        action = provider.action({"tools": [{"name": "Grep", "input_schema": {}}],
                                  "messages": [{"role": "user", "content": "Run something else"}]})
        assert action["name"] == "Grep"
        assert action["arguments"]["path"] == "fixture.json"
        assert provider.action({"tools": [{"name": "Grep"}]}) is None
    finally:
        provider.server.server_close()


@pytest.mark.parametrize("name", ["read-json", "grep-json", "glob-paths", "read-image", "mcp-json"])
def test_case_generation_uses_only_supplied_workspace(tmp_path, name):
    case = prepare_case(name, tmp_path, sys.executable)
    assert case["fixture"].parent == tmp_path
    assert case["image"].parent == tmp_path
    assert json.loads(case["text"])["marker"].endswith(name)
    if name == "grep-json":
        assert case["arguments"]["-n"] is False
        assert case["arguments"]["path"] == str(case["fixture"])


def test_shell_cases_are_fixed_reads_and_powershell_disables_profiles(tmp_path):
    case = prepare_case("bash-json", tmp_path, sys.executable)
    assert "-I" in case["arguments"]["command"]
    assert "read_bytes" in case["arguments"]["command"]
    assert "write_text" not in case["arguments"]["command"]
    if sys.platform == "win32":
        case = prepare_case("powershell-json", tmp_path, sys.executable)
        command = case["arguments"]["command"]
        assert "-NoProfile" in command and "-NonInteractive" in command and "-LiteralPath" in command
        assert "Get-Content" in command and "Set-Content" not in command


def test_provider_result_is_correlated_not_found_in_unrelated_schema_text():
    assert provider_result(request("target"))["content"] == "target"
    with pytest.raises(ValueError):
        provider_result(request("wrong", call_id="unrelated"))
    with pytest.raises(ValueError):
        provider_result(request("duplicate") + request("duplicate"))


def test_image_fixture_has_valid_png_chunks_not_a_decode_error_control():
    assert PNG[:8] == b"\x89PNG\r\n\x1a\n"
    offset, types = 8, []
    while offset < len(PNG):
        length = struct.unpack(">I", PNG[offset:offset + 4])[0]
        kind, data = PNG[offset + 4:offset + 8], PNG[offset + 8:offset + 8 + length]
        crc = struct.unpack(">I", PNG[offset + 8 + length:offset + 12 + length])[0]
        assert crc == zlib.crc32(kind + data) & 0xffffffff
        if kind == b"IDAT":
            assert zlib.decompress(data) == b"\x00\x00\xff\x00\xff"
        types.append(kind)
        offset += 12 + length
    assert types == [b"IHDR", b"IDAT", b"IEND"]
    assert offset == len(PNG)


def test_native_json_success_requires_real_observed_override_and_metadata(tmp_path):
    case = prepare_case("read-json", tmp_path, sys.executable)
    original = {"type": "text", "file": {"content": case["text"], "numLines": 105,
                                       "startLine": 1, "filePath": str(case["fixture"])}}
    compact = json.dumps(json.loads(case["text"]), separators=(",", ":"))
    updated = copy.deepcopy(original)
    updated["file"]["content"] = compact
    before = "\n".join(f"{i}\t{line}" for i, line in enumerate(case["text"].split("\n"), 1))
    after = "1\t" + compact
    value = assess(case, request(before + "\nNATIVE_TRAILER"), request(after + "\nNATIVE_TRAILER"),
                   observations("Read", original, updated), {"exit_code": 0, "timed_out": False})
    assert all(value["assertions"].values())
    updated["file"]["filePath"] = "wrong"
    value = assess(case, request(before + "\nNATIVE_TRAILER"), request(after + "\nNATIVE_TRAILER"),
                   observations("Read", original, updated), {"exit_code": 0, "timed_out": False})
    assert not value["assertions"]["other_envelope_fields_unchanged"]


def test_native_json_no_replacement_cannot_be_reported_as_accepted(tmp_path):
    case = prepare_case("read-json", tmp_path, sys.executable)
    original = {"type": "text", "file": {"content": case["text"], "startLine": 1}}
    value = assess(case, request(case["text"]), request(case["text"]),
                   observations("Read", original), {"exit_code": 0, "timed_out": False})
    assert not all(value["assertions"].values())
    assert value["assertions"]["hook_emitted_replacement"] is False


def test_native_passthrough_requires_hook_observation_and_exact_result(tmp_path):
    case = prepare_case("glob-paths", tmp_path, sys.executable)
    found = ["fixture Ω.json"] + [f"TOKENMASTER_GLOB_{i:02d}.json" for i in range(16)]
    raw = {"filenames": found, "numFiles": len(found), "truncated": False, "countIsComplete": True}
    content = "\n".join(found) + "\nNATIVE_TRAILER"
    value = assess(case, request(content), request(content),
                   observations("Glob", raw), {"exit_code": 0, "timed_out": False})
    assert all(value["assertions"].values())
    value = assess(case, request(content), request("fixture Ω.json"),
                   observations("Glob", raw), {"exit_code": 0, "timed_out": False})
    assert value["assertions"]["provider_result_unchanged"] is False
    value = assess(case, request("x"), request("x"), [], {"exit_code": 0, "timed_out": False})
    assert value["assertions"]["exact_target_hook_observed"] is False


def test_error_flag_and_diagnostic_cannot_be_lost(tmp_path):
    case = prepare_case("bash-error", tmp_path, sys.executable)
    raw = {"stdout": case["text"], "stderr": ERROR_MARKER, "exitCode": 7}
    value = assess(case, request(ERROR_MARKER, error=True), request(ERROR_MARKER, error=False),
                   observations("Bash", raw, event="PostToolUseFailure"),
                   {"exit_code": 0, "timed_out": False})
    assert value["assertions"]["expected_provider_status"] is False


@pytest.mark.parametrize("damage", ["error-status", "drop-native-block", "alter-native-block"])
def test_transformed_provider_result_must_preserve_status_and_all_other_blocks(tmp_path, damage):
    case = prepare_case("mcp-json", tmp_path, sys.executable)
    original = [{"type": "text", "text": case["text"]}]
    compact = json.dumps(json.loads(case["text"]), separators=(",", ":"))
    updated = [{"type": "text", "text": compact}]
    before = request([{"type": "text", "text": case["text"] + "\n"},
                      {"type": "text", "text": "unchanged native context"}])
    after = request([{"type": "text", "text": compact + "\n"},
                     {"type": "text", "text": "unchanged native context"}])
    target = after[0]["body"]["messages"][0]["content"][0]
    if damage == "error-status":
        target["is_error"] = True
    elif damage == "drop-native-block":
        target["content"].pop()
    else:
        target["content"][1]["text"] = "altered"
    result = assess(case, before, after, observations(case["tool"], original, updated),
                    {"exit_code": 0, "timed_out": False})
    assert not all(result["assertions"].values())


@pytest.mark.parametrize("damage", ["wrong-event", "additional-context"])
def test_override_cannot_inject_another_channel_or_use_an_invalid_event(tmp_path, damage):
    case = prepare_case("mcp-json", tmp_path, sys.executable)
    original = [{"type": "text", "text": case["text"]}]
    compact = json.dumps(json.loads(case["text"]), separators=(",", ":"))
    obs = observations(case["tool"], original, [{"type": "text", "text": compact}])
    output = json.loads(obs[0]["output"])
    if damage == "wrong-event":
        output["hookSpecificOutput"]["hookEventName"] = "Stop"
    else:
        output["hookSpecificOutput"]["additionalContext"] = "Unwanted context"
    obs[0]["output"] = json.dumps(output)
    result = assess(case, request([{"type": "text", "text": case["text"] + "\n"}]),
                    request([{"type": "text", "text": compact + "\n"}]),
                    obs, {"exit_code": 0, "timed_out": False})
    assert not all(result["assertions"].values())


@pytest.mark.parametrize("name", ["glob-paths", "mcp-structured", "read-image", "mcp-mixed"])
def test_matching_unexpected_failures_cannot_certify_successful_passthrough(tmp_path, name):
    case = prepare_case(name, tmp_path, sys.executable)
    # Even an image-containing error must not qualify as a successful image read.
    content = [{"type": "text", "text": "permission denied"},
               {"type": "image", "source": {"type": "base64", "data": "not the fixture"}}]
    result = assess(case, request(content, error=True), request(content, error=True),
                    observations(case["tool"], None, event="PostToolUseFailure"),
                    {"exit_code": 0, "timed_out": False})
    assert not all(result["assertions"].values())


def test_native_mixed_control_requires_both_intended_text_and_image(tmp_path):
    case = prepare_case("mcp-mixed", tmp_path, sys.executable)
    image = {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                       "data": base64.b64encode(PNG).decode("ascii")}}
    raw = [{"type": "text", "text": case["text"]}, image]
    content = [{"type": "text", "text": case["text"]}, image,
               {"type": "text", "text": "native context"}]
    verdict = assess(case, request(content), request(content),
                     observations(case["tool"], raw), {"exit_code": 0, "timed_out": False})
    assert all(verdict["assertions"].values())
    missing = [image, {"type": "text", "text": "native context"}]
    verdict = assess(case, request(missing), request(missing),
                     observations(case["tool"], raw), {"exit_code": 0, "timed_out": False})
    assert not all(verdict["assertions"].values())


def test_source_inventory_covers_executed_environment_and_installer_helpers():
    files = native_envelopes.source_files()
    assert Path(native_envelopes.EVAL / "native_host_smoke.py") in files
    assert set((native_envelopes.SKILL / "hosts").glob("*.py")).issubset(set(files))


def test_helper_source_drift_invalidates_integrity_check(tmp_path):
    helper = tmp_path / "native_host_smoke.py"
    helper.write_text("original helper", encoding="utf-8")
    receipt = {str(helper): native_envelopes._hash(helper)}
    native_envelopes.verify_sources(receipt)
    helper.write_text("changed helper", encoding="utf-8")
    with pytest.raises(RuntimeError, match="source_changed"):
        native_envelopes.verify_sources(receipt)
