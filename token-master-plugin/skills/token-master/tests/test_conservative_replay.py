"""Offline replay qualification; deliberately no model/provider calls."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

EVALS = Path(__file__).resolve().parents[3] / "evals"
sys.path.insert(0, str(EVALS))
import conservative_replay as replay  # noqa: E402
from brainspace import tokens  # noqa: E402
from brainspace.request_policy import SourceReadInfo  # noqa: E402
from quality.cases import Case, materialize  # noqa: E402


@pytest.fixture(autouse=True)
def deterministic_unit_counter(monkeypatch):
    # Unit fixtures exercise inventory/change checks, not a savings claim.
    # The actual replay requires the pinned tokenizer; tests must not depend
    # on this workstation's historical evidence directory.
    monkeypatch.setattr(tokens, "count_tokens", len)


def case():
    text = "".join(f"value_{i} = {i}\n" for i in range(600))
    return Case("offline-replay-control", "1", "Inspect both files.", (
        ("a.py", text), ("b.py", text + "other = 1\n"),
    ), (), intent="navigation")


def start(bound):
    public = bound.public_task()
    return {"model": "offline-fixture", "input": [
        {"role": "system", "content": "Do not change instructions."},
        {"role": "user", "content": json.dumps({
            key: public[key] for key in ("prompt", "paths", "allowed_changes")})},
    ], "tools": [], "stream": False, "store": False}


def append_read(body, bound, path, call_id, tool="read_file"):
    body["input"].extend([
        {"type": "function_call", "call_id": call_id, "name": tool,
         "arguments": json.dumps({"path": path})},
        {"type": "function_call_output", "call_id": call_id, "output": bound.files[path]},
    ])
    return SourceReadInfo.from_text(
        call_id=call_id, tool_name=tool, source_path=path,
        content=bound.files[path], status="success",
    )


def test_unique_reads_are_byte_identical_passthrough_without_mutation():
    bound, receipts = case(), []
    body = start(bound)
    receipts.append(append_read(body, bound, "a.py", "a"))
    receipts.append(append_read(body, bound, "b.py", "b"))
    before, wire = deepcopy(body), replay.canonical(body)
    result = replay.replay_request(wire, bound, receipts)
    assert body == before
    assert result["serialized_request_unchanged"] is True
    assert result["input_sha256"] == result["planned_input_sha256"]
    assert result["reference_input_tokens_before"] == result["reference_input_tokens_after"]
    assert result["changed_messages"] == []
    assert result["duplicate_read_pairs"] == []
    assert result["callbacks"] == {"transform": 0, "source_transform": 0, "recover": 0}
    assert result["originals_not_mutated"]


def test_changed_eligible_duplicate_is_detected_not_called_passthrough():
    bound = case()
    body = start(bound)
    receipts = [append_read(body, bound, path, str(i))
                for i, path in enumerate(("a.py", "a.py", "b.py"))]
    wire = replay.canonical(body)
    result = replay.replay_request(wire, bound, receipts)
    assert result["status"] == "transformed" and result["reason"] == "exact_visible_reuse"
    assert result["serialized_request_unchanged"] is False
    assert result["duplicate_read_pairs"] == [[3, 5]]
    assert [c["index"] for c in result["changed_messages"]] == [5]
    assert result["reference_input_tokens_after"] < result["reference_input_tokens_before"]
    assert result["input_sha256"] != result["planned_input_sha256"]
    assert replay.canonical(body) == wire


def test_absent_old_fetch_receipts_are_not_manufactured():
    bound = case()
    body = start(bound)
    for i, path in enumerate(("a.py", "a.py", "b.py")):
        append_read(body, bound, path, str(i), tool="fetch_artifact")
    result = replay.replay_request(replay.canonical(body), bound, ())
    assert result["duplicate_read_pairs"] == [[3, 5]]
    assert result["verified_visible_receipts"] == 0
    assert result["serialized_request_unchanged"]


@pytest.mark.parametrize("mutation", ["missing_receipt", "source_bytes", "task", "opaque", "noncanonical"])
def test_invalid_request_inputs_fail_closed(mutation):
    bound = case()
    body = start(bound)
    info = append_read(body, bound, "a.py", "a")
    receipts = [info]
    if mutation == "missing_receipt":
        receipts.clear()
    elif mutation == "source_bytes":
        body["input"][-1]["output"] = "partial read"
    elif mutation == "task":
        body["input"][1]["content"] = "{}"
    elif mutation == "opaque":
        body["previous_response_id"] = "not captured"
    wire = replay.canonical(body) if mutation != "noncanonical" else json.dumps(body, indent=2)
    with pytest.raises(ValueError):
        replay.replay_request(wire, bound, receipts)


@pytest.mark.parametrize("callback", ["transform", "source_transform", "recover"])
def test_swallowed_callback_invocation_still_fails_proof(monkeypatch, callback):
    real = replay.plan_request
    def bad(request, **options):
        try:
            options[callback]("unwanted")
        except AssertionError:
            pass
        return real(request, **options)
    monkeypatch.setattr(replay, "plan_request", bad)
    with pytest.raises(ValueError, match="callback invoked"):
        replay.replay_request(replay.canonical(start(case())), case(), ())


def test_mutating_planner_fails_proof(monkeypatch):
    real = replay.plan_request
    def bad(request, **options):
        request["messages"][0]["content"] = "mutated"
        return real(request, **options)
    monkeypatch.setattr(replay, "plan_request", bad)
    with pytest.raises(ValueError, match="original request mutated"):
        replay.replay_request(replay.canonical(start(case())), case(), ())


def make_run(tmp_path):
    bound, body, observations, captures, measured = case(), start(case()), [], [], []
    run = tmp_path / "run"
    run.mkdir()
    materialize(bound, run / "workspace")
    for index, name in enumerate(("read_file", "read_file", "answer")):
        args = {"path": ("a.py", "b.py")[index]} if name == "read_file" else {"content": "Done"}
        action = {"type": "function_call", "call_id": f"tool-{index}",
                  "name": name, "arguments": json.dumps(args, separators=(",", ":"))}
        text = replay.canonical(body)
        output = replay.canonical({"model": body["model"], "status": "completed",
                                   "incomplete_details": None, "output": [action]})
        call_id = f"call-{index}"
        captures.append({"call_id": call_id, "input": text, "output": output,
                         "complete": True, "reason": "ok", "error_type": None})
        measured.append({
            "call_id": call_id, "coverage": replay.COMPLETE, "completion_status": "succeeded",
            "missing_or_opaque_components": [],
            **{field + "_sha256": replay._sha(value.encode())
               for field, value in (("input", text), ("output", output))},
            "reference_input_tokens": tokens.count_tokens(text),
            "reference_output_tokens": tokens.count_tokens(output),
        })
        if name == "read_file":
            observations.append(append_read(body, bound, args["path"], action["call_id"]))
    incoming = sum(m["reference_input_tokens"] for m in measured)
    outgoing = sum(m["reference_output_tokens"] for m in measured)
    result = {
        "case_id": bound.id, "case_identity": bound.identity, "model": body["model"],
        "arm": {"name": "baseline", "scope": False, "views": False},
        "failure": None, "coverage": replay.COMPLETE, "incomplete_calls": [],
        "trace": {"coverage": replay.COMPLETE, "missing_or_opaque_components": [],
                  "expected_call_ids": [c["call_id"] for c in captures], "calls": measured},
        "totals": {"calls": 3, "input_tokens": incoming, "output_tokens": outgoing,
                   "total_tokens": incoming + outgoing},
    }
    (run / "result.json").write_text(json.dumps(result), encoding="utf-8")
    (run / "source-read-info.json").write_text(
        json.dumps([r.to_dict() for r in observations]), encoding="utf-8")
    write_lines(run / "captures.jsonl", captures)
    write_lines(run / "invocations.jsonl", [
        {"call_id": c["call_id"], "state": state}
        for c in captures for state in ("pending", "captured")
    ])
    return run, bound


def write_lines(path, values):
    path.write_text("".join(json.dumps(v) + "\n" for v in values), encoding="utf-8")


def test_complete_run_has_explicit_inventory_digests(tmp_path):
    run, bound = make_run(tmp_path)
    inventory = replay._Inventory(tmp_path)
    records = replay._load_run(run, bound, inventory)
    assert len(records) == 3 and all(r["serialized_request_unchanged"] for r in records)
    assert len(inventory.entries) == 6  # captures, receipts, invocations, result, two originals
    assert all(len(entry["sha256"]) == 64 for entry in inventory.entries.values())
    inventory.verify_unchanged()


@pytest.mark.parametrize("mutation", [
    "missing_capture", "incomplete_capture", "null_input", "null_output", "duplicate_capture",
    "wrong_capture_hash", "partial_trace", "missing_invocation", "unknown_receipt",
    "wrong_case", "wrong_source", "missing_receipts_file",
])
def test_incomplete_or_corrupt_runs_never_produce_a_report(tmp_path, mutation):
    run, bound = make_run(tmp_path)
    captures = [json.loads(line) for line in (run / "captures.jsonl").read_text().splitlines()]
    result = json.loads((run / "result.json").read_text())
    if mutation == "missing_capture":
        captures.pop()
    elif mutation == "duplicate_capture":
        captures.append(captures[-1])
    elif mutation == "incomplete_capture":
        captures[0]["complete"] = False
    elif mutation == "null_input":
        captures[0]["input"] = None
    elif mutation == "null_output":
        captures[0]["output"] = None
    elif mutation == "wrong_capture_hash":
        result["trace"]["calls"][0]["input_sha256"] = "0" * 64
    elif mutation == "partial_trace":
        result["trace"]["missing_or_opaque_components"] = ["unknown"]
    elif mutation == "missing_invocation":
        (run / "invocations.jsonl").write_text("", encoding="utf-8")
    elif mutation == "unknown_receipt":
        receipts = json.loads((run / "source-read-info.json").read_text())
        receipts[0]["call_id"] = "unbound"
        (run / "source-read-info.json").write_text(json.dumps(receipts), encoding="utf-8")
    elif mutation == "wrong_case":
        result["case_identity"] = "0" * 64
    elif mutation == "wrong_source":
        (run / "workspace/a.py").write_text("changed", encoding="utf-8")
    else:
        (run / "source-read-info.json").unlink()
    write_lines(run / "captures.jsonl", captures)
    (run / "result.json").write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises((ValueError, OSError)):
        replay._load_run(run, bound, replay._Inventory(tmp_path))


def test_input_change_after_inventory_is_rejected(tmp_path):
    path = tmp_path / "input"
    path.write_bytes(b"original")
    inventory = replay._Inventory(tmp_path)
    inventory.read(path)
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        inventory.verify_unchanged()


def test_cli_refuses_overwrite_before_replaying(tmp_path, monkeypatch):
    output = tmp_path / "report.json"
    output.write_bytes(b"existing evidence")
    monkeypatch.setattr(replay, "replay_study", lambda *_: pytest.fail("must not replay"))
    with pytest.raises(ValueError, match="overwrite"):
        replay.main(["--study", str(tmp_path / "old/six-task"), "--output", str(output)])
    assert output.read_bytes() == b"existing evidence"


def test_cli_never_writes_inside_old_study(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, "replay_study", lambda *_: pytest.fail("must not replay"))
    with pytest.raises(ValueError, match="old evidence"):
        replay.main(["--study", str(tmp_path / "old/six-task"),
                     "--output", str(tmp_path / "old/report.json")])
