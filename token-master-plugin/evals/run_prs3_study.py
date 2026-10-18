"""PRS-3: pre-registered live study of graph-first TokenMaster v7 on real repository tasks.

Protocol: token-master-plugin/docs/PRS3_PROTOCOL.md (written before any study call).
Primary endpoint, as in PRS-2: cost = uncached input + 0.1 x cached input + 8 x output.

  stock     Copilot-CLI-shaped agent with parallel tool calls; no TokenMaster
  tm6       stock + request-policy-v6 (the PRS-2 winner)
  tm6_hint  tm6 + a one-sentence reminder that whole-file views and broad grep cost tokens
            (attribution arm: the same advice as tm7's hint, without the tools)
  tm7       tm6 + graph-first navigation: locate / read_symbol / impact over graphify's call
            graph with exact line ranges (brainspace/symbol_index.py) and a two-sentence hint

Model, prompt, base tools, oracle, gateway, logical working directory and statistics are
reused unchanged from run_prs1_study.py and run_prs2_study.py.

Subcommands: self-test | prepare | smoke | run | analyze
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from unittest import mock

EVALS = Path(__file__).resolve().parent
if str(EVALS) not in sys.path:  # isolated child processes (-I) do not add the script folder
    sys.path.insert(0, str(EVALS))

import run_prs1_study as p1  # noqa: E402
import run_prs2_study as p2  # noqa: E402
from run_prs1_study import PLUGIN, REPO, SKILL, sha256_bytes, sha256_file, write_json  # noqa: E402

from brainspace import symbol_index  # noqa: E402
from brainspace.request_policy import RequestPolicy  # noqa: E402
from brainspace.runtime import ExecutedToolResult, RuntimeSession  # noqa: E402
from brainspace.runtime_policy import RuntimePolicy  # noqa: E402
from brainspace.runtime_resources import RuntimeResources  # noqa: E402
from brainspace.transport import parse_json  # noqa: E402

SEED = 20261020
REPEATS = 5
MAX_CALLS = 30
TOKEN_CAP = 60_000_000
LOGICAL_ROOT = p2.LOGICAL_ROOT
ARMS = ("stock", "tm6", "tm6_hint", "tm7")
# Holm runs within each family. "primary" answers the study question; "attribution" separates
# the navigation tools from the advice that comes with them.
FAMILIES = {"primary": (("tm6", "stock"), ("tm7", "stock"), ("tm7", "tm6")),
            "attribution": (("tm6_hint", "tm6"), ("tm7", "tm6_hint"))}
QUOTA = {"locate": 6, "logic": 6, "impact": 4, "docs": 4, "edit": 4}
NAV_TOOLS = tuple(spec["name"] for spec in symbol_index.TOOL_SPECS)
NAV_HINT = ("Code navigation tools: `locate` finds functions, classes, constants, Markdown sections and JSON keys "
            "with path:lines; `read_symbol` returns exactly one of them; `impact` lists callers from a resolved call "
            "graph. They cost far fewer tokens than whole-file views or broad grep; use grep or view for raw text.")
THRIFT_HINT = ("Whole-file views and broad grep cost far more tokens than targeted searches and ranged views; "
               "read only what the task needs.")


def arm_spec(arm: str) -> dict:
    return {"parallel": True, "v6": arm != "stock", "nav": arm == "tm7",
            "hint": {"tm6_hint": "thrift", "tm7": "nav"}.get(arm)}


def runtime_config(spec: dict):
    if spec["v6"]:
        return RuntimePolicy(backend="local", request_policy=RequestPolicy(version="request-policy-v6", enabled=True),
                             require_nonexpanding_input=True), RuntimeResources()
    return RuntimePolicy(), RuntimeResources()


def strip_logical(value):
    """Turn a path under the logical working directory into a repository-relative one."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    root = LOGICAL_ROOT.lower()
    if text.replace("/", "\\").lower() == root:
        return ""
    if text[:len(root) + 1].replace("/", "\\").lower() == root + "\\":
        return text[len(root) + 1:]
    return text


