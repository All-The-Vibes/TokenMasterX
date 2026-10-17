"""Fail-closed, cooperating-writer transactions for user-owned configuration.

Only entries recorded in the adjacent ownership receipt may be changed. A user
edit to an owned entry is a conflict, not permission to overwrite it. Unrelated
JSON values and all non-owned TOML text survive updates. Locks deliberately do
not auto-break: an abandoned lock needs operator inspection.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import time
import tomllib
import uuid


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse(text, toml=False):
    def invalid_constant(value):
        raise ValueError(f"invalid JSON constant: {value}")
    value = tomllib.loads(text) if toml else json.loads(
        text or "{}", object_pairs_hook=_object, parse_constant=invalid_constant)
    if not isinstance(value, dict):
        raise ValueError("configuration must be an object")
    return value


def read(path):
    if path.is_symlink():
        raise ValueError(f"refusing symlink configuration: {path}")
    if not path.exists():
        return b""
    content = path.read_bytes()
    if path.suffix == ".json" and not content.decode("utf-8-sig").strip():
        raise ValueError(f"empty JSON configuration: {path}")
    return content


def atomic_write(path, content):
    """Replace from the same directory; never expose a partially written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        if path.exists():
            os.chmod(name, path.stat().st_mode & 0o777)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def config_lock(path, timeout=10):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".token-master.lock")
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise ValueError(f"configuration busy (inspect lock before retrying): {lock}")
            time.sleep(0.025)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink()


