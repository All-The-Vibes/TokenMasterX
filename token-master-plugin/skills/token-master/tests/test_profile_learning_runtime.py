"""Full-profile adapter: real sessions/resources, tiny pinned assets, fake worker/transport."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict, replace
import hashlib
import json
import socket
import subprocess
from types import SimpleNamespace
from typing import Any

import pytest

from brainspace import headroom, learning_runtime, ponytail, runtime_policy, runtime_resources, tokens
from brainspace.learning_runtime import (
    CheckedOutcome, ProfileLearningManifest, RuntimeLearningManifest, RuntimePairEvaluator, learn_once,
)
from brainspace.optimizer import (
    BaselineValidation, EvaluationAttemptFailed, EvaluationAttemptInterrupted, FrozenTrial,
    Optimizer, OptimizerConfig, reference_measurement,
)
from brainspace.request_policy import RequestPolicy
from brainspace.runtime import RuntimeSession
from brainspace.ccr import CCR
from brainspace.runtime_policy import RuntimePolicy
from brainspace.runtime_resources import RuntimeResources
from brainspace.token_ledger import COMPLETE, TaskTrace
from brainspace.transport import Reply


def sha(value):
    return hashlib.sha256(value if type(value) is bytes else value.encode()).hexdigest()


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("no model/network/Docker execution in profile adapter tests")
    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(subprocess, "Popen", deny)


@pytest.fixture
def bound(tmp_path, monkeypatch):
    """Real resource validator, synthetic content pins only (not model assets)."""
    cache = tmp_path / "cache"
    pins, entries = {}, []
    for (repo, name), (revision, _, _) in runtime_resources._ASSETS.items():
        content = ("fixture:" + name).encode()
        relative = f"hub/models--{repo.replace('/', '--')}/snapshots/{revision}/{name}"
        path = cache / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        pins[(repo, name)] = (revision, len(content), sha(content))
        entries.append(dict(repo_id=repo, file=name, revision=revision, cache_path=relative,
                            bytes=len(content), sha256=sha(content), published_digest_verified=True))
    monkeypatch.setattr(runtime_resources, "_ASSETS", pins)
    ref = cache / "hub/models--answerdotai--ModernBERT-base/refs/main"
    ref.parent.mkdir(parents=True)
    ref.write_text(runtime_resources.TOKENIZER_REVISION, encoding="ascii")
    asset_file = tmp_path / "assets.json"
    asset_file.write_text(wire({"complete": True, "verified_files": entries}), encoding="utf-8")
    text = "Explicit synthetic pinned instruction component."
    for module in (ponytail, runtime_policy):
        monkeypatch.setattr(module, "PINNED_INSTRUCTIONS_SHA256", sha(text))
    export = tmp_path / "ponytail.json"
    export.write_text(wire(dict(instructions=text, source_commit=ponytail.PINNED_SOURCE_COMMIT,
                               instructions_sha256=sha(text), fallback_used=False, mode="full")), encoding="utf-8")
    resources = RuntimeResources(ponytail_export=export, headroom_cache=cache, headroom_assets=asset_file)
    return SimpleNamespace(resources=resources, export=export, assets=asset_file, cache=cache)


def policy(**changes):
    return RuntimePolicy(ponytail_instructions_sha256=ponytail.PINNED_INSTRUCTIONS_SHA256, **changes)


@pytest.fixture
def workers(monkeypatch):
    state: dict[str, Any] = {"objects": [], "events": [], "fail_start": None, "interrupt_start": None,
                             "fail_close": False, "incomplete_inventory": False}

    class Worker:
        def __init__(self, directory, **options):
            self.number = len(state["objects"]) + 1
            self.directory, self.options = directory, options
            self.closed = False
            directory.mkdir()
            state["objects"].append(self)
            state["events"].append(("construct", self.number))

        def start(self):
            state["events"].append(("start", self.number))
            (self.directory / "startup.json").write_text(wire({"attempt": self.number}), encoding="utf-8")
            if state["fail_start"] == self.number:
                raise RuntimeError("synthetic missing model readiness")
            if state["interrupt_start"] == self.number:
                raise KeyboardInterrupt("synthetic startup cancellation")
            return {"ready": True, "local_inference_inventory_complete": True}

        def prepare(self, chat):
            state["events"].append(("prepare", self.number))
            return {"model": chat["model"], "messages": deepcopy(chat["messages"])}

        def finish(self):
            state["events"].append(("finish", self.number))
            return {"complete": True, "fixture_only": True, "python_onnx_inventory": {
                "version": "python-onnx-lifetime-ledger-v1", "complete": not state["incomplete_inventory"],
                "since_revision": 0, "pending_count": 0, "pending_ids": [], "omitted_events": 0,
                "local_inference_inventory_complete": False}}

        def close(self):
            assert not self.closed
            self.closed = True
            state["events"].append(("close", self.number))
            if state["fail_close"]:
                raise OSError("synthetic cleanup failure")
            return {"container_id": "fake-owned-" + str(self.number), "container_removed": True}

    monkeypatch.setattr(headroom, "HeadroomContainer", Worker)
    return state


class Transport:
    model, allow_network = "profile-fixture-model", True
    base_url, reasoning_effort, timeout = "http://127.0.0.1:1/not-used", None, 1
    max_request_bytes, max_response_bytes, max_output_tokens = 524288, 524288, 1024

    def __init__(self, owner, arm):
        self.owner, self.arm, self.sent = owner, arm, []

    def encode(self, chat):
        return tokens.serialize({**deepcopy(chat), "max_output_tokens": self.max_output_tokens})

    def send(self, text):
        self.sent.append(text)
        self.owner.events.append(("send", self.arm))
        if self.owner.fail_arm == self.arm:
            if self.owner.failure == "interrupt":
                raise KeyboardInterrupt
            return Reply(False, "transport_error", input_text=text)
        body = {"model": self.model, "output": "independent answer", "usage": {
            "input_tokens": 11, "output_tokens": 7, "total_tokens": 18}}
        return Reply(True, "ok", True, text, json.dumps(body), body, 200)


class Host:
    identity = "profile-stub-host-v1"

    def __init__(self, workers):
        self.workers, self.events, self.sessions, self.prepared = workers, [], {}, {}
        self.fail_arm, self.failure, self.mutate = None, None, None
        self.resource_file = None
        self.expected_workers = 0
        self.wrong_transport = False
        self.success = True

    def task_digest(self, task_id):
        return sha(task_id + "-source-v1")

    def prepare(self, task_id, root):
        workspace = root / "workspace"
        workspace.mkdir()
        (workspace / "note.txt").write_text("Answer is independently checked.", encoding="utf-8")
        transport = Transport(self, root.name)
        if self.wrong_transport and root.name == "candidate":
            transport.max_output_tokens = 512
        prepared = SimpleNamespace(workspace=workspace, transport=transport)
        self.prepared[root.name] = prepared
        self.events.append(("prepare", root.name))
        return prepared

    def drive(self, task_id, session, prepared):
        assert type(session) is RuntimeSession
        arm = session.output.parent.name
        assert (session.output.parent.parent / "components-ready.json").is_file()
        assert len([e for e in self.workers["events"] if e[0] == "start"]) == self.expected_workers
        self.sessions[arm] = session
        self.events.append(("drive", arm))
        if self.mutate == "drive_interrupt":
            raise KeyboardInterrupt
        chat = {"model": prepared.transport.model, "messages": [
            {"role": "system", "content": "Fixed trusted instruction."},
            {"role": "user", "content": "Read task and answer."}], "tools": []}
        session.invoke(chat, intent="overview")
        if self.mutate == "resource":
            assert self.resource_file is not None
            self.resource_file.write_text("changed after a primary call", encoding="utf-8")
        if self.mutate == "capture":
            (session.output / "captures.jsonl").write_text("", encoding="utf-8")
        return {"answer": 7}

    def check(self, task_id, artifacts, prepared):
        arm = prepared.workspace.parent.name
        session = self.sessions[arm]
        assert session._closed
        if self.mutate == "readiness":
            (session.output.parent.parent / "components-ready.json").write_text("{}", encoding="utf-8")
        if self.mutate == "unknown":
            return None
        return CheckedOutcome(self.success, sha("checked-private-gold"))


def setup(tmp_path, bound, workers, *, incumbent=None, candidate=None):
    incumbent = incumbent or policy()
    candidate = candidate or policy(backend="headroom")
    host = Host(workers)
    host.expected_workers = sum(p.backend == "headroom" for p in (incumbent, candidate))
    cfg = OptimizerConfig(measurement=reference_measurement(), oracle_id="private-oracle-v1",
                          workload_id="fixed-test-v1", model_id=Transport.model, environment_id="profile-test-v1",
                          token_cap=10000, calls_per_pair=4, max_calls=100, synthetic_only=True)
    manifest = ProfileLearningManifest(cfg, host.identity, (("fresh", host.task_digest("fresh")),), 2,
                                       resources_id=bound.resources.identity)
    evaluator = RuntimePairEvaluator(manifest, host=host, output_root=tmp_path / "pairs", resources=bound.resources)
    trial = FrozenTrial(1, 1, 1, cfg.comparison(candidate.policy_id, incumbent.policy_id),
                        incumbent, candidate, 1, 4)
    return host, manifest, evaluator, trial


def read(path):
    return json.loads(path.read_text("utf-8"))


def test_legacy_manifest_bytes_and_identity_are_unchanged(bound, tmp_path, workers):
    host, profile, _, _ = setup(tmp_path, bound, workers)
    legacy = RuntimeLearningManifest(profile.config, host.identity, profile.task_digests, 2)
    old = {"version": learning_runtime.VERSION, **asdict(legacy)}
    assert legacy.to_dict() == old and legacy.identity == sha(wire(old))
    assert profile.identity != legacy.identity and profile.to_dict()["version"] == learning_runtime.PROFILE_VERSION
    assert profile.to_dict()["resources_id"] == bound.resources.identity
    with pytest.raises(FrozenInstanceError):
        profile.resources_id = "changed"
    with pytest.raises(ValueError):
        replace(profile, catalog_version="unrecognized")


@pytest.mark.parametrize("selection", ["headroom", "ponytail", "combined"])
def test_actual_policy_and_resource_identity_at_creation_and_both_ready_before_send(
        bound, workers, tmp_path, selection):
    incumbent = policy(backend="headroom", headroom_time_budget_seconds=5) if selection == "combined" else policy()
    candidate = replace(incumbent, instruction="ponytail") if selection != "headroom" else policy(backend="headroom")
    host, manifest, evaluate, trial = setup(tmp_path, bound, workers, incumbent=incumbent, candidate=candidate)
    result = evaluate(trial, "fresh")
    result.validate(trial.comparison)
    assert result.incumbent_outcome.success and result.candidate_outcome.success
    assert len(host.sessions) == 2
    for name, trace in (("incumbent", result.incumbent), ("candidate", result.candidate)):
        session = host.sessions[name]
        intended = getattr(trial, name)
        assert trace.policy_id == session.policy_id == intended.policy_id
        assert trace.task_id == session.task_id == "fresh" and trace.learning_run_id == trial.learning_run_id
        assert session.profile["runtime_policy"] == intended.to_dict()
        assert session.profile["runtime_resources_id"] == manifest.resources_id
        assert trace.calls[0].call_id == session.run_id + ":1"
        assert session._closed
        if intended.backend == intended.instruction == "none":
            preparation = json.loads((session.output / "preparations.jsonl").read_text().splitlines()[0])
            assert preparation["original"] == preparation["prepared"]
        if intended.instruction == "ponytail":
            assert session.ponytail.instructions_sha256 == intended.ponytail_instructions_sha256
    assert result.incumbent.calls[0].call_id != result.candidate.calls[0].call_id
    assert all(w.closed for w in workers["objects"])
    if selection == "combined":
        assert all(w.options["time_budget_seconds"] == 5 for w in workers["objects"])
    frozen = read(evaluate.output_root / "learning-manifest.json")
    plan = read(next(evaluate.output_root.glob("task-*/pair-plan.json")))
    assert frozen["kind"] == plan["kind"] == "profile"
    assert frozen["resources"] == bound.resources.to_manifest()
    assert candidate.to_dict() in plan["catalog"]


@pytest.mark.parametrize("failure", ["fail", "interrupt"])
def test_candidate_warmup_failure_keeps_both_empty_native_traces_and_no_primary(bound, workers, tmp_path, failure):
    host, _, evaluate, trial = setup(tmp_path, bound, workers)
    workers["fail_start" if failure == "fail" else "interrupt_start"] = 1
    expected = EvaluationAttemptFailed if failure == "fail" else EvaluationAttemptInterrupted
    with pytest.raises(expected) as caught:
        evaluate(trial, "fresh")
    assert not any(e[0] == "send" for e in host.events)
    assert len(caught.value.traces) == 2 and all(t.calls == () for t in caught.value.traces)
    assert {t.policy_id for t in caught.value.traces} == {trial.incumbent.policy_id, trial.candidate.policy_id}
    assert all(t.task_id == "fresh" and t.learning_run_id == "trial-1" for t in caught.value.traces)
    assert caught.value.receipt_sha256s and all(w.closed for w in workers["objects"])
    assert len(list(evaluate.output_root.rglob("cleanup.json"))) == 2
    assert not list(evaluate.output_root.rglob("observation.json"))


@pytest.mark.parametrize("failure", ["partial", "interrupt"])
def test_two_started_workers_retain_completed_incumbent_cost_when_candidate_fails(bound, workers, tmp_path, failure):
    incumbent = policy(backend="headroom", headroom_time_budget_seconds=4)
    host, _, evaluate, trial = setup(tmp_path, bound, workers, incumbent=incumbent,
                                    candidate=replace(incumbent, instruction="ponytail"))
    host.fail_arm, host.failure = "candidate", failure
    expected = EvaluationAttemptInterrupted if failure == "interrupt" else EvaluationAttemptFailed
    with pytest.raises(expected) as caught:
        evaluate(trial, "fresh")
    traces = {t.policy_id: t for t in caught.value.traces}
    assert traces[incumbent.policy_id].totals().total_tokens > 0
    partial = traces[trial.candidate.policy_id]
    assert partial.calls == () and len(partial.expected_call_ids) == 1 and partial.coverage == "partial"
    assert all(w.closed for w in workers["objects"]) and len(workers["objects"]) == 2
    assert workers["events"][:4] == [("construct", 1), ("start", 1), ("construct", 2), ("start", 2)]
    if failure == "interrupt":
        assert ("finish", 2) not in workers["events"]


def test_cancellation_before_first_send_skips_audits_for_ready_sibling(bound, workers, tmp_path):
    incumbent = policy(backend="headroom")
    host, _, evaluate, trial = setup(tmp_path, bound, workers, incumbent=incumbent,
                                    candidate=replace(incumbent, instruction="ponytail"))
    host.mutate = "drive_interrupt"
    with pytest.raises(EvaluationAttemptInterrupted) as caught:
        evaluate(trial, "fresh")
    assert len(caught.value.traces) == 2 and all(t.calls == () for t in caught.value.traces)
    assert len(workers["objects"]) == 2 and all(w.closed for w in workers["objects"])
    assert not any(e[0] in ("finish", "prepare") for e in workers["events"])


def test_resource_identity_and_drift_reject_before_requests(bound, workers, tmp_path):
    host, manifest, evaluate, trial = setup(tmp_path, bound, workers)
    with pytest.raises(ValueError, match="matching_runtime_resources"):
        RuntimePairEvaluator(manifest, host=host, output_root=tmp_path / "wrong", resources=RuntimeResources())
    assert not (tmp_path / "wrong").exists()
    bound.export.write_text("changed", encoding="utf-8")
    with pytest.raises(EvaluationAttemptFailed):
        evaluate(trial, "fresh")
    assert host.events == [] and workers["objects"] == []


def test_missing_selected_component_asset_fails_before_either_primary(workers, tmp_path):
    empty = SimpleNamespace(resources=RuntimeResources())
    host, _, evaluate, trial = setup(tmp_path, empty, workers)
    with pytest.raises(EvaluationAttemptFailed) as caught:
        evaluate(trial, "fresh")
    assert host.events == [] and workers["objects"] == [] and caught.value.traces == ()


def test_second_of_two_worker_startups_fails_before_first_primary(bound, workers, tmp_path):
    incumbent = policy(backend="headroom")
    host, _, evaluate, trial = setup(tmp_path, bound, workers, incumbent=incumbent,
                                    candidate=replace(incumbent, instruction="ponytail"))
    workers["fail_start"] = 2
    with pytest.raises(EvaluationAttemptFailed) as caught:
        evaluate(trial, "fresh")
    assert not any(e[0] == "send" for e in host.events)
    assert len(caught.value.traces) == 2 and all(t.calls == () for t in caught.value.traces)
    assert len(workers["objects"]) == 2 and all(w.closed for w in workers["objects"])


@pytest.mark.parametrize("failure", ["cleanup", "inventory"])
def test_component_failure_retains_primary_costs_without_quality_label(bound, workers, tmp_path, failure):
    incumbent = policy(backend="headroom")
    host, _, evaluate, trial = setup(tmp_path, bound, workers, incumbent=incumbent,
                                    candidate=replace(incumbent, instruction="ponytail"))
    workers["fail_close" if failure == "cleanup" else "incomplete_inventory"] = True
    with pytest.raises(EvaluationAttemptFailed) as caught:
        evaluate(trial, "fresh")
    assert sum(len(t.calls) for t in caught.value.traces) == 1
    assert all(w.closed for w in workers["objects"])
    assert not list(evaluate.output_root.rglob("observation.json"))


@pytest.mark.parametrize("mutation", ["resource", "capture", "unknown", "readiness"])
def test_postcall_verification_fails_closed_retaining_known_cost(bound, workers, tmp_path, mutation):
    host, _, evaluate, trial = setup(tmp_path, bound, workers)
    host.mutate, host.resource_file = mutation, bound.export
    with pytest.raises(EvaluationAttemptFailed) as caught:
        evaluate(trial, "fresh")
    assert sum(len(t.calls) for t in caught.value.traces) >= 1
    assert all(w.closed for w in workers["objects"])
    assert not list(evaluate.output_root.rglob("observation.json"))


def test_transport_mismatch_is_rejected_before_any_worker_or_send(bound, workers, tmp_path):
    host, _, evaluate, trial = setup(tmp_path, bound, workers)
    host.wrong_transport = True
    with pytest.raises(EvaluationAttemptFailed):
        evaluate(trial, "fresh")
    assert workers["objects"] == [] and not any(e[0] == "send" for e in host.events)


def test_mixed_families_and_non_neighbor_are_rejected_before_preparation(bound, workers, tmp_path):
    host, _, evaluate, trial = setup(tmp_path, bound, workers)
    legacy = RequestPolicy(version="request-policy-v3", enabled=True)
    with pytest.raises(ValueError):
        evaluate(replace(trial, candidate=legacy,
                         comparison=evaluate.manifest.config.comparison(legacy.policy_id, trial.incumbent.policy_id)), "fresh")
    composite = policy(backend="headroom", instruction="ponytail")
    with pytest.raises(ValueError, match="not_current_neighbor"):
        evaluate(replace(trial, candidate=composite,
                         comparison=evaluate.manifest.config.comparison(composite.policy_id, trial.incumbent.policy_id)), "fresh")
    assert host.events == []


def test_independently_checked_wrong_answer_is_valid_negative_observation(bound, workers, tmp_path):
    host, _, evaluate, trial = setup(tmp_path, bound, workers)
    host.success = False
    result = evaluate(trial, "fresh")
    result.validate(trial.comparison)
    assert result.incumbent_outcome.success is result.candidate_outcome.success is False


def test_learn_once_true_off_registry_retains_gate_and_never_promotes(bound, workers, tmp_path):
    host, manifest, evaluate, _ = setup(tmp_path, bound, workers, candidate=policy(instruction="ponytail"))
    host.expected_workers = 0  # The deterministic first neighbor is instruction-only.
    optimizer = Optimizer(tmp_path / "registry.sqlite", config=manifest.config, evaluator=evaluate)

    def safety_only(baseline, cfg, reserved):
        return BaselineValidation(baseline.policy_id, cfg.identity, cfg.oracle_id, True, sha("safety-only"),
                                  TaskTrace(reserved.task_id, baseline.policy_id, cfg.measurement, "learning",
                                            (), (), COMPLETE, reserved.learning_run_id))

    initial = optimizer.initialize(policy(), validator=safety_only, validation_call_limit=0)
    result = learn_once(optimizer, task_ids=["fresh"], samples=1)
    assert result["status"] == "not_certified" and result["policy_promoted"] is False
    assert optimizer.status()["champion"] == initial["champion"]
    assert optimizer.status()["learning"]["complete_calls"] == 2


def controller(tmp_path, manifest, evaluate):
    optimizer = Optimizer(tmp_path / "registry.sqlite", config=manifest.config, evaluator=evaluate)

    def safety_only(baseline, cfg, reserved):
        return BaselineValidation(baseline.policy_id, cfg.identity, cfg.oracle_id, True, sha("safety-only"),
                                  TaskTrace(reserved.task_id, baseline.policy_id, cfg.measurement, "learning",
                                            (), (), COMPLETE, reserved.learning_run_id))

    optimizer.initialize(policy(), validator=safety_only, validation_call_limit=0)
    return optimizer


def test_explicit_candidate_selects_proposed_headroom_before_freezing_without_screening(bound, workers, tmp_path):
    host, manifest, evaluate, example = setup(tmp_path, bound, workers)
    optimizer = controller(tmp_path, manifest, evaluate)
    expected = example.candidate.policy_id
    candidates = optimizer.propose()
    assert candidates[0].policy_id != expected and expected in {p.policy_id for p in candidates}
    # Same preflight used by the CLI; it is not a reservation or bypass.
    receipt = optimizer.preflight_learning(["fresh"], screening=False)
    result = learn_once(optimizer, task_ids=receipt["task_ids"], samples=1, candidate_id=expected)
    assert result["candidate_id"] == expected and result["status"] == "not_certified"
    assert not result["policy_promoted"]
    assert optimizer.status()["champion"]["policy_id"] == policy().policy_id
    assert optimizer.status()["learning"]["complete_calls"] == 2
    assert host.sessions["candidate"].backend == "headroom" and len(workers["objects"]) == 1
    assert not any(r["kind"] == "screening" for r in optimizer.learning_inventory()["runs"])


@pytest.mark.parametrize("choice", ["unknown", True, 123, []])
def test_invalid_explicit_candidate_does_not_freeze_or_dispatch(bound, workers, tmp_path, choice):
    host, manifest, evaluate, _ = setup(tmp_path, bound, workers)
    optimizer = controller(tmp_path, manifest, evaluate)
    with pytest.raises(ValueError, match="explicit_candidate"):
        learn_once(optimizer, task_ids=["fresh"], samples=1, candidate_id=choice)
    assert host.events == [] and workers["objects"] == []
    assert optimizer.status()["trials"] == [] and optimizer.status()["budget"]["rounds"] == 0


@pytest.mark.parametrize("mix", ["screener", "summaries", "classification"])
def test_explicit_candidate_rejects_screening_mix_before_proposals_or_calls(bound, workers, tmp_path, monkeypatch, mix):
    host, manifest, evaluate, example = setup(tmp_path, bound, workers)
    optimizer = controller(tmp_path, manifest, evaluate)

    def forbidden(*args, **kwargs):
        pytest.fail("must reject screening mix before proposing or screening")

    monkeypatch.setattr(optimizer, "propose", forbidden)
    options: dict[str, Any] = {"screener": SimpleNamespace(decide=forbidden)} if mix == "screener" else (
        {"summaries": {}} if mix == "summaries" else {"data_classification": "sanitized"})
    with pytest.raises(ValueError, match="explicit_candidate_screening_conflict"):
        learn_once(optimizer, task_ids=["fresh"], samples=1, candidate_id=example.candidate.policy_id, **options)
    assert host.events == [] and workers["objects"] == [] and optimizer.status()["trials"] == []


@pytest.mark.parametrize("permanent", [False, True])
def test_interrupted_component_close_is_not_settled_and_pair_unwind_is_bounded(
        bound, workers, tmp_path, monkeypatch, permanent):
    class FirstCancellation(KeyboardInterrupt):
        pass

    class LaterCancellation(KeyboardInterrupt):
        pass

    original = FirstCancellation("preserve first interruption")
    incumbent = policy(backend="headroom")
    host, _, evaluate, trial = setup(tmp_path, bound, workers, incumbent=incumbent,
                                    candidate=replace(incumbent, instruction="ponytail"))
    component_type = headroom.HeadroomContainer
    real_close = component_type.close
    attempts: dict[int, int] = {}

    def interrupt_close(self):
        attempts[self.number] = attempts.get(self.number, 0) + 1
        assert sum(event[0] == "start" for event in workers["events"]) == 2
        if self.number == 1 and attempts[self.number] == 1:
            raise original
        if self.number == 1 and permanent:
            raise LaterCancellation("second interruption must not replace the first")
        return real_close(self)

    monkeypatch.setattr(component_type, "close", interrupt_close)
    sessions, lease_attempts, finish_attempts = [], [], []
    prepare, release, finish = RuntimeSession.prepare_components, CCR.release_session, RuntimeSession.finish

    def prepare_with_lease(self):
        sessions.append(self)
        self.ccr.stash("owned cleanup test content", source="note.txt", ctype="source")
        return prepare(self)

    def release_with_receipt(self):
        lease_attempts.append(self)
        return release(self)

    def finish_once(self, **kwargs):
        finish_attempts.append(self)
        return finish(self, **kwargs)

    monkeypatch.setattr(RuntimeSession, "prepare_components", prepare_with_lease)
    monkeypatch.setattr(CCR, "release_session", release_with_receipt)
    monkeypatch.setattr(RuntimeSession, "finish", finish_once)
    with pytest.raises(EvaluationAttemptInterrupted) as caught:
        evaluate(trial, "fresh")
    assert caught.value.__context__ is original
    assert attempts == {1: 2, 2: 1}
    assert len(sessions) == 2
    assert [event for event in host.events if event[0] == "drive"] == [("drive", "incumbent")]
    assert [event for event in host.events if event[0] == "send"] == [("send", "incumbent")]
    assert sum(event[0] == "start" for event in workers["events"]) == 2
    assert ("finish", 2) not in workers["events"]  # No post-cancel sibling audit.
    assert len(caught.value.traces) == 2 and sum(len(t.calls) for t in caught.value.traces) == 1
    assert lease_attempts.count(sessions[0].ccr) == 2
    assert lease_attempts.count(sessions[1].ccr) == 1
    assert finish_attempts.count(sessions[0]) == finish_attempts.count(sessions[1]) == 1
    failed = read(next(evaluate.output_root.glob("task-*/attempt-failed.json")))
    assert failed["error_type"] == "FirstCancellation" and failed["reason"] == "interrupted"
    cleanup = failed["cleanup"]
    assert len(cleanup["incumbent"]["attempts"]) == 2 and len(cleanup["candidate"]["attempts"]) == 1
    assert cleanup["incumbent"]["attempts"][0]["error_type"] == "FirstCancellation"
    assert cleanup["incumbent"]["attempts"][0]["settled"] is False
    assert cleanup["incumbent"]["attempts"][0]["receipt_file"] == "cleanup.json"
    assert cleanup["incumbent"]["attempts"][1]["receipt_file"] == "cleanup-retry-2.json"
    assert cleanup["incumbent"]["settled"] is (not permanent)
    assert cleanup["incumbent"]["resource_state"] == ("unknown" if permanent else "released")
    assert cleanup["candidate"]["settled"] is True
    assert failed["unknown_cleanup_arms"] == (["incumbent"] if permanent else [])
    assert workers["objects"][0].closed is (not permanent)
    assert workers["objects"][1].closed is True
    for session in sessions:
        receipt = read(session.output / "cleanup.json")
        assert "released_leases" in receipt
    assert read(sessions[0].output / "cleanup.json")["complete"] is False
    assert read(sessions[0].output / "cleanup-retry-2.json")["complete"] is (not permanent)
    assert sessions[0].cleanup_settled is (not permanent)
    assert not list(evaluate.output_root.rglob("observation.json"))


def test_closed_flag_and_reported_complete_cannot_replace_durable_cleanup_proof(
        bound, workers, tmp_path, monkeypatch):
    incumbent = policy(backend="headroom")
    host, _, evaluate, trial = setup(tmp_path, bound, workers, incumbent=incumbent,
                                    candidate=replace(incumbent, instruction="ponytail"))
    real_close = RuntimeSession.close

    def corrupt_receipt(self):
        result = real_close(self)
        if self.output.parent.name == "incumbent":
            (self.output / "cleanup.json").write_text("{}", encoding="utf-8")
        return result

    monkeypatch.setattr(RuntimeSession, "close", corrupt_receipt)
    with pytest.raises(EvaluationAttemptFailed) as caught:
        evaluate(trial, "fresh")
    failed = read(next(evaluate.output_root.glob("task-*/attempt-failed.json")))
    failed_arm = failed["cleanup"]["incumbent"]
    assert failed_arm["settled"] is False and failed_arm["resource_state"] == "unknown"
    assert len(failed_arm["attempts"]) == 2
    assert all(item["closed"] and item["runtime_cleanup_settled"] for item in failed_arm["attempts"])
    assert not any(item["durable_receipt_verified"] for item in failed_arm["attempts"])
    assert failed["cleanup"]["candidate"]["settled"] is True
    assert sum(len(t.calls) for t in caught.value.traces) == 1
    assert len([e for e in host.events if e[0] == "send"]) == 1
    assert all(worker.closed for worker in workers["objects"])
    assert not list(evaluate.output_root.rglob("observation.json"))
