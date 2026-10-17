"""Synthetic product-boundary tests: no upstream text or workstation evidence."""
import ast
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path

import pytest

from brainspace import ponytail


@pytest.fixture
def pinned(monkeypatch):
    text = "\nSynthetic instruction fixture only.\r\nPreserve π, spaces  and newlines.\n"
    commit = "a" * 40
    checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
    monkeypatch.setattr(ponytail, "PINNED_SOURCE_COMMIT", commit)
    monkeypatch.setattr(ponytail, "PINNED_INSTRUCTIONS_SHA256", checksum)
    return {
        "instructions": text, "source_commit": commit,
        "instructions_sha256": checksum, "mode": "full", "fallback_used": False,
    }


def saved(tmp_path, data):
    path = tmp_path / "synthetic-export.json"
    raw = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode("utf-8")
    path.write_bytes(raw)
    return path


def component(pinned, **changes):
    fields = dict(text=pinned["instructions"], source_commit=pinned["source_commit"],
                  instructions_sha256=pinned["instructions_sha256"])
    return ponytail.PonytailInstructions(**(fields | changes))


def test_load_preserves_exact_text_and_does_not_modify_export(tmp_path, pinned):
    path = saved(tmp_path, pinned)
    before = path.read_bytes()
    result = ponytail.load_ponytail_export(path)
    assert result == component(pinned)
    assert result.text == pinned["instructions"]
    assert "\r\n" in result.text and result.text.startswith("\n")
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == [path.name]


