"""Production session wiring: actual sent boundary, ownership, and accounting."""
from copy import deepcopy
from dataclasses import replace
import json
import re

import pytest

from brainspace import tokens
from brainspace.request_policy import SourceReadInfo
from brainspace.runtime import ExecutedToolResult, RuntimeSession
from brainspace.task_mode import TaskContract, task_local_mode
from brainspace.transport import Reply


TEXT = "def important(value):\n" + "".join(f"    value_{i} = value + {i}\n" for i in range(100))


class Transport:
    model = "fixture-model"
    max_request_bytes = 524288
    max_output_tokens = 2048

    def __init__(self):
        self.sent = []
        self.fail = None
        self.inflate_views = False

    def encode(self, chat):
        result = {"request": deepcopy(chat), "max_output_tokens": self.max_output_tokens}
        if self.inflate_views and "EXACT_READ_REUSE" in json.dumps(chat):
            result["wrapper"] = "expansion " * 10000
        return tokens.serialize(result)

    def send(self, wire):
        self.sent.append(wire)
        if self.fail == "exception":
            raise TimeoutError("must-not-echo-sensitive-error")
        if self.fail == "partial":
            return Reply(False, "transport_error", input_text=wire)
        body = {"model": self.model, "usage": {
            "input_tokens": 20, "output_tokens": 3, "total_tokens": 23},
            "output": "completed" if not self.fail else "failed"}
        output = json.dumps(body)
        return Reply(not self.fail, "ok" if not self.fail else "http_error",
                     True, wire, output, body, 200 if not self.fail else 500)


def request():
    return {"model": Transport.model, "messages": [
        {"role": "system", "content": "Original system instruction."},
        {"role": "developer", "content": "Original developer instruction."},
        {"role": "user", "content": "Inspect the source."},
    ]}


def make_session(tmp_path, transport=None, **options):
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return RuntimeSession(
        workspace=workspace, session_id="test-session", output=tmp_path / "run",
        transport=transport or Transport(), **options)


def reads(session, original, contents=None):
    values = contents if contents is not None else [
        ("module.py", TEXT), ("module.py", TEXT), ("other.py", "Other.")]
    for number, (path, text) in enumerate(values):
        call_id = "read-" + str(number)
        original["messages"].extend([
            {"role": "assistant", "content": None, "tool_calls": [{
                "id": call_id, "type": "function",
                "function": {"name": "read_file", "arguments": json.dumps({"path": path})},
            }]},
            {"role": "tool", "tool_call_id": call_id, "content": text},
        ])
        session.observe_source_read(SourceReadInfo.from_text(
            call_id=call_id, tool_name="read_file", source_path=path, content=text, status="success"))


def test_baseline_sends_original_and_accounts_for_complete_wire(tmp_path):
    transport = Transport()
    session = make_session(tmp_path, transport)
    original = request()
    before = deepcopy(original)
    reply = session.invoke(original)
    assert reply.ok and transport.sent == [transport.encode(original)]
    assert original == before
    result = session.finish()
    assert result["trace_complete"] is True
    assert result["model_calls"] == 1 and result["gateway_reported_tokens"] == 23
    assert result["reference_totals"]["input_tokens"] == tokens.count_tokens(transport.sent[0])
    assert result["reference_totals"]["output_tokens"] == tokens.count_tokens(reply.output_text)
    assert result["quality_verified"] is None
    assert result["transformations"] == 0
    assert result["ledger"]["deployment"]["ratio_status"] == "incomplete_outcomes"
    assert not (tmp_path / "workspace" / ".token-master").exists()
    with pytest.raises(ValueError):
        session.invoke(original)
    session.close()


def test_local_mode_is_applied_once_without_promoting_or_mutating_instructions(tmp_path):
    mode = task_local_mode(TaskContract("Find the bug.", (), ("Check the result.",), "Verified answer."))
    transport = Transport()
    session = make_session(tmp_path, transport, mode=mode)
    original = request()
    session.invoke(original)
    original["messages"].append({"role": "assistant", "content": "Continuing."})
    session.invoke(original)
    for wire in transport.sent:
        sent = json.loads(wire)["request"]["messages"]
        assert sent[:2] == original["messages"][:2]
        assert sum("Task contract:" in str(m.get("content")) for m in sent) == 1
        assert sent[2]["role"] == "user"
        assert sent[3] == original["messages"][2]
    assert all("Task contract:" not in str(m.get("content")) for m in original["messages"])
    session.finish()
    session.close()


