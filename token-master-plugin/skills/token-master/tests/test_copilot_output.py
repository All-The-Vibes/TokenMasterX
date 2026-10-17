"""Offline Copilot hook contract checks, not native-host qualification."""
from copy import deepcopy
import io
import json
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

import brainspace_posttooluse as hook
from brainspace import host_output, tokens
from brainspace.compressors.json_compressor import compress_json
from brainspace.router import route_typed


CONTRACT = "copilot-posttooluse-2026-10-09"
TEXT = r'''{
    "negative_zero": -0,
    "precise": 1.00000000000000000001,
    "exponent": 1e400,
    "duplicate": 1,
    "duplicate": 2,
    "string": "\u0061  b\tquoted \"x\"\\path 雪🙂",
    "error": "an ordinary successful JSON data member",
    "items": [
        1,
        true,
        null,
        { "nested": [ 2, 3, 4 ] }
    ]
}'''
COMPACT = (
    r'{"negative_zero":-0,"precise":1.00000000000000000001,"exponent":1e400,'
    r'"duplicate":1,"duplicate":2,"string":"\u0061  b\tquoted \"x\"\\path 雪🙂",'
    r'"error":"an ordinary successful JSON data member","items":[1,true,null,{"nested":[2,3,4]}]}'
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline hook tests must not start processes or connect")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    # CLI tests exercise fresh explicit tokenizer selection inside this process.
    for name in ("_ENCODER", "_TRIED", "_VERSION"):
        monkeypatch.setattr(tokens, name, getattr(tokens, name))
    current = hook.os.environ.get("BRAINSPACE_TOKENIZER_FILE")
    # Register the missing key too: CLI main legitimately assigns it directly.
    monkeypatch.setenv("BRAINSPACE_TOKENIZER_FILE", current if current is not None else "")
    if current is None:
        monkeypatch.delenv("BRAINSPACE_TOKENIZER_FILE", raising=False)


def native_payload(text=TEXT):
    # Shape observed in hook-observer-001/hook-observations.jsonl.
    # Synthetic contents/IDs avoid a permanent dependency on workstation evidence.
    return {
        "sessionId": "offline-fixture",
        "timestamp": 1791500000000,
        "cwd": "C:/fixture",
        "toolName": "view",
        "toolArgs": {"path": "C:/fixture/資料.json"},
        "toolResult": {"resultType": "success", "textResultForLlm": text},
    }


def conservative(text, hint):
    return route_typed(text, hint, intent="conservative")[0]


def apply(payload=None, compress=conservative, **options):
    return host_output.transform_output(
        native_payload() if payload is None else payload, compress,
        contract=CONTRACT, min_chars=0, **options,
    )


def never(*args, **kwargs):
    pytest.fail("unsupported input must bypass before compression")


def test_native_success_changes_only_text_preserving_json_lexemes_and_metadata():
    payload = native_payload()
    before = deepcopy(payload)
    result = apply(payload)
    assert host_output.COPILOT_CONTRACT == CONTRACT
    assert result == {"modifiedResult": {"resultType": "success", "textResultForLlm": COMPACT}}
    assert payload == before
    assert result["modifiedResult"] is not payload["toolResult"]
    assert compress_json(TEXT, intent="conservative") == COMPACT
    old_wire, new_wire = tokens.serialize(payload["toolResult"]), tokens.serialize(result["modifiedResult"])
    assert tokens.count_tokens(new_wire) < tokens.count_tokens(old_wire)
    assert len(new_wire.encode("utf-8")) < len(old_wire.encode("utf-8"))
    assert set(result) == {"modifiedResult"}  # No context/history/footer channel.


def test_hint_comes_from_native_tool_args_path():
    seen = []

    def compress(text, hint):
        seen.append((text, hint))
        return COMPACT

    assert apply(compress=compress) is not None
    assert seen == [(TEXT, native_payload()["toolArgs"]["path"])]


@pytest.mark.parametrize("tool", ["Read", "read_file", "fetch_artifact", "bash", "mcp__view", "", None])
def test_only_native_view_is_qualified(tool):
    payload = native_payload()
    payload["toolName"] = tool
    assert apply(payload, never) is None


@pytest.mark.parametrize("status", ["error", "denied", "failure", "cancelled", "unknown", "Success", "", None, True])
def test_only_explicit_success_result_is_qualified(status):
    payload = native_payload()
    payload["toolResult"]["resultType"] = status
    assert apply(payload, never) is None


@pytest.mark.parametrize("extra", [
    {"error": "denied"}, {"isError": False}, {"interrupted": True},
    {"content": [{"type": "image", "data": "synthetic"}]},
    {"structuredContent": {"value": 1}}, {"text": TEXT},
    {"imageResultForLlm": "synthetic"}, {"metadata": {"opaque": "unqualified"}},
])
def test_mixed_structured_conflicting_or_unknown_result_fields_bypass(extra):
    payload = native_payload()
    payload["toolResult"].update(extra)
    snapshot = deepcopy(payload)
    assert apply(payload, never) is None
    assert payload == snapshot


@pytest.mark.parametrize("extra", [
    {"error": "denied"}, {"is_interrupt": True}, {"hook_event_name": "PostToolUseFailure"},
    {"tool_name": "Read"}, {"tool_input": {"path": "conflicting.py"}}, {"unknown": 1},
])
def test_unqualified_or_conflicting_top_level_fields_bypass(extra):
    payload = native_payload()
    payload.update(extra)
    assert apply(payload, never) is None


@pytest.mark.parametrize("field", ["sessionId", "timestamp", "cwd", "toolName", "toolArgs", "toolResult"])
def test_missing_native_envelope_fields_bypass(field):
    payload = native_payload()
    del payload[field]
    assert apply(payload, never) is None


@pytest.mark.parametrize("field,value", [
    ("sessionId", ""), ("sessionId", 1), ("timestamp", True), ("timestamp", "now"),
    ("cwd", ""), ("cwd", None), ("toolArgs", {}), ("toolArgs", {"path": None}),
    ("toolArgs", {"path": ""}), ("toolArgs", {"path": "x.json", "view_range": [1, 5]}),
    ("toolResult", TEXT), ("toolResult", []), ("toolResult", {}),
    ("toolResult", {"resultType": "success", "textResultForLlm": ["mixed"]}),
])
def test_unknown_or_malformed_native_shapes_bypass(field, value):
    payload = native_payload()
    payload[field] = value
    assert apply(payload, never) is None


@pytest.mark.parametrize("contract", ["", "copilot", "copilot-posttooluse-future", host_output.CLAUDE_CONTRACT, "codex"])
def test_unsupported_contracts_do_not_infer_another_host(contract):
    assert host_output.transform_output(native_payload(), never, contract=contract, min_chars=0) is None


def test_exact_contract_cannot_reinterpret_claude_payload():
    assert apply({"tool_name": "Read", "tool_response": {"type": "text", "file": {"content": TEXT}}}, never) is None


def test_minimum_size_bypasses_before_callback():
    assert host_output.transform_output(native_payload(), never, contract=CONTRACT, min_chars=len(TEXT) + 1) is None


@pytest.mark.parametrize("replacement", [TEXT, TEXT * 2, None, {"text": "wrong"}])
def test_unchanged_expanded_or_nontext_transform_is_noop(replacement):
    assert apply(compress=lambda *_: replacement) is None


def test_transform_failure_is_passthrough():
    def failed(*args):
        raise OSError("synthetic failure")

    assert apply(compress=failed) is None


def test_missing_exact_counter_is_passthrough(monkeypatch):
    monkeypatch.setattr(tokens, "_TRIED", True)
    monkeypatch.setattr(tokens, "_ENCODER", None)
    assert apply(compress=lambda *_: COMPACT) is None


def test_complete_result_not_just_text_is_token_guarded(monkeypatch):
    before = native_payload()["toolResult"]
    after = {**before, "textResultForLlm": COMPACT}
    assert tokens.count_tokens(COMPACT) < tokens.count_tokens(TEXT)
    seen = []

    def count(text):
        seen.append(text)
        return 100  # Final envelopes have equal cost, so they are not eligible.

    monkeypatch.setattr(tokens, "count_tokens", count)
    assert apply(compress=lambda *_: COMPACT) is None
    assert set(seen) == {tokens.serialize(before), tokens.serialize(after)}


def test_fewer_tokens_cannot_override_result_utf8_byte_growth(monkeypatch):
    # This injected counter isolates the independent byte guard.
    monkeypatch.setattr(tokens, "count_tokens", len)
    assert apply(native_payload("a" * 1000), lambda *_: "漢" * 500) is None


def test_final_stdout_cap_counts_utf8_envelope_inclusive_boundary():
    result = apply()
    assert result is not None
    cap = len(tokens.serialize(result).encode("utf-8"))
    assert apply(max_stdout_bytes=cap) == result
    assert apply(max_stdout_bytes=cap - 1) is None


@pytest.mark.parametrize("cap", [0, -1, True, "9000", None])
def test_invalid_stdout_cap_is_passthrough(cap):
    assert apply(max_stdout_bytes=cap) is None


def run_cli(monkeypatch, argv, payload=None, *, raw=None):
    data = (json.dumps(native_payload() if payload is None else payload, ensure_ascii=False).encode("utf-8")
            if raw is None else raw)
    output = io.BytesIO()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(data)))
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=output))
    monkeypatch.setenv("BRAINSPACE_HOOK_MIN_CHARS", "0")
    monkeypatch.setenv("BRAINSPACE_HOOK_STDOUT_CAP", "9000")
    monkeypatch.delenv("BRAINSPACE_INTENT", raising=False)
    assert hook.main(argv) == 0
    return output.getvalue()


