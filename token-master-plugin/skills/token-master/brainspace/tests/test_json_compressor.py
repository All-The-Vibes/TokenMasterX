"""Tests for brainspace.compressors.json_compressor.

Run from the skill dir so 'import brainspace' resolves:

    cd "C:/Users/shyamsridhar/code/TokenMaster/token-master-plugin/skills/token-master"
    uv run --with mcp --with pytest python -m pytest brainspace/tests/test_json_compressor.py -q

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

    def _stash(content: str, *, ctype: str = "", source: str = "", summary: str = "",
               kind: str = "fragment") -> str | None:
        if not content:
            return None
        raw = content.encode("utf-8", errors="replace")
        short = hashlib.sha256(raw).hexdigest()[:12]
        meta_parts = [p for p in (ctype, source or summary) if p]
        n_lines = content.count("\n") + 1
        meta_parts.append(f"{n_lines}L")
        meta = "; ".join(meta_parts)
        placeholder = f"[[BR:{short}|{meta}]]"
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
    from brainspace.compressors.json_compressor import compress_json
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
    """Exact compaction by default; overview recovers the full original root."""

    def test_long_strings_preserved_even_with_stash(self):
        compress_json = import_compressor()
        stash, store = make_fake_stash()
        text = json.dumps({"key": "Z" * 500})
        for intent in ("conservative", "overview"):
            result = compress_json(text, stash=stash, max_str=1, intent=intent)
            assert json.loads(result) == json.loads(text)
        assert not store

    def test_overview_full_original_is_recoverable(self):
        compress_json = import_compressor()
        stash, store = make_fake_stash()
        text = make_dir_listing(200)
        result = json.loads(compress_json(text, stash=stash, intent="overview"))
        assert result["_brainspace_view"] == "overview"
        assert result["lossy"] is True
        assert result["total_items"] == 200
        assert result["omitted_items"] == 197
        assert result["indices"] == [0, 1, 199]
        assert result["items"] == [json.loads(text)[i] for i in result["indices"]]
        assert store[result["original"]] == text

    @pytest.mark.parametrize("sample,tail", [(0, 2), (2, 0), (3, 2)])
    def test_overview_windows_keep_order_and_cardinality(self, sample, tail):
        compress_json = import_compressor()
        stash, store = make_fake_stash()
        text = make_dir_listing(30)
        result = json.loads(compress_json(text, stash=stash, intent="overview",
                                          sample=sample, tail=tail))
        expected = list(range(sample)) + list(range(30 - tail, 30))
        assert result["indices"] == expected
        assert len(result["items"]) + result["omitted_items"] == 30
        assert result["items"] == [json.loads(text)[i] for i in expected]
        assert store[result["original"]] == text

    @pytest.mark.parametrize("sample,tail", [(-1, 1), (1, -1), (0, 0), (True, 1), (1.5, 1)])
    def test_invalid_windows_passthrough(self, sample, tail):
        stash, _ = make_fake_stash()
        text = make_dir_listing(30)
        assert import_compressor()(text, stash=stash, intent="overview",
                                   sample=sample, tail=tail) == text

    def test_default_keeps_every_record_and_full_string(self):
        text = make_nested_api_response()
        assert json.loads(import_compressor()(text)) == json.loads(text)

    def test_keys_and_null_missing_remain_distinct(self):
        text = '{"z":null,"a":{"id":1},"b":{"id":1,"optional":null}}'
        result = import_compressor()(text)
        assert result == text
        assert list(json.loads(result)) == ["z", "a", "b"]

    @pytest.mark.parametrize("text", ["[]", "{}", "[10,20,30,40]", '"a  b"'])
    def test_small_json_passthrough(self, text):
        assert import_compressor()(text) == text

    def test_retained_overview_number_and_string_lexemes_are_exact(self):
        stash, store = make_fake_stash()
        record = '{"n":1.0000000000000000001,"zero":-0,"s":"\\u0061  b"}'
        text = "[" + ", ".join([record] * 30) + "]"
        result = import_compressor()(text, stash=stash, intent="overview")
        assert result.count(record) == 3
        assert store[json.loads(result)["original"]] == text



# ---------------------------------------------------------------------------
# (d) Measured reduction on a realistic 200-element directory listing
# ---------------------------------------------------------------------------

class TestMeasuredReduction:
    def test_explicit_overview_dir_listing_reduction(self):
        from brainspace import tokens
        stash, _ = make_fake_stash()
        text = make_dir_listing(200)
        out = import_compressor()(text, stash=stash, intent="overview")
        report = tokens.reduction(text, out)
        print(f"\nJSON overview: {report}")
        assert report["pct_reduction"] >= 50.0

    def test_default_nested_response_is_smaller_without_losing_values(self):
        text = json.dumps(json.loads(make_nested_api_response()), indent=4)
        out = import_compressor()(text)
        assert len(out) < len(text)
        assert json.loads(out) == json.loads(text)
