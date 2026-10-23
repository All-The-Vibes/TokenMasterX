"""Django 5.2 "who calls X?" tasks on COMMON function names, with an import-resolved AST answer key.
Exploratory, not pre-registered. Companion to ../django-impact-20261019, whose 10 tasks use rare names only
(a repository-wide grep returns at most 683 tokens for any of them).

Pool: module-level functions under django/ whose direct callers resolve exactly. Every call in a Python file
outside the top-level tests/ is resolved through that file's imports: module-level and function-level `import`
and `from ... import`, relative imports, re-exports and star imports. A function stays in the pool only if:
  - it is defined once at module level and never rebound there;
  - it is never referenced without being called (callbacks, decorators, partials, assignments);
  - it is never called from module level, a class body or a nested function (no unambiguous caller name);
  - no call of its name (bare or `module.name`) is left unresolved anywhere outside tests/;
  - it does not call itself (as in ../django-impact-20261019);
  - it has 2 to 8 callers, in at least 2 files.
Answer: the callers, "<path>::<function>" or "<path>::<Class.method>".
Sample (fixed seed): 5 of the 20 pool entries with the largest repository-wide `rg -n -w <name>` output.

  python make_tasks_common.py <django git checkout>
"""
import ast
import builtins
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
SEED = 20261022
TOP, PICK = 20, 5
WORD = re.compile(r"[A-Za-z_]\w*")
BUILTINS = set(dir(builtins))
USED = HERE.parent / "django-impact-20261019" / "tasks.json"


def module_name(path: str) -> str:
    parts = path[:-3].split("/")
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def import_bindings(package: str, node) -> tuple[dict, list]:
    """Names bound by one import statement, and its star-import sources."""
    names, stars = {}, []
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.asname:
                names[alias.asname] = ("module", alias.name)
            else:
                top = alias.name.split(".")[0]
                names[top] = ("module", top)
        return names, stars
    base = node.module or ""
    if node.level:
        parts = package.split(".")
        parts = parts[:len(parts) - (node.level - 1)]
        base = ".".join(parts + ([node.module] if node.module else []))
    for alias in node.names:
        if alias.name == "*":
            stars.append(base)
        else:
            names[alias.asname or alias.name] = ("from", base, alias.name)
    return names, stars


def stored_names(nodes) -> set:
    """Names a function binds locally (parameters excluded), without entering nested scopes."""
    out, todo = set(), list(nodes)
    while todo:
        node = todo.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
            continue
        if isinstance(node, ast.Lambda):
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            out.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            out.add(node.name)
        todo.extend(ast.iter_child_nodes(node))
    return out


