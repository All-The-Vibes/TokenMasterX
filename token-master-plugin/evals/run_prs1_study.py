"""PRS-1: pre-registered live study of TokenMaster on real repository tasks.

Protocol: token-master-plugin/docs/PRS1_PROTOCOL.md (written before any study call).

Every arm shares the model, tasks, frozen workspace snapshot, base system prompt
(the real GitHub Copilot CLI prompt, adapted only for paths and tool names),
base tools, limits and oracle. Each arm adds exactly one component:

  baseline           no TokenMaster runtime; parallel_tool_calls=false (held constant)
  baseline_parallel  baseline with parallel_tool_calls=true (stock CLI behavior; confound check)
  ponytail           pinned Ponytail ruleset injected by the runtime
  headroom           requests routed through `headroom proxy` v0.41.0 with default settings
  graph              graphify-nav + codegraph MCP tools and the shipped routing agent text
  v5                 TokenMaster runtime with request-policy-v5
  graph_v5           graph + v5

Subcommands: self-test | prepare | probe-headroom | smoke | run | analyze
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
import fnmatch
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import queue
import random
import re
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request

PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parent
SKILL = PLUGIN / "skills" / "token-master"
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

from brainspace.request_policy import RequestPolicy  # noqa: E402
from brainspace.runtime import ExecutedToolResult, RuntimeSession  # noqa: E402
from brainspace.runtime_policy import RuntimePolicy  # noqa: E402
from brainspace.runtime_resources import RuntimeResources  # noqa: E402
from brainspace.transport import Reply, ResponsesTransport, _json, parse_json  # noqa: E402

SNAPSHOT_COMMIT = "703aa20d3e0f1fc955302dc769a68b1801992150"
SNAPSHOT_PATHS = ("token-master-plugin/skills/token-master", "token-master-plugin/docs")
MODEL = "gpt-6-astra"
SEED = 20261018
REPEATS = 3
MAX_CALLS = 30
TOKEN_CAP = 80_000_000
ARMS = ("baseline", "baseline_parallel", "ponytail", "headroom", "graph", "v5", "graph_v5")
COMPARISONS = tuple((arm, "baseline") for arm in ARMS[1:]) + (("graph_v5", "graph"),)
CACHE_WEIGHTS = (0.1, 0.5)
BOOTSTRAP_ITERATIONS = 10_000
CATEGORIES = ("locate", "logic", "impact", "docs", "edit")

TOKENIZER_FILE = REPO / "evidence/controlled-scorecard-20261008/batch-001/cl100k_base.tiktoken"
PONYTAIL_EXPORT = REPO / "evidence/controlled-scorecard-20261008/batch-001/ponytail.json"
COPILOT_CAPTURE_DIR = REPO / "evidence/isolated-sandbox-savings-20261017/native-copilot-cli-gpt6-astra-001"
HEADROOM_MODEL_CACHE = REPO / "evidence/headroom-model-readiness-20261008/model-cache"
AGENT_TEMPLATE = SKILL / "agent.template.copilot.md"
GRAPHIFY_MCP = SKILL / "graphify_mcp.py"
RUNTIME_PYTHON = REPO / ".token-master-runtime/Scripts/python.exe"
HEADROOM_EXE = Path(r"C:\Users\shyamsridhar\.local\bin\headroom.exe")
GRAPHIFY_EXE = Path(r"C:\Users\shyamsridhar\AppData\Roaming\uv\tools\graphifyy\Scripts\graphify.exe")
NODE_EXE = Path(r"C:\Program Files\Microsoft Visual Studio\18\Enterprise\MSBuild\Microsoft\VisualStudio\NodeJs\node.exe")
CODEGRAPH_SHIM = Path(r"C:\Users\shyamsridhar\.copilot\token-master\cgtool\node_modules\@colbymchenry\codegraph\npm-shim.js")
GIT_EXE = Path(r"C:\Program Files\Git\cmd\git.exe")
OPENCODE_DB = Path(r"C:\Users\shyamsridhar\.local\share\opencode\opencode.db")
COPILOT_URL = "https://api.githubcopilot.com/responses"

CWD_TOKEN = "<<PRS1_CWD>>"
SESSION_TOKEN = "<<PRS1_SESSION_DIR>>"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SKIP_DIRS = {"__pycache__", "node_modules"}
VIEW_LIMIT_BYTES = 20_000
OUTPUT_CAP_LINES = 200
OUTPUT_CAP_CHARS = 40_000
FORBIDDEN_ENV_PREFIXES = ("HEADROOM_", "PONYTAIL", "ANTHROPIC_", "OPENAI_", "CAVEMAN", "HTTP_PROXY", "HTTPS_PROXY")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def write_json(path: Path, value) -> None:
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value, lock: threading.Lock) -> None:
    with lock, Path(path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def arm_spec(arm: str) -> dict:
    return {
        "parallel": arm == "baseline_parallel",
        "graph": arm in ("graph", "graph_v5"),
        "v5": arm in ("v5", "graph_v5"),
        "ponytail": arm == "ponytail",
        "headroom": arm == "headroom",
    }


def runtime_config(spec: dict):
    """Ponytail is appended to the system prompt (as its plugin ships), so its policy stays off."""
    if spec["v5"]:
        return RuntimePolicy(
            backend="local",
            request_policy=RequestPolicy(
                version="request-policy-v5", enabled=True, min_tool_chars=256,
                keep_recent_tool_results=1, max_transforms=12),
            require_nonexpanding_input=True), RuntimeResources()
    return RuntimePolicy(), RuntimeResources()


def ponytail_text() -> str:
    export = json.loads(PONYTAIL_EXPORT.read_text(encoding="utf-8"))
    text = export["instructions"]
    if sha256_bytes(text.encode("utf-8")) != export["instructions_sha256"] or export["mode"] != "full":
        raise ValueError("pinned Ponytail export does not match its recorded digest")
    return text


# --------------------------------------------------------------------------- tools

class ToolError(Exception):
    pass


def walk_files(base: Path):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS)
        for name in sorted(filenames):
            if not name.startswith("."):
                yield Path(dirpath) / name


def glob_match(rel_posix: str, pattern: str) -> bool:
    pattern = pattern.replace("\\", "/").removeprefix("./")
    if fnmatch.fnmatchcase(rel_posix, pattern):
        return True
    if pattern.startswith("**/") and fnmatch.fnmatchcase(rel_posix, pattern[3:]):
        return True
    return "/" not in pattern and fnmatch.fnmatchcase(rel_posix.rsplit("/", 1)[-1], pattern)


def cap_lines(lines: list[str], limit: int | None) -> str:
    limit = limit if isinstance(limit, int) and limit > 0 else OUTPUT_CAP_LINES
    shown, size = [], 0
    for line in lines[:limit]:
        if size + len(line) > OUTPUT_CAP_CHARS:
            break
        shown.append(line)
        size += len(line) + 1
    text = "\n".join(shown)
    if len(shown) < len(lines):
        text += f"\n[Output truncated: showing {len(shown)} of {len(lines)} results. Narrow the search.]"
    return text


class WorkspaceTools:
    """Copilot-CLI-shaped view/grep/glob/edit over one private session workspace."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def _resolve(self, path) -> Path:
        if not isinstance(path, str) or not path.strip():
            raise ToolError("`path` is required")
        candidate = Path(path.strip())
        target = (candidate if candidate.is_absolute() else self.root / candidate).resolve()
        if target != self.root and not target.is_relative_to(self.root):
            raise ToolError(f"Path is outside the working directory: {path}")
        return target

    def _rel(self, path: Path) -> str:
        return str(path.relative_to(self.root)) if path != self.root else "."

    def view(self, path, view_range=None, forceReadLargeFiles=False):
        target = self._resolve(path)
        if target.is_dir():
            lines = []
            for child in sorted(target.iterdir(), key=lambda p: p.name):
                if child.name.startswith(".") or child.name in SKIP_DIRS:
                    continue
                lines.append(self._rel(child) + ("\\" if child.is_dir() else ""))
                if child.is_dir():
                    for grand in sorted(child.iterdir(), key=lambda p: p.name):
                        if not grand.name.startswith(".") and grand.name not in SKIP_DIRS:
                            lines.append(self._rel(grand) + ("\\" if grand.is_dir() else ""))
            return "\n".join(lines) or "(empty directory)"
        if not target.is_file():
            raise ToolError(f"Path does not exist: {path}")
        text = target.read_text(encoding="utf-8", errors="replace")
        if view_range is not None:
            if (not isinstance(view_range, list) or len(view_range) != 2
                    or not all(type(x) is int for x in view_range)):
                raise ToolError("view_range must be [start, end]")
            lines = text.splitlines()
            start, end = view_range
            end = len(lines) if end == -1 else min(end, len(lines))
            if start < 1 or start > max(len(lines), 1) or end < start:
                raise ToolError(f"Invalid view_range {view_range}; the file has {len(lines)} lines")
            return "\n".join(f"{n}. {lines[n - 1]}" for n in range(start, end + 1))
        if len(text.encode("utf-8")) > VIEW_LIMIT_BYTES and not forceReadLargeFiles:
            cut = text.encode("utf-8")[:VIEW_LIMIT_BYTES].decode("utf-8", "ignore")
            cut = cut[: cut.rfind("\n") + 1] if "\n" in cut else cut
            return (f"{cut}[File truncated at 20KB: showing lines 1-{cut.count(chr(10))} of "
                    f"{len(text.splitlines())}. Use view_range to read more.]")
        return text

    def grep(self, pattern, path=None, glob=None, output_mode="files_with_matches",
             ignore_case=False, context=0, head_limit=None):
        try:
            regex = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
        except (re.error, TypeError) as error:
            raise ToolError(f"Invalid regular expression: {error}") from None
        base = self._resolve(path) if path else self.root
        files = [base] if base.is_file() else list(walk_files(base))
        if glob:
            files = [f for f in files if glob_match(f.relative_to(self.root).as_posix(), glob)]
        context = context if isinstance(context, int) and 0 < context <= 10 else 0
        out: list[str] = []
        for file in files:
            data = file.read_bytes()
            if b"\0" in data[:2048]:
                continue
            lines = data.decode("utf-8", "replace").splitlines()
            hits = [i for i, line in enumerate(lines) if regex.search(line)]
            if not hits:
                continue
            rel = self._rel(file)
            if output_mode == "count":
                out.append(f"{rel}:{len(hits)}")
            elif output_mode == "content":
                shown: set[int] = set()
                for i in hits:
                    for j in range(max(0, i - context), min(len(lines), i + context + 1)):
                        if j not in shown:
                            shown.add(j)
                            out.append(f"{rel}{':' if j in hits else '-'}{j + 1}{':' if j in hits else '-'}{lines[j]}")
            else:
                out.append(rel)
        return cap_lines(out, head_limit) if out else "No matches found."

    def glob(self, pattern, path=None):
        if not isinstance(pattern, str) or not pattern:
            raise ToolError("`pattern` is required")
        base = self._resolve(path) if path else self.root
        matches = [self._rel(f) for f in walk_files(base)
                   if glob_match(f.relative_to(base).as_posix(), pattern)]
        return cap_lines(matches, None) if matches else "No files found."

    def edit(self, path, old_str, new_str):
        target = self._resolve(path)
        if not target.is_file():
            raise ToolError(f"File does not exist: {path}")
        if not isinstance(old_str, str) or not isinstance(new_str, str) or not old_str:
            raise ToolError("`old_str` must be a non-empty string and `new_str` a string")
        with target.open(encoding="utf-8", newline="") as handle:
            text = handle.read()
        if old_str not in text and "\r\n" in text:
            old_str, new_str = old_str.replace("\n", "\r\n"), new_str.replace("\n", "\r\n")
        count = text.count(old_str)
        if count == 0:
            raise ToolError("`old_str` was not found. View the file to copy the exact current text.")
        if count > 1:
            raise ToolError(f"`old_str` matches {count} locations; include more context so it is unique.")
        with target.open("w", encoding="utf-8", newline="") as handle:
            handle.write(text.replace(old_str, new_str, 1))
        return f"Edited {path}."

    def execute(self, name: str, args: dict) -> ExecutedToolResult:
        allowed = {
            "view": ("path", "view_range", "forceReadLargeFiles"),
            "grep": ("pattern", "path", "glob", "output_mode", "ignore_case", "context", "head_limit"),
            "glob": ("pattern", "path"),
            "edit": ("path", "old_str", "new_str"),
        }
        if name not in allowed:
            return ExecutedToolResult(f"Error: tool `{name}` is not available.", "error")
        try:
            return ExecutedToolResult(
                getattr(self, name)(**{k: args[k] for k in allowed[name] if k in args}), "success")
        except ToolError as error:
            return ExecutedToolResult(f"Error: {error}", "error")
        except (TypeError, OSError, UnicodeError) as error:
            return ExecutedToolResult(f"Error: {type(error).__name__}: {error}", "error")


