"""Quality-margin gate tests.

S1: one pass rule, certification.passes, decides at every site that evaluates
it: certify, the optimizer's saved-certificate check and deployment recount, and
the feasibility boundary. optimizer.py and plan_feasibility.py import it by name,
so each test patches the binding of the module whose site it checks.

S2: GateComparisonSpec carries a quality_margin strictly between zero and one.
A margin registry has its own gate label and refuses other specs, anytime rounds
and rounds above 4000 tasks before it spends a round. certify stores
-quality_margin when the exact harm count passes and -1.0 when it fails, with
the two margin limit lines. The harm test's reference is the binomial tail in
Fraction arithmetic.

S3: GateOptimizerConfig copies the margin into every frozen spec. A margin
registry starts, searches, freezes and promotes only against a true-off
incumbent (a RuntimePolicy with no reducer and no instructions), refuses rounds
above 4000 tasks in freeze before it writes a trial, and its deployment re-check
recomputes the margin certificate byte for byte.

S4: fixed_plan_feasibility(quality_margin=...) reports the exact harm count, and
the optimizer snapshot reads a margin registry's label and passes its margin.

S5: --quality-margin exists on initialize-profile and learn-profile only; a
nonzero value builds GateOptimizerConfig, and a learn command whose margin
differs from the stored one stops with runtime_configuration_mismatch.
"""
from contextlib import closing
from dataclasses import asdict, fields
from fractions import Fraction
import itertools
import json
import math
import socket
import sqlite3

import pytest

from brainspace import certification, headroom, optimizer, plan_feasibility
from brainspace.optimizer import GateOptimizerConfig, Optimizer, OptimizerConfig, OptimizerError
from brainspace.request_policy import RequestPolicy
from brainspace.runtime_policy import RuntimePolicy
from brainspace.runtime_resources import RuntimeResources
from test_certification import observation, registry, spec, submit_batch
from test_optimizer import baseline_check, config, controller, evaluate, freeze, initialize, pair
import token_efficiency as cli

EDGES = (0.0, -0.0, 1e-300, -1e-300, 0.5, -0.5, 1.0, -1.0,
         math.inf, -math.inf, math.nan, 5e-324, -5e-324)


def inverted(monkeypatch, module, calls=None):
    """Patch module.passes to negate its result on every call, or on the numbered calls."""
    original, seen = certification.passes, []

    def wrapper(*args, **kwargs):
        seen.append(args)
        result = original(*args, **kwargs)
        return not result if calls is None or len(seen) in calls else result

    monkeypatch.setattr(module, "passes", wrapper)
    return seen


def certified_trial(tmp_path):
    opt = controller(tmp_path)
    initialize(opt)
    trial = freeze(opt, n=20)
    assert evaluate(opt, trial).decision == "certified"
    return opt, trial


def test_zero_margin_is_the_strict_rule_for_every_float():
    for lower, upper, required in itertools.product(EDGES, repeat=3):
        expected = lower >= 0 and upper <= -required
        for result in (certification.passes(lower, upper, required),
                       certification.passes(lower, upper, required, 0),
                       certification.passes(lower, upper, required, margin=0)):
            assert type(result) is bool and result is expected, (lower, upper, required)


def test_optimizer_and_feasibility_share_the_rule():
    assert optimizer.passes is certification.passes
    assert plan_feasibility.passes is certification.passes


def test_certify_decides_through_passes(tmp_path, monkeypatch):
    """Equal quality fails the strict rule, so only an inverted passes certifies it."""
    def certify(folder):
        folder.mkdir()
        r = registry(folder)
        k = r.start_round(spec(), sample_size=100)
        submit_batch(r, k, [observation(str(i), incumbent_success=True) for i in range(100)])
        return r.certify(k, spec()).decision

    assert certify(tmp_path / "strict") == "not_certified"
    seen = inverted(monkeypatch, certification)
    assert certify(tmp_path / "inverted") == "certified"
    assert len(seen) == 1


def test_promote_decides_through_passes(tmp_path, monkeypatch):
    opt, trial = certified_trial(tmp_path)
    inverted(monkeypatch, optimizer)
    with pytest.raises(OptimizerError, match="^registry_certificate_required$"):
        opt.promote(trial.trial_id)
    monkeypatch.undo()
    assert opt.promote(trial.trial_id)["champion"]["policy_id"] == trial.candidate.policy_id


