"""Necessary fixed-look bounds, not certification, power, or execution authority.

The most favorable allowed scalars are quality difference +1 and normalized
token difference -1. Even those cannot pass unless r <= 1 - eta/B. Actual
workloads need not attain either extreme, let alone both simultaneously.
No registry, tokenizer, model, oracle, or filesystem is accessed here.
"""
from __future__ import annotations

from fractions import Fraction
import math

from .certification import radius, round_alpha


MAX_INTEGER = 2**63 - 1
MAX_CONTROLLER_SAMPLES = 1_000_000


def _integer(value: int, name: str) -> None:
    if type(value) is not int or not 0 < value <= MAX_INTEGER:
        raise ValueError(f"invalid_{name}")


def fixed_plan_feasibility(
    *, alpha: float, round_index: int, sample_size: int, token_cap: int,
    minimum_token_reduction: float,
) -> dict:
    """Diagnose the existing gate without changing its arithmetic or identities.

    The ceil expression uses exact rational eta/B to avoid cancellation near B.
    Its log coefficient, like the gate, uses binary64. Both the ceil candidate
    and its predecessor are checked with the actual radius/inequalities.
    Within eight ulps of the boundary we decline a feasibility/minimum claim;
    this is a conservative numerical diagnostic, not an interval-arithmetic
    proof of the transcendental logarithm.
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
    try:
        allocated = round_alpha(alpha, round_index)
    except ValueError:
        # Scalar validity is already checked: the existing allocation underflows.
        return {
            **common, "status": "numerically_indeterminate", "alpha_round": None,
            "radius": None, "minimum_samples": None, "minimum_samples_estimate": None,
            "minimum_samples_reason": "round_allocation_outside_floating_point_range",
            "numerical_limitations": ["round_allocation_outside_floating_point_range"],
        }
    r = radius(alpha, round_index, sample_size)
    required = eta / token_cap
    margin = (Fraction(token_cap) - Fraction(eta)) / token_cap
    limitations: list[str] = []

    def boundary(n: int) -> str:
        candidate_radius = radius(alpha, round_index, n)
        error = Fraction(8 * math.ulp(candidate_radius))
        gap = margin - Fraction(candidate_radius)
        actual_pass = (1 - candidate_radius >= 0
                       and -1 + candidate_radius <= -required)
        if gap > error and actual_pass:
            return "not_ruled_out"
        if gap < -error and not actual_pass:
            return "mathematically_impossible"
        return "numerically_indeterminate"

    status = boundary(sample_size)
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
        elif (boundary(estimate) == "not_ruled_out"
              and (estimate == 1 or boundary(estimate - 1) == "mathematically_impossible")):
            minimum = estimate
        else:
            limitations.append("ceil_boundary_not_numerically_separated")
            minimum_reason = "numerically_indeterminate"
    if required == 0:
        status = "numerically_indeterminate"
        minimum = None
        minimum_reason = "normalized_reduction_underflow"
        limitations.append("positive_reduction_underflows_gate_ratio")
    if status == "numerically_indeterminate":
        limitations.append("requested_sample_not_numerically_separated")
    return {
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
