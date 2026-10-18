"""Explicit offline request adapter, not a host interceptor or task certificate."""
from __future__ import annotations

from typing import Any

from . import tokens
from .ccr import CCR
from .request_policy import (
    SERIALIZATION, RequestPlan, RequestPolicy, SourceReadInfo, TransformResult, plan_request,
)
from .router import route_typed


def request_measurement_identity() -> dict:
    """Identity for policy serialization, NOT tokens.serialize's sorted JSON."""
    return {
        **tokens.backend_info(), "protocol_id": SERIALIZATION,
        "boundary": "serialized-request", "tokenization": "ordinary",
        "complete_task_trace": False,
    }


def prepare_request(
    request: Any, policy: RequestPolicy | None = None, *,
    ccr: CCR, intent: str | None = None, protocol: str | None = None,
    stable_prefix_messages: int = 0, exact_message_indices: tuple[int, ...] = (),
    hint: str | None = None,
    source_reads: tuple[SourceReadInfo, ...] = (),
) -> RequestPlan:
    """Guard the whole materialized request, with exact full-root recovery.

    The caller supplies workspace/session-scoped CCR and explicit protocol/intent.
    Storage may retain recovery roots even when the final budget rejects a view.
    Send ``plan.serialized`` without extra wrappers or recheck the final boundary.
    Measurement identity is separate; no model call or complete trace is claimed.
    Successful source-read observations must come from the trusted executor and
    are never inserted into model-visible messages. V2 binds them to the exact
    candidate before using their filenames; no hints cross call boundaries.
    V4 bypasses routing and always uses conservative JSON compaction. Its fixed
    presentation is the complete compact JSON payload, newline, then scoped
    JSON root reference. The annotated tool string is not standalone JSON.
    """
    def transform(content: str, source_hint: str | None = hint) -> TransformResult:
        roots = []

        def stash(original: str, **metadata):
            reference = ccr.stash(original, **metadata)
            if original == content and metadata.get("kind") == "root" and reference:
                roots.append(reference)
            return reference

        view, ctype = route_typed(content, source_hint, stash=stash, intent=intent, diagnostics={})
        if view == content:
            return TransformResult(content, "")
        reference = next((ref for ref in roots if ref in view), None)
        if reference is None:
            reference = ccr.stash(content, ctype=ctype.value,
                                  source="request-tool-content", kind="root")
        if not reference:
            return TransformResult(content, "")
        if reference not in view:
            view += "\n" + reference
        return TransformResult(view, reference)

    def json_transform(content: str, info: SourceReadInfo) -> TransformResult:
        from .compressors.json_compressor import compress_json

        compact = compress_json(content, intent="conservative")
        if compact == content:
            return TransformResult(content, "")
        reference = ccr.stash(content, ctype="json", source=info.source_path, kind="root")
        if not reference:
            return TransformResult(content, "")
        return TransformResult(compact + "\n" + reference, reference)

    def v5_transform(content: str, info: SourceReadInfo) -> TransformResult:
        from .v5_reducer import transform_v5_content

        return transform_v5_content(
            content,
            info,
            stash_compact_root=lambda orig, src, ctype: ccr.stash(
                orig, source=src, ctype=ctype, kind="root", reference_style="compact-root-v1"
            ),
            intent=intent or "conservative",
        )

    return plan_request(
        request, policy=policy, protocol=protocol, intent=intent,
        transform=transform, recover=ccr.retrieve, count=tokens.count_tokens,
        stable_prefix_messages=stable_prefix_messages,
        exact_message_indices=exact_message_indices,
        source_reads=source_reads,
        source_transform=lambda content, info: transform(content, info.source_path),
        json_transform=json_transform,
        v5_transform=v5_transform,
    )
