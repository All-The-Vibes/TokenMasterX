#!/usr/bin/env python
"""Start GitHub Copilot CLI for TokenMaster: a lean tool set, plus a local bridge in BYOK mode.

Lean tool set: for a Copilot CLI session, the launcher adds --excluded-tools with the built-in
tools that no session called in the October 18 runs, and the two workflow tools that Copilot CLI
sends under default routing and, from 1.0.104, in every mode (LEAN_EXCLUDED_TOOLS). A prompt that
asks for a tool family keeps it, and a prompt that starts a skill also keeps the workflow and
subagent tools, which the skill may use. The launcher skips this with --all-tools, when the user
already chose tools, or for a Copilot CLI subcommand.

Bridge (only with a provider URL, Copilot CLI BYOK mode): Copilot CLI sends model requests to
COPILOT_PROVIDER_BASE_URL. The bridge listens on 127.0.0.1, rewrites each OpenAI Responses or
Anthropic Messages request, and forwards it to one upstream: --upstream, or the
COPILOT_PROVIDER_BASE_URL that was already set. The bridge never reads, stores or adds
credentials. The client's headers, including Authorization, go to the upstream unchanged.

The bridge applies two deterministic rewrites to every request. Each call of a session
therefore sends the same bytes for its history, and the provider's prefix cache stays valid:
- the cache-stable system prompt (brainspace.native_transport.stable_session_prefix; PRS-4);
- request-policy-v6 shaping of grep, glob and whole-file view results
  (brainspace.v6_shaping.shape_tool_result; PRS-2 and PRS-3). Other tool results pass through.

  python brainspace_copilot_bridge.py [--all-tools] [--upstream URL] [--log usage.jsonl] -- copilot [args...]
  python brainspace_copilot_bridge.py [--upstream URL]          (serve only; prints the base URL)

Without a provider URL, Copilot CLI keeps its normal GitHub routing and the launcher applies only
the lean tool set. See docs/COPILOT_BRIDGE.md.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from brainspace import tokens  # noqa: E402
from brainspace.native_transport import (  # noqa: E402
    _SESSION_FOLDER, SESSION_FOLDER_MOVED, _replace_span, stable_session_prefix)
from brainspace.v6_shaping import shape_tool_result, tool_kind  # noqa: E402

MAX_BODY = 64 * 1024 * 1024
_HOP = frozenset({"host", "content-length", "connection", "keep-alive", "proxy-authorization",
                  "proxy-connection", "te", "trailer", "transfer-encoding", "upgrade", "accept-encoding"})
_LOOPBACK = ("127.0.0.1", "localhost", "::1")
# Auxiliary Copilot CLI tool families and the intent patterns that require them.
# Core coding tools (view, edit, create, rg, glob, powershell, report_intent) are always kept.
CAPABILITY_GROUPS: dict[str, tuple[tuple[str, ...], re.Pattern[str]]] = {
    "session_history": (
        ("session_store_sql",),
        re.compile(r"\b(session_store_sql|session[- ]store|session\s+history|(?:previous|past|earlier|prior)\s+sessions?)\b", re.I),
    ),
    "agents": (
        ("task", "read_agent", "write_agent", "list_agents"),
        re.compile(r"\b(subagents?|parallel\s+agents?|multi-agent|spawn\s+(?:an?\s+)?agent|delegate\s+to\s+(?:an?\s+)?agent|read_agent|write_agent|list_agents)\b", re.I),
    ),
    "skills": (
        ("skill",),
        re.compile(r"(?:^|\s)/[a-z][\w-]*\b|\bskill://|\b(?:use|load|invoke|run)\s+(?:the\s+)?[\w-]+\s+skill\b", re.I),
    ),
    "sql": (
        ("sql",),
        re.compile(r"\b(sql\s+scratchpad|run\s+a?\s*sql\s+query|query\s+with\s+sql)\b", re.I),
    ),
    "background_shell": (
        ("read_powershell", "stop_powershell", "list_powershell"),
        re.compile(r"\b(read_powershell|stop_powershell|list_powershell|background\s+(?:powershell|shell|process|job|server)|in\s+the\s+background)\b", re.I),
    ),
    "copilot_docs": (
        ("fetch_copilot_cli_documentation",),
        re.compile(r"\b(fetch_copilot_cli_documentation|copilot\s+cli\s+(?:docs|documentation|flags|keybindings|settings))\b", re.I),
    ),
    # Sent under default routing, and in every mode from Copilot CLI 1.0.104 (about 2,040 tokens a call); none of the
    # 60 sessions of October 27 called them. "_" is a word character, so plain \b would miss "my_audit_workflow".
    "workflows": (
        ("run_dynamic_workflow", "dynamic_workflows_manage"),
        re.compile(r"(?<![a-z0-9])workflows?(?![a-z0-9])", re.I),
    ),
}
LEAN_EXCLUDED_TOOLS = tuple(tool for tools, _ in CAPABILITY_GROUPS.values() for tool in tools)
_TOOL_FLAGS = ("--available-tools", "--excluded-tools")


def _installed_names(subfolder: str) -> set[str]:
    """Installed skill or agent names in <COPILOT_HOME> and the current repository."""
    copilot = Path(os.environ.get("COPILOT_HOME") or Path.home() / ".copilot")
    cwd = Path.cwd()
    names: set[str] = set()
    for root in (copilot / subfolder, cwd / ".github" / subfolder, cwd / ".claude" / subfolder):
        try:
            for entry in root.iterdir() if root.is_dir() else ():
                stem = entry.name.split(".")[0].lower()
                if len(stem) >= 3 and stem != "token-master":
                    names.add(stem)
        except OSError:
            pass
    return names


def select_excluded_tools(command: list[str]) -> tuple[str, ...]:
    """Prune auxiliary tool families not needed by the command's flags, prompt, installed assets, or env."""
    keep: set[str] = set()
    env_keep = os.environ.get("TOKENMASTER_KEEP_TOOLS", "")
    for token in (part.strip() for part in env_keep.split(",") if part.strip()):
        if token in CAPABILITY_GROUPS:
            keep.update(CAPABILITY_GROUPS[token][0])
        else:
            keep.add(token)
    prompts: list[str] = []
    rest = command[1:]
    for index, arg in enumerate(rest):
        head, eq, val = arg.partition("=")
        if head in ("-p", "--prompt"):
            prompts.append(val if eq else (rest[index + 1] if index + 1 < len(rest) else ""))
        elif head == "--agent":
            keep.update(CAPABILITY_GROUPS["agents"][0])
        elif head in ("--resume", "--continue"):
            keep.update(CAPABILITY_GROUPS["session_history"][0])
    prompt_text = "\n".join(prompts).lower()
    if prompt_text:
        for tools, pattern in CAPABILITY_GROUPS.values():
            if pattern.search(prompt_text):
                keep.update(tools)
        words = set(re.findall(r"[a-z0-9][\w-]*", prompt_text))
        if words & _installed_names("skills"):
            keep.update(CAPABILITY_GROUPS["skills"][0])
        if words & _installed_names("agents"):
            keep.update(CAPABILITY_GROUPS["agents"][0])
    if "skill" in keep:
        # A skill or slash command may start a workflow (the workflow tools' own instructions) or hand work to a
        # subagent. Keeping the agent tools adds about 2,670 cl100k tokens a call on 1.0.104 with no custom agents
        # installed: their definitions and the subagent instructions Copilot CLI then adds to its system prompt.
        keep.update(CAPABILITY_GROUPS["workflows"][0])
        keep.update(CAPABILITY_GROUPS["agents"][0])
    return tuple(tool for tool in LEAN_EXCLUDED_TOOLS if tool not in keep)


