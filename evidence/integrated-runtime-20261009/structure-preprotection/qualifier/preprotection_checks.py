"""Offline receipt oracle for structural preprotection; no vendor/runtime imports.

Exact snapshots of the existing pure parser/fence guard avoid inventing a second
Markdown grammar. Independent hashes, typed echoes, raw slices and native wire
comparisons do not trust a worker's candidate as proof of parent publication.
"""
import hashlib
import json
import re

from span_reference.document_structure import document_structure_spans, document_structure_preserved
from span_reference.protected_text import protected_text_preserved, restore_protected_text

STRATEGY = "native-documents-structure-tags-v1"
STRUCTURE_GUARD = "document-structure-v1"
SPAN_CONTRACT = "document-structure-v1-offsets-v1"
OPERATION = "compress_documents_preprotected"
ROOT_STYLE = "compact-root-v1"
FRAMING = ("<tm-", "</tm-", "tm-structure", "headroom_tag")
VALIDATION_SCOPE = "local_preparation_validation_not_native_or_model_recovery"
FEEDBACK = "public_retrieve_updates_access_feedback_telemetry_toin_even_if_projection_reverts"
PUBLICATION = "unknown_no_parent_ack"
BOUNDS = {
    "max_spans_per_rpc": 256, "max_handles": 128, "max_retained_bytes": 8 * 1024 * 1024,
    "max_frame_identities": 2048, "max_validation_attempts": 1024,
    "max_fragment_bytes": 4194304, "max_annotated_message_frame_bytes": 4194304,
}
REQUEST_KEYS = {"id", "op", "model", "messages", "eligible_indices",
                "frozen_message_count", "keep_recent_tool_results", "span_contract", "message_spans"}
HANDLE = re.compile(r"[0-9a-f]{6,64}")
SHA = re.compile(r"[0-9a-f]{64}")
# Exact pinned upstream hash formats, not internal tag placeholders.
MARKERS = re.compile(r"(?:hash=|<<ccr:)([a-f0-9]{24}|[a-f0-9]{12})(?![a-f0-9])")


def need(value, reason):
    if not value:
        raise ValueError(reason)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def same(left, right):
    return canonical(left) == canonical(right)


def text_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def count(value):
    return type(value) is int and value >= 0


def clean(value):
    return type(value) is str and not any(part in value.lower() for part in FRAMING)


def span_descriptors(text):
    spans = document_structure_spans(text)
    need(spans is not None, "unsupported_observed_structure")
    return [span.to_dict() for span in spans]


def source_binding(call, index):
    message = call["messages"][index]
    calls = {c["id"]: c for m in call["messages"] for c in m.get("tool_calls", [])}
    need(message["tool_call_id"] in calls, "span_source_call_missing")
    return text_hash(canonical({
        "model": call["model"], "call": calls[message["tool_call_id"]],
        "result_metadata": {k: v for k, v in message.items() if k != "content"},
        "content_sha256": text_hash(message["content"]),
    }))


