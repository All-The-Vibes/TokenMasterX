"""Ownership-aware routing-agent writes and uninstall (never delete user edits)."""
import hashlib
import json
import uuid

from .config import atomic_write, config_lock, parse, read


def owned_file(path, content):
    receipt = path.with_name(path.name + ".token-master-owned.json")
    with config_lock(path):
        before = read(path)
        owned = parse(read(receipt).decode("utf-8"))
        digest = hashlib.sha256(before).hexdigest()
        if path.exists() and owned.get("sha256") != digest:
            raise ValueError(f"agent is unowned or user-edited; preserving {path}")
        if content == before or (content is None and not path.exists()):
            return path
        if before:
            atomic_write(path.with_name(path.name + ".token-master-backup-" + uuid.uuid4().hex), before)
        if content is None:
            path.unlink()
            receipt.unlink(missing_ok=True)
        else:
            atomic_write(path, content)
            atomic_write(receipt, (json.dumps({"sha256": hashlib.sha256(content).hexdigest()}) + "\n").encode())
    return path