def lean_command(command: list[str]) -> list[str]:
    """Copilot CLI sessions get dynamic --excluded-tools, unless the user already chose tools or runs a subcommand."""
    if not command or Path(command[0]).stem.lower() != "copilot":
        return command
    rest = command[1:]
    if (rest and not rest[0].startswith("-")) or any(arg.split("=")[0] in _TOOL_FLAGS for arg in rest):
        return command
    excluded = select_excluded_tools(command)
    return [*command, "--excluded-tools", *excluded] if excluded else command


def launch_registry() -> Path:
    """Where the launcher records Copilot CLI launches for tokenomics.py: <COPILOT_HOME>/token-master/launches.jsonl."""
    return Path(os.environ.get("COPILOT_HOME") or Path.home() / ".copilot") / "token-master" / "launches.jsonl"


def _record_launch(event: dict) -> None:
    try:  # bookkeeping only: never fail or delay a launch over it
        path = launch_registry()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")
    except OSError:
        pass


def _nav_installed(command: list[str] = ()) -> bool:
    paths = [launch_registry().parents[1] / "mcp-config.json"]
    for index, arg in enumerate(command):
        value = arg.partition("=")[2] if arg.startswith("--additional-mcp-config=") else (
            command[index + 1] if arg == "--additional-mcp-config" and index + 1 < len(command) else "")
        if "tokenmaster-nav" in value:
            return True
        if value.startswith("@"):
            paths.append(Path(value[1:]))
    for path in paths:
        try:
            config = json.loads(path.read_text(encoding="utf-8-sig"))
            if "tokenmaster-nav" in (config.get("mcpServers") or {}):
                return True
        except (OSError, ValueError, AttributeError):
            continue
    return False


