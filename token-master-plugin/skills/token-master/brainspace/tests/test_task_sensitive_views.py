"""G02/G06: exact defaults, explicit views, and fail-closed recovery."""

import hashlib
import json
import sys
import types

import pytest

from brainspace.compressors.code_compressor import compress_code
from brainspace.compressors.json_compressor import compress_json
from brainspace.compressors.logs_compressor import compress_logs
from brainspace.compressors.prose_compressor import compress_prose


CODE = '@decorate("a  b")\r\ndef work(x):\r\n\t"""Keep  spacing."""\r\n\treturn "a  b"\r\n'
PROSE = 'Quote: "a  b".  \r\n\r\n\r\n```python\r\nx = """a  b\n\n\nc"""\r\n```\r\n'
JSON = json.dumps([{"id": i, "value": "a  b" * 90} for i in range(20)])
LOG = "".join(f"[INFO] processed {i}\n" for i in range(40)) + "[INFO] Build succeeded\n"
CASES = [(compress_code, CODE), (compress_json, JSON),
         (compress_logs, LOG), (compress_prose, PROSE)]


def memory_stash():
    stored = {}

    def stash(text, **_):
        ref = f"[[BR:{hashlib.sha256(text.encode()).hexdigest()[:12]}]]"
        stored[ref] = text
        return ref

    return stash, stored


def broken_stash(mode):
    if mode == "absent":
        return None

    def stash(*_, **__):
        if mode == "readonly":
            raise PermissionError("read-only store")
        if mode == "full":
            raise OSError("disk full")
        if mode == "throws":
            raise RuntimeError("store unavailable")
        return {"none": None, "empty": "", "invalid": "not a reference",
                "wrong_type": 17}[mode]

    return stash


@pytest.mark.parametrize("compress,content", CASES, ids=["code", "json", "log", "prose"])
@pytest.mark.parametrize("intent", ["exact", "edit", "debug", "aggregate",
                                   "exhaustive", "security", "unknown", None])
def test_protected_intents_are_byte_exact(compress, content, intent):
    def forbidden(*_, **__):
        pytest.fail("Passthrough intents must not touch storage")

    assert compress(content, stash=forbidden, intent=intent, arbitrary_opt=True) == content


@pytest.mark.parametrize("mode", ["absent", "none", "empty", "invalid",
                                  "wrong_type", "throws", "readonly", "full"])
@pytest.mark.parametrize("compress,content", CASES, ids=["code", "json", "log", "prose"])
def test_opt_in_views_fail_closed(compress, content, mode):
    intent = "navigation" if compress is compress_code else "overview"
    assert compress(content, stash=broken_stash(mode), intent=intent) == content


@pytest.mark.parametrize("compress,content", [CASES[0], CASES[2], CASES[3]], ids=["code", "log", "prose"])
def test_default_is_exact_even_with_recovery(compress, content):
    stash, stored = memory_stash()
    assert compress(content, stash=stash) == content
    assert not stored


def test_default_json_keeps_all_rows_strings_and_semantics():
    text = json.dumps([{"id": i, "value": None if i == 5 else "a  b" * 90}
                       if i % 2 else {"id": i} for i in range(40)], indent=4)
    result = compress_json(text)
    assert json.loads(result) == json.loads(text)
    assert len(result) < len(text)
    assert len(json.loads(result)) == 40


def test_json_lexemes_duplicates_and_member_order_are_not_reserialized():
    text = ' { "x" : 1.0000000000000000001, "x": -0, "n":1e400, "s":"\\u0061  b", "v":null } '
    assert compress_json(text) == '{"x":1.0000000000000000001,"x":-0,"n":1e400,"s":"\\u0061  b","v":null}'


@pytest.mark.parametrize("text", ['[NaN]', '[Infinity]', '{"x":1,}', '["bad\ttext"]'])
def test_invalid_json_is_passthrough(text):
    assert compress_json(text) == text