def test_deployment_recount_decides_through_passes(tmp_path, monkeypatch):
    """Two saved-certificate checks come first; the third call is the recomputed decision."""
    opt, trial = certified_trial(tmp_path)
    opt.promote(trial.trial_id)
    seen = inverted(monkeypatch, optimizer, calls={3})
    with pytest.raises(OptimizerError, match="^invalid_deployment_certificate$"):
        opt.deployment_policy(expected_version=2, measurement=opt.config.measurement,
                              model_id=opt.config.model_id, workload_id=opt.config.workload_id,
                              environment_id=opt.config.environment_id)
    assert len(seen) == 3


def test_feasibility_boundary_decides_through_passes(monkeypatch):
    def status():
        return plan_feasibility.fixed_plan_feasibility(
            alpha=0.05, round_index=1, sample_size=9, token_cap=100000,
            minimum_token_reduction=1)["status"]

    assert status() == "not_ruled_out"
    inverted(monkeypatch, plan_feasibility)
    assert status() == "numerically_indeterminate"


MARGIN_GATE = "harm-margin-hoeffding-tokens-v1"
A1, A2 = certification.round_alpha(0.05, 1), certification.round_alpha(0.05, 2)


def margin_spec(delta=0.1):
    base = spec()
    return certification.GateComparisonSpec(*(getattr(base, f.name) for f in fields(base)),
                                            quality_margin=delta)


def refusal(call, *args, **kwargs):
    with pytest.raises(ValueError) as error:
        call(*args, **kwargs)
    return str(error.value)


@pytest.mark.parametrize("delta", [0.0, -0.0, -0.1, 1, 1.0, 1.5, True, False,
                                   math.nan, math.inf, "0.1", None])
def test_margin_must_be_a_float_strictly_between_zero_and_one(delta):
    assert refusal(margin_spec, delta) == (
        "quality_margin must be 0 or a float strictly between zero and one")


def test_margin_spec_round_trips_and_never_equals_the_plain_spec():
    assert refusal(margin_spec, 0) == "the strict gate uses ComparisonSpec, not GateComparisonSpec"
    plain = spec()
    assert type(certification.ComparisonSpec.from_dict(asdict(plain))) is certification.ComparisonSpec
    for delta in (0.1, 0.05, 5e-324, 0.9999999999999999):
        margin = margin_spec(delta)
        assert margin != plain and plain != margin and margin.identity != plain.identity
        again = certification.ComparisonSpec.from_dict(asdict(margin))
        assert type(again) is certification.GateComparisonSpec and again == margin


def tail(n, harms, delta):
    """P(Bin(n, delta) <= harms) in exact rationals."""
    d = Fraction(delta)
    return sum(math.comb(n, i) * d ** i * (1 - d) ** (n - i) for i in range(harms + 1))


@pytest.mark.parametrize("delta,alpha_round", [(0.1, A1), (0.1, A2), (0.05, A1), (0.3, A1)])
def test_harm_limit_is_the_largest_count_within_half_alpha(delta, alpha_round):
    level = Fraction(alpha_round) / 2
    for n in range(1, 131):
        limit = certification.harm_limit(n, delta, alpha_round)
        assert limit == -1 or tail(n, limit, delta) <= level, n
        assert tail(n, limit + 1, delta) > level, n
        assert certification.harm_passes(n, limit + 1, delta, alpha_round) is False
    minimum = certification.harm_minimum_samples(delta, alpha_round)
    assert (1 - Fraction(delta)) ** minimum <= level < (1 - Fraction(delta)) ** (minimum - 1)


def test_section_9_harm_values():
    for n, delta, alpha_round, limit in ((100, 0.1, A1, 3), (128, 0.1, A1, 5), (128, 0.1, A2, 4),
                                         (128, 0.05, A1, 1), (400, 0.05, A1, 10), (39, 0.1, A1, -1)):
        assert certification.harm_limit(n, delta, alpha_round) == limit
    assert [certification.harm_minimum_samples(delta, alpha_round) for delta, alpha_round in
            ((0.1, A1), (0.1, A2), (0.05, A1), (0.05, A2))] == [40, 53, 82, 109]


def test_margin_registry_stores_its_label_and_refuses_before_spending(tmp_path):
    for name in ("strict", "margin"):
        (tmp_path / name).mkdir()
    strict = registry(tmp_path / "strict")
    gated = registry(tmp_path / "margin", gate=certification.gate_label(0.1))
    with closing(sqlite3.connect(tmp_path / "margin" / "confirmation.sqlite")) as db:
        assert json.loads(db.execute("SELECT value FROM config").fetchone()[0])["gate"] == MARGIN_GATE
    mismatch = "comparison gate does not match this registry's gate"
    assert refusal(strict.start_round, margin_spec(), sample_size=128) == mismatch
    assert refusal(gated.start_round, spec(), sample_size=128) == mismatch
    assert refusal(gated.start_round, margin_spec(), mode="anytime") == (
        "margin and max-bet rounds must be fixed rounds")
    assert refusal(gated.start_round, margin_spec(), sample_size=4001) == (
        "margin and max-bet rounds allow at most 4000 tasks")
    assert strict.budget()["rounds"] == gated.budget()["rounds"] == 0
    assert refusal(registry, tmp_path / "margin") == "registry alpha/oracle/schema configuration mismatch"
    assert refusal(registry, tmp_path / "strict", gate="harm-margin-v0") == (
        "gate must be a supported certification gate label")


