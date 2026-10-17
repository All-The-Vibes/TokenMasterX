"""Scoped, content-addressed recovery of exact UTF-8 text.

``stash`` returns a reference or None (callers must keep the original on failure).
``retrieve`` returns exact text or None. Paging/search additionally report errors.
All reads verify the *entire* original's SHA-256, byte length and character count.
No Unicode normalization or replacement decoding is performed.

Default style ``annotated-v1`` retains V2 markers containing a full content
digest and separately encoded provenance.
Identical content is deduplicated inside a scope, but different source/kind/
summary metadata intentionally produces different markers. ``kind="fragment"``
is the conservative default: callers that stash a whole original must explicitly
use ``kind="root"``. Source is an opaque label, not an inferred filesystem path;
its canonical percent encoding preserves delimiters, Unicode and Windows paths.
Bare lowercase 6..64 hex prefixes remain supported within the current scope,
but ambiguous prefixes and unscoped legacy display markers are rejected.

Opt-in ``reference_style="compact-root-v1"`` requires ``kind="root"`` and
returns ``[[BR:<64-hex opaque ID>|r=1]]``. The ID hashes the style, scope,
content digest and canonical full metadata; it is not a bare content digest.
The complete marker must resolve to an exact minted ccr_references row before
metadata and blob verification. Metadata remains server-side without deletion
or normalization. Hash checks use the existing SHA-256 assumptions, not an
authentication claim against a coherent database rewrite. GC removes compact
reference rows with their blobs, so an unavailable compact ref is not_found.

Default stores are rooted at the supplied workspace (otherwise the captured cwd),
never discovered upward. Session IDs further isolate private scopes. Shared stores
require shared=True on both readers and writers, the same DB and scope name.
Only shared=True honors BRAINSPACE_CCR. This is logical isolation, not an OS-level
access-control boundary against someone who can read/modify the database.

Stash and successful reads pin originals for the calling session. Pins do not
silently expire; release/release_session is required before opt-in GC can evict
them. Without a session ID the workspace has a persistent default lease. TTL is
an idle-age cleanup policy applied only by explicit GC, not a read-time expiry.
Quotas count compressed content bytes, not SQLite/provenance/lease overhead.

Legacy ``ccr`` tables are left untouched and never queried for normal recovery.
With an explicitly supplied db_path, migrate_legacy(full_sha256) is an explicit
per-record assertion that the legacy record belongs in the new scope.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import time
import zlib
from contextlib import contextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import quote


PLACEHOLDER_RE = re.compile(r"\[\[BR:([0-9a-f]{6,64})(?:\|[^\]]*)?\]\]")
_BARE_RE = re.compile(r"[0-9a-f]{6,64}")
_V2_RE = re.compile(r"\[\[BR:([0-9a-f]{64})\|v=2;scope=([0-9a-f]{64});[^\]\r\n]*\]\]")
_COMPACT_ROOT_RE = re.compile(r"\[\[BR:([0-9a-f]{64})\|r=1\]\]")
_PAGE_LIMIT = 32768
_SEARCH_LIMIT = 20
_CONTEXT_LIMIT = 1024
_METADATA_LIMIT = 4096
_STORAGE_ERRORS = (sqlite3.Error, OSError)


def make_placeholder(short_hash: str, ctype: str = "", source: str = "", size: str = "") -> str:
    """Legacy display helper; not a scoped V2 reference issuer."""
    meta = "; ".join(p for p in (ctype, source, size) if p)
    return f"[[BR:{short_hash}|{meta}]]" if meta else f"[[BR:{short_hash}]]"


def parse_placeholders(text: str) -> list[str]:
    """Extract marker IDs for bookkeeping, not validation (V2 IDs are content hashes)."""
    return PLACEHOLDER_RE.findall(text)


def _identity(parts: list) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def _resolve_db_path(workspace_root: Path | None = None, *, shared: bool = False) -> Path:
    root = workspace_root if workspace_root is not None else Path.cwd().resolve()
    env = os.environ.get("BRAINSPACE_CCR") if shared else None
    if env:
        path = Path(os.path.expandvars(os.path.expanduser(env)))
        if not path.is_absolute():
            raise ValueError("BRAINSPACE_CCR must be absolute for explicit sharing")
        return path.resolve()
    return root / ".token-master" / "ccr.sqlite"


def _valid_bounds(offset, limit) -> bool:
    return type(offset) is int and offset >= 0 and type(limit) is int and limit > 0


def _decode_verified(full_hash, blob, orig_bytes, total_chars=None) -> str:
    """Reject damaged, trailing, truncated or substituted zlib/UTF-8 data."""
    if (not isinstance(full_hash, str) or re.fullmatch(r"[0-9a-f]{64}", full_hash) is None
            or type(orig_bytes) is not int or orig_bytes < 0
            or (total_chars is not None and (type(total_chars) is not int or total_chars < 0))):
        raise ValueError("invalid stored identity")
    decoder = zlib.decompressobj()
    raw = decoder.decompress(blob, orig_bytes + 1)
    if (not decoder.eof or decoder.unused_data or decoder.unconsumed_tail
            or len(raw) != orig_bytes or hashlib.sha256(raw).hexdigest() != full_hash):
        raise ValueError("content integrity check failed")
    text = raw.decode("utf-8")
    if total_chars is not None and len(text) != total_chars:
        raise ValueError("character length mismatch")
    return text


class CCR:
    """Lazy SQLite store; every connection is explicitly closed, including errors."""

    def __init__(
        self,
        db_path: Optional[os.PathLike | str] = None,
        *,
        workspace_root: Optional[os.PathLike | str] = None,
        scope: Optional[str] = None,
        session_id: Optional[str] = None,
        shared: bool = False,
    ):
        if scope is not None and (not isinstance(scope, str) or not scope):
            raise ValueError("scope must be a nonempty string or None")
        if session_id is not None and (not isinstance(session_id, str) or not session_id):
            raise ValueError("session_id must be a nonempty string or None")
        if type(shared) is not bool:
            raise ValueError("shared must be boolean")
        self.workspace_root = Path(workspace_root).resolve() if workspace_root is not None else Path.cwd().resolve()
        self.session_id = session_id
        self.shared = shared
        self.scope = scope or "default"
        self._workspace = os.path.normcase(str(self.workspace_root))
        self._scope_key = _identity(
            ["ccr-v2", "shared", self.scope] if shared
            else ["ccr-v2", "private", self._workspace, self.scope, session_id]
        )
        self._explicit_db_path = db_path is not None
        self._db_path = Path(db_path).resolve() if db_path is not None else _resolve_db_path(self.workspace_root, shared=shared)
        self.last_gc: dict | None = None

    @contextmanager
    def _connect(self):
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), timeout=5.0)
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS ccr_v2 (
                    scope TEXT NOT NULL, hash TEXT NOT NULL, blob BLOB NOT NULL,
                    orig_bytes INTEGER NOT NULL, total_chars INTEGER NOT NULL,
                    created REAL NOT NULL, last_access REAL NOT NULL,
                    hits INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(scope, hash)
                );
                CREATE TABLE IF NOT EXISTS ccr_references (
                    scope TEXT NOT NULL, ref TEXT NOT NULL, hash TEXT NOT NULL,
                    metadata TEXT NOT NULL, PRIMARY KEY(scope, ref),
                    FOREIGN KEY(scope, hash) REFERENCES ccr_v2(scope, hash) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS ccr_leases (
                    scope TEXT NOT NULL, hash TEXT NOT NULL, session TEXT NOT NULL,
                    PRIMARY KEY(scope, hash, session),
                    FOREIGN KEY(scope, hash) REFERENCES ccr_v2(scope, hash) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS ccr_evictions (
                    scope TEXT NOT NULL, hash TEXT NOT NULL, reason TEXT NOT NULL,
                    PRIMARY KEY(scope, hash)
                );
            """)
            with conn:
                yield conn
        finally:
            conn.close()

    def _session_key(self, session_id=None):
        session = self.session_id if session_id is None else session_id
        if session is not None and (not isinstance(session, str) or not session):
            raise ValueError("invalid session")
        return _identity([self._workspace, session])

    def _marker(self, full_hash, metadata):
        fields = [
            "v=2", f"scope={self._scope_key}", f"kind={metadata['kind']}",
            "source=" + quote(metadata["source"], safe="/:._-"),
            "type=" + quote(metadata["ctype"], safe="._-"),
            "summary=" + quote(metadata["summary"], safe="._-"),
            f"chars={metadata['chars']}", f"bytes={metadata['bytes']}",
        ]
        return f"[[BR:{full_hash}|{';'.join(fields)}]]"

    def _compact_marker(self, full_hash, metadata):
        payload = json.dumps(
            ["compact-root-v1", self._scope_key, full_hash, metadata],
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        return f"[[BR:{hashlib.sha256(payload).hexdigest()}|r=1]]"

    def _parse_ref(self, ref):
        if not isinstance(ref, str):
            return None, "invalid_reference"
        if _BARE_RE.fullmatch(ref):
            return ref, None
        compact = _COMPACT_ROOT_RE.fullmatch(ref)
        if compact:
            return compact[1], None
        match = _V2_RE.fullmatch(ref)
        if not match:
            return None, "invalid_reference"
        if match[2] != self._scope_key:
            return None, "foreign_reference"
        return match[1], None

    def _pin(self, conn, full_hash, session_id=None):
        conn.execute("INSERT OR IGNORE INTO ccr_leases VALUES (?, ?, ?)",
                     (self._scope_key, full_hash, self._session_key(session_id)))

    def _read(self, conn, ref):
        """Called inside a write transaction: verification and pin are atomic vs GC."""
        key, error = self._parse_ref(ref)
        if error:
            return None, error
        compact = _COMPACT_ROOT_RE.fullmatch(ref) is not None
        encoded_metadata = None
        if compact:
            references = conn.execute(
                "SELECT hash,metadata FROM ccr_references WHERE scope=? AND ref=? LIMIT 2",
                (self._scope_key, ref),
            ).fetchall()
            if len(references) > 1:
                return None, "ambiguous_reference"
            if not references:
                return None, "not_found"
            content_hash, encoded_metadata = references[0]
            rows = conn.execute(
                """SELECT hash, blob, orig_bytes, total_chars FROM ccr_v2
                   WHERE scope=? AND hash=? LIMIT 2""", (self._scope_key, content_hash),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT hash, blob, orig_bytes, total_chars FROM ccr_v2
                   WHERE scope=? AND hash LIKE ? LIMIT 2""", (self._scope_key, key + "%"),
            ).fetchall()
        if len(rows) > 1:
            return None, "ambiguous_reference"
        if not rows:
            if compact:
                return None, "corrupt"
            gone = conn.execute(
                "SELECT reason FROM ccr_evictions WHERE scope=? AND hash=?",
                (self._scope_key, key),
            ).fetchone()
            return None, gone[0] if gone else "not_found"
        full_hash, blob, orig_bytes, total_chars = rows[0]
        metadata = None
        if ref.startswith("[["):
            if not compact:
                row = conn.execute(
                    "SELECT metadata FROM ccr_references WHERE scope=? AND ref=? AND hash=?",
                    (self._scope_key, ref, full_hash),
                ).fetchone()
                if not row:
                    return None, "invalid_reference"
                encoded_metadata = row[0]
            if encoded_metadata is None:
                return None, "corrupt"
            try:
                metadata = json.loads(encoded_metadata)
                if (not isinstance(metadata, dict)
                        or set(metadata) != {"kind", "source", "ctype", "summary", "chars", "bytes"}
                        or metadata["kind"] not in ("root", "fragment")
                        or any(not isinstance(metadata[k], str) for k in ("source", "ctype", "summary"))
                        or sum(len(metadata[k]) for k in ("source", "ctype", "summary")) > _METADATA_LIMIT
                        or type(metadata["bytes"]) is not int or type(metadata["chars"]) is not int
                        or (compact and (
                            metadata["kind"] != "root"
                            or json.dumps(metadata, sort_keys=True, ensure_ascii=True) != encoded_metadata))
                        or (self._compact_marker(full_hash, metadata) if compact
                            else self._marker(full_hash, metadata)) != ref
                        or metadata["bytes"] != orig_bytes or metadata["chars"] != total_chars):
                    return None, "corrupt"
            except (ValueError, TypeError, KeyError, RecursionError):
                return None, "corrupt"
        try:
            text = _decode_verified(full_hash, blob, orig_bytes, total_chars)
        except (ValueError, TypeError, OverflowError, zlib.error):
            return None, "corrupt"
        return {"content": text, "sha256": full_hash, "total_chars": total_chars,
                "total_bytes": orig_bytes, "metadata": metadata}, None

    def _load(self, ref):
        _, error = self._parse_ref(ref)
        if error:
            return None, error
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                record, error = self._read(conn, ref)
                if error:
                    return None, error
                self._pin(conn, record["sha256"])
                conn.execute(
                    "UPDATE ccr_v2 SET hits=hits+1, last_access=? WHERE scope=? AND hash=?",
                    (time.time(), self._scope_key, record["sha256"]),
                )
                return record, None
        except _STORAGE_ERRORS:
            return None, "storage_error"

    def stash(self, content: str, ctype: str = "", source: str = "", summary: str = "",
              *, kind: str = "fragment", reference_style: str = "annotated-v1") -> Optional[str]:
        """Store exact text and pin it; never mint a reference after storage failure.

        Metadata strings have a combined 4096-character cap. Empty input, invalid
        UTF-8 text (e.g. lone surrogates), invalid metadata and corrupt existing
        rows fail closed. No content repair/overwrite happens implicitly.
        Default style annotated-v1 retains the existing V2 marker bytes.
        compact-root-v1 is an explicit root-only opaque reference; all metadata
        remains in the store.
        """
        try:
            if not isinstance(content, str) or not content:
                return None
            if (type(reference_style) is not str
                    or reference_style not in ("annotated-v1", "compact-root-v1")
                    or (reference_style == "compact-root-v1" and kind != "root")
                    or kind not in ("root", "fragment")
                    or any(not isinstance(p, str) for p in (ctype, source, summary))
                    or sum(map(len, (ctype, source, summary))) > _METADATA_LIMIT):
                return None
            raw = content.encode("utf-8")
            full_hash = hashlib.sha256(raw).hexdigest()
            metadata = dict(kind=kind, ctype=ctype, source=source, summary=summary,
                            chars=len(content), bytes=len(raw))
            compact = reference_style == "compact-root-v1"
            ref = self._compact_marker(full_hash, metadata) if compact else self._marker(full_hash, metadata)
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                if compact and conn.execute(
                    "SELECT 1 FROM ccr_references WHERE scope=? AND ref=?",
                    (self._scope_key, ref),
                ).fetchone():
                    previous, error = self._read(conn, ref)
                    if (error or previous["sha256"] != full_hash or previous["metadata"] != metadata):
                        raise ValueError("existing compact reference integrity check failed")
                row = conn.execute(
                    "SELECT blob, orig_bytes, total_chars FROM ccr_v2 WHERE scope=? AND hash=?",
                    (self._scope_key, full_hash),
                ).fetchone()
                if row and _decode_verified(full_hash, *row) != content:
                    return None
                now = time.time()
                conn.execute(
                    """INSERT INTO ccr_v2 VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                       ON CONFLICT(scope, hash) DO UPDATE SET last_access=excluded.last_access""",
                    (self._scope_key, full_hash, zlib.compress(raw, level=6), len(raw), len(content), now, now),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO ccr_references VALUES (?, ?, ?, ?)",
                    (self._scope_key, ref, full_hash, json.dumps(metadata, sort_keys=True, ensure_ascii=True)),
                )
                record, error = self._read(conn, ref)
                if error or (compact and (record["sha256"] != full_hash or record["metadata"] != metadata)):
                    raise ValueError("reference integrity check failed")
                self._pin(conn, full_hash)
                conn.execute("DELETE FROM ccr_evictions WHERE scope=? AND hash=?",
                             (self._scope_key, full_hash))
            return ref
        except (*_STORAGE_ERRORS, ValueError, TypeError, OverflowError, zlib.error):
            return None

    def retrieve(self, ref: str) -> Optional[str]:
        """Return exact verified text, or None for any failed recovery."""
        record, _ = self._load(ref)
        return record["content"] if record else None

    def retrieve_page(self, ref, offset=0, limit=_PAGE_LIMIT) -> dict:
        """Character-offset paging, capped at 32768 characters (not bytes).

        sha256 always covers the FULL UTF-8 original; page_sha256 covers just this
        page. next_offset is None only on completion. No partial failed content is
        returned. A successful terminal empty page at total_chars is allowed.
        """
        result = dict(ok=False, content=None, offset=offset, next_offset=None,
                      total_chars=None, total_bytes=None, sha256=None, page_sha256=None,
                      complete=False, error=None, metadata=None, encoding="utf-8")
        if not _valid_bounds(offset, limit):
            return dict(result, error="invalid_bounds")
        record, error = self._load(ref)
        if error:
            return dict(result, error=error)
        if offset > record["total_chars"]:
            return dict(result, error="invalid_offset")
        page = record["content"][offset:offset + min(limit, _PAGE_LIMIT)]
        end = offset + len(page)
        complete = end == record["total_chars"]
        return dict(result, **{k: v for k, v in record.items() if k != "content"},
                    ok=True, content=page, page_sha256=hashlib.sha256(page.encode("utf-8")).hexdigest(),
                    next_offset=None if complete else end, complete=complete)

    def search(self, ref, query, offset=0, limit=_SEARCH_LIMIT, context_lines=1) -> dict:
        """Literal, case-sensitive, overlapping substring search; no regex/fuzzy mode.

        offset/next_offset are original character positions, not result indices.
        At most 20 results, 10 context lines per side, and 1024 context characters
        per result are returned. Truncated contexts are labeled separately from
        complete (which means all matches at/after offset have been enumerated).
        Query length is limited to 4096 characters. Line/column are one-based,
        using LF as the line delimiter; start/end and context bounds are zero-based.
        """
        result = dict(ok=False, results=[], offset=offset, next_offset=None,
                      total_chars=None, total_bytes=None, sha256=None,
                      complete=False, error=None)
        if not _valid_bounds(offset, limit) or type(context_lines) is not int or context_lines < 0:
            return dict(result, error="invalid_bounds")
        if not isinstance(query, str) or not query or len(query) > 4096:
            return dict(result, error="invalid_query")
        record, error = self._load(ref)
        if error:
            return dict(result, error=error)
        text = record["content"]
        if offset > len(text):
            return dict(result, error="invalid_offset")
        limit, context_lines = min(limit, _SEARCH_LIMIT), min(context_lines, 10)
        matches: list[dict] = []
        position = text.find(query, offset)
        while position >= 0 and len(matches) < limit:
            end = position + len(query)
            start_context = text.rfind("\n", 0, position) + 1
            end_context = text.find("\n", end)
            end_context = len(text) if end_context < 0 else end_context
            for _ in range(context_lines):
                if start_context > 0:
                    start_context = text.rfind("\n", 0, start_context - 1) + 1
                if end_context < len(text):
                    following = text.find("\n", end_context + 1)
                    end_context = len(text) if following < 0 else following
            wanted_start, wanted_end = start_context, end_context
            if end_context - start_context > _CONTEXT_LIMIT:
                start_context = max(start_context, position - _CONTEXT_LIMIT // 4)
                end_context = min(end_context, start_context + _CONTEXT_LIMIT)
            matches.append(dict(
                start=position, end=end, line=text.count("\n", 0, position) + 1,
                column=position - text.rfind("\n", 0, position),
                content=text[start_context:end_context], context_start=start_context,
                context_end=end_context,
                context_truncated=(start_context, end_context) != (wanted_start, wanted_end),
            ))
            position = text.find(query, position + 1)
        return dict(result, ok=True, results=matches,
                    next_offset=None if position < 0 else matches[-1]["start"] + 1,
                    total_chars=len(text), total_bytes=record["total_bytes"],
                    sha256=record["sha256"], complete=position < 0,
                    limit=limit, context_lines=context_lines)

    def pin(self, ref, session_id=None) -> bool:
        """Verify and pin a reference for this workspace's specified/default session."""
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                record, error = self._read(conn, ref)
                if error:
                    return False
                self._pin(conn, record["sha256"], session_id)
            return True
        except (*_STORAGE_ERRORS, ValueError):
            return False

    def release(self, ref, session_id=None) -> bool:
        """Release one content lease (all provenance variants share the same lease)."""
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                record, error = self._read(conn, ref)
                if error:
                    return False
                count = conn.execute(
                    "DELETE FROM ccr_leases WHERE scope=? AND hash=? AND session=?",
                    (self._scope_key, record["sha256"], self._session_key(session_id)),
                ).rowcount
            return bool(count)
        except (*_STORAGE_ERRORS, ValueError):
            return False

    def release_session(self, session_id=None) -> int:
        """Release all this workspace/session's leases in this scope; return count.

        Release only after callers no longer need outstanding references. It does
        not delete originals. A subsequent stash/read/pin starts a new lease.
        """
        try:
            with self._connect() as conn:
                return conn.execute(
                    "DELETE FROM ccr_leases WHERE scope=? AND session=?",
                    (self._scope_key, self._session_key(session_id)),
                ).rowcount
        except (*_STORAGE_ERRORS, ValueError):
            return 0

    def stats(self) -> dict:
        """Scoped statistics; do not inspect or expose unscoped legacy records."""
        try:
            with self._connect() as conn:
                entries, orig, stored, hits = conn.execute(
                    """SELECT COUNT(*), COALESCE(SUM(orig_bytes), 0),
                              COALESCE(SUM(LENGTH(blob)), 0), COALESCE(SUM(hits), 0)
                       FROM ccr_v2 WHERE scope=?""", (self._scope_key,),
                ).fetchone()
                pins, sessions = conn.execute(
                    "SELECT COUNT(DISTINCT hash), COUNT(DISTINCT session) FROM ccr_leases WHERE scope=?",
                    (self._scope_key,),
                ).fetchone()
            return dict(entries=entries, original_bytes=orig, stored_bytes=stored,
                        compression_ratio=round(orig / stored, 2) if stored else None,
                        total_retrievals=hits, db_path=str(self._db_path), scope=self._scope_key,
                        shared=self.shared, pinned_entries=pins, active_sessions=sessions,
                        legacy_migration="explicit_full_digest_import_only",
                        last_gc=self.last_gc, ttl_policy="explicit_gc_idle_age",
                        quota_unit="compressed_content_bytes")
        except _STORAGE_ERRORS:
            return dict(entries=0, db_path=str(self._db_path), error="unreadable", last_gc=self.last_gc)

    def gc(self, max_bytes: int = 500 * 1024 * 1024, *, ttl_seconds=None) -> int:
        """Compatibility count API; see last_gc or gc_report for success/failure."""
        return self.gc_report(max_bytes, ttl_seconds=ttl_seconds)["evicted"]

    def gc_report(self, max_bytes: int = 500 * 1024 * 1024, *, ttl_seconds=None) -> dict:
        """Opt-in scoped LRU/idle-TTL cleanup; never evict ANY session's pinned data.

        The transaction serializes pin/stash/read against cleanup. quota_met=False
        truthfully reports when protected content prevents meeting the target.
        Failure reports no committed evictions. last_gc is instance-local, not a
        claim about another process's most recent cleanup.
        """
        report = dict(ok=False, error=None, evicted=0, expired=0, max_bytes=max_bytes,
                      ttl_seconds=ttl_seconds, stored_bytes_before=None, stored_bytes_after=None,
                      pinned_entries=0, expired_pinned_entries=0, quota_met=False)
        if (type(max_bytes) is not int or max_bytes < 0
                or (ttl_seconds is not None and (
                    type(ttl_seconds) not in (int, float) or ttl_seconds < 0
                    or (type(ttl_seconds) is float and not math.isfinite(ttl_seconds))))):
            self.last_gc = dict(report, error="invalid_policy")
            return self.last_gc
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                rows = conn.execute(
                    """SELECT hash, LENGTH(blob), last_access,
                              EXISTS(SELECT 1 FROM ccr_leases l WHERE l.scope=c.scope AND l.hash=c.hash)
                       FROM ccr_v2 c WHERE scope=? ORDER BY last_access, hash""",
                    (self._scope_key,),
                ).fetchall()
                total = sum(row[1] for row in rows)
                report["stored_bytes_before"] = total
                now = time.time()
                for full_hash, length, accessed, pinned in rows:
                    expired = ttl_seconds is not None and now - accessed >= ttl_seconds
                    if pinned:
                        report["pinned_entries"] += 1
                        report["expired_pinned_entries"] += int(expired)
                        continue
                    if not expired and total <= max_bytes:
                        continue
                    conn.execute("DELETE FROM ccr_v2 WHERE scope=? AND hash=?", (self._scope_key, full_hash))
                    conn.execute(
                        "INSERT OR REPLACE INTO ccr_evictions VALUES (?, ?, ?)",
                        (self._scope_key, full_hash, "expired" if expired else "evicted"),
                    )
                    total -= length
                    report["evicted"] += 1
                    report["expired"] += int(expired)
                report.update(ok=True, stored_bytes_after=total, quota_met=total <= max_bytes)
            self.last_gc = report
        except _STORAGE_ERRORS:
            self.last_gc = dict(report, ok=False, error="storage_error", evicted=0, expired=0,
                                quota_met=False, stored_bytes_after=None)
        return self.last_gc

    def migrate_legacy(self, full_sha256: str) -> Optional[str]:
        """Explicitly import ONE verified legacy record into this scope.

        Requires explicit db_path and a full lowercase digest. This is an opt-in
        ownership assertion, not automatic cross-workspace discovery. The original
        table is never modified; failed imports leave the legacy record recoverable.
        Provenance defaults to fragment because legacy rows cannot prove rootness.
        """
        if (not self._explicit_db_path or not isinstance(full_sha256, str)
                or re.fullmatch(r"[0-9a-f]{64}", full_sha256) is None):
            return None
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT blob, orig_bytes, ctype, source FROM ccr WHERE hash=?", (full_sha256,),
                ).fetchone()
                if row is None:
                    return None
                text = _decode_verified(full_sha256, row[0], row[1])
            return self.stash(text, ctype=row[2] or "", source=row[3] or "")
        except (*_STORAGE_ERRORS, ValueError, TypeError, OverflowError, zlib.error):
            return None
