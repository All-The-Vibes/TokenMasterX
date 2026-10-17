"""Small stdlib-only runtime boundaries shared by product adapters."""
import json
import math
import os
from pathlib import Path


def parse_json(text):
    """Parse JSON without ambiguous keys or nonfinite numbers, including overflow."""
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    def reject(_):
        raise ValueError("nonfinite JSON")

    def finite(text):
        value = float(text)
        if not math.isfinite(value):
            raise ValueError("nonfinite JSON")
        return value

    return json.loads(text, object_pairs_hook=unique, parse_constant=reject, parse_float=finite)


def safe_root(path):
    """Reject linked lexical parents BEFORE canonicalizing containment aliases.

    Check each prefix's normalized spelling too, so cancelled missing segments
    cannot hide a link before resolution. This is validation, not a race-proof
    filesystem open/creation primitive.
    """
    root = Path(path).absolute()
    for part in (root, *root.parents):
        for spelling in (part, Path(os.path.normpath(part))):
            if spelling.is_symlink() or spelling.is_junction():
                raise ValueError("linked workspace")
    root = root.resolve(strict=False)
    for part in (root, *root.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("linked workspace")
    return root


def append_receipt(path, value):
    """Flush and fsync a complete JSONL record before dispatch/acknowledgment."""
    text = json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n"
    with Path(path).open("a", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