def margin_round(folder, *, harms, gains=0, n=128):
    """One round at quality_margin 0.1: harms first, then gains, then tasks both arms pass."""
    folder.mkdir()
    margin = margin_spec()
    r = registry(folder, gate=MARGIN_GATE)
    k = r.start_round(margin, sample_size=n)
    pairs = [(True, False)] * harms + [(False, True)] * gains + [(True, True)] * (n - harms - gains)
    submit_batch(r, k, [observation(str(i), incumbent_success=a, candidate_success=b, comparison=margin)
                        for i, (a, b) in enumerate(pairs)], comparison=margin)
    return r.certify(k, margin)


def test_margin_round_counts_harms_and_stores_minus_delta_or_minus_one(tmp_path):
    passed = margin_round(tmp_path / "five", harms=5, gains=5)
    assert passed.mean_quality_difference == 0.0
    assert (passed.decision, passed.quality_difference_lower) == ("certified", -0.1)
    assert len(passed.limits) == 6
    assert passed.limits[3].startswith("This margin certificate allows verified success")
    assert passed.limits[4].endswith("the token condition only.")
    assert passed.to_dict()["comparison"]["quality_margin"] == 0.1
    # Six harms fail even though 50 gains put the mean above the strict radius.
    failed = margin_round(tmp_path / "six", harms=6, gains=50)
    assert failed.mean_quality_difference - failed.radius >= 0
    assert (failed.decision, failed.quality_difference_lower) == ("not_certified", -1.0)


TRUE_OFF = "margin_requires_true_off_incumbent"


def margin_config(**changes):
    plain = config(**changes)
    return GateOptimizerConfig(**{f.name: getattr(plain, f.name) for f in fields(plain)},
                               quality_margin=0.1)


def margin_controller(tmp_path, **changes):
    """A margin registry in which both arms pass every task, at 90 and 10 tokens."""
    return Optimizer(tmp_path / "optimizer.sqlite", config=margin_config(**changes),
                     evaluator=lambda trial, task: pair(trial, task, equal=True))


def refused(code, call, *args, **kwargs):
    with pytest.raises(OptimizerError) as error:
        call(*args, **kwargs)
    assert str(error.value) == code


def deploy(opt, version):
    return opt.deployment_policy(expected_version=version, measurement=opt.config.measurement,
                                 model_id=opt.config.model_id, workload_id=opt.config.workload_id,
                                 environment_id=opt.config.environment_id)


def test_margin_config_validates_through_its_spec_and_round_trips():
    margin = margin_config()
    frozen = margin.comparison("candidate", "incumbent")
    assert type(frozen) is certification.GateComparisonSpec and frozen.quality_margin == 0.1
    assert type(OptimizerConfig.from_dict(asdict(config()))) is OptimizerConfig
    again = OptimizerConfig.from_dict(asdict(margin))
    assert type(again) is GateOptimizerConfig and again == margin
    assert margin != config() and margin.identity != config().identity
    plain = {f.name: getattr(config(), f.name) for f in fields(OptimizerConfig)}
    for bad in (1.0, -0.1, True):
        assert refusal(GateOptimizerConfig, **plain, quality_margin=bad) == (
            "quality_margin must be 0 or a float strictly between zero and one")
    assert refusal(GateOptimizerConfig, **plain) == (
        "the strict gate uses ComparisonSpec, not GateComparisonSpec")


@pytest.mark.parametrize("baseline", [RuntimePolicy(instruction="ponytail"), RequestPolicy(enabled=True)],
                         ids=["ponytail", "request-policy"])
def test_margin_initialize_refuses_a_baseline_that_is_not_true_off(tmp_path, baseline):
    opt = margin_controller(tmp_path)
    refused(TRUE_OFF, opt.initialize, baseline, validator=baseline_check, validation_call_limit=5,
            search_task_ids=("search-0",))
    status = opt.status()
    assert (status["initialized"], status["baseline_attempts"], status["calls_budget_spent"],
            status["search_task_ids"]) == (False, [], 0, [])


