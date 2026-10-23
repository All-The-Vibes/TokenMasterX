"""Combine the four Django runs (2 models x {ab, lean}) into one summary. Exploratory, not pre-registered.

Arms: stock = Copilot CLI as shipped; lean = TokenMaster without graphify (bridge + lean tool set);
tm = full TokenMaster (lean + graphify navigation tools). tm vs lean isolates graphify.
Tool-output shares count every re-send: an output in a request's history is counted once per request.

  python summarize.py <runs folder holding astra-ab, astra-lean, opus-ab, opus-lean>
"""
from collections import defaultdict
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALS = HERE.parents[1] / "token-master-plugin/evals"
sys.path.insert(0, str(EVALS))
import quick_copilot_ab as q  # noqa: E402
import run_prs1_study as p1  # noqa: E402
import run_prs5_study as p5  # noqa: E402
from brainspace import tokens  # noqa: E402

MODELS = {"astra": "gpt-6-astra", "opus": "claude-opus-5.5"}


def kind(name: str, args: dict) -> str:
    if name.startswith("tokenmaster-nav"):
        return "graph/nav tools"
    if name in ("rg", "grep"):
        return "grep (rg tool)"
    if name == "powershell":
        command = str(args.get("command", ""))
        if re.search(r"Select-String|findstr|\brg\b|\bgrep\b", command, re.I):
            return "grep (PowerShell)"
        if re.search(r"Get-Content|\bcat\b|\btype\b", command, re.I):
            return "file read (PowerShell)"
        return "other shell"
    return {"view": "file read (view)", "glob": "file list"}.get(name, "other")


def output_tokens_by_kind(run_dir: Path, cache: dict) -> dict:
    shares = defaultdict(int)
    for capture in p5.read_jsonl(run_dir / "captures.jsonl"):
        request = json.loads(capture["input"])
        calls, outputs = {}, []
        for item in request.get("input") or []:  # Responses API
            if isinstance(item, dict) and item.get("type") == "function_call":
                try:
                    calls[item["call_id"]] = (item["name"], json.loads(item.get("arguments") or "{}"))
                except ValueError:
                    calls[item["call_id"]] = (item["name"], {})
            elif isinstance(item, dict) and item.get("type") == "function_call_output":
                outputs.append((item.get("call_id"), item.get("output")))
        for message in request.get("messages") or []:  # Anthropic Messages
            if isinstance(message, dict) and isinstance(message.get("content"), list):
                for block in message["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        calls[block["id"]] = (block["name"], block.get("input") or {})
                    elif isinstance(block, dict) and block.get("type") == "tool_result":
                        outputs.append((block.get("tool_use_id"), block.get("content")))
        for call_id, output in outputs:
            text = output if isinstance(output, str) else json.dumps(output)
            if text not in cache:
                cache[text] = tokens.count_tokens(text)
            name, args = calls.get(call_id, ("?", {}))
            shares[kind(name, args if isinstance(args, dict) else {})] += cache[text]
    return dict(shares)


def change(new: float, old: float):
    return round(new / old - 1, 4) if old else None


def main(runs: Path) -> None:
    summary, cache = {"kind": "exploratory, not pre-registered", "tasks": "tasks.json", "models": {}}, {}
    for short, model in MODELS.items():
        rows = {}  # (task, arm) -> row
        for variant, arms in (("ab", {"stock": "stock", "tm": "tm"}), ("lean", {"tm": "lean"})):
            out = runs / f"{short}-{variant}"
            target = HERE / f"{short}-{variant}"
            target.mkdir(exist_ok=True)
            for name in ("results.jsonl", "setup.json", "warmup.json"):
                if (out / name).exists():
                    shutil.copy2(out / name, target / name)
            chosen = p1.final_rows([r for r in p5.read_jsonl(out / "results.jsonl") if r.get("usage")])
            for (task, arm, _), row in chosen.items():
                row["run_dir"] = out / "runs" / row["session"]
                rows[(task, arms[arm])] = row
        arms = {}
        for arm in ("stock", "lean", "tm"):
            mine = [r for (t, a), r in rows.items() if a == arm and r["status"] in ("pass", "fail")]
            nav = [sum(v for k, v in q.tool_calls(r["run_dir"]).items() if k.startswith("tokenmaster-nav"))
                   for r in mine]
            shares = defaultdict(int)
            for r in mine:
                for k, v in output_tokens_by_kind(r["run_dir"], cache).items():
                    shares[k] += v
            raw = sum(r["usage"]["input"] + r["usage"]["output"] for r in mine)
            arms[arm] = {"sessions": len(mine), "passes": sum(r["status"] == "pass" for r in mine),
                         "raw_tokens": raw, "usd": round(sum(q.usd(r["usage"], model) for r in mine), 4),
                         "calls": sum(r["usage"]["calls"] for r in mine), "nav_calls": sum(nav),
                         "sessions_using_nav": sum(n > 0 for n in nav),
                         "tool_output_tokens_incl_resends": dict(sorted(shares.items(), key=lambda kv: -kv[1])),
                         "infra": sum(r["status"] == "infra" for (t, a), r in rows.items() if a == arm)}
        per_task = []
        for task in sorted({t for t, _ in rows}):
            entry = {"task": task}
            for arm in ("stock", "lean", "tm"):
                r = rows.get((task, arm))
                if r and r["status"] in ("pass", "fail"):
                    entry[arm] = {"raw": r["usage"]["input"] + r["usage"]["output"], "pass": r["status"] == "pass",
                                  "calls": r["usage"]["calls"], "why": r["why"]}
            per_task.append(entry)
        both = [e for e in per_task if "tm" in e and "lean" in e]
        summary["models"][model] = {
            "arms": arms, "per_task": per_task,
            "graphify_effect_tm_vs_lean": {"raw": change(arms["tm"]["raw_tokens"], arms["lean"]["raw_tokens"]),
                                           "usd": change(arms["tm"]["usd"], arms["lean"]["usd"]),
                                           "tasks_tm_lower_raw": sum(e["tm"]["raw"] < e["lean"]["raw"] for e in both),
                                           "tasks_compared": len(both)},
            "tm_vs_stock": {"raw": change(arms["tm"]["raw_tokens"], arms["stock"]["raw_tokens"]),
                            "usd": change(arms["tm"]["usd"], arms["stock"]["usd"])},
            "lean_vs_stock": {"raw": change(arms["lean"]["raw_tokens"], arms["stock"]["raw_tokens"]),
                              "usd": change(arms["lean"]["usd"], arms["stock"]["usd"])}}
    (HERE / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    for model, data in summary["models"].items():
        print(f"== {model}")
        for arm, a in data["arms"].items():
            print(f"  {arm:6} pass {a['passes']}/{a['sessions']} raw {a['raw_tokens']:>10,} usd {a['usd']:>8.4f} "
                  f"calls {a['calls']:>4} nav {a['nav_calls']:>3} ({a['sessions_using_nav']} sessions) infra {a['infra']}")
        print("  graphify (tm vs lean):", data["graphify_effect_tm_vs_lean"])
        print("  tm vs stock:", data["tm_vs_stock"], " lean vs stock:", data["lean_vs_stock"])


if __name__ == "__main__":
    main(Path(sys.argv[1]))
