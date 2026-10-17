"""Closed compact-root policy selection; no CCR, worker, native or model calls."""
from dataclasses import FrozenInstanceError, asdict, fields, replace
import hashlib
import socket
import subprocess

import pytest

from brainspace.request_policy import RequestPolicy
from brainspace.runtime_policy import (
    MAX_CONTROLLER_NEIGHBORS, RuntimePolicy, baseline_policy_admissible,
    controller_policy_neighbors, controller_policy_sort_key, decode_policy,
)


ANNOTATED = "annotated-v1"
COMPACT = "compact-root-v1"
DOCUMENTS = "native-documents-v1"
UPSTREAM = "upstream-default-v1"
FIELD = "headroom_root_reference_style"
# Captured before adding the root-style field. Old default IDs are not recomputed.
OLD_HEADROOM_IDS = [
    (UPSTREAM, "none", None, "1028e049f8aec5f317c20ae7fb36ece6f65d6eff163d16d6e814917b70433559"),
    (DOCUMENTS, "none", None, "79bcf3ca9eec6b7dea3df86b3c115dee36ff645b7376883dea8ff36713421776"),
    (UPSTREAM, "ponytail", None, "a5a2229a8ce8eb5f42cbc2344a5011e0c6809842f0660f4d593702521bd7ae95"),
    (UPSTREAM, "ponytail", 1, "93dc0cb782920c7e33290af46c781d44ac488f854349b5ecb6892304dd6b9c16"),
    (UPSTREAM, "ponytail", 30, "815c9301adae106f1a21e418927ba476874fbcfdc698967fb0549f31d1c0ebd4"),
    (UPSTREAM, "ponytail", 60, "db752788f2c1d6d79511667959b22eee27522b60838e8dfecd0aac9084255d8c"),
    (DOCUMENTS, "ponytail", None, "8bbfb9658ec2a802810bf587df1f76ce6602f6dac95d8af8a22a6b2de1562e6f"),
    (DOCUMENTS, "ponytail", 1, "de9bb1f0136c1e9a2d10300a0acf7ca6e51ce0341eab6c3cbca962e663ee3ef0"),
    (DOCUMENTS, "ponytail", 30, "5c25216229c7a232c87355da242131cba55e59184274c44e2b291650666cc5d5"),
    (DOCUMENTS, "ponytail", 60, "5054f305664068facb343d034f75103f49a29db1bd8da1f2afeff6aee91eb101"),
]
OLD_OFF_NEIGHBORS = [
    "runtime-policy-v1:0d9b509c8c71f63f9d61a844b1390e492f1a2443b03bf2cd952199655c5060f9",
    "runtime-policy-v1:ac0b4fd80d6b2f5426fc128cf4bbf1b89046d967fc01df802a49dc65bfa42ce1",
    "runtime-policy-v1:a3b2d79486c692059b9f24ca723f7fd67275bf5c848b360140759a7623990833",
    "runtime-policy-v1:e47f2e8461bea75a1934b6975184943b02bb1206263995dabe7e33caa0011e9d",
    "runtime-policy-v1:79bcf3ca9eec6b7dea3df86b3c115dee36ff645b7376883dea8ff36713421776",
]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("root-style policy checks may not start a process or use a network")

    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(subprocess, "Popen", deny)


def compact(**changes):
    return RuntimePolicy(**{
        "backend": "headroom", "require_nonexpanding_input": True, FIELD: COMPACT, **changes})


@pytest.mark.parametrize("strategy,instruction,budget,digest", OLD_HEADROOM_IDS)
def test_old_default_headroom_wire_and_ids_are_exactly_preserved(strategy, instruction, budget, digest):
    policy = RuntimePolicy(backend="headroom", headroom_strategy=strategy, instruction=instruction,
                           require_nonexpanding_input=True, headroom_time_budget_seconds=budget)
    assert policy.headroom_root_reference_style == ANNOTATED
    assert FIELD not in policy.to_dict()
    assert hashlib.sha256(policy.to_json().encode()).hexdigest() == digest
    assert policy.policy_id == "runtime-policy-v1:" + digest
    assert decode_policy(policy.to_json()) == policy
    assert RuntimePolicy.from_dict({**policy.to_dict(), FIELD: ANNOTATED}).to_json() == policy.to_json()
    assert replace(policy, headroom_root_reference_style=ANNOTATED).to_json() == policy.to_json()


