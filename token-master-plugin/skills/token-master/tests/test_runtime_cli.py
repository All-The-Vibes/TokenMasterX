"""Installed subprocess + loopback mock HTTP tests. No real provider/model calls."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Thread

import pytest

import brainspace_setup
import brainspace_tools
from brainspace import session_cli, tokens
from brainspace.request_policy import RequestPolicy, SourceReadInfo
from brainspace.task_mode import TaskContract, TaskModeStore
from hosts.tokenizer import read_tokenizer


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
MODEL = "local-mock-only"
TEXT = "def value():\n" + "".join(f"    number_{i} = {i}\n" for i in range(160))


@pytest.fixture
def bridge():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            self.server.requests.append((self.path, raw, dict(self.headers)))
            response = deepcopy(self.server.response)
            data = json.dumps(response, ensure_ascii=False).encode()
            self.send_response(self.server.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.requests, server.status = [], 200
    server.response = {
        "object": "response", "status": "completed", "model": MODEL,
        "output": [{"type": "message", "role": "assistant",
                    "content": [{"type": "output_text", "text": "A mock answer, not a quality verdict."}]}],
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    }
    server.url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def installed(tmp_path):
    return brainspace_setup._install_files(tmp_path / "installed-home")


BOOT = r'''
import importlib.abc, runpy, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"evals", "quality", "tests"}:
            raise AssertionError("evaluation imports forbidden")
sys.meta_path.insert(0, Block())
sys.path.insert(0, sys.argv[1])
sys.argv = sys.argv[2:]
runpy.run_path(sys.argv[0], run_name="__main__")
'''


def request():
    return {"model": MODEL, "messages": [
        {"role": "system", "content": "Keep the system instructions."},
        {"role": "developer", "content": "Keep developer instructions."},
        {"role": "user", "content": "Read the source."},
    ]}


def frames(*values):
    return b"".join((json.dumps(value, ensure_ascii=False) + "\n").encode() for value in values)


def command(installed, workspace, output, bridge, *extra, network=True, backend="none"):
    values = [
        sys.executable, "-I", "-B", "-c", BOOT, str(installed),
        str(installed / "brainspace_tools.py"), "--workspace", str(workspace), "--session", "cli-test",
        "session", "--output", str(output), "--base-url", bridge.url, "--model", MODEL,
        "--backend", backend,
    ]
    return values + (["--allow-network"] if network else []) + list(extra)


def verified_vocabulary(required=True):
    """TOKENMASTER_TEST_TOKENIZER_FILE, else tiktoken's cache, verified by hash.

    With none, skips the test if it needs the vocabulary; otherwise returns a path that does not exist.
    """
    try:
        _, receipt = read_tokenizer(os.environ.get("TOKENMASTER_TEST_TOKENIZER_FILE"))
    except ValueError as exc:
        if required:
            pytest.skip(f"no verified cl100k_base vocabulary: {exc}")
        return ROOT / "missing-cl100k_base.tiktoken"
    return Path(receipt["source"])


def environment(needs_vocabulary=True):
    env = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "PATHEXT")
           if key in os.environ}
    env.update(BRAINSPACE_TOKENIZER_FILE=str(verified_vocabulary(needs_vocabulary)), PYTHONIOENCODING="utf-8")
    return env


def launch(tmp_path, installed, bridge, input_bytes, *extra, needs_vocabulary=True, **options):
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    output = tmp_path / "run"
    completed = subprocess.run(
        command(installed, workspace, output, bridge, *extra, **options),
        input=input_bytes, capture_output=True, timeout=25, cwd=tmp_path, env=environment(needs_vocabulary),
    )
    rows = [json.loads(line) for line in completed.stdout.splitlines()]
    return completed, rows, output


def json_file(output, name):
    return json.loads((output / name).read_bytes())


def test_installed_two_call_stream_flushes_before_eof_without_duplicate_guidance(tmp_path, installed, bridge):
    workspace, output = tmp_path / "workspace", tmp_path / "run"
    workspace.mkdir()
    contract = TaskContract("Inspect the source carefully.", (), ("Check evidence.",), "Finish when verified.")
    contract_file = tmp_path / "contract.json"
    contract_file.write_text(contract.to_json(), encoding="utf-8")
    process = subprocess.Popen(
        command(installed, workspace, output, bridge, "--contract", str(contract_file)),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=tmp_path, env=environment(),
    )
    initial = request()
    try:
        process.stdin.write(frames({"op": "call", "request": initial}))
        process.stdin.flush()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(process.stdout.readline)
            try:
                first = json.loads(future.result(timeout=15))
            except Exception:
                process.kill()
                raise
        assert first["op"] == "call" and first["ok"]
        following = deepcopy(initial)
        following["messages"].append({"role": "assistant", "content": "Continue."})
        out, err = process.communicate(
            frames({"op": "call", "request": following}, {"op": "finish"}), timeout=15,
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    assert process.returncode == 0, err
    rows = [first] + [json.loads(line) for line in out.splitlines()]
    assert [row["op"] for row in rows] == ["call", "call", "finish"]  # no extra null frame
    assert rows[-1]["result"]["quality_verified"] is None
    assert rows[-1]["cleanup"]["complete"] is True
    assert rows[-1]["result"]["model_calls"] == 2
    assert len(bridge.requests) == 2
    captures = [json.loads(line) for line in (output / "captures.jsonl").read_text().splitlines()]
    for (_, raw, headers), capture in zip(bridge.requests, captures):
        body = json.loads(raw)
        assert body["reasoning"] == {"effort": "low"}
        assert raw.decode() == capture["input"]
        assert sum("Task contract:" in str(item.get("content")) for item in body["input"]) == 1
        assert body["input"][:2] == initial["messages"][:2]
        assert "Authorization" not in headers
    totals = rows[-1]["result"]["reference_totals"]
    assert totals["input_tokens"] == sum(tokens.count_tokens(c["input"]) for c in captures)
    assert totals["output_tokens"] == sum(tokens.count_tokens(c["output"]) for c in captures)
    assert rows[-1]["result"]["gateway_reported_tokens"] == 30
    assert not (workspace / ".token-master").exists()


def duplicate_frames():
    original = request()
    values = [{"op": "call", "request": deepcopy(original)}]
    for number, (path, text) in enumerate((("a.py", TEXT), ("a.py", TEXT), ("b.py", "other"))):
        call_id = f"read-{number}"
        original["messages"].extend([
            {"role": "assistant", "content": None, "tool_calls": [{
                "id": call_id, "type": "function",
                "function": {"name": "read_file", "arguments": json.dumps({"path": path})}}]},
            {"role": "tool", "tool_call_id": call_id, "content": text},
        ])
        info = SourceReadInfo.from_text(
            call_id=call_id, tool_name="read_file", source_path=path, content=text, status="success",
        )
        values.append({"op": "observe-read", "receipt": info.to_dict()})
    values.extend([{"op": "call", "request": original, "intent": "navigation",
                    "role": "primary", "stable_prefix_messages": 2, "exact_message_indices": []},
                   {"op": "finish"}])
    return values


def test_installed_trusted_sideband_enables_v3_on_second_call(tmp_path, installed, bridge):
    values = duplicate_frames()
    process, rows, output = launch(tmp_path, installed, bridge, frames(*values), backend="local")
    assert process.returncode == 0, process.stderr
    assert len(bridge.requests) == 2
    assert [row["op"] for row in rows] == ["call", "observe-read", "observe-read", "observe-read", "call", "finish"]
    sent = json.loads(bridge.requests[-1][1])["input"]
    assert sent[4]["output"] == TEXT
    assert "EXACT_READ_REUSE" in sent[6]["output"]
    assert sent[8]["output"] == "other"
    assert rows[-1]["result"]["transformations"] == 1
    assert len((output / "source-reads.jsonl").read_text().splitlines()) == 3
    assert values[-2]["request"]["messages"][6]["content"] == TEXT


def test_model_output_cannot_submit_receipts_or_self_grade(tmp_path, installed, bridge):
    values = duplicate_frames()
    receipt = values[1]["receipt"]
    bridge.response["output"] = [{"type": "function_call", "name": "observe-read",
                                 "call_id": "model-invented", "arguments": json.dumps(receipt)}]
    bridge.response["success"] = True
    values = [v for v in values if v["op"] != "observe-read"]
    process, rows, output = launch(tmp_path, installed, bridge, frames(*values), backend="local")
    assert process.returncode == 0
    assert rows[-1]["result"]["quality_verified"] is None
    assert rows[-1]["result"]["transformations"] == 0
    assert not (output / "source-reads.jsonl").exists()


def test_explicit_network_gate_precedes_output_creation(tmp_path, installed, bridge):
    process, rows, output = launch(
        tmp_path, installed, bridge, frames({"op": "call", "request": request()}), network=False,
        needs_vocabulary=False,
    )
    assert process.returncode == 2
    assert rows == [{"op": "error", "ok": False, "error": "explicit_network_opt_in_required"}]
    assert not output.exists() and not bridge.requests


@pytest.mark.parametrize("bad", [
    b'{"op":"SECRET_UNKNOWN"}\n',
    b'{"op":"finish","success":true}\n',
    b'{"op":"finish","op":"finish"}\n',
    b'{"op":"finish","extra":NaN}\n',
    b'{"op":"finish","extra":1e999}\n',
    b'{"op":"call","request":{},"executor":"SECRET_PLUGIN"}\n',
    b'{"op":"call","request":{},"stable_prefix_messages":true}\n',
    b'{"op":"call","request":{},"exact_message_indices":[false]}\n',
    b'{"op":"recover","name":"shell","args":{},"tool_call_id":"SECRET"}\n',
    b'{"op":"observe-read","receipt":{"success":"SECRET"}}\n',
    b'{"op":"finish"}', b'\xff\n', b'\n',
])
def test_bad_frame_aborts_safely_but_preserves_prior_call(tmp_path, installed, bridge, bad):
    process, rows, output = launch(
        tmp_path, installed, bridge, frames({"op": "call", "request": request()}) + bad,
    )
    assert process.returncode == 2
    assert [row["op"] for row in rows] == ["call", "error", "finish"]
    assert "SECRET" not in process.stdout.decode() and "SECRET" not in process.stderr.decode()
    result = json_file(output, "result.json")
    assert result["model_calls"] == 1 and result["quality_verified"] is None
    assert result["trace_complete"] is True
    assert json_file(output, "cleanup.json")["complete"] is True
    assert len(bridge.requests) == 1


@pytest.mark.parametrize("kind", ["frame_size", "frame_count", "call_count", "eof"])
def test_stream_limits_stop_without_extra_submission(tmp_path, installed, bridge, kind):
    first = frames({"op": "call", "request": request()})
    extras = []
    if kind == "frame_size":
        payload = first + b" " * session_cli.MAX_FRAME_BYTES + b"\n"
    elif kind == "frame_count":
        payload, extras = first + frames({"op": "finish"}), ["--max-frames", "1"]
    elif kind == "call_count":
        payload = first + first + frames({"op": "finish"})
        extras = ["--max-calls", "1"]
    else:
        payload = first
    process, rows, output = launch(tmp_path, installed, bridge, payload, *extras)
    assert process.returncode == 2
    assert rows[-1]["result"]["model_calls"] == 1 and len(bridge.requests) == 1
    assert json_file(output, "cleanup.json")["complete"]


def test_incomplete_response_is_nonzero_unknown_not_zero(tmp_path, installed, bridge):
    process, rows, output = launch(
        tmp_path, installed, bridge,
        frames({"op": "call", "request": request()}, {"op": "finish"}), "--max-response-bytes", "64",
    )
    assert process.returncode == 3
    assert rows[0]["ok"] is False and rows[0]["complete"] is False
    result = rows[-1]["result"]
    assert result["trace_complete"] is False and result["reference_totals"] is None
    assert result["model_calls"] == len(result["incomplete_calls"]) == 1
    assert len((output / "invocations.jsonl").read_text().splitlines()) == 2
    assert rows[-1]["cleanup"]["complete"]


def test_exit_zero_means_accounted_not_successful_http_or_answer(tmp_path, installed, bridge):
    bridge.status = 500
    process, rows, _ = launch(
        tmp_path, installed, bridge, frames({"op": "call", "request": request()}, {"op": "finish"}),
    )
    assert process.returncode == 0 and rows[0]["ok"] is False
    assert rows[-1]["result"]["trace"]["calls"][0]["completion_status"] == "failed"
    assert rows[-1]["result"]["quality_verified"] is None
    assert rows[-1]["result"]["reference_totals"]["total_tokens"] > 0


@pytest.mark.parametrize("extra", [
    ["--optimizer-db", "missing.sqlite"],
    ["--optimizer-version", "1"],
    ["--phase", "learning"],
    ["--learning-run-id", "not-a-learning-phase"],
    ["--max-frames", "0"],
    ["--headroom-cache", "unused"],
    ["--base-url", "https://not-loopback.invalid/v1"],
    ["--policy", '{"enabled":true,"enabled":false}'],
])
def test_invalid_configuration_creates_no_run_or_call(tmp_path, installed, bridge, extra):
    process, rows, output = launch(tmp_path, installed, bridge, frames({"op": "finish"}), *extra,
                                   needs_vocabulary=False)
    assert process.returncode == 2
    assert rows[0]["op"] == "error"
    assert not output.exists() and not bridge.requests


def test_explicit_session_mode_selection(tmp_path, installed, bridge):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    mode = TaskContract("Session-selected contract.", (), (), "Done.")
    store = TaskModeStore(workspace / ".token-master")
    store.enable("cli-test", mode)
    state_before = store.path_for_session("cli-test").read_bytes()
    process, rows, _ = launch(tmp_path, installed, bridge,
                              frames({"op": "call", "request": request()}, {"op": "finish"}),
                              "--use-session-mode")
    assert process.returncode == 0 and rows[-1]["result"]["quality_verified"] is None
    assert state_before == store.path_for_session("cli-test").read_bytes()
    assert "Session-selected contract." in json.dumps(json.loads(bridge.requests[0][1]))


def test_real_pinned_export_loads_in_installed_session(tmp_path, installed, bridge):
    export = Path(os.environ.get("TOKENMASTER_TEST_PONYTAIL_EXPORT",
                                 REPO / "evidence/controlled-scorecard-20261008/batch-001/ponytail.json"))
    if not export.is_file():
        pytest.skip("no pinned Ponytail export: set TOKENMASTER_TEST_PONYTAIL_EXPORT")
    process, rows, output = launch(
        tmp_path, installed, bridge, frames({"op": "call", "request": request()}, {"op": "finish"}),
        "--ponytail-export", str(export),
    )
    assert process.returncode == 0, process.stderr
    profile = json_file(output, "session.json")["profile"]
    assert profile["ponytail"]["mode"] == "full" and profile["mode"] is None
    items = json.loads(bridge.requests[0][1])["input"]
    assert sum(profile["ponytail"]["text"] in item.get("content", "")
               for item in items if item.get("role") == "user") == 1
    assert rows[-1]["result"]["quality_verified"] is None


def test_explicit_policy_and_learning_scope_are_forwarded(tmp_path, installed, bridge):
    policy = RequestPolicy(version="request-policy-v3", enabled=True, min_tool_chars=80)
    process, rows, output = launch(
        tmp_path, installed, bridge, frames({"op": "call", "request": request()}, {"op": "finish"}),
        "--policy", policy.to_json(), "--phase", "learning", "--learning-run-id", "explicit-learning",
        backend="local",
    )
    assert process.returncode == 0, process.stderr
    assert json_file(output, "session.json")["profile"]["policy"] == policy.to_dict()
    assert rows[-1]["result"]["trace"]["learning_run_id"] == "explicit-learning"
    assert rows[-1]["result"]["trace"]["phase"] == "learning"


@pytest.mark.parametrize("clean", [True, False])
def test_control_frames_keep_one_session_and_exit_on_cleanup_state(tmp_path, monkeypatch, clean):
    import io
    from brainspace.transport import Reply

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    lifecycle = []

    class Session:
        def __init__(self, **kwargs):
            lifecycle.append("created")

        def observe_source_read(self, info):
            assert type(info) is SourceReadInfo
            lifecycle.append("observe")

        def invoke(self, *args, **kwargs):
            lifecycle.append("call")
            return Reply(True, "ok", complete=True, body={})

        def recover(self, name, args, *, tool_call_id):
            assert (name, args, tool_call_id) == ("retrieve_original", {"ref": "r", "offset": 0}, "recovery")
            lifecycle.append("recover")
            return "A fragment, not a full-root claim."

        def finish(self):
            lifecycle.append("finish")
            return {"trace_complete": True, "component": {"complete": True}, "quality_verified": None}

        def close(self):
            lifecycle.append("close")
            return {"complete": clean}

    monkeypatch.setattr(session_cli, "RuntimeSession", Session)
    args = brainspace_tools._parser().parse_args([
        "--workspace", str(workspace), "--session", "s", "session",
        "--output", str(tmp_path / "run"), "--base-url", "http://127.0.0.1:1",
        "--model", MODEL, "--allow-network", "--backend", "none",
    ])
    receipt = SourceReadInfo.from_text(
        call_id="r", tool_name="read_file", source_path="a.py", content=TEXT, status="success")
    input_stream = io.BytesIO(frames(
        {"op": "observe-read", "receipt": receipt.to_dict()},
        {"op": "call", "request": request()},
        {"op": "recover", "name": "retrieve_original", "args": {"ref": "r", "offset": 0},
         "tool_call_id": "recovery"},
        {"op": "call", "request": request()}, {"op": "finish"},
    ))
    output_stream = io.BytesIO()
    code = session_cli.run_session(args, input_stream=input_stream, output_stream=output_stream)
    assert code == (0 if clean else 3)
    assert lifecycle == ["created", "observe", "call", "recover", "call", "finish", "close"]
    assert len(output_stream.getvalue().splitlines()) == 5


def test_headroom_options_default_to_owned_config_and_finalize_after_errors(tmp_path, monkeypatch):
    workspace, cache = tmp_path / "workspace", tmp_path / "cache"
    workspace.mkdir()
    cache.mkdir()
    assets = tmp_path / "assets.json"
    assets.write_text("{}", encoding="utf-8")
    received, lifecycle = [], []

    class Session:
        def __init__(self, **kwargs):
            received.append(kwargs)

        def invoke(self, *args, **kwargs):
            lifecycle.append("call")
            raise ValueError("SECRET INTERNAL DATA")

        def finish(self):
            lifecycle.append("finish")
            return {"trace_complete": True, "component": {"complete": True}, "quality_verified": None}

        def close(self):
            lifecycle.append("close")
            return {"complete": False}

    monkeypatch.setattr(session_cli, "RuntimeSession", Session)
    monkeypatch.setenv("DOCKER_CONFIG", "must-not-discover")
    args = brainspace_tools._parser().parse_args([
        "--workspace", str(workspace), "--session", "explicit", "session",
        "--output", str(tmp_path / "run"), "--base-url", "http://127.0.0.1/v1",
        "--model", MODEL, "--allow-network", "--backend", "headroom",
        "--headroom-cache", str(cache), "--headroom-assets", str(assets),
    ])
    import io
    stream = io.BytesIO()
    code = session_cli.run_session(args, input_stream=io.BytesIO(frames({"op": "call", "request": request()})),
                                   output_stream=stream)
    assert code == 2 and lifecycle == ["call", "finish", "close"]
    assert len(received) == 1 and received[0]["headroom_options"] == {
        "cache": cache, "assets": assets, "docker_config": None}
    assert b"SECRET" not in stream.getvalue()


def test_session_mode_contract_and_policy_optimizer_flags_are_mutually_exclusive():
    base = ["--workspace", ".", "--session", "s", "session", "--output", "out",
            "--base-url", "http://127.0.0.1", "--model", MODEL, "--backend", "none"]
    for options in (["--contract", "a", "--use-session-mode"], ["--policy", "{}", "--optimizer-db", "b"]):
        with pytest.raises(ValueError, match="invalid_arguments"):
            brainspace_tools._parser().parse_args(base + options)
