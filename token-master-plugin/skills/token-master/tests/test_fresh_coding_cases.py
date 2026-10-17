"""Offline corpus qualification. NEVER execute candidate/gold source on this host.

Correct patches are independently written implementations, not expected outputs
used by the hidden oracle. Real execution goes exclusively through the existing
Linux/WSL isolation boundary. An unavailable sandbox FAILS these tests, not skips.
No model/network calls, tokenizer, credentials, or new dependencies are needed.
"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import inspect
import json
from pathlib import Path
import sys

import pytest

EVALS = Path(__file__).resolve().parents[3] / "evals"
sys.path.insert(0, str(EVALS))
import fresh_coding_cases as fresh  # noqa: E402
from quality.cases import Case, digest, materialize  # noqa: E402
from quality.sandbox import sandbox_runner  # noqa: E402


CASES = fresh.load_cases()
GOOD = {
    "fresh_fifo_reservations": {
        "inventory.py": '''def reserve(stock, requests):
    if any(q < 0 for q in stock) or any(r[0] < 0 or r[0] >= len(stock) or r[1] < 0 for r in requests):
        raise ValueError("domain")
    allocations = [max(0, min(requests[i][1], stock[requests[i][0]] - sum(r[1] for r in requests[:i] if r[0] == requests[i][0]))) for i in range(len(requests))]
    remaining = [max(0, stock[i] - sum(r[1] for r in requests if r[0] == i)) for i in range(len(stock))]
    return (remaining, allocations)
''',
        "shortages.py": '''def shortages(requests, allocations):
    if len(requests) != len(allocations):
        raise ValueError("length")
    if any(r[0] < 0 or r[1] < 0 for r in requests) or any(allocations[i] < 0 or allocations[i] > requests[i][1] for i in range(len(requests))):
        raise ValueError("domain")
    return [(requests[i][0], requests[i][1] - allocations[i]) for i in range(len(requests)) if requests[i][1] > allocations[i]]
''',
    },
    "fresh_window_accounting": {
        "windows.py": '''def covered_minutes(windows, start, end):
    if end < start or any(w[1] < w[0] for w in windows):
        raise ValueError("range")
    clipped = sorted([(max(w[0], start), min(w[1], end)) for w in windows if w[1] > start and w[0] < end])
    return union_length(clipped, start)

def union_length(ordered, cursor):
    if not ordered:
        return 0
    return max(0, ordered[0][1] - max(ordered[0][0], cursor)) + union_length(ordered[1:], max(cursor, ordered[0][1]))
''',
        "charging.py": '''def charge(minutes, included, block, price):
    if minutes < 0 or included < 0 or block <= 0 or price < 0:
        raise ValueError("domain")
    paid = max(0, minutes - included)
    return ((paid + block - 1) // block) * price
''',
    },
    "fresh_revision_paging": {
        "revisions.py": '''def compact(events, cutoff):
    if cutoff < 0 or any(e[1] < 0 for e in events):
        raise ValueError("revision")
    eligible = [e for e in events if e[1] <= cutoff]
    keys = [eligible[i][0] for i in range(len(eligible)) if eligible[i][0] not in [e[0] for e in eligible[:i]]]
    return [(key, payload(eligible, key)) for key in keys if payload(eligible, key) is not None]

def payload(events, key):
    revision = max(e[1] for e in events if e[0] == key)
    matches = [e[2] for e in events if e[0] == key and e[1] == revision]
    return matches[-1]
''',
        "paging.py": '''def page(rows, offset, limit):
    if offset < 0 or limit <= 0:
        raise ValueError("bounds")
    selected = rows[offset:offset + limit]
    following = offset + len(selected)
    return (selected, following if following < len(rows) else None)
''',
    },
    "fresh_counter_rates": {
        "counters.py": '''def increments(samples, modulus):
    if modulus <= 0 or any(s[1] < 0 or s[1] >= modulus for s in samples):
        raise ValueError("counter")
    if any(samples[i][0] <= samples[i-1][0] for i in range(1, len(samples))):
        raise ValueError("timestamps")
    return [(samples[i][1] - samples[i-1][1]) % modulus for i in range(1, len(samples))]
''',
        "rates.py": '''def rate_segments(samples, deltas, max_gap):
    if max_gap <= 0 or len(deltas) != max(0, len(samples)-1):
        raise ValueError("shape")
    if any(s[1] < 0 for s in samples) or any(d < 0 for d in deltas):
        raise ValueError("negative")
    if any(samples[i][0] <= samples[i-1][0] for i in range(1, len(samples))):
        raise ValueError("timestamps")
    return [(samples[i-1][0], samples[i][0], deltas[i-1] / (samples[i][0] - samples[i-1][0])) for i in range(1, len(samples)) if samples[i][0] - samples[i-1][0] <= max_gap]
''',
    },
}

# A second algorithmic implementation for one module in EACH task proves that
# successful grading is behavioral, not exact-patch equality.
ALTERNATIVES = {
    "fresh_fifo_reservations": {
        "inventory.py": '''def reserve(stock, requests):
    if any(q < 0 for q in stock) or any(r[0] < 0 or r[0] >= len(stock) or r[1] < 0 for r in requests):
        raise ValueError("domain")
    return allocate(stock, requests)

def allocate(stock, requests):
    if not requests:
        return (stock[:], [])
    sku = requests[0][0]
    grant = min(stock[sku], requests[0][1])
    next_stock = [stock[i] - grant if i == sku else stock[i] for i in range(len(stock))]
    tail = allocate(next_stock, requests[1:])
    return (tail[0], [grant] + tail[1])
''',
    },
    "fresh_window_accounting": {
        "windows.py": '''def covered_minutes(windows, start, end):
    if end < start or any(w[1] < w[0] for w in windows):
        raise ValueError("range")
    ordered = sorted([(max(w[0], start), min(w[1], end)) for w in windows if w[1] > start and w[0] < end])
    return sum(max(0, ordered[i][1] - max(ordered[i][0], max([start] + [w[1] for w in ordered[:i]]))) for i in range(len(ordered)))
''',
    },
    "fresh_revision_paging": {
        "revisions.py": '''def compact(events, cutoff):
    if cutoff < 0 or any(e[1] < 0 for e in events):
        raise ValueError("revision")
    eligible = [e for e in events if e[1] <= cutoff]
    keys = [eligible[i][0] for i in range(len(eligible)) if all(e[0] != eligible[i][0] for e in eligible[:i])]
    rows = [(key, winner(eligible, key)) for key in keys]
    return [row for row in rows if row[1] is not None]

def winner(events, key):
    candidates = [(events[i][1], i) for i in range(len(events)) if events[i][0] == key]
    best = max(candidates)
    return events[best[1]][2]
''',
    },
    "fresh_counter_rates": {
        "counters.py": '''def increments(samples, modulus):
    if modulus <= 0 or any(s[1] < 0 or s[1] >= modulus for s in samples):
        raise ValueError("counter")
    if any(samples[i][0] <= samples[i-1][0] for i in range(1, len(samples))):
        raise ValueError("timestamps")
    return [difference(samples[i-1][1], samples[i][1], modulus) for i in range(1, len(samples))]

def difference(before, after, modulus):
    if after < before:
        return modulus - before + after
    return after - before
''',
    },
}

# Each mutation preserves parseability/allowed syntax but violates a distinct
# behavioral edge. Both edited modules are independently challenged.
MUTATIONS = {
    "fresh_fifo_reservations": [
        ("inventory.py", "requests[:i]", "requests[:0]"),
        ("shortages.py", "requests[i][1] > allocations[i]", "allocations[i] == 0"),
    ],
    "fresh_window_accounting": [
        ("windows.py", "union_length(clipped, start)",
         "sum(max(0, w[1] - w[0]) for w in clipped)"),
        ("charging.py", "(paid + block - 1) // block", "paid // block"),
    ],
    "fresh_revision_paging": [
        ("revisions.py", "return matches[-1]", "return matches[0]"),
        ("paging.py", "following < len(rows)", "following <= len(rows)"),
    ],
    "fresh_counter_rates": [
        ("counters.py", "(samples[i][1] - samples[i-1][1]) % modulus",
         "samples[i][1] - samples[i-1][1]"),
        ("rates.py", "samples[i][0] - samples[i-1][0] <= max_gap",
         "samples[i][0] - samples[i-1][0] < max_gap"),
    ],
}


def reads(case):
    return [{"name": "read_file", "arguments": {"path": path}} for path in case.files]


def prepare(case, tmp_path, patch=None):
    root = materialize(case, tmp_path / "workspace")
    events = reads(case)
    for path, text in (patch or {}).items():
        assert path in case.allowed_changes
        (root / path).write_bytes(text.encode("utf-8"))
        events.append({"name": "write_file", "arguments": {"path": path, "content": text}})
    events.append({"name": "answer", "arguments": {"content": "Implemented."}})
    return root, events


def forbidden_runner(plan):
    pytest.fail("sandbox must not launch on invalid input")


def qualified_runner(replies):
    def run(plan):
        assert set(plan) == {
            "identity", "case_identity", "oracle_identity", "sources",
            "test_code", "timeout_seconds",
        }
        assert plan["identity"] == digest({k: v for k, v in plan.items() if k != "identity"})
        reply = sandbox_runner(plan)
        replies.append(reply)
        return reply
    return run


def test_frozen_exactly_four_bounded_authored_cases_and_public_api():
    manifest = fresh._load_manifest()
    assert hashlib.sha256(fresh.MANIFEST_PATH.read_bytes()).hexdigest() == fresh.CORPUS_SHA256
    assert len(CASES) == 4 and len({c.id for c in CASES}) == 4
    assert len({task["category"] for task in manifest["tasks"]}) == 4
    assert "not_iid_or_representative_production_data" in manifest["scope"]
    assert "independently_authored" in manifest["scope"]
    assert manifest["max_tool_calls"] == 10
    assert str(inspect.signature(fresh.grade)) == "(case, root, answer, events, *, sandbox_runner=None)"
    assert str(inspect.signature(fresh.load_cases)) == "() -> 'list[Case]'"
    assert fresh.ORACLE_ID.startswith("authored-fresh-coding-v1:")
    for case in CASES:
        assert type(case) is Case
        assert case.intent == "edit" and not case.followups
        assert len(case.fixtures) == 3 and len(case.allowed_changes) == 2
        assert sum(len(text.encode()) for _, text in case.fixtures) < 4500
        # Three reads, two writes, one answer fit with four recovery calls spare.
        assert len(case.fixtures) + len(case.allowed_changes) + 1 <= fresh.MAX_TOOL_CALLS
        assert "Read ALL" in case.prompt and "Change ONLY" in case.prompt
        assert all(path in case.prompt for path in case.files)


def test_hidden_tests_and_gold_never_appear_in_public_cases():
    for case, task in zip(CASES, fresh._load_manifest()["tasks"]):
        public = case.public_task()
        assert set(public) == {"id", "version", "identity", "prompt", "paths", "allowed_changes"}
        visible = json.dumps({"public": public, "fixtures": case.fixtures})
        assert task["hidden_tests"] not in visible
        assert "FRESH_CODING_OK" not in visible
        assert "hidden_tests" not in visible
        assert case.global_hint == ""
        for source in GOOD[case.id].values():
            assert source not in dict(case.fixtures).values()


def test_no_prior_fixture_reuse():
    new_text = {text for case in CASES for _, text in case.fixtures}
    new_ids = {case.id for case in CASES}
    for name in ("parity-cases.json", "retention-cases.json", "recovery-replication-cases.json"):
        old = json.loads((EVALS / name).read_bytes())
        assert not new_ids & {task["id"] for task in old["tasks"]}
        # Recursively collect strings as data only, never import old fixtures.
        def strings(value):
            if isinstance(value, str):
                yield value
            elif isinstance(value, dict):
                for child in value.values():
                    yield from strings(child)
            elif isinstance(value, list):
                for child in value:
                    yield from strings(child)
        assert not new_text & set(strings(old))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
@pytest.mark.parametrize("alternative", [False, True], ids=["independent-fix", "alternative-fix"])
def test_independent_correct_patches_pass_real_isolated_oracle(case, alternative, tmp_path):
    patch = dict(GOOD[case.id])
    if alternative:
        patch.update(ALTERNATIVES[case.id])
    root, events = prepare(case, tmp_path, patch)
    replies = []
    result = fresh.grade(case, root, "Any summary is fine.", events,
                         sandbox_runner=qualified_runner(replies))
    assert result["status"] == "passed", (result, replies)
    assert result["success"] is True
    assert all(result["assertions"].values())
    assert result["checks"] == []
    assert sorted(case.allowed_changes) == result["changed_files"]
    assert fresh._boundary_ready(replies[0]), replies
    assert replies[0]["plan_identity"]
    assert "test_code" not in json.dumps(result) and "stderr" not in result


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
@pytest.mark.parametrize("fixed_module", [None, 0, 1], ids=["original", "only-first", "only-second"])
def test_originals_and_partial_fixes_fail_behaviorally(case, fixed_module, tmp_path):
    patch = {} if fixed_module is None else {
        case.allowed_changes[fixed_module]: GOOD[case.id][case.allowed_changes[fixed_module]]
    }
    root, events = prepare(case, tmp_path, patch)
    replies = []
    result = fresh.grade(case, root, "Claimed correct.", events,
                         sandbox_runner=qualified_runner(replies))
    assert result["success"] is False, (result, replies)
    assert "hidden_behavior_tests_failed" in result["checks"], (result, replies)
    assert fresh._boundary_ready(replies[0]), replies
    assert replies[0]["exit_code"] == 1


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
@pytest.mark.parametrize("module_index", [0, 1])
def test_nontrivial_edge_mutations_fail_real_behavior_tests(case, module_index, tmp_path):
    patch = dict(GOOD[case.id])
    path, old, new = MUTATIONS[case.id][module_index]
    assert patch[path].count(old) == 1
    patch[path] = patch[path].replace(old, new)
    root, events = prepare(case, tmp_path, patch)
    replies = []
    result = fresh.grade(case, root, "", events, sandbox_runner=qualified_runner(replies))
    assert result["success"] is False, (result, replies)
    assert "hidden_behavior_tests_failed" in result["checks"], (result, replies)
    assert fresh._boundary_ready(replies[0]), replies


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_behavior_preserving_parameter_rename_still_breaks_public_api(case, tmp_path):
    patch = dict(GOOD[case.id])
    path = case.allowed_changes[0]
    parameter = {
        "fresh_fifo_reservations": "stock", "fresh_window_accounting": "windows",
        "fresh_revision_paging": "events", "fresh_counter_rates": "samples",
    }[case.id]
    patch[path] = patch[path].replace(parameter, "records")
    root, events = prepare(case, tmp_path, patch)
    replies = []
    result = fresh.grade(case, root, "", events, sandbox_runner=qualified_runner(replies))
    assert result["success"] is False, (result, replies)
    assert "hidden_behavior_tests_failed" in result["checks"], (result, replies)
    assert fresh._boundary_ready(replies[0]), replies


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_no_sandbox_is_inconclusive_never_host_execution(case, tmp_path):
    root, events = prepare(case, tmp_path, GOOD[case.id])
    result = fresh.grade(case, root, "", events)
    assert result["success"] is None and result["status"] == "inconclusive"
    assert "sandbox_required" in result["checks"]


@pytest.mark.parametrize("mutation", ["extra", "deleted", "protected", "newline", "deleted_source"])
def test_workspace_inventory_and_non_target_bytes_are_preserved(mutation, tmp_path):
    case = CASES[0]
    root, events = prepare(case, tmp_path, GOOD[case.id])
    protected = root / "CONTRACT.txt"
    if mutation == "extra":
        (root / "extra.py").write_bytes(b"def fake():\n    return 0\n")
    elif mutation == "deleted":
        protected.unlink()
    elif mutation == "protected":
        protected.write_bytes(b"substituted contract")
    elif mutation == "deleted_source":
        (root / case.allowed_changes[0]).unlink()
    else:
        protected.write_bytes(protected.read_bytes().replace(b"\n", b"\r\n"))
    result = fresh.grade(case, root, "", events, sandbox_runner=forbidden_runner)
    assert result["success"] is False
    assert "source_scope_preserved" in result["checks"]


@pytest.mark.parametrize("kind", ["same_bytes", "restored", "rejected"])
def test_forbidden_write_attempt_fails_even_when_final_bytes_match(kind, tmp_path):
    case = CASES[0]
    root, events = prepare(case, tmp_path, GOOD[case.id])
    text = case.files["CONTRACT.txt"]
    events.insert(-1, {"name": "write_file", "arguments": {
        "path": "CONTRACT.txt", "content": text if kind == "same_bytes" else "changed",
    }})
    if kind == "restored":
        (root / "CONTRACT.txt").write_bytes(b"changed")
        (root / "CONTRACT.txt").write_bytes(text.encode())
    result = fresh.grade(case, root, "", events, sandbox_runner=forbidden_runner)
    assert not result["success"]
    assert "tool_scope_respected" in result["checks"]
    assert result["forbidden_files"] == []


@pytest.mark.parametrize("events", [
    None, {}, [None], [{"name": [], "arguments": {}}],
    [{"name": "run_python", "arguments": {"code": "print('FRESH_CODING_OK')"}}],
    [{"name": "read_file", "arguments": {"path": "../escape"}}],
    [{"name": "read_file", "arguments": {"path": ["not a path"]}}],
    [{"name": "read_file", "arguments": {"path": "inventory.py", "extra": 1}}],
    [{"name": "retrieve_original", "arguments": {"ref": "r", "offset": True}}],
    [{"name": "retrieve_original", "arguments": {"ref": "r", "offset": -1}}],
    [{"name": "search_original", "arguments": {"ref": "r", "query": 3}}],
    [{"name": "headroom_retrieve", "arguments": {"hash": 3}}],
])
def test_malformed_or_unexposed_tools_fail_closed(events, tmp_path):
    case = CASES[0]
    root, _ = prepare(case, tmp_path, GOOD[case.id])
    result = fresh.grade(case, root, "", events, sandbox_runner=forbidden_runner)
    assert result["success"] is False


def test_read_all_before_edits_and_call_budget_are_audited(tmp_path):
    case = CASES[0]
    root, events = prepare(case, tmp_path, GOOD[case.id])
    for invalid in (events[1:], [events[3], *events[:3], *events[4:]],
                    events[:-1] + [{"name": "list_files", "arguments": {}}] * 5 + events[-1:],
                    events + [{"name": "list_files", "arguments": {}}]):
        result = fresh.grade(case, root, "", invalid, sandbox_runner=forbidden_runner)
        assert result["success"] is False
    # Eight schemas, recovery metadata, and exact ten-call boundary.
    permitted = [
        *[{"name": "fetch_artifact", "arguments": e["arguments"]} for e in reads(case)],
        *events[3:-1],
        {"name": "list_files", "arguments": {}},
        {"name": "retrieve_original", "arguments": {"ref": "r", "offset": 0}},
        {"name": "search_original", "arguments": {"ref": "r", "query": "contract"}},
        {"name": "headroom_retrieve", "arguments": {"hash": "abcdef"}, "call_id": "audit-1"},
        events[-1],
    ]
    assert len(permitted) == 10
    assert fresh._events(case, permitted) == (True, True)


@pytest.mark.parametrize("field", ["prompt", "fixtures", "allowed_changes", "intent"])
def test_case_substitution_cannot_redefine_task(field, tmp_path):
    case = CASES[0]
    values = {
        "prompt": case.prompt + " Forged",
        "fixtures": ((case.fixtures[0][0], "forged"), *case.fixtures[1:]),
        "allowed_changes": (*case.allowed_changes, "CONTRACT.txt"),
        "intent": "overview",
    }
    forged = replace(case, **{field: values[field]})
    root, events = prepare(forged, tmp_path)
    result = fresh.grade(forged, root, "", events, sandbox_runner=forbidden_runner)
    assert result["success"] is False and "known_case" in result["checks"]


@pytest.mark.parametrize("field", ["hidden_tests", "prompt", "fixtures", "allowed_changes"])
def test_manifest_tampering_rejected_before_tests_are_trusted(field, tmp_path, monkeypatch):
    manifest = fresh._load_manifest()
    task = manifest["tasks"][0]
    if field == "fixtures":
        task[field]["inventory.py"] += "\n"
    elif field == "allowed_changes":
        task[field].append("CONTRACT.txt")
    else:
        task[field] += " forged"
    path = tmp_path / "untrusted.json"
    path.write_bytes(json.dumps(manifest).encode())
    monkeypatch.setattr(fresh, "MANIFEST_PATH", path)
    with pytest.raises(ValueError, match="integrity mismatch"):
        fresh.load_cases()
    case = CASES[0]
    root, events = prepare(case, tmp_path, GOOD[case.id])
    result = fresh.grade(case, root, "", events, sandbox_runner=forbidden_runner)
    assert not result["success"] and "manifest_integrity" in result["checks"]


def test_loads_do_not_share_mutable_private_state():
    manifest = fresh._load_manifest()
    manifest["tasks"][0]["hidden_tests"] = "forged"
    cases = fresh.load_cases()
    cases.clear()
    assert fresh.load_cases() == CASES
    assert fresh._load_manifest()["tasks"][0]["hidden_tests"] != "forged"


def test_spoofed_stdout_missing_attestation_and_exceptions_never_pass(tmp_path):
    case = CASES[0]
    root, events = prepare(case, tmp_path, GOOD[case.id])
    replies = [
        None,
        {"exit_code": 0, "stdout": "FRESH_CODING_OK\n", "stderr": ""},
        {"exit_code": 0, "timed_out": False, "stdout": "FRESH_CODING_OK\n", "stderr": ""},
    ]
    for reply in replies:
        def run(plan):
            return dict(reply, plan_identity=plan["identity"]) if isinstance(reply, dict) else reply
        result = fresh.grade(case, root, "", events, sandbox_runner=run)
        assert result["status"] == "inconclusive" and result["success"] is None
    def broken(plan):
        raise RuntimeError("unavailable")
    assert fresh.grade(case, root, "", events, sandbox_runner=broken)["success"] is None


def test_sandbox_receipt_tampering_and_workspace_race_fail_closed(tmp_path):
    case = CASES[0]
    root, events = prepare(case, tmp_path, GOOD[case.id])
    replies = []
    passed = fresh.grade(case, root, "", events, sandbox_runner=qualified_runner(replies))
    assert passed["success"], (passed, replies)
    original = replies[0]
    for key, value in [
        ("plan_identity", "0" * 64), ("exit_code", True), ("timed_out", None),
        ("stdout", ""), ("stderr", "injected"), ("boundary", {}),
    ]:
        bad = deepcopy(original)
        bad[key] = value
        result = fresh.grade(case, root, "", events, sandbox_runner=lambda plan: bad)
        assert result["success"] is None, (key, result)
    for key in ("readonly_root", "process_reaped", "scoped_cleanup", "host_canary_hidden"):
        bad = deepcopy(original)
        bad["boundary"][key] = False
        assert fresh.grade(case, root, "", events, sandbox_runner=lambda plan: bad)["success"] is None
    for key, value in (("timed_out", True), ("output_limit_exceeded", True), ("exit_code", 1)):
        bad = deepcopy(original)
        bad[key] = value
        result = fresh.grade(case, root, "", events, sandbox_runner=lambda plan: bad)
        assert result["success"] is False
        assert "hidden_behavior_tests_failed" in result["checks"]
    def racing(plan):
        (root / case.allowed_changes[0]).write_bytes(b"changed while grading")
        return original
    result = fresh.grade(case, root, "", events, sandbox_runner=racing)
    assert result["success"] is False
    assert "workspace_changed_during_validation" in result["checks"]


def test_unsupported_code_is_rejected_inside_sandbox_not_host(tmp_path):
    case = CASES[0]
    patch = dict(GOOD[case.id])
    patch["inventory.py"] = "import os\n"
    root, events = prepare(case, tmp_path, patch)
    replies = []
    result = fresh.grade(case, root, "", events, sandbox_runner=qualified_runner(replies))
    assert result["success"] is False, (result, replies)
    assert "candidate_rejected_by_sandbox_policy" in result["checks"]
    assert replies[0]["boundary"]["executed"] is False
    assert replies[0]["boundary"]["stage"] == "preflight"


def test_answer_text_is_not_correctness_and_is_bound_to_evidence(tmp_path):
    case = CASES[0]
    root, events = prepare(case, tmp_path)
    first = fresh.grade(case, root, "correct", events)
    second = fresh.grade(case, root, "incorrect", events)
    assert first["success"] is None and second["success"] is None
    assert first["evidence_digest"] != second["evidence_digest"]
    invalid = fresh.grade(case, root, float("nan"), events, sandbox_runner=forbidden_runner)
    assert invalid["success"] is False


def test_missing_or_linked_workspaces_fail_closed(tmp_path):
    case = CASES[0]
    assert fresh.grade(case, tmp_path / "absent", "", reads(case),
                       sandbox_runner=forbidden_runner)["success"] is False
    root, events = prepare(case, tmp_path)
    link = root / "linked"
    try:
        link.symlink_to(root / "CONTRACT.txt")
    except OSError:
        return  # Missing workspace check remains mandatory; Windows may deny symlinks.
    result = fresh.grade(case, root, "", events, sandbox_runner=forbidden_runner)
    assert result["success"] is False and "safe_workspace" in result["checks"]