def test_cli_explicit_copilot_opt_in_uses_conservative_router_without_storage(monkeypatch):
    monkeypatch.setattr(hook, "CCR", never)
    wire = run_cli(monkeypatch, ["--host", "copilot", "--contract", CONTRACT])
    assert json.loads(wire) == apply()
    assert wire == tokens.serialize(apply()).encode("utf-8")


def test_cli_installed_explicit_tokenizer_works_without_ambient_discovery(monkeypatch, tmp_path):
    source = tokens._vocabulary_path()
    assert source is not None and source.is_file()
    installed = tmp_path / "installed vocabulary" / "cl100k_base.tiktoken"
    installed.parent.mkdir()
    installed.write_bytes(source.read_bytes())
    monkeypatch.setenv("BRAINSPACE_TOKENIZER_FILE", str(tmp_path / "wrong-ambient-file"))
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path / "empty-cache"))
    monkeypatch.setattr(hook, "CCR", never)
    wire = run_cli(monkeypatch, ["--host", "copilot", "--contract", CONTRACT,
                                "--tokenizer-file", str(installed)])
    assert json.loads(wire)["modifiedResult"]["textResultForLlm"] == COMPACT
    assert tokens._vocabulary_path() == installed


@pytest.mark.parametrize("exists", [False, True])
def test_cli_invalid_explicit_tokenizer_cannot_use_previously_cached_encoder(monkeypatch, tmp_path, exists):
    assert tokens.count_tokens(TEXT) > 0
    assert tokens._ENCODER is not None
    bad = tmp_path / "invalid.tiktoken"
    if exists:
        bad.write_bytes(b"not-the-pinned-vocabulary")
    monkeypatch.setattr(hook, "CCR", never)
    assert run_cli(monkeypatch, ["--host", "copilot", "--contract", CONTRACT,
                                "--tokenizer-file", str(bad)]) == b""


