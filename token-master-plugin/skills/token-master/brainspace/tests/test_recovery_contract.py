"""CCR recovery boundary tests; all databases are synthetic and temporary."""

import hashlib
import sqlite3
import sys
import zlib
from contextlib import closing, contextmanager
from pathlib import Path

import pytest

_SKILL = Path(__file__).resolve().parents[2]
if str(_SKILL) not in sys.path:
    sys.path.insert(0, str(_SKILL))

from brainspace.ccr import CCR, parse_placeholders  # noqa: E402


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def store(tmp_path):
    return CCR(tmp_path / "ccr.sqlite", workspace_root=tmp_path, session_id="test")


@pytest.mark.parametrize("chars", [200001, 280004])
def test_public_pages_reconstruct_200001_or_more_characters(store, chars):
    original = ("🧪 café e\u0301\r\n零\x00 " * 30000)[:chars - 4] + "TAIL"
    assert len(original) == chars
    ref = store.stash(original, ctype="text", source="fixture", kind="root")
    offset, pieces = 0, []
    while True:
        page = store.retrieve_page(ref, offset=offset)
        assert page["ok"] and page["error"] is None
        assert page["sha256"] == digest(original)
        assert page["page_sha256"] == digest(page["content"])
        assert page["total_chars"] == len(original)
        assert page["total_bytes"] == len(original.encode("utf-8"))
        assert page["offset"] == offset
        assert len(page["content"]) <= 32768
        pieces.append(page["content"])
        if page["complete"]:
            assert page["next_offset"] is None
            break
        assert page["next_offset"] == offset + len(page["content"])
        offset = page["next_offset"]
    assert "".join(pieces) == original
    assert store.retrieve(ref) == original
    assert store.retrieve(digest(original)) == original


@pytest.mark.parametrize("text", ["\x00", "é", "e\u0301", "漢字🧪\r\n", "\ufeff\u2028\n"])
def test_unicode_and_utf8_byte_identity(store, text):
    ref = store.stash(text)
    assert store.retrieve(ref) == text
    assert store.retrieve_page(ref)["sha256"] == digest(text)
    assert parse_placeholders(ref) == [digest(text)]


@pytest.mark.parametrize("content", ["", "\ud800", b"not text", None, 17])
def test_unrepresentable_or_invalid_content_fails_without_replacement(store, content):
    assert store.stash(content) is None
    assert store.stats()["entries"] == 0


def test_reference_grammar_is_not_sanitized(store):
    ref = store.stash("secret")
    key = digest("secret")
    for invalid in [None, 42, "", key.upper(), f"xxx{key}", f"{key}garbage",
                    f"prefix {ref}", f"{ref} {ref}", ref + "\n", f"[[BR:{key}|fake]]"]:
        assert store.retrieve(invalid) is None
        page = store.retrieve_page(invalid)
        assert not page["ok"] and not page["complete"]
        assert page["sha256"] is None and page["content"] is None
        assert page["error"] == "invalid_reference"


def test_ambiguous_prefix_fails_even_if_one_blob_is_valid(store):
    store.stash("first")
    key = digest("first")
    with closing(sqlite3.connect(store._db_path)) as conn, conn:
        conn.execute(
            """INSERT INTO ccr_v2
               SELECT scope, ?, blob, orig_bytes, total_chars, created, last_access, hits
               FROM ccr_v2 WHERE hash=?""",
            (key[:12] + ("0" if key[12] != "0" else "1") + key[13:], key),
        )
    assert store.retrieve(key[:12]) is None
    assert store.retrieve_page(key[:12])["error"] == "ambiguous_reference"


