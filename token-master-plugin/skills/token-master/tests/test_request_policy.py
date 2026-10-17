"""Request planning is opt-in, measured at the final wire boundary, and reversible."""
import copy
import json
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brainspace.request_policy import (
    RequestPolicy, TransformResult, plan_request, policy_neighbors, serialize_request,
)


def request():
    messages = [
        {"role": "system", "content": "Stable system literal \n"},
        {"role": "developer", "content": "Keep every safety requirement."},
        {"role": "user", "content": "Give an overview."},
    ]
    for index in range(3):
        messages.extend([
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": f"call-{index}", "type": "function",
                 "function": {"name": "read", "arguments": '{"path":"a"}'}}]},
            {"role": "tool", "tool_call_id": f"call-{index}",
             "content": f"result-{index} " + "retained original text " * 100,
             "metadata": {"source": f"file-{index}", "order": [3, 1, 2]}},
            {"role": "user", "content": f"next-{index}"},
        ])
    return {"model": "fixture", "messages": messages, "tools": [
        {"type": "function", "function": {"name": "read", "parameters": {
            "type": "object", "properties": {"path": {"type": "string"}}}}}],
        "metadata": {"untouched": True}, "max_tokens": 100}


def planner(payload, **kwargs):
    saved = {}

    def transform(text):
        ref = "ref:" + str(len(saved))
        saved[ref] = text
        return TransformResult("overview; recover " + ref, ref)

    options = dict(policy=RequestPolicy(enabled=True, min_tool_chars=1),
                   protocol="chat-completions-v1", intent="overview",
                   transform=transform, recover=saved.__getitem__, count=len)
    options.update(kwargs)
    return plan_request(payload, **options)


def test_preserves_prefix_pairs_newest_schemas_metadata_order_and_input():
    original = request()
    before = copy.deepcopy(original)
    result = planner(original, stable_prefix_messages=5)
    assert result.status == "transformed"
    assert result.changed_message_indices == (7,)
    assert original == before
    assert result.request["messages"][:5] == before["messages"][:5]
    assert result.request["messages"][10] == before["messages"][10]
    expected = copy.deepcopy(before)
    expected["messages"][7]["content"] = result.request["messages"][7]["content"]
    assert serialize_request(expected) == result.serialized
    assert list(result.request) == list(before)
    assert result.host_interception == "unsupported"
    assert result.measurement == "caller_supplied_uncertified"


@pytest.mark.parametrize("change", [
    {"is_error": True}, {"isError": True}, {"error": {"message": "oops"}},
    {"exit_code": 2}, {"stderr": "warning"}, {"status": "failed"},
    {"exact_answer": True}, {"metadata": {"exact_answer": True}},
    {"content": "FAILED: important exception"}, {"content": "DENIED: important"},
    {"content": "<exact-answer> literal \n </exact-answer>"},
    {"content": "```python\n  literal = 4\n```"},
    {"content": [{"type": "exact_answer", "text": " literal "}]},
    {"content": [{"type": "text", "text": "hello"}, {"type": "image", "data": "abc"}]},
])
def test_errors_and_exact_or_mixed_blocks_are_never_transformed(change):
    payload = request()
    payload["messages"][4].update(change)
    result = planner(payload)
    assert result.request["messages"][4] == payload["messages"][4]


def test_explicit_exact_indices_and_navigation():
    result = planner(request(), intent="navigation", exact_message_indices=(4, 7))
    assert result.status == "unchanged"


@pytest.mark.parametrize("intent", [None, "exact", "debug", "patch", "exhaustive", "unknown"])
def test_ineligible_intent_does_not_invoke_transform(intent):
    result = planner(request(), intent=intent,
                     transform=lambda _: pytest.fail("must not transform"))
    assert result.status == "unchanged"


def test_disabled_by_default_and_no_default_truncation():
    payload = request()
    result = plan_request(payload, protocol="chat-completions-v1", count=len)
    assert result.request is payload
    assert result.reason == "not_enabled"
    assert planner(payload, transform=None).request == payload


@pytest.mark.parametrize("protocol", [None, "unknown", "anthropic-v1", "responses-v1"])
def test_unknown_protocol_passthrough(protocol):
    payload = request()
    result = planner(payload, protocol=protocol,
                     transform=lambda _: pytest.fail("must not transform"))
    assert result.request is payload
    assert result.reason == "unsupported_protocol"


