"""Explicit native Copilot registration; every configuration is temporary."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest


SKILL = Path(__file__).resolve().parents[1]


def load_setup():
    spec = importlib.util.spec_from_file_location("copilot_hook_setup_for_test",
                                                SKILL / "brainspace_setup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entry():
    return {"type": "command", "matcher": "view", "exec": "C:/fixed/python.exe",
            "args": ["fixed.py", "--host", "copilot"], "timeoutSec": 20}


@pytest.mark.parametrize("original", [
    {"theme": "keep"},
    {"theme": "keep", "hooks": {}},
    {"theme": "keep", "hooks": {"postToolUse": []}},
    {"theme": "keep", "hooks": {"postToolUse": [{"type": "command", "exec": "other"}],
                              "sessionStart": [{"type": "command", "exec": "also-other"}]}},
])
def test_copilot_hook_roundtrip_preserves_unrelated_and_empty_maps(tmp_path, original):
    from hosts import wire_copilot_hook

    path = tmp_path / "settings.json"
    path.write_text(json.dumps(original), encoding="utf-8")
    wire_copilot_hook(tmp_path, entry())
    installed = path.read_bytes()
    wire_copilot_hook(tmp_path, entry())
    assert path.read_bytes() == installed
    data = json.loads(installed)
    assert data["hooks"]["postToolUse"][-1] == entry()
    assert "PostToolUse" not in data["hooks"]
    wire_copilot_hook(tmp_path, None)
    assert json.loads(path.read_bytes()) == original


def test_update_preserves_order_relative_to_other_hooks(tmp_path):
    from hosts import wire_copilot_hook

    wire_copilot_hook(tmp_path, entry())
    path = tmp_path / "settings.json"
    data = json.loads(path.read_bytes())
    neighbor = {"type": "command", "exec": "later-hook"}
    data["hooks"]["postToolUse"].append(neighbor)
    path.write_text(json.dumps(data), encoding="utf-8")
    replacement = {**entry(), "timeoutSec": 15}
    wire_copilot_hook(tmp_path, replacement)
    assert json.loads(path.read_bytes())["hooks"]["postToolUse"] == [replacement, neighbor]


@pytest.mark.parametrize("edit_kind", ["edited", "duplicated", "foreign-identical"])
def test_ownership_conflicts_preserve_configuration(tmp_path, edit_kind):
    from hosts import wire_copilot_hook

    path = tmp_path / "settings.json"
    if edit_kind == "foreign-identical":
        path.write_text(json.dumps({"hooks": {"postToolUse": [entry()]}}), encoding="utf-8")
    else:
        wire_copilot_hook(tmp_path, entry())
        data = json.loads(path.read_bytes())
        if edit_kind == "edited":
            data["hooks"]["postToolUse"][0]["exec"] = "user-edited"
        else:
            data["hooks"]["postToolUse"].append(entry())
        path.write_text(json.dumps(data), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        wire_copilot_hook(tmp_path, entry())
    assert path.read_bytes() == before


@pytest.mark.parametrize("bad", [{"hooks": []}, {"hooks": {"postToolUse": {}}},
                               {"hooks": {"postToolUse": ["shell text"]}}])
def test_malformed_direct_hook_shape_is_not_guessed(tmp_path, bad):
    from hosts import wire_copilot_hook

    path = tmp_path / "settings.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        wire_copilot_hook(tmp_path, entry())
    assert path.read_bytes() == before


def test_absent_owned_hook_uninstall_is_noop(tmp_path):
    from hosts import wire_copilot_hook

    path = tmp_path / "settings.json"
    original = b'{"disableAllHooks":true,"hooks":{"postToolUse":[{"exec":"other"}]}}\n'
    path.write_bytes(original)
    wire_copilot_hook(tmp_path, None)
    assert path.read_bytes() == original


def test_self_contained_exec_argv_with_verified_tokenizer_path(tmp_path):
    from hosts.runtime import copilot_hook_entry

    script = tmp_path / "installed 空白" / "brainspace_posttooluse.py"
    vocabulary = tmp_path / "installed 空白" / "tokenizer" / "cl100k_base.tiktoken"
    command = copilot_hook_entry(sys.executable, script, vocabulary)
    assert command["type"] == "command"
    assert command["matcher"] == "view"
    assert command["exec"] == str(Path(sys.executable).absolute())
    assert command["args"] == [
        "-X", "utf8", str(script.resolve()), "--host", "copilot",
        "--contract", "copilot-posttooluse-2026-10-09",
        "--tokenizer-file", str(vocabulary.resolve()),
    ]
    assert "powershell" not in command and "bash" not in command


@pytest.mark.parametrize("host", ["claude", "codex"])
def test_copilot_opt_in_rejects_other_host_before_mutation(tmp_path, monkeypatch, host):
    for name in ("HOME", "USERPROFILE", "COPILOT_HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR"):
        monkeypatch.setenv(name, str(tmp_path / name))
    setup = load_setup()
    monkeypatch.setattr(sys, "argv", [
        "brainspace_setup.py", "--host", host, "--copilot-output-hook",
    ])
    assert setup.main() == 1
    assert not any(tmp_path.iterdir())


def test_user_disabled_hooks_not_silently_enabled(tmp_path, monkeypatch):
    home = tmp_path / "copilot"
    home.mkdir()
    settings = home / "settings.json"
    settings.write_text('{"disableAllHooks":true}', encoding="utf-8")
    monkeypatch.setenv("COPILOT_HOME", str(home))
    setup = load_setup()
    monkeypatch.setattr(sys, "argv", [
        "brainspace_setup.py", "--host", "copilot", "--copilot-output-hook",
    ])
    assert setup.main() == 1
    assert json.loads(settings.read_bytes()) == {"disableAllHooks": True}
    assert not (home / "mcp-config.json").exists()
    assert not (home / "token-master").exists()


def test_edited_hook_blocks_uninstall_before_mcp_is_removed(tmp_path, monkeypatch):
    from hosts import config_path, wire_copilot_hook, wire_mcp

    home = tmp_path / "copilot"
    monkeypatch.setenv("COPILOT_HOME", str(home))
    wire_mcp("copilot", "brainspace", {"command": "owned-interpreter", "args": []})
    wire_copilot_hook(home, entry())
    settings = home / "settings.json"
    data = json.loads(settings.read_bytes())
    data["hooks"]["postToolUse"][0]["exec"] = "user-edited-command"
    settings.write_text(json.dumps(data), encoding="utf-8")
    mcp = config_path("copilot")
    before = {path: path.read_bytes() for path in (mcp, settings)}
    setup = load_setup()
    monkeypatch.setattr(sys, "argv", [
        "brainspace_setup.py", "--host", "copilot", "--uninstall",
        "--python", "deliberately-unavailable",
    ])
    assert setup.main() == 1
    assert all(path.read_bytes() == content for path, content in before.items())
