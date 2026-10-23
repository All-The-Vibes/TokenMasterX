"""Exploratory A/B (not pre-registered): "who calls X?" questions on Django 5.2, real Copilot CLI (1.0.78-3 in the
October 2026 runs; run_prs5_study.cli_version checks the version that the sessions run).

Variant "ab": stock Copilot vs the full TokenMaster install (lean tool set, bridge and graphify navigation tools).
Variant "lean": TokenMaster without graphify (brainspace_setup.py only: lean tool set and bridge, no navigation
tools). Run both variants at the same time; "tm" vs "lean" isolates graphify. The repository is `git archive HEAD`
of a Django checkout, the same files make_tasks.py builds its answer key from. Machinery: quick_copilot_ab.py and
run_prs5_study.py (lanes, relay, isolation, grading).

  python django_ab.py --repo <django checkout> --tasks-file <tasks.json> --output <new folder> --variant ab|lean
                      --lanes <name> [--model claude-opus-5.5]
  python django_ab.py --self-test
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time

EVALS = Path(__file__).resolve().parent
sys.path.insert(0, str(EVALS))
import quick_copilot_ab as q  # noqa: E402
import run_prs1_study as p1  # noqa: E402
import run_prs5_study as p5  # noqa: E402

TEMPLATE_MANIFESTS: dict[str, dict] = {}


def reset_lane(lane: Path, template: Path) -> None:
    """Make the lane identical to its template, copying only what differs (robocopy /MIR).

    Same result as run_prs5_study.reset_lane (delete, then copy everything), which took minutes per session on the
    289 MB TokenMaster workspace."""
    for attempt in range(6):  # Windows: a process that is still exiting can hold a file for a moment
        proc = subprocess.run(["robocopy", str(template), str(lane), "/MIR", "/MT:16", "/R:2", "/W:1", "/NFL", "/NDL",
                               "/NJH", "/NJS", "/NP"], capture_output=True, text=True, errors="replace")
        if proc.returncode < 8:  # robocopy: 0-7 success, 8+ failure
            return
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"lane reset failed: {lane}: {proc.stdout[-500:]}")


def changed_files(lane: Path, template: Path) -> list[str]:
    """run_prs5_study.changed_files, hashing each read-only template once per run instead of once per session."""
    if str(template) not in TEMPLATE_MANIFESTS:
        TEMPLATE_MANIFESTS[str(template)] = p1.manifest(template)
    before, after = TEMPLATE_MANIFESTS[str(template)], p1.manifest(lane)
    changed = sorted(k for k in before.keys() & after.keys() if before[k] != after[k])
    changed += sorted(set(after) - set(before)) + sorted(set(before) - set(after))
    return [c for c in changed if not c.startswith(p5.IGNORED)]


def self_test() -> None:
    """reset_lane restores an edited lane; changed_files reports edits and additions."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        template, lane = Path(tmp) / "template", Path(tmp) / "lane"
        (template / "pkg").mkdir(parents=True)
        (template / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
        reset_lane(lane, template)
        assert changed_files(lane, template) == []
        (lane / "pkg" / "a.py").write_text("x = 2\n", encoding="utf-8")
        (lane / "new.txt").write_text("extra\n", encoding="utf-8")
        assert changed_files(lane, template) == ["pkg/a.py", "new.txt"], changed_files(lane, template)
        reset_lane(lane, template)
        assert changed_files(lane, template) == [] and not (lane / "new.txt").exists()
    print("self-test passed")


def install_lean(home: Path) -> dict:
    """TokenMaster without graphify: only brainspace_setup.py (bridge, lean tool set, output hook)."""
    argv = [sys.executable, "-B", str(p1.SKILL / "brainspace_setup.py"), "--host", "copilot", "--python",
            sys.executable, "--tokenizer-file", str(p5.TOKENIZER)]
    proc = subprocess.run(argv, cwd=p1.SKILL, env=p5.base_env(home), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=900, stdin=subprocess.DEVNULL)
    receipt = {"brainspace_setup.py": {"exit": proc.returncode, "tail": (proc.stdout + proc.stderr)[-1500:]}}
    if proc.returncode:
        raise SystemExit(f"brainspace_setup.py failed: {receipt}")
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--tasks-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variant", choices=("ab", "lean"), required=True)
    parser.add_argument("--lanes", required=True)
    parser.add_argument("--model", default="gpt-6-astra", choices=sorted(q.USD_PER_M))
    args = parser.parse_args(argv)
    out = args.output.resolve()
    if out.exists():
        raise SystemExit(f"output must be new: {out}")
    q.configure(args.model, args.lanes)
    p5.reset_lane, p5.changed_files = reset_lane, changed_files
    if args.variant == "lean":
        p5.ARMS = ("tm",)  # one arm: the bridge-wrapped TokenMaster lane, installed without graphify
    if p5.LANES.exists():
        p1.remove_tree(p5.LANES)
    out.mkdir(parents=True)
    tar = out / "snapshot.tar"
    subprocess.run([str(p1.GIT_EXE), "archive", "--format=tar", "-o", str(tar), "HEAD"], cwd=args.repo, check=True)
    if "stock" in p5.ARMS:
        p5.git_snapshot(out / "templates" / "stock", tar)
    versions = {arm: p5.cli_version(p5.lane_root(arm) / "home") for arm in p5.ARMS}
    if set(versions.values()) != {p5.CLI_VERSION}:
        raise SystemExit(f"Copilot CLI version must be {p5.CLI_VERSION!r}: {versions}")
    tm_repo, home = p5.lane_root("tm") / "tokenmaster", p5.lane_root("tm") / "home"
    p5.git_snapshot(tm_repo, tar)
    install = p5.install_tm(home, tm_repo) if args.variant == "ab" else install_lean(home)
    shutil.copytree(tm_repo, out / "templates" / "tm")
    tasks = json.loads(args.tasks_file.read_text(encoding="utf-8"))["tasks"]
    order = [task["id"] for task in tasks]
    random.Random(q.SEED).shuffle(order)
    jobs = [[1, task_id] for task_id in order]
    p5.write_json(out / "setup.json", {"model": args.model, "variant": args.variant, "arms": list(p5.ARMS),
                                       "versions": versions, "install": install, "jobs": jobs,
                                       "lanes": str(p5.LANES)})
    from brainspace import tokens
    tokens.count_tokens("warm-up")  # before worker threads (lazy init is not thread-safe)
    p5.execute(out, {"tasks": tasks}, jobs, out / "results.jsonl")
    if args.variant == "ab":
        print(json.dumps(q.summarize(out, args.model), indent=1))
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        raise SystemExit(self_test())
    raise SystemExit(main())