class Index:
    def __init__(self, trees: dict):
        self.trees = trees
        self.modules = {module_name(p) for p in trees}
        self.mods = {}
        for path, tree in trees.items():
            mod = module_name(path)
            package = mod if path.endswith("__init__.py") else mod.rpartition(".")[0]
            names, stars, exported, defs = {}, [], None, Counter()
            todo = list(tree.body)
            while todo:  # module level, including if/try/with blocks, never function or class bodies
                node = todo.pop(0)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names[node.name] = ("def", f"{mod}.{node.name}")
                    defs[node.name] += 1
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    bound, star = import_bindings(package, node)
                    names.update(bound)
                    stars += star
                elif isinstance(node, (ast.If, ast.Try, ast.With, ast.For, ast.While)) or (
                        hasattr(ast, "TryStar") and isinstance(node, ast.TryStar)):
                    todo[:0] = [child for field in ("body", "handlers", "orelse", "finalbody")
                                for child in getattr(node, field, [])]
                elif isinstance(node, ast.ExceptHandler):
                    todo[:0] = list(node.body)
                else:
                    if (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__"
                                                             for t in node.targets)
                            and isinstance(node.value, (ast.List, ast.Tuple))):
                        exported = {e.value for e in node.value.elts if isinstance(e, ast.Constant)}
                    for name in stored_names([node]):
                        names[name] = ("other",)
            self.mods[mod] = {"path": path, "package": package, "names": names, "stars": stars, "all": exported,
                              "defs": defs}

    def lookup(self, mod: str, name: str, depth: int = 0):
        """What `name` means at module level in `mod` (explicit bindings, then star imports)."""
        if depth > 25:
            return ("unknown",)
        if mod not in self.mods:
            return ("external", f"{mod}.{name}")
        info = self.mods[mod]
        if name in info["names"]:
            return self.follow(info["names"][name], depth + 1)
        for source in reversed(info["stars"]):
            if source not in self.mods:
                return ("unknown",)  # a star import from outside the checkout could bind anything
            exported = self.mods[source]["all"]
            if (name in exported) if exported is not None else not name.startswith("_"):
                found = self.lookup(source, name, depth + 1)
                if found[0] != "missing":
                    return found
        return ("missing",)

    def attribute(self, mod: str, name: str, depth: int = 0):
        """What `mod.name` means."""
        sub = f"{mod}.{name}"
        if mod in self.mods and sub in self.modules and self.mods[mod]["names"].get(name, ("from", mod, name)) == (
                "from", mod, name):  # unbound, or `from . import name` inside the package itself
            return ("module", sub)
        found = self.lookup(mod, name, depth)
        if found[0] == "missing" and f"{mod}.{name}" in self.modules:
            return ("module", f"{mod}.{name}")
        return found

    def follow(self, binding, depth: int = 0):
        if binding[0] == "from":
            return self.attribute(binding[1], binding[2], depth + 1)
        return binding

    def expr(self, mod: str, local: dict, node):
        if isinstance(node, ast.Name):
            if node.id in local:
                return self.follow(local[node.id])
            found = self.lookup(mod, node.id)
            if found[0] == "missing":
                return ("builtin",) if node.id in BUILTINS else ("unbound",)
            return found
        if isinstance(node, ast.Attribute):
            base = self.expr(mod, local, node.value)
            if base[0] == "module":
                return self.attribute(base[1], node.attr)
            return ("attr",)  # an attribute of an object or class: never a module-level function
        return ("expr",)


