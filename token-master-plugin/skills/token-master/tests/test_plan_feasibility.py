"""Offline diagnostics only: every SQLite database here is a new temp fixture."""
from contextlib import closing
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from brainspace.certification import radius, round_alpha
from brainspace.optimizer import Optimizer, OptimizerConfig, OptimizerError
from brainspace.request_policy import RequestPolicy
from brainspace.token_ledger import MeasurementIdentity
import token_efficiency as cli


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def reject(*args, **kwargs):
        pytest.fail("offline feasibility tests must not open connections")

    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket, "create_connection", reject)


def calculate(**changes):
    from brainspace.plan_feasibility import fixed_plan_feasibility
    return fixed_plan_feasibility(**{
        "alpha": 0.05, "round_index": 1, "sample_size": 8,
        "token_cap": 100000, "minimum_token_reduction": 1, **changes,
    })


def fixture_db(tmp_path, **changes):
    """Data-only current schema; never initialize a real controller/evaluator."""
    config = OptimizerConfig(
        measurement=MeasurementIdentity("fixture", "1", "fixture", "fixture", "1", "fixture"),
        oracle_id="fixture", workload_id="fixture", model_id="fixture",
        environment_id="fixture", token_cap=100000, **changes,
    )
    path = tmp_path / "controller.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE config (id INTEGER PRIMARY KEY, value TEXT, registry_id TEXT);
            CREATE TABLE opt_config (id INTEGER PRIMARY KEY, value TEXT);
            CREATE TABLE opt_accounting (id INTEGER PRIMARY KEY, version INTEGER);
            CREATE TABLE rounds (k INTEGER PRIMARY KEY AUTOINCREMENT, spec TEXT,
                                 mode TEXT, sample_size INTEGER, state TEXT);
            CREATE TABLE opt_trials (id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id INTEGER, incumbent_id TEXT, candidate_id TEXT, sample_size INTEGER,
                spec_json TEXT, state TEXT);
            CREATE TABLE opt_learning (kind TEXT);
            CREATE TABLE opt_baseline_attempts (call_limit INTEGER, reported_calls INTEGER);
            CREATE TABLE opt_champion (id INTEGER PRIMARY KEY, policy_id TEXT, version INTEGER);
            CREATE TABLE opt_policies (policy_id TEXT PRIMARY KEY, policy_json TEXT);
            CREATE TABLE tasks (task_hash TEXT PRIMARY KEY, round_id INTEGER, kind TEXT);
        """)
        db.execute("INSERT INTO opt_config VALUES(1,?)", (json.dumps(asdict(config)),))
        db.execute("INSERT INTO opt_accounting VALUES(1,2)")
        db.execute("INSERT INTO config VALUES(1,?,'fixture-registry')", (json.dumps({
            "schema_version": 1, "alpha": config.alpha, "trusted_oracle_id": config.oracle_id,
            "gate": "strict-paired-hoeffding-v1",
        }),))
        policy = RequestPolicy()
        db.execute("INSERT INTO opt_policies VALUES(?,?)", (policy.policy_id, policy.to_json()))
        db.execute("INSERT INTO opt_champion VALUES(1,?,1)", (policy.policy_id,))
    return path, config


def snapshot(path, **kwargs):
    return Optimizer.plan_feasibility_snapshot(path, **kwargs)


def fingerprint(path):
    return {
        p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns,
                 p.stat().st_ctime_ns, p.stat().st_size)
        for p in path.parent.iterdir() if p.is_file()
    }


def test_eight_impossible_nine_not_ruled_out_and_equal_quality_never_passes():
    report = calculate()
    assert report["status"] == "mathematically_impossible"
    assert report["minimum_samples"] == 9
    assert report["radius"] == radius(0.05, 1, 8)
    assert report["alpha_round"] == round_alpha(0.05, 1)
    assert calculate(sample_size=9)["status"] == "not_ruled_out"
    assert report["equal_observed_quality_can_pass"] is False
    assert report["certificate"] is False and report["authority"] is False
    for n in (1, 8, 9, 1000000, 2**63 - 1):
        assert 0 - radius(.05, 1, n) < 0


@pytest.mark.parametrize("k", [1, 2, 6, 50, 2**63 - 1])
def test_minimum_matches_actual_gate_and_predecessor(k):
    report = calculate(round_index=k)
    n = report["minimum_samples"]
    assert n is not None
    assert radius(.05, k, n) <= 1
    assert -1 + radius(.05, k, n) <= -1 / 100000
    assert -1 + radius(.05, k, n - 1) > -1 / 100000
    assert calculate(round_index=k, sample_size=n)["status"] == "not_ruled_out"


def test_full_cap_saving_impossible_and_extreme_margin_is_not_false_feasibility():
    assert calculate(minimum_token_reduction=100000)["minimum_samples"] is None
    assert calculate(minimum_token_reduction=100000)["status"] == "mathematically_impossible"
    report = calculate(token_cap=2**63 - 1, minimum_token_reduction=2**63 - 2)
    assert report["status"] == "mathematically_impossible"
    assert report["minimum_samples"] is None
    assert report["numerical_limitations"]


@pytest.mark.parametrize(("field", "value"), [
    ("sample_size", True), ("sample_size", 0), ("sample_size", 2**63),
    ("sample_size", 8.0), ("round_index", False), ("round_index", 0),
    ("round_index", 2**63), ("token_cap", True), ("token_cap", 2**63),
    ("alpha", True), ("alpha", 0), ("alpha", float("nan")), ("alpha", float("inf")),
    ("minimum_token_reduction", True), ("minimum_token_reduction", 0),
    ("minimum_token_reduction", 100001), ("minimum_token_reduction", float("nan")),
])
def test_closed_scalar_validation(field, value):
    with pytest.raises(ValueError):
        calculate(**{field: value})


def test_subnormal_ratio_and_near_boundary_report_numerical_limitations():
    report = calculate(minimum_token_reduction=5e-324)
    assert report["status"] == "numerically_indeterminate"
    boundary_eta = 100000 * (1 - radius(.05, 1, 9))
    report = calculate(sample_size=9, minimum_token_reduction=boundary_eta)
    assert report["status"] == "numerically_indeterminate"
    assert report["minimum_samples"] is None


def test_allocation_underflow_is_a_numeric_gap_not_feasibility():
    report = calculate(alpha=5e-324, round_index=2**63 - 1)
    assert report["status"] == "numerically_indeterminate"
    assert report["alpha_round"] is None
    assert report["minimum_samples"] is None and report["numerical_limitations"]
    json.dumps(report, allow_nan=False)


def test_controller_limit_is_not_silently_raised():
    report = calculate(minimum_token_reduction=99999)
    assert report["minimum_samples"] > report["controller_sample_limit"]
    assert report["controller_sample_limit"] == 1000000


def test_snapshot_does_not_open_controller_or_change_any_bytes_metadata(tmp_path, monkeypatch):
    path, config = fixture_db(tmp_path)
    before = fingerprint(path)
    monkeypatch.setattr(Optimizer, "open", lambda *a, **k: pytest.fail("mutating open"))
    report = snapshot(path, sample_size=8)
    assert report["config_id"] == config.identity
    assert report["round_index"] == 1
    assert report["arithmetic"]["status"] == "mathematically_impossible"
    assert report["budget"]["status"] == "within_snapshot_allocation"
    assert report["candidate"]["status"] == "available_at_snapshot"
    assert report["freshness"] == report["native_comparability"] == "UNVERIFIED"
    assert report["reservation"] is False and report["future_budget_guarantee"] is False
    assert fingerprint(path) == before


def test_missing_registry_never_created(tmp_path):
    path = tmp_path / "missing.sqlite"
    with pytest.raises(OptimizerError, match="not_initialized"):
        snapshot(path, sample_size=8)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_sidecars_refused_explicitly_without_modification(tmp_path, suffix):
    path, _ = fixture_db(tmp_path)
    Path(str(path) + suffix).write_bytes(b"uncheckpointed-or-unknown")
    before = fingerprint(path)
    with pytest.raises(OptimizerError, match="active_sqlite_sidecar"):
        snapshot(path, sample_size=8)
    assert fingerprint(path) == before


def test_live_wal_is_not_silently_ignored(tmp_path):
    path, _ = fixture_db(tmp_path)
    with sqlite3.connect(path) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("INSERT INTO opt_learning VALUES('screening')")
        writer.commit()
        before = fingerprint(path)
        with pytest.raises(OptimizerError, match="active_sqlite_sidecar"):
            snapshot(path, sample_size=8)
        assert fingerprint(path) == before


def test_round_sequence_not_trial_count_and_existing_trial_uses_allocated_round(tmp_path):
    path, config = fixture_db(tmp_path)
    spec = asdict(config.comparison("candidate", "incumbent"))
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO rounds VALUES(12,?,'fixed',9,'closed')", (json.dumps(spec),))
        db.execute("INSERT INTO opt_trials VALUES(1,12,'incumbent','candidate',9,?,'failed')",
                   (json.dumps(spec),))
        db.execute("UPDATE sqlite_sequence SET seq=20 WHERE name='rounds'")
    assert snapshot(path, sample_size=9)["round_index"] == 21
    before = fingerprint(path)
    report = snapshot(path, trial_id=1)
    assert report["round_index"] == 12 and report["sample_size"] == 9
    assert report["round_source"] == "existing_trial"
    assert report["budget"]["additional_required_call_slots"] == 0
    assert fingerprint(path) == before


@pytest.mark.parametrize("current_state", ["promoted", "rolled_back"])
@pytest.mark.parametrize("has_frozen_version", [True, False])
def test_historical_trial_uses_frozen_comparison_not_current_champion(
        tmp_path, current_state, has_frozen_version):
    from brainspace.request_policy import policy_neighbors
    path, config = fixture_db(tmp_path)
    incumbent = RequestPolicy()
    candidate = policy_neighbors(incumbent)[0]
    comparison = config.comparison(candidate.policy_id, incumbent.policy_id)
    frozen_spec = asdict(comparison)
    current = candidate if current_state == "promoted" else incumbent
    current_version = 2 if current_state == "promoted" else 3
    with closing(sqlite3.connect(path)) as db, db:
        if has_frozen_version:
            db.execute("ALTER TABLE opt_trials ADD COLUMN incumbent_version INTEGER")
        db.execute("INSERT INTO rounds VALUES(4,?,'fixed',32,'closed')",
                   (json.dumps(frozen_spec),))
        db.execute(
            """INSERT INTO opt_trials
               (id,round_id,incumbent_id,candidate_id,sample_size,spec_json,state)
               VALUES(1,4,?,?,32,?,'promoted')""",
            (incumbent.policy_id, candidate.policy_id, json.dumps(frozen_spec)))
        if has_frozen_version:
            db.execute("UPDATE opt_trials SET incumbent_version=1 WHERE id=1")
        db.execute("INSERT INTO opt_policies VALUES(?,?)", (candidate.policy_id, candidate.to_json()))
        db.execute("UPDATE opt_champion SET policy_id=?,version=?",
                   (current.policy_id, current_version))
        db.execute("UPDATE sqlite_sequence SET seq=9 WHERE name='rounds'")
    before = fingerprint(path)
    report = snapshot(path, trial_id=1)
    assert report["incumbent_id"] == incumbent.policy_id
    assert report["candidate_id"] == candidate.policy_id
    assert report["comparison"] == frozen_spec
    assert report["comparison_id"] == comparison.identity
    assert report["current_champion"] == {"policy_id": current.policy_id, "version": current_version}
    assert report["incumbent_version"] == (1 if has_frozen_version else None)
    assert report["incumbent_version_source"] == ("frozen_trial" if has_frozen_version else "unknown")
    assert report["candidate"]["scope"] == "current_champion_snapshot"
    assert report["round_index"] == 4 and report["sample_size"] == 32
    assert report["arithmetic"]["radius"] == radius(config.alpha, 4, 32)
    assert report["budget"]["additional_required_call_slots"] == 0
    assert report["certificate"] is False and report["authority"] is False
    assert fingerprint(path) == before


@pytest.mark.parametrize(("target", "field", "value", "reason"), [
    ("registry", "schema_version", True, "configuration_changed"),
    ("registry", "schema_version", 1.0, "configuration_changed"),
    ("round", "minimum_token_reduction", True, "invalid_trial"),
    ("trial", "minimum_token_reduction", True, "invalid_trial"),
    ("both", "minimum_token_reduction", True, "invalid_trial"),
    ("round", "minimum_token_reduction", 1.0, "invalid_trial"),
    ("round", "measurement.schema_version", True, "invalid_trial"),
    # Ordinary value-corruption controls from the independent review.
    ("registry", "schema_version", 2, "configuration_changed"),
    ("round", "minimum_token_reduction", 2, "invalid_trial"),
    # Both persisted specs must also match the typed frozen config.
    ("both", "minimum_token_reduction", 1.0, "invalid_trial"),
    ("both", "measurement.schema_version", 1.0, "invalid_trial"),
])
def test_persisted_identity_rejects_coercive_json_equality(tmp_path, target, field, value, reason):
    path, config = fixture_db(tmp_path)
    spec = asdict(config.comparison("candidate", "incumbent"))
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("INSERT INTO rounds VALUES(1,?,'fixed',9,'closed')", (json.dumps(spec),))
        db.execute("INSERT INTO opt_trials VALUES(1,1,'incumbent','candidate',9,?,'failed')",
                   (json.dumps(spec),))
        targets = {
            "registry": [("config", "value")],
            "round": [("rounds", "spec")],
            "trial": [("opt_trials", "spec_json")],
            "both": [("rounds", "spec"), ("opt_trials", "spec_json")],
        }[target]
        for table, column in targets:
            data = json.loads(db.execute(f"SELECT {column} FROM {table}").fetchone()[0])
            if field == "measurement.schema_version":
                data["measurement"]["schema_version"] = value
            else:
                data[field] = value
            db.execute(f"UPDATE {table} SET {column}=?", (json.dumps(data),))
    before = fingerprint(path)
    with pytest.raises(OptimizerError, match=f"^{reason}$"):
        snapshot(path, **({"sample_size": 9} if target == "registry" else {"trial_id": 1}))
    assert fingerprint(path) == before


@pytest.mark.parametrize("eta", [1, 1.0])
def test_valid_frozen_numeric_representation_is_preserved_not_normalized(tmp_path, eta):
    path, config = fixture_db(tmp_path, minimum_token_reduction=eta)
    comparison = config.comparison("candidate", "incumbent")
    spec = asdict(comparison)
    with closing(sqlite3.connect(path)) as db, db:
        # Formatting/key order is not identity; JSON scalar types are.
        db.execute("INSERT INTO rounds VALUES(1,?,'fixed',9,'closed')",
                   (json.dumps(spec, sort_keys=True, indent=2),))
        db.execute("INSERT INTO opt_trials VALUES(1,1,'incumbent','candidate',9,?,'failed')",
                   (json.dumps(spec),))
    before = fingerprint(path)
    report = snapshot(path, trial_id=1)
    assert report["comparison_id"] == comparison.identity
    assert type(report["comparison"]["minimum_token_reduction"]) is type(eta)
    assert report["comparison"]["minimum_token_reduction"] == eta
    assert report["config_id"] == config.identity
    assert fingerprint(path) == before


def test_failed_allocations_baselines_screening_and_candidate_capacity_retained(tmp_path):
    path, _ = fixture_db(tmp_path, max_calls=25, calls_per_pair=2, max_candidates=1)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO opt_trials VALUES(1,NULL,'old','c',8,'{}','failed')")
        db.execute("INSERT INTO opt_learning VALUES('screening')")
        db.execute("INSERT INTO opt_baseline_attempts VALUES(1,4)")
    report = snapshot(path, sample_size=2, screening=True)
    assert report["budget"]["allocated_call_slots"] == 21
    assert report["budget"]["additional_required_call_slots"] == 5
    assert report["budget"]["status"] == "budget_exhausted"
    assert report["budget"]["affordable_samples"] == 1
    assert report["candidate"]["status"] == "candidate_unavailable"


def test_tried_neighbors_unavailable_without_reset(tmp_path):
    from brainspace.request_policy import policy_neighbors
    path, _ = fixture_db(tmp_path, max_candidates=1000)
    policy = RequestPolicy()
    with sqlite3.connect(path) as db:
        for i, neighbor in enumerate(policy_neighbors(policy), 1):
            db.execute("INSERT INTO opt_trials VALUES(?,NULL,?,?,1,'{}','failed')",
                       (i, policy.policy_id, neighbor.policy_id))
    assert snapshot(path, sample_size=9)["candidate"]["status"] == "candidate_unavailable"


def test_true_off_profile_identity_and_neighbor_space_are_not_rewritten(tmp_path):
    from brainspace.runtime_policy import RuntimePolicy, controller_policy_neighbors
    path, _ = fixture_db(tmp_path)
    policy = RuntimePolicy()
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO opt_policies VALUES(?,?)", (policy.policy_id, policy.to_json()))
        db.execute("UPDATE opt_champion SET policy_id=?", (policy.policy_id,))
    before = fingerprint(path)
    report = snapshot(path, sample_size=9)
    assert report["incumbent_id"] == policy.policy_id
    assert report["candidate"]["available_candidate_ids"] == sorted(
        p.policy_id for p in controller_policy_neighbors(policy))
    assert fingerprint(path) == before


@pytest.mark.parametrize("kwargs", [
    {}, {"sample_size": True}, {"sample_size": 1000001}, {"trial_id": True},
    {"trial_id": 2**63}, {"sample_size": 8, "trial_id": 1},
    {"sample_size": 8, "screening": 1}, {"trial_id": 1, "screening": True},
])
def test_snapshot_argument_validation(tmp_path, kwargs):
    path, _ = fixture_db(tmp_path)
    with pytest.raises(OptimizerError):
        snapshot(path, **kwargs)


def test_concurrent_change_is_detected_without_retry(tmp_path, monkeypatch):
    import brainspace.plan_feasibility as module
    path, _ = fixture_db(tmp_path)
    original = module.fixed_plan_feasibility
    calls = []

    def mutate(**kwargs):
        calls.append(1)
        with sqlite3.connect(path) as db:
            db.execute("INSERT INTO opt_learning VALUES('screening')")
        return original(**kwargs)

    monkeypatch.setattr(module, "fixed_plan_feasibility", mutate)
    with pytest.raises(OptimizerError, match="snapshot_changed"):
        snapshot(path, sample_size=8)
    assert calls == [1]


@pytest.mark.parametrize("change", ["bad_config", "bad_accounting", "bad_sequence", "bad_spec"])
def test_corrupt_snapshot_is_rejected_readonly(tmp_path, change):
    path, config = fixture_db(tmp_path)
    kwargs = {"sample_size": 8}
    with sqlite3.connect(path) as db:
        if change == "bad_config":
            db.execute("UPDATE opt_config SET value=?", ('{"alpha":0.05,"alpha":0.5}',))
        elif change == "bad_accounting":
            db.execute("UPDATE opt_accounting SET version=99")
        elif change == "bad_sequence":
            db.execute("INSERT INTO rounds VALUES(2,'{}','fixed',8,'closed')")
            db.execute("UPDATE sqlite_sequence SET seq=1 WHERE name='rounds'")
        else:
            spec = json.dumps(asdict(config.comparison("candidate", "incumbent")))
            db.execute("INSERT INTO rounds VALUES(2,'{}','fixed',8,'closed')")
            db.execute("INSERT INTO opt_trials VALUES(1,2,'incumbent','candidate',8,?,'failed')",
                       (spec,))
            kwargs = {"trial_id": 1}
    before = fingerprint(path)
    with pytest.raises(OptimizerError):
        snapshot(path, **kwargs)
    assert fingerprint(path) == before


def test_cli_diagnostic_has_no_open_or_side_effects(tmp_path, monkeypatch, capsys):
    path, _ = fixture_db(tmp_path)
    before = fingerprint(path)
    monkeypatch.setattr(Optimizer, "open", lambda *a, **k: pytest.fail("no open"))
    monkeypatch.setattr(cli, "_PolicyScreen", lambda *a, **k: pytest.fail("no screen"))
    assert cli.main(["--db", str(path), "plan-feasibility", "--samples", "8"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["arithmetic"]["status"] == "mathematically_impossible"
    assert fingerprint(path) == before


@pytest.mark.parametrize("command", ["learn-runtime", "learn-profile"])
def test_fresh_impossible_learning_rejects_before_screen_open_freeze_or_tasks(
        tmp_path, monkeypatch, command):
    from brainspace import learning_runtime
    from brainspace.runtime_resources import RuntimeResources
    path, config = fixture_db(tmp_path)
    before = fingerprint(path)
    host = SimpleNamespace(task_ids=("fresh-fixture-task",))
    manifest = SimpleNamespace(config=config)
    monkeypatch.setattr(cli, "_runtime_setup", lambda *a, **k: ({}, host, manifest))
    monkeypatch.setattr(Optimizer, "open", lambda *a, **k: pytest.fail("no mutable open"))
    monkeypatch.setattr(Optimizer, "freeze", lambda *a, **k: pytest.fail("no freeze"))
    monkeypatch.setattr(cli, "_PolicyScreen", lambda *a, **k: pytest.fail("no screen"))
    monkeypatch.setattr(learning_runtime, "RuntimePairEvaluator",
                        lambda *a, **k: pytest.fail("no evaluator"))
    monkeypatch.setattr(learning_runtime, "learn_once", lambda *a, **k: pytest.fail("no learning"))
    monkeypatch.setattr(RuntimeResources, "__init__", lambda self, **k: None)
    monkeypatch.setattr(RuntimeResources, "to_manifest", lambda self: {})
    # No API key or provider is needed to identify an impossible plan.
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    args = cli._parser().parse_args([
        "--db", str(path), command, "--manifest", "unused", "--output", str(tmp_path / "out"),
        "--model", "fixture", "--base-url", "http://127.0.0.1:1", "--allow-network",
        "--task-id", "fresh-fixture-task", "--jev",
        *(["--ponytail-export", "unused", "--headroom-cache", "unused",
           "--headroom-assets", "unused"] if command == "learn-profile" else []),
    ])
    with pytest.raises(OptimizerError, match="plan_mathematically_impossible"):
        cli.execute(args)
    assert fingerprint(path) == before and not (tmp_path / "out").exists()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_synthetic_confirm_demo_and_existing_replay_are_not_newly_guarded(tmp_path, monkeypatch):
    from evals import synthetic_efficiency
    events = []
    fake = SimpleNamespace(
        config=SimpleNamespace(synthetic_only=True, oracle_id=synthetic_efficiency.ORACLE),
        freeze=lambda *a, **k: (events.append("freeze") or SimpleNamespace(trial_id=1, sample_size=1)),
        evaluate=lambda *a, **k: (events.append("evaluate") or SimpleNamespace(to_dict=lambda: {})),
        hill_climb=lambda **k: (events.append("hill_climb") or {}),
    )
    monkeypatch.setattr(Optimizer, "open", lambda *a, **k: fake)
    monkeypatch.setattr(Optimizer, "plan_feasibility_snapshot",
                        lambda *a, **k: pytest.fail("legacy paths unchanged"))
    monkeypatch.setattr(cli, "_initialize", lambda *a: (fake, {}))
    cli.execute(cli._parser().parse_args([
        "--db", str(tmp_path / "unused"), "confirm", "candidate", "--samples", "1"]))
    cli.execute(cli._parser().parse_args([
        "--db", str(tmp_path / "unused"), "demo", "--synthetic", "--samples", "1"]))
    assert events == ["freeze", "evaluate", "hill_climb"]


def test_learning_rechecks_snapshot_after_admission_before_any_screen(tmp_path, monkeypatch):
    from brainspace import learning_runtime
    path, config = fixture_db(tmp_path)
    tasks = tuple(f"fresh-{i}" for i in range(9))
    manifest = SimpleNamespace(config=config)
    monkeypatch.setattr(cli, "_runtime_setup", lambda *a, **k: (
        {}, SimpleNamespace(task_ids=tasks), manifest))
    monkeypatch.setattr(cli, "_PolicyScreen", lambda *a, **k: pytest.fail("no screen"))
    monkeypatch.setattr(learning_runtime, "RuntimePairEvaluator",
                        lambda *a, **k: pytest.fail("no evaluator"))
    monkeypatch.setenv("TYPESAFE_API_KEY", "unused-test-placeholder")

    def preflight(*a, **k):
        # Simulate a concurrent allocation, not performed by the diagnostic.
        with sqlite3.connect(path) as db:
            db.execute("INSERT INTO opt_learning VALUES('screening')")
        return {"available_candidate_ids": []}

    monkeypatch.setattr(Optimizer, "open", lambda *a, **k: SimpleNamespace(
        config=config, preflight_learning=preflight))
    args = cli._parser().parse_args([
        "--db", str(path), "learn-runtime", "--manifest", "unused",
        "--output", str(tmp_path / "out"), "--model", "fixture",
        "--base-url", "http://127.0.0.1:1", "--allow-network", "--jev",
        *[arg for task in tasks for arg in ("--task-id", task)],
    ])
    with pytest.raises(OptimizerError, match="plan_snapshot_changed"):
        cli.execute(args)
    assert not (tmp_path / "out").exists()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_not_ruled_out_learning_still_uses_existing_admission_and_evaluation(tmp_path, monkeypatch):
    from brainspace import learning_runtime
    path, config = fixture_db(tmp_path)
    tasks = tuple(f"fresh-{i}" for i in range(9))
    output = tmp_path / "out"
    manifest = SimpleNamespace(config=config)
    events = []
    monkeypatch.setattr(cli, "_runtime_setup", lambda *a, **k: (
        {}, SimpleNamespace(task_ids=tasks), manifest))

    def preflight(ids, *, screening):
        events.append("admission")
        assert tuple(ids) == tasks and screening is False
        return {"available_candidate_ids": []}

    def evaluator(*a, **k):
        events.append("evaluator")
        output.mkdir()
        return object()

    def learning(optimizer, **kwargs):
        events.append("existing_learn_once")
        assert kwargs["task_ids"] == tasks and kwargs["samples"] == 9
        return {"status": "not_certified", "fixture_only": True}

    monkeypatch.setattr(Optimizer, "open", lambda *a, **k: SimpleNamespace(
        config=config, preflight_learning=preflight, status=lambda: {"fixture": True}))
    monkeypatch.setattr(learning_runtime, "RuntimePairEvaluator", evaluator)
    monkeypatch.setattr(learning_runtime, "learn_once", learning)
    monkeypatch.setattr(cli, "_PolicyScreen", lambda *a, **k: pytest.fail("no screen"))
    before = path.read_bytes()
    args = cli._parser().parse_args([
        "--db", str(path), "learn-runtime", "--manifest", "unused",
        "--output", str(output), "--model", "fixture",
        "--base-url", "http://127.0.0.1:1", "--allow-network",
        *[arg for task in tasks for arg in ("--task-id", task)],
    ])
    result = cli.execute(args)
    assert events == ["admission", "evaluator", "existing_learn_once"]
    assert result["plan_feasibility"]["arithmetic"]["status"] == "not_ruled_out"
    assert result["policy_promoted"] is False and result["step"]["status"] == "not_certified"
    assert path.read_bytes() == before


def test_cli_missing_registry_and_invalid_selectors_are_noncreating(tmp_path, capsys):
    path = tmp_path / "missing.sqlite"
    assert cli.main(["--db", str(path), "plan-feasibility", "--samples", "8"]) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "not_initialized"
    assert cli.main(["--db", str(path), "plan-feasibility",
                     "--samples", "8", "--trial-id", "1"]) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "invalid_arguments"
    assert list(tmp_path.iterdir()) == []


def test_installer_copy_includes_new_module_and_offline_cli(tmp_path):
    import brainspace_setup
    root = Path(cli.__file__).parent
    # Use the real pure copy helper only; no installation/settings/runtime launch.
    install = brainspace_setup._install_files(tmp_path / "installed")
    assert (install / "brainspace/plan_feasibility.py").read_bytes() == (
        root / "brainspace/plan_feasibility.py").read_bytes()
    assert (install / "token_efficiency.py").read_bytes() == Path(cli.__file__).read_bytes()
    path, _ = fixture_db(tmp_path)
    before = fingerprint(path)
    result = subprocess.run(
        [sys.executable, "-B", str(install / "token_efficiency.py"), "--db", str(path),
         "plan-feasibility", "--samples", "8"], capture_output=True, text=True, timeout=30,
        cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["arithmetic"]["status"] == "mathematically_impossible"
    assert fingerprint(path) == before