@pytest.mark.parametrize("path,text", [
    ("source.py", "def example():\n    return 1\n"),
    ("guide.md", "# Heading\n\nKeep  this spacing.\n"),
    ("run.log", "[INFO] process succeeded\n"),
])
def test_cli_non_json_never_invokes_a_compressor(monkeypatch, path, text):
    payload = native_payload(text)
    payload["toolArgs"]["path"] = path
    monkeypatch.setattr(hook, "route_typed", never)
    monkeypatch.setattr(hook, "CCR", never)
    assert run_cli(monkeypatch, ["--host", "copilot", "--contract", CONTRACT], payload) == b""


@pytest.mark.parametrize("argv", [
    [], ["--host", "copilot"], ["--host", "codex"],
    ["--host", "copilot", "--contract", host_output.CLAUDE_CONTRACT],
    ["--host", "copilot", "--contract", "future"],
    ["--host", "codex", "--contract", CONTRACT],
    ["--host", "claude", "--contract", CONTRACT],
    ["--contract", CONTRACT],
])
def test_cli_unqualified_hosts_and_contracts_are_noop_before_input_or_storage(monkeypatch, argv):
    monkeypatch.setattr(hook, "CCR", never)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=SimpleNamespace(read=never)))
    output = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=output))
    assert hook.main(argv) == 0
    assert output.getvalue() == b""


@pytest.mark.parametrize("intent", ["overview", "navigation", "exact", "edit", "debug", "unknown"])
def test_copilot_contract_never_activates_lossy_or_protected_intent(monkeypatch, intent):
    monkeypatch.setattr(hook, "CCR", never)
    monkeypatch.setattr(hook, "route_typed", never)
    monkeypatch.setenv("BRAINSPACE_INTENT", intent)
    output = io.BytesIO()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(native_payload()).encode())))
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=output))
    assert hook.main(["--host", "copilot", "--contract", CONTRACT]) == 0
    assert output.getvalue() == b""


@pytest.mark.parametrize("raw", [
    b"", b"not-json", b"[]",
    json.dumps(native_payload()).replace('"resultType": "success"',
                                        '"resultType": "denied", "resultType": "success"').encode(),
    json.dumps(native_payload()).replace("1791500000000", "NaN").encode(),
])
def test_cli_malformed_or_ambiguous_payload_fails_closed(monkeypatch, raw):
    monkeypatch.setattr(hook, "CCR", never)
    assert run_cli(monkeypatch, ["--host", "copilot", "--contract", CONTRACT], raw=raw) == b""


@pytest.mark.parametrize("explicit", [False, True])
def test_claude_default_and_explicit_legacy_contract_are_unchanged(monkeypatch, explicit):
    monkeypatch.setattr(hook, "CCR", lambda **_: SimpleNamespace(stash=never))
    payload = {"hook_event_name": "PostToolUse", "tool_name": "Read", "tool_input": {"file_path": "x.json"},
               "tool_response": {"type": "text", "file": {"content": TEXT, "numLines": 20}}}
    argv = ["--host", "claude"]
    if explicit:
        argv += ["--contract", host_output.CLAUDE_CONTRACT]
    result = json.loads(run_cli(monkeypatch, argv, payload))
    assert result == {"hookSpecificOutput": {
        "hookEventName": "PostToolUse", "updatedToolOutput": {
            "type": "text", "file": {"content": COMPACT, "numLines": 20},
        },
    }}
