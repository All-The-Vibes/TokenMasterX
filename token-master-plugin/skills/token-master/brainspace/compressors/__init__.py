"""The compressor contract.

Every compressor is a callable with this exact signature::

    def compress(content: str, *, stash: StashFn | None = None, **opts) -> str

Hard rules (enforced by the test suite, relied on by the router and MCP server):

1.  **Never raise.** A compressor that hits anything it cannot handle returns the
    input unchanged (a no-op compression is always safe). The whole point of the
    layer is to be invisible when it cannot help — never to break the host.
2.  **Pure text in, text out.** Content arrives as a ``str`` and leaves as a
    ``str``. Closed token-only APIs (Claude, Copilot) cannot carry anything else.
3.  **Exact by default, recoverable views by explicit intent.** ``conservative``
    preserves content (JSON may remove insignificant whitespace). ``navigation``
    permits code skeletons; ``overview`` permits structured/log sampling. All
    other intents bypass. Omitted content must first be handed to ``stash``,
    which must return a valid ``[[BR:HASH|meta]]`` reference. Storage/reference
    failures return the original input, never an irrecoverable marker.
4.  **Deterministic.** Same input + same options + same stash ⇒ same output,
    byte for byte. This is what keeps provider prompt-cache prefixes stable.

``opts`` is compressor-specific (e.g. ``rate`` for prose, ``sample`` for JSON).
Unknown options must be ignored, not rejected — callers pass a shared bag.
"""

from __future__ import annotations

from typing import Callable, Protocol

# A stash function takes the original content plus light metadata and returns a
# stable placeholder string or None on failure. Storage is injected; only the
# canonical reference parser is imported, without constructing/opening a store.
StashFn = Callable[..., str | None]


def report_failure(options: dict, error: Exception) -> None:
    """Optional out-of-band reason; never expose exception text or content."""
    diagnostics = options.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return
    if diagnostics.get("reason") in ("storage_error", "storage_unavailable"):
        return
    reason = (
        "dependency_unavailable" if isinstance(error, ImportError)
        else "invalid_or_unsupported_input" if isinstance(error, (ValueError, TypeError))
        else "transform_error"
    )
    diagnostics.update(reason=reason, error_type=type(error).__name__)


def require_stash(content: str, *, stash, **metadata) -> str:
    """Require a reference from the injected recovery store, or abort the view.

    The callback owns durable storage and retrieval integrity. A syntactically
    valid reference is necessary, not independent proof of recoverability.
    Callers catch failures at the whole-input boundary, never per fragment.
    """
    from ..ccr import PLACEHOLDER_RE

    reference = stash(content, **metadata)
    if not isinstance(reference, str) or not PLACEHOLDER_RE.fullmatch(reference):
        raise ValueError("Storage did not return a recovery reference")
    return reference


class Compressor(Protocol):
    """Structural type for a compressor. Implementations are plain functions."""

    def __call__(self, content: str, *, stash: StashFn | None = None, **opts) -> str:
        ...


def noop(content: str, *, stash: StashFn | None = None, **opts) -> str:
    """The identity compressor — the safe fallback for unknown content.

    Also the reference implementation of the contract: it never raises, returns
    text, is lossless, and is deterministic.
    """
    return content