def product_sources() -> list[Path]:
    """Every product module a session can import (tests excluded), plus the graph stamping code."""
    modules = [p for p in (SKILL / "brainspace").rglob("*.py") if "tests" not in p.relative_to(SKILL).parts]
    return sorted([*modules, SKILL / "graphify_mcp.py"])


def first_call_cache(path: Path) -> tuple[int, int] | None:
    """(input, cached) tokens of a session's first model call, from its raw capture."""
    try:
        usage = json.loads(json.loads(path.read_text(encoding="utf-8").splitlines()[0])["output"])["usage"]
        return int(usage["input_tokens"]), int((usage.get("input_tokens_details") or {}).get("cached_tokens") or 0)
    except (OSError, IndexError, KeyError, TypeError, ValueError, AttributeError):
        return None


def wilcoxon_exact(diffs: list[float]) -> float:
    """run_prs1_study.wilcoxon_exact, counted by dynamic programming over doubled ranks instead of
    enumerating all 2**n sign patterns (minutes per call at 24 tasks). The p-values are identical."""
    d = [x for x in (round(v, 6) for v in diffs) if x != 0]
    n = len(d)
    if n == 0:
        return 1.0
    order = sorted(range(n), key=lambda i: abs(d[i]))
    doubled = [0] * n  # tied ranks average to half-integers; doubling keeps them exact
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(d[order[j + 1]]) == abs(d[order[i]]):
            j += 1
        for k in range(i, j + 1):
            doubled[order[k]] = i + j + 2
        i = j + 1
    ways = Counter({0: 1})  # rank sum -> number of sign patterns giving it
    for rank in doubled:
        step = Counter(ways)
        for total, count in ways.items():
            step[total + rank] += count
        ways = step
    total = sum(doubled)
    distance = abs(2 * sum(r for r, x in zip(doubled, d, strict=True) if x > 0) - total)
    return sum(count for value, count in ways.items() if abs(2 * value - total) >= distance) / (1 << n)


def build_nav_index(root: Path) -> dict:
    """graphify's graph (stamped as setup.py stamps it) plus the exact-range symbol index."""
    import graphify_mcp

    started = time.monotonic()
    version = subprocess.run([str(p1.GRAPHIFY_EXE), "--version"], capture_output=True, text=True,
                             creationflags=p1.NO_WINDOW).stdout.strip()
    subprocess.run([str(p1.GRAPHIFY_EXE), "update", "."], cwd=root, check=True, capture_output=True,
                   creationflags=p1.NO_WINDOW)
    graph = json.loads((root / "graphify-out/graph.json").read_text(encoding="utf-8"))
    graphify_mcp.stamp_graph(graph, root, {"name": "graphify", "version": version.removeprefix("graphify ") or None},
                             time.monotonic() - started)
    (root / ".token-master").mkdir(exist_ok=True)
    (root / ".token-master/graph.json").write_text(json.dumps(graph, ensure_ascii=False) + "\n", encoding="utf-8")
    shutil.rmtree(root / "graphify-out")  # keep the visible tree identical across arms
    index = symbol_index.SymbolIndex(root)
    try:
        kinds = dict(index.db.execute("SELECT kind, count(*) FROM symbols GROUP BY kind").fetchall())
    finally:
        index.close()
    return {"graphify": version, "graphify_nodes": len(graph.get("nodes", [])),
            "graphify_links": len(graph.get("links", [])), "symbols_by_kind": kinds,
            "graph_sha256": sha256_file(root / ".token-master/graph.json"),
            "symbols_sha256": sha256_file(root / ".token-master/symbols.sqlite"),
            "seconds": round(time.monotonic() - started, 2)}


def validate_design(tasks: list[dict]) -> None:
    if {t["set"] for t in tasks} != {"primary"}:
        raise SystemExit("every PRS-3 task is a fresh primary task (set=primary)")
    if Counter(t["category"] for t in tasks) != Counter(QUOTA):
        raise SystemExit(f"category quota must be {QUOTA}")