def test_v3_changes_only_exact_duplicates_at_actual_transport_boundary(tmp_path):
    transport = Transport()
    session = make_session(tmp_path, transport, backend="local")
    original = request()
    reads(session, original)
    before = deepcopy(original)
    session.invoke(original)
    sent = json.loads(transport.sent[0])["request"]
    assert original == before
    assert sent["messages"][4] == before["messages"][4]
    assert "EXACT_READ_REUSE" in sent["messages"][6]["content"]
    assert sent["messages"][8] == before["messages"][8]
    assert tokens.count_tokens(transport.sent[0]) < tokens.count_tokens(transport.encode(before))
    result = session.finish()
    assert result["transformations"] == 1 and result["model_calls"] == 1
    session.close()


def test_transport_wrapper_inflation_reverts_the_candidate(tmp_path):
    transport = Transport()
    transport.inflate_views = True
    session = make_session(tmp_path, transport, backend="local")
    original = request()
    reads(session, original)
    session.invoke(original)
    assert transport.sent == [transport.encode(original)]
    assert session.finish()["transformations"] == 0
    session.close()


@pytest.mark.parametrize("failure", ["partial", "exception"])
def test_partial_or_unknown_attempt_never_becomes_zero_usage(tmp_path, failure):
    transport = Transport()
    transport.fail = failure
    session = make_session(tmp_path, transport)
    reply = session.invoke(request())
    assert not reply.ok
    result = session.finish()
    assert result["trace_complete"] is False
    assert result["model_calls"] == 1
    assert result["reference_totals"] is None and result["gateway_reported_tokens"] is None
    assert len(result["trace"]["expected_call_ids"]) == len(result["incomplete_calls"]) == 1
    assert "must-not-echo-sensitive-error" not in json.dumps(result)
    session.close()


def test_complete_failed_http_attempt_is_counted_not_discarded(tmp_path):
    transport = Transport()
    transport.fail = "http"
    session = make_session(tmp_path, transport)
    assert not session.invoke(request()).ok
    result = session.finish()
    assert result["trace_complete"] is True and result["model_calls"] == 1
    assert result["trace"]["calls"][0]["completion_status"] == "failed"
    assert result["reference_totals"]["total_tokens"] > 0
    assert result["gateway_reported_tokens"] == 23
    session.close()


def test_changed_or_projected_client_history_is_rejected_before_submission(tmp_path):
    transport = Transport()
    session = make_session(tmp_path, transport)
    original = request()
    session.invoke(original)
    altered = deepcopy(original)
    altered["messages"][0]["content"] = "Changed."
    with pytest.raises(ValueError, match="original_history"):
        session.invoke(altered)
    assert len(transport.sent) == 1
    session.finish()
    session.close()


def test_conflicting_receipt_and_session_state_are_not_silently_replaced(tmp_path):
    session = make_session(tmp_path)
    info = SourceReadInfo.from_text(
        call_id="read", tool_name="read_file", source_path="a.py", content="x", status="success")
    session.observe_source_read(info)
    with pytest.raises(ValueError):
        session.observe_source_read(replace(info, source_path="b.py"))
    with pytest.raises((ValueError, FileExistsError)):
        make_session(tmp_path)
    session.finish()
    session.close()


def test_budget_rejects_an_extra_call_without_silently_retrying(tmp_path):
    transport = Transport()
    session = make_session(tmp_path, transport, max_calls=1)
    session.invoke(request())
    with pytest.raises(ValueError, match="call_budget"):
        session.invoke(request())
    assert len(transport.sent) == 1
    assert session.finish()["model_calls"] == 1
    session.close()


