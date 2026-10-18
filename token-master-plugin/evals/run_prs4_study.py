"""PRS-4: pre-registered live study of TokenMaster v7 plus a cache-stable system prompt.

Protocol: token-master-plugin/docs/PRS4_PROTOCOL.md (written before any study call).
Primary endpoint: billed cost per finished task, priced with the provider's own price table
(copilot_usage in every response): uncached input 1, cache read 0.1, cache write 1.25, output 5.

  stock  Copilot-CLI-shaped agent with parallel tool calls; no TokenMaster (as in PRS-3)
  tm7    stock + request-policy-v6 + v7 navigation tools and hint (as in PRS-3)
  tm8    tm7 + the native route's stable_session_prefix: Copilot CLI's per-session folder line
         moves from the system prompt to the first user message, so sessions share a cached prefix

Model, prompt, base tools, oracle, gateway, logical working directory, schedule rules and
statistics are reused unchanged from run_prs1_study.py, run_prs2_study.py and run_prs3_study.py.

Subcommands: self-test | prepare | smoke | run | analyze
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
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
import run_prs3_study as p3  # noqa: E402
from run_prs1_study import PLUGIN, REPO, sha256_bytes, sha256_file, write_json  # noqa: E402

from brainspace import symbol_index  # noqa: E402
from brainspace.native_transport import SESSION_FOLDER_MOVED, stable_session_prefix  # noqa: E402
from brainspace.runtime import ExecutedToolResult, RuntimeSession  # noqa: E402
from brainspace.transport import parse_json  # noqa: E402

SEED = 20261021
REPEATS = 5
MAX_CALLS = p3.MAX_CALLS
TOKEN_CAP = p3.TOKEN_CAP
LOGICAL_ROOT = p2.LOGICAL_ROOT
ARMS = ("stock", "tm7", "tm8")
# Holm runs within each family. "primary" answers the study question; "attribution" isolates the
# cache-stable system prompt.
FAMILIES = {"primary": (("tm8", "stock"), ("tm7", "stock")), "attribution": (("tm8", "tm7"),)}
QUOTA = p3.QUOTA
# The provider's own price table, relative to one uncached input token (copilot_usage.token_details).
PRICES = {"input": 1.0, "cache_read": 0.1, "cache_write": 1.25, "output": 5.0}
# endpoint rule (cached weight, output weight, write premium) over usage: (input - cached) is billed at 1,
# so a written token costs 1 + 0.25 = 1.25.
ENDPOINTS = {**p2.ENDPOINTS, "billed": (0.1, 5.0, 0.25)}
GOAL = 0.30  # tm8 must cost at least 30% less than stock per finished task ...
QUALITY_SLACK = 3  # ... and pass at least as many sessions as stock minus 3
WARM_SHARE = 0.5  # a first call that read at least half its input from the cache started warm
WORKERS = 8  # concurrency is part of the usage regime, so it is frozen
# Smoke sessions get their own system prompt, so they cannot warm the study's cached prefix.
SMOKE_SUFFIX = "\n\n(Smoke check run.)"


def arm_spec(arm: str) -> dict:
    return {"parallel": True, "v6": arm != "stock", "nav": arm != "stock",
            "hint": None if arm == "stock" else "nav", "stable_prefix": arm == "tm8"}


@dataclass(frozen=True)
class StablePrefixTransport(p1.StudyTransport):
    """tm8: each request gets the native route's own rewrite (native_transport.stable_session_prefix)."""

    def encode(self, chat: dict) -> str:
        return p1._json(stable_session_prefix(parse_json(super().encode(chat))))


def billed(usage: dict) -> float:
    """A session's bill in uncached-input-token units, from provider-reported usage."""
    return (usage["input"] - usage["cached"] - usage["cache_write"] + PRICES["cache_read"] * usage["cached"]
            + PRICES["cache_write"] * usage["cache_write"] + PRICES["output"] * usage["output"])


