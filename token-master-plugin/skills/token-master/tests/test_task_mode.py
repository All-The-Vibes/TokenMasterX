"""Task-local invocation never activates another task or session."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brainspace.task_mode import TaskContract, TaskModeStore, task_local_mode


def contract():
    return TaskContract(required_result="Explain only: trace the parser",
                        non_goals=("No edits", "No unrelated refactors"),
                        evidence=("Inspect the parser",),
                        stop_condition="The requested trace is explained",
                        output_budget=500)


def test_contract_json_validation_and_immutability():
    value = contract()
    assert TaskContract.from_json(value.to_json()) == value
    with pytest.raises(FrozenInstanceError):
        value.required_result = "other"
    for changes in [{"required_result": ""}, {"non_goals": "not a list"},
                    {"evidence": [1]}, {"output_budget": True},
                    {"output_budget": 0}, {"version": "future"}]:
        with pytest.raises(ValueError):
            TaskContract.from_dict({**value.to_dict(), **changes})
    with pytest.raises(ValueError):
        TaskContract.from_dict({**value.to_dict(), "unknown": True})


def test_task_local_mode_never_creates_durable_state(tmp_path):
    store = TaskModeStore(tmp_path / "state")
    result = task_local_mode(contract())
    assert result.enabled and result.scope == "task"
    assert result.session_id is None
    assert not result.obedience_guaranteed
    assert not store.status("session-a").enabled
    assert not (tmp_path / "state").exists()


def test_session_enable_off_status_roundtrip_no_other_session_leak(tmp_path):
    store = TaskModeStore(tmp_path / "state")
    first = store.enable("session-a", contract())
    assert first.enabled and first.scope == "session"
    assert TaskModeStore(store.root).status("session-a").contract == contract()
    assert not store.status("session-b").enabled
    store.enable("session-b", contract())
    second_path = store.path_for_session("session-b")
    before = second_path.read_bytes()
    assert not store.off("session-a").enabled
    assert not store.off("session-a").enabled
    assert second_path.read_bytes() == before
    assert store.status("session-b").enabled
    assert not store.status("later-session").enabled


def test_explicit_session_identity_no_ambient_fallback_or_path_escape(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_ID", "other")
    store = TaskModeStore(tmp_path / "state")
    for bad in ["", " ", None, 7]:
        with pytest.raises(ValueError):
            store.status(bad)
    session = "../other/🙂 session"
    store.enable(session, contract())
    assert store.path_for_session(session).parent == store.root
    assert store.status(session).enabled
    assert not store.status("other").enabled


@pytest.mark.parametrize("damage", ["invalid_json", "wrong_owner", "unknown_version", "extra_field"])
def test_damaged_or_foreign_state_fails_closed_without_overwrite(tmp_path, damage):
    store = TaskModeStore(tmp_path)
    store.enable("a", contract())
    path = store.path_for_session("a")
    data = json.loads(path.read_text("utf-8"))
    if damage == "invalid_json":
        path.write_text("{bad", encoding="utf-8")
    else:
        if damage == "wrong_owner":
            data["session_id"] = "b"
        elif damage == "unknown_version":
            data["version"] = "future"
        else:
            data["other_setting"] = "keep"
        path.write_text(json.dumps(data), encoding="utf-8")
    before = path.read_bytes()
    assert not store.status("a").enabled
    with pytest.raises(ValueError):
        store.enable("a", contract())
    with pytest.raises(ValueError):
        store.off("a")
    assert path.read_bytes() == before


def test_atomic_replace_failure_preserves_previous_state_and_cleans_only_own_temp(tmp_path, monkeypatch):
    store = TaskModeStore(tmp_path)
    store.enable("a", contract())
    before = store.path_for_session("a").read_bytes()
    unrelated = tmp_path / "unrelated.tmp"
    unrelated.write_text("keep")

    def fail(*_):
        raise OSError("disk unavailable")

    monkeypatch.setattr("brainspace.task_mode.os.replace", fail)
    with pytest.raises(OSError):
        store.enable("a", contract())
    assert store.path_for_session("a").read_bytes() == before
    assert unrelated.read_text() == "keep"
    assert len(list(tmp_path.iterdir())) == 2


def test_parallel_independent_sessions_do_not_lose_updates(tmp_path):
    store = TaskModeStore(tmp_path)
    sessions = [f"session-{n}" for n in range(12)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda session: store.enable(session, contract()), sessions))
    assert all(store.status(session).enabled for session in sessions)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(store.off, sessions[::2]))
    assert all(store.status(session).enabled == (index % 2 == 1)
               for index, session in enumerate(sessions))


def test_status_and_contract_are_json_ready_without_financial_fields(tmp_path):
    store = TaskModeStore(tmp_path)
    result = store.enable("a", contract())
    assert json.loads(json.dumps(result.to_dict()))["contract"] == contract().to_dict()
    assert result.to_dict()["obedience_guaranteed"] is False
    assert store.status("absent").to_dict()["contract"] is None


def test_symlinked_state_cannot_read_enable_or_remove_another_session(tmp_path):
    store = TaskModeStore(tmp_path)
    store.enable("b", contract())
    other = store.path_for_session("b")
    before = other.read_bytes()
    link = store.path_for_session("a")
    try:
        link.symlink_to(other)
    except OSError:
        pytest.skip("host does not permit symlink creation")
    assert not store.status("a").enabled
    with pytest.raises(ValueError):
        store.enable("a", contract())
    with pytest.raises(ValueError):
        store.off("a")
    assert link.is_symlink()
    assert other.read_bytes() == before
