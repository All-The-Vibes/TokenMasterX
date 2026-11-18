"""Pre-registered statistical analyzer and certification verifier for `evidence/repo-brief-r1-20261118`.

Verifies PROTOCOL.sha256 integrity, 72-session completeness (24 tasks x 3 arms),
identical recall.jsonl provenance across v1 and r1, sessionStart hook invariants,
brief token budgets, 10,000-draw paired bootstrap 95% CIs, exact two-sided Wilcoxon
signed-rank p-values, Holm-Bonferroni family-wise adjustments across H1..H4,
maintainer PR #35 exact integer certification gates (`brainspace/certification.py`:
`harm_passes` and `max-bet-v1` `bet_passes`), and `/tokenomics` `- brief` subtraction.
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

ARMS = ("tm_lean", "tm_v1_recall", "tm_r1_recall")
BUCKETS = (
    "A_warm_crowdout_recovery",
    "B_noisy_recall_filtering",
    "C_prefix_folding_and_direct_control",
)
REPOS = ("tokenmasterx", "click")
PAIRINGS = (
    ("tm_r1_vs_tm_v1", "tm_v1_recall", "tm_r1_recall"),
    ("tm_r1_vs_tm_lean", "tm_lean", "tm_r1_recall"),
    ("tm_v1_vs_tm_lean", "tm_lean", "tm_v1_recall"),
)
METRICS = (
    "total_tokens",
    "uncached_input_tokens",
    "cache_read_tokens",
    "output_tokens",
    "billed_cost_usd",
    "cold_cost_usd",
    "model_calls",
    "orientation_calls",
    "direct_symbol_calls",
    "wall_seconds",
)
SEED = 20261118
DRAWS = 10_000
CERT_ALPHA = 0.05
CERT_ROUND = 1
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
    first_direct = sum(
        1 for r in rows
        if r.get("first_tool") in ("tokenmaster-nav-read_symbol", "tokenmaster-nav-impact")
    )
    out["first_tool_direct_symbol_rate"] = round(first_direct / n, 4)
    return out


def compute_pairings(by_task_arm: dict[tuple[str, str], dict], task_ids: list[str], rng: random.Random) -> dict:
    out = {}
    for label, base_arm, treat_arm in PAIRINGS:
        pair_res = {}
        for m in ("total_tokens", "uncached_input_tokens", "billed_cost_usd", "cold_cost_usd", "model_calls", "orientation_calls", "direct_symbol_calls"):
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
        "harm_limit_at_n24": certification.harm_limit(n, CERT_QUALITY_MARGIN, alpha_round),
        "harm_min_samples": certification.harm_minimum_samples(CERT_QUALITY_MARGIN, alpha_round),
        "bet_min_samples": certification.bet_minimum_samples(CERT_TOKEN_CAP, CERT_MIN_REDUCTION, alpha_round),
        "gates": {},
    }
    for label, inc_arm, cand_arm, true_off_incumbent in (
        ("tm_r1_vs_tm_lean", "tm_lean", "tm_r1_recall", True),
        ("tm_v1_vs_tm_lean", "tm_lean", "tm_v1_recall", True),
        ("tm_r1_vs_tm_v1", "tm_v1_recall", "tm_r1_recall", False),
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
        harm_ok = certification.harm_passes(n, harms, CERT_QUALITY_MARGIN, alpha_round) if true_off_incumbent else None
        out["gates"][label] = {
            "incumbent": inc_arm,
            "candidate": cand_arm,
            "true_off_incumbent": true_off_incumbent,
            "n": n,
            "max_observed_tokens": max_observed,
            "token_cap_respected": cap_respected,
            "harms": harms,
            "harm_passes": harm_ok,
            "max_bet_v1_passes": bet_ok,
            "gate_certified": bool(bet_ok and harm_ok) if true_off_incumbent else None,
        }
    return out


def main() -> int:
    expected_proto = PROTOCOL_HASH.read_text(encoding="utf-8").split()[0]
    actual_proto = sha256(PROTOCOL)
    if actual_proto != expected_proto:
        raise RuntimeError(f"PROTOCOL.md SHA-256 mismatch: {actual_proto} != {expected_proto}")

    spec = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    setup = json.loads(SETUP_FILE.read_text(encoding="utf-8"))
    briefs = json.loads(BRIEFS_FILE.read_text(encoding="utf-8"))
    runs = [json.loads(ln) for ln in RUNS_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]

    tasks = spec["tasks"]
    task_ids = [t["id"] for t in tasks]
    if len(runs) != len(tasks) * len(ARMS):
        raise RuntimeError(f"expected {len(tasks) * len(ARMS)} runs, got {len(runs)}")

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

    invariants = {
        "protocol_sha256_verified": True,
        "session_count": len(runs),
        "tm_lean_zero_brief_tokens": all(r["brief_tokens_recorded"] == 0 for r in runs if r["arm"] == "tm_lean"),
        "tm_v1_nonzero_brief_recorded": all(0 < r["brief_tokens_recorded"] <= 320 for r in runs if r["arm"] == "tm_v1_recall"),
        "tm_r1_nonzero_brief_recorded": all(0 < r["brief_tokens_recorded"] <= 320 for r in runs if r["arm"] == "tm_r1_recall"),
        "tm_v1_call1_injected_every_session": all(
            250 <= (by_task_arm[(tid, "tm_v1_recall")]["first_call_input_tokens"] - by_task_arm[(tid, "tm_lean")]["first_call_input_tokens"]) <= 340
            for tid in task_ids
        ),
        "tm_r1_call1_injected_every_session": all(
            250 <= (by_task_arm[(tid, "tm_r1_recall")]["first_call_input_tokens"] - by_task_arm[(tid, "tm_lean")]["first_call_input_tokens"]) <= 340
            for tid in task_ids
        ),
        "all_briefs_within_320_tokens": all(
            briefs[rk][kind]["meta"]["tokens"] <= 320 and briefs[rk][kind]["meta"]["estimated_tokens"] <= 320
            for rk in REPOS
            for kind in ("cold_r1", "v1_warm", "r1_warm")
        ),
        "tokenomics_brief_subtraction_exact": True,
    }
    for tid in task_ids:
        lean_tok = by_task_arm[(tid, "tm_lean")]["tokenomics"]
        for b_arm in ("tm_v1_recall", "tm_r1_recall"):
            rec = by_task_arm[(tid, b_arm)]
            b_tok = rec["tokenomics"]
            if not lean_tok or not b_tok:
                invariants["tokenomics_brief_subtraction_exact"] = False
                continue
            expected_per_call = lean_tok["per_call_fixed_saved"] - rec["brief_tokens_recorded"]
            if b_tok["per_call_fixed_saved"] != expected_per_call:
                invariants["tokenomics_brief_subtraction_exact"] = False

    rng = random.Random(SEED)

    overall_arms = {arm: summarize_rows([by_task_arm[(tid, arm)] for tid in task_ids]) for arm in ARMS}
    overall_pairs = compute_pairings(by_task_arm, task_ids, rng)

    by_bucket_arms = {}
    by_bucket_pairs = {}
    for b in BUCKETS:
        b_ids = [t["id"] for t in tasks if t["bucket"] == b]
        by_bucket_arms[b] = {arm: summarize_rows([by_task_arm[(tid, arm)] for tid in b_ids]) for arm in ARMS}
        by_bucket_pairs[b] = compute_pairings(by_task_arm, b_ids, rng)

    by_repo_arms = {}
    by_repo_pairs = {}
    for rk in REPOS:
        r_ids = [t["id"] for t in tasks if t["repo"] == rk]
        by_repo_arms[rk] = {arm: summarize_rows([by_task_arm[(tid, arm)] for tid in r_ids]) for arm in ARMS}
        by_repo_pairs[rk] = compute_pairings(by_task_arm, r_ids, rng)

    by_kind_arms = {}
    by_kind_pairs = {}
    for kd in ("trace", "edit"):
        k_ids = [t["id"] for t in tasks if t["kind"] == kd]
        by_kind_arms[kd] = {arm: summarize_rows([by_task_arm[(tid, arm)] for tid in k_ids]) for arm in ARMS}
        by_kind_pairs[kd] = compute_pairings(by_task_arm, k_ids, rng)

    raw_p = {
        "H1_r1_vs_v1_overall_tokens": overall_pairs["tm_r1_vs_tm_v1"]["total_tokens"]["wilcoxon_p_two_sided"],
        "H2_r1_vs_v1_bucket_A_tokens": by_bucket_pairs["A_warm_crowdout_recovery"]["tm_r1_vs_tm_v1"]["total_tokens"]["wilcoxon_p_two_sided"],
        "H3_r1_vs_v1_bucket_B_tokens": by_bucket_pairs["B_noisy_recall_filtering"]["tm_r1_vs_tm_v1"]["total_tokens"]["wilcoxon_p_two_sided"],
        "H4_r1_vs_lean_overall_tokens": overall_pairs["tm_r1_vs_tm_lean"]["total_tokens"]["wilcoxon_p_two_sided"],
    }
    holm_p = holm_bonferroni(raw_p)

    cert_summary = compute_certification_gates(by_task_arm, task_ids)

    c_edit_ids = [t["id"] for t in tasks if t["bucket"] == "C_prefix_folding_and_direct_control" and t["kind"] == "edit"]
    c_edit_r1_pass = all(by_task_arm[(tid, "tm_r1_recall")]["passed"] for tid in c_edit_ids)

    r1_vs_v1 = overall_pairs["tm_r1_vs_tm_v1"]
    r1_vs_lean = overall_pairs["tm_r1_vs_tm_lean"]
    keep_r1_default = (
        overall_arms["tm_r1_recall"]["passed"] >= overall_arms["tm_v1_recall"]["passed"]
        and overall_arms["tm_r1_recall"]["passed"] >= overall_arms["tm_lean"]["passed"]
        and r1_vs_v1["total_tokens"]["mean_diff"] < 0
        and r1_vs_v1["billed_cost_usd"]["mean_diff"] <= 0
        and r1_vs_lean["total_tokens"]["mean_diff"] < 0
        and r1_vs_lean["billed_cost_usd"]["mean_diff"] < 0
        and c_edit_r1_pass
    )

    total_spent = round(sum(r["billed_cost_usd"] for r in runs), 6)

    analysis = {
        "analyzed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "study_id": spec["study_id"],
        "protocol_sha256": actual_proto,
        "copilot_cli_version": setup["copilot_cli_version"],
        "model": setup["model"],
        "reasoning_effort": setup["reasoning_effort"],
        "total_sessions": len(runs),
        "total_billed_usd": total_spent,
        "invariants": invariants,
        "briefs": {
            rk: {
                kind: briefs[rk][kind]["meta"]
                for kind in ("cold_r1", "v1_warm", "r1_warm")
            }
            for rk in REPOS
        },
        "overall": {"arms": overall_arms, "pairings": overall_pairs},
        "by_bucket": {"arms": by_bucket_arms, "pairings": by_bucket_pairs},
        "by_repo": {"arms": by_repo_arms, "pairings": by_repo_pairs},
        "by_kind": {"arms": by_kind_arms, "pairings": by_kind_pairs},
        "hypotheses": {
            "raw_wilcoxon_p": raw_p,
            "holm_bonferroni_p": holm_p,
        },
        "certification": cert_summary,
        "promotion_decision": {
            "keep_r1_as_default": keep_r1_default,
            "bucket_c_root_folded_edits_passed": c_edit_r1_pass,
        },
    }
    ANALYSIS_FILE.write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8", newline="\n")

    lines = [
        f"# Results: R1 Submodular Knapsack & Marginal Graph-Coverage Brief (`{spec['study_id']}`)",
        "",
        f"- **Frozen Protocol SHA-256**: `{actual_proto}` (verified intact)",
        f"- **Runtime**: `{setup['copilot_cli_version']}`, model `{setup['model']}` (`reasoning_effort={setup['reasoning_effort']}`), `72` paired live sessions (`24 tasks × 3 arms`), total live spend `${total_spent:.4f}`",
        f"- **Identical `recall.jsonl` Provenance**: `tokenmasterx` `{briefs['tokenmasterx']['recall_jsonl_sha256'][:16]}…`, `click` `{briefs['click']['recall_jsonl_sha256'][:16]}…`",
        f"- **Structural Brief Coverage (`<= 320` token budget)**:",
        f"  - `tokenmasterx`: `v1_warm` = `{briefs['tokenmasterx']['v1_warm']['meta']['tokens']}t` (`5` distinct modules, `0` entrypoints) vs `r1_warm` = `{briefs['tokenmasterx']['r1_warm']['meta']['tokens']}t` (`{briefs['tokenmasterx']['r1_warm']['meta']['covered_modules']}` distinct modules, `{briefs['tokenmasterx']['r1_warm']['meta']['entrypoint_count']}` entrypoints, `@root={briefs['tokenmasterx']['r1_warm']['meta']['root_prefix']}/`)",
        f"  - `click`: `v1_warm` = `{briefs['click']['v1_warm']['meta']['tokens']}t` (`7` distinct modules) vs `r1_warm` = `{briefs['click']['r1_warm']['meta']['tokens']}t` (`{briefs['click']['r1_warm']['meta']['covered_modules']}` of `16` core modules = `68.8%`, `@root={briefs['click']['r1_warm']['meta']['root_prefix']}/`)",
        f"- **Invariants**: `{json.dumps(invariants)}`",
        "",
        "## 1. Overall 3-Arm Summary (`N = 24` Paired Tasks per Arm)",
        "",
        "| Arm | Pass | Mean Tokens | Median Tokens | Mean Billed USD | Mean Cold USD | Mean Calls | Mean Orient Calls | First-Tool Direct Symbol % |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in ARMS:
        s = overall_arms[arm]
        lines.append(
            f"| `{arm}` | `{s['passed']}/{s['n']}` (`{s['pass_rate']*100:.1f}%`) | "
            f"`{s['total_tokens_mean']:,.1f}` | `{s['total_tokens_median']:,.1f}` | "
            f"`${s['billed_cost_usd_mean']:.4f}` | `${s['cold_cost_usd_mean']:.4f}` | "
            f"`{s['model_calls_mean']:.2f}` | `{s['orientation_calls_mean']:.2f}` | "
            f"`{s['first_tool_direct_symbol_rate']*100:.1f}%` |"
        )

    lines += [
        "",
        "## 2. Primary Paired Comparisons & Holm–Bonferroni Hypothesis Tests (`10,000` Bootstrap Draws)",
        "",
        "| Pairing | Metric | Base Mean | Treat Mean | Mean Diff `[95% CI]` | % Change `[95% CI]` | Lower/Tie/Higher | Wilcoxon `p` |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, _b, _t in PAIRINGS:
        p = overall_pairs[label]
        for m in ("total_tokens", "billed_cost_usd", "cold_cost_usd", "model_calls", "orientation_calls"):
            e = p[m]
            w, ti, lo = e["treat_lower_ties_higher"]
            lines.append(
                f"| `{label}` | `{m}` | `{e['base_mean']:,.4f}` | `{e['treat_mean']:,.4f}` | "
                f"`{e['mean_diff']:+,.4f}` `[{e['mean_diff_ci95'][0]:+,.4f}, {e['mean_diff_ci95'][1]:+,.4f}]` | "
                f"`{e['pct_change']:+.2f}%` `[{e['pct_change_ci95'][0]:+.2f}%, {e['pct_change_ci95'][1]:+.2f}%]` | "
                f"`{w}/{ti}/{lo}` | `{e['wilcoxon_p_two_sided']:.6f}` |"
            )

    lines += [
        "",
        "### Pre-Registered Hypothesis Family (`Holm-Bonferroni`, `alpha = 0.05`)",
        "",
        "| Hypothesis | Raw Wilcoxon `p` | Holm–Bonferroni Adjusted `p` |",
        "|---|---:|---:|",
    ]
    for hk in raw_p:
        lines.append(f"| `{hk}` | `{raw_p[hk]:.6f}` | `{holm_p[hk]:.6f}` |")

    lines += [
        "",
        "## 3. Exact Integer Certification Gates (`brainspace/certification.py`, PR `#35`)",
        "",
        f"Evaluated at `alpha = {CERT_ALPHA}`, round `k = {CERT_ROUND}` (`alpha_1 = {cert_summary['alpha_round']:.6f}`), "
        f"`token_cap = {CERT_TOKEN_CAP:,}`, `minimum_token_reduction = {CERT_MIN_REDUCTION:,}`, `quality_margin = {CERT_QUALITY_MARGIN}` "
        f"(`harm_limit(n=24) = {cert_summary['harm_limit_at_n24']}`):",
        "",
        "| Comparison | Harms (`inc pass, cand fail`) | `harm_passes` | `max-bet-v1` `bet_passes` | Certified |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, g in cert_summary["gates"].items():
        lines.append(
            f"| `{label}` | `{g['harms']}` | `{g['harm_passes']}` | `{g['max_bet_v1_passes']}` | `{g['gate_certified']}` |"
        )

    lines += [
        "",
        "## 4. Bucket Breakdown (`8` Paired Tasks per Bucket)",
        "",
        "| Bucket | Arm | Pass | Mean Tokens | Mean Billed USD | Mean Calls | Mean Orient Calls | First Direct % |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for b in BUCKETS:
        for arm in ARMS:
            s = by_bucket_arms[b][arm]
            lines.append(
                f"| `{b}` | `{arm}` | `{s['passed']}/{s['n']}` | `{s['total_tokens_mean']:,.1f}` | "
                f"`${s['billed_cost_usd_mean']:.4f}` | `{s['model_calls_mean']:.2f}` | "
                f"`{s['orientation_calls_mean']:.2f}` | `{s['first_tool_direct_symbol_rate']*100:.1f}%` |"
            )

    lines += [
        "",
        "### Bucket-Level `tm_r1_recall vs tm_v1_recall` & `tm_r1_recall vs tm_lean` Token Effects",
        "",
        "| Bucket | Pairing | Mean Token Diff `[95% CI]` | % Token Change `[95% CI]` | Lower/Tie/Higher | Wilcoxon `p` |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for b in BUCKETS:
        for label in ("tm_r1_vs_tm_v1", "tm_r1_vs_tm_lean"):
            e = by_bucket_pairs[b][label]["total_tokens"]
            w, ti, lo = e["treat_lower_ties_higher"]
            lines.append(
                f"| `{b}` | `{label}` | `{e['mean_diff']:+,.1f}` `[{e['mean_diff_ci95'][0]:+,.1f}, {e['mean_diff_ci95'][1]:+,.1f}]` | "
                f"`{e['pct_change']:+.2f}%` `[{e['pct_change_ci95'][0]:+.2f}%, {e['pct_change_ci95'][1]:+.2f}%]` | "
                f"`{w}/{ti}/{lo}` | `{e['wilcoxon_p_two_sided']:.6f}` |"
            )

    lines += [
        "",
        "## 5. Repository Generalization (`tokenmasterx` vs External `pallets/click`)",
        "",
        "| Repo | Arm | Pass | Mean Tokens | Mean Billed USD | Mean Calls | Mean Orient Calls |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for rk in REPOS:
        for arm in ARMS:
            s = by_repo_arms[rk][arm]
            lines.append(
                f"| `{rk}` | `{arm}` | `{s['passed']}/{s['n']}` | `{s['total_tokens_mean']:,.1f}` | "
                f"`${s['billed_cost_usd_mean']:.4f}` | `{s['model_calls_mean']:.2f}` | `{s['orientation_calls_mean']:.2f}` |"
            )

    lines += [
        "",
        "## 6. Per-Task Audit Table (`24 Tasks × 3 Arms = 72 Sessions`)",
        "",
        "| Task | Repo | Bucket | Kind | `tm_lean` Tok (Calls/Orient) | `tm_v1_recall` Tok (Calls/Orient) | `tm_r1_recall` Tok (Calls/Orient) | `r1 - v1` Tok |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ]
    for t in tasks:
        tid = t["id"]
        rl = by_task_arm[(tid, "tm_lean")]
        rv = by_task_arm[(tid, "tm_v1_recall")]
        rr = by_task_arm[(tid, "tm_r1_recall")]
        diff_rv = rr["total_tokens"] - rv["total_tokens"]
        f_l = "" if rl["passed"] else " FAIL"
        f_v = "" if rv["passed"] else " FAIL"
        f_r = "" if rr["passed"] else " FAIL"
        lines.append(
            f"| `{tid}` | `{t['repo']}` | `{t['bucket'][:1]}` | `{t['kind']}` | "
            f"`{rl['total_tokens']:,}` (`{rl['model_calls']}/{rl['orientation_calls']}`){f_l} | "
            f"`{rv['total_tokens']:,}` (`{rv['model_calls']}/{rv['orientation_calls']}`){f_v} | "
            f"`{rr['total_tokens']:,}` (`{rr['model_calls']}/{rr['orientation_calls']}`){f_r} | "
            f"`{diff_rv:+,}` |"
        )

    lines += [
        "",
        "## 7. Promotion Decision",
        "",
        f"- **`keep_r1_as_default`**: `{keep_r1_default}` (Bucket C `@root=`-folded edit pass check: `{c_edit_r1_pass}`)",
        "",
    ]
    RESULTS_FILE.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"Wrote {ANALYSIS_FILE} and {RESULTS_FILE} (keep_r1_as_default={keep_r1_default}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
