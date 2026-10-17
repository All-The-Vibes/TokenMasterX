"""Closed IPC protocol and stable effective-config receipts; no Docker/model calls."""
from copy import deepcopy
import hashlib
import json

import pytest

from brainspace.headroom import HeadroomContainer, DEFAULT_STRATEGY, DOCUMENT_STRATEGY


def adapter(tmp_path, *, strategy=DOCUMENT_STRATEGY):
    item = object.__new__(HeadroomContainer)
    item.strategy = strategy
    item._strategy_manifest = None
    item.directory = tmp_path
    item.failed = False
    return item


def request():
    return {"model": "fixture", "messages": [
        {"role": "user", "content": "Overview"},
        {"role": "assistant", "tool_calls": [{"id": "old", "type": "function", "function": {
            "name": "view", "arguments": '{"path":"notes.md"}'}}]},
        {"role": "tool", "tool_call_id": "old", "content": "old document"},
        {"role": "assistant", "tool_calls": [{"id": "new", "type": "function", "function": {
            "name": "view", "arguments": '{"path":"new.md"}'}}]},
        {"role": "tool", "tool_call_id": "new", "content": "newest document"},
    ]}


def response():
    manifest = {"strategy": DOCUMENT_STRATEGY, "source_commit": "pinned-by-worker"}
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                                      ensure_ascii=False).encode()).hexdigest()
    return {"messages": request()["messages"], "strategy": DOCUMENT_STRATEGY,
            "strategy_manifest": manifest, "strategy_manifest_sha256": digest,
            "eligible_indices": [2], "protected_indices": [0, 1, 3, 4]}


def test_default_operation_is_unchanged(tmp_path):
    item = adapter(tmp_path, strategy=DEFAULT_STRATEGY)
    seen = []
    item.rpc = lambda operation, **values: seen.append((operation, values)) or {
        "messages": request()["messages"]}
    assert item.prepare(request()) == request()
    assert seen == [("compress", {"model": "fixture", "messages": request()["messages"]})]
    assert not (tmp_path / "document-strategy.json").exists()


def test_document_controls_and_stable_manifest(tmp_path):
    item = adapter(tmp_path)
    seen = []
    item.rpc = lambda operation, **values: seen.append((operation, values)) or response()
    item.prepare(request(), eligible_indices=[2], frozen_message_count=1, keep_recent_tool_results=1)
    assert seen[0][0] == "compress_documents"
    assert seen[0][1]["eligible_indices"] == [2]
    assert seen[0][1]["frozen_message_count"] == 1
    saved = (tmp_path / "document-strategy.json").read_bytes()
    item.prepare(request(), eligible_indices=[2], frozen_message_count=1, keep_recent_tool_results=1)
    assert (tmp_path / "document-strategy.json").read_bytes() == saved


@pytest.mark.parametrize("indices", [None, [], [True], [-1], [5], [2, 2], [3, 2]])
def test_invalid_controls_never_rpc(tmp_path, indices):
    item = adapter(tmp_path)
    item.rpc = lambda *args, **kwargs: pytest.fail("must not dispatch")
    with pytest.raises(ValueError):
        item.prepare(request(), eligible_indices=indices)


@pytest.mark.parametrize("field,value", [
    ("strategy", "other"), ("strategy_manifest", None),
    ("strategy_manifest_sha256", "0" * 64), ("eligible_indices", [4]),
    ("protected_indices", [0, 1]),
])
def test_mismatched_receipt_poisoned(tmp_path, field, value):
    item = adapter(tmp_path)
    payload = response()
    payload[field] = value
    item.rpc = lambda *args, **kwargs: payload
    with pytest.raises(ValueError, match="manifest_mismatch"):
        item.prepare(request(), eligible_indices=[2])
    assert item.failed


def test_effective_config_cannot_drift_between_calls(tmp_path):
    item = adapter(tmp_path)
    payload = response()
    item.rpc = lambda *args, **kwargs: deepcopy(payload)
    item.prepare(request(), eligible_indices=[2])
    payload["strategy_manifest"]["changed"] = True
    payload["strategy_manifest_sha256"] = hashlib.sha256(json.dumps(
        payload["strategy_manifest"], sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()
    with pytest.raises(ValueError, match="manifest_mismatch"):
        item.prepare(request(), eligible_indices=[2])