def test_successful_executor_observations_are_bound_without_model_claims(tmp_path):
    session = make_session(tmp_path, backend="local")
    call = {"id": "real-read", "type": "function",
            "function": {"name": "read_file", "arguments": '{"path":"module.py"}'}}
    content = session.execute_tool(call, lambda name, args: ExecutedToolResult(TEXT, "success"))
    assert content == TEXT
    assert session.source_reads["real-read"].content_sha256 == SourceReadInfo.from_text(
        call_id="real-read", tool_name="read_file", source_path="module.py",
        content=TEXT, status="success").content_sha256
    failed = deepcopy(call)
    failed["id"] = "failed-read"
    with pytest.raises(OSError):
        session.execute_tool(failed, lambda *_: (_ for _ in ()).throw(OSError("failure")))
    assert "failed-read" not in session.source_reads
    unproven = deepcopy(call)
    unproven["id"] = "unproven-read"
    assert session.execute_tool(unproven, lambda *_: TEXT) == TEXT
    assert "unproven-read" not in session.source_reads
    session.finish()
    session.close()


def test_session_rejects_state_storage_inside_model_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(ValueError):
        RuntimeSession(workspace=workspace, session_id="session",
                       output=workspace / "state", transport=Transport())
    assert not (workspace / "state").exists()


def test_profile_is_frozen_and_transport_drift_is_not_a_new_silent_model(tmp_path):
    transport = Transport()
    session = make_session(tmp_path, transport, backend="local")
    with pytest.raises(AttributeError):
        session.backend = "none"
    with pytest.raises(AttributeError):
        session.policy = replace(session.policy, max_transforms=1)
    returned = session.profile
    returned["backend"] = "headroom"
    assert session.profile["backend"] == "local"
    transport.model = "different-model"
    with pytest.raises(ValueError, match="configuration_changed"):
        session.invoke(request())
    assert not transport.sent
    session.finish()
    session.close()


def test_claimed_input_that_differs_from_sent_wire_is_incomplete(tmp_path):
    class Mismatched(Transport):
        def send(self, wire):
            return replace(super().send(wire), input_text="different request")
    session = make_session(tmp_path, Mismatched())
    reply = session.invoke(request())
    assert not reply.ok and reply.reason == "wire_capture_mismatch"
    result = session.finish()
    assert result["model_calls"] == 1 and result["reference_totals"] is None
    assert result["gateway_reported_tokens"] is None and not result["trace_complete"]
    session.close()


def fake_headroom(monkeypatch, *, protected_change=False, failed_cleanup=False):
    from brainspace import headroom
    state = {"created": 0, "started": 0, "prepared": 0, "finished": 0, "closed": 0, "retrieved": []}

    class Backend:
        def __init__(self, directory, **options):
            state["created"] += 1
            self.directory = directory
            directory.mkdir()

        def start(self):
            state["started"] += 1
            return {"ready": True}

        def prepare(self, chat):
            state["prepared"] += 1
            messages = deepcopy(chat["messages"])
            if protected_change:
                messages[0]["content"] = "Rewritten system instruction."
            else:
                for message in messages:
                    if message["role"] == "tool":
                        message["content"] = "Reduced source with Headroom fragment reference."
                        break
            return {"model": chat["model"], "messages": messages}

        def retrieve(self, args, tool_call_id):
            state["retrieved"].append((args, tool_call_id))
            return "Exact upstream fragment, not the full source."

        def finish(self):
            state["finished"] += 1
            return {"reference_count": 1, "audit_after_task": True}

        def close(self):
            state["closed"] += 1
            return {"container_id": "unit-fixture", "container_removed": not failed_cleanup}

    monkeypatch.setattr(headroom, "HeadroomContainer", Backend)
    return state


def headroom_session(tmp_path, transport):
    return make_session(tmp_path, transport, backend="headroom", headroom_options={
        "cache": tmp_path / "unused-unit-cache", "assets": tmp_path / "unused-unit-assets",
        "docker_config": None,
    })


