"""Offline public-API contract tests; no installed Headroom or inference needed."""
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
import ast
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
from types import ModuleType, SimpleNamespace

import pytest

from brainspace import headroom_worker as worker


@dataclass
class CompressConfig:
    compress_user_messages: bool = False
    compress_system_messages: bool = True
    protect_recent: int = 4
    protect_analysis_context: bool = True
    frozen_message_count: int = 0
    target_ratio: float | None = None
    min_tokens_to_compress: int = 250
    kompress_model: str | None = None
    savings_profile: str | None = None
    diagnostics: bool = False


@dataclass
class CompressResult:
    messages: list
    tokens_before: int = 0
    tokens_after: int = 0
    tokens_saved: int = 0
    compression_ratio: float = 0
    transforms_applied: list = field(default_factory=list)
    diagnostics: list | None = None


class Strategy(str, Enum):
    KOMPRESS = "kompress"


@dataclass
class RouterConfig:
    exclude_tools: set | None = None
    protect_recent_reads_fraction: float = 0
    fallback_strategy: Strategy = Strategy.KOMPRESS
    bash_tool_names: frozenset = frozenset({"shell", "bash"})
    active_external_compressors: list | None = None
    nested: dict = field(default_factory=lambda: {"keep": [1, 2]})


@dataclass
class PipelineConfig:
    rollout: dict = field(default_factory=lambda: {"enabled": ("tool_result_interceptors",)})
    pipeline_extensions: list = field(default_factory=list)
    discover_pipeline_extensions: bool = True


@pytest.fixture
def public_api(monkeypatch):
    state = SimpleNamespace(pipelines=[], applies=[], mode="shrink", exclusions=None,
                            router_count=1, failure_index=0, ledger=worker.ActivityLedger())

    class BeaconCompressionObserver:
        pass

    class ContentRouter:
        name = "content_router"

        def __init__(self, config=None, observer=None):
            self.config = config or RouterConfig(exclude_tools=deepcopy(state.exclusions))
            self.observer = observer

    class Interceptor:
        name = "tool_result_interceptors"

    class CacheAligner:
        name = "cache_aligner"

    class TransformPipeline:
        def __init__(self, config=None, transforms=None):
            self.config = config or PipelineConfig()
            self.transforms = transforms if transforms is not None else [
                Interceptor(), CacheAligner(),
                *[ContentRouter(observer=BeaconCompressionObserver())
                  for _ in range(state.router_count)]]
            state.pipelines.append(self)

        def apply(self, **kwargs):
            state.applies.append(deepcopy(kwargs))
            if state.mode == "exception":
                raise RuntimeError("pipeline failure")
            # The existing observation boundary still accounts for actual work.
            worker.observe_run(lambda *a: None, state.ledger)(object(), [], {})
            messages = kwargs["messages"]
            if state.mode != "noop":
                for i, message in enumerate(messages):
                    if i not in kwargs["protect"]:
                        message["content"] = "Short document <<ccr:abc>>"
            if state.mode == "protected":
                messages[state.failure_index]["content"] = "unexpected mutation"
            if state.mode == "identity":
                messages[4]["tool_call_id"] = "changed"
            if state.mode == "length":
                messages.pop()
            return SimpleNamespace(
                messages=messages, tokens_before=0 if state.mode == "sentinel" else 1000,
                tokens_after=1100 if state.mode == "inflation" else
                (1000 if state.mode == "noop" else 500),
                transforms_applied=["pipeline:circuit_open"] if state.mode == "circuit"
                else ["content_router:kompress"],
                message_decisions=None)

    def extract_user_query(messages):
        return next(m["content"] for m in reversed(messages) if m["role"] == "user")

    modules = {
        "headroom": {"CompressConfig": CompressConfig, "CompressResult": CompressResult},
        "headroom.transforms": {"TransformPipeline": TransformPipeline,
                                "ContentRouter": ContentRouter},
        "headroom.config": {"DEFAULT_EXCLUDE_TOOLS": frozenset({"view", "Read", "edit"}),
                            "is_tool_excluded": lambda name, tools: any(
                                item.lower() in (name, "*") for item in tools)},
        "headroom.telemetry.session": {"BeaconCompressionObserver": BeaconCompressionObserver},
        "headroom.utils": {"extract_user_query": extract_user_query},
    }
    for name, attrs in modules.items():
        module = ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
    state.router_type = ContentRouter
    state.observer_type = BeaconCompressionObserver
    return state


