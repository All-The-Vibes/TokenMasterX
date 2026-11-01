"""Audit and analysis of TokenMaster with --lean against stock (exploratory, Copilot CLI 1.0.105, November 1, 2026).

Copies the numbers of every session from the local run folders into this folder: results.jsonl, summary.json,
setup.json (account reduced to its type) and runs/<session>/calls.jsonl, Copilot CLI's own record of each model call
(GitHub's token counts, GitHub's charge in nano-AIU and GitHub's per-token prices; no prompt or response text).

It stops if the runs do not match PROTOCOL.md (Django commit, model, Copilot CLI package, task order). It audits every
session: Copilot CLI version from the session's event log, model, one Copilot session per run, GitHub's charge
against its token counts, the store's charge against the CLI's own running total, and results.jsonl (including the
cold re-pricing) recomputed from calls.jsonl. Then it computes, as on October 27, paired 10,000-resample bootstrap
95% CIs (seed 20261022), exact Wilcoxon signed-rank p-values and a Holm-Bonferroni adjustment over raw tokens and
cold-repriced cost, and applies PROTOCOL.md's decision rule. The verdict is withheld unless the audit is clean. It also
compares this run's saving with the default-setup run of the same day and build (../default-nolean-20261101): the
difference of the two tm/stock ratios, with a bootstrap CI that resamples the same tasks in both runs.

  python analyze.py [<local run root>]
"""
from __future__ import annotations

import json
import random
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "token-master-plugin/evals"))
sys.path.insert(0, str(REPO / "token-master-plugin/skills/token-master"))
import run_prs1_study as p1  # noqa: E402
import run_prs3_study as p3  # noqa: E402
import tokenomics  # noqa: E402

# PROTOCOL.md: PRS-6's two Django shards and orders, as on October 27.
SHARDS = {"django-rare": ["D09", "D01", "D07", "D03", "D05", "D04", "D08", "D02", "D06", "D10"],
          "django-common": ["D12", "D11", "D14", "D13", "D15"]}
PILOT = ()
DJANGO_COMMIT, MODEL, PACKAGE = "9e7cc2b6", "gpt-6-astra", "1.0.105"
DRAWS, SEED = 10_000, 20261022
NANO_PER_USD = 1e11
CREDIT_CAP = 620  # the two shard caps, 370 + 250
DEFAULT_RUN = HERE.parent / "default-nolean-20261101"  # same day and build, TokenMaster without --lean
KEYS = ("calls", "input", "cached", "cache_write", "output", "nano")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] \
        if path.is_file() else []


def account_type(host: str) -> str:
    return "GitHub Enterprise Cloud with data residency (*.ghe.com)" if host.endswith(".ghe.com") else host


def copy_from_local(root: Path) -> None:
    for shard in (*SHARDS, *PILOT):
        src, dst = root / shard, HERE / shard
        if not src.is_dir():
            continue
        dst.mkdir(exist_ok=True)
        for name in ("results.jsonl", "summary.json"):
            if (src / name).is_file():
                shutil.copy2(src / name, dst / name)
        setup = json.loads((src / "setup.json").read_text(encoding="utf-8"))
        setup["account"] = {"type": account_type(setup["account"]["host"]), "routing": "Copilot CLI default sign-in"}
        (dst / "setup.json").write_text(json.dumps(setup, indent=1) + "\n", encoding="utf-8")
        for session in sorted((src / "runs").iterdir()):
            if (session / "calls.jsonl").is_file():
                (dst / "runs" / session.name).mkdir(parents=True, exist_ok=True)
                shutil.copy2(session / "calls.jsonl", dst / "runs" / session.name / "calls.jsonl")


def check_protocol() -> None:
    """The runs must be the ones PROTOCOL.md describes; anything else stops the analysis."""
    for shard, order in SHARDS.items():
        setup_file = HERE / shard / "setup.json"
        if not setup_file.is_file():
            raise SystemExit(f"missing study shard: {shard}")
        setup = json.loads(setup_file.read_text(encoding="utf-8"))
        problems = [name for name, ok in (
            ("django commit", (setup.get("django_head") or "").startswith(DJANGO_COMMIT)),
            ("model", setup.get("model") == MODEL), ("package", setup.get("package") == PACKAGE),
            ("task order", [task for _, task in setup.get("jobs", [])] == order)) if not ok]
        if problems:
            raise SystemExit(f"{shard} does not match PROTOCOL.md: {problems}")