def prepare(out: Path, tasks_file: Path) -> None:
    if out.exists():
        raise SystemExit(f"output must be new: {out}")
    out.mkdir(parents=True)
    tar = out / "snapshot.tar"
    subprocess.run([str(p1.GIT_EXE), "archive", "--format=tar", "-o", str(tar), p1.SNAPSHOT_COMMIT,
                    *p1.SNAPSHOT_PATHS], cwd=REPO, check=True)
    templates = {}
    for name in ("plain", "nav"):
        root = out / "templates" / name
        root.mkdir(parents=True)
        with tarfile.open(tar) as archive:
            archive.extractall(root, filter="data")
        subprocess.run([str(p1.GIT_EXE), "init", "-q"], cwd=root, check=True)
        templates[name] = root
    nav_receipt = build_nav_index(templates["nav"])
    manifest = p1.manifest(templates["plain"])
    if p1.manifest(templates["nav"]) != manifest:
        raise SystemExit("visible workspace differs between plain and nav templates")
    prompt, view_tool = p1.load_copilot_prompt()
    system_prompt = p1.adapt_copilot_prompt(prompt)
    tasks = json.loads(tasks_file.read_text(encoding="utf-8"))["tasks"]
    p1.validate_tasks(tasks, templates["plain"])
    validate_design(tasks)
    visible = [(templates["plain"] / rel).read_text(encoding="utf-8", errors="replace") for rel in manifest]
    for task in tasks:  # leak tripwire (idea from google-research/harness2): no task text inside the workspace
        if any(task["prompt"][:80] in text for text in visible):
            raise SystemExit(f"{task['id']}: task text is readable inside the workspace")
    from brainspace import tokens
    jobs = []
    for repeat in range(1, REPEATS + 1):
        block = [[repeat, t["id"], arm] for t in tasks for arm in ARMS]
        random.Random(SEED + repeat).shuffle(block)
        jobs += block
    protocol = {
        "study": "PRS-3", "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": p1.MODEL, "reasoning_effort": "low", "max_output_tokens": 4096, "max_calls_per_session": MAX_CALLS,
        "intent": "conservative (production default for every task)", "seed": SEED, "repeats": REPEATS,
        "logical_root": LOGICAL_ROOT, "arms": {arm: arm_spec(arm) for arm in ARMS},
        "families": {family: [list(c) for c in pairs] for family, pairs in FAMILIES.items()},
        "endpoints": dict(p2.ENDPOINTS),
        "primary_endpoint": "cost = uncached input + 0.1 x cached input + 8 x output, per session",
        "token_cap": TOKEN_CAP,
        "snapshot": {"commit": p1.SNAPSHOT_COMMIT, "paths": list(p1.SNAPSHOT_PATHS), "tar_sha256": sha256_file(tar),
                     "visible_files": len(manifest),
                     "manifest_sha256": sha256_bytes(json.dumps(manifest, sort_keys=True).encode())},
        "nav_index": nav_receipt,
        "system_prompt": system_prompt, "system_prompt_sha256": sha256_bytes(system_prompt.encode()),
        "system_prompt_tokens_cl100k": tokens.count_tokens(system_prompt),
        "nav_hint": NAV_HINT, "nav_hint_tokens_cl100k": tokens.count_tokens(NAV_HINT),
        "thrift_hint": THRIFT_HINT, "thrift_hint_tokens_cl100k": tokens.count_tokens(THRIFT_HINT),
        "tools": {"base": [view_tool, *p1.BASE_TOOL_SPECS], "nav": symbol_index.TOOL_SPECS},
        "nav_tool_tokens_cl100k": tokens.count_tokens(json.dumps(symbol_index.TOOL_SPECS)),
        "tasks": tasks, "tasks_file": str(tasks_file), "tasks_sha256": sha256_file(tasks_file), "schedule": jobs,
        "harness_sha256": sha256_file(Path(__file__)), "shared_harness_sha256": sha256_file(Path(p1.__file__)),
        "shared_harness2_sha256": sha256_file(Path(p2.__file__)),
        "protocol_doc_sha256": sha256_file(PLUGIN / "docs/PRS3_PROTOCOL.md"),
        "product_sources_sha256": {p.relative_to(REPO).as_posix(): sha256_file(p) for p in product_sources()},
    }
    write_json(out / "protocol.json", protocol)
    digest = sha256_file(out / "protocol.json")
    (out / "protocol.sha256").write_text(digest + "\n", encoding="utf-8")
    print(f"prepared {out}: {len(tasks)} tasks x {len(ARMS)} arms x {REPEATS} repeats = {len(jobs)} sessions; "
          f"protocol.json sha256 {digest}; nav index {nav_receipt}")


