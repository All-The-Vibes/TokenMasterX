"""The source exemption must be issued by the executing adapter, not the model."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
from brainspace.ccr import CCR  # noqa: E402
from quality import runner  # noqa: E402
from source_read_adapter import SourceAwareArm, executor_source_reads  # noqa: E402


SOURCE = (
    '"""An error-handling API."""\ndef read_item(path):\n'
    + "".join(f"    value_{i} = {i}\n" for i in range(45))
    + '    return {"error": None}\n'
)


def response(path="module.py", call_id="read-0"):
    return {"output": [{"type": "function_call", "call_id": call_id,
                        "name": "read_file", "arguments": json.dumps({"path": path})}]}


def messages(content=SOURCE):
    return {"model": "fixture", "messages": [
        {"role": "system", "content": "Navigate source."},
        {"role": "assistant", "tool_calls": [{"type": "function", "id": "read-0",
         "function": {"name": "read_file", "arguments": '{"path":"module.py"}'}}]},
        {"role": "tool", "tool_call_id": "read-0", "content": content},
        {"role": "assistant", "tool_calls": [{"type": "function", "id": "read-1",
         "function": {"name": "list_files", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "read-1", "content": "module.py"},
    ]}


@pytest.mark.parametrize("line_ending", ["\n", "\r\n"])
def test_real_successful_read_reaches_guard_without_adding_prompt_metadata(tmp_path, line_ending):
    expected = SOURCE.replace("\n", line_ending)
    (tmp_path / "module.py").write_bytes(expected.encode("utf-8"))
    store = CCR(workspace_root=tmp_path)
    before = runner._native_actions, runner._execute, runner.prepare_request
    plans = []
    with executor_source_reads(on_plan=lambda before, after: plans.append((before, after))) as observations:
        name, args, call_id = runner._native_actions(response())
        content = runner._execute(tmp_path, store, name, args)
        assert content == expected and observations[call_id].status == "success"
        planned = runner.prepare_request(
            messages(content), SourceAwareArm("tokenmaster", views=True).policy,
            ccr=store, protocol="chat-completions-v1", intent="navigation",
        )
        assert planned.status == "transformed"
        assert "source_reads" not in planned.serialized
        assert len(plans) == 1 and plans[0][0] == messages(content) and plans[0][1] == planned
    assert before == (runner._native_actions, runner._execute, runner.prepare_request)


def test_failed_read_does_not_issue_a_success_receipt(tmp_path):
    with executor_source_reads() as observations:
        name, args, _ = runner._native_actions(response("missing.py"))
        with pytest.raises(OSError):
            runner._execute(tmp_path, CCR(workspace_root=tmp_path), name, args)
        assert observations == {}


def test_a_read_without_matching_tool_call_is_not_attested(tmp_path):
    (tmp_path / "module.py").write_text(SOURCE, encoding="utf-8")
    with executor_source_reads() as observations:
        runner._execute(tmp_path, CCR(workspace_root=tmp_path), "read_file", {"path": "module.py"})
        assert observations == {}
        runner._native_actions(response("other.py"))
        runner._execute(tmp_path, CCR(workspace_root=tmp_path), "read_file", {"path": "module.py"})
        assert observations == {}


def test_context_restores_bindings_even_when_caller_fails():
    before = runner._native_actions, runner._execute, runner.prepare_request
    with pytest.raises(RuntimeError, match="synthetic"):
        with executor_source_reads():
            raise RuntimeError("synthetic")
    assert before == (runner._native_actions, runner._execute, runner.prepare_request)
    with executor_source_reads():
        with pytest.raises(RuntimeError, match="nested"):
            with executor_source_reads():
                pass
    assert before == (runner._native_actions, runner._execute, runner.prepare_request)


def test_v2_evaluation_arm_has_different_identity_and_does_not_change_default():
    assert SourceAwareArm("on", views=True).policy.version == "request-policy-v2"
    assert runner.Arm("on", views=True).policy.version == "request-policy-v1"
    assert SourceAwareArm("on", views=True).identity != runner.Arm("on", views=True).identity
    assert not SourceAwareArm("off").policy.enabled
