"""Native MCP recovery for the exact parent-owned task runtime.

No local CCR, container, credential search or provider call is created here.
The task-local control credential authorizes only the parent's closed recovery
endpoint. The parent binds requests to actual issued native tool-call IDs.
"""
from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .runtime_io import parse_json


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class NativeRecoveryClient:
    def __init__(self, *, base_url, token, timeout=30, max_response_bytes=524288):
        url = urlparse(base_url)
        if (url.scheme != "http" or url.hostname != "127.0.0.1"
                or url.username or url.password or url.path not in ("", "/")
                or url.query or url.fragment):
            raise ValueError("explicit_native_loopback_control_required")
        if type(token) is not str or not 32 <= len(token) <= 256 or any(c.isspace() for c in token):
            raise ValueError("explicit_native_control_credential_required")
        if type(timeout) not in (int, float) or not 0 < timeout <= 90:
            raise ValueError("invalid_native_control_timeout")
        if type(max_response_bytes) is not int or not 0 < max_response_bytes <= 4_194_304:
            raise ValueError("invalid_native_control_response_bound")
        self.base_url, self._token = base_url.rstrip("/"), token
        self.timeout, self.max_response_bytes = timeout, max_response_bytes

    def recover(self, name, arguments):
        if name not in ("retrieve_original", "headroom_retrieve") or type(arguments) is not dict:
            raise ValueError("unsupported_native_recovery")
        data = json.dumps({"name": name, "arguments": arguments}, ensure_ascii=False,
                          allow_nan=False, separators=(",", ":")).encode("utf-8")
        if len(data) > 16384:
            raise ValueError("native_recovery_request_bound")
        request = Request(
            self.base_url + "/control/recover", data=data, method="POST",
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + self._token},
        )
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        try:
            response = opener.open(request, timeout=self.timeout)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read(self.max_response_bytes + 1)
            if response.status != 200 or len(raw) > self.max_response_bytes:
                raise ValueError("native_recovery_unavailable")
        body = parse_json(raw.decode("utf-8"))
        if type(body) is not dict or set(body) != {"ok", "content"} \
                or body["ok"] is not True or type(body["content"]) is not str:
            raise ValueError("invalid_native_recovery_reply")
        return body["content"]


def make_server(client):
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("tokenmaster-runtime")

    @server.tool(structured_output=False)
    def retrieve_original(ref: str, offset: int) -> str:
        """TokenMaster [[BR:...]] recovery: return an exact 32768-character page."""
        return client.recover("retrieve_original", {"ref": ref, "offset": offset})

    @server.tool(structured_output=False)
    def headroom_retrieve(hash: str) -> str:
        """Headroom recovery only: retrieve the hash from a Headroom marker."""
        return client.recover("headroom_retrieve", {"hash": hash})

    return server
