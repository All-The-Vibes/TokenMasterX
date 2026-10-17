"""Explicit, read-only resource binding; no discovery, downloads or warmup.

Construct once, validate() before each pair, resolve() for runtime kwargs.
resolve checks receipts, roots, link targets and file metadata, but does not hash
the large model again. The checked worker independently hashes its mounted
assets. Filesystem checks are not atomic protection against a concurrent writer;
the caller must keep these resources read-only throughout a pair.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
from typing import TYPE_CHECKING, Any

from .headroom_worker import COMMIT, MODEL_REVISION, MODEL_SHA256, TOKENIZER_REVISION
from .ponytail import PonytailInstructions, load_ponytail_export
from .runtime_io import parse_json, safe_root

if TYPE_CHECKING:
    from .runtime_policy import RuntimePolicy


_VERSION = "runtime-resources-v1"
_MODEL = "chopratejas/kompress-v2-base"
_TOKENIZER = "answerdotai/ModernBERT-base"
# Exact published artifacts in the existing validated readiness receipt.
# Revision/model pins are the production worker's pins, not eval imports.
_ASSETS = {
    (_MODEL, "onnx/kompress-int8-wo.onnx"): (MODEL_REVISION, 274049435, MODEL_SHA256),
    (_TOKENIZER, "config.json"): (
        TOKENIZER_REVISION, 1193, "1609d59e627c33eaed524b4f01e546d42e84190a079a5a5ded84b212c41c324f"),
    (_TOKENIZER, "special_tokens_map.json"): (
        TOKENIZER_REVISION, 694, "ea97ecdbcc73713039d8d64dbb05e3689495c96657fbd9a18f5bed381be81049"),
    (_TOKENIZER, "tokenizer.json"): (
        TOKENIZER_REVISION, 2132967, "9fd55248d51d33976b324fc11592e28071da7d41e0e9401dfb7082e30574b7b1"),
    (_TOKENIZER, "tokenizer_config.json"): (
        TOKENIZER_REVISION, 20810, "3cd2017ff46d0a527e5d39cae39272eccfa1f19bb9f89b05d166aab2e38354e2"),
}
_ITEM_KEYS = {"repo_id", "revision", "file", "cache_path", "bytes", "sha256", "published_digest_verified"}
_RECEIPT_KEYS = {
    "complete", "verified_files", "started_at_utc", "completed_at_utc", "huggingface_hub",
    "credentials_supplied", "primary_provider_or_jev_calls", "local_model_inference",
}


def _require(value: bool, reason: str) -> None:
    if not value:
        raise ValueError(reason)


def _wire(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _root(value: Any) -> Path | None:
    if value is None:
        return None
    path = Path(value).absolute()
    _require(".." not in path.parts, "resource_root_traversal")
    return safe_root(path)


def _fingerprint(path: Path) -> tuple:
    info = path.stat()
    _require(stat.S_ISREG(info.st_mode), "resource_not_regular_file")
    return (str(path), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_file(cache: Path, relative: str) -> Path:
    """Follow only relative symlinks, checking every hop inside the cache."""
    path = PurePosixPath(relative)
    _require(bool(relative) and not path.is_absolute() and "\\" not in relative
             and not PureWindowsPath(relative).drive
             and all(part not in ("", ".", "..") for part in relative.split("/")),
             "invalid_asset_path")
    pending, current, links = list(path.parts), cache, 0
    while pending:
        part = pending.pop(0)
        if part == ".":
            continue
        if part == "..":
            current = current.parent
            _require(current.is_relative_to(cache), "asset_link_escape")
            continue
        item = current / part
        _require(not item.is_junction(), "asset_junction")
        if item.is_symlink():
            links += 1
            _require(links <= 40, "asset_link_cycle")
            target = os.readlink(item)
            _require(not Path(target).is_absolute() and not PureWindowsPath(target).drive,
                     "absolute_asset_link")
            pending = list(Path(target).parts) + pending
        else:
            current = item
    _require(current.resolve(strict=True) == current and current.is_relative_to(cache),
             "asset_link_escape")
    _fingerprint(current)
    return current


def _policy_requirements(policy: RuntimePolicy) -> tuple[bool, bool, int | None]:
    # Closed dispatch. No arbitrary policy object, plugin or dynamic import path.
    from .runtime_policy import RuntimePolicy
    _require(type(policy) is RuntimePolicy, "runtime_policy_required")
    policy.__post_init__()
    return policy.instruction == "ponytail", policy.backend == "headroom", policy.headroom_time_budget_seconds


@dataclass(frozen=True, slots=True, init=False)
class RuntimeResources:
    """Validated immutable content identity with private machine-local paths."""
    _ponytail_export: Path | None = field(repr=False)
    _headroom_cache: Path | None = field(repr=False)
    _headroom_assets: Path | None = field(repr=False)
    _manifest: str = field(repr=False)
    _files: tuple = field(repr=False)
    _identity: str

    def __init__(self, *, ponytail_export=None, headroom_cache=None, headroom_assets=None):
        try:
            _require((headroom_cache is None) == (headroom_assets is None), "headroom_resource_pair_required")
            for name, value in (("_ponytail_export", ponytail_export),
                                ("_headroom_cache", headroom_cache), ("_headroom_assets", headroom_assets)):
                object.__setattr__(self, name, _root(value))
            manifest, files, _ = self._scan(full_hash=True)
        except OSError:
            raise OSError("runtime_resource_unavailable") from None
        except (ValueError, TypeError, RecursionError):
            raise ValueError("invalid_runtime_resources") from None
        encoded = _wire(manifest)
        object.__setattr__(self, "_manifest", encoded)
        object.__setattr__(self, "_files", files)
        object.__setattr__(self, "_identity", _VERSION + ":" + hashlib.sha256(encoded.encode()).hexdigest())

    @property
    def identity(self) -> str:
        return self._identity

    def to_manifest(self) -> dict[str, Any]:
        """Detached portable data only; no paths, instruction text or secrets."""
        return {"identity": self.identity, **json.loads(self._manifest)}

    def _scan(self, *, full_hash: bool) -> tuple[dict[str, Any], tuple, PonytailInstructions | None]:
        files: list[tuple] = []
        manifest: dict[str, Any] = {"version": _VERSION, "ponytail": None, "headroom": None}
        ponytail = None
        if self._ponytail_export is not None:
            path = _root(self._ponytail_export)
            assert path is not None
            before = _fingerprint(path)
            ponytail = load_ponytail_export(path)
            # Small export is rehashed even on resolve; never an arbitrary loader.
            export_hash = _digest_file(path)
            _require(before == _fingerprint(path), "resource_changed_during_validation")
            files.append((before, export_hash))
            manifest["ponytail"] = {
                "component_id": ponytail.identity, "source_commit": ponytail.source_commit,
                "instructions_sha256": ponytail.instructions_sha256, "mode": ponytail.mode,
            }
        if self._headroom_cache is not None:
            cache, receipt_path = _root(self._headroom_cache), _root(self._headroom_assets)
            assert cache is not None and receipt_path is not None
            _require(cache.is_dir(), "headroom_cache_unavailable")
            root_stat = cache.stat()
            files.append(("cache_root", str(cache), root_stat.st_dev, root_stat.st_ino))
            before = _fingerprint(receipt_path)
            with receipt_path.open("rb") as stream:
                raw = stream.read(65537)
            _require(len(raw) <= 65536, "asset_receipt_too_large")
            receipt = parse_json(raw.decode("utf-8"))
            # Validate even ignored metadata for escaped surrogates/nonfinite values.
            json.dumps(receipt, ensure_ascii=False, allow_nan=False).encode("utf-8")
            _require(type(receipt) is dict and set(receipt) <= _RECEIPT_KEYS
                     and receipt.get("complete") is True
                     and type(receipt.get("verified_files")) is list,
                     "invalid_asset_receipt")
            for key, expected in (("credentials_supplied", False), ("local_model_inference", False)):
                if key in receipt:
                    _require(receipt[key] is expected, "invalid_asset_provenance")
            if "primary_provider_or_jev_calls" in receipt:
                _require(type(receipt["primary_provider_or_jev_calls"]) is int
                         and receipt["primary_provider_or_jev_calls"] == 0, "invalid_asset_provenance")
            for key in ("started_at_utc", "completed_at_utc", "huggingface_hub"):
                if key in receipt:
                    _require(type(receipt[key]) is str and bool(receipt[key]), "invalid_asset_provenance")
            receipt_hash = hashlib.sha256(raw).hexdigest()
            _require(before == _fingerprint(receipt_path), "resource_changed_during_validation")
            files.append((before, receipt_hash))
            entries = []
            seen: set[tuple[str, str]] = set()
            for item in receipt["verified_files"]:
                _require(type(item) is dict and set(item) == _ITEM_KEYS, "invalid_asset_entry")
                _require(all(type(item[key]) is str for key in
                             ("repo_id", "revision", "file", "cache_path", "sha256")), "invalid_asset_entry")
                asset_key = item["repo_id"], item["file"]
                _require(asset_key in _ASSETS and asset_key not in seen, "unexpected_or_duplicate_asset")
                seen.add(asset_key)
                revision, size, digest = _ASSETS[asset_key]
                expected_path = (
                    f"hub/models--{asset_key[0].replace('/', '--')}/snapshots/{revision}/{asset_key[1]}")
                _require(item["revision"] == revision and item["cache_path"] == expected_path
                         and type(item["bytes"]) is int and item["bytes"] == size
                         and item["sha256"] == digest and item["published_digest_verified"] is True,
                         "asset_pin_mismatch")
                target = _cache_file(cache, expected_path)
                stamp = _fingerprint(target)
                _require(stamp[3] == size, "asset_size_mismatch")
                if full_hash:
                    _require(_digest_file(target) == digest, "asset_digest_mismatch")
                _require(stamp == _fingerprint(target) and target == _cache_file(cache, expected_path),
                         "resource_changed_during_validation")
                files.append((stamp, expected_path))
                entries.append(dict(item))
            _require(seen == set(_ASSETS), "asset_inventory_incomplete")
            ref_path = "hub/models--answerdotai--ModernBERT-base/refs/main"
            target = _cache_file(cache, ref_path)
            stamp = _fingerprint(target)
            _require(target.read_bytes() == TOKENIZER_REVISION.encode("ascii")
                     and stamp == _fingerprint(target), "tokenizer_ref_mismatch")
            files.append((stamp, ref_path))
            manifest["headroom"] = {
                "source_commit": COMMIT, "asset_receipt_sha256": receipt_hash,
                "verified_files": sorted(entries, key=lambda item: (item["repo_id"], item["file"])),
                "tokenizer_ref": {"cache_path": ref_path, "revision": TOKENIZER_REVISION},
            }
        manifest["available_components"] = [
            key for key in ("ponytail", "headroom") if manifest[key] is not None]
        return manifest, tuple(files), ponytail

    def _check(self, policy: RuntimePolicy | None, *, full_hash: bool):
        try:
            if policy is not None:
                wants_pony, wants_headroom, _ = _policy_requirements(policy)
                _require(not wants_pony or self._ponytail_export is not None, "missing_ponytail_resource")
                _require(not wants_headroom or self._headroom_cache is not None, "missing_headroom_resource")
            manifest, files, ponytail = self._scan(full_hash=full_hash)
            _require(_wire(manifest) == self._manifest and files == self._files, "runtime_resource_drift")
            return ponytail
        except OSError:
            raise OSError("runtime_resource_unavailable") from None
        except (ValueError, TypeError, RecursionError):
            raise ValueError("invalid_or_changed_runtime_resources") from None

    def validate(self, policy: RuntimePolicy | None = None) -> None:
        """Rehash configured resources before a pair; no writes or component start."""
        self._check(policy, full_hash=True)

    def resolve(self, policy: RuntimePolicy) -> dict[str, Any]:
        """Only execution resources, never reducer settings or policy paths."""
        ponytail = self._check(policy, full_hash=False)
        wants_pony, wants_headroom, budget = _policy_requirements(policy)
        options: dict[str, Any] | None = None
        if wants_headroom:
            options = {"cache": self._headroom_cache, "assets": self._headroom_assets, "docker_config": None}
            if budget is not None:
                options["time_budget_seconds"] = budget
            if policy.headroom_strategy != "upstream-default-v1":
                options["strategy"] = policy.headroom_strategy
        return {"ponytail": ponytail if wants_pony else None, "headroom_options": options}
