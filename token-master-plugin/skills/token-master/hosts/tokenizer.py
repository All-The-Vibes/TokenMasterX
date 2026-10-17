"""Copy a verified, already-local reference vocabulary; never acquire assets."""
import hashlib
from pathlib import Path


def read_tokenizer(source=None, installed=None):
    from brainspace.tokens import VOCABULARY_SHA256, _vocabulary_path

    path = Path(source).expanduser().resolve() if source else (
        installed if installed is not None and installed.is_file() else _vocabulary_path())
    if path is None or not path.is_file():
        raise ValueError("verified local tokenizer required: prepare it explicitly, then pass --tokenizer-file PATH")
    # Bound even explicitly supplied files before digest validation.
    with path.open("rb") as stream:
        data = stream.read(2 * 1024 * 1024 + 1)
    if hashlib.sha256(data).hexdigest() != VOCABULARY_SHA256:
        raise ValueError("local tokenizer failed pinned SHA-256 verification; no configuration installed")
    return data, {"source": str(path.resolve()), "sha256": VOCABULARY_SHA256, "bytes": len(data)}