@pytest.mark.parametrize("strategy", [UPSTREAM, DOCUMENTS])
def test_compact_is_explicit_detached_immutable_and_identity_bound(strategy):
    policy = compact(headroom_strategy=strategy)
    old = replace(policy, headroom_root_reference_style=ANNOTATED)
    assert policy.to_dict() == {**old.to_dict(), FIELD: COMPACT}
    assert policy.policy_id != old.policy_id
    assert RuntimePolicy.from_json(policy.to_json()) == decode_policy(policy.to_json()) == policy
    detached = policy.to_dict()
    detached[FIELD] = ANNOTATED
    assert policy.headroom_root_reference_style == COMPACT
    with pytest.raises(FrozenInstanceError):
        setattr(policy, FIELD, ANNOTATED)


@pytest.mark.parametrize("style", ["", "compact", "compact-root-v2", "module:compact", None, True, 1, [], {}])
def test_only_the_two_typed_styles_are_admitted(style):
    with pytest.raises(ValueError):
        compact(**{FIELD: style})


@pytest.mark.parametrize("settings", [
    {"backend": "none"},
    {"backend": "none", "instruction": "ponytail"},
    {"backend": "local", "request_policy": RequestPolicy(version="request-policy-v3", enabled=True)},
    {"backend": "local", "request_policy": RequestPolicy(version="request-policy-v4", enabled=True)},
    {"require_nonexpanding_input": False},
])
def test_no_inactive_local_or_unguarded_compact_selection(settings):
    with pytest.raises(ValueError):
        compact(**settings)


@pytest.mark.parametrize("wire", [
    '{"version":"runtime-policy-v1","backend":"headroom","require_nonexpanding_input":true,'
    '"headroom_root_reference_style":"annotated-v1","headroom_root_reference_style":"compact-root-v1"}',
    '{"version":"runtime-policy-v1","headroom_root_reference_style":NaN}',
    '{"version":"runtime-policy-v1","headroom_root_reference_style":"compact-root-v1","root_style":"other"}',
    " " * 65537,
], ids=["duplicate", "nonfinite", "unknown_field", "oversized"])
def test_style_codec_keeps_strict_bounded_parsing(wire):
    with pytest.raises(ValueError):
        decode_policy(wire)


def test_forged_inactive_selection_cannot_bypass_admission_or_serialization():
    policy = RuntimePolicy()
    object.__setattr__(policy, FIELD, COMPACT)
    assert not baseline_policy_admissible(policy)
    for operation in (policy.to_dict, policy.to_json, lambda: controller_policy_neighbors(policy)):
        with pytest.raises(ValueError):
            operation()


def test_off_has_six_choices_retaining_all_five_old_ids_and_one_direct_compact_document_entry():
    neighbors = controller_policy_neighbors(RuntimePolicy())
    assert len(neighbors) == 6
    assert [p.policy_id for p in neighbors if p.headroom_root_reference_style == ANNOTATED] == OLD_OFF_NEIGHBORS
    assert [p for p in neighbors if p.headroom_root_reference_style == COMPACT] == [
        compact(headroom_strategy=DOCUMENTS)]
    assert all(p.headroom_root_reference_style == ANNOTATED for p in neighbors if p.backend != "headroom")


