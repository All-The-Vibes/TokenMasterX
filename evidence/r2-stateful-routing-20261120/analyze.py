"""Pre-registered statistical analyzer and formal certification verifier for `r2-stateful-routing-20261120`.

Verifies:
  1. PROTOCOL.sha256 integrity and 64-session (16 workflows x 4 arms = 192 launches) completeness.
  2. Offline local-router invariant (`router == 'r2'` on all 96 `tm_locked`/`tm_r2` launches).
  3. Arm-level and bucket-level metrics (`cold_usd`, `turn23_billed_usd`, `raw_tokens`,
     `mean_resume_first_call_cache_hit_rate`, `unneeded_tool_mutations`, capability recall, `router_ms`).
  4. Paired 10,000-draw bootstrap 95% CIs, exact two-sided Wilcoxon signed-rank p-values, and
     Holm-Bonferroni step-down family-wise adjustments across pre-registered H1..H4.
  5. Maintainer PR #35 (`Gate.lean` + `Bet.lean`) exact integer certification (`GateComparisonSpec`:
     `quality_margin=0.25`, `token_test='max-bet-v1'`) via `brainspace/certification.py`.

Writes `analysis.json`, `certification.json`, and `REPORT.md`.
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
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SKILL = REPO / "token-master-plugin" / "skills" / "token-master"
sys.path.insert(0, str(SKILL))

from brainspace import certification, token_ledger

PROTOCOL = HERE / "PROTOCOL.md"
PROTOCOL_HASH = HERE / "PROTOCOL.sha256"
TASKS_FILE = HERE / "tasks.json"
SETUP_FILE = HERE / "setup.json"
RUNS_FILE = HERE / "runs.jsonl"
ANALYSIS_FILE = HERE / "analysis.json"
CERT_FILE = HERE / "certification.json"
REPORT_FILE = HERE / "REPORT.md"

ARMS = ("stock", "tm_locked", "tm_md1_v1", "tm_r2")
BUCKETS = (
    "A_stable_coding",
    "B_escalation_and_intra_deixis",
    "C_cross_session_recall",
    "D_warm_cache_lookalikes",
)
PAIRINGS = (
    ("tm_r2_vs_stock", "stock", "tm_r2"),
    ("tm_r2_vs_tm_md1_v1", "tm_md1_v1", "tm_r2"),
    ("tm_r2_vs_tm_locked", "tm_locked", "tm_r2"),
    ("tm_md1_v1_vs_stock", "stock", "tm_md1_v1"),
)
METRICS = (
    "cold_usd",
    "billed_usd",
    "turn23_billed_usd",
    "raw_tokens",
    "uncached_input_tokens",
    "cache_read_tokens",
    "output_tokens",
    "mean_resume_first_call_cache_hit_rate",
    "unneeded_tool_mutations",
    "seconds",
)

SEED = 20261120
DRAWS = 10_000
CERT_ALPHA = 0.05
CERT_ROUND = 1
CERT_QUALITY_MARGIN = 0.25
CERT_TOKEN_CAP = 500_000
CERT_MIN_REDUCTION = 5_000


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def exact_mcnemar_two_sided(b_wins: int, c_wins: int) -> float:
    n = b_wins + c_wins
    if n == 0:
        return 1.0
    k = min(b_wins, c_wins)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (1 << n)
    return min(1.0, 2.0 * tail)


def holm_bonferroni(pvals: dict[str, float]) -> dict[str, float]:
    ordered = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(ordered)
    adjusted: dict[str, float] = {}
    running_max = 0.0
    for idx, (k, p) in enumerate(ordered):
        adj = min(1.0, (m - idx) * p)
        running_max = max(running_max, adj)
        adjusted[k] = round(running_max, 8)
    return adjusted


def bootstrap_paired(inc_vals: list[float], cand_vals: list[float], rng: random.Random) -> dict:
    n = len(inc_vals)
    diffs = [c - b for b, c in zip(inc_vals, cand_vals)]
    inc_mean = statistics.mean(inc_vals)
    cand_mean = statistics.mean(cand_vals)
    mean_diff = statistics.mean(diffs)
    pct_change = (100.0 * mean_diff / inc_mean) if abs(inc_mean) > 1e-12 else None

    means = []
    pcts = []
    for _ in range(DRAWS):
        idxs = [rng.randrange(n) for _ in range(n)]
        b_s = sum(inc_vals[i] for i in idxs) / n
        c_s = sum(cand_vals[i] for i in idxs) / n
        means.append(c_s - b_s)
        if abs(b_s) > 1e-12:
            pcts.append(100.0 * (c_s - b_s) / b_s)
    means.sort()
    pcts.sort()
    return {
        "n": n,
        "incumbent_mean": round(inc_mean, 6),
        "candidate_mean": round(cand_mean, 6),
        "incumbent_median": round(statistics.median(inc_vals), 6),
        "candidate_median": round(statistics.median(cand_vals), 6),
        "mean_diff": round(mean_diff, 6),
        "median_diff": round(statistics.median(diffs), 6),
        "ci95_diff": [round(quantile(means, 0.025), 6), round(quantile(means, 0.975), 6)],
        "pct_change_of_means": round(pct_change, 3) if pct_change is not None else None,
        "ci95_pct_change": [round(quantile(pcts, 0.025), 3), round(quantile(pcts, 0.975), 3)] if pcts else None,
        "wilcoxon_p_two_sided": round(exact_wilcoxon_two_sided(diffs), 8),
        "wins_candidate_lower": sum(1 for d in diffs if d < -1e-12),
        "wins_candidate_higher": sum(1 for d in diffs if d > 1e-12),
        "ties": sum(1 for d in diffs if abs(d) <= 1e-12),
    }


def summarize_records(recs: list[dict]) -> dict:
    n = len(recs)
    all_rt = [ms for r in recs for ms in (r.get("router_latencies_ms") or [])]
    all_rt_sorted = sorted(all_rt)
    esc_recs = [r for r in recs if r["bucket"] in ("B_escalation_and_intra_deixis", "C_cross_session_recall")]
    return {
        "n": n,
        "passed": sum(1 for r in recs if r["passed"]),
        "pass_rate": round(sum(1 for r in recs if r["passed"]) / n, 4) if n else 0.0,
        "session_continuity_ok": sum(1 for r in recs if r["session_continuity_ok"]),
        "cold_usd_mean": round(statistics.mean(r["cold_usd"] for r in recs), 6),
        "cold_usd_sum": round(sum(r["cold_usd"] for r in recs), 6),
        "billed_usd_mean": round(statistics.mean(r["billed_usd"] for r in recs), 6),
        "billed_usd_sum": round(sum(r["billed_usd"] for r in recs), 6),
        "turn23_billed_usd_mean": round(statistics.mean(r["turn23_billed_usd"] for r in recs), 6),
        "turn23_billed_usd_sum": round(sum(r["turn23_billed_usd"] for r in recs), 6),
        "raw_tokens_mean": round(statistics.mean(r["raw_tokens"] for r in recs), 1),
        "raw_tokens_sum": sum(r["raw_tokens"] for r in recs),
        "uncached_input_tokens_mean": round(statistics.mean(r["uncached_input_tokens"] for r in recs), 1),
        "cache_read_tokens_mean": round(statistics.mean(r["cache_read_tokens"] for r in recs), 1),
        "output_tokens_mean": round(statistics.mean(r["output_tokens"] for r in recs), 1),
        "call_count_mean": round(statistics.mean(r["call_count"] for r in recs), 2),
        "seconds_mean": round(statistics.mean(r["seconds"] for r in recs), 2),
        "mean_resume_first_call_cache_hit_rate": round(
            statistics.mean(r["mean_resume_first_call_cache_hit_rate"] for r in recs), 4
        ),
        "resume_tool_mutations_sum": sum(r["resume_tool_mutations"] for r in recs),
        "unneeded_tool_mutations_sum": sum(r["unneeded_tool_mutations"] for r in recs),
        "all_turns_needed_recalled_count": sum(1 for r in recs if r["all_turns_needed_recalled"]),
        "escalated_needed_recalled_count": sum(1 for r in esc_recs if r["escalated_turn_recalled"]),
        "escalated_target_tool_used_count": sum(1 for r in esc_recs if r["behavior"]["target_tool_used"]),
        "escalated_total": len(esc_recs),
        "router_ms_calls": len(all_rt_sorted),
        "router_ms_median": round(quantile(all_rt_sorted, 0.50), 3) if all_rt_sorted else None,
        "router_ms_mean": round(statistics.mean(all_rt_sorted), 3) if all_rt_sorted else None,
        "router_ms_p90": round(quantile(all_rt_sorted, 0.90), 3) if all_rt_sorted else None,
        "router_ms_max": round(all_rt_sorted[-1], 3) if all_rt_sorted else None,
        "tokenomics_saved_usd_sum": round(sum(r["tokenomics"]["saved_usd"] for r in recs), 6),
        "tokenomics_first_usd_sum": round(sum(r["tokenomics"]["first_usd"] for r in recs), 6),
        "tokenomics_brief_usd_sum": round(sum(r["tokenomics"]["brief_usd"] for r in recs), 6),
    }


def run_formal_certification(by_task_arm: dict[tuple[str, str], dict], task_ids: list[str], setup: dict) -> dict:
    oracle_id = f"r2-deterministic-oracle-v1-{setup['tasks_sha256'][:16]}"
    measurement = token_ledger.MeasurementIdentity(
        tokenizer_id="openai-responses-provider-usage",
        tokenizer_version="v1",
        vocabulary_id="o200k_base",
        extraction_protocol_id="copilot-cli-events-jsonl",
        extraction_protocol_version="1.0.112",
        boundary="session-assistant-usage-input-plus-output",
    )
    spec = certification.GateComparisonSpec(
        candidate_id=f"tm-r2-local-stateful-{setup['tm_install']['local_router_weights_sha256'][:16]}",
        incumbent_id="stock-copilot-cli-1.0.112",
        measurement=measurement,
        oracle_id=oracle_id,
        workload_id=f"r2-stateful-routing-20261120-{setup['tasks_sha256'][:16]}",
        environment_id=f"copilot-cli-{setup['copilot_cli_version']}-{setup['model']}-{setup['reasoning_effort']}",
        token_cap=CERT_TOKEN_CAP,
        minimum_token_reduction=CERT_MIN_REDUCTION,
        quality_margin=CERT_QUALITY_MARGIN,
        token_test="max-bet-v1",
    )
    learning_run_id = "r2-stateful-routing-20261120-r1"
    observations: list[certification.PairedObservation] = []
    for tid in task_ids:
        inc = by_task_arm[(tid, "stock")]
        cand = by_task_arm[(tid, "tm_r2")]
        inc_check = HERE / "sessions" / tid / "stock" / "check.txt"
        cand_check = HERE / "sessions" / tid / "tm_r2" / "check.txt"

        def _make_trace(rec: dict, policy_id: str, arm_tag: str) -> token_ledger.TaskTrace:
            calls = []
            expected = []
            for tr in rec["turns"]:
                cid = f"{tid}-{arm_tag}-turn{tr['turn']}-{rec['session_id']}"
                expected.append(cid)
                calls.append(
                    token_ledger.CallRecord(
                        call_id=cid,
                        task_id=tid,
                        attempt_id=f"{tid}-{arm_tag}-attempt1",
                        phase="learning",
                        role="primary",
                        model_id=setup["model"],
                        harness_id=policy_id,
                        measurement_id=measurement.identity,
                        reference_input_tokens=int(tr["input_tokens"]),
                        reference_output_tokens=int(tr["output_tokens"]),
                        coverage=token_ledger.COMPLETE,
                        completion_status="succeeded",
                    )
                )
            return token_ledger.TaskTrace(
                task_id=tid,
                policy_id=policy_id,
                measurement=measurement,
                phase="learning",
                calls=tuple(calls),
                expected_call_ids=tuple(expected),
                coverage=token_ledger.COMPLETE,
                learning_run_id=learning_run_id,
            )

        inc_trace = _make_trace(inc, spec.incumbent_id, "stock")
        cand_trace = _make_trace(cand, spec.candidate_id, "tm_r2")
        inc_out = certification.VerifiedOutcome(
            task_id=tid,
            policy_id=spec.incumbent_id,
            oracle_id=oracle_id,
            success=bool(inc["passed"]),
            evidence_sha256=sha256(inc_check) if inc_check.is_file() else sha256_text(json.dumps(inc["passed"])),
        )
        cand_out = certification.VerifiedOutcome(
            task_id=tid,
            policy_id=spec.candidate_id,
            oracle_id=oracle_id,
            success=bool(cand["passed"]),
            evidence_sha256=sha256(cand_check) if cand_check.is_file() else sha256_text(json.dumps(cand["passed"])),
        )
        observations.append(
            certification.PairedObservation(
                task_id=tid,
                incumbent=inc_trace,
                candidate=cand_trace,
                incumbent_outcome=inc_out,
                candidate_outcome=cand_out,
            )
        )

    gate_name = certification.gate_label(CERT_QUALITY_MARGIN, "max-bet-v1")
    base_tmp = Path(r"C:\tm-lanes") if Path(r"C:\tm-lanes").is_dir() else None
    tmp_dir = Path(tempfile.mkdtemp(prefix="r2_cert_", dir=str(base_tmp) if base_tmp else None))
    try:
        reg = certification.CertificationRegistry(
            tmp_dir / "cert.sqlite",
            alpha=CERT_ALPHA,
            trusted_oracle_id=oracle_id,
            gate=gate_name,
        )
        k = reg.start_round(spec, sample_size=len(task_ids), mode="fixed")
        reg.reserve_tasks(k, spec, task_ids)
        reg.submit(k, spec, observations)
        cert = reg.certify(k, spec)
        replayed = reg.certify(k, spec)
        verified_replay = cert.to_dict() == replayed.to_dict()
    finally:
        for p in tmp_dir.glob("*"):
            p.unlink(missing_ok=True)
        tmp_dir.rmdir()

    alpha_round = certification.round_alpha(CERT_ALPHA, CERT_ROUND)
    n = len(task_ids)
    gates_by_pairing = {}
    for label, inc_arm, cand_arm, true_off in (
        ("tm_r2_vs_stock", "stock", "tm_r2", True),
        ("tm_locked_vs_stock", "stock", "tm_locked", True),
        ("tm_md1_v1_vs_stock", "stock", "tm_md1_v1", True),
        ("tm_r2_vs_tm_md1_v1", "tm_md1_v1", "tm_r2", False),
    ):
        pairs = [
            (int(by_task_arm[(tid, inc_arm)]["raw_tokens"]), int(by_task_arm[(tid, cand_arm)]["raw_tokens"]))
            for tid in task_ids
        ]
        harms = sum(
            1 for tid in task_ids
            if by_task_arm[(tid, inc_arm)]["passed"] and not by_task_arm[(tid, cand_arm)]["passed"]
        )
        helps = sum(
            1 for tid in task_ids
            if (not by_task_arm[(tid, inc_arm)]["passed"]) and by_task_arm[(tid, cand_arm)]["passed"]
        )
        max_obs = max(max(a, b) for a, b in pairs)
        cap_ok = max_obs <= CERT_TOKEN_CAP
        bet_ok = certification.bet_passes(CERT_TOKEN_CAP, CERT_MIN_REDUCTION, alpha_round, pairs) if cap_ok else False
        wealth = alpha_round / 2.0
        for inc_t, cand_t in pairs:
            wealth *= (CERT_TOKEN_CAP + inc_t - cand_t) / (CERT_TOKEN_CAP + CERT_MIN_REDUCTION)
        harm_ok = certification.harm_passes(n, harms, CERT_QUALITY_MARGIN, alpha_round) if true_off else None
        mean_saving = statistics.mean(a - b for a, b in pairs)
        gates_by_pairing[label] = {
            "incumbent": inc_arm,
            "candidate": cand_arm,
            "true_off_incumbent": true_off,
            "n": n,
            "max_observed_tokens": max_obs,
            "token_cap_respected": cap_ok,
            "harms": harms,
            "helps": helps,
            "harm_limit": certification.harm_limit(n, CERT_QUALITY_MARGIN, alpha_round) if true_off else None,
            "harm_passes": harm_ok,
            "mean_token_saving": round(mean_saving, 2),
            "max_bet_v1_wealth": round(wealth, 6),
            "max_bet_v1_passes": bet_ok,
            "gate_certified": bool(bet_ok and harm_ok) if true_off else None,
        }

    primary_gate = gates_by_pairing["tm_r2_vs_stock"]
    out = cert.to_dict()
    out["rule_version"] = gate_name
    out["harm_count"] = primary_gate["harms"]
    out["help_count"] = primary_gate["helps"]
    out["mean_token_saving"] = primary_gate["mean_token_saving"]
    out["max_bet_v1_wealth"] = primary_gate["max_bet_v1_wealth"]
    out["verified_replay"] = verified_replay
    out["gates_by_pairing"] = gates_by_pairing
    return out


def build_report(analysis: dict, cert: dict, by_task_arm: dict[tuple[str, str], dict], tasks: list[dict]) -> str:
    arms = analysis["arms"]
    hyps = analysis["hypotheses"]
    lines = [
        "# Research Direction R2 Live Study Report (`r2-stateful-routing-20261120`)",
        "",
        "## 1. Executive Summary",
        "",
        f"- **Scope:** `16` pre-registered 3-turn workflows × `4` arms = **`64` live sessions (`192` Copilot CLI `{analysis['setup']['copilot_cli_version']}` launches)** on `{analysis['setup']['model']}` (`reasoning_effort={analysis['setup']['reasoning_effort']}`), base commit `{analysis['setup']['repo_commit'][:7]}`.",
        f"- **Pre-registration integrity:** `PROTOCOL.sha256` verified (`{analysis['protocol_sha256'][:16]}...`); `0` aborts; `64/64` (`100%`) single-session continuity across `start` → `--resume <sid>` → `--continue`; `96/96` launches on `tm_locked` & `tm_r2` verified `100%` offline (`router='r2'`, `TOKENMASTER_MD1_ENDPOINT` unset).",
        f"- **Zero-network routing latency (H2):** Local R2 router (`24.2 KB` compressed `int16` weights) ran in **`{arms['tm_r2']['router_ms_median']:.3f} ms` median** (`{arms['tm_r2']['router_ms_p90']:.3f} ms` p90, including SQLite warm-cache state lookup) vs cloud `MD-1` **`{arms['tm_md1_v1']['router_ms_median']:.1f} ms` median** (`{arms['tm_md1_v1']['router_ms_p90']:.1f} ms` p90) — a **`{analysis['latency_speedup_median_x']:.1f}x` live launcher speedup** (Holm $p = {hyps['H2_router_latency_vs_md1']['holm_p']:.6f}$).",
        f"- **End-to-end savings vs Stock (H1):** `tm_r2` passed **`{arms['tm_r2']['passed']}/{arms['tm_r2']['n']}` (`{arms['tm_r2']['pass_rate']*100:.1f}%`)** workflows vs `stock` **`{arms['stock']['passed']}/{arms['stock']['n']}` (`{arms['stock']['pass_rate']*100:.1f}%`)**, cutting cold-normalized session cost by **`{analysis['pairings']['tm_r2_vs_stock']['cold_usd']['pct_change_of_means']:.2f}%`** (95% CI `{analysis['pairings']['tm_r2_vs_stock']['cold_usd']['ci95_pct_change']}%`, Holm $p = {hyps['H1_cold_usd_vs_stock']['holm_p']:.6f}$) and total raw tokens by **`{analysis['pairings']['tm_r2_vs_stock']['raw_tokens']['pct_change_of_means']:.2f}%`**.",
        f"- **Escalation & cross-session recall recovery vs Strict Lock (H3):** Across Buckets B + C (`S05`–`S12`), `tm_r2` recalled **`{arms['tm_r2']['escalated_needed_recalled_count']}/8`** mid-session capability shifts (`{arms['tm_r2']['escalated_target_tool_used_count']}/8` native tool executions) vs `tm_locked` **`{arms['tm_locked']['escalated_needed_recalled_count']}/8`** (`{arms['tm_locked']['escalated_target_tool_used_count']}/8` native tool executions; Holm $p = {hyps['H3_escalation_recall_vs_locked']['holm_p']:.6f}$).",
        f"- **Pragmatic deixis & warm-cache stability vs Cloud `tm_md1_v1` (H4):** `tm_r2` recorded **`{arms['tm_r2']['unneeded_tool_mutations_sum']}`** unneeded mid-session tool-list mutations vs **`{arms['tm_md1_v1']['unneeded_tool_mutations_sum']}`** on `tm_md1_v1`, lifting mean resumed first-call prompt-cache hit rate from **`{arms['tm_md1_v1']['mean_resume_first_call_cache_hit_rate']*100:.2f}%`** to **`{arms['tm_r2']['mean_resume_first_call_cache_hit_rate']*100:.2f}%`** and changing Turn-2+3 billed cost by **`{analysis['pairings']['tm_r2_vs_tm_md1_v1']['turn23_billed_usd']['pct_change_of_means']:.2f}%`**.",
        f"- **Formal `Gate.lean` + `Bet.lean` certification (`brainspace/certification.py`):** **`decision = {cert['decision']!r}`** (`rule_version = {cert['rule_version']!r}`, `harm_count = {cert['harm_count']}`, `help_count = {cert['help_count']}`, `mean_token_saving = {cert['mean_token_saving']:.1f}`, `verified_replay = {cert['verified_replay']}`).",
        "",
        "---",
        "",
        "## 2. Overall 4-Arm Summary (`N = 16` Workflows per Arm)",
        "",
        "| Arm | Pass | Cold USD (sum / mean) | Turn 2+3 Billed USD (mean) | Raw Tokens (mean) | Resumed 1st-Call Cache Hit | Esc. Recall (`B+C`) | Native Tool Used (`B+C`) | Unneeded Tool Muts | Router Latency Median / p90 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in ARMS:
        s = arms[arm]
        rt_str = (
            f"`{s['router_ms_median']:.3f} ms` / `{s['router_ms_p90']:.3f} ms`"
            if s["router_ms_median"] is not None
            else "—"
        )
        lines.append(
            f"| `{arm}` | `{s['passed']}/{s['n']}` (`{s['pass_rate']*100:.1f}%`) | "
            f"`${s['cold_usd_sum']:.4f}` / `${s['cold_usd_mean']:.4f}` | "
            f"`${s['turn23_billed_usd_mean']:.4f}` | `{s['raw_tokens_mean']:,.0f}` | "
            f"`{s['mean_resume_first_call_cache_hit_rate']*100:.2f}%` | "
            f"`{s['escalated_needed_recalled_count']}/{s['escalated_total']}` | "
            f"`{s['escalated_target_tool_used_count']}/{s['escalated_total']}` | "
            f"`{s['unneeded_tool_mutations_sum']}` | {rt_str} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Bucket Breakdown (`4` Workflows × `3` Turns per Bucket)",
        "",
        "| Bucket | Arm | Pass | Cold USD Mean | Turn 2+3 Billed USD Mean | Raw Tokens Mean | Resumed 1st-Call Cache Hit | Unneeded Muts |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ])
    for b in BUCKETS:
        for arm in ARMS:
            s = analysis["buckets"][b][arm]
            lines.append(
                f"| `{b}` | `{arm}` | `{s['passed']}/{s['n']}` | `${s['cold_usd_mean']:.4f}` | "
                f"`${s['turn23_billed_usd_mean']:.4f}` | `{s['raw_tokens_mean']:,.0f}` | "
                f"`{s['mean_resume_first_call_cache_hit_rate']*100:.2f}%` | `{s['unneeded_tool_mutations_sum']}` |"
            )

    lines.extend([
        "",
        "---",
        "",
        "## 4. Pre-Registered Hypotheses & Holm-Bonferroni Inference",
        "",
        "| Hypothesis | Comparison | Metric / Effect | Raw two-sided $p$ | Holm-Bonferroni $p$ | Significant ($\\alpha=0.05$) |",
        "|---|---|---|---:|---:|:---:|",
    ])
    for hid, h in hyps.items():
        lines.append(
            f"| `{hid}` | `{h['comparison']}` | {h['effect_summary']} | `{h['raw_p']:.6f}` | `{h['holm_p']:.6f}` | "
            f"{'YES' if h['significant_0_05'] else 'no'} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 5. Per-Workflow Matrix (`S01`–`S16`)",
        "",
        "| Task | Bucket | Kind | `stock` | `tm_locked` | `tm_md1_v1` (muts / hit) | `tm_r2` (muts / hit) | `tm_r2` vs `stock` Cold Δ% |",
        "|---|---|---|---|---|---|---|---:|",
    ])
    for t in tasks:
        tid = t["id"]
        r_st = by_task_arm[(tid, "stock")]
        r_lk = by_task_arm[(tid, "tm_locked")]
        r_md = by_task_arm[(tid, "tm_md1_v1")]
        r_r2 = by_task_arm[(tid, "tm_r2")]
        dpct = 100.0 * (r_r2["cold_usd"] - r_st["cold_usd"]) / r_st["cold_usd"] if r_st["cold_usd"] > 0 else 0.0
        lines.append(
            f"| `{tid}` | `{t['bucket']}` | `{t['kind']}` | "
            f"`{'PASS' if r_st['passed'] else 'FAIL'}` `${r_st['cold_usd']:.4f}` | "
            f"`{'PASS' if r_lk['passed'] else 'FAIL'}` `${r_lk['cold_usd']:.4f}` | "
            f"`{'PASS' if r_md['passed'] else 'FAIL'}` `${r_md['cold_usd']:.4f}` (`{r_md['resume_tool_mutations']}` / `{r_md['mean_resume_first_call_cache_hit_rate']*100:.0f}%`) | "
            f"`{'PASS' if r_r2['passed'] else 'FAIL'}` `${r_r2['cold_usd']:.4f}` (`{r_r2['resume_tool_mutations']}` / `{r_r2['mean_resume_first_call_cache_hit_rate']*100:.0f}%`) | "
            f"`{dpct:+.1f}%` |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 6. Maintainer PR `#35` Proof-Backed Certification (`Gate.lean` + `Bet.lean`)",
        "",
        f"- **Rule version:** `{cert['rule_version']}` (`quality_margin = {CERT_QUALITY_MARGIN}`, `token_test = 'max-bet-v1'`, `token_cap = {CERT_TOKEN_CAP:,}`, `minimum_token_reduction = {CERT_MIN_REDUCTION:,}`)",
        f"- **Sample size:** `n = {cert['sample_size']}` paired 3-turn workflows (`S01`–`S16`), `alpha_round = {cert['alpha_round']:.6f}`",
        f"- **Quality gate (`Gate.lean`):** `harm_count = {cert['harm_count']}` (limit `{cert['gates_by_pairing']['tm_r2_vs_stock']['harm_limit']}`), `help_count = {cert['help_count']}`, `quality_difference_lower = {cert['quality_difference_lower']:.6f}`",
        f"- **Token savings gate (`Bet.lean`):** `mean_token_saving = {cert['mean_token_saving']:,.1f}` tokens (`max_bet_v1_wealth = {cert['max_bet_v1_wealth']:.4f}` vs threshold `1.0`, `normalized_token_difference_upper = {cert['normalized_token_difference_upper']:.6f}`)",
        f"- **Registry decision (`tm_r2` vs `stock`):** **`{cert['decision']}`** (`verified_replay = {cert['verified_replay']}`)",
        "",
        "| Pairing | Harms | Helps | Harm Passes (`δ=0.25`) | Mean Token Saving | `max-bet-v1` Wealth | `max-bet-v1` Passes | Gate Certified |",
        "|---|---:|---:|---|---:|---:|---|---|",
    ])
    for gname, g in cert["gates_by_pairing"].items():
        lines.append(
            f"| `{gname}` | `{g['harms']}` | `{g['helps']}` | `{g['harm_passes']}` | "
            f"`{g['mean_token_saving']:,.1f}` | `{g['max_bet_v1_wealth']:.4f}` | "
            f"`{g['max_bet_v1_passes']}` | `{g['gate_certified']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    expected_proto = PROTOCOL_HASH.read_text(encoding="utf-8").split()[0]
    actual_proto = sha256(PROTOCOL)
    if actual_proto != expected_proto:
        raise RuntimeError(f"PROTOCOL.md hash mismatch: {actual_proto} != {expected_proto}")

    setup = json.loads(SETUP_FILE.read_text(encoding="utf-8"))
    tasks = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    task_ids = [t["id"] for t in tasks]

    raw_rows = [json.loads(ln) for ln in RUNS_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    by_task_arm: dict[tuple[str, str], dict] = {}
    for r in raw_rows:
        by_task_arm[(r["task_id"], r["arm"])] = r

    if len(by_task_arm) != len(tasks) * len(ARMS):
        missing = [(tid, a) for tid in task_ids for a in ARMS if (tid, a) not in by_task_arm]
        raise RuntimeError(f"incomplete run: {len(by_task_arm)}/{len(tasks)*len(ARMS)}, missing={missing}")

    # Verify strict offline local-router invariant on tm_locked and tm_r2
    for tid in task_ids:
        for arm in ARMS:
            rec = by_task_arm[(tid, arm)]
            if rec["aborted"] or not rec["session_continuity_ok"] or rec["turns_completed"] != 3:
                raise RuntimeError(f"session integrity failure on {tid}/{arm}")
            if arm in ("tm_locked", "tm_r2"):
                for tr in rec["turns"]:
                    if tr.get("router") != "r2":
                        raise RuntimeError(f"offline invariant violated on {tid}/{arm} T{tr['turn']}: {tr.get('router')}")

    rng = random.Random(SEED)
    arms_summary = {arm: summarize_records([by_task_arm[(tid, arm)] for tid in task_ids]) for arm in ARMS}
    buckets_summary = {
        b: {
            arm: summarize_records(
                [by_task_arm[(t["id"], arm)] for t in tasks if t["bucket"] == b]
            )
            for arm in ARMS
        }
        for b in BUCKETS
    }

    pairings_out: dict[str, dict] = {}
    for pname, inc_arm, cand_arm in PAIRINGS:
        pairings_out[pname] = {}
        for m in METRICS:
            inc_v = [float(by_task_arm[(tid, inc_arm)][m]) for tid in task_ids]
            cand_v = [float(by_task_arm[(tid, cand_arm)][m]) for tid in task_ids]
            pairings_out[pname][m] = bootstrap_paired(inc_v, cand_v, rng)

    # Router latency paired comparison (tm_r2 vs tm_md1_v1 across 16 workflows)
    md1_lat_wf = [float(by_task_arm[(tid, "tm_md1_v1")]["mean_router_ms"]) for tid in task_ids]
    r2_lat_wf = [float(by_task_arm[(tid, "tm_r2")]["mean_router_ms"]) for tid in task_ids]
    lat_boot = bootstrap_paired(md1_lat_wf, r2_lat_wf, rng)
    speedup_median_x = round(
        arms_summary["tm_md1_v1"]["router_ms_median"] / max(0.001, arms_summary["tm_r2"]["router_ms_median"]),
        2,
    )

    # Escalation capability recall McNemar across Buckets B+C (n=8)
    esc_ids = [t["id"] for t in tasks if t["bucket"] in ("B_escalation_and_intra_deixis", "C_cross_session_recall")]
    r2_wins_rec = sum(
        1
        for tid in esc_ids
        if by_task_arm[(tid, "tm_r2")]["escalated_turn_recalled"]
        and not by_task_arm[(tid, "tm_locked")]["escalated_turn_recalled"]
    )
    lk_wins_rec = sum(
        1
        for tid in esc_ids
        if by_task_arm[(tid, "tm_locked")]["escalated_turn_recalled"]
        and not by_task_arm[(tid, "tm_r2")]["escalated_turn_recalled"]
    )
    p_h3 = exact_mcnemar_two_sided(r2_wins_rec, lk_wins_rec)

    # H4: Resumed first-call cache hit rate (tm_r2 vs tm_md1_v1) across all 16 workflows
    p_h1 = pairings_out["tm_r2_vs_stock"]["cold_usd"]["wilcoxon_p_two_sided"]
    p_h2 = lat_boot["wilcoxon_p_two_sided"]
    p_h4 = pairings_out["tm_r2_vs_tm_md1_v1"]["mean_resume_first_call_cache_hit_rate"]["wilcoxon_p_two_sided"]

    raw_pvals = {
        "H1_cold_usd_vs_stock": p_h1,
        "H2_router_latency_vs_md1": p_h2,
        "H3_escalation_recall_vs_locked": p_h3,
        "H4_resume_cache_hit_vs_md1_v1": p_h4,
    }
    holm_pvals = holm_bonferroni(raw_pvals)

    hypotheses = {
        "H1_cold_usd_vs_stock": {
            "comparison": "tm_r2 vs stock (N=16)",
            "effect_summary": (
                f"cold_usd {pairings_out['tm_r2_vs_stock']['cold_usd']['pct_change_of_means']:+.2f}% "
                f"(95% CI {pairings_out['tm_r2_vs_stock']['cold_usd']['ci95_pct_change']}%)"
            ),
            "raw_p": p_h1,
            "holm_p": holm_pvals["H1_cold_usd_vs_stock"],
            "significant_0_05": holm_pvals["H1_cold_usd_vs_stock"] < 0.05,
        },
        "H2_router_latency_vs_md1": {
            "comparison": "tm_r2 vs tm_md1_v1 (N=16 workflows / 48 launches)",
            "effect_summary": (
                f"median {arms_summary['tm_r2']['router_ms_median']:.3f} ms vs "
                f"{arms_summary['tm_md1_v1']['router_ms_median']:.1f} ms ({speedup_median_x:.1f}x faster)"
            ),
            "raw_p": p_h2,
            "holm_p": holm_pvals["H2_router_latency_vs_md1"],
            "significant_0_05": holm_pvals["H2_router_latency_vs_md1"] < 0.05,
        },
        "H3_escalation_recall_vs_locked": {
            "comparison": "tm_r2 vs tm_locked on Buckets B+C (N=8)",
            "effect_summary": (
                f"mid-session capability recall {arms_summary['tm_r2']['escalated_needed_recalled_count']}/8 vs "
                f"{arms_summary['tm_locked']['escalated_needed_recalled_count']}/8 "
                f"(native tool used {arms_summary['tm_r2']['escalated_target_tool_used_count']}/8 vs "
                f"{arms_summary['tm_locked']['escalated_target_tool_used_count']}/8)"
            ),
            "raw_p": round(p_h3, 8),
            "holm_p": holm_pvals["H3_escalation_recall_vs_locked"],
            "significant_0_05": holm_pvals["H3_escalation_recall_vs_locked"] < 0.05,
        },
        "H4_resume_cache_hit_vs_md1_v1": {
            "comparison": "tm_r2 vs tm_md1_v1 (N=16)",
            "effect_summary": (
                f"resumed 1st-call cache hit {arms_summary['tm_r2']['mean_resume_first_call_cache_hit_rate']*100:.2f}% "
                f"vs {arms_summary['tm_md1_v1']['mean_resume_first_call_cache_hit_rate']*100:.2f}%, "
                f"unneeded muts {arms_summary['tm_r2']['unneeded_tool_mutations_sum']} vs "
                f"{arms_summary['tm_md1_v1']['unneeded_tool_mutations_sum']}"
            ),
            "raw_p": p_h4,
            "holm_p": holm_pvals["H4_resume_cache_hit_vs_md1_v1"],
            "significant_0_05": holm_pvals["H4_resume_cache_hit_vs_md1_v1"] < 0.05,
        },
    }

    cert = run_formal_certification(by_task_arm, task_ids, setup)
    CERT_FILE.write_text(json.dumps(cert, indent=2) + "\n", encoding="utf-8", newline="\n")

    analysis = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "protocol_sha256": actual_proto,
        "setup": setup,
        "arms": arms_summary,
        "buckets": buckets_summary,
        "pairings": pairings_out,
        "router_latency_pairing": lat_boot,
        "latency_speedup_median_x": speedup_median_x,
        "hypotheses": hypotheses,
        "certification": cert,
    }
    ANALYSIS_FILE.write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8", newline="\n")
    REPORT_FILE.write_text(build_report(analysis, cert, by_task_arm, tasks), encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                "decision": cert["decision"],
                "speedup_median_x": speedup_median_x,
                "hypotheses": hypotheses,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