def provider_bill(path: Path) -> tuple[float, set]:
    """Sum of every call's own bill (copilot_usage.token_details) in input-token units, and the (type, price) seen."""
    total, seen = 0.0, set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            details = json.loads(json.loads(line)["output"])["copilot_usage"]["token_details"]
        except (KeyError, TypeError, ValueError):
            continue
        rate = {d["token_type"]: d["cost_per_batch"] / d["batch_size"] for d in details}
        total += sum(d["token_count"] * rate[d["token_type"]] for d in details) / rate["input"]
        seen |= {(kind, round(value / rate["input"], 6)) for kind, value in rate.items()}
    return total, seen


def cold_usage(usage: dict, first_cached: int) -> dict:
    """The same session if its first call had found nothing in the cache (no session within the cache lifetime)."""
    return {**usage, "cached": usage["cached"] - first_cached, "cache_write": usage["cache_write"] + first_cached}


def finished_task_change(chosen: dict, tasks: list[str], repeats: list[int], arm: str, ref: str, seed: int,
                         rounds: int = 2000) -> dict:
    """Change in billed cost per finished task over the sessions p2.compare pairs, with a two-stage cluster
    bootstrap 95% CI (tasks, then sessions within each task)."""
    by_task: dict[str, list[tuple]] = {}
    for t in tasks:
        for r in repeats:
            a, b = chosen.get((t, arm, r)), chosen.get((t, ref, r))
            if a and b and a["status"] in ("pass", "fail") and b["status"] in ("pass", "fail"):
                by_task.setdefault(t, []).append((billed(a["usage"]), a["status"] == "pass",
                                                  billed(b["usage"]), b["status"] == "pass"))

    def change(groups) -> float:
        cost_a, pass_a, cost_b, pass_b = (sum(row[i] for group in groups for row in group) for i in range(4))
        return (cost_a / pass_a) / (cost_b / pass_b) - 1 if pass_a and pass_b and cost_b else float("inf")

    groups = list(by_task.values())
    if not groups:
        return {"change": None, "ci95": [None, None]}
    rng = random.Random(seed)
    draws = sorted(change([[rng.choice(g) for _ in g] for g in (rng.choice(groups) for _ in groups)])
                   for _ in range(rounds))
    return {"change": round(change(groups), 4),
            "ci95": [round(draws[int(0.025 * rounds)], 4), round(draws[int(0.975 * rounds) - 1], 4)]}


