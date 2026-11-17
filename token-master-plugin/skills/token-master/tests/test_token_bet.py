"""Token-bet gate tests.

T1: certification.bet_passes decides the exact fixed full bet in integers, and
bet_minimum_samples is the smallest round in which every task saving token_cap
passes it. The reference here is the same inequality in Fraction arithmetic:
alpha_round/2 * prod((B + T_a - T_b) / (B + eta)) >= 1.

T2: GateComparisonSpec also takes token_test, hoeffding-v1 or max-bet-v1, and
each of the four settings has its own registry label. A max-bet-v1 round stores
-required as normalized_token_difference_upper when the bet passes and 1.0 when
it fails, and appends the bet limit line. With a quality margin as well, the
margin lines say the radius field applies to neither condition.

T3: GateOptimizerConfig also carries token_test. A bet registry at quality
margin 0 needs no true-off incumbent, certifies and promotes a saving the
Hoeffding bound cannot, and its deployment re-check recomputes the stored bound;
with a margin it needs a true-off incumbent, and freeze refuses 4001 tasks.

T4: fixed_plan_feasibility(token_test="max-bet-v1") reports the exact bet floor
and minimums, and the optimizer snapshot passes a bet registry's test.

T5: --token-test exists on the profile commands only and builds
GateOptimizerConfig for max-bet-v1, keeping the int 0 margin.
"""
from contextlib import closing
from dataclasses import asdict, fields
from fractions import Fraction
import json
import random
import sqlite3

import pytest

from brainspace.certification import (
    MAX_GATE_SAMPLES, ComparisonSpec, GateComparisonSpec, PairedObservation, VerifiedOutcome,
    bet_minimum_samples, bet_passes, certificate_limits, gate_label, margin_of, round_alpha,
    token_test_of,
)
from brainspace.optimizer import GateOptimizerConfig, Optimizer, OptimizerConfig
from brainspace.plan_feasibility import fixed_plan_feasibility
from brainspace.runtime_policy import RuntimePolicy
from brainspace.token_ledger import COMPLETE, TaskTrace, _canonical, measure_call
from brainspace.tokens import count_tokens
from test_certification import observation, registry, spec, submit_batch
from test_optimizer import baseline_check, config, evaluate, freeze, initialize
from test_quality_margin import built_config, deploy, profile_cli, refused  # noqa: F401 (fixture)
import token_efficiency as cli

B = 100000
A1, A2 = round_alpha(0.05, 1), round_alpha(0.05, 2)


def exact(cap, eta, alpha_round, pairs):
    capital = Fraction(alpha_round) / 2
    for incumbent, candidate in pairs:
        capital *= Fraction(cap + incumbent - candidate) / (cap + Fraction(eta))
    return capital >= 1


def test_decision_matches_the_exact_inequality():
    """Seeded rounds whose savings sit near the constant saving that just passes."""
    rng = random.Random(1)
    seen = {True: 0, False: 0}
    for _ in range(500):
        cap = rng.choice([10, 1000, B])
        eta = rng.choice([1, 0.1, 2.5])
        alpha_round = rng.choice([A1, A2, 0.5])
        n = rng.randint(8, 60)
        floor = (cap + eta) * (2 / alpha_round) ** (1 / n) - cap
        pairs = []
        for _ in range(n):
            saving = max(-cap, min(cap, round(rng.gauss(floor, 0.02 * cap))))
            incumbent = rng.randint(max(0, saving), min(cap, cap + saving))
            pairs.append((incumbent, incumbent - saving))
        decision = bet_passes(cap, eta, alpha_round, pairs)
        assert decision is exact(cap, eta, alpha_round, pairs), (cap, eta, alpha_round, n)
        seen[decision] += 1
    assert min(seen.values()) >= 100, seen


