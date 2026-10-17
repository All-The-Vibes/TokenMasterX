"""Pinned observable reference tokens, never prices or hidden provider tokens.

Runtime is offline: it reads an explicit local vocabulary or an existing cache.
Missing/corrupt assets produce labeled estimates for diagnostics only. Exact
guards fail closed. ``prepare_tokenizer`` is the explicit download operation.
Protocol v1 counts complete canonical JSON (or literal text), treating special
token spellings as ordinary text, not as a provider's private chat template.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.metadata
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

VOCABULARY_URL = "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
VOCABULARY_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
# Source: OpenAI tiktoken 0.14.0, tiktoken_ext/openai_public.py, cl100k_base.
_PATTERN = r"'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+| ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s"
_ENCODER = None
_TRIED = False
_VERSION = ""


class ReferenceTokenizerUnavailable(ValueError):
    """An estimate is not admissible as an exact reference count."""


def _vocabulary_path() -> Path | None:
    explicit = os.environ.get("BRAINSPACE_TOKENIZER_FILE")
    if explicit:
        return Path(explicit)
    cache = os.environ.get(
        "TIKTOKEN_CACHE_DIR",
        os.environ.get("DATA_GYM_CACHE_DIR", str(Path(tempfile.gettempdir()) / "data-gym-cache")),
    )
    if not cache:
        return None
    return Path(cache) / hashlib.sha1(VOCABULARY_URL.encode()).hexdigest()


def _encoder():
    """Load only verified local bytes; no network, even on a cache race."""
    global _TRIED, _ENCODER, _VERSION
    if _TRIED:
        return _ENCODER
    _TRIED = True
    try:
        import tiktoken
        path = _vocabulary_path()
        data = path.read_bytes() if path is not None else b""
        if hashlib.sha256(data).hexdigest() != VOCABULARY_SHA256:
            return None
        ranks = {base64.b64decode(token, validate=True): int(rank)
                 for token, rank in (line.split() for line in data.splitlines())}
        _ENCODER = tiktoken.Encoding(
            name="cl100k_base", pat_str=_PATTERN, mergeable_ranks=ranks,
            special_tokens={
                "<|endoftext|>": 100257, "<|fim_prefix|>": 100258,
                "<|fim_middle|>": 100259, "<|fim_suffix|>": 100260,
                "<|endofprompt|>": 100276,
            },
        )
        _VERSION = importlib.metadata.version("tiktoken")
    except Exception:
        _ENCODER = None
    return _ENCODER


def serialize(value: object) -> str:
    """Protocol v1: preserve text exactly; canonicalize whole JSON envelopes."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def count_tokens(text: str) -> int:
    """Exact count under the pinned reference, or an explicit error."""
    if not isinstance(text, str):
        raise ValueError("reference measurement requires complete text")
    text.encode("utf-8")  # reject unpaired surrogates, never silently replace
    enc = _encoder()
    if enc is None:
        raise ReferenceTokenizerUnavailable("verified local reference tokenizer unavailable")
    return len(enc.encode_ordinary(text))


@dataclass(frozen=True)
class TokenMeasurement:
    count: int
    exact_reference: bool
    tokenizer_id: str


def measure(text: str) -> TokenMeasurement:
    try:
        return TokenMeasurement(count_tokens(text), True, "cl100k_base")
    except ReferenceTokenizerUnavailable:
        return TokenMeasurement((len(text) + 3) // 4, False, "estimate:ceil-characters/4")


def estimate(text: str) -> int:
    """Compatibility diagnostic; use count_tokens for all proof obligations."""
    return measure(text).count


def backend_info() -> dict:
    exact = _encoder() is not None
    return {
        "tokenizer_id": "cl100k_base" if exact else "estimate:ceil-characters/4",
        "tokenizer_version": _VERSION if exact else "1",
        "vocabulary_id": VOCABULARY_SHA256 if exact else None,
        "protocol_id": "canonical-json-or-text/ordinary",
        "protocol_version": "1",
        "exact_reference": exact,
        "provider_native": False,
    }


def measurement_identity(boundary: str):
    from .token_ledger import MeasurementIdentity
    info = backend_info()
    if not info["exact_reference"]:
        raise ReferenceTokenizerUnavailable("certification requires the exact reference tokenizer")
    return MeasurementIdentity(
        tokenizer_id=info["tokenizer_id"], tokenizer_version=info["tokenizer_version"],
        vocabulary_id=info["vocabulary_id"], extraction_protocol_id=info["protocol_id"],
        extraction_protocol_version=info["protocol_version"], boundary=boundary,
    )


def guard_replacement(before: object, after: object, *, max_bytes: int | None = None,
                      max_tokens: int | None = None) -> bool:
    """Strict token reduction of the FINAL representation and optional byte cap."""
    try:
        original, replacement = serialize(before), serialize(after)
        wire_bytes = len(replacement.encode("utf-8"))
        if max_bytes is not None:
            if type(max_bytes) is not int or max_bytes <= 0 or wire_bytes > max_bytes:
                return False
        a, b = count_tokens(replacement), count_tokens(original)
        if max_tokens is not None:
            if type(max_tokens) is not int or max_tokens < 0 or a > max_tokens:
                return False
        return a < b
    except (TypeError, ValueError, UnicodeError):
        return False


def reduction(before: str, after: str) -> dict:
    info = backend_info()
    b, a = estimate(before), estimate(after)
    return {
        "tokens_before": b, "tokens_after": a, "tokens_saved": b - a,
        "pct_reduction": round((b - a) / b * 100, 1) if b else 0.0,
        "ratio": round(b / a, 2) if a else None,
        "backend": "tiktoken" if info["exact_reference"] else "heuristic",
        **info,
    }


def prepare_tokenizer(destination: str | Path, *, allow_download: bool = False) -> dict:
    """Explicit one-time acquisition; TLS and content digest are both checked."""
    if not allow_download:
        raise ValueError("tokenizer download requires explicit opt-in")
    from urllib.request import urlopen
    path = Path(destination).resolve()
    with urlopen(VOCABULARY_URL, timeout=30) as response:
        data = response.read(2 * 1024 * 1024 + 1)
    if hashlib.sha256(data).hexdigest() != VOCABULARY_SHA256:
        raise ValueError("reference vocabulary failed digest verification")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)
    return {"vocabulary_id": VOCABULARY_SHA256, "bytes": len(data), "path": str(path)}
