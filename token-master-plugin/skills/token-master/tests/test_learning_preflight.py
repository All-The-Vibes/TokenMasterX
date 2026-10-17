"""Read-only learning admission; final freeze/task reservations still own races."""
from contextlib import contextmanager
import itertools
import sqlite3

import pytest

from brainspace.jev import Result
from brainspace.optimizer import OptimizerError
from test_optimizer import controller, evaluate, freeze, initialize


def snapshot(opt):
    db = sqlite3.connect(opt.path)
    try:
        return "\n".join(db.iterdump()), opt.path.read_bytes()
    finally:
        db.close()


def test_preflight_is_one_read_only_transaction_and_does_not_register_proposals(tmp_path, monkeypatch):
    opt = controller(tmp_path, max_calls=5)
    initialize(opt)
    before, statements, transactions = snapshot(opt), [], []
    transaction = opt._transaction

    @contextmanager
    def counted():
        transactions.append(True)
        with transaction() as db:
            db.set_trace_callback(statements.append)
            yield db

    def forbidden(*args, **kwargs):
        pytest.fail("Preflight must not propose, freeze, reserve or evaluate")

    monkeypatch.setattr(opt, "_transaction", counted)
    for name in ("propose", "freeze", "evaluate"):
        monkeypatch.setattr(opt, name, forbidden)
    monkeypatch.setattr(opt._registry, "reserve_tasks", forbidden)
    receipt = opt.preflight_learning(iter(("first", "second")), screening=True)
    assert receipt["task_ids"] == ("first", "second")
    assert receipt["samples"] == 2 and receipt["required_call_slots"] == 5
    assert receipt["calls_budget_spent"] == 0 and receipt["reservation"] is False
    assert receipt["screening"] is True and receipt["incumbent_version"] == 1
    assert receipt["config_id"] == opt.config.identity
    assert receipt["available_candidate_ids"]
    assert len(transactions) == 1 and snapshot(opt) == before
    assert all(s.split()[0].upper() in {"SELECT", "COMMIT"} for s in statements)


@pytest.mark.parametrize("screening", [None, 0, 1, "yes"])
def test_screening_flag_requires_explicit_boolean(tmp_path, screening):
    opt = controller(tmp_path)
    initialize(opt)
    before = snapshot(opt)
    with pytest.raises(OptimizerError, match="invalid_screening_flag"):
        opt.preflight_learning(("fresh",), screening=screening)
    assert snapshot(opt) == before


@pytest.mark.parametrize("ids", [None, "", "one", b"one", (), ("",), (" ",), (True,),
                                ("same", "same"), ("\ud800",)])
def test_invalid_ids_fail_without_writes(tmp_path, ids):
    opt = controller(tmp_path)
    initialize(opt)
    before = snapshot(opt)
    with pytest.raises(OptimizerError, match="invalid_task_ids"):
        opt.preflight_learning(ids)
    assert snapshot(opt) == before


def test_iterator_consumption_is_bounded_by_maximum_possible_pair_allocation(tmp_path):
    opt = controller(tmp_path, max_calls=4)
    initialize(opt)
    seen = []

    def infinite():
        for i in itertools.count():
            seen.append(i)
            yield f"task-{i}"

    before = snapshot(opt)
    with pytest.raises(OptimizerError, match="call_budget_exhausted"):
        opt.preflight_learning(infinite())
    assert seen == [0, 1, 2] and snapshot(opt) == before


def test_screening_slot_is_added_to_full_batch_not_just_one_pair(tmp_path):
    opt = controller(tmp_path, max_calls=4)
    initialize(opt)
    assert opt.preflight_learning(("a", "b"))["required_call_slots"] == 4
    before = snapshot(opt)
    with pytest.raises(OptimizerError, match="call_budget_exhausted"):
        opt.preflight_learning(("a", "b"), screening=True)
    assert snapshot(opt) == before


def test_prior_failed_screen_and_cancelled_trial_still_spend_budget(tmp_path):
    opt = controller(tmp_path, max_calls=6)
    initialize(opt)
    candidates = opt.propose()

    class FailedScreen:
        def decide(self, *args, **kwargs):
            return Result(False, "transport_error")

    opt.propose(screener=FailedScreen(), summaries={p.policy_id: "settings" for p in candidates},
                data_classification="synthetic")
    trial = freeze(opt, n=1)
    opt.cancel(trial.trial_id)
    before = snapshot(opt)
    receipt = opt.preflight_learning(("fresh",), screening=True)
    assert receipt["calls_budget_spent"] == 3 and receipt["required_call_slots"] == 3
    with pytest.raises(OptimizerError, match="call_budget_exhausted"):
        opt.preflight_learning(("a", "b"))
    assert snapshot(opt) == before