def check_span_exchange(call, answer):
    need(type(call) is dict and set(call) == REQUEST_KEYS and call["op"] == OPERATION,
         "preprotection_rpc_shape")
    need(call["span_contract"] == SPAN_CONTRACT, "preprotection_span_contract")
    messages, eligible = call["messages"], call["eligible_indices"]
    need(type(messages) is list and type(eligible) is list and bool(eligible)
         and all(type(i) is int and 0 <= i < len(messages) for i in eligible)
         and eligible == sorted(set(eligible)), "preprotection_eligibility")
    prefix, recent = call["frozen_message_count"], call["keep_recent_tool_results"]
    need(count(prefix) and prefix <= len(messages) and type(recent) is int and recent >= 1,
         "preprotection_protection_bounds")
    tool_indices = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    need(all(i >= prefix and i in tool_indices[:-recent] for i in eligible),
         "preprotection_newest_or_frozen_eligible")
    expected = [{"index": i, "content_sha256": text_hash(messages[i]["content"]),
                 "spans": span_descriptors(messages[i]["content"])} for i in eligible]
    need(same(call["message_spans"], expected), "observed_span_plan_mismatch")
    need(sum(len(e["spans"]) for e in expected) <= BOUNDS["max_spans_per_rpc"], "span_count_bound")
    protected = sorted(set(range(len(messages))) - set(eligible))
    need(answer.get("strategy") == STRATEGY and answer.get("span_contract") == SPAN_CONTRACT
         and answer.get("message_spans_sha256") == text_hash(canonical(expected)),
         "span_contract_or_digest_echo_mismatch")
    need(same(answer.get("eligible_indices"), eligible)
         and same(answer.get("protected_indices"), protected)
         and same(answer.get("document_request"), {"frozen_message_count": prefix,
                                                  "keep_recent_tool_results": recent}),
         "typed_span_protection_echo_mismatch")
    manifest = answer["strategy_manifest"]
    need(answer["strategy_manifest_sha256"] == text_hash(canonical(manifest)), "strategy_manifest_digest")
    need(manifest["strategy"] == STRATEGY and manifest["compress_config"]["compress_system_messages"] is False,
         "wrong_preprotection_manifest")
    need(manifest.get("hooks") is None and manifest.get("extension_discovery") is False
         and manifest.get("external_compressors_selected") == [], "unqualified_pipeline_extensions")
    pp = manifest["preprotection"]
    required = {
        "span_contract": SPAN_CONTRACT, "codec": "task-owned-exact-custom-tag-frames-v1",
        "tag_protection": "public_protect_restore_roundtrip_then_original_pipeline",
        "compress_tagged_content": False, "reserved_families": list(FRAMING), "bounds": BOUNDS,
        "span_authority": "trusted_parent_grammar_worker_mechanical_validation_only",
        "validation": "public_store_retrieve_before_return_access_feedback_side_effects",
        "vendor_content": "exact_nonempty_unique_pristine_slice_no_decoding_or_rekeying",
        "handle_binding": "immutable_raw_and_source_association_no_eviction",
        "recovery": "actual_handler_once_then_validate_unchanged_payload_no_preread",
        "publication": PUBLICATION,
        "measurement": "annotated_upstream_counts_not_final_wire_savings",
        "parent_guards": "structure_fence_source_root_complete_original_nonexpansion",
    }
    need(same(pp, required), "preprotection_contract_manifest")
    router = manifest["router_index"]
    need(type(router) is int and 0 <= router < len(manifest["stages"])
         and manifest["stages"][router]["class"].endswith(".ContentRouter")
         and same(manifest["router_config"], manifest["stages"][router]["config"])
         and manifest["router_config"]["compress_tagged_content"] is False,
         "actual_public_tag_router_not_attested")
    result = answer["preprotection"]
    need(result["span_contract"] == SPAN_CONTRACT and same(result["message_spans"], expected)
         and result["candidate_publication"] == PUBLICATION
         and result["upstream_tokens_scope"] == "annotated_vendor_pass_before_adapter_fallback_not_final_wire"
         and answer["upstream_tokens_scope"] == "annotated_vendor_pass_not_final_wire",
         "candidate_not_claimed_published_required")
    effective = result["effective_protected_indices"]
    need(type(effective) is list and all(type(i) is int and 0 <= i < len(messages) for i in effective)
         and effective == sorted(set(effective)) and set(protected) <= set(effective),
         "effective_protection_mismatch")
    need(type(result["decisions"]) is list and [d.get("index") for d in result["decisions"]] == eligible
         and all(type(d.get("index")) is int for d in result["decisions"]), "decision_inventory_mismatch")
    need(type(result["annotation"]) is list and [a.get("index") for a in result["annotation"]] == eligible,
         "annotation_inventory_mismatch")
    decisions = {d["index"]: d for d in result["decisions"]}
    for entry, annotation in zip(expected, result["annotation"]):
        index = entry["index"]
        original, projected = messages[index], answer["messages"][index]
        frames = 0 if index in effective else len(entry["spans"])
        need(type(annotation["index"]) is int and annotation["pristine_sha256"] == entry["content_sha256"]
             and type(annotation["pristine_chars"]) is int and annotation["pristine_chars"] == len(original["content"])
             and type(annotation["frame_count"]) is int and annotation["frame_count"] == frames
             and count(annotation["annotated_chars"]) and SHA.fullmatch(annotation["annotated_sha256"]) is not None,
             "annotation_receipt_mismatch")
        if frames:
            need(annotation["annotated_chars"] > len(original["content"])
                 and annotation["annotated_sha256"] != annotation["pristine_sha256"], "span_frames_not_attested")
        need(same({k: v for k, v in original.items() if k != "content"},
                  {k: v for k, v in projected.items() if k != "content"}), "worker_changed_native_identity")
        need(clean(projected["content"]), "worker_returned_generated_framing")
        decision = decisions[index]
        need(set(decision) == {"index", "status", "reason"}
             and decision["status"] in ("validated_candidate", "unchanged", "fallback"), "unknown_candidate_decision")
        if projected["content"] != original["content"]:
            need(index not in effective and decision["status"] == "validated_candidate"
                 and decision["reason"] == "checks_passed", "changed_fallback_candidate")
        else:
            need(decision["status"] in ("unchanged", "fallback"), "unchanged_claimed_candidate")
    need(len(messages) == len(answer["messages"])
         and all(same(messages[i], answer["messages"][i]) for i in protected), "worker_changed_protected_input")
    byte_counts = result["internal_input_bytes"]
    need(byte_counts["scope"] == "internal_canonical_message_json_not_native_model_wire"
         and type(byte_counts["pristine"]) is int
         and byte_counts["pristine"] == len(canonical(messages).encode("utf-8"))
         and count(byte_counts["annotated"]) and byte_counts["annotated"] >= byte_counts["pristine"],
         "internal_annotation_counts_not_native_wire")
    return expected


