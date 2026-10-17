from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from threading import Thread

import pytest

EVALS = Path(__file__).resolve().parents[3] / "evals"
sys.path.insert(0, str(EVALS))
from brainspace import tokens  # noqa: E402
from refinement.cases import generate_cases  # noqa: E402
from refinement.core import wire  # noqa: E402
from run_refinement import StudyBudget, freeze  # noqa: E402


def test_budget_stops_unknown_usage_and_counts_completed_overrun():
    budget = StudyBudget(4, 60, 100)
    assert budget.reserve(20, 30) > 0
    budget.observe({"measurement": {"reference_total": 110}})
    assert budget.snapshot()["reference_stop_threshold_exceeded"] is True
    assert budget.reference_known == 110
    assert budget.reserve(1, 30) == 0
    budget = StudyBudget(4, 60, 100)
    assert budget.reserve(1, 30) > 0
    budget.observe({"measurement": {"reference_total": None}})
    assert budget.reserve(1, 30) == 0
    assert budget.incomplete == 1


def test_budget_never_starts_extra_calls():
    budget = StudyBudget(1, 60, 100)
    assert budget.reserve(10, 30) > 0
    assert budget.reserve(10, 30) == 0
    assert budget.attempts == 1


def test_rate_limit_stops_study_without_retry_or_provider_switch():
    budget = StudyBudget(114, 1200, 500000)
    assert budget.reserve(10, 30) > 0
    budget.observe({"http_status": 429, "measurement": {"reference_total": 20}})
    assert budget.reserve(10, 30) == 0
    assert budget.snapshot()["halt_reason"] == "rate_limited"


def test_freeze_hashes_canonical_transport_required_by_responses_shim(tmp_path):
    output = tmp_path / "frozen"
    freeze(output)
    relative = "skills/token-master/brainspace/transport.py"
    manifest = json.loads((output / "source-manifest.json").read_text(encoding="utf-8"))
    assert relative in manifest
    original = (EVALS.parent / relative).read_bytes()
    frozen = (output / "source/token-master-plugin" / relative).read_bytes()
    assert frozen == original
    assert manifest[relative] == hashlib.sha256(original).hexdigest()


def test_copied_freeze_imports_canonical_transport_without_checkout(tmp_path):
    output = tmp_path / "frozen"
    freeze(output)
    copied = tmp_path / "relocated"
    shutil.copytree(output, copied)
    root = copied / "source/token-master-plugin"
    probe = r'''
import json, sys
from pathlib import Path
def deny_external(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
        raise AssertionError("import probe attempted external execution")
sys.addaudithook(deny_external)
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "skills/token-master"))
sys.path.insert(0, str(root / "evals"))
import quality.responses as shim
import brainspace.transport as canonical
import refinement.core as core
import refinement.audit
import refinement.messages
import run_refinement
assert shim is canonical
assert shim.Reply is canonical.Reply and core.ResponsesTransport is canonical.ResponsesTransport
assert Path(canonical.__file__).resolve() == root / "skills/token-master/brainspace/transport.py"
for module in (core, refinement.audit, refinement.messages, run_refinement):
    assert Path(module.__file__).resolve().is_relative_to(root)
for api in ("responses", "messages"):
    client = core.make_client("http://127.0.0.1:1/v1", "offline-fixture", api, allow_network=False)
    reply = client.call({"input":[{"role":"user","content":"Offline import probe."}]})
    assert type(reply) is canonical.Reply and reply.reason == "network_not_allowed"
print(json.dumps({"canonical_transport": True, "relocated_imports": True, "provider_calls": 0}))
'''
    env = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "PATHEXT")
           if key in os.environ}
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", probe, str(root)], cwd=tmp_path,
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "canonical_transport": True, "relocated_imports": True, "provider_calls": 0}
    assert not (copied / "manifest.json").exists()


