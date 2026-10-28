"""Audit and analysis of the relay control for the default-routing A/B (exploratory, Copilot CLI 1.0.104,
October 27, 2026): PRS-6's evaluation relay with the default-routing study's client, lanes, graphify and account.

Copies the numbers of every session from the local run folders into this folder: results.jsonl, summary.json,
warmup.json, setup.json (account reduced to its type) and runs/<session>/calls.jsonl. calls.jsonl is the relay's record
of each model call (token counts and price ratios, as in PRS-6), plus three fields taken from the captured response:
GitHub's charge (total_nano_aiu), GitHub's per-token prices and the model that answered. The captures stay local: they
hold Copilot CLI's system prompt. From them, captures_audit.json records per session only numbers and flags: the
Copilot CLI version in the system prompt, a recount of the results row, and what the first request carried from the
operator's profile folder (the lane test).

Audit of every study session: Copilot CLI 1.0.104, model gpt-6-astra, GitHub's charge on every answered call and equal
to its token counts at its own prices, the results row recounted from calls.jsonl and from the captures. Statistics as
in PRS-6 and the default-routing study: paired 10,000-resample bootstrap over tasks (seed 20261022), exact Wilcoxon,
Holm over raw tokens and cold-repriced cost. Comparisons, each with a task bootstrap of the difference: this run vs the
default-routing run (routing, same client build, account and day) and vs PRS-6's relay run (client build, TokenMaster
commit, day, lane location and account).

  python analyze.py [<local run root>]
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import random
import re
import shutil
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "token-master-plugin/evals"))
sys.path.insert(0, str(REPO / "token-master-plugin/skills/token-master"))
import quick_copilot_ab as q  # noqa: E402
import run_prs1_study as p1  # noqa: E402
import run_prs3_study as p3  # noqa: E402
import run_prs5_study as p5  # noqa: E402

# The default-routing study's shards and orders (its PROTOCOL.md), which are PRS-6's.
SHARDS = {"relay-rare": ["D09", "D01", "D07", "D03", "D05", "D04", "D08", "D02", "D06", "D10"],
          "relay-common": ["D12", "D11", "D14", "D13", "D15"]}
PILOT = ("pilot-d01", "lanetest-d01", "lanetest-short-d01")  # D01 from C:\tm-lanes, %TEMP% and %TEMP% in its 8.3
# form; excluded from the statistics
DJANGO_COMMIT, MODEL, PACKAGE = "9e7cc2b6", "gpt-6-astra", "1.0.104"
DRAWS, SEED = 10_000, 20261022
NANO_PER_USD = 1e11
CREDIT_CAP = 700
DEFAULT = REPO / "evidence/default-routing-20261027"
DEFAULT_SHARDS = ("django-rare", "django-common")
PRS6 = REPO / "evidence/prs6-copilot-1.0.98-20261026"
PRS6_SHARDS = ("django-astra-ab", "django-astra-common-ab")
KEYS = ("calls", "input", "cached", "cache_write", "output")
# nano-AIU per token at GitHub's published gpt-6-astra prices; used only if a response carried no prices (an audit fail)
PUBLISHED = {k: usd * NANO_PER_USD / 1e6 for k, usd in zip(("input", "cache_read", "cache_write", "output"),
                                                              q.USD_PER_M[MODEL])}
VERSION = re.compile(r"Version number:\s*([^\s<\\\"]+)")
ANSWERED_BY = re.compile(r'"model"\s*:\s*"([^"]+)"')


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] \
        if path.is_file() else []


def account_type(host: str) -> str:
    return "GitHub Enterprise Cloud with data residency (*.ghe.com)" if host.endswith(".ghe.com") else host


def copilot_usage(tail: str) -> dict | None:
    """GitHub's charge and per-token prices (nano-AIU per token) from a captured response."""
    at = tail.rfind('"copilot_usage":')
    if at < 0:
        return None
    start = at + len('"copilot_usage":')
    while start < len(tail) and tail[start] in " \t\r\n":
        start += 1
    try:
        usage = json.JSONDecoder().raw_decode(tail, start)[0]
        prices = {d["token_type"]: d["cost_per_batch"] / d["batch_size"] for d in usage["token_details"]}
        return {"total_nano_aiu": usage["total_nano_aiu"], "prices": prices}
    except (ValueError, KeyError, TypeError, ZeroDivisionError):
        return None


