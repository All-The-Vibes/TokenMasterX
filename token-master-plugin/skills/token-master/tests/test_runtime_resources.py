"""Resource binding only: tiny synthetic pinned assets, no neural/host startup."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
import os
from types import SimpleNamespace
from typing import Any

import pytest

from brainspace import ponytail, runtime_policy, runtime_resources as resources
from brainspace.request_policy import RequestPolicy
from brainspace.runtime_policy import RuntimePolicy


@pytest.fixture
def asset_set(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    pins, entries = {}, []
    for (repo, name), (revision, _, _) in resources._ASSETS.items():
        content = ("synthetic asset " + name).encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        relative = f"hub/models--{repo.replace('/', '--')}/snapshots/{revision}/{name}"
        path = cache / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        pins[(repo, name)] = (revision, len(content), digest)
        entries.append(dict(repo_id=repo, revision=revision, file=name, cache_path=relative,
                            bytes=len(content), sha256=digest, published_digest_verified=True))
    monkeypatch.setattr(resources, "_ASSETS", pins)
    ref = cache / "hub/models--answerdotai--ModernBERT-base/refs/main"
    ref.parent.mkdir(parents=True)
    ref.write_bytes(resources.TOKENIZER_REVISION.encode("ascii"))
    data = dict(complete=True, verified_files=entries, credentials_supplied=False,
                primary_provider_or_jev_calls=0, local_model_inference=False,
                huggingface_hub="synthetic", started_at_utc="fixture", completed_at_utc="fixture")
    manifest = tmp_path / "assets.json"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    return SimpleNamespace(cache=cache, manifest=manifest, data=data, ref=ref)


@pytest.fixture
def export(tmp_path, monkeypatch):
    text = "Synthetic pinned Ponytail instructions.\n"
    digest = hashlib.sha256(text.encode()).hexdigest()
    for module in (ponytail, runtime_policy):
        monkeypatch.setattr(module, "PINNED_INSTRUCTIONS_SHA256", digest)
    path = tmp_path / "ponytail.json"
    path.write_text(json.dumps(dict(
        instructions=text, instructions_sha256=digest,
        source_commit=ponytail.PINNED_SOURCE_COMMIT, mode="full", fallback_used=False)), encoding="utf-8")
    return path


def policy(**kwargs):
    # Explicit runtime pins preserve constructor defaults when tests patch only
    # the synthetic instruction digest, never production model/source values.
    return RuntimePolicy(ponytail_instructions_sha256=ponytail.PINNED_INSTRUCTIONS_SHA256, **kwargs)


def bound(asset_set, **kwargs):
    return resources.RuntimeResources(
        headroom_cache=asset_set.cache, headroom_assets=asset_set.manifest, **kwargs)


def test_empty_off_local_and_closed_dispatch():
    value = resources.RuntimeResources()
    assert value.identity.startswith("runtime-resources-v1:")
    assert value.to_manifest()["available_components"] == []
    value.validate()
    for candidate in (RuntimePolicy(), RuntimePolicy(
            backend="local", request_policy=RequestPolicy(version="request-policy-v3", enabled=True))):
        assert value.resolve(candidate) == {"ponytail": None, "headroom_options": None}
    impostors: list[Any] = [{}, SimpleNamespace(backend="none", instruction="none"), RequestPolicy()]
    for impostor in impostors:
        with pytest.raises(ValueError):
            value.resolve(impostor)
    class Subclass(RuntimePolicy):
        pass
    with pytest.raises(ValueError):
        value.validate(Subclass())


def test_full_resolution_manifest_identity_and_immutability(asset_set, export):
    before = {p: p.read_bytes() for p in export.parent.rglob("*") if p.is_file()}
    value = bound(asset_set, ponytail_export=export)
    manifest = value.to_manifest()
    assert manifest["available_components"] == ["ponytail", "headroom"]
    encoded = json.dumps(manifest)
    assert str(export.parent) not in encoded and "Synthetic pinned" not in encoded
    candidate = policy(backend="headroom", instruction="ponytail", headroom_time_budget_seconds=60)
    value.validate(candidate)
    resolved = value.resolve(candidate)
    assert set(resolved) == {"ponytail", "headroom_options"}
    assert type(resolved["ponytail"]) is ponytail.PonytailInstructions
    assert resolved["headroom_options"] == {
        "cache": asset_set.cache.resolve(), "assets": asset_set.manifest.resolve(),
        "docker_config": None, "time_budget_seconds": 60}
    assert "time_budget_seconds" not in value.resolve(policy(backend="headroom"))["headroom_options"]
    assert value.resolve(policy()) == {"ponytail": None, "headroom_options": None}
    manifest["headroom"]["verified_files"].clear()
    assert len(value.to_manifest()["headroom"]["verified_files"]) == 5
    with pytest.raises(FrozenInstanceError):
        value._identity = "changed"
    assert not hasattr(value, "__dict__")
    assert str(export.parent) not in repr(value)
    assert before == {p: p.read_bytes() for p in export.parent.rglob("*") if p.is_file()}


def test_same_content_at_different_machine_paths_has_same_identity(asset_set, tmp_path):
    import shutil
    first = bound(asset_set)
    destination = tmp_path / "copy"
    shutil.copytree(asset_set.cache, destination)
    receipt = tmp_path / "copy.json"
    receipt.write_bytes(asset_set.manifest.read_bytes())
    second = resources.RuntimeResources(headroom_cache=destination, headroom_assets=receipt)
    assert first.identity == second.identity
    assert first.to_manifest() == second.to_manifest()


@pytest.mark.parametrize("selection", [
    {"instruction": "ponytail"}, {"backend": "headroom"},
    {"backend": "headroom", "instruction": "ponytail"},
])
def test_missing_required_resource_fails_before_resolution(selection):
    value = resources.RuntimeResources()
    for operation in (value.validate, value.resolve):
        with pytest.raises(ValueError):
            operation(RuntimePolicy(**selection))


@pytest.mark.parametrize("key", ["headroom_cache", "headroom_assets"])
def test_resource_pair_required(key, tmp_path):
    with pytest.raises(ValueError):
        resources.RuntimeResources(**{key: tmp_path})


@pytest.mark.parametrize("change", [
    "missing", "duplicate", "extra", "wrong_revision", "wrong_model_hash", "wrong_tokenizer_hash",
    "wrong_file", "absolute", "escape", "windows_drive", "backslash", "false_digest_provenance",
    "numeric_provenance", "bool_bytes", "incomplete", "numeric_complete", "estimated",
    "credentials", "calls", "inference", "unsupported_metadata",
])
def test_malicious_or_incomplete_asset_manifest_rejects(asset_set, change):
    data = deepcopy(asset_set.data)
    item = data["verified_files"][0]
    if change == "missing":
        data["verified_files"].pop()
    elif change == "duplicate":
        data["verified_files"].append(deepcopy(item))
    elif change == "extra":
        extra = deepcopy(item)
        extra["repo_id"] = "unsupported/model"
        data["verified_files"].append(extra)
    elif change == "wrong_revision":
        item["revision"] = "0" * 40
    elif change == "wrong_model_hash":
        item["sha256"] = "0" * 64
    elif change == "wrong_tokenizer_hash":
        data["verified_files"][-1]["sha256"] = "0" * 64
    elif change == "wrong_file":
        item["file"] = "onnx/other.onnx"
    elif change in ("absolute", "escape", "windows_drive", "backslash"):
        item["cache_path"] = {
            "absolute": "/etc/passwd", "escape": "../outside",
            "windows_drive": "C:/private", "backslash": "hub\\models",
        }[change]
    elif change == "false_digest_provenance":
        item["published_digest_verified"] = False
    elif change == "numeric_provenance":
        item["published_digest_verified"] = 1
    elif change == "bool_bytes":
        item["bytes"] = True
    elif change == "incomplete":
        data["complete"] = False
    elif change == "numeric_complete":
        data["complete"] = 1
    elif change == "estimated":
        data = {"complete": True, "readiness": "estimated"}
    elif change == "credentials":
        data["credentials_supplied"] = True
    elif change == "calls":
        data["primary_provider_or_jev_calls"] = True
    elif change == "inference":
        data["local_model_inference"] = True
    elif change == "unsupported_metadata":
        data["environment"] = {"HF_TOKEN": "must-not-echo"}
    asset_set.manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError) as error:
        bound(asset_set)
    assert "must-not-echo" not in str(error.value)
    assert str(asset_set.cache) not in str(error.value)


@pytest.mark.parametrize("raw", [
    b"\xff", b'{"complete":true,"complete":false}',
    b'{"complete":true,"verified_files":[],"huggingface_hub":NaN}',
    b'{"complete":true,"verified_files":[],"huggingface_hub":"\\ud800"}',
    b" " * 65537,
], ids=["invalid-utf8", "duplicate", "nonfinite", "surrogate", "oversized"])
def test_invalid_utf8_duplicate_nonfinite_and_large_receipts(asset_set, raw):
    asset_set.manifest.write_bytes(raw)
    with pytest.raises(ValueError):
        bound(asset_set)


@pytest.mark.parametrize("target", ["asset", "receipt", "ref", "root"])
def test_detects_content_and_root_drift(asset_set, target):
    value = bound(asset_set)
    if target == "asset":
        path = asset_set.cache / asset_set.data["verified_files"][0]["cache_path"]
        path.write_bytes(b"corrupt")
    elif target == "receipt":
        asset_set.manifest.write_text("{}", encoding="utf-8")
    elif target == "ref":
        asset_set.ref.write_text("wrong", encoding="utf-8")
    else:
        asset_set.cache.rename(asset_set.cache.with_name("original-cache"))
        asset_set.cache.mkdir()
    for operation in (value.validate, lambda: value.resolve(RuntimePolicy(backend="headroom"))):
        with pytest.raises((ValueError, OSError)):
            operation()


def link_or_skip(link, target, *, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as error:
        pytest.skip("symlink creation unavailable: " + type(error).__name__)


def test_internal_relative_cache_link_accepted_and_retarget_detected(asset_set):
    path = asset_set.cache / asset_set.data["verified_files"][0]["cache_path"]
    blob = asset_set.cache / "blob"
    path.replace(blob)
    link_or_skip(path, os.path.relpath(blob, path.parent))
    value = bound(asset_set)
    value.validate()
    other = asset_set.cache / "other-blob"
    other.write_bytes(blob.read_bytes())
    path.unlink()
    link_or_skip(path, os.path.relpath(other, path.parent))
    with pytest.raises(ValueError):
        value.resolve(RuntimePolicy(backend="headroom"))


@pytest.mark.parametrize("kind", ["outside", "absolute_inside", "cycle", "linked_root", "traversal"])
def test_links_and_traversal_fail_closed(asset_set, tmp_path, kind):
    if kind == "traversal":
        with pytest.raises(ValueError):
            resources.RuntimeResources(headroom_cache=asset_set.cache / ".." / "cache",
                                       headroom_assets=asset_set.manifest)
        return
    if kind == "linked_root":
        link = tmp_path / "linked-cache"
        link_or_skip(link, "cache", directory=True)
        with pytest.raises(ValueError):
            resources.RuntimeResources(headroom_cache=link, headroom_assets=asset_set.manifest)
        return
    path = asset_set.cache / asset_set.data["verified_files"][0]["cache_path"]
    content = path.read_bytes()
    path.unlink()
    if kind == "outside":
        destination = tmp_path / "outside-model"
        destination.write_bytes(content)
        target = os.path.relpath(destination, path.parent)
    elif kind == "absolute_inside":
        destination = asset_set.cache / "blob"
        destination.write_bytes(content)
        target = str(destination)
    else:
        target = path.name
    link_or_skip(path, target)
    with pytest.raises(ValueError):
        bound(asset_set)


def test_explicit_validate_rehashes_but_resolve_skips_large_assets(asset_set, monkeypatch):
    value = bound(asset_set)
    original = resources._digest_file
    calls = []
    def counted(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(resources, "_digest_file", counted)
    value.resolve(RuntimePolicy(backend="headroom"))
    assert calls == []
    value.validate()
    assert len(calls) == 5


def test_same_size_corruption_is_not_readiness(asset_set):
    path = asset_set.cache / asset_set.data["verified_files"][0]["cache_path"]
    path.write_bytes(b"x" * path.stat().st_size)
    with pytest.raises(ValueError):
        bound(asset_set)


def test_receipt_bytes_bound_to_identity_and_drift(asset_set):
    value = bound(asset_set)
    asset_set.manifest.write_text(json.dumps(asset_set.data, indent=2), encoding="utf-8")
    with pytest.raises(ValueError):
        value.validate()
    assert bound(asset_set).identity != value.identity


def test_real_ponytail_loader_and_drift(export):
    value = resources.RuntimeResources(ponytail_export=export)
    selected = policy(instruction="ponytail")
    assert value.resolve(selected)["ponytail"] == ponytail.load_ponytail_export(export)
    data = json.loads(export.read_text(encoding="utf-8"))
    data["fallback_used"] = True
    export.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        value.validate(selected)


def test_missing_file_has_content_free_oserror(tmp_path):
    with pytest.raises(OSError) as error:
        resources.RuntimeResources(ponytail_export=tmp_path / "secret-name")
    assert str(error.value) == "runtime_resource_unavailable"
