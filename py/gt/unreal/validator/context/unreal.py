"""Unreal Engine :class:`ValidationContext` implementation.

Collects asset metadata via the Unreal Python API.
Only usable when running inside Unreal Editor.

"""
from __future__ import annotations

import logging
from typing import Any

from .base import ValidationContext, AssetMetadata
from ..env import UNREAL_AVAILABLE

logger = logging.getLogger(__name__)

if UNREAL_AVAILABLE:
    import unreal  # type: ignore[import]


class UnrealContext(ValidationContext):
    """ValidationContext backed by Unreal's EditorAssetLibrary.

    Enumerates all assets under *directory* and provides per-asset metadata
    collection via :meth:`collect`.

    Args:
        directory: Unreal content path prefix to scan (e.g. ``"/Game/"``).
            Defaults to ``"/Game/"`` (the entire project content).

    Raises:
        ImportError: If called outside the Unreal Editor
            (``UNREAL_AVAILABLE`` is ``False``).

    """

    def __init__(self, directory: str = "/Game/") -> None:
        if not UNREAL_AVAILABLE:
            raise ImportError(
                "UnrealContext requires the Unreal Editor to be running. "
                "Use FilesystemContext for standalone Python mode."
            )
        self.directory = directory

    # ── ValidationContext interface ─────────────────────────────────────── #

    def isAvailable(self) -> bool:
        """Return True — this context is only instantiated when Unreal is live."""
        return UNREAL_AVAILABLE

    def collect(self, asset_path: str) -> AssetMetadata:
        """Collect metadata for a single asset path.

        Args:
            asset_path: Content-browser path of the asset to inspect.

        Returns:
            A populated :class:`AssetMetadata` instance, or a default instance
            with only ``path`` set if loading fails.

        """
        meta = self._buildMetadata(asset_path)
        return meta if meta is not None else AssetMetadata(path=asset_path)

    # ── Directory enumeration ────────────────────────────────────────────── #

    def getAssets(self) -> list[AssetMetadata]:
        """Enumerate all assets under :attr:`directory` via EditorAssetLibrary.

        Returns:
            A list of :class:`AssetMetadata` objects; one per asset found.

        """
        asset_paths = unreal.EditorAssetLibrary.list_assets(
            self.directory, recursive=True
        )
        results: list[AssetMetadata] = []
        for ap in asset_paths:
            meta = self._buildMetadata(ap)
            if meta is not None:
                results.append(meta)
        return results

    # ── Private helpers ──────────────────────────────────────────────────── #

    def _buildMetadata(self, asset_path: str) -> AssetMetadata | None:
        """Build AssetMetadata by querying the asset registry for *asset_path*.

        Args:
            asset_path: Unreal content path for the asset.

        Returns:
            A populated :class:`AssetMetadata`, or ``None`` if the asset data
            is invalid (e.g. a redirector or deleted-asset cache entry).

        """
        try:
            data = unreal.EditorAssetLibrary.find_asset_data(asset_path)
        except Exception as exc:
            logger.warning("find_asset_data failed for '%s': %s", asset_path, exc)
            return None

        if not data.is_valid():
            return None

        asset_class: str = str(data.asset_class_path.asset_name)
        asset_name:  str = str(data.asset_name)

        return AssetMetadata(
            path=asset_path,
            name=asset_name,
            extension=".uasset",
            size_bytes=0,
            asset_class=asset_class,
        )

    def __repr__(self) -> str:
        return f"UnrealContext(directory={self.directory!r})"
