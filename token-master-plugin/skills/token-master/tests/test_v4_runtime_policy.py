"""Guarded v4 catalog data and synthetic controller gates; no component calls."""
from dataclasses import FrozenInstanceError, asdict, fields, replace
import hashlib
import json
import socket
import subprocess

import pytest

from brainspace.learning_runtime import CATALOG_VERSION, ProfileLearningManifest, RuntimeLearningManifest
from brainspace.optimizer import Optimizer, OptimizerError
from brainspace.request_policy import RequestPolicy, policy_neighbors
from brainspace.runtime_policy import (
    MAX_CONTROLLER_NEIGHBORS, RuntimePolicy, baseline_policy_admissible,
    controller_policy_neighbors, controller_policy_sort_key, decode_policy,
)
from test_optimizer import baseline_check, config, pair


V4 = "request-policy-v4"
V3 = "request-policy-v3"
LEGACY = ("request-policy-v1", "request-policy-v2", V3)
FIXED_NESTED = (
    "max_input_tokens", "max_wire_bytes", "max_output_tokens", "protected_roles",
    "recovery_required", "quality_gate", "measurement_protocol",
)


@pytest.fixture(autouse=True)
def no_execution(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("catalog checks may not invoke network, models, or Docker")
    monkeypatch.setattr(subprocess, "Popen", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


def local(version=V4, **changes):
    return RuntimePolicy(
        backend="local", request_policy=RequestPolicy(version=version, enabled=True, **changes),
        require_nonexpanding_input=version == V4)


def v4_neighbor(value):
    candidates = [p for p in controller_policy_neighbors(value)
                  if p.backend == "local" and p.request_policy.version == V4]
    assert len(candidates) == 1
    return candidates[0]


def test_direct_true_off_to_v4_preserves_legacy_local_candidate_and_freezes():
    baseline = RuntimePolicy()
    neighbors = controller_policy_neighbors(baseline)
    candidate = v4_neighbor(baseline)
    assert local(V3) in neighbors
    assert len(neighbors) == 6
    assert sum(p.headroom_strategy == "native-documents-v1" for p in neighbors) == 2
    assert sum(p.headroom_root_reference_style == "compact-root-v1" for p in neighbors) == 1
    assert candidate == local()
    assert candidate.instruction == "none" and candidate.require_nonexpanding_input
    assert candidate.request_policy == replace(baseline.request_policy, version=V4, enabled=True)
    assert baseline_policy_admissible(candidate)
    with pytest.raises(FrozenInstanceError):
        candidate.require_nonexpanding_input = False


@pytest.mark.parametrize("instruction", ["none", "ponytail"])
def test_direct_mode_choice_preserves_caps_protections_pins_and_existing_guidance(instruction):
    baseline = RuntimePolicy(
        instruction=instruction, request_policy=RequestPolicy(
            version=V3, max_input_tokens=8000, max_wire_bytes=32000, max_output_tokens=512))
    candidate = v4_neighbor(baseline)
    assert candidate.instruction == instruction
    for name in FIXED_NESTED:
        assert getattr(candidate.request_policy, name) == getattr(baseline.request_policy, name)
    for field in fields(RuntimePolicy):
        if field.name not in {"backend", "request_policy", "require_nonexpanding_input"}:
            assert getattr(candidate, field.name) == getattr(baseline, field.name)


@pytest.mark.parametrize("version", LEGACY)
def test_local_legacy_to_v4_is_one_mode_choice_without_retuning(version):
    baseline = local(version, min_tool_chars=765, keep_recent_tool_results=3, max_transforms=5,
                     max_input_tokens=8000, max_wire_bytes=32000, max_output_tokens=512)
    candidate = v4_neighbor(baseline)
    assert candidate == replace(
        baseline, request_policy=replace(baseline.request_policy, version=V4),
        require_nonexpanding_input=True)
    assert replace(candidate, request_policy=replace(candidate.request_policy, version=V3)) in (
        controller_policy_neighbors(candidate))
    assert all(p.require_nonexpanding_input for p in controller_policy_neighbors(candidate)
               if p.backend == "local" and p.request_policy.version == V4)


@pytest.mark.parametrize("backend,guard", [
    ("local", False), ("none", False), ("none", True), ("headroom", False), ("headroom", True),
])
def test_v4_requires_local_enabled_and_whole_request_guard(backend, guard):
    with pytest.raises(ValueError):
        RuntimePolicy(backend=backend, request_policy=RequestPolicy(version=V4, enabled=backend == "local"),
                      require_nonexpanding_input=guard)


def test_explicit_v4_codec_roundtrip_and_invalid_guard_rejects_every_admission():
    nested = RequestPolicy(version=V4, enabled=True)
    assert type(decode_policy(nested.to_json())) is RequestPolicy
    assert decode_policy(nested.to_json()) == nested
    candidate = local()
    assert decode_policy(candidate.to_json()) == candidate
    forged = candidate.to_dict()
    forged["require_nonexpanding_input"] = False
    with pytest.raises(ValueError):
        RuntimePolicy.from_dict(forged)
    object.__setattr__(candidate, "require_nonexpanding_input", False)
    assert baseline_policy_admissible(candidate) is False
    with pytest.raises(ValueError):
        controller_policy_neighbors(candidate)


@pytest.mark.parametrize("version", [*LEGACY, V4])
@pytest.mark.parametrize("extreme", [False, True])
def test_catalog_bounded_deduplicated_sorted_and_caps_preserved(version, extreme):
    baseline = local(version, min_tool_chars=1 if extreme else 765,
                     keep_recent_tool_results=64 if extreme else 3,
                     max_transforms=64 if extreme else 5,
                     max_input_tokens=8000, max_wire_bytes=32000, max_output_tokens=512)
    neighbors = controller_policy_neighbors(baseline)
    assert neighbors == controller_policy_neighbors(baseline)
    assert neighbors == tuple(sorted(neighbors, key=controller_policy_sort_key))
    assert len(neighbors) == len({p.policy_id for p in neighbors}) <= MAX_CONTROLLER_NEIGHBORS == 12
    assert baseline.policy_id not in {p.policy_id for p in neighbors}
    for p in neighbors:
        p.__post_init__()
        for name in FIXED_NESTED:
            assert getattr(p.request_policy, name) == getattr(baseline.request_policy, name)
        if p.backend != "local":
            assert p.request_policy.version == V3


def test_v4_direct_controller_membership_freeze_and_unchanged_strict_gate(tmp_path):
    # Synthetic equal-quality observations cannot certify the direct candidate.
    opt = Optimizer(tmp_path / "controller.sqlite",
                    config=config(synthetic_only=True, max_candidates=12),
                    evaluator=lambda trial, task: pair(trial, task, equal=True))
    baseline = RuntimePolicy()
    opt.initialize(baseline, validator=baseline_check, validation_call_limit=0)
    candidate = v4_neighbor(baseline)
    assert candidate.policy_id in opt.preflight_learning(("fresh-v4",))["available_candidate_ids"]
    assert candidate in opt.propose()
    trial = opt.freeze(candidate.policy_id, sample_size=100)
    assert trial.incumbent == baseline and trial.candidate == candidate
    certificate = opt.evaluate(trial.trial_id, [f"synthetic-v4-{i}" for i in range(100)])
    assert certificate.decision == "not_certified"
    with pytest.raises(OptimizerError):
        opt.promote(trial.trial_id)
    assert opt.status()["champion"]["policy_id"] == baseline.policy_id


def test_new_catalog_is_frozen_and_obsolete_catalog_rejects_without_legacy_manifest_changes():
    cfg = config(synthetic_only=True)
    args = (cfg, "fixture-host", (("fixture-task", "a" * 64),), 1)
    legacy = RuntimeLearningManifest(*args)
    expected = {"version": "runtime-learning-pair-v1", **asdict(legacy)}
    encoded = json.dumps(expected, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    assert legacy.to_dict() == expected
    assert legacy.identity == hashlib.sha256(encoded.encode()).hexdigest()
    assert "catalog_version" not in legacy.to_dict()
    manifest = ProfileLearningManifest(*args, resources_id="runtime-resources-v1:" + "b" * 64)
    assert CATALOG_VERSION == manifest.catalog_version == "runtime-policy-neighbors-v4"
    assert manifest.to_dict()["catalog_version"] == CATALOG_VERSION
    with pytest.raises(FrozenInstanceError):
        setattr(manifest, "catalog_version", "runtime-policy-neighbors-v3")
    with pytest.raises(ValueError, match="unsupported_profile_learning_contract"):
        replace(manifest, catalog_version="runtime-policy-neighbors-v3")


@pytest.mark.parametrize("version", LEGACY)
@pytest.mark.parametrize("enabled", [False, True])
def test_all_captured_legacy_request_policy_vectors_and_neighbor_order_unchanged(version, enabled):
    baseline = RequestPolicy(version=version, enabled=enabled, min_tool_chars=765,
                             keep_recent_tool_results=3, max_transforms=5,
                             max_input_tokens=1000, max_wire_bytes=9000, max_output_tokens=256)
    decoded = decode_policy(baseline.to_json())
    assert type(decoded) is RequestPolicy
    assert decoded.to_json() == baseline.to_json() and decoded.policy_id == baseline.policy_id
    assert controller_policy_neighbors(baseline) == policy_neighbors(baseline)
    payload = [baseline.to_json(), baseline.policy_id, [
        [p.to_json(), p.policy_id, list(controller_policy_sort_key(p))]
        for p in controller_policy_neighbors(baseline)]]
    digest = hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    assert digest == LEGACY_VECTOR_HASHES[(version, enabled)]


# Frozen before changing controller catalog/codec; wire, IDs, ordered neighbors and sort keys.
LEGACY_VECTOR_HASHES = {
    ('request-policy-v1', False): 'cc4e4d2927d43bd2188835a599640436c85511dadbd347496232150ca6e3b2e1',
    ('request-policy-v1', True): 'acd17267920a3256ffcce960463ab0d67105608845ab31a5b5a6f2d0a73918bb',
    ('request-policy-v2', False): 'c4245fa361096ec431aa08153c4154bf35bc4299357a3bb2872a1b4633119c23',
    ('request-policy-v2', True): 'c36e562b92dc7b38efea8f3dc531232b256696a4c7d3c8bd757c46fe4467440a',
    ('request-policy-v3', False): '9d927a54d93ef965ff11c87f4bc04a51e2c0c6e850936f031793c0b9d7af460a',
    ('request-policy-v3', True): '6f904e8e5a53b6bbf7c7e3523d134793cb3456490cf1f67c0132d0b4e097f376',
}
