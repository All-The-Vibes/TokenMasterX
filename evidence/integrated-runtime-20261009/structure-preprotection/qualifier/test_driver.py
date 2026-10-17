"""Offline driver-path regressions: every runtime/provider/I/O boundary is mocked."""
import ast
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qualify_ranges as driver
from checks import Script, actions
from test_checks import ANNOTATED_REF


def test_script_root_arguments_match_production_schema_and_dispatch():
    """Read the actual production schema/dispatch AST, never import its runtime."""
    tree = ast.parse((driver.SKILL / "brainspace/runtime.py").read_bytes())
    schema_node = next(n for n in tree.body if isinstance(n, ast.AnnAssign)
                       and isinstance(n.target, ast.Name) and n.target.id == "_RECOVERY_TOOLS")
    tools = ast.literal_eval(schema_node.value)
    root = next(t["function"] for t in tools if t["function"]["name"] == "retrieve_original")
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RuntimeSession")
    exposed = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "recovery_tools")
    assert ast.unparse(exposed.body[-1]) == "return deepcopy(_RECOVERY_TOOLS)"
    recover = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_recover_content")
    guard = next(n for n in recover.body if isinstance(n, ast.If))
    dispatch_keys = ast.literal_eval(guard.test.values[1].comparators[0])
    schema = root["parameters"]
    assert schema["additionalProperties"] is False
    assert dispatch_keys == set(schema["required"]) == set(schema["properties"])

    script = Script(actions(Path("C:/offline/public"), "overview"), "overview")
    script.next({"input": []})
    script.next({"input": [{"type": "function_call_output", "call_id": "overview_partial", "output": "native text"}]})
    call = script.next({"input": [{"type": "function_call_output", "call_id": "overview_partial",
                                  "output": ANNOTATED_REF + "short"}]})
    assert set(call["arguments"]) == dispatch_keys
    assert type(call["arguments"]["offset"]) is int
    assert type(call["arguments"]["ref"]) is str
    page_call = next(n for n in ast.walk(guard) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute) and n.func.attr == "retrieve_page")
    assert len(page_call.args) == 2 and not page_call.keywords
    ccr = ast.parse((driver.SKILL / "brainspace/ccr.py").read_bytes())
    cap = next(n for n in ccr.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "_PAGE_LIMIT" for t in n.targets))
    assert ast.literal_eval(cap.value) == 32768  # server-owned character cap


@pytest.fixture
def offline(monkeypatch):
    root = driver.HERE / "_in_memory_driver_output"
    state = SimpleNamespace(root=root, files={}, saves=[], calls=[], fail_saves={}, runtime_error=None,
                            close_error=None, validation_error=None, validations=0, capture_exists=True,
                            runtime_hook=None)
    state.plan = {
        "root_reference_style": "compact-root-v1",
        "schedule": [{"intent": "overview", "max_calls": 5}, {"intent": "exact", "max_calls": 3}],
        "package": str(root / "package"), "tokenizer_file": str(root / "vocabulary"),
        "resources": {}, "resources_manifest": {"offline": True}, "policy": {}, "policy_id": "offline",
        "workspaces": {intent: {"path": str(root / intent / "workspace")} for intent in ("overview", "exact")},
        "planned_actions": {intent: actions(root / intent / "workspace", intent) for intent in ("overview", "exact")},
        "model": "gpt-6-astra", "prompt": "offline unit test", "native_executable": "not-executed",
        "transport_timeout": 60, "native_timeout": 360,
    }
    state.files[root / "plan.json"] = deepcopy(state.plan)
    real_exists, real_mkdir = Path.exists, Path.mkdir

    def exists(path):
        if path.is_relative_to(root):
            return path in state.files or path.name == "captures.jsonl" and state.capture_exists
        return real_exists(path)

    def mkdir(path, *args, **kwargs):
        if not path.is_relative_to(root):
            return real_mkdir(path, *args, **kwargs)

    def save(path, value):
        state.saves.append(path.name)
        if path.name in state.fail_saves:
            raise state.fail_saves[path.name]
        assert path not in state.files, "exclusive write, never overwrite"
        state.files[path] = deepcopy(value)

    def validate(*_):
        state.validations += 1
        if state.validation_error and state.validations >= 3:
            raise state.validation_error

    class Provider:
        url = "http://offline.invalid"  # Never connected; no socket object exists.

        def __init__(self, *_):
            state.provider = self
            self.requests = [{"body": {"input": []}}]
            self.actions, self.errors = [], []

        def __enter__(self):
            return self

        def __exit__(self, *_):
            if state.close_error:
                raise state.close_error

    class Resources:
        def __init__(self, **_):
            pass

        def to_manifest(self):
            return {"offline": True}

    class Policy:
        @staticmethod
        def from_dict(value):
            return value

    def run_native(**kwargs):
        assert threading.current_thread() is threading.main_thread()
        state.calls.append(kwargs)
        if state.runtime_hook:
            state.runtime_hook()
        if state.runtime_error:
            raise state.runtime_error
        return {"complete": True, "runtime": {"policy_id": "offline"},
                "native_process": {"source_contract": driver.CONTRACT, "stdout": ""}}

    tokens = ModuleType("brainspace.tokens")
    tokens.backend_info = lambda: {"exact_reference": True}
    brainspace = ModuleType("brainspace")
    brainspace.tokens = tokens
    monkeypatch.setitem(sys.modules, "brainspace", brainspace)
    monkeypatch.setitem(sys.modules, "brainspace.tokens", tokens)
    monkeypatch.setenv("BRAINSPACE_TOKENIZER_FILE", "offline-original")
    monkeypatch.setattr(Path, "exists", exists)
    monkeypatch.setattr(Path, "mkdir", mkdir)
    monkeypatch.setattr(driver, "save", save)
    monkeypatch.setattr(driver, "load", lambda p: deepcopy(state.files[p]))
    monkeypatch.setattr(driver, "output_path", lambda _: root)
    monkeypatch.setattr(driver, "validate", validate)
    monkeypatch.setattr(driver, "mock_class", lambda: Provider)
    monkeypatch.setattr(driver, "import_installed", lambda _: (run_native, Policy, Resources))
    monkeypatch.setattr(driver, "rows", lambda p: [{"ok": True, "complete": True}, {"ok": False, "complete": False}]
                        if p.name == "captures.jsonl" else [])
    monkeypatch.setattr(driver, "assess", lambda *_, **__: {"passed": True})
    state.args = SimpleNamespace(output=str(root), execute_reviewed_canned_protocol=True)
    return state


