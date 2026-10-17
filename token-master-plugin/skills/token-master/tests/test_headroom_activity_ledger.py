"""Stub-only lifetime Python ONNX boundary tests: no vendor imports/inference."""
from dataclasses import FrozenInstanceError
import importlib.util
import io
import json
from pathlib import Path
import sys
import threading
from typing import Any

import pytest

from brainspace import headroom_worker as worker


def test_between_rpc_events_and_late_terminal_revision_are_not_lost() -> None:
    ledger = worker.ActivityLedger()
    session = object()
    ledger.context("warmup")
    warm = ledger.start(session, {})
    ledger.terminal(warm, "completed")
    ready = ledger.snapshot()
    ledger.context("between_rpcs")
    late = ledger.start(session, {})
    first = ledger.snapshot(ready.revision)
    assert [event.event_id for event in first.events] == [late]
    assert first.events[0].state == "pending"
    ledger.context("rpc", "request-2")
    ledger.terminal(late, "completed")
    second = ledger.snapshot(first.revision)
    assert [event.event_id for event in second.events] == [late]
    assert second.events[0].revision > first.events[0].revision
    assert second.events[0].phase_at_entry == "between_rpcs"
    assert second.events[0].rpc_at_entry is None
    assert first.events[0].state == "pending"  # older snapshots never mutate
    final = ledger.snapshot()
    assert [event.event_id for event in final.events] == [warm, late]
    assert len({event.event_id for event in final.events}) == 2
    assert final.complete
    with pytest.raises(FrozenInstanceError):
        setattr(final.events[0], "state", "failed")


def test_wrapper_preserves_arguments_results_exceptions_and_cancellation() -> None:
    ledger = worker.ActivityLedger()
    session, output_names, feed, options = object(), ["out"], {"ids": object()}, object()
    result = object()
    seen: list[Any] = []

    def original(*args: Any, **kwargs: Any) -> object:
        seen.append((args, kwargs))
        return result

    wrapped = worker.observe_run(original, ledger)
    assert wrapped(session, output_names, feed, options, custom=True) is result
    assert seen == [((session, output_names, feed, options), {"custom": True})]
    assert ledger.snapshot().events[0].state == "completed"
    for failure in (RuntimeError("private contents"), KeyboardInterrupt()):
        def raises(*args: Any, **kwargs: Any) -> Any:
            raise failure
        with pytest.raises(type(failure)) as caught:
            worker.observe_run(raises, ledger)(session, input_feed=feed)
        assert caught.value is failure
    events = ledger.snapshot().events
    assert [event.state for event in events] == ["completed", "failed", "failed"]
    assert "private contents" not in json.dumps(ledger.inventory())


def test_background_thread_context_is_temporal_not_causal() -> None:
    ledger = worker.ActivityLedger()
    entered, release = threading.Event(), threading.Event()

    def original(*args: Any, **kwargs: Any) -> str:
        entered.set()
        assert release.wait(5)
        return "same-result"

    ledger.context("rpc", "compress-1")
    thread = threading.Thread(target=lambda: worker.observe_run(original, ledger)(object(), [], {}))
    thread.start()
    assert entered.wait(5)
    pending = ledger.snapshot()
    assert not pending.complete and pending.events[0].state == "pending"
    ledger.context("rpc", "finish-2")
    release.set()
    thread.join(5)
    assert not thread.is_alive()
    final = ledger.inventory()
    event = final["events"][0]
    assert event["phase_at_entry"] == "rpc" and event["rpc_at_entry"] == "compress-1"
    assert event["state"] == "completed"
    assert final["attribution"] == "temporal_context_at_entry_not_causal"
    assert final["local_inference_inventory_complete"] is False


def test_pending_final_is_unknown_not_completion_and_sessions_are_distinct() -> None:
    ledger = worker.ActivityLedger()
    a, b = object(), object()
    first, second = ledger.start(a, {}), ledger.start(b, {})
    third = ledger.start(a, {})
    inventory = ledger.inventory()
    assert not inventory["complete"]
    assert inventory["pending_ids"] == [first, second, third]
    events = inventory["events"]
    assert events[0]["session_id"] == events[2]["session_id"] != events[1]["session_id"]
    assert all(event["state"] == "pending" and event["start_state"] == "started"
               and event["seconds"] is None for event in events)


def test_bounded_overflow_reports_unknown_work_but_never_blocks_original_call() -> None:
    ledger = worker.ActivityLedger(max_events=1)
    calls: list[Any] = []

    def original(*args: Any, **kwargs: Any) -> str:
        calls.append(args)
        return "result"

    wrapped = worker.observe_run(original, ledger)
    session = object()
    assert wrapped(session, [], {}) == wrapped(session, [], {}) == "result"
    assert len(calls) == 2
    inventory = ledger.inventory()
    assert inventory["attempts"] == 2 and inventory["omitted_events"] == 1
    assert len(inventory["events"]) == 1 and not inventory["complete"]
    assert inventory["incomplete_reasons"] == ["event_limit"]


def test_shape_capture_is_bounded_defensive_and_never_consumes_feeds() -> None:
    ledger = worker.ActivityLedger()

    class Array:
        shape = (1, 2)
        dtype = "int64"

    class Hostile:
        @property
        def shape(self) -> Any:
            raise RuntimeError("no introspection")

    inputs = {"input_ids": Array(), "bad": Hostile()}
    worker.observe_run(lambda *a, **kw: inputs, ledger)(object(), [], inputs)
    event = ledger.inventory()["events"][0]
    assert event["input_shapes"] == {"input_ids": [1, 2]}
    assert event["input_dtypes"] == {"input_ids": "int64"}
    assert event["metadata_complete"] is False
    assert event["mask_counts"] is None  # not guessed from shape or tokenizer