@pytest.mark.parametrize("damage", ["blob", "hash", "bytes", "chars", "utf8", "trailing"])
def test_corruption_never_returns_a_partial_or_complete_answer(store, damage):
    original = "original 🧪"
    ref = store.stash(original)
    with closing(sqlite3.connect(store._db_path)) as conn, conn:
        if damage == "blob":
            conn.execute("UPDATE ccr_v2 SET blob=?", (b"invalid zlib",))
        elif damage == "hash":
            conn.execute("UPDATE ccr_v2 SET blob=?", (zlib.compress(b"substituted"),))
        elif damage == "bytes":
            conn.execute("UPDATE ccr_v2 SET orig_bytes=orig_bytes+1")
        elif damage == "chars":
            conn.execute("UPDATE ccr_v2 SET total_chars=total_chars+1")
        elif damage == "utf8":
            conn.execute("UPDATE ccr_v2 SET blob=?", (zlib.compress(b"\xff"),))
        else:
            conn.execute("UPDATE ccr_v2 SET blob=?", (zlib.compress(original.encode()) + b"junk",))
    assert store.retrieve(ref) is None
    page = store.retrieve_page(ref)
    assert page["error"] == "corrupt"
    assert not page["ok"] and not page["complete"] and page["content"] is None
    assert store.search(ref, "original")["error"] == "corrupt"
    assert store.stash(original) is None  # do not mint refs to already corrupt rows


def test_scopes_isolate_workspace_session_and_named_scope(tmp_path):
    db = tmp_path / "same.sqlite"
    owner = CCR(db, workspace_root=tmp_path / "a", session_id="one", scope="private")
    ref = owner.stash("isolated")
    for kwargs in [
        dict(workspace_root=tmp_path / "b", session_id="one", scope="private"),
        dict(workspace_root=tmp_path / "a", session_id="two", scope="private"),
        dict(workspace_root=tmp_path / "a", session_id="one", scope="other"),
        dict(workspace_root=tmp_path / "a", session_id="one", scope="private", shared=True),
    ]:
        foreign = CCR(db, **kwargs)
        assert foreign.retrieve(ref) is None
        assert foreign.retrieve_page(ref)["error"] == "foreign_reference"
        assert foreign.retrieve(digest("isolated")) is None
        assert foreign.stats()["entries"] == 0
    assert CCR(db, workspace_root=tmp_path / "a", session_id="one",
               scope="private").retrieve(ref) == "isolated"


def test_cross_workspace_sharing_is_explicit(tmp_path):
    db = tmp_path / "shared.sqlite"
    a = CCR(db, workspace_root=tmp_path / "a", session_id="a", scope="team", shared=True)
    b = CCR(db, workspace_root=tmp_path / "b", session_id="b", scope="team", shared=True)
    ref = a.stash("shared")
    assert b.retrieve(ref) == "shared"
    assert b.stash("shared") == ref
    assert a.release_session() == 1
    assert a.gc(0) == 0  # b's lease still protects the original
    assert b.release_session() == 1
    assert a.gc(0) == 1


def test_default_resolution_never_discovers_parent_or_implicit_environment(tmp_path, monkeypatch):
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    parent_store = CCR(workspace_root=parent)
    ref = parent_store.stash("parent only")
    monkeypatch.chdir(child)
    monkeypatch.setenv("BRAINSPACE_CCR", str(parent_store._db_path))
    local = CCR()
    assert local._db_path == child / ".token-master" / "ccr.sqlite"
    assert local.retrieve(ref) is None
    shared = CCR(shared=True)
    assert shared._db_path == parent_store._db_path
    assert shared.retrieve(ref) is None  # explicit sharing does not unlock private rows


def test_metadata_is_stable_but_not_confused_with_content_identity(store):
    source = "C:\\demo\\strange];\n名.py"
    a = store.stash("same", "code", source, "summary", kind="root")
    assert a == store.stash("same", "code", source, "summary", kind="root")
    b = store.stash("same", ctype="code", source=source, summary="summary", kind="fragment")
    c = store.stash("same", ctype="code", source="other", kind="root")
    assert len({a, b, c}) == 3
    assert parse_placeholders(a) == parse_placeholders(b) == parse_placeholders(c)
    assert "\n" not in a and a.count("]]") == 1
    meta = store.retrieve_page(a)["metadata"]
    assert meta["kind"] == "root" and meta["source"] == source
    assert meta["summary"] == "summary" and meta["ctype"] == "code"
    assert store.retrieve_page(b)["metadata"]["kind"] == "fragment"
    assert store.retrieve_page(digest("same"))["metadata"] is None
    assert store.stats()["entries"] == 1
    assert store.retrieve(a.replace("kind=root", "kind=fake")) is None


