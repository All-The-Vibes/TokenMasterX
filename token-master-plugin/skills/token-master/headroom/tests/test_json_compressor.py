"""Tests for headroom.compressors.json_compressor.

Run from the skill dir so 'import headroom' resolves:

    cd "C:/Users/shyamsridhar/code/TokenMaster/token-master-plugin/skills/token-master"
    uv run --with mcp --with pytest python -m pytest headroom/tests/test_json_compressor.py -q

The test suite verifies:
  (a) lossless recovery -- for any placeholder emitted, the stash round-trip
      returns the original value
  (b) never-raises on garbage / edge-case input
  (c) determinism -- calling twice gives identical bytes
  (d) a real measured reduction on a realistic 200-element directory listing
"""

from __future__ import annotations

import hashlib
import json

import pytest


# ---------------------------------------------------------------------------
# Fake in-memory stash (no SQLite dependency)
# ---------------------------------------------------------------------------

def make_fake_stash():
    """Return a (stash_fn, store_dict) pair.

    stash_fn(content, *, ctype='', source='', summary='') -> placeholder str
    store_dict maps placeholder -> original content for recovery checks.
    """
    store: dict[str, str] = {}

    def _stash(content: str, *, ctype: str = "", source: str = "", summary: str = "") -> str | None:
        if not content:
            return None
        raw = content.encode("utf-8", errors="replace")
        short = hashlib.sha256(raw).hexdigest()[:12]
        meta_parts = [p for p in (ctype, source or summary) if p]
        n_lines = content.count("\n") + 1
        meta_parts.append(f"{n_lines}L")
        meta = "; ".join(meta_parts)
        placeholder = f"[[HR:{short}|{meta}]]"
        store[placeholder] = content
        return placeholder

    return _stash, store


# ---------------------------------------------------------------------------
# Realistic samples
# ---------------------------------------------------------------------------

def make_dir_listing(n: int = 200) -> str:
    """Generate a JSON array of n file-object entries (name/size/mode/mtime)."""
    entries = []
    for i in range(n):
        entries.append({
            "name": f"file_{i:04d}.py",
            "size": 1024 + i * 7,
            "mode": "100644",
            "mtime": 1700000000 + i * 60,
        })
    return json.dumps(entries)


