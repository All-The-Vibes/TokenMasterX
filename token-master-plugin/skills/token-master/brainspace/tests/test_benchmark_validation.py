"""Recovery evidence must exercise the actual store, not just parse markers."""
from __future__ import annotations

import json

import pytest

from brainspace import benchmark
from brainspace.ccr import make_placeholder
from brainspace.router import ContentType


class Store:
    def __init__(self, mode="exact"):
        self.mode = mode
        self.originals = {}
        self.calls = []

    def stash(self, content, **_):
        ref = make_placeholder("012345abcdef", ctype="test")
        self.originals[ref] = content
        return ref

    def retrieve(self, ref):
        self.calls.append(ref)
        if self.mode == "missing":
            return None
        if self.mode == "wrong":
            return "incorrect original"
        if self.mode == "error":
            raise ValueError("corrupt")
        return self.originals.get(ref)


def root_view(content, hint, *, stash, **_):
    return stash(content), ContentType.LOG


@pytest.mark.parametrize("mode", ["missing", "wrong", "error"])
def test_bad_original_fails_actual_validation(monkeypatch, mode):
    monkeypatch.setattr(benchmark, "route_typed", root_view)
    store = Store(mode)
    row = benchmark.benchmark_one("fixture", "original " * 100, "fixture.log", store)
    assert store.calls, "the recovery oracle must actually call retrieve"
    assert row.recovery_status == "failed"
    assert row.checked_references == 1
    assert not row.recovery_valid
    assert row.lossless is False


def test_full_original_is_checked_for_equality(monkeypatch):
    monkeypatch.setattr(benchmark, "route_typed", root_view)
    store = Store()
    row = benchmark.benchmark_one("fixture", "original " * 100, "fixture.log", store)
    assert row.recovery_status == "root_exact"
    assert row.root_recovered
    assert row.checked_references == 1
    assert row.recovery_valid
    assert row.lossless is True


def test_exact_fragment_is_not_full_original_recovery(monkeypatch):
    def view(content, hint, *, stash, **_):
        return "kept prefix " + stash("only a fragment"), ContentType.CODE
    monkeypatch.setattr(benchmark, "route_typed", view)
    row = benchmark.benchmark_one("fixture", "whole original " * 50, "fixture.py", Store())
    assert row.recovery_status == "fragments_exact"
    assert row.recovery_valid
    assert not row.root_recovered
    assert row.lossless is None


def test_unchanged_input_is_not_a_verified_retrieval(monkeypatch):
    monkeypatch.setattr(
        benchmark, "route_typed",
        lambda content, *args, **kwargs: (content, ContentType.PROSE),
    )
    row = benchmark.benchmark_one(
        "literal", "An example [[BR:123456abcdef|example]]", "example.md", Store(),
    )
    assert row.recovery_status == "unchanged"
    assert row.checked_references == 0
    assert row.lossless is None
    assert row.recovery_valid


def test_changed_unreferenced_output_is_unverified(monkeypatch):
    monkeypatch.setattr(
        benchmark, "route_typed",
        lambda *args, **kwargs: ("unexplained omission", ContentType.PROSE),
    )
    row = benchmark.benchmark_one("fixture", "original " * 100, "fixture.md", Store())
    assert row.recovery_status == "unverified"
    assert not row.recovery_valid
    assert row.lossless is None


def test_report_does_not_certify_zero_retrievals(monkeypatch):
    monkeypatch.setattr(
        benchmark, "route_typed",
        lambda content, *args, **kwargs: (content, ContentType.PROSE),
    )
    row = benchmark.benchmark_one("fixture", "unchanged", "fixture.md", Store())
    result = benchmark.to_json([row], turns=5)
    assert result["lossless"] is None
    assert result["recovery_valid"]
    assert result["checked_references"] == 0
    assert result["task_quality_verified"] is False
    assert "HELD on every placeholder" not in benchmark.format_report(
        [row], turns=5, skipped=0, demo=False,
    )


def test_cli_returns_nonzero_for_recovery_failure(monkeypatch, capsys, tmp_path):
    fixture = tmp_path / "fixture.log"
    fixture.write_text("original " * 100, encoding="utf-8")
    store = Store("wrong")
    monkeypatch.setattr(benchmark, "CCR", lambda *args, **kwargs: store)
    monkeypatch.setattr(benchmark, "route_typed", root_view)
    assert benchmark.main([str(fixture), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["recovery_valid"] is False


def test_benchmark_does_not_replace_invalid_utf8_and_call_it_exact(tmp_path):
    fixture = tmp_path / "invalid.log"
    fixture.write_bytes(b"original\xffpayload")
    assert benchmark._read_text(fixture) is None


def test_large_unicode_file_is_a_valid_bounded_prefix(tmp_path):
    fixture = tmp_path / "large.log"
    fixture.write_bytes(("漢" * (benchmark._MAX_READ_BYTES // 3 + 100)).encode("utf-8"))
    prefix = benchmark._read_text(fixture)
    assert prefix is not None and "\ufffd" not in prefix
    assert len(prefix.encode("utf-8")) <= benchmark._MAX_READ_BYTES + 4