def test_headroom_lives_across_turns_and_has_exact_full_root_recovery(tmp_path, monkeypatch):
    state = fake_headroom(monkeypatch)
    transport = Transport()
    session = headroom_session(tmp_path, transport)
    original = request()
    reads(session, original)
    before = deepcopy(original)
    session.invoke(original, intent="navigation")
    sent = json.loads(transport.sent[0])["request"]
    assert original == before
    ref = re.search(r"\[\[BR:[^\]]+\]\]", sent["messages"][4]["content"])[0]
    assert "kind=root" in ref
    recovered = json.loads(session.recover(
        "retrieve_original", {"ref": ref, "offset": 0}, tool_call_id="root-recovery"))
    assert recovered["ok"] and recovered["content"] == TEXT
    assert session.recover("headroom_retrieve", {"hash": "upstream"},
                           tool_call_id="fragment-recovery").startswith("Exact upstream fragment")
    original["messages"].append({"role": "assistant", "content": "Continuing the task."})
    session.invoke(original, intent="navigation")
    assert state["created"] == state["started"] == 1 and state["prepared"] == 2
    assert len(transport.sent) == 2
    final = session.finish()
    assert final["model_calls"] == 2 and final["transformations"] == 2
    assert state["finished"] == 1 and final["component"]["complete"]
    session.close()
    assert state["closed"] == 1
    assert json.loads((tmp_path / "run/docker-config/config.json").read_text()) == {}


def test_headroom_never_rewrites_protected_instructions(tmp_path, monkeypatch):
    fake_headroom(monkeypatch, protected_change=True)
    transport = Transport()
    session = headroom_session(tmp_path, transport)
    original = request()
    reads(session, original)
    session.invoke(original, intent="navigation")
    sent = json.loads(transport.sent[0])["request"]
    assert sent["messages"] == original["messages"]
    assert session.finish()["transformations"] == 0
    session.close()


def test_headroom_unconfirmed_cleanup_is_not_success(tmp_path, monkeypatch):
    fake_headroom(monkeypatch, failed_cleanup=True)
    session = headroom_session(tmp_path, Transport())
    original = request()
    reads(session, original)
    session.invoke(original, intent="navigation")
    session.finish()
    with pytest.raises(RuntimeError, match="cleanup_unconfirmed"):
        session.close()
    assert json.loads((tmp_path / "run/cleanup.json").read_text())["complete"] is False


def test_model_cannot_grade_itself_or_reopen_an_immutable_outcome(tmp_path):
    session = make_session(tmp_path)
    session.invoke(request())
    with pytest.raises(ValueError):
        session.finish(success="true")
    assert session.finish()["quality_verified"] is None
    with pytest.raises(ValueError, match="outcome_changed"):
        session.finish(success=True)
    session.close()


def test_missing_counters_prevent_submission_not_a_fake_zero_token_success(tmp_path, monkeypatch):
    session = make_session(tmp_path)
    def missing(_):
        raise tokens.ReferenceTokenizerUnavailable("not available")
    monkeypatch.setattr(tokens, "count_tokens", missing)
    with pytest.raises(tokens.ReferenceTokenizerUnavailable):
        session.invoke(request())
    assert not session.transport.sent
    result = session.finish()
    assert result["model_calls"] == 0 and result["quality_verified"] is None
    session.close()


@pytest.mark.parametrize("failed_write", ["capture", "captured_journal"])
def test_failed_capture_persistence_cannot_seal_complete_accounting(tmp_path, monkeypatch, failed_write):
    from brainspace import runtime
    original_append = runtime.append_receipt
    session = make_session(tmp_path)

    def broken(path, value):
        if ((failed_write == "capture" and path.name == "captures.jsonl")
                or (failed_write == "captured_journal" and path.name == "invocations.jsonl"
                    and value.get("state") == "captured")):
            raise OSError("injected journal failure")
        return original_append(path, value)

    monkeypatch.setattr(runtime, "append_receipt", broken)
    with pytest.raises(OSError):
        session.invoke(request())
    final = session.finish()
    assert final["model_calls"] == 1
    assert final["trace_complete"] is False and final["reference_totals"] is None
    assert final["gateway_reported_tokens"] is None
    assert final["ledger"]["deployment"]["tasks"] == 0
    assert any(c["reason"] == "capture_persistence_failed" for c in final["incomplete_calls"])
    session.close()


