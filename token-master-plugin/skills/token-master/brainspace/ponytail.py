"""The pinned Ponytail instruction component, not a host/plugin integration.

Load an explicitly supplied local export; never download, substitute instructions,
or activate a mode. The caller owns authorization, single application, and token
accounting. Upstream instruction text is deliberately not bundled here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import stat

__all__ = ["PonytailInstructions", "load_ponytail_export"]

# Production pins are deliberately independent of the evaluation package.
PINNED_SOURCE_COMMIT = "c982cd411abb53323c4baa1baa3c2f020b8d0b08"
PINNED_INSTRUCTIONS_SHA256 = "da4fb09cff2f6726691ce6591cebc38c95597d79da132e49c6fa2665c4e8a3ff"
MAX_EXPORT_BYTES = 128 * 1024
_REQUIRED_EXPORT_FIELDS = frozenset(
    ("instructions", "source_commit", "instructions_sha256", "mode", "fallback_used")
)


@dataclass(frozen=True, slots=True)
class PonytailInstructions:
    """Validated exact UTF-8 instructions with content-bound, stable identity.

    Neither whitespace nor line endings are normalized. ``identity`` identifies
    these four component fields, not the export's incidental runtime metadata.
    """

    text: str = field(repr=False)
    source_commit: str
    instructions_sha256: str
    mode: str = "full"

    def __post_init__(self) -> None:
        if type(self.text) is not str or not self.text.strip():
            raise ValueError("Ponytail instructions must be nonempty text")
        try:
            content = self.text.encode("utf-8")
        except UnicodeError:
            raise ValueError("Ponytail instructions must be valid UTF-8") from None
        if len(content) > MAX_EXPORT_BYTES:
            raise ValueError("Ponytail instructions exceed the size limit")
        if type(self.mode) is not str or self.mode != "full":
            raise ValueError("Only pinned full-mode Ponytail instructions are supported")
        if type(self.source_commit) is not str or self.source_commit != PINNED_SOURCE_COMMIT:
            raise ValueError("Ponytail source commit does not match the pin")
        if (type(self.instructions_sha256) is not str
                or self.instructions_sha256 != PINNED_INSTRUCTIONS_SHA256):
            raise ValueError("Ponytail instruction digest does not match the pin")
        if hashlib.sha256(content).hexdigest() != self.instructions_sha256:
            raise ValueError("Ponytail instruction bytes do not match the pinned digest")

    def to_dict(self) -> dict[str, str]:
        """Return a detached component representation, without export metadata."""
        return {
            "text": self.text,
            "source_commit": self.source_commit,
            "instructions_sha256": self.instructions_sha256,
            "mode": self.mode,
        }

    @property
    def identity(self) -> str:
        """A domain-separated SHA-256 over the exact component representation."""
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("utf-8")
        return hashlib.sha256(b"ponytail-instructions-v1\0" + payload).hexdigest()


def _parse_export(raw: bytes):
    """Small local strict parser; no dependency on evaluation or pending modules."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def nonfinite(_):
        raise ValueError("nonfinite JSON value")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                           parse_constant=nonfinite)
        # Also reject numeric overflow (e.g. 1e999) and escaped lone surrogates,
        # including in ignored metadata. This validates, not normalizes, text.
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return value
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise ValueError("Invalid Ponytail export JSON") from None


def load_ponytail_export(path: str | os.PathLike[str]) -> PonytailInstructions:
    """Read a bounded local export and fail closed on missing/invalid provenance.

    A regular file is required. At most ``MAX_EXPORT_BYTES + 1`` bytes are read.
    Unknown metadata is permitted (actual exports include runtime receipts), but
    the entire document must be strict UTF-8 JSON. ``fallback_used`` must be the
    JSON boolean false, not a missing field or another false-like value.

    Invalid content raises ValueError; filesystem errors propagate as OSError.
    No file, session, host setting, or request is modified.
    """
    source = Path(path)
    if not stat.S_ISREG(source.stat().st_mode):
        raise ValueError("Ponytail export must be a regular file")
    with source.open("rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("Ponytail export must be a regular file")
        raw = handle.read(MAX_EXPORT_BYTES + 1)
    if len(raw) > MAX_EXPORT_BYTES:
        raise ValueError("Ponytail export exceeds the size limit")
    export = _parse_export(raw)
    if type(export) is not dict or not _REQUIRED_EXPORT_FIELDS.issubset(export):
        raise ValueError("Ponytail export is missing required provenance")
    if export["fallback_used"] is not False:
        raise ValueError("Ponytail fallback exports are not supported")
    return PonytailInstructions(
        text=export["instructions"], source_commit=export["source_commit"],
        instructions_sha256=export["instructions_sha256"], mode=export["mode"],
    )