BASE_TOOL_SPECS = [
    {"type": "function", "name": "grep", "strict": False,
     "description": ("Search file contents with a regular expression.\n"
                     "* Defaults to listing matching files; set `output_mode` to \"content\" for matching lines "
                     "(path:line:text) or \"count\" for per-file counts.\n"
                     "* `path` defaults to the current working directory. Use `glob` (e.g. \"*.py\", "
                     "\"**/*.md\") to filter files.\n* Results are capped; narrow the search if truncated."),
     "parameters": {"type": "object", "required": ["pattern"], "properties": {
         "pattern": {"type": "string", "description": "Regular expression (Python syntax)."},
         "path": {"type": "string", "description": "File or directory to search; defaults to the cwd."},
         "glob": {"type": "string", "description": "Glob filter for file paths."},
         "output_mode": {"type": "string", "enum": ["content", "files_with_matches", "count"]},
         "ignore_case": {"type": "boolean"},
         "context": {"type": "integer", "description": "Context lines around each match (content mode)."},
         "head_limit": {"type": "integer", "description": "Return at most this many lines."}}}},
    {"type": "function", "name": "glob", "strict": False,
     "description": "Find files by glob pattern (e.g. \"**/*.py\"). Returns paths relative to the cwd.",
     "parameters": {"type": "object", "required": ["pattern"], "properties": {
         "pattern": {"type": "string"},
         "path": {"type": "string", "description": "Directory to search; defaults to the cwd."}}}},
    {"type": "function", "name": "edit", "strict": False,
     "description": ("Edit a file by replacing exactly one occurrence of `old_str` with `new_str`.\n"
                     "* `old_str` must match the current file text exactly once, including whitespace.\n"
                     "* View the file first to copy the exact text."),
     "parameters": {"type": "object", "required": ["path", "old_str", "new_str"], "properties": {
         "path": {"type": "string"}, "old_str": {"type": "string"}, "new_str": {"type": "string"}}}},
]


def chat_tool(spec: dict) -> dict:
    return {"type": "function", "function": {k: spec[k] for k in ("name", "description", "parameters", "strict")
                                             if k in spec}}


# --------------------------------------------------------------------------- MCP (graph arms)

