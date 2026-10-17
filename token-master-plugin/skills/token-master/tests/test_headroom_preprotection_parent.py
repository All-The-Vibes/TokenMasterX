"""Explicit preprotected pipeline wiring, no real vendor, Docker or model calls."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json

import pytest

from brainspace import headroom, tokens
from brainspace.document_structure import SPAN_CONTRACT, document_structure_spans
from brainspace.runtime import RuntimeSession
from brainspace.runtime_policy import RuntimePolicy, controller_policy_neighbors
from brainspace.runtime_resources import RuntimeResources
from test_headroom_document_adapter import adapter
from test_headroom_document_runtime import Transport, request


MODE = "native-documents-structure-tags-v1"
TABLE = "| Key | Value |\n|---|---|\n| Primary | config |\n| Secondary | workspace |\n"
ORDERED = "1. Config first.\n2. Workspace second.\n\n"
TEXT = "A document with background information and operational context.\n" * 90 + "\n" + TABLE + "\n" + ORDERED


def policy(**changes):
    return RuntimePolicy(**{
        "backend": "headroom", "headroom_strategy": MODE,
        "headroom_structure_guard": "document-structure-v1",
        "headroom_root_reference_style": "compact-root-v1",
        "require_nonexpanding_input": True, **changes,
    })


def descriptors(chat, indices):
    result = []
    for index in indices:
        text = chat["messages"][index]["content"]
        spans = document_structure_spans(text)
        assert spans is not None
        result.append({
            "index": index, "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "spans": [span.to_dict() for span in spans],
        })
    return result


def test_new_mode_is_explicit_typed_and_does_not_change_existing_off_catalog():
    selected = policy()
    assert RuntimePolicy.from_json(selected.to_json()) == selected
    assert selected.policy_id != replace(selected, headroom_strategy="native-documents-v1").policy_id
    assert all(p.headroom_strategy != MODE for p in controller_policy_neighbors(RuntimePolicy()))
    for neighbor in controller_policy_neighbors(selected):
        neighbor.__post_init__()
        if neighbor.headroom_strategy != MODE:
            assert neighbor.headroom_structure_guard in ("none", "document-structure-v1")


@pytest.mark.parametrize("changes", [
    {"headroom_structure_guard": "none"}, {"require_nonexpanding_input": False},
    {"backend": "none"}, {"headroom_structure_guard": True},
])
def test_new_mode_cannot_bypass_existing_acceptance_guards(changes):
    with pytest.raises(ValueError):
        policy(**changes)


def test_strategy_selection_reaches_actual_resource_options(tmp_path, monkeypatch):
    resources = object.__new__(RuntimeResources)
    monkeypatch.setattr(RuntimeResources, "_check", lambda *a, **kw: None)
    for name in ("_headroom_cache", "_headroom_assets"):
        object.__setattr__(resources, name, tmp_path)
    # No real resource content or component is used by this identity routing check.
    assert resources.resolve(policy())["headroom_options"]["strategy"] == MODE


@pytest.fixture
def session(tmp_path, monkeypatch):
    state = {"starts": 0, "calls": [], "replacement": "Short background.\n\n" + TABLE + "\n" + ORDERED}

    class Backend:
        def __init__(self, directory, **options):
            directory.mkdir()
            state["options"] = options

        def start(self):
            state["starts"] += 1
            return {"ready": True}

        def prepare(self, chat, **controls):
            state["calls"].append((deepcopy(chat), deepcopy(controls)))
            result = deepcopy(chat["messages"])
            for index in controls["eligible_indices"]:
                result[index]["content"] = state["replacement"]
            return {"model": chat["model"], "messages": result}

        def finish(self):
            return {}

        def close(self):
            return {"container_removed": True}

    monkeypatch.setattr(headroom, "HeadroomContainer", Backend)
    monkeypatch.setattr(RuntimeResources, "resolve", lambda self, selected: {
        "ponytail": None, "headroom_options": {
            "cache": tmp_path / "cache", "assets": tmp_path / "assets",
            "docker_config": None, "strategy": selected.headroom_strategy,
        },
    })
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    item = RuntimeSession(
        workspace=workspace, session_id="preprotect", output=tmp_path / "run",
        transport=Transport(), runtime_policy=policy(), runtime_resources=RuntimeResources(),
    )
    yield item, state
    item.close()


def test_runtime_passes_pristine_digest_bound_offsets_and_preserves_all_guards(session):
    item, state = session
    original = request(item, content=TEXT)
    before = deepcopy(original)
    item.invoke(original, intent="overview", stable_prefix_messages=2)
    offered, controls = state["calls"][0]
    assert original == before
    assert controls["eligible_indices"] == [3]
    assert controls["message_spans"] == descriptors(offered, [3])
    assert controls["message_spans"][0]["spans"]
    assert offered["messages"] == before["messages"]  # Annotation belongs inside worker only.
    submitted = json.loads(item.transport.sent[-1])
    ref, view = submitted["messages"][3]["content"].split("\n", 1)
    assert item.ccr.retrieve(ref) == TEXT
    assert view == state["replacement"]
    assert submitted["messages"][0] == before["messages"][0]
    assert submitted["messages"][-1] == before["messages"][-1]
    assert tokens.count_tokens(item.transport.sent[-1]) < tokens.count_tokens(tokens.serialize(before))
    assert item.profile["headroom_preprotection_contract"] == SPAN_CONTRACT


@pytest.mark.parametrize("guard", ["exact", "edit", "debug", "newest", "unbound", "ambiguous", "span_bound"])
def test_unsupported_or_protected_inputs_do_not_start_headroom(session, guard):
    item, state = session
    content = TEXT
    if guard == "ambiguous":
        content += "\n> unsupported quote\n"
    elif guard == "span_bound":
        content = (TABLE + "\n") * 257
    payload = request(item, content=content, bound=guard != "unbound")
    if guard == "newest":
        payload["messages"] = payload["messages"][:-2]
    item.invoke(payload, intent=guard if guard in ("exact", "edit", "debug") else "overview")
    assert state["starts"] == 0 and not state["calls"]
    assert json.loads(item.transport.sent[-1]) == payload


@pytest.mark.parametrize("replacement", ["Damaged table/list text.", TEXT + "Added expansion.\n"])
def test_worker_proposal_still_requires_structure_and_complete_wire_acceptance(session, replacement):
    item, state = session
    state["replacement"] = replacement
    original = request(item, content=TEXT)
    item.invoke(original, intent="overview")
    assert json.loads(item.transport.sent[-1]) == original


def adapter_request():
    return {"model": "fixture", "messages": [
        {"role": "user", "content": "Overview"},
        {"role": "assistant", "tool_calls": [{
            "id": "old", "type": "function", "function": {"name": "view", "arguments": '{"path":"a.md"}'},
        }]},
        {"role": "tool", "tool_call_id": "old", "content": TEXT},
        {"role": "assistant", "tool_calls": [{
            "id": "new", "type": "function", "function": {"name": "view", "arguments": '{"path":"b.md"}'},
        }]},
        {"role": "tool", "tool_call_id": "new", "content": "Newest unchanged."},
    ]}


def adapter_response(chat, spans):
    manifest = {"strategy": MODE, "declaration": "synthetic API-shaped test only"}
    def wire(value):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return {
        "messages": chat["messages"], "strategy": MODE, "strategy_manifest": manifest,
        "strategy_manifest_sha256": hashlib.sha256(wire(manifest).encode()).hexdigest(),
        "eligible_indices": [2], "protected_indices": [0, 1, 3, 4],
        "document_request": {"frozen_message_count": 1, "keep_recent_tool_results": 1},
        "span_contract": SPAN_CONTRACT,
        "message_spans_sha256": hashlib.sha256(wire(spans).encode()).hexdigest(),
    }


def test_adapter_uses_new_rpc_and_checks_exact_controls(tmp_path):
    item = adapter(tmp_path, strategy=MODE)
    chat = adapter_request()
    spans = descriptors(chat, [2])
    seen = []
    item.rpc = lambda operation, **values: seen.append((operation, values)) or adapter_response(chat, spans)
    assert item.prepare(chat, eligible_indices=[2], frozen_message_count=1, message_spans=spans) == chat
    assert seen == [("compress_documents_preprotected", {
        "model": chat["model"], "messages": chat["messages"], "eligible_indices": [2],
        "frozen_message_count": 1, "keep_recent_tool_results": 1,
        "span_contract": SPAN_CONTRACT, "message_spans": spans,
    })]


@pytest.mark.parametrize("field,value", [
    ("span_contract", "unknown"), ("message_spans_sha256", "0" * 64),
    ("document_request", {"frozen_message_count": True, "keep_recent_tool_results": 1}),
    ("strategy", "native-documents-v1"),
])
def test_adapter_rejects_wrong_receipt_before_accepting_a_projection(tmp_path, field, value):
    item = adapter(tmp_path, strategy=MODE)
    chat = adapter_request()
    spans = descriptors(chat, [2])
    returned = adapter_response(chat, spans)
    returned[field] = value
    item.rpc = lambda *a, **k: returned
    with pytest.raises(ValueError, match="manifest_mismatch"):
        item.prepare(chat, eligible_indices=[2], frozen_message_count=1, message_spans=spans)
    assert item.failed


@pytest.mark.parametrize("field,value", [
    ("eligible_indices", [2.0]),
    ("protected_indices", [False, 1, 3, 4]),
    ("protected_indices", [0, True, 3, 4]),
    ("protected_indices", [0, 1, 3.0, 4]),
    ("protected_indices", [0.0, 1.0, 3.0, 4.0]),
])
def test_adapter_rejects_coercively_equal_index_echoes(tmp_path, field, value):
    item = adapter(tmp_path, strategy=MODE)
    chat = adapter_request()
    spans = descriptors(chat, [2])
    returned = adapter_response(chat, spans)
    returned[field] = value
    item.rpc = lambda *a, **k: returned
    with pytest.raises(ValueError, match="manifest_mismatch"):
        item.prepare(chat, eligible_indices=[2], frozen_message_count=1, message_spans=spans)
    assert item.failed


@pytest.mark.parametrize("manifest", [None, '{"strategy":"native-documents-v1"}', "not-json", "[]"])
def test_new_mode_cannot_retrieve_before_a_verified_new_mode_handshake(tmp_path, manifest):
    item = adapter(tmp_path, strategy=MODE)
    item._strategy_manifest = manifest
    called = []
    item.rpc = lambda *a, **k: called.append((a, k)) or {
        "tool_call_id": "early", "tool_name": "headroom_retrieve",
        "content": '{"original_content":"<tm-structure-unvalidated>not allowed</tm-structure-unvalidated>"}',
    }
    with pytest.raises(ValueError, match="preprotection_recovery_not_initialized"):
        item.retrieve({"hash": "a" * 24}, "early")
    assert called == []


def test_eager_runtime_readiness_does_not_authorize_unvalidated_fragment_recovery(tmp_path, monkeypatch):
    calls = []
    parent_retrieve = headroom.HeadroomContainer.retrieve

    class ReadyBackend:
        def __init__(self, directory, **options):
            directory.mkdir()
            self.strategy = options["strategy"]
            self._strategy_manifest = None

        def start(self):
            return {"ready": True}

        def rpc(self, *args, **kwargs):
            calls.append((args, kwargs))
            return {"tool_call_id": "eager-read", "tool_name": "headroom_retrieve",
                    "content": '{"original_content":"<tm-structure-unvalidated>contaminated</tm-structure-unvalidated>"}'}

        retrieve = parent_retrieve

        def finish(self):
            return {}

        def close(self):
            return {"container_removed": True}

    monkeypatch.setattr(headroom, "HeadroomContainer", ReadyBackend)
    monkeypatch.setattr(RuntimeResources, "validate", lambda self, selected=None: None)
    monkeypatch.setattr(RuntimeResources, "resolve", lambda self, selected: {
        "ponytail": None, "headroom_options": {
            "cache": tmp_path, "assets": tmp_path, "docker_config": None, "strategy": MODE,
        },
    })
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    item = RuntimeSession(
        workspace=workspace, session_id="eager-test", output=tmp_path / "runtime",
        transport=Transport(), runtime_policy=policy(), runtime_resources=RuntimeResources(),
    )
    try:
        assert item.prepare_components()["headroom_executed"]
        with pytest.raises(ValueError, match="preprotection_recovery_not_initialized"):
            item.recover("headroom_retrieve", {"hash": "a" * 24}, tool_call_id="eager-read")
        assert not calls and not item.transport.sent
    finally:
        item.close()


@pytest.mark.parametrize("strategy", ["upstream-default-v1", "native-documents-v1"])
def test_old_modes_keep_their_original_precompression_retrieval_route(tmp_path, strategy):
    item = adapter(tmp_path, strategy=strategy)
    seen = []
    item.rpc = lambda operation, **values: seen.append((operation, values)) or {
        "tool_call_id": "legacy", "tool_name": "headroom_retrieve", "content": "legacy result",
    }
    assert item.retrieve({"hash": "a" * 24}, "legacy") == "legacy result"
    assert len(seen) == 1


def test_new_mode_recovery_uses_worker_only_after_its_validated_prepare(tmp_path):
    item = adapter(tmp_path, strategy=MODE)
    chat = adapter_request()
    spans = descriptors(chat, [2])
    seen = []

    def rpc(operation, **values):
        seen.append(operation)
        if operation == "compress_documents_preprotected":
            return adapter_response(chat, spans)
        return {"tool_call_id": "later", "tool_name": "headroom_retrieve",
                "content": "actual worker-returned payload"}

    item.rpc = rpc
    item.prepare(chat, eligible_indices=[2], frozen_message_count=1, message_spans=spans)
    assert item.retrieve({"hash": "a" * 24}, "later") == "actual worker-returned payload"
    assert seen == ["compress_documents_preprotected", "retrieve"]
