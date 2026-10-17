"""Cancellation cleanup mechanics; no real worker, model, or Docker execution."""
import json

import pytest

from brainspace import runtime
from brainspace.runtime import RuntimeSession
from brainspace.transport import ResponsesTransport


def make(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return RuntimeSession(
        workspace=workspace, output=tmp_path / "runtime", session_id="cleanup",
        transport=ResponsesTransport("http://127.0.0.1:1/unused", "offline-model"))


class Component:
    def __init__(self, *, repeated=False):
        self.close_calls = self.finish_calls = 0
        self.repeated = repeated
        self.interruption = KeyboardInterrupt("retain the original cancellation")

    def finish(self):
        self.finish_calls += 1
        return {"fixture": True}

    def close(self):
        self.close_calls += 1
        if self.close_calls == 1 or self.repeated:
            raise self.interruption
        return {"container_id": "owned-test-container", "container_removed": True}


def test_component_interrupt_cannot_skip_lease_release_or_runtime_receipt(tmp_path):
    session = make(tmp_path)
    component = Component()
    session._headroom = component  # Explicit in-memory lifecycle test double.
    reference = session.ccr.stash("owned source", source="owned.txt", ctype="source", kind="root")
    assert reference and session.ccr.stats()["pinned_entries"] == 1
    with pytest.raises(KeyboardInterrupt) as caught:
        session.close()
    assert caught.value is component.interruption
    assert session._closed and not session.cleanup_settled
    assert session.ccr.stats()["pinned_entries"] == 0
    first = json.loads((session.output / "cleanup.json").read_text("utf-8"))
    assert first["complete"] is False and first["interrupted"]
    assert first["released_leases"] == 1 and first["headroom_error_type"] == "KeyboardInterrupt"
    assert component.finish_calls == component.close_calls == 1
    second = session.close()
    assert second["complete"] and second["cleanup_attempt"] == 2 and session.cleanup_settled
    assert component.close_calls == 2 and component.finish_calls == 1
    assert json.loads((session.output / "cleanup.json").read_text("utf-8")) == first
    assert json.loads((session.output / "cleanup-retry-2.json").read_text("utf-8")) == second
    assert session.close() == second and component.close_calls == 2
    with pytest.raises(ValueError, match="closed"):
        session.invoke({"model": "offline-model", "messages": [{"role": "user", "content": "no retry"}]})


def test_repeated_interrupt_is_bounded_and_never_claims_settled(tmp_path):
    session = make(tmp_path)
    component = Component(repeated=True)
    session._headroom = component
    for _ in range(2):
        with pytest.raises(KeyboardInterrupt):
            session.close()
    assert not session.cleanup_settled
    assert session.close()["complete"] is False
    assert component.close_calls == 2 and component.finish_calls == 1
    assert (session.output / "cleanup.json").is_file()
    assert (session.output / "cleanup-retry-2.json").is_file()


def test_receipt_interruption_preserves_partial_file_and_physical_cleanup(tmp_path, monkeypatch):
    session = make(tmp_path)
    reference = session.ccr.stash("owned source", source="owned.txt", kind="root")
    assert reference and session.ccr.stats()["pinned_entries"] == 1
    original = runtime._write_new
    interruption = KeyboardInterrupt()

    def interrupted_write(path, value):
        if path.name == "cleanup.json":
            path.write_text('{"partial":', encoding="utf-8")
            raise interruption
        return original(path, value)

    monkeypatch.setattr(runtime, "_write_new", interrupted_write)
    with pytest.raises(KeyboardInterrupt) as caught:
        session.close()
    assert caught.value is interruption and session._closed and not session.cleanup_settled
    assert session.ccr.stats()["pinned_entries"] == 0
    assert (session.output / "cleanup.json").read_text("utf-8") == '{"partial":'
    unknown = json.loads((session.output / "cleanup-unconfirmed-1.json").read_text("utf-8"))
    assert unknown["complete"] is False and unknown["receipt_error_type"] == "KeyboardInterrupt"
    assert session.close()["complete"] is True and session.cleanup_settled
    assert (session.output / "cleanup.json").read_text("utf-8") == '{"partial":'


def test_finish_interrupt_still_releases_resources_and_preserves_cancellation(tmp_path, monkeypatch):
    session = make(tmp_path)
    reference = session.ccr.stash("owned source", source="owned.txt", kind="root")
    assert reference and session.ccr.stats()["pinned_entries"] == 1
    interruption = KeyboardInterrupt()
    seen = []

    def cancelled_finish(*args, **kwargs):
        seen.append("finish")
        raise interruption

    monkeypatch.setattr(session, "_finish", cancelled_finish)
    with pytest.raises(KeyboardInterrupt) as caught:
        session.close()
    assert caught.value is interruption
    assert session.ccr.stats()["pinned_entries"] == 0 and session.cleanup_settled
    receipt = session.close()
    assert receipt["complete"] and receipt["finalization_error_type"] == "KeyboardInterrupt"
    assert seen == ["finish"]  # No audit or model redispatch from repeated close.


def test_silent_lease_release_failure_is_not_complete(tmp_path, monkeypatch):
    session = make(tmp_path)
    assert session.ccr.stash("owned source", source="owned.txt", kind="root")
    monkeypatch.setattr(session.ccr, "release_session", lambda: 0)
    with pytest.raises(RuntimeError, match="release_unconfirmed"):
        session.close()
    assert not session.cleanup_settled
    receipt = json.loads((session.output / "cleanup.json").read_text("utf-8"))
    assert receipt["complete"] is False and receipt["remaining_session_leases"] == 1