def inventory_counts(value):
    """Report known receipt counters, never aggregate cumulative snapshots."""
    return {
        "attempts": value.get("attempts"), "public_retrieve_entries": value.get("public_retrieve_entries"),
        "validated_candidate_handles": value.get("validated_handles"),
        "retained_raw_fragment_bytes": value.get("retained_bytes"),
        "scope": value.get("scope"), "feedback": value.get("feedback"), "publication": value.get("publication"),
        "candidate_not_claimed_published": value.get("publication") == PUBLICATION,
    }


def retained_validation_summary(received):
    """Best-effort failure report from raw receipts; not an acceptance check."""
    snapshots = []
    for row in received:
        response = row.get("response", {})
        for holder in (response, response.get("result", {})):
            if type(holder) is dict and type(holder.get("preparation_validation")) is dict:
                snapshots.append(holder["preparation_validation"])
    # Latest cumulative snapshot, not sum/delta, and no fabricated zero when absent.
    return {"receipt_validation": "not_checked", **inventory_counts(snapshots[-1] if snapshots else {})}


def check_preprotection(calls, replies, rpc, component):
    need(bool(calls), "preprotected_pipeline_not_called")
    accumulated, validated, expected_by_call, stable_manifest = [], {}, {}, None
    bindings_by_call, candidate_views = {}, {}
    counts = {"table": 0, "ordered-list": 0}
    current = None
    for call in calls:
        answer = replies[str(call["id"])]
        spans = check_span_exchange(call, answer)
        encoded_manifest = canonical(answer["strategy_manifest"])
        need(stable_manifest is None or stable_manifest == encoded_manifest, "task_strategy_manifest_changed")
        stable_manifest = encoded_manifest
        for entry in spans:
            message = call["messages"][entry["index"]]
            expected_by_call[message["tool_call_id"]] = entry["spans"]
            bindings_by_call[message["tool_call_id"]] = source_binding(call, entry["index"])
        current = answer["preparation_validation"]
        need(current["since_attempt"] == len(accumulated) and type(current["since_attempt"]) is int,
             "validation_delta_start_mismatch")
        new_events = current["events"]
        need(type(new_events) is list, "validation_events_required")
        for event in new_events:
            index = event["message_index"]
            need(event["id"] == f"preparation-validation-{len(accumulated) + 1}"
                 and event["rpc_id"] == call["id"] and type(index) is int and index in call["eligible_indices"]
                 and type(event["public_retrieve_entered"]) is bool
                 and HANDLE.fullmatch(event["handle"]) is not None
                 and not ({"tool_call_id", "native_tool_call_id"} & set(event)), "validation_event_identity")
            original = call["messages"][index]["content"]
            need(event["source_sha256"] == text_hash(original)
                 and event["source_binding"] == source_binding(call, index), "validation_source_binding")
            need(event["outcome"] in (
                "validated_candidate", "missing", "invalid_raw_fragment", "contaminated",
                "fragment_byte_limit", "binding_conflict", "not_pristine_slice", "ambiguous_slice",
                "retained_byte_limit", "exception"), "unsupported_validation_outcome")
            if event["outcome"] == "validated_candidate":
                start, end = event["source_start"], event["source_end"]
                need(event["public_retrieve_entered"] is True and type(start) is int and type(end) is int
                     and 0 <= start < end <= len(original), "validated_raw_slice_bounds")
                raw = original[start:end]
                need(clean(raw) and original.find(raw) == start and original.find(raw, start + 1) < 0
                     and event["raw_sha256"] == text_hash(raw)
                     and type(event["raw_utf8_bytes"]) is int and event["raw_utf8_bytes"] == len(raw.encode("utf-8")),
                     "validated_raw_not_exact_pristine_slice")
                identity = (event["source_binding"], raw)
                need(event["handle"] not in validated or validated[event["handle"]] == identity,
                     "validated_handle_rebound")
                validated[event["handle"]] = identity
            accumulated.append(event)
        check_inventory(current, accumulated, validated)
        # Every emitted candidate handle was validated before worker return.
        for index in call["eligible_indices"]:
            returned = answer["messages"][index]["content"]
            if returned != call["messages"][index]["content"]:
                call_id = call["messages"][index]["tool_call_id"]
                candidate_views.setdefault(call_id, []).append(returned)
                for handle in MARKERS.findall(returned):
                    need(handle in validated and validated[handle][0] == source_binding(call, index),
                         "candidate_contains_unvalidated_handle")
    final = component.get("preparation_validation")
    need(type(final) is dict and type(final["since_attempt"]) is int and final["since_attempt"] == 0
         and same(final["events"], accumulated), "final_validation_inventory_mismatch")
    check_inventory(final, accumulated, validated)
    need(component.get("strategy") == STRATEGY and component.get("audit_after_task") is True
         and component.get("recoveries_scope") == "raw_vendor_store_audit_may_contain_annotation_not_native_delivery",
         "raw_store_audit_scope_missing")
    recoveries = component["recoveries"]
    for handle, (_, raw) in validated.items():
        need(recoveries.get(handle) == raw, "raw_store_audit_changed_validated_fragment")
    retrievals = [r["request"] for r in rpc if r.get("request", {}).get("op") == "retrieve"]
    for retrieval in retrievals:
        handle = retrieval["hash"]
        need(handle in validated, "native_recovery_has_no_prior_validation")
        need(str(retrieval["id"]) in replies, "worker_recovery_response_missing")
        result = replies[str(retrieval["id"])]
        need(result["tool_call_id"] == retrieval["tool_call_id"] and result["tool_name"] == "headroom_retrieve"
             and result["success"] is True and clean(result["content"]), "raw_native_recovery_rejected_or_contaminated")
        # Parse envelope only; NEVER deannotate/rekey the decoded original_content.
        from checks import loads  # Shared strict parser; this function runs after module initialization.
        payload = loads(result["content"])
        need(type(payload) is dict and set(payload) == {"hash", "original_content", "original_item_count"}
             and type(payload["original_item_count"]) is int and type(result["items_retrieved"]) is int
             and result["items_retrieved"] >= 0 and payload["original_item_count"] == result["items_retrieved"]
             and payload["hash"] == handle and payload["original_content"] == validated[handle][1],
             "raw_handler_changed_validated_original")
    for descriptors in expected_by_call.values():
        for span in descriptors:
            counts[span["kind"]] += 1
    return {
        "span_contract": SPAN_CONTRACT, "span_counts": counts, "by_call": expected_by_call,
        "validated_bindings": validated, "bindings_by_call": bindings_by_call, "candidate_views": candidate_views,
        "validation": {"receipt_validation": "checked", **inventory_counts(final),
                       "native_requested_fragment_recoveries": len(retrievals),
                       "post_task_audit_handles": len(recoveries), "separate_from_native_recovery": True},
    }