def test_default_configuration_needs_seven_tasks():
    assert MAX_GATE_SAMPLES == 4000
    assert bet_passes(B, 1, A1, [(B, 0)] * 6) is False
    assert bet_passes(B, 1, A1, [(B, 0)] * 7) is True
    assert bet_minimum_samples(B, 1, A1) == 7
    assert bet_passes(B, 1, A2, [(B, 0)] * 8) is False
    assert bet_passes(B, 1, A2, [(B, 0)] * 9) is True
    assert bet_minimum_samples(B, 1, A2) == 9
    assert bet_minimum_samples(B, 1, A1, limit=6) is None
    assert bet_minimum_samples(B, B, A1) is None  # at eta = B no factor exceeds 1


@pytest.mark.parametrize("cap,k,eta,floor", [
    (B, 1, 1, 3326), (B, 2, 1, 4452), (16000, 1, 1, 534), (B, 1, 0.1, 3325),
])
def test_smallest_constant_saving_over_128_tasks(cap, k, eta, floor):
    alpha_round = round_alpha(0.05, k)
    assert bet_passes(cap, eta, alpha_round, [(floor, 0)] * 128) is True
    assert bet_passes(cap, eta, alpha_round, [(floor - 1, 0)] * 128) is False


def test_tie_passes_order_is_free_and_a_zero_factor_fails():
    # B 14, eta 1, alpha_round 0.75: 3/8 * 24 * 25 = 225 = 15 ** 2.
    assert bet_passes(14, 1, 0.75, [(10, 0), (11, 0)]) is True
    assert bet_passes(14, 1, 0.75, [(11, 0), (10, 0)]) is True
    assert bet_passes(14, 1, 0.75, [(10, 0), (10, 0)]) is False
    assert bet_minimum_samples(4, 1, 0.78125) == 2  # 25/64 * 8 ** 2 = 5 ** 2
    assert bet_passes(B, 1, A1, iter([(B, 0)] * 7)) is True
    assert bet_passes(B, 1, A1, [(B, 0)] * 20 + [(0, B)]) is False


PAIRS = "pairs must be a sequence of (incumbent_tokens, candidate_tokens)"
ETA = "minimum_token_reduction must be finite, positive and <= token_cap"


@pytest.mark.parametrize("args,message", [
    ((0, 1, A1, [(1, 0)]), "token_cap must be an integer >= 1"),
    ((True, 1, A1, [(1, 0)]), "token_cap must be an integer >= 1"),
    ((B, 0, A1, [(1, 0)]), ETA),
    ((B, B + 1, A1, [(1, 0)]), ETA),
    ((B, float("nan"), A1, [(1, 0)]), ETA),
    ((B, 1, 1.0, [(1, 0)]), "alpha must be finite and strictly between zero and one"),
    ((B, 1, A1, []), "a bet round needs at least one paired task"),
    ((B, 1, A1, "ab"), PAIRS),
    ((B, 1, A1, [[1, 0]]), PAIRS),
    ((B, 1, A1, [(1, 0, 0)]), PAIRS),
    ((B, 1, A1, [(True, 0)]), "incumbent_tokens must be an integer >= 0"),
    ((B, 1, A1, [(0, -1)]), "candidate_tokens must be an integer >= 0"),
    ((B, 1, A1, [(0, B + 1)]), "bet factor is negative; a run exceeds token_cap"),
])
def test_bet_refusals(args, message):
    with pytest.raises(ValueError) as error:
        bet_passes(*args)
    assert str(error.value) == message


@pytest.mark.parametrize("args,message", [
    ((B, 0, A1), ETA),
    ((B, 1, A1, 0), "limit must be an integer >= 1"),
    ((B, 1, A1, True), "limit must be an integer >= 1"),
])
def test_minimum_refusals(args, message):
    with pytest.raises(ValueError) as error:
        bet_minimum_samples(*args)
    assert str(error.value) == message


def gate_spec(**settings):
    base = spec(token_cap=B, minimum_token_reduction=1)
    return GateComparisonSpec(*(getattr(base, f.name) for f in fields(base)), **settings)


