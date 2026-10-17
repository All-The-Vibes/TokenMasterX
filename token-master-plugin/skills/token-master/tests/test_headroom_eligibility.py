"""Offline Headroom admission tests; fake pipeline, real runtime guards/counters."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import re
import socket
from typing import Any

import pytest

from brainspace import headroom, runtime, tokens
from brainspace.request_policy import RequestPolicy, SourceReadInfo
from brainspace.runtime import RuntimeSession
from brainspace.transport import Reply


TEXT = "Ordinary source paragraph with useful details.\n" * 200
STRATEGY = "bound-source-eligibility-before-start-v1"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("no model or Docker/network calls in eligibility tests")
    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


class Transport:
    model = "offline-eligibility"
    max_request_bytes = 524288
    max_output_tokens = 2048

    def __init__(self) -> None:
        self.sent: list[str] = []

    def encode(self, chat: dict[str, Any]) -> str:
        return tokens.serialize({"request": chat, "max_output_tokens": self.max_output_tokens})

    def send(self, wire: str) -> Reply:
        self.sent.append(wire)
        output = json.dumps({"model": self.model, "usage": {
            "input_tokens": 10, "output_tokens": 5, "total_tokens": 15}})
        return Reply(True, "ok", True, wire, output, json.loads(output), 200)


@pytest.fixture
def component(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"started": 0, "created": 0, "prepared": [], "finished": 0,
                             "closed": 0, "retrieved": [], "replacement": "A small source view.",
                             "proposal": None}

    class Backend:
        def __init__(self, directory: Path, **kwargs: Any) -> None:
            state["created"] += 1
            directory.mkdir()

        def start(self) -> dict[str, Any]:
            state["started"] += 1
            return {"ready": True}

        def prepare(self, chat: dict[str, Any]) -> dict[str, Any]:
            state["prepared"].append(deepcopy(chat))
            if state["proposal"]:
                return state["proposal"](chat)
            messages = deepcopy(chat["messages"])
            for message in messages:
                if message["role"] == "tool":
                    message["content"] = state["replacement"]
            return {"model": chat["model"], "messages": messages}

        def retrieve(self, args: Any, tool_call_id: str) -> str:
            state["retrieved"].append(tool_call_id)
            return "Exact upstream fragment."

        def finish(self) -> dict[str, Any]:
            state["finished"] += 1
            return {"pipeline_invocations": len(state["prepared"])}

        def close(self) -> dict[str, Any]:
            state["closed"] += 1
            return {"container_id": None, "container_removed": True}

    monkeypatch.setattr(headroom, "HeadroomContainer", Backend)
    return state


def make(tmp_path: Path, *, guard: bool = True, **options: Any) -> RuntimeSession:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return RuntimeSession(
        workspace=workspace, output=tmp_path / "runtime", session_id="eligibility",
        backend="headroom", transport=Transport(), require_nonexpanding_input=guard,
        headroom_options={"cache": tmp_path / "cache", "assets": tmp_path / "assets",
                          "docker_config": None}, **options)


def request() -> dict[str, Any]:
    return {"model": Transport.model, "messages": [
        {"role": "system", "content": "Keep instructions."},
        {"role": "user", "content": "Inspect the documents."}]}


def add_read(session: RuntimeSession, chat: dict[str, Any], *, call_id: str = "old",
             content: Any = TEXT, tool: str = "read_file", path: str = "notes.md",
             bound: bool = True, status: str = "success") -> int:
    call = {"id": call_id, "type": "function", "function": {
        "name": tool, "arguments": json.dumps({"path": path})}}
    chat["messages"].extend([
        {"role": "assistant", "content": None, "tool_calls": [call]},
        {"role": "tool", "tool_call_id": call_id, "content": content}])
    if bound:
        session.observe_source_read(SourceReadInfo.from_text(
            call_id=call_id, tool_name=tool, source_path=path,
            content=content if type(content) is str else "nontext", status=status))
    return len(chat["messages"]) - 1


def prep(session: RuntimeSession) -> dict[str, Any]:
    return json.loads((session.output / "preparations.jsonl").read_text().splitlines()[-1])


@pytest.mark.parametrize("case", [
    "no_calls", "unbound", "not_success", "unknown", "wrong_hash", "wrong_path",
    "wrong_tool", "unsupported_tool", "recent", "exact", "prefix", "short", "nonstring",
    "error_status", "exit_status", "exact_metadata", "nested_error_metadata",
])
def test_ineligible_sources_do_not_start_or_prepare(
    tmp_path: Path, component: dict[str, Any], case: str,
) -> None:
    session = make(tmp_path)
    chat = request()
    prefix = 0
    exact: tuple[int, ...] = ()
    if case != "no_calls":
        index = add_read(
            session, chat, content="short" if case == "short" else
            [{"type": "text", "text": TEXT}] if case == "nonstring" else TEXT,
            bound=case != "unbound", status="error" if case == "not_success" else
            "unknown" if case == "unknown" else "success",
            tool="execute" if case == "unsupported_tool" else "read_file")
        if case in ("wrong_hash", "wrong_path", "wrong_tool"):
            old = session._source_reads["old"]
            session._source_reads["old"] = replace(old, **{
                "wrong_hash": {"content_sha256": "0" * 64},
                "wrong_path": {"source_path": "different.md"},
                "wrong_tool": {"tool_name": "fetch_artifact"},
            }[case])
        if case == "exact":
            exact = (index,)
        if case == "prefix":
            prefix = index + 1
        if case == "error_status":
            chat["messages"][index]["status"] = "failed"
        if case == "exit_status":
            chat["messages"][index]["exit_code"] = 1
        if case == "exact_metadata":
            chat["messages"][index]["preserve_exact"] = True
        if case == "nested_error_metadata":
            chat["messages"][index]["metadata"] = {"ok": False}
        if case != "recent":
            add_read(session, chat, call_id="new", content="recent", bound=False)
    before = deepcopy(chat)
    session.invoke(chat, intent="navigation", stable_prefix_messages=prefix, exact_message_indices=exact)
    assert component["created"] == component["started"] == 0 and not component["prepared"]
    assert chat == before and session.transport.sent == [session.transport.encode(before)]
    row = prep(session)
    assert row["input_composition"]["projection_reason"] == "headroom_no_eligible_sources"
    assert row["changed_messages"] == [] and row["prepared"] == before
    assert not (session.output / "docker-config").exists()
    assert not (session.output / "recovery.sqlite").exists()
    result = session.finish()
    assert result["model_calls"] == 1 and result["transformations"] == 0
    assert result["component"]["headroom_executed"] is False
    session.close()
    assert component["finished"] == component["closed"] == 0


def test_bad_pairing_is_rejected_before_start(tmp_path: Path, component: dict[str, Any]) -> None:
    session = make(tmp_path)
    chat = request()
    chat["messages"].append({"role": "tool", "tool_call_id": "orphan", "content": TEXT})
    with pytest.raises(ValueError, match="unpaired"):
        session.invoke(chat, intent="navigation")
    assert component["started"] == 0 and not component["prepared"]
    assert session.finish()["model_calls"] == 0
    session.close()


@pytest.mark.parametrize("tool,path", [("read_file", "source.py"), ("fetch_artifact", "manual.md")])
def test_eligible_source_calls_unchanged_pipeline_once_and_only_then_stashes_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, component: dict[str, Any], tool: str, path: str,
) -> None:
    session = make(tmp_path)
    chat = request()
    index = add_read(session, chat, tool=tool, path=path)
    add_read(session, chat, call_id="new", content="recent", bound=False)
    original = deepcopy(chat)
    stash = session.ccr.stash
    stashes: list[str] = []

    def checked_stash(content: str, **kwargs: Any) -> Any:
        assert len(component["prepared"]) == 1
        stashes.append(content)
        return stash(content, **kwargs)

    monkeypatch.setattr(session.ccr, "stash", checked_stash)
    session.invoke(chat, intent="overview")
    assert component["started"] == 1 and len(component["prepared"]) == 1
    augmented, _ = session._augment(original)
    assert component["prepared"][0] == augmented  # no masking, data/metadata rewriting or feature overrides
    assert stashes == [TEXT] and chat == original
    prepared = prep(session)["prepared"]
    assert prepared["messages"][index + 2]["content"] == "recent"
    match = re.search(r"\[\[BR:[^\]]+\]\]", prepared["messages"][index]["content"])
    assert match is not None
    assert session.ccr.retrieve(match.group()) == TEXT
    assert len(session.transport.sent) == 1
    assert session.finish()["transformations"] == 1
    session.close()
    assert component["finished"] == component["closed"] == 1


def test_no_effect_upstream_result_is_not_given_a_recovery_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, component: dict[str, Any],
) -> None:
    session = make(tmp_path)
    chat = request()
    add_read(session, chat)
    add_read(session, chat, call_id="new", content="recent", bound=False)
    component["proposal"] = lambda value: {
        "model": value["model"], "messages": deepcopy(value["messages"])}
    monkeypatch.setattr(session.ccr, "stash", lambda *a, **kw: pytest.fail("no transform, no root"))
    session.invoke(chat, intent="navigation")
    assert len(component["prepared"]) == 1 and component["started"] == 1
    assert session.transport.sent == [session.transport.encode(chat)]
    assert session.finish()["transformations"] == 0
    session.close()


def test_later_ineligible_request_skips_prepare_but_keeps_recovery_and_cleanup(
    tmp_path: Path, component: dict[str, Any],
) -> None:
    session = make(tmp_path)
    chat = request()
    index = add_read(session, chat)
    add_read(session, chat, call_id="new", content="recent", bound=False)
    session.invoke(chat, intent="navigation")
    first = prep(session)
    match = re.search(r"\[\[BR:[^\]]+\]\]", first["prepared"]["messages"][index]["content"])
    assert match is not None
    chat["messages"].append({"role": "assistant", "content": "Continue without changing old source."})
    session.invoke(chat, intent="navigation", exact_message_indices=(index,))
    assert component["started"] == 1 and len(component["prepared"]) == 1
    assert prep(session)["input_composition"]["projection_reason"] == "headroom_no_eligible_sources"
    recovered = json.loads(session.recover("retrieve_original", {"ref": match.group(), "offset": 0},
                                          tool_call_id="recover-root"))
    assert recovered["ok"] and recovered["content"] == TEXT
    assert session.recover("headroom_retrieve", {"hash": "upstream"}, tool_call_id="recover-fragment") == (
        "Exact upstream fragment.")
    result = session.finish()
    assert result["model_calls"] == 2 and result["transformations"] == 1
    assert result["component"]["headroom_executed"] is True
    assert result["recovery_tool_attempts"] == 2
    session.close()
    assert component["finished"] == component["closed"] == 1


def test_native_error_content_reaches_pipeline_unchanged_not_masked(
    tmp_path: Path, component: dict[str, Any],
) -> None:
    session = make(tmp_path)
    chat = request()
    text = "ERROR: failed operation with diagnostic source\n" + TEXT
    add_read(session, chat, content=text)
    add_read(session, chat, call_id="new", content="recent", bound=False)
    component["proposal"] = lambda value: {
        "model": value["model"], "messages": deepcopy(value["messages"])}
    session.invoke(chat, intent="navigation")
    assert len(component["prepared"]) == 1
    assert component["prepared"][0]["messages"][3]["content"] == text
    assert session.finish()["transformations"] == 0
    session.close()


def test_guarded_profile_binds_admission_but_legacy_behavior_and_id_stay_unchanged(
    tmp_path: Path, component: dict[str, Any],
) -> None:
    guarded_root, legacy_root = tmp_path / "on", tmp_path / "off"
    guarded_root.mkdir()
    legacy_root.mkdir()
    guarded = make(guarded_root)
    assert guarded.profile["headroom_admission_strategy"] == STRATEGY
    previous = guarded.profile
    previous.pop("headroom_admission_strategy")
    assert guarded.profile_id != runtime.RUNTIME_VERSION + ":" + runtime._digest(previous)
    legacy = make(legacy_root, guard=False)
    expected = {
        "version": runtime.RUNTIME_VERSION, "backend": "headroom", "policy": legacy.policy.to_dict(),
        "mode": None, "ponytail": None, "optimizer_selection": None, "require_nonexpanding_input": False,
        "model": Transport.model, "harness_id": runtime.RUNTIME_VERSION,
        "transport_declaration": legacy._transport_config(),
        "headroom_protection": "source-root-verbatim-fences-v2"}
    assert legacy.profile == expected
    assert legacy.profile_id == runtime.RUNTIME_VERSION + ":" + runtime._digest(expected)
    legacy.invoke(request(), intent="navigation")
    assert component["started"] == 1 and len(component["prepared"]) == 1
    assert "tools" in json.loads(legacy.transport.sent[0])["request"]
    for session in (guarded, legacy):
        session.finish()
        session.close()


@pytest.mark.parametrize("cap_kind", ["input_tokens", "wire_bytes"])
def test_skipped_pipeline_still_obeys_final_caps(
    tmp_path: Path, component: dict[str, Any], cap_kind: str,
) -> None:
    policy = RequestPolicy(version="request-policy-v3", enabled=False,
                           max_input_tokens=1 if cap_kind == "input_tokens" else None,
                           max_wire_bytes=1 if cap_kind == "wire_bytes" else None)
    session = make(tmp_path, policy=policy)
    with pytest.raises(ValueError, match="final_request_budget"):
        session.invoke(request(), intent="navigation")
    assert not component["prepared"] and component["started"] == 0
    assert not session.transport.sent and session.finish()["model_calls"] == 0
    session.close()


def test_eligible_projection_still_obeys_structure_and_final_composition_guard(
    tmp_path: Path, component: dict[str, Any],
) -> None:
    session = make(tmp_path)
    chat = request()
    add_read(session, chat)
    add_read(session, chat, call_id="new", content="recent", bound=False)
    component["replacement"] = TEXT + "expansion " * 1000
    session.invoke(chat, intent="navigation")
    assert len(component["prepared"]) == 1
    assert session.transport.sent == [session.transport.encode(chat)]
    assert session.finish()["transformations"] == 0
    session.close()


def test_one_eligible_source_does_not_authorize_neighbor_results(
    tmp_path: Path, component: dict[str, Any],
) -> None:
    session = make(tmp_path)
    chat = request()
    eligible = add_read(session, chat)
    unbound = add_read(session, chat, call_id="unbound", bound=False)
    protected = add_read(session, chat, call_id="protected")
    chat["messages"][protected]["status"] = "error"
    exact = add_read(session, chat, call_id="exact")
    add_read(session, chat, call_id="new", content="recent", bound=False)
    before = deepcopy(chat)
    session.invoke(chat, intent="navigation", exact_message_indices=(exact,))
    assert len(component["prepared"]) == 1 and chat == before
    candidate = prep(session)["prepared"]
    assert prep(session)["changed_messages"] == [eligible]
    for index in (unbound, protected, exact):
        assert candidate["messages"][index] == before["messages"][index]
        assert component["prepared"][0]["messages"][index] == before["messages"][index]
    assert session.finish()["transformations"] == 1
    session.close()


def test_structure_reversion_and_protected_source_checks_still_run(
    tmp_path: Path, component: dict[str, Any],
) -> None:
    session = make(tmp_path)
    chat = request()
    add_read(session, chat)
    add_read(session, chat, call_id="new", content="recent", bound=False)

    def corrupted(value: dict[str, Any]) -> dict[str, Any]:
        messages = deepcopy(value["messages"])
        messages[3]["tool_call_id"] = "tampered"
        return {"model": value["model"], "messages": messages}

    component["proposal"] = corrupted
    session.invoke(chat, intent="navigation")
    assert len(component["prepared"]) == 1
    assert session.transport.sent == [session.transport.encode(chat)]
    assert prep(session)["input_composition"]["projection_reason"] == "headroom_structure_reversion"
    assert session.finish()["transformations"] == 0
    session.close()


def test_fenced_source_is_not_removed_by_admission_or_final_validation(
    tmp_path: Path, component: dict[str, Any],
) -> None:
    session = make(tmp_path)
    chat = request()
    fenced = "```text\n" + TEXT + "```"
    index = add_read(session, chat, content=fenced)
    add_read(session, chat, call_id="new", content="recent", bound=False)
    session.invoke(chat, intent="navigation")
    assert len(component["prepared"]) == 1
    assert component["prepared"][0]["messages"][index]["content"] == fenced
    assert fenced in prep(session)["prepared"]["messages"][index]["content"]
    session.finish()
    session.close()
