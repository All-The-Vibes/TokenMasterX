"""G08 Linux-only Codex transport cell. No real model, credentials or Desktop.

Host execution is opt-in (--execute); tests and receipt validation are offline.
Only the fixed evidence directory and labelled Docker resources are written.
The existing native_host_smoke fixture, installer and mock server do the work.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import time

VERSION = "0.147.0"
LABEL = "tokenmaster.g08.sidecar"
OWNER = "codex-linux-isolation-20261008"
NODE = "sha256:c72861c6705868ed7f08e1cf22ef4f7ba07a82c19a54ba65d931c442d3575889"
PYTHON = "sha256:72a58063c7563c5c64052da2becebce3f25b60055cb351b668c4e2df9153702c"
CODEX_ASSET = "codex-x86_64-unknown-linux-musl.tar.gz"
CODEX_SHA256 = "0246e2e773834e07f0fb5249ed6ebad12e4591e608f8c7bb97dd6a9690544c36"
ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": "/tmp/home", "TMPDIR": "/tmp", "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONUTF8": "1", "LANG": "C.UTF-8",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def immutable_id(value):
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", value):
        raise ValueError("full immutable image ID required")
    return value


def owned_output(path, repo):
    expected = repo.resolve() / "evidence" / OWNER
    if path.resolve() != expected or path.is_symlink():
        raise ValueError("output must be the exact task-owned evidence directory")
    return expected


def docker_environment(config):
    # Do not enumerate or read host credential variables or Docker auth config.
    result = {k: os.environ[k] for k in ("PATH", "SystemRoot", "WINDIR", "COMSPEC")
              if k in os.environ}
    result["DOCKER_CONFIG"] = str(config)
    result["DOCKER_BUILDKIT"] = "0"  # local FROM images; no registry resolution/pull
    return result


def dockerfile(python_tag):
    return f"""FROM {python_tag}