def verify_frozen(out: Path, protocol: dict) -> None:
    """Refuse to run if anything recorded at prepare changed: code, protocol, tasks, index or workspace."""
    if sha256_file(out / "protocol.json") != (out / "protocol.sha256").read_text(encoding="utf-8").strip():
        raise SystemExit("protocol.json changed after prepare")
    frozen = {"harness": (Path(__file__), protocol["harness_sha256"]),
              "shared harness": (Path(p1.__file__), protocol["shared_harness_sha256"]),
              "shared harness 2": (Path(p2.__file__), protocol["shared_harness2_sha256"]),
              "protocol document": (PLUGIN / "docs/PRS3_PROTOCOL.md", protocol["protocol_doc_sha256"]),
              "tasks": (Path(protocol["tasks_file"]), protocol["tasks_sha256"]),
              "graph": (out / "templates/nav/.token-master/graph.json", protocol["nav_index"]["graph_sha256"]),
              "symbol index": (out / "templates/nav/.token-master/symbols.sqlite",
                               protocol["nav_index"]["symbols_sha256"])}
    frozen.update({rel: (REPO / rel, digest) for rel, digest in protocol["product_sources_sha256"].items()})
    current = {p.relative_to(REPO).as_posix() for p in product_sources()}
    if current != set(protocol["product_sources_sha256"]):
        raise SystemExit("product modules were added or removed after prepare")
    for name, (path, digest) in frozen.items():
        if not path.is_file() or sha256_file(path) != digest:
            raise SystemExit(f"{name} changed after prepare ({path}); re-run prepare and disclose it")
    for name in ("plain", "nav"):
        manifest = p1.manifest(out / "templates" / name)
        if sha256_bytes(json.dumps(manifest, sort_keys=True).encode()) != protocol["snapshot"]["manifest_sha256"]:
            raise SystemExit(f"{name} template changed after prepare")


