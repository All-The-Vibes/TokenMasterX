"""Closed policy data/codec checks; no runtime, provider, Docker or assets."""
import ast
from dataclasses import FrozenInstanceError, asdict, fields
import hashlib
import json
from pathlib import Path
import socket
import subprocess
from typing import Any

import pytest

from brainspace import runtime_policy as policies
from brainspace.headroom import COMMIT, IMAGE_ID, MODEL_REVISION
from brainspace.headroom_worker import MODEL_SHA256, TOKENIZER_REVISION
from brainspace.ponytail import PINNED_INSTRUCTIONS_SHA256, PINNED_SOURCE_COMMIT
from brainspace.request_policy import RequestPolicy, policy_neighbors
from brainspace.runtime_policy import (
    EXECUTION_CONTRACT, MAX_CONTROLLER_NEIGHBORS, RuntimePolicy, baseline_policy_admissible,
    controller_policy_neighbors, controller_policy_sort_key, decode_policy,
)


@pytest.fixture(autouse=True)
def no_execution(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("policy data helpers must not execute or request anything")
    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(subprocess, "Popen", deny)


def local(version="request-policy-v3", **changes):
    return RuntimePolicy(backend="local", request_policy=RequestPolicy(version=version, enabled=True, **changes))


def test_true_off_default_is_admissible_without_fake_enabled_or_asset_claim():
    policy = RuntimePolicy()
    assert policy.backend == policy.instruction == "none"
    assert policy.request_policy == RequestPolicy(version="request-policy-v3", enabled=False)
    assert policy.require_nonexpanding_input is False and policy.headroom_time_budget_seconds is None
    assert not hasattr(policy, "enabled")
    assert baseline_policy_admissible(policy)
    assert not baseline_policy_admissible(RequestPolicy())
    assert baseline_policy_admissible(RequestPolicy(enabled=True))
    assert RuntimePolicy(instruction="ponytail").backend == "none"  # Instruction-only, not true off.


def test_component_pins_match_known_product_constants():
    policy = RuntimePolicy()
    assert policy.execution_contract == EXECUTION_CONTRACT
    assert (policy.ponytail_source_commit, policy.ponytail_instructions_sha256) == (
        PINNED_SOURCE_COMMIT, PINNED_INSTRUCTIONS_SHA256)
    assert (policy.headroom_image_id, policy.headroom_source_commit, policy.headroom_model_revision,
            policy.headroom_model_sha256, policy.headroom_tokenizer_revision) == (
        IMAGE_ID, COMMIT, MODEL_REVISION, MODEL_SHA256, TOKENIZER_REVISION)


@pytest.mark.parametrize("version", ["request-policy-v1", "request-policy-v2", "request-policy-v3"])
@pytest.mark.parametrize("enabled", [False, True])
def test_legacy_wire_id_neighbor_sequence_and_sorting_are_exactly_preserved(version, enabled):
    original = RequestPolicy(version=version, enabled=enabled, min_tool_chars=765,
                             keep_recent_tool_results=3, max_transforms=5,
                             max_input_tokens=1000, max_wire_bytes=9000, max_output_tokens=256)
    wire = original.to_json()
    decoded = decode_policy(wire)
    assert type(decoded) is RequestPolicy and decoded == original
    assert decoded.to_json().encode() == wire.encode()
    assert decoded.policy_id == original.policy_id == version + ":" + hashlib.sha256(wire.encode()).hexdigest()
    assert controller_policy_neighbors(original) == policy_neighbors(original)
    def old_key(p):
        return (p.min_tool_chars, p.keep_recent_tool_results, -p.max_transforms, p.policy_id)
    assert controller_policy_sort_key(original) == old_key(original)
    assert sorted(controller_policy_neighbors(original), key=controller_policy_sort_key) == sorted(
        policy_neighbors(original), key=old_key)


@pytest.mark.parametrize("policy", [
    RuntimePolicy(), RuntimePolicy(instruction="ponytail"),
    RuntimePolicy(instruction="ponytail", require_nonexpanding_input=True),
    local(), local("request-policy-v1"), RuntimePolicy(backend="headroom"),
    RuntimePolicy(backend="headroom", instruction="ponytail", require_nonexpanding_input=True,
                  headroom_time_budget_seconds=5),
])
def test_roundtrip_detached_dict_and_distinct_domain(policy):
    wire = policy.to_json()
    assert RuntimePolicy.from_json(wire) == RuntimePolicy.from_dict(policy.to_dict()) == decode_policy(wire) == policy
    assert wire == json.dumps(policy.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert policy.policy_id == "runtime-policy-v1:" + hashlib.sha256(wire.encode()).hexdigest()
    assert policy.policy_id != policy.request_policy.policy_id
    detached = policy.to_dict()
    detached["request_policy"]["protected_roles"].append("user")
    assert policy.request_policy.protected_roles == ("system", "developer")
    with pytest.raises(FrozenInstanceError):
        policy.instruction = "ponytail"
    with pytest.raises(FrozenInstanceError):
        policy.request_policy.enabled = True


@pytest.mark.parametrize("name", [
    "version", "execution_contract", "ponytail_source_commit", "ponytail_instructions_sha256",
    "headroom_image_id", "headroom_source_commit", "headroom_model_revision",
    "headroom_model_sha256", "headroom_tokenizer_revision",
])
def test_reject_changed_pins_and_unknown_contract(name):
    value = RuntimePolicy().to_dict()
    value[name] = "unknown"
    with pytest.raises(ValueError):
        RuntimePolicy.from_dict(value)


@pytest.mark.parametrize("changes", [
    {"backend": "module:factory"}, {"backend": True}, {"instruction": "local-mode"},
    {"require_nonexpanding_input": 1}, {"require_nonexpanding_input": True},
    {"backend": "local"}, {"request_policy": {"enabled": False}},
    {"request_policy": RequestPolicy(version="request-policy-v1")},
    {"request_policy": RequestPolicy(version="request-policy-v3", min_tool_chars=512)},
    {"request_policy": RequestPolicy(version="request-policy-v3", enabled=True)},
    {"headroom_time_budget_seconds": 5},
    {"backend": "headroom", "headroom_time_budget_seconds": True},
    {"backend": "headroom", "headroom_time_budget_seconds": 0},
    {"backend": "headroom", "headroom_time_budget_seconds": 61},
    {"backend": "headroom", "headroom_time_budget_seconds": 1.5},
])
def test_noncanonical_or_inconsistent_execution_settings_reject(changes):
    with pytest.raises(ValueError):
        RuntimePolicy(**changes)


@pytest.mark.parametrize("name", ["command", "path", "api_key", "model", "oracle", "plugin", "factory"])
def test_unknown_data_fields_reject(name):
    value = RuntimePolicy().to_dict()
    value[name] = "not-supported"
    with pytest.raises(ValueError, match="fields"):
        RuntimePolicy.from_dict(value)


@pytest.mark.parametrize("wire", [
    "[]", "null", '{"version":"other"}',
    '{"version":"runtime-policy-v1","version":"runtime-policy-v1"}',
    '{"version":"runtime-policy-v1","headroom_time_budget_seconds":NaN}',
    '{"version":"runtime-policy-v1","headroom_time_budget_seconds":1e999}',
    '{"version":"runtime-policy-v1","request_policy":{"version":"request-policy-v3","enabled":false,"enabled":true}}',
    " " * 65537,
], ids=["array", "null", "unknown", "duplicate", "nan", "overflow", "nested_duplicate", "oversized"])
def test_strict_bounded_runtime_json_rejects_ambiguous_or_nonfinite_input(wire):
    with pytest.raises(ValueError):
        decode_policy(wire)


def test_unknown_objects_and_subclasses_are_not_plugins():
    class Foreign(RequestPolicy):
        pass
    invalid: tuple[Any, ...] = (None, object(), "factory", {}, Foreign(enabled=True))
    for value in invalid:
        assert baseline_policy_admissible(value) is False
        with pytest.raises(ValueError, match="unsupported"):
            controller_policy_neighbors(value)
        with pytest.raises(ValueError, match="unsupported"):
            controller_policy_sort_key(value)


def test_tampered_frozen_instance_fails_closed():
    value = RuntimePolicy()
    object.__setattr__(value, "execution_contract", "forged")
    assert baseline_policy_admissible(value) is False
    with pytest.raises(ValueError):
        value.to_json()
    with pytest.raises(ValueError):
        controller_policy_neighbors(value)


def test_default_neighborhood_reaches_all_component_choices_without_false_off_guard():
    neighbors = controller_policy_neighbors(RuntimePolicy())
    assert {(p.backend, p.instruction) for p in neighbors} == {
        ("local", "none"), ("headroom", "none"), ("none", "ponytail")}
    assert len(neighbors) == 6
    assert sum(p.request_policy.version == "request-policy-v4" for p in neighbors) == 1
    for policy in neighbors:
        assert policy.request_policy.enabled is (policy.backend == "local")
        assert policy.headroom_time_budget_seconds is None
        assert policy.require_nonexpanding_input is (
            policy.request_policy.version == "request-policy-v4"
            or policy.headroom_strategy == "native-documents-v1")
    guarded = RuntimePolicy(instruction="ponytail", require_nonexpanding_input=True)
    assert RuntimePolicy() in controller_policy_neighbors(guarded)


@pytest.mark.parametrize("policy", [
    RuntimePolicy(), RuntimePolicy(instruction="ponytail", require_nonexpanding_input=True),
    local(), local("request-policy-v2", min_tool_chars=1, keep_recent_tool_results=64, max_transforms=64),
    RuntimePolicy(backend="headroom", instruction="ponytail", require_nonexpanding_input=True,
                  headroom_time_budget_seconds=30),
])
def test_neighbors_are_bounded_unique_deterministic_single_concept_and_keep_all_invariants(policy):
    neighbors = controller_policy_neighbors(policy)
    assert neighbors == controller_policy_neighbors(policy)
    assert neighbors == tuple(sorted(neighbors, key=controller_policy_sort_key))
    assert 0 < len(neighbors) <= MAX_CONTROLLER_NEIGHBORS
    assert len({p.policy_id for p in neighbors}) == len(neighbors)
    assert policy.policy_id not in {p.policy_id for p in neighbors}
    fixed = [f.name for f in fields(RuntimePolicy) if f.name not in {
        "backend", "instruction", "request_policy", "require_nonexpanding_input",
        "headroom_time_budget_seconds", "headroom_strategy", "headroom_root_reference_style"}]
    for neighbor in neighbors:
        assert type(neighbor) is RuntimePolicy
        assert all(getattr(neighbor, f) == getattr(policy, f) for f in fixed)
        for invariant in ("max_input_tokens", "max_output_tokens", "max_wire_bytes",
                          "protected_roles", "recovery_required", "quality_gate", "measurement_protocol"):
            assert getattr(neighbor.request_policy, invariant) == getattr(policy.request_policy, invariant)
        changed = {key for key in asdict(policy) if asdict(policy)[key] != asdict(neighbor)[key]}
        if neighbor.backend != policy.backend:
            assert changed <= {"backend", "request_policy", "headroom_time_budget_seconds",
                               "require_nonexpanding_input", "headroom_strategy", "headroom_root_reference_style"}
        elif neighbor.instruction != policy.instruction:
            assert changed <= {"instruction", "require_nonexpanding_input"}
        elif neighbor.request_policy.version != policy.request_policy.version:
            assert changed <= {"request_policy", "require_nonexpanding_input"}
            assert neighbor.require_nonexpanding_input is True
            assert "request-policy-v4" in (neighbor.request_policy.version, policy.request_policy.version)
        elif neighbor.headroom_strategy != policy.headroom_strategy:
            assert changed <= {"headroom_strategy", "require_nonexpanding_input"}
            if neighbor.headroom_strategy == "native-documents-v1":
                assert neighbor.require_nonexpanding_input is True
        elif neighbor.headroom_root_reference_style != policy.headroom_root_reference_style:
            assert changed <= {"headroom_root_reference_style", "require_nonexpanding_input"}
            if neighbor.headroom_root_reference_style == "compact-root-v1":
                assert neighbor.require_nonexpanding_input is True
        else:
            assert len(changed) == 1


@pytest.mark.parametrize("budget,expected", [(None, {1}), (1, {None, 2}), (30, {29, 31}), (60, {59})])
def test_budget_domain_is_closed_adjacent_and_inactive_switch_resets(budget, expected):
    policy = RuntimePolicy(backend="headroom", headroom_time_budget_seconds=budget)
    neighbors = controller_policy_neighbors(policy)
    moves = {p.headroom_time_budget_seconds for p in neighbors
             if p.backend == policy.backend and p.headroom_time_budget_seconds != budget}
    assert moves == expected
    assert all(p.headroom_time_budget_seconds is None for p in neighbors if p.backend != "headroom")


def test_local_tuning_reuses_exact_legacy_moves_and_caps_survive_off_switch():
    policy = local(max_input_tokens=5000, max_wire_bytes=6000, max_output_tokens=256,
                   min_tool_chars=300, keep_recent_tool_results=3, max_transforms=2)
    neighbors = controller_policy_neighbors(policy)
    actual = {p.request_policy for p in neighbors if p.backend == "local"
              and p.instruction == policy.instruction
              and p.require_nonexpanding_input == policy.require_nonexpanding_input}
    assert actual == set(policy_neighbors(policy.request_policy))
    off = next(p for p in neighbors if p.backend == "none")
    assert off.request_policy == RequestPolicy(version="request-policy-v3", enabled=False,
                                               max_input_tokens=5000, max_wire_bytes=6000,
                                               max_output_tokens=256)


def test_module_has_no_runtime_optimizer_eval_or_dynamic_imports():
    tree = ast.parse(Path(policies.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module not in ("runtime", "optimizer") and not (node.module or "").startswith("evals")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in ("__import__", "eval", "exec")
