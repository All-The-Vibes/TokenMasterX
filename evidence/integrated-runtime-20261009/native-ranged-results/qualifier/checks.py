"""Offline protocol evidence checks; no runtime imports, sockets or subprocesses."""
from copy import deepcopy
import hashlib
import json
from pathlib import PureWindowsPath
import re

CONTRACT = "native-view-result-v2"
LEGACY = "native-full-view-v1"
ROOT_REFERENCE_STYLES = ("annotated-v1", "compact-root-v1")
# Syntax recognition only, never storage/scope/content authentication. Preserve
# exactly minted reference bytes; actual native recovery remains the authority.
ROOT_PATTERNS = {
    "annotated-v1": re.compile(
        r"^\[\[BR:[0-9a-f]{64}\|v=2;scope=[0-9a-f]{64};kind=root;"
        r"source=(?:[A-Za-z0-9/:._~-]|%[0-9A-Fa-f]{2})*;"
        r"type=(?:[A-Za-z0-9._~-]|%[0-9A-Fa-f]{2})*;"
        r"summary=(?:[A-Za-z0-9._~-]|%[0-9A-Fa-f]{2})*;"
        r"chars=[0-9]+;bytes=[0-9]+\]\]"),
    "compact-root-v1": re.compile(r"^\[\[BR:[0-9a-f]{64}\|r=1\]\]"),
}
FRAGMENT_REF = re.compile(r"(?:hash=|<<ccr:)([a-f0-9]{24}|[a-f0-9]{12})(?![a-f0-9])")
SOURCE_PIN = "1cf496612e781ef8d67ff87ee4f78037492f0bc7"
DOCUMENTS = {
    "filesystem-contract.md": "6a679ec6a586eaff8c805d63860c4c14a666ab6ddca1e42ce0c20363e42f5e2c",
    "persistent-installs.md": "2500c1ef0f3ab389dbbd72fdb28968c1586291d87919b2a1719a7a6fc2055ea0",
}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def loads(text):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    def nonfinite(_):
        raise ValueError("nonfinite_json")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)


def same_json(left, right):
    """Strict canonical JSON identity: True != 1 and 1 != 1.0."""
    options = {"sort_keys": True, "separators": (",", ":"), "ensure_ascii": False, "allow_nan": False}
    return json.dumps(left, **options) == json.dumps(right, **options)


def outputs(body):
    return {item["call_id"]: item["output"] for item in body.get("input", [])
            if item.get("type") == "function_call_output"}


def root_reference(text, style):
    require(style in ROOT_REFERENCE_STYLES, "unknown_root_reference_style")
    match = ROOT_PATTERNS[style].match(text) if type(text) is str else None
    return match.group(0) if match else None


def actions(workspace, intent):
    """Absolute arguments frozen before invocation; preserve native tool naming."""
    first = {"name": "view", "arguments": {
        "path": str(workspace / "filesystem-contract.md"), "view_range": [3, 159],
        "forceReadLargeFiles": True,
    }, "call_id": intent + "_partial", "namespace": None}
    second = {"name": "view", "arguments": {
        "path": str(workspace / ("persistent-installs.md" if intent == "overview" else "missing-status-control.md")),
        "view_range": [30, -1] if intent == "overview" else [1, -1],
    }, "call_id": intent + ("_eof" if intent == "overview" else "_missing"), "namespace": None}
    return [first, second]


