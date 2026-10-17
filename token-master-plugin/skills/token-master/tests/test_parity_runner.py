"""Offline controls; fabricated replies are never evidence of model savings."""
import copy
from dataclasses import dataclass
import json
from pathlib import Path
import sys
import subprocess

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
from quality.cases import CASES  # noqa: E402
from quality import runner  # noqa: E402
from quality.responses import Reply, ResponsesTransport  # noqa: E402
from competitors.headroom_container import HeadroomContainer, validate_container, IMAGE_ID  # noqa: E402
from competitors.headroom_worker import diagnostic_rows, parse  # noqa: E402
from run_parity import recount, summarize  # noqa: E402


class Client:
    model = "fixture"
    max_request_bytes = 524288

    def __init__(self, partial=False):
        self.partial = partial

    def request(self, payload):
        return ResponsesTransport("http://127.0.0.1/v1", self.model).request(payload)

    def call(self, payload):
        incoming = json.dumps(self.request(payload))
        if self.partial:
            return Reply(False, "transport_error", input_text=incoming)
        body = {"object": "response", "status": "completed", "model": self.model,
                "usage": {"input_tokens": 12, "output_tokens": 3, "total_tokens": 15},
                "output": [{"type": "function_call", "call_id": "answer-1", "name": "answer",
                            "arguments": json.dumps({"content": {"returns": [10, None, 10],
                                                                "stored": {"x": 10}}})}]}
        return Reply(True, "ok", True, incoming, json.dumps(body), body, 200)


def run(tmp_path, partial=False):
    case = next(item for item in CASES if item.id == "explain_only")
    directory = tmp_path / "run"
    result = runner.run_case(case, runner.Arm("baseline"), directory, Client(partial))
    return result, directory


def test_recount_uses_raw_bodies_and_separates_bridge_usage(tmp_path):
    result, directory = run(tmp_path)
    row = recount(result, directory)
    assert row["primary_reference_tokens"] == result["totals"]["total_tokens"]
    assert row["bridge_reported_tokens"] == 15
    assert row["primary_accounting_complete"] and row["calls"] == 1


def test_partial_primary_remains_unknown(tmp_path):
    result, directory = run(tmp_path, partial=True)
    row = recount(result, directory)
    assert row["calls"] == 1 and row["complete_primary_calls"] == 0
    assert row["primary_reference_tokens"] is row["bridge_reported_tokens"] is None
    assert row["known_primary_reference_tokens"] == 0
    assert not row["primary_accounting_complete"]


def test_removed_capture_is_not_accepted_as_zero(tmp_path):
    result, directory = run(tmp_path)
    (directory / "captures.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="journal"):
        recount(result, directory)


def test_duplicate_trace_records_are_rejected(tmp_path):
    result, directory = run(tmp_path)
    result["trace"]["calls"] *= 2
    with pytest.raises(ValueError, match="inventory"):
        recount(result, directory)


def test_missing_model_run_keeps_planned_totals_unknown(tmp_path):
    result, directory = run(tmp_path)
    row = recount(result, directory) | {
        "case": "case", "arm": "baseline", "correct": True,
        "comparator_complete": True, "all_in_case_seconds": 1,
    }
    summary = summarize([row], [("case", "baseline"), ("case", "headroom")])
    assert not summary["complete"]
    assert summary["by_arm"]["headroom"]["primary_reference_tokens"] is None
    assert summary["missing_task_runs"] == [["case", "headroom"]]


def test_failed_comparator_is_not_a_completed_comparison(tmp_path):
    result, directory = run(tmp_path)
    row = recount(result, directory) | {
        "case": "case", "arm": "headroom", "correct": False,
        "comparator_complete": False, "all_in_case_seconds": 1,
    }
    summary = summarize([row], [("case", "headroom")])
    assert not summary["complete"]
    assert summary["by_arm"]["headroom"]["primary_reference_tokens"] is None


@pytest.mark.parametrize("text", ['{"id":1,"id":2}', '{"value":NaN}', '{"value":Infinity}'])
def test_worker_json_rejects_ambiguous_numbers_or_keys(text):
    with pytest.raises(ValueError):
        parse(text)


def boundary(tmp_path):
    from brainspace.headroom import TASK_ENVIRONMENT, PINNED_BASE_ENVIRONMENT

    mounts = {"/cache": (tmp_path / "cache", False), "/out": (tmp_path / "out", True)}
    value = {
        "Id": "identity", "Image": IMAGE_ID,
        "Config": {"Labels": {"tokenmaster.parity": "fixture"}, "User": "65532:65532",
                   "Entrypoint": ["python"], "Cmd": ["/inputs/worker.py"], "OpenStdin": True,
                   "Volumes": {"/home/nonroot/.headroom": {}},
                   "Env": [key + "=" + value for key, value in
                           {**TASK_ENVIRONMENT, **PINNED_BASE_ENVIRONMENT}.items()]},
        "HostConfig": {
            "NetworkMode": "none", "ReadonlyRootfs": True, "Privileged": False,
            "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges"], "NanoCpus": 2_000_000_000,
            "Memory": 4 * 1024**3, "MemorySwap": 4 * 1024**3, "PidsLimit": 256,
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=256m",
                      "/home/nonroot/.headroom": "rw,noexec,nosuid,nodev,size=64m"},
        },
        "Mounts": [{"Destination": target, "Source": str(path), "RW": writable, "Type": "bind"}
                   for target, (path, writable) in mounts.items()],
    }
    return value, mounts


