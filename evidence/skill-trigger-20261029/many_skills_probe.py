"""What keeping the `skill` tool costs with a real skill list: the SKILL.md files of the operator's ~/.copilot/skills and
~/.agents/skills (the folders only, no other files) copied into a lane's Copilot home, then the first request of
probe.py's plain prompt with the 13 lean tools excluded, and with `skill` kept. Copilot CLI 1.0.104, closed upstream,
no model call.

  python many_skills_probe.py <output json>
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

import probe as pr


def main() -> None:
    pr.ROOT = pr.dr.LANES_ROOT / "skill-trigger-many"
    pr.p5.CLI_VERSION = f"GitHub Copilot CLI {pr.PACKAGE}."
    pr.p5.COPILOT, pr.p5.base_env, pr.p5.MODEL = str(pr.dr.LAUNCHER), pr.dr.base_env, pr.dr.MODEL
    skills = pr.ROOT / "home" / "copilot" / "skills"
    shutil.rmtree(skills, ignore_errors=True)
    copied = set()
    for source in (Path.home() / ".copilot" / "skills", Path.home() / ".agents" / "skills"):
        for found in sorted(source.rglob("SKILL.md")):
            name = found.parent.name
            if name not in copied and name != "demo-skill":
                (skills / name).mkdir(parents=True)
                shutil.copyfile(found, skills / name / "SKILL.md")
                copied.add(name)
    results = {"lean": pr.capture("many-lean", ["-p", pr.PLAIN], excluded=pr.LEAN),
               "keep-skill": pr.capture("many-keep-skill", ["-p", pr.PLAIN],
                                        excluded=[t for t in pr.LEAN if t != "skill"])}
    lean, kept = (results[k]["requests"][0] for k in ("lean", "keep-skill"))
    listed = kept["available_skills_cl100k_tokens"]
    print(f"{len(copied)} skills copied, {kept['skills_listed']} listed; skill kept adds "
          f"{kept['request_cl100k_tokens'] - lean['request_cl100k_tokens']} tokens ({listed} of them the list)")
    Path(sys.argv[1]).write_text(json.dumps({"probe": "skill tool cost with the operator's skills, Copilot CLI "
                                             + pr.PACKAGE, "skills_copied": len(copied), "results": results},
                                            indent=1) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
