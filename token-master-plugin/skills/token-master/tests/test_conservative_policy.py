"""V3 removes no unique evidence and must not manufacture retrieval work."""
import copy
from dataclasses import replace
import json

import pytest

from brainspace.request_policy import (
    PROTOCOL, RequestPolicy, SourceReadInfo, plan_request, serialize_request,
)

TEXT = "def important(value):\n" + "".join(f"    item_{i} = value + {i}\n" for i in range(90))


def payload(contents=None, paths=None):
    contents = contents or [TEXT, TEXT, "other.py"]
    paths = paths or ["module.py", "module.py", "other.py"]
    messages = [{"role": "system", "content": "Original system instructions."},
                {"role": "user", "content": "Explain the code; keep exact details."}]
    infos = []
    for i, (text, path) in enumerate(zip(contents, paths)):
        call = f"call_{i}"
        messages.extend([
            {"role": "assistant", "tool_calls": [{
                "id": call, "type": "function", "function": {
                    "name": "read_file", "arguments": json.dumps({"path": path})}}]},
            {"role": "tool", "tool_call_id": call, "content": text, "ok": True},
        ])
        infos.append(SourceReadInfo.from_text(
            call_id=call, tool_name="read_file", source_path=path,
            content=text, status="success"))
    return {"model": "fixture", "messages": messages, "metadata": {"unchanged": True}}, tuple(infos)


def forbidden(*_):
    pytest.fail("Conservative reuse must never call lossy transform or external recovery")


def plan(request, infos, **changes):
    options = dict(
        policy=RequestPolicy(version="request-policy-v3", enabled=True, min_tool_chars=1),
        protocol=PROTOCOL, intent="navigation", count=len,
        source_reads=infos, transform=forbidden, recover=forbidden, source_transform=forbidden)
    options.update(changes)
    return plan_request(request, **options)


def test_v3_identity_is_distinct_and_legacy_versions_remain_explicit():
    fixed = RequestPolicy(version="request-policy-v3", enabled=True)
    assert RequestPolicy.from_json(fixed.to_json()) == fixed
    assert fixed.policy_id.startswith("request-policy-v3:")
    assert len({replace(fixed, version=v).policy_id for v in (
        "request-policy-v1", "request-policy-v2", "request-policy-v3")}) == 3
    assert RequestPolicy().enabled is False


def test_unique_source_cannot_be_replaced_with_a_recovery_stub():
    request, infos = payload([TEXT, TEXT.replace("important", "different"), "file list"],
                             ["one.py", "two.py", "other.py"])
    before = copy.deepcopy(request)
    result = plan(request, infos)
    assert result.status == "unchanged"
    assert result.request is request and request == before
    assert result.serialized == serialize_request(before)


def test_exact_duplicate_is_reused_without_hiding_the_full_original():
    request, infos = payload()
    before = copy.deepcopy(request)
    result = plan(request, infos)
    assert result.status == "transformed"
    assert result.reason == "exact_visible_reuse"
    assert result.changed_message_indices == (5,)
    assert result.request["messages"][3] == before["messages"][3]
    assert "module.py" in result.request["messages"][5]["content"]
    assert "call_0" in result.request["messages"][5]["content"]
    assert "[[BR:" not in result.request["messages"][5]["content"]
    assert result.tokens_after < result.tokens_before
    assert result.wire_bytes_after <= result.wire_bytes_before
    assert request == before
    for i, message in enumerate(before["messages"]):
        if i != 5:
            assert result.request["messages"][i] == message
    assert result.request["messages"][5].keys() == before["messages"][5].keys()


@pytest.mark.parametrize("options", [
    {"stable_prefix_messages": 6},
    {"exact_message_indices": (5,)},
    {"intent": "exact"},
    {"intent": "unknown"},
    {"intent": None},
    {"source_reads": ()},
])
def test_protected_or_unproven_results_stay_unchanged(options):
    request, infos = payload()
    assert plan(request, infos, **options).status == "unchanged"


def test_recent_duplicate_is_retained():
    request, infos = payload()
    request["messages"] = request["messages"][:6]
    result = plan(request, infos[:2])
    assert result.status == "unchanged"


def test_changed_content_or_different_source_is_not_redundant():
    request, infos = payload(paths=["one.py", "two.py", "other.py"])
    assert plan(request, infos).status == "unchanged"
    request, infos = payload([TEXT, TEXT + "\n# updated", "other.py"])
    assert plan(request, infos).status == "unchanged"


@pytest.mark.parametrize("changes", [
    {"status": "error"}, {"status": "unknown"}, {"source_path": "wrong.py"},
    {"content_sha256": "0" * 64}, {"tool_name": "run_shell"},
])
def test_bad_source_provenance_never_authorizes_reuse(changes):
    request, infos = payload()
    infos = (infos[0], replace(infos[1], **changes), infos[2])
    assert plan(request, infos).status == "unchanged"


@pytest.mark.parametrize("metadata", [
    {"is_error": True}, {"stderr": "failure"}, {"ok": False},
    {"preserve_exact": True}, {"status": "unknown"}, {"exit_code": 1},
])
def test_result_status_and_explicit_exactness_override_receipts(metadata):
    request, infos = payload()
    request["messages"][5].update(metadata)
    assert plan(request, infos).status == "unchanged"


def test_no_measurement_or_bad_measurement_keeps_original():
    request, infos = payload()
    for count in (None, lambda _: True, lambda _: -1):
        assert plan(request, infos, count=count).status == "unchanged"


def test_final_counter_and_budget_can_reject_a_reuse():
    request, infos = payload()
    assert plan(request, infos, count=lambda _: 1).status == "unchanged"
    result = plan(request, infos, policy=RequestPolicy(
        version="request-policy-v3", enabled=True, min_tool_chars=1, max_input_tokens=1))
    assert result.status == "unchanged"
    assert result.reason == "cannot_safely_meet_budget"