@pytest.mark.parametrize("offset,limit", [(-1, 10), (True, 10), (0, 0), (0, -1), (0, True), ("0", 10)])
def test_invalid_page_bounds(store, offset, limit):
    ref = store.stash("abc")
    assert store.retrieve_page(ref, offset=offset, limit=limit)["error"] == "invalid_bounds"


def test_page_edges_and_cap(store):
    ref = store.stash("x" * 40000)
    assert len(store.retrieve_page(ref, limit=999999)["content"]) == 32768
    end = store.retrieve_page(ref, offset=40000)
    assert end["ok"] and end["complete"] and end["content"] == ""
    assert store.retrieve_page(ref, offset=40001)["error"] == "invalid_offset"


def test_exact_search_is_literal_case_sensitive_overlapping_and_paged(store):
    text = "header\nbanana .* BANANA\nbanana\nfooter"
    ref = store.stash(text)
    first = store.search(ref, "ana", limit=2)
    assert first["ok"] and not first["complete"]
    assert [r["start"] for r in first["results"]] == [8, 10]
    assert first["sha256"] == digest(text)
    second = store.search(ref, "ana", offset=first["next_offset"], limit=2)
    assert second["complete"]
    assert [r["start"] for r in second["results"]] == [25, 27]
    for r in first["results"] + second["results"]:
        assert text[r["start"]:r["end"]] == "ana"
        assert r["content"] == text[r["context_start"]:r["context_end"]]
    assert len(store.search(ref, ".*")["results"]) == 1
    assert store.search(ref, "missing")["complete"]
    assert store.search(ref, "")["error"] == "invalid_query"


def test_search_output_is_bounded_even_for_one_enormous_line(store):
    ref = store.stash("a" * 300000)
    result = store.search(ref, "a", limit=999999, context_lines=100000)
    assert result["ok"] and not result["complete"]
    assert len(result["results"]) == 20
    assert all(len(item["content"]) <= 1024 for item in result["results"])
    assert all(item["context_truncated"] for item in result["results"])


def test_gc_pins_ttl_quota_and_explicit_outcomes(store, monkeypatch):
    import brainspace.ccr as module

    monkeypatch.setattr(module.time, "time", lambda: 1000.0)
    ref = store.stash("retained")
    monkeypatch.setattr(module.time, "time", lambda: 2000.0)
    report = store.gc_report(max_bytes=0, ttl_seconds=10)
    assert report["ok"] and report["evicted"] == 0
    assert not report["quota_met"] and report["pinned_entries"] == 1
    assert report["expired_pinned_entries"] == 1
    assert store.release(ref)
    report = store.gc_report(max_bytes=0, ttl_seconds=10)
    assert report["evicted"] == 1 and report["expired"] == 1 and report["quota_met"]
    assert store.retrieve_page(ref)["error"] == "expired"
    assert store.stats()["last_gc"] == report
    assert store.stash("retained") == ref
    assert store.pin(ref, session_id="other")
    assert store.release_session() == 1
    assert store.gc(0) == 0
    assert store.release_session("other") == 1
    assert store.gc(0) == 1
    assert store.retrieve_page(ref)["error"] == "evicted"


def test_retrieval_pins_for_a_consumer_and_gc_is_scoped(tmp_path):
    db = tmp_path / "shared.sqlite"
    a = CCR(db, workspace_root=tmp_path, shared=True, session_id="a")
    b = CCR(db, workspace_root=tmp_path, shared=True, session_id="b")
    foreign = CCR(db, workspace_root=tmp_path, scope="foreign")
    ref = a.stash("read lease")
    other = foreign.stash("unrelated")
    assert a.release_session() == 1
    assert b.retrieve_page(ref)["ok"]
    assert a.gc(0) == 0
    assert b.release_session() == 1
    assert a.gc(0) == 1
    assert foreign.retrieve(other) == "unrelated"


