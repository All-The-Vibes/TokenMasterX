"""Numerical checks/counterexamples, not theorem-prover or model validation."""
from __future__ import annotations

from itertools import product
import json
import math
from pathlib import Path
import random

BASE = Path(__file__).resolve().parent


def alpha_at(k: int, total: float = 0.05) -> float:
    return 6.0 * total / (math.pi**2 * k**2)


def paired_radius(n: int, alpha: float) -> float:
    return math.sqrt(2.0 * math.log(2.0 / alpha) / n)


def mean_radius(n: int, alpha: float) -> float:
    return math.sqrt(math.log(8.0 / alpha) / (2.0 * n))


def anytime_paired_radius(n: int, alpha: float) -> float:
    return math.sqrt(2.0 * math.log(2.0 * n * (n + 1) / alpha) / n)


def main():
    checks = []

    def check(name, condition, detail=None):
        checks.append({"check": name, "passed": bool(condition), "detail": detail})

    alpha = 0.05
    count = 100_000
    spent = math.fsum(alpha_at(k, alpha) for k in range(1, count + 1))
    remainder_bound = 6.0 * alpha / (math.pi**2 * count)
    check("Finite alpha spending stays below the total", spent < alpha)
    check("Integral tail bound covers remaining alpha",
          0 < alpha - spent < remainder_bound)

    for k, n in ((1, 1_000), (10, 10_000), (100, 25_000)):
        a = alpha_at(k)
        r = paired_radius(n, a)
        check(f"Two paired Hoeffding tails spend alpha_{k}",
              math.isclose(2 * math.exp(-n * r * r / 2), a, rel_tol=1e-12))
        s = mean_radius(n, a)
        check(f"Eight mean-interval tails spend alpha_{k}",
              math.isclose(8 * math.exp(-2 * n * s * s), a, rel_tol=1e-12))
        seq = anytime_paired_radius(n, a)
        check(f"Anytime look ({k},{n}) spends its allocated two-tail budget",
              math.isclose(2 * math.exp(-n * seq * seq / 2),
                           a / (n * (n + 1)), rel_tol=1e-12))

    look_prefix = math.fsum(1 / (n * (n + 1)) for n in range(1, 10_001))
    check("Within-stream error-spending series telescopes",
          math.isclose(look_prefix, 1 - 1 / 10_001, rel_tol=1e-12))

    sample_table = []
    for k in (1, 10, 100):
        for tolerance in (0.10, 0.05, 0.02, 0.01):
            a = alpha_at(k)
            n = math.ceil(2 * math.log(2 / a) / tolerance**2)
            check(f"Required n achieves paired radius {tolerance}, round {k}",
                  paired_radius(n, a) <= tolerance)
            sample_table.append({
                "proposal_round": k,
                "round_alpha": a,
                "desired_confidence_radius": tolerance,
                "task_pairs_required": n,
                "target_model_runs_if_two_per_pair": 2 * n,
                "qualification": "Worst-case bounded-variable precision; not an acceptance or task-quality guarantee.",
            })

    beta = alpha_at(1) / 2
    harm_tolerance = 0.01
    harm_n = math.ceil(math.log(beta) / math.log(1 - harm_tolerance))
    harm_bound = 1 - beta**(1 / harm_n)
    check("Zero-observed-harm bound reaches 1% using allocated alpha",
          harm_bound <= harm_tolerance)
    check("One fewer zero-harm observation is insufficient",
          1 - beta**(1 / (harm_n - 1)) > harm_tolerance)
    check("Zero observed difference cannot pass the strict quality gate",
          0 - paired_radius(1_000, alpha_at(1)) < 0)

    # Pure illustrative proxy optimization counterexample.
    proxy = {"A": 0.8, "B": 0.99}
    truth = {"A": 1.0, "B": 0.0}
    selected = max(proxy, key=proxy.get)
    check("Optimizing an unvalidated proxy can reduce true quality",
          selected == "B" and truth[selected] < truth["A"])

    # Exhaustively check this small exact query/projection example.
    projection_cases = 0
    for statuses in product(("PASSED", "FAILED"), repeat=8):
        rows = [
            {"id": str(i), "status": status, "irrelevant_payload": "not needed"}
            for i, status in enumerate(statuses)
        ]
        projected = {
            "count": sum(row["status"] == "FAILED" for row in rows),
            "ids": [row["id"] for row in rows if row["status"] == "FAILED"],
        }
        direct_count = len([row for row in rows if row["status"] == "FAILED"])
        assert projected["count"] == direct_count == len(projected["ids"])
        projection_cases += 1
    check("Exact failure-count projection on all eight-row binary fixtures",
          projection_cases == 256, projection_cases)

    # This is not a probabilistic proof: it checks algebra on reproducible values.
    rng = random.Random(20261004)
    for _ in range(1_000):
        cost_a = rng.uniform(0.01, 1.0)
        cost_b = rng.uniform(0, cost_a)
        quality_a = rng.uniform(0.01, 1.0)
        quality_b = rng.uniform(quality_a, 1.0)
        assert cost_b / quality_b < cost_a / quality_a
    check("Pareto-to-ratio implication on 1000 numerical cases", True)

    bad_ratio = {
        "incumbent": 1.0 / 0.99,
        "candidate": 0.99 / 0.90,
    }
    check("Lower cost alone can worsen cost per success",
          0.99 < 1.0 and bad_ratio["candidate"] > bad_ratio["incumbent"])

    ratio_upper_b = 0.45 / 0.85
    ratio_lower_a = 0.75 / 0.85
    ratio_true_b = 0.40 / 0.90
    ratio_true_a = 0.80 / 0.80
    check("Valid simultaneous ratio interval gate implies true improvement",
          ratio_true_b <= ratio_upper_b
          and ratio_lower_a <= ratio_true_a
          and ratio_upper_b + 0.1 < ratio_lower_a
          and ratio_true_b + 0.1 < ratio_true_a)

    adjacency = {"A": ["B"], "B": ["A", "C"], "C": ["B"]}
    costs = {"A": 2, "B": 3, "C": 0}
    position = "A"
    trace = [position]
    while True:
        improving = [v for v in adjacency[position] if costs[v] < costs[position]]
        if not improving:
            break
        position = min(improving, key=costs.get)
        trace.append(position)
    check("Local hill climbing can miss the global optimum",
          position == "A" and min(costs, key=costs.get) == "C", trace)

    # Distribution shift attains the range-width times TV bound.
    p = (0.5, 0.5)
    p_new = (0.4, 0.6)
    f = (-1.0, 1.0)
    tv = sum(abs(a - b) for a, b in zip(p, p_new)) / 2
    shifted_mean = abs(sum(a * v for a, v in zip(p_new, f))
                       - sum(a * v for a, v in zip(p, f)))
    check("Width-2 drift example saturates 2*TV",
          math.isclose(shifted_mean, 2 * tv))

    # These are normalized hypothetical cost units, not Jev/provider prices.
    search_cost = 12.0
    saving_per_task = 0.02
    break_even_tasks = search_cost / saving_per_task
    check("Expected search payback threshold",
          math.isclose(break_even_tasks, 600)
          and 600 * saving_per_task - search_cost == 0
          and 601 * saving_per_task - search_cost > 0)

    result = {
        "research_date": "2026-10-04",
        "passed": all(row["passed"] for row in checks),
        "check_count": len(checks),
        "checks": checks,
        "alpha_spending": {
            "overall_alpha": alpha,
            "first_round_alpha": alpha_at(1),
            "first_100000_rounds_spent": spent,
            "remaining_alpha_upper_bound": remainder_bound,
        },
        "sample_complexity": sample_table,
        "zero_observed_harm": {
            "quality_test_alpha": beta,
            "harm_tolerance": harm_tolerance,
            "task_pairs_required": harm_n,
            "harm_probability_upper_bound": harm_bound,
            "qualification": "Assumes no harmful discordances, independent representative pairs, and valid outcome labels. This permits up to 1% harm; it does not prove zero regression.",
        },
        "multiple_testing_counterexample": {
            "assumption": "100 independent tests, each having exactly 5% false acceptance probability.",
            "probability_of_at_least_one_false_acceptance": 1 - 0.95**100,
        },
        "ratio_counterexample": bad_ratio,
        "hypothetical_roi": {
            "one_time_cost_units": search_cost,
            "per_task_saving_units": saving_per_task,
            "break_even_task_count": break_even_tasks,
            "strictly_positive_expected_saving_at": 601,
        },
        "limitations": [
            "Numerical and small-fixture checks are not theorem-prover certification.",
            "No Jev or target-model API was called.",
            "No cost, quality, calibration, independence or stationarity assumption was empirically established.",
            "Theorems are conditional statements; actual deployment needs independent outcome data.",
        ],
    }
    (BASE / "math-checks.json").write_bytes(
        (json.dumps(result, indent=2) + "\n").encode("utf-8")
    )
    print(json.dumps({
        "passed": result["passed"],
        "check_count": result["check_count"],
        "first_round_alpha": alpha_at(1),
        "round_1_pairs_for_1pct_radius": sample_table[3]["task_pairs_required"],
        "zero_harm_pairs_for_1pct_tolerance": harm_n,
        "failed_checks": [row for row in checks if not row["passed"]],
    }, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