def test_direct_compact_document_entry_preserves_explicit_caps_and_protections():
    policy = RuntimePolicy(request_policy=RequestPolicy(
        version="request-policy-v3", max_input_tokens=8765, max_wire_bytes=54321, max_output_tokens=321))
    candidate, = [p for p in controller_policy_neighbors(policy) if p.headroom_root_reference_style == COMPACT]
    assert candidate == compact(headroom_strategy=DOCUMENTS, request_policy=policy.request_policy)
    assert candidate.instruction == "none" and candidate.headroom_time_budget_seconds is None


@pytest.mark.parametrize("guard", [False, True])
def test_one_root_style_move_derives_guard_but_does_not_retune_other_settings(guard):
    policy = RuntimePolicy(backend="headroom", require_nonexpanding_input=guard, headroom_time_budget_seconds=7)
    changed = [p for p in controller_policy_neighbors(policy) if p.headroom_root_reference_style != ANNOTATED]
    assert changed == [replace(policy, headroom_root_reference_style=COMPACT, require_nonexpanding_input=True)]
    assert replace(changed[0], headroom_root_reference_style=ANNOTATED) in controller_policy_neighbors(changed[0])
    assert all(p.require_nonexpanding_input for p in controller_policy_neighbors(changed[0])
               if p.headroom_root_reference_style == COMPACT)


@pytest.mark.parametrize("strategy", [UPSTREAM, DOCUMENTS])
@pytest.mark.parametrize("style", [ANNOTATED, COMPACT])
@pytest.mark.parametrize("budget", [None, 1, 30, 60])
def test_closed_headroom_neighborhoods_keep_bounds_pins_caps_and_reset_inactive_style(strategy, style, budget):
    policy = RuntimePolicy(
        backend="headroom", headroom_strategy=strategy, headroom_root_reference_style=style,
        instruction="ponytail", require_nonexpanding_input=True, headroom_time_budget_seconds=budget,
        request_policy=RequestPolicy(version="request-policy-v3", min_tool_chars=765,
                                     max_input_tokens=8765, max_wire_bytes=54321, max_output_tokens=321))
    neighbors = controller_policy_neighbors(policy)
    assert neighbors == controller_policy_neighbors(policy)
    assert neighbors == tuple(sorted(neighbors, key=controller_policy_sort_key))
    assert len(neighbors) == len({p.policy_id for p in neighbors}) <= MAX_CONTROLLER_NEIGHBORS == 12
    assert policy.policy_id not in {p.policy_id for p in neighbors}
    tunable = {"backend", "instruction", "request_policy", "require_nonexpanding_input",
               "headroom_time_budget_seconds", "headroom_strategy", FIELD}
    for neighbor in neighbors:
        neighbor.__post_init__()
        for descriptor in fields(policy):
            if descriptor.name not in tunable:
                assert getattr(policy, descriptor.name) == getattr(neighbor, descriptor.name)
        for name in ("max_input_tokens", "max_wire_bytes", "max_output_tokens", "protected_roles",
                     "quality_gate", "recovery_required", "measurement_protocol"):
            assert getattr(policy.request_policy, name) == getattr(neighbor.request_policy, name)
        if neighbor.backend != "headroom":
            assert neighbor.headroom_root_reference_style == ANNOTATED
            assert neighbor.headroom_strategy == UPSTREAM and neighbor.headroom_time_budget_seconds is None
        elif neighbor.headroom_root_reference_style == COMPACT:
            assert neighbor.require_nonexpanding_input
        changed = {key for key, value in asdict(policy).items() if value != asdict(neighbor)[key]}
        if neighbor.backend == policy.backend:
            assert len(changed) == 1  # Guard already true in these parent states.
        else:
            assert changed <= {"backend", "request_policy", "require_nonexpanding_input",
                               "headroom_time_budget_seconds", "headroom_strategy", FIELD}


def test_largest_upstream_headroom_neighborhood_is_eight_not_above_the_fixed_bound():
    policy = RuntimePolicy(backend="headroom", headroom_time_budget_seconds=30)
    assert len(controller_policy_neighbors(policy)) == 8
    assert MAX_CONTROLLER_NEIGHBORS == 12