def request():
    # Recorded canonical native shape: status is checked by the parent before
    # projection and successful exact-byte receipts supply E out of band.
    messages = [
        {"role": "system", "content": "Immutable system"},
        {"role": "developer", "content": "Immutable developer"},
        {"role": "user", "content": "Give an overview. eligible_indices=[0, 1]"},
    ]
    for call_id, name, path, text in (
        ("old", "view", "docs/overview.md", "Document prose. " * 200),
        ("unknown", "view", "unknown.txt", "Unbound output"),
        ("failed", "view", "failed.rst", "Error: read failed"),
        ("new", "view", "new.markdown", "Newest output"),
    ):
        messages += [
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": call_id, "type": "function",
                 "function": {"name": name, "arguments": json.dumps({"path": path})}}]},
            {"role": "tool", "tool_call_id": call_id, "content": text},
        ]
    messages[8]["_native_metadata"] = {"success": False}
    return {"id": "doc-1", "op": "compress_documents", "model": "recorded-model",
            "messages": messages, "eligible_indices": [4], "frozen_message_count": 3,
            "keep_recent_tool_results": 1}


def test_real_public_composition_and_all_facade_knobs(public_api):
    runner = worker.DocumentPipeline()
    incoming = request()
    original = deepcopy(incoming)
    result, receipt = runner.compress(incoming)
    prototype, configured = public_api.pipelines
    assert prototype is not configured
    assert prototype.config is configured.config
    assert configured.transforms[:2] == prototype.transforms[:2]
    assert configured.transforms[2] is not prototype.transforms[2]
    old, new = prototype.transforms[2], configured.transforms[2]
    assert old.config.exclude_tools is None
    assert new.config.exclude_tools == {"Read", "edit"}
    assert isinstance(new.observer, public_api.observer_type)
    assert new.config.nested == old.config.nested
    assert new.config.nested is not old.config.nested
    assert new.config.fallback_strategy == old.config.fallback_strategy
    kwargs = public_api.applies[0]
    assert kwargs == {
        "messages": original["messages"], "model": "recorded-model", "model_limit": 200000,
        "context": original["messages"][2]["content"], "biases": None,
        "protect": set(range(len(original["messages"]))) - {4},
        "compress_user_messages": False, "compress_system_messages": False,
        "target_ratio": None, "protect_recent": 4, "protect_analysis_context": True,
        "min_tokens_to_compress": 250, "kompress_model": None,
        "frozen_message_count": 3, "collect_diagnostics": True,
    }
    assert incoming == original
    assert result.messages[4]["content"] != original["messages"][4]["content"]
    for i in range(len(original["messages"])):
        if i != 4:
            assert result.messages[i] == original["messages"][i]
    assert result.messages[3]["tool_calls"][0]["function"]["name"] == "view"
    assert result.tokens_saved == 500
    assert public_api.ledger.snapshot().attempts == 1
    assert receipt["strategy"] == "native-documents-v1"
    manifest = receipt["strategy_manifest"]
    assert manifest["hooks"] is None
    assert manifest["extension_discovery"] is False
    assert manifest["compress_config"]["savings_profile"] is None
    assert receipt["strategy_manifest_sha256"] == hashlib.sha256(json.dumps(
        manifest, sort_keys=True, ensure_ascii=False, allow_nan=False,
        separators=(",", ":")).encode()).hexdigest()
    assert receipt["eligible_indices"] == [4]
    assert receipt["protected_indices"] == sorted(set(range(len(original["messages"]))) - {4})
    again, receipt2 = runner.compress({**incoming, "id": "doc-2"})
    assert receipt2 == receipt
    assert len(public_api.pipelines) == 2


