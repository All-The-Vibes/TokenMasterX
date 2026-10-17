"""Small synthetic OFFLINE checker records, never native task input or evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from checks import CONTRACT, actions
from span_reference.document_structure import document_structure_spans

COMPACT_REF = "[[BR:" + "a" * 64 + "|r=1]]"
TABLE = "| Key | Value |\r\n|---|---|\r\n| 雪 | retained |\r\n"
ORDERED = "1. Config first.\n2. Workspace second.\n\n"
FENCE = "```python\nvalue = '雪'\n```\n"
RAW = "Recoverable café narrative.\n"
SOURCE = "Original operational explanation.\n\n" + TABLE + "\n" + ORDERED + FENCE + "\n" + RAW
VIEW = "Brief.\n\n" + TABLE + "\n" + ORDERED + FENCE
HANDLE = "abcdef123456"


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def manifest():
    return {
        "strategy": "native-documents-structure-tags-v1",
        "vendor_commit": "1cf496612e781ef8d67ff87ee4f78037492f0bc7",
        "compress_config": {"compress_system_messages": False},
        "hooks": None, "extension_discovery": False, "external_compressors_selected": [],
        "router_index": 0, "router_config": {"compress_tagged_content": False},
        "stages": [{"class": "headroom.transforms.content_router.ContentRouter",
                    "config": {"compress_tagged_content": False}}],
        "preprotection": {
            "span_contract": "document-structure-v1-offsets-v1",
            "codec": "task-owned-exact-custom-tag-frames-v1",
            "tag_protection": "public_protect_restore_roundtrip_then_original_pipeline",
            "compress_tagged_content": False,
            "reserved_families": ["<tm-", "</tm-", "tm-structure", "headroom_tag"],
            "bounds": {"max_spans_per_rpc": 256, "max_handles": 128, "max_retained_bytes": 8388608,
                       "max_frame_identities": 2048, "max_validation_attempts": 1024,
                       "max_fragment_bytes": 4194304, "max_annotated_message_frame_bytes": 4194304},
            "span_authority": "trusted_parent_grammar_worker_mechanical_validation_only",
            "validation": "public_store_retrieve_before_return_access_feedback_side_effects",
            "vendor_content": "exact_nonempty_unique_pristine_slice_no_decoding_or_rekeying",
            "handle_binding": "immutable_raw_and_source_association_no_eviction",
            "recovery": "actual_handler_once_then_validate_unchanged_payload_no_preread",
            "publication": "unknown_no_parent_ack",
            "measurement": "annotated_upstream_counts_not_final_wire_savings",
            "parent_guards": "structure_fence_source_root_complete_original_nonexpansion",
        },
    }


def refresh_wire(data):
    """Refresh synthetic body/digest fields after deliberate test mutations."""
    for prep, request, capture in zip(data["preparations"], data["requests"], data["captures"]):
        request["body"] = {"input": [
            {"type": "function_call_output", "call_id": m["tool_call_id"], "output": m["content"]}
            for m in prep["prepared"]["messages"] if m["role"] == "tool"
        ]}
        wire = json.dumps(request["body"])
        capture.update(input=wire, ok=True, complete=True)
        final = {"reference_tokens": 5, "utf8_bytes": len(wire.encode()), "wire_sha256": sha(wire)}
        prep["wire_sha256"] = final["wire_sha256"]
        prep["input_composition"] = {"original": {"reference_tokens": 10, "utf8_bytes": len(wire.encode()) + 50},
                                     "final": final}


def validation_inventory(events):
    good = {e["handle"]: e for e in events if e["outcome"] == "validated_candidate"}
    return {
        "version": "preparation-validation-v1", "attempts": len(events), "since_attempt": 0,
        "events": deepcopy(events), "attempts_semantics": "cumulative_not_additive",
        "public_retrieve_entries": sum(e["public_retrieve_entered"] for e in events),
        "scope": "local_preparation_validation_not_native_or_model_recovery",
        "feedback": "public_retrieve_updates_access_feedback_telemetry_toin_even_if_projection_reverts",
        "publication": "unknown_no_parent_ack", "validated_handles": len(good),
        "retained_bytes": sum(e["raw_utf8_bytes"] for e in good.values()),
        "retained_frame_identities": 2, "retention_unit": "exact_raw_fragment_utf8_bytes",
    }


def overview_evidence(with_fragment=False):
    # Imported only when the test asks for fixture construction, never by driver.
    from test_checks import events
    planned = actions(Path("C:/owned"), "overview")
    root = {"name": "tokenmaster-retrieve_original", "call_id": "range_root_recovery",
            "arguments": {"ref": COMPACT_REF, "offset": 0}, "namespace": None}
    fragment = {"name": "tokenmaster-headroom_retrieve", "call_id": "range_fragment_recovery",
                "arguments": {"hash": HANDLE}, "namespace": None}
    emitted = [*planned, root] + ([fragment] if with_fragment else [])
    page = json.dumps({"ok": True, "complete": True, "content": SOURCE})
    raw_payload = json.dumps({"hash": HANDLE, "original_content": RAW, "original_item_count": 1}, indent=2)
    results = [SOURCE, "Newest EOF result.\n", page] + ([raw_payload] if with_fragment else [])
    data = {"intent": "overview", "planned": planned, "emitted": emitted, "preparations": [],
            "captures": [], "requests": [], "events": [], "rpc": [], "received": [], "cleanup": {"complete": True}}
    candidate = VIEW + ("\n<<ccr:" + HANDLE + ">>" if with_fragment else "")
    history = []
    for i in range(len(emitted) + 1):
        before = deepcopy(history)
        after = deepcopy(before)
        if i >= 2:
            after[1]["content"] = COMPACT_REF + "\n" + candidate
        data["preparations"].append({
            "original": {"model": "gpt-6-astra", "messages": before},
            "prepared": {"model": "gpt-6-astra", "messages": after},
            "changed_messages": [1] if i >= 2 else [],
        })
        data["requests"].append({})
        data["captures"].append({})
        if i < len(emitted):
            call = emitted[i]
            history.extend([
                {"role": "assistant", "tool_calls": [{"id": call["call_id"], "type": "function",
                  "function": {"name": call["name"], "arguments": json.dumps(call["arguments"])}}]},
                {"role": "tool", "tool_call_id": call["call_id"], "content": results[i]},
            ])
            data["events"] += events(call, text=results[i])
    refresh_wire(data)
    messages = deepcopy(data["preparations"][2]["original"]["messages"])
    spans = [{"index": 1, "content_sha256": sha(SOURCE),
              "spans": [s.to_dict() for s in document_structure_spans(SOURCE)]}]
    request = {"id": "prepare-1", "op": "compress_documents_preprotected", "model": "gpt-6-astra",
               "messages": messages, "eligible_indices": [1], "frozen_message_count": 0,
               "keep_recent_tool_results": 1, "span_contract": "document-structure-v1-offsets-v1",
               "message_spans": spans}
    binding = sha(canonical({"model": request["model"], "call": messages[0]["tool_calls"][0],
                             "result_metadata": {k: v for k, v in messages[1].items() if k != "content"},
                             "content_sha256": sha(SOURCE)}))
    validation = []
    if with_fragment:
        validation.append({
            "id": "preparation-validation-1", "rpc_id": request["id"], "message_index": 1,
            "handle": HANDLE, "source_binding": binding, "source_sha256": sha(SOURCE),
            "outcome": "validated_candidate", "public_retrieve_entered": True,
            "raw_sha256": sha(RAW), "raw_utf8_bytes": len(RAW.encode()),
            "source_start": SOURCE.index(RAW), "source_end": SOURCE.index(RAW) + len(RAW), "seconds": 0.01,
        })
    manifest_value = manifest()
    answer = {
        "strategy": manifest_value["strategy"], "strategy_manifest": manifest_value,
        "strategy_manifest_sha256": sha(canonical(manifest_value)),
        "span_contract": request["span_contract"], "message_spans_sha256": sha(canonical(spans)),
        "eligible_indices": [1], "protected_indices": [0, 2, 3],
        "document_request": {"frozen_message_count": 0, "keep_recent_tool_results": 1},
        "messages": deepcopy(messages), "upstream_tokens_scope": "annotated_vendor_pass_not_final_wire",
        "preprotection": {
            "span_contract": request["span_contract"], "message_spans": deepcopy(spans),
            "decisions": [{"index": 1, "status": "validated_candidate", "reason": "checks_passed"}],
            "effective_protected_indices": [0, 2, 3],
            "annotation": [{"index": 1, "pristine_sha256": sha(SOURCE), "annotated_sha256": "f" * 64,
                            "pristine_chars": len(SOURCE), "annotated_chars": len(SOURCE) + 192, "frame_count": 2}],
            "internal_input_bytes": {"scope": "internal_canonical_message_json_not_native_model_wire",
                                     "pristine": len(canonical(messages).encode()),
                                     "annotated": len(canonical(messages).encode()) + 192},
            "upstream_tokens_scope": "annotated_vendor_pass_before_adapter_fallback_not_final_wire",
            "candidate_publication": "unknown_no_parent_ack",
        },
        "preparation_validation": validation_inventory(validation),
    }
    answer["messages"][1]["content"] = candidate
    component = {"strategy": manifest_value["strategy"], "audit_after_task": True,
                 "recoveries_scope": "raw_vendor_store_audit_may_contain_annotation_not_native_delivery",
                 "preparation_validation": validation_inventory(validation),
                 "recoveries": {HANDLE: RAW} if with_fragment else {}}
    data["rpc"].append({"request": request})
    data["received"].append({"response": {"id": request["id"], "ok": True, "result": answer}})
    if with_fragment:
        data["rpc"].append({"request": {"id": "retrieve-1", "op": "retrieve", "hash": HANDLE,
                                        "tool_call_id": "range_fragment_recovery"}})
        data["received"].append({"response": {"id": "retrieve-1", "ok": True, "result": {
            "tool_call_id": "range_fragment_recovery", "tool_name": "headroom_retrieve",
            "success": True, "content": raw_payload, "items_retrieved": 1}}})
    process = {k: True for k in ("io_complete", "process_tree_settled", "reader_threads_stopped",
                                "queue_settled", "stdout_eof", "stderr_eof", "secret_config_removed")}
    process.update(errors=[], stdout="")
    data["native"] = {
        "complete": True, "source_contract": CONTRACT, "version": "copilot-native-runtime-view-result-v2",
        "native_executor": {"source_contract": CONTRACT}, "native_process": process,
        "runtime": {"model_calls": len(emitted) + 1, "source_read_receipts": 2,
                    "component": {"headroom_executed": True, "headroom": component}},
    }
    return data