def test_rejected_concurrent_close_does_not_destroy_inflight_recovery(tmp_path, monkeypatch):
    from threading import Event, Thread
    state = fake_headroom(monkeypatch)
    entered, release = Event(), Event()

    class Slow(Transport):
        def send(self, wire):
            entered.set()
            if not release.wait(10):
                raise TimeoutError("unit rendezvous timed out")
            return super().send(wire)

    session = headroom_session(tmp_path, Slow())
    original = request()
    reads(session, original)
    outcome = []
    thread = Thread(target=lambda: outcome.append(session.invoke(original, intent="navigation")))
    thread.start()
    try:
        assert entered.wait(10) and thread.is_alive()
        with pytest.raises(ValueError):
            session.close()
        assert not session._closed and state["closed"] == 0
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive() and outcome[0].ok
    final = session.finish()
    assert final["trace_complete"] and final["model_calls"] == 1
    session.close()
    assert state["closed"] == 1


def test_material_transport_controls_change_profile_not_local_policy_identity(tmp_path):
    from brainspace.transport import ResponsesTransport
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    one = make_session(tmp_path / "one", ResponsesTransport(
        "http://127.0.0.1:1/v1", "fixture", max_output_tokens=100, reasoning_effort="low"), backend="local")
    two = make_session(tmp_path / "two", ResponsesTransport(
        "http://127.0.0.1:1/v1", "fixture", max_output_tokens=200, reasoning_effort="high"), backend="local")
    assert one.profile_id != two.profile_id and one.policy_id == two.policy_id
    one.finish()
    two.finish()
    one.close()
    two.close()


def test_recovery_operation_survives_lost_terminal_tool_receipts(tmp_path, monkeypatch):
    from brainspace import runtime
    session = make_session(tmp_path)
    session.invoke(request())
    reference = session.ccr.stash(TEXT, source="module.py", kind="root")
    original_append = runtime.append_receipt
    actual_reads = []
    original_read = session.ccr.retrieve_page

    def read(*args):
        actual_reads.append(args)
        return original_read(*args)

    def broken(path, value):
        if path.name == "tools.jsonl" and value.get("state") in ("returned", "failed"):
            raise OSError("lost terminal tool receipt")
        return original_append(path, value)

    monkeypatch.setattr(session.ccr, "retrieve_page", read)
    monkeypatch.setattr(runtime, "append_receipt", broken)
    with pytest.raises(OSError):
        session.recover("retrieve_original", {"ref": reference, "offset": 0}, tool_call_id="recover-1")
    result = session.finish()
    assert len(actual_reads) == 1
    assert result["recovery_tool_attempts"] == result["wrapped_tool_attempts"] == 1
    assert result["tool_inventory_complete"] is False and result["component"]["complete"] is False
    assert result["trace_complete"] is True and result["reference_totals"]["total_tokens"] > 0
    assert result["gateway_reported_tokens"] == 23
    session.close()


def test_ctrl_c_during_submission_remains_unknown_through_jsonl_cleanup(tmp_path, monkeypatch):
    from io import BytesIO
    import brainspace_tools
    from brainspace import session_cli

    class Interrupted(Transport):
        def send(self, wire):
            self.sent.append(wire)
            raise KeyboardInterrupt("interrupted after send entry")

    transport = Interrupted()
    monkeypatch.setattr(session_cli, "ResponsesTransport", lambda **_: transport)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = tmp_path / "run"
    args = brainspace_tools._parser().parse_args([
        "--workspace", str(workspace), "--session", "cancelled-session", "session",
        "--output", str(output), "--base-url", "http://127.0.0.1:1/v1",
        "--model", transport.model, "--allow-network", "--backend", "none",
    ])
    incoming = BytesIO((json.dumps({"op": "call", "request": request()}) + "\n"
                        + json.dumps({"op": "finish"}) + "\n").encode())
    outgoing = BytesIO()
    assert session_cli.run_session(args, input_stream=incoming, output_stream=outgoing) != 0
    result = json.loads((output / "result.json").read_text())
    assert len(transport.sent) == 1
    assert result["model_calls"] == 1 and result["trace_complete"] is False
    assert result["reference_totals"] is None and result["gateway_reported_tokens"] is None
    assert len(result["incomplete_calls"]) == 1
    assert json.loads((output / "cleanup.json").read_text())["complete"] is True