def test_preserve_custom_exclusions_and_manifest_independence(public_api):
    public_api.exclusions = {"view", "Read", "extra"}
    runner = worker.DocumentPipeline()
    _, first = runner.compress(request())
    incoming = request()
    incoming["eligible_indices"] = [6]
    _, second = runner.compress(incoming)
    assert public_api.pipelines[0].transforms[2].config.exclude_tools == {"view", "Read", "extra"}
    assert public_api.pipelines[1].transforms[2].config.exclude_tools == {"Read", "extra"}
    assert first["strategy_manifest"] == second["strategy_manifest"]
    assert first["strategy_manifest_sha256"] == second["strategy_manifest_sha256"]
    assert first["eligible_indices"] != second["eligible_indices"]
    assert first["protected_indices"] != second["protected_indices"]


@pytest.mark.parametrize("field,value", [
    ("eligible_indices", []), ("eligible_indices", [4, 4]),
    ("eligible_indices", [True]), ("eligible_indices", [4.0]),
    ("eligible_indices", [-1]), ("eligible_indices", [100]),
    ("eligible_indices", [0]), ("eligible_indices", [1]),
    ("eligible_indices", [3]), ("eligible_indices", [8]),
    ("eligible_indices", [10]), ("eligible_indices", "4"),
    ("frozen_message_count", 5), ("frozen_message_count", True),
    ("frozen_message_count", -1), ("frozen_message_count", 100),
    ("keep_recent_tool_results", 0), ("keep_recent_tool_results", True),
    ("keep_recent_tool_results", 4), ("keep_recent_tool_results", 65),
    ("model", ""), ("model", None), ("messages", []),
    ("id", ""), ("id", " "), ("id", "a\0b"), ("op", "compress"),
])
def test_reject_bad_envelope_before_pipeline_apply(public_api, field, value):
    incoming = request()
    incoming[field] = value
    with pytest.raises(ValueError):
        worker.DocumentPipeline().compress(incoming)
    assert not public_api.applies


@pytest.mark.parametrize("kind", [
    "extra_key", "missing_key", "duplicate_id", "orphan", "missing_result",
    "interleaved", "duplicate_result", "bad_args", "duplicate_args", "nonobject_args",
    "nan_args", "path_type", "code_path", "name", "nontext", "status", "call_status",
    "success_type", "error", "exit_code", "bad_range", "unknown_args",
])
def test_reject_invalid_document_identity_sequence_and_status(public_api, kind):
    incoming = request()
    messages = incoming["messages"]
    call = messages[3]["tool_calls"][0]
    if kind == "extra_key":
        incoming["hooks"] = None
    elif kind == "missing_key":
        incoming.pop("eligible_indices")
    elif kind == "duplicate_id":
        messages[5]["tool_calls"][0]["id"] = "old"
    elif kind == "orphan":
        messages[4]["tool_call_id"] = "unseen"
    elif kind == "missing_result":
        messages.pop()
    elif kind == "interleaved":
        messages.insert(4, {"role": "user", "content": "interruption"})
    elif kind == "duplicate_result":
        messages.insert(5, deepcopy(messages[4]))
    elif kind in ("bad_args", "duplicate_args", "nonobject_args", "nan_args",
                  "path_type", "code_path", "bad_range", "unknown_args"):
        call["function"]["arguments"] = {
            "bad_args": "{", "duplicate_args": '{"path":"a.md","path":"b.md"}',
            "nonobject_args": "[]", "nan_args": '{"path":"a.md","x":NaN}',
            "path_type": '{"path":null}', "code_path": '{"path":"a.py"}',
            "bad_range": '{"path":"a.md","view_range":[true,5]}',
            "unknown_args": '{"path":"a.md","eligible_indices":[4]}',
        }[kind]
    elif kind == "name":
        call["function"]["name"] = "read_file"
    elif kind == "nontext":
        messages[4]["content"] = [{"type": "text", "text": "document"}]
    elif kind == "status":
        messages[4]["status"] = "unknown"
    elif kind == "call_status":
        call["status"] = "failed"
    elif kind == "success_type":
        messages[4]["_native_metadata"] = {"success": "true"}
    elif kind == "error":
        messages[4]["_native_metadata"] = {"is_error": True}
    elif kind == "exit_code":
        messages[4]["_native_metadata"] = {"exit_code": True}
    with pytest.raises(ValueError):
        worker.DocumentPipeline().compress(incoming)
    assert not public_api.applies