def cold_nano(calls: list[dict]) -> float:
    """PRS-6's cold re-pricing from calls.jsonl: the first main-agent call's cache reads priced as cache writes."""
    first = next((c for c in calls if not c.get("agent_id")), None)
    if first is None:
        return 0.0
    prices = tokenomics.prices_of(first.get("token_details_json"))
    return (first.get("cache_read_tokens") or 0) * (prices.get("cache_write", 0) - prices.get("cache_read", 0))


def charge_problems(calls: list[dict]) -> list[str]:
    """GitHub's charge for each call recomputed from the call's own token counts and per-token prices. A call
    without all four prices cannot be checked, so it counts as a problem."""
    problems = []
    for call in calls:
        prices = tokenomics.prices_of(call.get("token_details_json"))
        if any(kind not in prices for kind in ("input", "cache_read", "cache_write", "output")):
            problems.append(f"call {call.get('n')}: missing prices")
            continue
        read, write = call["cache_read_tokens"] or 0, call["cache_write_tokens"] or 0
        charge = (((call["input_tokens"] or 0) - read - write) * prices["input"] + read * prices["cache_read"]
                  + write * prices["cache_write"] + (call["output_tokens"] or 0) * prices["output"])
        if abs(charge - (call["total_nano_aiu"] or 0)) > 1:
            problems.append(f"call {call.get('n')}: charged {call['total_nano_aiu']}, tokens give {round(charge)}")
    return problems


def audit(shard: Path) -> dict:
    """Every session of a shard. Spend counts every calls.jsonl, including sessions without a graded result."""
    out = {"sessions": 0, "wrong_version": [], "other_models": [], "several_copilot_sessions": [],
           "charge_mismatch": [], "cli_total_mismatch": [], "recount_mismatch": [], "infra": [],
           "nano_total": sum(c.get("total_nano_aiu") or 0 for f in (shard / "runs").glob("*/calls.jsonl")
                             for c in read_jsonl(f))}
    for row in read_jsonl(shard / "results.jsonl"):
        if row["status"] not in ("pass", "fail"):
            out["infra"].append(row["session"])
            continue
        out["sessions"] += 1
        usage, calls = row["usage"], read_jsonl(shard / "runs" / row["session"] / "calls.jsonl")
        if row.get("copilot_version") != PACKAGE:
            out["wrong_version"].append([row["session"], row.get("copilot_version")])
        if usage["models"] != [MODEL]:
            out["other_models"].append([row["session"], usage["models"]])
        if len(usage.get("session_ids") or []) > 1:
            out["several_copilot_sessions"].append(row["session"])
        problems = charge_problems(calls)  # recomputed from calls.jsonl, not the harness's stored recount
        if problems:
            out["charge_mismatch"].append([row["session"], problems])
        if row.get("cli_nano") is not None and row["cli_nano"] != usage["nano"]:
            out["cli_total_mismatch"].append([row["session"], row["cli_nano"], usage["nano"]])
        recount = {"calls": len(calls), "input": sum(c["input_tokens"] or 0 for c in calls),
                   "cached": sum(c["cache_read_tokens"] or 0 for c in calls),
                   "cache_write": sum(c["cache_write_tokens"] or 0 for c in calls),
                   "output": sum(c["output_tokens"] or 0 for c in calls),
                   "nano": sum(c["total_nano_aiu"] or 0 for c in calls)}
        if recount != {k: usage[k] for k in KEYS} or abs(recount["nano"] + cold_nano(calls) - usage["nano_cold"]) > 1:
            out["recount_mismatch"].append(row["session"])
    out["clean"] = not any(out[k] for k in ("wrong_version", "other_models", "several_copilot_sessions",
                                            "charge_mismatch", "cli_total_mismatch", "recount_mismatch"))
    return out


def chosen(shards: list[Path]) -> dict:
    """Per (task, arm): the session, or its re-run if the session was an infrastructure failure."""
    rows = {}
    for shard in shards:
        for row in read_jsonl(shard / "results.jsonl"):
            key = (row["task"], row["arm"])
            if key not in rows or (rows[key]["status"] == "infra" and row["session"].endswith("-rerun")):
                rows[key] = row
    return rows