class McpStdio:
    """Minimal synchronous MCP stdio client (newline-delimited JSON-RPC)."""

    def __init__(self, cmd: list[str], cwd: Path, env: dict, log_path: Path):
        self._log = open(log_path, "ab")
        self._proc = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=self._log, creationflags=NO_WINDOW)
        self._lines: queue.Queue = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self._next = 0
        self.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                    "clientInfo": {"name": "prs1", "version": "1.0"}}, timeout=120)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def _pump(self):
        assert self._proc.stdout is not None
        for raw in self._proc.stdout:
            self._lines.put(raw)
        self._lines.put(None)

    def _send(self, message: dict):
        assert self._proc.stdin is not None
        try:
            self._proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
            self._proc.stdin.flush()
        except (OSError, ValueError) as error:
            raise RuntimeError(f"MCP pipe closed ({type(error).__name__})") from None

    def request(self, method: str, params: dict, timeout: float = 90):
        self._next += 1
        ident = self._next
        self._send({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            try:
                raw = self._lines.get(timeout=max(0.1, deadline - time.monotonic()))
            except queue.Empty:
                raise TimeoutError(f"MCP {method} timed out") from None
            if raw is None:
                raise RuntimeError("MCP server exited")
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            if message.get("id") == ident:
                if "error" in message:
                    raise RuntimeError(str(message["error"])[:500])
                return message.get("result", {})

    def tools(self) -> list[dict]:
        return self.request("tools/list", {}).get("tools", [])

    def call(self, name: str, arguments: dict) -> ExecutedToolResult:
        try:
            result = self.request("tools/call", {"name": name, "arguments": arguments})
        except (RuntimeError, TimeoutError) as error:
            return ExecutedToolResult(f"Error: {error}", "error")
        text = "\n".join(part.get("text", "") for part in result.get("content", []) if part.get("type") == "text")
        return ExecutedToolResult(text, "error" if result.get("isError") else "success")

    def close(self):
        kill_tree(self._proc)
        self._log.close()


def kill_tree(proc: subprocess.Popen) -> None:
    """Windows does not kill grandchildren with the parent (npm shim -> node)."""
    if proc.poll() is None:
        taskkill = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"
        subprocess.run([str(taskkill), "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                       creationflags=NO_WINDOW)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def remove_tree(path: Path) -> None:
    def clear_readonly(func, target, _error):
        os.chmod(target, stat.S_IWRITE)
        func(target)
    shutil.rmtree(path, onexc=clear_readonly)


def start_graph_servers(workspace: Path, env: dict, log_dir: Path) -> dict[str, McpStdio]:
    log_dir.mkdir(parents=True, exist_ok=True)
    servers: dict[str, McpStdio] = {}
    try:
        servers["graphify-nav"] = McpStdio(
            [str(RUNTIME_PYTHON), "-X", "utf8", "-B", str(GRAPHIFY_MCP)], workspace,
            {**env, "GRAPH_PATH": ".token-master/graph.json"}, log_dir / "graphify-nav.log")
        servers["codegraph"] = McpStdio(
            [str(NODE_EXE), str(CODEGRAPH_SHIM), "serve", "--mcp", "-p", "."], workspace, env,
            log_dir / "codegraph.log")
    except BaseException:
        for server in servers.values():
            server.close()
        raise
    return servers


def mcp_tool_specs(servers: dict[str, McpStdio]) -> list[dict]:
    specs = []
    for server_name, server in servers.items():
        for tool in server.tools():
            specs.append({"type": "function", "name": f"{server_name}-{tool['name']}", "strict": False,
                          "description": tool.get("description", ""),
                          "parameters": tool.get("inputSchema") or {"type": "object", "properties": {}}})
    return specs


def dispatch(name: str, args: dict, tools: WorkspaceTools, servers: dict[str, McpStdio]) -> ExecutedToolResult:
    for server_name, server in servers.items():
        if name.startswith(server_name + "-"):
            return server.call(name[len(server_name) + 1:], args)
    return tools.execute(name, args)


# --------------------------------------------------------------------------- transport + gateway

@dataclass(frozen=True)
class StudyTransport(ResponsesTransport):
    """Product ResponsesTransport plus Copilot CLI's per-session prompt_cache_key and a parallel flag."""

    parallel: bool = False
    cache_key: str = ""

    def encode(self, chat: dict) -> str:
        body = parse_json(super().encode(chat))
        body["parallel_tool_calls"] = self.parallel
        body["prompt_cache_key"] = self.cache_key
        return _json(body)

    def send(self, text: str) -> Reply:
        if not self.allow_network:
            return Reply(False, "network_not_allowed")
        try:
            body = parse_json(text)
            if (body.get("model") != self.model or body.get("prompt_cache_key") != self.cache_key
                    or body.get("parallel_tool_calls") is not self.parallel):
                raise ValueError("foreign wire")
        except (ValueError, TypeError):
            return Reply(False, "invalid_request")
        return self._send_validated_wire(text)


def start_gateway(token: str, log_path: Path) -> ThreadingHTTPServer:
    """Loopback bridge to the Copilot API. Retries only 429/5xx/network errors; 70 s total budget."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            started = time.monotonic()
            status, out = 599, b'{"error":"gateway_no_attempt"}'
            for attempt in range(1, 4):
                attempt_started = time.monotonic()
                request = urllib.request.Request(COPILOT_URL, data=body, method="POST", headers={
                    "Authorization": f"Bearer {token}", "Content-Type": "application/json",
                    "Accept": "application/json", "Copilot-Integration-Id": "vscode-chat",
                    "Editor-Version": "vscode/1.100.0"})
                try:
                    with opener.open(request, timeout=max(5.0, 70 - (time.monotonic() - started))) as response:
                        status, out = response.status, response.read()
                except urllib.error.HTTPError as error:
                    status, out = error.code, error.read()
                except Exception as error:  # network failure: no provider response
                    status, out = 599, json.dumps({"error": type(error).__name__}).encode()
                with lock, log_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({
                        "t": round(time.time(), 3), "attempt": attempt, "status": status,
                        "seconds": round(time.monotonic() - attempt_started, 3),
                        "request_bytes": len(body), "response_bytes": len(out)}) + "\n")
                if status not in (429, 500, 502, 503, 504, 599) or time.monotonic() - started > 30:
                    break
                time.sleep(2 * attempt)
            self.send_response(502 if status == 599 else status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_headroom(upstream: str, env: dict, root: Path):
    """Run the real `headroom proxy` with default mode/excludes; only egress and paths are pinned."""
    home = root / "headroom-home"
    home.mkdir(parents=True, exist_ok=True)
    port = free_port()
    proxy_env = {**env, "HOME": str(home), "USERPROFILE": str(home), "HEADROOM_OFFLINE": "1",
                 "HEADROOM_BEACON": "off", "HEADROOM_UPDATE_CHECK": "off", "DO_NOT_TRACK": "1",
                 "HF_HOME": str(HEADROOM_MODEL_CACHE), "HF_HUB_CACHE": str(HEADROOM_MODEL_CACHE / "hub"),
                 "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    log = open(root / "headroom-proxy.log", "ab")
    proc = subprocess.Popen(
        [str(HEADROOM_EXE), "proxy", "--host", "127.0.0.1", "--port", str(port), "--openai-api-url", upstream],
        cwd=str(home), env=proxy_env, stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"headroom proxy exited with {proc.returncode}; see {root / 'headroom-proxy.log'}")
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                    f"http://127.0.0.1:{port}/health", timeout=5) as response:
                if response.status == 200:
                    return proc, port, log
        except Exception:
            time.sleep(2)
    proc.kill()
    raise RuntimeError("headroom proxy did not become healthy within 240 s")


def load_copilot_token() -> str:
    with sqlite3.connect(str(OPENCODE_DB)) as conn:
        row = conn.execute("SELECT value FROM credential WHERE integration_id='github-copilot' "
                           "AND active=1 LIMIT 1").fetchone()
    value = json.loads(row[0]) if row and row[0] else {}
    token = value.get("access") or value.get("refresh")
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError("no active GitHub Copilot credential in opencode.db")
    return token.strip()


def isolated_env(root: Path) -> dict[str, str]:
    windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    env = {"SystemRoot": str(windows), "WINDIR": str(windows), "COMSPEC": str(windows / "System32/cmd.exe"),
           "PATH": str(windows / "System32"), "PATHEXT": ".COM;.EXE;.BAT;.CMD", "PYTHONUTF8": "1",
           "PYTHONIOENCODING": "utf-8", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
           "BRAINSPACE_TOKENIZER_FILE": str(TOKENIZER_FILE)}
    for key, rel in {"HOME": "home", "USERPROFILE": "home", "APPDATA": "appdata", "LOCALAPPDATA": "localappdata",
                     "XDG_CONFIG_HOME": "xdg-config", "XDG_CACHE_HOME": "xdg-cache", "XDG_DATA_HOME": "xdg-data",
                     "COPILOT_HOME": "copilot", "CLAUDE_CONFIG_DIR": "claude", "CODEX_HOME": "codex",
                     "TEMP": "temp", "TMP": "temp"}.items():
        (root / rel).mkdir(parents=True, exist_ok=True)
        env[key] = str(root / rel)
    return env


def isolation_receipt(root: Path) -> dict:
    leaked = sorted(k for k in os.environ if k.upper().startswith(FORBIDDEN_ENV_PREFIXES))
    home = Path(os.environ.get("HOME", "")).resolve()
    receipt = {"leaked_env": leaked, "home_isolated": home.is_relative_to(root.resolve()),
               "global_headroom_state_visible": (home / ".headroom").exists(),
               "global_ponytail_state_visible": (home / ".config/opencode/.ponytail-active").exists()}
    if leaked or not receipt["home_isolated"] or receipt["global_headroom_state_visible"] \
            or receipt["global_ponytail_state_visible"]:
        raise RuntimeError(f"sandbox isolation failed: {receipt}")
    return receipt


# --------------------------------------------------------------------------- grading

MISSING = object()


def extract_json_object(text: str, keys) -> dict | None:
    """Top-level JSON objects only (nested objects are never considered separately)."""
    decoder, found, i, text = json.JSONDecoder(), [], 0, text or ""
    while i < len(text):
        if text[i] != "{":
            i += 1
            continue
        try:
            value, end = decoder.raw_decode(text, i)
        except ValueError:
            i += 1
            continue
        if isinstance(value, dict):
            found.append(value)
        i = end
    for value in found:
        if set(keys) & set(value):
            return value
    return found[0] if found else None


def norm_text(value: str, expected: str) -> str:
    text = value.strip().strip("`'\"").strip()
    if "/" in expected or re.search(r"\.(py|md|json|txt|toml|yaml|yml)$", expected):
        text = text.replace("\\", "/")
        marker = text.find("token-master-plugin/")
        text = text[marker:] if marker > 0 else text
        text = text.removeprefix("./")
        longer, shorter = (text, expected) if len(text) > len(expected) else (expected, text)
        # Accept a different but unambiguous root only when the shorter path keeps >= 2 components.
        if text != expected and "/" in shorter and longer.endswith("/" + shorter):
            text = expected
    if text.endswith("()"):
        text = text[:-2]
    if "." in text and "." not in expected and "/" not in text and text.rsplit(".", 1)[-1] == expected:
        text = expected
    return text


def scalar_matches(value, expected) -> bool:
    if isinstance(expected, bool):
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            value = value.strip().lower() == "true"
        return value is expected
    if isinstance(expected, (int, float)):
        if isinstance(value, str):
            try:
                value = float(value.strip())
            except ValueError:
                return False
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isclose(float(value), float(expected), rel_tol=1e-9, abs_tol=1e-9))
    if isinstance(expected, str):
        return isinstance(value, str) and norm_text(value, expected).casefold() == expected.casefold()
    return value == expected


def value_matches(value, expected, unordered: bool) -> bool:
    if value is MISSING:
        return False
    if isinstance(expected, list):
        if not isinstance(value, list) or len(value) != len(expected):
            return False
        if not unordered:
            return all(scalar_matches(v, e) for v, e in zip(value, expected, strict=True))
        remaining = list(value)
        for item in expected:
            hit = next((i for i, v in enumerate(remaining) if scalar_matches(v, item)), None)
            if hit is None:
                return False
            remaining.pop(hit)
        return True
    return scalar_matches(value, expected)


def manifest(root: Path) -> dict[str, str]:
    return {f.relative_to(root).as_posix(): sha256_file(f) for f in walk_files(root)}


def expected_source(template: Path, file: str, replacements: list[dict]) -> str:
    text = (template / file).read_text(encoding="utf-8")
    for rep in replacements:
        if rep["file"] == file:
            if text.count(rep["old"]) != 1:
                raise ValueError(f"oracle replacement is not unique in {file}")
            text = text.replace(rep["old"], rep["new"], 1)
    return text


def same_content(file: str, got: str, expected: str) -> bool:
    if file.endswith(".py"):
        return ast.dump(ast.parse(got)) == ast.dump(ast.parse(expected))
    if file.endswith(".json"):
        return json.loads(got) == json.loads(expected)
    return ([line.rstrip() for line in got.strip().splitlines()]
            == [line.rstrip() for line in expected.strip().splitlines()])


def grade(task: dict, final_text: str | None, workspace: Path, template: Path) -> dict:
    before, after = manifest(template), manifest(workspace)
    changed = sorted(k for k in before.keys() & after.keys() if before[k] != after[k])
    changed += sorted(set(after) - set(before)) + sorted(set(before) - set(after))
    if task["category"] == "edit":
        reps = task["edit_oracle"]["replacements"]
        allowed = sorted({r["file"] for r in reps})
        unexpected = [f for f in changed if f not in allowed]
        if unexpected:
            return {"pass": False, "why": "unexpected_changes", "changed": changed}
        for file in allowed:
            try:
                ok = same_content(file, (workspace / file).read_text(encoding="utf-8"),
                                  expected_source(template, file, reps))
            except (SyntaxError, ValueError):
                return {"pass": False, "why": f"unparseable:{file}", "changed": changed}
            if not ok:
                return {"pass": False, "why": f"mismatch:{file}", "changed": changed}
        return {"pass": True, "why": "ok", "changed": changed}
    if changed:
        return {"pass": False, "why": "modified_files_in_question_task", "changed": changed}
    answer = extract_json_object(final_text or "", task["expected"])
    if answer is None:
        return {"pass": False, "why": "no_json_object", "changed": changed}
    unordered = set(task.get("unordered_list_keys", []))
    wrong = [k for k, exp in task["expected"].items() if not value_matches(answer.get(k, MISSING), exp, k in unordered)]
    return {"pass": not wrong, "why": "ok" if not wrong else "wrong:" + ",".join(wrong),
            "answer": answer, "changed": changed}


# --------------------------------------------------------------------------- prepare

def load_copilot_prompt() -> tuple[str, dict]:
    capture = sorted(COPILOT_CAPTURE_DIR.rglob("captures.jsonl"))[0]
    request = json.loads(json.loads(capture.read_text(encoding="utf-8").splitlines()[0])["input"])
    system = request["input"][0]
    if system.get("role") != "system":
        raise ValueError("captured Copilot request does not start with its system prompt")
    text = system["content"] if isinstance(system["content"], str) else "".join(
        part.get("text", "") for part in system["content"])
    view = next(t for t in request["tools"] if t.get("name") == "view")
    return text, view


def adapt_copilot_prompt(text: str) -> str:
    env_block = ("<environment_context>\nYou are working in the following environment. You do not need to make "
                 f"additional tool calls to verify this.\n* Current working directory: {CWD_TOKEN}\n"
                 "* Operating System: windows\nCRITICAL: Since you're running on Windows, always use "
                 "Windows-style paths with backslashes (\\) as the path separator. Do not attempt to use "
                 "forward-slash-separated paths as it will not work.\n</environment_context>")
    for pattern, replacement in ((r"<environment_context>.*?</environment_context>", env_block),
                                 (r"Session folder: [^\n]*", f"Session folder: {SESSION_TOKEN}")):
        text, count = re.subn(pattern, lambda _m, r=replacement: r, text, flags=re.S)
        if count != 1:
            raise ValueError(f"prompt adaptation matched {count} times: {pattern}")
    text = text.replace("apply_patch", "edit")
    if "isolated-sandbox-savings" in text or "shyamsridhar" in text:
        raise ValueError("captured prompt still contains capture-specific paths")
    return text


def agent_text() -> str:
    raw = AGENT_TEMPLATE.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise ValueError("agent template frontmatter not found")
    return parts[2].strip()


def build_graph_indexes(root: Path) -> dict:
    import graphify_mcp  # same function setup.py uses

    started = time.monotonic()
    subprocess.run([str(GRAPHIFY_EXE), "update", "."], cwd=root, check=True, capture_output=True,
                   creationflags=NO_WINDOW)
    graph = json.loads((root / "graphify-out/graph.json").read_text(encoding="utf-8"))
    graphify_mcp.stamp_graph(graph, root, {"name": "graphify", "version": "0.9.84"}, time.monotonic() - started)
    (root / ".token-master").mkdir()
    (root / ".token-master/graph.json").write_text(json.dumps(graph, ensure_ascii=False) + "\n", encoding="utf-8")
    shutil.rmtree(root / "graphify-out")  # deviation: keep the visible tree identical across arms
    subprocess.run([str(NODE_EXE), str(CODEGRAPH_SHIM), "init", "."], cwd=root, check=True,
                   capture_output=True, creationflags=NO_WINDOW)
    status = json.loads(subprocess.check_output([str(NODE_EXE), str(CODEGRAPH_SHIM), "status", "--json", "."],
                                                cwd=root, text=True, encoding="utf-8", creationflags=NO_WINDOW))
    return {"graphify_nodes": len(graph.get("nodes", [])), "graphify_links": len(graph.get("links", [])),
            "codegraph_nodes": status.get("nodeCount"), "codegraph_edges": status.get("edgeCount"),
            "seconds": round(time.monotonic() - started, 2)}


def validate_tasks(tasks: list[dict], template: Path) -> None:
    ids = [t["id"] for t in tasks]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate task id")
    for task in tasks:
        if task["category"] not in CATEGORIES or not task["prompt"].strip():
            raise ValueError(f"bad task {task['id']}")
        if task["category"] == "edit":
            files = {r["file"] for r in task["edit_oracle"]["replacements"]}
            for file in files:
                original = (template / file).read_text(encoding="utf-8")
                expected = expected_source(template, file, task["edit_oracle"]["replacements"])
                if same_content(file, original, expected):
                    raise ValueError(f"{task['id']}: oracle edit is a no-op")
        elif not isinstance(task.get("expected"), dict) or not task["expected"]:
            raise ValueError(f"{task['id']}: expected answer missing")


def make_schedule(task_ids: list[str]) -> list[list]:
    jobs = []
    for repeat in range(1, REPEATS + 1):
        block = [[repeat, task, arm] for task in task_ids for arm in ARMS]
        random.Random(SEED + repeat).shuffle(block)
        jobs += block
    return jobs


def prepare(out: Path, tasks_file: Path) -> None:
    if out.exists():
        raise SystemExit(f"output must be new: {out}")
    out.mkdir(parents=True)
    tar = out / "snapshot.tar"
    subprocess.run([str(GIT_EXE), "archive", "--format=tar", "-o", str(tar), SNAPSHOT_COMMIT, *SNAPSHOT_PATHS],
                   cwd=REPO, check=True)
    templates = {}
    for name in ("plain", "graph"):
        root = out / "templates" / name
        root.mkdir(parents=True)
        with tarfile.open(tar) as archive:
            archive.extractall(root, filter="data")
        subprocess.run([str(GIT_EXE), "init", "-q"], cwd=root, check=True)
        templates[name] = root
    graph_receipt = build_graph_indexes(templates["graph"])
    workspace_manifest = manifest(templates["plain"])
    if manifest(templates["graph"]) != workspace_manifest:
        raise SystemExit("visible workspace differs between plain and graph templates")
    prompt, view_tool = load_copilot_prompt()
    system_prompt = adapt_copilot_prompt(prompt)
    servers = start_graph_servers(templates["graph"], isolated_env(out / "prepare-env"), out / "prepare-logs")
    try:
        graph_tools = mcp_tool_specs(servers)
    finally:
        for server in servers.values():
            server.close()
    tasks = json.loads(tasks_file.read_text(encoding="utf-8"))["tasks"]
    validate_tasks(tasks, templates["plain"])
    from brainspace import tokens
    protocol = {
        "study": "PRS-1", "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": MODEL, "reasoning_effort": "low", "max_output_tokens": 4096, "max_calls_per_session": MAX_CALLS,
        "intent": "conservative (production default for every task)", "seed": SEED, "repeats": REPEATS,
        "arms": {arm: arm_spec(arm) for arm in ARMS}, "comparisons": [list(c) for c in COMPARISONS],
        "primary_endpoint": "provider-reported input_tokens + output_tokens per session",
        "secondary_endpoints": ["uncached input", "cached input", "cache-weighted tokens w=0.1 and w=0.5",
                                "output tokens", "model calls", "success rate", "tokens per success"],
        "token_cap": TOKEN_CAP,
        "snapshot": {"commit": SNAPSHOT_COMMIT, "paths": list(SNAPSHOT_PATHS), "tar_sha256": sha256_file(tar),
                     "visible_files": len(workspace_manifest),
                     "manifest_sha256": sha256_bytes(json.dumps(workspace_manifest, sort_keys=True).encode())},
        "graph_index": graph_receipt,
        "system_prompt": system_prompt, "system_prompt_sha256": sha256_bytes(system_prompt.encode()),
        "system_prompt_tokens_cl100k": tokens.count_tokens(system_prompt),
        "graph_agent_text": agent_text(),
        "ponytail_text": ponytail_text(),
        "tools": {"base": [view_tool, *BASE_TOOL_SPECS], "graph": graph_tools},
        "tasks": tasks, "tasks_sha256": sha256_file(tasks_file),
        "schedule": make_schedule([t["id"] for t in tasks]),
        "harness_sha256": sha256_file(Path(__file__)),
        "protocol_doc_sha256": sha256_file(PLUGIN / "docs/PRS1_PROTOCOL.md"),
        "component_versions": {"graphify": "0.9.84", "codegraph": "1.6.2", "headroom-ai": "0.41.0",
                               "ponytail_export_sha256": sha256_file(PONYTAIL_EXPORT)},
    }
    write_json(out / "protocol.json", protocol)
    print(f"prepared {out}: {len(tasks)} tasks x {len(ARMS)} arms x {REPEATS} repeats = "
          f"{len(protocol['schedule'])} sessions; system prompt {protocol['system_prompt_tokens_cl100k']} tokens")


# --------------------------------------------------------------------------- execution

def usage_from_captures(path: Path) -> dict:
    """Provider-reported usage per call. A submitted call without usage is counted with the
    cl100k size of its request as a flagged estimate, never as zero."""
    from brainspace import tokens

    totals = {"calls": 0, "input": 0, "cached": 0, "cache_write": 0, "output": 0, "reasoning": 0,
              "estimated_calls": 0, "complete": True}
    if not path.exists():
        return totals
    for line in path.read_text(encoding="utf-8").splitlines():
        capture = json.loads(line)
        totals["calls"] += 1
        try:
            usage = json.loads(capture["output"])["usage"]
            details = usage.get("input_tokens_details") or {}
            values = (int(usage["input_tokens"]), int(usage["output_tokens"]),
                      int(details.get("cached_tokens") or 0), int(details.get("cache_write_tokens") or 0),
                      int((usage.get("output_tokens_details") or {}).get("reasoning_tokens") or 0))
        except (TypeError, KeyError, ValueError, AttributeError):
            totals["complete"] = False
            if capture.get("input"):
                totals["input"] += tokens.count_tokens(capture["input"])
                totals["estimated_calls"] += 1
            continue
        for key, value in zip(("input", "output", "cached", "cache_write", "reasoning"), values, strict=True):
            totals[key] += value
    return totals


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
        row = {"task": task["id"], "category": task["category"], "arm": arm, "repeat": repeat, "session": sid}
        with self.lock:
            over_cap = self.tokens_used >= TOKEN_CAP
        if over_cap:
            return {**row, "status": "not_run", "why": "token_cap"}
        run_dir.mkdir(parents=True)
        shutil.copytree(template, workspace)
        tools_impl, servers = WorkspaceTools(workspace), {}
        tool_counts: Counter = Counter()
        final_text, failure, transformed = None, None, None
        started = time.monotonic()
        try:
            if spec["graph"]:
                servers = start_graph_servers(workspace, self.env, run_dir / "mcp")
            policy, resources = runtime_config(spec)
            transport = StudyTransport(
                base_url=self.urls[arm], model=MODEL, allow_network=True, max_output_tokens=4096,
                max_request_bytes=4_000_000, max_response_bytes=4_000_000, timeout=90, reasoning_effort="low",
                parallel=spec["parallel"], cache_key=sha256_bytes(sid.encode())[:32])
            session = RuntimeSession(workspace=workspace, session_id=sid, output=run_dir / "session",
                                     transport=transport, runtime_policy=policy, runtime_resources=resources,
                                     task_id=task["id"], max_calls=MAX_CALLS)
            system = (self.protocol["system_prompt"].replace(CWD_TOKEN, str(workspace))
                      .replace(SESSION_TOKEN, str(run_dir / "session-folder")))
            if spec["graph"]:
                system += "\n\n" + self.protocol["graph_agent_text"]
            if spec["ponytail"]:
                system += "\n\n" + self.protocol["ponytail_text"]
            specs = self.protocol["tools"]["base"] + (self.protocol["tools"]["graph"] if spec["graph"] else [])
            tools = [chat_tool(t) for t in specs]
            messages = [{"role": "system", "content": system}, {"role": "user", "content": task["prompt"]}]
            try:
                for _ in range(MAX_CALLS):
                    reply = session.invoke({"model": MODEL, "messages": deepcopy(messages), "tools": deepcopy(tools)},
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
                            output = session.execute_tool(call, lambda n, a: dispatch(n, a, tools_impl, servers))
                        except ValueError as error:
                            output = f"Error: invalid tool call ({error})"
                        messages.append({"role": "tool", "tool_call_id": c["call_id"], "content": output})
                else:
                    failure = "call_cap_reached"
                verdict = grade(task, final_text, workspace, template) if failure is None else \
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
        usage = usage_from_captures(run_dir / "session/captures.jsonl")
        with self.lock:
            self.tokens_used += usage["input"] + usage["output"]
        status = "infra" if failure and failure.startswith("infra") else ("pass" if verdict["pass"] else "fail")
        if task["category"] == "edit" or verdict.get("changed"):
            for rel in verdict.get("changed", [])[:10]:
                target = workspace / rel
                if target.is_file():
                    keep = run_dir / "changed" / rel
                    keep.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, keep)
        try:
            remove_tree(workspace)
        except OSError:
            pass  # a leftover private workspace copy does not affect results
        row.update(status=status, why=verdict["why"], answer=verdict.get("answer"), final_text=(final_text or "")[:2000],
                   changed=verdict.get("changed", []), usage=usage, tool_calls=dict(tool_counts),
                   transformed_requests=transformed, wall_seconds=round(time.monotonic() - started, 2))
        return row


def warmup(urls: dict[str, str], out: Path) -> None:
    """One tiny request per arm endpoint before any session; abort if any component path fails."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    body = json.dumps({"model": MODEL, "input": [{"role": "user", "content": "Reply with OK."}],
                       "max_output_tokens": 64, "store": False, "stream": False}).encode("utf-8")
    receipt: dict[str, object] = {}
    for arm, url in urls.items():
        request = urllib.request.Request(url + "/responses", data=body, method="POST",
                                         headers={"Content-Type": "application/json"})
        try:
            with opener.open(request, timeout=90) as response:
                receipt[arm] = response.status
        except urllib.error.HTTPError as error:
            receipt[arm] = error.code
        except Exception as error:
            receipt[arm] = type(error).__name__
    write_json(out / "warmup.json", receipt)
    if any(status != 200 for status in receipt.values()):
        raise RuntimeError(f"component warm-up failed: {receipt}")


def probe_headroom(out: Path) -> dict:
    """Offline mechanism check of the real proxy on /v1/responses (fake upstream, no model calls)."""
    out.mkdir(parents=True, exist_ok=True)
    captured: list[dict] = []
    reply = json.dumps({"id": "resp_probe", "object": "response", "status": "completed", "model": MODEL,
                        "output": [{"type": "message", "id": "msg_probe", "role": "assistant", "status": "completed",
                                    "content": [{"type": "output_text", "text": "OK", "annotations": []}]}],
                        "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}).encode("utf-8")

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self):
            captured.append(json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0")))))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    proc, port, log = start_headroom(f"http://127.0.0.1:{upstream.server_port}/v1",
                                     isolated_env(out / "probe-env"), out)
    samples = {"code": (SKILL / "brainspace/runtime.py").read_text(encoding="utf-8")[:24000],
               "json": json.dumps({"records": [{"id": i, "name": f"item-{i}", "status": "active", "score": i * 3,
                                                "tags": ["alpha", "beta"]} for i in range(300)]}, indent=2)}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    results: dict[str, dict] = {}
    try:
        time.sleep(60)
        for tool in ("view", "grep", "fetch_data"):
            for kind, text in samples.items():
                history = [{"role": "system", "content": "Probe."}, {"role": "user", "content": f"Probe {tool} {kind}."},
                           {"type": "function_call", "call_id": "c1", "name": tool, "arguments": "{}"},
                           {"type": "function_call_output", "call_id": "c1", "output": text}]
                for turn, items in (("newest", history), ("prior", history + [
                        {"type": "function_call", "call_id": "c2", "name": tool, "arguments": "{}"},
                        {"type": "function_call_output", "call_id": "c2", "output": "done"}])):
                    body = {"model": MODEL, "store": False, "stream": False, "max_output_tokens": 64, "input": items,
                            "tools": [{"type": "function", "name": tool,
                                       "parameters": {"type": "object", "properties": {}}}]}
                    count = len(captured)
                    request = urllib.request.Request(f"http://127.0.0.1:{port}/v1/responses", method="POST",
                                                     data=json.dumps(body).encode("utf-8"),
                                                     headers={"Content-Type": "application/json"})
                    with opener.open(request, timeout=120) as response:
                        status = response.status
                    sent = captured[count]["input"][3]["output"] if len(captured) > count else None
                    results[f"{tool}/{kind}/{turn}"] = {
                        "status": status, "original_chars": len(text),
                        "forwarded_chars": len(sent) if isinstance(sent, str) else None,
                        "modified": sent != text}
    finally:
        kill_tree(proc)
        log.close()
        upstream.shutdown()
    write_json(out / "headroom-probe.json", results)
    for key, value in results.items():
        print(f"{key:<24} modified={value['modified']!s:<5} {value['original_chars']:>6} -> {value['forwarded_chars']}")
    return results


def execute(out: Path, protocol: dict, token: str, workers: int, jobs: list[list], results: Path) -> None:
    env = isolated_env(out / "env")
    gateways, urls = {}, {}
    hr_proc = hr_log = None
    try:
        for arm in ARMS:
            gateways[arm] = start_gateway(token, out / f"gateway-{arm}.jsonl")
            urls[arm] = f"http://127.0.0.1:{gateways[arm].server_port}/v1"
        hr_proc, hr_port, hr_log = start_headroom(urls["headroom"], env, out)
        urls["headroom"] = f"http://127.0.0.1:{hr_port}/v1"
        time.sleep(60)  # let Headroom finish its deferred background Kompress warm-up
        warmup(urls, out)
        study = Study(out, protocol, urls, env)
        tasks = {t["id"]: t for t in protocol["tasks"]}
        lock = threading.Lock()

        def one(job, suffix=""):
            repeat, task_id, arm = job
            row = study.run_session(tasks[task_id], arm, repeat, suffix)
            append_jsonl(results, row, lock)
            u = row.get("usage", {})
            print(f"[{row['session']:<34}] {row['status']:<6} calls={u.get('calls', 0):>2} "
                  f"tokens={u.get('input', 0) + u.get('output', 0):>9,} why={row.get('why')}", flush=True)
            return row

        with ThreadPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(one, jobs))
        retry = [[r["repeat"], r["task"], r["arm"]] for r in rows if r["status"] == "infra"]
        if retry:
            print(f"re-running {len(retry)} infra-failed sessions once (pre-declared rule)", flush=True)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(lambda job: one(job, "-rerun"), retry))
    finally:
        if hr_proc is not None:
            hr_proc.kill()
        if hr_log is not None:
            hr_log.close()
        for server in gateways.values():
            server.shutdown()


SMOKE_TASK = {"id": "SMOKE", "category": "locate", "unordered_list_keys": ["dirs"],
              "prompt": ("List the immediate subdirectories of token-master-plugin in this workspace. "
                         "Reply with ONLY a JSON object: {\"dirs\": [<directory names>]} (order does not matter)."),
              "expected": {"dirs": ["docs", "skills"]}}


def child_main(out: Path, mode: str, workers: int) -> int:
    token = sys.stdin.readline().strip()
    protocol = json.loads((out / "protocol.json").read_text(encoding="utf-8"))
    if sha256_file(Path(__file__)) != protocol["harness_sha256"]:
        raise SystemExit("harness changed after prepare; re-run prepare (and disclose it)")
    from brainspace import tokens
    tokens.count_tokens("warm-up")  # load once before worker threads (lazy init is not thread-safe)
    if not tokens.backend_info()["exact_reference"]:
        raise SystemExit("verified reference tokenizer unavailable")
    write_json(out / f"{mode}-isolation.json", isolation_receipt(Path(os.environ["HOME"]).parents[0]))
    if mode == "smoke":
        smoke = out / "smoke"
        smoke.mkdir(exist_ok=True)
        protocol = {**protocol, "tasks": [SMOKE_TASK]}
        for name in ("templates",):
            if not (smoke / name).exists():
                shutil.copytree(out / name, smoke / name)
        execute(smoke, protocol, token, workers, [[0, "SMOKE", arm] for arm in ARMS], smoke / "results.jsonl")
    else:
        if (out / "results.jsonl").exists():
            raise SystemExit("results already exist; a study is never re-run in place")
        execute(out, protocol, token, workers, protocol["schedule"], out / "results.jsonl")
    return 0


def launch(out: Path, mode: str, workers: int) -> int:
    out = out.resolve()
    if not (out / "protocol.json").exists():
        raise SystemExit("run `prepare` first")
    env = isolated_env(out / ("env" if mode == "run" else "smoke-env"))
    proc = subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).resolve()), "child", "--output", str(out),
                           "--mode", mode, "--workers", str(workers)],
                          env=env, cwd=str(out), input=load_copilot_token() + "\n", text=True, encoding="utf-8")
    return proc.returncode


