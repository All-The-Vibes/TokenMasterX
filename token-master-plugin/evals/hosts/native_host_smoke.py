"""Isolated native-host smoke harness: synthetic mock-provider transport ONLY.

No real auth is copied or inherited. All host homes, cwd, caches and stores are
temporary. Explicit provider URLs point to loopback. No model quality is tested.
Use --inventory first; evidence belongs to the caller-selected output directory.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import sys

from mock_provider import MockProvider

SKILL = Path(__file__).resolve().parents[2] / "skills" / "token-master"
EVAL = Path(__file__).resolve().parent


def clean_environment(root):
    """Allowlist OS executable-discovery essentials, never provider credentials."""
    env = {key: os.environ[key] for key in
           ("PATH", "PATHEXT", "SystemRoot", "SYSTEMROOT", "WINDIR", "COMSPEC")
           if key in os.environ}
    for key, folder in {
        "HOME": "home", "USERPROFILE": "home", "APPDATA": "appdata",
        "LOCALAPPDATA": "localappdata", "XDG_CONFIG_HOME": "xdg-config",
        "XDG_CACHE_HOME": "xdg-cache", "XDG_DATA_HOME": "xdg-data",
        "CLAUDE_CONFIG_DIR": "claude", "CLAUDE_HOME": "claude",
        "CODEX_HOME": "codex", "COPILOT_HOME": "copilot",
        "TEMP": "temp", "TMP": "temp",
    }.items():
        path = root / folder
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    env.update({
        "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1",
        "DO_NOT_TRACK": "1", "NO_COLOR": "1", "CI": "true",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(root / "empty-gitconfig"),
    })
    return env


def discover(host):
    if host == "claude":
        executable = shutil.which("claude")
        return [executable] if executable else None
    package, script = ("@openai/codex", "bin/codex.js") if host == "codex" else ("@github/copilot", "npm-loader.js")
    shim = shutil.which(host + ".cmd") if os.name == "nt" else shutil.which(host)
    if shim and os.name == "nt":
        js = Path(shim).parent / "node_modules" / package / script
        node = shutil.which("node")
        if node and js.is_file():
            return [node, str(js)]
    if shim and Path(shim).suffix not in (".cmd", ".ps1"):
        return [shim]
    return None


def invoke(argv, env, cwd, timeout=45):
    started = time.monotonic()
    job = None
    if os.name == "nt":
        # pywin32 is already in the pinned MCP runtime. A private kill-on-close
        # job cleans descendants even if the CLI exits before its MCP children.
        import win32job
        job = win32job.CreateJobObject(None, "")
        limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
        limits["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                               start_new_session=os.name != "nt")
    if job is not None:
        try:
            win32job.AssignProcessToJobObject(job, int(process._handle))
        except Exception:
            process.kill()
            process.communicate(timeout=10)
            job.Close()
            raise
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if os.name == "nt":
            job.Close()
            job = None
        else:
            import signal
            os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=15)
    finally:
        if job is not None:
            job.Close()
    return {"argv": argv, "exit_code": process.returncode, "timed_out": timed_out,
            "process_tree_cleanup": "private-job-closed" if os.name == "nt" else "process-group",
            "seconds": round(time.monotonic() - started, 3),
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace")}


def inventory(output):
    results = {}
    with tempfile.TemporaryDirectory(prefix="tokenmaster-native-inventory-") as temp:
        root = Path(temp).resolve()
        if root.parent != Path(tempfile.gettempdir()).resolve() or not root.name.startswith("tokenmaster-native-inventory-"):
            raise RuntimeError("temporary-directory ownership check failed")
        env = clean_environment(root)
        for host in ("claude", "codex", "copilot"):
            command = discover(host)
            if not command:
                results[host] = {"available": False}
                continue
            results[host] = {"available": True, "command": command,
                             "version": invoke(command + ["--version"], env, root),
                             "help": invoke(command + ["--help"], env, root)}
    output.mkdir(parents=True, exist_ok=True)
    (output / "inventory.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def strings(value):
    """Inspect nested native envelopes, including JSON serialized inside text."""
    if isinstance(value, str):
        yield value
        try:
            nested = json.loads(value)
            if not isinstance(nested, str):
                yield from strings(nested)
        except ValueError:
            pass
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def dictionaries(value):
    if isinstance(value, str):
        try:
            yield from dictionaries(json.loads(value))
        except ValueError:
            # Codex wraps MCP content in a timing header before serializing the
            # actual content array. Parse that observed native envelope exactly.
            if value.startswith("Wall time: ") and "\nOutput:\n" in value:
                yield from dictionaries(value.split("\nOutput:\n", 1)[1])
    elif isinstance(value, dict):
        yield value
        for item in value.values():
            yield from dictionaries(item)
    elif isinstance(value, list):
        for item in value:
            yield from dictionaries(item)


def provider_env(env, provider, host):
    env.update({
        "HTTP_PROXY": provider.url, "HTTPS_PROXY": provider.url,
        "NO_PROXY": "127.0.0.1,localhost,::1", "NODE_USE_ENV_PROXY": "1",
    })
    if host == "claude":
        env.update({"ANTHROPIC_BASE_URL": provider.url, "ANTHROPIC_API_KEY": "synthetic-not-a-real-key",
                    "ANTHROPIC_MODEL": "claude-sonnet-4-20250514", "ENABLE_TOOL_SEARCH": "false",
                    "DISABLE_PROMPT_CACHING": "1"})
    elif host == "copilot":
        env.update({"COPILOT_PROVIDER_BASE_URL": provider.url,
                    "COPILOT_PROVIDER_TYPE": "anthropic", "COPILOT_PROVIDER_API_KEY": "synthetic-not-a-real-key",
                    "COPILOT_MODEL": "claude-sonnet-4-20250514",
                    "COPILOT_OFFLINE": "true", "COPILOT_AUTO_UPDATE": "false"})


def configure_mcp(root, env, host, provider):
    """Only write harness-created temp configs. No normal host homes are used."""
    import tomllib
    home = Path(env[{"claude": "CLAUDE_CONFIG_DIR", "codex": "CODEX_HOME", "copilot": "COPILOT_HOME"}[host]])
    path = home / ("config.toml" if host == "codex" else ".claude.json" if host == "claude" else "mcp-config.json")
    data = tomllib.loads(path.read_text("utf-8")) if host == "codex" else json.loads(path.read_text("utf-8"))
    entry = data["mcp_servers" if host == "codex" else "mcpServers"]["brainspace"]
    entry["env"].update({"BRAINSPACE_WORKSPACE_ROOT": str(root / "workspace"),
                         "BRAINSPACE_SESSION_ID": "native-smoke"})
    if host == "codex":
        text = ('model = "gpt-5.4"\nmodel_provider = "smoke"\napproval_policy = "never"\n'
                'sandbox_mode = "read-only"\nmodel_reasoning_effort = "low"\n'
                'mcp_optional_startup_grace_ms = 0\n'
                '[model_providers.smoke]\nname = "Loopback synthetic provider"\n'
                f'base_url = {json.dumps(provider.url + "/v1")}\n'
                'wire_api = "responses"\nrequires_openai_auth = false\n'
                'supports_websockets = false\nrequest_max_retries = 0\nstream_max_retries = 0\n'
                '[mcp_servers.brainspace]\nenabled = true\nrequired = true\nstartup_timeout_sec = 30\n'
                'default_tools_approval_mode = "approve"\n'
                'enabled_tools = ["brainspace_stats", "brainspace_retrieve"]\n')
        for key, value in entry.items():
            if isinstance(value, dict):
                text += key + " = {" + ", ".join(json.dumps(k) + " = " + json.dumps(v) for k, v in value.items()) + "}\n"
            else:
                text += key + " = " + json.dumps(value) + "\n"
        path.write_text(text, encoding="utf-8")
    else:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def run_scenario(host, scenario, output, python, tokenizer, timeout):
    record = {"schema_version": 1, "host": host, "scenario": scenario,
              "evidence_kind": "mock-provider-transport-only", "model_quality_verified": False,
              "runtime_acceptance_verified": False, "status": "blocked", "assertions": {}}
    if host == "codex-desktop":
        record["blocker"] = "Desktop is explicitly out of scope; no running desktop was manipulated."
        return record
    if scenario == "hook" and host != "claude":
        record["blocker"] = "Only Claude replacement is implemented; no equivalent replacement claimed."
        return record
    command = discover(host)
    if not command:
        record["blocker"] = "Native CLI unavailable"
        return record
    destination = output / f"{host}-{scenario}"
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tokenmaster-native-smoke-") as temp:
        root = Path(temp).resolve()
        # Verify cleanup ownership before TemporaryDirectory's recursive removal.
        if root.parent != Path(tempfile.gettempdir()).resolve() or not root.name.startswith("tokenmaster-native-smoke-"):
            raise RuntimeError("temporary-directory ownership check failed")
        env = clean_environment(root)
        workspace = root / "workspace"
        workspace.mkdir()
        fixture = json.dumps({"marker": "TOKENMASTER_SYNTHETIC_TRANSPORT",
                              "rows": [{"index": i, "value": "synthetic item"} for i in range(25)]}, indent=4)
        fixture_path = workspace / "synthetic.json"
        fixture_path.write_text(fixture, encoding="utf-8")
        env.update({"BRAINSPACE_WORKSPACE_ROOT": str(workspace), "BRAINSPACE_SESSION_ID": "native-smoke"})
        install = invoke([python, "-X", "utf8", str(SKILL / "brainspace_setup.py"), "--host", host,
                          "--python", python, "--tokenizer-file", str(tokenizer)], env, workspace, timeout=45)
        (destination / "install.json").write_text(json.dumps(install, indent=2), encoding="utf-8")
        if install["exit_code"]:
            record["blocker"] = "isolated installer failed; see install.json"
            return record
        home = Path(env[{"claude": "CLAUDE_CONFIG_DIR", "codex": "CODEX_HOME", "copilot": "COPILOT_HOME"}[host]])
        installed = home / "token-master"
        record["tested_file_sha256"] = {
            name: hashlib.sha256((installed / name).read_bytes()).hexdigest()
            for name in ("brainspace_mcp.py", "brainspace_posttooluse.py", "brainspace/host_output.py",
                         "brainspace/router.py", "brainspace/tokens.py", "brainspace/ccr.py")
            if (installed / name).is_file()
        }
        env["BRAINSPACE_TOKENIZER_FILE"] = str(installed / "tokenizer" / "cl100k_base.tiktoken")
        seed_code = ("import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
                     "from brainspace.ccr import CCR; "
                     "print(CCR(workspace_root=sys.argv[2],session_id='native-smoke').stash("
                     "Path(sys.argv[3]).read_text(encoding='utf-8'),ctype='json',source='synthetic',kind='root'))")
        seed = invoke([python, "-X", "utf8", "-c", seed_code, str(installed), str(workspace), str(fixture_path)], env, workspace)
        if seed["exit_code"]:
            record["blocker"] = "synthetic reference seeding failed"
            record["seed"] = seed
            return record
        reference = seed["stdout"].strip()
        hook_log = root / "hook-observations.jsonl"
        with MockProvider(scenario, fixture_path, reference) as provider:
            provider_env(env, provider, host)
            config = configure_mcp(root, env, host, provider)
            if host == "claude":
                settings = root / "explicit-settings.json"
                hook = {"type": "command", "command": python,
                        "args": ["-X", "utf8", str(EVAL / "hook_observer.py"), str(hook_log),
                                 str(installed / "brainspace_posttooluse.py"), python]}
                settings.write_text(json.dumps({"hooks": {"PostToolUse": [
                    {"matcher": "Read", "hooks": [hook]}]} if scenario == "hook" else {}}), encoding="utf-8")
                mcp = config if scenario == "mcp" else '{"mcpServers":{}}'
                argv = command + ["-p", "Run the synthetic transport fixture.", "--model", "claude-sonnet-4-20250514",
                                  "--output-format", "stream-json", "--verbose", "--no-session-persistence",
                                  "--setting-sources", "", "--settings", str(settings), "--strict-mcp-config",
                                  "--mcp-config", str(mcp), "--allowedTools",
                                  "Read" if scenario == "hook" else "mcp__brainspace__brainspace_stats,mcp__brainspace__brainspace_retrieve",
                                  "--tools", "Read" if scenario == "hook" else "",
                                  "--system-prompt", "Synthetic transport test; use only supplied local tools.",
                                  "--debug-file", str(root / "claude-debug.log")]
            elif host == "codex":
                record["native_mcp_list"] = invoke(command + ["mcp", "list", "--json"], env, workspace)
                argv = command + ["exec", "--skip-git-repo-check", "--ephemeral", "--json", "--ignore-rules",
                                  "-C", str(workspace), "Run the synthetic transport fixture."]
            else:
                argv = command + ["-p", "Run the synthetic transport fixture.", "--allow-all-tools",
                                  "--disable-builtin-mcps", "--no-auto-update", "--no-custom-instructions",
                                  "--no-ask-user", "--no-remote", "--no-remote-export",
                                  "--output-format", "json", "--stream", "off", "--log-level", "error"]
            record["version"] = invoke(command + ["--version"], env, workspace)["stdout"].strip()
            execution = invoke(argv, env, workspace, timeout=timeout)
            record["process"] = execution
            record["provider_requests"] = len(provider.requests)
            record["tool_calls_requested"] = provider.actions
            record["mock_errors"] = provider.errors
            requests = list(provider.requests)
        # Windows Codex may discover the OS user's .agents skill catalog despite
        # redirected homes. Keep its content out of artifacts and fail the strict
        # isolation gate, without hiding the separately observed transport result.
        recorded_requests = copy.deepcopy(requests)
        external_catalogs = []
        for request in recorded_requests:
            for item in request["body"].get("input", []):
                if not isinstance(item, dict):
                    continue
                for block in item.get("content", []) if isinstance(item.get("content"), list) else []:
                    text = block.get("text", "") if isinstance(block, dict) else ""
                    if "<skills_instructions>" in text and "/.agents/skills" in text:
                        digest = hashlib.sha256(text.encode()).hexdigest()
                        external_catalogs.append(digest)
                        block["text"] = f"[REDACTED non-fixture OS-user skill catalog; sha256={digest}]"
        record["isolation"] = {"temporary_host_configs_and_state": True,
                               "real_auth_copied_or_supplied": False,
                               "external_skill_catalog_observed": bool(external_catalogs)}
        (destination / "provider-requests.json").write_text(json.dumps(recorded_requests, indent=2), encoding="utf-8")
        if hook_log.exists():
            observations = [json.loads(line) for line in hook_log.read_text("utf-8").splitlines()]
            (destination / "hook-observations.json").write_text(json.dumps(observations, indent=2), encoding="utf-8")
        else:
            observations = []
        if (root / "claude-debug.log").exists():
            (destination / "claude-debug.log").write_bytes((root / "claude-debug.log").read_bytes())
        if scenario == "hook":
            eligible = [o for o in observations if o["output"]]
            if eligible:
                observation = eligible[0]
                original = observation["input"]["tool_response"]["file"]["content"]
                updated = json.loads(observation["output"])["hookSpecificOutput"]["updatedToolOutput"]["file"]["content"]
                subsequent = requests[1:]
                values = list(strings(subsequent))
                record["assertions"] = {
                    "hook_emitted_replacement": updated != original,
                    "json_semantics_preserved": json.loads(original) == json.loads(updated),
                    "replacement_in_provider_request": any(updated in value for value in values),
                    "raw_original_absent_after_hook": not any(original in value for value in values),
                    "native_process_exited": execution["exit_code"] == 0 and not execution["timed_out"],
                }
                record["original_sha256"] = hashlib.sha256(original.encode()).hexdigest()
                record["replacement_sha256"] = hashlib.sha256(updated.encode()).hexdigest()
            else:
                record["blocker"] = "No nonempty native hook replacement captured; inspect hook/provider/debug evidence."
        else:
            returned = [d for request in requests for d in dictionaries(request["body"])
                        if d.get("ok") is True and d.get("content") == fixture and d.get("complete") is True]
            record["assertions"] = {
                "native_tool_schema_listed": all(any(a["name"].endswith(name) for a in record["tool_calls_requested"])
                                                for name in ("brainspace_stats", "brainspace_retrieve")),
                "public_retrieve_exact_original_in_provider_request": bool(returned),
                "native_process_exited": execution["exit_code"] == 0 and not execution["timed_out"],
            }
        passed = bool(record["assertions"]) and all(record["assertions"].values())
        record["transport_verified"] = passed
        record["runtime_acceptance_verified"] = passed and not external_catalogs
        record["status"] = "passed" if passed else "blocked" if execution["timed_out"] or record.get("blocker") else "failed"
        if external_catalogs:
            record["status"] = "blocked"
            record["blocker"] = ("Native transport evaluated separately, but this Windows Codex build discovers OS-user "
                                 ".agents/skills despite redirected homes. Strict user-skill isolation is unverified. "
                                 "Catalog bodies were redacted from saved requests; no real auth was copied or supplied.")
        record["temp_state_removed_on_return"] = True
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--host", choices=("claude", "codex", "copilot", "codex-desktop"), default="claude")
    parser.add_argument("--scenario", choices=("hook", "mcp"), default="hook")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--tokenizer-file", type=Path)
    parser.add_argument("--timeout", type=int, default=75)
    args = parser.parse_args()
    if args.inventory:
        results = inventory(args.output.resolve())
        print(json.dumps({name: {"available": info["available"],
                                "version": info.get("version", {}).get("stdout", "").strip(),
                                "exit_code": info.get("version", {}).get("exit_code")}
                          for name, info in results.items()}, indent=2))
        return 0
    if not args.tokenizer_file:
        parser.error("--tokenizer-file is required; acquisition is never implicit")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = run_scenario(args.host, args.scenario, output, args.python, args.tokenizer_file.resolve(), args.timeout)
    (output / f"{args.host}-{args.scenario}-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "process"}, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
