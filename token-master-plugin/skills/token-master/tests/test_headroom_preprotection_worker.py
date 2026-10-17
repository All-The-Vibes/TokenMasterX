"""Worker-only composition tests. Vendor pipeline/tag/store/handler are doubles."""
from copy import deepcopy
from dataclasses import dataclass, field
import ast
import hashlib
import importlib.abc
import importlib.util
import io
import json
from pathlib import Path
import re
import socket
import sys
from types import ModuleType, SimpleNamespace

import pytest

from brainspace import headroom_worker as worker
from test_headroom_document_worker import CompressConfig, CompressResult, request as document_request


STRATEGY = "native-documents-structure-tags-v1"
CONTRACT = "document-structure-v1-offsets-v1"
HANDLE = "a" * 24
TABLE = "| Name | Path |\r\n| --- | --- |\r\n| 雪 | config.json |\r\n"
ORDERED = "1. Config first.\n2. Workspace second.\n\n"
PROSE = "This is ordinary source prose without any internal framing.\n"
SOURCE = "Long introduction.\n" + TABLE + "\n" + ORDERED + PROSE
FRAME = re.compile(r"<(tm-structure-[a-f0-9]+-[0-9]+)>(.*?)</\1>", re.S)


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def request(*, source=SOURCE, spans=None):
    value = document_request()
    value.update(op="compress_documents_preprotected", span_contract=CONTRACT)
    value["messages"][4]["content"] = source
    if spans is None:
        spans = [(kind, source.index(text), source.index(text) + len(text))
                 for kind, text in (("table", TABLE), ("ordered-list", ORDERED))]
    value["message_spans"] = [{
        "index": 4, "content_sha256": digest(source),
        "spans": [{"kind": kind, "start": start, "end": end,
                   "sha256": digest(source[start:end])} for kind, start, end in spans],
    }]
    return value


@pytest.fixture
def vendor(monkeypatch):
    state = SimpleNamespace(pipelines=[], applies=[], preflights=[], reads=[], handler_calls=[],
                            store={HANDLE: PROSE}, mode="clean", preflight_mode="normal",
                            handles=[HANDLE], read_exception=None, handler_override=None)

    def denied(*a, **kw):
        pytest.fail("no actual model/native/network execution")
    monkeypatch.setattr(socket, "create_connection", denied)
    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, denied)

    @dataclass
    class RouterConfig:
        exclude_tools: set | None = None
        active_external_compressors: list | None = None
        compress_tagged_content: bool = True  # Verify only new mode explicitly disables it.
        nested: dict = field(default_factory=lambda: {"unchanged": [1, 2]})

    @dataclass
    class PipelineConfig:
        pipeline_extensions: list = field(default_factory=list)
        rollout: tuple = ("stable",)

    class BeaconCompressionObserver:
        pass

    class ContentRouter:
        name = "content_router"

        def __init__(self, config=None, observer=None):
            self.config, self.observer = config or RouterConfig(), observer

    class Interceptor:
        name = "interceptor"

    class TransformPipeline:
        def __init__(self, config=None, transforms=None):
            self.config = config or PipelineConfig()
            self.transforms = transforms if transforms is not None else [
                Interceptor(), ContentRouter(observer=BeaconCompressionObserver())]
            state.pipelines.append(self)

        def apply(self, **kwargs):
            state.applies.append(deepcopy(kwargs))
            if state.mode == "exception":
                raise RuntimeError("vendor pipeline failed")
            messages = kwargs["messages"]
            for index, message in enumerate(messages):
                if index in kwargs["protect"]:
                    continue
                original = message["content"]
                projected = original.replace("Long introduction.", "Brief.")
                frames = [match.group() for match in FRAME.finditer(projected)]
                if state.mode == "noop":
                    projected = original
                elif state.mode == "drop":
                    projected = projected.replace(frames[0], "")
                elif state.mode == "duplicate":
                    projected += frames[0]
                elif state.mode == "reorder":
                    projected = projected.replace(frames[0], "@first@").replace(
                        frames[1], frames[0]).replace("@first@", frames[1])
                elif state.mode == "alter":
                    projected = projected.replace("Config first.", "Workspace first.")
                elif state.mode == "partial":
                    projected = projected.replace("</tm-structure-", "</broken-", 1)
                elif state.mode == "residue":
                    projected += "\n{{HEADROOM_TAG_9}}"
                elif state.mode == "unknown_frame":
                    projected += "\n<tm-structure-unknown>bad</tm-structure-unknown>"
                elif state.mode == "pure":
                    state.store[HANDLE] = original  # Real pure route stores annotated ccr_original.
                if state.mode != "noop":
                    projected += "".join(f"\n[Retrieve more: hash={key}]" for key in state.handles)
                message["content"] = projected
            if state.mode == "protected":
                messages[0]["content"] = "mutated protected system"
            if state.mode == "identity":
                messages[4]["tool_call_id"] = "forged"
            return SimpleNamespace(
                messages=messages, tokens_before=0 if state.mode == "sentinel" else 1000,
                tokens_after=1100 if state.mode == "inflation" else 700,
                transforms_applied=["pipeline:circuit_open"] if state.mode == "circuit" else ["router:mixed"],
                message_decisions=None)

    def protect_tags(text, compress_tagged_content=False):
        assert compress_tagged_content is False
        state.preflights.append(text)
        if state.preflight_mode == "exception":
            raise RuntimeError("private malformed tag detail")
        blocks = []

        def protect(match):
            token = "{{HEADROOM_TAG_" + str(len(blocks)) + "}}"
            blocks.append((token, match.group()))
            return token
        cleaned = FRAME.sub(protect, text)
        if state.preflight_mode == "swallowed" and blocks:
            return "{{HEADROOM_TAG_0}}", [("{{HEADROOM_TAG_0}}", text)]
        if state.preflight_mode == "not_hidden":
            return text, blocks
        return cleaned, blocks

    def restore_tags(text, blocks):
        if state.preflight_mode == "lost":
            return "lost"
        for token, original in blocks:
            text = text.replace(token, original)
        return text

    class Scanner:
        def scan_for_markers(self, messages):
            return sorted({key for message in messages for key in
                           re.findall(r"(?:hash=|<<ccr:)([a-f0-9]{6,64})", message.get("content") or "")})

    class Store:
        def retrieve(self, handle):
            state.reads.append(handle)
            if state.read_exception:
                raise state.read_exception
            value = state.store.get(handle)
            return None if value is None else SimpleNamespace(hash=handle, original_content=value)

    @dataclass
    class CCRToolCall:
        tool_call_id: str
        hash_key: str
        tool_name: str

    @dataclass
    class ToolResult:
        tool_call_id: str
        content: str
        success: bool = True
        tool_name: str = "headroom_retrieve"
        items_retrieved: int = 1

    class Handler:
        def _execute_retrieval(self, call):
            state.handler_calls.append(call)
            if state.handler_override:
                return state.handler_override(call)
            entry = store.retrieve(call.hash_key)
            return ToolResult(call.tool_call_id, json.dumps({
                "hash": call.hash_key, "original_content": entry.original_content,
                "original_item_count": 1}, indent=2))

    store = Store()
    modules = {
        "headroom": {"CompressConfig": CompressConfig, "CompressResult": CompressResult},
        "headroom.config": {"DEFAULT_EXCLUDE_TOOLS": frozenset({"view", "Read", "edit"}),
                            "is_tool_excluded": lambda n, exclusions: n in exclusions},
        "headroom.transforms": {"TransformPipeline": TransformPipeline, "ContentRouter": ContentRouter},
        "headroom.telemetry.session": {"BeaconCompressionObserver": BeaconCompressionObserver},
        "headroom.utils": {"extract_user_query": lambda ms: next(
            m["content"] for m in reversed(ms) if m["role"] == "user")},
        "headroom.transforms.tag_protector": {"protect_tags": protect_tags, "restore_tags": restore_tags},
        "headroom.ccr": {"CCRToolInjector": Scanner},
        "headroom.ccr.tool_calls": {"CCRToolCall": CCRToolCall},
        "headroom.cache.compression_store": {"get_compression_store": lambda: store},
    }
    for name, attrs in modules.items():
        module = ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
    state.handler, state.ToolResult, state.scanner, state.vendor_store = Handler(), ToolResult, Scanner(), store
    return state


