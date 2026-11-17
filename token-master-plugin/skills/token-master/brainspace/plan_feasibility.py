"""Necessary fixed-look bounds, not certification, power, or execution authority.

The strict gate (the defaults) uses the Hoeffding radius on both sides. The most
favorable allowed scalars are quality difference +1 and normalized token
difference -1. Even those cannot pass unless r <= 1 - eta/B. A quality margin
replaces the quality side with the exact harm count, whose best case is zero
harms; max-bet-v1 replaces the token side with the exact fixed bet, whose best
case is every task saving B. Gate reports refuse rounds above 4000 tasks.
Actual workloads need not attain either extreme, let alone both simultaneously.
No registry, tokenizer, model, oracle, or filesystem is accessed here.
"""
from __future__ import annotations

from fractions import Fraction
import math

from .certification import (
    MAX_GATE_SAMPLES, STRICT_GATE, TOKEN_TESTS, bet_minimum_samples, bet_passes, gate_label,
    harm_limit, harm_minimum_samples, passes, radius, round_alpha,
)


MAX_INTEGER = 2**63 - 1
MAX_CONTROLLER_SAMPLES = 1_000_000
_GATE_METHOD = "exact_integer_harm_and_bet_tests_with_binary64_hoeffding_and_eight_ulp_boundary_check"


def _integer(value: int, name: str) -> None:
    if type(value) is not int or not 0 < value <= MAX_INTEGER:
        raise ValueError(f"invalid_{name}")