class Script:
    """Pure canned scheduler. Only recovery refs, never instructions, are extracted."""
    def __init__(self, planned, intent, *, root_reference_style="annotated-v1"):
        require(root_reference_style in ROOT_REFERENCE_STYLES, "unknown_root_reference_style")
        self.root_reference_style = root_reference_style
        self.planned, self.intent = deepcopy(planned), intent
        self.originals, self.emitted = {}, []
        self.root = self.fragment = None
        self.root_called = self.fragment_called = False
        self.requests = 0

    def next(self, body):
        self.requests += 1
        require(self.requests <= (5 if self.intent == "overview" else 3), "primary_budget_exhausted")
        values = outputs(body)
        for call_id, value in values.items():
            self.originals.setdefault(call_id, value)
        source_id = self.planned[0]["call_id"]
        current = values.get(source_id)
        original = self.originals.get(source_id)
        if self.intent == "overview" and current and current != original:
            root = root_reference(current, self.root_reference_style)
            if root and self.root is None:
                self.root = root
            markers = [v for v in FRAGMENT_REF.findall(current)
                       if v not in FRAGMENT_REF.findall(original)]
            if markers and self.fragment is None:
                self.fragment = markers[0]
        if len(self.emitted) < 2:
            action = deepcopy(self.planned[len(self.emitted)])
        elif self.intent == "overview" and self.root and not self.root_called:
            self.root_called = True
            action = {"name": "tokenmaster-retrieve_original",
                      "arguments": {"ref": self.root, "offset": 0},
                      "call_id": "range_root_recovery", "namespace": None}
        elif self.intent == "overview" and self.fragment and not self.fragment_called:
            self.fragment_called = True
            action = {"name": "tokenmaster-headroom_retrieve",
                      "arguments": {"hash": self.fragment},
                      "call_id": "range_fragment_recovery", "namespace": None}
        else:
            return None
        self.emitted.append(action)
        return action


def observed(events, action, success=True):
    starts = [e["data"] for e in events if e.get("type") == "tool.execution_start"
              and e.get("data", {}).get("toolCallId") == action["call_id"]]
    ends = [e["data"] for e in events if e.get("type") == "tool.execution_complete"
            and e.get("data", {}).get("toolCallId") == action["call_id"]]
    require(bool(starts) and bool(ends), "missing_native_start_or_completion")
    require(all(same_json(s, starts[0]) for s in starts) and all(same_json(e, ends[0]) for e in ends),
            "conflicting_native_replay")
    start, end = starts[0], ends[0]
    require(start["toolName"] == action["name"] and same_json(start["arguments"], action["arguments"]),
            "native_name_or_arguments_changed")
    require(end["success"] is success and end["rte"] is False
            and start["turnId"] == end["turnId"], "native_status_or_turn_mismatch")
    if success and action["name"] == "view":
        require(end.get("toolTelemetry", {}).get("properties", {}).get("viewType") == "file",
                "native_file_telemetry_required")
    result = end.get("result")
    if success:
        # Successful MCP results retain their native rendered content, including
        # the existing detailedContent/contents representations. Do not replace
        # that rendering with a reconstruction from MCP blocks.
        require(type(result) is dict, "unsupported_observed_native_result")
        text = result.get("content")
        require(type(text) is str and bool(text), "empty_observed_native_result")
    elif type(result) is dict:
        require(not set(result) - {"content", "detailedContent"}
                and type(result.get("content")) is str
                and ("detailedContent" not in result or type(result["detailedContent"]) is str),
                "unsupported_observed_native_failure")
        text = result["content"]
    else:
        # Absent/null results normally bind literal error.message. A single
        # pinned native-003 renderer below is the only derived-text exception;
        # malformed non-None results never fall through to another source.
        error = end.get("error")
        require(action["name"] == "view" and result is None
                and type(error) is dict and type(error.get("message")) is str,
                "unsupported_observed_native_failure")
        text = error["message"]
        telemetry = end.get("toolTelemetry")
        properties = telemetry.get("properties") if type(telemetry) is dict else None
        path = action["arguments"].get("path")  # Already matched to native start.
        if (end["success"] is False and end["rte"] is False
                and error.get("code") == "failure" and text == "Path does not exist"
                and type(properties) is dict and properties.get("command") == "view"
                and properties.get("viewType") == "unknown"
                and properties.get("resolvedPathAgainstCwd") == "false"
                and type(path) is str and 0 < len(path) <= 4096 and "\0" not in path
                and PureWindowsPath(path).is_absolute()):
            # native-view-missing-path-1.0.95-v1: exact evidenced punctuation
            # and the unchanged issued absolute path; no filesystem lookup,
            # normalization, generic prefix inference or source authority.
            text = f"Path {path} does not exist. Please provide a valid path."
    return text


def tool_map(messages):
    return {m["tool_call_id"]: m for m in messages if m.get("role") == "tool"}


def exact_root(page_text, observed_text):
    page = loads(page_text)
    return (page.get("ok") is True and page.get("complete") is True
            and page.get("content") == observed_text)


