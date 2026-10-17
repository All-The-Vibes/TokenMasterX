"""Real offline adapter and subprocess coverage; no provider success claims."""
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

from brainspace import tokens
from brainspace.ccr import CCR
from brainspace.pipeline import prepare_request, request_measurement_identity
from brainspace.request_policy import PROTOCOL, SERIALIZATION, RequestPolicy, serialize_request


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "brainspace_tools.py"
TEXT = json.dumps([{"id": i, "value": "漢字 café  literal " * 30} for i in range(30)],
                  ensure_ascii=False, indent=2)
POLICY = RequestPolicy(enabled=True, min_tool_chars=1)


def request():
    messages = [{"role": "system", "content": "Keep exact instructions."}]
    for i in range(2):
        messages.extend([
            {"role": "assistant", "tool_calls": [
                {"id": str(i), "type": "function",
                 "function": {"name": "read", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": str(i), "content": TEXT},
        ])
    return {"messages": messages, "metadata": {"literal": "漢字"}, "model": "fixture"}


def run_cli(workspace, *args, text="", session=None, env=None):
    command = [sys.executable, str(CLI), "--workspace", str(workspace)]
    if session is not None:
        command += ["--session", session]
    return subprocess.run(command + list(args), input=text.encode("utf-8"),
                          capture_output=True, cwd=workspace, env=env, timeout=30)


def plan(tmp_path, **kwargs):
    options = dict(policy=POLICY, protocol=PROTOCOL, intent="overview",
                   hint="rows.json", ccr=CCR(workspace_root=tmp_path))
    options.update(kwargs)
    return prepare_request(request(), **options)


def test_actual_router_request_root_roundtrip_and_final_wire(tmp_path):
    original = request()
    before = copy.deepcopy(original)
    store = CCR(workspace_root=tmp_path)
    result = prepare_request(original, POLICY, protocol=PROTOCOL, intent="overview", ccr=store)
    assert result.status == "transformed"
    assert result.changed_message_indices == (2,)
    view = result.request["messages"][2]["content"]
    ref = re.search(r"\[\[BR:.*?\]\]", view)[0]
    assert "kind=root" in ref
    assert store.retrieve(ref) == TEXT
    assert original == before
    assert result.request["messages"][4] == before["messages"][4]
    assert result.serialized == serialize_request(result.request)
    assert result.tokens_after == tokens.count_tokens(result.serialized) < result.tokens_before
    assert result.wire_bytes_after <= result.wire_bytes_before
    assert result.host_interception == "unsupported"
    identity = request_measurement_identity()
    assert identity["protocol_id"] == SERIALIZATION
    assert identity["exact_reference"] and not identity["provider_native"]
    assert identity["boundary"] == "serialized-request"


def test_root_added_when_router_only_compacts_json(tmp_path):
    result = plan(tmp_path, hint=None)
    assert result.status == "transformed"
    # Heterogeneous JSON is compacted rather than sampled, so the adapter adds a root.
    payload = request()
    payload["messages"][2]["content"] = json.dumps({"values": list(range(600))}, indent=8)
    result = prepare_request(payload, POLICY, protocol=PROTOCOL, intent="overview",
                             ccr=CCR(workspace_root=tmp_path))
    view = result.request["messages"][2]["content"]
    ref = re.search(r"\[\[BR:.*?\]\]", view)[0]
    assert "kind=root" in ref
    assert CCR(workspace_root=tmp_path).retrieve(ref) == payload["messages"][2]["content"]


@pytest.mark.parametrize("options,reason", [
    ({"policy": RequestPolicy()}, "not_enabled"),
    ({"protocol": "unknown"}, "unsupported_protocol"),
    ({"intent": "exact"}, "no_eligible_transform"),
    ({"stable_prefix_messages": 3}, "no_eligible_transform"),
    ({"exact_message_indices": (2,)}, "no_eligible_transform"),
    ({"policy": RequestPolicy(enabled=True, max_input_tokens=1)}, "cannot_safely_meet_budget"),
])
def test_passthrough_never_forces_budget_or_changes_protected_content(tmp_path, options, reason):
    result = plan(tmp_path, **options)
    assert result.request == request()
    assert result.reason == reason


def test_missing_tokenizer_and_broken_recovery_fail_closed(tmp_path, monkeypatch):
    store = CCR(workspace_root=tmp_path)
    monkeypatch.setattr(store, "retrieve", lambda _: "wrong original")
    assert plan(tmp_path, ccr=store).request == request()
    monkeypatch.setattr(tokens, "_TRIED", True)
    monkeypatch.setattr(tokens, "_ENCODER", None)
    assert plan(tmp_path).reason == "measurement_unavailable"


def test_final_reference_overhead_is_guarded(tmp_path):
    payload = request()
    payload["messages"][2]["content"] = '{ "a": 1, "b": 2 }'
    result = prepare_request(payload, POLICY, protocol=PROTOCOL, intent="overview",
                             ccr=CCR(workspace_root=tmp_path))
    assert result.request == payload
    assert result.reason == "no_eligible_transform"


@pytest.mark.parametrize("intent", ["conservative", "exact"])
def test_cli_literal_utf8_crlf_no_added_newline_or_state(tmp_path, intent):
    text = '@decorator\r\ndef work():\r\n\treturn "漢字  café"\r\n'
    result = run_cli(tmp_path, "compress", "--hint", "work.py", "--intent", intent, text=text)
    assert result.returncode == 0, result.stderr
    assert result.stdout == text.encode("utf-8")
    assert not result.stderr
    assert not (tmp_path / ".token-master").exists()


def test_cli_request_retrieve_search_and_disabled_default(tmp_path):
    payload = json.dumps(request(), ensure_ascii=False)
    disabled = run_cli(tmp_path, "request", text=payload)
    assert disabled.returncode == 0, disabled.stderr
    assert json.loads(disabled.stdout)["plan"]["reason"] == "not_enabled"
    assert not (tmp_path / ".token-master").exists()
    result = run_cli(tmp_path, "request", "--policy", POLICY.to_json(),
                     "--protocol", PROTOCOL, "--intent", "overview", text=payload, session="one")
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["plan"]["status"] == "transformed"
    assert value["measurement_identity"]["protocol_id"] == SERIALIZATION
    view = value["plan"]["request"]["messages"][2]["content"]
    ref = re.search(r"\[\[BR:.*?\]\]", view)[0]
    offset, chunks = 0, []
    while True:
        page = run_cli(tmp_path, "retrieve", ref, "--offset", str(offset),
                       "--limit", "32768", session="one")
        assert page.returncode == 0, page.stderr
        data = json.loads(page.stdout)
        chunks.append(data["content"])
        if data["complete"]:
            break
        offset = data["next_offset"]
    assert "".join(chunks) == TEXT
    search = run_cli(tmp_path, "search", ref, "café", "--limit", "2", session="one")
    data = json.loads(search.stdout)
    assert search.returncode == 0 and data["ok"] and len(data["results"]) == 2
    foreign = run_cli(tmp_path, "retrieve", ref, session="two")
    assert foreign.returncode != 0 and not json.loads(foreign.stdout)["ok"]


def contract_file(tmp_path):
    path = tmp_path / "contract.json"
    path.write_text(json.dumps({
        "version": "task-contract-v1", "required_result": "Verified result",
        "non_goals": [], "evidence": ["tests"], "stop_condition": "Tests pass",
    }), encoding="utf-8")
    return str(path.resolve())


@pytest.mark.parametrize("command", ["mode-enable", "mode-status", "mode-off"])
def test_persistent_commands_require_explicit_session(tmp_path, command):
    args = ["--contract", contract_file(tmp_path)] if command == "mode-enable" else []
    result = run_cli(tmp_path, command, *args)
    assert result.returncode == 2 and not result.stdout
    assert json.loads(result.stderr)["ok"] is False
    assert not (tmp_path / ".token-master").exists()


def test_task_ephemeral_and_off_preserves_other_session(tmp_path):
    contract = contract_file(tmp_path)
    result = run_cli(tmp_path, "mode-task", "--contract", contract)
    assert result.returncode == 0
    assert json.loads(result.stdout)["scope"] == "task"
    assert not (tmp_path / ".token-master").exists()
    for session in ("one", "two"):
        result = run_cli(tmp_path, "mode-enable", "--contract", contract, session=session)
        assert result.returncode == 0, result.stderr
    result = run_cli(tmp_path, "mode-off", session="one")
    assert result.returncode == 0 and not json.loads(result.stdout)["enabled"]
    assert json.loads(run_cli(tmp_path, "mode-status", session="two").stdout)["enabled"]


@pytest.mark.parametrize("args,text", [
    (["request"], '{"secret":"do-not-echo", broken}'),
    (["compress"], "x" * (1_048_576 + 1)),
    (["no-such-command", "do-not-echo"], ""),
    (["prepare-tokenizer", "vocabulary.txt"], ""),
], ids=["invalid-json", "oversized-input", "invalid-command", "download-not-enabled"])
def test_cli_safe_json_failures_and_input_bound(tmp_path, args, text):
    result = run_cli(tmp_path, *args, text=text)
    assert result.returncode == 2 and not result.stdout
    assert json.loads(result.stderr)["ok"] is False
    assert b"do-not-echo" not in result.stderr and b"Traceback" not in result.stderr


def test_cli_missing_tokenizer_is_offline_passthrough(tmp_path):
    env = dict(os.environ, BRAINSPACE_TOKENIZER_FILE=str(tmp_path / "missing-vocab"))
    result = run_cli(tmp_path, "request", "--policy", POLICY.to_json(),
                     "--protocol", PROTOCOL, "--intent", "overview",
                     text=json.dumps(request()), env=env)
    value = json.loads(result.stdout)
    assert result.returncode == 0 and value["plan"]["reason"] == "measurement_unavailable"
    assert value["plan"]["request"] == request()
    assert not (tmp_path / ".token-master").exists()


def test_prepare_command_delegates_only_explicit_opt_in(tmp_path, monkeypatch):
    import brainspace_tools
    calls = []
    monkeypatch.setattr(brainspace_tools, "prepare_tokenizer",
                        lambda path, **kwargs: calls.append((path, kwargs)))
    args = brainspace_tools._parser().parse_args([
        "--workspace", str(tmp_path), "prepare-tokenizer",
        str(tmp_path / "vocab"), "--allow-download",
    ])
    brainspace_tools.execute(args)
    assert calls == [((tmp_path / "vocab").resolve(), {"allow_download": True})]
    assert not (tmp_path / "vocab").exists()


def test_copied_install_has_no_repo_or_mcp_dependency(tmp_path, monkeypatch):
    install = tmp_path / "install"
    install.mkdir()
    shutil.copy2(CLI, install / CLI.name)
    for relative in [
        "__init__.py", "pipeline.py", "request_policy.py", "ccr.py", "router.py",
        "tokens.py", "task_mode.py", "compressors/__init__.py",
        "compressors/json_compressor.py", "compressors/code_compressor.py",
        "compressors/logs_compressor.py", "compressors/prose_compressor.py",
    ]:
        destination = install / "brainspace" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "brainspace" / relative, destination)
    monkeypatch.setattr(sys.modules[__name__], "CLI", install / CLI.name)
    result = run_cli(tmp_path, "request", "--protocol", PROTOCOL, "--intent", "overview",
                     "--policy", POLICY.to_json(), text=json.dumps(request()))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["plan"]["status"] == "transformed"