@pytest.mark.parametrize("mutate", [
    lambda p: p.pop("messages"),
    lambda p: p["messages"].__setitem__(4, {"role": "tool", "tool_call_id": "missing", "content": "x"}),
    lambda p: p["messages"][0].update(role="unknown"),
    lambda p: p["messages"].pop(4),
    lambda p: p["messages"][3]["tool_calls"][0].update(type="unknown"),
    lambda p: p["messages"][4].update(content={"unknown": "shape"}),
    lambda p: p["messages"][6]["tool_calls"][0].update(id="call-0"),
    lambda p: p.update(tools="not a list"),
    lambda p: p.update(tools=[{}]),
    lambda p: p["tools"][0].update(type="unsupported"),
    lambda p: p["messages"][4].update(content=[123]),
    lambda p: p["messages"][4].update(content=[{"type": "text", "text": 123}]),
    lambda p: p["messages"][4].update(role=["tool"]),
])
def test_invalid_envelope_passthrough(mutate):
    payload = request()
    mutate(payload)
    result = planner(payload, transform=lambda _: pytest.fail("must not transform"))
    assert result.request is payload
    assert result.reason == "invalid_envelope"


def test_deterministic_wire_and_final_counter_includes_envelope_and_references():
    seen = []

    def count(wire):
        seen.append(wire)
        assert json.loads(wire)["tools"] == request()["tools"]
        return len(wire)

    first = planner(request(), count=count)
    second = planner(request())
    assert first.serialized == second.serialized
    assert first.policy_id == second.policy_id
    assert first.tokens_before == len(serialize_request(request()))
    assert first.tokens_after == len(first.serialized)
    assert first.serialized in seen
    assert "recover ref:" in first.serialized


def test_full_request_count_can_reject_a_shorter_inner_string():
    def nonadditive_count(wire):
        return 10000 if "recover ref:" in wire else 100

    result = planner(request(), count=nonadditive_count)
    assert result.status == "unchanged"
    assert result.tokens_after == 100


def test_equal_token_count_is_not_a_useful_replacement():
    result = planner(request(), count=lambda _: 100)
    assert result.status == "unchanged"


@pytest.mark.parametrize("recover", [None, lambda _: "wrong", lambda _: 1])
def test_missing_or_unverified_recovery_never_elides(recover):
    result = planner(request(), recover=recover)
    assert result.request == request()


def test_recovery_reference_must_be_in_final_text():
    result = planner(request(), transform=lambda _: TransformResult("short", "missing"))
    assert result.status == "unchanged"


@pytest.mark.parametrize("failure", ["transform", "recover", "count"])
def test_callback_failure_is_safe_passthrough(failure):
    def explode(_):
        raise OSError("unavailable")

    result = planner(request(), **{failure: explode})
    assert result.request == request()
    assert result.status == "unchanged"


@pytest.mark.parametrize("count", [lambda _: -1, lambda _: True, lambda _: 1.5])
def test_invalid_measurement_is_not_certified(count):
    assert planner(request(), count=count).reason == "measurement_unavailable"


def test_cannot_safely_meet_budget_rolls_back_all_partial_changes():
    payload = request()
    result = planner(payload, policy=RequestPolicy(enabled=True, min_tool_chars=1,
                                                  max_input_tokens=1))
    assert result.request is payload
    assert result.reason == "cannot_safely_meet_budget"
    assert result.changed_message_indices == ()
    assert result.tokens_after == result.tokens_before


def test_unicode_cap_counts_utf8_serialized_envelope_not_characters():
    payload = request()
    payload["metadata"]["unicode"] = "🙂漢" * 40
    candidate = planner(payload)
    assert len(candidate.serialized.encode("utf-8")) > len(candidate.serialized)
    capped = planner(payload, policy=RequestPolicy(
        enabled=True, min_tool_chars=1, max_wire_bytes=len(candidate.serialized)))
    assert capped.reason == "cannot_safely_meet_budget"
    assert capped.request == payload
    assert candidate.wire_bytes_after == len(candidate.serialized.encode("utf-8"))


def test_output_cap_checks_declaration_without_rewriting_metadata():
    payload = request()
    assert planner(payload, policy=RequestPolicy(
        enabled=True, min_tool_chars=1, max_output_tokens=50)
    ).reason == "cannot_safely_meet_budget"
    assert planner(payload, policy=RequestPolicy(
        enabled=True, min_tool_chars=1, max_output_tokens=100)
    ).request["max_tokens"] == 100
    payload.pop("max_tokens")
    assert planner(payload, policy=RequestPolicy(
        enabled=True, min_tool_chars=1, max_output_tokens=100)
    ).reason == "cannot_safely_meet_budget"


