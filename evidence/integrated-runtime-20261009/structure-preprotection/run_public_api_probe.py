"""Explicit one-shot local public-API probe in the existing pinned image.

No image download, provider/native-client call, normal Docker config or broad
cleanup. Preparation freezes inputs only. Run requires an explicit flag and
uses the production container boundary/owned-cleanup validator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SKILL = ROOT / "token-master-plugin/skills/token-master"
CACHE = ROOT / "evidence/headroom-model-readiness-20261008/model-cache"
ASSETS = ROOT / "evidence/integrated-runtime-20261008/installed-cross-documents-001/headroom-assets.json"
PROBE = HERE / "public_api_probe.py"


def load(path):
    return json.loads(path.read_text("utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def require(value, reason):
    if not value:
        raise ValueError(reason)


def retain(original, later):
    if original is None:
        return later
    if isinstance(original, Exception) and not isinstance(later, Exception):
        later.add_note("earlier_failure:" + type(original).__name__)
        return later
    original.add_note("later_failure:" + type(later).__name__)
    return original


def output_path(value):
    path = Path(value).absolute()
    require(path.resolve() == path and path.is_relative_to(HERE / "public-api-runs")
            and path != HERE / "public-api-runs", "new_probe_child_output_required")
    return path


def prepare(args):
    output = output_path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    sources = {
        str(path): sha(path) for path in (
            Path(__file__), PROBE, SKILL / "brainspace/headroom.py",
            SKILL / "brainspace/headroom_worker.py",
            SKILL / "brainspace/document_structure.py", SKILL / "brainspace/protected_text.py", ASSETS,
        )
    }
    for name, source in (("worker.py", SKILL / "brainspace/headroom_worker.py"),
                         ("probe.py", PROBE)):
        with (output / name).open("xb") as stream:
            stream.write(source.read_bytes())
    docker_config = output / "docker-config"
    docker_config.mkdir()
    save(docker_config / "config.json", {})
    plan = {
        "version": "headroom-public-api-controlled-probe-v1", "sources": sources,
        "snapshots": {name: sha(output / name) for name in ("worker.py", "probe.py")},
        "label": "preprotect-public-" + uuid.uuid4().hex[:20],
        "cache": str(CACHE), "assets": str(ASSETS), "python": str(Path(sys.executable).resolve()),
        "python_sha256": sha(Path(sys.executable)), "timeout_seconds": 180,
        "real_primary_model_calls": 0, "neural_compressor": "controlled_double",
        "detector": "controlled_double", "read_only_root": True, "network": "none",
        "no_image_download": True, "preserve_all_outputs": True, "no_retry": True,
        "scope": "public-API mechanics, not learned compression or task savings",
    }
    save(output / "plan.json", plan)
    save(output / "plan-seal.json", {"sha256": sha(output / "plan.json")})
    print(json.dumps({"prepared": str(output), "plan_sha256": sha(output / "plan.json"),
                      "container_or_model_calls": 0}))


def validate(output, plan):
    require(sha(output / "plan.json") == load(output / "plan-seal.json")["sha256"], "plan_drift")
    require(str(Path(sys.executable).resolve()) == plan["python"]
            and sha(Path(sys.executable)) == plan["python_sha256"], "interpreter_drift")
    for path, expected in plan["sources"].items():
        require(sha(Path(path)) == expected, "source_drift")
    for name, expected in plan["snapshots"].items():
        require(sha(output / name) == expected, "snapshot_drift")
    require(load(output / "docker-config/config.json") == {}, "private_empty_docker_config_required")


def run(args):
    require(args.execute_offline_container_probe, "explicit_offline_probe_execution_required")
    output = output_path(args.output)
    plan = load(output / "plan.json")
    validate(output, plan)
    save(output / "started.json", {"container_probe": True, "real_primary_model_calls": 0})
    sys.path.insert(0, str(SKILL))
    from brainspace.headroom import (
        COMMIT, IMAGE_ID, HeadroomContainer, _task_environment, validate_container,
    )
    client = None
    error, process, parsed = None, None, None
    created_attempted = False
    stdout, stderr, cleanup = b"", b"", None
    cidfile = output / "container-id.txt"
    try:
        client = HeadroomContainer(
            output / "control", cache=plan["cache"], assets=plan["assets"],
            docker_config=output / "docker-config", label=plan["label"],
        )
        image = load_json(client.command(["image", "inspect", IMAGE_ID]).stdout)[0]
        require(image["Id"] == IMAGE_ID and image["Config"]["Labels"].get(
            "org.opencontainers.image.revision") == COMMIT, "image_pin_mismatch")
        mounts = {
            # The production boundary requires exactly python /inputs/worker.py.
            # That entry is the explicitly frozen probe here; the actual product
            # worker is a separate read-only import, never run via its main().
            "/inputs/worker.py": (output / "probe.py", False),
            "/inputs/product_worker.py": (output / "worker.py", False),
            "/inputs/assets.json": (Path(plan["assets"]), False),
            "/cache": (Path(plan["cache"]), False),
        }
        command = [
            "create", "-i", "--pull", "never", "--cidfile", str(cidfile),
            "--label", "tokenmaster.parity=" + plan["label"],
            "--user", "65532:65532", "--read-only", "--network", "none",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--cpus", "2", "--memory", "4g", "--memory-swap", "4g", "--pids-limit", "256",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=256m",
            "--tmpfs", "/home/nonroot/.headroom:rw,noexec,nosuid,nodev,size=64m",
            "--no-healthcheck", "--workdir", "/tmp", "--entrypoint", "python",
        ]
        for key, value in _task_environment(None).items():
            command.extend(("--env", key + "=" + value))
        for destination, (source, _) in mounts.items():
            command.extend(("--mount", f"type=bind,source={source},target={destination},readonly"))
        command.extend((IMAGE_ID, "/inputs/worker.py"))
        created_attempted = True
        made = client.command(command)
        identity = made.stdout.strip()
        require(re.fullmatch(r"[0-9a-f]{64}", identity) is not None
                and cidfile.read_text("utf-8").strip() == identity, "created_identity_mismatch")
        client.identity = identity
        client.worker_snapshot, client.worker_sha256 = output / "probe.py", plan["snapshots"]["probe.py"]
        actual = load_json(client.command(["inspect", identity]).stdout)[0]
        save(output / "container-inspect.json", actual)
        validate_container(actual, identity=identity, label=plan["label"], mounts=mounts)
        process = subprocess.Popen(
            client.base + ["start", "--attach", identity], env=client.environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        client.process = process
        stdout, stderr = process.communicate(timeout=plan["timeout_seconds"])
        require(len(stdout) <= 4_194_304 and len(stderr) <= 4_194_304, "probe_output_bound")
        require(process.returncode == 0, "container_probe_failed")
        parsed = load_json(stdout.decode("utf-8"))
        require(parsed.get("passed") is True, "probe_not_passed")
        from brainspace.document_structure import document_structure_preserved
        from brainspace.protected_text import restore_protected_text
        parent_checks = []
        for case in parsed["reports"]:
            restored = restore_protected_text(case["pristine_text"], case["candidate_text"])
            parent_checks.append({
                "case": case["case"], "fence_restoration_available": restored is not None,
                "structure_preserved": restored is not None and document_structure_preserved(
                    case["pristine_text"], restored),
            })
        save(output / "parent-guard-checks.json", parent_checks)
        require(all(item["structure_preserved"] for item in parent_checks), "parent_guard_rejected_candidate")
        client.finished = True
    except BaseException as failure:
        error = failure
    finally:
        if client is not None and client.identity is None and cidfile.exists():
            try:
                identity = cidfile.read_text("utf-8").strip()
                require(re.fullmatch(r"[0-9a-f]{64}", identity) is not None, "invalid_cidfile")
                client.identity = identity  # close rechecks full ID + exact ownership label.
            except BaseException as failure:
                error = retain(error, failure)
        if created_attempted and (client is None or client.identity is None):
            error = retain(error, RuntimeError("unconfirmed_create_outcome"))
        if client is not None:
            try:
                cleanup = client.close()
            except BaseException as failure:
                error = retain(error, failure)
        if process is not None:
            try:
                # After exact-owned cleanup this cannot leave a running container.
                remaining_out, remaining_err = process.communicate(timeout=10)
                stdout = remaining_out or stdout
                stderr = remaining_err or stderr
            except BaseException as failure:
                error = retain(error, failure)
        for name, value in (("stdout.txt", stdout), ("stderr.txt", stderr)):
            try:
                require(len(value) <= 4_194_304, "probe_output_bound")
                with (output / name).open("xb") as stream:
                    stream.write(value)
            except BaseException as failure:
                error = retain(error, failure)
        try:
            validate(output, plan)
        except BaseException as failure:
            error = retain(error, failure)
        summary = {
            "passed": error is None and type(cleanup) is dict and cleanup.get("complete") is True,
            "probe_result": parsed, "cleanup": cleanup,
            "error_type": type(error).__name__ if error else None,
            "real_primary_model_calls": 0, "task_quality": False, "savings_claim": False,
            "scope": plan["scope"],
        }
        try:
            save(output / "summary.json", summary)
        except BaseException as failure:
            error = retain(error, failure)
    if error is not None:
        raise error
    print(json.dumps({"passed": summary["passed"], "output": str(output),
                      "real_primary_model_calls": 0}))
    return 0 if summary["passed"] else 1


def load_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    def reject(_):
        raise ValueError("nonfinite_json")
    return json.loads(text, object_pairs_hook=unique, parse_constant=reject)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--output", required=True)
    execute = sub.add_parser("run")
    execute.add_argument("--output", required=True)
    execute.add_argument("--execute-offline-container-probe", action="store_true")
    options = parser.parse_args()
    raise SystemExit(prepare(options) if options.command == "prepare" else run(options))
