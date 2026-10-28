"""Native CLI intent/configuration boundary; launcher replaced by a test stub."""
import json
import os
from pathlib import Path

import pytest

import brainspace_tools
from brainspace import native_cli, native_copilot, tokens


@pytest.fixture(autouse=True)
def restore_cli_process_state(monkeypatch):
    # The CLI owns one interpreter process. These unit calls deliberately run
    # in-process, so register all mutated globals for exact restoration.
    existing = os.environ.get("BRAINSPACE_TOKENIZER_FILE")
    # Register the missing key too: delenv records nothing for an unset key, and the CLI assigns it directly.
    monkeypatch.setenv("BRAINSPACE_TOKENIZER_FILE", existing if existing is not None else "")
    if existing is None:
        monkeypatch.delenv("BRAINSPACE_TOKENIZER_FILE")
    for name in ("_TRIED", "_ENCODER", "_VERSION"):
        monkeypatch.setattr(tokens, name, getattr(tokens, name))


def arguments(tmp_path, *, network=True, extra=()):
    values = [
        "--workspace", str(tmp_path), "--session", "explicit-session", "native-copilot",
        "--native-executable", str(tmp_path / "explicit.exe"),
        "--output", str(tmp_path.parent / "private-output"),
        "--base-url", "http://127.0.0.1:1/v1", "--model", "fixture",
        "--tokenizer-file", str(tmp_path / "vocab"), "--prompt", "Read the supplied file.",
    ]
    if network:
        values.append("--allow-network")
    return brainspace_tools._parser().parse_args([*values, *extra])


def test_native_cli_requires_explicit_network_before_launch(tmp_path, monkeypatch):
    monkeypatch.setattr(native_copilot, "run_native_copilot",
                        lambda **kwargs: pytest.fail("must not launch"))
    with pytest.raises(ValueError, match="network_and_session"):
        native_cli.run_native_cli(arguments(tmp_path, network=False))


def test_native_cli_missing_tokenizer_never_launches(tmp_path, monkeypatch):
    monkeypatch.setattr(native_copilot, "run_native_copilot",
                        lambda **kwargs: pytest.fail("must not launch"))
    monkeypatch.setattr(tokens, "backend_info", lambda: {"exact_reference": False})
    with pytest.raises(ValueError, match="verified_native_tokenizer"):
        native_cli.run_native_cli(arguments(tmp_path))


@pytest.mark.parametrize("complete,exit_code", [(True, 0), (False, 3)])
def test_native_cli_default_v6_and_compact_operational_output(
    tmp_path, monkeypatch, capsys, complete, exit_code,
):
    monkeypatch.setattr(tokens, "backend_info", lambda: {"exact_reference": True})
    calls = []

    def run(**kwargs):
        calls.append(kwargs)
        return {"complete": complete, "runtime": {"model_calls": 2,
                                                 "gateway_reported_tokens": None},
                "native_process": {"stdout": "PRIVATE_NATIVE_EVENT_CONTENT"}}

    monkeypatch.setattr(native_copilot, "run_native_copilot", run)
    args = arguments(tmp_path)
    assert native_cli.run_native_cli(args) == exit_code
    policy = calls[0]["policy"]  # the PRS-2/PRS-3 configuration
    assert (policy.backend, policy.instruction, policy.require_nonexpanding_input) == ("local", "none", True)
    assert policy.request_policy.version == "request-policy-v6" and policy.request_policy.enabled
    output = capsys.readouterr().out
    assert "PRIVATE_NATIVE_EVENT_CONTENT" not in output
    value = json.loads(output)
    assert value["quality_verified"] is None and value["policy_promoted"] is False
    assert value["gateway_reported_tokens"] is None
    assert Path(value["output"]).is_absolute()
