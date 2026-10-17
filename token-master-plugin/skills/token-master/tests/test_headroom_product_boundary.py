"""Product extraction checks; fake IPC/Docker only, never vendor inference."""
import ast
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from brainspace import headroom, headroom_worker, runtime_io


ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT.parents[1] / "evals"
IDENTITY = "a" * 64


def new_worker(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    assets = tmp_path / "assets.json"
    assets.write_text("{}", encoding="utf-8")
    config = tmp_path / "docker-config"
    config.mkdir()
    (config / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(headroom, "shutil", SimpleNamespace(which=lambda _: "fake-docker"))
    return headroom.HeadroomContainer(
        tmp_path / "task", cache=cache, assets=assets, docker_config=config, label="product-test",
    )


def boundary(worker):
    mounts = {
        "/inputs/worker.py": worker.directory / "worker-frozen.py",
        "/inputs/assets.json": worker.assets, "/cache": worker.cache,
    }
    return {
        "Id": IDENTITY, "Image": headroom.IMAGE_ID,
        "Config": {
            "Labels": {"tokenmaster.parity": worker.label}, "User": "65532:65532",
            "Entrypoint": ["python"], "Cmd": ["/inputs/worker.py"], "OpenStdin": True,
            "Volumes": {"/home/nonroot/.headroom": {}},
            "Env": [key + "=" + value for key, value in
                    {**headroom.TASK_ENVIRONMENT, **headroom.PINNED_BASE_ENVIRONMENT}.items()],
        },
        "HostConfig": {
            "NetworkMode": "none", "ReadonlyRootfs": True, "Privileged": False,
            "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges"],
            "NanoCpus": 2_000_000_000, "Memory": 4 * 1024**3, "MemorySwap": 4 * 1024**3,
            "PidsLimit": 256, "Tmpfs": {
                "/tmp": "rw,noexec,nosuid,nodev,size=256m",
                "/home/nonroot/.headroom": "rw,noexec,nosuid,nodev,size=64m",
            },
        },
        "Mounts": [{"Type": "bind", "Destination": target, "Source": str(path), "RW": False}
                   for target, path in mounts.items()],
        "State": {"Running": True, "ExitCode": 0},
    }


class Process:
    def __init__(self):
        self.stdin = io.BytesIO()
        self.returncode = None
        self.terminated = False

    def wait(self, timeout):
        if self.returncode is None:
            raise subprocess.TimeoutExpired("owned fake attach", timeout)
        return self.returncode

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.returncode = -9


def fake_engine(worker, monkeypatch, *, ready_changes=None):
    commands, state, process = [], boundary(worker), Process()

    def command(args, **kwargs):
        commands.append(args)
        if args[:2] == ["image", "inspect"]:
            value = [{"Id": headroom.IMAGE_ID, "Config": {
                "Labels": {"org.opencontainers.image.revision": headroom.COMMIT}}}]
        elif args[0] == "create":
            return SimpleNamespace(returncode=0, stdout=IDENTITY + "\n")
        elif args[0] == "inspect":
            assert args == ["inspect", IDENTITY]
            value = [deepcopy(state)]
        elif args[0] == "stop":
            assert args == ["stop", "--time", "5", IDENTITY]
            state["State"]["Running"] = False
            process.returncode = 0
            value = {}
        elif args[0] == "rm":
            assert args == ["rm", IDENTITY]
            assert not state["State"]["Running"]
            value = {}
        else:
            pytest.fail("unexpected Docker operation: " + repr(args))
        return SimpleNamespace(returncode=0, stdout=json.dumps(value))

    def popen(args, **kwargs):
        assert args[-4:] == ["start", "--attach", "--interactive", IDENTITY]
        assert kwargs["env"] == worker.environment
        ready = dict(id="ready", ok=True, protocol="headroom-task-worker-v1",
                     commit=headroom.COMMIT, model_revision=headroom.MODEL_REVISION,
                     worker_sha256=worker.worker_sha256)
        ready.update(ready_changes or {})
        worker.replies.put(ready)
        return process

    class Thread:
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            # Feed responses explicitly; execute only the bounded stdin write.
            if self.target.__name__ != "_read":
                self.target()

    worker.command = command
    monkeypatch.setattr(headroom, "threading", SimpleNamespace(Thread=Thread))
    monkeypatch.setattr(headroom, "subprocess", SimpleNamespace(
        Popen=popen, PIPE=subprocess.PIPE, TimeoutExpired=subprocess.TimeoutExpired,
    ))
    return commands, state, process


def reply(worker, result):
    worker.replies.put({"id": str(worker.sequence + 1), "ok": True, "result": result})


def test_one_task_lifecycle_keeps_same_worker_and_fragment_content(tmp_path, monkeypatch):
    worker = new_worker(tmp_path, monkeypatch)
    commands, state, process = fake_engine(worker, monkeypatch)
    ready = worker.start()
    assert ready["worker_sha256"] == hashlib.sha256(
        (ROOT / "brainspace/headroom_worker.py").read_bytes()).hexdigest()
    chat = {"model": "fixture", "messages": [{"role": "tool", "content": "original"}]}
    original = deepcopy(chat)
    compact = [{"role": "tool", "content": "vendor fragment marker"}]
    reply(worker, {"messages": compact})
    assert worker.prepare(chat) == {"model": "fixture", "messages": compact}
    assert chat == original
    # Upstream retrieval is not relabeled a complete/root/full-file recovery.
    fragment = "Only a stored fragment, not the whole source file."
    reply(worker, {"tool_call_id": "r1", "tool_name": "headroom_retrieve", "content": fragment})
    assert worker.retrieve({"hash": "vendor-hash"}, "r1") == fragment
    reply(worker, {"messages": compact})
    assert worker.prepare(chat)["messages"] == compact
    audit = {"recoveries": {"vendor-hash": fragment}, "reference_count": 1, "audit_after_task": True}
    reply(worker, audit)
    assert worker.finish() == audit and worker.finished
    sent = [json.loads(line) for line in process.stdin.getvalue().splitlines()]
    assert [r["op"] for r in sent] == ["compress", "retrieve", "compress", "finish"]
    assert len([c for c in commands if c[0] == "create"]) == 1
    with pytest.raises(RuntimeError):
        worker.prepare(chat)
    state["State"]["Running"], process.returncode = False, 0
    cleanup = worker.close()
    assert cleanup["container_removed"] and cleanup["worker_snapshot_unchanged"]
    assert cleanup["attach_client_reaped"]
    assert [c for c in commands if c[0] == "rm"] == [["rm", IDENTITY]]
    journal = [runtime_io.parse_json(line) for line in (worker.directory / "rpc.jsonl").read_text().splitlines()]
    assert [r["state"] for r in journal] == ["pending", "completed"] * 4


def test_start_requires_pinned_offline_mounts_and_cannot_repeat(tmp_path, monkeypatch):
    worker = new_worker(tmp_path, monkeypatch)
    commands, _, _ = fake_engine(worker, monkeypatch)
    worker.start()
    create = next(c for c in commands if c[0] == "create")
    assert create[create.index("--network") + 1] == "none"
    assert "--read-only" in create
    assert "HF_HUB_OFFLINE=1" in create and "TRANSFORMERS_OFFLINE=1" in create
    assert create[-2:] == [headroom.IMAGE_ID, "/inputs/worker.py"]
    assert all(create[i+1].endswith(",readonly") for i, v in enumerate(create) if v == "--mount")
    assert all(c[0] not in ("pull", "build", "run") for c in commands)
    with pytest.raises(RuntimeError):
        worker.start()
    worker.close()
    with pytest.raises(RuntimeError):
        worker.start()
    with pytest.raises(RuntimeError):
        worker.prepare({"model": "fixture", "messages": []})


@pytest.mark.parametrize("changes", [
    {"commit": "wrong"}, {"model_revision": "wrong"}, {"worker_sha256": "wrong"},
    {"protocol": "wrong"}, {"ok": False}, {"id": "wrong"},
])
def test_bad_handshake_is_failed_and_owned_container_still_closes(tmp_path, monkeypatch, changes):
    worker = new_worker(tmp_path, monkeypatch)
    commands, _, _ = fake_engine(worker, monkeypatch, ready_changes=changes)
    with pytest.raises(ValueError):
        worker.start()
    assert worker.failed
    with pytest.raises(RuntimeError):
        worker.prepare({"model": "fixture", "messages": []})
    assert worker.close()["container_removed"]
    assert commands[-1] == ["rm", IDENTITY]


@pytest.mark.parametrize("response", [
    {"id": "1", "ok": False, "error_type": "upstream_failure"},
    {"id": "foreign", "ok": True, "result": {}},
    {"id": "1", "ok": True},
])
def test_rpc_failure_keeps_pending_receipt_and_disallows_continuation(tmp_path, monkeypatch, response):
    worker = new_worker(tmp_path, monkeypatch)
    fake_engine(worker, monkeypatch)
    worker.start()
    worker.replies.put(response)
    with pytest.raises(ValueError):
        worker.prepare({"model": "fixture", "messages": []})
    assert worker.failed
    with pytest.raises(RuntimeError):
        worker.finish()
    rows = [json.loads(line) for line in (worker.directory / "rpc.jsonl").read_text().splitlines()]
    assert [row["state"] for row in rows] == ["pending"]
    assert worker.close()["failed"] is True


@pytest.mark.parametrize("mode", ["foreign", "unavailable", "timeout", "foreign_after_stop"])
def test_cleanup_never_removes_unconfirmed_or_foreign_container(tmp_path, monkeypatch, mode):
    worker = new_worker(tmp_path, monkeypatch)
    commands, state, process = fake_engine(worker, monkeypatch)
    worker.start()
    original = worker.command
    inspections = 0

    def command(args, **kwargs):
        nonlocal inspections
        if args[0] == "inspect":
            inspections += 1
            if mode == "unavailable":
                return SimpleNamespace(returncode=1, stdout="")
            if mode == "timeout":
                raise subprocess.TimeoutExpired("inspect", 30)
            if mode == "foreign" or (mode == "foreign_after_stop" and inspections == 2):
                state["Config"]["Labels"]["tokenmaster.parity"] = "another-task"
        return original(args, **kwargs)

    worker.command = command
    if mode == "unavailable":
        assert worker.close()["container_state"] == "unconfirmed"
    else:
        with pytest.raises((ValueError, subprocess.TimeoutExpired)):
            worker.close()
    assert not any(c[0] == "rm" for c in commands)
    receipt = json.loads((worker.directory / "cleanup.json").read_text())
    assert not receipt.get("container_removed", False)
    assert receipt["attach_client_reaped"] and process.returncode is not None


def test_retrieval_identity_is_not_reinterpreted(tmp_path, monkeypatch):
    worker = new_worker(tmp_path, monkeypatch)
    fake_engine(worker, monkeypatch)
    worker.start()
    reply(worker, {"tool_call_id": "foreign", "tool_name": "headroom_retrieve", "content": "fragment"})
    with pytest.raises(ValueError, match="identity"):
        worker.retrieve({"hash": "hash"}, "own")
    worker.close()


def test_missing_image_does_not_create_or_download(tmp_path, monkeypatch):
    worker = new_worker(tmp_path, monkeypatch)
    calls = []
    def command(args, **kwargs):
        calls.append(args)
        raise RuntimeError("image unavailable")
    worker.command = command
    with pytest.raises(RuntimeError):
        worker.start()
    assert calls == [["image", "inspect", headroom.IMAGE_ID]]
    assert worker.failed and worker.identity is None
    assert not worker.close().get("container_removed", False)


def test_production_and_compatibility_interfaces_are_identical():
    sys.path.insert(0, str(EVALS))
    from competitors import headroom_container as old, headroom_worker as old_worker
    for name in ("HeadroomContainer", "validate_container", "IMAGE_ID", "COMMIT", "MODEL_REVISION", "MAX_FRAME"):
        assert getattr(old, name) is getattr(headroom, name)
    for name in ("parse", "emit", "diagnostic_rows", "main", "COMMIT", "MODEL_SHA256"):
        assert getattr(old_worker, name) is getattr(headroom_worker, name)


def test_installer_copies_standalone_product_without_eval_or_vendor_imports(tmp_path):
    import brainspace_setup
    installed = brainspace_setup._install_files(tmp_path / "home")
    # Make a minimal installed package: no checkout, evals, MCP or vendor libs.
    package = tmp_path / "minimal/brainspace"
    package.mkdir(parents=True)
    for name in ("__init__.py", "headroom.py", "headroom_worker.py", "runtime_io.py"):
        shutil.copy2(installed / "brainspace" / name, package / name)
    script = r'''
import importlib.abc, importlib.util, pathlib, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"evals","quality","tests","headroom","onnxruntime","mcp","tiktoken"}:
            raise AssertionError("forbidden eager import: " + fullname)
sys.meta_path.insert(0, Block())
sys.path.insert(0, sys.argv[1])
from brainspace.headroom import HeadroomContainer
from brainspace.runtime_io import parse_json
assert parse_json('{"ok":true}') == {"ok":True}
# The mounted worker is loaded alone, outside package context; main is NOT run.
spec = importlib.util.spec_from_file_location("mounted_worker", sys.argv[2])
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
assert worker.parse('{"ok":true}') == {"ok":True}
print("PRODUCT_IMPORT_OK")
'''
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", script, str(package.parent),
         str(package / "headroom_worker.py")],
        capture_output=True, text=True, timeout=15, cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PRODUCT_IMPORT_OK"
    for name in ("headroom.py", "headroom_worker.py", "runtime_io.py"):
        tree = ast.parse((package / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in {"evals", "quality", "tests"}
        # Flat files are selected by the existing snapshot's brainspace/*.py glob.
        assert package / name in list(package.glob("*.py"))


@pytest.mark.parametrize("text", [
    '{"a":1,"a":2}', '{"nested":{"a":1,"a":2}}', '{"a":NaN}', '{"a":Infinity}',
    '{"a":-Infinity}', '{"a":1e999}', '{"a":-1e999}',
])
def test_shared_json_rejects_duplicate_and_nonfinite_values(text):
    with pytest.raises(ValueError):
        runtime_io.parse_json(text)


def test_shared_root_checks_parents_without_resolving_away_links(tmp_path, monkeypatch):
    linked = tmp_path / "linked"
    path = linked / "not-created/yet"
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda p: p == linked or original(p))
    with pytest.raises(ValueError, match="linked"):
        runtime_io.safe_root(path)


def test_shared_root_rejects_junction_parent(tmp_path, monkeypatch):
    linked = tmp_path / "junction"
    monkeypatch.setattr(Path, "is_junction", lambda p: p == linked)
    with pytest.raises(ValueError, match="linked"):
        runtime_io.safe_root(linked / "child")
    assert runtime_io.safe_root(tmp_path / "ordinary") == tmp_path / "ordinary"


@pytest.mark.parametrize("alias", [
    "sibling/../workspace/private-state",
    "./sibling/../workspace/./private-state",
    "sibling/../workspace/nested/../private-state",
])
def test_shared_root_canonicalizes_dot_aliases_before_containment(tmp_path, monkeypatch, alias):
    (tmp_path / "sibling").mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(tmp_path)
    expected = workspace / "private-state"
    for path in (Path(alias), tmp_path / alias):
        canonical = runtime_io.safe_root(path)
        assert canonical == expected.resolve()
        assert canonical.is_relative_to(runtime_io.safe_root(workspace))
        assert ".." not in canonical.parts
    assert not expected.exists()


@pytest.mark.parametrize("kind", ["is_symlink", "is_junction"])
@pytest.mark.parametrize("cancelled_prefix", [False, True])
def test_link_cannot_be_erased_by_parent_traversal_before_check(
    tmp_path, monkeypatch, kind, cancelled_prefix,
):
    linked = tmp_path / "linked"
    original = getattr(Path, kind)
    monkeypatch.setattr(Path, kind, lambda p: p == linked or original(p))
    monkeypatch.setattr(Path, "resolve", lambda *a, **k: pytest.fail("link checked after resolution"))
    prefix = tmp_path / "missing" / ".." / "linked" if cancelled_prefix else linked
    with pytest.raises(ValueError, match="linked"):
        runtime_io.safe_root(prefix / ".." / "workspace" / "private-state")


@pytest.mark.parametrize("workspace_alias", [False, True])
def test_runtime_rejects_canonical_private_output_inside_workspace(tmp_path, workspace_alias):
    from brainspace.runtime import RuntimeSession

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    chosen_workspace = sibling / ".." / "workspace" if workspace_alias else workspace
    chosen_output = sibling / ".." / "workspace" / "private-state"
    # Deliberately invalid transport: containment must reject BEFORE transport
    # validation, tokenizer initialization, or any output directory creation.
    with pytest.raises(ValueError, match="explicit_private_session_scope_required"):
        RuntimeSession(workspace=chosen_workspace, session_id="containment-test",
                       output=chosen_output, transport=object())
    assert not (workspace / "private-state").exists()


def test_ordinary_parent_relative_external_output_remains_valid(tmp_path, monkeypatch):
    from brainspace.runtime import RuntimeSession

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (tmp_path / "cwd").mkdir()
    (tmp_path / "sibling").mkdir()
    monkeypatch.chdir(tmp_path / "cwd")

    class NoCalls:
        model = "no-network-fixture"
        max_request_bytes = 1024

        def encode(self, request):
            pytest.fail("no model request should be prepared")

        def send(self, wire):
            pytest.fail("no network call should occur")

    session = RuntimeSession(
        workspace="../workspace", session_id="parent-relative",
        output="../sibling/../private-run", transport=NoCalls(),
    )
    try:
        assert session.workspace == workspace.resolve()
        assert session.output == (tmp_path / "private-run").resolve()
        assert not session.output.is_relative_to(session.workspace)
        result = session.finish()
        assert result["model_calls"] == 0 and result["quality_verified"] is None
    finally:
        session.close()


@pytest.mark.skipif(os.name != "nt", reason="native Windows path semantics")
def test_windows_mixed_separator_and_case_alias_is_canonical(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (tmp_path / "sibling").mkdir()
    alias = str(tmp_path).replace("\\", "/") + "/sibling\\..\\WORKSPACE/private-state"
    assert runtime_io.safe_root(alias).is_relative_to(runtime_io.safe_root(workspace))
    assert runtime_io.safe_root(alias) == (workspace / "private-state").resolve()


def test_append_receipt_flushes_before_fsync_and_preserves_existing_rows(tmp_path, monkeypatch):
    path = tmp_path / "receipts.jsonl"
    synced = []
    actual = os.fsync
    def fsync(fd):
        synced.append(path.read_text(encoding="utf-8"))
        actual(fd)
    monkeypatch.setattr(runtime_io.os, "fsync", fsync)
    runtime_io.append_receipt(path, {"state": "pending", "text": "α"})
    runtime_io.append_receipt(path, {"state": "completed"})
    assert len(synced) == 2
    assert [len(value.splitlines()) for value in synced] == [1, 2]
    assert [runtime_io.parse_json(line)["state"] for line in synced[-1].splitlines()] == [
        "pending", "completed",
    ]
    with pytest.raises(ValueError):
        runtime_io.append_receipt(path, {"bad": float("nan")})
    assert path.read_text(encoding="utf-8") == synced[-1]


def test_worker_keeps_pinned_vendor_execution_and_fragment_semantics():
    source = (ROOT / "brainspace/headroom_worker.py").read_text()
    assert 'importlib.metadata.version("headroom-ai") == "0.39.1"' in source
    assert "warmer.preload(allow_download=False)" in source
    assert "result = headroom.compress(" in source
    assert "handler._execute_retrieval(" in source
    assert "entry.original_content" in source
    assert "fragment" in headroom.__doc__.lower()
    assert "fragment" in headroom_worker.__doc__.lower()
