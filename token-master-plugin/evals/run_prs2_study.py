"""PRS-2: pre-registered live study of TokenMaster request-policy-v6 on real repository tasks.

Protocol: token-master-plugin/docs/PRS2_PROTOCOL.md (written before any study call).

The primary endpoint is cost, not raw tokens:
    cost = uncached input + 0.1 x cached input + 8 x output
so prompt caching counts the way providers bill it. Arms share the model, tasks, frozen
snapshot, Copilot CLI system prompt, tools, limits and oracle (all reused unchanged from
run_prs1_study.py):

  stock      Copilot-CLI-shaped agent with parallel tool calls; no TokenMaster
  tm6        stock + TokenMaster runtime with request-policy-v6 (cache-native shaping)
  tm6_graph  tm6 + graphify-nav/codegraph MCP tools and the shipped routing agent text

Every session shows the same logical working directory, as real sessions in one
repository do, so the system prompt can be cached across sessions in every arm.

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
import threading
import time

EVALS = Path(__file__).resolve().parent
if str(EVALS) not in sys.path:  # isolated child processes (-I) do not add the script folder
    sys.path.insert(0, str(EVALS))

import run_prs1_study as p1  # noqa: E402
from run_prs1_study import PLUGIN, REPO, SKILL, sha256_bytes, sha256_file, write_json  # noqa: E402

from brainspace.request_policy import RequestPolicy  # noqa: E402
from brainspace.runtime import ExecutedToolResult, RuntimeSession  # noqa: E402
from brainspace.runtime_policy import RuntimePolicy  # noqa: E402
from brainspace.runtime_resources import RuntimeResources  # noqa: E402
from brainspace.transport import parse_json  # noqa: E402

SEED = 20261019
REPEATS = 3
MAX_CALLS = 30
TOKEN_CAP = 60_000_000
LOGICAL_ROOT = r"C:\work\tokenmaster"
ARMS = ("stock", "tm6", "tm6_graph")
COMPARISONS = (("tm6", "stock"), ("tm6_graph", "stock"), ("tm6_graph", "tm6"))
SETS = ("primary", "secondary")
# (cached weight, output weight, cache-write premium); "cost" is the pre-declared primary endpoint.
ENDPOINTS = {"cost": (0.1, 8.0, 0.0), "cost_w0.25": (0.25, 8.0, 0.0), "cost_r4": (0.1, 4.0, 0.0),
             "cost_write1.25": (0.1, 8.0, 0.25), "raw_tokens": None, "uncached": "uncached", "calls": "calls"}


def arm_spec(arm: str) -> dict:
    return {"parallel": True, "graph": arm == "tm6_graph", "v6": arm in ("tm6", "tm6_graph"),
            "ponytail": False, "headroom": False}


def runtime_config(spec: dict):
    if spec["v6"]:
        return RuntimePolicy(backend="local", request_policy=RequestPolicy(version="request-policy-v6", enabled=True),
                             require_nonexpanding_input=True), RuntimeResources()
    return RuntimePolicy(), RuntimeResources()


def endpoint_value(usage: dict, endpoint: str) -> float:
    rule = ENDPOINTS[endpoint]
    uncached = usage["input"] - usage["cached"]
    if rule is None:
        return usage["input"] + usage["output"]
    if rule == "uncached":
        return uncached
    if rule == "calls":
        return usage["calls"]
    cached_weight, output_weight, write_premium = rule
    return (uncached + cached_weight * usage["cached"] + output_weight * usage["output"]
            + write_premium * usage["cache_write"])


class MappedTools(p1.WorkspaceTools):
    """Shows every session the same logical root and maps it to the private copy."""

    def _resolve(self, path):
        if isinstance(path, str):
            text = path.strip().replace("/", "\\")
            if text.lower() == LOGICAL_ROOT.lower() or text.lower().startswith(LOGICAL_ROOT.lower() + "\\"):
                path = str(self.root) + text[len(LOGICAL_ROOT):]
        return super()._resolve(path)

    def execute(self, name: str, args: dict) -> ExecutedToolResult:
        result = super().execute(name, args)
        # Never reveal the private copy (its path names the task and the arm).
        return ExecutedToolResult(result.content.replace(str(self.root), LOGICAL_ROOT), result.status)


# --------------------------------------------------------------------------- prepare

def prepare(out: Path, tasks_file: Path) -> None:
    if out.exists():
        raise SystemExit(f"output must be new: {out}")
    out.mkdir(parents=True)
    tar = out / "snapshot.tar"
    subprocess.run([str(p1.GIT_EXE), "archive", "--format=tar", "-o", str(tar), p1.SNAPSHOT_COMMIT,
                    *p1.SNAPSHOT_PATHS], cwd=REPO, check=True)
    templates = {}
    for name in ("plain", "graph"):
        root = out / "templates" / name
        root.mkdir(parents=True)
        with tarfile.open(tar) as archive:
            archive.extractall(root, filter="data")
        subprocess.run([str(p1.GIT_EXE), "init", "-q"], cwd=root, check=True)
        templates[name] = root
    graph_receipt = p1.build_graph_indexes(templates["graph"])
    manifest = p1.manifest(templates["plain"])
    if p1.manifest(templates["graph"]) != manifest:
        raise SystemExit("visible workspace differs between plain and graph templates")
    prompt, view_tool = p1.load_copilot_prompt()
    system_prompt = p1.adapt_copilot_prompt(prompt)
    servers = p1.start_graph_servers(templates["graph"], p1.isolated_env(out / "prepare-env"), out / "prepare-logs")
    try:
        graph_tools = p1.mcp_tool_specs(servers)
    finally:
        for server in servers.values():
            server.close()
    tasks = json.loads(tasks_file.read_text(encoding="utf-8"))["tasks"]
    p1.validate_tasks(tasks, templates["plain"])
    if {t["set"] for t in tasks} != set(SETS):
        raise SystemExit("every task needs set=primary|secondary")
    from brainspace import tokens
    jobs = []
    for repeat in range(1, REPEATS + 1):
        block = [[repeat, t["id"], arm] for t in tasks for arm in ARMS]
        random.Random(SEED + repeat).shuffle(block)
        jobs += block
    protocol = {
        "study": "PRS-2", "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": p1.MODEL, "reasoning_effort": "low", "max_output_tokens": 4096, "max_calls_per_session": MAX_CALLS,
        "intent": "conservative (production default for every task)", "seed": SEED, "repeats": REPEATS,
        "logical_root": LOGICAL_ROOT, "arms": {arm: arm_spec(arm) for arm in ARMS},
        "comparisons": [list(c) for c in COMPARISONS], "endpoints": {k: v for k, v in ENDPOINTS.items()},
        "primary_endpoint": "cost = uncached input + 0.1 x cached input + 8 x output, per session, primary task set",
        "token_cap": TOKEN_CAP,
        "snapshot": {"commit": p1.SNAPSHOT_COMMIT, "paths": list(p1.SNAPSHOT_PATHS), "tar_sha256": sha256_file(tar),
                     "visible_files": len(manifest),
                     "manifest_sha256": sha256_bytes(json.dumps(manifest, sort_keys=True).encode())},
        "graph_index": graph_receipt,
        "system_prompt": system_prompt, "system_prompt_sha256": sha256_bytes(system_prompt.encode()),
        "system_prompt_tokens_cl100k": tokens.count_tokens(system_prompt),
        "graph_agent_text": p1.agent_text(),
        "tools": {"base": [view_tool, *p1.BASE_TOOL_SPECS], "graph": graph_tools},
        "tasks": tasks, "tasks_sha256": sha256_file(tasks_file), "schedule": jobs,
        "harness_sha256": sha256_file(Path(__file__)), "shared_harness_sha256": sha256_file(Path(p1.__file__)),
        "protocol_doc_sha256": sha256_file(PLUGIN / "docs/PRS2_PROTOCOL.md"),
        "product_sources_sha256": {p.relative_to(REPO).as_posix(): sha256_file(p) for p in sorted(
            [*(SKILL / "brainspace").glob("*.py"), SKILL / "graphify_mcp.py", SKILL / "agent.template.copilot.md"])},
    }
    write_json(out / "protocol.json", protocol)
    print(f"prepared {out}: {len(tasks)} tasks x {len(ARMS)} arms x {REPEATS} repeats = {len(jobs)} sessions")


# --------------------------------------------------------------------------- execution

class Study:
    def __init__(self, out: Path, protocol: dict, urls: dict[str, str], env: dict):
        self.out, self.protocol, self.urls, self.env = out, protocol, urls, env
        self.lock = threading.Lock()
        self.tokens_used = 0

    def run_session(self, task: dict, arm: str, repeat: int, suffix: str = "") -> dict:
        spec = arm_spec(arm)
        sid = f"{task['id']}-{arm}-r{repeat}{suffix}"
        run_dir, workspace = self.out / "runs" / sid, self.out / "ws" / sid
        template = self.out / "templates" / ("graph" if spec["graph"] else "plain")
        row = {"task": task["id"], "set": task["set"], "category": task["category"], "arm": arm,
               "repeat": repeat, "session": sid}
        with self.lock:
            over_cap = self.tokens_used >= TOKEN_CAP
        if over_cap:
            return {**row, "status": "not_run", "why": "token_cap"}
        run_dir.mkdir(parents=True)
        shutil.copytree(template, workspace)
        tools_impl, servers = MappedTools(workspace), {}
        tool_counts: Counter = Counter()
        final_text, failure, transformed = None, None, None
        started = time.monotonic()
        try:
            if spec["graph"]:
                servers = p1.start_graph_servers(workspace, self.env, run_dir / "mcp")
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
            if spec["graph"]:
                system += "\n\n" + self.protocol["graph_agent_text"]
            specs = self.protocol["tools"]["base"] + (self.protocol["tools"]["graph"] if spec["graph"] else [])
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
                            output = session.execute_tool(call, lambda n, a: p1.dispatch(n, a, tools_impl, servers))
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
            for server in servers.values():
                server.close()
        usage = p1.usage_from_captures(run_dir / "session/captures.jsonl")
        with self.lock:
            self.tokens_used += usage["input"] + usage["output"]
        status = "infra" if failure and failure.startswith("infra") else ("pass" if verdict["pass"] else "fail")
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
    env = p1.isolated_env(out / "env")
    gateways, urls = {}, {}
    try:
        for arm in ARMS:
            gateways[arm] = p1.start_gateway(token, out / f"gateway-{arm}.jsonl")
            urls[arm] = f"http://127.0.0.1:{gateways[arm].server_port}/v1"
        p1.warmup(urls, out)
        study = Study(out, protocol, urls, env)
        tasks = {t["id"]: t for t in protocol["tasks"]}
        lock = threading.Lock()

        def one(job, suffix=""):
            repeat, task_id, arm = job
            row = study.run_session(tasks[task_id], arm, repeat, suffix)
            p1.append_jsonl(results, row, lock)
            u = row.get("usage", {})
            print(f"[{row['session']:<28}] {row['status']:<6} calls={u.get('calls', 0):>2} "
                  f"cost={endpoint_value(u, 'cost') if u else 0:>9,.0f} why={row.get('why')}", flush=True)
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
    if (sha256_file(Path(__file__)) != protocol["harness_sha256"]
            or sha256_file(Path(p1.__file__)) != protocol["shared_harness_sha256"]):
        raise SystemExit("harness changed after prepare; re-run prepare (and disclose it)")
    for rel, digest in protocol["product_sources_sha256"].items():
        if sha256_file(REPO / rel) != digest:
            raise SystemExit(f"product source changed after prepare: {rel}")
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


# --------------------------------------------------------------------------- analysis

def compare(chosen: dict, tasks: list[str], repeats: list[int], arm: str, ref: str, endpoint: str, seed: int) -> dict:
    by_task: dict[str, list[tuple[float, float]]] = {}
    passes = [0, 0]
    for t in tasks:
        for r in repeats:
            a, b = chosen.get((t, arm, r)), chosen.get((t, ref, r))
            if a and b and a["status"] in ("pass", "fail") and b["status"] in ("pass", "fail"):
                by_task.setdefault(t, []).append((endpoint_value(a["usage"], endpoint),
                                                  endpoint_value(b["usage"], endpoint)))
                passes[0] += a["status"] == "pass"
                passes[1] += b["status"] == "pass"
    a_sum = sum(x for pairs in by_task.values() for x, _ in pairs)
    b_sum = sum(y for pairs in by_task.values() for _, y in pairs)
    diffs = [sum(x - y for x, y in pairs) / len(pairs) for pairs in by_task.values()]
    ci = p1.bootstrap_reduction(by_task, seed) if by_task else [0.0, 0.0]
    return {"pairs": sum(len(p) for p in by_task.values()), "arm_sum": round(a_sum, 1), "ref_sum": round(b_sum, 1),
            "change": round(a_sum / b_sum - 1, 4) if b_sum else None,
            "change_ci95": [round(-ci[1], 4), round(-ci[0], 4)],
            "tasks_lower": sum(x < 0 for x in diffs), "tasks_higher": sum(x > 0 for x in diffs),
            "wilcoxon_p": round(p1.wilcoxon_exact(diffs), 5), "paired_passes": passes}


def analyze(out: Path) -> dict:
    protocol = json.loads((out / "protocol.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    for row in rows:  # recount every session from raw captures; any mismatch aborts the analysis
        if row["status"] != "not_run" and p1.usage_from_captures(
                out / "runs" / row["session"] / "session/captures.jsonl") != row["usage"]:
            raise SystemExit(f"recount mismatch for {row['session']}")
    chosen = p1.final_rows(rows)
    repeats = sorted({r["repeat"] for r in rows})
    summary = {"study": "PRS-2", "protocol_sha256": sha256_file(out / "protocol.json"),
               "harness_sha256": protocol["harness_sha256"], "tasks_sha256": protocol["tasks_sha256"],
               "model": protocol["model"], "sessions_recorded": len(rows), "sets": {}}
    lines = ["# PRS-2 results (generated by `run_prs2_study.py analyze`)"]
    for index, task_set in enumerate(SETS):
        tasks = [t["id"] for t in protocol["tasks"] if t["set"] == task_set]
        arms = {}
        for arm in ARMS:
            group = [r for (t, a, _), r in chosen.items() if a == arm and t in tasks]
            valid = [r for r in group if r["status"] in ("pass", "fail")]
            passes = sum(r["status"] == "pass" for r in valid)
            tools: Counter = Counter()
            for r in valid:
                tools.update(r["tool_calls"])
            arms[arm] = {"graded": len(valid), "passes": passes, "success_ci95": p1.wilson(passes, len(valid)),
                         "infra_excluded": sum(r["status"] == "infra" for r in group),
                         "estimated_token_calls": sum(r["usage"].get("estimated_calls", 0) for r in valid),
                         "failure_reasons": dict(Counter(r["why"].split(":")[0] for r in group if r["status"] != "pass")),
                         "totals": {e: round(sum(endpoint_value(r["usage"], e) for r in valid), 1) for e in ENDPOINTS},
                         "cached": sum(r["usage"]["cached"] for r in valid),
                         "tool_calls": dict(tools.most_common())}
        comparisons = []
        for number, (arm, ref) in enumerate(COMPARISONS):
            entry = {"arm": arm, "reference": ref}
            for endpoint in ENDPOINTS:
                entry[endpoint] = compare(chosen, tasks, repeats, arm, ref, endpoint, SEED + 100 * index + number)
            comparisons.append(entry)
        for entry, adjusted in zip(comparisons, p1.holm([c["cost"]["wilcoxon_p"] for c in comparisons]), strict=True):
            primary = entry["cost"]
            primary["holm_p"] = round(adjusted, 5)
            quality_ok = primary["paired_passes"][0] >= primary["paired_passes"][1]
            if primary["change_ci95"][1] < 0 and adjusted < 0.05:
                entry["verdict"] = "lower cost" + ("" if quality_ok else " but lower success")
            elif primary["change_ci95"][0] > 0 and adjusted < 0.05:
                entry["verdict"] = "higher cost"
            else:
                entry["verdict"] = "no significant cost difference"
        summary["sets"][task_set] = {"tasks": tasks, "arms": arms, "comparisons": comparisons}
        lines += ["", f"## {task_set} tasks ({'confirmatory' if task_set == 'primary' else 'exposed, from PRS-1'})", "",
                  "| Arm | Passed | Cost | Raw tokens | Uncached | Calls |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
        for arm, a in arms.items():
            t = a["totals"]
            lines.append(f"| {arm} | {a['passes']}/{a['graded']} | {t['cost']:,.0f} | {t['raw_tokens']:,.0f} | "
                         f"{t['uncached']:,.0f} | {t['calls']:,.0f} |")
        lines += ["", "| Comparison | Cost change (95% CI) | Holm p | Raw-token change | Passed (paired) | Verdict |",
                  "| --- | ---: | ---: | ---: | ---: | --- |"]
        for c in comparisons:
            p, r = c["cost"], c["raw_tokens"]
            lines.append(f"| {c['arm']} vs {c['reference']} | {p['change'] * 100:+.1f}% "
                         f"[{p['change_ci95'][0] * 100:+.1f}%, {p['change_ci95'][1] * 100:+.1f}%] | {p['holm_p']} | "
                         f"{r['change'] * 100:+.1f}% | {p['paired_passes'][0]} vs {p['paired_passes'][1]} | "
                         f"{c['verdict']} |")
    write_json(out / "summary.json", summary)
    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return summary


def self_test() -> None:
    usage = {"calls": 2, "input": 1000, "cached": 600, "cache_write": 100, "output": 50, "reasoning": 0}
    assert endpoint_value(usage, "cost") == 400 + 60 + 400
    assert endpoint_value(usage, "cost_write1.25") == 400 + 60 + 400 + 25
    assert endpoint_value(usage, "raw_tokens") == 1050 and endpoint_value(usage, "calls") == 2
    tools = MappedTools(SKILL)
    assert tools._resolve(LOGICAL_ROOT + r"\brainspace\tokens.py") == (SKILL / "brainspace/tokens.py").resolve()
    assert tools._resolve("C:/work/tokenmaster/brainspace") == (SKILL / "brainspace").resolve()
    assert tools.execute("view", {"path": r"C:\elsewhere\x.py"}).status == "error"
    escape = tools.execute("view", {"path": LOGICAL_ROOT + r"\..\x.py"})
    assert escape.status == "error" and str(SKILL) not in escape.content and LOGICAL_ROOT in escape.content
    print("self-test passed")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("self-test", "prepare", "smoke", "run", "analyze", "child"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tasks", type=Path, default=PLUGIN / "evals/prs2_tasks.json")
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
