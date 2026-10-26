"""Audit and statistical analysis of PRS-6 (pre-registered Copilot CLI 1.0.98 study, October 26, 2026).

Copies per-session results.jsonl, setup.json, summary.json, and per-call calls.jsonl from the local run
directory into this evidence folder (excluding captures.jsonl, which holds Copilot's system prompt),
verifies from local captures.jsonl (when present) that every session ran Copilot CLI 1.0.98 and matches
calls.jsonl to the token, and computes 10,000-resample paired bootstrap 95% CIs (seed 20261022), exact
Wilcoxon signed-rank p-values, and Holm-Bonferroni adjusted p-values across the two co-primary endpoints
(raw tokens and cold-repriced USD cost).

  python analyze.py [<local prs6-runs-20261026 folder>]
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "token-master-plugin/evals"))
import quick_copilot_ab as q  # noqa: E402
import run_prs1_study as p1  # noqa: E402
import run_prs3_study as p3  # noqa: E402
import run_prs5_study as p5  # noqa: E402

SHARDS = ("astra-a", "astra-b", "opus-a", "opus-b",
          "django-astra-ab", "django-opus-ab", "django-astra-common-ab", "django-opus-common-ab")
MODELS = {"astra": "gpt-6-astra", "opus": "claude-opus-5.5"}
INPUT_USD_PER_M = {"gpt-6-astra": 10.00, "claude-opus-5.5": 4.00}
DRAWS, SEED = 10_000, 20261022
NANO_AIU = re.compile(r'"total_nano_aiu"\s*:\s*(\d+)')
VERSION_RE = re.compile(r"Version number:\s*([^\s<\\n\"]+)")


def cold_usage(row: dict) -> dict:
    moved = row["first_call"].get("cached") or 0
    return dict(row["usage"], cached=row["usage"]["cached"] - moved, cache_write=row["usage"]["cache_write"] + moved)


def copy_from_local(local_root: Path) -> dict:
    """Copy results.jsonl, setup.json, summary.json and calls.jsonl; audit local captures.jsonl."""
    capture_audit = {"sessions_checked": 0, "version_1_0_98_sessions": 0, "other_versions": [],
                     "recount_mismatches": 0, "nano_aiu_by_model_arm": {}}
    for shard in SHARDS:
        src = local_root / shard
        if not src.is_dir():
            continue
        dst = HERE / shard
        dst.mkdir(parents=True, exist_ok=True)
        for name in ("results.jsonl", "setup.json", "summary.json", "warmup.json"):
            if (src / name).is_file():
                shutil.copy2(src / name, dst / name)
        rows_by_sid = {r["session"]: r for r in p5.read_jsonl(src / "results.jsonl") if r.get("usage")}
        for session in sorted((src / "runs").iterdir()):
            target_run = dst / "runs" / session.name
            target_run.mkdir(parents=True, exist_ok=True)
            if (session / "calls.jsonl").is_file():
                shutil.copy2(session / "calls.jsonl", target_run / "calls.jsonl")
            cap = session / "captures.jsonl"
            if cap.is_file() and session.name in rows_by_sid:
                capture_audit["sessions_checked"] += 1
                row = rows_by_sid[session.name]
                recount = p5.session_usage(session, from_captures=True)
                keys = ("calls", "input", "cached", "cache_write", "output")
                if {k: recount[k] for k in keys} != {k: row["usage"][k] for k in keys}:
                    capture_audit["recount_mismatches"] += 1
                first_line = cap.read_text(encoding="utf-8").splitlines()[0]
                m = VERSION_RE.search(first_line)
                ver = m.group(1) if m else "missing"
                if ver == "1.0.98":
                    capture_audit["version_1_0_98_sessions"] += 1
                else:
                    capture_audit["other_versions"].append({"session": session.name, "version": ver})
                model = "gpt-6-astra" if "astra" in shard else "claude-opus-5.5"
                key = f"{model}:{row['arm']}"
                bucket = capture_audit["nano_aiu_by_model_arm"].setdefault(key, {"nano_aiu": 0, "calls": 0})
                for line in cap.read_text(encoding="utf-8").splitlines():
                    obj = json.loads(line)
                    found = NANO_AIU.findall(obj.get("output_tail") or "")
                    if obj.get("status") == 200 and found:
                        bucket["nano_aiu"] += int(found[-1])
                        bucket["calls"] += 1
    for key, bucket in capture_audit["nano_aiu_by_model_arm"].items():
        bucket["usd_from_nano_aiu"] = round(bucket["nano_aiu"] / 1e11, 4)
    return capture_audit


def analyze_suite(folders: list[Path], model: str) -> dict:
    rows, starts, bill_units, calls_without_bill = {}, [], {"stock": 0.0, "tm": 0.0}, {"stock": 0, "tm": 0}
    nav_sessions, nav_calls = {"stock": 0, "tm": 0}, {"stock": 0, "tm": 0}
    for folder in folders:
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        for arm in ("stock", "tm"):
            nav_sessions[arm] += summary["arms"][arm]["sessions_using_nav"]
            nav_calls[arm] += summary["arms"][arm]["nav_calls"]
        for line in (folder / "results.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["status"] in ("pass", "fail"):
                rows[(row["task"], row["arm"])] = row
                starts.append(row["started_utc"])
                session_calls = folder / "runs" / row["session"] / "calls.jsonl"
                for cline in session_calls.read_text(encoding="utf-8").splitlines():
                    call = json.loads(cline)
                    if call["status"] == 200:
                        if call.get("bill"):
                            bill_units[row["arm"]] += call["bill"]["units"]
                        else:
                            calls_without_bill[row["arm"]] += 1
    tasks = sorted({t for t, _ in rows})
    values = {"raw_tokens": lambda r: r["usage"]["input"] + r["usage"]["output"],
              "usd_if_every_first_call_cold": lambda r: q.usd(cold_usage(r), model),
              "usd_as_run": lambda r: q.usd(r["usage"], model),
              "calls": lambda r: r["usage"]["calls"]}
    rng = random.Random(SEED)
    entry = {"tasks": len(tasks), "task_ids": tasks,
             "sessions_started_utc": [min(starts), max(starts)],
             "passes": {arm: sum(rows[(t, arm)]["status"] == "pass" for t in tasks) for arm in ("stock", "tm")},
             "warm_first_calls": {arm: sum((rows[(t, arm)]["first_call"].get("cached") or 0)
                                           >= 0.5 * (rows[(t, arm)]["first_call"].get("input") or 1) for t in tasks)
                                  for arm in ("stock", "tm")},
             "first_call_cache_write_median": {
                 arm: sorted(rows[(t, arm)]["first_call"].get("cache_write") or 0 for t in tasks)[len(tasks) // 2]
                 for arm in ("stock", "tm")
             },
             "first_call_cached_median": {
                 arm: sorted(rows[(t, arm)]["first_call"].get("cached") or 0 for t in tasks)[len(tasks) // 2]
                 for arm in ("stock", "tm")
             },
             "sessions_using_nav": nav_sessions, "nav_calls": nav_calls,
             "github_bill_usd": {arm: round(bill_units[arm] * INPUT_USD_PER_M[model] / 1e6, 4) for arm in ("stock", "tm")},
             "calls_without_bill": calls_without_bill}
    for name, value in values.items():
        per = {t: {arm: value(rows[(t, arm)]) for arm in ("stock", "tm")} for t in tasks}
        totals = {arm: round(sum(per[t][arm] for t in tasks), 4) for arm in ("stock", "tm")}
        diffs = [per[t]["tm"] - per[t]["stock"] for t in tasks]
        draws = []
        for _ in range(DRAWS):
            sample = [rng.choice(tasks) for _ in tasks]
            draws.append(sum(per[t]["tm"] for t in sample) / sum(per[t]["stock"] for t in sample) - 1)
        draws.sort()
        entry[name] = {**totals, "change": round(totals["tm"] / totals["stock"] - 1, 4),
                       "ci95": [round(draws[int(0.025 * DRAWS)], 4), round(draws[int(0.975 * DRAWS)], 4)],
                       "tasks_lower": sum(per[t]["tm"] < per[t]["stock"] for t in tasks),
                       "wilcoxon_p": round(p3.wilcoxon_exact(diffs), 6)}
    primary = ("raw_tokens", "usd_if_every_first_call_cold")
    for endpoint, adj in zip(primary, p1.holm([entry[e]["wilcoxon_p"] for e in primary]), strict=True):
        entry[endpoint]["holm_p"] = round(adj, 6)
        entry[endpoint]["verdict"] = ("lower" if entry[endpoint]["ci95"][1] < 0 and adj < 0.05
                                      else "higher" if entry[endpoint]["ci95"][0] > 0 and adj < 0.05
                                      else "no significant difference")
    entry["workload_floor_met"] = entry["raw_tokens"]["stock"] >= 2_000_000
    return entry


def main() -> None:
    local_default = Path(os.environ.get("TEMP", "/tmp")) / "opencode" / "prs6-runs-20261026"
    local_root = Path(sys.argv[1]) if len(sys.argv) > 1 else local_default
    audit_path = HERE / "capture_audit.json"
    if local_root.is_dir():
        capture_audit = copy_from_local(local_root)
        audit_path.write_text(json.dumps(capture_audit, indent=1) + "\n", encoding="utf-8")
    else:
        capture_audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.is_file() else {}
    out = {"study": "PRS-6", "kind": "pre-registered (token-master-plugin/docs/PRS6_PROTOCOL.md, commit 19443fc)",
           "copilot_cli_version": "1.0.98",
           "bootstrap": {"draws": DRAWS, "seed": SEED},
           "capture_audit": capture_audit,
           "repository_29_tasks": {},
           "django_15_tasks": {}}
    for short, model in MODELS.items():
        out["repository_29_tasks"][model] = analyze_suite([HERE / f"{short}-a", HERE / f"{short}-b"], model)
        out["django_15_tasks"][model] = analyze_suite(
            [HERE / f"django-{short}-ab", HERE / f"django-{short}-common-ab"], model
        )
    (HERE / "analysis.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