@pytest.mark.parametrize("mode", ["sentinel", "circuit", "exception", "identity", "length"])
def test_pipeline_failures_are_not_success(public_api, mode):
    public_api.mode = mode
    with pytest.raises((ValueError, RuntimeError)):
        worker.DocumentPipeline().compress(request())


@pytest.mark.parametrize("index", [0, 1, 2, 3, 6, 8, 10])
def test_any_noneligible_mutation_fails_even_in_place(public_api, index):
    public_api.mode, public_api.failure_index = "protected", index
    incoming = request()
    original = deepcopy(incoming)
    with pytest.raises(ValueError, match="protected"):
        worker.DocumentPipeline().compress(incoming)
    assert incoming == original


@pytest.mark.parametrize("mode", ["inflation", "noop"])
def test_noop_and_facade_inflation_reversion(public_api, mode):
    public_api.mode = mode
    incoming = request()
    result, _ = worker.DocumentPipeline().compress(incoming)
    assert result.messages == incoming["messages"]
    assert result.tokens_before == result.tokens_after == 1000
    assert result.tokens_saved == result.compression_ratio == 0
    assert result.transforms_applied == (
        ["inflation_guard:reverted"] if mode == "inflation" else ["content_router:kompress"])


@pytest.mark.parametrize("count", [0, 2])
def test_exactly_one_router_required(public_api, count):
    public_api.router_count = count
    with pytest.raises(ValueError):
        worker.DocumentPipeline()


def test_retained_wildcard_exclusion_must_not_be_removed(public_api):
    public_api.exclusions = {"view", "*"}
    with pytest.raises(ValueError):
        worker.DocumentPipeline()
    assert public_api.pipelines[0].transforms[2].config.exclude_tools == {"view", "*"}


def test_strategy_lock_is_task_lifetime_and_both_directions():
    for first, other in (("legacy", "native-documents-v1"),
                         ("native-documents-v1", "legacy")):
        assert worker.lock_strategy(None, first) == first
        assert worker.lock_strategy(first, first) == first
        with pytest.raises(ValueError):
            worker.lock_strategy(first, other)


def run_rpc_loop(requests, public_api):
    """Run the actual dispatcher AST, excluding container startup assertions.

    Security/bootstrap and inference are deliberately not simulated as proof of
    a real container. This exercises unchanged dispatch/emit/ledger code offline.
    """
    tree = ast.parse(Path(worker.__file__).read_text(encoding="utf-8"))
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    main.body = ast.parse(
        "strategy = None\ndocuments = None\ncursor = 0\nseen_hashes = set()\n"
        "config = fixture_config\n"
    ).body + main.body[-2:]
    output, legacy_calls = [], []
    ledger = public_api.ledger

    def legacy_compress(messages, **kwargs):
        legacy_calls.append((deepcopy(messages), kwargs))
        return CompressResult(messages, tokens_before=100, tokens_after=100)

    class Scanner:
        def scan_for_markers(self, messages):
            return ["abc"] if any("<<ccr:abc>>" in str(m.get("content")) for m in messages) else []

    @dataclass
    class Retrieval:
        content: str = "actual stored fragment"

    namespace = dict(vars(worker))
    namespace.update(
        fixture_config=CompressConfig(diagnostics=True),
        headroom=SimpleNamespace(compress=legacy_compress), ledger=ledger,
        sys=SimpleNamespace(stdin=SimpleNamespace(buffer=io.BytesIO(
            b"".join(json.dumps(r).encode() + b"\n" for r in requests)))),
        emit=lambda value, **kwargs: output.append(deepcopy(value)) is None,
        scanner=Scanner(), reference=SimpleNamespace(encode_ordinary=lambda text: list(text)),
        get_tokenizer=lambda model: object(),
        get_compression_store=lambda: SimpleNamespace(
            retrieve=lambda key: SimpleNamespace(original_content="actual stored fragment")),
        handler=SimpleNamespace(_execute_retrieval=lambda call: Retrieval()),
        CCRToolCall=lambda *args: args)
    compiled = ast.fix_missing_locations(ast.Module(body=[main], type_ignores=[]))
    exec(compile(compiled, worker.__file__, "exec"), namespace)
    code = namespace["main"]()
    return code, output, legacy_calls