def median(values: list) -> float | None:
    values = sorted(values)
    return values[len(values) // 2] if values else None


def analyze_suite(shards: list[Path], tasks: list[str]) -> dict:
    rows = chosen(shards)
    paired = [t for t in tasks if all(rows.get((t, a), {}).get("status") in ("pass", "fail") for a in ("stock", "tm"))]
    values = {"raw_tokens": lambda r: r["usage"]["input"] + r["usage"]["output"],
              "usd_cold": lambda r: r["usage"]["nano_cold"] / NANO_PER_USD,
              "usd_as_run": lambda r: r["usage"]["nano"] / NANO_PER_USD,
              "calls": lambda r: r["usage"]["calls"]}
    # PROTOCOL.md: a task without a graded session after its re-run counts as not passed
    passes_all = {arm: sum(rows.get((t, arm), {}).get("status") == "pass" for t in tasks) for arm in ("stock", "tm")}
    passes = {arm: sum(rows[(t, arm)]["status"] == "pass" for t in paired) for arm in ("stock", "tm")}
    firsts = {arm: [rows[(t, arm)]["first_call"] for t in paired] for arm in ("stock", "tm")}
    entry = {"tasks": len(tasks), "paired_tasks": len(paired), "excluded_tasks": sorted(set(tasks) - set(paired)),
             "sessions_started_utc": [min(r["started_utc"] for r in rows.values() if "started_utc" in r),
                                      max(r["started_utc"] for r in rows.values() if "started_utc" in r)],
             "passes_of_all_tasks": passes_all, "passes": passes,
             "pass_rate_ci95": {arm: p1.wilson(passes_all[arm], len(tasks)) for arm in passes_all},
             "stock_only_passes": [t for t in paired if rows[(t, "stock")]["status"] == "pass"
                                   and rows[(t, "tm")]["status"] != "pass"],
             "tm_only_passes": [t for t in paired if rows[(t, "tm")]["status"] == "pass"
                                and rows[(t, "stock")]["status"] != "pass"],
             "failure_reasons": {arm: {t: rows.get((t, arm), {}).get("why", "not run") for t in tasks
                                       if rows.get((t, arm), {}).get("status") != "pass"} for arm in ("stock", "tm")},
             "first_call_median": {arm: {k: median([f.get(k) or 0 for f in firsts[arm]])
                                         for k in ("input", "cached", "cache_write")} for arm in firsts},
             "warm_first_calls": {arm: sum((f.get("cached") or 0) >= 0.5 * (f.get("input") or 1) for f in firsts[arm])
                                  for arm in firsts},
             "tm_sessions_using_nav": sum(rows[(t, "tm")]["nav_calls"] > 0 for t in paired),
             "tm_nav_calls": sum(rows[(t, "tm")]["nav_calls"] for t in paired),
             "subagent_calls": {arm: sum(rows[(t, arm)]["usage"]["subagent_calls"] for t in paired)
                                for arm in ("stock", "tm")}}
    rng = random.Random(SEED)
    for name, value in values.items():
        per = {t: {arm: value(rows[(t, arm)]) for arm in ("stock", "tm")} for t in paired}
        totals = {arm: round(sum(per[t][arm] for t in paired), 4) for arm in ("stock", "tm")}
        draws = []
        for _ in range(DRAWS):
            sample = [rng.choice(paired) for _ in paired]
            draws.append(sum(per[t]["tm"] for t in sample) / sum(per[t]["stock"] for t in sample) - 1)
        draws.sort()
        entry[name] = {**totals, "change": round(totals["tm"] / totals["stock"] - 1, 4),
                       "ci95": [round(draws[int(0.025 * DRAWS)], 4), round(draws[int(0.975 * DRAWS)], 4)],
                       "tasks_lower": sum(per[t]["tm"] < per[t]["stock"] for t in paired),
                       "wilcoxon_p": round(p3.wilcoxon_exact([per[t]["tm"] - per[t]["stock"] for t in paired]), 6)}
    primary = ("raw_tokens", "usd_cold")
    for endpoint, adjusted in zip(primary, p1.holm([entry[e]["wilcoxon_p"] for e in primary]), strict=True):
        entry[endpoint]["holm_p"] = round(adjusted, 6)
        entry[endpoint]["verdict"] = ("lower" if entry[endpoint]["ci95"][1] < 0 and adjusted < 0.05
                                      else "higher" if entry[endpoint]["ci95"][0] > 0 and adjusted < 0.05
                                      else "no significant difference")
    return entry


def decision(suite: dict, audit_clean: bool) -> dict:
    """PROTOCOL.md: a headline may quote a default-setup saving only if raw tokens are "lower" (whole 95% CI below 0,
    Holm p < 0.05), with the point estimate and its CI; nothing is decided unless the audit is clean."""
    out = {"audit_clean": audit_clean}
    for endpoint in ("raw_tokens", "usd_cold"):
        out[endpoint] = {"change": suite[endpoint]["change"], "ci95": suite[endpoint]["ci95"],
                         "holm_p": suite[endpoint]["holm_p"], "verdict": suite[endpoint]["verdict"]}
    out["headline_saving_allowed"] = audit_clean and suite["raw_tokens"]["verdict"] == "lower"
    if not audit_clean:
        out["verdict_withheld"] = "the audit found problems; see audit"
    return out


def cross_run(lean_shards: list[Path], default_shards: list[Path], tasks: list[str]) -> dict:
    """PROTOCOL.md: the --lean saving minus the default setup's, each against its own stock arm, over the tasks graded
    in both runs. Each draw resamples tasks once and uses the same tasks in both runs (a comparison across two runs)."""
    runs = {"lean": chosen(lean_shards), "default": chosen(default_shards)}
    paired = [t for t in tasks if all(runs[r].get((t, a), {}).get("status") in ("pass", "fail")
                                      for r in runs for a in ("stock", "tm"))]
    values = {"raw_tokens": lambda r: r["usage"]["input"] + r["usage"]["output"],
              "usd_cold": lambda r: r["usage"]["nano_cold"] / NANO_PER_USD}
    out = {"note": "two runs on the same day and Copilot CLI build; each saving is against its own stock arm",
           "paired_tasks": len(paired)}
    rng = random.Random(SEED)
    for name, value in values.items():
        per = {t: {(r, a): value(runs[r][(t, a)]) for r in runs for a in ("stock", "tm")} for t in paired}

        def ratio(sample, run):
            return sum(per[t][(run, "tm")] for t in sample) / sum(per[t][(run, "stock")] for t in sample)

        draws = sorted(ratio(s, "lean") - ratio(s, "default") for s in ([rng.choice(paired) for _ in paired]
                                                                         for _ in range(DRAWS)))
        out[name] = {"lean_change": round(ratio(paired, "lean") - 1, 4),
                     "default_change": round(ratio(paired, "default") - 1, 4),
                     "lean_minus_default": round(ratio(paired, "lean") - ratio(paired, "default"), 4),
                     "ci95": [round(draws[int(0.025 * DRAWS)], 4), round(draws[int(0.975 * DRAWS)], 4)],
                     "stock_lean_over_stock_default": round(sum(per[t][("lean", "stock")] for t in paired)
                                                            / sum(per[t][("default", "stock")] for t in paired) - 1, 4)}
    return out


def self_test() -> None:
    prices = (("input", 10**12), ("cache_read", 10**11), ("cache_write", 125 * 10**10), ("output", 5 * 10**12))
    details = json.dumps([{"batchSize": 10**6, "costPerBatch": cost, "tokenCount": 0, "tokenType": kind}
                          for kind, cost in prices])  # gpt-6-astra: 1e6, 1e5, 1.25e6 and 5e6 nano per token
    good = {"n": 1, "input_tokens": 1000, "cache_read_tokens": 600, "cache_write_tokens": 300, "output_tokens": 10,
            "total_nano_aiu": 100 * 10**6 + 600 * 10**5 + 300 * 125 * 10**4 + 10 * 5 * 10**6,
            "token_details_json": details}
    assert charge_problems([good]) == []
    assert charge_problems([{**good, "token_details_json": "[]"}])  # no prices: the charge cannot be checked
    assert charge_problems([{**good, "total_nano_aiu": good["total_nano_aiu"] + 10}])
    print("self-test passed")


def main() -> None:
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        return
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"C:\tm-work\lean-runs")
    if root.is_dir():
        copy_from_local(root)
    check_protocol()
    audits = {shard.name: audit(shard) for shard in sorted(HERE.iterdir())
              if shard.is_dir() and (shard / "runs").is_dir()}
    spent = sum(a["nano_total"] for a in audits.values()) / 1e9
    tasks = sorted(t for order in SHARDS.values() for t in order)
    suite = analyze_suite([HERE / s for s in SHARDS], tasks)
    clean = all(audits[s]["clean"] for s in SHARDS)
    out = {"study": "TokenMaster with --lean vs stock, default GitHub routing",
           "kind": "exploratory; decision rule frozen in PROTOCOL.md",
           "copilot_cli": PACKAGE, "model": MODEL, "bootstrap": {"draws": DRAWS, "seed": SEED},
           "audit": audits, "ai_credits_spent": round(spent, 2), "ai_credit_cap": CREDIT_CAP,
           "django_15_tasks": {**suite, "decision": decision(suite, clean),
                               "against_default_setup_same_build": cross_run(
                                   [HERE / s for s in SHARDS], [DEFAULT_RUN / s for s in SHARDS], tasks)}}
    (HERE / "analysis.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
