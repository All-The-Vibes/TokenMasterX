"""Full CLI -> host -> runtime -> controller seam over fake assets and HTTP.

These tests do not attest vendor assets or real model quality. Resource
provenance is separately tested; no Docker or external inference is allowed.
"""
import json

import pytest

from brainspace import headroom
from brainspace.jev import Diagnostics, JevClient, Result
from brainspace.optimizer import Optimizer, OptimizerError
from brainspace.runtime_policy import RuntimePolicy
from brainspace.runtime_resources import RuntimeResources
import token_efficiency as cli
import test_runtime_efficiency_cli as local_cli_fixtures

peer = local_cli_fixtures.peer
setup = local_cli_fixtures.setup


@pytest.fixture
def components(tmp_path, monkeypatch):
    events = []
    original_init = RuntimeResources.__init__

    def fake_bind(self, **paths):
        events.append("resources")
        original_init(self)  # Empty actual type; fake resolution is explicit below.

    def fake_resolve(self, policy):
        if policy.instruction == "ponytail":
            raise ValueError("no_ponytail_in_this_offline_fixture")
        options = None
        if policy.backend == "headroom":
            options = {"cache": tmp_path, "assets": tmp_path / "not-a-real-model",
                       "docker_config": None}
            if policy.headroom_time_budget_seconds is not None:
                options["time_budget_seconds"] = policy.headroom_time_budget_seconds
        return {"ponytail": None, "headroom_options": options}

    monkeypatch.setattr(RuntimeResources, "__init__", fake_bind)
    monkeypatch.setattr(RuntimeResources, "validate", lambda self, policy=None: events.append("validate"))
    monkeypatch.setattr(RuntimeResources, "resolve", fake_resolve)

    class Component:
        def __init__(self, directory, **kwargs):
            directory.mkdir()
            events.append("component-construct")

        def start(self):
            events.append("component-start")
            return {"fixture": True, "local_inference_inventory_complete": False}

        def prepare(self, chat):
            pytest.fail("exact task does not need compression")

        def finish(self):
            from brainspace.headroom_worker import ActivityLedger
            events.append("component-finish")
            return {"fixture": True, "python_onnx_inventory": ActivityLedger().inventory()}

        def close(self):
            events.append("component-close")
            return {"container_id": None, "container_removed": True}

    monkeypatch.setattr(headroom, "HeadroomContainer", Component)
    return events


def call(db, command, output, common, *extra):
    args = cli._parser().parse_args([
        "--db", str(db), command, "--output", str(output), *common,
        "--ponytail-export", str(output.parent / "fake-export"),
        "--headroom-cache", str(output.parent / "fake-cache"),
        "--headroom-assets", str(output.parent / "fake-assets"), *extra])
    return cli.execute(args)


@pytest.mark.parametrize("backend", ["local", "headroom"])
def test_true_off_admission_and_explicit_runtime_neighbor(tmp_path, peer, components, backend):
    db, _, common = setup(tmp_path, peer, feasible=True, planned_rounds=2)
    initial = call(db, "initialize-profile", tmp_path / "initial", common)
    assert not peer[1]
    assert initial["initial_policy_is_optimizer_off"] is True
    assert initial["status"]["champion"]["policy"] == RuntimePolicy().to_dict()
    admission = json.loads((tmp_path / "initial/safety-check/admission.json").read_text("utf-8"))
    assert admission["passed"] and admission["true_optimizer_off"]
    assert admission["model_calls"] == 0 and admission["model_quality_tested"] is False
    assert "component-start" not in components
    optimizer = Optimizer.open(db)
    chosen = next(p for p in optimizer.propose() if p.backend == backend)
    count = len(initial["task_ids"])
    result = call(db, "learn-profile", tmp_path / "trial", common,
                  *local_cli_fixtures.task_arguments(initial), "--candidate-id", chosen.policy_id)
    assert len(peer[1]) == 4 * count and result["policy_promoted"] is False
    assert result["plan_feasibility"]["arithmetic"]["status"] == "not_ruled_out"
    assert result["incumbent_is_optimizer_off"] is True
    assert result["step"]["candidate_id"] == chosen.policy_id
    assert result["step"]["status"] == "not_certified"
    assert result["status"]["champion"] == initial["status"]["champion"]
    assert result["status"]["learning"]["coverage"] == "complete"
    observation = json.loads(next((tmp_path / "trial").rglob("observation.json")).read_text("utf-8"))
    assert observation["incumbent_outcome"]["success"] and observation["candidate_outcome"]["success"]
    assert observation["incumbent"]["policy_id"] == RuntimePolicy().policy_id
    assert observation["candidate"]["policy_id"] == chosen.policy_id
    if backend == "headroom":
        assert components.count("component-start") == components.count("component-close") == count
    with pytest.raises(OptimizerError, match="^task_already_consumed$"):
        call(db, "learn-profile", tmp_path / "reused", common,
             *local_cli_fixtures.task_arguments(initial), "--candidate-id", chosen.policy_id)
    assert len(peer[1]) == 4 * count and not (tmp_path / "reused").exists()


