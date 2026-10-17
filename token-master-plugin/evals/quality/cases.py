"""Synthetic, non-IID challenge suite, not statistical population certification.
Only public_task()/fixtures go to models; parent owns isolation/actions/traces."""
import ast
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
from types import MappingProxyType


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def safe_path(path):
    if not isinstance(path, str) or not path or "\\" in path or ":" in path:
        raise ValueError("unsafe path")
    parts = path.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(10)}
    if PurePosixPath(path).is_absolute() or any(
        p in ("", ".", "..") or p.endswith((".", " ")) or
        p.split(".")[0].upper() in reserved or any(ord(c) < 32 for c in p)
        for p in parts
    ):
        raise ValueError("unsafe path")
    return path


def safe_root(root):
    root = Path(root).absolute()
    for part in (root, *root.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("linked workspace")
    return root


@dataclass(frozen=True)
class Case:
    id: str
    version: str
    prompt: str
    fixtures: tuple[tuple[str, str], ...]
    allowed_changes: tuple[str, ...]
    followups: tuple[str, ...] = ()
    intent: str = "exact"
    global_hint: str = ""

    def __post_init__(self):
        if self.intent not in ("exact", "aggregate", "debug", "edit", "navigation", "overview", "task"):
            raise ValueError("unknown explicit intent")
        if type(self.global_hint) is not str:
            raise ValueError("global_hint must be text")
        if any(type(x) is not str or not x for x in (self.id, self.version, self.prompt)):
            raise ValueError("identity and prompt fields must be nonempty strings")
        if not all(type(x) is tuple for x in (self.fixtures, self.allowed_changes, self.followups)):
            raise ValueError("case collections must be immutable tuples")
        if any(type(x) is not str or not x for x in self.followups):
            raise ValueError("followups must be strings")
        if any(type(pair) is not tuple or len(pair) != 2 for pair in self.fixtures):
            raise ValueError("fixtures must be immutable path/content pairs")
        paths = [safe_path(p) for p, content in self.fixtures if isinstance(content, str)]
        if len(paths) != len(self.fixtures) or len(set(paths)) != len(paths):
            raise ValueError("invalid or duplicate fixtures")
        if any(p not in paths or p.startswith("tests/") for p in self.allowed_changes):
            raise ValueError("only existing non-test files may be changed")

    @property
    def identity(self):
        return digest(asdict(self))

    @property
    def files(self):
        return MappingProxyType(dict(self.fixtures))

    @property
    def stratum(self):
        return self.id

    def public_task(self, stage=0):
        prompts = (self.prompt, *self.followups)
        if type(stage) is not int or not 0 <= stage < len(prompts):
            raise ValueError("invalid stage")
        protocol = (" Emit one JSON action: read {type,path}, write {type,path,content:string}, "
                    "or answer {type,content:JSON}. Native tools may use these same arguments. "
                    "No shell. allowed_changes is the grading contract, not a disabled tool. "
                    "Never add/edit tests. No edits for answer-only tasks. ")
        return dict(id=self.id, version=self.version, identity=self.identity,
                    prompt=protocol + prompts[stage], paths=[p for p, _ in self.fixtures],
                    allowed_changes=list(self.allowed_changes))


def validate_action(case, action):
    """Validate syntax/relative paths, NOT compliance. Parent enforces root isolation."""
    if type(action) is not dict:
        raise ValueError("action must be a dict")
    kind = action.get("type")
    required = {"read": {"type", "path"}, "write": {"type", "path", "content"},
                "answer": {"type", "content"}}
    if not isinstance(kind, str) or kind not in required or set(action) != required[kind]:
        raise ValueError("unknown action or fields")
    try:
        encoded = json.dumps(action, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("non-JSON action") from exc
    if len(encoded.encode()) > 262144:
        raise ValueError("action too large")
    if kind != "answer":
        safe_path(action["path"])
        if kind == "write" and not isinstance(action["content"], str):
            raise ValueError("write content must be text")
    return action


def materialize(case, root):
    """Populate an empty private workspace. Not a race-proof OS sandbox."""
    root = safe_root(root)
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ValueError("workspace must be empty")
    root.mkdir(parents=True, exist_ok=True)
    for path, content in case.fixtures:
        target = root / safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))
    return root


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def source_atoms(files):
    """Static name -> exact file spans; whole classes retained. NOT safe-to-exec validation."""
    atoms = {}
    for path, source in files.items():
        safe_path(path)
        if not path.endswith(".py"):
            continue
        if type(source) is not str or len(source.encode("utf-8")) > 524288:
            raise ValueError("oversized or nontext source")
        lines = source.splitlines(keepends=True)
        stack = [(ast.parse(source, filename=path), ())]
        while stack:
            node, scope = stack.pop()
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                scope = (*scope, node.name)
                name = ".".join(scope)
                start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
                if node.decorator_list:
                    while start > 1 and not lines[start-1].lstrip().startswith("@"):
                        start -= 1
                atoms[f"{path}:{name}@{start}"] = dict(
                    path=path, symbol=name, kind="class" if isinstance(node, ast.ClassDef) else "function",
                    start_line=start, end_line=node.end_lineno, source="".join(lines[start-1:node.end_lineno]))
            stack.extend((child, scope) for child in ast.iter_child_nodes(node))
    return atoms