def cli(output, *extra):
    env = dict(os.environ)
    env["BRAINSPACE_TOKENIZER_FILE"] = str(tokens._vocabulary_path())
    return subprocess.run(
        [sys.executable, str(EVALS / "run_refinement.py"), "--output", str(output),
         "--primary", "model-A", "--secondary", "model-B", "--tasks", "4",
         "--secondary-api", "responses",
         "--seed", "19", "--max-total-calls", "58", *extra],
        capture_output=True, text=True, encoding="utf-8", timeout=240, env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def test_actual_cli_is_offline_by_default_and_never_overwrites(tmp_path):
    output = tmp_path / "prepared"
    process = cli(output)
    assert process.returncode == 0, process.stdout + process.stderr
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["network_opt_in"] is False
    assert manifest["maximum_attempts"] == 58
    assert not (output / "preflight").exists()
    assert len(manifest["schedule"]) == 20
    assert json.loads((output / "status.json").read_text()) == {"status": "prepared_only", "attempts": 0}
    rerun = cli(output)
    assert rerun.returncode != 0
    assert "must be new" in rerun.stderr


def test_relative_output_is_resolved_before_frozen_child_changes_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    process = cli(Path("relative-study"))
    assert process.returncode == 0, process.stdout + process.stderr
    assert json.loads((tmp_path / "relative-study" / "status.json").read_text())["status"] == "prepared_only"


class MockBridge(BaseHTTPRequestHandler):
    requests = []
    native_alias = None
    gold = {case.prompt: case.expected for case in generate_cases(19, 4)}

    def log_message(self, *_):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append((self.path, dict(self.headers), request))
        native_messages = self.path == "/v1/messages"
        text = request["messages" if native_messages else "input"][0]["content"]
        instructions = request.get("system" if native_messages else "instructions", "")
        if text.startswith("Return exactly READY"):
            result = "READY"
        elif '"critique":' in instructions:
            result = wire({"critique": "The provided answer passes the synthetic check."})
        else:
            context = json.loads(text)
            result = wire({"answer": self.gold[context["problem"]], "explanation": "Synthetic derivation."})
        body = {
            "object": "response", "status": "completed", "model": request["model"],
            "output": [{"type": "message", "role": "assistant", "content": [
                {"type": "output_text", "text": result}]}],
            "usage": {"input_tokens": 5, "output_tokens": 4, "total_tokens": 9},
        }
        if native_messages:
            body = {
                "type": "message", "role": "assistant", "model": self.native_alias or request["model"],
                "id": f"native-messages-{len(self.requests)}", "stop_reason": "end_turn",
                "content": [{"type": "text", "text": result}],
                "usage": {"input_tokens": 5, "output_tokens": 4,
                          "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            }
        self.send_response(200)
        self.end_headers()
        self.wfile.write(wire(body).encode("utf-8"))


@pytest.fixture
def mock_bridge():
    MockBridge.requests = []
    MockBridge.native_alias = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockBridge)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_actual_frozen_cli_all_arms_transport_accounting_and_no_credentials(tmp_path, mock_bridge):
    output = tmp_path / "live-mock"
    process = cli(output, "--allow-network", "--base-url", mock_bridge)
    assert process.returncode == 0, process.stdout + process.stderr
    assert len(MockBridge.requests) == 58
    for path, headers, body in MockBridge.requests:
        assert path == "/v1/responses"
        assert not any(key.lower() in {"authorization", "x-api-key"} for key in headers)
        assert body["store"] is False
        assert not ({"tools", "previous_response_id", "conversation"} & body.keys())
    report = json.loads((output / "audit.json").read_text())
    assert report["audit_status"] == "consistent"
    assert report["population_certificate"] is False
    assert len(report["by_arm"]) == 5
    assert all(row["tasks"] == row["correct"] == 4 for row in report["by_arm"].values())
    assert sum(row["calls"] for row in report["by_arm"].values()) == 56
    assert sum(row["bridge_reported_tokens"] for row in report["by_arm"].values()) == 56 * 9
    env = dict(os.environ, BRAINSPACE_TOKENIZER_FILE=str(output / "cl100k_base.tiktoken"))
    offline = subprocess.run(
        [sys.executable, str(output / "source/token-master-plugin/evals/run_refinement.py"),
         "--output", str(output), "--audit-only"],
        capture_output=True, text=True, encoding="utf-8", timeout=30, env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert offline.returncode == 0, offline.stdout + offline.stderr
    assert json.loads(offline.stdout)["audit_status"] == "consistent"
    assert len(MockBridge.requests) == 58  # offline audit did not generate anything


def test_actual_frozen_mixed_api_subset_and_native_usage(tmp_path, mock_bridge):
    output = tmp_path / "mixed-api"
    MockBridge.native_alias = "native-model-B"
    process = cli(output, "--allow-network", "--base-url", mock_bridge,
                  "--secondary-api", "messages", "--secondary-reported-model", "native-model-B", "--arms",
                  "single_primary", "single_secondary", "cross_refine")
    assert process.returncode == 0, process.stdout + process.stderr
    assert len(MockBridge.requests) == 26
    assert sum(path == "/v1/messages" for path, _, _ in MockBridge.requests) == 9
    for path, headers, body in MockBridge.requests:
        headers = {key.lower(): value for key, value in headers.items()}
        if path == "/v1/messages":
            assert headers.get("anthropic-version") == "2023-06-01"
            assert body["output_config"] == {"effort": "low"}
            assert "input" not in body and "tools" not in body
        assert "authorization" not in headers and "x-api-key" not in headers
    report = json.loads((output / "audit.json").read_text())
    assert report["audit_status"] == "consistent"
    assert set(report["by_arm"]) == {"single_primary", "single_secondary", "cross_refine"}
    assert all(row["correct"] == row["tasks"] == 4 for row in report["by_arm"].values())
    assert report["all_in"]["calls"] == 26
    assert report["all_in"]["bridge_reported_tokens"] == 26 * 9
