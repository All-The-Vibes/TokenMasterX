"""Trusted artifact aliases must bind to the model-facing call, not lose provenance."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
from brainspace.ccr import CCR  # noqa: E402
from quality import runner  # noqa: E402
from source_read_adapter import ConservativeArm, executor_source_reads  # noqa: E402


TEXT = "Source description.\n" + "".join(f"Detailed fact {i}: literal {i}.\n" for i in range(100))


def response(path, call_id):
    return {"output": [{"type": "function_call", "name": "fetch_artifact",
                        "call_id": call_id, "arguments": json.dumps({"path": path})}]}


@pytest.fixture
def artifact_tool(monkeypatch):
    monkeypatch.setattr(runner, "TOOLS", runner.TOOLS + [
        runner._tool("fetch_artifact", {"path": {"type": "string"}}, "Read exact artifact text."),
    ])


def test_exact_artifact_alias_receipts_authorize_reuse_not_prompt_injection(tmp_path, artifact_tool):
    (tmp_path / "source.txt").write_bytes(TEXT.encode("utf-8"))
    (tmp_path / "other.txt").write_bytes(b"Other.")
    messages = [{"role": "system", "content": "Read the artifacts."},
                {"role": "user", "content": "Keep unique content."}]
    store = CCR(workspace_root=tmp_path)
    with executor_source_reads() as receipts:
        for n, path in enumerate(("source.txt", "source.txt", "other.txt")):
            name, args, call_id = runner._native_actions(response(path, f"fetch-{n}"))
            # This is the actual parent dispatcher alias, not a fabricated result.
            text = runner._execute(tmp_path, store, "read_file", args)
            messages.extend([
                {"role": "assistant", "tool_calls": [{
                    "id": call_id, "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }]},
                {"role": "tool", "tool_call_id": call_id, "content": text},
            ])
        assert len(receipts) == 3
        assert all(info.tool_name == "fetch_artifact" for info in receipts.values())
        request = {"model": "fixture", "messages": messages}
        result = runner.prepare_request(
            request, ConservativeArm("candidate").policy, ccr=store,
            protocol="chat-completions-v1", intent="overview")
        assert result.status == "transformed" and result.changed_message_indices == (5,)
        assert result.request["messages"][3] == request["messages"][3]
        assert result.request["messages"][:3] == request["messages"][:3]
        assert "source_reads" not in result.serialized
    assert not (tmp_path / ".token-master").exists()


def test_failed_or_mismatched_artifact_read_does_not_issue_receipt(tmp_path, artifact_tool):
    (tmp_path / "other.txt").write_bytes(b"Other.")
    with executor_source_reads() as receipts:
        runner._native_actions(response("missing.txt", "fetch-0"))
        with pytest.raises(OSError):
            runner._execute(tmp_path, CCR(workspace_root=tmp_path),
                            "read_file", {"path": "missing.txt"})
        assert not receipts
        runner._execute(tmp_path, CCR(workspace_root=tmp_path),
                        "read_file", {"path": "other.txt"})
        assert not receipts
