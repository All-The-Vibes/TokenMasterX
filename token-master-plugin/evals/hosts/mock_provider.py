"""Minimal synthetic Anthropic/Responses provider; localhost transport, no AI."""
from copy import deepcopy
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
from typing import Any


def tool_names(tools, namespace=None):
    result = []
    for tool in tools:
        if tool.get("type") == "namespace":
            result.extend(tool_names(tool.get("tools", []), tool["name"]))
        else:
            function = tool.get("function", tool)
            if function.get("name"):
                result.append((function["name"], namespace))
    return result


class MockProvider:
    def __init__(self, scenario, fixture_path, reference, *, tool_steps=None):
        self.scenario, self.fixture_path, self.reference = scenario, fixture_path, reference
        # Evaluation-only predetermined actions; never instructions from a model
        # or arbitrary commands parsed from tool output.
        self.tool_steps = tool_steps
        self.requests: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self.stage = 0
        self.warmup = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_CONNECT(self):
                self.send_error(403, "External network is not a mock-provider operation")

            def do_GET(self):
                self.json({"object": "list", "data": [{"id": "gpt-5.4", "object": "model"}]})

            def json(self, value):
                data = json.dumps(value).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def events(self, events):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                for name, event in events:
                    self.wfile.write(("event: " + name + "\ndata: " + json.dumps(event) + "\n\n").encode())
                    self.wfile.flush()
                self.close_connection = True

            def do_POST(self):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                    if "count_tokens" in self.path:
                        self.json({"input_tokens": 100})
                        return
                    if not any(part in self.path for part in ("/messages", "/responses")):
                        self.json({})
                        return
                    owner.requests.append({"path": self.path, "body": body})
                    action = owner.action(body)
                    if "/responses" in self.path:
                        events = owner.responses(action, body)
                        if body.get("stream") is True:
                            self.events(events)
                        else:
                            self.json(events[-1][1]["response"])
                    else:
                        message, events = owner.anthropic(action, body)
                        self.events(events) if body.get("stream") else self.json(message)
                except Exception as exc:
                    owner.errors.append(repr(exc))
                    self.send_error(500, "Synthetic provider failure")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def action(self, body):
        names = tool_names(body.get("tools", []))
        for item in body.get("input", []):
            if isinstance(item, dict) and item.get("type") == "tool_search_output":
                names.extend(tool_names(item.get("tools", [])))
        if self.tool_steps is not None:
            expected = [name for name, _ in self.tool_steps]
            inputs = [arguments for _, arguments in self.tool_steps]
        elif self.scenario == "hook":
            expected = ["Read"]
            inputs = [{"file_path": str(self.fixture_path)}]
        else:
            expected = ["brainspace_stats", "brainspace_retrieve"]
            inputs = [{}, {"ref": self.reference, "offset": 0, "limit": 32768}]
        if self.stage >= len(expected):
            return None
        wanted = expected[self.stage]
        match = next(((name, ns) for name, ns in names if name == wanted or name.endswith(wanted)), None)
        if not match:
            if not self.warmup and any(t.get("type") == "tool_search" for t in body.get("tools", [])):
                self.warmup = True
                result = {"kind": "tool_search", "name": "tool_search", "namespace": None,
                          "arguments": {"query": "brainspace brainspace_stats brainspace_retrieve", "limit": 2},
                          "call_id": "smoke_discovery"}
                self.actions.append(result)
                return result
            if not self.warmup and any(n == "list_mcp_resources" for n, ns in names):
                self.warmup = True
                result = {"name": "list_mcp_resources", "namespace": None,
                          "arguments": {"server": "brainspace"}, "call_id": "smoke_warmup"}
                self.actions.append(result)
                return result
            self.errors.append(f"Required tool {wanted!r} absent; available={names}")
            return None
        result = {"name": match[0], "namespace": match[1], "arguments": inputs[self.stage],
                  "call_id": f"smoke_call_{self.stage}"}
        self.stage += 1
        self.actions.append(result)
        return result

    def anthropic(self, action, request):
        content = ({"type": "tool_use", "id": action["call_id"], "name": action["name"],
                    "input": action["arguments"]} if action else
                   {"type": "text", "text": "MOCK_TRANSPORT_DONE"})
        reason = "tool_use" if action else "end_turn"
        message = {"id": f"msg_smoke_{len(self.requests)}", "type": "message", "role": "assistant",
                   "content": [content], "model": request.get("model", "mock"),
                   "stop_reason": reason, "stop_sequence": None,
                   "usage": {"input_tokens": 100, "output_tokens": 10}}
        start = {**message, "content": [], "stop_reason": None}
        block = {**content, "input": {}} if action else {"type": "text", "text": ""}
        delta = ({"type": "input_json_delta", "partial_json": json.dumps(action["arguments"])}
                 if action else {"type": "text_delta", "text": content["text"]})
        events = [
            ("message_start", {"type": "message_start", "message": start}),
            ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": block}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": delta}),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            ("message_delta", {"type": "message_delta", "delta": {"stop_reason": reason, "stop_sequence": None},
                               "usage": {"output_tokens": 10}}),
            ("message_stop", {"type": "message_stop"}),
        ]
        return message, events

    def responses(self, action, request):
        """Build synthetic Responses events; fixed usage is not measured cost."""
        rid = f"resp_smoke_{len(self.requests)}"
        item: dict[str, Any] = ({"id": "fc_" + rid, "type": "function_call", "call_id": action["call_id"],
                 "name": action["name"], "arguments": json.dumps(action["arguments"]),
                 "status": "completed"} if action else
                {"id": "msg_" + rid, "type": "message", "role": "assistant", "status": "completed",
                 "content": [{"type": "output_text", "text": "MOCK_TRANSPORT_DONE",
                              "annotations": [], "logprobs": []}]})
        if action and action.get("kind") == "tool_search":
            item = {"id": "ts_" + rid, "type": "tool_search_call", "execution": "client",
                    "call_id": action["call_id"], "status": "completed", "arguments": action["arguments"]}
        if action and action.get("namespace"):
            item["namespace"] = action["namespace"]
        response = {"id": rid, "object": "response", "created_at": int(time.time()),
                    "status": "completed", "model": request.get("model", "mock"),
                    "metadata": {"usage_source": "synthetic"},
                    "output": [item], "usage": {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110}}
        events: list[tuple[str, dict[str, Any]]] = []

        def emit(kind: str, **fields: Any) -> None:
            # Clients may accumulate into added items: snapshots must not alias
            # either later events or the completed nonstream response.
            events.append((kind, {"type": kind, "sequence_number": len(events),
                                  "response_id": rid, **deepcopy(fields)}))

        pending = {**response, "status": "in_progress", "output": [], "usage": None}
        emit("response.created", response=pending)
        emit("response.in_progress", response=pending)
        if item["type"] == "function_call":
            emit("response.output_item.added", output_index=0,
                 item={**item, "status": "in_progress", "arguments": ""})
            arguments = item["arguments"]
            # Chunk the serialized string, not the object; even split JSON
            # escapes reconstruct exactly once when consumers join the deltas.
            for offset in range(0, len(arguments), 8):
                emit("response.function_call_arguments.delta", item_id=item["id"],
                     output_index=0, delta=arguments[offset:offset + 8])
            emit("response.function_call_arguments.done", item_id=item["id"],
                 output_index=0, arguments=arguments)
        elif item["type"] == "message":
            emit("response.output_item.added", output_index=0,
                 item={**item, "status": "in_progress", "content": []})
            part = item["content"][0]
            indices = {"item_id": item["id"], "output_index": 0, "content_index": 0}
            emit("response.content_part.added", **indices, part={**part, "text": ""})
            text = part["text"]
            for offset in range(0, len(text), 8):
                emit("response.output_text.delta", **indices, delta=text[offset:offset + 8], logprobs=[])
            emit("response.output_text.done", **indices, text=text, logprobs=[])
            emit("response.content_part.done", **indices, part=part)
        else:
            # Deferred client tool_search has object arguments, not ordinary
            # function-call argument deltas. Preserve its explicit protocol.
            emit("response.output_item.added", output_index=0, item=item)
        emit("response.output_item.done", output_index=0, item=item)
        emit("response.completed", response=response)
        return events