def _corpus():
    rows = [dict(id=f"r{i:03}", status="ready", units=(i % 19) * 17) for i in range(241)]
    rows[119]["units"] = None
    del rows[120]["units"]
    rows[121].update(status="FAILED", units=999999)
    rows[122]["units"], rows[123]["units"] = True, "17"
    logs = [f"{i:03} INFO R{i:03} completed" for i in range(301)]
    logs[149:153] = ["149 INFO R151 archive connected", "150 ERROR R151 disk full",
                    "151 FAILED R151 archive E28", "152 RETRY R151 deferred"]
    manuals = tuple((f"manual/part{i:02}.json", _json([
        dict(key=f"{'normalize' if i == 17 else 'stage' + str(i)}.{j}",
             retry=7 if (i, j) == (17, 173) else 3,
             note="keep α / β; do not trim" if (i, j) == (17, 173) else "ordinary")
        for j in range(200)])) for i in range(24))
    return (
        Case("explain_only", "3", "Explain cache.py without editing. For a new Cache, put('x',10), "
             "get('x',0), get('x',1), get('x',0) in order; "
             "report returns from only the three get calls; exclude put return. Answer exact JSON "
             "{returns:[...],stored:{...}}. Distinguish expiry from deletion.",
             (("cache.py", "class Cache:\n    def __init__(self): self.data = {}\n"
               "    def put(self, key, value): self.data[key] = value\n"
               "    def get(self, key, age):\n        if age > 0: return None\n"
               "        return self.data.get(key)\n"),), (), intent="exact", global_hint="Cache"),
        Case("small_fix", "2", "Fix trailing_mean's one boundary bug in app.py. For positive integer "
             "width use up to the last width values, divide by actual count; empty values returns None. "
             "Width <= 0 raises ValueError. Preserve input. No unrelated edits; answer a summary.",
             (("app.py", "def trailing_mean(values, width):\n    if width <= 0: raise ValueError('width')\n"
               "    if not values: return None\n    return sum(values[-width:]) / width\n"),
              ("README.txt", "Public API: trailing_mean(values, width); Python numeric lists.\n")), ("app.py",),
             intent="edit", global_hint="trailing_mean"),
        Case("reusable_abstraction", "2", "Explicitly introduce public reusable clamp(value, low, high) "
             "in scores.py. Inclusive bounds; low>high raises ValueError. Both score(value) and "
             "percentage(value,total) must delegate to clamp (including when it is replaced). "
             "score clamps to [0,100]; percentage clamps value/total*100 to [0,100]. "
             "Preserve ZeroDivisionError at total=0. Requested reuse is required, not overengineering.",
             (("scores.py", "def score(value):\n    return max(0, min(100, value))\n" +
               "def percentage(value, total):\n    return max(0, min(100, value / total * 100))\n"),),
             ("scores.py",), intent="edit", global_hint="clamp score percentage"),
        Case("deep_proof", "2", "Give a deep proof for integer n>=1 that log(n)<=H_n<=1+log(n), "
             "H_n=sum(1/k,k=1..n), natural log. Derive each bound by explicit interval integral "
             "comparisons and summation, handle n=1, discuss strictness, and refute H_n<=log(n). "
             "Answer JSON {premises:[strings],inequalities:[strings],counterexample:{n,lhs,rhs},"
             "rationale:string}. Include a full derivation, not just final inequalities.",
             (("problem.txt", "H_n = 1 + 1/2 + ... + 1/n. Domain: positive integers.\n"),), (), intent="exact"),
        Case("json_exact", "2", "Read all records.json. Answer exact JSON {row_count,valid_count,"
             "sum_units,invalid_ids,failed_ids,failed_record}. Valid for sum/count: status ready "
             "and units is an integer, not boolean. invalid_ids: null/missing/noninteger units "
             "in source order. failed_ids: status FAILED in source order. failed_record: full "
             "unique FAILED row. Do not coerce values or omit middle anomalies.",
             (("records.json", _json(rows)),), (), intent="aggregate", global_hint="units status FAILED"),
        Case("rare_failure", "2", "Inspect all run.log; successful tail does not negate earlier "
             "failure. Answer exact JSON {failed_count,request,code,cause,sequence}; sequence is "
             "all line numbers for the failed request in order including connection, cause, "
             "failure, retry. cause is the ERROR message without prefix.",
             (("run.log", "\n".join(logs) + "\n"),), (), intent="debug", global_hint="FAILED ERROR"),
        Case("navigation", "3", "Constructed recovery stress case, not performance-representative. "
             "Follow this source order exactly. First read catalog.json to locate normalize's owning "
             "manual. Then read that manual to obtain its first object's key. Finally read "
             "verification.txt for its single-line marker (omit the trailing newline). "
             "Read no other sources before answering {path:string,first_key:string,marker:string}. "
             "A later question will require exact detail recovery.",
             (("catalog.json", _json([dict(stage="normalize" if i == 17 else f"stage{i}",
               path=f"manual/part{i:02}.json") for i in range(24)])), *manuals,
              ("verification.txt", "VERIFY-ORBIT-731\n")), (),
             ("Recover the complete normalize.173 object from the root you located. Answer that "
              "exact JSON object, including punctuation and Unicode; no overview substitute.",),
             intent="overview", global_hint="normalize"),
        Case("graph_freshness", "2", "index.json was captured before the current app.py. Source "
             "is authoritative. Disambiguate render across files and answer {stale:boolean,"
             "candidates:[qualified IDs],actual_edges:[[caller,callee]],obsolete_edges:[[caller,callee]]}. "
             "List render candidates lexically; edges are direct calls of app.py:run.",
             (("a.py", "def render(): return 'a'\n"), ("b.py", "def render(): return 'b'\n"),
              ("app.py", "from b import render as emit\ndef run(): return emit()\n"),
              ("index.json", _json(dict(source="from a import render as emit\ndef run(): return emit()\n",
               edges=[["app.py:run", "a.py:render"]], names=["a.py:render", "b.py:render"])))), (),
             intent="exact", global_hint="run render"),
    )


CASES = _corpus()