LABEL {LABEL}="{OWNER}"
# Official standalone Codex CLI {VERSION}; upstream archive SHA-256 checked before build.
COPY codex /usr/local/bin/codex
RUN chmod 755 /usr/local/bin/codex
COPY linux-runtime.lock.txt /opt/linux-runtime.lock.txt
RUN python -m pip --isolated install --no-deps --only-binary=:all: --no-cache-dir --index-url https://pypi.org/simple -r /opt/linux-runtime.lock.txt && python -m pip check
COPY plugin /app/plugin
COPY cl100k_base.tiktoken /app/cl100k_base.tiktoken
RUN printf 'tmcell:x:65532:65532:Task cell:/tmp/home:/bin/sh\\n' >> /etc/passwd && printf 'tmcell:x:65532:\\n' >> /etc/group
USER 65532:65532
WORKDIR /tmp
ENTRYPOINT ["/usr/bin/env"]
"""


def extract_codex(archive, target):
    if digest(archive) != CODEX_SHA256:
        raise ValueError("Codex archive differs from official pinned release digest")
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        if (len(members) != 1 or members[0].name != CODEX_ASSET.removesuffix(".tar.gz")
                or not members[0].isfile() or members[0].size > 300 * 1024 * 1024):
            raise ValueError("unexpected official CLI archive layout")
        source = bundle.extractfile(members[0])
        if source is None:
            raise ValueError("missing CLI archive member")
        with source, target.open("xb") as dest:
            shutil.copyfileobj(source, dest)


def owned_image(info, expected):
    if (info["Id"] != immutable_id(expected)
            or (info["Config"].get("Labels") or {}).get(LABEL) != OWNER
            or info.get("RepoTags")):
        raise ValueError("image cleanup identity/label/untagged ownership check failed")


def launch_args(image, output, name):
    immutable_id(image)
    output = output.resolve()
    if not output.is_dir() or "," in str(output) or output.name != "runtime":
        raise ValueError("exact existing runtime output directory required")
    return [
        "create", "--name", name, "--label", f"{LABEL}={OWNER}",
        "--network", "none", "--user", "65532:65532", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--read-only",
        "--pids-limit", "128", "--memory", "1g", "--memory-swap", "1g",
        "--cpus", "2", "--shm-size", "16m", "--ipc", "private",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=512m,mode=1777",
        "--mount", f"type=bind,source={output},target=/out",
        "--workdir", "/tmp", "--entrypoint", "/usr/bin/env", image,
        "-i", *(f"{k}={v}" for k, v in ENV.items()),
        "/usr/local/bin/python", "-B",
        "/app/plugin/evals/hosts/docker_codex_cli.py", "--inside",
    ]


def validate_container(info, image, output):
    """Fail before start, and again after exit, on any weaker launch boundary."""
    h, c = info["HostConfig"], info["Config"]
    checks = {
        "immutable_image": info["Image"] == immutable_id(image),
        "ownership_label": c.get("Labels", {}).get(LABEL) == OWNER,
        "non_root": c["User"] == "65532:65532",
        "network_none": h["NetworkMode"] == "none",
        "read_only_root": h["ReadonlyRootfs"] is True,
        "not_privileged": h["Privileged"] is False,
        "no_cap_add": not h.get("CapAdd"),
        "drop_all_caps": h["CapDrop"] == ["ALL"],
        "no_new_privileges": h["SecurityOpt"] == ["no-new-privileges"],
        "limits": h["PidsLimit"] == 128 and h["Memory"] == 1073741824
        and h["MemorySwap"] == 1073741824 and h["NanoCpus"] == 2000000000,
        "private_namespaces": h.get("PidMode", "") == "" and h["IpcMode"] == "private",
        "no_devices": not h.get("Devices") and not h.get("DeviceRequests"),
        "no_extra_mounts": not h.get("Binds") and not h.get("VolumesFrom"),
        "bounded_tmp": h["Tmpfs"] == {"/tmp": "rw,nosuid,nodev,size=512m,mode=1777"},
        "entrypoint": c["Entrypoint"] == ["/usr/bin/env"],
        "clean_process_environment": c["Cmd"] == launch_args(image, output, "unused")[
            launch_args(image, output, "unused").index(image) + 1:],
    }
    # Linux Docker Desktop converts the Windows source path. Compare against
    # the original source retained by HostConfig, not a guessed translated path.
    mounts = h.get("Mounts", [])
    checks["only_task_output_bind"] = len(mounts) == 1 and (
        mounts[0].get("Type") == "bind"
        and mounts[0].get("Source") == str(output.resolve())
        and mounts[0].get("Target") == "/out"
        and not mounts[0].get("ReadOnly", False)
    )
    actual = [m for m in info.get("Mounts", []) if m["Type"] != "tmpfs"]
    checks["no_implicit_volumes"] = len(actual) == 1 and actual[0]["Destination"] == "/out"
    checks["no_ports"] = not h.get("PortBindings")
    if not all(checks.values()):
        raise ValueError(f"unsafe container receipt: {checks}")
    return checks


def correlate(requests, responses, actions, original):
    """Require exact recovery in the result of the provider's own retrieve call."""
    from native_host_smoke import dictionaries

    wanted = [a for a in actions if a["name"].endswith("brainspace_retrieve")]
    if len(wanted) != 1:
        return False
    action = wanted[0]
    sent = [(i, item) for i, r in enumerate(responses)
            for item in r["events"][-1][1]["response"]["output"]
            if item.get("type") == "function_call" and item.get("call_id") == action["call_id"]
            and item.get("name") == action["name"]
            and json.loads(item["arguments"]) == action["arguments"]]
    if len(sent) != 1:
        return False
    for request in requests[sent[0][0] + 1:]:
        for item in request["body"].get("input", []):
            if item.get("type") != "function_call_output" or item.get("call_id") != action["call_id"]:
                continue
            pages = [d for d in dictionaries(item.get("output"))
                     if d.get("ok") is True and d.get("complete") is True
                     and d.get("content") == original]
            if pages and not any(d.get("isError") is True for d in dictionaries(item.get("output"))):
                return True
    return False


