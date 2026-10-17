"""Offline environment boundary tests: no Docker, worker, or inference calls."""
from copy import deepcopy
import hashlib
import json

import pytest

from brainspace import headroom
from test_headroom_product_boundary import fake_engine, new_worker


# Config.Env from guarded-study/live-001/10-doc-rollout-headroom_guarded.
# Public settings copied, not loaded from mutable evidence at test time.
SAVED_ENV = [
    "HF_HUB_DISABLE_TELEMETRY=1",
    "HEADROOM_KOMPRESS_ONNX_INTRA_THREADS=2",
    "XDG_CACHE_HOME=/tmp/headroom/cache",
    "HF_HOME=/cache",
    "HF_HUB_CACHE=/cache/hub",
    "TIKTOKEN_CACHE_DIR=/cache/tiktoken",
    "LITELLM_LOCAL_MODEL_COST_MAP=True",
    "TOKENIZERS_PARALLELISM=false",
    "HF_HUB_OFFLINE=1",
    "DO_NOT_TRACK=1",
    "OMP_NUM_THREADS=2",
    "HEADROOM_KOMPRESS_ONNX_INTER_THREADS=1",
    "HOME=/tmp/headroom",
    "HF_HUB_DISABLE_IMPLICIT_TOKEN=1",
    "OPENBLAS_NUM_THREADS=2",
    "TRANSFORMERS_OFFLINE=1",
    "PATH=/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "GPG_KEY=7169605F62C751356D054A26A821E680E5FA6305",
    "PYTHON_VERSION=3.13.16",
    "PYTHON_SHA256=f4b1bfb3c79b5bb11b8d228a12504163b4c0dab4d679828d8f5f26b6cb6ab35d",
    "HEADROOM_HOST=127.0.0.1",
    "PYTHONUNBUFFERED=1",
    "PYTHONDONTWRITEBYTECODE=1",
]
SAVED_VALUES = dict(value.split("=", 1) for value in SAVED_ENV)
UNDECLARED = [
    "HEADROOM_KOMPRESS_ENDPOINT", "HEADROOM_KOMPRESS_BACKEND",
    "HEADROOM_KOMPRESS_ONNX_FILENAME", "HEADROOM_HF_PIN", "HF_TOKEN",
    "HUGGING_FACE_HUB_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "TYPESAFE_API_KEY",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    "HEADROOM_DETECTOR_BACKEND", "LD_PRELOAD", "PYTHONPATH", "UNDECLARED_SETTING",
]
SECRET = "not-a-real-secret-do-not-persist"


def reject_before_start(tmp_path, monkeypatch, env, *, absent=False):
    worker = new_worker(tmp_path, monkeypatch)
    commands, state, _ = fake_engine(worker, monkeypatch)
    if absent:
        state["Config"].pop("Env", None)
    else:
        state["Config"]["Env"] = env

    def forbidden(*args, **kwargs):
        pytest.fail("Rejected environment reached Popen")

    monkeypatch.setattr(headroom.subprocess, "Popen", forbidden)
    with pytest.raises(ValueError, match="environment") as failure:
        worker.start()
    assert SECRET not in str(failure.value)
    assert worker.failed and worker.process is None
    assert not (worker.directory / "container-config.json").exists()
    assert not (worker.directory / "environment.json").exists()
    assert not (worker.directory / "stderr.txt").exists()
    with pytest.raises(RuntimeError, match="restarted"):
        worker.start()
    assert worker.close()["container_removed"]
    assert commands[-1] == ["rm", worker.identity]
    # Even post-failure cleanup must not leak inspected environment values.
    assert all(SECRET.encode() not in p.read_bytes()
               for p in worker.directory.rglob("*") if p.is_file())


@pytest.mark.parametrize("env", [None, [], {}, "HOME=/tmp/headroom", (), [1], ["NO_EQUALS"],
                                     ["=value"], ["BAD-KEY=value"], ["BAD\nKEY=value"],
                                     ["HOME=/tmp/headroom\0"], [True]])