def run_recorded(parser, command: list[str], env: dict, *, lean: bool, bridge: bool) -> int:
    """run_child, plus a start and an end record (folder, lean tool set, bridge, navigation tools; no prompt text)."""
    if Path(command[0]).stem.lower() != "copilot":
        return run_child(parser, command, env)
    launch_id = hashlib.sha256(f"{time.time_ns()}-{os.getpid()}".encode()).hexdigest()[:16]
    now = lambda: datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")  # noqa: E731
    _record_launch({"event": "start", "id": launch_id, "at": now(), "cwd": os.getcwd(), "lean": lean,
                    "bridge": bridge, "nav": _nav_installed(command)})
    try:
        return run_child(parser, command, env)
    finally:
        _record_launch({"event": "end", "id": launch_id, "at": now()})


def _prefix_digest(request: dict) -> str:
    """Hash of everything before the first user message: the part that sessions can share."""
    head = []
    for item in request["input"] if type(request.get("input")) is list else []:
        if type(item) is dict and item.get("role") == "user":
            break
        head.append(item)
    blob = json.dumps([request.get("instructions"), request.get("tools"), head], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def rewrite_request(body: dict, count=None) -> tuple[dict, dict]:
    """Pure: the same request always gives the same result. ``count`` None turns v6 shaping off."""
    request = stable_session_prefix(body)
    moved = request is not body
    if not moved:
        request = copy.deepcopy(body)
    items = request["input"] if type(request.get("input")) is list else []
    calls = {item.get("call_id"): item for item in items
             if type(item) is dict and item.get("type") == "function_call"}
    shaped = outputs = 0
    for item in items:
        if type(item) is not dict or item.get("type") != "function_call_output":
            continue
        outputs += 1
        call = calls.get(item.get("call_id"))
        name = call.get("name") if call else None
        if count is None or type(item.get("output")) is not str or type(name) is not str or tool_kind(name) == "other":
            continue
        try:
            arguments = json.loads(call.get("arguments") or "{}")
        except (TypeError, ValueError):
            continue
        if type(arguments) is not dict:
            continue
        result = shape_tool_result(name, arguments, item["output"], count)
        if result != item["output"]:
            item["output"] = result
            shaped += 1
    return request, {"stable_prefix": moved, "shaped": shaped, "tool_outputs": outputs,
                     "prefix_sha256": _prefix_digest(request)}


def _blocks(holder: dict, key: str) -> list:
    """(holder, key) for each text of an Anthropic content field, in order."""
    value = holder.get(key)
    if type(value) is str:
        return [(holder, key)]
    if type(value) is list:
        return [(b, "text") for b in value if type(b) is dict and b.get("type", "text") == "text"
                and type(b.get("text")) is str]
    return []


def rewrite_messages_request(body: dict, count=None) -> tuple[dict, dict]:
    """The same two rewrites for Anthropic Messages requests (Copilot CLI with COPILOT_PROVIDER_TYPE=anthropic):
    the session-folder line moves from `system` to the first user message, and v6 shapes tool_result blocks."""
    request = copy.deepcopy(body)
    messages = request["messages"] if type(request.get("messages")) is list else []
    user = next((m for m in messages if type(m) is dict and m.get("role") == "user"), None)
    system = _blocks(request, "system")
    found = list(_SESSION_FOLDER.finditer("".join(h[k] for h, k in system)))
    target = _blocks(user, "content") if user else []
    moved = len(found) == 1 and bool(target)
    if moved:
        match = found[0]
        _replace_span(system, match.start(), match.end(), SESSION_FOLDER_MOVED)
        holder, key = target[0]
        holder[key] = f"Session folder: {match.group(1).strip()}\n\n" + holder[key]
    uses = {b.get("id"): b for m in messages if type(m) is dict and m.get("role") == "assistant"
            and type(m.get("content")) is list for b in m["content"] if type(b) is dict and b.get("type") == "tool_use"}
    shaped = outputs = 0
    for message in messages:
        if type(message) is not dict or message.get("role") != "user" or type(message.get("content")) is not list:
            continue
        for block in message["content"]:
            if type(block) is not dict or block.get("type") != "tool_result":
                continue
            outputs += 1
            use = uses.get(block.get("tool_use_id"))
            name, arguments = (use or {}).get("name"), (use or {}).get("input")
            texts = _blocks(block, "content")
            if (count is None or block.get("is_error") or type(name) is not str or tool_kind(name) == "other"
                    or type(arguments) is not dict or len(texts) != 1
                    or (type(block["content"]) is list and len(block["content"]) != 1)):
                continue
            holder, key = texts[0]
            result = shape_tool_result(name, arguments, holder[key], count)
            if result != holder[key]:
                holder[key] = result
                shaped += 1
    digest = hashlib.sha256(json.dumps([request.get("system"), request.get("tools")], sort_keys=True,
                                       ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    return request, {"stable_prefix": moved, "shaped": shaped, "tool_outputs": outputs, "prefix_sha256": digest}


def _usage(tail: bytes) -> dict:
    """Provider-reported usage from a JSON or event-stream response, normalized: input counts every prompt token
    (Anthropic's input_tokens excludes cache reads and writes); no content."""
    text = tail.decode("utf-8", "replace")
    found, at = [], text.find('"usage":')
    while at >= 0:
        start = at + len('"usage":')
        while start < len(text) and text[start] in " \t\r\n":
            start += 1
        try:
            value = json.JSONDecoder().raw_decode(text, start)[0]
            if type(value) is dict:
                found.append(value)
        except ValueError:
            pass
        at = text.find('"usage":', start)
    if any("cache_read_input_tokens" in u or "cache_creation_input_tokens" in u for u in found):
        merged = {}
        for usage in found:  # message_start carries the prompt numbers; the last message_delta the output total
            merged.update({k: v for k, v in usage.items() if v is not None})
        read, write = merged.get("cache_read_input_tokens") or 0, merged.get("cache_creation_input_tokens") or 0
        if merged.get("input_tokens") is None:
            return {}
        return {"input": merged["input_tokens"] + read + write, "cached": read, "cache_write": write,
                "output": merged.get("output_tokens")}
    usage = next((u for u in reversed(found) if "input_tokens" in u), None)
    if usage is None:
        return {}
    details = usage.get("input_tokens_details") or {}
    return {"input": usage.get("input_tokens"), "cached": details.get("cached_tokens"),
            "cache_write": details.get("cache_write_tokens"), "output": usage.get("output_tokens")}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def do_GET(self):
        self._forward(None)

    def do_POST(self):
        try:
            body = self._body()
        except ValueError:
            self._reply(413, b'{"error":"tokenmaster_bridge_request_rejected"}')
            return
        self._forward(body)

    def _body(self) -> bytes:
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            parts, total = [], 0
            while True:
                size = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                if not size:
                    while self.rfile.readline().strip():
                        pass
                    return b"".join(parts)
                total += size
                if total > MAX_BODY:
                    raise ValueError("request too large")
                parts.append(self.rfile.read(size))
                self.rfile.readline()
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError("request too large")
        return self.rfile.read(length)

    def _reply(self, status: int, payload: bytes) -> None:
        self.close_connection = True
        self.send_response_only(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)

    def _forward(self, body: bytes | None) -> None:
        bridge = self.server.bridge
        if not self.path.startswith("/"):
            self._reply(400, b'{"error":"tokenmaster_bridge_path_must_be_origin_form"}')  # never another host
            return
        body, receipt = bridge.prepare(self.path, body)
        request = urllib.request.Request(bridge.upstream + self.path, data=body, method=self.command,
                                         headers=bridge.upstream_headers(self.headers))
        try:
            response = bridge.opener.open(request, timeout=bridge.timeout)
        except urllib.error.HTTPError as error:
            response = error
        except (OSError, ValueError, http.client.HTTPException) as error:
            self._reply(502, json.dumps({"error": f"tokenmaster_bridge_upstream_{type(error).__name__}"}).encode())
            return
        status = getattr(response, "status", None) or response.code
        tail = bytearray()
        with response:
            self.send_response_only(status)
            for key, value in response.headers.items():
                if key.lower() not in _HOP:
                    self.send_header(key, value)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            read = getattr(response, "read1", None) or response.read
            try:
                while chunk := read(65536):
                    self.wfile.write(b"%X\r\n%s\r\n" % (len(chunk), chunk))
                    self.wfile.flush()
                    tail += chunk
                    if len(tail) > 2_000_000:  # usage sits at the end; keep only the end
                        del tail[:-1_000_000]
                self.wfile.write(b"0\r\n\r\n")
            except (OSError, ValueError, http.client.HTTPException):
                self.close_connection = True  # the client or the upstream went away mid-stream
        bridge.record(self.path, status, receipt, bytes(tail))


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # The bridge shares a terminal with Copilot CLI: no tracebacks there. A client that closes a
        # kept-alive connection is normal; anything else gets one line.
        error = sys.exc_info()[1]
        if not isinstance(error, (ConnectionError, TimeoutError)):
            print(f"[tokenmaster] bridge request failed: {type(error).__name__}", file=sys.stderr)


class Bridge:
    """Local Responses bridge on 127.0.0.1; use as a context manager."""

    def __init__(self, upstream: str, *, port: int = 0, log: str | Path | None = None, count=None,
                 timeout: float = 600):
        parts = urlsplit(upstream or "")
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("upstream must be an http or https URL")
        self.upstream = upstream.rstrip("/")
        self.count, self.timeout = count, timeout
        self.log = Path(log) if log else None
        self._lock = threading.Lock()
        handlers = [urllib.request.ProxyHandler({})] if parts.hostname in _LOOPBACK else []
        self.opener = urllib.request.build_opener(*handlers)
        self.server = _Server(("127.0.0.1", port), _Handler)
        self.server.bridge = self

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()

    def prepare(self, path: str, body: bytes | None) -> tuple[bytes | None, dict]:
        """Rewrite Responses and Anthropic Messages requests; every other request passes through unchanged."""
        route = urlsplit(path).path
        if body is None or not route.endswith(("/responses", "/messages")):
            return body, {}
        try:
            parsed = json.loads(body)
        except ValueError:
            return body, {}
        if type(parsed) is not dict:
            return body, {}
        rewrite = rewrite_request if route.endswith("/responses") else rewrite_messages_request
        request, receipt = rewrite(parsed, self.count)
        return json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), receipt

    def upstream_headers(self, headers) -> dict:
        return {key: value for key, value in headers.items() if key.lower() not in _HOP}

    def record(self, path: str, status: int, receipt: dict, tail: bytes) -> None:
        if self.log is None or not receipt:
            return
        row = {"t": round(time.time(), 3), "path": urlsplit(path).path, "status": status, **receipt, **_usage(tail)}
        with self._lock, self.log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")


def run_child(parser, command: list[str], env: dict) -> int:
    try:
        child = subprocess.Popen([shutil.which(command[0]) or command[0], *command[1:]], env=env)
    except OSError as error:
        parser.error(f"cannot run {command[0]}: {error.strerror or error}")
    while True:
        try:
            return child.wait()
        except KeyboardInterrupt:
            continue  # Copilot CLI handles Ctrl+C itself; keep the bridge up until it exits


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--upstream", default=os.environ.get("COPILOT_PROVIDER_BASE_URL"),
                        help="Responses or Anthropic API base URL (default: the current COPILOT_PROVIDER_BASE_URL). "
                             "Without one, Copilot CLI keeps its normal routing and the launcher applies only the "
                             "lean tool set.")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--log", help="append one JSON line per model request: usage numbers, no content")
    parser.add_argument("--all-tools", action="store_true",
                        help="keep every built-in Copilot CLI tool (default: exclude the ones no session used in "
                             "the October 18 runs and the two workflow tools)")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- copilot [args...]; omit to serve only")
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    original = list(command)
    if command and not args.all_tools:
        command = lean_command(command)
    lean = command != original
    if not args.upstream:
        if not command:
            parser.error("set --upstream or COPILOT_PROVIDER_BASE_URL to serve the bridge")
        print("[tokenmaster] no provider URL: Copilot CLI keeps its normal routing; lean tool set "
              f"{'off' if args.all_tools else 'on'}", file=sys.stderr)
        return run_recorded(parser, command, dict(os.environ), lean=lean, bridge=False)
    provider = os.environ.get("COPILOT_PROVIDER_TYPE") or "openai"
    if provider not in ("openai", "anthropic") or \
            (provider == "openai" and (os.environ.get("COPILOT_PROVIDER_WIRE_API") or "responses") != "responses"):
        parser.error("the bridge supports COPILOT_PROVIDER_TYPE=openai with the responses wire API, "
                     "or COPILOT_PROVIDER_TYPE=anthropic")
    installed = HERE / "tokenizer" / "cl100k_base.tiktoken"  # where brainspace_setup.py puts it
    if not os.environ.get("BRAINSPACE_TOKENIZER_FILE") and installed.is_file():
        os.environ["BRAINSPACE_TOKENIZER_FILE"] = str(installed)
    try:
        tokens.count_tokens("tokenmaster")  # load once, before server threads start
        count = tokens.count_tokens
    except tokens.ReferenceTokenizerUnavailable:
        count = None
    try:
        bridge = Bridge(args.upstream, port=args.port, log=args.log, count=count)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    with bridge:
        print(f"[tokenmaster] bridge {bridge.url} -> {bridge.upstream}; cache-stable system prompt on; "
              f"v6 shaping {'on' if count else 'off (verified tokenizer unavailable)'}; lean tool set "
              f"{'off' if args.all_tools else 'on'}", file=sys.stderr)
        if not command:
            print(f"COPILOT_PROVIDER_BASE_URL={bridge.url}", flush=True)
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                return 0
        env = {**os.environ, "COPILOT_PROVIDER_BASE_URL": bridge.url}
        if provider == "openai":
            env["COPILOT_PROVIDER_WIRE_API"] = "responses"
        return run_recorded(parser, command, env, lean=lean, bridge=True)


if __name__ == "__main__":
    raise SystemExit(main())
