"""Controller reservations bind actual runtime traces without post-hoc rewriting."""
from dataclasses import replace
import json

import pytest

from brainspace.request_policy import RequestPolicy
from brainspace.runtime import RuntimeSession
from test_product_runtime import Transport, request


def make(tmp_path, name, **changes):
    workspace = tmp_path / name / "workspace"
    workspace.mkdir(parents=True)
    options = dict(workspace=workspace, output=tmp_path / name / "run", session_id="same-host-session",
                   transport=Transport(), backend="local", phase="learning", learning_run_id="trial-7")
    return RuntimeSession(**(options | changes))


def test_pair_shares_reserved_task_but_not_actual_call_identity(tmp_path):
    task_id = "task:" + "a" * 64
    first = make(tmp_path, "first", task_id=task_id)
    second = make(tmp_path, "second", task_id=task_id, policy=replace(
        RequestPolicy(version="request-policy-v3", enabled=True, min_tool_chars=512),
        keep_recent_tool_results=2))
    first.invoke(request())
    second.invoke(request())
    a, b = first.finish()["trace"], second.finish()["trace"]
    assert a["task_id"] == b["task_id"] == task_id
    assert a["learning_run_id"] == b["learning_run_id"] == "trial-7"
    assert a["calls"][0]["task_id"] == b["calls"][0]["task_id"] == task_id
    assert a["calls"][0]["call_id"] != b["calls"][0]["call_id"]
    assert a["policy_id"] == first.policy.policy_id
    assert b["policy_id"] == second.policy.policy_id
    for session in (first, second):
        saved = json.loads((session.output / "session.json").read_text(encoding="utf-8"))
        assert saved["task_id"] == task_id and saved["run_id"] == session.run_id
        assert session.task_id != session.run_id
        session.close()


@pytest.mark.parametrize("task_id", ["", "../foreign", "with space", "a" * 257, 42, True])
def test_invalid_reserved_task_identity_is_rejected_before_run_directory(tmp_path, task_id):
    with pytest.raises(ValueError, match="reserved_task"):
        make(tmp_path, "bad", task_id=task_id)
    assert not (tmp_path / "bad/run").exists()


def test_default_identity_behavior_remains_unchanged(tmp_path):
    session = make(tmp_path, "default")
    assert session.task_id == session.run_id
    with pytest.raises(AttributeError):
        session.run_id = "replacement"
    session.invoke(request())
    result = session.finish()
    assert result["trace"]["calls"][0]["call_id"] == session.task_id + ":1"
    session.close()
