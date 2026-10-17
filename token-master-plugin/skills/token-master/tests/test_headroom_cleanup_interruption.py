"""Cancellation-safe cleanup, fake Docker only; never start an actual component."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_headroom_product_boundary import IDENTITY, fake_engine, new_worker


def started(tmp_path, monkeypatch):
    worker = new_worker(tmp_path, monkeypatch)
    commands, state, process = fake_engine(worker, monkeypatch)
    worker.start()
    commands.clear()
    return worker, commands, state, process


def receipt(worker):
    return json.loads((worker.directory / "cleanup.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("operation", ["inspect", "stop", "rm"])
def test_interrupted_container_cleanup_retries_once_and_finishes_other_stages(
        tmp_path, monkeypatch, operation):
    worker, commands, _, process = started(tmp_path, monkeypatch)
    original, interrupted = worker.command, KeyboardInterrupt("private cancellation")
    attempts = []

    def command(args, **kwargs):
        attempts.append(args)
        if args[0] == operation and sum(c[0] == operation for c in attempts) == 1:
            raise interrupted
        return original(args, **kwargs)

    worker.command = command
    with pytest.raises(KeyboardInterrupt) as failure:
        worker.close()
    assert failure.value is interrupted
    saved = receipt(worker)
    assert saved["container_removed"] and saved["attach_client_reaped"]
    assert saved["worker_snapshot_unchanged"] and worker.stderr.closed and process.stdin.closed
    assert saved["complete"] is False and saved["cleanup_interrupted"] is True
    assert "private cancellation" not in json.dumps(saved)
    assert all(c[-1] == IDENTITY for c in commands)
    assert not any(c[0] in ("start", "create", "kill") for c in commands)
    assert sum(c[0] == "rm" for c in commands) == 1


@pytest.mark.parametrize("query", ["absent", "present", "failed", "interrupted"])
def test_rm_may_have_completed_but_absence_requires_successful_scoped_read(
        tmp_path, monkeypatch, query):
    worker, _, state, _ = started(tmp_path, monkeypatch)
    original, interrupted = worker.command, KeyboardInterrupt()
    removed, queries = False, []

    def command(args, **kwargs):
        nonlocal removed
        if args[0] == "inspect" and removed:
            return SimpleNamespace(returncode=1, stdout="")
        if args[0] == "ps":
            queries.append(args)
            assert args == ["ps", "--all", "--no-trunc", "--filter", "id=" + IDENTITY,
                            "--format", "{{.ID}}"]
            if query == "interrupted":
                raise SystemExit(17)
            return SimpleNamespace(returncode=1 if query == "failed" else 0,
                                   stdout=IDENTITY + "\n" if query == "present" else "")
        result = original(args, **kwargs)
        if args[0] == "rm":
            removed = True
            raise interrupted
        return result

    worker.command = command
    with pytest.raises(KeyboardInterrupt) as failure:
        worker.close()
    assert failure.value is interrupted
    saved = receipt(worker)
    assert len(queries) == 1
    assert saved.get("container_removed", False) is (query == "absent")
    assert saved.get("container_absence_verified", False) is (query == "absent")
    assert saved["attach_client_reaped"] and saved["worker_snapshot_unchanged"]
    assert not state["State"]["Running"]
    if query != "absent":
        assert saved["container_state"] in ("unknown", "unconfirmed")


@pytest.mark.parametrize("foreign", ["Id", "label"])
def test_retry_rechecks_identity_before_any_destructive_command(tmp_path, monkeypatch, foreign):
    worker, commands, state, _ = started(tmp_path, monkeypatch)
    original, interrupted = worker.command, KeyboardInterrupt()
    count = 0

    def command(args, **kwargs):
        nonlocal count
        if args[0] == "inspect":
            count += 1
            if count == 1:
                raise interrupted
            if foreign == "Id":
                state["Id"] = "b" * 64
            else:
                state["Config"]["Labels"]["tokenmaster.parity"] = "other-task"
        return original(args, **kwargs)

    worker.command = command
    with pytest.raises(KeyboardInterrupt) as failure:
        worker.close()
    assert failure.value is interrupted
    assert not any(c[0] in ("stop", "rm") for c in commands)
    saved = receipt(worker)
    assert saved["container_state"] == "unknown" and saved["attach_client_reaped"]
    assert saved["worker_snapshot_unchanged"] and worker.stderr.closed


def test_repeated_container_interruption_is_bounded_and_first_interrupt_wins(tmp_path, monkeypatch):
    worker, _, _, _ = started(tmp_path, monkeypatch)
    first, second = KeyboardInterrupt(), SystemExit(23)
    inspections = []

    def command(args, **kwargs):
        assert args == ["inspect", IDENTITY]
        inspections.append(args)
        raise first if len(inspections) == 1 else second

    worker.command = command
    with pytest.raises(KeyboardInterrupt) as failure:
        worker.close()
    assert failure.value is first and len(inspections) == 2
    saved = receipt(worker)
    assert saved["container_state"] == "unknown" and not saved.get("container_removed", False)
    assert saved["attach_client_reaped"] and worker.stderr.closed and saved["worker_snapshot_unchanged"]
    assert len(saved["interruptions"]) == 2


@pytest.mark.parametrize("grace", [False, True])
def test_wait_interruption_still_reaps_attach_and_records_cleanup(tmp_path, monkeypatch, grace):
    worker, commands, _, process = started(tmp_path, monkeypatch)
    worker.finished = grace
    original, interrupted, waits = process.wait, KeyboardInterrupt(), []

    def wait(timeout):
        waits.append(timeout)
        if len(waits) == 1:
            raise interrupted
        return original(timeout)

    process.wait = wait
    with pytest.raises(KeyboardInterrupt) as failure:
        worker.close()
    assert failure.value is interrupted and len(waits) <= 4
    saved = receipt(worker)
    assert saved["container_removed"] and saved["attach_client_reaped"]
    assert saved["worker_snapshot_unchanged"] and worker.stderr.closed and process.stdin.closed
    assert sum(c[0] == "rm" for c in commands) == 1


def test_receipt_interruption_gets_one_retry_after_remaining_stages(tmp_path, monkeypatch):
    worker, _, _, process = started(tmp_path, monkeypatch)
    original, interrupted, writes = Path.write_text, KeyboardInterrupt(), []

    def write(path, data, *args, **kwargs):
        if path == worker.directory / "cleanup.json":
            writes.append(data)
            assert worker.stderr.closed and process.stdin.closed
            assert json.loads(data)["worker_snapshot_unchanged"]
            if len(writes) == 1:
                raise interrupted
        return original(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", write)
    with pytest.raises(KeyboardInterrupt) as failure:
        worker.close()
    assert failure.value is interrupted and len(writes) == 2
    saved = receipt(worker)
    assert saved["cleanup_interrupted"] and saved["container_removed"] and saved["attach_client_reaped"]
    assert saved["complete"] is False


def test_stderr_interruption_does_not_skip_worker_hash_or_receipt(tmp_path, monkeypatch):
    worker, _, _, _ = started(tmp_path, monkeypatch)
    worker.stderr.close()
    interrupted = KeyboardInterrupt()

    class Stream:
        def close(self):
            raise interrupted

    worker.stderr = Stream()
    with pytest.raises(KeyboardInterrupt) as failure:
        worker.close()
    assert failure.value is interrupted
    saved = receipt(worker)
    assert saved["worker_snapshot_unchanged"] and saved["attach_client_reaped"]
    assert saved["stderr_close_error"] == "KeyboardInterrupt" and saved["complete"] is False


def test_repeated_receipt_interruption_is_bounded_and_retained_in_memory(tmp_path, monkeypatch):
    worker, _, _, _ = started(tmp_path, monkeypatch)
    first, second, writes = KeyboardInterrupt(), SystemExit(5), []
    original = Path.write_text

    def write(path, data, *args, **kwargs):
        if path == worker.directory / "cleanup.json":
            writes.append(data)
            raise first if len(writes) == 1 else second
        return original(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", write)
    with pytest.raises(KeyboardInterrupt) as failure:
        worker.close()
    assert failure.value is first and len(writes) == 2
    assert worker._cleanup_receipt["complete"] is False
    assert worker._cleanup_receipt["receipt_write_error"] == "SystemExit"
    assert worker._cleanup_receipt["worker_snapshot_unchanged"] and worker.stderr.closed


def test_worker_hash_interruption_still_persists_honest_unknown(tmp_path, monkeypatch):
    worker, _, _, _ = started(tmp_path, monkeypatch)
    original, interrupted = Path.read_bytes, KeyboardInterrupt()

    def read(path):
        if path == worker.worker_snapshot:
            raise interrupted
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    with pytest.raises(KeyboardInterrupt) as failure:
        worker.close()
    assert failure.value is interrupted
    saved = receipt(worker)
    assert saved["container_removed"] and saved["attach_client_reaped"] and worker.stderr.closed
    assert saved["worker_snapshot_unchanged"] is False and saved["complete"] is False


def test_repeated_attach_interruptions_do_not_skip_receipt_or_loop(tmp_path, monkeypatch):
    worker, _, _, process = started(tmp_path, monkeypatch)
    first, waits = KeyboardInterrupt(), []

    def wait(timeout):
        waits.append(timeout)
        raise first if len(waits) == 1 else SystemExit(9)

    process.wait = wait
    with pytest.raises(KeyboardInterrupt) as failure:
        worker.close()
    assert failure.value is first and waits == [3, 5, 5]
    saved = receipt(worker)
    assert saved["container_removed"] and worker.stderr.closed and saved["worker_snapshot_unchanged"]
    assert not saved.get("attach_client_reaped", False) and saved["complete"] is False


def test_cancellation_is_preserved_over_prior_ordinary_cleanup_error(tmp_path, monkeypatch):
    worker, _, _, process = started(tmp_path, monkeypatch)
    interrupted = KeyboardInterrupt()

    def command(*args, **kwargs):
        raise RuntimeError("ordinary cleanup failure")

    original, count = process.wait, 0

    def wait(timeout):
        nonlocal count
        count += 1
        if count == 1:
            raise interrupted
        return original(timeout)

    worker.command, process.wait = command, wait
    with pytest.raises(KeyboardInterrupt) as failure:
        worker.close()
    assert failure.value is interrupted
    saved = receipt(worker)
    assert saved["cleanup_error_type"] == "RuntimeError" and saved["container_state"] == "unknown"
    assert saved["attach_client_reaped"] and worker.stderr.closed and saved["worker_snapshot_unchanged"]


@pytest.mark.parametrize("query", ["absent", "failed", "present"])
def test_second_close_reconciles_removed_container_without_losing_first_interrupt(
        tmp_path, monkeypatch, query):
    worker, commands, _, _ = started(tmp_path, monkeypatch)
    original, interrupted = worker.command, KeyboardInterrupt()
    removed, interrupted_once, queries = False, False, []

    def command(args, **kwargs):
        nonlocal removed, interrupted_once
        if args[0] == "inspect" and removed:
            return SimpleNamespace(returncode=1, stdout="")
        if args[0] == "ps":
            queries.append(args)
            assert args == ["ps", "--all", "--no-trunc", "--filter", "id=" + IDENTITY,
                            "--format", "{{.ID}}"]
            return SimpleNamespace(returncode=1 if query == "failed" else 0,
                                   stdout=IDENTITY if query == "present" else "")
        if args[0] == "inspect" and not interrupted_once:
            interrupted_once = True
            raise interrupted
        result = original(args, **kwargs)
        if args[0] == "rm":
            removed = True
        return result

    worker.command = command
    with pytest.raises(KeyboardInterrupt) as failure:
        worker.close()
    assert failure.value is interrupted
    first = receipt(worker)
    assert first["container_removed"] and first["complete"] is False
    second = worker.close()
    assert second["complete"] is (query == "absent")
    assert second.get("container_absence_verified", False) is (query == "absent")
    assert second["attach_client_reaped"] and len(queries) == 1
    archived = json.loads((worker.directory / second["prior_cleanup_receipt"]).read_text(encoding="utf-8"))
    assert archived == first and archived["cleanup_interrupted"]
    assert receipt(worker) == second
    assert sum(c[0] == "rm" for c in commands) == 1
    assert not any(c[0] in ("start", "create", "kill") for c in commands)


@pytest.mark.parametrize("change", ["identity", "label"])
def test_repeated_close_cannot_change_frozen_cleanup_owner(tmp_path, monkeypatch, change):
    worker, commands, _, _ = started(tmp_path, monkeypatch)
    worker.close()
    first = receipt(worker)
    commands.clear()
    if change == "identity":
        worker.identity = "b" * 64
    else:
        worker.label = "other-task"
    with pytest.raises(ValueError, match="ownership"):
        worker.close()
    assert commands == [] and receipt(worker) == first
