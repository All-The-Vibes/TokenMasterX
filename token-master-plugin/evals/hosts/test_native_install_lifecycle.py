import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_install_lifecycle import (  # noqa: E402
    expected_uninstalled_mcp, expected_uninstalled_settings, installation_checks,
)


def installation_fixture():
    unrelated = {"matcher": "Read", "hooks": [{"command": "keep"}]}
    owned = {"matcher": "owned", "hooks": [{"command": "owned-hook"}]}
    before_settings = {"env": {"keep": "yes"}, "hooks": {"PostToolUse": [unrelated]},
                       "nativeAddedBeforeInstall": {"counter": 3}}
    before_mcp = {"mcpServers": {"unrelated": {"command": "keep"}},
                  "nativeAddedBeforeInstall": [1, False]}
    installed_settings, installed_mcp = copy.deepcopy(before_settings), copy.deepcopy(before_mcp)
    installed_settings["env"]["BRAINSPACE_TOKENIZER_FILE"] = "owned-file"
    installed_settings["hooks"]["PostToolUse"].append(owned)
    installed_mcp["mcpServers"]["brainspace"] = {"command": "owned"}
    return before_settings, before_mcp, installed_settings, installed_mcp, owned


def test_installation_accepts_only_owned_additions():
    assert all(installation_checks(*installation_fixture(), "owned-file").values())


@pytest.mark.parametrize("damage", ["modify-mcp", "delete-mcp", "modify-settings", "delete-settings"])
def test_install_time_unrelated_corruption_cannot_become_a_new_baseline(damage):
    before_settings, before_mcp, settings, mcp, owned = installation_fixture()
    if damage == "modify-mcp":
        mcp["mcpServers"]["unrelated"]["command"] = "changed"
    elif damage == "delete-mcp":
        mcp["mcpServers"].pop("unrelated")
    elif damage == "modify-settings":
        settings["nativeAddedBeforeInstall"]["counter"] = 4
    else:
        settings.pop("nativeAddedBeforeInstall")
    checks = installation_checks(before_settings, before_mcp, settings, mcp, owned, "owned-file")
    assert not all(checks.values())
    expected_failure = ("install_preserved_all_other_mcp_configuration"
                        if damage.endswith("mcp") else "install_preserved_all_other_settings")
    assert checks[expected_failure] is False


def test_uninstall_expectation_preserves_native_added_and_unrelated_fields():
    owned = {"matcher": "owned", "hooks": [{"command": "owned-hook"}]}
    unrelated = {"matcher": "Read", "hooks": [{"command": "keep"}]}
    settings = {"env": {"BRAINSPACE_TOKENIZER_FILE": "owned-file", "keep": "yes"},
                "hooks": {"PostToolUse": [unrelated, owned]},
                "nativeAddedField": {"counter": 3}}
    original = copy.deepcopy(settings)
    expected = expected_uninstalled_settings(settings, owned, "owned-file")
    assert expected == {"env": {"keep": "yes"}, "hooks": {"PostToolUse": [unrelated]},
                        "nativeAddedField": {"counter": 3}}
    assert settings == original
    entry = {"command": "owned-server", "args": ["unchanged"]}
    before = {"mcpServers": {"brainspace": entry, "unrelated": {"command": "keep"}},
              "nativeRunCounter": 4, "nestedNativeValue": [False, 1]}
    expected = expected_uninstalled_mcp(before, entry)
    assert expected == {"mcpServers": {"unrelated": {"command": "keep"}},
                        "nativeRunCounter": 4, "nestedNativeValue": [False, 1]}
    assert "brainspace" in before["mcpServers"]


def test_changed_owned_entries_are_not_silently_removed_from_expectation():
    with pytest.raises(ValueError):
        expected_uninstalled_mcp({"mcpServers": {"brainspace": {"command": "changed"}}},
                                 {"command": "original"})
    with pytest.raises(ValueError):
        expected_uninstalled_settings(
            {"env": {"BRAINSPACE_TOKENIZER_FILE": "changed"},
             "hooks": {"PostToolUse": [{"command": "owned"}]}},
            {"command": "owned"}, "expected",
        )


def test_duplicate_owned_hook_is_not_an_unambiguous_lifecycle():
    group = {"matcher": "owned", "hooks": []}
    with pytest.raises(ValueError):
        expected_uninstalled_settings(
            {"env": {"BRAINSPACE_TOKENIZER_FILE": "file"}, "hooks": {"PostToolUse": [group, group]}},
            group, "file",
        )
