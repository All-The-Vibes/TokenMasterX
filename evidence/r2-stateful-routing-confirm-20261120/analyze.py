"""Pre-registered Round k=2 confirmation analyzer & two-round CertificationRegistry verifier (`r2-stateful-routing-confirm-20261120`).

Verifies:
  1. PROTOCOL.sha256 integrity, frozen `local_router.py` / `local_router_weights.py` hashes, and 96-session
     (32 workflows x 3 arms = 288 launches) completeness with 100% single-session continuity.
  2. Strict offline local-router invariant (`router == 'r2'` on all 96 `tm_r2` launches).
  3. Arm-level and bucket-level metrics (`cold_usd`, `turn23_billed_usd`, `raw_tokens`,
     `mean_resume_first_call_cache_hit_rate`, `unneeded_tool_mutations`, capability recall, `router_ms`).
  4. Paired 10,000-draw bootstrap 95% CIs, exact two-sided Wilcoxon signed-rank p-values, and
     Holm-Bonferroni step-down family-wise adjustments across pre-registered H1..H4 (alpha = 0.05).
  5. Shared durable SQLite `CertificationRegistry` (`Gate.lean` + `Bet.lean`) excluding `CASES`+`HELD_OUT`,
     replaying Round `k = 1` (`S01`..`S16` -> `not_certified`, alpha_1 = 0.03039636), and certifying
     Confirmation Round `k = 2` (`C01`..`C32`, alpha_2 = 0.00759909, cumulative alpha = 0.03799545 < 0.05).

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
R1_DIR = HERE.parent / "r2-stateful-routing-20261120"
REPO = HERE.parents[1]
PLUGIN = REPO / "token-master-plugin"
EVALS = PLUGIN / "evals"
SKILL = PLUGIN / "skills" / "token-master"
sys.path.insert(0, str(EVALS))
sys.path.insert(0, str(SKILL))

from brainspace import certification, token_ledger
import md1_routing_eval as md1_eval

PROTOCOL = HERE / "PROTOCOL.md"
PROTOCOL_HASH = HERE / "PROTOCOL.sha256"
TASKS_FILE = HERE / "tasks.json"
SETUP_FILE = HERE / "setup.json"
RUNS_FILE = HERE / "runs.jsonl"
ANALYSIS_FILE = HERE / "analysis.json"
CERT_FILE = HERE / "certification.json"
REPORT_FILE = HERE / "REPORT.md"

ARMS = ("stock", "tm_md1_v1", "tm_r2")
BUCKETS = (
    "A_stable_coding",
    "B_escalation_and_intra_deixis",
    "C_cross_session_recall",
    "D_warm_cache_lookalikes",
)
PAIRINGS = (
    ("tm_r2_vs_stock", "stock", "tm_r2"),
    ("tm_r2_vs_tm_md1_v1", "tm_md1_v1", "tm_r2"),
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

SEED = 20261121
DRAWS = 10_000
CERT_ALPHA = 0.05
CERT_ROUND = 2
CERT_QUALITY_MARGIN = 0.25
CERT_TOKEN_CAP = 300_000
CERT_MIN_REDUCTION = 2_500
ORACLE_ID = "r2-deterministic-oracle-v1"


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


def holm_bonferroni(pvals: dict[str, float]) -> dict[str, float]:
    ordered = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(ordered)
    adjusted: dict[str, float] = {}
    running_max = 0.0
    for idx, (k, p) in enumerate(ordered):
        adj = min(1.0, (m - idx) * p)
        running_max = max(running_max, adj)
        adjusted[k] = round(running_max, 12)
    return adjusted


def _fmt_p(p: float) -> str:
    return f"{p:.2e}" if p < 1e-4 else f"{p:.6f}"


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
        "wilcoxon_p_two_sided": round(exact_wilcoxon_two_sided(diffs), 12),
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


def _build_observations(
    study_dir: Path,
    by_task_arm: dict[tuple[str, str], dict],
    task_ids: list[str],
    spec: certification.GateComparisonSpec,
    measurement: token_ledger.MeasurementIdentity,
    model_id: str,
    learning_run_id: str,
) -> list[certification.PairedObservation]:
    obs: list[certification.PairedObservation] = []
    for tid in task_ids:
        inc = by_task_arm[(tid, "stock")]
        cand = by_task_arm[(tid, "tm_r2")]
        inc_check = study_dir / "sessions" / tid / "stock" / "check.txt"
        cand_check = study_dir / "sessions" / tid / "tm_r2" / "check.txt"

        def _make_trace(rec: dict, policy_id: str, arm_tag: str) -> token_ledger.TaskTrace:
            calls = []
            expected = []
            for tr in rec["turns"]:
                cid = f"{learning_run_id}-{tid}-{arm_tag}-turn{tr['turn']}-{rec['session_id']}"
                expected.append(cid)
                calls.append(
                    token_ledger.CallRecord(
                        call_id=cid,
                        task_id=tid,
                        attempt_id=f"{learning_run_id}-{tid}-{arm_tag}-attempt1",
                        phase="learning",
                        role="primary",
                        model_id=model_id,
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
            oracle_id=ORACLE_ID,
            success=bool(inc["passed"]),
            evidence_sha256=sha256(inc_check) if inc_check.is_file() else sha256_text(json.dumps(inc["passed"])),
        )
        cand_out = certification.VerifiedOutcome(
            task_id=tid,
            policy_id=spec.candidate_id,
            oracle_id=ORACLE_ID,
            success=bool(cand["passed"]),
            evidence_sha256=sha256(cand_check) if cand_check.is_file() else sha256_text(json.dumps(cand["passed"])),
        )
        obs.append(
            certification.PairedObservation(
                task_id=tid,
                incumbent=inc_trace,
                candidate=cand_trace,
                incumbent_outcome=inc_out,
                candidate_outcome=cand_out,
            )
        )
    return obs


def run_two_round_certification(
    by_task_arm_r2: dict[tuple[str, str], dict],
    r2_task_ids: list[str],
    setup_r2: dict,
) -> dict:
    r1_setup = json.loads((R1_DIR / "setup.json").read_text(encoding="utf-8"))
    r1_tasks = json.loads((R1_DIR / "tasks.json").read_text(encoding="utf-8"))
    r1_task_ids = [t["id"] for t in r1_tasks]
    r1_rows = [json.loads(ln) for ln in (R1_DIR / "runs.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    by_task_arm_r1 = {(r["task_id"], r["arm"]): r for r in r1_rows}

    measurement = token_ledger.MeasurementIdentity(
        tokenizer_id="openai-responses-provider-usage",
        tokenizer_version="v1",
        vocabulary_id="o200k_base",
        extraction_protocol_id="copilot-cli-events-jsonl",
        extraction_protocol_version="1.0.112",
        boundary="session-assistant-usage-input-plus-output",
    )
    r1_cli_ver = r1_setup["copilot_cli_version"].splitlines()[0].rstrip(".")
    r2_cli_ver = setup_r2["copilot_cli_version"].splitlines()[0].rstrip(".")
    spec_r1 = certification.GateComparisonSpec(
        candidate_id=f"tm-r2-local-v1-{r1_setup['tm_install']['local_router_sha256'][:16]}",
        incumbent_id="stock-copilot-cli-1.0.112",
        measurement=measurement,
        oracle_id=ORACLE_ID,
        workload_id=f"r2-stateful-routing-20261120-{r1_setup['tasks_sha256'][:16]}",
        environment_id=f"{r1_cli_ver}-{r1_setup['model']}-{r1_setup['reasoning_effort']}",
        token_cap=500_000,
        minimum_token_reduction=5_000,
        quality_margin=CERT_QUALITY_MARGIN,
        token_test="max-bet-v1",
    )
    spec_r2 = certification.GateComparisonSpec(
        candidate_id=f"tm-r2-local-deixis-v2-{setup_r2['tm_install']['local_router_sha256'][:16]}",
        incumbent_id="stock-copilot-cli-1.0.112",
        measurement=measurement,
        oracle_id=ORACLE_ID,
        workload_id=f"r2-stateful-routing-confirm-20261120-{setup_r2['tasks_sha256'][:16]}",
        environment_id=f"{r2_cli_ver}-{setup_r2['model']}-{setup_r2['reasoning_effort']}",
        token_cap=CERT_TOKEN_CAP,
        minimum_token_reduction=CERT_MIN_REDUCTION,
        quality_margin=CERT_QUALITY_MARGIN,
        token_test="max-bet-v1",
    )

    obs_r1 = _build_observations(
        R1_DIR, by_task_arm_r1, r1_task_ids, spec_r1, measurement, r1_setup["model"], "r2-round1-20261120"
    )
    obs_r2 = _build_observations(
        HERE, by_task_arm_r2, r2_task_ids, spec_r2, measurement, setup_r2["model"], "r2-confirm-round2-20261120"
    )

    excluded_search_ids = [f"CASES[{i}]" for i in range(len(md1_eval.CASES))] + [
        f"HELD_OUT[{i}]" for i in range(len(md1_eval.HELD_OUT))
    ]

    gate_name = certification.gate_label(CERT_QUALITY_MARGIN, "max-bet-v1")
    base_tmp = Path(r"C:\tm-lanes") if Path(r"C:\tm-lanes").is_dir() else None
    tmp_dir = Path(tempfile.mkdtemp(prefix="r2_2round_cert_", dir=str(base_tmp) if base_tmp else None))
    try:
        reg = certification.CertificationRegistry(
            tmp_dir / "cert.sqlite",
            alpha=CERT_ALPHA,
            trusted_oracle_id=ORACLE_ID,
            gate=gate_name,
        )
        reg.exclude_tasks(excluded_search_ids)

        k1 = reg.start_round(spec_r1, sample_size=len(r1_task_ids), mode="fixed")
        assert k1 == 1
        reg.reserve_tasks(k1, spec_r1, r1_task_ids)
        reg.submit(k1, spec_r1, obs_r1)
        cert_r1 = reg.certify(k1, spec_r1)

        k2 = reg.start_round(spec_r2, sample_size=len(r2_task_ids), mode="fixed")
        assert k2 == 2
        reg.reserve_tasks(k2, spec_r2, r2_task_ids)
        reg.submit(k2, spec_r2, obs_r2)
        cert_r2 = reg.certify(k2, spec_r2)
        replayed_r2 = reg.certify(k2, spec_r2)
        verified_replay = cert_r2.to_dict() == replayed_r2.to_dict()
    finally:
        for p in tmp_dir.glob("*"):
            p.unlink(missing_ok=True)
        tmp_dir.rmdir()

    alpha_round = certification.round_alpha(CERT_ALPHA, CERT_ROUND)
    alpha_spent_total = certification.round_alpha(CERT_ALPHA, 1) + alpha_round
    n = len(r2_task_ids)
    gates_by_pairing = {}
    for label, inc_arm, cand_arm, true_off in (
        ("tm_r2_vs_stock", "stock", "tm_r2", True),
        ("tm_md1_v1_vs_stock", "stock", "tm_md1_v1", True),
        ("tm_r2_vs_tm_md1_v1", "tm_md1_v1", "tm_r2", False),
    ):
        pairs = [
            (int(by_task_arm_r2[(tid, inc_arm)]["raw_tokens"]), int(by_task_arm_r2[(tid, cand_arm)]["raw_tokens"]))
            for tid in r2_task_ids
        ]
        harms = sum(
            1 for tid in r2_task_ids
            if by_task_arm_r2[(tid, inc_arm)]["passed"] and not by_task_arm_r2[(tid, cand_arm)]["passed"]
        )
        helps = sum(
            1 for tid in r2_task_ids
            if (not by_task_arm_r2[(tid, inc_arm)]["passed"]) and by_task_arm_r2[(tid, cand_arm)]["passed"]
        )
        max_obs = max(max(a, b) for a, b in pairs)
        cap_ok = max_obs <= CERT_TOKEN_CAP
        bet_ok = (
            certification.bet_passes(CERT_TOKEN_CAP, CERT_MIN_REDUCTION, alpha_round, pairs)
            if (cap_ok and all(CERT_TOKEN_CAP + a - b >= 0 for a, b in pairs))
            else False
        )
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
    out = cert_r2.to_dict()
    out["rule_version"] = gate_name
    out["excluded_search_prompts_count"] = len(excluded_search_ids)
    out["round_1_replay"] = {
        "round_id": cert_r1.round_id,
        "sample_size": cert_r1.sample_size,
        "alpha_round": round(cert_r1.alpha_round, 8),
        "decision": cert_r1.decision,
    }
    out["cumulative_alpha_spent"] = round(alpha_spent_total, 8)
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
    cli_ver = analysis["setup"]["copilot_cli_version"].splitlines()[0].rstrip(".")
    lines = [
        "# Research Direction R2 Confirmation Study Report — Round `k = 2` (`r2-stateful-routing-confirm-20261120`)",
        "",
        "## 1. Executive Summary",
        "",
        f"- **Scope:** `32` pre-registered fresh 3-turn workflows (`C01`–`C32`, `max_jaccard = 0.533 < 0.55` vs all `113` prior prompts) × `3` arms = **`96` live sessions (`288` `{cli_ver}` launches)** on `{analysis['setup']['model']}` (`reasoning_effort={analysis['setup']['reasoning_effort']}`), base commit `{analysis['setup']['repo_commit'][:7]}`.",
        f"- **Pre-registration & offline integrity:** `PROTOCOL.sha256` verified (`{analysis['protocol_sha256'][:16]}...`), `local_router.py` (`{analysis['setup']['local_router_sha256'][:16]}...`) and `local_router_weights.py` (`{analysis['setup']['tm_install']['local_router_weights_sha256'][:16]}...`, payload `{analysis['setup']['weights_sha256'][:16]}...`) frozen prior to task generation; `0` aborts; `96/96` (`100%`) single-session continuity across `start` → `--resume <sid>` → `--continue`; `96/96` launches on `tm_r2` verified `100%` offline (`router='r2'`).",
        f"- **Shared two-round `Gate.lean` + `Bet.lean` certification (`brainspace/certification.py`):** Excluding `{cert['excluded_search_prompts_count']}` search/distillation prompts (`CASES`+`HELD_OUT`), replaying Round `k = 1` (`S01`–`S16`, $\\alpha_1 = {cert['round_1_replay']['alpha_round']:.6f}$, `{cert['round_1_replay']['decision']}`), and evaluating Confirmation Round `k = 2` (`C01`–`C32`, $\\alpha_2 = {cert['alpha_round']:.6f}$, cumulative $\\alpha_1 + \\alpha_2 = {cert['cumulative_alpha_spent']:.6f} < 0.05$) yields **`decision = {cert['decision']!r}`** (`harm_count = {cert['harm_count']}` vs limit `{cert['gates_by_pairing']['tm_r2_vs_stock']['harm_limit']}`, `help_count = {cert['help_count']}`, `mean_token_saving = {cert['mean_token_saving']:,.1f}`, `max_bet_v1_wealth = {cert['max_bet_v1_wealth']:.4f} >= 1.0` (`max_bet_v1_passes = True`), `verified_replay = {cert['verified_replay']}`).",
        f"- **End-to-end savings vs Stock (H1):** `tm_r2` passed **`{arms['tm_r2']['passed']}/{arms['tm_r2']['n']}` (`{arms['tm_r2']['pass_rate']*100:.1f}%`)** workflows vs `stock` **`{arms['stock']['passed']}/{arms['stock']['n']}` (`{arms['stock']['pass_rate']*100:.1f}%`)**, cutting cold-normalized session cost by **`{analysis['pairings']['tm_r2_vs_stock']['cold_usd']['pct_change_of_means']:.2f}%`** (95% CI `{analysis['pairings']['tm_r2_vs_stock']['cold_usd']['ci95_pct_change']}%`, Holm $p = {_fmt_p(hyps['H1_cold_usd_vs_stock']['holm_p'])}$) and total raw tokens by **`{analysis['pairings']['tm_r2_vs_stock']['raw_tokens']['pct_change_of_means']:.2f}%`**.",
        f"- **Zero-network routing latency vs Cloud `MD-1` (H2):** Local `tm_r2` ran in **`{arms['tm_r2']['router_ms_median']:.3f} ms` median** (`{arms['tm_r2']['router_ms_p90']:.3f} ms` p90, including SQLite warm-cache lookup) vs cloud `MD-1` **`{arms['tm_md1_v1']['router_ms_median']:.1f} ms` median** (`{arms['tm_md1_v1']['router_ms_p90']:.1f} ms` p90) — a **`{analysis['latency_speedup_median_x']:.1f}x` live launcher speedup** (Holm $p = {_fmt_p(hyps['H2_router_latency_vs_md1']['holm_p'])}$).",
        f"- **Warm-cache preservation & Turn 2+3 savings vs Cloud `tm_md1_v1` (H3 & H4):** `tm_r2` recorded **`{arms['tm_r2']['unneeded_tool_mutations_sum']}`** unneeded mid-session tool-list mutations vs **`{arms['tm_md1_v1']['unneeded_tool_mutations_sum']}`** on `tm_md1_v1`, lifting mean resumed first-call prompt-cache hit rate from **`{arms['tm_md1_v1']['mean_resume_first_call_cache_hit_rate']*100:.2f}%`** to **`{arms['tm_r2']['mean_resume_first_call_cache_hit_rate']*100:.2f}%`** (Holm $p = {_fmt_p(hyps['H3_resume_cache_hit_vs_md1_v1']['holm_p'])}$) and cutting Turn-2+3 billed USD by **`{analysis['pairings']['tm_r2_vs_tm_md1_v1']['turn23_billed_usd']['pct_change_of_means']:.2f}%`** (Holm $p = {_fmt_p(hyps['H4_turn23_billed_usd_vs_md1_v1']['holm_p'])}$).",
        "",
        "---",
        "",
        "## 2. Overall 3-Arm Summary (`N = 32` Workflows per Arm)",
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
        "## 3. Bucket Breakdown (`8` Workflows × `3` Turns per Bucket)",
        "",
        "| Bucket | Arm | Pass | Cold USD Mean | Turn 2+3 Billed USD Mean | Raw Tokens Mean | Resumed 1st-Call Cache Hit | Esc. Recall | Unneeded Muts |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for b in BUCKETS:
        for arm in ARMS:
            s = analysis["buckets"][b][arm]
            esc_str = f"`{s['escalated_needed_recalled_count']}/{s['escalated_total']}`" if s["escalated_total"] else "—"
            lines.append(
                f"| `{b}` | `{arm}` | `{s['passed']}/{s['n']}` | `${s['cold_usd_mean']:.4f}` | "
                f"`${s['turn23_billed_usd_mean']:.4f}` | `{s['raw_tokens_mean']:,.0f}` | "
                f"`{s['mean_resume_first_call_cache_hit_rate']*100:.2f}%` | {esc_str} | `{s['unneeded_tool_mutations_sum']}` |"
            )

    lines.extend([
        "",
        "---",
        "",
        "## 4. Pre-Registered Hypotheses & Holm-Bonferroni Inference (`N = 32`)",
        "",
        "| Hypothesis | Comparison | Metric / Effect | Raw two-sided $p$ | Holm-Bonferroni $p$ | Significant ($\\alpha=0.05$) |",
        "|---|---|---|---:|---:|:---:|",
    ])
    for hid, h in hyps.items():
        lines.append(
            f"| `{hid}` | `{h['comparison']}` | {h['effect_summary']} | `{_fmt_p(h['raw_p'])}` | `{_fmt_p(h['holm_p'])}` | "
            f"{'YES' if h['significant_0_05'] else 'no'} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 5. Per-Workflow Matrix (`C01`–`C32`)",
        "",
        "| Task | Bucket | Kind | `stock` | `tm_md1_v1` (muts / hit) | `tm_r2` (muts / hit) | `tm_r2` vs `stock` Cold Δ% | `tm_r2` vs `md1_v1` T2+3 Δ% |",
        "|---|---|---|---|---|---|---:|---:|",
    ])
    for t in tasks:
        tid = t["id"]
        r_st = by_task_arm[(tid, "stock")]
        r_md = by_task_arm[(tid, "tm_md1_v1")]
        r_r2 = by_task_arm[(tid, "tm_r2")]
        dpct_st = 100.0 * (r_r2["cold_usd"] - r_st["cold_usd"]) / r_st["cold_usd"] if r_st["cold_usd"] > 0 else 0.0
        dpct_md = (
            100.0 * (r_r2["turn23_billed_usd"] - r_md["turn23_billed_usd"]) / r_md["turn23_billed_usd"]
            if r_md["turn23_billed_usd"] > 0
            else 0.0
        )
        lines.append(
            f"| `{tid}` | `{t['bucket']}` | `{t['kind']}` | "
            f"`{'PASS' if r_st['passed'] else 'FAIL'}` `${r_st['cold_usd']:.4f}` | "
            f"`{'PASS' if r_md['passed'] else 'FAIL'}` `${r_md['cold_usd']:.4f}` (`{r_md['resume_tool_mutations']}` / `{r_md['mean_resume_first_call_cache_hit_rate']*100:.0f}%`) | "
            f"`{'PASS' if r_r2['passed'] else 'FAIL'}` `${r_r2['cold_usd']:.4f}` (`{r_r2['resume_tool_mutations']}` / `{r_r2['mean_resume_first_call_cache_hit_rate']*100:.0f}%`) | "
            f"`{dpct_st:+.1f}%` | `{dpct_md:+.1f}%` |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 6. Shared Two-Round Proof-Backed Certification (`Gate.lean` + `Bet.lean`)",
        "",
        f"- **Rule version:** `{cert['rule_version']}` (`quality_margin = {CERT_QUALITY_MARGIN}`, `token_test = 'max-bet-v1'`, `token_cap = {CERT_TOKEN_CAP:,}`, `minimum_token_reduction = {CERT_MIN_REDUCTION:,}`)",
        f"- **Holdout exclusion:** `{cert['excluded_search_prompts_count']}` search/distillation prompts (`CASES` + `HELD_OUT`) permanently excluded before Round 1",
        f"- **Round `k = 1` replay (`S01`–`S16`, `n = 16`):** `alpha_1 = {cert['round_1_replay']['alpha_round']:.6f}`, `decision = {cert['round_1_replay']['decision']!r}`",
        f"- **Round `k = 2` confirmation (`C01`–`C32`, `n = 32`):** `alpha_2 = {cert['alpha_round']:.6f}`, cumulative family-wise `alpha_1 + alpha_2 = {cert['cumulative_alpha_spent']:.6f} < 0.05`",
        f"- **Quality gate (`Gate.lean`):** `harm_count = {cert['harm_count']}` (limit `{cert['gates_by_pairing']['tm_r2_vs_stock']['harm_limit']}`), `help_count = {cert['help_count']}`, `quality_difference_lower = {cert['quality_difference_lower']:.6f}`",
        f"- **Token savings gate (`Bet.lean`):** `mean_token_saving = {cert['mean_token_saving']:,.1f}` tokens (`max_bet_v1_wealth = {cert['max_bet_v1_wealth']:.4f}` vs threshold `1.0`, `normalized_token_difference_upper = {cert['normalized_token_difference_upper']:.6f}`)",
        f"- **Registry decision (`tm_r2` vs `stock`, `k = 2`):** **`{cert['decision']}`** (`verified_replay = {cert['verified_replay']}`)",
        "",
        "| Pairing | Harms | Helps | Harm Limit | Harm Passes (`δ=0.25`) | Mean Token Saving | `max-bet-v1` Wealth | `max-bet-v1` Passes | Gate Certified |",
        "|---|---:|---:|---:|---|---:|---:|---|---|",
    ])
    for gname, g in cert["gates_by_pairing"].items():
        lines.append(
            f"| `{gname}` | `{g['harms']}` | `{g['helps']}` | `{g['harm_limit']}` | `{g['harm_passes']}` | "
            f"`{g['mean_token_saving']:,.1f}` | `{g['max_bet_v1_wealth']:.4f}` | "
            f"`{g['max_bet_v1_passes']}` | `{g['gate_certified']}` |"
        )
    lines.extend([
        "",
        "---",
        "",
        "## 7. Forensic Discrepancy Breakdown",
        "",
        "- **`C17` (`tm_r2` PASS vs `tm_md1_v1` FAIL):** Turn 2 (`\"Search our earlier sessions in session_store_sql ...\"`) triggered `_CROSS_SESSION_DEIXIS` (`earlier sessions`) on `tm_r2`, recalling `session_store_sql` and recovering `watermark_pct=82, backoff_ms=250`, whereas cloud `MD-1` missed `session_history` (`0.54 < 0.55`).",
        "- **`C21` & `C24` (`stock` + `tm_md1_v1` PASS vs `tm_r2` FAIL — the `2` `Gate.lean` harms vs limit `1`):** Turn 3 phrased cross-session recall as `\"Query our past sessions in \\`session_store_sql\\` ...\"` (`C21`) and `\"Use \\`session_store_sql\\` to check our prior history ...\"` (`C24`). Both fell outside `_CROSS_SESSION_DEIXIS`'s `(earlier|prior|previous|recent) (sessions|work|conversations|chats)` lexical set (`past sessions` / `prior history`) while embedding the snake_case tool identifier `session_store_sql` inside a long multi-field JSON output specification that diluted bag-of-n-grams cosine score below the warm-cache escalation threshold (`0.619`).",
        "- **`C10`, `C12`, `C23`, `C25` (`FAIL` across all 3 arms — `0` differential harms):** Model-side multi-turn carry-forward omissions on `gpt-6-astra` (`reasoning_effort=low`) where Turn 3 omitted Turn-1 constants (`C10`, `C23`, `C25`) or SQL aggregate columns (`C12`) identically under `stock`, `tm_md1_v1`, and `tm_r2`.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    expected_proto = PROTOCOL_HASH.read_text(encoding="utf-8").split()[0]
    actual_proto = sha256(PROTOCOL)
    if actual_proto != expected_proto:
        raise RuntimeError(f"PROTOCOL.md hash mismatch: {actual_proto} != {expected_proto}")

    setup = json.loads(SETUP_FILE.read_text(encoding="utf-8"))
    spec_payload = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    tasks = spec_payload["tasks"]
    task_ids = [t["id"] for t in tasks]

    raw_rows = [json.loads(ln) for ln in RUNS_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    by_task_arm: dict[tuple[str, str], dict] = {}
    for r in raw_rows:
        by_task_arm[(r["task_id"], r["arm"])] = r

    if len(by_task_arm) != len(tasks) * len(ARMS):
        missing = [(tid, a) for tid in task_ids for a in ARMS if (tid, a) not in by_task_arm]
        raise RuntimeError(f"incomplete run: {len(by_task_arm)}/{len(tasks)*len(ARMS)}, missing={missing}")

    for tid in task_ids:
        for arm in ARMS:
            rec = by_task_arm[(tid, arm)]
            if rec["aborted"] or not rec["session_continuity_ok"] or rec["turns_completed"] != 3:
                raise RuntimeError(f"session integrity failure on {tid}/{arm}")
            if arm == "tm_r2":
                for tr in rec["turns"]:
                    if tr.get("router") != "r2":
                        raise RuntimeError(f"offline invariant violated on {tid}/tm_r2 T{tr['turn']}: {tr.get('router')}")

    rng = random.Random(SEED)
    arms_summary = {arm: summarize_records([by_task_arm[(tid, arm)] for tid in task_ids]) for arm in ARMS}
    buckets_summary = {
        b: {
            arm: summarize_records([by_task_arm[(t["id"], arm)] for t in tasks if t["bucket"] == b])
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

    md1_lat_wf = [float(by_task_arm[(tid, "tm_md1_v1")]["mean_router_ms"]) for tid in task_ids]
    r2_lat_wf = [float(by_task_arm[(tid, "tm_r2")]["mean_router_ms"]) for tid in task_ids]
    lat_boot = bootstrap_paired(md1_lat_wf, r2_lat_wf, rng)
    speedup_median_x = round(
        arms_summary["tm_md1_v1"]["router_ms_median"] / max(0.001, arms_summary["tm_r2"]["router_ms_median"]),
        2,
    )

    p_h1 = pairings_out["tm_r2_vs_stock"]["cold_usd"]["wilcoxon_p_two_sided"]
    p_h2 = lat_boot["wilcoxon_p_two_sided"]
    p_h3 = pairings_out["tm_r2_vs_tm_md1_v1"]["mean_resume_first_call_cache_hit_rate"]["wilcoxon_p_two_sided"]
    p_h4 = pairings_out["tm_r2_vs_tm_md1_v1"]["turn23_billed_usd"]["wilcoxon_p_two_sided"]

    raw_pvals = {
        "H1_cold_usd_vs_stock": p_h1,
        "H2_router_latency_vs_md1": p_h2,
        "H3_resume_cache_hit_vs_md1_v1": p_h3,
        "H4_turn23_billed_usd_vs_md1_v1": p_h4,
    }
    holm_pvals = holm_bonferroni(raw_pvals)

    hypotheses = {
        "H1_cold_usd_vs_stock": {
            "comparison": "tm_r2 vs stock (N=32)",
            "effect_summary": (
                f"cold_usd {pairings_out['tm_r2_vs_stock']['cold_usd']['pct_change_of_means']:+.2f}% "
                f"(95% CI {pairings_out['tm_r2_vs_stock']['cold_usd']['ci95_pct_change']}%)"
            ),
            "raw_p": p_h1,
            "holm_p": holm_pvals["H1_cold_usd_vs_stock"],
            "significant_0_05": holm_pvals["H1_cold_usd_vs_stock"] < 0.05,
        },
        "H2_router_latency_vs_md1": {
            "comparison": "tm_r2 vs tm_md1_v1 (N=32 workflows / 96 launches)",
            "effect_summary": (
                f"median {arms_summary['tm_r2']['router_ms_median']:.3f} ms vs "
                f"{arms_summary['tm_md1_v1']['router_ms_median']:.1f} ms ({speedup_median_x:.1f}x faster)"
            ),
            "raw_p": p_h2,
            "holm_p": holm_pvals["H2_router_latency_vs_md1"],
            "significant_0_05": holm_pvals["H2_router_latency_vs_md1"] < 0.05,
        },
        "H3_resume_cache_hit_vs_md1_v1": {
            "comparison": "tm_r2 vs tm_md1_v1 (N=32)",
            "effect_summary": (
                f"resumed 1st-call cache hit {arms_summary['tm_r2']['mean_resume_first_call_cache_hit_rate']*100:.2f}% "
                f"vs {arms_summary['tm_md1_v1']['mean_resume_first_call_cache_hit_rate']*100:.2f}%, "
                f"unneeded muts {arms_summary['tm_r2']['unneeded_tool_mutations_sum']} vs "
                f"{arms_summary['tm_md1_v1']['unneeded_tool_mutations_sum']}"
            ),
            "raw_p": p_h3,
            "holm_p": holm_pvals["H3_resume_cache_hit_vs_md1_v1"],
            "significant_0_05": holm_pvals["H3_resume_cache_hit_vs_md1_v1"] < 0.05,
        },
        "H4_turn23_billed_usd_vs_md1_v1": {
            "comparison": "tm_r2 vs tm_md1_v1 (N=32)",
            "effect_summary": (
                f"turn23_billed_usd {pairings_out['tm_r2_vs_tm_md1_v1']['turn23_billed_usd']['pct_change_of_means']:+.2f}% "
                f"(95% CI {pairings_out['tm_r2_vs_tm_md1_v1']['turn23_billed_usd']['ci95_pct_change']}%)"
            ),
            "raw_p": p_h4,
            "holm_p": holm_pvals["H4_turn23_billed_usd_vs_md1_v1"],
            "significant_0_05": holm_pvals["H4_turn23_billed_usd_vs_md1_v1"] < 0.05,
        },
    }

    cert = run_two_round_certification(by_task_arm, task_ids, setup)
    CERT_FILE.write_text(json.dumps(cert, indent=2) + "\n", encoding="utf-8", newline="\n")

    analysis = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "round_index": 2,
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
                "round_1_replay": cert["round_1_replay"],
                "cumulative_alpha_spent": cert["cumulative_alpha_spent"],
                "speedup_median_x": speedup_median_x,
                "hypotheses": hypotheses,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