def test_legacy_records_require_explicit_verified_import(tmp_path):
    db = tmp_path / "legacy.sqlite"
    text = "legacy original 零"
    key = digest(text)
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("""CREATE TABLE ccr (
            hash TEXT PRIMARY KEY, blob BLOB, orig_bytes INTEGER, ctype TEXT,
            source TEXT, created REAL, last_access REAL, hits INTEGER)""")
        conn.execute("INSERT INTO ccr VALUES (?, ?, ?, 'code', 'legacy.py', 0, 0, 0)",
                     (key, zlib.compress(text.encode()), len(text.encode())))
    store = CCR(db, workspace_root=tmp_path)
    assert store.retrieve(key) is None
    assert store.stats()["entries"] == 0
    assert store.stats()["legacy_migration"] == "explicit_full_digest_import_only"
    assert store.migrate_legacy(key[:12]) is None
    ref = store.migrate_legacy(key)
    assert store.retrieve(ref) == text
    assert store.retrieve_page(ref)["metadata"]["kind"] == "fragment"
    other = CCR(db, workspace_root=tmp_path / "other")
    assert other.retrieve(key) is None
    with closing(sqlite3.connect(db)) as conn, conn:
        assert conn.execute("SELECT blob FROM ccr").fetchone()[0] == zlib.compress(text.encode())


def test_storage_failure_is_visible_and_legacy_int_gc_stays_compatible(tmp_path):
    path = tmp_path / "file"
    path.write_text("not a directory")
    store = CCR(path / "ccr.sqlite", workspace_root=tmp_path)
    assert store.stash("safe") is None
    assert store.retrieve("a" * 64) is None
    assert store.retrieve_page("a" * 64)["error"] == "storage_error"
    assert store.gc(0) == 0
    assert store.last_gc["error"] == "storage_error"
    assert store.stats()["error"] == "unreadable"


def test_connections_are_closed_after_all_public_operations(store, monkeypatch):
    real_connect = sqlite3.connect
    connections = []

    def tracking_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        connections.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", tracking_connect)
    ref = store.stash("closed")
    store.retrieve(ref)
    store.retrieve_page(ref)
    store.search(ref, "closed")
    store.pin(ref)
    store.release(ref)
    store.release_session()
    store.stats()
    store.gc()
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")


def test_invalid_utf8_with_matching_digest_is_still_rejected(store):
    ref = store.stash("text")
    raw = b"\xff"
    key = hashlib.sha256(raw).hexdigest()
    with closing(sqlite3.connect(store._db_path)) as conn, conn:
        conn.execute("UPDATE ccr_v2 SET hash=?, blob=?, orig_bytes=1, total_chars=1",
                     (key, zlib.compress(raw)))
    assert store.retrieve_page(key)["error"] == "corrupt"
    assert store.retrieve(ref) is None


@pytest.mark.parametrize("metadata", ['null', '[]', '{}', '{"kind":"root"}', 'invalid'])
def test_corrupt_provenance_fails_closed(store, metadata):
    ref = store.stash("metadata")
    with closing(sqlite3.connect(store._db_path)) as conn, conn:
        conn.execute("UPDATE ccr_references SET metadata=?", (metadata,))
    assert store.retrieve_page(ref)["error"] == "corrupt"
    assert store.stash("metadata") is None


def test_added_provenance_fields_cannot_smuggle_unbounded_output(store):
    import json

    ref = store.stash("metadata")
    with closing(sqlite3.connect(store._db_path)) as conn, conn:
        meta = json.loads(conn.execute("SELECT metadata FROM ccr_references").fetchone()[0])
        meta["extra"] = "x" * 100000
        conn.execute("UPDATE ccr_references SET metadata=?", (json.dumps(meta),))
    assert store.retrieve_page(ref)["error"] == "corrupt"