def test_frozen_component_identity_and_detached_representation(pinned):
    result = component(pinned)
    expected = {
        "text": pinned["instructions"], "source_commit": pinned["source_commit"],
        "instructions_sha256": pinned["instructions_sha256"], "mode": "full",
    }
    assert result.to_dict() == expected
    encoded = json.dumps(expected, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("utf-8")
    assert result.identity == hashlib.sha256(b"ponytail-instructions-v1\0" + encoded).hexdigest()
    assert result.identity == component(pinned).identity
    assert ponytail.PonytailInstructions(**result.to_dict()) == result
    assert len(result.identity) == 64
    assert hash(result) == hash(component(pinned))
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        result.text = "replacement"
    detached = result.to_dict()
    detached["text"] = "replacement"
    assert result.to_dict() == expected
    assert pinned["instructions"] not in repr(result)


@pytest.mark.parametrize("changes", [
    {"text": ""}, {"text": " \t\r\n"}, {"text": None}, {"text": b"not text"},
    {"text": True}, {"text": ["not text"]}, {"text": "\ud800"},
    {"source_commit": "b" * 40}, {"source_commit": None}, {"source_commit": False},
    {"instructions_sha256": "0" * 64}, {"instructions_sha256": None},
    {"instructions_sha256": 0}, {"mode": "lite"}, {"mode": "ultra"},
    {"mode": "FULL"}, {"mode": " full"}, {"mode": None}, {"mode": False},
])
def test_direct_construction_enforces_product_pins(pinned, changes):
    with pytest.raises(ValueError):
        component(pinned, **changes)


def test_no_normalization_or_correct_digest_for_unpinned_content(pinned):
    for changed in (pinned["instructions"].strip(),
                    pinned["instructions"].replace("\r\n", "\n"),
                    pinned["instructions"] + "extra",
                    pinned["instructions"].replace("π", "p")):
        with pytest.raises(ValueError):
            component(pinned, text=changed)
        with pytest.raises(ValueError):
            component(pinned, text=changed,
                      instructions_sha256=hashlib.sha256(changed.encode("utf-8")).hexdigest())
    with pytest.raises(ValueError):
        replace(component(pinned), mode="lite")


def test_component_identity_binds_commit_and_text(monkeypatch, pinned):
    first = component(pinned)
    first_identity = first.identity
    second_commit = "b" * 40
    monkeypatch.setattr(ponytail, "PINNED_SOURCE_COMMIT", second_commit)
    second = component(pinned, source_commit=second_commit)
    assert second.identity != first.identity
    new_text = pinned["instructions"] + "Additional synthetic fixture."
    new_hash = hashlib.sha256(new_text.encode("utf-8")).hexdigest()
    monkeypatch.setattr(ponytail, "PINNED_INSTRUCTIONS_SHA256", new_hash)
    third = component(pinned, source_commit=second_commit,
                      text=new_text, instructions_sha256=new_hash)
    assert third.identity != second.identity
    # Identity belongs to the immutable value, not subsequently changed pins.
    assert first.identity == first_identity


@pytest.mark.parametrize("field", [
    "instructions", "source_commit", "instructions_sha256", "mode", "fallback_used",
])
def test_required_export_fields_are_not_defaulted(tmp_path, pinned, field):
    data = dict(pinned)
    del data[field]
    with pytest.raises(ValueError):
        ponytail.load_ponytail_export(saved(tmp_path, data))


@pytest.mark.parametrize("fallback", [True, None, 0, 1, "", "false", [], {}])
def test_only_literal_false_fallback_is_accepted(tmp_path, pinned, fallback):
    with pytest.raises(ValueError):
        ponytail.load_ponytail_export(saved(tmp_path, pinned | {"fallback_used": fallback}))


@pytest.mark.parametrize("changes", [
    {"mode": "lite"}, {"mode": None}, {"source_commit": "b" * 40},
    {"source_commit": 0}, {"instructions_sha256": "0" * 64},
    {"instructions": "pretend Ponytail"}, {"instructions": None},
])
def test_loader_cannot_bypass_component_validation(tmp_path, pinned, changes):
    with pytest.raises(ValueError):
        ponytail.load_ponytail_export(saved(tmp_path, pinned | changes))


@pytest.mark.parametrize("raw", [
    b"", b"not JSON", b"null", b"[]", b"true", b'"string"',
    b"{}", b'{"incomplete":', b"{}{}", b"\xff", b"\xef\xbb\xbf{}",
])
def test_malformed_utf8_json_and_nonobject_roots_fail_closed(tmp_path, raw):
    with pytest.raises(ValueError):
        ponytail.load_ponytail_export(saved(tmp_path, raw))


@pytest.mark.parametrize("duplicate", [
    '"fallback_used":true',
    '"instructions":"different"',
    '"source_commit":"different"',
    '"mode":"lite"',
    '"mode":"full"',
    '"mo\\u0064e":"full"',
    '"metadata":{"nested":{"value":1,"value":2}}',
])
def test_duplicate_keys_are_rejected_even_when_last_values_would_validate(tmp_path, pinned, duplicate):
    fields = json.dumps(pinned, ensure_ascii=True)[1:-1]
    raw = ("{" + duplicate + "," + fields + "}").encode("utf-8")
    with pytest.raises(ValueError, match="JSON"):
        ponytail.load_ponytail_export(saved(tmp_path, raw))


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e999", "-1e999"])
def test_nonfinite_values_anywhere_in_metadata_are_rejected(tmp_path, pinned, value):
    fields = json.dumps(pinned, ensure_ascii=True)[1:-1]
    raw = ("{" + fields + ',"metadata":{"nested":[' + value + "]}}").encode("utf-8")
    with pytest.raises(ValueError, match="JSON"):
        ponytail.load_ponytail_export(saved(tmp_path, raw))


def test_escaped_surrogates_fail_closed(tmp_path, pinned):
    fields = json.dumps(pinned, ensure_ascii=True)[1:-1]
    raw = ("{" + fields + ',"metadata":"\\ud800"}').encode("utf-8")
    with pytest.raises(ValueError, match="JSON"):
        ponytail.load_ponytail_export(saved(tmp_path, raw))


def test_parser_recursion_failure_is_normalized_without_assuming_host_recursion_limit(
    tmp_path, pinned, monkeypatch,
):
    path = saved(tmp_path, pinned)

    def recursive(*_, **__):
        raise RecursionError("synthetic parser limit")

    monkeypatch.setattr(ponytail.json, "loads", recursive)
    with pytest.raises(ValueError, match="JSON"):
        ponytail.load_ponytail_export(path)


def test_export_metadata_is_not_component_identity(tmp_path, pinned):
    base = ponytail.load_ponytail_export(saved(tmp_path, pinned))
    metadata = {
        "version": "synthetic", "node": "fixture", "platform": "fixture",
        "scope": "Only synthetic export metadata", "nested": {"numbers": [1, 2.5, None]},
    }
    loaded = ponytail.load_ponytail_export(saved(tmp_path, pinned | metadata))
    assert loaded == base and loaded.identity == base.identity
    assert set(loaded.to_dict()) == {"text", "source_commit", "instructions_sha256", "mode"}


def test_export_byte_limit_including_exact_boundary(tmp_path, pinned, monkeypatch):
    raw = json.dumps(pinned, ensure_ascii=True).encode("utf-8")
    monkeypatch.setattr(ponytail, "MAX_EXPORT_BYTES", len(raw))
    assert ponytail.load_ponytail_export(saved(tmp_path, raw)) == component(pinned)
    with pytest.raises(ValueError, match="size limit"):
        ponytail.load_ponytail_export(saved(tmp_path, raw + b" "))


def test_read_is_explicitly_bounded(tmp_path, pinned, monkeypatch):
    path = saved(tmp_path, pinned)
    original_open = Path.open
    reads = []

    class ObservedFile:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.handle.close()

        def fileno(self):
            return self.handle.fileno()

        def read(self, size):
            reads.append(size)
            return self.handle.read(size)

    def observed_open(target, *args, **kwargs):
        return ObservedFile(original_open(target, *args, **kwargs))

    monkeypatch.setattr(Path, "open", observed_open)
    assert ponytail.load_ponytail_export(path) == component(pinned)
    assert reads == [ponytail.MAX_EXPORT_BYTES + 1]


def test_direct_text_limit_is_utf8_bytes(pinned, monkeypatch):
    monkeypatch.setattr(ponytail, "MAX_EXPORT_BYTES", len(pinned["instructions"]))
    with pytest.raises(ValueError, match="size limit"):
        component(pinned)


def test_missing_file_or_directory_never_falls_back(tmp_path):
    with pytest.raises(FileNotFoundError):
        ponytail.load_ponytail_export(tmp_path / "missing.json")
    with pytest.raises(ValueError, match="regular file"):
        ponytail.load_ponytail_export(tmp_path)


def test_production_loader_has_no_eval_or_network_imports():
    tree = ast.parse(Path(ponytail.__file__).read_text(encoding="utf-8"))
    imports = [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    imports += [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    forbidden = ("evals", "run_parity", "quality", "urllib", "requests", "httpx", "subprocess")
    assert not any(name == root or name.startswith(root + ".") for name in imports for root in forbidden)