def make_nested_api_response() -> str:
    """Generate a nested API-response style JSON object."""
    return json.dumps({
        "status": "ok",
        "meta": {
            "page": 1,
            "per_page": 50,
            "total": 1200,
        },
        "results": [
            {
                "id": i,
                "title": f"Result {i}",
                "description": "A" * 300,  # long string -- should be stashed/truncated
                "tags": [f"tag{j}" for j in range(10)],
                "nested": {
                    "a": 1,
                    "b": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
                },
            }
            for i in range(20)
        ],
        "errors": [],
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def import_compressor():
    from headroom.compressors.json_compressor import compress_json
    return compress_json


# ---------------------------------------------------------------------------
# (b) Never raises
# ---------------------------------------------------------------------------

class TestNeverRaises:
    """Rule 1: the function must never raise."""

    def test_empty_string(self):
        compress_json = import_compressor()
        result = compress_json("")
        assert isinstance(result, str)

    def test_whitespace_only(self):
        compress_json = import_compressor()
        result = compress_json("   \n\t  ")
        assert isinstance(result, str)

    def test_plain_text_not_json(self):
        compress_json = import_compressor()
        result = compress_json("hello world, not JSON at all!")
        assert result == "hello world, not JSON at all!"

    def test_invalid_json(self):
        compress_json = import_compressor()
        bad = "{broken json: [1, 2, 3"
        result = compress_json(bad)
        assert result == bad

    def test_none_input(self):
        compress_json = import_compressor()
        result = compress_json(None)  # type: ignore[arg-type]
        assert result is None  # returned unchanged per contract

    def test_binary_garbage(self):
        compress_json = import_compressor()
        garbage = "\x00\xff\xfe\x80" * 50
        result = compress_json(garbage)
        assert isinstance(result, str)

    def test_very_large_input(self):
        compress_json = import_compressor()
        big = make_dir_listing(1000)
        result = compress_json(big)
        assert isinstance(result, str)

    def test_json_null(self):
        compress_json = import_compressor()
        result = compress_json("null")
        assert isinstance(result, str)

    def test_json_number(self):
        compress_json = import_compressor()
        result = compress_json("42")
        assert isinstance(result, str)

    def test_json_boolean(self):
        compress_json = import_compressor()
        assert compress_json("true") in ("true", "True")
        assert compress_json("false") in ("false", "False")

    def test_unknown_opts_ignored(self):
        compress_json = import_compressor()
        result = compress_json('{"a":1}', bogus_option=True, another=42)
        assert isinstance(result, str)

    def test_stash_that_always_raises(self):
        compress_json = import_compressor()

        def bad_stash(content, **kwargs):
            raise RuntimeError("stash exploded!")

        result = compress_json('{"key": "' + "x" * 300 + '"}', stash=bad_stash)
        assert isinstance(result, str)

    def test_stash_returning_none(self):
        compress_json = import_compressor()
        result = compress_json(
            '{"key": "' + "x" * 300 + '"}',
            stash=lambda *a, **kw: None,
        )
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# (c) Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Rule 4: same input + same opts + same stash => byte-identical output."""

    def test_deterministic_without_stash(self):
        compress_json = import_compressor()
        data = make_dir_listing(200)
        r1 = compress_json(data)
        r2 = compress_json(data)
        assert r1 == r2

    def test_deterministic_with_stash(self):
        compress_json = import_compressor()
        data = make_nested_api_response()
        stash1, _ = make_fake_stash()
        stash2, _ = make_fake_stash()
        r1 = compress_json(data, stash=stash1)
        r2 = compress_json(data, stash=stash2)
        assert r1 == r2, (
            "Two calls with separate but identical stash implementations must "
            "produce byte-identical output (stash keys are content-addressed)"
        )

    def test_deterministic_small_object(self):
        compress_json = import_compressor()
        payload = json.dumps({"z": 1, "a": 2, "m": [1, 2, 3]})
        r1 = compress_json(payload)
        r2 = compress_json(payload)
        assert r1 == r2


# ---------------------------------------------------------------------------
# (a) Lossless recovery
# ---------------------------------------------------------------------------

class TestLosslessRecovery:
    """Rule 3: every value stashed must be exactly recoverable."""

    def test_long_string_value_stashed(self):
        compress_json = import_compressor()
        stash_fn, store = make_fake_stash()
        original_value = "Z" * 500  # well over default max_str=200
        payload = json.dumps({"key": original_value})

        result = compress_json(payload, stash=stash_fn, max_str=200)
        result_obj = json.loads(result)

        # The value must contain a placeholder.
        compressed_val = result_obj["key"]
        ph_matches = [k for k in store if k in compressed_val]
        assert ph_matches, (
            f"No placeholder found in compressed value {compressed_val!r}. "
            f"Store keys: {list(store)}"
        )
        # The placeholder must recover the exact original.
        ph = ph_matches[0]
        assert store[ph] == original_value

    def test_keys_always_preserved(self):
        compress_json = import_compressor()
        payload = json.dumps({"alpha": 1, "beta": 2, "gamma": 3, "delta": 4})
        result = compress_json(payload)
        result_obj = json.loads(result)
        assert set(result_obj.keys()) == {"alpha", "beta", "gamma", "delta"}

    def test_short_values_not_stashed(self):
        compress_json = import_compressor()
        stash_fn, store = make_fake_stash()
        payload = json.dumps({"x": "short string"})
        result = compress_json(payload, stash=stash_fn, max_str=200)
        result_obj = json.loads(result)
        assert result_obj["x"] == "short string"
        assert len(store) == 0, "Short strings must not be stashed"

    def test_list_elision_marker_present(self):
        compress_json = import_compressor()
        items = list(range(20))
        payload = json.dumps(items)
        result = compress_json(payload, sample=2, tail=1)
        result_obj = json.loads(result)
        # The middle items should be replaced with a marker string.
        assert any(
            isinstance(v, str) and "more items" in v
            for v in result_obj
        ), f"Expected elision marker in {result_obj!r}"

    def test_list_head_tail_preserved(self):
        compress_json = import_compressor()
        items = [{"id": i, "name": f"item{i}"} for i in range(20)]
        payload = json.dumps(items)
        result = compress_json(payload, sample=2, tail=1)
        result_obj = json.loads(result)
        # First 2 elements should be kept (as dicts) and last 1.
        assert result_obj[0] == items[0]
        assert result_obj[1] == items[1]
        assert result_obj[-1] == items[-1]

    def test_no_stash_truncation_marker(self):
        """Without stash, long strings get a truncation marker (no stash involved)."""
        compress_json = import_compressor()
        original_value = "A" * 500
        payload = json.dumps({"text": original_value})
        result = compress_json(payload, stash=None, max_str=200)
        result_obj = json.loads(result)
        val = result_obj["text"]
        assert val.startswith("A" * 200), "Prefix must be preserved"
        assert "chars" in val, "Must include a character-count marker"

    def test_nested_dict_keys_preserved(self):
        compress_json = import_compressor()
        payload = json.dumps({
            "outer": {
                "inner": {
                    "deep": [1, 2, 3],
                    "also": "value",
                }
            }
        })
        result = compress_json(payload)
        result_obj = json.loads(result)
        assert "outer" in result_obj
        assert "inner" in result_obj["outer"]
        assert "deep" in result_obj["outer"]["inner"]
        assert "also" in result_obj["outer"]["inner"]

    def test_short_list_not_elided(self):
        """Lists at or below the threshold must be kept intact."""
        compress_json = import_compressor()
        # sample=2, tail=1 => threshold = 4; a list of 4 should not be elided.
        items = [10, 20, 30, 40]
        payload = json.dumps(items)
        result = compress_json(payload, sample=2, tail=1)
        result_obj = json.loads(result)
        assert result_obj == items, (
            f"List of length {len(items)} should not be elided (threshold=4)"
        )

    def test_long_list_elision_count_correct(self):
        """The elision marker must report the correct number of hidden items."""
        compress_json = import_compressor()
        n = 20
        items = list(range(n))
        payload = json.dumps(items)
        result = compress_json(payload, sample=2, tail=1)
        result_obj = json.loads(result)
        marker = next(v for v in result_obj if isinstance(v, str) and "more items" in v)
        hidden = n - 2 - 1  # n - sample - tail
        assert str(hidden) in marker, f"Marker {marker!r} must contain the count {hidden}"

    def test_empty_list_passthrough(self):
        compress_json = import_compressor()
        payload = "[]"
        result = compress_json(payload)
        assert json.loads(result) == []

    def test_empty_dict_passthrough(self):
        compress_json = import_compressor()
        payload = "{}"
        result = compress_json(payload)
        assert json.loads(result) == {}


# ---------------------------------------------------------------------------
# (d) Measured reduction on a realistic 200-element directory listing
# ---------------------------------------------------------------------------

class TestMeasuredReduction:
    """Verify meaningful token reduction on the realistic sample."""

    def test_dir_listing_reduction(self):
        compress_json = import_compressor()
        from headroom import tokens

        data = make_dir_listing(200)
        stash_fn, _ = make_fake_stash()
        compressed = compress_json(data, stash=stash_fn, sample=2, tail=1)

        report = tokens.reduction(data, compressed)
        print(
            f"\n[JSON dir listing: {report['tokens_before']}->{report['tokens_after']} tok, "
            f"{report['pct_reduction']}% reduction, {report['ratio']}x, "
            f"backend={report['backend']}]"
        )
        assert report["pct_reduction"] >= 50.0, (
            f"Expected >= 50% reduction on 200-element dir listing, "
            f"got {report['pct_reduction']}% "
            f"(before={report['tokens_before']}, after={report['tokens_after']})"
        )

    def test_nested_api_response_reduction(self):
        compress_json = import_compressor()
        from headroom import tokens

        data = make_nested_api_response()
        stash_fn, _ = make_fake_stash()
        compressed = compress_json(data, stash=stash_fn)

        report = tokens.reduction(data, compressed)
        print(
            f"\n[JSON nested API: {report['tokens_before']}->{report['tokens_after']} tok, "
            f"{report['pct_reduction']}% reduction]"
        )
        assert report["pct_reduction"] >= 30.0, (
            f"Expected >= 30% reduction on nested API response, "
            f"got {report['pct_reduction']}%"
        )

    def test_compressed_shorter_than_original(self):
        compress_json = import_compressor()
        data = make_dir_listing(200)
        stash_fn, _ = make_fake_stash()
        compressed = compress_json(data, stash=stash_fn)
        assert len(compressed) < len(data), (
            f"Compressed ({len(compressed)} chars) must be shorter than "
            f"original ({len(data)} chars)"
        )
