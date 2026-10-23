"""Django 5.2 "who calls X?" tasks with an AST answer key. Exploratory, not pre-registered.

Pool: functions and methods under django/ whose name is defined exactly once in the checkout, and whose every
mention in a Python file outside tests/ is the definition, a `from ... import` of it, or a direct call made in a
module-level function or in a method of a module-level class. Answer: those callers, "<path>::<function>" or
"<path>::<Class.method>". Sample (fixed seed): 5 tasks from the fifth of the pool with the largest repository-wide
`rg -n -w <name>` output (where grep is a token sink) and 5 tasks from the rest.

  python make_tasks.py <django git checkout>
"""
import ast
from collections import Counter, defaultdict
import io
import json
import random
import re
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "token-master-plugin/skills/token-master"))
from brainspace import tokens  # noqa: E402

GIT = r"C:\Program Files\Git\cmd\git.exe"
SEED = 20261019
PER_STRATUM = 5
WORD = re.compile(r"[A-Za-z_]\w*")


class Scan(ast.NodeVisitor):
    """Definitions, direct calls with the function that makes them, and `from ... import` names."""

    def __init__(self):
        self.stack, self.defs, self.calls, self.imports = [], [], [], Counter()

    def where(self):
        kinds = [kind for kind, _ in self.stack]
        if kinds == ["def"]:
            return self.stack[0][1]
        if kinds == ["class", "def"]:
            return f"{self.stack[0][1]}.{self.stack[1][1]}"
        return None  # module level, class body, nested function or nested class: no unambiguous caller name

    def visit_ClassDef(self, node):
        for child in [*node.decorator_list, *node.bases, *node.keywords]:
            self.visit(child)  # evaluated in the enclosing scope
        self.defs.append((node.name, None))
        self.stack.append(("class", node.name))
        for child in node.body:
            self.visit(child)
        self.stack.pop()

    def visit_FunctionDef(self, node):
        for child in [*node.decorator_list, node.args, *([node.returns] if node.returns else [])]:
            self.visit(child)  # decorators and defaults run in the enclosing scope
        kinds = [kind for kind, _ in self.stack]
        qual = node.name if not kinds else f"{self.stack[0][1]}.{node.name}" if kinds == ["class"] else None
        self.defs.append((node.name, qual))
        self.stack.append(("def", node.name))
        for child in node.body:
            self.visit(child)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ImportFrom(self, node):
        for alias in node.names:
            if alias.asname in (None, alias.name):
                self.imports[alias.name] += 1

    def visit_Call(self, node):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
        if name:
            self.calls.append((name, self.where()))
        self.generic_visit(node)


def main(checkout: Path) -> None:
    commit = subprocess.run([GIT, "rev-parse", "HEAD"], cwd=checkout, capture_output=True, text=True,
                            check=True).stdout.strip()
    raw = subprocess.run([GIT, "archive", "--format=tar", "HEAD"], cwd=checkout, capture_output=True, check=True).stdout
    texts = {}  # exactly the files the agents get: the harness snapshots the same `git archive HEAD`
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive.getmembers():
            data = archive.extractfile(member).read() if member.isfile() else b"\0"
            if b"\0" not in data:
                try:
                    texts[member.name] = data.decode("utf-8")
                except UnicodeDecodeError:
                    pass
    python = [path for path in texts if path.endswith(".py")]
    scans, broken = {}, set()
    for path in python:
        try:
            tree = ast.parse(texts[path])
        except SyntaxError:
            broken.add(path)
            continue
        scans[path] = scan = Scan()
        scan.visit(tree)
    defined = Counter(name for scan in scans.values() for name, _ in scan.defs)
    home = {name: (path, qual) for path, scan in scans.items() for name, qual in scan.defs
            if defined[name] == 1 and qual and path.startswith("django/") and len(name) >= 8
            and not name.startswith(("__", "test"))}
    mentions = defaultdict(list)
    for path in python:
        if not path.startswith("tests/"):
            for name, seen in Counter(w for w in WORD.findall(texts[path]) if w in home).items():
                mentions[name].append((path, seen))
    pool = []
    for name, (def_path, def_qual) in sorted(home.items()):
        callers, ok = set(), True
        for path, seen in mentions[name]:
            scan = scans.get(path)
            sites = [where for called, where in scan.calls if called == name] if scan else [None]
            if None in sites or seen != len(sites) + scan.imports[name] + (path == def_path):
                ok = False  # a mention that is not a definition, an import or an attributable direct call
                break
            callers |= {f"{path}::{where}" for where in sites}
        files = {caller.split("::")[0] for caller in callers}
        if ok and f"{def_path}::{def_qual}" not in callers and 2 <= len(callers) <= 8 and len(files) >= 2:
            pool.append({"name": name, "symbol": f"{def_path}::{def_qual}", "callers": sorted(callers)})
    names = {row["name"] for row in pool}
    lines = defaultdict(list)  # what `rg -n -w <name>` prints over the whole checkout
    for path, text in texts.items():
        if set(WORD.findall(text)) & names:
            for number, line in enumerate(text.splitlines(), 1):
                for name in set(WORD.findall(line)) & names:
                    lines[name].append(f"{path}:{number}:{line}")
    for row in pool:
        row["grep_tokens"] = tokens.count_tokens("\n".join(lines[row["name"]]))
    pool.sort(key=lambda row: (-row["grep_tokens"], row["name"]))
    cut = -(-len(pool) // 5)
    rng = random.Random(SEED)
    picked = ([dict(row, stratum="grep-top-fifth") for row in rng.sample(pool[:cut], PER_STRATUM)]
              + [dict(row, stratum="grep-rest") for row in rng.sample(pool[cut:], PER_STRATUM)])
    tasks = []
    for number, row in enumerate(picked, 1):
        path, qual = row["symbol"].split("::")
        what = f"the method `{qual}`" if "." in qual else f"the function `{qual}()`"
        tasks.append({
            "id": f"D{number:02d}", "category": "investigate", "stratum": row["stratum"], "symbol": row["symbol"],
            "grep_tokens": row["grep_tokens"],
            "prompt": (f"We're about to change the signature of {what} in {path}. Which non-test functions or "
                       "methods call it directly? Only files under the top-level `tests/` directory count as test "
                       "code. Reply with ONLY a JSON object with exactly 1 key: \"callers\" (list of strings, each "
                       "\"<path relative to the repository root>::<Class.method or function>\"). List order does "
                       "not matter."),
            "expected": {"callers": row["callers"]}, "unordered_list_keys": ["callers"]})
    result = {"kind": "exploratory, not pre-registered", "django_commit": commit, "seed": SEED,
              "python_files": len(python), "unparseable": sorted(broken), "pool_size": len(pool),
              "heavy_cutoff_grep_tokens": pool[cut - 1]["grep_tokens"],
              "pool_grep_tokens": {"max": pool[0]["grep_tokens"], "median": pool[len(pool) // 2]["grep_tokens"]},
              "tasks": tasks}
    (HERE / "tasks.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "tasks"}, indent=1))
    for task in tasks:
        print(task["id"], task["stratum"], task["grep_tokens"], task["symbol"], len(task["expected"]["callers"]))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
