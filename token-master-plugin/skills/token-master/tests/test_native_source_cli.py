"""Source-contract CLI plumbing only; never launch native/model/container work."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import pytest

import brainspace_tools
from brainspace import native_cli, native_copilot, tokens


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ("native-full-view-v1", "native-view-result-v2")


@pytest.fixture(autouse=True)
def isolated_cli(monkeypatch):
    existing = os.environ.get("BRAINSPACE_TOKENIZER_FILE")
    if existing is None:
        monkeypatch.delenv("BRAINSPACE_TOKENIZER_FILE", raising=False)
    else:
        monkeypatch.setenv("BRAINSPACE_TOKENIZER_FILE", existing)
    for name in ("_TRIED", "_ENCODER", "_VERSION"):
        monkeypatch.setattr(tokens, name, getattr(tokens, name))

    def denied(*args, **kwargs):
        pytest.fail("native/model/socket work is forbidden")
    monkeypatch.setattr(native_copilot, "_execute", denied)
    monkeypatch.setattr(native_copilot, "NativeRuntime", denied)
    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def argv(tmp_path, extra=()):
    return [
        "--workspace", str(tmp_path), "--session", "source-cli", "native-copilot",
        "--native-executable", str(tmp_path / "explicit.exe"),
        "--output", str(tmp_path / "output"), "--base-url", "http://127.0.0.1:1/v1",
        "--model", "offline-fixture", "--tokenizer-file", str(tmp_path / "vocab"),
        "--prompt", "Read only.", "--allow-network", *extra,
    ]


@pytest.mark.parametrize("contract", [None, *CONTRACTS])
def test_parser_and_native_cli_forward_source_contract(tmp_path, monkeypatch, capsys, contract):
    extra = () if contract is None else ("--source-contract", contract)
    args = brainspace_tools._parser().parse_args(argv(tmp_path, extra))
    expected = contract or CONTRACTS[0]
    assert args.source_contract == expected
    monkeypatch.setattr(tokens, "backend_info", lambda: {"exact_reference": True})
    calls = []

    def run(**kwargs):
        calls.append(kwargs)
        return {"complete": True, "runtime": {"model_calls": 0}}

    monkeypatch.setattr(native_copilot, "run_native_copilot", run)
    assert native_cli.run_native_cli(args) == 0
    assert len(calls) == 1 and calls[0]["source_contract"] == expected
    # Selection belongs to the adapter, not RuntimePolicy serialization/IDs.
    from brainspace.runtime_policy import RuntimePolicy
    assert calls[0]["policy"].to_dict() == RuntimePolicy().to_dict()
    assert calls[0]["policy"].policy_id == RuntimePolicy().policy_id
    assert json.loads(capsys.readouterr().out)["complete"] is True
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("contract", ["", "native-view-result-v1", "other", "native-view-result-v2 "])
def test_parser_rejects_unknown_source_contract_without_output(tmp_path, contract):
    with pytest.raises(ValueError, match="invalid_arguments"):
        brainspace_tools._parser().parse_args(argv(tmp_path, ("--source-contract", contract)))
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("contract", [None, True, [], "other"])
def test_direct_cli_invalid_contract_precedes_tokenizer_environment_and_file_access(
    tmp_path, monkeypatch, contract,
):
    args = brainspace_tools._parser().parse_args(argv(tmp_path))
    args.source_contract = contract
    monkeypatch.setenv("BRAINSPACE_TOKENIZER_FILE", "unchanged-tokenizer-setting")
    monkeypatch.setattr(native_cli, "safe_root",
                        lambda *a: pytest.fail("invalid contract must not inspect paths"))
    with pytest.raises(ValueError, match="source_contract"):
        native_cli.run_native_cli(args)
    assert os.environ["BRAINSPACE_TOKENIZER_FILE"] == "unchanged-tokenizer-setting"
    assert not (tmp_path / "output").exists()


def test_minimal_copied_cli_parses_contracts_without_optional_native_imports(tmp_path):
    install = tmp_path / "minimal"
    install.mkdir()
    shutil.copy2(ROOT / "brainspace_tools.py", install / "brainspace_tools.py")
    # Existing minimal-installed CLI surface, intentionally without native_*,
    # runtime policy/resources, MCP, tokenizer packages, or win32 dependencies.
    for relative in (
        "__init__.py", "pipeline.py", "request_policy.py", "ccr.py", "router.py",
        "tokens.py", "task_mode.py", "compressors/__init__.py",
        "compressors/json_compressor.py", "compressors/code_compressor.py",
        "compressors/logs_compressor.py", "compressors/prose_compressor.py",
    ):
        destination = install / "brainspace" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "brainspace" / relative, destination)
    code = """
import json, sys
sys.path.insert(0, sys.argv[1])
import brainspace_tools
base = json.loads(sys.argv[2])
parser = brainspace_tools._parser()
assert parser.parse_args(base).source_contract == 'native-full-view-v1'
for value in ('native-full-view-v1', 'native-view-result-v2'):
    assert parser.parse_args(base + ['--source-contract', value]).source_contract == value
assert not any(name.startswith('brainspace.native_') for name in sys.modules)
print('minimal-source-contract-parser-ok')
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", code, str(install), json.dumps(argv(tmp_path))],
        cwd=install, capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "minimal-source-contract-parser-ok"
    assert not (tmp_path / "output").exists()