def test_explicit_candidate_cannot_be_combined_with_jev(tmp_path, peer, components, monkeypatch):
    db, _, common = setup(tmp_path, peer)
    initial = call(db, "initialize-profile", tmp_path / "initial", common)
    with pytest.raises(OptimizerError, match="candidate_and_screener_conflict"):
        call(db, "learn-profile", tmp_path / "forbidden", common,
             "--task-id", initial["task_ids"][0], "--candidate-id", "not-a-neighbor", "--jev")
    assert not peer[1] and not (tmp_path / "forbidden").exists()
    assert Optimizer.open(db).status()["trials"] == []


def test_unknown_explicit_candidate_cannot_dispatch_or_promote(tmp_path, peer, components):
    db, _, common = setup(tmp_path, peer, feasible=True)
    initial = call(db, "initialize-profile", tmp_path / "initial", common)
    with pytest.raises(OptimizerError, match="^explicit_candidate_not_proposed$"):
        call(db, "learn-profile", tmp_path / "bad-choice", common,
             *local_cli_fixtures.task_arguments(initial), "--candidate-id", "foreign")
    assert not peer[1]
    assert Optimizer.open(db).status()["champion"] == initial["status"]["champion"]


def test_missing_authority_precedes_any_resource_validation(tmp_path, peer, monkeypatch):
    db, _, common = setup(tmp_path, peer)
    common.remove("--allow-network")
    monkeypatch.setattr(RuntimeResources, "__init__", lambda *a, **k: pytest.fail("no resource reads"))
    with pytest.raises(OptimizerError, match="runtime_network_opt_in_required"):
        call(db, "initialize-profile", tmp_path / "forbidden", common)
    assert not db.exists() and not peer[1]


def test_policy_only_jev_selection_cannot_become_quality_or_promotion(tmp_path, peer, components, monkeypatch):
    db, _, common = setup(tmp_path, peer, feasible=True)
    initial = call(db, "initialize-profile", tmp_path / "initial", common)
    screens = []

    def decide(self, state, questions, *, data_classification):
        from brainspace.jev import MODEL
        assert data_classification == "sanitized"
        wire = json.dumps({"state": state, "questions": questions})
        assert "note.txt" not in wire and "Résumé" not in wire and '"expected"' not in wire
        selected = next(key for key, value in state.items()
                        if value["policy_settings"]["backend"] == "local")
        probabilities = {key: float(key == selected) for key in questions["proposal"]["criteria"]}
        payload = {"model": MODEL, "answers": {"proposal": {
            "type": "choice", "choice": selected, "confidence": 1.0,
            "probabilities": probabilities}}, "usage": {"input_tokens": 11, "output_tokens": 4}}
        screens.append(wire)
        return Result(True, "ok", wire, json.dumps(payload), payload,
                      Diagnostics(attempts=1, response_complete=True, http_status=200))

    monkeypatch.setattr(JevClient, "decide", decide)
    monkeypatch.setenv("TYPESAFE_API_KEY", "offline-test-placeholder")
    result = call(db, "learn-profile", tmp_path / "trial", common,
                  *local_cli_fixtures.task_arguments(initial), "--jev")
    assert len(screens) == 1 and len(peer[1]) == 4 * len(initial["task_ids"])
    assert result["status"]["learning"]["complete_calls"] == 4 * len(initial["task_ids"]) + 1
    assert result["step"]["status"] == "not_certified"
    assert result["policy_promoted"] is False
    assert result["status"]["champion"] == initial["status"]["champion"]
