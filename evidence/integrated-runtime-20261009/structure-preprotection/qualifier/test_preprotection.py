"""Behavioral mutations of tiny offline records; never invoke a vendor pipeline."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checks
import preprotection_checks as structure
import qualify_ranges as driver
from structure_fixtures import (
    COMPACT_REF, FENCE, HANDLE, ORDERED, RAW, SOURCE, TABLE, VIEW,
    canonical, overview_evidence, refresh_wire, sha, validation_inventory,
)


def answer(data):
    return data["received"][0]["response"]["result"]


def finish(data):
    return data["native"]["runtime"]["component"]["headroom"]


def rehash_manifest(data):
    value = answer(data)
    value["strategy_manifest_sha256"] = sha(canonical(value["strategy_manifest"]))


def test_complete_span_and_raw_recovery_evidence_preserves_both_structure_kinds():
    result = checks.assess(**overview_evidence(with_fragment=True))
    assert result["passed"]
    assert result["span_contract"] == "document-structure-v1-offsets-v1"
    assert result["accepted_structure_counts"] == {"table": 1, "ordered-list": 1}
    assert result["table_and_ordered_list_exact_in_native_wire"] is True
    assert result["generated_framing_absent_in_native_delivery"] is True
    assert result["preparation_validation"]["attempts"] == 1
    assert result["preparation_validation"]["native_requested_fragment_recoveries"] == 1
    assert result["preparation_validation"]["candidate_not_claimed_published"] is True
    assert result["preparation_validation"]["scope"] == structure.VALIDATION_SCOPE


@pytest.mark.parametrize("mutation", ["contract", "content_hash", "span_hash", "missing_table",
                                     "bool_index", "bool_offset", "overlap", "kind", "digest_echo", "bool_echo"])
def test_exact_observed_span_contract_and_typed_digest_echo_are_mandatory(mutation):
    data = overview_evidence()
    call, reply = data["rpc"][0]["request"], answer(data)
    entry = call["message_spans"][0]
    if mutation == "contract":
        call["span_contract"] = "invented-v2"
    elif mutation == "content_hash":
        entry["content_sha256"] = "0" * 64
    elif mutation == "span_hash":
        entry["spans"][0]["sha256"] = "0" * 64
    elif mutation == "missing_table":
        entry["spans"].pop(0)
    elif mutation == "bool_index":
        entry["index"] = True
    elif mutation == "bool_offset":
        entry["spans"][0]["start"] = True
    elif mutation == "overlap":
        entry["spans"][1]["start"] = entry["spans"][0]["start"]
    elif mutation == "kind":
        entry["spans"][0]["kind"] = "prose"
    elif mutation == "digest_echo":
        reply["message_spans_sha256"] = "0" * 64
    else:
        reply["eligible_indices"] = [True]
    with pytest.raises(ValueError):
        checks.assess(**data)


@pytest.mark.parametrize("mutation", ["table", "ordered", "drop_list", "duplicate_table",
                                     "reorder", "fence", "wrapper", "placeholder", "encoded_placeholder"])
def test_accepted_native_wire_not_just_worker_candidate_must_preserve_exact_structures(mutation):
    data = overview_evidence()
    current = data["preparations"][2]["prepared"]["messages"][1]["content"]
    changed = {
        "table": current.replace("retained", "altered"),
        "ordered": current.replace("1. Config", "2. Config"),
        "drop_list": current.replace(ORDERED, ""),
        "duplicate_table": current + "\n" + TABLE,
        "reorder": current.replace(TABLE, "@table@").replace(ORDERED, TABLE + "\n").replace("@table@", ORDERED),
        "fence": current.replace("value = '雪'", "value = 'changed'"),
        "wrapper": current + "\n<tm-structure-owned-1>leak</tm-structure-owned-1>",
        "placeholder": current + "\n{{HEADROOM_TAG_1}}",
        "encoded_placeholder": current + "\nHEADROOM_TAG_1",
    }[mutation]
    for prep in data["preparations"][2:]:
        prep["prepared"]["messages"][1]["content"] = changed
    refresh_wire(data)  # All wire receipts agree; compare original structure, not a stale hash.
    with pytest.raises(ValueError, match="native_table_or_ordered_list_changed|native_fenced_text_changed"):
        checks.assess(**data)


@pytest.mark.parametrize("field,value", [
    ("candidate_publication", "published"), ("span_contract", "other"),
    ("upstream_tokens_scope", "final_wire"),
])
def test_internal_annotation_and_candidate_receipts_cannot_claim_publication(field, value):
    data = overview_evidence()
    answer(data)["preprotection"][field] = value
    with pytest.raises(ValueError):
        checks.assess(**data)


@pytest.mark.parametrize("mutation", ["manifest_hash", "compression_enabled", "wrong_codec",
                                     "frame_count", "annotated_identity", "changed_effective_protected",
                                     "fallback_changed", "worker_wrapper", "worker_placeholder"])
def test_public_preprotect_route_and_unwrapped_candidate_are_required(mutation):
    data = overview_evidence()
    value = answer(data)
    if mutation == "manifest_hash":
        value["strategy_manifest_sha256"] = "0" * 64
    elif mutation == "compression_enabled":
        value["strategy_manifest"]["router_config"]["compress_tagged_content"] = True
        rehash_manifest(data)
    elif mutation == "wrong_codec":
        value["strategy_manifest"]["preprotection"]["codec"] = "decode-raw-fragments-v1"
        rehash_manifest(data)
    elif mutation == "frame_count":
        value["preprotection"]["annotation"][0]["frame_count"] = 0
    elif mutation == "annotated_identity":
        value["preprotection"]["annotation"][0]["annotated_sha256"] = sha(SOURCE)
    elif mutation == "changed_effective_protected":
        value["preprotection"]["effective_protected_indices"] = [0, 1, 2, 3]
    elif mutation == "fallback_changed":
        value["preprotection"]["decisions"][0]["status"] = "fallback"
    else:
        value["messages"][1]["content"] += "\n" + (
            "<tm-owned>leak</tm-owned>" if mutation == "worker_wrapper" else "{{HEADROOM_TAG_0}}")
    with pytest.raises(ValueError):
        checks.assess(**data)


@pytest.mark.parametrize("mutation", ["raw_hash", "raw_length", "source_binding", "source_offset", "handle_rebound",
                                     "count", "count_bool", "publication", "feedback", "scope", "fake_native_id"])
def test_raw_store_validation_is_bound_and_separate_not_native_recovery(mutation):
    data = overview_evidence(with_fragment=True)
    inventory = answer(data)["preparation_validation"]
    event = inventory["events"][0]
    if mutation == "raw_hash":
        event["raw_sha256"] = "0" * 64
    elif mutation == "raw_length":
        event["raw_utf8_bytes"] += 1
    elif mutation == "source_binding":
        event["source_binding"] = "0" * 64
    elif mutation == "source_offset":
        event["source_end"] -= 1
    elif mutation == "handle_rebound":
        finish(data)["recoveries"][HANDLE] = "rewritten store value"
    elif mutation == "count":
        inventory["attempts"] += 1
    elif mutation == "count_bool":
        inventory["public_retrieve_entries"] = True
    elif mutation in ("publication", "feedback", "scope"):
        inventory[mutation] = "native_model_recovery"
    else:
        event["tool_call_id"] = "fake_native_recovery"
    with pytest.raises(ValueError):
        checks.assess(**data)


def test_validation_count_is_cumulative_not_sum_of_duplicate_final_snapshot():
    data = overview_evidence(with_fragment=True)
    result = checks.assess(**data)
    assert result["preparation_validation"]["attempts"] == 1
    assert result["preparation_validation"]["public_retrieve_entries"] == 1
    assert result["preparation_validation"]["native_requested_fragment_recoveries"] == 1
    assert result["preparation_validation"]["post_task_audit_handles"] == 1


def test_revalidation_delta_counts_two_feedback_reads_but_one_native_recovery():
    data = overview_evidence(with_fragment=True)
    second_call = deepcopy(data["rpc"][0])
    second_call["request"]["id"] = "prepare-2"
    second_reply = deepcopy(data["received"][0])
    second_reply["response"]["id"] = "prepare-2"
    previous = answer(data)["preparation_validation"]["events"][0]
    next_event = {**previous, "id": "preparation-validation-2", "rpc_id": "prepare-2"}
    combined = validation_inventory([previous, next_event])
    second_reply["response"]["result"]["preparation_validation"] = {
        **deepcopy(combined), "since_attempt": 1, "events": [next_event],
    }
    data["rpc"].insert(1, second_call)
    data["received"].insert(1, second_reply)
    finish(data)["preparation_validation"] = combined
    result = checks.assess(**data)["preparation_validation"]
    assert result["attempts"] == result["public_retrieve_entries"] == 2  # Not 1+2+2.
    assert result["native_requested_fragment_recoveries"] == 1
    assert result["validated_candidate_handles"] == 1


def test_second_unvalidated_marker_in_native_wire_cannot_hide_behind_first_valid_recovery():
    data = overview_evidence(with_fragment=True)
    for prep in data["preparations"][2:]:
        prep["prepared"]["messages"][1]["content"] += "\n<<ccr:" + "e" * 24 + ">>"
    refresh_wire(data)
    with pytest.raises(ValueError, match="native_wire_contains_unvalidated_handle"):
        checks.assess(**data)


def test_native_view_must_be_actual_unwrapped_worker_candidate_not_a_fresh_rewrite():
    data = overview_evidence()
    for prep in data["preparations"][2:]:
        prep["prepared"]["messages"][1]["content"] = prep["prepared"]["messages"][1]["content"].replace("Brief.", "Rewritten.")
    refresh_wire(data)
    with pytest.raises(ValueError, match="native_view_not_returned_unwrapped_candidate"):
        checks.assess(**data)


@pytest.mark.parametrize("mutation", ["bool_count", "duplicate_key", "changed_raw"])
def test_raw_recovery_envelope_is_strict_and_never_reserialized_as_a_substitute(mutation):
    data = overview_evidence(with_fragment=True)
    value = data["received"][1]["response"]["result"]
    if mutation == "bool_count":
        value["items_retrieved"] = True
    elif mutation == "duplicate_key":
        value["content"] = value["content"].replace('"hash":', '"hash": "' + HANDLE + '", "hash":', 1)
    else:
        value["content"] = value["content"].replace("Recoverable", "Different")
    with pytest.raises(ValueError):
        checks.assess(**data)


@pytest.mark.parametrize("contamination", ["<tm-x>" + RAW + "</tm-x>", "{{HEADROOM_TAG_1}}", "HEADROOM_TAG_x"])
def test_raw_successful_fragment_is_never_deannotated_to_make_it_pass(contamination):
    data = overview_evidence(with_fragment=True)
    vendor = data["received"][1]["response"]["result"]
    vendor["content"] = json.dumps({"hash": HANDLE, "original_content": contamination, "original_item_count": 1})
    with pytest.raises(ValueError, match="raw_native_recovery_rejected_or_contaminated"):
        checks.assess(**data)


def test_rejected_contaminated_audit_payload_may_be_retained_but_not_delivered_or_published():
    data = overview_evidence(with_fragment=True)
    bad = deepcopy(answer(data)["preparation_validation"]["events"][0])
    bad.update(id="preparation-validation-2", handle="f" * 24, outcome="contaminated",
               raw_sha256=sha("<tm-x>bad</tm-x>"), raw_utf8_bytes=len("<tm-x>bad</tm-x>"))
    bad.pop("source_start"); bad.pop("source_end")
    all_events = answer(data)["preparation_validation"]["events"] + [bad]
    answer(data)["preparation_validation"] = validation_inventory(all_events)
    finish(data)["preparation_validation"] = validation_inventory(all_events)
    finish(data)["recoveries"][bad["handle"]] = "<tm-x>bad</tm-x>"
    result = checks.assess(**data)
    assert result["preparation_validation"]["attempts"] == 2
    assert result["preparation_validation"]["validated_candidate_handles"] == 1
    assert result["preparation_validation"]["native_requested_fragment_recoveries"] == 1
    assert result["preparation_validation"]["candidate_not_claimed_published"] is True


def test_absent_fragment_means_zero_validation_reads_not_fabricated_recovery():
    result = checks.assess(**overview_evidence())
    assert result["preparation_validation"]["attempts"] == 0
    assert result["preparation_validation"]["native_requested_fragment_recoveries"] == 0
    assert result["fragment_recovery"] == "not_emitted_not_claimed"


def test_preparation_reads_are_retained_on_noop_without_acceptance_credit():
    data = overview_evidence(with_fragment=True)
    for prep in data["preparations"]:
        prep["prepared"] = deepcopy(prep["original"])
        prep["changed_messages"] = []
    refresh_wire(data)
    with pytest.raises(ValueError, match="no_accepted_partial_document_change"):
        checks.assess(**data)
    report = structure.retained_validation_summary(data["received"])
    assert report["attempts"] == 1
    assert report["candidate_not_claimed_published"] is True
    assert report["receipt_validation"] == "not_checked"


def test_new_policy_requires_structure_guard_compact_root_and_nonexpanding():
    selected = {}
    class Policy:
        def __init__(self, **kw):
            selected.update(kw)
    driver.qualification_policy(Policy, "compact-root-v1")
    assert selected == {
        "backend": "headroom", "instruction": "ponytail", "require_nonexpanding_input": True,
        "headroom_time_budget_seconds": 60, "headroom_strategy": structure.STRATEGY,
        "headroom_root_reference_style": "compact-root-v1", "headroom_structure_guard": structure.STRUCTURE_GUARD,
    }
    with pytest.raises(ValueError, match="requires_compact_root"):
        driver.qualification_policy(Policy, "annotated-v1")


def test_worker_api_and_pure_grammar_snapshots_are_source_pinned():
    driver.validate_grammar_snapshot()
    worker = ast.parse((driver.SKILL / "brainspace/headroom_worker.py").read_bytes())
    literals = {}
    for node in worker.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ("PREPROTECTION_STRATEGY", "SPAN_CONTRACT", "MAX_PREPROTECTION_SPANS"):
                literals[node.targets[0].id] = ast.literal_eval(node.value)
    assert literals == {"PREPROTECTION_STRATEGY": structure.STRATEGY,
                        "SPAN_CONTRACT": structure.SPAN_CONTRACT, "MAX_PREPROTECTION_SPANS": 256}


def test_original_qualifier_and_frozen_task_configuration_remain_unchanged():
    origin = driver.load(driver.HERE / "ORIGIN.json")
    old = driver.REPO / origin["copied_from"]
    assert driver.inventory(old) == origin["old_inventory"]
    old_tree = ast.parse((old / "qualify_ranges.py").read_bytes())
    new_tree = ast.parse(Path(driver.__file__).read_bytes())
    def plan(tree):
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "prepare")
        node = next(n.value for n in ast.walk(function) if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "plan" for t in n.targets))
        return {ast.literal_eval(k): v for k, v in zip(node.keys, node.values)}
    before, after = plan(old_tree), plan(new_tree)
    for key in ("prompt", "schedule", "max_primary_requests", "model", "native_timeout", "transport_timeout"):
        assert ast.literal_eval(before[key]) == ast.literal_eval(after[key])
    old_checks = ast.parse((old / "checks.py").read_bytes())
    new_checks = ast.parse((driver.HERE / "checks.py").read_bytes())
    old_action = next(n for n in old_checks.body if isinstance(n, ast.FunctionDef) and n.name == "actions")
    new_action = next(n for n in new_checks.body if isinstance(n, ast.FunctionDef) and n.name == "actions")
    assert ast.dump(old_action, include_attributes=False) == ast.dump(new_action, include_attributes=False)


@pytest.mark.parametrize("first,later,winner", [
    (ValueError("ordinary"), KeyboardInterrupt("cancel"), "later"),
    (KeyboardInterrupt("first cancel"), ValueError("later"), "first"),
    (SystemExit("first exit"), KeyboardInterrupt("second cancel"), "first"),
])
def test_inherited_cancellation_repairs_preserve_first_cancellation_over_ordinary_failures(first, later, winner):
    retained = driver.retain_error(first, later, "offline")
    assert retained is (first if winner == "first" else later)
    if winner == "later":
        assert any("displaced ValueError" in note for note in retained.__notes__)


def test_new_contract_and_grammar_are_frozen_in_preparation_not_source_rewritten():
    tree = ast.parse(Path(driver.__file__).read_bytes())
    prepare = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "prepare")
    plan = next(n.value for n in ast.walk(prepare) if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "plan" for t in n.targets))
    fields = {ast.literal_eval(k): v for k, v in zip(plan.keys, plan.values)}
    for name, value in (("headroom_strategy", "STRATEGY"), ("headroom_structure_guard", "STRUCTURE_GUARD"),
                        ("span_contract", "SPAN_CONTRACT"), ("source_contract", "CONTRACT")):
        assert ast.unparse(fields[name]) == value
    assert "authoring_inventory" in fields and "installed_inventory" in fields and "source_inventory" in fields
    assert ast.unparse(fields["policy"]) == "policy.to_dict()"
