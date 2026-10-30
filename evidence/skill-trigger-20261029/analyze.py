"""Read captures.json (probe.py) and print what the change relies on: what each built-in command's first request
asks for, each tool family's cost and per-tool weight, and where Copilot CLI put demo-skill's text.

  python analyze.py captures.json
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "token-master-plugin/skills/token-master"))
import brainspace_copilot_bridge as bridge  # noqa: E402

AGENT_WORDS = re.compile(r"\btask\b|agent_type|subagent|code-review|rubber-duck|security-review|\bresearch\b", re.I)


def first(entry: dict) -> dict:
    return entry["requests"][0] if entry["requests"] else {}


def main() -> None:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print("version:", data["version"], "model:", data["model"])
    print("\nA. built-in commands (first request)")
    for name, entry in data["results"]["A"].items():
        request = first(entry)
        tools = sorted(request.get("tool_cl100k_tokens") or {})
        print(f"  {name:28} captured {entry['captured']}  tokens {request.get('request_cl100k_tokens')}  "
              f"tools {tools}")
        print(f"      system: {request.get('system_head', '')[:150]!r}")
        print(f"      user:   {request.get('last_user_text', '')[:600]!r}")
        print(f"      mentions: {sorted({m.lower() for m in AGENT_WORDS.findall(request.get('last_user_text', ''))})}")
    b = data["results"]["B"]
    lean = first(b["lean"])["request_cl100k_tokens"]
    stock = first(b["stock"])["request_cl100k_tokens"]
    print(f"\nB. per-family cost over the lean request ({lean} tokens; stock {stock}, lean saves {stock - lean})")
    weights, total = {}, 0
    for family, (tools, _) in bridge.CAPABILITY_GROUPS.items():
        request = first(b[f"keep-{family}"])
        cost = request["request_cl100k_tokens"] - lean
        definitions = {t: request["tool_cl100k_tokens"].get(t, 0) for t in tools}
        sent = sum(definitions.values())
        total += cost
        print(f"  {family:18} +{cost:5}  definitions {definitions}  system +"
              f"{request['system_cl100k_tokens'] - first(b['lean'])['system_cl100k_tokens']}  "
              f"available_skills {request['available_skills_cl100k_tokens']}")
        for tool, size in definitions.items():  # the family's cost, split by definition size
            weights[tool] = round(cost * size / sent) if sent else round(cost / len(tools))
    print(f"  sum of family costs {total} vs stock - lean {stock - lean}")
    print("  per-tool weights:", json.dumps(weights))
    print("\nC. slash expansion: where demo-skill's text appeared in the first request")
    for name, entry in data["results"]["C"].items():
        request = first(entry)
        print(f"  {name:14} captured {entry['captured']}  marker in {request.get('marker_in')}  "
              f"tools has skill: {'skill' in (request.get('tool_cl100k_tokens') or {})}  "
              f"user: {request.get('last_user_text', '')[:160]!r}")


if __name__ == "__main__":
    main()
