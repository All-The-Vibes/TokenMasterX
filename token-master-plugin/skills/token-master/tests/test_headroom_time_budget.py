"""Explicit finite latency regime only; fake Docker and no model calls."""
from copy import deepcopy
import hashlib
import json

import pytest

import brainspace_tools
from brainspace import headroom, runtime, session_cli
from test_headroom_environment import SAVED_ENV, SAVED_VALUES
from test_headroom_product_boundary import fake_engine
from test_product_runtime import Transport


INVALID = [True, False, 0, -1, 61, 60.0, "60", float("nan"), float("inf"), {}, []]
BUDGET_KEYS = ("HEADROOM_COMPRESSION_DEADLINE_MS", "HEADROOM_KOMPRESS_TIME_BUDGET_SECONDS")


def selected_env(seconds):
    return SAVED_ENV + [f"{BUDGET_KEYS[0]}={seconds * 1000}", f"{BUDGET_KEYS[1]}={seconds}"]


def worker_for(tmp_path, monkeypatch, seconds):
    cache, config = tmp_path / "cache", tmp_path / "config"
    cache.mkdir()
    config.mkdir()
    assets = tmp_path / "assets.json"
    assets.write_text("{}", encoding="utf-8")
    (config / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(headroom.shutil, "which", lambda _: "fake-docker")
    return headroom.HeadroomContainer(
        tmp_path / "worker", cache=cache, assets=assets, docker_config=config,
        label="budget-test", time_budget_seconds=seconds)


@pytest.mark.parametrize("seconds", [None, 1, 60])
def test_only_explicit_budget_adds_both_create_settings_and_bound_receipt(tmp_path, monkeypatch, seconds):
    monkeypatch.setenv(BUDGET_KEYS[0], "0")
    monkeypatch.setenv(BUDGET_KEYS[1], "0")
    monkeypatch.setenv("HEADROOM_KOMPRESS_ENDPOINT", "must-not-forward")
    worker = worker_for(tmp_path, monkeypatch, seconds)
    commands, state, _ = fake_engine(worker, monkeypatch)
    state["Config"]["Env"] = SAVED_ENV if seconds is None else selected_env(seconds)
    worker.start()
    create = next(c for c in commands if c[0] == "create")
    env = dict(create[i+1].split("=", 1) for i, value in enumerate(create) if value == "--env")
    assert len(env) == (16 if seconds is None else 18)
    assert not set(BUDGET_KEYS) & worker.environment.keys()
    assert "HEADROOM_KOMPRESS_ENDPOINT" not in worker.environment
    assert {k: v for k, v in env.items() if k not in BUDGET_KEYS} == headroom.TASK_ENVIRONMENT
    assert env["HEADROOM_KOMPRESS_ONNX_INTRA_THREADS"] == "2"
    assert env["HEADROOM_KOMPRESS_ONNX_INTER_THREADS"] == "1"
    assert create[create.index("--cpus") + 1] == "2"
    assert create[create.index("--memory") + 1] == "4g"
    receipt = json.loads((worker.directory / "environment.json").read_text(encoding="utf-8"))
    if seconds is None:
        assert not set(BUDGET_KEYS) & env.keys()
        assert receipt == headroom.validate_environment(SAVED_ENV)
        assert len(receipt["names"]) == 23
    else:
        assert env[BUDGET_KEYS[0]] == str(seconds * 1000)
        assert env[BUDGET_KEYS[1]] == str(seconds)
        assert receipt["time_budget_seconds"] == seconds
        assert len(receipt["names"]) == 25
        values = dict(value.split("=", 1) for value in selected_env(seconds))
        assert receipt["declared_nonsecret_regime_sha256"] == hashlib.sha256(
            json.dumps(values, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        assert receipt != headroom.validate_environment(SAVED_ENV)
        assert all(values[k] == v for k, v in SAVED_VALUES.items())
    worker.close()


@pytest.mark.parametrize("seconds", INVALID)
def test_container_rejects_invalid_budget_before_path_io(monkeypatch, seconds):
    monkeypatch.setattr(headroom, "safe_root", lambda *_: pytest.fail("path I/O before validation"))
    with pytest.raises(ValueError, match="time_budget"):
        headroom.HeadroomContainer(
            "unused", cache="unused", assets="unused", docker_config="unused",
            label="budget-test", time_budget_seconds=seconds)


@pytest.mark.parametrize("seconds", INVALID + [None])
def test_runtime_rejects_explicit_invalid_budget_before_io(monkeypatch, seconds):
    monkeypatch.setattr(runtime, "safe_root", lambda *_: pytest.fail("path I/O before validation"))
    with pytest.raises(ValueError, match="time_budget"):
        runtime.RuntimeSession(
            workspace="unused", output="unused", session_id="s", transport=Transport(),
            backend="headroom", headroom_options={
                "cache": "unused", "assets": "unused", "docker_config": None,
                "time_budget_seconds": seconds})


@pytest.mark.parametrize("backend", ["none", "local"])
def test_runtime_rejects_unused_budget_before_io(monkeypatch, backend):
    monkeypatch.setattr(runtime, "safe_root", lambda *_: pytest.fail("path I/O before validation"))
    with pytest.raises(ValueError, match="unused_headroom"):
        runtime.RuntimeSession(
            workspace="unused", output="unused", session_id="s", transport=Transport(),
            backend=backend, headroom_options={"time_budget_seconds": 60})


def test_runtime_profile_binds_budget_and_copies_options_without_changing_default(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    base: dict = {"cache": tmp_path / "cache", "assets": tmp_path / "assets.json", "docker_config": None}
    profiles = []
    options_seen = []

    class FakeHeadroom:
        def __init__(self, *args, **kwargs):
            options_seen.append(kwargs)

        def start(self):
            return {"fixture": True}

        def finish(self):
            return {"fixture": True}

        def close(self):
            return {"container_id": None}

    monkeypatch.setattr(headroom, "HeadroomContainer", FakeHeadroom)
    for i, seconds in enumerate([None, None, 1, 60]):
        options = deepcopy(base)
        if seconds is not None:
            options["time_budget_seconds"] = seconds
        session = runtime.RuntimeSession(
            workspace=workspace, output=tmp_path / str(i), session_id="budget-test",
            transport=Transport(), backend="headroom", headroom_options=options)
        if seconds is None:
            assert "headroom_time_budget_seconds" not in session.profile
        else:
            assert session.profile["headroom_time_budget_seconds"] == seconds
            options["time_budget_seconds"] = 2
        persisted = json.loads((session.output / "session.json").read_text(encoding="utf-8"))
        assert persisted["profile"] == session.profile
        assert persisted["profile_id"] == session.profile_id
        profiles.append((session.profile_id, session.profile))
        session._start_headroom()
        assert options_seen[-1].get("time_budget_seconds") == seconds
        session.close()
    assert profiles[0] == profiles[1]
    assert len({p[0] for p in profiles}) == 3
    assert {**profiles[0][1], "headroom_time_budget_seconds": 60} == profiles[3][1]


@pytest.mark.parametrize("env,budget", [
    (selected_env(60), None), (SAVED_ENV, 60), (selected_env(1), 60),
    (SAVED_ENV + [f"{BUDGET_KEYS[0]}=60000"], 60),
    (SAVED_ENV + [f"{BUDGET_KEYS[0]}=0", f"{BUDGET_KEYS[1]}=60"], 60),
    (selected_env(60) + ["HEADROOM_KOMPRESS_BACKEND=onnx"], 60),
    (selected_env(60) + ["HEADROOM_KOMPRESS_CANARY_SECONDS=0"], 60),
    (selected_env(60) + [f"{BUDGET_KEYS[1]}=60"], 60),
])
def test_exact_selected_environment_not_arbitrary_overrides(env, budget):
    with pytest.raises(ValueError, match="environment"):
        headroom.validate_environment(env, time_budget_seconds=budget)


def cli_args(tmp_path, extra=()):
    return brainspace_tools._parser().parse_args([
        "--workspace", str(tmp_path / "workspace"), "--session", "s", "session",
        "--output", str(tmp_path / "run"), "--backend", "headroom",
        "--base-url", "http://127.0.0.1/v1", "--model", "fixture", "--allow-network",
        "--headroom-cache", str(tmp_path / "cache"), "--headroom-assets", str(tmp_path / "assets.json"),
        *extra])


@pytest.mark.parametrize("seconds", [None, 1, 60])
def test_cli_propagation_and_embedded_absent_default(tmp_path, monkeypatch, seconds):
    args = cli_args(tmp_path, [] if seconds is None else ["--headroom-time-budget-seconds", str(seconds)])
    if seconds is None:
        del args.headroom_time_budget_seconds  # Older trusted embedded callers.
    (tmp_path / "workspace").mkdir()
    (tmp_path / "cache").mkdir()
    (tmp_path / "assets.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(session_cli, "RuntimeSession", lambda **kwargs: kwargs)
    result = session_cli._session(args)
    assert result["headroom_options"].get("time_budget_seconds") == seconds
    assert ("time_budget_seconds" in result["headroom_options"]) == (seconds is not None)
    assert result["headroom_options"]["docker_config"] is None
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("seconds", INVALID)
def test_cli_invalid_budget_rejected_before_io(tmp_path, monkeypatch, seconds):
    args = cli_args(tmp_path)
    args.headroom_time_budget_seconds = seconds
    monkeypatch.setattr(session_cli, "safe_root", lambda *_: pytest.fail("path I/O before validation"))
    with pytest.raises(session_cli.ProtocolError, match="time_budget"):
        session_cli._session(args)


@pytest.mark.parametrize("backend", ["none", "local"])
def test_cli_unused_budget_rejected_before_io(tmp_path, monkeypatch, backend):
    args = cli_args(tmp_path, ["--headroom-time-budget-seconds", "60"])
    args.backend = backend
    monkeypatch.setattr(session_cli, "safe_root", lambda *_: pytest.fail("path I/O before validation"))
    with pytest.raises(session_cli.ProtocolError, match="unused_headroom"):
        session_cli._session(args)