def inside():
    """Wrap the existing smoke; capture generated mock responses without a new server."""
    import native_host_smoke as smoke

    output = Path("/out")
    status = dict(line.split(":\t", 1) for line in Path("/proc/self/status").read_text().splitlines()
                  if ":\t" in line)
    boundary = {
        "uid": os.getuid(), "gid": os.getgid(), "environment": dict(os.environ),
        "cap_effective": status["CapEff"], "cap_permitted": status["CapPrm"],
        "cap_bounding": status["CapBnd"], "no_new_privs": status["NoNewPrivs"],
        "interfaces": sorted(p.name for p in Path("/sys/class/net").iterdir()),
        "docker_socket_present": Path("/var/run/docker.sock").exists(),
        "mountinfo": Path("/proc/self/mountinfo").read_text(),
    }
    save(output / "process-boundary.json", boundary)
    if (boundary["uid"] != 65532 or boundary["gid"] != 65532
            or any(int(boundary[k], 16) for k in ("cap_effective", "cap_permitted", "cap_bounding"))
            or boundary["no_new_privs"] != "1" or boundary["interfaces"] != ["lo"]
            or boundary["docker_socket_present"] or dict(os.environ) != ENV):
        raise RuntimeError("in-container isolation preflight failed")
    records = []
    original_type = smoke.MockProvider

    class CapturedProvider(original_type):
        def responses(self, action, request):
            events = super().responses(action, request)
            records.append({"request_index": len(self.requests) - 1,
                            "action": action, "events": events})
            return events

    smoke.MockProvider = CapturedProvider
    try:
        result = smoke.run_scenario("codex", "mcp", output, sys.executable,
                                    Path("/app/cl100k_base.tiktoken"), 90)
    finally:
        smoke.MockProvider = original_type
        save(output / "provider-responses.json", records)
    save(output / "native-result.json", result)
    request_path = output / "codex-mcp" / "provider-requests.json"
    requests = json.loads(request_path.read_text()) if request_path.exists() else []
    original = json.dumps({"marker": "TOKENMASTER_SYNTHETIC_TRANSPORT",
                           "rows": [{"index": i, "value": "synthetic item"} for i in range(25)]}, indent=4)
    # Independently record the exact original, not a nested matching schema string.
    (output / "known-original.json").write_text(original, encoding="utf-8")
    listing = result.get("native_mcp_list", {})
    try:
        listed = json.loads(listing.get("stdout", ""))
    except ValueError:
        listed = []
    checks = {
        "existing_smoke_passed": result.get("status") == "passed",
        "existing_runtime_acceptance": result.get("runtime_acceptance_verified") is True,
        "pinned_native_version": result.get("version") == f"codex-cli {VERSION}",
        "native_mcp_list": listing.get("exit_code") == 0 and not listing.get("timed_out")
        and any(x.get("name") == "brainspace" and x.get("enabled") is True for x in listed),
        "correlated_exact_recovery": correlate(requests, records, result.get("tool_calls_requested", []), original),
        "no_mock_errors": result.get("mock_errors") == [],
        "one_response_per_request": len(requests) == len(records) and bool(records),
    }
    versions = subprocess.run([sys.executable, "-m", "pip", "freeze", "--all"],
                              capture_output=True, text=True, check=True)
    (output / "python-freeze.txt").write_text(versions.stdout, encoding="utf-8")
    save(output / "qualification.json", {
        "scope": "Linux native CLI MCP transport with local MOCK provider only",
        "real_model_calls": 0, "model_quality_verified": False,
        "windows_gate_closed": False, "desktop_gate_closed": False,
        "original_sha256": hashlib.sha256(original.encode()).hexdigest(),
        "checks": checks, "passed": all(checks.values()),
    })
    return 0 if all(checks.values()) else 1


def prepare_context(repo, output):
    plugin = repo / "token-master-plugin"
    old = repo / "evidence/jev-implementation-20261004/native-host-smoke/codex-mcp-result.json"
    if json.loads(old.read_text(encoding="utf-8"))["version"] != f"codex-cli {VERSION}":
        raise ValueError("existing native receipt does not confirm CLI pin")
    context = output / "build-context"
    context.mkdir()
    skill = plugin / "skills/token-master"
    sources = [plugin / n for n in ("THIRD_PARTY_NOTICES.txt", "requirements-runtime.txt",
                                    "requirements-runtime.lock.txt")]
    sources += [skill / n for n in ("brainspace_setup.py", "brainspace_mcp.py",
                                   "brainspace_posttooluse.py", "brainspace_benchmark.py",
                                   "brainspace_tools.py", "token_efficiency.py")]
    sources += [p for folder in ("brainspace", "hosts") for p in (skill / folder).rglob("*.py")
                if "tests" not in p.relative_to(skill).parts]
    sources += [skill / "evals" / n for n in ("__init__.py", "synthetic_efficiency.py")]
    sources += [plugin / "evals/hosts" / n for n in
                ("native_host_smoke.py", "mock_provider.py", "docker_codex_cli.py")]
    inventory = {}
    for source in sources:
        if source.is_symlink():
            raise ValueError("symlink input refused")
        target = context / "plugin" / source.relative_to(plugin)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        inventory[str(source.relative_to(repo))] = digest(target)
    vocabulary = repo / "evidence/repository-diagnostic-20261007/live-v2/cl100k_base.tiktoken"
    shutil.copyfile(vocabulary, context / vocabulary.name)
    inventory[str(vocabulary.relative_to(repo))] = digest(context / vocabulary.name)
    evidence = repo / "evidence" / OWNER
    archive = evidence / CODEX_ASSET
    release_path = evidence / "official-codex-release.json"
    release = json.loads(release_path.read_text(encoding="utf-8-sig"))
    assets = [a for a in release["assets"] if a["name"] == CODEX_ASSET]
    if (release["tag_name"] != f"rust-v{VERSION}" or len(assets) != 1
            or assets[0]["digest"] != f"sha256:{CODEX_SHA256}"):
        raise ValueError("official release metadata does not match CLI pin")
    extract_codex(archive, context / "codex")
    inventory[str(archive.relative_to(repo))] = digest(archive)
    inventory[str(release_path.relative_to(repo))] = digest(release_path)
    # Preserve the source lock; pywin32 is the sole Windows-only omission.
    lock = (plugin / "requirements-runtime.lock.txt").read_text()
    pins = [s for raw in lock.splitlines() if (s := raw.strip()) and not s.startswith("#")]
    if not all(re.fullmatch(r"[a-z0-9-]+==[a-zA-Z0-9.]+", p) for p in pins):
        raise ValueError("only exact package pins supported")
    (context / "linux-runtime.lock.txt").write_text(
        "\n".join(p for p in pins if not p.startswith("pywin32==")) + "\n", encoding="utf-8")
    save(output / "source-manifest.json", inventory)
    save(output / "pin-provenance.json", {"prior_receipt": str(old), "sha256": digest(old),
         "codex_version": VERSION, "omitted_linux_inapplicable_pin": "pywin32==312",
         "codex_distribution": "official standalone Linux musl release; no npm dependencies",
         "codex_archive_sha256": CODEX_SHA256, "codex_binary_sha256": digest(context / "codex"),
         "new_dependency_categories": [], "inputs_are_snapshot_not_live_mount": True})
    return context, inventory