def fixed_plan_feasibility(
    *, alpha: float, round_index: int, sample_size: int, token_cap: int,
    minimum_token_reduction: float, quality_margin: float = 0, token_test: str = "hoeffding-v1",
) -> dict:
    """Diagnose the existing gate without changing its arithmetic or identities.

    The ceil expression uses exact rational eta/B to avoid cancellation near B.
    Its log coefficient, like the gate, uses binary64. Both the ceil candidate
    and its predecessor are checked with the actual radius/inequalities.
    Within eight ulps of the boundary we decline a feasibility/minimum claim;
    this is a conservative numerical diagnostic, not an interval-arithmetic
    proof of the transcendental logarithm. The harm count and the fixed bet are
    decided exactly in integers, as the gate decides them; their minimums are
    searched up to 4000 tasks.
    """
    for value, name in ((round_index, "round_index"), (sample_size, "sample_size"),
                        (token_cap, "token_cap")):
        _integer(value, name)
    eta = minimum_token_reduction
    if (type(eta) not in (int, float) or not 0 < eta <= token_cap
            or not math.isfinite(eta)):
        raise ValueError("invalid_minimum_token_reduction")
    if type(alpha) not in (int, float) or not 0 < alpha < 1 or not math.isfinite(alpha):
        raise ValueError("invalid_alpha")
    if not (type(quality_margin) is int and quality_margin == 0
            or type(quality_margin) is float and 0 < quality_margin < 1):
        raise ValueError("invalid_quality_margin")
    if type(token_test) is not str or token_test not in TOKEN_TESTS:
        raise ValueError("invalid_token_test")
    gate = gate_label(quality_margin, token_test)
    if gate != STRICT_GATE and sample_size > MAX_GATE_SAMPLES:
        raise ValueError("gate_sample_limit_exceeded")
    common = {
        "schema_version": 1, "gate": "strict-paired-hoeffding-v1", "mode": "fixed",
        "alpha_total": alpha, "round_index": round_index, "sample_size": sample_size,
        "token_cap": token_cap, "minimum_token_reduction": eta,
        "controller_sample_limit": MAX_CONTROLLER_SAMPLES,
        "equal_observed_quality_can_pass": False,
        "numerical_method": "binary64_gate_with_exact_rational_margin_and_eight_ulp_boundary_check",
        "interpretation": "necessary_bounded_support_condition_not_power_or_attainable_outcomes",
        "population_assumptions": "UNVERIFIED", "fresh_iid_sampling": "UNVERIFIED",
        "certificate": False, "authority": False,
    }
    if gate != STRICT_GATE:
        common.update(gate=gate, controller_sample_limit=MAX_GATE_SAMPLES, numerical_method=_GATE_METHOD,
                      quality_margin=quality_margin, token_test=token_test)
    try:
        allocated = round_alpha(alpha, round_index)
    except ValueError:
        # Scalar validity is already checked: the existing allocation underflows.
        return {
            **common, "status": "numerically_indeterminate", "alpha_round": None,
            "radius": None, "minimum_samples": None, "minimum_samples_estimate": None,
            "minimum_samples_reason": "round_allocation_outside_floating_point_range",
            "numerical_limitations": ["round_allocation_outside_floating_point_range"],
            **({} if gate == STRICT_GATE else {
                "max_passing_harms": None, "equal_quality_minimum_samples": None,
                "token_minimum_samples": None}),
        }
    r = radius(alpha, round_index, sample_size)
    required = eta / token_cap
    margin = (Fraction(token_cap) - Fraction(eta)) / token_cap

    def boundary(n: int, margin=margin, required=required) -> str:
        candidate_radius = radius(alpha, round_index, n)
        error = Fraction(8 * math.ulp(candidate_radius))
        gap = margin - Fraction(candidate_radius)
        actual_pass = passes(1 - candidate_radius, -1 + candidate_radius, required)
        if gap > error and actual_pass:
            return "not_ruled_out"
        if gap < -error and not actual_pass:
            return "mathematically_impossible"
        return "numerically_indeterminate"

    def hoeffding(margin, required):
        limitations: list[str] = []
        status = boundary(sample_size, margin, required)
        minimum: int | None = None
        estimate: int | None = None
        if not margin:
            status = "mathematically_impossible"
            minimum_reason = "eta_equals_cap_no_finite_sample"
        else:
            coefficient = 2 * (math.log(2) - math.log(allocated))
            # Fraction avoids squared-margin underflow and a falsely rounded ceil.
            estimate = math.ceil(Fraction(coefficient) / margin**2)
            minimum_reason = "verified_ceil_and_predecessor"
            if estimate > MAX_INTEGER:
                limitations.append("minimum_exceeds_supported_integer_range")
                minimum_reason = "outside_supported_integer_range"
            elif (boundary(estimate, margin, required) == "not_ruled_out"
                  and (estimate == 1 or boundary(estimate - 1, margin, required)
                       == "mathematically_impossible")):
                minimum = estimate
            else:
                limitations.append("ceil_boundary_not_numerically_separated")
                minimum_reason = "numerically_indeterminate"
        return status, minimum, estimate, minimum_reason, limitations

    status, minimum, estimate, minimum_reason, limitations = hoeffding(margin, required)
    if required == 0:
        status = "numerically_indeterminate"
        minimum = None
        minimum_reason = "normalized_reduction_underflow"
        limitations.append("positive_reduction_underflows_gate_ratio")
    if status == "numerically_indeterminate":
        limitations.append("requested_sample_not_numerically_separated")
    report = {
        **common, "status": status, "alpha_round": allocated, "radius": r,
        "required_mean_quality_difference": r,
        "required_mean_token_saving": eta + token_cap * r,
        "best_case_quality_lower": 1 - r,
        "best_case_normalized_token_upper": -1 + r,
        "required_normalized_token_reduction": required,
        "minimum_samples": minimum, "minimum_samples_estimate": estimate,
        "minimum_samples_reason": minimum_reason,
        "numerical_limitations": limitations,
    }
    if gate == STRICT_GATE:
        return report
    n, sides = sample_size, []
    if quality_margin:
        harms = harm_limit(n, quality_margin, allocated)
        zero_harm = harm_minimum_samples(quality_margin, allocated)
        sides.append(("not_ruled_out" if harms >= 0 else "mathematically_impossible", zero_harm, []))
        report.update(
            max_passing_harms=harms if harms >= 0 else None, equal_quality_minimum_samples=zero_harm,
            required_mean_quality_difference=None,
            best_case_quality_lower=-quality_margin if harms >= 0 else -1.0,
            equal_observed_quality_can_pass=harms >= 0)
    else:
        # Strict quality alone: the joint check with eta = 0 is 1 - r >= 0.
        q_status, q_minimum, _, _, q_limitations = hoeffding(Fraction(1), 0)
        if q_status == "numerically_indeterminate":
            q_limitations.append("requested_sample_not_numerically_separated")
        sides.append((q_status, q_minimum, q_limitations))
        report.update(max_passing_harms=None, equal_quality_minimum_samples=None)
    if token_test == "max-bet-v1":
        best = bet_passes(token_cap, eta, allocated, ((token_cap, 0),) * n)
        token_minimum = bet_minimum_samples(token_cap, eta, allocated)
        saving = None
        if best:  # smallest whole saving s with every task saving s passing; s <= B
            low, high = 0, token_cap
            while low < high:
                mid = (low + high) // 2
                if bet_passes(token_cap, eta, allocated, ((mid, 0),) * n):
                    high = mid
                else:
                    low = mid + 1
            saving = low
        sides.append(("not_ruled_out" if best else "mathematically_impossible", token_minimum, []))
        report.update(token_minimum_samples=token_minimum, required_mean_token_saving=saving,
                      best_case_normalized_token_upper=-required if best else 1.0)
    else:
        sides.append((status, minimum, limitations))
        report.update(token_minimum_samples=minimum)
    statuses = [side[0] for side in sides]
    minima = [side[1] for side in sides]
    report.update(
        status=("mathematically_impossible" if "mathematically_impossible" in statuses
                else "numerically_indeterminate" if "numerically_indeterminate" in statuses
                else "not_ruled_out"),
        minimum_samples=None if None in minima else max(minima),
        minimum_samples_estimate=None,
        minimum_samples_reason=("larger_of_quality_and_token_minimums" if None not in minima
                                else "quality_or_token_minimum_unavailable"),
        numerical_limitations=[item for side in sides for item in side[2]],
    )
    return report
