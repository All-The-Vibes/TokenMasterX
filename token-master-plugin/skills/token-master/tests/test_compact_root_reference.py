"""Offline compact-root integrity and compatibility tests; temporary SQLite only."""
from contextlib import closing
import hashlib
import json
import re
import sqlite3
import zlib

import pytest

from brainspace.ccr import CCR, PLACEHOLDER_RE, parse_placeholders


STYLE = "compact-root-v1"
TEXT = "Observed source 雪\r\nexact spaces  \r\n"


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def store(tmp_path):
    return CCR(tmp_path / "ccr.sqlite", workspace_root=tmp_path, session_id="task")


def compact(store, text=TEXT, **metadata):
    return store.stash(text, kind="root", reference_style=STYLE, **metadata)


def metadata_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def expected_marker(store, full_hash, metadata):
    data = json.dumps(
        [STYLE, store._scope_key, full_hash, metadata],
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    return "[[BR:" + sha(data) + "|r=1]]"


def test_compact_marker_is_metadata_and_scope_bound_with_no_new_table(store):
    ref = compact(store, ctype="native", source=r"C:\docs\雪.md", summary="complete observed result")
    assert re.fullmatch(r"\[\[BR:[0-9a-f]{64}\|r=1\]\]", ref)
    assert len(ref) == 75 and PLACEHOLDER_RE.fullmatch(ref)
    page = store.retrieve_page(ref)
    assert page["ok"] and page["content"] == TEXT and page["sha256"] == sha(TEXT)
    assert page["metadata"] == {
        "kind": "root", "ctype": "native", "source": r"C:\docs\雪.md",
        "summary": "complete observed result", "chars": len(TEXT), "bytes": len(TEXT.encode()),
    }
    assert ref == expected_marker(store, sha(TEXT), page["metadata"])
    assert parse_placeholders(ref) == [ref[5:69]]
    assert ref[5:69] != sha(TEXT)
    assert store.retrieve(ref[5:69]) is None  # No implicit opaque-ID/prefix resolution.
    with closing(sqlite3.connect(store._db_path)) as conn:
        assert {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {
            "ccr_v2", "ccr_references", "ccr_leases", "ccr_evictions"}
        row = conn.execute("SELECT hash,metadata FROM ccr_references WHERE ref=?", (ref,)).fetchone()
    assert row == (sha(TEXT), metadata_json(page["metadata"]))


def test_same_content_different_full_metadata_keeps_distinct_provenance(store):
    variants = [
        {"source": "one.md", "ctype": "text", "summary": "one"},
        {"source": "two.md", "ctype": "text", "summary": "one"},
        {"source": "one.md", "ctype": "code", "summary": "one"},
        {"source": "one.md", "ctype": "text", "summary": "two"},
    ]
    refs = [compact(store, **meta) for meta in variants]
    assert len(set(refs)) == len(variants)
    for ref, meta in zip(refs, variants):
        assert compact(store, **meta) == ref
        page = store.retrieve_page(ref)
        assert page["content"] == TEXT
        assert all(page["metadata"][key] == value for key, value in meta.items())
    assert store.stats()["entries"] == store.stats()["pinned_entries"] == 1


def test_reopen_and_default_annotated_serialization_remain_compatible(store):
    annotated = store.stash(TEXT, "text", "one.md", "one", kind="root")
    expected = (f"[[BR:{sha(TEXT)}|v=2;scope={store._scope_key};kind=root;"
                f"source=one.md;type=text;summary=one;chars={len(TEXT)};bytes={len(TEXT.encode())}]]")
    assert annotated == expected
    assert store.stash(TEXT, "text", "one.md", "one", kind="root",
                       reference_style="annotated-v1") == annotated
    short = compact(store, ctype="text", source="one.md", summary="one")
    assert len(short) < len(annotated)
    reopened = CCR(store._db_path, workspace_root=store.workspace_root, session_id="task")
    assert compact(reopened, ctype="text", source="one.md", summary="one") == short
    for ref in (short, annotated, sha(TEXT), sha(TEXT)[:12]):
        assert reopened.retrieve(ref) == TEXT
    assert reopened.retrieve_page(short)["metadata"] == reopened.retrieve_page(annotated)["metadata"]
    assert parse_placeholders(annotated) == [sha(TEXT)]
    assert reopened.retrieve(f"[[BR:{sha(TEXT)}]]") is None


@pytest.mark.parametrize("change", ["workspace", "session", "scope", "shared"])
def test_foreign_scopes_reject_even_when_identical_content_is_minted(tmp_path, store, change):
    owner = compact(store, source="one.md")
    options = dict(workspace_root=store.workspace_root, session_id="task")
    options.update({
        "workspace": {"workspace_root": tmp_path / "other"},
        "session": {"session_id": "other"},
        "scope": {"scope": "other"},
        "shared": {"shared": True},
    }[change])
    foreign = CCR(store._db_path, **options)
    other = compact(foreign, source="one.md")
    assert other != owner
    assert foreign.retrieve(owner) is None and store.retrieve(other) is None
    assert not foreign.pin(owner) and not foreign.release(owner)


def test_explicit_shared_scope_and_session_leases_keep_existing_semantics(tmp_path):
    db = tmp_path / "shared.sqlite"
    a = CCR(db, workspace_root=tmp_path / "a", session_id="a", scope="team", shared=True)
    b = CCR(db, workspace_root=tmp_path / "b", session_id="b", scope="team", shared=True)
    ref = compact(a)
    assert compact(b) == ref and b.retrieve(ref) == TEXT
    assert a.release_session() == 1
    assert a.gc(0) == 0
    assert b.release_session() == 1
    assert a.gc(0) == 1
    assert a.retrieve(ref) is None


@pytest.mark.parametrize("style", [None, "", "annotated-v2", "compact-root-v2", "compact", True, [], {}])
def test_unsupported_style_fails_before_storage(store, style):
    assert store.stash(TEXT, kind="root", reference_style=style) is None
    assert not store._db_path.exists()


@pytest.mark.parametrize("kind", ["fragment", "", "ROOT", None])
def test_compact_is_explicit_root_only(store, kind):
    assert store.stash(TEXT, reference_style=STYLE, kind=kind) is None
    assert not store._db_path.exists()


def test_default_fragment_cannot_be_promoted_or_wrapped_as_compact(store):
    fragment = store.stash(TEXT, source="piece.md")
    meta = store.retrieve_page(fragment)["metadata"]
    assert meta["kind"] == "fragment"
    assert store.stash(TEXT, reference_style=STYLE) is None
    promoted = expected_marker(store, sha(TEXT), {**meta, "kind": "root"})
    for unknown in (promoted, f"[[BR:{sha(TEXT)}|r=1]]"):
        assert store.retrieve(unknown) is None
        assert store.retrieve_page(unknown)["content"] is None
    # Even a stored, self-consistent fragment identity cannot enter the root-only format.
    forged = expected_marker(store, sha(TEXT), meta)
    with closing(sqlite3.connect(store._db_path)) as conn, conn:
        conn.execute("INSERT INTO ccr_references VALUES (?,?,?,?)",
                     (store._scope_key, forged, sha(TEXT), metadata_json(meta)))
    assert store.retrieve_page(forged)["error"] == "corrupt"


def test_requires_exact_minted_reference_never_falls_back_to_blob(store):
    ref = compact(store)
    for unknown in (
        ref.replace("|r=1", "|r=2"), ref.replace("|r=1", "|r=1;kind=root"),
        ref.replace(ref[5:69], ref[5:17]), ref + "\n",
        "[[BR:" + "0" * 64 + "|r=1]]",
    ):
        assert store.retrieve(unknown) is None
    with closing(sqlite3.connect(store._db_path)) as conn, conn:
        conn.execute("DELETE FROM ccr_references WHERE ref=?", (ref,))
    assert store.retrieve(ref) is None
    assert store.retrieve(sha(TEXT)) == TEXT  # Existing bare-content lookup stays available.


@pytest.mark.parametrize("damage", [
    "invalid_json", "duplicate_key", "noncanonical_json", "source", "summary", "ctype",
    "kind", "chars", "bytes", "boolean_chars", "extra", "missing",
    "wrong_hash", "blob", "substitution", "truncated", "trailing", "missing_blob",
    "orig_bytes", "total_chars",
])
def test_corruption_never_yields_metadata_or_partial_content(store, damage):
    ref = compact(store, source="one.md", summary="saved", ctype="text")
    with closing(sqlite3.connect(store._db_path)) as conn, conn:
        encoded = conn.execute("SELECT metadata FROM ccr_references WHERE ref=?", (ref,)).fetchone()[0]
        meta = json.loads(encoded)
        if damage in ("invalid_json", "duplicate_key", "noncanonical_json"):
            changed = {"invalid_json": "{", "duplicate_key": encoded[:-1] + ', "kind": "root"}',
                       "noncanonical_json": encoded + " "}[damage]
            conn.execute("UPDATE ccr_references SET metadata=? WHERE ref=?", (changed, ref))
        elif damage in ("source", "summary", "ctype", "kind", "chars", "bytes",
                        "boolean_chars", "extra", "missing"):
            if damage == "missing":
                meta.pop("summary")
            elif damage == "boolean_chars":
                meta["chars"] = True
            else:
                meta[damage] = "fragment" if damage == "kind" else 999 if damage in ("chars", "bytes") else "changed"
            conn.execute("UPDATE ccr_references SET metadata=? WHERE ref=?",
                         (metadata_json(meta), ref))
        elif damage == "wrong_hash":
            conn.execute("UPDATE ccr_references SET hash=? WHERE ref=?", ("0" * 64, ref))
        elif damage == "missing_blob":
            conn.execute("DELETE FROM ccr_v2")  # External corruption; FK checks deliberately off.
        elif damage in ("orig_bytes", "total_chars"):
            conn.execute(f"UPDATE ccr_v2 SET {damage}={damage}+1")
        else:
            blob = zlib.compress(TEXT.encode())
            blob = {"blob": b"broken", "substitution": zlib.compress(b"other"),
                    "truncated": blob[:-2], "trailing": blob + b"junk"}[damage]
            conn.execute("UPDATE ccr_v2 SET blob=?", (blob,))
    assert store.retrieve(ref) is None
    page = store.retrieve_page(ref, 0, 2)
    assert not page["ok"] and not page["complete"] and page["content"] is None
    assert page["metadata"] is None
    assert not store.search(ref, "source")["ok"]
    assert not store.pin(ref) and not store.release(ref)
    assert compact(store, source="one.md", summary="saved", ctype="text") is None


def test_ambiguous_reference_rows_fail_closed(store):
    ref = compact(store)
    with closing(sqlite3.connect(store._db_path)) as conn, conn:
        # Model externally damaged schema with duplicate reference rows.
        conn.execute("ALTER TABLE ccr_references RENAME TO old_references")
        conn.execute("CREATE TABLE ccr_references AS SELECT * FROM old_references")
        conn.execute("INSERT INTO ccr_references SELECT * FROM old_references")
    assert store.retrieve_page(ref)["error"] == "ambiguous_reference"
    assert not store.pin(ref)


def test_valid_other_blob_and_metadata_cannot_replace_minted_identity(store):
    ref = compact(store, source="one.md")
    other = compact(store, "Other valid content", source="other.md")
    with closing(sqlite3.connect(store._db_path)) as conn, conn:
        full_hash, metadata = conn.execute(
            "SELECT hash,metadata FROM ccr_references WHERE ref=?", (other,)).fetchone()
        conn.execute("UPDATE ccr_references SET hash=?,metadata=? WHERE ref=?",
                     (full_hash, metadata, ref))
    assert store.retrieve_page(ref)["error"] == "corrupt"
    assert store.retrieve(other) == "Other valid content"


def test_changed_stored_marker_is_not_a_minted_identity(store):
    ref = compact(store)
    changed = ref[:5] + ("0" if ref[5] != "0" else "1") + ref[6:]
    with closing(sqlite3.connect(store._db_path)) as conn, conn:
        conn.execute("UPDATE ccr_references SET ref=? WHERE ref=?", (changed, ref))
    assert store.retrieve_page(changed)["error"] == "corrupt"
    assert store.retrieve(ref) is None


def test_unicode_crlf_pages_search_and_terminal_page_are_exact(store):
    text = ("🧪 café e\u0301\r\n零\x00 " * 15000) + "TAIL\r\n"
    ref = compact(store, text, source="source with ] ; 雪\r\n",
                  summary="observed result, not a file claim")
    pieces, offset = [], 0
    while True:
        page = store.retrieve_page(ref, offset, 999999)
        assert page["ok"] and len(page["content"]) <= 32768
        assert page["sha256"] == sha(text) and page["page_sha256"] == sha(page["content"])
        assert page["total_bytes"] == len(text.encode()) and page["total_chars"] == len(text)
        assert page["metadata"]["source"] == "source with ] ; 雪\r\n"
        pieces.append(page["content"])
        if page["complete"]:
            assert page["next_offset"] is None
            break
        offset = page["next_offset"]
    assert "".join(pieces) == text
    assert store.retrieve_page(ref, len(text))["content"] == ""
    assert store.retrieve_page(ref, len(text) + 1)["error"] == "invalid_offset"
    assert store.search(ref, "TAIL")["results"][0]["start"] == text.index("TAIL")


def test_compact_and_annotated_share_content_lease_ttl_and_gc(store):
    ref = compact(store)
    old = store.stash(TEXT, kind="root")
    with closing(sqlite3.connect(store._db_path)) as conn, conn:
        conn.execute("UPDATE ccr_v2 SET last_access=0")
    assert store.gc_report(0, ttl_seconds=0)["evicted"] == 0
    assert store.release(ref)
    assert store.gc_report(0, ttl_seconds=0)["expired"] == 1
    assert store.retrieve_page(old)["error"] == "expired"  # Legacy tombstone semantics unchanged.
    assert store.retrieve(ref) is None


def test_reference_collision_does_not_alias_other_metadata(store, monkeypatch):
    ref = compact(store, source="one.md")
    monkeypatch.setattr(store, "_compact_marker", lambda *args: ref)
    assert compact(store, source="other.md") is None
    assert store.retrieve_page(ref)["metadata"]["source"] == "one.md"


@pytest.mark.parametrize("metadata", [
    {"source": "\ud800"}, {"summary": "\udfff"}, {"ctype": None},
    {"source": "x" * 4097}, {"summary": "x" * 4096, "source": "a"},
])
def test_compact_retains_metadata_validation_before_storage(store, metadata):
    assert compact(store, **metadata) is None
    assert not store._db_path.exists()


def test_metadata_limit_and_unicode_spelling_remain_exact(store):
    full = "雪" * 4096
    ref = compact(store, source=full)
    assert len(ref) == 75 and store.retrieve_page(ref)["metadata"]["source"] == full
    composed = compact(store, source="é")
    decomposed = compact(store, source="e\u0301")
    assert composed != decomposed
    assert store.retrieve_page(composed)["metadata"]["source"] == "é"
    assert store.retrieve_page(decomposed)["metadata"]["source"] == "e\u0301"


def test_storage_failure_never_mints_a_compact_reference(store, monkeypatch):
    def unavailable():
        raise sqlite3.OperationalError("fixture unavailable")
    monkeypatch.setattr(store, "_connect", unavailable)
    assert compact(store) is None
    assert not store._db_path.exists()


@pytest.mark.parametrize("depth", [2000, 10000])
def test_excessively_nested_metadata_fails_closed(store, depth):
    ref = compact(store)
    damaged = "[" * depth + "]" * depth
    with closing(sqlite3.connect(store._db_path)) as conn, conn:
        conn.execute("UPDATE ccr_references SET metadata=?", (damaged,))
    assert store.retrieve_page(ref)["error"] == "corrupt"
    assert store.retrieve(ref) is None
    assert compact(store) is None
    assert store.search(ref, "source")["error"] == "corrupt"
    assert not store.pin(ref) and not store.release(ref)
    with closing(sqlite3.connect(store._db_path)) as conn:
        assert conn.execute("SELECT metadata FROM ccr_references").fetchone() == (damaged,)


@pytest.mark.parametrize("style", ["annotated-v1", "compact-root-v1"])
@pytest.mark.parametrize("operation", ["retrieve", "page", "search", "pin", "release", "restash"])
def test_metadata_decoder_recursion_is_contained_without_repair(
    store, monkeypatch, style, operation,
):
    ref = store.stash(TEXT, kind="root", reference_style=style)
    with closing(sqlite3.connect(store._db_path)) as conn:
        encoded = conn.execute("SELECT metadata FROM ccr_references").fetchone()[0]

    def snapshot():
        with closing(sqlite3.connect(store._db_path)) as conn:
            return {
                table: conn.execute(f"SELECT * FROM {table} ORDER BY 1,2").fetchall()
                for table in ("ccr_v2", "ccr_references", "ccr_leases", "ccr_evictions")
            }

    before = snapshot()
    original_loads = json.loads
    calls = []

    def recursion_failure(value, *args, **kwargs):
        if value == encoded:
            calls.append(True)
            raise RecursionError("synthetic stored-metadata decoder limit")
        return original_loads(value, *args, **kwargs)

    monkeypatch.setattr(json, "loads", recursion_failure)
    if operation == "retrieve":
        assert store.retrieve(ref) is None
    elif operation == "page":
        result = store.retrieve_page(ref, 0, 2)
        assert result["error"] == "corrupt" and not result["ok"] and not result["complete"]
        assert result["content"] is result["metadata"] is None
    elif operation == "search":
        result = store.search(ref, "source")
        assert result["error"] == "corrupt" and not result["ok"] and result["results"] == []
    elif operation == "pin":
        assert not store.pin(ref)
    elif operation == "release":
        assert not store.release(ref)
    else:
        assert store.stash(TEXT, kind="root", reference_style=style) is None
    assert calls
    # Failed reads must not increment hits/pin, and failed re-stash must roll
    # back timestamp/blob/reference changes rather than healing the record.
    assert snapshot() == before