def transaction(path, edit):
    """Serialize read/validate/merge/backup/replace plus the ownership receipt.

    Each file replacement is atomic. An interrupted multi-file transaction can
    leave an ownership mismatch; future edits fail closed rather than guessing.
    Cooperating installers are locked; concurrent external-editor changes detected
    before replacement abort. No filesystem can CAS an arbitrary external writer.
    """
    path = Path(path)
    receipt = path.with_name(path.name + ".token-master-owned.json")
    with config_lock(path):
        before = read(path)
        prior_receipt = read(receipt)
        owned = parse(prior_receipt.decode("utf-8"))
        after = edit(before.decode("utf-8-sig"), owned).encode("utf-8")
        if before.startswith(b"\xef\xbb\xbf"):
            after = b"\xef\xbb\xbf" + after
        encoded_owned = (json.dumps(owned, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        if after == before and encoded_owned == prior_receipt:
            return path
        if after == before and not owned and not prior_receipt:
            return path
        if read(path) != before or read(receipt) != prior_receipt:
            raise ValueError("configuration changed during merge; retry")
        if before and after != before:
            backup = path.with_name(path.name + ".token-master-backup-" + uuid.uuid4().hex)
            atomic_write(backup, before)
            os.chmod(backup, 0o600)
        # Persist ownership first. A crash leaves a safe conflict, never grants
        # ownership of an unrelated entry. Roll back receipt on ordinary failure.
        atomic_write(receipt, encoded_owned)
        try:
            if after != before:
                atomic_write(path, after)
        except BaseException:
            if prior_receipt:
                atomic_write(receipt, prior_receipt)
            else:
                receipt.unlink()
            raise
    return path


def check_owned(owned, key, current):
    if key in owned:
        if current != owned[key]:
            raise ValueError(f"owned setting {key!r} was edited; preserving it")
    elif current is not None:
        raise ValueError(f"setting {key!r} already exists and is not owned by TokenMaster")


def json_server(path, name, entry):
    def edit(text, owned):
        data = parse(text)
        servers = data.get("mcpServers", {})
        if not isinstance(servers, dict):
            raise ValueError("mcpServers must be an object")
        key = "server:" + name
        check_owned(owned, key, servers.get(name))
        if entry is not None and "mcpServers" in data and not servers:
            owned.setdefault("preserve_empty_mcpServers", True)
        if entry is None:
            servers.pop(name, None)
            owned.pop(key, None)
            if not servers and not owned.get("preserve_empty_mcpServers"):
                data.pop("mcpServers", None)
        else:
            servers[name] = entry
            data["mcpServers"] = servers
            owned[key] = entry
        if data == parse(text):
            return text
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return transaction(path, edit)


def toml_server(path, name, entry):
    # Only installer-owned blocks are rewritten. Preserve comments, ordering,
    # dotted keys, multiline strings and all other TOML syntax byte-for-byte.
    marker = "# TokenMaster managed MCP: " + name
    end_marker = "# End TokenMaster MCP: " + name

    def block(value):
        lines = [marker, "[mcp_servers." + json.dumps(name) + "]"]
        for key, val in value.items():
            if isinstance(val, dict):
                lines.append(key + " = { " + ", ".join(
                    json.dumps(k) + " = " + json.dumps(v, ensure_ascii=False)
                    for k, v in val.items()) + " }")
            else:
                lines.append(key + " = " + json.dumps(val, ensure_ascii=False))
        return "\n".join(lines) + "\n" + end_marker + "\n"

    def edit(text, owned):
        data = parse(text, toml=True)
        servers = data.get("mcp_servers", {})
        if not isinstance(servers, dict):
            raise ValueError("mcp_servers must be a table")
        key = "server:" + name
        check_owned(owned, key, servers.get(name))
        old_block = owned.get("block:" + name)
        insertion = len(text)
        if old_block is not None:
            if text.count(old_block) != 1:
                raise ValueError("owned TOML block changed; preserving configuration")
            insertion = text.index(old_block)
            text = text.replace(old_block, "", 1)
        elif marker in text:
            raise ValueError("unowned TOML marker; preserving configuration")
        if entry is None:
            owned.pop(key, None)
            owned.pop("block:" + name, None)
        else:
            prefix = text[:insertion]
            addition = ("" if not prefix or prefix.endswith("\n") else "\n") + block(entry)
            text = prefix + addition + text[insertion:]
            owned[key] = entry
            owned["block:" + name] = addition
        parse(text, toml=True)  # refuse unsupported table conflicts before writing
        return text
    return transaction(path, edit)


def hook(path, command):
    def edit(text, owned):
        data = parse(text)
        hooks = data.get("hooks", {})
        if not isinstance(hooks, dict):
            raise ValueError("hooks must be an object")
        post = hooks.get("PostToolUse", [])
        if not isinstance(post, list) or any(not isinstance(e, dict) for e in post):
            raise ValueError("PostToolUse must be a list of objects")
        if any(not isinstance(e.get("hooks", []), list) or
               any(not isinstance(h, dict) for h in e.get("hooks", [])) for e in post):
            raise ValueError("PostToolUse hooks must be a list of objects")
        previous = owned.get("hook:brainspace")
        if previous is not None:
            if post.count(previous) != 1:
                raise ValueError("owned hook was edited; preserving it")
            post = [e for e in post if e != previous]
        if command is not None:
            handler = command if isinstance(command, dict) else {"type": "command", "command": command}
            entry = {"matcher": "*", "hooks": [handler]}
            if entry in post:
                raise ValueError("hook already exists without ownership receipt")
            post.append(entry)
            owned["hook:brainspace"] = entry
        else:
            owned.pop("hook:brainspace", None)
        if post:
            hooks["PostToolUse"] = post
            data["hooks"] = hooks
        else:
            hooks.pop("PostToolUse", None)
            if not hooks:
                data.pop("hooks", None)
        return text if data == parse(text) else json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return transaction(path, edit)


def copilot_hook(path, command):
    """One explicitly opted-in native command hook; preserve all neighboring hooks."""
    key = "hook:brainspace:copilot"

    def edit(text, owned):
        data = parse(text)
        hooks = data.get("hooks", {})
        if not isinstance(hooks, dict):
            raise ValueError("hooks must be an object")
        post = hooks.get("postToolUse", [])
        if not isinstance(post, list) or any(not isinstance(item, dict) for item in post):
            raise ValueError("postToolUse must be a list of objects")
        previous = owned.get(key)
        position = len(post)
        if previous is not None:
            if post.count(previous) != 1:
                raise ValueError("owned Copilot hook was edited; preserving it")
            position = post.index(previous)
            post = post[:position] + post[position + 1:]
        elif command is None:
            return text
        else:
            if "hooks" in data and not hooks:
                owned["copilot:preserve_empty_hooks"] = True
            if "postToolUse" in hooks and not post:
                owned["copilot:preserve_empty_postToolUse"] = True
        if command is not None:
            if not isinstance(command, dict):
                raise ValueError("native Copilot hook requires an exec-argv object")
            entry = dict(command)
            if entry in post:
                raise ValueError("Copilot hook already exists without ownership receipt")
            post.insert(position, entry)
            owned[key] = entry
        else:
            owned.pop(key, None)
        if post or owned.get("copilot:preserve_empty_postToolUse"):
            hooks["postToolUse"] = post
        else:
            hooks.pop("postToolUse", None)
        if hooks or owned.get("copilot:preserve_empty_hooks"):
            data["hooks"] = hooks
        else:
            data.pop("hooks", None)
        if command is None:
            owned.pop("copilot:preserve_empty_hooks", None)
            owned.pop("copilot:preserve_empty_postToolUse", None)
        return text if data == parse(text) else json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return transaction(path, edit)


def environment(path, name, value):
    """One namespaced Claude settings env variable; never replace the env map."""
    def edit(text, owned):
        data = parse(text)
        env = data.get("env", {})
        if not isinstance(env, dict):
            raise ValueError("settings env must be an object")
        key = "env:" + name
        check_owned(owned, key, env.get(name))
        if value is None:
            env.pop(name, None)
            owned.pop(key, None)
            if not env:
                data.pop("env", None)
        else:
            env[name] = value
            data["env"] = env
            owned[key] = value
        return text if data == parse(text) else json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return transaction(path, edit)
