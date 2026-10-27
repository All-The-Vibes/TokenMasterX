"""Copy a verified, already-local reference vocabulary; never acquire assets."""
import hashlib
import os
from pathlib import Path


def read_tokenizer(source=None, installed=None):
    from brainspace.tokens import VOCABULARY_SHA256, _vocabulary_path

    path = Path(source).expanduser().resolve() if source else (
        installed if installed is not None and installed.is_file() else _vocabulary_path())
    if path is None or not path.is_file():
        if source or os.environ.get("BRAINSPACE_TOKENIZER_FILE"):
            raise ValueError(f"tokenizer file not found: {path}")
        looked = f" (looked for {path})" if path is not None else ""
        raise ValueError(f"verified local tokenizer required{looked}: run `<runtime-python> -c \"import tiktoken; "
                         "tiktoken.get_encoding('cl100k_base')\"` once to cache OpenAI's cl100k_base vocabulary, "
                         "or pass --tokenizer-file PATH")
    # Bound even explicitly supplied files before digest validation.
    with path.open("rb") as stream:
        data = stream.read(2 * 1024 * 1024 + 1)
    if hashlib.sha256(data).hexdigest() != VOCABULARY_SHA256:
        raise ValueError("local tokenizer failed pinned SHA-256 verification; no configuration installed")
    return data, {"source": str(path.resolve()), "sha256": VOCABULARY_SHA256, "bytes": len(data)}