def test_new_mode_composes_real_worker_checks_preserves_defaults_and_manifest(vendor):
    incoming = request()
    before = deepcopy(incoming)
    runner = worker.DocumentPipeline(preprotect=True)
    result, receipt = runner.compress(incoming)
    assert incoming == before
    assert len(vendor.applies) == 1
    prototype, pipeline = vendor.pipelines
    assert prototype.config is pipeline.config
    assert pipeline.transforms[0] is prototype.transforms[0]
    assert prototype.transforms[1].config.compress_tagged_content is True
    assert pipeline.transforms[1].config.compress_tagged_content is False
    assert pipeline.transforms[1].config.exclude_tools == {"Read", "edit"}
    assert result.messages[4]["content"] != SOURCE
    assert TABLE in result.messages[4]["content"] and ORDERED in result.messages[4]["content"]
    assert "<tm-" not in result.messages[4]["content"] and "HEADROOM_TAG" not in result.messages[4]["content"]
    assert all(result.messages[i] == before["messages"][i] for i in range(11) if i != 4)
    assert vendor.applies[0]["context"] == before["messages"][2]["content"]
    assert "<tm-structure-" in vendor.applies[0]["messages"][4]["content"]
    assert receipt["strategy"] == worker.PREPROTECTION_STRATEGY == STRATEGY
    assert worker.SPAN_CONTRACT == CONTRACT
    assert worker.PREPROTECTION_KEYS == worker.DOCUMENT_KEYS | {"span_contract", "message_spans"}
    assert receipt["eligible_indices"] == [4]
    assert receipt["span_contract"] == CONTRACT
    assert receipt["message_spans_sha256"] == digest(json.dumps(
        incoming["message_spans"], sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    assert receipt["document_request"] == {"frozen_message_count": 3, "keep_recent_tool_results": 1}
    manifest = receipt["strategy_manifest"]
    assert manifest["preprotection"]["bounds"]["max_spans_per_rpc"] == worker.MAX_PREPROTECTION_SPANS == 256
    assert manifest["preprotection"]["bounds"]["max_handles"] == worker.MAX_PREPROTECTION_HANDLES == 128
    assert manifest["preprotection"]["bounds"]["max_retained_bytes"] == 8 * 1024 * 1024
    assert receipt["strategy_manifest_sha256"] == digest(json.dumps(
        manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    assert receipt["preparation_validation"]["attempts"] == 1
    assert receipt["preparation_validation"]["events"][0]["outcome"] == "validated_candidate"
    assert receipt["preparation_validation"]["publication"] == "unknown_no_parent_ack"
    annotation = receipt["preprotection"]["annotation"][0]
    assert annotation["pristine_sha256"] == digest(SOURCE)
    assert annotation["annotated_sha256"] == digest(vendor.applies[0]["messages"][4]["content"])
    assert annotation["frame_count"] == 2 and annotation["annotated_chars"] > annotation["pristine_chars"]
    counts = receipt["preprotection"]["internal_input_bytes"]
    assert counts["annotated"] > counts["pristine"] and "not_native_model_wire" in counts["scope"]
    assert vendor.reads == [HANDLE]
    assert vendor.store[HANDLE] == PROSE  # Never decoded, rewritten or rekeyed.


def test_frames_are_stable_across_rpcs_but_not_in_task_manifest(vendor):
    runner = worker.DocumentPipeline(preprotect=True)
    _, first = runner.compress(request())
    _, second = runner.compress({**request(), "id": "again"})
    assert vendor.applies[0]["messages"] == vendor.applies[1]["messages"]
    assert first["strategy_manifest"] == second["strategy_manifest"]
    assert first["strategy_manifest_sha256"] == second["strategy_manifest_sha256"]
    assert len(vendor.reads) == 2
    assert second["preparation_validation"]["attempts"] == 2


@pytest.mark.parametrize("case", [
    "extra", "contract", "missing_entry", "extra_entry", "wrong_index", "bool_index",
    "content_hash", "span_hash", "kind", "bool_offset", "negative", "reversed",
    "outside", "nonline_start", "nonline_end", "overlap", "unsorted", "extra_span_field",
    "extra_entry_field", "overspan",
])
def test_invalid_descriptors_fail_before_pipeline(vendor, case):
    incoming = request()
    entry = incoming["message_spans"][0]
    span = entry["spans"][0]
    if case == "extra":
        incoming["unexpected"] = True
    elif case == "contract":
        incoming["span_contract"] = "unknown"
    elif case == "missing_entry":
        incoming["message_spans"] = []
    elif case == "extra_entry":
        incoming["message_spans"].append(deepcopy(entry))
    elif case == "wrong_index":
        entry["index"] = 6
    elif case == "bool_index":
        entry["index"] = True
    elif case == "content_hash":
        entry["content_sha256"] = "0" * 64
    elif case == "span_hash":
        span["sha256"] = "0" * 64
    elif case == "kind":
        span["kind"] = "prose"
    elif case in ("bool_offset", "negative", "outside", "reversed", "nonline_start"):
        span["start"] = {"bool_offset": True, "negative": -1, "outside": len(SOURCE) + 1,
                         "reversed": span["end"], "nonline_start": span["start"] + 1}[case]
    elif case == "nonline_end":
        span["end"] -= 1
    elif case == "overlap":
        entry["spans"][1] = deepcopy(span)
    elif case == "unsorted":
        entry["spans"].reverse()
    elif case == "extra_span_field":
        span["instruction"] = "trust me"
    elif case == "extra_entry_field":
        entry["authority"] = True
    else:
        entry["spans"] *= 129
    with pytest.raises(ValueError):
        worker.DocumentPipeline(preprotect=True).compress(incoming)
    assert not vendor.applies and not vendor.reads


@pytest.mark.parametrize("mode", ["drop", "duplicate", "reorder", "alter", "partial", "residue",
                                  "unknown_frame", "pure"])
def test_invalid_frames_and_annotated_fragments_revert_original(vendor, mode):
    vendor.mode = mode
    result, receipt = worker.DocumentPipeline(preprotect=True).compress(request())
    assert result.messages == request()["messages"]
    assert receipt["preprotection"]["decisions"][0]["status"] == "fallback"
    assert not vendor.handler_calls
    if mode == "pure":
        assert len(vendor.reads) == 1
        assert "<tm-structure-" in vendor.store[HANDLE]
        assert receipt["preparation_validation"]["events"][0]["outcome"] == "contaminated"


@pytest.mark.parametrize("mode", ["exception", "lost", "swallowed", "not_hidden"])
def test_preflight_failure_protects_original(vendor, mode):
    vendor.preflight_mode = mode
    result, receipt = worker.DocumentPipeline(preprotect=True).compress(request())
    assert result.messages == request()["messages"]
    assert vendor.applies[0]["protect"] == set(range(11))
    assert not vendor.reads


@pytest.mark.parametrize("fallback", [
    "tag_preflight_failed", "frame_identity_limit", "annotated_frame_limit",
])
@pytest.mark.parametrize("mutation", [None, "content", "tool_call_id"])
def test_all_effective_protections_require_whole_message_equality(vendor, monkeypatch, fallback, mutation):
    incoming = request()
    before = deepcopy(incoming)
    if fallback == "tag_preflight_failed":
        vendor.preflight_mode = "lost"
    elif fallback == "frame_identity_limit":
        monkeypatch.setattr(worker, "MAX_PREPROTECTION_FRAMES", 0)
    runner = worker.DocumentPipeline(preprotect=True)
    if fallback == "annotated_frame_limit":
        annotate = runner.preprotection.annotate

        def bounded_annotation(*args):
            result = annotate(*args)
            # Exercise the post-admission frame bound without rejecting the RPC
            # at its earlier mechanical size check or replacing the codec.
            monkeypatch.setattr(worker, "MAX_FRAME", len(worker._canonical(incoming["messages"]).encode()))
            return result
        monkeypatch.setattr(runner.preprotection, "annotate", bounded_annotation)
    apply = runner.pipeline.apply

    def violate_protection(**kwargs):
        result = apply(**kwargs)
        assert 4 in kwargs["protect"]
        if mutation is not None:
            result.messages[4][mutation] = "unapproved protected mutation"
        return result
    monkeypatch.setattr(runner.pipeline, "apply", violate_protection)
    if mutation is None:
        result, receipt = runner.compress(incoming)
        assert result.messages == before["messages"]
        assert receipt["preprotection"]["decisions"] == [
            {"index": 4, "status": "fallback", "reason": fallback}]
        assert receipt["preprotection"]["effective_protected_indices"] == list(range(11))
    else:
        with pytest.raises(ValueError, match="pipeline changed protected message"):
            runner.compress(incoming)
    assert incoming == before
    assert len(vendor.applies) == 1 and vendor.applies[0]["protect"] == set(range(11))
    assert not vendor.reads and not vendor.handler_calls


@pytest.mark.parametrize("collision", [
    "<tm-structure-user>spoof</tm-structure-user>", "{{HEADROOM_TAG_0}}",
    "[Retrieve more: hash=" + HANDLE + "]",
])
def test_original_literals_never_authorize_frames_or_handles(vendor, collision):
    incoming = request(source=SOURCE + collision)
    result, _ = worker.DocumentPipeline(preprotect=True).compress(incoming)
    assert result.messages == incoming["messages"]
    assert not vendor.reads


def test_empty_spans_and_eof_unicode_offsets_are_mechanical_not_markdown(vendor):
    for incoming in (request(spans=[]), request(source=SOURCE.rstrip("\n"), spans=[
            ("table", SOURCE.index(TABLE), SOURCE.index(TABLE) + len(TABLE)),
        ])):
        result, _ = worker.DocumentPipeline(preprotect=True).compress(incoming)
        assert len(vendor.applies) >= 1
        assert "<tm-" not in result.messages[4]["content"]


@pytest.mark.parametrize("raw,outcome", [
    (None, "missing"), ("foreign source", "not_pristine_slice"),
    ("", "invalid_raw_fragment"), ("\ud800", "invalid_raw_fragment"),
    ("{{HEADROOM_TAG_1}}", "contaminated"), (True, "invalid_raw_fragment"),
])
def test_invalid_raw_fragment_reads_are_counted_and_fail_closed(vendor, raw, outcome):
    vendor.store[HANDLE] = raw
    result, receipt = worker.DocumentPipeline(preprotect=True).compress(request())
    assert result.messages == request()["messages"]
    assert len(vendor.reads) == 1
    assert receipt["preparation_validation"]["events"][0]["outcome"] == outcome


def test_validation_exception_is_recorded_without_exception_text(vendor):
    vendor.read_exception = RuntimeError("private <tm-structure-secret>details")
    result, receipt = worker.DocumentPipeline(preprotect=True).compress(request())
    assert result.messages == request()["messages"]
    event = receipt["preparation_validation"]["events"][0]
    assert event["outcome"] == "exception" and event["error_type"] == "RuntimeError"
    assert event["id"].startswith("preparation-validation-")
    assert "tool_call_id" not in event
    assert "private" not in json.dumps(receipt)


def test_duplicate_pristine_slice_is_ambiguous(vendor):
    incoming = request(source=SOURCE + PROSE)
    result, receipt = worker.DocumentPipeline(preprotect=True).compress(incoming)
    assert result.messages == incoming["messages"]
    assert receipt["preparation_validation"]["events"][0]["outcome"] == "ambiguous_slice"


def test_actual_handler_once_and_unchanged_delivery_no_pre_read(vendor):
    runner = worker.DocumentPipeline(preprotect=True)
    runner.compress(request())
    result = runner.recover(HANDLE, "native-call-1", vendor.handler)
    assert result["success"] is True
    assert result["content"] == json.dumps(
        {"hash": HANDLE, "original_content": PROSE, "original_item_count": 1}, indent=2)
    assert result["tool_call_id"] == "native-call-1"
    assert len(vendor.handler_calls) == 1 and vendor.reads == [HANDLE, HANDLE]


def test_handle_binding_is_immutable_and_new_origin_must_be_checked(vendor):
    runner = worker.DocumentPipeline(preprotect=True)
    runner.compress(request())
    different = "Different pristine prose.\n"
    vendor.store[HANDLE] = different
    incoming = request(source=SOURCE.replace(PROSE, different))
    result, receipt = runner.compress(incoming)
    assert result.messages == incoming["messages"]
    assert receipt["preparation_validation"]["events"][-1]["outcome"] == "binding_conflict"
    refused = runner.recover(HANDLE, "actual-native", vendor.handler)
    assert not refused["success"] and different not in refused["content"]
    vendor.store[HANDLE] = PROSE
    assert runner.recover(HANDLE, "actual-native-2", vendor.handler)["success"]
    incoming = request()
    incoming["messages"][3]["tool_calls"][0]["id"] = "other-source-call"
    incoming["messages"][4]["tool_call_id"] = "other-source-call"
    result, receipt = runner.compress(incoming)
    assert result.messages == incoming["messages"]
    assert receipt["preparation_validation"]["events"][-1]["outcome"] == "binding_conflict"


@pytest.mark.parametrize("mutation", ["content", "hash", "id", "name", "success", "json",
                                     "duplicate", "error", "count", "extra"])
def test_handler_payload_failure_never_leaks_or_substitutes(vendor, mutation):
    runner = worker.DocumentPipeline(preprotect=True)
    runner.compress(request())

    def bad(call):
        payload = {"hash": HANDLE, "original_content": PROSE, "original_item_count": 1}
        result = vendor.ToolResult(call.tool_call_id, "")
        if mutation == "content":
            payload["original_content"] = "<tm-structure-secret>raw contamination"
        elif mutation == "hash":
            payload["hash"] = "b" * 24
        elif mutation == "id":
            result.tool_call_id = "wrong"
        elif mutation == "name":
            result.tool_name = "wrong"
        elif mutation == "success":
            result.success = 1
        elif mutation == "count":
            payload["original_item_count"] = True
        elif mutation == "extra":
            payload["hidden"] = "{{HEADROOM_TAG_1}}"
        result.content = json.dumps(payload)
        if mutation == "json":
            result.content = "broken <tm-structure-secret>"
        elif mutation == "duplicate":
            result.content = result.content[:-1] + ', "hash":"' + HANDLE + '"}'
        elif mutation == "error":
            result.success = False
            result.content = '{"error":"private <tm-structure-secret> exception"}'
        return result
    vendor.handler_override = bad
    response = runner.recover(HANDLE, "actual-native", vendor.handler)
    assert response["success"] is False and response["tool_call_id"] == "actual-native"
    assert PROSE not in response["content"] and "tm-structure" not in response["content"]
    assert "private" not in response["content"]
    assert len(vendor.handler_calls) == 1 and len(vendor.reads) == 1


def test_unknown_recovery_does_not_call_handler(vendor):
    runner = worker.DocumentPipeline(preprotect=True)
    response = runner.recover("b" * 24, "actual-native", vendor.handler)
    assert response["success"] is False
    assert not vendor.handler_calls and not vendor.reads


@pytest.mark.parametrize("bound", ["handles", "bytes", "validations", "frames"])
def test_saturation_never_evicts_older_bindings(vendor, monkeypatch, bound):
    if bound == "handles":
        monkeypatch.setattr(worker, "MAX_PREPROTECTION_HANDLES", 1)
    elif bound == "bytes":
        monkeypatch.setattr(worker, "MAX_PREPROTECTION_RETAINED_BYTES", len(PROSE.encode()))
    elif bound == "validations":
        monkeypatch.setattr(worker, "MAX_PREPROTECTION_VALIDATIONS", 1)
    else:
        monkeypatch.setattr(worker, "MAX_PREPROTECTION_FRAMES", 2)
    runner = worker.DocumentPipeline(preprotect=True)
    runner.compress(request())
    vendor.handles = ["b" * 24]
    vendor.store[vendor.handles[0]] = "Different.\n"
    incoming = request(source=SOURCE.replace(PROSE, "Different.\n"))
    result, _ = runner.compress(incoming)
    assert result.messages == incoming["messages"]
    assert runner.recover(HANDLE, "still-owned", vendor.handler)["success"] is True


@pytest.mark.parametrize("mode", ["exception", "sentinel", "circuit", "protected", "identity"])
def test_vendor_pipeline_guard_errors_are_not_success(vendor, mode):
    vendor.mode = mode
    with pytest.raises((ValueError, RuntimeError)):
        worker.DocumentPipeline(preprotect=True).compress(request())


@pytest.mark.parametrize("mode", ["noop", "inflation"])
def test_noop_and_inflation_do_not_validate_or_claim_projection(vendor, mode):
    vendor.mode = mode
    result, receipt = worker.DocumentPipeline(preprotect=True).compress(request())
    assert result.messages == request()["messages"]
    assert not vendor.reads
    assert receipt["preparation_validation"]["attempts"] == 0


def test_strategy_lock_keeps_new_mode_separate_from_both_old_modes():
    for other in ("legacy", "native-documents-v1"):
        with pytest.raises(ValueError):
            worker.lock_strategy(STRATEGY, other)
        with pytest.raises(ValueError):
            worker.lock_strategy(other, STRATEGY)
    assert worker.lock_strategy(None, STRATEGY) == STRATEGY


def test_standalone_worker_has_no_product_imports():
    tree = ast.parse(Path(worker.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0
            assert (node.module or "").split(".")[0] not in {"brainspace", "tests", "evals"}


def test_mechanical_validator_imported_standalone_needs_no_vendor_or_product(monkeypatch):
    class Block(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in ("headroom", "brainspace", "onnxruntime", "tiktoken"):
                raise AssertionError("optional import during mechanical validation")
    monkeypatch.setattr(sys, "meta_path", [Block(), *sys.meta_path])
    spec = importlib.util.spec_from_file_location("standalone_preprotection_worker", worker.__file__)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    assert module.preprotection_indices(request()) == {4}


def run_rpc_loop(requests, vendor, *, ledger=None, emit=None, input_stream=None):
    """Actual dispatcher code, minus privileged bootstrap; no real vendor imports."""
    tree = ast.parse(Path(worker.__file__).read_text(encoding="utf-8"))
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    main.body = ast.parse(
        "strategy = None\ndocuments = None\ncursor = 0\nseen_hashes = set()\n"
        "config = fixture_config\n"
    ).body + main.body[-2:]
    output, calls = [], []

    def facade(messages, **kwargs):
        calls.append(deepcopy(kwargs))
        return CompressResult(messages, tokens_before=1000, tokens_after=1000)

    namespace = dict(vars(worker))
    namespace.update(
        fixture_config=CompressConfig(diagnostics=True),
        headroom=SimpleNamespace(compress=facade),
        ledger=worker.ActivityLedger() if ledger is None else ledger,
        sys=SimpleNamespace(stdin=SimpleNamespace(buffer=(
            io.BytesIO(b"".join(json.dumps(r).encode() + b"\n" for r in requests))
            if input_stream is None else input_stream))),
        emit=(lambda value, **kwargs: output.append(deepcopy(value)) is None) if emit is None else emit,
        scanner=vendor.scanner, reference=SimpleNamespace(encode_ordinary=lambda text: list(text)),
        get_tokenizer=lambda model: object(), get_compression_store=lambda: vendor.vendor_store,
        handler=vendor.handler,
        CCRToolCall=sys.modules["headroom.ccr.tool_calls"].CCRToolCall,
    )
    compiled = ast.fix_missing_locations(ast.Module(body=[main], type_ignores=[]))
    exec(compile(compiled, worker.__file__, "exec"), namespace)
    return namespace["main"](), output, calls


def test_rpc_handshake_guarded_recovery_and_scoped_raw_finish(vendor):
    code, rows, calls = run_rpc_loop([
        request(),
        {"id": "recover", "op": "retrieve", "hash": HANDLE, "tool_call_id": "actual-native"},
        {"id": "finish", "op": "finish"},
    ], vendor)
    assert code == 0 and not calls and all(row["ok"] for row in rows)
    result = rows[0]["result"]
    assert result["strategy"] == STRATEGY and result["span_contract"] == CONTRACT
    assert result["eligible_indices"] == [4] and result["protected_indices"] == [0, 1, 2, 3, 5, 6, 7, 8, 9, 10]
    assert result["messages"][4]["content"] != SOURCE and "<tm-" not in result["messages"][4]["content"]
    assert result["upstream_tokens_scope"] == "annotated_vendor_pass_not_final_wire"
    assert rows[1]["result"]["content"] == json.dumps(
        {"hash": HANDLE, "original_content": PROSE, "original_item_count": 1}, indent=2)
    audit = rows[2]["result"]
    assert audit["recoveries"] == {HANDLE: PROSE}
    assert audit["preparation_validation"]["attempts"] == 1
    assert "not_native_delivery" in audit["recoveries_scope"]
    assert audit["python_onnx_inventory"]["local_inference_inventory_complete"] is False
    assert len(vendor.handler_calls) == 1
    assert vendor.reads == [HANDLE, HANDLE, HANDLE]  # validation, real request, late audit.


def test_rejected_pure_fragment_is_only_returned_in_labeled_raw_audit(vendor):
    vendor.mode = "pure"
    code, rows, _ = run_rpc_loop([
        request(),
        {"id": "recover", "op": "retrieve", "hash": HANDLE, "tool_call_id": "actual-native"},
        {"id": "finish", "op": "finish"},
    ], vendor)
    assert code == 0
    assert rows[0]["result"]["messages"] == request()["messages"]
    assert not rows[1]["result"]["success"] and "tm-" not in rows[1]["result"]["content"]
    assert not vendor.handler_calls
    assert "<tm-structure-" in rows[2]["result"]["recoveries"][HANDLE]
    assert "not_native_delivery" in rows[2]["result"]["recoveries_scope"]


@pytest.mark.parametrize("first_new", [False, True])
@pytest.mark.parametrize("old_operation", ["compress", "compress_documents"])
def test_rpc_mixed_modes_fail_before_second_invocation(vendor, first_new, old_operation):
    old = document_request()
    old["op"] = old_operation
    if old_operation == "compress":
        old = {key: old[key] for key in ("id", "op", "model", "messages")}
    new = request()
    code, rows, calls = run_rpc_loop([new, old] if first_new else [old, new], vendor)
    assert code == 2 and rows[0]["ok"] and not rows[1]["ok"]
    assert len(vendor.applies) == (0 if not first_new and old_operation == "compress" else 1)
    assert len(calls) == int(not first_new and old_operation == "compress")
    if first_new:
        assert rows[1]["preparation_validation"]["attempts"] == 1


def test_rpc_bad_spans_fail_before_vendor_construction(vendor):
    incoming = request()
    incoming["message_spans"][0]["spans"][0]["start"] = True
    code, rows, _ = run_rpc_loop([incoming], vendor)
    assert code == 2 and not rows[0]["ok"]
    assert not vendor.pipelines and not vendor.applies and not vendor.reads


def test_failed_final_reference_scan_keeps_validation_attempt_receipt(vendor):
    class FailedScanner:
        def scan_for_markers(self, messages):
            raise RuntimeError("final response marker scan failed")
    vendor.scanner = FailedScanner()  # Worker state's own scanner remains the public fake.
    code, rows, _ = run_rpc_loop([request()], vendor)
    assert code == 2 and not rows[0]["ok"]
    assert rows[0]["preparation_validation"]["attempts"] == 1
    assert rows[0]["preparation_validation"]["events"][0]["outcome"] == "validated_candidate"


class InterruptedInput(io.BytesIO):
    """One admitted RPC, then a controlled interruption while awaiting input."""

    def __init__(self, incoming, interruption):
        super().__init__(json.dumps(incoming).encode() + b"\n")
        self.interruption = interruption

    def readline(self, *args, **kwargs):
        if self.tell():
            raise self.interruption
        return super().readline(*args, **kwargs)


@pytest.mark.parametrize("interruption_type", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("where", ["public_read", "final_scan", "between_rpcs"])
@pytest.mark.parametrize("emit_error_type", [None, OSError, KeyboardInterrupt, SystemExit])
def test_dispatcher_cancellation_emits_known_inventories_without_masking_or_retry(
        vendor, interruption_type, where, emit_error_type):
    interruption = interruption_type("private <tm-structure-original> cancellation")
    emit_error = None if emit_error_type is None else emit_error_type("secondary private cancellation")
    incoming = request()
    stream = None
    if where == "public_read":
        vendor.read_exception = interruption
    elif where == "final_scan":
        def interrupted_scan(messages):
            raise interruption
        vendor.scanner = SimpleNamespace(scan_for_markers=interrupted_scan)
    else:
        stream = InterruptedInput(incoming, interruption)
    ledger = worker.ActivityLedger()
    # Synthetic bookkeeping only: no ONNX/model execution. Keep a pending
    # record to prove the termination receipt does not claim complete inventory.
    event = ledger.start(object(), {})
    ledger.terminal(event, "completed")
    ledger.start(object(), {})
    emission_attempts = []

    def emit(value, **kwargs):
        emission_attempts.append(deepcopy(value))
        if not value["ok"] and emit_error is not None:
            raise emit_error  # A failed attempt is NOT proof of receipt delivery.
        return True
    with pytest.raises(interruption_type) as raised:
        run_rpc_loop([incoming], vendor, ledger=ledger, emit=emit, input_stream=stream)
    assert raised.value is interruption
    assert len(vendor.applies) == 1 and vendor.reads == [HANDLE] and not vendor.handler_calls
    assert len(emission_attempts) == (2 if where == "between_rpcs" else 1)
    receipt = emission_attempts[-1]
    assert receipt["ok"] is False and receipt["id"] == incoming["id"]
    assert receipt["error_type"] == interruption_type.__name__
    validation = receipt["preparation_validation"]
    assert validation["attempts"] == validation["public_retrieve_entries"] == 1
    assert validation["publication"] == "unknown_no_parent_ack"
    event = validation["events"][0]
    assert event["public_retrieve_entered"] is True
    assert event["outcome"] == ("exception" if where == "public_read" else "validated_candidate")
    if where == "public_read":
        assert event["error_type"] == interruption_type.__name__
    inventory = receipt["python_onnx_inventory"]
    assert inventory == ledger.inventory()
    assert inventory["attempts"] == 2 and inventory["pending_count"] == 1
    assert inventory["complete"] is inventory["local_inference_inventory_complete"] is False
    assert receipt["python_onnx_updates"]["revision"] == inventory["revision"]
    assert receipt["python_onnx_calls"] == receipt["python_onnx_updates"]["events"]
    assert len(receipt["python_onnx_calls"]) == (0 if where == "between_rpcs" else 2)
    assert "private" not in json.dumps(receipt) and "<tm-structure-" not in json.dumps(receipt)


@pytest.mark.parametrize("operation", ["compress", "compress_documents"])
@pytest.mark.parametrize("interruption_type", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("where", ["final_scan", "between_rpcs"])
def test_old_dispatcher_cancellation_behavior_is_unchanged(vendor, operation, interruption_type, where):
    incoming = document_request()
    incoming["op"] = operation
    if operation == "compress":
        incoming = {key: incoming[key] for key in ("id", "op", "model", "messages")}
    interruption = interruption_type("old-mode exit")
    stream = None
    if where == "final_scan":
        def interrupted_scan(messages):
            raise interruption
        vendor.scanner = SimpleNamespace(scan_for_markers=interrupted_scan)
    else:
        stream = InterruptedInput(incoming, interruption)
    rows = []
    with pytest.raises(interruption_type) as raised:
        run_rpc_loop([incoming], vendor, input_stream=stream,
                     emit=lambda value, **kwargs: rows.append(deepcopy(value)) is None)
    assert raised.value is interruption
    assert len(rows) == int(where == "between_rpcs") and all(row["ok"] for row in rows)
    assert not vendor.reads and not vendor.preflights and not vendor.handler_calls


@pytest.mark.parametrize("emit_error_type", [OSError, KeyboardInterrupt, SystemExit])
def test_ordinary_exception_secondary_emit_behavior_is_preserved(vendor, emit_error_type):
    def failed_scan(messages):
        raise RuntimeError("ordinary final scan failure")
    vendor.scanner = SimpleNamespace(scan_for_markers=failed_scan)
    secondary = emit_error_type("ordinary-path secondary exit")
    rows = []

    def failed_emit(value, **kwargs):
        rows.append(deepcopy(value))
        raise secondary
    with pytest.raises(emit_error_type) as raised:
        run_rpc_loop([request()], vendor, emit=failed_emit)
    assert raised.value is secondary
    assert rows[0]["ok"] is False and rows[0]["error_type"] == "RuntimeError"
    assert rows[0]["preparation_validation"]["attempts"] == 1
    assert vendor.reads == [HANDLE] and len(vendor.applies) == 1


def test_response_overflow_retains_validation_events(vendor, monkeypatch):
    _, receipt = worker.DocumentPipeline(preprotect=True).compress(request())
    stream = io.StringIO()
    monkeypatch.setattr(worker.sys, "stdout", stream)
    monkeypatch.setattr(worker, "MAX_FRAME", 8192)
    assert worker.emit({"id": "big", "ok": True, "result": {
        "messages": "x" * 9000, "preparation_validation": receipt["preparation_validation"]},
    }, ledger=worker.ActivityLedger()) is False
    overflow = json.loads(stream.getvalue())
    assert overflow["error_type"] == "ResponseFrameOverflow"
    assert overflow["preparation_validation"]["attempts"] == 1
    assert overflow["preparation_validation"]["events"][0]["public_retrieve_entered"] is True


def test_total_span_limit_is_not_a_per_message_limit():
    text = "".join(f"line {index}\n" for index in range(257))
    spans = []
    start = 0
    for line in text.splitlines(keepends=True):
        spans.append(("ordered-list", start, start + len(line)))
        start += len(line)
    assert worker.preprotection_indices(request(source=text, spans=spans[:256])) == {4}
    with pytest.raises(ValueError, match="span budget"):
        worker.preprotection_indices(request(source=text, spans=spans))
    incoming = request(source=text, spans=spans[:129])
    incoming["messages"][6]["content"] = text
    incoming["eligible_indices"] = [4, 6]
    incoming["message_spans"].append({**deepcopy(incoming["message_spans"][0]), "index": 6})
    with pytest.raises(ValueError, match="span budget"):
        worker.preprotection_indices(incoming)


def test_codepoint_offsets_support_astral_unicode_and_eof(vendor):
    text = "🚀 paragraph\n| 雪 | café |\r\n| --- | --- |\r\n| e\u0301 | 🧪 |"
    start = text.index("|")
    incoming = request(source=text, spans=[("table", start, len(text))])
    assert worker.preprotection_indices(incoming) == {4}
    vendor.mode = "noop"
    result, _ = worker.DocumentPipeline(preprotect=True).compress(incoming)
    assert result.messages == incoming["messages"]
    span = incoming["message_spans"][0]["spans"][0]
    span["start"] += 1  # UTF-16-style extra surrogate unit is NOT a Python offset.
    with pytest.raises(ValueError):
        worker.preprotection_indices(incoming)


def test_one_bad_handle_reverts_whole_message_but_retains_successful_validation(vendor):
    second = "b" * 24
    vendor.handles = [HANDLE, second]
    vendor.store[second] = "not present in pristine source"
    runner = worker.DocumentPipeline(preprotect=True)
    result, receipt = runner.compress(request())
    assert result.messages == request()["messages"]
    assert [event["outcome"] for event in receipt["preparation_validation"]["events"]] == [
        "validated_candidate", "not_pristine_slice"]
    assert receipt["preparation_validation"]["publication"] == "unknown_no_parent_ack"
    assert runner.recover(HANDLE, "native-real", vendor.handler)["success"]
    count = len(vendor.handler_calls)
    assert not runner.recover(second, "native-real-2", vendor.handler)["success"]
    assert len(vendor.handler_calls) == count


def test_independent_eligible_message_survives_another_message_fallback(vendor):
    incoming = request()
    incoming["eligible_indices"] = [4, 6]
    incoming["messages"][6]["content"] = "Long introduction.\nDifferent source.\n"
    incoming["message_spans"].append({
        "index": 6, "content_sha256": digest(incoming["messages"][6]["content"]), "spans": []})
    result, receipt = worker.DocumentPipeline(preprotect=True).compress(incoming)
    assert result.messages[4]["content"] != SOURCE
    assert result.messages[6] == incoming["messages"][6]
    assert [d["status"] for d in receipt["preprotection"]["decisions"]] == [
        "validated_candidate", "fallback"]
    assert len(vendor.reads) == 2  # A new origin never silently inherits old handle authority.


def test_recovery_exception_is_contained_after_exactly_one_handler_call(vendor):
    runner = worker.DocumentPipeline(preprotect=True)
    runner.compress(request())

    def fail(call):
        raise RuntimeError("private {{HEADROOM_TAG_1}}")
    vendor.handler_override = fail
    response = runner.recover(HANDLE, "actual-native", vendor.handler)
    assert response["content"] == '{"error":"preprotection_recovery_rejected"}'
    assert not response["success"]
    assert len(vendor.handler_calls) == 1 and vendor.reads == [HANDLE]


@pytest.mark.parametrize("control,value", [
    ("eligible_indices", [10]), ("eligible_indices", [0]),
    ("frozen_message_count", 5), ("keep_recent_tool_results", True),
])
def test_new_mode_keeps_document_control_guards(vendor, control, value):
    incoming = request()
    incoming[control] = value
    with pytest.raises(ValueError):
        worker.DocumentPipeline(preprotect=True).compress(incoming)
    assert not vendor.applies and not vendor.reads