def main(checkout: Path) -> None:
    commit = subprocess.run([GIT, "rev-parse", "HEAD"], cwd=checkout, capture_output=True, text=True,
                            check=True).stdout.strip()
    raw = subprocess.run([GIT, "archive", "--format=tar", "HEAD"], cwd=checkout, capture_output=True, check=True).stdout
    texts = {}  # exactly the files the agents get
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive.getmembers():
            data = archive.extractfile(member).read() if member.isfile() else b"\0"
            if b"\0" not in data:
                try:
                    texts[member.name] = data.decode("utf-8")
                except UnicodeDecodeError:
                    pass
    trees = {}
    for path, text in texts.items():
        if path.endswith(".py") and not path.startswith("tests/"):
            try:
                trees[path] = ast.parse(text)
            except SyntaxError:
                pass
    index = Index(trees)
    callers, bad, unbound = defaultdict(set), set(), set()

    def visit(path, mod, local, nodes, caller):
        """Resolve every call and reference below `nodes`; `caller` is None where no caller name is unambiguous."""
        todo = list(nodes)
        call_funcs = set()
        while todo:
            node = todo.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                inner = {**local, **{n: ("other",) for n in stored_names(node.body)}}
                if not isinstance(node, ast.ClassDef):
                    args = node.args
                    inner.update({a.arg: ("other",) for a in [*args.posonlyargs, *args.args, *args.kwonlyargs,
                                                              *([args.vararg] if args.vararg else []),
                                                              *([args.kwarg] if args.kwarg else [])]})
                todo.extend([*node.decorator_list, *getattr(node, "bases", []),
                             *[k.value for k in getattr(node, "keywords", [])]])
                if not isinstance(node, ast.ClassDef):
                    todo.extend([d for d in [*node.args.defaults, *node.args.kw_defaults] if d is not None])
                visit(path, mod, inner, node.body, None)
                continue
            if isinstance(node, ast.Call):
                call_funcs.add(id(node.func))
                target = index.expr(mod, local, node.func)
                if target[0] == "def":
                    if caller is None:
                        bad.add(target[1])
                    else:
                        callers[target[1]].add(caller)
                elif target[0] in ("unbound", "unknown", "missing"):
                    unbound.add(node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", ""))
            elif isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load) \
                    and id(node) not in call_funcs:
                target = index.expr(mod, local, node)
                if target[0] == "def":
                    bad.add(target[1])  # referenced without a call
            todo.extend(ast.iter_child_nodes(node))

    for path, tree in trees.items():
        mod = module_name(path)
        top = []
        for node in tree.body:
            functions = [(node, node.name)] if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else []
            if isinstance(node, ast.ClassDef):
                functions = [(m, f"{node.name}.{m.name}") for m in node.body
                             if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
                rest = [m for m in node.body if not isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
                visit(path, mod, {}, [*node.decorator_list, *node.bases, *[k.value for k in node.keywords], *rest],
                      None)
            elif not functions:
                top.append(node)
            for function, qual in functions:
                args = function.args
                local = {n: ("other",) for n in stored_names(function.body)}
                local.update({a.arg: ("other",) for a in [*args.posonlyargs, *args.args, *args.kwonlyargs,
                                                          *([args.vararg] if args.vararg else []),
                                                          *([args.kwarg] if args.kwarg else [])]})
                package = index.mods[mod]["package"]
                for inner in ast.walk(ast.Module(body=function.body, type_ignores=[])):
                    if isinstance(inner, (ast.Import, ast.ImportFrom)):
                        local.update(import_bindings(package, inner)[0])  # function-level imports
                visit(path, mod, {}, [*function.decorator_list,
                                      *[d for d in [*args.defaults, *args.kw_defaults] if d is not None]], None)
                visit(path, mod, local, function.body, f"{path}::{qual}")
        visit(path, mod, {}, top, None)

    used = {t["symbol"] for t in json.loads(USED.read_text(encoding="utf-8"))["tasks"]}
    pool = []
    for mod, info in index.mods.items():
        if not info["path"].startswith("django/"):
            continue
        for name, count in info["defs"].items():
            qual = f"{mod}.{name}"
            symbol = f"{info['path']}::{name}"
            if (count != 1 or info["names"].get(name) != ("def", qual) or qual in bad or name in unbound
                    or symbol in used or not isinstance(next((n for n in trees[info["path"]].body
                                                               if getattr(n, "name", None) == name), None),
                                                          (ast.FunctionDef, ast.AsyncFunctionDef))):
                continue
            found = callers.get(qual, set())
            if (2 <= len(found) <= 8 and len({c.split("::")[0] for c in found}) >= 2
                    and symbol not in found):  # as in ../django-impact-20261019: no self-recursive targets
                pool.append({"name": name, "symbol": symbol, "callers": sorted(found)})
    names = {row["name"] for row in pool}
    lines = defaultdict(list)  # what `rg -n -w <name>` prints over the whole checkout
    for path, text in texts.items():
        if set(WORD.findall(text)) & names:
            for number, line in enumerate(text.splitlines(), 1):
                for name in set(WORD.findall(line)) & names:
                    lines[name].append(f"{path}:{number}:{line}")
    for row in pool:
        row["grep_tokens"] = tokens.count_tokens("\n".join(lines[row["name"]]))
    pool.sort(key=lambda row: (-row["grep_tokens"], row["symbol"]))
    picked = random.Random(SEED).sample(pool[:TOP], min(PICK, len(pool)))
    tasks = []
    for number, row in enumerate(picked, 11):
        path, name = row["symbol"].split("::")
        tasks.append({
            "id": f"D{number:02d}", "category": "investigate", "stratum": "common-name", "symbol": row["symbol"],
            "grep_tokens": row["grep_tokens"],
            "prompt": (f"We're about to change the signature of the function `{name}()` in {path}. Which non-test "
                       "functions or methods call it directly? Only files under the top-level `tests/` directory "
                       "count as test code. Reply with ONLY a JSON object with exactly 1 key: \"callers\" (list of "
                       "strings, each \"<path relative to the repository root>::<Class.method or function>\"). List "
                       "order does not matter."),
            "expected": {"callers": row["callers"]}, "unordered_list_keys": ["callers"]})
    result = {"kind": "exploratory, not pre-registered", "django_commit": commit, "seed": SEED,
              "pool_size": len(pool), "top": [{k: r[k] for k in ("symbol", "grep_tokens")} | {"callers": len(r["callers"])}
                                              for r in pool[:TOP]],
              "tasks": tasks}
    (HERE / "tasks.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print("pool", len(pool), "| grep tokens, top 20:", [r["grep_tokens"] for r in pool[:TOP]])
    for task in tasks:
        print(task["id"], task["grep_tokens"], task["symbol"], task["expected"]["callers"])


if __name__ == "__main__":
    main(Path(sys.argv[1]))