def test_cumulative_final_is_authoritative_and_deltas_are_revision_upserts() -> None:
    ledger = worker.ActivityLedger()
    event_id = ledger.start(object(), {})
    before = ledger.snapshot()
    ledger.terminal(event_id, "failed", "RuntimeError")
    delta = ledger.inventory(before.revision)
    final = ledger.inventory()
    assert delta["semantics"] == "revision_upserts_not_additive_calls"
    assert final["semantics"] == "cumulative_latest_event_per_id"
    assert delta["events"][0]["event_id"] == final["events"][0]["event_id"]
    assert final["attempts"] == 1 and len(final["events"]) == 1


def test_frame_overflow_emits_small_explicit_incomplete_error(monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = worker.ActivityLedger()
    ledger.start(object(), {})
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(worker, "MAX_FRAME", 2048)
    assert worker.emit({"id": "finish", "ok": True, "result": {"large": "x" * 4000}},
                       ledger=ledger) is False
    raw = stream.getvalue()
    assert len(raw.encode()) <= 2048
    value = json.loads(raw)
    assert not value["ok"] and value["error_type"] == "ResponseFrameOverflow"
    inventory = value["python_onnx_inventory"]
    assert not inventory["complete"] and "frame_limit" in inventory["incomplete_reasons"]
    assert inventory["attempts"] == 1 and inventory["pending_count"] == 1
    assert inventory["events_omitted_from_frame"] == 1
    assert inventory["local_inference_inventory_complete"] is False


def test_worker_wiring_keeps_upstream_timing_and_final_inventory() -> None:
    source = Path(worker.__file__).read_text(encoding="utf-8")
    assert "observed.clear()" not in source and "before = len(observed)" not in source
    assert source.index("ort.InferenceSession.run =") < source.index("warmer.preload(allow_download=False)")
    assert "warmer._canary_thread.join(timeout=45)" in source
    assert "handler._execute_retrieval(" in source and "entry.original_content" in source
    assert 'value["python_onnx_inventory"] = _inventory(final)' in source
    assert '"local_inference_inventory_complete": False' in source


def test_parallel_calls_have_stable_unique_ids_and_atomic_terminal_snapshots() -> None:
    ledger = worker.ActivityLedger()
    barrier = threading.Barrier(17)
    release = threading.Event()
    session = object()

    def original(*args: Any, **kwargs: Any) -> None:
        barrier.wait(timeout=5)
        assert release.wait(5)

    wrapped = worker.observe_run(original, ledger)
    threads = [threading.Thread(target=lambda: wrapped(session, [], {})) for _ in range(16)]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=5)
    pending = ledger.snapshot()
    assert len(pending.events) == len(pending.pending_ids) == pending.attempts == 16
    assert len({event.event_id for event in pending.events}) == 16
    assert len({event.session_id for event in pending.events}) == 1
    release.set()
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive()
    done = ledger.snapshot(pending.revision)
    assert done.complete and len(done.events) == 16
    assert all(event.state == "completed" and event.seconds is not None for event in done.events)
    assert len({event.revision for event in done.events}) == 16
    assert all(event.revision > pending.revision for event in done.events)
    assert all(event.state == "pending" and event.seconds is None for event in pending.events)


def test_detached_inventory_cannot_mutate_ledger_and_terminal_is_single_use() -> None:
    ledger = worker.ActivityLedger()
    event = ledger.start(object(), {})
    exported = ledger.inventory()
    exported["events"][0]["state"] = "completed"
    exported["pending_ids"].clear()
    assert ledger.snapshot().events[0].state == "pending"
    ledger.terminal(event, "failed", "ExampleError")
    with pytest.raises(ValueError, match="already terminal"):
        ledger.terminal(event, "completed")
    with pytest.raises(ValueError, match="revision"):
        ledger.snapshot(ledger.snapshot().revision + 1)
    assert ledger.inventory()["events"][0]["state"] == "failed"


def test_metadata_inspection_exception_does_not_skip_or_replace_actual_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = worker.ActivityLedger()
    result = object()

    def broken_metadata(_: Any) -> Any:
        raise RuntimeError("metadata introspection failed")

    monkeypatch.setattr(worker, "_feed_metadata", broken_metadata)
    assert worker.observe_run(lambda *a, **kw: result, ledger)(object(), [], {}) is result
    event = ledger.inventory()["events"][0]
    assert event["state"] == "completed" and not event["metadata_complete"]
    assert event["input_shapes"] == {} and event["mask_counts"] is None


def test_metadata_limits_and_dtype_failure_stay_explicit() -> None:
    class Array:
        shape = (1, 512)
        dtype = "int64"

    ledger = worker.ActivityLedger()
    worker.observe_run(lambda *a, **kw: None, ledger)(
        object(), [], {f"input{i}": Array() for i in range(40)})
    row = ledger.inventory()["events"][0]
    assert len(row["input_shapes"]) == len(row["input_dtypes"]) == 32
    assert not row["metadata_complete"]
    assert row["mask_counts"] is None


@pytest.mark.parametrize("limit", [0, -1, True, 4097])
def test_event_bound_must_be_explicit_positive_integer(limit: Any) -> None:
    with pytest.raises(ValueError, match="event bound"):
        worker.ActivityLedger(max_events=limit)


def test_standalone_worker_import_needs_no_vendor_or_package_context() -> None:
    # Exercise the adapter's standalone source-copy loading convention directly.
    spec = importlib.util.spec_from_file_location("isolated_worker_ledger_test", worker.__file__)
    assert spec is not None and spec.loader is not None
    standalone = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(standalone)
    assert standalone.parse('{"ok":true}') == {"ok": True}
    assert standalone.ActivityLedger().inventory()["attempts"] == 0