def test_interrupted_attempt_is_not_unattempted_and_keeps_partial_counts(offline):
    original = KeyboardInterrupt("runtime interrupted")
    offline.runtime_error = original
    with pytest.raises(KeyboardInterrupt) as caught:
        driver.run(offline.args)
    assert caught.value is original
    summary = offline.files[offline.root / "summary.json"]
    assert summary["attempted_cells"] == [offline.plan["schedule"][0]]
    assert summary["remaining_unattempted_cells"] == [offline.plan["schedule"][1]]
    cell = summary["results"][0]
    assert cell["attempted"] is True and cell["native_dispatched"] is True
    assert cell["status"] == "interrupted" and cell["passed"] is False
    assert cell["primary_request_count"] == 1
    assert cell["capture_counts"] == {"present": True, "rows": 2, "complete": 1, "accepted": 1}
    assert len(offline.calls) == 1


@pytest.mark.parametrize("failed", ["upstream-requests.json", "driver-failure.json", "checks.json", "summary.json"])
def test_interrupt_wins_over_each_save_failure_and_all_writes_are_attempted(offline, failed):
    original = KeyboardInterrupt("original runtime interrupt")
    offline.runtime_error = original
    offline.fail_saves[failed] = OSError("offline disk failure")
    with pytest.raises(KeyboardInterrupt) as caught:
        driver.run(offline.args)
    assert caught.value is original
    assert {"upstream-requests.json", "upstream-actions.json", "driver-failure.json",
            "checks.json", "summary.json"} <= set(offline.saves)
    assert any(failed in note for note in original.__notes__)
    assert len(offline.calls) == 1
    if failed != "summary.json":
        summary = offline.files[offline.root / "summary.json"]
        assert summary["passed"] is False
        assert summary["results"][0]["reporting_failures"]


def test_persistence_failure_without_runtime_failure_is_not_a_pass_or_next_cell(offline):
    offline.fail_saves["upstream-requests.json"] = OSError("offline disk failure")
    assert driver.run(offline.args) == 1
    summary = offline.files[offline.root / "summary.json"]
    assert summary["passed"] is False
    assert len(offline.calls) == 1
    assert summary["results"][0]["reporting_failures"]
    assert summary["remaining_unattempted_cells"] == [offline.plan["schedule"][1]]


def test_second_run_after_interruption_cannot_dispatch_again(offline):
    offline.runtime_error = KeyboardInterrupt("stop")
    with pytest.raises(KeyboardInterrupt):
        driver.run(offline.args)
    with pytest.raises(ValueError, match="one_shot_run_already_started"):
        driver.run(offline.args)
    assert len(offline.calls) == 1


def test_interrupt_survives_multiple_reporting_failures_and_provider_shutdown_failure(offline):
    original = KeyboardInterrupt("first runtime interrupt")
    offline.runtime_error = original
    offline.close_error = OSError("provider shutdown failed")
    offline.fail_saves = {name: OSError("cannot persist") for name in
                         ("upstream-requests.json", "upstream-actions.json", "driver-failure.json",
                          "checks.json", "summary.json")}
    with pytest.raises(KeyboardInterrupt) as caught:
        driver.run(offline.args)
    assert caught.value is original
    assert set(offline.fail_saves) <= set(offline.saves)
    assert all(any(name in note for note in original.__notes__) for name in offline.fail_saves)
    assert any("setup_cleanup" in note for note in original.__notes__)
    with pytest.raises(ValueError, match="one_shot_run_already_started"):
        driver.run(offline.args)
    assert len(offline.calls) == 1


