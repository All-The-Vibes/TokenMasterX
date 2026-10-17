"""Actual pinned Headroom, in one checked network-none process per task.

No vendor replacement, provider calls, implicit downloads, or eval imports.
The existing pre-provisioned Docker Desktop/Linux image and verified asset cache
are required. Keep this object alive across prepare/retrieve calls; finish audits
the same task store, and close cleans only the exact owned container.

Upstream recovery can return a fragment. Neither retrieve nor finish certifies
exact whole-file/root recovery. The historical container label and wire protocol
are retained for compatibility; they do not certify parity or token savings.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import time

from .runtime_io import append_receipt, parse_json, safe_root


IMAGE_ID = "sha256:eb04988b9360cb5b4d0348a519a5a66232e04593de8f3bbee6571a6a397343c6"
COMMIT = "1cf496612e781ef8d67ff87ee4f78037492f0bc7"
MODEL_REVISION = "b1563631b35bfdcee37587ad530147497d820d4c"
MAX_FRAME = 4_194_304
DEFAULT_STRATEGY = "upstream-default-v1"
DOCUMENT_STRATEGY = "native-documents-v1"
PREPROTECTION_STRATEGY = "native-documents-structure-tags-v1"


def validate_strategy(value):
    if type(value) is not str or value not in (
            DEFAULT_STRATEGY, DOCUMENT_STRATEGY, PREPROTECTION_STRATEGY):
        raise ValueError("invalid_headroom_strategy")

# Keep create's existing task overrides and the immutable image's public defaults
# explicit. Unknown settings (including credentials, proxies, detector/backend
# and remote/model overrides) are rejected, even when their values are empty.
TASK_ENVIRONMENT = {
    "HOME": "/tmp/headroom", "XDG_CACHE_HOME": "/tmp/headroom/cache",
    "HF_HOME": "/cache", "HF_HUB_CACHE": "/cache/hub", "TIKTOKEN_CACHE_DIR": "/cache/tiktoken",
    "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1", "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1",
    "LITELLM_LOCAL_MODEL_COST_MAP": "True", "TOKENIZERS_PARALLELISM": "false",
    "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2",
    "HEADROOM_KOMPRESS_ONNX_INTRA_THREADS": "2", "HEADROOM_KOMPRESS_ONNX_INTER_THREADS": "1",
}
PINNED_BASE_ENVIRONMENT = {
    "PATH": "/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "GPG_KEY": "7169605F62C751356D054A26A821E680E5FA6305",  # Public signing fingerprint.
    "PYTHON_VERSION": "3.13.16",
    "PYTHON_SHA256": "f4b1bfb3c79b5bb11b8d228a12504163b4c0dab4d679828d8f5f26b6cb6ab35d",
    "HEADROOM_HOST": "127.0.0.1",
    "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1",
}


def validate_time_budget_seconds(value):
    """An explicit cooperative budget, not a hard end-to-end latency bound."""
    if type(value) is not int or not 1 <= value <= 60:
        raise ValueError("invalid_headroom_time_budget_seconds")


def _task_environment(time_budget_seconds):
    declared = dict(TASK_ENVIRONMENT)
    if time_budget_seconds is not None:
        validate_time_budget_seconds(time_budget_seconds)
        declared.update(
            HEADROOM_COMPRESSION_DEADLINE_MS=str(time_budget_seconds * 1000),
            HEADROOM_KOMPRESS_TIME_BUDGET_SECONDS=str(time_budget_seconds))
    return declared


def validate_environment(entries, *, time_budget_seconds=None):
    """Validate the effective container regime; never echo rejected input.

    This declares configuration only, not actual inference/backend coverage.
    The receipt hashes only the fully matched, public nonsecret regime.
    """
    declared = {**_task_environment(time_budget_seconds), **PINNED_BASE_ENVIRONMENT}
    if type(entries) is not list:
        raise ValueError("container environment must be a declared list")
    found = {}
    for entry in entries:
        if type(entry) is not str or "=" not in entry or "\0" in entry:
            raise ValueError("container environment entry is invalid")
        key, value = entry.split("=", 1)
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) is None or key in found:
            raise ValueError("container environment key is invalid or duplicated")
        found[key] = value
    if found != declared:
        raise ValueError("container environment differs from declared regime")
    receipt = {
        "profile": "headroom-pinned-local-environment-v1",
        "names": sorted(declared),
        "checks": {"typed_unique_entries": True, "exact_declared_values": True,
                   "undeclared_settings_absent": True},
        "declared_nonsecret_regime_sha256": hashlib.sha256(
            json.dumps(declared, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
    }
    if time_budget_seconds is not None:
        receipt["time_budget_seconds"] = time_budget_seconds
    return receipt


def validate_container(actual, *, identity, label, mounts, time_budget_seconds=None):
    """Check actual state before starting the default-untrusted image process."""
    host, config = actual["HostConfig"], actual["Config"]
    validate_environment(config.get("Env"), time_budget_seconds=time_budget_seconds)
    if (actual["Id"] != identity or actual["Image"] != IMAGE_ID
            or config["Labels"].get("tokenmaster.parity") != label
            or config["User"] != "65532:65532" or config["Entrypoint"] != ["python"]
            or config["Cmd"] != ["/inputs/worker.py"] or config["OpenStdin"] is not True
            or host["NetworkMode"] != "none" or host["ReadonlyRootfs"] is not True
            or host["Privileged"] is not False or host["CapDrop"] != ["ALL"]
            or "no-new-privileges" not in host["SecurityOpt"]
            or host["NanoCpus"] != 2_000_000_000
            or host["Memory"] != 4 * 1024**3 or host["MemorySwap"] != 4 * 1024**3
            or host["PidsLimit"] != 256
            or config["Volumes"] != {"/home/nonroot/.headroom": {}}
            or host["Tmpfs"] != {
                "/tmp": "rw,noexec,nosuid,nodev,size=256m",
                "/home/nonroot/.headroom": "rw,noexec,nosuid,nodev,size=64m",
            }):
        raise ValueError("container boundary mismatch")
    found = actual["Mounts"]
    if len(found) != len(mounts) or {item["Destination"] for item in found} != set(mounts):
        raise ValueError("container mount inventory mismatch")
    for item in found:
        source, writable = mounts[item["Destination"]]
        if (item["Type"] != "bind" or Path(item["Source"]).resolve() != Path(source).resolve()
                or item["RW"] is not writable):
            raise ValueError("container mount boundary mismatch")


class HeadroomContainer:
    def __init__(self, directory, *, cache, assets, docker_config, label, time_budget_seconds=None,
                 strategy=DEFAULT_STRATEGY):
        validate_strategy(strategy)
        self.strategy = strategy
        self._strategy_manifest = None
        if time_budget_seconds is not None:
            validate_time_budget_seconds(time_budget_seconds)
        self.time_budget_seconds = time_budget_seconds
        self.directory = safe_root(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.cache, self.assets = safe_root(cache), safe_root(assets)
        if not self.cache.is_dir() or not self.assets.is_file():
            raise ValueError("verified comparator assets are required")
        self.label = label
        if re.fullmatch(r"[a-z0-9-]{1,64}", label) is None:
            raise ValueError("invalid task label")
        self.base = [shutil.which("docker"), "--config", str(safe_root(docker_config))]
        if self.base[0] is None:
            raise ValueError("Docker is unavailable")
        configuration = parse_json((Path(docker_config) / "config.json").read_text(encoding="utf-8"))
        if configuration != {}:
            raise ValueError("comparator requires an empty task-owned Docker configuration")
        self.environment = {key: os.environ[key] for key in
                            ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "PATHEXT")
                            if key in os.environ}
        self.environment["DOCKER_HOST"] = "npipe:////./pipe/dockerDesktopLinuxEngine"
        self.identity = None
        self.process = None
        self.stderr = None
        self.replies: queue.Queue = queue.Queue()
        self.commands = []
        self.sequence = 0
        self.finished = False
        self.failed = False
        self.ready = None
        self.worker_snapshot = None
        self.worker_sha256 = None
        self.started = time.monotonic()
        self._started = False
        self._closed = False

    def command(self, args, *, timeout=30, check=True):
        result = subprocess.run(self.base + args, env=self.environment, capture_output=True,
                                text=True, encoding="utf-8", timeout=timeout,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.commands.append({"arguments": args, "exit_code": result.returncode})
        (self.directory / "docker-commands.json").write_text(
            json.dumps(self.commands, indent=2), encoding="utf-8")
        if check and result.returncode:
            raise RuntimeError("Docker comparator command failed")
        return result

    def _read(self):
        try:
            process = self.process
            if process is None or process.stdout is None:
                raise RuntimeError("Headroom attach output is unavailable")
            while True:
                line = process.stdout.readline(MAX_FRAME + 1)
                if not line:
                    self.replies.put(EOFError("comparator exited"))
                    return
                if len(line) > MAX_FRAME or not line.endswith(b"\n"):
                    raise ValueError("invalid comparator response frame")
                response = parse_json(line.decode("utf-8"))
                append_receipt(self.directory / "received.jsonl", {
                    "response": response, "sha256": hashlib.sha256(line).hexdigest(),
                })
                self.replies.put(response)
        except Exception as error:
            self.replies.put(error)

    def _receive(self, identifier, timeout):
        try:
            result = self.replies.get(timeout=timeout)
        except queue.Empty as error:
            self.failed = True
            raise TimeoutError("comparator response deadline") from error
        if isinstance(result, Exception):
            self.failed = True
            raise result
        if (type(result) is not dict or result.get("id") != identifier or result.get("ok") is not True
                or (identifier != "ready" and type(result.get("result")) is not dict)):
            self.failed = True
            raise ValueError("comparator response identity or status mismatch")
        return result

    def start(self):
        """Start once; failed setup stays unavailable until exact-owned cleanup."""
        if self._started or self._closed:
            raise RuntimeError("Headroom task cannot be restarted")
        self._started = True
        try:
            return self._start()
        except BaseException:
            self.failed = True
            raise

    def _start(self):
        inspected = parse_json(self.command(["image", "inspect", IMAGE_ID]).stdout)[0]
        if (inspected["Id"] != IMAGE_ID
                or inspected["Config"]["Labels"].get("org.opencontainers.image.revision") != COMMIT):
            raise ValueError("comparator image identity mismatch")
        worker_source = Path(__file__).with_name("headroom_worker.py").resolve()
        data = worker_source.read_bytes()
        self.worker_sha256 = hashlib.sha256(data).hexdigest()
        worker = self.directory / "worker-frozen.py"
        worker.write_bytes(data)
        self.worker_snapshot = worker
        if hashlib.sha256(worker_source.read_bytes()).hexdigest() != self.worker_sha256:
            raise ValueError("worker source changed while freezing")
        (self.directory / "worker-source.json").write_text(json.dumps({
            "source": str(worker_source), "sha256": self.worker_sha256,
            "executed_snapshot": str(worker),
        }, indent=2), encoding="utf-8")
        mounts = {
            "/inputs/worker.py": (worker, False), "/inputs/assets.json": (self.assets, False),
            "/cache": (self.cache, False),
        }
        args = [
            "create", "-i", "--label", "tokenmaster.parity=" + self.label,
            "--user", "65532:65532", "--read-only", "--network", "none",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--cpus", "2", "--memory", "4g", "--memory-swap", "4g", "--pids-limit", "256",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=256m",
            "--tmpfs", "/home/nonroot/.headroom:rw,noexec,nosuid,nodev,size=64m",
            "--no-healthcheck", "--workdir", "/tmp", "--entrypoint", "python",
        ]
        for key, value in _task_environment(self.time_budget_seconds).items():
            args += ["--env", key + "=" + value]
        for target, (source, writable) in mounts.items():
            args += ["--mount", f"type=bind,source={source},target={target}" +
                     ("" if writable else ",readonly")]
        args += [IMAGE_ID, "/inputs/worker.py"]
        self.identity = self.command(args).stdout.strip()
        if re.fullmatch("[0-9a-f]{64}", self.identity) is None:
            raise ValueError("invalid created container ID")
        (self.directory / "container-id.txt").write_text(self.identity, encoding="utf-8")
        actual = parse_json(self.command(["inspect", self.identity]).stdout)[0]
        validate_container(actual, identity=self.identity, label=self.label, mounts=mounts,
                           time_budget_seconds=self.time_budget_seconds)
        (self.directory / "environment.json").write_text(
            json.dumps(validate_environment(
                actual["Config"]["Env"], time_budget_seconds=self.time_budget_seconds), indent=2),
            encoding="utf-8")
        (self.directory / "container-config.json").write_text(
            json.dumps(actual, indent=2), encoding="utf-8")
        self.stderr = (self.directory / "stderr.txt").open("wb")
        self.process = subprocess.Popen(
            self.base + ["start", "--attach", "--interactive", self.identity],
            env=self.environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        threading.Thread(target=self._read, daemon=True).start()
        self.ready = self._receive("ready", 90)
        if (self.ready.get("commit") != COMMIT or self.ready.get("model_revision") != MODEL_REVISION
                or self.ready.get("protocol") != "headroom-task-worker-v1"
                or self.ready.get("worker_sha256") != self.worker_sha256):
            raise ValueError("wrong comparator worker")
        (self.directory / "ready.json").write_text(json.dumps(self.ready, indent=2), encoding="utf-8")
        return self.ready

    def rpc(self, operation, **values):
        if self.failed or self.finished or self._closed or self.process is None or self.ready is None:
            raise RuntimeError("comparator is not available")
        self.sequence += 1
        identifier = str(self.sequence)
        request = {"id": identifier, "op": operation, **values}
        raw = (json.dumps(request, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode()
        if len(raw) > MAX_FRAME:
            raise ValueError("comparator request too large")
        append_receipt(self.directory / "rpc.jsonl", {
            "id": identifier, "state": "pending", "request": request,
            "input_sha256": hashlib.sha256(raw).hexdigest(),
        })
        written: queue.Queue = queue.Queue()
        process = self.process

        def send():
            try:
                process.stdin.write(raw)
                process.stdin.flush()
                written.put(None)
            except Exception as error:
                written.put(error)

        threading.Thread(target=send, daemon=True).start()
        try:
            outcome = written.get(timeout=15)
            if isinstance(outcome, Exception):
                raise outcome
            response = self._receive(identifier, 120)
        except Exception:
            self.failed = True
            raise
        append_receipt(self.directory / "rpc.jsonl", {
            "id": identifier, "state": "completed", "response": response,
        })
        if operation == "finish":
            self.finished = True
        return response["result"]

    def prepare(self, chat, *, eligible_indices=None, frozen_message_count=0,
                keep_recent_tool_results=1, message_spans=None):
        strategy = self.strategy
        validate_strategy(strategy)
        if strategy == DEFAULT_STRATEGY:
            if (eligible_indices is not None or frozen_message_count != 0
                    or keep_recent_tool_results != 1 or message_spans is not None):
                raise ValueError("unused_headroom_document_controls")
            result = self.rpc("compress", model=chat["model"], messages=chat["messages"])
        else:
            if (type(eligible_indices) is not list or not eligible_indices
                    or any(type(i) is not int or not 0 <= i < len(chat["messages"])
                           for i in eligible_indices)
                    or eligible_indices != sorted(set(eligible_indices))
                    or type(frozen_message_count) is not int
                    or not 0 <= frozen_message_count <= len(chat["messages"])
                    or type(keep_recent_tool_results) is not int or keep_recent_tool_results < 1):
                raise ValueError("invalid_headroom_document_controls")
            controls = {
                "model": chat["model"], "messages": chat["messages"],
                "eligible_indices": eligible_indices, "frozen_message_count": frozen_message_count,
                "keep_recent_tool_results": keep_recent_tool_results,
            }
            span_digest = None
            span_contract = None
            if strategy == PREPROTECTION_STRATEGY:
                from .headroom_worker import SPAN_CONTRACT, preprotection_indices
                span_contract = SPAN_CONTRACT
                operation = "compress_documents_preprotected"
                controls.update(span_contract=SPAN_CONTRACT, message_spans=message_spans)
                # Reuse the worker's pure mechanical validator. This internal
                # protocol label is not a claimed native executor/tool-call ID.
                preprotection_indices({"id": "parent-preflight", "op": operation, **controls})
                span_digest = hashlib.sha256(json.dumps(
                    message_spans, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                    allow_nan=False).encode("utf-8")).hexdigest()
            else:
                if message_spans is not None:
                    raise ValueError("unused_headroom_preprotection_controls")
                operation = "compress_documents"
            result = self.rpc(operation, **controls)
            manifest = result.get("strategy_manifest")
            encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False, allow_nan=False)
            expected_protect = sorted(set(range(len(chat["messages"]))) - set(eligible_indices))
            if (result.get("strategy") != strategy or type(manifest) is not dict
                    or result.get("strategy_manifest_sha256")
                    != hashlib.sha256(encoded.encode("utf-8")).hexdigest()
                    or type(result.get("eligible_indices")) is not list
                    or any(type(index) is not int for index in result["eligible_indices"])
                    or result["eligible_indices"] != eligible_indices
                    or type(result.get("protected_indices")) is not list
                    or any(type(index) is not int for index in result["protected_indices"])
                    or result["protected_indices"] != expected_protect
                    or self._strategy_manifest is not None and self._strategy_manifest != encoded):
                self.failed = True
                raise ValueError("headroom_document_manifest_mismatch")
            if strategy == PREPROTECTION_STRATEGY and (
                    manifest.get("strategy") != strategy
                    or result.get("span_contract") != span_contract
                    or result.get("message_spans_sha256") != span_digest
                    or json.dumps(result.get("document_request"), sort_keys=True, allow_nan=False)
                    != json.dumps({"frozen_message_count": frozen_message_count,
                                   "keep_recent_tool_results": keep_recent_tool_results},
                                  sort_keys=True, allow_nan=False)):
                self.failed = True
                raise ValueError("headroom_document_manifest_mismatch")
            if self._strategy_manifest is None:
                with (self.directory / "document-strategy.json").open("x", encoding="utf-8") as handle:
                    json.dump({"strategy": strategy, "manifest": manifest,
                               "sha256": result["strategy_manifest_sha256"]}, handle,
                              ensure_ascii=False, indent=2, allow_nan=False)
                    handle.write("\n")
                self._strategy_manifest = encoded
        return {"model": chat["model"], "messages": result["messages"]}

    def retrieve(self, arguments, tool_call_id):
        """Return vendor content unchanged; it may be a fragment or an error."""
        if type(arguments) is not dict or set(arguments) != {"hash"}:
            raise ValueError("invalid retrieval arguments")
        if self.strategy == PREPROTECTION_STRATEGY:
            # Eager component readiness alone leaves the worker's compression
            # strategy unselected. Never let a new-mode retrieval fall through
            # its legacy handler before a validated new-mode prepare handshake.
            try:
                manifest = parse_json(self._strategy_manifest)
            except (ValueError, TypeError, RecursionError):
                manifest = None
            if type(manifest) is not dict or manifest.get("strategy") != PREPROTECTION_STRATEGY:
                raise ValueError("headroom_preprotection_recovery_not_initialized")
        result = self.rpc("retrieve", hash=arguments["hash"], tool_call_id=tool_call_id)
        if result["tool_call_id"] != tool_call_id or result["tool_name"] != "headroom_retrieve":
            self.failed = True
            raise ValueError("retrieval call identity changed")
        return result["content"]

    def finish(self):
        """Audit vendor-stored payloads after the task, not necessarily full files."""
        return self.rpc("finish")

    def close(self):
        """Bounded exact-owned cleanup; defer cancellation until all stages run.

        Only an interrupted container cleanup gets one reinspection attempt.
        A failed inspect is not absence. Interruptions remain incomplete even
        when best-effort cleanup succeeds, and the first cancellation is rethrown.
        A later close of the same frozen owner can reconcile verified absence;
        its prior receipt is archived before the latest receipt is replaced.
        """
        self._closed = True
        identity, label = self.identity, getattr(self, "label", None)
        prior = getattr(self, "_cleanup_receipt", None)
        repeated = prior is not None
        if prior is not None and (getattr(self, "_cleanup_owner", None) != (identity, label)
                                  or prior.get("container_id") != identity):
            raise ValueError("cleanup ownership changed between attempts")
        self._cleanup_owner = (identity, label)
        self._cleanup_attempts = getattr(self, "_cleanup_attempts", 0) + 1
        receipt: dict = {"container_id": identity, "finished": self.finished,
                         "failed": self.failed, "elapsed_seconds": time.monotonic() - self.started}
        if repeated:
            receipt["prior_cleanup_receipt"] = f"cleanup-attempt-{self._cleanup_attempts - 1}.json"
        history_preserved = not repeated
        # Preserve known state even if both bounded receipt-write attempts fail.
        self._cleanup_receipt = receipt
        error: BaseException | None = None
        interruption: BaseException | None = None

        def remember(failure, stage, key):
            nonlocal error, interruption
            receipt[key] = type(failure).__name__
            if isinstance(failure, Exception):
                if error is None:
                    error = failure
            else:
                if interruption is None:
                    interruption = failure
                receipt["cleanup_interrupted"] = True
                receipt.setdefault("interruptions", []).append({
                    "stage": stage, "error_type": type(failure).__name__})

        def owned_state(result):
            state = parse_json(result.stdout)[0]
            if (type(identity) is not str or re.fullmatch("[0-9a-f]{64}", identity) is None
                    or type(label) is not str or not label or state["Id"] != identity
                    or state["Config"]["Labels"].get("tokenmaster.parity") != label):
                raise ValueError("cleanup ownership mismatch")
            return state

        def clean_container(*, reinspection):
            if identity is None:
                return
            current = self.command(["inspect", identity], check=False)
            if current.returncode != 0:
                receipt["container_state"] = "unconfirmed"
                if reinspection:
                    if type(identity) is not str or re.fullmatch("[0-9a-f]{64}", identity) is None:
                        raise ValueError("cleanup ownership identity invalid")
                    # Read-only, exact full-ID scope. A command failure, matching
                    # row or unexpected output cannot establish absence.
                    found = self.command([
                        "ps", "--all", "--no-trunc", "--filter", "id=" + identity,
                        "--format", "{{.ID}}"], check=False)
                    if found.returncode == 0 and not found.stdout.strip():
                        receipt.update(container_state="absent", container_removed=True,
                                       container_absence_verified=True)
                return
            state = owned_state(current)
            if state["State"]["Running"]:
                self.command(["stop", "--time", "5", identity], timeout=20)
                state = owned_state(self.command(["inspect", identity]))
            if state["State"]["Running"]:
                raise RuntimeError("owned comparator did not stop")
            receipt["terminal_state"] = state["State"]
            receipt["container_removed"] = self.command(["rm", identity]).returncode == 0
            if receipt["container_removed"]:
                receipt.pop("container_state", None)

        if self.finished and self.process is not None:
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            except BaseException as failure:
                remember(failure, "attach_grace_wait", "attach_client_grace_error")
        for attempt in range(2):
            try:
                clean_container(reinspection=repeated or attempt == 1)
                break
            except BaseException as failure:
                remember(failure, "container_cleanup", "cleanup_error_type")
                receipt["container_state"] = "unknown"
                if isinstance(failure, Exception) or attempt == 1:
                    break

        # Each attach stage is independent of daemon cleanup and cancellation.
        # Only this object's own Popen is terminated/killed, never a PID search.
        if self.process is not None:
            reaped = False
            for action, timeout in ((None, 3), ("terminate", 5), ("kill", 5)):
                if action is not None:
                    try:
                        getattr(self.process, action)()
                    except BaseException as failure:
                        remember(failure, "attach_" + action, "attach_client_cleanup_error")
                try:
                    self.process.wait(timeout=timeout)
                    reaped = True
                    break
                except subprocess.TimeoutExpired as failure:
                    if action == "kill":
                        remember(failure, "attach_wait", "attach_client_cleanup_error")
                except BaseException as failure:
                    remember(failure, "attach_wait", "attach_client_cleanup_error")
            if reaped:
                receipt["attach_client_reaped"] = True
                receipt["attach_client_exit_code"] = self.process.returncode
            try:
                if self.process.poll() is not None and self.process.stdin is not None:
                    self.process.stdin.close()
            except BaseException as failure:
                remember(failure, "attach_stdin_close", "attach_stdin_close_error")
        if self.stderr is not None:
            try:
                self.stderr.close()
            except BaseException as failure:
                remember(failure, "stderr_close", "stderr_close_error")
        if self.worker_snapshot is not None:
            try:
                receipt["worker_snapshot_unchanged"] = (
                    hashlib.sha256(self.worker_snapshot.read_bytes()).hexdigest() == self.worker_sha256)
                if not receipt["worker_snapshot_unchanged"]:
                    raise ValueError("executed worker snapshot changed")
            except BaseException as failure:
                receipt["worker_snapshot_unchanged"] = False
                remember(failure, "worker_snapshot", "worker_snapshot_error")

        for attempt in range(2):
            receipt["complete"] = (
                error is None and interruption is None
                and (identity is None or receipt.get("container_removed") is True)
                and (self.process is None or receipt.get("attach_client_reaped") is True))
            try:
                # Archive the prior attempt before replacing the latest receipt.
                # Exclusive creation preserves cancellation history on retries;
                # archival failure leaves cleanup.json untouched and incomplete.
                if not history_preserved:
                    with (self.directory / receipt["prior_cleanup_receipt"]).open(
                            "x", encoding="utf-8") as stream:
                        json.dump(prior, stream, indent=2)
                        stream.flush()
                        os.fsync(stream.fileno())
                    history_preserved = True
                (self.directory / "cleanup.json").write_text(
                    json.dumps(receipt, indent=2), encoding="utf-8")
                break
            except BaseException as failure:
                remember(failure, "receipt_write", "receipt_write_error")
                receipt["complete"] = False
                if not history_preserved:
                    receipt["unarchived_prior_cleanup"] = prior
                if isinstance(failure, Exception) or attempt == 1:
                    break
        if interruption is not None:
            raise interruption
        if error is not None:
            raise error
        return receipt