# --------------------------------------------------------------------------- analysis

def wilcoxon_exact(diffs: list[float]) -> float:
    d = [x for x in (round(v, 6) for v in diffs) if x != 0]  # rounding makes float ties exact
    n = len(d)
    if n == 0:
        return 1.0
    order = sorted(range(n), key=lambda i: abs(d[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(d[order[j + 1]]) == abs(d[order[i]]):
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    observed = sum(r for r, x in zip(ranks, d, strict=True) if x > 0)
    center = sum(ranks) / 2
    extreme = sum(1 for mask in range(1 << n)
                  if abs(sum(ranks[k] for k in range(n) if mask >> k & 1) - center) >= abs(observed - center) - 1e-9)
    return extreme / (1 << n)


def holm(pvalues: list[float]) -> list[float]:
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    adjusted, running = [0.0] * len(pvalues), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(pvalues) - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(centre - half, 4), round(centre + half, 4)]


def metrics(row: dict) -> dict:
    u = row["usage"]
    uncached = u["input"] - u["cached"]
    out = {"total": u["input"] + u["output"], "input": u["input"], "cached": u["cached"], "uncached": uncached,
           "output": u["output"], "calls": u["calls"]}
    for w in CACHE_WEIGHTS:
        out[f"cache_weighted_{w}"] = uncached + w * u["cached"] + u["output"]
    return out


def bootstrap_reduction(by_task: dict[str, list[tuple[float, float]]], seed: int) -> list[float]:
    rng, tasks, stats = random.Random(seed), sorted(by_task), []
    for _ in range(BOOTSTRAP_ITERATIONS):
        a = b = 0.0
        for _ in tasks:
            pairs = by_task[rng.choice(tasks)]
            for _ in pairs:
                x, y = rng.choice(pairs)
                a, b = a + x, b + y
        stats.append(1 - a / b if b else 0.0)
    stats.sort()
    return [stats[int(0.025 * BOOTSTRAP_ITERATIONS)], stats[int(0.975 * BOOTSTRAP_ITERATIONS) - 1]]


def final_rows(rows: list[dict]) -> dict[tuple, dict]:
    chosen: dict[tuple, dict] = {}
    for row in rows:
        key = (row["task"], row["arm"], row["repeat"])
        if key not in chosen or (chosen[key]["status"] == "infra" and row["session"].endswith("-rerun")):
            chosen[key] = row
    return chosen


def analyze(out: Path) -> dict:
    protocol = json.loads((out / "protocol.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    for row in rows:  # recount every session from raw captures; any mismatch aborts the analysis
        capture = out / "runs" / row["session"] / "session/captures.jsonl"
        if row["status"] != "not_run" and usage_from_captures(capture) != row["usage"]:
            raise SystemExit(f"recount mismatch for {row['session']}")
    chosen = final_rows(rows)
    tasks = [t["id"] for t in protocol["tasks"]]
    category = {t["id"]: t["category"] for t in protocol["tasks"]}
    repeats = sorted({r["repeat"] for r in rows})
    arms: dict[str, dict] = {}
    for arm in ARMS:
        group = [r for (t, a, _), r in chosen.items() if a == arm]
        valid = [r for r in group if r["status"] in ("pass", "fail")]
        passes = sum(r["status"] == "pass" for r in valid)
        m = [metrics(r) for r in valid]
        sums = {k: round(sum(x[k] for x in m), 1) for k in (m[0] if m else {})}
        tool_totals: Counter = Counter()
        for r in valid:
            tool_totals.update(r["tool_calls"])
        arms[arm] = {"sessions": len(group), "graded": len(valid), "passes": passes,
                     "success_rate": round(passes / len(valid), 4) if valid else None,
                     "success_ci95": wilson(passes, len(valid)),
                     "infra_excluded": sum(r["status"] == "infra" for r in group),
                     "not_run": sum(r["status"] == "not_run" for r in group),
                     "estimated_token_calls": sum(r["usage"].get("estimated_calls", 0) for r in valid),
                     "failure_reasons": dict(Counter(r["why"].split(":")[0] for r in group if r["status"] != "pass")),
                     "totals": sums, "tokens_per_success": round(sums.get("total", 0) / passes) if passes else None,
                     "tool_calls": dict(tool_totals.most_common())}
    comparisons, pvalues = [], []
    for index, (arm, ref) in enumerate(protocol["comparisons"]):
        entry = {"arm": arm, "reference": ref}
        for endpoint in ("total", "cache_weighted_0.1", "cache_weighted_0.5", "uncached", "calls"):
            by_task: dict[str, list[tuple[float, float]]] = {}
            for t in tasks:
                for r in repeats:
                    a, b = chosen.get((t, arm, r)), chosen.get((t, ref, r))
                    if a and b and a["status"] in ("pass", "fail") and b["status"] in ("pass", "fail"):
                        by_task.setdefault(t, []).append((metrics(a)[endpoint], metrics(b)[endpoint]))
            a_sum = sum(x for pairs in by_task.values() for x, _ in pairs)
            b_sum = sum(y for pairs in by_task.values() for _, y in pairs)
            diffs = [sum(x - y for x, y in pairs) / len(pairs) for pairs in by_task.values()]
            entry[endpoint] = {
                "pairs": sum(len(p) for p in by_task.values()), "arm_sum": round(a_sum, 1), "ref_sum": round(b_sum, 1),
                "reduction": round(1 - a_sum / b_sum, 4) if b_sum else None,
                "reduction_ci95": [round(x, 4) for x in bootstrap_reduction(by_task, SEED + index)] if by_task else None,
                "tasks_lower": sum(x < 0 for x in diffs), "tasks_higher": sum(x > 0 for x in diffs),
                "wilcoxon_p": round(wilcoxon_exact(diffs), 5)}
        pvalues.append(entry["total"]["wilcoxon_p"])
        paired = [(chosen[(t, arm, r)], chosen[(t, ref, r)]) for t in tasks for r in repeats
                  if (t, arm, r) in chosen and (t, ref, r) in chosen
                  and chosen[(t, arm, r)]["status"] in ("pass", "fail")
                  and chosen[(t, ref, r)]["status"] in ("pass", "fail")]
        entry["passes"] = [sum(a["status"] == "pass" for a, _ in paired),
                           sum(b["status"] == "pass" for _, b in paired)]
        comparisons.append(entry)
    for entry, adjusted in zip(comparisons, holm(pvalues), strict=True):
        entry["total"]["holm_p"] = round(adjusted, 5)
        ci = entry["total"]["reduction_ci95"] or [0, 0]
        quality_ok = entry["passes"][0] >= entry["passes"][1]
        if ci[0] > 0 and adjusted < 0.05:
            verdict = "fewer tokens" + ("" if quality_ok else " but lower success")
        elif ci[1] < 0 and adjusted < 0.05:
            verdict = "more tokens"
        else:
            verdict = "no significant token difference"
        entry["verdict"] = verdict
    per_category = {cat: {arm: {"tokens": sum(metrics(r)["total"] for (t, a, _), r in chosen.items()
                                              if a == arm and category[t] == cat and r["status"] in ("pass", "fail")),
                                "passes": sum(r["status"] == "pass" for (t, a, _), r in chosen.items()
                                              if a == arm and category[t] == cat)}
                            for arm in ARMS} for cat in CATEGORIES}
    gateway = {}
    for arm in ARMS:
        path = out / f"gateway-{arm}.jsonl"
        attempts = ([json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                    if path.exists() else [])
        gateway[arm] = dict(Counter(str(a["status"]) for a in attempts))
    summary = {"study": "PRS-1", "protocol_sha256": sha256_file(out / "protocol.json"),
               "harness_sha256": protocol["harness_sha256"], "tasks_sha256": protocol["tasks_sha256"],
               "model": protocol["model"], "sessions_recorded": len(rows), "arms": arms,
               "comparisons": comparisons, "per_category": per_category, "gateway_status_counts": gateway}
    write_json(out / "summary.json", summary)
    lines = ["# PRS-1 results (generated by `run_prs1_study.py analyze`)", "",
             "| Arm | Passed | Total tokens (in+out) | Uncached input | Cached input | Output | Calls | Tokens/success |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for arm, a in arms.items():
        t = a["totals"]
        lines.append(f"| {arm} | {a['passes']}/{a['graded']} | {t.get('total', 0):,.0f} | {t.get('uncached', 0):,.0f} | "
                     f"{t.get('cached', 0):,.0f} | {t.get('output', 0):,.0f} | {t.get('calls', 0):,.0f} | "
                     f"{a['tokens_per_success'] or 0:,} |")
    lines += ["", "| Comparison | Total-token change (95% CI) | Holm p | Cache-weighted w=0.1 change (95% CI) "
                  "| Passed (paired) | Verdict |",
              "| --- | ---: | ---: | ---: | ---: | --- |"]
    for c in comparisons:
        def fmt(e):
            ci = e["reduction_ci95"] or [0, 0]
            return f"{-e['reduction'] * 100:+.1f}% [{-ci[1] * 100:+.1f}%, {-ci[0] * 100:+.1f}%]"
        lines.append(f"| {c['arm']} vs {c['reference']} | {fmt(c['total'])} | {c['total']['holm_p']} | "
                     f"{fmt(c['cache_weighted_0.1'])} | {c['passes'][0]} vs {c['passes'][1]} | {c['verdict']} |")
    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return summary


# --------------------------------------------------------------------------- self-test

def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "pkg").mkdir()
        (root / ".hidden").mkdir()
        (root / "pkg/a.py").write_text("X = 1\ndef f():\n    return X\n", encoding="utf-8")
        (root / "pkg/big.txt").write_text("line\n" * 6000, encoding="utf-8")
        (root / ".hidden/secret.py").write_text("X = 2\n", encoding="utf-8")
        tools = WorkspaceTools(root)
        assert tools.view("pkg/a.py") == "X = 1\ndef f():\n    return X\n"
        assert tools.view(str(root / "pkg/a.py"), [2, -1]) == "2. def f():\n3.     return X"
        assert "File truncated at 20KB" in tools.view("pkg/big.txt")
        assert len(tools.view("pkg/big.txt", forceReadLargeFiles=True)) == 30000
        assert tools.view(".") == "pkg\\\npkg\\a.py\npkg\\big.txt"
        assert tools.grep("X", output_mode="content") == "pkg\\a.py:1:X = 1\npkg\\a.py:3:    return X"
        assert tools.grep("X") == "pkg\\a.py" and tools.grep("nomatch") == "No matches found."
        assert tools.grep("X", glob="*.txt") == "No matches found."
        assert tools.glob("**/*.py") == "pkg\\a.py"
        assert tools.execute("view", {"path": "../outside"}).status == "error"
        assert tools.execute("edit", {"path": "pkg/a.py", "old_str": "X", "new_str": "Y"}).status == "error"
        assert tools.execute("edit", {"path": "pkg/a.py", "old_str": "X = 1", "new_str": "X = 2"}).status == "success"
        assert (root / "pkg/a.py").read_text(encoding="utf-8").startswith("X = 2")
        assert tools.execute("bash", {}).status == "error"
    assert extract_json_object('Done.\n```json\n{"a": 1, "b": "x"}\n```', ["a"]) == {"a": 1, "b": "x"}
    assert value_matches("`brainspace/router.py`", "brainspace/router.py", False)
    assert value_matches(r"C:\w\token-master-plugin\skills\x.py", "token-master-plugin/skills/x.py", False)
    assert value_matches("graphify_mcp._resolve()", "_resolve", False)
    assert value_matches(["b", "a"], ["a", "b"], True) and not value_matches(["b", "a"], ["a", "b"], False)
    assert value_matches("3", 3, False) and value_matches("true", True, False) and not value_matches(1, True, False)
    assert value_matches(0.10, 0.1, False) and not value_matches("4", 3, False)
    assert value_matches("token-master-plugin/skills/token-master/brainspace/router.py::x", "brainspace/router.py::x", False)
    assert value_matches(r"brainspace\router.py::x", "brainspace/router.py::x", False)
    assert not value_matches("router.py::x", "brainspace/router.py::x", False)
    assert not value_matches("other/router.py::x", "brainspace/router.py::x", False)
    assert value_matches("Headroom", "headroom", False)
    assert extract_json_object('{"a": {"b": 1}} then {"b": 2}', ["b"]) == {"b": 2}
    assert extract_json_object('{"a": {"b": 1}}', ["b"]) == {"a": {"b": 1}}
    assert abs(wilcoxon_exact([1, 2, 3, 4, 5, 6]) - 2 / 64) < 1e-12
    assert wilcoxon_exact([0, 0]) == 1.0 and abs(wilcoxon_exact([1, -1]) - 1.0) < 1e-12
    assert holm([0.01, 0.04, 0.03]) == [0.03, 0.06, 0.06]
    lo, hi = bootstrap_reduction({"t1": [(50, 100), (60, 100)], "t2": [(40, 100)]}, 1)
    assert 0.35 <= lo <= hi <= 0.6, (lo, hi)
    assert wilson(0, 10)[0] == 0.0 and wilson(10, 10)[1] == 1.0
    assert make_schedule(["T1", "T2"]) == make_schedule(["T1", "T2"]) and len(make_schedule(["T1"])) == 3 * len(ARMS)
    print("self-test passed")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("self-test", "prepare", "probe-headroom", "smoke", "run", "analyze",
                                            "child"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tasks", type=Path, default=PLUGIN / "evals/prs1_tasks.json")
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
    if args.command == "probe-headroom":
        probe_headroom(args.output.resolve())
        return 0
    if args.command in ("smoke", "run"):
        return launch(args.output, args.command, args.workers)
    if args.command == "child":
        return child_main(args.output.resolve(), args.mode, args.workers)
    analyze(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
