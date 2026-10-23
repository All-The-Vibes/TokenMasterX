"""Independent recount of the 45-task Django run from the relay's raw per-call records. Exploratory.

Reads only runs/<session>/calls.jsonl (one row per API call: GitHub's usage counts and GitHub's own copilot_usage
bill) and, where present, captures.jsonl (the raw response tail, for copilot_usage.total_nano_aiu; kept local
because it holds Copilot's prompt). Shares no code with summarize.py or analyze.py, so a bug there would show up
as a mismatch here. The committed calls.jsonl files let anyone recount tokens and GitHub's bill:

  python audit.py <runs folder holding astra-ab, astra-lean, opus-ab, opus-lean> [<audit.json to write>]
  python audit.py evidence/django-scale-20261022
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
INPUT_USD_PER_M = {"astra": 10.00, "opus": 4.00}  # GitHub's price per 1M uncached input tokens; the bill is in these units
NANO_AIU = re.compile(r'"total_nano_aiu"\s*:\s*(\d+)')


def main(runs: Path, out_path: Path | None = None) -> None:
    out = {"kind": "exploratory, not pre-registered", "models": {}}
    for model in ("astra", "opus"):
        arms = defaultdict(lambda: {"sessions": 0, "calls": 0, "non_200": 0, "raw_tokens": 0, "bill_units": 0.0,
                                    "calls_without_bill": 0, "nano_aiu": 0, "calls_with_nano_aiu": 0})
        for variant in ("ab", "lean"):
            for session in sorted((runs / f"{model}-{variant}" / "runs").iterdir()):
                arm = "lean" if variant == "lean" else session.name.split("-")[1]
                totals = arms[arm]
                totals["sessions"] += 1
                for line in (session / "calls.jsonl").read_text(encoding="utf-8").splitlines():
                    call = json.loads(line)
                    totals["calls"] += 1
                    if call["status"] != 200:
                        totals["non_200"] += 1
                        continue
                    totals["raw_tokens"] += call["usage"]["input"] + call["usage"]["output"]
                    if call.get("bill"):
                        totals["bill_units"] += call["bill"]["units"]
                    else:
                        totals["calls_without_bill"] += 1
                capture_file = session / "captures.jsonl"  # local only: it holds Copilot's prompt
                for line in capture_file.read_text(encoding="utf-8").splitlines() if capture_file.exists() else []:
                    capture = json.loads(line)
                    found = NANO_AIU.findall(capture.get("output_tail") or "")
                    if capture.get("status") == 200 and found:
                        totals["nano_aiu"] += int(found[-1])
                        totals["calls_with_nano_aiu"] += 1
        for totals in arms.values():
            totals["github_bill_usd"] = round(totals["bill_units"] * INPUT_USD_PER_M[model] / 1e6, 4)
            totals["github_ai_credits"] = round(totals["nano_aiu"] / 1e9, 2)
        out["models"][model] = dict(arms)
    if out_path:
        out_path.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    for model, arms in out["models"].items():
        for arm, t in sorted(arms.items()):
            print(f"{model:5} {arm:5} sessions {t['sessions']:2} calls {t['calls']:3} (non-200: {t['non_200']}) "
                  f"raw {t['raw_tokens']:>10,} | GitHub bill ${t['github_bill_usd']:.2f} "
                  f"(calls without a bill: {t['calls_without_bill']}) | total_nano_aiu {t['github_ai_credits']:,} credits "
                  f"on {t['calls_with_nano_aiu']} calls")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
