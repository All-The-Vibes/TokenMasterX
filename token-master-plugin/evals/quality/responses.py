"""Compatibility import for the production transport; no second implementation."""
import sys

from brainspace import transport as _implementation
from brainspace.transport import Reply, ResponsesTransport, parse_json  # noqa: F401

# Preserve imports and existing evaluator monkeypatch points. Frozen historical
# studies retain their original source and are not changed by this shim.
sys.modules[__name__] = _implementation