def validate_design(tasks: list[dict]) -> None:
    if {t["set"] for t in tasks} != {"primary"}:
        raise SystemExit("every PRS-4 task is a fresh primary task (set=primary)")
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
    nav_receipt = p3.build_nav_index(templates["nav"])
    manifest = p1.manifest(templates["plain"])
    if p1.manifest(templates["nav"]) != manifest:
        raise SystemExit("visible workspace differs between plain and nav templates")
    prompt, view_tool = p1.load_copilot_prompt()
    system_prompt = p1.adapt_copilot_prompt(prompt)
    probe = {"input": [{"role": "system", "content": system_prompt.replace(p1.SESSION_TOKEN, "C:/s/session-state/x")},
                       {"role": "user", "content": "task"}]}
    if stable_session_prefix(probe) is probe:  # the treatment must apply to the frozen prompt
        raise SystemExit("tm8's rewrite does not apply to the system prompt")
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
        "study": "PRS-4", "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": p1.MODEL, "reasoning_effort": "low", "max_output_tokens": 4096, "max_calls_per_session": MAX_CALLS,
        "intent": "conservative (production default for every task)", "seed": SEED, "repeats": REPEATS,
        "logical_root": LOGICAL_ROOT, "arms": {arm: arm_spec(arm) for arm in ARMS},
        "families": {family: [list(c) for c in pairs] for family, pairs in FAMILIES.items()},
        "endpoints": dict(ENDPOINTS), "prices_relative_to_input": PRICES,
        "primary_endpoint": "billed cost per finished task = sum over all sessions of (input - cached) "
                            "+ 0.1 x cached + 0.25 x cache_write + 5 x output, divided by passed sessions",
        "goal_rule": {"comparison": ["tm8", "stock"], "max_change": -GOAL, "holm_p_below": 0.05,
                      "quality": f"tm8 passes >= stock passes - {QUALITY_SLACK}",
                      "confident_if": "95% CI upper bound <= -0.30"},
        "usage_regime": "continuous: all sessions of one repository run back to back with 8 workers, in the "
                        "shuffled schedule below; a tm8 session starts warm when another tm8 session wrote the "
                        "shared prefix within the provider's cache lifetime",
        "workers": WORKERS, "smoke_suffix": SMOKE_SUFFIX,
        "warm_share": WARM_SHARE, "sensitivity": ["tm8_cold (first call re-priced as a cache miss)",
                                                  "cost (PRS-3 metric)", "cost_write1.25"],
        "token_cap": TOKEN_CAP,
        "snapshot": {"commit": p1.SNAPSHOT_COMMIT, "paths": list(p1.SNAPSHOT_PATHS), "tar_sha256": sha256_file(tar),
                     "visible_files": len(manifest),
                     "manifest_sha256": sha256_bytes(json.dumps(manifest, sort_keys=True).encode())},
        "nav_index": nav_receipt,
        "system_prompt": system_prompt, "system_prompt_sha256": sha256_bytes(system_prompt.encode()),
        "system_prompt_tokens_cl100k": tokens.count_tokens(system_prompt),
        "nav_hint": p3.NAV_HINT, "nav_hint_tokens_cl100k": tokens.count_tokens(p3.NAV_HINT),
        "stable_prefix_line": SESSION_FOLDER_MOVED,
        "tools": {"base": [view_tool, *p1.BASE_TOOL_SPECS], "nav": symbol_index.TOOL_SPECS},
        "nav_tool_tokens_cl100k": tokens.count_tokens(json.dumps(symbol_index.TOOL_SPECS)),
        "tasks": tasks, "tasks_file": str(tasks_file), "tasks_sha256": sha256_file(tasks_file), "schedule": jobs,
        "harness_sha256": sha256_file(Path(__file__)), "shared_harness_sha256": sha256_file(Path(p1.__file__)),
        "shared_harness2_sha256": sha256_file(Path(p2.__file__)),
        "shared_harness3_sha256": sha256_file(Path(p3.__file__)),
        "protocol_doc_sha256": sha256_file(PLUGIN / "docs/PRS4_PROTOCOL.md"),
        "product_sources_sha256": {p.relative_to(REPO).as_posix(): sha256_file(p) for p in p3.product_sources()},
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
              "shared harness 3": (Path(p3.__file__), protocol["shared_harness3_sha256"]),
              "protocol document": (PLUGIN / "docs/PRS4_PROTOCOL.md", protocol["protocol_doc_sha256"]),
              "tasks": (Path(protocol["tasks_file"]), protocol["tasks_sha256"]),
              "graph": (out / "templates/nav/.token-master/graph.json", protocol["nav_index"]["graph_sha256"]),
              "symbol index": (out / "templates/nav/.token-master/symbols.sqlite",
                               protocol["nav_index"]["symbols_sha256"])}
    frozen.update({rel: (REPO / rel, digest) for rel, digest in protocol["product_sources_sha256"].items()})
    current = {p.relative_to(REPO).as_posix() for p in p3.product_sources()}
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
                    output = symbol_index.dispatch(index, name, {k: p3.strip_logical(v) for k, v in args.items()})
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
            policy, resources = p3.runtime_config(spec)
            transport_class = StablePrefixTransport if spec["stable_prefix"] else p1.StudyTransport
            transport = transport_class(
                base_url=self.urls[arm], model=p1.MODEL, allow_network=True, max_output_tokens=4096,
                max_request_bytes=4_000_000, max_response_bytes=4_000_000, timeout=90, reasoning_effort="low",
                parallel=spec["parallel"], cache_key=sha256_bytes(sid.encode())[:32])
            session = RuntimeSession(workspace=workspace, session_id=sid, output=run_dir / "session",
                                     transport=transport, runtime_policy=policy, runtime_resources=resources,
                                     task_id=task["id"], max_calls=MAX_CALLS)
            session_folder = "C:/Users/dev/.copilot/session-state/" + sha256_bytes(sid.encode())[:32]
            system = (self.protocol["system_prompt"].replace(p1.CWD_TOKEN, LOGICAL_ROOT)
                      .replace(p1.SESSION_TOKEN, session_folder))
            if spec["hint"]:
                system += "\n\n" + self.protocol["nav_hint"]
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
                   transformed_requests=transformed, wall_seconds=round(time.monotonic() - started, 2),
                   started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - (time.monotonic() - started))))
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
                  f"billed={billed(u) if u else 0:>9,.0f} why={row.get('why')}", flush=True)
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
        # One worker: the second tm8 session shows whether the product's exact bytes start warm.
        execute(smoke, {**protocol, "tasks": [task], "system_prompt": protocol["system_prompt"] + SMOKE_SUFFIX},
                token, 1, [[0, "SMOKE", arm] for arm in ARMS] + [[1, "SMOKE", "tm8"]], smoke / "results.jsonl")
    else:
        if (out / "results.jsonl").exists():
            raise SystemExit("results already exist; a study is never re-run in place")
        if workers != protocol["workers"]:
            raise SystemExit(f"the frozen protocol runs with {protocol['workers']} workers")
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
    verify_frozen(out, protocol)  # the analysis code and rules must be the ones frozen at prepare
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    for row in rows:  # recount every session from raw captures; any mismatch aborts the analysis
        if row["status"] != "not_run" and p1.usage_from_captures(
                out / "runs" / row["session"] / "session/captures.jsonl") != row["usage"]:
            raise SystemExit(f"recount mismatch for {row['session']}")
    chosen = p1.final_rows(rows)
    repeats = sorted({r["repeat"] for r in rows})
    tasks = [t["id"] for t in protocol["tasks"]]
    captures = {key: out / "runs" / r["session"] / "session/captures.jsonl" for key, r in chosen.items()}
    # The primary endpoint prices usage with the provider's table; check it against every call's own bill.
    worst, prices = 0.0, set()
    for key, r in chosen.items():
        if r["status"] in ("pass", "fail"):
            bill, seen = provider_bill(captures[key])
            worst, prices = max(worst, abs(bill - billed(r["usage"]))), prices | seen
    if prices - set(PRICES.items()) or worst > 0.5:
        raise SystemExit(f"provider bills differ from the frozen price table: {sorted(prices)}, worst {worst}")
    first = {key: p3.first_call_cache(path) for key, path in captures.items()}
    for (t, a, r), row in list(chosen.items()):  # sensitivity: tm8 as if every session started cold
        if a == "tm8" and "usage" in row:
            chosen[(t, "tm8_cold", r)] = {**row, "arm": "tm8_cold",
                                          "usage": cold_usage(row["usage"], (first[(t, a, r)] or (0, 0))[1])}
    arms = {}
    for arm in (*ARMS, "tm8_cold"):
        group = [r for (t, a, _), r in chosen.items() if a == arm and t in tasks]
        valid = [r for r in group if r["status"] in ("pass", "fail")]
        passes = sum(r["status"] == "pass" for r in valid)
        tools: Counter = Counter()
        for r in valid:
            tools.update(r["tool_calls"])
        firsts = [f for f in (first[(r["task"], r["arm"], r["repeat"])] for r in valid if arm != "tm8_cold") if f]
        total = sum(billed(r["usage"]) for r in valid)
        arms[arm] = {"graded": len(valid), "passes": passes, "success_ci95": p1.wilson(passes, len(valid)),
                     "infra_excluded": sum(r["status"] == "infra" for r in group),
                     "failure_reasons": dict(Counter(r["why"].split(":")[0] for r in group if r["status"] != "pass")),
                     "billed_total": round(total, 1),
                     "billed_per_session": round(total / max(1, len(valid)), 1),
                     "billed_per_finished_task": round(total / passes, 1) if passes else None,
                     "calls_per_session": round(sum(r["usage"]["calls"] for r in valid) / max(1, len(valid)), 2),
                     "totals": {e: round(sum(p2.endpoint_value(r["usage"], e) for r in valid), 1)
                                for e in p2.ENDPOINTS},
                     "cached": sum(r["usage"]["cached"] for r in valid), "tool_calls": dict(tools.most_common()),
                     "nav_calls_per_session": round(sum(tools[n] for n in p3.NAV_TOOLS) / max(1, len(valid)), 2),
                     "first_call_cached_share": round(sum(c for _, c in firsts) / max(1, sum(i for i, _ in firsts)), 4),
                     "warm_starts": sum(c >= WARM_SHARE * i for i, c in firsts)}
    comparisons, seed = [], SEED
    plan = {**FAMILIES, "sensitivity": (("tm8_cold", "stock"),)}
    with mock.patch.dict(p2.ENDPOINTS, ENDPOINTS), mock.patch.object(p1, "wilcoxon_exact", p3.wilcoxon_exact):
        for family, pairs in plan.items():
            entries = []
            for arm, ref in pairs:
                entry = {"family": family, "arm": arm, "reference": ref}
                for endpoint in ENDPOINTS:
                    entry[endpoint] = p2.compare(chosen, tasks, repeats, arm, ref, endpoint, seed)
                    seed += 1
                entry["per_finished_task"] = finished_task_change(chosen, tasks, repeats, arm, ref, seed)
                seed += 1
                entries.append(entry)
            for entry, adjusted in zip(entries, p1.holm([e["billed"]["wilcoxon_p"] for e in entries]), strict=True):
                primary = entry["billed"]
                primary["holm_p"] = round(adjusted, 5)
                quality_ok = primary["paired_passes"][0] >= primary["paired_passes"][1]
                if family == "sensitivity":
                    entry["verdict"] = "n/a (sensitivity, no claim)"
                elif primary["change_ci95"][1] < 0 and adjusted < 0.05:
                    entry["verdict"] = "lower cost" + ("" if quality_ok else " but lower success")
                elif primary["change_ci95"][0] > 0 and adjusted < 0.05:
                    entry["verdict"] = "higher cost"
                else:
                    entry["verdict"] = "no significant cost difference"
            comparisons += entries
    main_entry = next(c for c in comparisons if (c["arm"], c["reference"]) == ("tm8", "stock"))
    finished = main_entry["per_finished_task"]
    quality = arms["tm8"]["passes"] >= arms["stock"]["passes"] - QUALITY_SLACK
    met = (finished["change"] is not None and finished["change"] <= -GOAL
           and main_entry["billed"]["holm_p"] < 0.05 and quality)
    goal = {"change_per_finished_task": finished["change"], "ci95": finished["ci95"],
            "holm_p": main_entry["billed"]["holm_p"], "quality_ok": quality, "met": met,
            "confident": met and finished["ci95"][1] <= -GOAL,
            "saving_per_session": round(arms["stock"]["billed_per_session"] - arms["tm8"]["billed_per_session"], 1)}
    summary = {"study": "PRS-4", "protocol_sha256": sha256_file(out / "protocol.json"),
               "harness_sha256": protocol["harness_sha256"], "tasks_sha256": protocol["tasks_sha256"],
               "model": protocol["model"], "sessions_recorded": len(rows), "tasks": tasks,
               "billing_check": {"prices": dict(PRICES), "max_session_abs_diff": round(worst, 3)},
               "arms": arms, "comparisons": comparisons, "goal": goal}
    lines = ["# PRS-4 results (generated by `run_prs4_study.py analyze`)", "",
             f"{len(tasks)} fresh blind tasks x {len(ARMS)} arms x {len(repeats)} repeats. Primary endpoint: billed "
             "cost per finished task (provider prices: input 1, cache read 0.1, cache write 1.25, output 5). "
             "Regime: continuous use, 8 workers.", "",
             "| Arm | Passed | Billed per session | Billed per finished task | Calls/session | Nav calls/session "
             "| First-call cached share | Warm starts |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for arm, a in arms.items():
        lines.append(f"| {arm} | {a['passes']}/{a['graded']} | {a['billed_per_session']:,.0f} | "
                     f"{a['billed_per_finished_task'] or 0:,.0f} | {a['calls_per_session']} | "
                     f"{a['nav_calls_per_session']} | {a['first_call_cached_share']:.1%} | {a['warm_starts']} |")
    lines += ["", "| Family | Comparison | Per finished task (95% CI) | Billed, paired (95% CI) | Holm p "
              "| PRS-3 metric | Passed (paired) | Verdict |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for c in comparisons:
        p, f, old = c["billed"], c["per_finished_task"], c["cost"]
        lines.append(f"| {c['family']} | {c['arm']} vs {c['reference']} | {f['change'] * 100:+.1f}% "
                     f"[{f['ci95'][0] * 100:+.1f}%, {f['ci95'][1] * 100:+.1f}%] | {p['change'] * 100:+.1f}% "
                     f"[{p['change_ci95'][0] * 100:+.1f}%, {p['change_ci95'][1] * 100:+.1f}%] | {p['holm_p']} | "
                     f"{old['change'] * 100:+.1f}% | {p['paired_passes'][0]} vs {p['paired_passes'][1]} | {c['verdict']} |")
    lines += ["", f"Goal (tm8 at least 30% below stock per finished task, Holm p < 0.05, quality kept): "
              f"{'MET' if goal['met'] else 'NOT MET'}; whole 95% CI at or beyond -30%: "
              f"{'yes' if goal['confident'] else 'no'}. Saving per session: {goal['saving_per_session']:,.0f} "
              "input-token units."]
    write_json(out / "summary.json", summary)
    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return summary


def self_test() -> None:
    assert [arm_spec(a)["stable_prefix"] for a in ARMS] == [False, False, True]
    assert [arm_spec(a)["nav"] for a in ARMS] == [False, True, True] == [arm_spec(a)["v6"] for a in ARMS]
    assert {a for pairs in FAMILIES.values() for pair in pairs for a in pair} == set(ARMS)
    usage = {"calls": 2, "input": 1000, "cached": 600, "cache_write": 300, "output": 50, "reasoning": 0}
    assert billed(usage) == 100 + 60 + 375 + 250
    with mock.patch.dict(p2.ENDPOINTS, ENDPOINTS):
        assert p2.endpoint_value(usage, "billed") == billed(usage)
    assert billed(cold_usage(usage, 500)) == billed(usage) + 500 * (1.25 - 0.1)
    def session(cost, ok):
        return {"status": "pass" if ok else "fail", "usage": {**usage, "input": cost, "cached": 0, "cache_write": 0,
                                                               "output": 0}}
    chosen = {(t, arm, r): session(cost, ok) for t in ("A", "B") for r in (1, 2)
              for arm, cost, ok in (("x", 50, True), ("y", 100, True), ("z", 50, r == 1))}
    assert finished_task_change(chosen, ["A", "B"], [1, 2], "x", "y", 1) == {"change": -0.5, "ci95": [-0.5, -0.5]}
    assert finished_task_change(chosen, ["A", "B"], [1, 2], "z", "y", 1)["change"] == 0.0  # half the cost, half the passes
    details = [{"token_type": kind, "token_count": count, "cost_per_batch": int(price * 1e12), "batch_size": 1000000}
               for kind, count, price in (("input", 100, 1), ("cache_read", 600, 0.1), ("cache_write", 300, 1.25),
                                          ("output", 50, 5))]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "captures.jsonl"
        line = json.dumps({"output": json.dumps({"copilot_usage": {"token_details": details}})})
        path.write_text(line + "\n" + json.dumps({"output": "not json"}) + "\n", encoding="utf-8")
        bill, seen = provider_bill(path)
        assert abs(bill - billed(usage)) < 1e-6 and seen == set(PRICES.items()), (bill, seen)
    chat = {"model": p1.MODEL, "messages": [
        {"role": "system", "content": "Rules.\nSession folder: C:/Users/dev/.copilot/session-state/abc\nMore."},
        {"role": "user", "content": "Task."}]}
    settings = dict(base_url="http://127.0.0.1:1/v1", model=p1.MODEL, allow_network=False, max_output_tokens=4096,
                    reasoning_effort="low", parallel=True, cache_key="k" * 32)
    plain, moved = (json.loads(c(**settings).encode(chat)) for c in (p1.StudyTransport, StablePrefixTransport))
    assert SESSION_FOLDER_MOVED in moved["input"][0]["content"] and "abc" not in moved["input"][0]["content"]
    assert moved["input"][1]["content"].startswith("Session folder: C:/Users/dev/.copilot/session-state/abc\n\n")
    assert {k: v for k, v in moved.items() if k != "input"} == {k: v for k, v in plain.items() if k != "input"}
    print("self-test passed")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("self-test", "prepare", "smoke", "run", "analyze", "child"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tasks", type=Path, default=PLUGIN / "evals/prs4_tasks.json")
    parser.add_argument("--workers", type=int, default=WORKERS)
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