class Study:
    def __init__(self, out: Path, protocol: dict, urls: dict[str, str]):
        self.out, self.protocol, self.urls = out, protocol, urls
        self.lock = threading.Lock()
        self.tokens_used = 0

    def run_session(self, task: dict, arm: str, repeat: int, suffix: str = "") -> dict:
        spec = arm_spec(arm)
        sid = f"{task['id']}-{arm}-r{repeat}{suffix}"
        run_dir, workspace = self.out / "runs" / sid, self.out / "ws" / sid
        template = self.out / "templates" / ("nav" if spec["nav"] else "plain")
        row = {"task": task["id"], "set": task["set"], "category": task["category"], "arm": arm,
               "repeat": repeat, "session": sid}
        with self.lock:
            over_cap = self.tokens_used >= TOKEN_CAP
        if over_cap:
            return {**row, "status": "not_run", "why": "token_cap"}
        run_dir.mkdir(parents=True)
        shutil.copytree(template, workspace)
        tools_impl, index = p2.MappedTools(workspace), None
        tool_counts: Counter = Counter()
        final_text, failure, transformed = None, None, None
        started = time.monotonic()

        def run_tool(name: str, args: dict) -> ExecutedToolResult:
            if index is not None:
                try:
                    output = symbol_index.dispatch(index, name, {k: strip_logical(v) for k, v in args.items()})
                except Exception as error:  # shown to the model as an error, as an MCP server would report it
                    output = f"Error: {type(error).__name__}: {str(error)[:300]}"
                if output is not None:  # never reveal the private copy (its path names the task and the arm)
                    output = (output.replace(str(index.root), LOGICAL_ROOT)
                              .replace(index.root.as_posix(), LOGICAL_ROOT.replace("\\", "/")))
                    return ExecutedToolResult(output, "error" if output.startswith("Error") else "success")
            return tools_impl.execute(name, args)

        try:
            if spec["nav"]:
                index = symbol_index.SymbolIndex(workspace)
            policy, resources = runtime_config(spec)
            transport = p1.StudyTransport(
                base_url=self.urls[arm], model=p1.MODEL, allow_network=True, max_output_tokens=4096,
                max_request_bytes=4_000_000, max_response_bytes=4_000_000, timeout=90, reasoning_effort="low",
                parallel=spec["parallel"], cache_key=sha256_bytes(sid.encode())[:32])
            session = RuntimeSession(workspace=workspace, session_id=sid, output=run_dir / "session",
                                     transport=transport, runtime_policy=policy, runtime_resources=resources,
                                     task_id=task["id"], max_calls=MAX_CALLS)
            session_folder = "C:/Users/dev/.copilot/session-state/" + sha256_bytes(sid.encode())[:32]
            system = (self.protocol["system_prompt"].replace(p1.CWD_TOKEN, LOGICAL_ROOT)
                      .replace(p1.SESSION_TOKEN, session_folder))
            hint = {"nav": self.protocol["nav_hint"], "thrift": self.protocol["thrift_hint"]}.get(spec["hint"])
            if hint:
                system += "\n\n" + hint
            specs = self.protocol["tools"]["base"] + (self.protocol["tools"]["nav"] if spec["nav"] else [])
            tools = [p1.chat_tool(t) for t in specs]
            messages = [{"role": "system", "content": system}, {"role": "user", "content": task["prompt"]}]
            try:
                for _ in range(MAX_CALLS):
                    reply = session.invoke({"model": p1.MODEL, "messages": deepcopy(messages), "tools": deepcopy(tools)},
                                           intent="conservative", stable_prefix_messages=2)
                    if not reply.ok or not reply.complete:
                        infra = reply.http_status in (None, 429, 500, 502, 503, 504)
                        failure = f"{'infra' if infra else 'provider'}:{reply.reason}:{reply.http_status}"
                        break
                    items = parse_json(reply.output_text).get("output", [])
                    calls = [i for i in items if i.get("type") == "function_call"]
                    text = "".join(c.get("text", "") for i in items if i.get("type") == "message"
                                   for c in i.get("content", []) if c.get("type") == "output_text")
                    if not calls:
                        final_text = text
                        break
                    messages.append({"role": "assistant", "content": text or None, "tool_calls": [
                        {"id": c["call_id"], "type": "function",
                         "function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls]})
                    for c in calls:
                        tool_counts[c["name"]] += 1
                        call = {"id": c["call_id"], "type": "function",
                                "function": {"name": c["name"], "arguments": c["arguments"]}}
                        try:
                            output = session.execute_tool(call, lambda n, a: run_tool(n, a))
                        except ValueError as error:
                            output = f"Error: invalid tool call ({error})"
                        messages.append({"role": "tool", "tool_call_id": c["call_id"], "content": output})
                else:
                    failure = "call_cap_reached"
                verdict = p1.grade(task, final_text, workspace, template) if failure is None else \
                    {"pass": False, "why": failure}
                transformed = getattr(session, "_transformed", None)
                session.finish(success=verdict["pass"])
            finally:
                session.close()
        except Exception as error:  # harness/component failure: recorded, never silently dropped
            failure = f"harness:{type(error).__name__}:{str(error)[:300]}"
            verdict = {"pass": False, "why": failure}
        finally:
            if index is not None:
                index.close()
        usage = p1.usage_from_captures(run_dir / "session/captures.jsonl")
        with self.lock:
            self.tokens_used += usage["input"] + usage["output"]
        # A harness failure before any model call says nothing about the arm: treat it as infrastructure.
        early = bool(failure) and failure.startswith("harness") and usage["calls"] == 0
        status = "infra" if failure and (failure.startswith("infra") or early) else ("pass" if verdict["pass"] else "fail")
        for rel in verdict.get("changed", [])[:10]:
            target = workspace / rel
            if target.is_file():
                keep = run_dir / "changed" / rel
                keep.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, keep)
        try:
            p1.remove_tree(workspace)
        except OSError:
            pass  # a leftover private workspace copy does not affect results
        row.update(status=status, why=verdict["why"], answer=verdict.get("answer"), final_text=(final_text or "")[:2000],
                   changed=verdict.get("changed", []), usage=usage, tool_calls=dict(tool_counts),
                   transformed_requests=transformed, wall_seconds=round(time.monotonic() - started, 2))
        return row


def execute(out: Path, protocol: dict, token: str, workers: int, jobs: list[list], results: Path) -> None:
    gateways, urls = {}, {}
    try:
        for arm in ARMS:
            gateways[arm] = p1.start_gateway(token, out / f"gateway-{arm}.jsonl")
            urls[arm] = f"http://127.0.0.1:{gateways[arm].server_port}/v1"
        p1.warmup(urls, out)
        study = Study(out, protocol, urls)
        tasks = {t["id"]: t for t in protocol["tasks"]}
        lock = threading.Lock()

        def one(job, suffix=""):
            repeat, task_id, arm = job
            row = study.run_session(tasks[task_id], arm, repeat, suffix)
            p1.append_jsonl(results, row, lock)
            u = row.get("usage", {})
            print(f"[{row['session']:<26}] {row['status']:<6} calls={u.get('calls', 0):>2} "
                  f"cost={p2.endpoint_value(u, 'cost') if u else 0:>9,.0f} why={row.get('why')}", flush=True)
            return row

        with ThreadPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(one, jobs))
        retry = [[r["repeat"], r["task"], r["arm"]] for r in rows if r["status"] == "infra"]
        if retry:
            print(f"re-running {len(retry)} infra-failed sessions once (pre-declared rule)", flush=True)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(lambda job: one(job, "-rerun"), retry))
    finally:
        for server in gateways.values():
            server.shutdown()


def child_main(out: Path, mode: str, workers: int) -> int:
    token = sys.stdin.readline().strip()
    protocol = json.loads((out / "protocol.json").read_text(encoding="utf-8"))
    verify_frozen(out, protocol)
    from brainspace import tokens
    tokens.count_tokens("warm-up")  # load once before worker threads (lazy init is not thread-safe)
    if not tokens.backend_info()["exact_reference"]:
        raise SystemExit("verified reference tokenizer unavailable")
    write_json(out / f"{mode}-isolation.json", p1.isolation_receipt(Path(os.environ["HOME"]).parents[0]))
    if mode == "smoke":
        smoke = out / "smoke"
        smoke.mkdir(exist_ok=True)
        if not (smoke / "templates").exists():
            shutil.copytree(out / "templates", smoke / "templates")
        task = {**p1.SMOKE_TASK, "set": "primary"}
        execute(smoke, {**protocol, "tasks": [task]}, token, workers, [[0, "SMOKE", arm] for arm in ARMS],
                smoke / "results.jsonl")
    else:
        if (out / "results.jsonl").exists():
            raise SystemExit("results already exist; a study is never re-run in place")
        execute(out, protocol, token, workers, protocol["schedule"], out / "results.jsonl")
    return 0


def launch(out: Path, mode: str, workers: int) -> int:
    out = out.resolve()
    if not (out / "protocol.json").exists():
        raise SystemExit("run `prepare` first")
    env = p1.isolated_env(out / ("env" if mode == "run" else "smoke-env"))
    proc = subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).resolve()), "child", "--output", str(out),
                           "--mode", mode, "--workers", str(workers)],
                          env=env, cwd=str(out), input=p1.load_copilot_token() + "\n", text=True, encoding="utf-8")
    return proc.returncode


