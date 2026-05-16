"""Unreal Engine :class:`ValidationContext` implementation.

Collects asset metadata via the Unreal Python API.
Only usable when running inside Unreal Editor.
"""
from __future__ import annotations

import logging

from .base import ValidationContext, AssetMetadata
from ..env import UNREAL_AVAILABLE

logger = logging.getLogger(__name__)


class UnrealContext(ValidationContext):
    """Collects asset metadata using Unreal's EditorAssetLibrary.

    Only available when UNREAL_AVAILABLE is True (inside UE Editor).
    Falls back to empty metadata gracefully if Unreal is not available.
    """

    def is_available(self) -> bool:
        return UNREAL_AVAILABLE

    def collect(self, asset_path: str) -> AssetMetadata:
        """Collect asset metadata using the Unreal Python API.

        Args:
            asset_path: Content-browser path of the asset to inspect.

        Returns:
            A populated :class:`AssetMetadata` instance, or a default instance
            with only ``path`` set if Unreal is unavailable or loading fails.
        """
        if not UNREAL_AVAILABLE:
            return AssetMetadata(path=asset_path)

        try:
            import unreal
            obj = unreal.EditorAssetLibrary.load_asset(asset_path)
            if obj is None:
                return AssetMetadata(path=asset_path)

            asset_class = type(obj).__name__
            props: dict = {}

            return AssetMetadata(
                path=asset_path,
                name=str(obj.get_name()),
                extension=".uasset",
                size_bytes=0,
                asset_class=asset_class,
                properties=props,
            )
        except Exception as exc:  # noqa: BLE001 – Unreal C++ bridge raises undocumented exceptions
            logger.warning("Failed to collect Unreal metadata for '%s': %s", asset_path, exc)
            return AssetMetadata(path=asset_path)