def test_document_rpc_returns_standard_fields_echo_manifest_and_recovery(public_api):
    code, rows, legacy = run_rpc_loop([
        request(), {**request(), "id": "doc-2"},
        {"id": "get", "op": "retrieve", "hash": "abc", "tool_call_id": "get-1"},
        {"id": "done", "op": "finish"},
    ], public_api)
    assert code == 0 and not legacy
    assert [row["id"] for row in rows] == ["doc-1", "doc-2", "get", "done"]
    assert all(row["ok"] for row in rows)
    result = rows[0]["result"]
    assert {"messages", "transforms", "diagnostics", "reference_message_tokens",
            "upstream_counter", "upstream_tokens_before", "upstream_tokens_after",
            "references", "strategy", "strategy_manifest", "strategy_manifest_sha256",
            "eligible_indices", "protected_indices"} <= result.keys()
    assert result["strategy"] == "native-documents-v1"
    assert result["strategy_manifest"] == rows[1]["result"]["strategy_manifest"]
    assert result["references"] == ["abc"]
    assert rows[2]["result"]["content"] == "actual stored fragment"
    assert rows[3]["result"]["recoveries"] == {"abc": "actual stored fragment"}
    assert rows[3]["result"]["python_onnx_inventory"]["local_inference_inventory_complete"] is False
    assert rows[3]["result"]["python_onnx_inventory"]["attempts"] == 2
    assert rows[0]["python_onnx_updates"]["events"][0]["rpc_at_entry"] == "doc-1"
    assert "python_onnx_updates" in rows[0]


def test_legacy_rpc_keeps_facade_arguments_and_legacy_result_shape(public_api):
    incoming = request()
    legacy = {key: incoming[key] for key in ("id", "model", "messages")}
    legacy["op"] = "compress"
    code, rows, calls = run_rpc_loop([legacy, {"id": "done", "op": "finish"}], public_api)
    assert code == 0 and len(calls) == 1 and not public_api.pipelines
    assert calls[0] == (incoming["messages"], {
        "model": incoming["model"], "model_limit": 200000, "optimize": True,
        "config": CompressConfig(diagnostics=True)})
    assert set(rows[0]["result"]) == {
        "messages", "transforms", "diagnostics", "reference_message_tokens",
        "upstream_counter", "upstream_tokens_before", "upstream_tokens_after", "references"}
    assert "strategy" not in rows[0]["result"]


@pytest.mark.parametrize("document_first", [True, False])
def test_rpc_rejects_strategy_mixing_before_second_compression(public_api, document_first):
    document = request()
    legacy = {key: document[key] for key in ("id", "model", "messages")}
    legacy.update(id="legacy", op="compress")
    requests = [document, legacy] if document_first else [legacy, document]
    code, rows, calls = run_rpc_loop(requests, public_api)
    assert code == 2 and rows[0]["ok"] and rows[1]["ok"] is False
    assert rows[1]["error_type"] == "ValueError"
    assert len(public_api.applies) == int(document_first)
    assert len(calls) == int(not document_first)
    assert len(public_api.pipelines) == (2 if document_first else 0)
    assert public_api.ledger.snapshot().attempts == int(document_first)


def test_rpc_invalid_eligibility_does_not_even_construct_vendor_pipeline(public_api):
    incoming = request()
    incoming["eligible_indices"] = [0]
    code, rows, _ = run_rpc_loop([incoming], public_api)
    assert code == 2 and rows[0]["ok"] is False
    assert not public_api.pipelines


def test_utf8_manifest_and_no_request_model_prefix_or_content_leak(public_api):
    public_api.exclusions = {"view", "工具"}
    runner = worker.DocumentPipeline()
    incoming = request()
    _, first = runner.compress(incoming)
    incoming.update(id="different", model="different-model", frozen_message_count=4,
                    keep_recent_tool_results=2)
    incoming["messages"][4]["content"] = "Other legitimate prose with a ```fence``` interior."
    _, second = runner.compress(incoming)
    assert first["strategy_manifest"] == second["strategy_manifest"]
    assert first["strategy_manifest_sha256"] == second["strategy_manifest_sha256"]
    wire = json.dumps(first["strategy_manifest"], ensure_ascii=False,
                      sort_keys=True, separators=(",", ":"))
    assert "工具" in wire and "Other legitimate prose" not in wire
    assert hashlib.sha256(wire.encode("utf-8")).hexdigest() == first["strategy_manifest_sha256"]


