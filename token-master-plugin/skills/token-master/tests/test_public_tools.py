import hashlib
import json

import pytest

import brainspace_mcp as server
from brainspace.ccr import CCR
from brainspace.router import ContentType
from brainspace.tokens import count_tokens


@pytest.fixture
def store(tmp_path, monkeypatch):
    value = CCR(tmp_path / "ccr.sqlite", workspace_root=tmp_path)
    monkeypatch.setitem(server._STATE, "ccr", value)
    return value


def test_public_retrieval_reconstructs_200001_unicode_characters(store):
    original = "漢" * 200001
    ref = store.stash(original, kind="root")
    offset, parts = 0, []
    while True:
        page = server.brainspace_retrieve(ref, offset=offset, limit=32768)
        assert page["ok"]
        assert page["sha256"] == hashlib.sha256(original.encode()).hexdigest()
        assert page["page_sha256"] == hashlib.sha256(page["content"].encode()).hexdigest()
        assert len(page["content"]) <= 32768
        parts.append(page["content"])
        if page["complete"]:
            break
        assert page["next_offset"] > offset
        offset = page["next_offset"]
    assert "".join(parts) == original
    assert len(parts) == 7


def test_public_search_and_invalid_recovery_report_errors(store):
    ref = store.stash("alpha\nDENIED\nomega", kind="root")
    found = server.brainspace_search(ref, "DENIED")
    assert found["ok"]
    assert found["results"][0]["line"] == 2
    assert found["complete"]
    assert not server.brainspace_retrieve("not-a-reference")["ok"]
    assert not server.brainspace_retrieve(ref, offset=-1)["ok"]


def test_no_savings_footer_or_failure_notice_is_added(monkeypatch, store):
    text = '{"hello":    "world"}'
    monkeypatch.setattr(server, "route_typed",
                        lambda *a, **k: ('{"hello":"world"}', ContentType.JSON))
    result = server.brainspace_compress(text)
    assert result == '{"hello":"world"}'
    assert count_tokens(result) < count_tokens(text)
    def broken():
        raise OSError("storage failed")
    monkeypatch.setattr(server, "_ccr", broken)
    assert server.brainspace_compress(text) == text


def test_explicit_exact_intent_and_default_code_are_unchanged(store):
    source = "def f():\n" + "    x = 'keep original body'\n" * 200
    assert server.brainspace_compress(source, "x.py") == source
    assert server.brainspace_compress(source, "x.py", intent="exact") == source


def test_overview_is_recoverable_and_telemetry_is_out_of_band(store):
    text = json.dumps([{"value": i, "status": "ok"} for i in range(500)])
    result = server.brainspace_compress(text, "x.json", intent="overview")
    assert len(result) < len(text)
    view = json.loads(result)
    page = server.brainspace_retrieve(view["original"])
    assert page["content"] == text
    assert page["complete"]
    assert "pct_reduction" not in result
    assert server.brainspace_stats()["last_transform"]["decision"] == "transformed"


def test_oversize_final_mcp_representation_bypasses_not_truncates(monkeypatch, store):
    monkeypatch.setattr(server, "MAX_COMPRESS_BYTES", 10)
    text = '{ "a": 1, "b": 2, "c": 3 }'
    assert server.brainspace_compress(text) == text


def test_release_does_not_delete_and_unknown_scopes_fail(store, tmp_path):
    ref = store.stash("exact original", kind="root")
    assert server.brainspace_release(ref)["released"]
    assert server.brainspace_retrieve(ref)["content"] == "exact original"
    other = CCR(store._db_path, workspace_root=tmp_path / "other")
    assert not other.retrieve_page(ref)["ok"]
