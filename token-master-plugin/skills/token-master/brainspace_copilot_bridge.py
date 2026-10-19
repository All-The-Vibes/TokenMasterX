#!/usr/bin/env python
"""Run GitHub Copilot CLI through a local TokenMaster bridge (opt-in; Copilot CLI BYOK mode).

Copilot CLI sends model requests to COPILOT_PROVIDER_BASE_URL. The bridge listens on
127.0.0.1, rewrites each Responses API request, and forwards it to one upstream: --upstream,
or the COPILOT_PROVIDER_BASE_URL that was already set. The bridge never reads, stores or adds
credentials. The client's headers, including Authorization, go to the upstream unchanged.

The bridge applies two deterministic rewrites to every request. Each call of a session
therefore sends the same bytes for its history, and the provider's prefix cache stays valid:
- the cache-stable system prompt (brainspace.native_transport.stable_session_prefix; PRS-4);
- request-policy-v6 shaping of grep, glob and whole-file view results
  (brainspace.v6_shaping.shape_tool_result; PRS-2 and PRS-3). Other tool results pass through.

  python brainspace_copilot_bridge.py [--upstream URL] [--log usage.jsonl] -- copilot [args...]
  python brainspace_copilot_bridge.py [--upstream URL]          (serve only; prints the base URL)

The upstream must accept OpenAI Responses requests at <upstream>/responses.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import http.client
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from brainspace import tokens  # noqa: E402
from brainspace.native_transport import stable_session_prefix  # noqa: E402
from brainspace.v6_shaping import shape_tool_result, tool_kind  # noqa: E402

MAX_BODY = 64 * 1024 * 1024
_HOP = frozenset({"host", "content-length", "connection", "keep-alive", "proxy-authorization",
                  "proxy-connection", "te", "trailer", "transfer-encoding", "upgrade", "accept-encoding"})
_LOOPBACK = ("127.0.0.1", "localhost", "::1")


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


def _usage(tail: bytes) -> dict:
    """Provider-reported usage from the end of a JSON or event-stream response; no content."""
    text = tail.decode("utf-8", "replace")
    at = text.rfind('"usage":')
    if at < 0:
        return {}
    start = at + len('"usage":')
    while start < len(text) and text[start] in " \t\r\n":
        start += 1
    try:
        usage = json.JSONDecoder().raw_decode(text, start)[0]
    except ValueError:
        return {}
    if type(usage) is not dict:
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
        """Rewrite Responses requests; every other request passes through unchanged."""
        if body is None or not urlsplit(path).path.endswith("/responses"):
            return body, {}
        try:
            parsed = json.loads(body)
        except ValueError:
            return body, {}
        if type(parsed) is not dict:
            return body, {}
        request, receipt = rewrite_request(parsed, self.count)
        return json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), receipt

    def upstream_headers(self, headers) -> dict:
        return {key: value for key, value in headers.items() if key.lower() not in _HOP}

    def record(self, path: str, status: int, receipt: dict, tail: bytes) -> None:
        if self.log is None or not receipt:
            return
        row = {"t": round(time.time(), 3), "path": urlsplit(path).path, "status": status, **receipt, **_usage(tail)}
        with self._lock, self.log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--upstream", default=os.environ.get("COPILOT_PROVIDER_BASE_URL"),
                        help="Responses API base URL (default: the current COPILOT_PROVIDER_BASE_URL)")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--log", help="append one JSON line per model request: usage numbers, no content")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- copilot [args...]; omit to serve only")
    args = parser.parse_args(argv)
    if not args.upstream:
        parser.error("set --upstream or COPILOT_PROVIDER_BASE_URL")
    if (os.environ.get("COPILOT_PROVIDER_TYPE") or "openai") != "openai" \
            or (os.environ.get("COPILOT_PROVIDER_WIRE_API") or "responses") != "responses":
        parser.error("the bridge supports COPILOT_PROVIDER_TYPE=openai with the responses wire API only")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
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
              f"v6 shaping {'on' if count else 'off (verified tokenizer unavailable)'}", file=sys.stderr)
        if not command:
            print(f"COPILOT_PROVIDER_BASE_URL={bridge.url}", flush=True)
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                return 0
        env = {**os.environ, "COPILOT_PROVIDER_BASE_URL": bridge.url, "COPILOT_PROVIDER_WIRE_API": "responses"}
        try:
            child = subprocess.Popen([shutil.which(command[0]) or command[0], *command[1:]], env=env)
        except OSError as error:
            parser.error(f"cannot run {command[0]}: {error.strerror or error}")
        while True:
            try:
                return child.wait()
            except KeyboardInterrupt:
                continue  # Copilot CLI handles Ctrl+C itself; keep the bridge up until it exits


if __name__ == "__main__":
    raise SystemExit(main())
