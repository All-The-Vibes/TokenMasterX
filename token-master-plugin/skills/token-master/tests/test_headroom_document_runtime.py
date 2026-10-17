"""Bound document selection before upstream work; real runtime/wire guards."""
from copy import deepcopy
import json

import pytest

from brainspace import headroom, tokens
from brainspace.request_policy import SourceReadInfo
from brainspace.runtime import RuntimeSession
from brainspace.runtime_policy import RuntimePolicy
from brainspace.runtime_resources import RuntimeResources
from brainspace.transport import Reply


STRATEGY = "native-documents-v1"
TEXT = "Document prose about exact task execution and independent validation.\n" * 100


class Transport:
    model = "document-fixture"
    max_request_bytes = 524288
    max_output_tokens = 2048

    def __init__(self):
        self.sent = []

    def encode(self, value):
        return tokens.serialize(value)

    def send(self, value):
        self.sent.append(value)
        answer = json.dumps({"model": self.model, "usage": {
            "input_tokens": 10, "output_tokens": 5, "total_tokens": 15}})
        return Reply(True, "ok", True, value, answer, json.loads(answer), 200)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    state = {"starts": 0, "calls": [], "mutate_protected": False, "replacement": "Short document view."}

    class Backend:
        def __init__(self, directory, **kwargs):
            state["options"] = kwargs
            directory.mkdir()

        def start(self):
            state["starts"] += 1
            return {"ready": True}

        def prepare(self, request, **controls):
            state["calls"].append((deepcopy(request), deepcopy(controls)))
            messages = deepcopy(request["messages"])
            for index in controls["eligible_indices"]:
                messages[index]["content"] = state["replacement"]
            if state["mutate_protected"]:
                messages[0]["content"] = "unexpected rewrite"
            return {"model": request["model"], "messages": messages}

        def finish(self):
            return {}

        def close(self):
            return {"container_removed": True}

    monkeypatch.setattr(headroom, "HeadroomContainer", Backend)
    monkeypatch.setattr(RuntimeResources, "resolve", lambda self, policy: {
        "ponytail": None, "headroom_options": {
            "cache": tmp_path / "cache", "assets": tmp_path / "assets",
            "docker_config": None, "strategy": STRATEGY,
        },
    })
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session = RuntimeSession(
        workspace=workspace, output=tmp_path / "runtime", session_id="documents",
        transport=Transport(), runtime_policy=RuntimePolicy(
            backend="headroom", headroom_strategy=STRATEGY, require_nonexpanding_input=True),
        runtime_resources=RuntimeResources(),
    )
    yield session, state
    session.close()


def request(session, *, path="notes.md", status="success", bound=True, content=TEXT, tool="view"):
    messages = [{"role": "system", "content": "Keep instructions."},
                {"role": "user", "content": "Give an overview."}]
    for call_id, text in (("old", content), ("new", "newest")):
        messages += [
            {"role": "assistant", "tool_calls": [{"id": call_id, "type": "function",
              "function": {"name": tool, "arguments": json.dumps({"path": path})}}]},
            {"role": "tool", "tool_call_id": call_id, "content": text},
        ]
    if bound:
        session.observe_source_read(SourceReadInfo.from_text(
            call_id="old", tool_name=tool, source_path=path, content=content, status=status))
    return {"model": Transport.model, "messages": messages}


def test_only_bound_older_document_is_offered_and_name_preserved(setup):
    session, state = setup
    payload = request(session)
    original = deepcopy(payload)
    session.invoke(payload, intent="overview", stable_prefix_messages=2)
    assert payload == original
    assert state["starts"] == 1 and len(state["calls"]) == 1
    offered, controls = state["calls"][0]
    assert controls == {"eligible_indices": [3], "frozen_message_count": 2,
                        "keep_recent_tool_results": 1}
    assert offered == original | {"tools": RuntimeSession.recovery_tools()}
    emitted = json.loads(session.transport.sent[0])
    assert emitted["messages"][0] == original["messages"][0]
    assert emitted["messages"][-1] == original["messages"][-1]
    assert emitted["messages"][2]["tool_calls"][0]["function"]["name"] == "view"
    assert emitted["messages"][3]["content"] != TEXT
    assert tokens.count_tokens(session.transport.sent[0]) < tokens.count_tokens(
        session.transport.encode(original))


@pytest.mark.parametrize("change", [
    "no_receipt", "failure", "unknown", "code", "json", "exact", "edit",
    "debug", "recent", "prefix", "exact_index", "status", "short", "other_tool",
])
def test_ineligible_document_mode_never_starts_worker(setup, change):
    session, state = setup
    payload = request(session, path={"code": "source.py", "json": "data.json"}.get(change, "notes.md"),
                      status={"failure": "error", "unknown": "unknown"}.get(change, "success"),
                      bound=change != "no_receipt",
                      content="small" if change == "short" else TEXT,
                      tool="fetch_artifact" if change == "other_tool" else "view")
    if change == "recent":
        payload["messages"] = payload["messages"][:-2]
    if change == "status":
        payload["messages"][3]["isError"] = True
    session.invoke(
        payload, intent=change if change in ("exact", "edit", "debug") else "overview",
        stable_prefix_messages=4 if change == "prefix" else 0,
        exact_message_indices=(3,) if change == "exact_index" else (),
    )
    assert state["starts"] == 0 and state["calls"] == []
    assert json.loads(session.transport.sent[0]) == payload


def test_document_mode_rejects_any_protected_upstream_mutation(setup):
    session, state = setup
    state["mutate_protected"] = True
    with pytest.raises(ValueError, match="protected"):
        session.invoke(request(session), intent="overview")
    assert not session.transport.sent


def test_fenced_code_cannot_be_lost_in_an_accepted_view(setup):
    session, state = setup
    source = TEXT + "\n```python\nprint('preserve exactly')\n```\n"
    payload = request(session, content=source)
    session.invoke(payload, intent="overview")
    emitted = json.loads(session.transport.sent[0])
    assert emitted["messages"][3]["content"] == source
