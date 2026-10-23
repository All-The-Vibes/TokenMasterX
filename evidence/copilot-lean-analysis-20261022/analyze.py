"""Analysis of the 27-task run on this repository (October 19, 2026; evidence/copilot-lean-*-20261019). Exploratory.

Same method as ../django-scale-20261022/analyze.py: paired bootstrap over tasks (10,000 resamples, seed 20261022)
of the change in summed raw tokens and cost, and a cost sensitivity that re-prices every session as if its first
call found no cached prompt from an earlier session. The 27 tasks ran in two halves (a and b) at the same time.

  python analyze.py
"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
sys.path.insert(0, str(HERE.parents[1] / "token-master-plugin/evals"))
import quick_copilot_ab as q  # noqa: E402

MODELS = {"astra": "gpt-6-astra", "opus": "claude-opus-5.5"}
DRAWS, SEED = 10_000, 20261022


def cold_usage(row: dict) -> dict:
    moved = row["first_call"].get("cached") or 0
    return dict(row["usage"], cached=row["usage"]["cached"] - moved, cache_write=row["usage"]["cache_write"] + moved)


def main() -> None:
    out = {"kind": "exploratory, not pre-registered", "bootstrap": {"draws": DRAWS, "seed": SEED}, "models": {}}
    for short, model in MODELS.items():
        rows, starts = {}, []
        for part in ("a", "b"):
            folder = EVIDENCE / f"copilot-lean-{short}-{part}-20261019"
            for line in (folder / "results.jsonl").read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if row["status"] in ("pass", "fail"):
                    rows[(row["task"], row["arm"])] = row
                    starts.append(row["started_utc"])
        tasks = sorted({t for t, _ in rows})
        values = {"raw": lambda r: r["usage"]["input"] + r["usage"]["output"],
                  "usd": lambda r: q.usd(r["usage"], model),
                  "usd_if_every_first_call_cold": lambda r: q.usd(cold_usage(r), model)}
        rng = random.Random(SEED)
        entry = {"tasks": len(tasks), "sessions_started_utc": [min(starts), max(starts)],
                 "passes": {arm: sum(rows[(t, arm)]["status"] == "pass" for t in tasks) for arm in ("stock", "tm")},
                 "warm_first_calls": {arm: sum((rows[(t, arm)]["first_call"].get("cached") or 0)
                                               >= 0.5 * (rows[(t, arm)]["first_call"].get("input") or 1) for t in tasks)
                                      for arm in ("stock", "tm")}}
        for name, value in values.items():
            per = {t: {arm: value(rows[(t, arm)]) for arm in ("stock", "tm")} for t in tasks}
            totals = {arm: round(sum(per[t][arm] for t in tasks), 4) for arm in ("stock", "tm")}
            draws = []
            for _ in range(DRAWS):
                sample = [rng.choice(tasks) for _ in tasks]
                draws.append(sum(per[t]["tm"] for t in sample) / sum(per[t]["stock"] for t in sample) - 1)
            draws.sort()
            entry[name] = {**totals, "change": round(totals["tm"] / totals["stock"] - 1, 4),
                           "ci95": [round(draws[int(0.025 * DRAWS)], 4), round(draws[int(0.975 * DRAWS)], 4)]}
        out["models"][model] = entry
        print(model, json.dumps(entry))
    (HERE / "analysis.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
