"""Compatibility imports; implementation lives in the installed product package."""
from brainspace.headroom import (
    COMMIT, IMAGE_ID, MAX_FRAME, MODEL_REVISION, HeadroomContainer, validate_container,
)

__all__ = ["COMMIT", "IMAGE_ID", "MAX_FRAME", "MODEL_REVISION",
           "HeadroomContainer", "validate_container"]
