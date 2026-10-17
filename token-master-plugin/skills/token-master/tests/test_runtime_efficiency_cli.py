"""Real CLI/host/runtime seam over a local fake HTTP peer, not model-quality evidence."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

import pytest

from brainspace import tokens
from brainspace.jev import Diagnostics, JevClient, Result
from brainspace.optimizer import Optimizer, OptimizerError
import token_efficiency as cli


pytestmark = pytest.mark.skipif(
    not tokens.backend_info()["exact_reference"], reason="verified local tokenizer required")


@pytest.fixture
def peer():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            has_read = any(item.get("type") == "function_call_output" for item in body["input"])
            reply = {"object": "response", "model": body["model"], "status": "completed",
                     "output": [{
                         "type": "function_call", "call_id": f"call_{len(requests):05}",
                         "name": "answer" if has_read else "read_file",
                         "arguments": json.dumps({"content": '{"value":7}'} if has_read
                                                 else {"path": "note.txt"}),
                     }], "usage": {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30}}
            data = json.dumps(reply, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def task_arguments(initial):
    return [value for task in initial["task_ids"] for value in ("--task-id", task)]


def setup(tmp_path, peer, *, feasible=False, planned_rounds=1):
    # Positive seam tests use the necessary arithmetic floor, not an exemption
    # from production preflight. These distinct fake-peer fixtures are NOT IID
    # sampling, real quality evidence, or permission to alter an existing DB.
    from brainspace.plan_feasibility import fixed_plan_feasibility
    count = fixed_plan_feasibility(
        alpha=.05, round_index=planned_rounds, sample_size=1, token_cap=50000,
        minimum_token_reduction=1)["minimum_samples"] if feasible else 1
    assert type(count) is int and count >= 1
    manifest = tmp_path / "tasks.json"
    manifest.write_text(json.dumps({"schema_version": 1, "tasks": [{
        "prompt": ("Read note.txt and return the numeric value in a JSON object."
                   + (f" Offline seam case {i}." if feasible else "")),
        "files": {"note.txt": "The numeric value is 7. Résumé is preserved.\n"},
        "expected": {"value": 7}, "intent": "exact",
    } for i in range(count)]}), encoding="utf-8")
    common = ["--manifest", str(manifest), "--base-url", peer[0], "--model", "test-fixed-model",
              "--allow-network", "--max-calls-per-arm", "4", "--max-tool-calls", "4",
              "--max-output-tokens", "256", "--token-cap", "50000",
              "--max-search-calls", str(max(32, planned_rounds * count * 8 + 1))]
    return tmp_path / "controller.sqlite", manifest, common


def execute(db, command, output, common, *extra):
    args = cli._parser().parse_args(
        ["--db", str(db), command, "--output", str(output), *common, *extra])
    return cli.execute(args)


def test_real_cli_initialization_pair_and_single_use_tasks(tmp_path, peer):
    db, _, common = setup(tmp_path, peer, feasible=True, planned_rounds=2)
    initial = execute(db, "initialize-runtime", tmp_path / "init", common)
    assert not peer[1]
    assert initial["baseline_admission"] == "deterministic_safety_only_not_model_quality"
    assert initial["status"]["learning"]["complete_calls"] == 0
    assert initial["synthetic_only"] is False
    count = len(initial["task_ids"])
    result = execute(db, "learn-runtime", tmp_path / "trial", common, *task_arguments(initial))
    assert len(peer[1]) == 4 * count
    assert result["plan_feasibility"]["arithmetic"]["status"] == "not_ruled_out"
    assert result["policy_promoted"] is False
    assert result["not_optimizer_off_baseline"] is True
    assert result["step"]["status"] == "not_certified"
    assert result["status"]["champion"] == initial["status"]["champion"]
    assert result["status"]["learning"]["complete_calls"] == 4 * count
    assert result["status"]["learning"]["coverage"] == "complete"
    observation = json.loads(next((tmp_path / "trial").rglob("observation.json")).read_text("utf-8"))
    assert observation["candidate_outcome"]["success"]
    assert observation["incumbent_outcome"]["success"]
    assert (tmp_path / "trial/controller-status.json").is_file()
    # The private gold is not serialized into any request or prepared workspace.
    for arm in ("incumbent", "candidate"):
        workspace = next((tmp_path / "trial").glob(f"task-*/{arm}/workspace"))
        assert {p.name for p in workspace.iterdir()} == {"note.txt"}
    with pytest.raises(OptimizerError, match="^task_already_consumed$"):
        execute(db, "learn-runtime", tmp_path / "replay", common, *task_arguments(initial))
    assert len(peer[1]) == 4 * count
    assert not (tmp_path / "replay").exists()


def test_cli_refuses_missing_authority_before_registry_or_output(tmp_path, peer):
    db, _, common = setup(tmp_path, peer)
    common.remove("--allow-network")
    with pytest.raises(OptimizerError, match="runtime_network_opt_in_required"):
        execute(db, "initialize-runtime", tmp_path / "init", common)
    assert not db.exists() and not (tmp_path / "init").exists() and not peer[1]


@pytest.mark.parametrize("change", ["model", "gold", "duplicate", "unknown", "missing_key"])
def test_cli_rejects_regime_task_or_credential_mismatch_before_calls(tmp_path, peer, monkeypatch, change):
    db, manifest, common = setup(tmp_path, peer, feasible=change == "missing_key")
    initial = execute(db, "initialize-runtime", tmp_path / "init", common)
    extra = ["--task-id", initial["task_ids"][0]]
    if change == "model":
        common[common.index("--model") + 1] = "other-model"
    elif change == "gold":
        data = json.loads(manifest.read_text("utf-8"))
        data["tasks"][0]["expected"] = {"value": 8}
        manifest.write_text(json.dumps(data), encoding="utf-8")
    elif change == "duplicate":
        extra *= 2
    elif change == "unknown":
        extra[-1] = "readonly:unknown"
    else:
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        extra = [*task_arguments(initial), "--jev"]
    expected = {
        "model": "runtime_configuration_mismatch", "gold": "declared_unique_task_ids_required",
        "duplicate": "declared_unique_task_ids_required",
        "unknown": "declared_unique_task_ids_required", "missing_key": "typesafe_api_key_required",
    }
    with pytest.raises(OptimizerError, match="^" + expected[change] + "$"):
        execute(db, "learn-runtime", tmp_path / "rejected", common, *extra)
    assert not peer[1] and not (tmp_path / "rejected").exists()
    assert Optimizer.open(db).status()["trials"] == []


def test_enabled_explicit_policy_and_no_registry_overwrite(tmp_path, peer):
    db, _, common = setup(tmp_path, peer)
    policy = tmp_path / "policy.json"
    policy.write_text('{"version":"request-policy-v3","enabled":false}', encoding="utf-8")
    with pytest.raises(OptimizerError, match="enabled_baseline_required"):
        execute(db, "initialize-runtime", tmp_path / "bad", common, "--policy", str(policy))
    assert not db.exists()
    initial = execute(db, "initialize-runtime", tmp_path / "init", common)
    with pytest.raises(OptimizerError, match="new_runtime_registry_required"):
        execute(db, "initialize-runtime", tmp_path / "again", common)
    assert Optimizer.open(db).status() == initial["status"]
    assert not peer[1]


def test_jev_disclosure_is_policy_only_and_auxiliary_cost_is_not_free(tmp_path, peer, monkeypatch):
    db, _, common = setup(tmp_path, peer, feasible=True)
    initial = execute(db, "initialize-runtime", tmp_path / "init", common)
    screens = []

    def decide(self, state, questions, *, data_classification):
        assert self.enabled and self.allow_network and data_classification == "sanitized"
        wire = json.dumps({"state": state, "questions": questions})
        assert "note.txt" not in wire and "Résumé" not in wire and "expected" not in wire
        assert set(state) == set(questions["proposal"]["criteria"]) - {"abstain"}
        screens.append(wire)
        # A fully captured failed screen still costs tokens; order falls back.
        return Result(False, "http_error", wire, "service unavailable", diagnostics=Diagnostics(
            attempts=1, response_complete=True, http_status=503))

    monkeypatch.setattr(JevClient, "decide", decide)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-only-placeholder")
    result = execute(db, "learn-runtime", tmp_path / "trial", common,
                     *task_arguments(initial), "--jev")
    assert len(screens) == 1 and len(peer[1]) == 4 * len(initial["task_ids"])
    assert result["jev_capture_complete"] is False  # Raw remote error bodies are withheld.
    saved = json.loads((tmp_path / "trial/jev-capture.json").read_text("utf-8"))
    assert saved["request_text"] == screens[0] and "test-only-placeholder" not in json.dumps(saved)
    assert saved["raw_response_withheld"] and "response_text" not in saved
    assert result["status"]["learning"]["complete_calls"] == 4 * len(initial["task_ids"]) + 1
    assert result["status"]["learning"]["coverage"] == "complete"
    assert result["policy_promoted"] is False
    traces = Optimizer.open(db).learning_inventory()["traces"]
    primary = sum(t.totals().total_tokens for t in traces if not t.task_id.startswith("screen-"))
    auxiliary = tokens.count_tokens(screens[0]) + tokens.count_tokens("service unavailable")
    assert result["status"]["learning"]["reference_tokens"] == primary + auxiliary


def test_cli_main_sanitizes_invalid_manifest_errors(tmp_path, capsys):
    manifest = tmp_path / "private-name.json"
    manifest.write_text('{"private":"DO-NOT-ECHO",', encoding="utf-8")
    code = cli.main(["--db", str(tmp_path / "c.sqlite"), "initialize-runtime",
                     "--manifest", str(manifest), "--output", str(tmp_path / "init"),
                     "--base-url", "http://127.0.0.1:1/v1", "--model", "test",
                     "--allow-network"])
    result = capsys.readouterr()
    assert code == 2 and "DO-NOT-ECHO" not in result.out
    assert str(tmp_path) not in result.out and not result.err
    assert json.loads(result.out) == {"ok": False, "reason": "controller_operation_failed"}


@pytest.mark.parametrize("failure", ["write_error", "reflected_secret", "escaped_secret",
                                    "escaped_success_metadata"])
def test_screen_capture_failure_never_masks_usage_or_persists_secret(tmp_path, monkeypatch, failure):
    key = "test-only-reflection-placeholder"
    monkeypatch.setenv("TYPESAFE_API_KEY", key)
    escaped = '"' + "".join(f"\\u{ord(c):04x}" for c in key) + '"'
    reply = Result(
        failure == "escaped_success_metadata", "ok" if failure == "escaped_success_metadata" else "http_error",
        '{"state":{}}',
        escaped if failure.startswith("escaped") else
        key if failure == "reflected_secret" else "complete failed body",
        diagnostics=Diagnostics(attempts=1, response_complete=True, http_status=503))
    monkeypatch.setattr(JevClient, "decide", lambda *a, **k: reply)
    original = cli._write_data

    def failing_write(path, value):
        if path.name == "jev-capture.json":
            raise OSError("unavailable capture path")
        original(path, value)

    if failure == "write_error":
        monkeypatch.setattr(cli, "_write_data", failing_write)
    screen = cli._PolicyScreen(tmp_path)
    assert screen.decide({}, {}, data_classification="sanitized") is reply
    assert not (tmp_path / "jev-capture.json").exists()  # Accounting happens before extra I/O.
    screen.persist()
    assert screen.capture_complete is False
    if failure == "write_error":
        assert not (tmp_path / "jev-capture.json").exists()
    else:
        captured = json.loads((tmp_path / "jev-capture.json").read_text("utf-8"))
        assert captured["raw_response_withheld"] and "response_text" not in captured
        assert "payload" not in captured and key not in json.dumps(captured)
    assert key not in (tmp_path / "jev-disclosure.json").read_text("utf-8")


def test_capture_interruption_occurs_after_durable_accounting(tmp_path, peer, monkeypatch):
    db, _, common = setup(tmp_path, peer, feasible=True)
    initial = execute(db, "initialize-runtime", tmp_path / "init", common)
    raw_input, raw_output = '{"state":"policy only"}', '{"complete":"failed-screen"}'
    reply = Result(False, "http_error", raw_input, raw_output,
                   diagnostics=Diagnostics(attempts=1, response_complete=True, http_status=503))
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-only-placeholder")
    monkeypatch.setattr(JevClient, "decide", lambda *a, **k: reply)
    original, calls_at_interruption = cli._write_data, []

    def interrupt(path, value):
        if path.name == "jev-capture.json":
            calls_at_interruption.append(len(peer[1]))
            raise KeyboardInterrupt
        original(path, value)

    monkeypatch.setattr(cli, "_write_data", interrupt)
    with pytest.raises(KeyboardInterrupt):
        execute(db, "learn-runtime", tmp_path / "trial", common,
                *task_arguments(initial), "--jev")
    optimizer = Optimizer.open(db)
    assert calls_at_interruption == [len(peer[1])]
    screen = [t for t in optimizer.learning_inventory()["traces"] if t.task_id.startswith("screen-")]
    assert len(screen) == 1
    assert screen[0].totals().total_tokens == tokens.count_tokens(raw_input) + tokens.count_tokens(raw_output)
    assert optimizer.status()["champion"] == initial["status"]["champion"]
    assert not (tmp_path / "trial/command-result.json").exists()