def test_each_setting_has_its_own_registry_label():
    specs = (spec(), gate_spec(quality_margin=0.1), gate_spec(token_test="max-bet-v1"),
             gate_spec(quality_margin=0.1, token_test="max-bet-v1"))
    assert [gate_label(margin_of(s), token_test_of(s)) for s in specs] == [
        "strict-paired-hoeffding-v1", "harm-margin-hoeffding-tokens-v1",
        "strict-quality-max-bet-tokens-v1", "harm-margin-max-bet-tokens-v1"]


@pytest.mark.parametrize("value", ["hoeffding", "max-bet-v2", "", None, 1, True, b"max-bet-v1"])
def test_token_test_must_be_a_known_name(value):
    with pytest.raises(ValueError) as error:
        gate_spec(quality_margin=0.1, token_test=value)
    assert str(error.value) == "token_test must be hoeffding-v1 or max-bet-v1"


def test_bet_spec_keeps_the_int_zero_margin_and_round_trips():
    bet = gate_spec(token_test="max-bet-v1")
    assert type(asdict(bet)["quality_margin"]) is int and bet.quality_margin == 0
    again = ComparisonSpec.from_dict(asdict(bet))
    assert type(again) is GateComparisonSpec and again == bet


def bet_round(folder, comparison, candidate_tokens, *, harms=0, rest=(False, True), n=128):
    """One round at 10,000 incumbent tokens per task: harms first, then rest."""
    folder.mkdir()
    r = registry(folder, gate=gate_label(margin_of(comparison), token_test_of(comparison)))
    k = r.start_round(comparison, sample_size=n)
    pairs = [(True, False)] * harms + [rest] * (n - harms)
    submit_batch(r, k, [observation(str(i), incumbent_success=a, candidate_success=b,
                                    incumbent_tokens=10000, candidate_tokens=candidate_tokens,
                                    comparison=comparison)
                        for i, (a, b) in enumerate(pairs)], comparison=comparison)
    return r.certify(k, comparison)


def test_bet_round_stores_minus_required_or_one(tmp_path):
    bet = gate_spec(token_test="max-bet-v1")
    passed = bet_round(tmp_path / "pass", bet, 5000)
    assert (passed.decision, passed.normalized_token_difference_upper) == ("certified", -1e-05)
    assert passed.limits[:6] == certificate_limits(spec()) and len(passed.limits) == 7
    assert passed.limits[6].startswith("The token decision is an exact fixed-bet test")
    # A saving of 3,000 is below the 3,326 floor at n 128.
    failed = bet_round(tmp_path / "fail", bet, 7000)
    assert (failed.decision, failed.normalized_token_difference_upper) == ("not_certified", 1.0)
    # The Hoeffding token side does not certify the batch the bet passes.
    plain = bet_round(tmp_path / "plain", spec(token_cap=B, minimum_token_reduction=1), 5000)
    assert plain.decision == "not_certified" and plain.limits == certificate_limits(spec())


def test_margin_and_bet_each_decide_their_side(tmp_path):
    both = gate_spec(quality_margin=0.1, token_test="max-bet-v1")
    c = bet_round(tmp_path / "both", both, 5000, harms=5, rest=(True, True))
    assert (c.decision, c.quality_difference_lower, c.normalized_token_difference_upper) == (
        "certified", -0.1, -1e-05)
    assert c.limits[4].endswith("applies to neither condition.") and len(c.limits) == 7


def test_bet_rounds_are_fixed_and_at_most_4000_tasks(tmp_path):
    bet = gate_spec(token_test="max-bet-v1")
    r = registry(tmp_path, gate=gate_label(0, "max-bet-v1"))
    for comparison, kwargs, message in (
        (bet, {"mode": "anytime"}, "margin and max-bet rounds must be fixed rounds"),
        (bet, {"sample_size": 4001}, "margin and max-bet rounds allow at most 4000 tasks"),
        (gate_spec(quality_margin=0.1, token_test="max-bet-v1"), {"sample_size": 128},
         "comparison gate does not match this registry's gate"),
    ):
        with pytest.raises(ValueError) as error:
            r.start_round(comparison, **kwargs)
        assert str(error.value) == message
    assert r.budget()["rounds"] == 0