def operator_heading() -> str | None:
    """The first heading of the operator's CLAUDE.md: text that only an inherited instruction file puts in a prompt."""
    claude_md = Path.home() / ".claude" / "CLAUDE.md"
    lines = claude_md.read_text(encoding="utf-8").splitlines() if claude_md.is_file() else []
    return next((line.strip() for line in lines if line.startswith("# ")), None)


def request_facts(request: str, heading: str | None) -> dict:
    """What a first request carried, as sizes and flags (no content): its length, its tools, whether it held the
    operator's CLAUDE.md, and how many skills its available_skills list named."""
    try:
        body = json.loads(request)
    except ValueError:
        return {"request_chars": len(request)}
    system = (body.get("instructions") or "") + "".join(
        json.dumps(i, ensure_ascii=False) for i in body.get("input") or []
        if isinstance(i, dict) and i.get("role") in ("system", "developer"))
    listed = re.search(r"<available_skills>(.*?)</available_skills>", system, re.S)
    return {"request_chars": len(request), "system_chars": len(system), "tools": len(body.get("tools") or []),
            "operator_claude_md": bool(heading) and heading in request,
            "skills_listed": listed.group(1).count("<name>") if listed else 0}


def copy_from_local(root: Path) -> dict:
    heading, facts = operator_heading(), {}
    for shard in (*SHARDS, *PILOT):
        src, dst = root / shard, HERE / shard
        if not src.is_dir():
            continue
        dst.mkdir(exist_ok=True)
        for name in ("results.jsonl", "summary.json", "warmup.json"):
            if (src / name).is_file():
                shutil.copy2(src / name, dst / name)
        setup = json.loads((src / "setup.json").read_text(encoding="utf-8"))
        setup["account"] = {"type": account_type(setup["account"]["host"]),
                            "routing": "evaluation relay with Copilot CLI's stored sign-in"}
        setup["copilot_api"] = re.sub(r"//copilot-api\.[^./]+\.ghe\.com", "//copilot-api.<tenant>.ghe.com",
                                      setup["copilot_api"])
        (dst / "setup.json").write_text(json.dumps(setup, indent=1) + "\n", encoding="utf-8")
        rows = {r["session"]: r for r in read_jsonl(src / "results.jsonl")}
        for session in sorted((src / "runs").iterdir()):
            captures = {c["n"]: c for c in read_jsonl(session / "captures.jsonl")}
            calls = []
            for call in read_jsonl(session / "calls.jsonl"):
                tail = (captures.get(call["n"]) or {}).get("output_tail") or ""
                charge, answered_by = copilot_usage(tail), ANSWERED_BY.findall(tail)
                calls.append({**call, "total_nano_aiu": charge and charge["total_nano_aiu"],
                              "prices": charge and charge["prices"], "model": answered_by[-1] if answered_by else None})
            (dst / "runs" / session.name).mkdir(parents=True, exist_ok=True)
            (dst / "runs" / session.name / "calls.jsonl").write_text(
                "".join(json.dumps(c) + "\n" for c in calls), encoding="utf-8")
            row = rows.get(session.name)
            recount = p5.session_usage(session, from_captures=True) if captures else None
            first = captures[min(captures)]["input"] if captures else ""
            facts[f"{shard}/{session.name}"] = {
                "versions": sorted({m.group(1) for c in captures.values() if (m := VERSION.search(c["input"]))}),
                "recount_matches_results": bool(row and row.get("usage") and recount
                                                and all(recount[k] == row["usage"][k] for k in KEYS)),
                "first_request": request_facts(first, heading)}
    (HERE / "captures_audit.json").write_text(json.dumps(facts, indent=1) + "\n", encoding="utf-8")
    return facts


