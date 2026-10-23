"""Does the /tokenomics savings estimate hold up? Exploratory check against measured A/B results.

tokenomics.py estimates what TokenMaster sessions would have cost without TokenMaster. Here its estimate() runs on the
TokenMaster sessions of the real-CLI A/B runs, and the result is compared with the stock sessions that actually ran on
the same tasks at the same time. Each session is rebuilt from its results row: the first call exactly, the rest of
its usage as one more call, plus empty calls up to its real call count (the estimate counts calls, not their sizes).
The A/B runs used Copilot CLI 1.0.78-3, so the check uses the 1.0.78-3 calibration.

  python validate.py
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
sys.path.insert(0, str(HERE.parents[1] / "token-master-plugin/skills/token-master"))
import tokenomics  # noqa: E402

CALIBRATION = tokenomics.CALIBRATIONS["1.0.78-3"]
PRICES = {"gpt-6-astra": ("/responses", 10.0, 1.0, 12.5, 50.0),  # USD per 1M: new input, cache read, write, output
          "claude-opus-5.5": ("/v1/messages", 4.0, 0.2, 5.0, 20.0)}
NANO_PER_TOKEN = 1e5  # per USD-per-1M


def rows(folders, arm):
    out = []
    for folder in folders:
        for line in (EVIDENCE / folder / "results.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["arm"] == arm and row["status"] in ("pass", "fail"):
                out.append(row)
    return out


def usd(model, usage):
    _, new, read, write, out = PRICES[model]
    return ((usage["input"] - usage["cached"] - usage["cache_write"]) * new + usage["cached"] * read
            + usage["cache_write"] * write + usage["output"] * out) / 1e6


def rebuilt_calls(model, row):
    endpoint, new, read, write, out = PRICES[model]
    prices = {"input": new * NANO_PER_TOKEN, "cache_read": read * NANO_PER_TOKEN,
              "cache_write": write * NANO_PER_TOKEN, "output": out * NANO_PER_TOKEN}
    usage, first = row["usage"], row["first_call"]
    rest = {key: usage[key] - (first.get(key) or 0) for key in ("input", "cached", "cache_write", "output")}
    parts = [{key: first.get(key) or 0 for key in rest}, rest] + [dict.fromkeys(rest, 0)] * max(0, usage["calls"] - 2)
    start = tokenomics.parse_time(row["started_utc"])
    calls = []
    for index, part in enumerate(parts[:max(usage["calls"], 1)]):
        nano = usd(model, part) * 1e11
        calls.append({"session": row["session"], "at": start + timedelta(seconds=index), "model": model,
                      "api": tokenomics.api_of(endpoint), "input": part["input"], "output": part["output"],
                      "cache_read": part["cached"], "cache_write": part["cache_write"], "nano": nano,
                      "prices": prices, "main": True})
    return calls


def check(label, model, stock_rows, tm_rows, nav):
    calls = [call for row in tm_rows for call in rebuilt_calls(model, row)]
    sessions = {row["session"]: {"cwd": "/benchmark", "repository": "", "created": None} for row in tm_rows}
    start = min(call["at"] for call in calls) - timedelta(minutes=1)
    launches = [{"id": "benchmark", "start": start, "end": start + timedelta(days=1), "cwd": tokenomics.norm("/benchmark"),
                 "lean": True, "bridge": True, "nav": nav}]
    tokenomics.estimate(calls, sessions, launches, CALIBRATION)
    actual_tokens = sum(r["usage"]["input"] + r["usage"]["output"] for r in tm_rows)
    actual_usd = sum(usd(model, r["usage"]) for r in tm_rows)
    saved_tokens = sum(call["saved_tokens"] for call in calls)
    saved_usd = sum(call["saved_nano"] for call in calls) / 1e11
    stock_tokens = sum(r["usage"]["input"] + r["usage"]["output"] for r in stock_rows)
    stock_usd = sum(usd(model, r["usage"]) for r in stock_rows)
    result = {"comparison": label, "model": model, "sessions": len(tm_rows),
              "tokens": {"tokenmaster": actual_tokens, "estimated_without": actual_tokens + saved_tokens,
                         "measured_stock": stock_tokens,
                         "estimated_saving_pct": round(100 * saved_tokens / (actual_tokens + saved_tokens), 1),
                         "measured_saving_pct": round(100 * (1 - actual_tokens / stock_tokens), 1)},
              "usd": {"tokenmaster": round(actual_usd, 4), "estimated_without": round(actual_usd + saved_usd, 4),
                      "measured_stock": round(stock_usd, 4),
                      "estimated_saving_pct": round(100 * saved_usd / (actual_usd + saved_usd), 1),
                      "measured_saving_pct": round(100 * (1 - actual_usd / stock_usd), 1)}}
    for key in ("tokens", "usd"):
        part = result[key]
        part["share_of_measured_saving_pct"] = round(100 * (part["estimated_without"] - part["tokenmaster"])
                                                     / (part["measured_stock"] - part["tokenmaster"]), 1)
    return result


def main() -> None:
    results = []
    for short, model in (("astra", "gpt-6-astra"), ("opus", "claude-opus-5.5")):
        ab, lean = [f"django-scale-20261022/{short}-ab"], [f"django-scale-20261022/{short}-lean"]
        repo = [f"copilot-lean-{short}-{part}-20261019" for part in ("a", "b")]
        results.append(check("Django, 45 tasks, full TokenMaster", model, rows(ab, "stock"), rows(ab, "tm"), True))
        results.append(check("Django, 45 tasks, TokenMaster without graphify", model, rows(ab, "stock"),
                             rows(lean, "tm"), False))
        results.append(check("This repository, 27 tasks, full TokenMaster", model, rows(repo, "stock"),
                             rows(repo, "tm"), True))
    (HERE / "results.json").write_text(json.dumps({"kind": "exploratory", "cli_version": "1.0.78-3",
                                                   "calibration": CALIBRATION, "results": results}, indent=1) + "\n",
                                      encoding="utf-8")
    for r in results:
        t, u = r["tokens"], r["usd"]
        print(f"{r['model']:16} {r['comparison']:47} tokens: estimated -{t['estimated_saving_pct']}% vs measured "
              f"-{t['measured_saving_pct']}% ({t['share_of_measured_saving_pct']}% of it) | cost: estimated "
              f"-{u['estimated_saving_pct']}% vs measured -{u['measured_saving_pct']}% "
              f"({u['share_of_measured_saving_pct']}% of it)")


if __name__ == "__main__":
    main()