def test_actual_declared_boundary_is_accepted(tmp_path):
    value, mounts = boundary(tmp_path)
    validate_container(value, identity="identity", label="fixture", mounts=mounts)


@pytest.mark.parametrize("section,key,value", [
    ("HostConfig", "NetworkMode", "bridge"),
    ("HostConfig", "ReadonlyRootfs", False),
    ("HostConfig", "Privileged", True),
    ("HostConfig", "CapDrop", []),
    ("HostConfig", "SecurityOpt", []),
    ("HostConfig", "MemorySwap", -1),
    ("HostConfig", "Tmpfs", {}),
    ("Config", "User", "root"),
    ("Config", "Entrypoint", ["headroom", "proxy"]),
    ("Config", "Cmd", []),
    ("Config", "OpenStdin", False),
    ("Config", "Volumes", {"/unexpected": {}}),
])
def test_boundary_changes_fail_before_start(tmp_path, section, key, value):
    actual, mounts = boundary(tmp_path)
    actual[section][key] = value
    with pytest.raises(ValueError, match="boundary"):
        validate_container(actual, identity="identity", label="fixture", mounts=mounts)


@pytest.mark.parametrize("change", ["writable_cache", "foreign_source", "extra_volume", "foreign_id"])
def test_ownership_and_mount_changes_reject(tmp_path, change):
    actual, mounts = boundary(tmp_path)
    if change == "writable_cache":
        actual["Mounts"][0]["RW"] = True
    elif change == "foreign_source":
        actual["Mounts"][0]["Source"] = str(tmp_path / "unrelated")
    elif change == "extra_volume":
        actual["Mounts"].append(copy.deepcopy(actual["Mounts"][0]))
    else:
        actual["Id"] = "foreign"
    with pytest.raises(ValueError):
        validate_container(actual, identity="identity", label="fixture", mounts=mounts)


def test_upstream_inflation_reversion_without_diagnostics_is_valid():
    assert diagnostic_rows(None) == []
    assert diagnostic_rows([]) == []

    @dataclass
    class Decision:
        action: str

    assert diagnostic_rows([Decision("protected")]) == [{"action": "protected"}]


def test_inspection_timeout_still_reaps_own_attach_client(tmp_path):
    calls = []

    class Process:
        returncode = None
        stdin = None

        def wait(self, timeout):
            calls.append(("wait", timeout))
            if self.returncode is None:
                raise subprocess.TimeoutExpired("owned attach", timeout)
            return self.returncode

        def terminate(self):
            calls.append(("terminate",))
            self.returncode = -15

        def kill(self):
            calls.append(("kill",))
            self.returncode = -9

        def poll(self):
            return self.returncode

    worker = HeadroomContainer.__new__(HeadroomContainer)
    worker.directory = tmp_path
    worker.identity = "owned-container"
    worker.finished = False
    worker.failed = True
    worker.started = 0
    worker.process = Process()
    worker.stderr = None
    worker.worker_snapshot = None
    worker.command = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        subprocess.TimeoutExpired("docker inspect", 30))
    with pytest.raises(subprocess.TimeoutExpired):
        worker.close()
    receipt = json.loads((tmp_path / "cleanup.json").read_text())
    assert receipt["container_state"] == "unknown"
    assert receipt["attach_client_reaped"] is True
    assert ("terminate",) in calls
    assert not receipt.get("container_removed", False)