def check_protocol() -> None:
    """The study shards must be the ones the default-routing study ran, through the relay; anything else stops."""
    account = json.loads((DEFAULT / "django-rare" / "setup.json").read_text(encoding="utf-8"))["account"]["type"]
    for shard, order in SHARDS.items():
        setup_file = HERE / shard / "setup.json"
        if not setup_file.is_file():
            raise SystemExit(f"missing study shard: {shard}")
        setup = json.loads(setup_file.read_text(encoding="utf-8"))
        problems = [name for name, ok in (
            ("django commit", (setup.get("django_head") or "").startswith(DJANGO_COMMIT)),
            ("model", setup.get("model") == MODEL), ("package", setup.get("package") == PACKAGE),
            ("task order", [task for _, task in setup.get("jobs", [])] == order),
            ("lanes", setup.get("lanes", "").lower().startswith("c:\\tm-lanes\\")),
            ("lane sources", not setup.get("lanes_inherit_allowed")),
            ("account", setup.get("account", {}).get("type") == account)) if not ok]
        if problems:
            raise SystemExit(f"{shard} does not match the default-routing study: {problems}")


def recharge(call: dict) -> float:
    """GitHub's charge for one call, recomputed from its token counts and its own per-token prices."""
    u, p = call["usage"], call["prices"]
    new = u["input"] - (u["cached"] or 0) - (u["cache_write"] or 0)
    return (new * p["input"] + (u["cached"] or 0) * p["cache_read"] + (u["cache_write"] or 0) * p["cache_write"]
            + (u["output"] or 0) * p["output"])


def answered(calls: list[dict]) -> list[dict]:
    return sorted((c for c in calls if c["status"] == 200 and c.get("usage")), key=lambda c: c["n"])


def audit(shard: Path, facts: dict) -> dict:
    """Every session of a shard. Spend counts every call, including sessions without a graded result."""
    out = {"sessions": 0, "wrong_version": [], "other_models": [], "uncharged_calls": [], "charge_mismatch": [],
           "recount_mismatch": [], "failed_calls": [], "infra": [],
           "nano_total": sum(c.get("total_nano_aiu") or 0 for f in (shard / "runs").glob("*/calls.jsonl")
                             for c in read_jsonl(f))}
    for row in read_jsonl(shard / "results.jsonl"):
        if row["status"] not in ("pass", "fail"):
            out["infra"].append(row["session"])
            continue
        out["sessions"] += 1
        calls = read_jsonl(shard / "runs" / row["session"] / "calls.jsonl")
        ok = answered(calls)
        # the version in the system prompt, and the one in Copilot CLI's event log (rows from the study's harness)
        versions = set(row.get("copilot_versions") or []) | ({row["version"]} if "version" in row else set())
        if versions != {PACKAGE}:
            out["wrong_version"].append([row["session"], sorted(map(str, versions))])
        if {c["model"] for c in ok} != {MODEL}:
            out["other_models"].append([row["session"], sorted({str(c["model"]) for c in ok})])
        uncharged = [c["n"] for c in ok if c.get("total_nano_aiu") is None
                     or set(c.get("prices") or {}) < {"input", "cache_read", "cache_write", "output"}]
        if uncharged:
            out["uncharged_calls"].append([row["session"], uncharged])
        worst = max((abs(recharge(c) - c["total_nano_aiu"]) for c in ok if c["n"] not in uncharged), default=0)
        if worst > 1:
            out["charge_mismatch"].append([row["session"], worst])
        recount = {"calls": len(ok), **{k: sum(c["usage"][k] or 0 for c in ok) for k in KEYS[1:]}}
        if recount != {k: row["usage"][k] for k in KEYS} or sum(c["total_nano_aiu"] or 0 for c in ok) != row["nano"] \
                or not facts.get(f"{shard.name}/{row['session']}", {}).get("recount_matches_results", True):
            out["recount_mismatch"].append(row["session"])
        if len(ok) != len(calls):
            out["failed_calls"].append([row["session"], len(calls) - len(ok)])
    out["clean"] = not any(out[k] for k in ("wrong_version", "other_models", "uncharged_calls", "charge_mismatch",
                                            "recount_mismatch"))
    return out


def chosen(rows: list[dict]) -> dict:
    """Per (task, arm): the session, or its re-run if the session was an infrastructure failure."""
    picked = {}
    for row in rows:
        key = (row["task"], row["arm"])
        if key not in picked or (picked[key]["status"] == "infra" and row["session"].endswith("-rerun")):
            picked[key] = row
    return picked