def test_post_send_measurement_cancellation_never_starts_headroom_finish(tmp_path, monkeypatch):
    state = fake_headroom(monkeypatch)
    returned = []

    class Completed(Transport):
        def send(self, wire):
            reply = super().send(wire)
            returned.append(True)
            return reply

    session = headroom_session(tmp_path, Completed())
    original = request()
    reads(session, original)
    count = tokens.count_tokens

    def cancelled_count(text):
        if returned:
            raise KeyboardInterrupt("interrupted during measurement")
        return count(text)

    monkeypatch.setattr(tokens, "count_tokens", cancelled_count)
    with pytest.raises(KeyboardInterrupt):
        session.invoke(original, intent="navigation")
    result = session.finish()
    assert result["model_calls"] == 1 and result["trace_complete"] is False
    assert result["gateway_reported_tokens"] is None and result["reference_totals"] is None
    assert result["component"]["interrupted"] is True and state["finished"] == 0
    session.close()
    assert state["closed"] == 1


@pytest.mark.parametrize("preserve_block", [True, False])
def test_headroom_clamps_protected_messages_but_can_reduce_unprotected_prose(
    tmp_path, monkeypatch, preserve_block,
):
    from brainspace import headroom
    fake_headroom(monkeypatch)
    block = "```python\r\nprint('literal α')\r\n```\r\n"
    original_document = "Overview sentence with details.\r\n" * 80 + block

    def proposal(_, chat):
        messages = deepcopy(chat["messages"])
        messages[0]["content"] = "Vendor tried to alter system instructions."
        messages[4]["content"] = "Short overview.\r\n" + (
            block if preserve_block else block.replace("literal α", "changed"))
        messages[6]["content"] = "Vendor also changed the newest protected result."
        return {"model": chat["model"], "messages": messages}

    monkeypatch.setattr(headroom.HeadroomContainer, "prepare", proposal)
    transport = Transport()
    session = headroom_session(tmp_path, transport)
    original = request()
    reads(session, original, [("document.md", original_document), ("latest.md", "Latest original.")])
    session.invoke(original, intent="overview")
    sent = json.loads(transport.sent[0])["request"]["messages"]
    assert sent[0] == original["messages"][0]
    assert sent[6] == original["messages"][6]
    if preserve_block:
        assert block in sent[4]["content"] and sent[4] != original["messages"][4]
        reference = sent[4]["content"].splitlines()[0]
        assert session.ccr.retrieve(reference) == original_document
    else:
        assert sent[4] == original["messages"][4]
    assert session.finish()["transformations"] == int(preserve_block)
    session.close()


def test_final_recovery_annotation_preserves_a_fence_ending_at_eof(tmp_path, monkeypatch):
    from brainspace import headroom
    from brainspace.protected_text import protected_text_preserved
    fake_headroom(monkeypatch)
    block = "```\nexact code\n```"
    original_document = "Long explanatory prose that may be reduced.\n" * 90 + block

    def proposal(_, chat):
        messages = deepcopy(chat["messages"])
        messages[4]["content"] = "Short explanation.\n" + block
        return {"model": chat["model"], "messages": messages}

    monkeypatch.setattr(headroom.HeadroomContainer, "prepare", proposal)
    transport = Transport()
    session = headroom_session(tmp_path, transport)
    original = request()
    reads(session, original, [("document.md", original_document), ("last.md", "Latest.")])
    session.invoke(original, intent="overview")
    sent = json.loads(transport.sent[0])["request"]["messages"][4]["content"]
    assert protected_text_preserved(original_document, sent)
    session.finish()
    session.close()