def saving_pair(candidate_tokens):
    """Evaluator: the incumbent fails at 90 tokens, the candidate passes at candidate_tokens."""
    def paired(trial, task_id):
        comparison = trial.comparison

        def trace(policy_id, tokens):
            call = measure_call(comparison.measurement, count_tokens, input_text="x " * (tokens - 1),
                                output_text="", call_id=f"{task_id}:{policy_id}", task_id=task_id,
                                attempt_id="1", phase="learning", role="primary",
                                model_id="fixture-model-v1", harness_id="offline-fixture",
                                coverage=COMPLETE, completion_status="succeeded")
            return TaskTrace(task_id, policy_id, comparison.measurement, "learning", (call,),
                             (call.call_id,), COMPLETE, trial.learning_run_id)

        return PairedObservation(
            task_id, trace(comparison.incumbent_id, 90), trace(comparison.candidate_id, candidate_tokens),
            VerifiedOutcome(task_id, comparison.incumbent_id, comparison.oracle_id, False, "b" * 64),
            VerifiedOutcome(task_id, comparison.candidate_id, comparison.oracle_id, True, "c" * 64))
    return paired


def bet_controller(tmp_path, *, name="bet", candidate_tokens=60, **settings):
    """token_cap 100 and eta 1, as tests/test_optimizer.py configures them."""
    plain = config(max_calls=9000)
    gate = GateOptimizerConfig(**{f.name: getattr(plain, f.name) for f in fields(plain)},
                               **{"token_test": "max-bet-v1", **settings})
    return Optimizer(tmp_path / f"{name}.sqlite", config=gate, evaluator=saving_pair(candidate_tokens))


def test_bet_registry_certifies_promotes_and_rechecks_without_true_off(tmp_path):
    opt = bet_controller(tmp_path)
    assert type(opt.config.quality_margin) is int and opt.config.quality_margin == 0
    initialize(opt)  # a RequestPolicy baseline: at margin 0 no true-off incumbent is needed
    candidate = opt.propose()[0]
    refused("gate_sample_limit_exceeded", opt.freeze, candidate.policy_id, sample_size=4001)
    trial = opt.freeze(candidate.policy_id, sample_size=20)
    assert trial.trial_id == 1 and trial.comparison.token_test == "max-bet-v1"
    certificate = evaluate(opt, trial)
    # 30 tokens saved per task at cap 100: the bet passes, the Hoeffding bound does not.
    assert (certificate.decision, certificate.normalized_token_difference_upper) == ("certified", -0.01)
    assert certificate.mean_normalized_token_difference + certificate.radius > -0.01
    opt.promote(trial.trial_id)
    assert deploy(opt, 2) == trial.candidate
    with closing(sqlite3.connect(opt.path)) as db:
        data = json.loads(db.execute("SELECT certificate FROM looks WHERE round_id=?",
                                     (trial.round_id,)).fetchone()[0])
        data["normalized_token_difference_upper"] = -0.5  # still passes the shared rule
        db.execute("UPDATE looks SET certificate=? WHERE round_id=?", (_canonical(data), trial.round_id))
        db.commit()
    refused("invalid_deployment_certificate", deploy, opt, 2)
    plain = Optimizer(tmp_path / "plain.sqlite", config=config(), evaluator=saving_pair(60))
    initialize(plain)
    assert evaluate(plain, freeze(plain, n=20)).decision == "not_certified"


def test_margin_bet_registry_needs_a_true_off_incumbent(tmp_path):
    opt = bet_controller(tmp_path, quality_margin=0.1)
    refused("margin_requires_true_off_incumbent", initialize, opt)
    opt.initialize(RuntimePolicy(), validator=baseline_check, validation_call_limit=0)
    refused("gate_sample_limit_exceeded", opt.freeze, opt.propose()[0].policy_id, sample_size=4001)
    assert opt.status()["trials"] == []


def bet_report(**changes):
    return fixed_plan_feasibility(**{**dict(
        alpha=0.05, round_index=1, sample_size=128, token_cap=B, minimum_token_reduction=1,
        token_test="max-bet-v1"), **changes})


