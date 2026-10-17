import json

import pytest

from brainspace.task_mode import ModeStatus, TaskContract, render_task_mode, task_local_mode
from brainspace.tokens import count_tokens


def test_renderer_preserves_contract_without_machine_metadata():
    contract = TaskContract("Explain parser behavior.", ("No edits.",),
                            ("Use current source.",), "Stop after the explanation.")
    mode = task_local_mode(contract)
    text = render_task_mode(mode)
    for field in (contract.required_result, *contract.non_goals, *contract.evidence,
                  contract.stop_condition):
        assert field in text
    assert "session_id" not in text and "obedience_guaranteed" not in text
    assert count_tokens(text) < count_tokens(json.dumps(mode.to_dict()))
    assert text == render_task_mode(mode)


def test_disabled_mode_adds_no_prompt_text():
    assert render_task_mode(ModeStatus(False, "session", "s", None, "disabled")) == ""


def test_budget_is_advisory_and_does_not_erase_requested_depth():
    mode = task_local_mode(TaskContract("Give a full proof.", (), ("Show all assumptions.",),
                                       "Stop after verification.", output_budget=10))
    text = render_task_mode(mode)
    assert "10" in text and "advisory" in text.lower()
    assert "requested depth" in text
    assert "Give a full proof." in text


def test_unknown_or_inconsistent_mode_is_not_an_instruction():
    with pytest.raises(ValueError):
        render_task_mode({"enabled": True})
    with pytest.raises(ValueError):
        render_task_mode(ModeStatus(True, "task", None, None, "invalid"))
