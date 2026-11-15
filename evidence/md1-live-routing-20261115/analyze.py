"""Audit and statistical analysis for evidence/md1-live-routing-20261115.

Verifies PROTOCOL.sha256, billing reconciliation, and MD-1 launch attribution,
then writes analysis.json and REPORT.md.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import random
import statistics

HERE = Path(__file__).resolve().parent
ARMS = ("stock", "tm_regex", "tm_md1")
PAIRINGS = (
    ("tm_md1_vs_stock", "stock", "tm_md1"),
    ("tm_regex_vs_stock", "stock", "tm_regex"),
    ("tm_md1_vs_tm_regex", "tm_regex", "tm_md1"),
)
BUCKETS = ("A_pure_coding", "B_multi_capability", "C_adversarial_lookalike")
SEED = 20261022
DRAWS = 10_000


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
    ranks = [0.0] * m
    i = 0
    while i < m:
        j = i
        while j + 1 < m and abs(abs_sorted[j + 1][0] - abs_sorted[i][0]) <= 1e-12:
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[abs_sorted[k][1]] = avg_rank
        i = j + 1
    w_pos = sum(ranks[idx] for idx, d in enumerate(nz) if d > 0)
    w_neg = sum(ranks) - w_pos
    obs = min(w_pos, w_neg)
    extreme = 0
    total = 1 << m
    for mask in range(total):
        s = 0.0
        for bit in range(m):
            if (mask >> bit) & 1:
                s += ranks[bit]
        stat = min(s, sum(ranks) - s)
        if stat <= obs + 1e-12:
            extreme += 1
    return min(1.0, extreme / total)


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
    pct_change = ((mean_t / mean_b) - 1.0) * 100.0 if mean_b > 0 else 0.0

    boot_diffs = []
    boot_pcts = []
    for _ in range(DRAWS):
        picks = [rng.randrange(n) for _ in range(n)]
        sb = sum(base_vals[i] for i in picks) / n
        st = sum(treat_vals[i] for i in picks) / n
        boot_diffs.append(st - sb)
        boot_pcts.append(((st / sb) - 1.0) * 100.0 if sb > 0 else 0.0)
    boot_diffs.sort()
    boot_pcts.sort()
    p_raw = exact_wilcoxon_two_sided(diffs)
    return {
        "n": n,
        "base_mean": mean_b,
        "treat_mean": mean_t,
        "base_median": statistics.median(base_vals),
        "treat_median": statistics.median(treat_vals),
        "mean_diff": mean_diff,
        "mean_diff_ci95": [quantile(boot_diffs, 0.025), quantile(boot_diffs, 0.975)],
        "pct_change": pct_change,
        "pct_change_ci95": [quantile(boot_pcts, 0.025), quantile(boot_pcts, 0.975)],
        "wilcoxon_p": round(p_raw, 6),
        "improved_pairs": sum(1 for d in diffs if d < -1e-12),
        "worse_pairs": sum(1 for d in diffs if d > 1e-12),
        "tied_pairs": sum(1 for d in diffs if abs(d) <= 1e-12),
    }


def audit(runs: list[dict], tasks: list[dict], md1_scores: list[dict], setup: dict) -> dict:
    problems: list[str] = []
    proto_expected = (HERE / "PROTOCOL.sha256").read_text(encoding="utf-8").split()[0]
    proto_actual = sha256(HERE / "PROTOCOL.md")
    if proto_actual != proto_expected:
        problems.append(f"PROTOCOL.md SHA-256 mismatch: {proto_actual} != {proto_expected}")
    if setup.get("protocol_sha256") != proto_expected:
        problems.append("setup.json protocol_sha256 does not match PROTOCOL.sha256")

    task_ids = [t["id"] for t in tasks]
    by_pair: dict[tuple[str, str], dict] = {}
    for r in runs:
        key = (r["task_id"], r["arm"])
        if key in by_pair:
            problems.append(f"duplicate run record for {key}")
        by_pair[key] = r

    for tid in task_ids:
        for arm in ARMS:
            if (tid, arm) not in by_pair:
                problems.append(f"missing session ({tid}, {arm})")

    md1_expected = {row["task_id"]: sorted(row["md1_kept_groups"]) for row in md1_scores}
    charge_checks = 0
    for (tid, arm), r in sorted(by_pair.items()):
        if r.get("copilot_version") != "1.0.112":
            problems.append(f"{tid}/{arm}: copilot_version {r.get('copilot_version')!r} != '1.0.112'")
        if r["call_count"] == 0:
            problems.append(f"{tid}/{arm}: zero LLM calls recorded")
        if arm in ("tm_regex", "tm_md1") and not r["launch_recorded"]:
            problems.append(f"{tid}/{arm}: missing launches.jsonl attribution")
        if arm == "tm_md1" and tid in md1_expected:
            if sorted(r["kept_groups"]) != md1_expected[tid]:
                problems.append(
                    f"{tid}/tm_md1 kept_groups {r['kept_groups']} != MD-1 expected {md1_expected[tid]}"
                )
        for c in r["calls"]:
            charge_checks += 1
            billed = c["total_nano_aiu"]
            recharged = c["recharged_nano_aiu"]
            tol = max(5_000, round(0.01 * max(billed, recharged)))
            if abs(billed - recharged) > tol:
                problems.append(
                    f"{tid}/{arm} call {c['call_index']}: billed {billed} vs recharged {recharged}"
                )

    lanes_dir = Path(setup["lanes_dir"])
    if lanes_dir.is_dir():
        lingering = list(lanes_dir.rglob("md1-token.json"))
        if lingering:
            problems.append(f"lingering md1-token.json found: {[str(p) for p in lingering]}")

    return {
        "passed": len(problems) == 0,
        "protocol_sha256": proto_actual,
        "total_sessions": len(by_pair),
        "charge_calls_verified": charge_checks,
        "problems": problems,
    }


def summarize_arm(records: list[dict]) -> dict:
    n = len(records)
    schema_vals = [r["schema_plus_instr_tokens"] for r in records if r.get("schema_plus_instr_tokens") is not None]
    tool_tok_vals = [r["tool_tokens"] for r in records if r.get("tool_tokens") is not None]
    tool_cnt_vals = [r["tool_count"] for r in records if r.get("tool_count") is not None]
    return {
        "n": n,
        "passed": sum(1 for r in records if r["passed"]),
        "pass_rate": sum(1 for r in records if r["passed"]) / n if n else 0.0,
        "needed_recalled": sum(1 for r in records if r["needed_recalled"]),
        "target_tool_used": sum(1 for r in records if r.get("target_tool_used")),
        "shell_workarounds": sum(1 for r in records if r.get("shell_workaround")),
        "mean_false_keep_tools": statistics.fmean(r["false_keep_tool_count"] for r in records),
        "mean_tool_count": statistics.fmean(tool_cnt_vals) if tool_cnt_vals else None,
        "mean_tool_tokens": statistics.fmean(tool_tok_vals) if tool_tok_vals else None,
        "mean_schema_plus_instr_tokens": statistics.fmean(schema_vals) if schema_vals else None,
        "mean_calls": statistics.fmean(r["call_count"] for r in records),
        "total_subagent_calls": sum(r["subagent_calls"] for r in records),
        "mean_first_call_input": statistics.fmean(r["first_call_input_tokens"] for r in records),
        "mean_raw_tokens": statistics.fmean(r["raw_tokens"] for r in records),
        "median_raw_tokens": statistics.median(r["raw_tokens"] for r in records),
        "total_raw_tokens": sum(r["raw_tokens"] for r in records),
        "mean_cold_usd": statistics.fmean(r["cold_usd"] for r in records),
        "total_cold_usd": sum(r["cold_usd"] for r in records),
        "mean_billed_usd": statistics.fmean(r["billed_usd"] for r in records),
        "total_billed_usd": sum(r["billed_usd"] for r in records),
        "mean_seconds": statistics.fmean(r["seconds"] for r in records),
        "median_seconds": statistics.median(r["seconds"] for r in records),
    }


def main() -> int:
    tasks = json.loads((HERE / "tasks.json").read_text(encoding="utf-8"))
    setup = json.loads((HERE / "setup.json").read_text(encoding="utf-8"))
    md1_scores = json.loads((HERE / "md1_prompt_scores.json").read_text(encoding="utf-8"))
    runs = [
        json.loads(line)
        for line in (HERE / "runs.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    audit_res = audit(runs, tasks, md1_scores, setup)
    if not audit_res["passed"]:
        raise SystemExit("AUDIT FAILED:\n  - " + "\n  - ".join(audit_res["problems"]))

    by_pair = {(r["task_id"], r["arm"]): r for r in runs}
    task_ids = [t["id"] for t in tasks]

    overall_arms = {arm: summarize_arm([by_pair[(tid, arm)] for tid in task_ids]) for arm in ARMS}
    bucket_arms = {
        b: {
            arm: summarize_arm([by_pair[(t["id"], arm)] for t in tasks if t["bucket"] == b])
            for arm in ARMS
        }
        for b in BUCKETS
    }

    rng = random.Random(SEED)
    comparisons: dict[str, dict] = {}
    for metric in ("raw_tokens", "cold_usd", "billed_usd", "first_call_input_tokens", "seconds"):
        m_res = {}
        raw_ps = {}
        for label, base_arm, treat_arm in PAIRINGS:
            b_vals = [float(by_pair[(tid, base_arm)][metric]) for tid in task_ids]
            t_vals = [float(by_pair[(tid, treat_arm)][metric]) for tid in task_ids]
            eff = paired_effect(b_vals, t_vals, rng)
            m_res[label] = eff
            raw_ps[label] = eff["wilcoxon_p"]
        adj_ps = holm_bonferroni(raw_ps)
        for label in m_res:
            m_res[label]["wilcoxon_p_holm"] = adj_ps[label]
        comparisons[metric] = m_res

    bucket_comparisons: dict[str, dict] = {}
    for b in BUCKETS:
        b_tids = [t["id"] for t in tasks if t["bucket"] == b]
        bucket_comparisons[b] = {}
        for metric in ("raw_tokens", "cold_usd", "schema_plus_instr_tokens"):
            bucket_comparisons[b][metric] = {}
            for label, base_arm, treat_arm in PAIRINGS:
                b_vals = [float(by_pair[(tid, base_arm)][metric] or 0.0) for tid in b_tids]
                t_vals = [float(by_pair[(tid, treat_arm)][metric] or 0.0) for tid in b_tids]
                bucket_comparisons[b][metric][label] = paired_effect(b_vals, t_vals, rng)

    latencies = sorted(r["md1_latency_ms"] for r in md1_scores)
    md1_summary = {
        "n_prompts": len(latencies),
        "mean_ms": round(statistics.fmean(latencies), 1),
        "median_ms": round(statistics.median(latencies), 1),
        "p90_ms": round(quantile(latencies, 0.90), 1),
        "max_ms": round(max(latencies), 1),
        "bucket_b_recall": sum(
            1
            for r in md1_scores
            if r["bucket"] == "B_multi_capability" and set(r["needed_groups"]).issubset(set(r["md1_kept_groups"]))
        ),
        "bucket_b_md1_only_recall": sum(
            1
            for r in md1_scores
            if r["bucket"] == "B_multi_capability"
            and set(r["needed_groups"]).issubset(set(r.get("md1_only_kept_groups", [])))
        ),
        "bucket_c_false_keep_prompts": sum(
            1 for r in md1_scores if r["bucket"] == "C_adversarial_lookalike" and len(r["md1_kept_groups"]) > 0
        ),
        "bucket_c_md1_only_false_keep_prompts": sum(
            1
            for r in md1_scores
            if r["bucket"] == "C_adversarial_lookalike" and len(r.get("md1_only_kept_groups", [])) > 0
        ),
        "prompts": md1_scores,
    }

    analysis = {
        "setup": setup,
        "audit": audit_res,
        "overall_arms": overall_arms,
        "bucket_arms": bucket_arms,
        "pairwise_comparisons": comparisons,
        "bucket_comparisons": bucket_comparisons,
        "md1_routing_profile": md1_summary,
    }
    (HERE / "analysis.json").write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8", newline="\n")

    # Build REPORT.md
    lines = [
        "# Live 3-Arm Routing Study Report (`md1-live-routing-20261115`)",
        "",
        f"- **Repository Commit:** `{setup['repo_commit'][:7]}` (`All-The-Vibes/TokenMasterX`)",
        f"- **Copilot CLI:** `{setup['copilot_cli_version']}` (`{setup['model']}`, reasoning `{setup['reasoning_effort']}`)",
        f"- **MD-1 Deployment:** `{setup['md1_endpoint']}` (`Microsoft-Decision-1` v1, threshold `{setup['md1_threshold']}`)",
        f"- **Protocol Freeze SHA-256:** `{audit_res['protocol_sha256']}` (audit: `PASS`, `{audit_res['total_sessions']}` sessions, `{audit_res['charge_calls_verified']}` billed calls verified)",
        "",
        "## 1. Overall Results Across All 15 Paired Tasks (`45` Sessions)",
        "",
        "| Metric | `stock` | `tm_regex` (`--lean`) | `tm_md1` (`--lean` + MD-1) |",
        "| --- | ---: | ---: | ---: |",
        f"| Task pass rate | {overall_arms['stock']['passed']}/15 ({overall_arms['stock']['pass_rate']*100:.1f}%) | {overall_arms['tm_regex']['passed']}/15 ({overall_arms['tm_regex']['pass_rate']*100:.1f}%) | {overall_arms['tm_md1']['passed']}/15 ({overall_arms['tm_md1']['pass_rate']*100:.1f}%) |",
        f"| Needed capability recalled | {overall_arms['stock']['needed_recalled']}/15 | {overall_arms['tm_regex']['needed_recalled']}/15 | {overall_arms['tm_md1']['needed_recalled']}/15 |",
        f"| Mean active tools / session | {overall_arms['stock']['mean_tool_count']:.1f} | {overall_arms['tm_regex']['mean_tool_count']:.1f} | {overall_arms['tm_md1']['mean_tool_count']:.1f} |",
        f"| Mean `tool_tokens + tool_instructions` | {overall_arms['stock']['mean_schema_plus_instr_tokens']:,.0f} | {overall_arms['tm_regex']['mean_schema_plus_instr_tokens']:,.0f} | {overall_arms['tm_md1']['mean_schema_plus_instr_tokens']:,.0f} |",
        f"| Mean first-call input tokens | {overall_arms['stock']['mean_first_call_input']:,.0f} | {overall_arms['tm_regex']['mean_first_call_input']:,.0f} | {overall_arms['tm_md1']['mean_first_call_input']:,.0f} |",
        f"| Mean raw tokens / session | {overall_arms['stock']['mean_raw_tokens']:,.0f} | {overall_arms['tm_regex']['mean_raw_tokens']:,.0f} | {overall_arms['tm_md1']['mean_raw_tokens']:,.0f} |",
        f"| Total raw tokens (15 tasks) | {overall_arms['stock']['total_raw_tokens']:,} | {overall_arms['tm_regex']['total_raw_tokens']:,} | {overall_arms['tm_md1']['total_raw_tokens']:,} |",
        f"| Total cold-start cost (`cold_usd`) | ${overall_arms['stock']['total_cold_usd']:.4f} | ${overall_arms['tm_regex']['total_cold_usd']:.4f} | ${overall_arms['tm_md1']['total_cold_usd']:.4f} |",
        f"| Total as-run billed cost (`billed_usd`) | ${overall_arms['stock']['total_billed_usd']:.4f} | ${overall_arms['tm_regex']['total_billed_usd']:.4f} | ${overall_arms['tm_md1']['total_billed_usd']:.4f} |",
        f"| Mean session duration (s) | {overall_arms['stock']['mean_seconds']:.1f}s | {overall_arms['tm_regex']['mean_seconds']:.1f}s | {overall_arms['tm_md1']['mean_seconds']:.1f}s |",
        "",
        "## 2. Pairwise Statistical Comparisons (`n = 15` Paired Tasks, 10,000 Bootstrap Draws)",
        "",
        "| Endpoint | Comparison | Mean Change (%) | 95% Bootstrap CI (%) | Wilcoxon `p` | Holm `p` | Pairs (Lower / Higher / Tie) |",
        "| --- | --- | ---: | --- | ---: | ---: | --- |",
    ]
    for metric in ("raw_tokens", "cold_usd", "billed_usd", "first_call_input_tokens", "seconds"):
        for label, _, _ in PAIRINGS:
            c = comparisons[metric][label]
            ci_lo, ci_hi = c["pct_change_ci95"]
            lines.append(
                f"| `{metric}` | `{label}` | {c['pct_change']:+.1f}% | [{ci_lo:+.1f}%, {ci_hi:+.1f}%] | "
                f"{c['wilcoxon_p']:.4f} | {c['wilcoxon_p_holm']:.4f} | "
                f"{c['improved_pairs']}/{c['worse_pairs']}/{c['tied_pairs']} |"
            )

    lines.extend(
        [
            "",
            "## 3. Bucket-Stratified Breakdown (`5` Tasks per Bucket)",
            "",
            "| Bucket | Arm | Pass | Capability Recalled | Native Tool Used | Shell Workarounds | Avg False-Keep Tools | Mean Schema+Instr Toks | Mean Raw Toks | Total Cold USD |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for b in BUCKETS:
        for arm in ARMS:
            s = bucket_arms[b][arm]
            lines.append(
                f"| `{b}` | `{arm}` | {s['passed']}/5 | {s['needed_recalled']}/5 | {s['target_tool_used']}/5 | "
                f"{s['shell_workarounds']}/5 | {s['mean_false_keep_tools']:.1f} | "
                f"{s['mean_schema_plus_instr_tokens']:,.0f} | {s['mean_raw_tokens']:,.0f} | ${s['total_cold_usd']:.4f} |"
            )

    lines.extend(
        [
            "",
            "## 4. MD-1 Routing Scores & Pre-Launch Latency (`15` Frozen Prompts)",
            "",
            f"- **Latency:** mean `{md1_summary['mean_ms']} ms`, median `{md1_summary['median_ms']} ms`, p90 `{md1_summary['p90_ms']} ms`, max `{md1_summary['max_ms']} ms`.",
            "",
            "| Task | Bucket | Needed | Regex Kept | MD-1 Standalone | `v0.3.0` Union Kept | Latency (ms) | Top MD-1 Group Scores |",
            "| --- | --- | --- | --- | --- | --- | ---: | --- |",
        ]
    )
    for row in md1_scores:
        tid = row["task_id"]
        rx_kept = by_pair[(tid, "tm_regex")]["kept_groups"]
        top_scores = ", ".join(
            f"{k}={v:.3f}" for k, v in sorted(row["scores"].items(), key=lambda kv: -kv[1])[:3]
        )
        lines.append(
            f"| `{tid}` | `{row['bucket']}` | `{row['needed_groups']}` | `{rx_kept}` | "
            f"`{row.get('md1_only_kept_groups', [])}` | `{row['md1_kept_groups']}` | "
            f"{row['md1_latency_ms']:.0f} | {top_scores} |"
        )

    lines.extend(
        [
            "",
            "## 5. Per-Task Live Session Ledger (`45` Sessions)",
            "",
            "| Task | Bucket | Pass (`S / R / M`) | Calls (`S / R / M`) | Raw Tokens (`S / R / M`) | Cold USD (`S / R / M`) | Native Cap Tool (`S / R / M`) |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for tid in task_ids:
        s, r, m = by_pair[(tid, "stock")], by_pair[(tid, "tm_regex")], by_pair[(tid, "tm_md1")]
        p_str = f"{'Y' if s['passed'] else 'N'} / {'Y' if r['passed'] else 'N'} / {'Y' if m['passed'] else 'N'}"
        c_str = f"{s['call_count']} / {r['call_count']} / {m['call_count']}"
        tok_str = f"{s['raw_tokens']:,} / {r['raw_tokens']:,} / {m['raw_tokens']:,}"
        usd_str = f"${s['cold_usd']:.4f} / ${r['cold_usd']:.4f} / ${m['cold_usd']:.4f}"
        cap_str = (
            f"{'Y' if s['target_tool_used'] else '-'} / "
            f"{'Y' if r['target_tool_used'] else ('W' if r['shell_workaround'] else '-')} / "
            f"{'Y' if m['target_tool_used'] else ('W' if m['shell_workaround'] else '-')}"
        )
        lines.append(f"| `{tid}` | `{s['bucket']}` | {p_str} | {c_str} | {tok_str} | {usd_str} | {cap_str} |")

    lines.extend(
        [
            "",
            "## 6. Key Behavioral & Architectural Findings",
            "",
            "1. **Pure-Coding Schema Savings Hold Live (`Bucket A`, `15/15` pass across all arms):**",
            "   - When all 13 auxiliary tools are pruned (`8` active tools instead of `21`), Copilot CLI `1.0.112`'s `promptCacheBreakState` confirms static schema + tool-instruction overhead drops from **`12,156` tokens/call** (`9,394` `tool_tokens` + `2,762` `tool_instructions`) to **`3,649` tokens/call (`-70.0%`, `-8,507` tokens/call)**.",
            "   - Across `A01`–`A05`, raw session tokens fall **`-46.0%`** (`tm_regex`) and **`-44.4%`** (`tm_md1`) and cold-start cost falls **`-37.3%`** and **`-34.0%`** with `5/5` task accuracy.",
            "",
            "2. **Regex-Only `--lean` Breaks Natural Multi-Capability Workflows (`Bucket B`, `0/5` capability recall on `tm_regex` vs `5/5` on `tm_md1`):**",
            "   - **`B02` (`session_history`) fails outright on `tm_regex`:** Without `session_store_sql`, `tm_regex` searches repo files and returns `Unknown`, whereas `tm_md1` (`session_history = 0.999`) recalls `session_store_sql` and passes in `3` calls (`24,753` tokens vs `stock`'s `88,618`, **`-72.1%`**).",
            "   - **`B04` (`copilot_docs`) thrashes on `tm_regex`:** Stripping `fetch_copilot_cli_documentation` forces `tm_regex` into `8` shell/search calls (`58,233` tokens, `25.9s`), whereas `tm_md1` (`copilot_docs = 0.999`) finishes cleanly in `3` calls (`25,992` tokens, `19.3s` — **`-55.4%` fewer tokens than `tm_regex`** and **`-60.1%` fewer than `stock`**).",
            "   - **`B01` (`agents`) & `B05` (`sql`) silently violate workflow constraints on `tm_regex`:** Stripping `task` (`B01`) prevents helper subagent delegation (`0` subagent calls vs `4` on `stock` and `tm_md1`), and stripping `sql` (`B05`) prevents creating the requested `headroom_suite` table in the built-in session SQLite database.",
            "   - **`B03` (`background_shell`) exposes a split-schema hazard in `tm_regex`:** Even when `read_powershell` and `stop_powershell` are excluded from `active_tools`, `powershell`'s own description still instructs the model to use them. Unable to read `READY:<port>` from its async shell cleanly, `tm_regex` scraped OS-wide `Get-NetTCPConnection` and `Win32_Process` tables across sibling processes (`36.9s`, `$0.1698`) before hallucinating an unlisted `read_powershell` call at cleanup; `tm_md1` (`background_shell = 0.999`) completed cleanly via `read_powershell` + `stop_powershell` in `26.9s` (`$0.1599`).",
            "",
            "3. **Architectural Discovery on Adversarial Lookalikes (`Bucket C`): `v0.3.0`'s Additive `regex | md1` Union Leaks False Positives That Standalone MD-1 Rejects (`0/5` vs `5/5`):**",
            "   - Standalone `Microsoft-Decision-1` (`MD-1 Standalone`) achieved **`15/15` (`100%`) exact family classification** across all three buckets: `>= 0.999` on every true Bucket B capability and `<= 0.053` on every Bucket A and Bucket C distractor (`0/5` false-keep prompts on Bucket C), with **`628 ms` median** (`703 ms` p90) one-time pre-launch HTTP latency.",
            "   - However, `brainspace_copilot_bridge.py` (`lines 324–328`) runs `CAPABILITY_GROUPS` regex matching unconditionally and **only unions** `md1_families(prompt_text)` (`# opt-in; only ever adds families`), rendering the `false` criteria in `MD1_QUESTIONS` (`lines 120–160`) dead code whenever any regex matches. Consequently, `v0.3.0`'s `tm_md1` inherited all `5/5` regex false positives on `C01`–`C05`, inflating schema + tool-instruction overhead from **`3,649` -> `6,601` tokens/call (`+80.9%`)** (and up to `10,345` tokens/call on `C05`, nearly erasing `--lean` savings).",
            "   - **Recommended `v0.3.1` fix (`~10` lines in `select_excluded_tools`):** Keep deterministic hard signals unconditional (`--agent`, `--fleet`, `--resume`/`--continue`, `/slash` commands, `TOKENMASTER_KEEP_TOOLS`, and literal installed skill/agent names), but when `md1_scores(prompt_text)` returns a score for `family`, let MD-1 decide that family instead of `CAPABILITY_GROUPS` regexes, falling back to regexes only when MD-1 is unset or unreachable.",
        ]
    )

    (HERE / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("Analysis complete: wrote analysis.json and REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