@pytest.mark.parametrize("intent", ["conservative", "overview", "navigation"])
def test_prose_literals_fences_and_whitespace_are_exact(intent):
    stash, _ = memory_stash()
    assert compress_prose(PROSE * 100, stash=stash, intent=intent) == PROSE * 100


def test_ml_option_does_not_load_models_or_normalize_literals(monkeypatch):
    class ForbiddenModel:
        def __init__(self, **_):
            pytest.fail("Compression must not download or call a model")

    monkeypatch.setitem(sys.modules, "llmlingua",
                        types.SimpleNamespace(PromptCompressor=ForbiddenModel))
    stash, _ = memory_stash()
    for intent in ("conservative", "overview", "exact"):
        assert compress_prose(PROSE, stash=stash, use_ml=True, intent=intent) == PROSE


@pytest.mark.parametrize("state", ["FAILED test_case", "XPASS test_case", "[ERROR] broken",
                                    "exit code: 7", "Process exited with status 2",
                                    "stderr: invalid input", "[WARN] shaky",
                                    "Traceback (most recent call last):",
                                    "unrecognized final state"])
def test_failing_or_unknown_logs_keep_entire_causal_context(state):
    content = LOG + "causal context\n" * 20 + state + "\n" + LOG
    stash, _ = memory_stash()
    assert compress_logs(content, stash=stash, intent="overview", context=0) == content


def test_json_denied_record_in_middle_remains_visible():
    rows = [{"id": i, "status": "OK"} for i in range(50)]
    rows[25]["status"] = "DENIED"
    stash, _ = memory_stash()
    for intent in ("conservative", "overview"):
        out = compress_json(json.dumps(rows), stash=stash, intent=intent)
        assert "DENIED" in out
        assert json.loads(out) == rows


def test_heterogeneous_json_is_not_claimed_same_shape_or_sampled():
    rows = [{"id": 0}, {"id": "1"}, {"id": None}, {}, ["x"], False, 7]
    stash, _ = memory_stash()
    out = compress_json(json.dumps(rows), stash=stash, intent="overview")
    assert json.loads(out) == rows
    assert "same shape" not in out


def test_default_json_is_exact_even_when_budget_cannot_be_met():
    rows = [{"id": i, "value": "a" * 300} for i in range(20)]
    stash, _ = memory_stash()
    assert json.loads(compress_json(json.dumps(rows), stash=stash, budget=1)) == rows


@pytest.mark.parametrize("compress,content", CASES, ids=["code", "json", "log", "prose"])
def test_direct_router_forwards_protected_intent(compress, content):
    from brainspace.router import route

    hints = {compress_code: "source.py", compress_json: "data.json",
             compress_logs: "build.log", compress_prose: "README.md"}
    stash, stored = memory_stash()
    assert route(content, hints[compress], stash=stash, intent="exact") == content
    assert not stored


def test_router_overview_retains_json_recovery_envelope():
    from brainspace.router import route

    stash, stored = memory_stash()
    view = json.loads(route(JSON, "data.json", stash=stash, intent="overview"))
    assert view["lossy"] is True
    assert stored[view["original"]] == JSON


@pytest.mark.parametrize("compress,content", [(compress_json, JSON), (compress_logs, LOG)],
                         ids=["json", "log"])
def test_full_original_stashes_are_explicitly_root_kind(compress, content):
    calls = []
    stash, _ = memory_stash()

    def record(text, **metadata):
        calls.append((text, metadata))
        return stash(text)

    assert compress(content, stash=record, intent="overview") != content
    assert len(calls) == 1
    assert calls[0][0] == content
    assert calls[0][1].get("kind") == "root"


@pytest.mark.parametrize("compress,content", [(compress_json, JSON), (compress_logs, LOG)],
                         ids=["json", "log"])
