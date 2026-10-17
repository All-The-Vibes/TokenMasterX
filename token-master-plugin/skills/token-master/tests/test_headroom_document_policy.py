"""Opt-in Headroom document policy data; no worker, native host or inference."""
from dataclasses import FrozenInstanceError, asdict, fields, replace
import hashlib
import json
import socket
import subprocess

import pytest

from brainspace import runtime_resources as resources
from brainspace.request_policy import RequestPolicy, policy_neighbors
from brainspace.runtime_policy import (
    MAX_CONTROLLER_NEIGHBORS, RuntimePolicy, baseline_policy_admissible,
    controller_policy_neighbors, controller_policy_sort_key, decode_policy,
)


DEFAULT = "upstream-default-v1"
DOCUMENTS = "native-documents-v1"
# Captured from the pre-change implementation, not computed from new behavior.
FROZEN_RUNTIME_HASHES = {
    "off": "579bf9ab6972b791692d7e41fd7a33f2842c48ad830c377d41be357bf4a9d9b1",
    "pony": "50f4d48b0029eceac140130d0133c692ee54db899be5c99193b9749f10c1fa21",
    "local-v1": "95c0e0cefe7c43d8d463a385d56ac7293374132ff08bd72f4c3b0485b357b0af",
    "local-v3": "ac0b4fd80d6b2f5426fc128cf4bbf1b89046d967fc01df802a49dc65bfa42ce1",
    "local-v4": "a3b2d79486c692059b9f24ca723f7fd67275bf5c848b360140759a7623990833",
    "headroom": "e47f2e8461bea75a1934b6975184943b02bb1206263995dabe7e33caa0011e9d",
    "headroom-combined-budget": "b666f0e696273573762db4b27f2eb60e7062ca27828161c13640ff0832aeaebb",
}
FROZEN_LOCAL_NEIGHBORS = {
    "request-policy-v1": "74b376bd6e0fc54d8e2db6d11bbb7521dfbcfaac6f1257624012cbf96ecbc336",
    "request-policy-v3": "1eb731de0e570a57ad9698b601591624275d125a3cbcb7454bf1a1585e9c58cf",
    "request-policy-v4": "eefee6b526166f202518ab213c8d7187b57189cb11bdb9a389f00c384d8ca3c2",
}
FROZEN_REQUEST_HASHES = {
    "request-policy-v1": ("417fcc4d57dea8f0d510e82eb3ee15adb393bfb2ae76374492798674bd43a66d",
                          "4661322e3bc81584f348b20b5bf3a872ae9d1124ca62ccc9f535237013490710"),
    "request-policy-v2": ("ade716ad12144ac23f46c90e15de2a43a8ec25e7c523e4e3ea648ea2e308bbc6",
                          "58a2843cc9d15fdb5f937031ff26daa96bbfdae77c7f296e36dcaa82d3cb0bfb"),
    "request-policy-v3": ("74df5eb2df3c35529146b043713d5095c01bec04bb497edd2a319222f2fd26e7",
                          "dc4d8552ce2a4ebcaa9ecf1ace556704e72f6190a769683f59be773bde766713"),
    "request-policy-v4": ("dafae9b384f613d6aecb78a25bca86f931ff204499a0c71a8765722d07888278",
                          "4309746f7a9ec716f6d77f056caa76a34a8acc138f65569e26c7187940841882"),
}
FROZEN_DEFAULT_JSON = (
    '{"backend":"none","execution_contract":"runtime-execution-v1",'
    '"headroom_image_id":"sha256:eb04988b9360cb5b4d0348a519a5a66232e04593de8f3bbee6571a6a397343c6",'
    '"headroom_model_revision":"b1563631b35bfdcee37587ad530147497d820d4c",'
    '"headroom_model_sha256":"c47ddd764dec5cf91fd1f10cf69e5538dd2a49d913828da7f6a993931cc7904f",'
    '"headroom_source_commit":"1cf496612e781ef8d67ff87ee4f78037492f0bc7",'
    '"headroom_time_budget_seconds":null,'
    '"headroom_tokenizer_revision":"8949b909ec900327062f0ebf497f51aef5e6f0c8",'
    '"instruction":"none",'
    '"ponytail_instructions_sha256":"da4fb09cff2f6726691ce6591cebc38c95597d79da132e49c6fa2665c4e8a3ff",'
    '"ponytail_source_commit":"c982cd411abb53323c4baa1baa3c2f020b8d0b08",'
    '"request_policy":{"enabled":false,"keep_recent_tool_results":1,"max_input_tokens":null,'
    '"max_output_tokens":null,"max_transforms":4,"max_wire_bytes":null,'
    '"measurement_protocol":"json-utf8-compact-v1","min_tool_chars":1024,'
    '"protected_roles":["system","developer"],"quality_gate":"external-certification-required",'
    '"recovery_required":true,"version":"request-policy-v3"},'
    '"require_nonexpanding_input":false,"version":"runtime-policy-v1"}'
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("policy/resource tests may not execute processes or use a network")

    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(subprocess, "Popen", deny)


def legacy_cases():
    return {
        "off": RuntimePolicy(),
        "pony": RuntimePolicy(instruction="ponytail", require_nonexpanding_input=True),
        **{f"local-{version}": RuntimePolicy(
            backend="local", request_policy=RequestPolicy(version="request-policy-" + version, enabled=True),
            require_nonexpanding_input=version == "v4") for version in ("v1", "v3", "v4")},
        "headroom": RuntimePolicy(backend="headroom"),
        "headroom-combined-budget": RuntimePolicy(
            backend="headroom", instruction="ponytail", require_nonexpanding_input=True,
            headroom_time_budget_seconds=7, request_policy=RequestPolicy(
                version="request-policy-v3", max_input_tokens=7777, max_wire_bytes=30000, max_output_tokens=128)),
    }


def documents(**changes):
    return RuntimePolicy(**{
        "backend": "headroom", "require_nonexpanding_input": True, "headroom_strategy": DOCUMENTS,
        **changes,
    })


def sequence_hash(neighbors):
    return hashlib.sha256(json.dumps([p.to_json() for p in neighbors], separators=(",", ":")).encode()).hexdigest()


@pytest.mark.parametrize("name", FROZEN_RUNTIME_HASHES)
def test_every_old_default_runtime_serialization_hash_and_identity_survives(name):
    policy = legacy_cases()[name]
    assert policy.headroom_strategy == DEFAULT
    assert "headroom_strategy" not in policy.to_dict()
    assert hashlib.sha256(policy.to_json().encode()).hexdigest() == FROZEN_RUNTIME_HASHES[name]
    assert policy.policy_id == "runtime-policy-v1:" + FROZEN_RUNTIME_HASHES[name]
    assert decode_policy(policy.to_json()) == policy
    assert RuntimePolicy.from_dict(policy.to_dict()) == policy
    assert replace(policy, headroom_strategy=DEFAULT).to_json() == policy.to_json()
    explicit_default = {**policy.to_dict(), "headroom_strategy": DEFAULT}
    assert RuntimePolicy.from_dict(explicit_default).to_dict() == policy.to_dict()


def test_frozen_default_wire_and_true_off_admission_are_unchanged():
    assert RuntimePolicy().to_json() == FROZEN_DEFAULT_JSON
    assert RuntimePolicy.from_json(FROZEN_DEFAULT_JSON).to_dict() == json.loads(FROZEN_DEFAULT_JSON)
    assert baseline_policy_admissible(RuntimePolicy())
    assert not hasattr(RuntimePolicy(), "enabled")


def test_document_mode_is_explicit_immutable_and_identity_bound():
    policy = documents()
    baseline = replace(policy, headroom_strategy=DEFAULT)
    assert policy.to_dict() == {**baseline.to_dict(), "headroom_strategy": DOCUMENTS}
    assert policy.policy_id != baseline.policy_id
    assert RuntimePolicy.from_json(policy.to_json()) == decode_policy(policy.to_json()) == policy
    detached = policy.to_dict()
    detached["headroom_strategy"] = DEFAULT
    assert policy.headroom_strategy == DOCUMENTS
    with pytest.raises(FrozenInstanceError):
        setattr(policy, "headroom_strategy", DEFAULT)


@pytest.mark.parametrize("strategy", ["", "native-documents", "future", "module:strategy", None, False, 1, {}, []])
def test_invalid_strategies_are_rejected(strategy):
    with pytest.raises(ValueError):
        documents(headroom_strategy=strategy)


@pytest.mark.parametrize("settings", [
    {"backend": "none"},
    {"backend": "none", "instruction": "ponytail"},
    {"backend": "local", "request_policy": RequestPolicy(version="request-policy-v3", enabled=True)},
    {"require_nonexpanding_input": False},
])
def test_documents_require_active_headroom_and_whole_wire_guard(settings):
    with pytest.raises(ValueError):
        documents(**settings)


def test_forged_inactive_mode_is_revalidated_by_serialization_neighbors_and_resources():
    policy = RuntimePolicy()
    object.__setattr__(policy, "headroom_strategy", DOCUMENTS)
    assert not baseline_policy_admissible(policy)
    for operation in (policy.to_dict, lambda: controller_policy_neighbors(policy),
                      lambda: resources.RuntimeResources().resolve(policy)):
        with pytest.raises(ValueError):
            operation()


@pytest.mark.parametrize("version", FROZEN_REQUEST_HASHES)
def test_legacy_request_serialization_identity_and_neighbor_order_remain_frozen(version):
    policy = RequestPolicy(version=version, enabled=True)
    identity, sequence = FROZEN_REQUEST_HASHES[version]
    assert policy.policy_id == version + ":" + identity
    assert decode_policy(policy.to_json()) == policy
    assert controller_policy_neighbors(policy) == policy_neighbors(policy)
    assert sequence_hash(controller_policy_neighbors(policy)) == sequence
    assert controller_policy_sort_key(policy) == (
        policy.min_tool_chars, policy.keep_recent_tool_results, -policy.max_transforms, policy.policy_id)


@pytest.mark.parametrize("version", FROZEN_LOCAL_NEIGHBORS)
def test_default_local_runtime_neighbor_order_is_unchanged(version):
    policy = RuntimePolicy(
        backend="local", request_policy=RequestPolicy(version=version, enabled=True),
        require_nonexpanding_input=version == "request-policy-v4")
    assert sequence_hash(controller_policy_neighbors(policy)) == FROZEN_LOCAL_NEIGHBORS[version]


def test_true_off_reaches_both_guarded_document_styles_without_removing_old_choices():
    neighbors = controller_policy_neighbors(RuntimePolicy())
    modes = [p for p in neighbors if p.headroom_strategy == DOCUMENTS]
    assert set(modes) == {documents(), replace(documents(), headroom_root_reference_style="compact-root-v1")}
    old_ids = [p.policy_id for p in neighbors if p.headroom_strategy == DEFAULT]
    assert old_ids == [
        "runtime-policy-v1:0d9b509c8c71f63f9d61a844b1390e492f1a2443b03bf2cd952199655c5060f9",
        "runtime-policy-v1:ac0b4fd80d6b2f5426fc128cf4bbf1b89046d967fc01df802a49dc65bfa42ce1",
        "runtime-policy-v1:a3b2d79486c692059b9f24ca723f7fd67275bf5c848b360140759a7623990833",
        "runtime-policy-v1:e47f2e8461bea75a1934b6975184943b02bb1206263995dabe7e33caa0011e9d",
    ]
    assert len(neighbors) == 6


@pytest.mark.parametrize("guard", [False, True])
def test_headroom_has_one_explicit_mode_move_with_only_required_derived_guard(guard):
    policy = RuntimePolicy(backend="headroom", require_nonexpanding_input=guard, headroom_time_budget_seconds=9)
    mode_moves = [p for p in controller_policy_neighbors(policy) if p.headroom_strategy != DEFAULT]
    assert mode_moves == [replace(policy, headroom_strategy=DOCUMENTS, require_nonexpanding_input=True)]
    reverse = [p for p in controller_policy_neighbors(mode_moves[0])
               if p.backend == "headroom" and p.headroom_strategy == DEFAULT]
    assert reverse == [replace(mode_moves[0], headroom_strategy=DEFAULT)]


@pytest.mark.parametrize("budget", [None, 1, 30, 60])
@pytest.mark.parametrize("instruction", ["none", "ponytail"])
def test_document_neighbors_are_bounded_closed_single_moves_with_frozen_pins_and_caps(budget, instruction):
    policy = documents(instruction=instruction, headroom_time_budget_seconds=budget,
                       request_policy=RequestPolicy(
                           version="request-policy-v3", max_input_tokens=9000, max_wire_bytes=12000,
                           max_output_tokens=123, min_tool_chars=512, keep_recent_tool_results=3))
    neighbors = controller_policy_neighbors(policy)
    assert neighbors == controller_policy_neighbors(policy)
    assert neighbors == tuple(sorted(neighbors, key=controller_policy_sort_key))
    assert len({p.policy_id for p in neighbors}) == len(neighbors)
    assert 0 < len(neighbors) <= MAX_CONTROLLER_NEIGHBORS <= 12
    assert policy.policy_id not in {p.policy_id for p in neighbors}
    tunable = {"backend", "request_policy", "instruction", "require_nonexpanding_input",
               "headroom_time_budget_seconds", "headroom_strategy", "headroom_root_reference_style"}
    for neighbor in neighbors:
        neighbor.__post_init__()
        for descriptor in fields(policy):
            if descriptor.name not in tunable:
                assert getattr(policy, descriptor.name) == getattr(neighbor, descriptor.name)
        for key in ("max_input_tokens", "max_wire_bytes", "max_output_tokens", "protected_roles",
                    "quality_gate", "recovery_required", "measurement_protocol"):
            assert getattr(policy.request_policy, key) == getattr(neighbor.request_policy, key)
        if neighbor.backend != "headroom":
            assert neighbor.headroom_strategy == DEFAULT
            assert neighbor.headroom_time_budget_seconds is None
        elif neighbor.headroom_strategy == DOCUMENTS:
            assert neighbor.require_nonexpanding_input is True
        changed = {k for k, v in asdict(policy).items() if v != asdict(neighbor)[k]}
        if neighbor.backend != policy.backend:
            assert changed <= {"backend", "request_policy", "require_nonexpanding_input",
                               "headroom_time_budget_seconds", "headroom_strategy", "headroom_root_reference_style"}
        else:
            assert len(changed) == 1


@pytest.fixture
def bound_resources(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    pins, entries = {}, []
    for (repo, name), (revision, _, _) in resources._ASSETS.items():
        data = ("synthetic-" + name).encode()
        digest = hashlib.sha256(data).hexdigest()
        relative = f"hub/models--{repo.replace('/', '--')}/snapshots/{revision}/{name}"
        path = cache / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        pins[(repo, name)] = (revision, len(data), digest)
        entries.append({"repo_id": repo, "revision": revision, "file": name, "cache_path": relative,
                        "bytes": len(data), "sha256": digest, "published_digest_verified": True})
    monkeypatch.setattr(resources, "_ASSETS", pins)
    ref = cache / "hub/models--answerdotai--ModernBERT-base/refs/main"
    ref.parent.mkdir(parents=True)
    ref.write_bytes(resources.TOKENIZER_REVISION.encode("ascii"))
    receipt = tmp_path / "assets.json"
    receipt.write_text(json.dumps({"complete": True, "verified_files": entries}), encoding="utf-8")
    return resources.RuntimeResources(headroom_cache=cache, headroom_assets=receipt), cache, receipt


@pytest.mark.parametrize("budget", [None, 7])
def test_resolution_adds_strategy_only_for_explicit_mode_without_changing_resource_identity(bound_resources, budget):
    value, cache, receipt = bound_resources
    baseline = RuntimePolicy(backend="headroom", require_nonexpanding_input=True,
                             headroom_time_budget_seconds=budget)
    policy = replace(baseline, headroom_strategy=DOCUMENTS)
    before = value.to_manifest()
    files_before = {p: p.read_bytes() for p in cache.rglob("*") if p.is_file()}
    receipt_before = receipt.read_bytes()
    expected = {"cache": cache.resolve(), "assets": receipt.resolve(), "docker_config": None}
    if budget is not None:
        expected["time_budget_seconds"] = budget
    assert value.resolve(baseline) == {"ponytail": None, "headroom_options": expected}
    value.validate(policy)
    actual = value.resolve(policy)
    assert actual == {"ponytail": None, "headroom_options": {**expected, "strategy": DOCUMENTS}}
    actual["headroom_options"]["strategy"] = "caller mutation"
    assert value.resolve(policy)["headroom_options"]["strategy"] == DOCUMENTS
    assert value.to_manifest() == before
    assert receipt.read_bytes() == receipt_before
    assert files_before == {p: p.read_bytes() for p in cache.rglob("*") if p.is_file()}


def test_document_mode_still_requires_verified_headroom_assets():
    value = resources.RuntimeResources()
    policy = documents()
    for operation in (value.validate, value.resolve):
        with pytest.raises(ValueError):
            operation(policy)
