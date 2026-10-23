"""Host regression tests: never read or mutate a real host home."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
from concurrent.futures import ThreadPoolExecutor

import pytest

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL))


def load(name):
    spec = importlib.util.spec_from_file_location("test_" + name, SKILL / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def homes(tmp_path, monkeypatch):
    for var in ("HOME", "USERPROFILE", "CLAUDE_HOME", "CLAUDE_CONFIG_DIR",
                "COPILOT_HOME", "CODEX_HOME"):
        monkeypatch.setenv(var, str(tmp_path / var))
    monkeypatch.delenv("CLAUDE_CONFIG", raising=False)
    monkeypatch.delenv("TOKEN_MASTER_HOST", raising=False)
    return tmp_path


@pytest.fixture
def tokenizer_source(tmp_path, monkeypatch):
    """Read only a known public vocabulary asset; all test writes stay in temp."""
    from brainspace.tokens import VOCABULARY_SHA256, VOCABULARY_URL
    source = Path(os.environ.get("TOKENMASTER_TEST_TOKENIZER_FILE",
                  str(Path(tempfile.gettempdir()) / "data-gym-cache" /
                      hashlib.sha1(VOCABULARY_URL.encode()).hexdigest())))
    if not source.is_file():
        pytest.skip("prepare the verified public vocabulary locally and set TOKENMASTER_TEST_TOKENIZER_FILE")
    data = source.read_bytes()
    assert hashlib.sha256(data).hexdigest() == VOCABULARY_SHA256
    local = tmp_path / "source cache 工具.tiktoken"
    local.write_bytes(data)
    monkeypatch.setenv("BRAINSPACE_TOKENIZER_FILE", str(local))
    return local


@pytest.mark.parametrize("host", ["claude", "copilot", "codex"])
def test_host_roundtrip_preserves_unrelated(homes, host):
    from hosts import config_path, wire_mcp
    path = config_path(host)
    path.parent.mkdir(parents=True)
    original = 'model = "keep"\n# user comment\n' if host == "codex" else '{"theme":"keep"}\n'
    path.write_text(original, encoding="utf-8")
    entry = {"command": "C:\\工具 space\\python.exe", "args": ["-X", "utf8", "a b.py"],
             "env": {"PYTHONUTF8": "1"}}
    wire_mcp(host, "brainspace", entry)
    first = path.read_bytes()
    wire_mcp(host, "brainspace", entry)
    assert path.read_bytes() == first
    data = tomllib.loads(path.read_text("utf-8")) if host == "codex" else json.loads(first)
    assert data["mcp_servers" if host == "codex" else "mcpServers"]["brainspace"]["args"] == entry["args"]
    assert list(path.parent.glob(path.name + ".token-master-backup-*"))
    wire_mcp(host, "brainspace", None)
    assert path.read_text("utf-8") == original if host == "codex" else json.loads(path.read_bytes()) == {"theme": "keep"}


@pytest.mark.parametrize("host,bad", [("claude", "{bad"), ("copilot", '{"mcpServers": []}'),
                                     ("codex", "[broken"), ("claude", "[]"),
                                     ("copilot", ""), ("claude", '{"x":NaN}'),
                                     ("claude", '{"x":1,"x":2}')])
def test_bad_config_unchanged(homes, host, bad):
    from hosts import config_path, wire_mcp
    path = config_path(host)
    path.parent.mkdir(parents=True)
    path.write_text(bad, encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        wire_mcp(host, "brainspace", {"command": "python", "args": []})
    assert path.read_bytes() == before
    assert not list(path.parent.glob("*.token-master-backup-*"))


def test_unknown_owned_name_and_modified_entry_preserved(homes):
    from hosts import config_path, wire_mcp
    path = config_path("copilot")
    path.parent.mkdir(parents=True)
    path.write_text('{"mcpServers":{"brainspace":{"command":"other"}}}')
    with pytest.raises(ValueError):
        wire_mcp("copilot", "brainspace", {"command": "python"})
    assert json.loads(path.read_bytes())["mcpServers"]["brainspace"]["command"] == "other"
    with pytest.raises(ValueError):
        wire_mcp("copilot", "brainspace", None)


def test_concurrent_updates_do_not_lose_other_server(homes):
    from hosts import config_path, wire_mcp
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda n: wire_mcp("codex", n, {"command": "python", "args": [n]}),
                      ["one", "two", "three", "four"]))
    assert len(tomllib.loads(config_path("codex").read_text())["mcp_servers"]) == 4


def test_hook_preserves_neighbor_and_uninstall_without_runtime(homes):
    from hosts import host_home, wire_hook
    home = host_home("claude")
    home.mkdir(parents=True)
    path = home / "settings.json"
    neighbor = {"matcher": "*", "hooks": [{"type": "command", "command": "echo unrelated"}]}
    path.write_text(json.dumps({"hooks": {"PostToolUse": [neighbor]}, "theme": "dark"}))
    wire_hook(home, '"C:\\Python space\\python.exe" -X utf8 "C:\\插件\\hook.py" --host claude')
    wire_hook(home, None)
    assert json.loads(path.read_bytes()) == {"hooks": {"PostToolUse": [neighbor]}, "theme": "dark"}


def test_host_resolution_and_capability(homes):
    from hosts import capabilities, resolve_host
    assert resolve_host("codex") == "codex"
    with pytest.raises(ValueError):
        resolve_host("typo")
    cap = capabilities("codex")
    assert cap["configuration_clients"] == ["cli", "desktop"]
    assert cap["runtime_verified"] is False
    assert cap["transparent_replacement"] is False


def test_runtime_argv_unicode_no_network(homes, tmp_path):
    from hosts.runtime import runtime_entry, validate_runtime
    receipt = validate_runtime(sys.executable, ("mcp",))
    assert receipt["versions"]["mcp"]
    script = tmp_path / "space 工具.py"
    script.write_text("import sys; print('工具', sys.argv[1])", encoding="utf-8")
    entry = runtime_entry(sys.executable, str(script), ["quoted space"])
    assert "--with" not in entry["args"]
    result = subprocess.run([entry["command"], *entry["args"]], capture_output=True,
                            text=True, encoding="utf-8", check=True)
    assert result.stdout.strip() == "工具 quoted space"


def test_missing_runtime_dependency_fails_before_config(homes):
    from hosts.runtime import validate_runtime
    with pytest.raises(ValueError, match="runtime"):
        validate_runtime(sys.executable, ("definitely_missing_tokenmaster_dep",))


def test_runtime_rejects_mcp2_against_verified_pin(homes, monkeypatch):
    import hosts.runtime as runtime
    fake = {"python": sys.executable, "versions": {"mcp": "2.0.0"},
            "inventory": {"mcp": "2.0.0"}}
    monkeypatch.setattr(runtime.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps(fake)))
    with pytest.raises(ValueError, match="expected 1.27.2"):
        runtime.validate_runtime(sys.executable, ("mcp",))


@pytest.mark.parametrize("host", ["claude", "copilot", "codex"])
def test_brainspace_cli_install_and_uninstall(homes, tokenizer_source, monkeypatch, host):
    from hosts import config_path, host_home
    setup = load("brainspace_setup")
    monkeypatch.setattr(sys, "argv", ["brainspace_setup.py", "--host", host,
                                    "--python", sys.executable, "--tokenizer-file", str(tokenizer_source),
                                    *(["--brainspace-mcp"] if host == "copilot" else [])])  # opt-in for Copilot
    assert setup.main() == 0
    config = (tomllib.loads(config_path(host).read_text("utf-8")) if host == "codex"
              else json.loads(config_path(host).read_bytes()))
    servers_key = "mcp_servers" if host == "codex" else "mcpServers"
    entry = config[servers_key]["brainspace"]
    assert entry["command"] == str(Path(sys.executable).resolve())
    installed_vocab = Path(entry["env"]["BRAINSPACE_TOKENIZER_FILE"])
    assert installed_vocab.read_bytes() == tokenizer_source.read_bytes()
    if host == "claude":
        settings = json.loads((host_home(host) / "settings.json").read_bytes())
        assert settings["env"]["BRAINSPACE_TOKENIZER_FILE"] == str(installed_vocab)
        assert settings["hooks"]["PostToolUse"][0]["hooks"][0]["args"][-2:] == ["--host", "claude"]
    if host == "copilot":  # the v6 output hook is on by default
        saved = json.loads((host_home(host) / "settings.json").read_bytes())["hooks"]["postToolUse"][0]
        assert saved["matcher"] == "view" and "--contract" in saved["args"]
        skill = (host_home(host) / "skills" / "tokenomics" / "SKILL.md").read_text("utf-8")
        assert setup.TOKENOMICS_MARKER in skill and "name: tokenomics" in skill
        assert str(Path(sys.executable).resolve()) in skill and "tokenomics.py" in skill
        assert (host_home(host) / "token-master" / "tokenomics.py").is_file()
    # Invoke the actual installed offline tokenizer, not just the test source.
    code = ("import sys, json; sys.path.insert(0, sys.argv[1]); "
            "from brainspace.tokens import backend_info, count_tokens; "
            "assert backend_info()['exact_reference']; print(count_tokens('hello world'))")
    result = subprocess.run([sys.executable, "-X", "utf8", "-c", code,
                             str(host_home(host) / "token-master")],
                            capture_output=True, encoding="utf-8", check=True,
                            env={**os.environ, **entry["env"]})
    assert result.stdout.strip() == "2"
    monkeypatch.setattr(sys, "argv", ["brainspace_setup.py", "--host=" + host, "--uninstall",
                                    "--python", "missing.exe"])
    assert setup.main() == 0
    config = (tomllib.loads(config_path(host).read_text("utf-8")) if host == "codex"
              else json.loads(config_path(host).read_bytes()))
    assert "brainspace" not in config.get(servers_key, {})
    if host == "claude":
        settings = json.loads((host_home(host) / "settings.json").read_bytes())
        assert "BRAINSPACE_TOKENIZER_FILE" not in settings.get("env", {})
    if host == "copilot":
        settings = json.loads((host_home(host) / "settings.json").read_bytes())
        assert not settings.get("hooks", {}).get("postToolUse")
        assert not (host_home(host) / "skills" / "tokenomics").exists()


def test_copilot_tokenomics_skill_never_replaces_a_user_skill(homes, tokenizer_source, monkeypatch):
    from hosts import host_home
    mine = host_home("copilot") / "skills" / "tokenomics" / "SKILL.md"
    mine.parent.mkdir(parents=True)
    mine.write_text("---\nname: tokenomics\ndescription: my own\n---\n", encoding="utf-8")
    setup = load("brainspace_setup")
    for extra in ([], ["--uninstall"]):
        monkeypatch.setattr(sys, "argv", ["brainspace_setup.py", "--host", "copilot", "--python", sys.executable,
                                          "--tokenizer-file", str(tokenizer_source), *extra])
        assert setup.main() == 0
        assert mine.read_text("utf-8").endswith("description: my own\n---\n")


@pytest.mark.parametrize("argv,disabled", [(["--no-copilot-output-hook"], False), ([], True)])
def test_copilot_install_without_the_output_hook(homes, tokenizer_source, monkeypatch, argv, disabled):
    from hosts import config_path, host_home
    settings = host_home("copilot") / "settings.json"
    if disabled:  # hooks the user turned off stay off; the MCP server still installs
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text('{"disableAllHooks":true}', encoding="utf-8")
    setup = load("brainspace_setup")
    monkeypatch.setattr(sys, "argv", ["brainspace_setup.py", "--host", "copilot", "--python", sys.executable,
                                      "--tokenizer-file", str(tokenizer_source), *argv])
    assert setup.main() == 0
    servers = json.loads(config_path("copilot").read_bytes()).get("mcpServers", {}) \
        if config_path("copilot").is_file() else {}
    assert "brainspace" not in servers  # off for Copilot by default
    saved = json.loads(settings.read_bytes()) if settings.is_file() else {}
    assert not saved.get("hooks", {}).get("postToolUse")
    assert saved.get("disableAllHooks", False) is disabled


def test_copilot_brainspace_mcp_is_opt_in_and_reinstall_removes_an_owned_one(homes, tokenizer_source, monkeypatch):
    from hosts import config_path
    setup = load("brainspace_setup")
    base = ["brainspace_setup.py", "--host", "copilot", "--python", sys.executable, "--tokenizer-file",
            str(tokenizer_source), "--no-copilot-output-hook"]
    monkeypatch.setattr(sys, "argv", [*base, "--brainspace-mcp"])
    assert setup.main() == 0
    assert "brainspace" in json.loads(config_path("copilot").read_bytes())["mcpServers"]
    monkeypatch.setattr(sys, "argv", base)
    assert setup.main() == 0
    assert "brainspace" not in json.loads(config_path("copilot").read_bytes()).get("mcpServers", {})


@pytest.mark.parametrize("corrupt", [False, True])
def test_tokenizer_missing_or_corrupt_fails_before_config(homes, monkeypatch, corrupt):
    from hosts import config_path, host_home
    monkeypatch.delenv("BRAINSPACE_TOKENIZER_FILE", raising=False)
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(homes / "missing-cache"))
    setup = load("brainspace_setup")
    argv = ["brainspace_setup.py", "--host", "codex", "--python", sys.executable]
    if corrupt:
        path = homes / "corrupt.tiktoken"
        path.write_bytes(b"not the pinned vocabulary")
        argv.extend(["--tokenizer-file", str(path)])
    monkeypatch.setattr(sys, "argv", argv)
    assert setup.main() == 1
    assert not config_path("codex").exists()
    assert not (host_home("codex") / "token-master").exists()


@pytest.mark.parametrize("host", ["claude", "copilot", "codex"])
def test_user_edit_to_owned_setting_blocks_uninstall(homes, host):
    from hosts import config_path, wire_mcp
    path = config_path(host)
    wire_mcp(host, "brainspace", {"command": "original"})
    path.write_text(path.read_text().replace("original", "user-edit"), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="edited"):
        wire_mcp(host, "brainspace", None)
    assert path.read_bytes() == before


def test_toml_preserves_crlf_comments_and_other_tables(homes):
    from hosts import config_path, wire_mcp
    path = config_path("codex")
    path.parent.mkdir(parents=True)
    original = b'# keep\r\n[mcp_servers.other]\r\ncommand = "other"\r\n'
    path.write_bytes(original)
    wire_mcp("codex", "brainspace", {"command": "python", "args": ["C:\\space dir\\工具.py"]})
    wire_mcp("codex", "graphify-nav", {"command": "python"})
    before = path.read_bytes()
    wire_mcp("codex", "brainspace", {"command": "python", "args": ["C:\\space dir\\工具.py"]})
    assert path.read_bytes() == before
    wire_mcp("codex", "graphify-nav", None)
    wire_mcp("codex", "brainspace", None)
    assert path.read_bytes() == original


def test_atomic_failure_keeps_original_and_releases_lock(homes, monkeypatch):
    from hosts import config_path, wire_mcp
    import hosts.config as config
    path = config_path("copilot")
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"custom": "keep"}\r\n')
    before = path.read_bytes()
    replace = config.os.replace

    def fail_config(source, target):
        if Path(target) == path:
            raise OSError("injected write failure")
        return replace(source, target)
    monkeypatch.setattr(config.os, "replace", fail_config)
    with pytest.raises(OSError, match="injected"):
        wire_mcp("copilot", "brainspace", {"command": "python"})
    assert path.read_bytes() == before
    assert not path.with_name(path.name + ".token-master.lock").exists()
    assert not path.with_name(path.name + ".token-master-owned.json").exists()


def test_existing_lock_fails_closed(homes):
    from hosts.config import config_lock
    path = homes / "config.json"
    lock = path.with_name(path.name + ".token-master.lock")
    lock.write_text("other process")
    with pytest.raises(ValueError, match="busy"):
        with config_lock(path, timeout=0):
            pytest.fail("acquired somebody else's lock")
    assert lock.read_text() == "other process"


@pytest.mark.parametrize("bad", [{"hooks": []}, {"hooks": {"PostToolUse": [42]}},
                                {"hooks": {"PostToolUse": [{"hooks": "bad"}]}}, {"env": []}])
def test_malformed_settings_preflight_no_mcp_or_package_write(homes, monkeypatch, bad):
    from hosts import config_path, host_home
    home = host_home("claude")
    home.mkdir(parents=True)
    path = home / "settings.json"
    path.write_text(json.dumps(bad))
    before = path.read_bytes()
    setup = load("brainspace_setup")
    monkeypatch.setattr(sys, "argv", ["brainspace_setup.py", "--host", "claude"])
    assert setup.main() == 1
    assert path.read_bytes() == before
    assert not config_path("claude").exists()
    assert not (home / "token-master").exists()


def test_exec_hook_argv_no_shell_interpolation(homes, tmp_path):
    from hosts import host_home, wire_hook
    from hosts.runtime import hook_entry
    script = tmp_path / "a b 工具 %!'.py"
    script.write_text("import sys; print(repr(sys.argv[1:]))", encoding="utf-8")
    entry = hook_entry(sys.executable, str(script))
    wire_hook(host_home("claude"), entry)
    settings = json.loads((host_home("claude") / "settings.json").read_bytes())
    saved = settings["hooks"]["PostToolUse"][0]["hooks"][0]
    assert saved["args"] == ["-X", "utf8", str(script.resolve()), "--host", "claude"]
    result = subprocess.run([saved["command"], *saved["args"]], capture_output=True,
                            encoding="utf-8", check=True)
    assert result.stdout.strip() == "['--host', 'claude']"


def test_routing_agent_owned_update_and_uninstall(homes):
    from hosts.files import owned_file
    path = homes / "agents" / "token-master.md"
    owned_file(path, b"first")
    owned_file(path, b"second")
    path.write_text("user-edit")
    with pytest.raises(ValueError, match="preserving"):
        owned_file(path, None)
    path.write_bytes(b"second")
    owned_file(path, None)
    assert not path.exists()


def test_graph_setup_fake_supplier_real_installer_in_temp_home(homes, monkeypatch):
    """Run all graph setup logic, mocking only the external graph supplier."""
    from hosts import config_path, host_home, wire_mcp
    setup = load("setup")
    repo = homes / "repo space 工具"
    repo.mkdir()
    (repo / "code.py").write_text("def f(): pass\n")
    output = repo / "graphify-out"
    output.mkdir()
    (output / "graph.json").write_text(json.dumps({"nodes": [
        {"id": "f", "label": "f", "file_type": "code", "source_file": "code.py"}],
        "links": []}))
    real_run = setup.subprocess.run
    real_which = setup.shutil.which
    def run(argv, **kwargs):
        if argv[:2] == ["fixture-graphify", "update"]:
            return subprocess.CompletedProcess(argv, 0, "")
        return real_run(argv, **kwargs)
    monkeypatch.setattr(setup.subprocess, "run", run)
    monkeypatch.setattr(setup.shutil, "which",
                        lambda name: "fixture-graphify" if name == "graphify" else real_which(name))
    monkeypatch.setattr(setup, "_git_root", lambda path: path)
    monkeypatch.setattr(setup, "_supplier", lambda p: {"name": "fixture-graphify", "version": "1"})
    for host in ("claude", "copilot", "codex"):
        wire_mcp(host, "graphify-nav", {"command": sys.executable, "args": ["old.py"]})  # a pre-v7 install
        monkeypatch.setattr(sys, "argv", ["setup.py", str(repo), "--host", host, "--python", sys.executable])
        assert setup.main() == 0
        saved = json.loads((repo / ".token-master" / "graph.json").read_bytes())
        assert saved["token_master_index"]["supplier"]["name"] == "fixture-graphify"
        ignored = (repo / ".gitignore").read_text("utf-8").splitlines()
        assert ".token-master/" in ignored and ignored.count("graphify-out/") == 1  # agents' grep skips the graph
        config = config_path(host).read_text("utf-8")
        assert "tokenmaster-nav" in config and "graphify-nav" not in config
        install = host_home(host) / "token-master"
        assert (install / "navigation_mcp.py").is_file() and (install / "brainspace" / "symbol_index.py").is_file()
        assert (repo / ".token-master" / "symbols.sqlite").is_file()
        if host == "copilot":
            text = (host_home(host) / "agents" / "token-master.agent.md").read_text("utf-8")
            assert "--with" not in text
            assert "fixture-graphify" not in text
            assert "tokenmaster-nav:" in text and "`impact` lists callers" in text
        monkeypatch.setattr(sys, "argv", ["setup.py", "--host", host, "--uninstall"])
        assert setup.main() == 0
        assert not config_path(host).is_file() or "tokenmaster-nav" not in config_path(host).read_text("utf-8")