def test_margin_round_promotes_against_true_off_then_waits_for_rollback(tmp_path, monkeypatch):
    opt = margin_controller(tmp_path)
    opt.initialize(RuntimePolicy(), validator=baseline_check, validation_call_limit=0)
    trial = freeze(opt, n=40)  # the smallest round at which zero harms pass at 0.1
    assert trial.incumbent == RuntimePolicy() and trial.comparison.quality_margin == 0.1
    certificate = evaluate(opt, trial)
    assert (certificate.decision, certificate.quality_difference_lower) == ("certified", -0.1)
    monkeypatch.setattr(optimizer, "_true_off", lambda policy: False)
    refused("registry_certificate_required", opt.promote, trial.trial_id)
    monkeypatch.undo()
    opt.promote(trial.trial_id)
    # The re-check tests the trial's frozen true-off incumbent, not the promoted champion.
    assert deploy(opt, 2) == trial.candidate
    spent = opt.status()["calls_budget_spent"]
    refused(TRUE_OFF, opt.preflight_learning, ["after-0"])
    refused(TRUE_OFF, opt.propose)
    refused(TRUE_OFF, opt.freeze, RuntimePolicy().policy_id, sample_size=40)
    assert opt.status()["calls_budget_spent"] == spent
    opt.rollback(expected_version=2)
    assert freeze(opt, n=40).incumbent == RuntimePolicy()


def test_margin_freeze_refuses_more_than_4000_tasks_before_writing_a_trial(tmp_path):
    opt = margin_controller(tmp_path, max_calls=9000)
    opt.initialize(RuntimePolicy(), validator=baseline_check, validation_call_limit=0)
    candidate = opt.propose()[0]
    refused("gate_sample_limit_exceeded", opt.freeze, candidate.policy_id, sample_size=4001)
    assert opt.status()["trials"] == []
    assert opt.freeze(candidate.policy_id, sample_size=4000).trial_id == 1


def report(**changes):
    return plan_feasibility.fixed_plan_feasibility(**{**dict(
        alpha=0.05, round_index=1, sample_size=128, token_cap=100000, minimum_token_reduction=1),
        **changes})


def test_margin_feasibility_reports_the_exact_harm_count():
    strict = report()
    assert strict["gate"] == certification.STRICT_GATE and "max_passing_harms" not in strict
    assert report(quality_margin=0) == strict
    hundred = report(sample_size=100, quality_margin=0.1)
    assert {key: hundred[key] for key in (
        "gate", "status", "quality_margin", "token_test", "max_passing_harms",
        "equal_quality_minimum_samples", "token_minimum_samples", "minimum_samples",
        "required_mean_quality_difference", "best_case_quality_lower",
        "equal_observed_quality_can_pass", "controller_sample_limit")} == {
        "gate": MARGIN_GATE, "status": "not_ruled_out", "quality_margin": 0.1,
        "token_test": "hoeffding-v1", "max_passing_harms": 3, "equal_quality_minimum_samples": 40,
        "token_minimum_samples": 9, "minimum_samples": 40, "required_mean_quality_difference": None,
        "best_case_quality_lower": -0.1, "equal_observed_quality_can_pass": True,
        "controller_sample_limit": 4000}
    short = report(sample_size=39, quality_margin=0.1)
    assert (short["status"], short["max_passing_harms"], short["best_case_quality_lower"]) == (
        "mathematically_impossible", None, -1.0)
    assert [report(quality_margin=0.05)[key] for key in ("max_passing_harms", "minimum_samples")] == [1, 82]
    assert report(round_index=2, quality_margin=0.1)["max_passing_harms"] == 4
    assert report(sample_size=4001)["gate"] == certification.STRICT_GATE
    for changes, code in ((dict(sample_size=4001, quality_margin=0.1), "gate_sample_limit_exceeded"),
                          (dict(quality_margin=1.0), "invalid_quality_margin"),
                          (dict(quality_margin=0.0), "invalid_quality_margin"),
                          (dict(quality_margin=True), "invalid_quality_margin")):
        assert refusal(report, **changes) == code


