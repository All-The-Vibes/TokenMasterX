"""Native view keeps its actual name; executor provenance is still mandatory."""
from copy import deepcopy
import json

import pytest

from brainspace.ccr import CCR
from brainspace.pipeline import prepare_request
from brainspace.request_policy import PROTOCOL, RequestPolicy, SourceReadInfo


def request():
    old = json.dumps({"items": [{"id": i, "value": "literal  spaces"} for i in range(40)]},
                     indent=8)
    messages = [{"role": "user", "content": "Summarize the supplied JSON."}]
    for call_id, text in (("native-old", old), ("native-new", "newest source")):
        messages.extend([
            {"role": "assistant", "tool_calls": [{
                "id": call_id, "type": "function",
                "function": {"name": "view", "arguments": json.dumps({"path": call_id + ".json"})},
            }]},
            {"role": "tool", "tool_call_id": call_id, "content": text},
        ])
    return {"model": "fixture", "messages": messages}, old


@pytest.mark.parametrize("status,with_receipt,changes", [
    ("success", True, True), ("error", True, False),
    ("unknown", True, False), ("success", False, False),
])
def test_v4_native_view_admission(tmp_path, status, with_receipt, changes):
    payload, old = request()
    original = deepcopy(payload)
    info = SourceReadInfo.from_text(
        call_id="native-old", tool_name="view", source_path="native-old.json",
        content=old, status=status,
    )
    store = CCR(tmp_path / "recovery.sqlite", workspace_root=tmp_path, session_id="native-test")
    result = prepare_request(
        payload, RequestPolicy(version="request-policy-v4", enabled=True, min_tool_chars=1),
        ccr=store, intent="overview", protocol=PROTOCOL,
        source_reads=(info,) if with_receipt else (),
    )
    assert bool(result.changed_message_indices) is changes
    assert payload == original
    assert all(call["function"]["name"] == "view"
               for message in result.request["messages"] for call in message.get("tool_calls", []))
    assert result.request["messages"][-1] == original["messages"][-1]


def test_native_view_exact_mode_stays_original(tmp_path):
    payload, old = request()
    store = CCR(tmp_path / "recovery.sqlite", workspace_root=tmp_path, session_id="native-exact")
    info = SourceReadInfo.from_text(
        call_id="native-old", tool_name="view", source_path="native-old.json",
        content=old, status="success",
    )
    result = prepare_request(
        payload, RequestPolicy(version="request-policy-v4", enabled=True, min_tool_chars=1),
        ccr=store, intent="exact", protocol=PROTOCOL, source_reads=(info,),
    )
    assert result.request == payload and not result.changed_message_indices
