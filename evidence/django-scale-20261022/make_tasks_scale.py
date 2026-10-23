"""Scale-up task set for the Django "who calls X?" A/B: the 15 frozen tasks plus 30 new ones.
Exploratory, not pre-registered.

New tasks come from the same pools and AST answer keys as the frozen ones:
  D16-D30: 15 rare-name tasks, sampled (seed 20261023) from ../django-impact-20261019's pool, D01-D10 removed;
  D31-D45: the 15 common-name tasks in the top 20 of ../django-common-20261022's pool (ranked by repository-wide
           `rg -n -w <name>` output) that D11-D15 did not take, so D11-D15 plus D31-D45 are that whole top 20.
Sized so stock Copilot spends at least 2 million raw tokens per model: earlier Django sessions averaged about
51K raw tokens per task on gpt-6-astra and 72K on claude-opus-5.5.

  python make_tasks_scale.py <django git checkout>
"""
import importlib.util
import json
import random
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
FROZEN = ("django-impact-20261019", "django-common-20261022")
SEED = 20261023
RARE_NEW, COMMON_TOP = 15, 20


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prompt(path: str, qual: str) -> str:
    """The frozen tasks' wording (make_tasks.py; make_tasks_common.py is its function branch)."""
    what = f"the method `{qual}`" if "." in qual else f"the function `{qual}()`"
    return (f"We're about to change the signature of {what} in {path}. Which non-test functions or methods call it "
            "directly? Only files under the top-level `tests/` directory count as test code. Reply with ONLY a JSON "
            "object with exactly 1 key: \"callers\" (list of strings, each \"<path relative to the repository "
            "root>::<Class.method or function>\"). List order does not matter.")


def main(checkout: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pools = {}
        for folder, script, key in ((FROZEN[0], "make_tasks.py", "rare"), (FROZEN[1], "make_tasks_common.py", "common")):
            # Re-runs the generator (its own tasks.json comes out unchanged) and keeps its whole pool.
            load(EVIDENCE / folder / script, key).main(checkout, Path(tmp) / f"{key}.json")
            pools[key] = json.loads((Path(tmp) / f"{key}.json").read_text(encoding="utf-8"))
    frozen = [task for folder in FROZEN
              for task in json.loads((EVIDENCE / folder / "tasks.json").read_text(encoding="utf-8"))["tasks"]]
    for task in frozen:  # the frozen prompts must match the wording used for the new tasks
        assert task["prompt"] == prompt(*task["symbol"].split("::")), task["id"]
    used = {task["symbol"] for task in frozen}
    rare = random.Random(SEED).sample([row for row in pools["rare"] if row["symbol"] not in used], RARE_NEW)
    common = [row for row in pools["common"][:COMMON_TOP] if row["symbol"] not in used]
    assert len(common) == COMMON_TOP - 5, len(common)
    tasks = list(frozen)
    for number, (row, stratum) in enumerate([(row, "rare-name") for row in rare]
                                            + [(row, "common-name") for row in common], len(frozen) + 1):
        path, qual = row["symbol"].split("::")
        tasks.append({"id": f"D{number:02d}", "category": "investigate", "stratum": stratum, "symbol": row["symbol"],
                      "grep_tokens": row["grep_tokens"], "prompt": prompt(path, qual),
                      "expected": {"callers": row["callers"]}, "unordered_list_keys": ["callers"]})
    result = {"kind": "exploratory, not pre-registered", "seed": SEED, "frozen_from": list(FROZEN),
              "pool_sizes": {key: len(rows) for key, rows in pools.items()}, "tasks": tasks}
    (HERE / "tasks.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    for task in tasks[len(frozen):]:
        print(task["id"], task["stratum"], task["grep_tokens"], task["symbol"], task["expected"]["callers"])


if __name__ == "__main__":
    main(Path(sys.argv[1]))
