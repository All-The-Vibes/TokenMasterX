"""Zero-cost probe (no model call): what Copilot CLI's built-in GitHub MCP server adds to every request.

Every TokenMaster study ran both arms with --disable-builtin-mcps, and the launcher does not add that flag, so a real
session under default sign-in carries the built-in GitHub MCP server's tools and no study measured them. This probe
starts a signed-in Copilot CLI session (an isolated home whose config.json names the operator's account; the token
stays in Credential Manager) in BYOK mode WITHOUT COPILOT_OFFLINE, so GitHub features stay on, and points the provider
at a local server that records each request and answers 502. Nothing reaches a model. The two arms differ only in
--disable-builtin-mcps. It records sizes and names only: cl100k tokens of the request, of the system text and of each
tool definition as sent (compact JSON), and which tools the GitHub MCP server owns.

Tools sent with defer_loading (the GitHub server's, behind a tool-search tool) are counted separately: a provider that
supports tool search shows the model only their namespace or name and loads the rest on demand.

  python probe.py <output json> [package ...] [--wire anthropic]       (default: 1.0.105, OpenAI Responses wire)
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import sys
import threading

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "token-master-plugin/evals"))
import default_routing_ab as dr  # noqa: E402
import run_prs5_study as p5  # noqa: E402
from brainspace import tokens  # noqa: E402  (on sys.path through run_prs1_study)

WIRES = {"openai": ("gpt-6-astra", {"COPILOT_PROVIDER_TYPE": "openai", "COPILOT_PROVIDER_WIRE_API": "responses",
                                    "COPILOT_PROVIDER_MAX_OUTPUT_TOKENS": "16000"}),
         # Copilot CLI 1.0.105 asks Claude models for 32,000 output tokens and refuses a lower advertised maximum
         "anthropic": ("claude-opus-5.5", {"COPILOT_PROVIDER_TYPE": "anthropic", "COPILOT_PROVIDER_MAX_OUTPUT_TOKENS": "64000"})}
WIRE = "openai"
PROMPT = "Reply with the single word ok."
ROOT = dr.LANES_ROOT / "gh-mcp-probe"  # outside the profile: nothing inherited from ancestor folders
REPEATS = 2


def flags() -> list[str]:
    return ["--model", WIRES[WIRE][0], "--reasoning-effort", "low", "--allow-all-tools", "--no-ask-user",
            "--output-format", "json"]


class Capture(ThreadingHTTPServer):
    """Records every request body and answers 502, so Copilot CLI gives up without a model call."""

    def __init__(self):
        self.requests: list[dict] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self):
                body = self.rfile.read(int(self.headers.get("content-length") or 0))
                server.requests.append({"method": self.command, "path": self.path, "body": body.decode("utf-8", "replace")})
                payload = b'{"error":{"message":"capture only","type":"server_error"}}'
                self.send_response(502)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_POST = do_GET = _answer

            def log_message(self, *args):
                pass

        super().__init__(("127.0.0.1", 0), Handler)


def lane_env(home: Path, url: str) -> dict:
    """Default-routing lane environment (signed in, pinned package), switched to BYOK on the capture server."""
    model, provider = WIRES[WIRE]
    env = dr.cli_env(home)
    env.update({"COPILOT_PROVIDER_BASE_URL": url, "COPILOT_PROVIDER_API_KEY": "capture-only",
                "COPILOT_PROVIDER_MODEL_ID": model, "COPILOT_PROVIDER_WIRE_MODEL": model,
                "COPILOT_PROVIDER_MAX_PROMPT_TOKENS": "200000", **provider})
    assert "COPILOT_OFFLINE" not in env
    return env


def _count(obj) -> int:
    return tokens.count_tokens(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


def sizes(body: str) -> dict:
    """Responses (instructions/input, namespace tools) or Messages (system, flat tools) request sizes."""
    request = json.loads(body)
    tools, deferred = {}, {}
    for tool in request.get("tools") or []:
        name = tool.get("name") or tool.get("type") or "?"
        tools[name] = _count(tool)
        for sub in tool.get("tools") or []:  # a namespace's functions
            if sub.get("defer_loading"):
                deferred[sub.get("name") or "?"] = _count(sub)
        if tool.get("defer_loading"):
            deferred[name] = _count(tool)
    system = request.get("instructions") or ""
    top = request.get("system")
    system += top if isinstance(top, str) else "".join(b.get("text", "") for b in top or [] if isinstance(b, dict))
    for item in request.get("input") or []:
        if isinstance(item, dict) and item.get("role") in ("system", "developer"):
            content = item.get("content")
            system += content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return {"request_cl100k": tokens.count_tokens(body), "system_cl100k": tokens.count_tokens(system),
            "tools_cl100k": sum(tools.values()), "tool_count": len(tools), "tools": tools,
            "deferred_cl100k": sum(deferred.values()), "deferred": sorted(deferred),
            "github_mentions_in_system": system.lower().count("github-mcp-server")}


def run(package: str, arm: str, repeat: int) -> dict:
    base = ROOT / WIRE / package / arm / f"r{repeat}"
    home, lane = base / "home", base / "lane"
    for path in (home / "copilot" / "session-state", lane):
        shutil.rmtree(path, ignore_errors=True)
    lane.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(lane)], check=True)
    (lane / "README.md").write_text("probe lane\n", encoding="utf-8")
    dr.PACKAGE = package
    with Capture() as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        env = lane_env(home, f"http://127.0.0.1:{server.server_address[1]}")
        version = subprocess.run([dr.LAUNCHER, "--version"], env=env, capture_output=True, text=True, timeout=180,
                                 stdin=subprocess.DEVNULL).stdout.strip().splitlines()[0]
        p5.SESSION_TIMEOUT = 90  # Copilot CLI retries the 502 for a while; the first requests are enough
        args = flags() + (["--disable-builtin-mcps"] if arm == "builtin-mcps-off" else [])
        code, out, err = p5.run_copilot([str(dr.LAUNCHER), "-p", PROMPT, *args], lane, env)
        server.shutdown()
        posts = [r for r in server.requests if r["method"] == "POST" and r["body"].lstrip().startswith("{")]
    raw = base / "captures.jsonl"  # raw bodies stay outside the repository
    raw.write_text("".join(json.dumps(r) + "\n" for r in server.requests), encoding="utf-8")
    calls = [sizes(r["body"]) for r in posts]
    return {"version": version, "exit": code, "requests": len(server.requests), "paths": sorted({r["path"] for r in server.requests}),
            "calls": calls, "stderr_tail": err[-400:]}


def main() -> None:
    global WIRE
    args = sys.argv[1:]
    if "--wire" in args:
        WIRE = args.pop(args.index("--wire") + 1)
        args.remove("--wire")
    output = Path(args[0])
    packages = args[1:] or ["1.0.105"]
    results = {}
    for package in packages:
        for arm in ("builtin-mcps-on", "builtin-mcps-off"):
            for repeat in range(1, REPEATS + 1):
                key = f"{package} {arm} r{repeat}"
                results[key] = run(package, arm, repeat)
                first = (results[key]["calls"] or [{}])[0]
                print(json.dumps({key: {k: first.get(k) for k in ("request_cl100k", "system_cl100k", "tools_cl100k",
                                                                  "deferred_cl100k", "tool_count")}
                                  | {"posts": len(results[key]["calls"])}}), flush=True)
    output.write_text(json.dumps({"probe": "first BYOK requests to a 502 capture server, signed in, online",
                                  "wire": WIRE, "model": WIRES[WIRE][0], "prompt": PROMPT, "flags": flags(),
                                  "results": results}, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