def check_inventory(current, events, validated):
    need(current["version"] == "preparation-validation-v1"
         and current["attempts_semantics"] == "cumulative_not_additive"
         and current["scope"] == VALIDATION_SCOPE and current["feedback"] == FEEDBACK
         and current["publication"] == PUBLICATION
         and current["retention_unit"] == "exact_raw_fragment_utf8_bytes", "validation_side_effect_scope")
    for key, expected in (
        ("attempts", len(events)), ("public_retrieve_entries", sum(e["public_retrieve_entered"] for e in events)),
        ("validated_handles", len(validated)),
        ("retained_bytes", sum(len(raw.encode("utf-8")) for _, raw in validated.values())),
    ):
        need(type(current[key]) is int and current[key] == expected, "validation_count_mismatch:" + key)
    need(count(current["retained_frame_identities"])
         and current["attempts"] <= BOUNDS["max_validation_attempts"]
         and current["validated_handles"] <= BOUNDS["max_handles"]
         and current["retained_bytes"] <= BOUNDS["max_retained_bytes"]
         and current["retained_frame_identities"] <= BOUNDS["max_frame_identities"], "validation_retention_bound")


def check_accepted_structure(original, delivered, reference):
    need(type(reference) is str and delivered.startswith(reference + "\n"), "native_root_prefix_mismatch")
    # Remove ONLY the separately verified exact Root prefix for the existing
    # grammar; its '|' is not a Markdown table. No view bytes are rewritten.
    view = delivered[len(reference) + 1:]
    spans = span_descriptors(original)
    need({"table", "ordered-list"} <= {s["kind"] for s in spans}, "accepted_document_missing_structure_kinds")
    need(clean(delivered) and document_structure_preserved(original, view),
         "native_table_or_ordered_list_changed")
    need(protected_text_preserved(original, delivered), "native_fenced_text_changed")
    return {"table": sum(s["kind"] == "table" for s in spans),
            "ordered-list": sum(s["kind"] == "ordered-list" for s in spans)}


def check_native_publication(protection, call_id, original, delivered, reference):
    view = delivered[len(reference) + 1:]
    for handle in MARKERS.findall(view):
        need(handle in protection["validated_bindings"]
             and protection["validated_bindings"][handle][0] == protection["bindings_by_call"][call_id],
             "native_wire_contains_unvalidated_handle")
    # Expected parent fence-formatting operation only; compare actual delivered
    # bytes, never replace them or "repair" the evidence being judged.
    need(any(restore_protected_text(original, proposed) == view
             for proposed in protection["candidate_views"].get(call_id, [])),
         "native_view_not_returned_unwrapped_candidate")
