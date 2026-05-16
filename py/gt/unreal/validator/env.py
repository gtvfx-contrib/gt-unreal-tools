"""Environment detection and Unreal Engine bootstrap helpers.

Detects whether the code is running inside Unreal Engine's embedded Python
interpreter or in a standalone Python environment.

Example::

    from validator.env import UNREAL_AVAILABLE

    if UNREAL_AVAILABLE:
        import unreal
        obj = unreal.EditorAssetLibrary.load_asset(path)
    else:
        # run filesystem-only checks
        ...
"""
import logging
import sys
from typing import Any

from .errors import UnrealAPIError

logger = logging.getLogger(__name__)


def _detectUnreal() -> bool:
    """Return True if the 'unreal' module is importable (i.e., inside UE)."""
    try:
        import unreal  # noqa: F401
        return True
    except ImportError:
        return False


UNREAL_AVAILABLE: bool = _detectUnreal()


def logEnvStatus() -> None:
    """Log the environment status to the root logger."""
    if UNREAL_AVAILABLE:
        logger.info("[env] Running inside Unreal Engine — Unreal Python API available.")
    else:
        logger.info("[env] Running in standalone mode — Unreal Python API NOT available.")


def requireUnreal(msg: str = "") -> None:
    """Raise ``ImportError`` if Unreal is not available.

    Use this at the start of functions that absolutely require Unreal.

    Args:
        msg: Optional custom error message.  When empty, a default message
            is used.

    Raises:
        ImportError: If Unreal Engine is not available in the current
            Python environment.
    """
    if not UNREAL_AVAILABLE:
        raise ImportError(
            msg or "This feature requires Unreal Engine's Python environment."
        )


def loadUnrealAsset(asset_path: str) -> Any:
    """Load an Unreal Engine asset by its content-browser path.

    Provides a single, audited point for the broad ``except Exception``
    that the Unreal Python C++ bridge requires.  All rule implementations
    should call this helper rather than calling
    ``EditorAssetLibrary.load_asset`` directly.

    Args:
        asset_path: Content-browser path of the asset, e.g.
            ``"/Game/Characters/SK_Hero"``.

    Returns:
        The loaded Unreal asset object.

    Raises:
        UnrealAPIError: If Unreal is unavailable, if the API call raises,
            or if the returned asset is ``None``.
    """
    if not UNREAL_AVAILABLE:
        raise UnrealAPIError(
            f"Unreal Engine is not available; cannot load '{asset_path}'."
        )
    try:
        import unreal  # noqa: PLC0415 – deferred to avoid top-level ImportError
        obj = unreal.EditorAssetLibrary.load_asset(asset_path)
    except Exception as exc:  # noqa: BLE001 – Unreal C++ bridge raises undocumented exceptions
        raise UnrealAPIError(
            f"Unreal API error loading '{asset_path}': {exc}"
        ) from exc
    if obj is None:
        raise UnrealAPIError(
            f"Asset '{asset_path}' could not be loaded (EditorAssetLibrary returned None)."
        )
    return obj