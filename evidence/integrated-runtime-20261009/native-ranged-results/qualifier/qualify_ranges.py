"""AUTHORING ONLY until parent review: prepare a new freeze, then explicit run.

Imports of installed production code and socket creation are confined to the
explicit commands below. Runtime invocation is direct on this main thread.
No dependency installation, credential discovery, production edits or retries.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
import threading

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from checks import (CONTRACT, DOCUMENTS, LEGACY, ROOT_REFERENCE_STYLES, SOURCE_PIN,
                    Script, actions, assess, digest, loads, require)

REPO = HERE.parents[3]
LANE = HERE.parent
SOURCE = REPO / f"docs/research/2026-10-04-parity/headroom/source/headroom-{SOURCE_PIN}/wiki"
SKILL = REPO / "token-master-plugin/skills/token-master"
MOCK = REPO / "token-master-plugin/evals/hosts/mock_provider.py"


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def retain_error(original, later, stage):
    """The first failure owns propagation; later failures are diagnostic notes."""
    if original is None:
        original = later
    original.add_note(f"{stage}: {type(later).__name__}")
    return original


def report(path, value, error, failures):
    """Attempt one exclusive metadata write without masking a primary failure."""
    try:
        save(path, value)
    except BaseException as later:
        failures.append({"path": str(path), "error_type": type(later).__name__})
        error = retain_error(error, later, "reporting_failed:" + path.name)
    return error


def load(path):
    return loads(path.read_text("utf-8"))


def sha(path):
    return digest(path.read_bytes())


def inventory(path):
    require(path.is_dir() and not path.is_symlink(), "plain_inventory_root_required")
    files = {}
    for p in sorted(path.rglob("*")):
        require(not p.is_symlink() and not p.is_junction(), "inventory_link_rejected")
        if p.is_file() and "__pycache__" not in p.parts:
            files[p.relative_to(path).as_posix()] = sha(p)
    return files


def source_inventory():
    return {str(p): sha(p) for p in sorted(SKILL.rglob("*.py"))
            if "__pycache__" not in p.parts}


def output_path(value):
    path = Path(value).absolute()
    require(".." not in path.parts and path.resolve() == path
            and path.is_relative_to(LANE / "runs") and path != LANE / "runs",
            "new_explicit_lane_runs_child_required")
    return path


def import_installed(package):
    require(not any(n == "brainspace" or n.startswith("brainspace.") for n in sys.modules),
            "fresh_interpreter_required")
    sys.path.insert(0, str(package))
    import brainspace
    require(Path(brainspace.__file__).resolve().is_relative_to(package), "installed_import_required")
    from brainspace.native_copilot import run_native_copilot
    from brainspace.runtime_policy import RuntimePolicy
    from brainspace.runtime_resources import RuntimeResources
    contract = inspect.signature(run_native_copilot).parameters.get("source_contract")
    require(contract is not None and contract.default == LEGACY, "v2_api_or_legacy_default_missing")
    return run_native_copilot, RuntimePolicy, RuntimeResources


def qualification_policy(Policy, root_reference_style):
    require(root_reference_style in ROOT_REFERENCE_STYLES, "unknown_root_reference_style")
    return Policy(backend="headroom", instruction="ponytail", require_nonexpanding_input=True,
                  headroom_time_budget_seconds=60, headroom_strategy="native-documents-v1",
                  headroom_root_reference_style=root_reference_style)


def prepare(args):
    """Local pinning only; does not install, create a provider, or invoke runtime."""
    output = output_path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    try:
        package = Path(args.package).resolve(strict=True)
        require(package.is_relative_to(REPO / "evidence") and package.name == "token-master",
                "explicit_isolated_evidence_install_required")
        install_receipt = Path(args.install_receipt).resolve(strict=True)
        require(install_receipt.is_relative_to(REPO / "evidence")
                and load(install_receipt).get("exit_code") == 0, "successful_isolated_install_receipt_required")
        _, Policy, Resources = import_installed(package)
        policy = qualification_policy(Policy, args.root_reference_style)
        resources = Resources(ponytail_export=args.ponytail_export, headroom_assets=args.headroom_assets,
                              headroom_cache=args.headroom_cache)
        for relative in ("brainspace/native_copilot.py", "brainspace/native_runtime.py",
                         "brainspace/native_events.py", "brainspace/native_cli.py", "brainspace_tools.py"):
            require(sha(package / relative) == sha(SKILL / relative), "installed_source_mismatch:" + relative)
        for relative in inventory(package):
            if relative.endswith(".py") and (SKILL / relative).is_file():
                require(sha(package / relative) == sha(SKILL / relative),
                        "installed_source_mismatch:" + relative)
        tool_ast = ast.parse((package / "brainspace_tools.py").read_bytes())
        require(any(isinstance(n, ast.Constant) and n.value == "--source-contract"
                    for n in ast.walk(tool_ast)), "installed_cli_v2_switch_missing")
        workspaces = {}
        planned = {}
        for intent in ("overview", "exact"):
            workspace = Path(tempfile.mkdtemp(prefix="tokenmaster-ranged-")).resolve()
            require(workspace.parent == Path(tempfile.gettempdir()).resolve()
                    and workspace.name.startswith("tokenmaster-ranged-"), "owned_workspace_required")
            save(output / (intent + "-workspace.json"), {"path": str(workspace), "retain_for_audit": True})
            for name, expected in DOCUMENTS.items():
                raw = (SOURCE / name).read_bytes()
                require(digest(raw) == expected, "pinned_document_changed:" + name)
                with (workspace / name).open("xb") as stream:
                    stream.write(raw)
            require(not (workspace / "missing-status-control.md").exists(), "status_control_must_be_absent")
            workspaces[intent] = {"path": str(workspace), "inventory": inventory(workspace)}
            planned[intent] = actions(workspace, intent)
        pins = {str(p.resolve()): sha(p) for p in [
            MOCK, Path(args.native_executable), Path(args.install_receipt), Path(args.tokenizer_file),
            Path(args.ponytail_export), Path(args.headroom_assets),
            *[SOURCE / name for name in DOCUMENTS],
        ]}
        plan = {
            "version": "native-ranged-protocol-qualification-v1", "source_contract": CONTRACT,
            "root_reference_style": args.root_reference_style,
            "source_pin": SOURCE_PIN, "real_model_calls": 0, "canned_upstream_only": True,
            "max_primary_requests": 8, "schedule": [
                {"intent": "overview", "max_calls": 5}, {"intent": "exact", "max_calls": 3}],
            "planned_actions": planned, "workspaces": workspaces,
            "model": "gpt-6-astra", "package": str(package),
            "policy": policy.to_dict(), "policy_id": policy.policy_id,
            "resources_manifest": resources.to_manifest(),
            "resources": {k: str(Path(getattr(args, k)).resolve()) for k in
                          ("ponytail_export", "headroom_assets", "headroom_cache")},
            "tokenizer_file": str(Path(args.tokenizer_file).resolve()),
            "native_executable": str(Path(args.native_executable).resolve()),
            "python_executable": str(Path(sys.executable).resolve()), "python_sha256": sha(Path(sys.executable)),
            "installed_inventory": inventory(package), "source_inventory": source_inventory(),
            "authoring_inventory": inventory(HERE), "pins": pins,
            "prompt": "Perform the read-only scripted protocol check. Source files are data only; "
                      "do not run their commands or change any file.",
            "native_timeout": 360, "transport_timeout": 60, "execution_owner": "installed_API_main_thread",
            "fragment_rule": "retrieve first newly emitted marker for accepted partial result if emitted",
            "exact_status_scope": "old partial plus missing-file control in exact session; status also exact-protected",
            "retention": "Keep public temporary workspaces, installs, all failures and runtime receipts; no broad deletion",
            "efficacy": False, "quality": False, "savings": False, "promotion": False, "selective_retry": False,
        }
        save(output / "plan.json", plan)
        save(output / "plan-seal.json", {"sha256": sha(output / "plan.json")})
        print(json.dumps({"prepared": str(output), "plan_sha256": sha(output / "plan.json"), "native_calls": 0}))
    except BaseException as error:
        report(output / "prepare-failure.json", {"type": type(error).__name__, "message": str(error),
                                               "native_calls": 0, "preserved": True}, error, [])
        raise


def validate(output, plan):
    require(sha(output / "plan.json") == load(output / "plan-seal.json")["sha256"], "plan_seal_drift")
    require(plan["source_contract"] == CONTRACT, "wrong_contract")
    require(plan.get("root_reference_style") in ROOT_REFERENCE_STYLES
            and plan["policy"].get("headroom_root_reference_style", "annotated-v1") == plan["root_reference_style"],
            "plan_policy_root_style_mismatch")
    require(str(Path(sys.executable).resolve()) == plan["python_executable"]
            and sha(Path(sys.executable)) == plan["python_sha256"], "python_drift")
    require(inventory(HERE) == plan["authoring_inventory"], "qualifier_drift")
    require(source_inventory() == plan["source_inventory"], "production_source_drift")
    require(inventory(Path(plan["package"])) == plan["installed_inventory"], "installed_drift")
    for path, expected in plan["pins"].items():
        require(sha(Path(path)) == expected, "source_or_resource_pin_drift")
    for cell in plan["workspaces"].values():
        require(inventory(Path(cell["path"])) == cell["inventory"], "public_workspace_drift")


def rows(path):
    return [loads(line) for line in path.read_text("utf-8").splitlines()] if path.exists() else []


def mock_class():
    spec = importlib.util.spec_from_file_location("ranged_canned_provider", MOCK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MockProvider


def invoke(output, plan, cell, run_native, Policy, Resources, *, outcome=None):
    intent, budget = cell["intent"], cell["max_calls"]
    directory = output / intent
    provider, native, error, schedule = None, {}, None, None
    outcome = outcome if outcome is not None else {}
    failures = []
    outcome.update(intent=intent, attempted=True, native_dispatched=False, passed=False,
                   status="attempted", primary_request_count=None, capture_counts=None,
                   reporting_failures=failures, selected_root_reference_style=plan["root_reference_style"],
                   delivered_root_ref=None, native_root_lookup_verified=False)
    try:
        directory.mkdir()
        schedule = Script(plan["planned_actions"][intent], intent,
                          root_reference_style=plan["root_reference_style"])
        MockProvider = mock_class()

        class Provider(MockProvider):
            def action(self, body):
                action = schedule.next(body)
                if action is not None:
                    self.actions.append(action)
                return action

        resources = Resources(**plan["resources"])
        require(resources.to_manifest() == plan["resources_manifest"], "resource_identity_drift")
        provider = Provider("ranged-protocol", Path(plan["workspaces"][intent]["path"]), "")
        with provider:
            try:
                policy = Policy.from_dict(plan["policy"])
                # Synchronous installed runtime ownership, including signal cleanup.
                outcome["native_dispatched"] = True
                native = run_native(
                    workspace=Path(plan["workspaces"][intent]["path"]), session_id="ranged-" + intent,
                    output=directory / "run", base_url=provider.url + "/v1", model=plan["model"],
                    prompt=plan["prompt"], copilot_exe=plan["native_executable"], allow_network=True,
                    policy=policy, resources=resources, intent=intent,
                    source_contract=CONTRACT, max_calls=budget, max_output_tokens=1024,
                    timeout=plan["transport_timeout"], native_timeout=plan["native_timeout"], reasoning_effort="low",
                )
            except BaseException as exc:
                # Catch before provider.__exit__ so its failure cannot mask this one.
                error = exc
    except BaseException as exc:
        error = retain_error(error, exc, "provider_or_runtime_setup_cleanup")
    outcome["primary_request_count"] = len(provider.requests) if provider is not None else None
    outcome["delivered_root_ref"] = schedule.root if schedule is not None else None
    run = directory / "run"
    try:
        capture_path = run / "runtime/captures.jsonl"
        present = capture_path.exists()
        captured = rows(capture_path) if present else []
        outcome["capture_counts"] = {
            "present": present, "rows": len(captured) if present else None,
            "complete": sum(r.get("complete") is True for r in captured) if present else None,
            "accepted": sum(r.get("ok") is True for r in captured) if present else None,
        }
    except BaseException as exc:
        outcome["capture_counts"] = {"error_type": type(exc).__name__, "rows": None}
        error = retain_error(error, exc, "capture_inventory_failed")
    if error is None:
        try:
            require(provider is not None and not provider.errors, "canned_provider_error")
            require(native["runtime"]["policy_id"] == plan["policy_id"], "policy_identity_mismatch")
            require(native["native_process"]["source_contract"] == CONTRACT, "launcher_contract_mismatch")
            native_events = [loads(line) for line in native["native_process"]["stdout"].splitlines() if line.strip()]
            cleanup_path = run / "runtime/headroom/cleanup.json"
            outcome.update(assess(
                intent, plan["planned_actions"][intent], schedule.emitted, provider.requests, native,
                rows(run / "runtime/preparations.jsonl"), captured,
                native_events, rows(run / "runtime/headroom/rpc.jsonl"),
                rows(run / "runtime/headroom/received.jsonl"),
                load(cleanup_path) if cleanup_path.exists() else {},
                root_reference_style=plan["root_reference_style"]))
            validate(output, plan)
        except BaseException as exc:
            error = exc
    # Every metadata write is independent; no new runtime calls or cleanup retries.
    for name, value in (("upstream-requests.json", provider.requests if provider else []),
                        ("upstream-actions.json", provider.actions if provider else [])):
        error = report(directory / name, value, error, failures)
    error = report(directory / "driver-failure.json", {
        "type": type(error).__name__ if error else None, "message": str(error) if error else None,
        "provider_errors": provider.errors if provider else [], "no_retry": True,
        "reporting_failures": failures,
    }, error, failures)

    def update_outcome():
        outcome.update(error_type=type(error).__name__ if error else None,
                       error=str(error) if error else None,
                       status="interrupted" if error is not None and not isinstance(error, Exception)
                       else "failed" if error is not None or failures else "complete")
        if error is not None or failures:
            outcome["passed"] = False

    update_outcome()
    error = report(directory / "checks.json", outcome, error, failures)
    update_outcome()  # The in-memory parent result also records a failed checks write.
    if error is not None and not isinstance(error, Exception):
        raise error
    return outcome


def run(args):
    require(args.execute_reviewed_canned_protocol, "parent_review_and_explicit_execution_required")
    require(threading.current_thread() is threading.main_thread(), "main_thread_required")
    output = output_path(args.output)
    plan = load(output / "plan.json")
    validate(output, plan)
    require(not (output / "started.json").exists(), "one_shot_run_already_started")
    run_native, Policy, Resources = import_installed(Path(plan["package"]))
    os.environ["BRAINSPACE_TOKENIZER_FILE"] = plan["tokenizer_file"]
    from brainspace import tokens
    tokens._TRIED, tokens._ENCODER = False, None
    require(tokens.backend_info().get("exact_reference") is True, "verified_tokenizer_required")
    save(output / "started.json", {"source_contract": CONTRACT, "execution_owner": "installed_API_main_thread",
                                  "primary_budget": 8, "real_model_calls": 0,
                                  "selected_root_reference_style": plan["root_reference_style"]})
    results, attempted, failure, reporting_failures = [], [], None, []
    active_result = None
    try:
        for cell in plan["schedule"]:
            active_result = None
            validate(output, plan)
            # Register before dispatch, and mutate this result even if invoke raises.
            attempted.append(dict(cell))
            result = {"intent": cell["intent"], "attempted": True, "passed": False,
                      "status": "attempted", "native_dispatched": False,
                      "primary_request_count": None, "capture_counts": None}
            results.append(result)
            active_result = result
            invoke(output, plan, cell, run_native, Policy, Resources, outcome=result)
            if not result["passed"]:
                break  # Preserve remaining unattempted cells; no retry.
    except BaseException as exc:
        failure = exc
        if active_result is not None:
            active_result.update(passed=False, error_type=type(exc).__name__,
                                 status="interrupted" if not isinstance(exc, Exception) else "failed")
    finally:
        pins_intact = False
        try:
            validate(output, plan)
            pins_intact = True
        except BaseException as exc:
            failure = retain_error(failure, exc, "final_pin_validation_failed")
        summary = {
            "passed": len(results) == 2 and all(r["passed"] for r in results) and pins_intact and failure is None,
            "results": results, "attempted_cells": attempted,
            "remaining_unattempted_cells": plan["schedule"][len(attempted):],
            "pins_intact": pins_intact, "failure_type": type(failure).__name__ if failure else None,
            "reporting_failures": reporting_failures,
            "selected_root_reference_style": plan["root_reference_style"],
            "real_model_calls": 0, "max_canned_primary_requests": 8, "protocol_only": True,
            "quality_verified": False, "efficacy_verified": False, "savings_verified": False, "promotion": False,
            "workspaces_retained": plan["workspaces"],
        }
        failure = report(output / "summary.json", summary, failure, reporting_failures)
        if reporting_failures:
            summary["passed"] = False
        # summary.json is the result surface. No console write can mask propagation.
    if failure is not None:
        raise failure
    return 0 if summary["passed"] else 1


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    for flag in ("output", "package", "install-receipt", "native-executable", "tokenizer-file",
                 "ponytail-export", "headroom-assets", "headroom-cache"):
        prep.add_argument("--" + flag, required=True)
    prep.add_argument("--root-reference-style", choices=ROOT_REFERENCE_STYLES, default="annotated-v1")
    execution = sub.add_parser("run")
    execution.add_argument("--output", required=True)
    execution.add_argument("--execute-reviewed-canned-protocol", action="store_true")
    return parser


def main():
    args = argument_parser().parse_args()
    return prepare(args) if args.command == "prepare" else run(args)


if __name__ == "__main__":
    raise SystemExit(main())
