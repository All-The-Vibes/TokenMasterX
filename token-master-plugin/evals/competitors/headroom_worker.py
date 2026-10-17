"""Compatibility imports; the container mounts the standalone production worker."""
from brainspace.headroom_worker import (
    COMMIT, MAX_FRAME, MODEL_REVISION, MODEL_SHA256, TOKENIZER_REVISION,
    diagnostic_rows, emit, main, parse,
)

__all__ = ["COMMIT", "MAX_FRAME", "MODEL_REVISION", "MODEL_SHA256", "TOKENIZER_REVISION",
           "diagnostic_rows", "emit", "main", "parse"]

if __name__ == "__main__":
    raise SystemExit(main())