def test_original_interrupt_wins_over_later_final_validation_interrupt(offline):
    original = KeyboardInterrupt("first")
    offline.runtime_error = original
    offline.validation_error = KeyboardInterrupt("during final validation")
    with pytest.raises(KeyboardInterrupt) as caught:
        driver.run(offline.args)
    assert caught.value is original
    assert any("final_pin_validation_failed" in note for note in original.__notes__)
    assert offline.files[offline.root / "summary.json"]["pins_intact"] is False


def test_later_reporting_interrupt_does_not_replace_original_baseexception(offline):
    original = SystemExit("primary exit")
    offline.runtime_error = original
    offline.fail_saves["upstream-requests.json"] = KeyboardInterrupt("later reporting interrupt")
    with pytest.raises(SystemExit) as caught:
        driver.run(offline.args)
    assert caught.value is original
    assert "summary.json" in offline.saves
    assert any("upstream-requests.json" in note for note in original.__notes__)


def test_missing_capture_file_is_unknown_not_zero_on_interrupt(offline):
    offline.runtime_error = KeyboardInterrupt("stop")
    offline.capture_exists = False
    with pytest.raises(KeyboardInterrupt):
        driver.run(offline.args)
    counts = offline.files[offline.root / "summary.json"]["results"][0]["capture_counts"]
    assert counts == {"present": False, "rows": None, "complete": None, "accepted": None}


def test_success_path_remains_two_main_thread_cells_with_global_eight_call_cap(offline):
    assert driver.run(offline.args) == 0
    assert [call["max_calls"] for call in offline.calls] == [5, 3]
    assert sum(call["max_calls"] for call in offline.calls) == 8
    assert all(call["source_contract"] == driver.CONTRACT for call in offline.calls)
    summary = offline.files[offline.root / "summary.json"]
    assert summary["passed"] is True
    assert summary["remaining_unattempted_cells"] == []
    assert len(summary["attempted_cells"]) == 2


def test_summary_persistence_failure_cannot_return_success_or_restart(offline):
    original = OSError("summary storage failure")
    offline.fail_saves["summary.json"] = original
    with pytest.raises(OSError) as caught:
        driver.run(offline.args)
    assert caught.value is original
    with pytest.raises(ValueError, match="one_shot_run_already_started"):
        driver.run(offline.args)
    assert len(offline.calls) == 2


def test_pre_dispatch_failure_does_not_relabel_a_previous_completed_cell(offline, monkeypatch):
    original = KeyboardInterrupt("stop before exact dispatch")

    def validate(*_):
        offline.validations += 1
        # initial, first pre-dispatch, first post-check, next pre-dispatch
        if offline.validations == 4:
            raise original
    monkeypatch.setattr(driver, "validate", validate)
    with pytest.raises(KeyboardInterrupt) as caught:
        driver.run(offline.args)
    assert caught.value is original
    summary = offline.files[offline.root / "summary.json"]
    assert summary["results"][0]["status"] == "complete"
    assert summary["results"][0]["passed"] is True
    assert summary["remaining_unattempted_cells"] == [offline.plan["schedule"][1]]
    assert len(offline.calls) == 1


def test_delivered_compact_ref_is_reported_but_interrupt_before_lookup_gets_no_credit(offline):
    ref = "[[BR:" + "a" * 64 + "|r=1]]"
    offline.plan["root_reference_style"] = "compact-root-v1"
    offline.plan["policy"] = {"headroom_root_reference_style": "compact-root-v1"}
    offline.files[offline.root / "plan.json"] = deepcopy(offline.plan)

    def see_projection_only():
        offline.provider.action({"input": []})
        offline.provider.action({"input": [{"type": "function_call_output",
                                            "call_id": "overview_partial", "output": "observed native text"}]})
        action = offline.provider.action({"input": [{"type": "function_call_output",
                                                     "call_id": "overview_partial", "output": ref + "\nshort"}]})
        assert action["arguments"] == {"ref": ref, "offset": 0}
    offline.runtime_hook = see_projection_only
    offline.runtime_error = KeyboardInterrupt("no native lookup completed")
    with pytest.raises(KeyboardInterrupt):
        driver.run(offline.args)
    summary = offline.files[offline.root / "summary.json"]
    assert summary["selected_root_reference_style"] == "compact-root-v1"
    assert summary["results"][0]["delivered_root_ref"] == ref
    assert summary["results"][0]["native_root_lookup_verified"] is False
    assert summary["passed"] is False
