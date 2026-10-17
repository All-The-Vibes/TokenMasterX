"""Documented host configuration, not proof of host runtime acceptance.

Contract review: 2026-10-04
Codex: https://developers.openai.com/codex/mcp/
       https://developers.openai.com/codex/hooks/
Copilot: https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers
Claude: https://code.claude.com/docs/en/mcp?plain=1
        https://code.claude.com/docs/en/hooks?plain=1
        https://code.claude.com/docs/en/env-vars?plain=1
        (Exec-form args and schema-matching updatedToolOutput documented;
        configuration here is not proof of actual runtime acceptance.)
"""
import os
from pathlib import Path

from .config import copilot_hook, hook, json_server, parse, read, toml_server

HOSTS = ("claude", "codex", "copilot")
CLAUDE_HOOK_CONTRACT = {
    "capability_id": "claude-posttooluse-updatedToolOutput-2026-10-04",
    "host": "claude", "event": "PostToolUse",
    "replacement_field": "hookSpecificOutput.updatedToolOutput",
    "built_in_schema_validation": True,
    "documented_min_version": None,
    "documented_replacement_cap": None,
    "runtime_verified": False,
    "requires_explicit_opt_in": True,
}
COPILOT_HOOK_CONTRACT = {
    "capability_id": "copilot-posttooluse-2026-10-09",
    "host": "copilot", "event": "postToolUse",
    "replacement_field": "modifiedResult.textResultForLlm",
    "documented_min_version": None,
    "documented_replacement_cap": None,
    "runtime_verified": False,
    "requires_explicit_opt_in": True,
    "qualified_tool_family": "pure successful view text; conservative JSON only",
}


def resolve_host(value=""):
    explicit = (value or os.environ.get("TOKEN_MASTER_HOST", "")).strip().lower()
    if explicit:
        if explicit not in HOSTS:
            raise ValueError(f"unsupported host: {explicit}")
        return explicit
    if os.environ.get("CODEX_HOME"):
        return "codex"
    claude = bool(os.environ.get("CLAUDE_PLUGIN_ROOT")) or (Path.home() / ".claude").is_dir()
    copilot = bool(os.environ.get("COPILOT_HOME")) or (Path.home() / ".copilot").is_dir()
    return "copilot" if copilot and not claude else "claude"


def host_home(host):
    if host not in HOSTS:
        raise ValueError(f"unsupported host: {host}")
    raw = os.environ.get(host.upper() + "_HOME")
    if host == "claude":
        raw = os.environ.get("CLAUDE_CONFIG_DIR") or raw
    return Path(os.path.expandvars(os.path.expanduser(raw))).resolve() if raw else (Path.home() / ("." + host)).resolve()


def config_path(host):
    home = host_home(host)
    if host == "codex":
        return home / "config.toml"
    if host == "copilot":
        return home / "mcp-config.json"
    # CLAUDE_HOME/CLAUDE_CONFIG are legacy installer-only sandbox overrides;
    # they do not themselves configure the Claude executable.
    explicit = os.environ.get("CLAUDE_CONFIG")
    if explicit:
        return Path(os.path.expandvars(os.path.expanduser(explicit))).resolve()
    if os.environ.get("CLAUDE_CONFIG_DIR") or os.environ.get("CLAUDE_HOME"):
        return home / ".claude.json"
    return Path.home() / ".claude.json"


def preflight(host, include_hook=False):
    path = config_path(host)
    data = parse(read(path).decode("utf-8-sig"), toml=host == "codex")
    servers = data.get("mcp_servers" if host == "codex" else "mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("MCP servers must be an object/table")
    if include_hook:
        data = parse(read(host_home(host) / "settings.json").decode("utf-8-sig"))
        if host == "copilot":
            hooks = data.get("hooks", {})
            if not isinstance(hooks, dict) or not isinstance(hooks.get("postToolUse", []), list):
                raise ValueError("malformed Copilot postToolUse hooks configuration")
            if any(not isinstance(handler, dict) for handler in hooks.get("postToolUse", [])):
                raise ValueError("malformed Copilot postToolUse handler")
            return
        if not isinstance(data.get("env", {}), dict):
            raise ValueError("settings env must be an object")
        hooks = data.get("hooks", {})
        if not isinstance(hooks, dict) or not isinstance(hooks.get("PostToolUse", []), list):
            raise ValueError("malformed PostToolUse hooks configuration")
        for group in hooks.get("PostToolUse", []):
            if not isinstance(group, dict) or not isinstance(group.get("hooks", []), list):
                raise ValueError("malformed PostToolUse matcher group")
            if any(not isinstance(handler, dict) for handler in group.get("hooks", [])):
                raise ValueError("malformed PostToolUse handler")


def wire_mcp(host, name, entry):
    if entry is not None and host == "copilot":
        entry = {**entry, "type": "local", "tools": ["*"]}
    writer = toml_server if host == "codex" else json_server
    return writer(config_path(host), name, entry)


def wire_hook(home, command):
    return hook(home / "settings.json", command)


def wire_copilot_hook(home, command):
    return copilot_hook(home / "settings.json", command)


def copilot_hook_status(home):
    """Registered owned entry only; not proof of enabled/accepted native behavior."""
    path = home / "settings.json"
    receipt = parse(read(path.with_name(path.name + ".token-master-owned.json")).decode("utf-8"))
    entry = receipt.get("hook:brainspace:copilot")
    if entry is None:
        return False
    data = parse(read(path).decode("utf-8-sig"))
    hooks = data.get("hooks", {})
    post = hooks.get("postToolUse", []) if isinstance(hooks, dict) else None
    return True if isinstance(post, list) and post.count(entry) == 1 else None


def capabilities(host):
    return {
        "host": host, "configuration_clients": ["cli", "desktop"] if host == "codex" else ["cli"],
        "mcp": "model-invoked", "hook_configuration_supported": host in ("claude", "copilot"),
        "hook_launch_form": "exec-argv" if host in ("claude", "copilot") else None,
        "hook_output_contract": dict(CLAUDE_HOOK_CONTRACT) if host == "claude" else
            dict(COPILOT_HOOK_CONTRACT) if host == "copilot" else None,
        "transparent_replacement": False, "runtime_verified": False,
        "contract_review_date": "2026-10-09" if host == "copilot" else "2026-10-04",
        "note": ("Claude hook registration supported; output-schema and actual host acceptance require validation."
                 if host == "claude" else
                 "MCP by default; native view-text hook requires --copilot-output-hook. "
                 "Registration is not proof of host acceptance or token savings."
                 if host == "copilot" else
                 "MCP-only adapter. No output replacement hook installed; configuration support is not runtime acceptance."),
    }