@pytest.mark.parametrize("max_bytes,ttl", [(-1, None), (True, None), (0, -1),
                                         (0, float("nan")), (0, float("inf")), (0, True)])
def test_invalid_gc_policy_does_not_mutate(store, max_bytes, ttl):
    ref = store.stash("keep")
    assert store.release(ref)
    assert store.gc_report(max_bytes, ttl_seconds=ttl)["error"] == "invalid_policy"
    assert store.retrieve(ref) == "keep"


def test_huge_nonnegative_ttl_is_valid_not_an_overflow(store):
    ref = store.stash("keep")
    assert store.release(ref)
    assert store.gc_report(ttl_seconds=10**1000)["ok"]
    assert store.retrieve(ref) == "keep"


def test_gc_is_lru_only_for_released_records(store, monkeypatch):
    import brainspace.ccr as module

    monkeypatch.setattr(module.time, "time", lambda: 1.0)
    old = store.stash("old original")
    monkeypatch.setattr(module.time, "time", lambda: 2.0)
    newer = store.stash("new original")
    assert store.release_session() == 2
    with closing(sqlite3.connect(store._db_path)) as conn, conn:
        newer_size = conn.execute("SELECT LENGTH(blob) FROM ccr_v2 WHERE hash=?",
                                  (digest("new original"),)).fetchone()[0]
    assert store.gc(newer_size) == 1
    assert store.retrieve_page(old)["error"] == "evicted"
    assert store.retrieve(newer) == "new original"


def test_shared_concurrent_readers_and_gc_do_not_strand_pinned_reference(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    db = tmp_path / "concurrent.sqlite"
    owner = CCR(db, workspace_root=tmp_path, shared=True, session_id="owner")
    original = "concurrent 零\n" * 20000
    ref = owner.stash(original)

    def reader(index):
        consumer = CCR(db, workspace_root=tmp_path, shared=True, session_id=str(index))
        for _ in range(3):
            assert consumer.retrieve(ref) == original
            assert consumer.gc(0) == 0
        return consumer.release_session()

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(reader, range(8))) == [1] * 8
    assert owner.retrieve(ref) == original
    assert owner.release_session() == 1
    assert owner.gc(0) == 1


def test_corrupt_legacy_import_does_not_create_scoped_reference(tmp_path):
    db = tmp_path / "bad-legacy.sqlite"
    key = digest("expected")
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("CREATE TABLE ccr (hash TEXT, blob BLOB, orig_bytes INTEGER, ctype TEXT, source TEXT)")
        conn.execute("INSERT INTO ccr VALUES (?, ?, 5, '', '')", (key, zlib.compress(b"wrong")))
    store = CCR(db, workspace_root=tmp_path)
    assert store.migrate_legacy(key) is None
    assert store.stats()["entries"] == 0


def test_stash_and_gc_commit_failures_roll_back_and_close(store, monkeypatch):
    original_connect = store._connect
    connections = []

    @contextmanager
    def failed_commit():
        with original_connect() as conn:
            connections.append(conn)
            yield conn
            raise sqlite3.OperationalError("injected transaction failure")

    monkeypatch.setattr(store, "_connect", failed_commit)
    assert store.stash("rollback") is None
    monkeypatch.setattr(store, "_connect", original_connect)
    assert store.stats()["entries"] == 0
    ref = store.stash("retained")
    assert store.release_session() == 1
    monkeypatch.setattr(store, "_connect", failed_commit)
    report = store.gc_report(0)
    assert not report["ok"] and report["evicted"] == 0
    assert report["error"] == "storage_error"
    monkeypatch.setattr(store, "_connect", original_connect)
    assert store.retrieve(ref) == "retained"
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")


@pytest.mark.parametrize("kwargs", [
    {"kind": "unknown"}, {"source": "\ud800"}, {"source": "x" * 4097},
    {"ctype": 7}, {"summary": None},
])
def test_invalid_metadata_fails_without_minting_reference(store, kwargs):
    assert store.stash("original", **kwargs) is None
    assert store.stats()["entries"] == 0