def test_bet_feasibility_reports_the_exact_floor_and_minimums():
    bet = bet_report()
    assert {key: bet[key] for key in (
        "gate", "status", "quality_margin", "token_test", "required_mean_token_saving",
        "token_minimum_samples", "minimum_samples", "best_case_normalized_token_upper",
        "max_passing_harms", "equal_quality_minimum_samples", "controller_sample_limit")} == {
        "gate": "strict-quality-max-bet-tokens-v1", "status": "not_ruled_out", "quality_margin": 0,
        "token_test": "max-bet-v1", "required_mean_token_saving": 3326, "token_minimum_samples": 7,
        "minimum_samples": 9, "best_case_normalized_token_upper": -1e-05, "max_passing_harms": None,
        "equal_quality_minimum_samples": None, "controller_sample_limit": 4000}
    assert bet_report(quality_margin=0.1)["minimum_samples"] == 40
    second = bet_report(round_index=2)
    assert [second[key] for key in ("token_minimum_samples", "minimum_samples",
                                    "required_mean_token_saving")] == [9, 12, 4452]
    assert [bet_report(sample_size=n)["status"] for n in (6, 7, 8, 9)] == [
        "mathematically_impossible"] * 3 + ["not_ruled_out"]
    for changes, code in ((dict(sample_size=4001), "gate_sample_limit_exceeded"),
                          (dict(token_test="max-bet-v2"), "invalid_token_test"),
                          (dict(token_test=None), "invalid_token_test")):
        with pytest.raises(ValueError) as error:
            bet_report(**changes)
        assert str(error.value) == code


def test_snapshot_reads_the_bet_label_and_reports_the_bet(tmp_path):
    opt = bet_controller(tmp_path)
    with closing(sqlite3.connect(opt.path)) as db:
        assert json.loads(db.execute("SELECT value FROM config").fetchone()[0])["gate"] == (
            "strict-quality-max-bet-tokens-v1")
    initialize(opt)
    snapshot = Optimizer.plan_feasibility_snapshot(opt.path, sample_size=20)
    arithmetic = snapshot["arithmetic"]
    assert snapshot["config_id"] == opt.config.identity
    # At cap 100 and 20 tasks the smallest constant whole saving that passes is 25 tokens.
    assert (arithmetic["token_test"], arithmetic["status"], arithmetic["required_mean_token_saving"],
            arithmetic["best_case_normalized_token_upper"]) == ("max-bet-v1", "not_ruled_out", 25, -0.01)


def test_token_test_flag_builds_the_gate_config_on_the_profile_commands_only(profile_cli):
    plain = built_config(profile_cli)
    explicit = built_config(profile_cli, "--token-test", "hoeffding-v1")
    assert type(explicit) is OptimizerConfig and explicit.identity == plain.identity
    bet = built_config(profile_cli, "--token-test", "max-bet-v1")
    assert type(bet) is GateOptimizerConfig and bet.token_test == "max-bet-v1"
    assert type(bet.quality_margin) is int and bet.quality_margin == 0
    both = built_config(profile_cli, "--quality-margin", "0.1", "--token-test", "max-bet-v1")
    assert (both.quality_margin, both.token_test) == (0.1, "max-bet-v1")
    refused("invalid_arguments", profile_cli, "initialize-runtime", "out", "--token-test", "max-bet-v1")
    refused("invalid_arguments", profile_cli, "learn-runtime", "out", "--task-id", "t",
            "--token-test", "hoeffding-v1")
    refused("invalid_arguments", profile_cli, "initialize-profile", "out", "--token-test", "max-bet-v2")


def test_learn_with_another_token_test_stops_with_a_configuration_mismatch(profile_cli):
    initial = cli.execute(profile_cli("initialize-profile", "initial", "--token-test", "max-bet-v1"))
    refused("runtime_configuration_mismatch", cli.execute,
            profile_cli("learn-profile", "plain", "--task-id", initial["task_ids"][0]))
