"""Typed profile/session wiring. Stub sends/components are not quality evidence."""
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import socket

import pytest

from brainspace import headroom
import brainspace_tools
from brainspace import session_cli
from brainspace.request_policy import RequestPolicy
from brainspace.runtime import RuntimeSession
from brainspace.runtime_policy import RuntimePolicy
from brainspace.runtime_resources import RuntimeResources
from brainspace.transport import Reply, ResponsesTransport


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("no provider sockets in profile/session tests")
    monkeypatch.setattr(socket, "create_connection", deny)
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, deny)


@pytest.fixture
def sent(monkeypatch):
    wires = []

    def send(self, wire):
        wires.append(wire)
        body = {"object": "response", "status": "completed", "model": self.model,
                "output": [], "usage": {"input_tokens": 9, "output_tokens": 2, "total_tokens": 11}}
        return Reply(True, "ok", True, wire, json.dumps(body), body, 200)

    monkeypatch.setattr(ResponsesTransport, "send", send)
    return wires


def make(tmp_path, **options):
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return RuntimeSession(
        workspace=workspace, output=tmp_path / "runtime", session_id="profile-test",
        task_id="reserved:profile-test",
        transport=ResponsesTransport("http://127.0.0.1:1/not-used", "fixture-model"),
        **options)


def request():
    return {"model": "fixture-model", "messages": [
        {"role": "system", "content": "Preserve source text and permissions."},
        {"role": "user", "content": "Explain the supplied input."}]}


@pytest.mark.parametrize("backend", ["none", "local"])
def test_native_policy_identity_precedes_receipts_and_calls(tmp_path, sent, backend):
    policy = (RuntimePolicy() if backend == "none" else RuntimePolicy(
        backend="local", request_policy=RequestPolicy(version="request-policy-v3", enabled=True)))
    session = make(tmp_path, runtime_policy=policy)
    metadata = json.loads((session.output / "session.json").read_text("utf-8"))
    assert metadata["policy_id"] == session.policy_id == policy.policy_id
    assert metadata["task_id"] == "reserved:profile-test"
    assert metadata["profile"]["runtime_policy"] == policy.to_dict()
    assert metadata["profile"]["runtime_resources_id"] == session.runtime_resources.identity
    assert session.profile_id != session.policy_id
    assert session.backend == backend and session.policy == policy.request_policy
    assert session.prepare_components()["headroom_executed"] is False
    original = request()
    session.invoke(original, intent="exact")
    assert sent == [session.transport.encode(original)]
    result = session.finish()
    assert result["trace"]["policy_id"] == policy.policy_id
    assert result["trace"]["calls"][0]["call_id"] == session.run_id + ":1"
    assert result["model_calls"] == 1 and result["gateway_reported_tokens"] == 11
    assert result["quality_verified"] is None and result["transformations"] == 0
    assert session.close()["complete"]


@pytest.mark.parametrize("extra", [
    {"backend": "local"}, {"policy": RequestPolicy()}, {"mode": object()},
    {"ponytail": object()}, {"headroom_options": {}}, {"optimizer": object()},
    {"optimizer_version": 1}, {"workload_id": "foreign"}, {"environment_id": "foreign"},
    {"require_nonexpanding_input": True},
])
def test_profile_cannot_label_an_independently_overridden_composition(tmp_path, extra):
    with pytest.raises(ValueError, match="composition_conflict"):
        make(tmp_path, runtime_policy=RuntimePolicy(), **extra)
    assert not (tmp_path / "runtime").exists()


@pytest.mark.parametrize("policy", [
    RuntimePolicy(instruction="ponytail"),
    RuntimePolicy(backend="headroom"),
])
def test_required_assets_cannot_silently_fall_back(tmp_path, policy):
    with pytest.raises(ValueError, match="runtime_resources"):
        make(tmp_path, runtime_policy=policy)
    assert not (tmp_path / "runtime").exists()


def test_legacy_profile_remains_legacy_and_unused_bindings_reject(tmp_path, sent):
    with pytest.raises(ValueError, match="unused_runtime_resources"):
        make(tmp_path, runtime_resources=RuntimeResources())
    session = make(tmp_path)
    assert session.runtime_policy is None and session.runtime_resources is None
    assert "runtime_policy" not in session.profile and "runtime_resources_id" not in session.profile
    session.invoke(request())
    assert sent == [session.transport.encode(request())]
    session.finish()
    session.close()


def test_profile_and_resource_fields_are_frozen_and_object_bypass_detected(tmp_path, sent):
    policy = RuntimePolicy()
    session = make(tmp_path, runtime_policy=policy)
    with pytest.raises(AttributeError):
        session.runtime_policy = replace(policy, instruction="ponytail")
    with pytest.raises(AttributeError):
        session.runtime_resources = RuntimeResources()
    object.__setattr__(policy, "instruction", "ponytail")  # Adversarial trusted-code test.
    with pytest.raises(ValueError, match="configuration_changed"):
        session.invoke(request())
    assert not sent
    assert session.finish()["component"]["complete"] is False
    session.close()


