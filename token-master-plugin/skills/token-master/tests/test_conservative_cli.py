"""Exercise the opt-in conservative adapter through its actual offline CLI."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from brainspace.request_policy import PROTOCOL, RequestPolicy, SourceReadInfo


CLI = Path(__file__).resolve().parents[1] / "brainspace_tools.py"


def fixture():
    text = "def exact(value):\n" + "".join(
        f"    value_{i} = value + {i}\n" for i in range(100))
    messages = [{"role": "system", "content": "Keep these instructions unchanged."},
                {"role": "user", "content": "Explain the source."}]
    receipts = []
    for i, (path, content) in enumerate([
        ("source.py", text), ("source.py", text), ("other.py", "other"),
    ]):
        call_id = f"read-{i}"
        messages.extend([
            {"role": "assistant", "tool_calls": [{
                "type": "function", "id": call_id,
                "function": {"name": "read_file", "arguments": json.dumps({"path": path})},
            }]},
            {"role": "tool", "tool_call_id": call_id, "content": content},
        ])
        receipts.append(SourceReadInfo.from_text(
            call_id=call_id, tool_name="read_file", source_path=path,
            content=content, status="success").to_dict())
    return {"model": "offline-fixture", "messages": messages}, receipts


def run(tmp_path, *args, request=None, env=None):
    request = fixture()[0] if request is None else request
    return subprocess.run(
        [sys.executable, "-B", str(CLI), "--workspace", str(tmp_path), "request", *args],
        input=json.dumps(request).encode("utf-8"), capture_output=True,
        cwd=tmp_path, env=env, timeout=30,
    )


def receipt_file(tmp_path, value=None):
    path = tmp_path / "executor-receipts.json"
    path.write_text(json.dumps(fixture()[1] if value is None else value), encoding="utf-8")
    return str(path)


def test_conservative_cli_reuses_duplicate_without_state_or_new_instructions(tmp_path):
    request, _ = fixture()
    result = run(tmp_path, "--conservative", "--protocol", PROTOCOL,
                 "--source-reads", receipt_file(tmp_path))
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    output = json.loads(result.stdout)
    plan = output["plan"]
    assert plan["policy_id"] == RequestPolicy(
        version="request-policy-v3", enabled=True, min_tool_chars=512).policy_id
    assert plan["status"] == "transformed"
    assert plan["reason"] == "exact_visible_reuse"
    assert plan["changed_message_indices"] == [5]
    assert plan["tokens_after"] < plan["tokens_before"]
    assert plan["wire_bytes_after"] <= plan["wire_bytes_before"]
    assert plan["request"]["messages"][:5] == request["messages"][:5]
    assert plan["request"]["messages"][6:] == request["messages"][6:]
    assert "source_reads" not in plan["serialized"]
    assert not (tmp_path / ".token-master").exists()


@pytest.mark.parametrize("args,reason", [
    ([], "not_enabled"),
    (["--conservative"], "unsupported_protocol"),
    (["--conservative", "--protocol", PROTOCOL], "no_eligible_transform"),
])
def test_cli_defaults_and_missing_provenance_do_not_change_request(tmp_path, args, reason):
    request, receipts = fixture()
    # A model/request field is not a substitute for the trusted sideband file.
    request["source_reads"] = receipts
    result = run(tmp_path, *args, request=request)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)["plan"]
    assert plan["reason"] == reason
    assert plan["request"] == request
    assert not (tmp_path / ".token-master").exists()


@pytest.mark.parametrize("value", [
    {"not": "an array"}, [{"secret": "never-echo-this"}],
    [dict(fixture()[1][0], status="unproven")],
])
def test_cli_bad_receipts_fail_without_echoing_input(tmp_path, value):
    result = run(tmp_path, "--conservative", "--protocol", PROTOCOL,
                 "--source-reads", receipt_file(tmp_path, value))
    assert result.returncode == 2 and not result.stdout
    assert json.loads(result.stderr)["ok"] is False
    assert b"never-echo-this" not in result.stderr
    assert b"Traceback" not in result.stderr
    assert not (tmp_path / ".token-master").exists()


def test_cli_policy_and_conservative_are_mutually_exclusive(tmp_path):
    result = run(tmp_path, "--conservative", "--policy", RequestPolicy().to_json())
    assert result.returncode == 2 and not result.stdout
    assert json.loads(result.stderr)["ok"] is False


@pytest.mark.parametrize("version", ["request-policy-v1", "request-policy-v2"])
def test_legacy_policy_keeps_existing_fail_closed_intent_default(tmp_path, version):
    # Explicit enabling never silently chooses a lossy navigation/overview
    # intent. This was the CLI's behavior before V3 and remains compatible.
    policy = RequestPolicy(version=version, enabled=True)
    result = run(tmp_path, "--policy", policy.to_json(), "--protocol", PROTOCOL)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)["plan"]
    assert plan["reason"] == "no_eligible_transform"
    assert plan["request"] == fixture()[0]
    assert not (tmp_path / ".token-master").exists()


def test_cli_missing_reference_counter_keeps_original(tmp_path):
    result = run(
        tmp_path, "--conservative", "--protocol", PROTOCOL,
        "--source-reads", receipt_file(tmp_path),
        env=dict(os.environ, BRAINSPACE_TOKENIZER_FILE=str(tmp_path / "absent-vocabulary")),
    )
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)["plan"]
    assert plan["reason"] == "measurement_unavailable"
    assert plan["request"] == fixture()[0]
    assert not (tmp_path / ".token-master").exists()


def test_conservative_evaluation_arm_does_not_enable_task_mode():
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
    from source_read_adapter import ConservativeArm

    arm = ConservativeArm("tokenmaster_conservative")
    assert arm.scope is False and arm.views is True
    assert arm.policy.version == "request-policy-v3" and arm.policy.enabled is True


def test_real_installer_copy_contains_v3_and_runs_outside_checkout(tmp_path, monkeypatch):
    from brainspace_setup import _install_files

    home = tmp_path / "isolated-test-home"
    install = _install_files(home)
    assert (install / "brainspace" / "exact_reuse.py").is_file()
    monkeypatch.setattr(sys.modules[__name__], "CLI", install / "brainspace_tools.py")
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    result = run(tmp_path, "--conservative", "--protocol", PROTOCOL,
                 "--source-reads", receipt_file(tmp_path), env=environment)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)["plan"]
    assert plan["status"] == "transformed" and plan["changed_message_indices"] == [5]
    assert plan["request"]["messages"][3] == fixture()[0]["messages"][3]
    assert not (home / "mcp-config.json").exists()
    assert not (home / "settings.json").exists()