def analyze(out: Path) -> dict:
    protocol = json.loads((out / "protocol.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    for row in rows:  # recount every session from raw captures; any mismatch aborts the analysis
        if row["status"] != "not_run" and p1.usage_from_captures(
                out / "runs" / row["session"] / "session/captures.jsonl") != row["usage"]:
            raise SystemExit(f"recount mismatch for {row['session']}")
    chosen = p1.final_rows(rows)
    repeats = sorted({r["repeat"] for r in rows})
    tasks = [t["id"] for t in protocol["tasks"]]
    arms = {}
    for arm in ARMS:
        group = [r for (t, a, _), r in chosen.items() if a == arm and t in tasks]
        valid = [r for r in group if r["status"] in ("pass", "fail")]
        passes = sum(r["status"] == "pass" for r in valid)
        tools: Counter = Counter()
        for r in valid:
            tools.update(r["tool_calls"])
        first = [f for f in (first_call_cache(out / "runs" / r["session"] / "session/captures.jsonl") for r in valid) if f]
        arms[arm] = {"graded": len(valid), "passes": passes, "success_ci95": p1.wilson(passes, len(valid)),
                     "infra_excluded": sum(r["status"] == "infra" for r in group),
                     "estimated_token_calls": sum(r["usage"].get("estimated_calls", 0) for r in valid),
                     "failure_reasons": dict(Counter(r["why"].split(":")[0] for r in group if r["status"] != "pass")),
                     "totals": {e: round(sum(p2.endpoint_value(r["usage"], e) for r in valid), 1) for e in p2.ENDPOINTS},
                     "cached": sum(r["usage"]["cached"] for r in valid), "tool_calls": dict(tools.most_common()),
                     "nav_calls_per_session": round(sum(tools[n] for n in NAV_TOOLS) / max(1, len(valid)), 2),
                     "first_call_cached_share": round(sum(c for _, c in first) / max(1, sum(i for i, _ in first)), 4)}
    comparisons, seed = [], SEED
    for family, pairs in FAMILIES.items():
        entries = []
        for arm, ref in pairs:
            entry = {"family": family, "arm": arm, "reference": ref}
            for endpoint in p2.ENDPOINTS:
                with mock.patch.object(p1, "wilcoxon_exact", wilcoxon_exact):  # same p-values, computed fast
                    entry[endpoint] = p2.compare(chosen, tasks, repeats, arm, ref, endpoint, seed)
                seed += 1
            entries.append(entry)
        for entry, adjusted in zip(entries, p1.holm([e["cost"]["wilcoxon_p"] for e in entries]), strict=True):
            primary = entry["cost"]
            primary["holm_p"] = round(adjusted, 5)
            quality_ok = primary["paired_passes"][0] >= primary["paired_passes"][1]
            if primary["change_ci95"][1] < 0 and adjusted < 0.05:
                entry["verdict"] = "lower cost" + ("" if quality_ok else " but lower success")
            elif primary["change_ci95"][0] > 0 and adjusted < 0.05:
                entry["verdict"] = "higher cost"
            else:
                entry["verdict"] = "no significant cost difference"
        comparisons += entries
    summary = {"study": "PRS-3", "protocol_sha256": sha256_file(out / "protocol.json"),
               "harness_sha256": protocol["harness_sha256"], "tasks_sha256": protocol["tasks_sha256"],
               "model": protocol["model"], "sessions_recorded": len(rows), "tasks": tasks, "arms": arms,
               "comparisons": comparisons}
    lines = ["# PRS-3 results (generated by `run_prs3_study.py analyze`)", "",
             f"{len(tasks)} fresh blind tasks x {len(ARMS)} arms x {len(repeats)} repeats.", "",
             "| Arm | Passed | Cost | Raw tokens | Uncached | Calls | Nav calls/session | First-call cached share |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for arm, a in arms.items():
        t = a["totals"]
        lines.append(f"| {arm} | {a['passes']}/{a['graded']} | {t['cost']:,.0f} | {t['raw_tokens']:,.0f} | "
                     f"{t['uncached']:,.0f} | {t['calls']:,.0f} | {a['nav_calls_per_session']} | "
                     f"{a['first_call_cached_share']:.1%} |")
    lines += ["", "| Family | Comparison | Cost change (95% CI) | Holm p | Raw-token change | Passed (paired) | Verdict |",
              "| --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for c in comparisons:
        p, r = c["cost"], c["raw_tokens"]
        lines.append(f"| {c['family']} | {c['arm']} vs {c['reference']} | {p['change'] * 100:+.1f}% "
                     f"[{p['change_ci95'][0] * 100:+.1f}%, {p['change_ci95'][1] * 100:+.1f}%] | {p['holm_p']} | "
                     f"{r['change'] * 100:+.1f}% | {p['paired_passes'][0]} vs {p['paired_passes'][1]} | {c['verdict']} |")
    write_json(out / "summary.json", summary)
    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return summary


def self_test() -> None:
    assert strip_logical(LOGICAL_ROOT + r"\pkg\a.py::f") == r"pkg\a.py::f"
    assert strip_logical("c:/work/tokenmaster/pkg/a.py:1-3") == "pkg/a.py:1-3"
    assert strip_logical(r"C:\work/tokenmaster\x/y") == "x/y" and strip_logical(LOGICAL_ROOT) == ""
    assert strip_logical(r"C:\work\tokenmaster2\x") == r"C:\work\tokenmaster2\x" and strip_logical(3) == 3
    assert [arm_spec(a)["hint"] for a in ARMS] == [None, None, "thrift", "nav"]
    assert [arm_spec(a)["v6"] for a in ARMS] == [False, True, True, True]
    assert {a for pairs in FAMILIES.values() for pair in pairs for a in pair} == set(ARMS)
    assert SKILL / "brainspace/compressors/__init__.py" in product_sources()
    assert not any("tests" in p.parts for p in product_sources())
    rng = random.Random(7)
    for n in range(13):  # the fast Wilcoxon must match the frozen enumeration exactly, ties and zeros included
        for _ in range(25):
            diffs = [rng.choice([0, 1e-7, 1, -1, 2, -2, 2.5, -3, rng.uniform(-9, 9)]) for _ in range(n)]
            assert wilcoxon_exact(diffs) == p1.wilcoxon_exact(diffs), diffs
    started = time.monotonic()
    wilcoxon_exact([rng.uniform(-9, 9) for _ in range(24)])
    assert time.monotonic() - started < 1
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "pkg").mkdir()
        (root / "pkg/a.py").write_text("def f():\n    return g()\n\n\ndef g():\n    return 1\n", encoding="utf-8")
        capture = {"output": json.dumps({"usage": {"input_tokens": 900, "input_tokens_details": {"cached_tokens": 600}}})}
        (root / "captures.jsonl").write_text(json.dumps(capture) + "\n" + json.dumps(capture) + "\n", encoding="utf-8")
        assert first_call_cache(root / "captures.jsonl") == (900, 600) and first_call_cache(root / "none") is None
        index = symbol_index.SymbolIndex(root)
        try:
            located = symbol_index.dispatch(index, "locate", {"query": strip_logical(LOGICAL_ROOT + r"\pkg\a.py")})
            assert located.startswith("pkg/a.py: 2 symbols"), located
            assert "pkg/a.py:2 f" in symbol_index.dispatch(index, "impact", {"symbol": "g", "depth": 1})
        finally:
            index.close()
    print("self-test passed")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("self-test", "prepare", "smoke", "run", "analyze", "child"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tasks", type=Path, default=PLUGIN / "evals/prs3_tasks.json")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--mode", choices=("smoke", "run"), default="run")
    args = parser.parse_args(argv)
    if args.command == "self-test":
        self_test()
        return 0
    if args.output is None:
        parser.error("--output is required")
    if args.command == "prepare":
        prepare(args.output.resolve(), args.tasks.resolve())
        return 0
    if args.command in ("smoke", "run"):
        return launch(args.output, args.command, args.workers)
    if args.command == "child":
        return child_main(args.output.resolve(), args.mode, args.workers)
    analyze(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
