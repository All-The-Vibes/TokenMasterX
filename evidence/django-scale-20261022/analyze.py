"""Analysis of the 45-task Django run: confidence intervals, rare vs common names, failures. Exploratory.

Paired bootstrap over tasks (10,000 resamples, fixed seed) of the change in summed raw tokens and cost.

  python analyze.py
"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "token-master-plugin/evals"))
import quick_copilot_ab as q  # noqa: E402

MODELS = {"astra": "gpt-6-astra", "opus": "claude-opus-5.5"}
PAIRS = (("tm", "stock"), ("lean", "stock"), ("tm", "lean"))
DRAWS, SEED = 10_000, 20261022


def rows_for(short: str) -> dict:
    """(task, arm) -> graded row, arm in stock / lean / tm."""
    out = {}
    for variant, rename in (("ab", {"stock": "stock", "tm": "tm"}), ("lean", {"tm": "lean"})):
        for line in (HERE / f"{short}-{variant}" / "results.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["status"] in ("pass", "fail"):
                out[(row["task"], rename[row["arm"]])] = row
    return out


def change(rows: dict, tasks: list, new: str, old: str, model: str) -> dict:
    raw = {t: {arm: rows[(t, arm)]["usage"]["input"] + rows[(t, arm)]["usage"]["output"] for arm in (new, old)}
           for t in tasks}
    usd = {t: {arm: q.usd(rows[(t, arm)]["usage"], model) for arm in (new, old)} for t in tasks}
    rng = random.Random(SEED)
    result = {}
    for name, values in (("raw", raw), ("usd", usd)):
        point = sum(values[t][new] for t in tasks) / sum(values[t][old] for t in tasks) - 1
        draws = []
        for _ in range(DRAWS):
            sample = [rng.choice(tasks) for _ in tasks]
            draws.append(sum(values[t][new] for t in sample) / sum(values[t][old] for t in sample) - 1)
        draws.sort()
        result[name] = {"change": round(point, 4), "ci95": [round(draws[int(0.025 * DRAWS)], 4),
                                                             round(draws[int(0.975 * DRAWS)], 4)]}
    result["tasks_lower_raw"] = f"{sum(raw[t][new] < raw[t][old] for t in tasks)}/{len(tasks)}"
    return result


def main() -> None:
    tasks = json.loads((HERE / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    strata = {"all": [t["id"] for t in tasks],
              "rare names (D01-D10, D16-D30)": [t["id"] for t in tasks if t["stratum"] != "common-name"],
              "common names (D11-D15, D31-D45)": [t["id"] for t in tasks if t["stratum"] == "common-name"]}
    expected = {t["id"]: sorted(t["expected"]["callers"]) for t in tasks}
    out = {"kind": "exploratory, not pre-registered", "bootstrap": {"draws": DRAWS, "seed": SEED}, "models": {}}
    for short, model in MODELS.items():
        rows = rows_for(short)
        entry = {}
        for label, ids in strata.items():
            ids = [t for t in ids if all((t, arm) in rows for arm in ("stock", "lean", "tm"))]
            entry[label] = {"tasks": len(ids),
                            "raw_tokens": {arm: sum(rows[(t, arm)]["usage"]["input"] + rows[(t, arm)]["usage"]["output"]
                                                    for t in ids) for arm in ("stock", "lean", "tm")},
                            "passes": {arm: sum(rows[(t, arm)]["status"] == "pass" for t in ids)
                                       for arm in ("stock", "lean", "tm")},
                            **{f"{new}_vs_{old}": change(rows, ids, new, old, model) for new, old in PAIRS}}
        entry["failures"] = [{"task": t, "arm": arm, "why": row["why"],
                              "missing": sorted(set(expected[t]) - set((row.get("answer") or {}).get("callers") or [])),
                              "extra": sorted(set((row.get("answer") or {}).get("callers") or []) - set(expected[t]))}
                             for (t, arm), row in sorted(rows.items()) if row["status"] == "fail"]
        out["models"][model] = entry
    (HERE / "analysis.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    for model, entry in out["models"].items():
        print("==", model)
        for label, data in entry.items():
            if label == "failures":
                for failure in data:
                    print("  FAIL", failure)
                continue
            print(f"  {label}: {data['tasks']} tasks, raw {data['raw_tokens']}, passes {data['passes']}")
            for pair in (f"{new}_vs_{old}" for new, old in PAIRS):
                d = data[pair]
                print(f"    {pair:13} raw {d['raw']['change']:+.1%} [{d['raw']['ci95'][0]:+.1%}, {d['raw']['ci95'][1]:+.1%}]"
                      f"  cost {d['usd']['change']:+.1%} [{d['usd']['ci95'][0]:+.1%}, {d['usd']['ci95'][1]:+.1%}]"
                      f"  lower on {d['tasks_lower_raw']}")


if __name__ == "__main__":
    main()
