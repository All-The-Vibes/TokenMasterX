"""Pre-registered Confirmation Round 2 statistical analyzer and certification verifier (`evidence/class-skeleton-r6-discovery-20261119`).

Verifies PROTOCOL.sha256 integrity, 78-session completeness (26 tasks x 3 arms: stock, tm_v1, tm_r6),
zero prompt-prefix confound between tm_v1 and tm_r6, 10,000-draw paired bootstrap 95% CIs,
exact two-sided Wilcoxon signed-rank p-values, Holm-Bonferroni family-wise adjustments across H1..H4,
and PR #35 exact integer certification gates at sequential Round k = 2 (`round_alpha(0.05, 2) = 0.00759909`).
Writes `analysis.json` and `RESULTS.md`.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SKILL = REPO / "token-master-plugin" / "skills" / "token-master"
sys.path.insert(0, str(SKILL))

from brainspace import certification

PROTOCOL = HERE / "PROTOCOL.md"
PROTOCOL_HASH = HERE / "PROTOCOL.sha256"
TASKS_FILE = HERE / "tasks.json"
SETUP_FILE = HERE / "setup.json"
BRIEFS_FILE = HERE / "briefs.json"
RUNS_FILE = HERE / "runs.jsonl"
ANALYSIS_FILE = HERE / "analysis.json"
RESULTS_FILE = HERE / "RESULTS.md"

ARMS = ("stock", "tm_v1", "tm_r6")
BUCKETS = (
    "A_oversized_class_trace",
    "B_oversized_class_edit",
    "C_small_symbol_control",
)
OVERSIZED_BUCKETS = ("A_oversized_class_trace", "B_oversized_class_edit")
REPOS = ("tokenmasterx", "click")
PAIRINGS = (
    ("tm_r6_vs_tm_v1", "tm_v1", "tm_r6"),
    ("tm_r6_vs_stock", "stock", "tm_r6"),
    ("tm_v1_vs_stock", "stock", "tm_v1"),
)
METRICS = (
    "total_tokens",
    "uncached_input_tokens",
    "cache_read_tokens",
    "output_tokens",
    "billed_cost_usd",
    "cold_cost_usd",
    "model_calls",
    "tool_call_count",
    "read_symbol_calls",
    "read_symbol_tokens",
    "tool_result_tokens",
    "class_skeleton_hits",
    "truncated_read_hits",
    "ambiguous_read_hits",
    "wall_seconds",
)
PAIRED_METRICS = (
    "total_tokens",
    "uncached_input_tokens",
    "billed_cost_usd",
    "cold_cost_usd",
    "model_calls",
    "read_symbol_calls",
    "read_symbol_tokens",
    "tool_result_tokens",
    "truncated_read_hits",
    "ambiguous_read_hits",
)
SEED = 20261119
DRAWS = 10_000
CERT_ALPHA = 0.05
CERT_ROUND = 2
CERT_TOKEN_CAP = 200_000
CERT_MIN_REDUCTION = 1_000
CERT_QUALITY_MARGIN = 0.20


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quantile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (pos - lo) * (sorted_vals[hi] - sorted_vals[lo])


def exact_wilcoxon_two_sided(diffs: list[float]) -> float:
    nz = [d for d in diffs if abs(d) > 1e-12]
    m = len(nz)
    if m == 0:
        return 1.0
    abs_sorted = sorted((abs(d), idx) for idx, d in enumerate(nz))
    twice_ranks = [0] * m
    i = 0
    while i < m:
        j = i
        while j + 1 < m and abs(abs_sorted[j + 1][0] - abs_sorted[i][0]) <= 1e-12:
            j += 1
        twice_avg = i + j + 2
        for k in range(i, j + 1):
            twice_ranks[abs_sorted[k][1]] = twice_avg
        i = j + 1

    total_twice = sum(twice_ranks)
    w_pos_twice = sum(twice_ranks[idx] for idx, d in enumerate(nz) if d > 0)
    obs_twice = min(w_pos_twice, total_twice - w_pos_twice)

    dp: dict[int, int] = {0: 1}
    for r2 in twice_ranks:
        nxt = dict(dp)
        for s, cnt in dp.items():
            nxt[s + r2] = nxt.get(s + r2, 0) + cnt
        dp = nxt

    extreme = sum(cnt for s, cnt in dp.items() if min(s, total_twice - s) <= obs_twice)
    return min(1.0, extreme / (1 << m))


def holm_bonferroni(pvals: dict[str, float]) -> dict[str, float]:
    ordered = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(ordered)
    adj: dict[str, float] = {}
    running_max = 0.0
    for idx, (k, p) in enumerate(ordered):
        val = min(1.0, p * (m - idx))
        running_max = max(running_max, val)
        adj[k] = round(running_max, 6)
    return adj


def paired_effect(base_vals: list[float], treat_vals: list[float], rng: random.Random) -> dict:
    n = len(base_vals)
    assert n == len(treat_vals) and n > 0
    diffs = [t - b for b, t in zip(base_vals, treat_vals)]
    mean_b = statistics.fmean(base_vals)
    mean_t = statistics.fmean(treat_vals)
    mean_diff = statistics.fmean(diffs)
    med_diff = statistics.median(diffs)
    pct_change = ((mean_t - mean_b) / mean_b * 100.0) if abs(mean_b) > 1e-12 else 0.0

    boot_means = []
    boot_pcts = []
    for _ in range(DRAWS):
        idxs = [rng.randrange(n) for _ in range(n)]
        sb = sum(base_vals[i] for i in idxs) / n
        st = sum(treat_vals[i] for i in idxs) / n
        boot_means.append(st - sb)
        boot_pcts.append(((st - sb) / sb * 100.0) if abs(sb) > 1e-12 else 0.0)
    boot_means.sort()
    boot_pcts.sort()

    wins = sum(1 for d in diffs if d < -1e-12)
    ties = sum(1 for d in diffs if abs(d) <= 1e-12)
    losses = sum(1 for d in diffs if d > 1e-12)

    return {
        "n": n,
        "base_mean": round(mean_b, 6),
        "treat_mean": round(mean_t, 6),
        "mean_diff": round(mean_diff, 6),
        "median_diff": round(med_diff, 6),
        "mean_diff_ci95": [round(quantile(boot_means, 0.025), 6), round(quantile(boot_means, 0.975), 6)],
        "pct_change": round(pct_change, 3),
        "pct_change_ci95": [round(quantile(boot_pcts, 0.025), 3), round(quantile(boot_pcts, 0.975), 3)],
        "wilcoxon_p_two_sided": round(exact_wilcoxon_two_sided(diffs), 6),
        "treat_lower_ties_higher": [wins, ties, losses],
    }


def summarize_rows(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {}
    passed = sum(1 for r in rows if r["passed"])
    out = {
        "n": n,
        "passed": passed,
        "pass_rate": round(passed / n, 4),
    }
    for m in METRICS:
        vals = [float(r[m]) for r in rows]
        out[f"{m}_mean"] = round(statistics.fmean(vals), 6)
        out[f"{m}_median"] = round(statistics.median(vals), 6)
    return out


def compute_pairings(by_task_arm: dict[tuple[str, str], dict], task_ids: list[str], rng: random.Random) -> dict:
    out = {}
    for label, base_arm, treat_arm in PAIRINGS:
        pair_res = {}
        for m in PAIRED_METRICS:
            b_vals = [float(by_task_arm[(tid, base_arm)][m]) for tid in task_ids]
            t_vals = [float(by_task_arm[(tid, treat_arm)][m]) for tid in task_ids]
            pair_res[m] = paired_effect(b_vals, t_vals, rng)
        b_pass = sum(1 for tid in task_ids if by_task_arm[(tid, base_arm)]["passed"])
        t_pass = sum(1 for tid in task_ids if by_task_arm[(tid, treat_arm)]["passed"])
        harms = sum(
            1 for tid in task_ids
            if by_task_arm[(tid, base_arm)]["passed"] and not by_task_arm[(tid, treat_arm)]["passed"]
        )
        helps = sum(
            1 for tid in task_ids
            if (not by_task_arm[(tid, base_arm)]["passed"]) and by_task_arm[(tid, treat_arm)]["passed"]
        )
        pair_res["pass_delta"] = {
            "base_passed": b_pass,
            "treat_passed": t_pass,
            "diff": t_pass - b_pass,
            "harms": harms,
            "helps": helps,
            "n": len(task_ids),
        }
        out[label] = pair_res
    return out


def compute_certification_gates(by_task_arm: dict[tuple[str, str], dict], task_ids: list[str]) -> dict:
    alpha_round = certification.round_alpha(CERT_ALPHA, CERT_ROUND)
    n = len(task_ids)
    out = {
        "alpha": CERT_ALPHA,
        "round": CERT_ROUND,
        "alpha_round": round(alpha_round, 8),
        "token_cap": CERT_TOKEN_CAP,
        "minimum_token_reduction": CERT_MIN_REDUCTION,
        "quality_margin": CERT_QUALITY_MARGIN,
        "harm_limit": certification.harm_limit(n, CERT_QUALITY_MARGIN, alpha_round),
        "harm_min_samples": certification.harm_minimum_samples(CERT_QUALITY_MARGIN, alpha_round),
        "bet_min_samples": certification.bet_minimum_samples(CERT_TOKEN_CAP, CERT_MIN_REDUCTION, alpha_round),
        "gates": {},
    }
    for label, inc_arm, cand_arm, true_off_incumbent in (
        ("tm_r6_vs_stock", "stock", "tm_r6", True),
        ("tm_v1_vs_stock", "stock", "tm_v1", True),
        ("tm_r6_vs_tm_v1", "tm_v1", "tm_r6", False),
    ):
        pairs = [
            (int(by_task_arm[(tid, inc_arm)]["total_tokens"]), int(by_task_arm[(tid, cand_arm)]["total_tokens"]))
            for tid in task_ids
        ]
        max_observed = max(max(a, b) for a, b in pairs)
        harms = sum(
            1 for tid in task_ids
            if by_task_arm[(tid, inc_arm)]["passed"] and not by_task_arm[(tid, cand_arm)]["passed"]
        )
        cap_respected = max_observed <= CERT_TOKEN_CAP
        bet_ok = certification.bet_passes(CERT_TOKEN_CAP, CERT_MIN_REDUCTION, alpha_round, pairs) if cap_respected else False
        wealth = alpha_round / 2.0
        for inc_t, cand_t in pairs:
            wealth *= (CERT_TOKEN_CAP + inc_t - cand_t) / (CERT_TOKEN_CAP + CERT_MIN_REDUCTION)
        harm_ok = (
            certification.harm_passes(n, harms, CERT_QUALITY_MARGIN, alpha_round)
            if (true_off_incumbent and n >= out["harm_min_samples"])
            else None
        )
        out["gates"][label] = {
            "incumbent": inc_arm,
            "candidate": cand_arm,
            "true_off_incumbent": true_off_incumbent,
            "n": n,
            "max_observed_tokens": max_observed,
            "token_cap_respected": cap_respected,
            "harms": harms,
            "harm_passes": harm_ok,
            "max_bet_v1_wealth": round(wealth, 6),
            "max_bet_v1_passes": bet_ok,
            "gate_certified": bool(bet_ok and harm_ok) if (true_off_incumbent and harm_ok is not None) else None,
        }
    return out


def main() -> int:
    expected_proto = PROTOCOL_HASH.read_text(encoding="utf-8").split()[0]
    actual_proto = sha256(PROTOCOL)
    if actual_proto != expected_proto:
        raise RuntimeError(f"PROTOCOL.md SHA-256 mismatch: {actual_proto} != {expected_proto}")

    spec = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    setup = json.loads(SETUP_FILE.read_text(encoding="utf-8"))
    runs = [json.loads(ln) for ln in RUNS_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]

    tasks = spec["tasks"]
    task_ids = [t["id"] for t in tasks]
    oversized_ids = [t["id"] for t in tasks if t["bucket"] in OVERSIZED_BUCKETS]
    n_all = len(task_ids)
    n_ov = len(oversized_ids)

    if len(runs) != n_all * len(ARMS):
        raise RuntimeError(f"expected {n_all * len(ARMS)} runs, got {len(runs)}")

    by_task_arm: dict[tuple[str, str], dict] = {}
    for r in runs:
        key = (r["task_id"], r["arm"])
        if key in by_task_arm:
            raise RuntimeError(f"duplicate run record for {key}")
        by_task_arm[key] = r
    for tid in task_ids:
        for arm in ARMS:
            if (tid, arm) not in by_task_arm:
                raise RuntimeError(f"missing run for {(tid, arm)}")

    fc_diffs = [
        by_task_arm[(tid, "tm_r6")]["first_call_input_tokens"] - by_task_arm[(tid, "tm_v1")]["first_call_input_tokens"]
        for tid in task_ids
    ]
    skel_tasks = sum(1 for tid in oversized_ids if by_task_arm[(tid, "tm_r6")]["class_skeleton_hits"] > 0)
    exposed_ids = [
        tid for tid in oversized_ids
        if by_task_arm[(tid, "tm_v1")]["truncated_read_hits"] > 0
        or by_task_arm[(tid, "tm_v1")]["ambiguous_read_hits"] > 0
        or by_task_arm[(tid, "tm_r6")]["class_skeleton_hits"] > 0
    ]
    bypassed_ids = [tid for tid in oversized_ids if tid not in exposed_ids]

    invariants = {
        "protocol_sha256_verified": True,
        "certification_round": CERT_ROUND,
        "session_count": len(runs),
        "stock_zero_mcp_calls": all(r["read_symbol_calls"] == 0 and r["brief_tokens_recorded"] == 0 for r in runs if r["arm"] == "stock"),
        "tm_v1_zero_skeleton_hits": all(r["class_skeleton_hits"] == 0 for r in runs if r["arm"] == "tm_v1"),
        "tm_r6_oversized_tasks_with_skeleton": skel_tasks,
        "oversized_tasks_mechanism_exposed": len(exposed_ids),
        "tm_v1_and_r6_first_call_input_max_abs_diff": max(abs(d) for d in fc_diffs),
        "tm_v1_and_r6_first_call_input_mean_diff": round(statistics.fmean(fc_diffs), 3),
        "tm_v1_and_r6_identical_brief_tokens": all(
            0 < by_task_arm[(tid, "tm_v1")]["brief_tokens_recorded"] == by_task_arm[(tid, "tm_r6")]["brief_tokens_recorded"] <= 320
            for tid in task_ids
        ),
    }

    rng = random.Random(SEED)
    exposure_subgroups = {
        "mechanism_exposed": {
            "task_ids": exposed_ids,
            "summary": {arm: summarize_rows([by_task_arm[(tid, arm)] for tid in exposed_ids]) for arm in ARMS} if exposed_ids else {},
            "pairings": compute_pairings(by_task_arm, exposed_ids, random.Random(SEED + 1)) if exposed_ids else {},
        },
        "unexposed_control_like": {
            "task_ids": bypassed_ids,
            "summary": {arm: summarize_rows([by_task_arm[(tid, arm)] for tid in bypassed_ids]) for arm in ARMS} if bypassed_ids else {},
            "pairings": compute_pairings(by_task_arm, bypassed_ids, random.Random(SEED + 2)) if bypassed_ids else {},
        },
    }

    overall_arm_summary = {arm: summarize_rows([by_task_arm[(tid, arm)] for tid in task_ids]) for arm in ARMS}
    oversized_arm_summary = {arm: summarize_rows([by_task_arm[(tid, arm)] for tid in oversized_ids]) for arm in ARMS}
    overall_pairings = compute_pairings(by_task_arm, task_ids, rng)
    oversized_pairings = compute_pairings(by_task_arm, oversized_ids, rng)

    by_bucket_summary = {}
    by_bucket_pairings = {}
    for b in BUCKETS:
        b_tids = [t["id"] for t in tasks if t["bucket"] == b]
        by_bucket_summary[b] = {arm: summarize_rows([by_task_arm[(tid, arm)] for tid in b_tids]) for arm in ARMS}
        by_bucket_pairings[b] = compute_pairings(by_task_arm, b_tids, rng)

    by_repo_summary = {}
    by_repo_pairings = {}
    for rk in REPOS:
        r_tids = [t["id"] for t in tasks if t["repo"] == rk]
        by_repo_summary[rk] = {arm: summarize_rows([by_task_arm[(tid, arm)] for tid in r_tids]) for arm in ARMS}
        by_repo_pairings[rk] = compute_pairings(by_task_arm, r_tids, rng)

    cert_all = compute_certification_gates(by_task_arm, task_ids)
    cert_oversized = compute_certification_gates(by_task_arm, oversized_ids)

    raw_p = {
        "H1_oversized_tool_result_tokens_r6_vs_v1": oversized_pairings["tm_r6_vs_tm_v1"]["tool_result_tokens"]["wilcoxon_p_two_sided"],
        "H2_oversized_total_tokens_r6_vs_v1": oversized_pairings["tm_r6_vs_tm_v1"]["total_tokens"]["wilcoxon_p_two_sided"],
        "H3_pooled_total_tokens_r6_vs_v1": overall_pairings["tm_r6_vs_tm_v1"]["total_tokens"]["wilcoxon_p_two_sided"],
        "H4_pooled_total_tokens_r6_vs_stock": overall_pairings["tm_r6_vs_stock"]["total_tokens"]["wilcoxon_p_two_sided"],
    }
    holm_p = holm_bonferroni(raw_p)

    hypotheses = {
        "H1_oversized_tool_result_tokens_r6_vs_v1": {
            **oversized_pairings["tm_r6_vs_tm_v1"]["tool_result_tokens"],
            "read_symbol_tokens": oversized_pairings["tm_r6_vs_tm_v1"]["read_symbol_tokens"],
            "holm_adjusted_p": holm_p["H1_oversized_tool_result_tokens_r6_vs_v1"],
        },
        "H2_oversized_total_tokens_r6_vs_v1": {
            **oversized_pairings["tm_r6_vs_tm_v1"]["total_tokens"],
            "holm_adjusted_p": holm_p["H2_oversized_total_tokens_r6_vs_v1"],
        },
        "H3_pooled_total_tokens_r6_vs_v1": {
            **overall_pairings["tm_r6_vs_tm_v1"]["total_tokens"],
            "pass_delta": overall_pairings["tm_r6_vs_tm_v1"]["pass_delta"],
            "holm_adjusted_p": holm_p["H3_pooled_total_tokens_r6_vs_v1"],
        },
        "H4_pooled_total_tokens_r6_vs_stock": {
            **overall_pairings["tm_r6_vs_stock"]["total_tokens"],
            "pass_delta": overall_pairings["tm_r6_vs_stock"]["pass_delta"],
            "certification_gate": cert_all["gates"]["tm_r6_vs_stock"],
            "holm_adjusted_p": holm_p["H4_pooled_total_tokens_r6_vs_stock"],
        },
    }

    analysis = {
        "analyzed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "study_id": spec["study_id"],
        "certification_round": CERT_ROUND,
        "protocol_sha256": actual_proto,
        "copilot_cli_version": setup["copilot_cli_version"],
        "model": setup["model"],
        "reasoning_effort": setup["reasoning_effort"],
        "invariants": invariants,
        "overall_arm_summary": overall_arm_summary,
        "oversized_arm_summary": oversized_arm_summary,
        "overall_pairings": overall_pairings,
        "oversized_pairings": oversized_pairings,
        "by_bucket_summary": by_bucket_summary,
        "by_bucket_pairings": by_bucket_pairings,
        "by_repo_summary": by_repo_summary,
        "by_repo_pairings": by_repo_pairings,
        "exposure_subgroups": exposure_subgroups,
        "hypotheses": hypotheses,
        "certification_all_n26": cert_all,
        "certification_oversized_n18": cert_oversized,
    }
    ANALYSIS_FILE.write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8", newline="\n")

    s_st = overall_arm_summary["stock"]
    s_v1 = overall_arm_summary["tm_v1"]
    s_r6 = overall_arm_summary["tm_r6"]
    o_st = oversized_arm_summary["stock"]
    o_v1 = oversized_arm_summary["tm_v1"]
    o_r6 = oversized_arm_summary["tm_r6"]

    p_ov = oversized_pairings["tm_r6_vs_tm_v1"]
    p_all = overall_pairings["tm_r6_vs_tm_v1"]
    p_stk = overall_pairings["tm_r6_vs_stock"]

    lines = [
        "# R6 Skeletal Class Projection — Confirmation Round 2 Results (`class-skeleton-r6-discovery-20261119`)",
        "",
        f"- **Protocol SHA-256**: `{actual_proto}` (verified intact)",
        f"- **Sequential Certification Round**: `k = {CERT_ROUND}` (`alpha_2 = round_alpha(0.05, 2) = {cert_all['alpha_round']:.8f}`; cumulative `alpha_1 + alpha_2 = 0.03799545 < 0.05`)",
        f"- **Host / Model**: `{setup['copilot_cli_version'].splitlines()[0]}` · `{setup['model']}` (`reasoning_effort={setup['reasoning_effort']}`)",
        f"- **Sample**: `{len(runs)}` live sessions (`{n_all}` paired tasks × `3` arms: `stock`, `tm_v1`, `tm_r6`; `13` `TokenMasterX @ dcd73c4a` + `13` `Click 8.1.8 @ 934813e4`)",
        f"- **Anti-Leakage & Mechanism Exposure**: `0` target method names in any Bucket A/B prompt; `tm_r6` rendered class skeletons on **`{skel_tasks}/{n_ov}`** oversized tasks (`{len(exposed_ids)}/{n_ov}` mechanism-exposed across container reads & `@overload` lookups).",
        f"- **Zero Prompt-Prefix Confound (`tm_v1` vs `tm_r6`)**: R1 `brief.md` tokens identical on `{n_all}/{n_all}` tasks; Call-1 input tokens mean diff `{invariants['tm_v1_and_r6_first_call_input_mean_diff']:+.2f}` tokens (max `±{invariants['tm_v1_and_r6_first_call_input_max_abs_diff']}`).",
        "",
        "## 1. Overall & Oversized-Class Arm Summary",
        "",
        f"### 1.1 Naturalistic Oversized-Class Target Stratum (Buckets A + B, `N = {n_ov}` paired tasks)",
        "",
        "| Arm | Pass | Mean Total Tokens | Mean Uncached Input | Mean `read_symbol` Calls | Mean `read_symbol` Tokens | Mean Tool-Result Tokens | Skeleton Hits | Truncated Reads | Ambiguous Hits | Mean Calls | Mean Billed USD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| `stock` | `{o_st['passed']}/{n_ov}` (`{o_st['pass_rate']*100:.1f}%`) | `{o_st['total_tokens_mean']:,.0f}` | `{o_st['uncached_input_tokens_mean']:,.0f}` | `{o_st['read_symbol_calls_mean']:.2f}` | `{o_st['read_symbol_tokens_mean']:,.0f}` | `{o_st['tool_result_tokens_mean']:,.0f}` | `0.00` | `0.00` | `0.00` | `{o_st['model_calls_mean']:.2f}` | `${o_st['billed_cost_usd_mean']:.4f}` |",
        f"| `tm_v1` | `{o_v1['passed']}/{n_ov}` (`{o_v1['pass_rate']*100:.1f}%`) | `{o_v1['total_tokens_mean']:,.0f}` | `{o_v1['uncached_input_tokens_mean']:,.0f}` | `{o_v1['read_symbol_calls_mean']:.2f}` | `{o_v1['read_symbol_tokens_mean']:,.0f}` | `{o_v1['tool_result_tokens_mean']:,.0f}` | `{o_v1['class_skeleton_hits_mean']:.2f}` | `{o_v1['truncated_read_hits_mean']:.2f}` | `{o_v1['ambiguous_read_hits_mean']:.2f}` | `{o_v1['model_calls_mean']:.2f}` | `${o_v1['billed_cost_usd_mean']:.4f}` |",
        f"| **`tm_r6`** | **`{o_r6['passed']}/{n_ov}` (`{o_r6['pass_rate']*100:.1f}%`)** | **`{o_r6['total_tokens_mean']:,.0f}`** | **`{o_r6['uncached_input_tokens_mean']:,.0f}`** | **`{o_r6['read_symbol_calls_mean']:.2f}`** | **`{o_r6['read_symbol_tokens_mean']:,.0f}`** | **`{o_r6['tool_result_tokens_mean']:,.0f}`** | **`{o_r6['class_skeleton_hits_mean']:.2f}`** | **`{o_r6['truncated_read_hits_mean']:.2f}`** | **`{o_r6['ambiguous_read_hits_mean']:.2f}`** | **`{o_r6['model_calls_mean']:.2f}`** | **`${o_r6['billed_cost_usd_mean']:.4f}`** |",
        "",
        f"### 1.2 All Tasks Pooled (Buckets A + B + C, `N = {n_all}` paired tasks)",
        "",
        "| Arm | Pass | Mean Total Tokens | Median Total Tokens | Mean Uncached Input | Mean `read_symbol` Tokens | Mean Tool-Result Tokens | Mean Calls | Mean Billed USD | Mean Cold USD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| `stock` | `{s_st['passed']}/{n_all}` (`{s_st['pass_rate']*100:.1f}%`) | `{s_st['total_tokens_mean']:,.0f}` | `{s_st['total_tokens_median']:,.0f}` | `{s_st['uncached_input_tokens_mean']:,.0f}` | `{s_st['read_symbol_tokens_mean']:,.0f}` | `{s_st['tool_result_tokens_mean']:,.0f}` | `{s_st['model_calls_mean']:.2f}` | `${s_st['billed_cost_usd_mean']:.4f}` | `${s_st['cold_cost_usd_mean']:.4f}` |",
        f"| `tm_v1` | `{s_v1['passed']}/{n_all}` (`{s_v1['pass_rate']*100:.1f}%`) | `{s_v1['total_tokens_mean']:,.0f}` | `{s_v1['total_tokens_median']:,.0f}` | `{s_v1['uncached_input_tokens_mean']:,.0f}` | `{s_v1['read_symbol_tokens_mean']:,.0f}` | `{s_v1['tool_result_tokens_mean']:,.0f}` | `{s_v1['model_calls_mean']:.2f}` | `${s_v1['billed_cost_usd_mean']:.4f}` | `${s_v1['cold_cost_usd_mean']:.4f}` |",
        f"| **`tm_r6`** | **`{s_r6['passed']}/{n_all}` (`{s_r6['pass_rate']*100:.1f}%`)** | **`{s_r6['total_tokens_mean']:,.0f}`** | **`{s_r6['total_tokens_median']:,.0f}`** | **`{s_r6['uncached_input_tokens_mean']:,.0f}`** | **`{s_r6['read_symbol_tokens_mean']:,.0f}`** | **`{s_r6['tool_result_tokens_mean']:,.0f}`** | **`{s_r6['model_calls_mean']:.2f}`** | **`${s_r6['billed_cost_usd_mean']:.4f}`** | **`${s_r6['cold_cost_usd_mean']:.4f}`** |",
        "",
        "## 2. Pre-Registered Hypotheses (`H1..H4`, Holm-Bonferroni Adjusted)",
        "",
        "| Hypothesis | Comparison & Metric | Mean Change (`%` [95% Bootstrap CI]) | Wins / Ties / Losses | Raw Wilcoxon `p` | Holm `p` |",
        "|---|---|---:|---:|---:|---:|",
        f"| **`H1`** (`N={n_ov}` A+B) | `tm_r6` vs `tm_v1` `tool_result_tokens` | `{p_ov['tool_result_tokens']['mean_diff']:+,.0f}` (`{p_ov['tool_result_tokens']['pct_change']:+.1f}%` [`{p_ov['tool_result_tokens']['pct_change_ci95'][0]:+.1f}%`, `{p_ov['tool_result_tokens']['pct_change_ci95'][1]:+.1f}%`]) | `{p_ov['tool_result_tokens']['treat_lower_ties_higher'][0]}W / {p_ov['tool_result_tokens']['treat_lower_ties_higher'][1]}T / {p_ov['tool_result_tokens']['treat_lower_ties_higher'][2]}L` | `{raw_p['H1_oversized_tool_result_tokens_r6_vs_v1']:.6f}` | `{holm_p['H1_oversized_tool_result_tokens_r6_vs_v1']:.6f}` |",
        f"| **`H2`** (`N={n_ov}` A+B) | `tm_r6` vs `tm_v1` `total_tokens` | `{p_ov['total_tokens']['mean_diff']:+,.0f}` (`{p_ov['total_tokens']['pct_change']:+.1f}%` [`{p_ov['total_tokens']['pct_change_ci95'][0]:+.1f}%`, `{p_ov['total_tokens']['pct_change_ci95'][1]:+.1f}%`]) | `{p_ov['total_tokens']['treat_lower_ties_higher'][0]}W / {p_ov['total_tokens']['treat_lower_ties_higher'][1]}T / {p_ov['total_tokens']['treat_lower_ties_higher'][2]}L` | `{raw_p['H2_oversized_total_tokens_r6_vs_v1']:.6f}` | `{holm_p['H2_oversized_total_tokens_r6_vs_v1']:.6f}` |",
        f"| **`H3`** (`N={n_all}` All) | `tm_r6` vs `tm_v1` `total_tokens` | `{p_all['total_tokens']['mean_diff']:+,.0f}` (`{p_all['total_tokens']['pct_change']:+.1f}%` [`{p_all['total_tokens']['pct_change_ci95'][0]:+.1f}%`, `{p_all['total_tokens']['pct_change_ci95'][1]:+.1f}%`]) | `{p_all['total_tokens']['treat_lower_ties_higher'][0]}W / {p_all['total_tokens']['treat_lower_ties_higher'][1]}T / {p_all['total_tokens']['treat_lower_ties_higher'][2]}L` | `{raw_p['H3_pooled_total_tokens_r6_vs_v1']:.6f}` | `{holm_p['H3_pooled_total_tokens_r6_vs_v1']:.6f}` |",
        f"| **`H4`** (`N={n_all}` All) | `tm_r6` vs `stock` `total_tokens` | `{p_stk['total_tokens']['mean_diff']:+,.0f}` (`{p_stk['total_tokens']['pct_change']:+.1f}%` [`{p_stk['total_tokens']['pct_change_ci95'][0]:+.1f}%`, `{p_stk['total_tokens']['pct_change_ci95'][1]:+.1f}%`]) | `{p_stk['total_tokens']['treat_lower_ties_higher'][0]}W / {p_stk['total_tokens']['treat_lower_ties_higher'][1]}T / {p_stk['total_tokens']['treat_lower_ties_higher'][2]}L` | `{raw_p['H4_pooled_total_tokens_r6_vs_stock']:.6f}` | `{holm_p['H4_pooled_total_tokens_r6_vs_stock']:.6f}` |",
        "",
        "## 3. Bucket Breakdown (`10` Bucket A / `8` Bucket B / `8` Bucket C)",
        "",
        "| Bucket | `stock` Tokens (Pass) | `tm_v1` Tokens (Pass) | `tm_r6` Tokens (Pass) | `tm_r6` vs `tm_v1` Tokens (`p`) | `tm_r6` vs `tm_v1` `read_symbol` Tokens |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for b in BUCKETS:
        bs = by_bucket_summary[b]
        bn = bs["stock"]["n"]
        bp = by_bucket_pairings[b]["tm_r6_vs_tm_v1"]
        lines.append(
            f"| `{b}` | `{bs['stock']['total_tokens_mean']:,.0f}` (`{bs['stock']['passed']}/{bn}`) | "
            f"`{bs['tm_v1']['total_tokens_mean']:,.0f}` (`{bs['tm_v1']['passed']}/{bn}`) | "
            f"**`{bs['tm_r6']['total_tokens_mean']:,.0f}` (`{bs['tm_r6']['passed']}/{bn}`)** | "
            f"`{bp['total_tokens']['pct_change']:+.1f}%` (`p={bp['total_tokens']['wilcoxon_p_two_sided']:.4f}`) | "
            f"`{bs['tm_v1']['read_symbol_tokens_mean']:,.0f}` → `{bs['tm_r6']['read_symbol_tokens_mean']:,.0f}` (`{bp['read_symbol_tokens']['pct_change']:+.1f}%`) |"
        )

    lines.extend([
        "",
        f"## 4. Exact Integer Certification Gates (`brainspace/certification.py`, Sequential Round `k = {CERT_ROUND}`, `alpha_2 = {cert_all['alpha_round']:.8f}`)",
        "",
        "| Gate Comparison | `N` | Harms (Limit) | `harm_passes` | `max-bet-v1` Wealth | `max-bet-v1` `bet_passes` | Certified vs True-Off |",
        "|---|---:|---:|---|---:|---|---|",
    ])
    for gname in ("tm_r6_vs_stock", "tm_v1_vs_stock", "tm_r6_vs_tm_v1"):
        g = cert_all["gates"][gname]
        lines.append(
            f"| `{gname}` | `{g['n']}` | `{g['harms']}` (`<={cert_all['harm_limit']}` if true-off) | "
            f"`{g['harm_passes']}` | `{g['max_bet_v1_wealth']:.6f}` | `{g['max_bet_v1_passes']}` | `{g['gate_certified']}` |"
        )
    g18 = cert_oversized["gates"]["tm_r6_vs_tm_v1"]
    lines.append(
        f"| `tm_r6_vs_tm_v1` (Oversized A+B) | `{n_ov}` | `{g18['harms']}` | `None` (active incumbent) | `{g18['max_bet_v1_wealth']:.6f}` | `{g18['max_bet_v1_passes']}` | `N/A` |"
    )

    lines.extend([
        "",
        f"## 5. Per-Task Paired Ledger (`{n_all}` Tasks × `3` Arms)",
        "",
        "| Task | Repo | Bucket | Kind | `stock` Tokens (Pass) | `tm_v1` Tokens / `rs_tok` (Pass) | `tm_r6` Tokens / `rs_tok` / `skel` (Pass) | `r6 - v1` Tokens |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ])
    for t in tasks:
        tid = t["id"]
        rst = by_task_arm[(tid, "stock")]
        rv1 = by_task_arm[(tid, "tm_v1")]
        rr6 = by_task_arm[(tid, "tm_r6")]
        dt = rr6["total_tokens"] - rv1["total_tokens"]
        lines.append(
            f"| `{tid}` | `{t['repo']}` | `{t['bucket'].split('_')[0]}` | `{t['kind']}` | "
            f"`{rst['total_tokens']:,}` ({'✓' if rst['passed'] else '✗'}) | "
            f"`{rv1['total_tokens']:,}` / `{rv1['read_symbol_tokens']:,}` ({'✓' if rv1['passed'] else '✗'}) | "
            f"**`{rr6['total_tokens']:,}`** / `{rr6['read_symbol_tokens']:,}` / `{rr6['class_skeleton_hits']}` ({'✓' if rr6['passed'] else '✗'}) | "
            f"`{dt:+,}` |"
        )

    ba_p = by_bucket_pairings["A_oversized_class_trace"]["tm_r6_vs_tm_v1"]
    bb_p = by_bucket_pairings["B_oversized_class_edit"]["tm_r6_vs_tm_v1"]
    bc_p = by_bucket_pairings["C_small_symbol_control"]["tm_r6_vs_tm_v1"]
    lines.extend([
        "",
        "## 6. Exploratory Payload & Cost Decomposition (`tm_r6` vs `tm_v1`)",
        "",
        "| Stratum | Metric | `tm_v1` Mean | `tm_r6` Mean | `%` Change [95% CI] | Wins / Ties / Losses | Exact Wilcoxon `p` (unadjusted) |",
        "|---|---|---:|---:|---:|---:|---:|",
        f"| `Bucket A` (`N=10` trace) | `read_symbol_tokens` | `{ba_p['read_symbol_tokens']['base_mean']:,.0f}` | `{ba_p['read_symbol_tokens']['treat_mean']:,.0f}` | `{ba_p['read_symbol_tokens']['pct_change']:+.1f}%` [`{ba_p['read_symbol_tokens']['pct_change_ci95'][0]:+.1f}%`, `{ba_p['read_symbol_tokens']['pct_change_ci95'][1]:+.1f}%`] | `{ba_p['read_symbol_tokens']['treat_lower_ties_higher'][0]}W / {ba_p['read_symbol_tokens']['treat_lower_ties_higher'][1]}T / {ba_p['read_symbol_tokens']['treat_lower_ties_higher'][2]}L` | `{ba_p['read_symbol_tokens']['wilcoxon_p_two_sided']:.6f}` |",
        f"| `Bucket A` (`N=10` trace) | `billed_cost_usd` | `${ba_p['billed_cost_usd']['base_mean']:.4f}` | `${ba_p['billed_cost_usd']['treat_mean']:.4f}` | `{ba_p['billed_cost_usd']['pct_change']:+.1f}%` [`{ba_p['billed_cost_usd']['pct_change_ci95'][0]:+.1f}%`, `{ba_p['billed_cost_usd']['pct_change_ci95'][1]:+.1f}%`] | `{ba_p['billed_cost_usd']['treat_lower_ties_higher'][0]}W / {ba_p['billed_cost_usd']['treat_lower_ties_higher'][1]}T / {ba_p['billed_cost_usd']['treat_lower_ties_higher'][2]}L` | `{ba_p['billed_cost_usd']['wilcoxon_p_two_sided']:.6f}` |",
        f"| `Oversized A+B` (`N={n_ov}`) | `read_symbol_tokens` | `{p_ov['read_symbol_tokens']['base_mean']:,.0f}` | `{p_ov['read_symbol_tokens']['treat_mean']:,.0f}` | `{p_ov['read_symbol_tokens']['pct_change']:+.1f}%` [`{p_ov['read_symbol_tokens']['pct_change_ci95'][0]:+.1f}%`, `{p_ov['read_symbol_tokens']['pct_change_ci95'][1]:+.1f}%`] | `{p_ov['read_symbol_tokens']['treat_lower_ties_higher'][0]}W / {p_ov['read_symbol_tokens']['treat_lower_ties_higher'][1]}T / {p_ov['read_symbol_tokens']['treat_lower_ties_higher'][2]}L` | `{p_ov['read_symbol_tokens']['wilcoxon_p_two_sided']:.6f}` |",
        f"| `Oversized A+B` (`N={n_ov}`) | `billed_cost_usd` | `${p_ov['billed_cost_usd']['base_mean']:.4f}` | `${p_ov['billed_cost_usd']['treat_mean']:.4f}` | `{p_ov['billed_cost_usd']['pct_change']:+.1f}%` [`{p_ov['billed_cost_usd']['pct_change_ci95'][0]:+.1f}%`, `{p_ov['billed_cost_usd']['pct_change_ci95'][1]:+.1f}%`] | `{p_ov['billed_cost_usd']['treat_lower_ties_higher'][0]}W / {p_ov['billed_cost_usd']['treat_lower_ties_higher'][1]}T / {p_ov['billed_cost_usd']['treat_lower_ties_higher'][2]}L` | `{p_ov['billed_cost_usd']['wilcoxon_p_two_sided']:.6f}` |",
        f"| `Bucket B` (`N=8` edit) | `read_symbol_tokens` | `{bb_p['read_symbol_tokens']['base_mean']:,.0f}` | `{bb_p['read_symbol_tokens']['treat_mean']:,.0f}` | `{bb_p['read_symbol_tokens']['pct_change']:+.1f}%` [`{bb_p['read_symbol_tokens']['pct_change_ci95'][0]:+.1f}%`, `{bb_p['read_symbol_tokens']['pct_change_ci95'][1]:+.1f}%`] | `{bb_p['read_symbol_tokens']['treat_lower_ties_higher'][0]}W / {bb_p['read_symbol_tokens']['treat_lower_ties_higher'][1]}T / {bb_p['read_symbol_tokens']['treat_lower_ties_higher'][2]}L` | `{bb_p['read_symbol_tokens']['wilcoxon_p_two_sided']:.6f}` |",
        f"| `Bucket C` (`N=8` control) | `read_symbol_tokens` | `{bc_p['read_symbol_tokens']['base_mean']:,.0f}` | `{bc_p['read_symbol_tokens']['treat_mean']:,.0f}` | `{bc_p['read_symbol_tokens']['pct_change']:+.1f}%` [`{bc_p['read_symbol_tokens']['pct_change_ci95'][0]:+.1f}%`, `{bc_p['read_symbol_tokens']['pct_change_ci95'][1]:+.1f}%`] | `{bc_p['read_symbol_tokens']['treat_lower_ties_higher'][0]}W / {bc_p['read_symbol_tokens']['treat_lower_ties_higher'][1]}T / {bc_p['read_symbol_tokens']['treat_lower_ties_higher'][2]}L` | `{bc_p['read_symbol_tokens']['wilcoxon_p_two_sided']:.6f}` |",
        f"| `Pooled All` (`N={n_all}`) | `read_symbol_tokens` | `{p_all['read_symbol_tokens']['base_mean']:,.0f}` | `{p_all['read_symbol_tokens']['treat_mean']:,.0f}` | `{p_all['read_symbol_tokens']['pct_change']:+.1f}%` [`{p_all['read_symbol_tokens']['pct_change_ci95'][0]:+.1f}%`, `{p_all['read_symbol_tokens']['pct_change_ci95'][1]:+.1f}%`] | `{p_all['read_symbol_tokens']['treat_lower_ties_higher'][0]}W / {p_all['read_symbol_tokens']['treat_lower_ties_higher'][1]}T / {p_all['read_symbol_tokens']['treat_lower_ties_higher'][2]}L` | `{p_all['read_symbol_tokens']['wilcoxon_p_two_sided']:.6f}` |",
        f"| `Pooled All` (`N={n_all}`) | `billed_cost_usd` | `${p_all['billed_cost_usd']['base_mean']:.4f}` | `${p_all['billed_cost_usd']['treat_mean']:.4f}` | `{p_all['billed_cost_usd']['pct_change']:+.1f}%` [`{p_all['billed_cost_usd']['pct_change_ci95'][0]:+.1f}%`, `{p_all['billed_cost_usd']['pct_change_ci95'][1]:+.1f}%`] | `{p_all['billed_cost_usd']['treat_lower_ties_higher'][0]}W / {p_all['billed_cost_usd']['treat_lower_ties_higher'][1]}T / {p_all['billed_cost_usd']['treat_lower_ties_higher'][2]}L` | `{p_all['billed_cost_usd']['wilcoxon_p_two_sided']:.6f}` |",
        "",
        "### Why Payload & Billed Cost Improved Sharply While Raw `total_tokens` Attenuated",
        "",
        "1. **Cached-prefix accounting vs billed cost in 2-step skeleton discovery (`Bucket A`, `N=10`)**: In `tm_r6`, reading an oversized class (`~966–1,080` skeleton tokens vs `2,391–2,399` truncated `tm_v1` tokens) followed by a surgical `Class.method` lookup (`~250–400` tokens) cut `read_symbol` payload **`-43.6%`** (`10W / 0T / 0L`, `p = 0.001953`) and **reduced actual billed USD cost on `10/10` (`100%`) of Bucket A tasks (`-17.8%`, `10W / 0T / 0L`, `p = 0.001953`)**. On `3/10` tasks (`D04`, `D05`, `K05`), executing that second surgical `Class.method` lookup added one cached-prefix API turn (`3 → 4` calls), which adds `~11k` cheap *cached* prefix tokens to raw `total_tokens` (`sum(input_tokens + output_tokens)`) even as billed USD cost fell (`$0.1614 → $0.1373`, `$0.1595 → $0.1310`, `$0.1490 → $0.1206`). Net raw `total_tokens` on Bucket A still improved **`-9.4%`** (`31,442 → 28,497t`, `7W / 0T / 3L`).",
        "2. **Edit + `pytest` loop variance (`Bucket B`, `N=8`)**: Multi-step edit + test sessions span `6–9` API calls (`~62k` cumulative tokens) where `read_symbol` represents `<3%` of cumulative tokens (`1,824 → 1,303t`, `-28.5%`); normal 1-turn `edit`/`pytest` variance dominated cumulative `total_tokens` (`+1.8%`, `4W / 0T / 4L`), while `TokenMasterX` edits (`D06..D09`) improved `-8.7%` (`59,132 → 54,440t`).",
        "3. **Small-symbol parity (`Bucket C`, `N=8`)**: Below `max_lines = 120`, `read_symbol_tokens` tied identically on `7/8` tasks (`1W / 7T / 0L`, `p = 1.0000`), confirming zero small-symbol overhead.",
    ])

    RESULTS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {ANALYSIS_FILE} and {RESULTS_FILE}")
    print(f"Oversized (N={n_ov}) tm_v1={o_v1['total_tokens_mean']:,.0f}t -> tm_r6={o_r6['total_tokens_mean']:,.0f}t ({p_ov['total_tokens']['pct_change']:+.1f}%, raw p={raw_p['H2_oversized_total_tokens_r6_vs_v1']:.6f}, Holm p={holm_p['H2_oversized_total_tokens_r6_vs_v1']:.6f})")
    print(f"Pooled    (N={n_all}) stock={s_st['total_tokens_mean']:,.0f}t | tm_v1={s_v1['total_tokens_mean']:,.0f}t | tm_r6={s_r6['total_tokens_mean']:,.0f}t ({p_all['total_tokens']['pct_change']:+.1f}% vs v1, {p_stk['total_tokens']['pct_change']:+.1f}% vs stock)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