def accepted_smaller(prep, capture, upstream):
    composition = prep["input_composition"]
    original, final = composition["original"], composition["final"]
    wire = capture.get("input")
    return bool(prep["changed_messages"] and capture.get("ok") is True
                and capture.get("complete") is True and type(wire) is str
                and final["reference_tokens"] < original["reference_tokens"]
                and final["utf8_bytes"] < original["utf8_bytes"]
                and len(wire.encode("utf-8")) == final["utf8_bytes"]
                and digest(wire.encode("utf-8")) == final["wire_sha256"] == prep["wire_sha256"]
                and same_json(loads(wire), upstream["body"]))


def source_contract_recorded(value):
    if isinstance(value, dict):
        return value.get("source_contract") == CONTRACT or any(source_contract_recorded(v) for v in value.values())
    return isinstance(value, list) and any(source_contract_recorded(v) for v in value)


def assess(intent, planned, emitted, requests, native, preparations, captures, events,
           rpc, received, cleanup, *, root_reference_style="annotated-v1"):
    """Fail closed on absent/mismatched evidence; never synthesize successful rows."""
    require(root_reference_style in ROOT_REFERENCE_STYLES, "unknown_root_reference_style")
    require(native.get("complete") is True, "native_not_complete")
    require(native.get("source_contract") == CONTRACT
            and native.get("version") == "copilot-native-runtime-view-result-v2"
            and native.get("native_executor", {}).get("source_contract") == CONTRACT,
            "selected_source_contract_not_recorded")
    process = native["native_process"]
    for key in ("io_complete", "process_tree_settled", "reader_threads_stopped",
                "queue_settled", "stdout_eof", "stderr_eof", "secret_config_removed"):
        require(process.get(key) is True, "unsettled_native_" + key)
    require(not process.get("errors"), "native_process_errors")
    require(len(requests) == len(preparations) == len(captures), "primary_capture_inventory_mismatch")
    require(native["runtime"]["model_calls"] == len(requests), "runtime_primary_inventory_mismatch")
    require(native["runtime"]["source_read_receipts"] == (2 if intent == "overview" else 1),
            "unexpected_ranged_or_failure_source_receipts")
    require(len(requests) <= (5 if intent == "overview" else 3), "primary_budget_exceeded")
    require(same_json(emitted[:2], planned), "scripted_native_calls_changed")
    originals = {action["call_id"]: observed(events, action, not action["call_id"].endswith("_missing"))
                 for action in planned}
    for i, prep in enumerate(preparations):
        before, after = tool_map(prep["original"]["messages"]), tool_map(prep["prepared"]["messages"])
        for call_id, message in before.items():
            if call_id in originals:
                require(message["content"] == originals[call_id], "ingress_not_observed_result")
        if before:
            newest = list(before)[-1]
            require(before[newest] == after[newest], "newest_result_changed")
        if intent == "exact":
            require(before == after and not prep["changed_messages"], "exact_or_status_control_changed")
        require(captures[i].get("ok") is True and captures[i].get("complete") is True,
                "failed_primary_capture")
        require(same_json(loads(captures[i]["input"]), requests[i]["body"]), "upstream_wire_mismatch")
        delivered_results = outputs(requests[i]["body"])
        require(all(delivered_results.get(call_id) == message["content"] for call_id, message in after.items()),
                "prepared_tool_result_not_delivered")
        issued = {a["call_id"]: a for a in emitted}
        for item in requests[i]["body"].get("input", []):
            if item.get("type") == "function_call" and item.get("call_id") in issued:
                action = issued[item["call_id"]]
                require(item["name"] == action["name"]
                        and same_json(loads(item["arguments"]), action["arguments"]), "historical_native_call_changed")
    if intent == "exact":
        require(len(requests) == 3 and len(emitted) == 2, "exact_control_not_completed")
        require(planned[0]["call_id"] in tool_map(preparations[-1]["original"]["messages"]), "missing_old_exact_control")
        require(not any(r.get("request", {}).get("op") == "compress_documents" for r in rpc),
                "exact_reached_document_pipeline")
        return {"passed": True, "controls": ["exact", "status"], "primary_requests": len(requests),
                "status_control_is_also_exact_protected": True,
                "selected_root_reference_style": root_reference_style,
                "delivered_root_ref": None, "native_root_lookup_verified": False}
    require(cleanup.get("complete") is True, "headroom_cleanup_unsettled")
    require(native["runtime"]["component"].get("headroom_executed") is True, "headroom_not_executed")
    calls = [r["request"] for r in rpc if r.get("request", {}).get("op") == "compress_documents"]
    replies = {str(r["response"]["id"]): r["response"].get("result", {})
               for r in received if "id" in r.get("response", {})}
    partial_id = planned[0]["call_id"]
    nonempty_eligible = False
    for call in calls:
        eligible = call["eligible_indices"]
        require(bool(eligible), "empty_document_eligibility")
        answer = replies[str(call["id"])]
        manifest = answer["strategy_manifest"]
        require(manifest["strategy"] == "native-documents-v1"
                and manifest["vendor_commit"] == SOURCE_PIN, "wrong_public_pipeline_strategy")
        require(manifest["compress_config"]["compress_system_messages"] is False, "unprotected_system")
        before, after = call["messages"], answer["messages"]
        require(len(before) == len(after), "pipeline_changed_message_count")
        require(all(a == b for index, (a, b) in enumerate(zip(before, after)) if index not in eligible),
                "pipeline_changed_protected_input")
        for index in eligible:
            if before[index].get("tool_call_id") == partial_id:
                require(before[index]["content"] == originals[partial_id], "pipeline_not_observed_range")
                nonempty_eligible = bool(before[index]["content"])
    require(nonempty_eligible, "partial_old_document_never_reached_pipeline")
    changed = [i for i, p in enumerate(preparations)
               if partial_id in tool_map(p["prepared"]["messages"])
               and tool_map(p["prepared"]["messages"])[partial_id]["content"] != originals[partial_id]]
    require(bool(changed), "no_accepted_partial_document_change")
    require(all(accepted_smaller(preparations[i], captures[i], requests[i]) for i in changed),
            "accepted_complete_wire_not_smaller")
    values = {key: value for request in requests for key, value in outputs(request["body"]).items()}
    root_actions = [a for a in emitted if a["call_id"] == "range_root_recovery"]
    require(len(root_actions) == 1, "native_root_not_issued")
    projected = tool_map(preparations[changed[0]]["prepared"]["messages"])[partial_id]["content"]
    delivered_ref = root_reference(projected, root_reference_style)
    require(delivered_ref is not None and same_json(root_actions[0]["arguments"], {"ref": delivered_ref, "offset": 0}),
            "root_style_or_delivered_reference_mismatch")
    root_observed = observed(events, root_actions[0])
    require(same_json(loads(root_observed), loads(values.get("range_root_recovery", "{}"))),
            "native_root_delivery_changed")
    require(exact_root(values.get("range_root_recovery", "{}"), originals[partial_id]),
            "root_not_exact_observed_range_result")
    # One first-emitted vendor marker is sufficient for this bounded protocol cell.
    markers = [h for h in FRAGMENT_REF.findall(projected) if h not in FRAGMENT_REF.findall(originals[partial_id])]
    if markers:
        fragment_actions = [a for a in emitted if a["call_id"] == "range_fragment_recovery"]
        require(len(fragment_actions) == 1, "native_fragment_not_issued")
        fragment_observed = observed(events, fragment_actions[0])
        recoveries = [r["response"].get("result", {}) for r in received]
        vendor = [r.get("content") for r in recoveries if r.get("tool_call_id") == "range_fragment_recovery"]
        require(len(vendor) == 1, "vendor_recovery_not_exercised")
        delivered = loads(values.get("range_fragment_recovery", "{}"))
        require(same_json(delivered, loads(vendor[0])) and same_json(delivered, loads(fragment_observed)),
                "native_vendor_delivery_changed")
        stored = native["runtime"]["component"]["headroom"]["recoveries"].get(markers[0])
        require(type(stored) is str and delivered.get("hash") == markers[0]
                and delivered.get("original_content") == stored, "vendor_fragment_not_exact")
    return {"passed": True, "primary_requests": len(requests), "nonempty_pipeline_admission": True,
            "accepted_complete_wire_smaller": True, "root_exact_observed_range": True,
            "selected_root_reference_style": root_reference_style, "delivered_root_ref": delivered_ref,
            "native_root_lookup_verified": True,
            "fragment_recovery": "verified_first_emitted" if markers else "not_emitted_not_claimed",
            "emitted_fragment_count": len(set(markers)), "newest_control": True}