def test_real_scoped_ccr_recovers_exact_overview_root(tmp_path, compress, content):
    from brainspace.ccr import CCR, PLACEHOLDER_RE

    # Explicit test database: never use automatic/global storage discovery.
    store = CCR(tmp_path / "test.db")
    view = compress(content, stash=store.stash, intent="overview")
    refs = [match[0] for match in PLACEHOLDER_RE.finditer(view)]
    assert len(refs) == 1
    assert store.retrieve(refs[0]) == content


@pytest.mark.parametrize("state", ["[INFO] UNKNOWN", "[INFO] CANCELLED",
                                   "[INFO] TIMED OUT", "[INFO] ABORTED",
                                   "[INFO] PANIC", "[INFO] UNSUCCESSFUL",
                                   "[INFO] ValueError: missing value",
                                   "[INFO] return code 2", "[INFO] completed with code 3",
                                   "[INFO] runtime state indeterminate",
                                   "[INFO] 2 errors"])
def test_non_success_state_cannot_be_hidden_by_later_success(state):
    text = LOG + state + "\n" + LOG
    stash, stored = memory_stash()
    assert compress_logs(text, stash=stash, intent="overview") == text
    assert not stored


@pytest.mark.parametrize("field,state", [
    ("status", "DENIED"), ("state", "unknown"), ("exit_code", 2),
    ("errors", ["hidden diagnostic"]), ("stderr", "hidden diagnostic"),
])
def test_json_middle_failure_and_unknown_states_bypass(field, state):
    rows = [{"id": i, field: "OK"} for i in range(30)]
    rows[15][field] = state
    text = json.dumps(rows)
    stash, stored = memory_stash()
    assert compress_json(text, intent="overview", stash=stash) == text
    assert not stored


@pytest.mark.parametrize("variant", [
    {"v": None}, {}, {"v": False}, {"v": 1.0}, {"v": [1, 2]},
    {"v": {"nested": 1}}, {"v": 1, "extra": 2},
])
def test_overview_checks_every_record_shape_before_sampling(variant):
    rows = [{"v": 1} for _ in range(30)]
    rows[15] = variant
    text = json.dumps(rows)
    stash, stored = memory_stash()
    assert json.loads(compress_json(text, intent="overview", stash=stash)) == rows
    assert not stored


@pytest.mark.parametrize("lang,module", [("python", "tree_sitter_python"),
                                        ("rust", "tree_sitter_rust")])
def test_missing_grammar_is_passthrough(monkeypatch, lang, module):
    import brainspace.compressors.code_compressor as cc

    real_import = cc.importlib.import_module

    def unavailable(name, *args, **kwargs):
        if name == module:
            raise ImportError("missing grammar")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(cc.importlib, "import_module", unavailable)
    stash, _ = memory_stash()
    assert compress_code(CODE, lang=lang, stash=stash, intent="navigation") == CODE


def test_navigation_references_reconstruct_exact_source_including_decorator_gaps():
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_python")
    text = CODE + "\r\n" + "def longer():\r\n" + "".join(
        f'    value_{i} = "literal  {i}"\r\n' for i in range(50))
    stash, stored = memory_stash()
    out = compress_code(text, stash=stash, intent="navigation")
    assert stored and out != text
    assert '@decorate("a  b")\r\ndef work(x):' in out
    assert '"""Keep  spacing."""' in out
    for ref, body in stored.items():
        out = out.replace(ref, body)
    assert out == text


def test_navigation_partial_storage_failure_returns_entire_original():
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_python")
    text = "def first():\n    return 1\n\ndef second():\n    return 2\n"
    good, stored = memory_stash()

    def flaky(text, **kwargs):
        return None if stored else good(text, **kwargs)

    assert compress_code(text, stash=flaky, intent="navigation") == text


@pytest.mark.parametrize("lang,text", [("python", "def f(:\n    return 1\n"),
                                      ("rust", "fn bad( { let x = ; }")])
def test_navigation_malformed_source_is_passthrough(lang, text):
    stash, _ = memory_stash()
    assert compress_code(text, stash=stash, lang=lang, intent="navigation") == text