def relay_values(shards: list[Path]) -> dict:
    """(task, arm) -> this run's endpoints. Cold: the first call's cache reads re-priced as cache writes at that call's
    own prices (PRS-6's cold re-pricing)."""
    values = {}
    for shard in shards:
        for key, row in chosen(read_jsonl(shard / "results.jsonl")).items():
            if row["status"] not in ("pass", "fail"):
                continue
            ok = answered(read_jsonl(shard / "runs" / row["session"] / "calls.jsonl"))
            prices = (ok[0].get("prices") or PUBLISHED) if ok else PUBLISHED
            moved = (ok[0]["usage"]["cached"] or 0) * (prices["cache_write"] - prices["cache_read"]) if ok else 0
            values[key] = {"raw_tokens": row["usage"]["input"] + row["usage"]["output"],
                           "usd_cold": (row["nano"] + moved) / NANO_PER_USD, "usd_as_run": row["nano"] / NANO_PER_USD,
                           "calls": row["usage"]["calls"], "pass": row["status"] == "pass",
                           "first_call": row["first_call"], "nav_calls": row.get("nav_calls", 0),
                           "started_utc": row["started_utc"]}
    return values


def default_values() -> dict:
    """The default-routing study's sessions, valued as its analyze.py does."""
    values = {}
    for shard in DEFAULT_SHARDS:
        for key, row in chosen(read_jsonl(DEFAULT / shard / "results.jsonl")).items():
            if row["status"] in ("pass", "fail"):
                values[key] = {"raw_tokens": row["usage"]["input"] + row["usage"]["output"],
                               "usd_cold": row["usage"]["nano_cold"] / NANO_PER_USD,
                               "usd_as_run": row["usage"]["nano"] / NANO_PER_USD, "calls": row["usage"]["calls"],
                               "pass": row["status"] == "pass", "first_call": row["first_call"]}
    return values


def prs6_values() -> dict:
    """PRS-6's gpt-6-astra Django sessions, valued as its analyze.py does (GitHub's published prices)."""
    values = {}
    for shard in PRS6_SHARDS:
        for key, row in chosen(read_jsonl(PRS6 / shard / "results.jsonl")).items():
            if row["status"] in ("pass", "fail"):
                moved = row["first_call"].get("cached") or 0
                cold = dict(row["usage"], cached=row["usage"]["cached"] - moved,
                            cache_write=row["usage"]["cache_write"] + moved)
                values[key] = {"raw_tokens": row["usage"]["input"] + row["usage"]["output"],
                               "usd_cold": q.usd(cold, MODEL), "usd_as_run": q.usd(row["usage"], MODEL),
                               "calls": row["usage"]["calls"], "pass": row["status"] == "pass",
                               "first_call": row["first_call"]}
    return values


