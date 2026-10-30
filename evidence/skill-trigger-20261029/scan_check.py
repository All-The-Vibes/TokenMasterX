"""Does the launcher read the skills that Copilot CLI 1.0.104 loads? In each folder, compare `_installed_names("skills")`
with `copilot skill list --json` (no model call). A Copilot CLI skill counts as covered when the scan holds its name, or
for a plugin skill ("plugin:skill") the part after the colon. Extra names in the scan are harmless: they count only
after a slash or a verb in a prompt.

Folders: this repository; a git repository under the profile, run from a subfolder, with skills and a .claude/commands
file at its root and a skill above it; a folder under the profile outside any repository; a folder outside the profile
and outside any repository; this repository with COPILOT_HOME set to an empty folder; and this repository with a
Copilot home whose settings.json lists a `copilot skill add` folder, plus COPILOT_SKILLS_DIRS naming two folders. Each
row also records how long the scan took.

  python scan_check.py <output json>
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SKILL = REPO / "token-master-plugin/skills/token-master"
CHILD = ("import json, sys, time; sys.path.insert(0, sys.argv[1]); import brainspace_copilot_bridge as b; "
         "t = time.perf_counter(); names = b._installed_names('skills'); "
         "print(json.dumps({'names': sorted(names), 'seconds': round(time.perf_counter() - t, 3)}))")


def make_skill(root: Path, *parts: str) -> None:
    folder = root.joinpath(*parts)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(f"---\nname: {parts[-1]}\ndescription: Scan check skill {parts[-1]}.\n---\nbody\n",
                                     encoding="utf-8")


def compare(folder: Path, env: dict) -> dict:
    listed = json.loads(subprocess.run(["copilot", "skill", "list", "--json"], cwd=folder, env=env, capture_output=True,
                                       text=True, encoding="utf-8", timeout=180).stdout)
    scan = json.loads(subprocess.run([sys.executable, "-c", CHILD, str(SKILL)], cwd=folder, env=env,
                                     capture_output=True, text=True, timeout=180).stdout)
    scanned = set(scan["names"])
    names = {entry["name"].lower() for entry in listed}
    missed = sorted(n for n in names if n not in scanned and n.rsplit(":", 1)[-1] not in scanned)
    return {"folder": str(folder), "copilot_listed": len(names), "scanned": len(scanned), "missed": missed,
            "extra": len(scanned - names - {n.rsplit(":", 1)[-1] for n in names}),
            "scan_seconds": scan["seconds"], "sources": sorted({entry["source"] for entry in listed})}


def main() -> None:
    profile = Path(os.environ["USERPROFILE"])
    under = Path(tempfile.mkdtemp(prefix="tm-scan-", dir=profile / "AppData" / "Local" / "Temp"))
    outside = Path(tempfile.mkdtemp(prefix="tm-scan-", dir="C:\\tm-lanes"))  # outside the profile, not a repository
    try:
        make_skill(under, ".github", "skills", "scan-above-repo")
        make_skill(under, "repo", ".agents", "skills", "scan-repo-root")
        make_skill(under, "repo", ".claude", "skills", "group", "scan-nested")
        (under / "repo" / ".claude" / "commands").mkdir(parents=True)
        (under / "repo" / ".claude" / "commands" / "scan-command.md").write_text(
            "---\ndescription: Scan check command.\n---\nDo it.\n", encoding="utf-8")
        (under / "repo" / "sub").mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=under / "repo", check=True)
        make_skill(under, "nogit", ".github", "skills", "scan-no-repo")
        (under / "nogit" / "sub").mkdir(parents=True)
        make_skill(outside, ".github", "skills", "scan-outside-profile")
        (outside / "sub").mkdir()
        env = {k: v for k, v in os.environ.items() if k not in ("COPILOT_HOME", "COPILOT_SKILLS_DIRS")}
        empty_home = outside / "empty-copilot-home"
        empty_home.mkdir()
        custom_home = outside / "custom-copilot-home"  # `copilot skill add` folders and COPILOT_SKILLS_DIRS
        make_skill(outside, "added", "scan-skill-add")
        make_skill(outside, "env-a", "scan-env-a")
        make_skill(outside, "env-b", "scan-env-b")
        custom_home.mkdir()
        (custom_home / "settings.json").write_text(json.dumps({"skillDirectories": [str(outside / "added")]}),
                                                   encoding="utf-8")
        custom_env = {**env, "COPILOT_HOME": str(custom_home),
                      "COPILOT_SKILLS_DIRS": f"{outside / 'env-a'},{outside / 'env-b'}"}
        results = {"this repository": compare(REPO, env),
                   "git repository under the profile": compare(under / "repo" / "sub", env),
                   "no repository, under the profile": compare(under / "nogit" / "sub", env),
                   "no repository, outside the profile": compare(outside / "sub", env),
                   "this repository, COPILOT_HOME set": compare(REPO, {**env, "COPILOT_HOME": str(empty_home)}),
                   "skill add folder and COPILOT_SKILLS_DIRS": compare(REPO, custom_env)}
    finally:
        shutil.rmtree(under, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)
    version = subprocess.run(["copilot", "--version"], capture_output=True, text=True).stdout.strip().splitlines()[0]
    Path(sys.argv[1]).write_text(json.dumps({"check": "launcher skill scan vs copilot skill list --json",
                                             "version": version, "results": results}, indent=1) + "\n",
                                 encoding="utf-8", newline="\n")
    for name, row in results.items():
        print(f"{name:42} listed {row['copilot_listed']:3}  scanned {row['scanned']:3}  extra {row['extra']:3}  "
              f"{row['scan_seconds']:5.2f} s  missed {row['missed']}")


if __name__ == "__main__":
    main()