@pytest.mark.parametrize("suffix", [".md", ".markdown", ".rst", ".txt"])
def test_document_suffixes_and_native_view_range(public_api, suffix):
    incoming = request()
    incoming["messages"][3]["tool_calls"][0]["function"]["arguments"] = json.dumps(
        {"path": "docs/real" + suffix, "view_range": [1, -1]})
    result, _ = worker.DocumentPipeline().compress(incoming)
    assert result.messages[4]["content"] != incoming["messages"][4]["content"]


@pytest.mark.parametrize("identity", [" ", "a\0b", "x" * 513])
def test_malformed_call_ids_fail_even_when_result_matches(public_api, identity):
    incoming = request()
    incoming["messages"][3]["tool_calls"][0]["id"] = identity
    incoming["messages"][4]["tool_call_id"] = identity
    with pytest.raises(ValueError):
        worker.DocumentPipeline().compress(incoming)
    assert not public_api.applies


def test_worker_accepts_large_positive_recent_bound_when_an_old_result_exists(public_api):
    incoming = request()
    messages = incoming["messages"]
    for index in range(62):
        call_id = f"recent-{index}"
        call = deepcopy(messages[3])
        call["tool_calls"][0]["id"] = call_id
        messages.extend([call, {"role": "tool", "tool_call_id": call_id, "content": "Recent text"}])
    incoming["keep_recent_tool_results"] = 65
    result, receipt = worker.DocumentPipeline().compress(incoming)
    assert receipt["eligible_indices"] == [4]
    assert receipt["document_request"]["keep_recent_tool_results"] == 65
    assert result.messages[4]["content"] != messages[4]["content"]
    assert all(result.messages[i] == messages[i] for i in receipt["protected_indices"])


def test_recent_bound_larger_than_history_protects_every_result(public_api):
    incoming = request()
    incoming["keep_recent_tool_results"] = 10**30
    with pytest.raises(ValueError, match="protected or incomplete"):
        worker.DocumentPipeline().compress(incoming)
    assert not public_api.applies


@pytest.mark.parametrize("path,eligible", [
    (r"C:\workspace\docs\overview.md", True),
    (r"C:\workspace\docs\overview.markdown", True),
    (r"\\server\share\docs\overview.rst", True),
    (r"docs\overview.txt", True),
    (r"C:\workspace\docs.md\source.py", False),
    (r"C:\workspace\docs.md\README", False),
    (r"C:\workspace\docs\.txt", False),
])
def test_windows_document_paths_with_linux_path_semantics(public_api, monkeypatch, path, eligible):
    # Explicitly model container pathlib semantics even when pytest runs on Windows.
    monkeypatch.setattr(worker, "Path", PurePosixPath)
    incoming = request()
    incoming["messages"][3]["tool_calls"][0]["function"]["arguments"] = json.dumps({"path": path})
    if eligible:
        result, _ = worker.DocumentPipeline().compress(incoming)
        assert result.messages[4]["content"] != incoming["messages"][4]["content"]
        assert result.messages[3] == incoming["messages"][3]
    else:
        with pytest.raises(ValueError, match="ineligible document"):
            worker.DocumentPipeline().compress(incoming)
        assert not public_api.applies


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("bounds", [None, [2, 9], [2, -1], [9007199254740991, -1],
                                   [9007199254740991, 9007199254740991]])