def execute(repo, attempt=1):
    root = owned_output(repo / "evidence" / OWNER, repo)
    root.mkdir(exist_ok=True)
    if not 1 <= attempt <= 99:
        raise ValueError("attempt must be 1..99")
    output = root / f"attempt-{attempt:03}"
    output.mkdir(exist_ok=False)
    # Every attempt is retained; do not overwrite a previous failure.
    with (output / "execution-start.json").open("x", encoding="utf-8") as stream:
        json.dump({"owner": OWNER, "real_model_calls_authorized": False}, stream)
    runtime = output / "runtime"
    runtime.mkdir()
    config = output / "docker-client"
    config.mkdir()
    save(config / "config.json", {"auths": {}})
    env = docker_environment(config)
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("Docker CLI unavailable")
    prefix = [docker, "--config", str(config),
              "--host", "npipe:////./pipe/dockerDesktopLinuxEngine"]
    counter = 0
    build_layers = []

    def command(args, timeout=120, check=True):
        nonlocal counter
        counter += 1
        argv = prefix + args
        started = time.monotonic()
        try:
            run = subprocess.run(argv, env=env, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=timeout)
            receipt = {"argv": argv, "exit_code": run.returncode,
                       "stdout": run.stdout, "stderr": run.stderr,
                       "seconds": round(time.monotonic() - started, 3)}
        except subprocess.TimeoutExpired as exc:
            receipt = {"argv": argv, "timed_out": True,
                       "stdout": (exc.stdout or b"").decode("utf-8", errors="replace"),
                       "stderr": (exc.stderr or b"").decode("utf-8", errors="replace")}
            save(output / f"command-{counter:03}.json", receipt)
            raise
        save(output / f"command-{counter:03}.json", receipt)
        if args[0] == "build":
            build_layers.extend(re.findall(r"^ ---> ([a-f0-9]{12,64})$", run.stdout, re.MULTILINE))
        if check and run.returncode:
            raise RuntimeError(
                f"command-{counter:03} failed: {run.stdout[-1800:]} {run.stderr[-500:]}")
        return run.stdout

    tags, image, cid = [], None, None
    final = {"passed": False, "scope": "Linux CLI MOCK transport only",
             "windows_gate_closed": False, "desktop_gate_closed": False,
             "real_model_calls": 0, "transport_verified": False}
    try:
        context, manifest = prepare_context(repo, output)
        command(["info", "--format", "{{.OSType}} {{.ServerVersion}}"])
        for suffix, base in (("python", PYTHON),):
            info = json.loads(command(["image", "inspect", base]))[0]
            if info["Id"] != base or info["Os"] != "linux" or info["Architecture"] != "amd64":
                raise ValueError("base image identity/platform mismatch")
            tag = f"tokenmaster-g08-{suffix}:{OWNER}"
            # Never overwrite a pre-existing tag, even if it points to the same ID.
            if command(["image", "ls", "-q", tag]).strip():
                raise ValueError("task base tag already exists")
            command(["tag", base, tag])
            tags.append((tag, base))
        (context / "Dockerfile").write_text(dockerfile(tags[0][0]), encoding="utf-8")
        command(["build", "--pull=false", "--rm", "--force-rm",
                 "--label", f"{LABEL}={OWNER}", "--iidfile", str(output / "image.id"),
                 str(context)], timeout=600)
        image = immutable_id((output / "image.id").read_text().strip())
        image_info = json.loads(command(["image", "inspect", image]))[0]
        if image_info["Config"].get("Labels", {}).get(LABEL) != OWNER:
            raise ValueError("built image ownership label missing")
        cid = command(launch_args(image, runtime, OWNER)).strip()
        if not re.fullmatch(r"[a-f0-9]{64}", cid):
            raise ValueError("full container ID required")
        info = json.loads(command(["inspect", cid]))[0]
        final["launch_checks"] = validate_container(info, image, runtime)
        save(output / "container-before.json", info)
        command(["start", "--attach", cid], timeout=180, check=False)
        info = json.loads(command(["inspect", cid]))[0]
        save(output / "container-after.json", info)
        validate_container(info, image, runtime)
        if info["State"]["Running"]:
            raise RuntimeError("container still running")
        qualification = runtime / "qualification.json"
        final["native"] = json.loads(qualification.read_text()) if qualification.exists() else None
        final["source_unchanged"] = all(digest(repo / p) == h for p, h in manifest.items())
        final["passed"] = (info["State"]["ExitCode"] == 0 and not info["State"]["OOMKilled"]
                           and bool(final["native"] and final["native"]["passed"])
                           and final["source_unchanged"])
        final["transport_verified"] = final["passed"]
    except Exception as exc:
        final["blocker"] = f"{type(exc).__name__}: {exc}"
    finally:
        # No prune, name-prefix enumeration, forced image removal or global cleanup.
        cleanup = []
        try:
            if cid and re.fullmatch(r"[a-f0-9]{64}", cid):
                owned = json.loads(command(["inspect", cid]))[0]
                if owned["Id"] != cid or owned["Config"].get("Labels", {}).get(LABEL) != OWNER:
                    raise ValueError("container cleanup identity changed")
                command(["rm", "-f", cid])
                cleanup.append({"container_removed": cid})
            if image:
                owned = json.loads(command(["image", "inspect", image]))[0]
                owned_image(owned, image)
                command(["image", "rm", image])
                cleanup.append({"image_removed": image})
            # Failed builds can leave intermediate images. Only consider IDs
            # emitted by this build, and require the early Dockerfile label.
            for layer in reversed(list(dict.fromkeys(build_layers))):
                if any(base.removeprefix("sha256:").startswith(layer) for base in (NODE, PYTHON)):
                    continue
                raw = command(["image", "inspect", layer], check=False)
                remaining = json.loads(raw) if raw.strip() else []
                if not remaining:
                    continue
                owned = remaining[0]
                owned_image(owned, owned["Id"])
                command(["image", "rm", owned["Id"]])
                cleanup.append({"build_layer_removed": owned["Id"]})
            for tag, base in tags:
                info = json.loads(command(["image", "inspect", tag]))[0]
                if info["Id"] != base:
                    raise ValueError("base tag cleanup identity changed")
                command(["image", "rm", tag])
                cleanup.append({"task_tag_removed": tag, "base_preserved": base})
            for base in (NODE, PYTHON):
                command(["image", "inspect", base, "--format", "{{.Id}}"])
        except Exception as exc:
            final["cleanup_blocker"] = str(exc)
            final["passed"] = False
        final["cleanup"] = cleanup
        save(output / "summary.json", final)
        files = {str(p.relative_to(output)): digest(p) for p in output.rglob("*")
                 if p.is_file() and p.name != "evidence-sha256.json"}
        save(output / "evidence-sha256.json", files)
    print(json.dumps(final, indent=2))
    return 0 if final["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--inside", action="store_true")
    parser.add_argument("--attempt", type=int, default=1)
    args = parser.parse_args()
    if args.inside and sys.platform == "linux" and Path("/out").is_dir():
        return inside()
    if args.execute and not args.inside:
        return execute(Path(__file__).resolve().parents[3], args.attempt)
    parser.error("explicit --execute required on host; --inside is container-only")


if __name__ == "__main__":
    raise SystemExit(main())
