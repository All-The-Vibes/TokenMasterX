"""Shared description changes must not silently reroute or change tool schemas."""
import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
from quality.recovery_guidance import clarify_recovery_tools, absent_headroom_message  # noqa: E402


def tools():
    return [
        {"type": "function", "name": name, "description": "original " + name,
         "parameters": {"type": "object", "properties": {"value": {"type": "string"}}},
         "strict": True}
        for name in ("read_file", "retrieve_original", "search_original", "headroom_retrieve")
    ]


def test_descriptions_change_without_mutating_input_or_schema():
    original = tools()
    before = copy.deepcopy(original)
    result = clarify_recovery_tools(original)
    assert original == before
    for left, right in zip(original, result, strict=True):
        assert {key: value for key, value in left.items() if key != "description"} == \
            {key: value for key, value in right.items() if key != "description"}
    assert result[0] == original[0]


def test_br_markers_have_one_explicit_destination():
    result = {tool["name"]: tool for tool in clarify_recovery_tools(tools())}
    assert "[[BR:...]]" in result["retrieve_original"]["description"]
    assert "offset=0" in result["retrieve_original"]["description"]
    assert "Do not send TokenMaster" in result["retrieve_original"]["description"]
    assert "Do not use this for TokenMaster" in result["headroom_retrieve"]["description"]
    assert "<<ccr:...>>" in result["headroom_retrieve"]["description"]


@pytest.mark.parametrize("name", ["retrieve_original", "search_original", "headroom_retrieve"])
def test_missing_namespace_fails_closed(name):
    with pytest.raises(ValueError):
        clarify_recovery_tools([tool for tool in tools() if tool["name"] != name])


def test_duplicate_namespace_fails_closed():
    original = tools()
    with pytest.raises(ValueError):
        clarify_recovery_tools([*original, copy.deepcopy(original[-1])])


def test_wrong_tool_error_advises_without_retrieving_or_claiming_success():
    result = absent_headroom_message()
    assert "error" in result
    assert "retrieve_original" in result["recovery_guidance"]
    assert "original_content" not in result and "success" not in result
