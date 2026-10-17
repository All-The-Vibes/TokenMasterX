"""Offline, fixed-history v3 replay. No provider, recovery store, or model calls.

replay_request(input_text, case, source_reads) audits one materialized request.
replay_study(study, *, expected_captures=69) validates and replays the complete
scheduled baseline inventory. It returns a report without writing anything.
CLI: --study <six-task directory> --output <new report.json>; never overwrites.
This proves request behavior on saved histories, not counterfactual task quality.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "skills/token-master"))
from brainspace import tokens  # noqa: E402
from brainspace.request_policy import (  # noqa: E402
    PROTOCOL, SourceReadInfo, _tool_indices, plan_request, serialize_request,
)
import parity_cases  # noqa: E402
from quality.cases import digest, safe_path, safe_root  # noqa: E402
from quality.oracle import _snapshot  # noqa: E402
from quality.responses import parse_json  # noqa: E402
from quality.runner import to_responses  # noqa: E402
from run_repository import canonical, chat_from_request  # noqa: E402
from source_read_adapter import ConservativeArm  # noqa: E402


COMPLETE = "complete_for_declared_boundary"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def replay_request(input_text, case, source_reads):
    """Audit v3, retaining every observed change rather than assuming neutrality.

    Only executor receipts authorize reuse. Read-only fixture equality independently
    checks tool output completeness. Missing fetch_artifact receipts are permitted:
    the old executor did not record them; none are synthesized for the planner.
    """
    body = parse_json(input_text)
    _require(canonical(body) == input_text, "noncanonical captured input")
    _require(not body.get("previous_response_id") and not body.get("conversation"),
             "opaque prior context unsupported")
    original_body = deepcopy(body)
    chat = chat_from_request(body)
    indices = _tool_indices(chat)
    original_chat = deepcopy(chat)
    original_wire = serialize_request(chat)
    public = case.public_task()
    _require(len(chat["messages"]) >= 2 and chat["messages"][1]["role"] == "user"
             and parse_json(chat["messages"][1]["content"]) == {
                 k: public[k] for k in ("prompt", "paths", "allowed_changes")},
             "captured task does not match bound case")
    by_call = {}
    for info in source_reads:
        _require(type(info) is SourceReadInfo and info.status == "success"
                 and info.call_id not in by_call and info.tool_name in ("read_file", "fetch_artifact"),
                 "invalid executor receipt")
        _require(info.source_path in case.files
                 and info.content_sha256 == _sha(case.files[info.source_path].encode()),
                 "receipt does not bind original fixture")
        by_call[info.call_id] = info
    calls = {c["id"]: c for m in chat["messages"] for c in m.get("tool_calls", [])}
    visible, duplicates = {}, []
    seen: dict[tuple[str, str, str], int] = {}
    for index in indices:
        message = chat["messages"][index]
        call = calls[message["tool_call_id"]]
        tool = call["function"]["name"]
        info = by_call.get(message["tool_call_id"])
        if tool in ("read_file", "fetch_artifact"):
            args = parse_json(call["function"]["arguments"])
            _require(set(args) == {"path"} and args["path"] in case.files
                     and message["content"] == case.files[args["path"]], "incomplete source read")
            if tool == "read_file":
                _require(info is not None, "missing read_file executor receipt")
            key = (tool, args["path"], message["content"])
            if key in seen:
                duplicates.append([seen[key], index])
            else:
                seen[key] = index
        if info is not None:
            _require(info.matches(message, call), "executor receipt binding mismatch")
            visible[index] = info
    callbacks: Counter[str] = Counter()

    def forbidden(name):
        def callback(*args, **kwargs):
            callbacks[name] += 1
            raise AssertionError("v3 invoked a forbidden callback")
        return callback

    policy = ConservativeArm("conservative").policy
    _require(policy.version == "request-policy-v3" and policy.enabled, "v3 policy unavailable")
    plan = plan_request(
        chat, policy=policy, protocol=PROTOCOL, intent=case.intent,
        stable_prefix_messages=2, source_reads=tuple(visible.values()),
        count=tokens.count_tokens, transform=forbidden("transform"),
        source_transform=forbidden("source_transform"), recover=forbidden("recover"),
    )
    _require(not callbacks, "transform/recover callback invoked")
    _require(body == original_body and chat == original_chat
             and serialize_request(chat) == original_wire, "original request mutated")
    _require(plan.status in ("unchanged", "transformed")
             and plan.reason in ("no_eligible_transform", "exact_visible_reuse")
             and plan.serialized == serialize_request(plan.request), "invalid/incomplete replay plan")
    changes = [
        {"index": i, "before_sha256": digest(before), "after_sha256": digest(after)}
        for i, (before, after) in enumerate(zip(chat["messages"], plan.request["messages"]))
        if before != after
    ]
    _require(len(chat["messages"]) == len(plan.request["messages"])
             and tuple(c["index"] for c in changes) == plan.changed_message_indices,
             "unreported message changes")
    planned_body = deepcopy(body)
    planned_body["input"] = to_responses(plan.request)["input"]
    planned_wire = canonical(planned_body)
    unchanged = planned_wire == input_text
    _require(bool(changes) == (plan.status == "transformed") == (not unchanged),
             "inconsistent change status")
    _require(duplicates or unchanged, "unique-read history changed")
    incoming, outgoing = tokens.count_tokens(input_text), tokens.count_tokens(planned_wire)
    _require(not changes or (outgoing < incoming
                            and len(planned_wire.encode()) <= len(input_text.encode())),
             "full-wire guard failed")
    return {
        "case_id": case.id, "case_identity": case.identity, "intent": case.intent,
        "policy_id": policy.policy_id, "status": plan.status, "reason": plan.reason,
        "duplicate_read_pairs": duplicates, "verified_visible_receipts": len(visible),
        "visible_receipt_call_ids": [info.call_id for info in visible.values()],
        "changed_messages": changes, "serialized_request_unchanged": unchanged,
        "originals_not_mutated": True,
        "callbacks": {name: callbacks[name] for name in ("transform", "source_transform", "recover")},
        "input_sha256": _sha(input_text.encode()), "planned_input_sha256": _sha(planned_wire.encode()),
        "reference_input_tokens_before": incoming, "reference_input_tokens_after": outgoing,
        "wire_bytes_before": len(input_text.encode()), "wire_bytes_after": len(planned_wire.encode()),
    }


class _Inventory:
    def __init__(self, root):
        self.root = safe_root(root)
        self.entries = {}

    def read(self, path):
        path = Path(path).absolute()
        relative = safe_path(path.relative_to(self.root).as_posix())
        safe_root(path)
        _require(path.is_file(), "missing inventory file: " + relative)
        raw = path.read_bytes()
        entry = {"sha256": _sha(raw), "bytes": len(raw)}
        _require(relative not in self.entries or self.entries[relative] == entry,
                 "input changed during replay")
        self.entries[relative] = entry
        return raw

    def json(self, path):
        return parse_json(self.read(path).decode("utf-8"))

    def lines(self, path):
        lines = self.read(path).decode("utf-8").splitlines()
        _require(lines and all(line.strip() for line in lines), "empty or incomplete JSONL")
        return [parse_json(line) for line in lines]

    def verify_unchanged(self):
        for relative, entry in list(self.entries.items()):
            _require(_sha(self.read(self.root / relative)) == entry["sha256"],
                     "inventory mutated during replay")


def _load_run(run, case, inventory):
    result = inventory.json(run / "result.json")
    captures = inventory.lines(run / "captures.jsonl")
    invocations = inventory.lines(run / "invocations.jsonl")
    receipts = tuple(SourceReadInfo.from_dict(v)
                     for v in inventory.json(run / "source-read-info.json"))
    _require(result["case_id"] == case.id and result["case_identity"] == case.identity
             and result["arm"]["name"] == "baseline" and result["arm"]["views"] is False
             and result["arm"]["scope"] is False and result["failure"] is None
             and result["coverage"] == COMPLETE and result["incomplete_calls"] == [],
             "incomplete or misbound baseline result")
    trace = result["trace"]
    _require(trace["coverage"] == COMPLETE and trace["missing_or_opaque_components"] == [],
             "incomplete trace")
    ids = [capture["call_id"] for capture in captures]
    _require(len(ids) == len(set(ids)) and ids == trace["expected_call_ids"]
             and ids == [row["call_id"] for row in trace["calls"]], "capture inventory mismatch")
    _require(invocations == [row for call_id in ids for row in (
        {"call_id": call_id, "state": "pending"}, {"call_id": call_id, "state": "captured"},
    )], "incomplete invocation inventory")
    files = _snapshot(run / "workspace")
    _require(files == {p: t.encode() for p, t in case.fixtures}, "original workspace changed")
    for path in files:
        inventory.read(run / "workspace" / path)
    previous_body, visible_receipts = None, set()
    previous_action: dict = {}
    records, input_tokens, output_tokens = [], 0, 0
    for capture, measured in zip(captures, trace["calls"]):
        _require(capture["complete"] is True and capture["reason"] == "ok"
                 and capture["error_type"] is None
                 and type(capture["input"]) is str and type(capture["output"]) is str,
                 "incomplete capture")
        _require(measured["coverage"] == COMPLETE
                 and measured["completion_status"] == "succeeded"
                 and measured["missing_or_opaque_components"] == [],
                 "incomplete measured call")
        for field in ("input", "output"):
            _require(_sha(capture[field].encode()) == measured[field + "_sha256"],
                     "capture digest mismatch")
            _require(tokens.count_tokens(capture[field]) == measured["reference_" + field + "_tokens"],
                     "reference count mismatch")
        body, response = parse_json(capture["input"]), parse_json(capture["output"])
        _require(body["model"] == result["model"] == response["model"]
                 and response["status"] == "completed"
                 and response.get("incomplete_details") is None, "incomplete model response")
        if previous_body is None:
            _require(len(body["input"]) == 2, "missing initial capture")
        else:
            prefix = previous_body["input"]
            _require(body["input"][:len(prefix)] == prefix and len(body["input"]) == len(prefix) + 2,
                     "history omitted or changed")
            added_call, added_result = body["input"][-2:]
            _require({k: added_call[k] for k in ("type", "call_id", "name")}
                     == {k: previous_action[k] for k in ("type", "call_id", "name")}
                     and parse_json(added_call["arguments"]) == parse_json(previous_action["arguments"])
                     and added_result["type"] == "function_call_output"
                     and added_result["call_id"] == previous_action["call_id"],
                     "history not bound to previous action")
        actions = [item for item in response["output"] if item.get("type") == "function_call"]
        _require(len(actions) == 1, "ambiguous response action")
        previous_body, previous_action = body, actions[0]
        record = replay_request(capture["input"], case, receipts)
        record.update(run=run.name, call_id=capture["call_id"])
        visible_receipts.update(record["visible_receipt_call_ids"])
        records.append(record)
        input_tokens += measured["reference_input_tokens"]
        output_tokens += measured["reference_output_tokens"]
    _require(previous_action["name"] == "answer", "missing final answer")
    _require(visible_receipts == {r.call_id for r in receipts}, "unbound executor receipts")
    _require(result["totals"]["calls"] == len(captures)
             and result["totals"]["input_tokens"] == input_tokens
             and result["totals"]["output_tokens"] == output_tokens
             and result["totals"]["total_tokens"] == input_tokens + output_tokens,
             "incomplete recorded totals")
    return records


def replay_study(study, *, expected_captures=69):
    """Validate frozen source/capture inventories, then audit every baseline input."""
    study = safe_root(study)
    batch = study.parent
    inventory = _Inventory(batch)
    manifest = inventory.json(study / "manifest.json")
    common = inventory.json(batch / "manifest.json")
    summary = inventory.json(study / "summary.json")
    sources = inventory.json(batch / "source-manifest.json")
    _require(manifest["suite"] == "six-task" and summary["complete"] is True
             and summary["missing_task_runs"] == [], "incomplete study")
    _require(manifest["common_manifest_sha256"] == _sha(inventory.read(batch / "manifest.json"))
             and common["frozen_source_identity"] == digest(sources), "original source inventory mismatch")
    source_inventory = {}
    for path, expected in sources.items():
        relative = safe_path(path.replace("\\", "/"))
        actual = _sha(inventory.read(batch / "source/token-master-plugin" / relative))
        _require(actual == expected, "original frozen source changed: " + relative)
        source_inventory[relative] = actual
    vocabulary = batch / "cl100k_base.tiktoken"
    _require(_sha(inventory.read(vocabulary)) == tokens.VOCABULARY_SHA256, "invalid old vocabulary")
    os.environ["BRAINSPACE_TOKENIZER_FILE"] = str(vocabulary)
    tokens.count_tokens("offline replay")
    _require(tokens.backend_info() == common["tokenizer"], "reference tokenizer identity mismatch")
    cases = {case.id: case for case in parity_cases.load_cases()}
    _require(manifest["oracle"] == parity_cases.ORACLE_ID and len(manifest["tasks"]) == len(cases),
             "original parity corpus mismatch")
    for task in manifest["tasks"]:
        _require(task["id"] in cases and task["identity"] == cases[task["id"]].identity
                 and digest({k: v for k, v in task.items() if k != "identity"}) == task["identity"],
                 "case identity mismatch")
    scheduled = [(repeat, case) for repeat, case, arm in manifest["schedule"] if arm == "baseline"]
    _require(set(scheduled) == {(r, c) for r in range(3) for c in cases}
             and len(scheduled) == 18, "incomplete baseline schedule")
    names = {f"r{repeat}-{case}-baseline" for repeat, case in scheduled}
    _require({p.name for p in (study / "runs").glob("*-baseline")} == names,
             "baseline run inventory mismatch")
    implementation = {}
    for path in (
        Path(__file__), PLUGIN / "evals/source_read_adapter.py", PLUGIN / "evals/run_repository.py",
        PLUGIN / "evals/parity_cases.py", PLUGIN / "evals/parity-cases.json",
        PLUGIN / "skills/token-master/brainspace/request_policy.py",
        PLUGIN / "skills/token-master/brainspace/exact_reuse.py",
        PLUGIN / "skills/token-master/brainspace/tokens.py",
    ):
        implementation[str(path)] = _sha(path.read_bytes())
    records = []
    for repeat, case_id in scheduled:
        records.extend(_load_run(study / "runs" / f"r{repeat}-{case_id}-baseline",
                                 cases[case_id], inventory))
    _require(len(records) == expected_captures
             and len({r["call_id"] for r in records}) == len(records), "expected capture count mismatch")
    inventory.verify_unchanged()
    _require({p.name for p in (study / "runs").glob("*-baseline")} == names,
             "baseline inventory changed during replay")
    _require(all(_sha(Path(p).read_bytes()) == value for p, value in implementation.items()),
             "replay implementation changed during replay")
    changed = [r for r in records if not r["serialized_request_unchanged"]]
    capture_inventory = {path: entry for path, entry in inventory.entries.items()
                         if path.startswith(study.name + "/runs/") and "/workspace/" not in path}
    result = {
        "protocol": "conservative-offline-replay-v1", "study": str(study),
        "complete": True, "runs": len(names), "captures": len(records),
        "changed_requests": len(changed), "unchanged_requests": len(records) - len(changed),
        "histories_with_exact_duplicates": sum(bool(r["duplicate_read_pairs"]) for r in records),
        "all_originals_not_mutated": all(r["originals_not_mutated"] for r in records),
        "callback_invocations": sum(sum(r["callbacks"].values()) for r in records),
        "reference_input_tokens_before": sum(r["reference_input_tokens_before"] for r in records),
        "reference_input_tokens_after": sum(r["reference_input_tokens_after"] for r in records),
        "policy": ConservativeArm("conservative").policy.to_dict(), "tokenizer": tokens.backend_info(),
        "original_source_inventory": source_inventory,
        "original_source_inventory_digest": digest(sources),
        "capture_inventory": capture_inventory, "capture_inventory_digest": digest(capture_inventory),
        "input_inventory": inventory.entries, "input_inventory_digest": digest(inventory.entries),
        "implementation": implementation, "implementation_digest": digest(implementation),
        "original_inventories_unchanged": True, "requests": records,
        "limitations": [
            "Fixed saved histories only; no model/provider calls or task-quality inference.",
            "Old executor has no fetch_artifact receipts; none are synthesized.",
            "Reference counts are not provider billing or hidden computation.",
        ],
    }
    result["evidence_digest"] = digest(result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    output = safe_root(args.output)
    _require(not output.exists(), "refusing to overwrite output")
    _require(not output.is_relative_to(safe_root(args.study).parent), "output cannot enter old evidence")
    report = replay_study(args.study)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=True, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({k: report[k] for k in ("captures", "changed_requests", "unchanged_requests",
                                           "reference_input_tokens_before", "reference_input_tokens_after")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