def test_malformed_or_missing_environment_rejected_before_popen_and_raw_persist(
        tmp_path, monkeypatch, env):
    reject_before_start(tmp_path, monkeypatch, env)


def test_absent_environment_never_means_complete(tmp_path, monkeypatch):
    reject_before_start(tmp_path, monkeypatch, None, absent=True)


@pytest.mark.parametrize("key", list(SAVED_VALUES))
def test_every_declared_setting_is_required(tmp_path, monkeypatch, key):
    reject_before_start(tmp_path, monkeypatch,
                        [entry for entry in SAVED_ENV if entry.split("=", 1)[0] != key])


@pytest.mark.parametrize("key", list(SAVED_VALUES))
def test_every_declared_value_is_pinned(tmp_path, monkeypatch, key):
    env = [entry if entry.split("=", 1)[0] != key else key + "=" + SECRET for entry in SAVED_ENV]
    reject_before_start(tmp_path, monkeypatch, env)


@pytest.mark.parametrize("key", UNDECLARED)
@pytest.mark.parametrize("value", ["", SECRET])
def test_undeclared_overrides_credentials_and_proxies_rejected(tmp_path, monkeypatch, key, value):
    reject_before_start(tmp_path, monkeypatch, SAVED_ENV + [key + "=" + value])


@pytest.mark.parametrize("entry", ["HF_HUB_OFFLINE=1", "HF_HUB_OFFLINE=0", "PATH=" + SECRET])
def test_duplicate_keys_rejected_even_when_equal(tmp_path, monkeypatch, entry):
    reject_before_start(tmp_path, monkeypatch, SAVED_ENV + [entry])


def test_clean_saved_environment_accepted_and_receipted_without_values(tmp_path, monkeypatch):
    worker = new_worker(tmp_path, monkeypatch)
    commands, state, _ = fake_engine(worker, monkeypatch)
    state["Config"]["Env"] = deepcopy(SAVED_ENV)
    worker.start()
    receipt = json.loads((worker.directory / "environment.json").read_text(encoding="utf-8"))
    assert receipt["names"] == sorted(SAVED_VALUES)
    assert receipt["checks"] == {
        "typed_unique_entries": True, "exact_declared_values": True,
        "undeclared_settings_absent": True,
    }
    expected_hash = hashlib.sha256(json.dumps(
        SAVED_VALUES, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    assert receipt["declared_nonsecret_regime_sha256"] == expected_hash
    assert set(receipt) == {"profile", "names", "checks", "declared_nonsecret_regime_sha256"}
    actual = json.loads((worker.directory / "container-config.json").read_text(encoding="utf-8"))
    assert actual["Config"]["Env"] == SAVED_ENV
    assert state["Config"]["Env"] == SAVED_ENV
    create = next(command for command in commands if command[0] == "create")
    overrides = dict(create[i+1].split("=", 1) for i, arg in enumerate(create) if arg == "--env")
    assert len(overrides) == 16
    assert all(SAVED_VALUES[key] == value for key, value in overrides.items())
    assert overrides["HEADROOM_KOMPRESS_ONNX_INTRA_THREADS"] == "2"
    assert overrides["HEADROOM_KOMPRESS_ONNX_INTER_THREADS"] == "1"
    worker.close()


def test_env_order_does_not_change_regime_receipt(tmp_path, monkeypatch):
    worker = new_worker(tmp_path, monkeypatch)
    _, state, _ = fake_engine(worker, monkeypatch)
    state["Config"]["Env"] = list(reversed(SAVED_ENV))
    worker.start()
    receipt = json.loads((worker.directory / "environment.json").read_text(encoding="utf-8"))
    assert receipt["declared_nonsecret_regime_sha256"] == hashlib.sha256(json.dumps(
        SAVED_VALUES, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    worker.close()