def test_snapshot_reads_the_margin_label_and_reports_the_margin(tmp_path):
    opt = margin_controller(tmp_path)
    with closing(sqlite3.connect(opt.path)) as db:
        assert json.loads(db.execute("SELECT value FROM config").fetchone()[0])["gate"] == MARGIN_GATE
    opt.initialize(RuntimePolicy(), validator=baseline_check, validation_call_limit=0)
    trial = freeze(opt, n=128)
    frozen = Optimizer.plan_feasibility_snapshot(opt.path, trial_id=trial.trial_id)
    following = Optimizer.plan_feasibility_snapshot(opt.path, sample_size=128)
    assert frozen["config_id"] == following["config_id"] == opt.config.identity
    assert [(s["round_index"], s["arithmetic"]["quality_margin"], s["arithmetic"]["max_passing_harms"])
            for s in (frozen, following)] == [(1, 0.1, 5), (2, 0.1, 4)]
    refused("gate_sample_limit_exceeded", Optimizer.plan_feasibility_snapshot, opt.path, sample_size=4001)


class FakeResources:
    identity = "runtime-resources-v1:" + "0" * 64

    def to_manifest(self):
        return {"identity": self.identity, "fixture": True}


@pytest.fixture
def profile_cli(tmp_path, monkeypatch):
    """Parse a runtime command offline: sockets refuse, resources are faked, no component starts."""
    def offline(*args, **kwargs):
        raise AssertionError("these tests make no network connection and start no component")

    monkeypatch.setattr(socket.socket, "connect", offline)
    monkeypatch.setattr(socket, "create_connection", offline)
    monkeypatch.setattr(headroom, "HeadroomContainer", offline)
    original = RuntimeResources.__init__
    monkeypatch.setattr(RuntimeResources, "__init__", lambda self, **paths: original(self))
    monkeypatch.setattr(RuntimeResources, "validate", lambda self, policy=None: None)
    monkeypatch.setattr(RuntimeResources, "resolve",
                        lambda self, policy: {"ponytail": None, "headroom_options": None})
    manifest = tmp_path / "tasks.json"
    manifest.write_text(json.dumps({"schema_version": 1, "tasks": [{
        "prompt": "Read note.txt and return the numeric value in a JSON object.",
        "files": {"note.txt": "The numeric value is 7.\n"}, "expected": {"value": 7}, "intent": "exact",
    }]}), encoding="utf-8")

    def parse(command, output, *extra):
        resources = ["--ponytail-export", str(tmp_path / "export"), "--headroom-cache",
                     str(tmp_path / "cache"), "--headroom-assets", str(tmp_path / "assets")]
        return cli._parser().parse_args([
            "--db", str(tmp_path / "controller.sqlite"), command, "--output", str(tmp_path / output),
            "--manifest", str(manifest), "--base-url", "http://127.0.0.1:9/v1", "--model",
            "fixture-model", "--allow-network", "--max-calls-per-arm", "4", "--max-search-calls", "64",
            *(resources if command.endswith("-profile") else []), *extra])
    return parse


def built_config(profile_cli, *extra):
    return cli._runtime_setup(profile_cli("initialize-profile", "out", *extra),
                              profile_resources=FakeResources())[2].config


def test_quality_margin_flag_is_on_the_profile_commands_only(profile_cli):
    assert profile_cli("initialize-profile", "out").quality_margin == 0
    assert profile_cli("learn-profile", "out", "--task-id", "t", "--quality-margin", "0.1").quality_margin == 0.1
    refused("invalid_arguments", profile_cli, "initialize-runtime", "out", "--quality-margin", "0.1")
    refused("invalid_arguments", profile_cli, "learn-runtime", "out", "--task-id", "t", "--quality-margin", "0")
    refused("invalid_arguments", profile_cli, "initialize-profile", "out", "--quality-margin", "abc")


def test_runtime_setup_builds_the_gate_config_only_for_a_nonzero_margin(profile_cli):
    plain = built_config(profile_cli)
    assert type(plain) is OptimizerConfig
    for value in ("0", "0.0"):
        zero = built_config(profile_cli, "--quality-margin", value)
        assert type(zero) is OptimizerConfig and zero.identity == plain.identity
    margin = built_config(profile_cli, "--quality-margin", "0.1")
    assert type(margin) is GateOptimizerConfig and margin.quality_margin == 0.1
    assert {f.name: getattr(margin, f.name) for f in fields(OptimizerConfig)} == {
        f.name: getattr(plain, f.name) for f in fields(OptimizerConfig)}
    with pytest.raises(ValueError):
        built_config(profile_cli, "--quality-margin", "1.5")


def test_learn_with_another_margin_stops_with_a_configuration_mismatch(profile_cli):
    initial = cli.execute(profile_cli("initialize-profile", "initial", "--quality-margin", "0.1"))
    task = initial["task_ids"][0]
    for output, extra in (("other", ("--quality-margin", "0.05")), ("plain", ())):
        refused("runtime_configuration_mismatch", cli.execute,
                profile_cli("learn-profile", output, "--task-id", task, *extra))
