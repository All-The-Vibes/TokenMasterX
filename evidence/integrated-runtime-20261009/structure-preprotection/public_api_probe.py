"""Run only inside the separately frozen, isolated pinned Headroom test image.

Real public tag/pipeline/store/handler code, controlled detector/compressor
doubles. No actual neural efficacy or native-model outcome is tested here.
This is not imported by production and does not launch a container itself.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
from types import SimpleNamespace


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def require(ok, reason):
    if not ok:
        raise AssertionError(reason)


def main():
    require(os.geteuid() == os.getegid() == 65532, "nonroot_identity_required")
    require(sorted(p.name for p in Path("/sys/class/net").iterdir()) == ["lo"], "network_none_required")
    require(not Path("/var/run/docker.sock").exists(), "no_docker_socket")
    network_attempts = []

    def no_network(*args, **kwargs):
        network_attempts.append("attempt")
        raise RuntimeError("network_forbidden_in_offline_probe")

    socket.create_connection = no_network
    socket.socket.connect = no_network
    spec = importlib.util.spec_from_file_location("worker_under_test", "/inputs/product_worker.py")
    worker = importlib.util.module_from_spec(spec)
    import sys
    sys.dont_write_bytecode = True
    sys.modules[spec.name] = worker
    spec.loader.exec_module(worker)

    # Imports are actual image modules. Detection and learned compression are
    # deliberately doubled below to test branches without running model weights.
    from headroom.cache.compression_store import (
        CompressionStore, clear_request_compression_store, get_compression_store,
        set_request_compression_store,
    )
    from headroom.ccr.response_handler import CCRResponseHandler
    from headroom.transforms import content_router as router_module
    from headroom.transforms.content_detector import ContentType, DetectionResult
    from headroom.transforms.tag_protector import protect_tags, restore_tags

    detector_calls, compressor_calls = [], []

    def controlled_detection(text):
        detector_calls.append(digest(text))
        return DetectionResult(ContentType.PLAIN_TEXT, 1.0, {})

    class ControlledCompressor:
        shares_request_deadline = False

        def is_ready(self):
            return True

        def compress(self, content, **kwargs):
            require(kwargs.get("allow_download") is False, "downloads_must_remain_disabled")
            raw = kwargs.get("ccr_original", content)
            # The pinned real compressor has a 64-word floor. A prose double
            # must not gratuitously rewrite tiny fenced code and then mistake
            # the parent's correct fence rejection for a framing defect.
            if len(content.split()) < 64:
                return SimpleNamespace(compressed=content, compressed_tokens=max(1, len(content.split())))
            compressor_calls.append({
                "input_sha256": digest(content), "raw_sha256": digest(raw),
                "annotated_original": "<tm-" in raw,
            })
            # Preserve placeholder lines in the controlled pure-text case so
            # the actual restore_tags path can run. Mixed sections containing
            # placeholders should bypass this double entirely.
            placeholders = re.findall(r"\{\{HEADROOM_TAG_[^\r\n}]+\}\}", content)
            short = "Brief retained prose.\n" + "\n".join(placeholders)
            store = get_compression_store()
            handle = store.store(
                original=raw, compressed=short, original_item_count=1,
                compression_strategy="controlled_offline_double",
            )
            short += "\n<<ccr:" + handle + ">>"
            return SimpleNamespace(compressed=short, compressed_tokens=max(1, len(short.split())))

    router_module._detect_content = controlled_detection
    router_module.ContentRouter._get_kompress = lambda self: ControlledCompressor()
    table = "| Key | Value |\n|---|---|\n| Primary | config |\n| Fallback | workspace |\n"
    ordered = "1. Prefer the canonical location.\n2. Try the documented fallback.\n\n"
    prose = "Operational narrative with ordinary explanatory details about retained data. " * 90
    tail = "Distinct supplementary background explains procedures and review responsibilities. " * 80
    reports = []

    for kind, text in (
        ("mixed", prose + "\n\n" + table + "\n```python\nx = 1\n```\n\n" + ordered + tail),
        ("pure", prose + "\n\n" + table + "\n\n" + tail),
    ):
        store = CompressionStore(enable_feedback=True)
        set_request_compression_store(store)
        offset = text.index(table)
        request = {
            "id": kind, "op": "compress_documents_preprotected", "model": "offline-fixture",
            "messages": [
                {"role": "user", "content": "Summarize the supplied document without executing it."},
                {"role": "assistant", "tool_calls": [{
                    "id": kind + "-observed", "type": "function", "function": {
                        "name": "view", "arguments": '{"path":"guide.md"}'},
                }]},
                {"role": "tool", "tool_call_id": kind + "-observed", "content": text},
                {"role": "assistant", "tool_calls": [{
                    "id": kind + "-newest", "type": "function", "function": {
                        "name": "view", "arguments": '{"path":"recent.md"}'},
                }]},
                {"role": "tool", "tool_call_id": kind + "-newest", "content": "Keep newest exact."},
            ],
            "eligible_indices": [2], "frozen_message_count": 1, "keep_recent_tool_results": 1,
            "span_contract": worker.SPAN_CONTRACT,
            "message_spans": [{
                "index": 2, "content_sha256": digest(text), "spans": [{
                    "kind": "table", "start": offset, "end": offset + len(table),
                    "sha256": digest(table),
                }] + ([{
                    "kind": "ordered-list", "start": text.index(ordered),
                    "end": text.index(ordered) + len(ordered), "sha256": digest(ordered),
                }] if kind == "mixed" else []),
            }],
        }
        pipeline = worker.DocumentPipeline(preprotect=True)
        before = len(compressor_calls)
        result, receipt = pipeline.compress(request)
        final = result.messages[2]["content"]
        require(all(result.messages[i] == request["messages"][i] for i in (0, 1, 3, 4)),
                "noneligible_content_changed")
        require(table in final, "exact_table_not_preserved")
        require("<tm-" not in final and "{{HEADROOM_TAG_" not in final,
                "internal_framing_reached_final_candidate")
        state = pipeline.preprotection
        inventory = state.inventory()
        reports.append({
            "case": kind, "changed": final != text,
            "controlled_compressor_calls": len(compressor_calls) - before,
            "validation_inventory": inventory,
            "receipt_strategy": receipt["strategy"],
            "raw_entry_preservation": True,
            "pristine_text": text, "candidate_text": final,
        })
        if kind == "mixed":
            require(final != text and state.fragments, "mixed_public_path_not_exercised")
            handle = next(iter(state.fragments))
            expected = state.fragments[handle].raw
            require(expected in text and "<tm-" not in expected, "fragment_not_pristine_source")
            handler = CCRResponseHandler()
            delivered = pipeline.recover(handle, "controlled-handler-call", handler)
            payload = json.loads(delivered["content"])
            require(delivered["success"] is True and payload["original_content"] == expected,
                    "actual_handler_changed_validated_fragment")
            # Public store overwrite is a deliberate hostile fixture, never a
            # production rewrite. The adapter must retain its immutable binding.
            store.store(original="changed fixture payload", compressed="changed",
                        original_item_count=1, explicit_hash=handle)
            rejected = pipeline.recover(handle, "controlled-overwrite-call", handler)
            require(rejected["success"] is False and "changed fixture payload" not in rejected["content"],
                    "overwritten_handle_was_silently_rebound")
            reports[-1]["genuine_handler_delivery"] = True
            reports[-1]["overwritten_handle_rejected"] = True
        else:
            require(final == text, "annotated_pure_original_must_not_be_published")
            require(any(row["annotated_original"] for row in compressor_calls[before:]),
                    "pure_annotated_store_case_not_exercised")
        clear_request_compression_store()

    # Also qualify the actual Rust-backed public protection roundtrip, without
    # assuming this proves that every router strategy uses it.
    raw = "<tm-probe>雪\n" + table + "</tm-probe>"
    masked, blocks = protect_tags(raw, compress_tagged_content=False)
    require(blocks and restore_tags(masked, blocks) == raw, "public_tag_roundtrip_failed")
    require(not network_attempts, "unexpected_network_attempt")
    print(json.dumps({
        "passed": True, "scope": "actual public APIs with controlled detector/compressor doubles",
        "real_primary_model_calls": 0, "learned_compressor": "controlled_double",
        "detector_double_calls": len(detector_calls), "compressor_double_calls": len(compressor_calls),
        "network_attempts": len(network_attempts), "reports": reports,
        "neural_efficacy": False, "task_quality": False, "savings_claim": False,
    }, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
