"""Predeclared supplementary explicit-context footprint, separate from body counts.

Omits vendor usage/response IDs/control metadata, NOT user text, schemas or call
pairs. Whole canonical projected strings are tokenized, never additive chunks.
This is not a proprietary chat-template count. Opaque state/multimodal inputs
reject rather than masquerade as fully materialized text. Never used for a
promotion certificate or substituted after inspecting favorable outcomes.
"""
import json


PROTOCOL = "explicit-context-fields-json-v1"


def _wire(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _message(item):
    if item.get("role") not in ("system", "developer", "user", "assistant"):
        raise ValueError("unsupported role")
    content = item.get("content")
    if not isinstance(content, str):
        if type(content) is not list or any(
            type(part) is not dict or part.get("type") not in ("input_text", "output_text", "refusal")
            for part in content
        ):
            raise ValueError("nontext message")
        retained = []
        for part in content:
            key = "refusal" if part["type"] == "refusal" else "text"
            if type(part.get(key)) is not str:
                raise ValueError("missing text")
            retained.append({k: part[k] for k in ("type", key, "annotations") if k in part})
        content = retained
    return {"role": item["role"], "content": content}


def _item(item):
    if type(item) is not dict:
        raise ValueError("invalid context item")
    kind = item.get("type")
    if kind == "message" or kind is None and "role" in item:
        return _message(item)
    if kind == "function_call":
        if any(type(item.get(k)) is not str for k in ("call_id", "name", "arguments")):
            raise ValueError("incomplete function call")
        return {k: item[k] for k in ("type", "call_id", "name", "arguments", "namespace") if k in item}
    if kind == "function_call_output":
        if type(item.get("call_id")) is not str or type(item.get("output")) is not str:
            raise ValueError("unsupported tool output")
        return {k: item[k] for k in ("type", "call_id", "output")}
    if kind == "reasoning" and not item.get("encrypted_content"):
        summary = item.get("summary", [])
        if type(summary) is not list or any(type(x) is not dict or type(x.get("text")) is not str for x in summary):
            raise ValueError("unsupported reasoning summary")
        return {"type": "reasoning_summary", "text": [x["text"] for x in summary]}
    raise ValueError("opaque or unsupported context item")


def input_context_text(request):
    if request.get("previous_response_id") or request.get("conversation"):
        raise ValueError("remote state is not materialized input")
    incoming = request["input"]
    if isinstance(incoming, str):
        incoming = [{"role": "user", "content": incoming}]
    if type(incoming) is not list:
        raise ValueError("invalid request shape")
    projected = {"input": [_item(item) for item in incoming]}
    for key in ("tools", "instructions"):
        if key in request:
            projected[key] = request[key]
    return _wire(projected)


def context_texts(request, response):
    if type(response.get("output")) is not list:
        raise ValueError("invalid response shape")
    return input_context_text(request), _wire([_item(item) for item in response["output"]])