def median(values: list) -> float | None:
    values = sorted(values)
    return values[len(values) // 2] if values else None


def paired(values: dict, tasks: list[str]) -> list[str]:
    return [t for t in tasks if (t, "stock") in values and (t, "tm") in values]


def analyze_suite(values: dict, tasks: list[str]) -> dict:
    """The default-routing study's statistics, on this run."""
    both = paired(values, tasks)
    entry = {"tasks": len(tasks), "paired_tasks": len(both), "excluded_tasks": sorted(set(tasks) - set(both)),
             "sessions_started_utc": [min(v["started_utc"] for v in values.values()),
                                      max(v["started_utc"] for v in values.values())],
             "passes_of_all_tasks": {arm: sum(values.get((t, arm), {}).get("pass", False) for t in tasks)
                                     for arm in ("stock", "tm")},
             "passes": {arm: sum(values[(t, arm)]["pass"] for t in both) for arm in ("stock", "tm")},
             "tm_sessions_using_nav": sum(values[(t, "tm")]["nav_calls"] > 0 for t in both),
             "tm_nav_calls": sum(values[(t, "tm")]["nav_calls"] for t in both)}
    entry["pass_rate_ci95"] = {arm: p1.wilson(entry["passes_of_all_tasks"][arm], len(tasks)) for arm in ("stock", "tm")}
    rng = random.Random(SEED)
    for name in ("raw_tokens", "usd_cold", "usd_as_run", "calls"):
        per = {t: {arm: values[(t, arm)][name] for arm in ("stock", "tm")} for t in both}
        totals = {arm: round(sum(per[t][arm] for t in both), 4) for arm in ("stock", "tm")}
        draws = []
        for _ in range(DRAWS):
            sample = [rng.choice(both) for _ in both]
            draws.append(sum(per[t]["tm"] for t in sample) / sum(per[t]["stock"] for t in sample) - 1)
        draws.sort()
        entry[name] = {**totals, "change": round(totals["tm"] / totals["stock"] - 1, 4),
                       "ci95": [round(draws[int(0.025 * DRAWS)], 4), round(draws[int(0.975 * DRAWS)], 4)],
                       "tasks_lower": sum(per[t]["tm"] < per[t]["stock"] for t in both),
                       "wilcoxon_p": round(p3.wilcoxon_exact([per[t]["tm"] - per[t]["stock"] for t in both]), 6)}
    for endpoint, adjusted in zip(("raw_tokens", "usd_cold"),
                                  p1.holm([entry[e]["wilcoxon_p"] for e in ("raw_tokens", "usd_cold")]), strict=True):
        entry[endpoint]["holm_p"] = round(adjusted, 6)
        entry[endpoint]["verdict"] = ("lower" if entry[endpoint]["ci95"][1] < 0 and adjusted < 0.05
                                      else "higher" if entry[endpoint]["ci95"][0] > 0 and adjusted < 0.05
                                      else "no significant difference")
    return entry


def profile(values: dict, tasks: list[str]) -> dict:
    """Per arm: totals, tokens per call and first-call medians."""
    out = {}
    for arm in ("stock", "tm"):
        mine = [values[(t, arm)] for t in tasks]
        raw, calls = sum(v["raw_tokens"] for v in mine), sum(v["calls"] for v in mine)
        out[arm] = {"raw_tokens": raw, "calls": calls,
                    "raw_tokens_per_call": int(raw / calls + 0.5) if calls else None,
                    "usd_cold": round(sum(v["usd_cold"] for v in mine), 4),
                    "usd_as_run": round(sum(v["usd_as_run"] for v in mine), 4), "passes": sum(v["pass"] for v in mine),
                    "first_call_median": {k: median([v["first_call"].get(k) or 0 for v in mine])
                                          for k in ("input", "cached", "cache_write")}}
    return out


def compare(this: dict, other: dict, tasks: list[str], seed: int) -> dict:
    """This run vs another on the same tasks, resampling tasks: the change in each arm's total, and the difference
    between the two runs' TokenMaster-vs-stock changes (percentage points)."""
    both = [t for t in tasks if all((t, arm) in run for run in (this, other) for arm in ("stock", "tm"))]
    rng, out = random.Random(seed), {"tasks": len(both)}
    for name in ("raw_tokens", "usd_cold", "usd_as_run", "calls"):
        def stats(sample: list[str]) -> dict:
            s = {(run, arm): sum(r[(t, arm)][name] for t in sample)
                 for run, r in (("this", this), ("other", other)) for arm in ("stock", "tm")}
            return {"stock_change": s[("this", "stock")] / s[("other", "stock")] - 1,
                    "tm_change": s[("this", "tm")] / s[("other", "tm")] - 1,
                    "saving_difference_pp": 100 * ((s[("this", "tm")] / s[("this", "stock")])
                                                   - (s[("other", "tm")] / s[("other", "stock")]))}
        point = stats(both)
        draws = [stats([rng.choice(both) for _ in both]) for _ in range(DRAWS)]
        out[name] = {k: {"point": round(v, 4), "ci95": [round(x, 4) for x in (
            sorted(d[k] for d in draws)[int(0.025 * DRAWS)], sorted(d[k] for d in draws)[int(0.975 * DRAWS)])]}
            for k, v in point.items()}
    return out


def lane_test() -> dict:
    """D01 from C:\\tm-lanes (pilot) and from %TEMP% in both path forms: first-call size and what it carried."""
    facts = json.loads((HERE / "captures_audit.json").read_text(encoding="utf-8")) \
        if (HERE / "captures_audit.json").is_file() else {}
    out = {}
    for shard in PILOT:
        setup_file = HERE / shard / "setup.json"
        if not setup_file.is_file():
            continue
        setup = json.loads(setup_file.read_text(encoding="utf-8"))
        for row in read_jsonl(HERE / shard / "results.jsonl"):
            sources = setup["lane_sources"][row["arm"]] if setup.get("lanes_inherit_allowed") else \
                "built-in skills only (checked before the first session)"
            out[f"{shard}/{row['arm']}"] = {"lane_root": str(Path(setup["lanes"]).parent), "status": row["status"],
                                            "first_call": row["first_call"],
                                            "calls": (row.get("usage") or {}).get("calls"), "lane_sources": sources,
                                            **facts.get(f"{shard}/{row['session']}", {}).get("first_request", {})}
    return out


def reading(vs_default: dict, vs_prs6: dict, profiles: dict, audit_clean: bool) -> dict:
    """PROTOCOL.md's reading rule, from the differences in tm / stock (percentage points of stock)."""
    out = {}
    for name in ("raw_tokens", "usd_cold"):
        ratio = {run: p["tm"][name] / p["stock"][name] for run, p in profiles.items()}
        gap = 100 * (ratio["default_routing_1.0.104"] - ratio["prs6_relay_1.0.98"])
        routing, rest = vs_default[name]["saving_difference_pp"], vs_prs6[name]["saving_difference_pp"]
        contains = lambda ci: ci[0] <= 0 <= ci[1]  # noqa: E731
        verdict = ("routing explains the gap" if routing["ci95"][1] < 0 and contains(rest["ci95"])
                   else "routing explains none of it" if contains(routing["ci95"]) and rest["ci95"][0] > 0
                   else "routing explains part of it, or the run cannot tell")
        out[name] = {"tm_stock_ratio": {run: round(r, 4) for run, r in ratio.items()}, "gap_pp": round(gap, 2),
                     "d_routing_pp": routing, "d_rest_pp": rest,
                     "routing_share_of_gap": round(-routing["point"] / gap, 3) if gap else None,
                     "verdict": verdict if audit_clean else "withheld: the audit found problems"}
    return out


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ.get("TEMP", "/tmp")) / "tm-rc"
    facts = copy_from_local(root) if root.is_dir() else json.loads(
        (HERE / "captures_audit.json").read_text(encoding="utf-8"))
    audits = {shard.name: audit(shard, facts) for shard in sorted(HERE.iterdir())
              if shard.is_dir() and (shard / "runs").is_dir()}
    spent = sum(a["nano_total"] for a in audits.values()) / 1e9
    out = {"study": "relay control for the default-routing A/B", "kind": "exploratory",
           "copilot_cli": PACKAGE, "model": MODEL, "bootstrap": {"draws": DRAWS, "seed": SEED}, "audit": audits,
           "ai_credits_spent": round(spent, 2), "ai_credit_cap": CREDIT_CAP, "lane_test": lane_test()}
    if all((HERE / shard / "results.jsonl").is_file() for shard in SHARDS):
        check_protocol()
        tasks = sorted(t for order in SHARDS.values() for t in order)
        relay, default, prs6 = relay_values([HERE / s for s in SHARDS]), default_values(), prs6_values()
        both = paired(relay, tasks)
        clean = all(audits[s]["clean"] for s in SHARDS)
        profiles = {"relay_1.0.104": profile(relay, both), "default_routing_1.0.104": profile(default, both),
                    "prs6_relay_1.0.98": profile(prs6, both)}
        vs_default, vs_prs6 = compare(relay, default, both, SEED + 1), compare(relay, prs6, both, SEED + 2)
        out["django_15_tasks"] = {**analyze_suite(relay, tasks), "audit_clean": clean, "profile": profiles,
                                  "vs_default_routing": vs_default, "vs_prs6_relay": vs_prs6,
                                  "reading": reading(vs_default, vs_prs6, profiles, clean)}
    (HERE / "analysis.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