def test_explicit_readiness_uses_one_same_component_without_primary_calls(tmp_path, sent, monkeypatch):
    resources = RuntimeResources()
    state = []

    # Fake binding/component deliberately bypasses real assets only in this
    # lifecycle unit test. Resource provenance has its own independent tests.
    monkeypatch.setattr(RuntimeResources, "resolve", lambda self, policy: {
        "ponytail": None,
        "headroom_options": {"cache": tmp_path, "assets": tmp_path / "not-a-model",
                            "docker_config": None, "time_budget_seconds": 60}})
    monkeypatch.setattr(RuntimeResources, "validate", lambda self, policy=None: None)

    class Component:
        def __init__(self, path, **options):
            path.mkdir()
            assert options["time_budget_seconds"] == 60
            state.append("construct")

        def start(self):
            state.append("start")
            return {"fixture": True, "local_inference_inventory_complete": False}

        def prepare(self, chat):
            pytest.fail("protected intent must not compress")

        def finish(self):
            state.append("finish")
            return {"fixture": True}

        def close(self):
            state.append("close")
            return {"container_id": None, "container_removed": True}

    monkeypatch.setattr(headroom, "HeadroomContainer", Component)
    policy = RuntimePolicy(backend="headroom", headroom_time_budget_seconds=60,
                           require_nonexpanding_input=True)
    session = make(tmp_path, runtime_policy=policy, runtime_resources=resources)
    for _ in range(2):
        ready = session.prepare_components()
        assert ready["headroom_executed"] and ready["primary_calls"] == 0
    assert state == ["construct", "start"] and not sent
    assert session.profile["headroom_time_budget_seconds"] == 60
    session.invoke(request(), intent="exact")
    assert session.finish()["component"]["headroom_executed"]
    assert session.close()["complete"]
    assert state == ["construct", "start", "finish", "close"]


def test_readiness_resource_failure_stays_incomplete(tmp_path, monkeypatch, sent):
    session = make(tmp_path, runtime_policy=RuntimePolicy())

    def fail(*args, **kwargs):
        raise OSError("private filesystem detail")

    monkeypatch.setattr(RuntimeResources, "validate", fail)
    with pytest.raises(OSError):
        session.prepare_components()
    result = session.finish()
    assert result["component"]["complete"] is False
    assert result["component"]["failure"]["phase"] == "component_readiness"
    assert result["model_calls"] == 0 and not sent
    assert session.close()["complete"]


def test_actual_pinned_ponytail_is_bound_at_creation(tmp_path, sent):
    export = os.getenv("TOKENMASTER_TEST_PONYTAIL_EXPORT")
    if not export:
        pytest.skip("optional actual local pinned export not supplied")
    resources = RuntimeResources(ponytail_export=Path(export))
    policy = RuntimePolicy(instruction="ponytail")
    session = make(tmp_path, runtime_policy=policy, runtime_resources=resources)
    session.invoke(request())
    assert session.ponytail is not None
    assert session.ponytail.instructions_sha256 == policy.ponytail_instructions_sha256
    assert sent[0] != session.transport.encode(request())
    receipt = json.loads((session.output / "preparations.jsonl").read_text("utf-8"))
    assert receipt["instruction_component_applied"] == "ponytail"
    assert session.finish()["model_calls"] == 1
    session.close()


def profile_args(tmp_path, *extra):
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    path = tmp_path / "profile.json"
    path.write_text(RuntimePolicy().to_json(), encoding="utf-8")
    return brainspace_tools._parser().parse_args([
        "--workspace", str(workspace), "--session", "profile-cli", "session",
        "--backend", "profile", "--runtime-policy", str(path),
        "--output", str(tmp_path / "runtime"), "--base-url", "http://127.0.0.1:1/not-used",
        "--model", "fixture-model", "--allow-network", *extra])


def test_user_session_cli_uses_the_declared_profile(tmp_path, sent):
    args = profile_args(tmp_path)
    incoming = io.BytesIO((json.dumps({"op": "call", "request": request()}) + "\n"
                          + '{"op":"finish"}\n').encode())
    outgoing = io.BytesIO()
    assert session_cli.run_session(args, input_stream=incoming, output_stream=outgoing) == 0
    finish = json.loads(outgoing.getvalue().splitlines()[-1])
    assert finish["result"]["policy_id"] == RuntimePolicy().policy_id
    assert finish["result"]["quality_verified"] is None and len(sent) == 1
    metadata = json.loads((tmp_path / "runtime/session.json").read_text("utf-8"))
    assert metadata["profile"]["backend"] == "none"
    assert metadata["profile"]["runtime_policy"] == RuntimePolicy().to_dict()


@pytest.mark.parametrize("extra", [
    ["--require-nonexpanding-input"],
    ["--headroom-time-budget-seconds", "60"],
    ["--use-session-mode"],
    ["--headroom-docker-config", "not-read"],
])
def test_profile_cli_rejects_independent_composition_overrides(tmp_path, sent, extra):
    args = profile_args(tmp_path, *extra)
    outgoing = io.BytesIO()
    assert session_cli.run_session(args, input_stream=io.BytesIO(), output_stream=outgoing) == 2
    assert not sent and not (tmp_path / "runtime").exists()


def test_cli_profile_file_requires_explicit_profile_backend(tmp_path, sent):
    args = profile_args(tmp_path)
    args.backend = "none"
    with pytest.raises(ValueError, match="explicit_profile_selection_required"):
        session_cli._session(args)
    assert not sent and not (tmp_path / "runtime").exists()