def test_v2_source_receipt_composes_with_actual_worker_validator(
    tmp_path, public_api, force, bounds,
):
    from brainspace.native_events import NativeEventCollector, RANGED_SOURCE_CONTRACT
    from test_native_events import events

    incoming = request()
    incoming["model"] = "gpt-6-astra"
    call = incoming["messages"][3]["tool_calls"][0]
    arguments = {"path": "docs/overview.md", "forceReadLargeFiles": force}
    if bounds is not None:
        arguments["view_range"] = bounds
    # Retain the original JSON bytes, not just equivalent parsed arguments.
    call["function"]["arguments"] = json.dumps(arguments, indent=2)
    original = deepcopy(incoming)
    collector = NativeEventCollector(
        workspace=tmp_path, expected_model=incoming["model"],
        source_contract=RANGED_SOURCE_CONTRACT,
    )
    collector.register_expected_calls([call], model=incoming["model"])
    for event in events(call, incoming["messages"][4]["content"]):
        collector.observe(event)
    receipts = collector.source_reads(incoming)
    assert len(receipts) == 1 and receipts[0].matches(incoming["messages"][4], call)
    assert collector.close()["coverage_complete"]
    incoming["eligible_indices"] = [
        i for i, message in enumerate(incoming["messages"])
        if message.get("tool_call_id") == receipts[0].call_id
    ]
    assert worker.document_indices(incoming) == {4}  # Real standalone validator, not Backend.
    result, receipt = worker.DocumentPipeline().compress(incoming)
    assert incoming == original
    assert result.messages[3] == original["messages"][3]
    assert public_api.applies[0]["messages"][3] == original["messages"][3]
    assert all(result.messages[i] == original["messages"][i]
               for i in receipt["protected_indices"])
    assert receipt["strategy"] == "native-documents-v1"
    assert receipt["strategy_manifest"]["guards"]["view_arguments"] == {
        "allowed_fields": ["path", "view_range", "forceReadLargeFiles"],
        "forceReadLargeFiles": "optional_strict_boolean",
        "view_range": {"optional": True, "integer_max": 9007199254740991,
                       "start_min": 1, "end": "inclusive_gte_start_or_minus_one"},
        "preserve_arguments": True,
    }


@pytest.mark.parametrize("bounds", [None, [2, -1]])
@pytest.mark.parametrize("force", [None, 0, 1, "true", "false", [], {}])
def test_force_flag_requires_exact_json_boolean(public_api, force, bounds):
    from brainspace.native_events import _valid_observed_view_arguments

    incoming = request()
    arguments = {"path": "docs/overview.md", "forceReadLargeFiles": force}
    if bounds is not None:
        arguments["view_range"] = bounds
    assert not _valid_observed_view_arguments(arguments)
    incoming["messages"][3]["tool_calls"][0]["function"]["arguments"] = json.dumps(arguments)
    with pytest.raises(ValueError):
        worker.DocumentPipeline().compress(incoming)
    assert not public_api.applies


@pytest.mark.parametrize("bounds", [
    [9007199254740992, -1], [1, 9007199254740992],
    [9007199254740992, 9007199254740992],
    [True, 5], [1, False], [1, 2.0], ["1", 3], [0, 2], [3, 2], [1, -2],
])
def test_worker_range_bounds_match_native_safe_integer_boundary(public_api, bounds):
    from brainspace.native_events import _valid_observed_view_arguments

    incoming = request()
    arguments = {"path": "docs/overview.md", "view_range": bounds}
    assert not _valid_observed_view_arguments(arguments)
    incoming["messages"][3]["tool_calls"][0]["function"]["arguments"] = json.dumps(arguments)
    with pytest.raises(ValueError, match="invalid document view range"):
        worker.DocumentPipeline().compress(incoming)
    assert not public_api.applies


@pytest.mark.parametrize("violation", ["extra_field", "frozen", "newest", "status", "suffix"])
def test_force_flag_does_not_bypass_other_document_guards(public_api, violation):
    incoming = request()
    arguments = {"path": "docs/overview.md", "forceReadLargeFiles": True, "view_range": [2, -1]}
    if violation == "extra_field":
        arguments["other"] = True
    elif violation == "frozen":
        incoming["frozen_message_count"] = 5
    elif violation == "newest":
        incoming["keep_recent_tool_results"] = 4
    elif violation == "status":
        incoming["messages"][4]["status"] = "unknown"
    else:
        arguments["path"] = "docs/source.py"
    incoming["messages"][3]["tool_calls"][0]["function"]["arguments"] = json.dumps(arguments)
    with pytest.raises(ValueError):
        worker.DocumentPipeline().compress(incoming)
    assert not public_api.applies