@pytest.mark.parametrize("kind", ["baseline", "search", "reserved", "confirmed", "failed", "cancelled"])
def test_any_existing_task_exposure_is_rejected_before_advisory_work(tmp_path, kind):
    def failure(*args):
        if kind == "cancelled":
            raise KeyboardInterrupt
        raise RuntimeError("not persisted")

    opt = controller(tmp_path, failure) if kind in ("failed", "cancelled") else controller(tmp_path)
    initialize(opt)
    task = "used"
    if kind == "baseline":
        task = opt.status()["baseline_attempts"][0]["task_id"]
    elif kind == "search":
        opt.exclude_search_tasks((task,))
    else:
        trial = freeze(opt, n=1)
        if kind == "reserved":
            opt._registry.reserve_tasks(trial.round_id, trial.comparison, (task,))
        elif kind == "confirmed":
            opt.evaluate(trial.trial_id, (task,))
        else:
            with pytest.raises(KeyboardInterrupt if kind == "cancelled" else OptimizerError):
                opt.evaluate(trial.trial_id, (task,))
    before = snapshot(opt)
    with pytest.raises(OptimizerError, match="task_already_consumed"):
        opt.preflight_learning(("fresh", task), screening=True)
    assert snapshot(opt) == before


def test_global_candidate_budget_is_checked_without_side_effects(tmp_path):
    opt = controller(tmp_path, max_candidates=1)
    initialize(opt)
    trial = freeze(opt, n=1)
    opt.cancel(trial.trial_id)
    before = snapshot(opt)
    with pytest.raises(OptimizerError, match="candidate_budget_exhausted"):
        opt.preflight_learning(("fresh",), screening=True)
    assert snapshot(opt) == before


def test_exhausted_neighbors_reject_even_with_global_candidate_budget_remaining(tmp_path):
    opt = controller(tmp_path, max_candidates=10)
    initialize(opt)
    for candidate in opt.propose():
        trial = opt.freeze(candidate.policy_id, sample_size=1)
        opt.cancel(trial.trial_id)
    before = snapshot(opt)
    with pytest.raises(OptimizerError, match="no_available_candidates"):
        opt.preflight_learning(("fresh",))
    assert snapshot(opt) == before


def test_current_initialization_and_config_checks_are_not_bypassed(tmp_path):
    opt = controller(tmp_path)
    before = snapshot(opt)
    with pytest.raises(OptimizerError, match="not_initialized"):
        opt.preflight_learning(("fresh",))
    assert snapshot(opt) == before
    initialize(opt)
    db = sqlite3.connect(opt.path)
    try:
        db.execute("UPDATE opt_config SET value='{}'")
        db.commit()
    finally:
        db.close()
    before = snapshot(opt)
    with pytest.raises(OptimizerError, match="configuration_changed"):
        opt.preflight_learning(("fresh",))
    assert snapshot(opt) == before


def test_preflight_does_not_reserve_candidate_slots_or_task_ids(tmp_path):
    opt = controller(tmp_path, max_candidates=1)
    initialize(opt)
    first = opt.preflight_learning(("fresh",))
    other = controller(tmp_path, max_candidates=1)
    assert other.preflight_learning(("fresh",)) == first
    trial = freeze(other, n=1)
    with pytest.raises(OptimizerError, match="candidate_budget_exhausted"):
        opt.freeze(opt.propose()[0].policy_id, sample_size=1)
    other.cancel(trial.trial_id)


def test_final_registry_reservation_rejects_a_task_consumed_after_preflight(tmp_path):
    calls = []

    def forbidden(*args):
        calls.append(args)
        pytest.fail("A task excluded after preflight must not execute")

    opt = controller(tmp_path, forbidden)
    initialize(opt)
    receipt = opt.preflight_learning(("fresh-0",))
    opt.exclude_search_tasks(("fresh-0",))
    trial = freeze(opt, n=1)
    with pytest.raises(OptimizerError, match="evaluation_failed"):
        evaluate(opt, trial)
    assert receipt["reservation"] is False and calls == []