def test_policy_roundtrip_identity_validation_and_bounded_neighbors():
    policy = RequestPolicy(enabled=True, max_input_tokens=5000, max_wire_bytes=10000,
                           max_output_tokens=500)
    assert RequestPolicy.from_json(policy.to_json()) == policy
    assert RequestPolicy.from_dict(policy.to_dict()).policy_id == policy.policy_id
    with pytest.raises(FrozenInstanceError):
        policy.enabled = False
    for bad in [{"version": "future"}, {"enabled": 1}, {"keep_recent_tool_results": 0},
                {"min_tool_chars": -1}, {"max_input_tokens": True},
                {"protected_roles": ("user",)}, {"recovery_required": False},
                {"measurement_protocol": "other"}, {"quality_gate": "none"}]:
        with pytest.raises(ValueError):
            replace(policy, **bad)
    with pytest.raises(ValueError):
        RequestPolicy.from_dict({**policy.to_dict(), "unknown": 1})
    neighbors = policy_neighbors(policy)
    assert 0 < len(neighbors) <= 6
    assert len({p.policy_id for p in neighbors}) == len(neighbors)
    mutable = {"min_tool_chars", "keep_recent_tool_results", "max_transforms"}
    for neighbor in neighbors:
        changed = {key for key in policy.to_dict()
                   if policy.to_dict()[key] != neighbor.to_dict()[key]}
        assert len(changed) == 1
        assert changed <= mutable


def test_multiple_tool_calls_keep_pair_identity_and_order():
    payload = request()
    messages = payload["messages"]
    messages[3]["tool_calls"].append({
        "id": "parallel", "type": "function",
        "function": {"name": "read", "arguments": "{}"},
    })
    messages.insert(5, {"role": "tool", "tool_call_id": "parallel",
                        "content": "parallel original " * 100})
    result = planner(payload)
    assert result.changed_message_indices == (4, 5, 8)
    assert [m.get("tool_call_id") for m in result.request["messages"]] == [
        m.get("tool_call_id") for m in payload["messages"]]
    assert result.request["messages"][3] == payload["messages"][3]
    assert result.request["messages"][11] == payload["messages"][11]


def test_prefix_and_exact_index_validation_is_fail_open():
    for options in ({"stable_prefix_messages": -1}, {"stable_prefix_messages": 999},
                    {"stable_prefix_messages": True}, {"exact_message_indices": (999,)},
                    {"exact_message_indices": "all"}):
        result = planner(request(), **options)
        assert result.reason == "invalid_envelope"
        assert result.request == request()


def test_nothing_serializable_is_coerced_or_pruned():
    for value in (float("nan"), b"bytes", (1, 2), {1: "integer key"}):
        payload = request()
        payload["metadata"]["value"] = value
        result = planner(payload)
        assert result.request is payload
        assert result.reason == "invalid_envelope"


def test_recovery_callback_restores_original_before_view_is_accepted():
    original = request()
    saved = {}
    retrieved = []

    def transform(text):
        reference = "root-" + str(len(saved))
        saved[reference] = text
        return TransformResult("Navigate; restore " + reference, reference)

    def recover(reference):
        retrieved.append(reference)
        return saved[reference]

    result = planner(original, transform=transform, recover=recover)
    assert result.status == "transformed"
    assert retrieved == ["root-0", "root-1"]
    assert saved["root-0"] == original["messages"][4]["content"]
    assert saved["root-1"] == original["messages"][7]["content"]


def test_bounded_policy_limits_number_of_changes_and_retains_newest_results():
    result = planner(request(), policy=RequestPolicy(
        enabled=True, min_tool_chars=1, max_transforms=1, keep_recent_tool_results=2))
    assert result.changed_message_indices == (4,)
    assert result.request["messages"][7:] == request()["messages"][7:]


def test_no_claimed_model_obedience_in_scoped_templates():
    skill = Path(__file__).resolve().parents[1]
    for name in ("claude", "copilot"):
        content = (skill / f"agent.template.{name}.md").read_text("utf-8")
        assert "explain-only means no edits" in content
        assert "deep proofs" in content
        assert "does not guarantee model obedience" in content
        assert "not automatic host interception" in content


def test_pinned_reference_counter_guards_final_wire():
    from brainspace import tokens

    if not tokens.backend_info()["exact_reference"]:
        pytest.skip("exact tokenizer has no verified local vocabulary")
    payload = request()
    payload["metadata"]["unicode"] = "🙂漢 café"
    result = planner(payload, count=tokens.count_tokens)
    assert result.status == "transformed"
    assert result.tokens_before == tokens.count_tokens(serialize_request(payload))
    assert result.tokens_after == tokens.count_tokens(result.serialized)
    assert tokens.guard_replacement(serialize_request(payload), result.serialized,
                                    max_bytes=result.wire_bytes_after)
    assert result.measurement == "caller_supplied_uncertified"


def test_unavailable_exact_counter_does_not_fallback():
    from brainspace.tokens import ReferenceTokenizerUnavailable

    def unavailable(_):
        raise ReferenceTokenizerUnavailable("offline vocabulary absent")

    result = planner(request(), count=unavailable,
                     transform=lambda _: pytest.fail("must not transform"))
    assert result.reason == "measurement_unavailable"
    assert result.tokens_before is None
