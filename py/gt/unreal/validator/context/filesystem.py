"""Filesystem-based :class:`ValidationContext` implementation.

Collects asset metadata using only the local filesystem.  Works in any
Python environment — no Unreal dependency.

"""
from __future__ import annotations

import os

from .base import ValidationContext, AssetMetadata


class FilesystemContext(ValidationContext):
    """Collects asset metadata using ``os.path`` and filesystem inspection.

    Available in all environments (standalone, CI, Unreal).
    
    """

    def isAvailable(self) -> bool:
        """Return ``True``; the filesystem context is always available."""
        return True

    def collect(self, asset_path: str) -> AssetMetadata:
        """Collect file-level metadata for the asset.

        Args:
            asset_path: Filesystem path of the asset.

        Returns:
            A :class:`AssetMetadata` instance populated from ``os.path``
            calls.  ``size_bytes`` is ``0`` for paths that are not regular
            files.
        
        """
        name = os.path.basename(asset_path)
        _, ext = os.path.splitext(name)
        size = 0
        if os.path.isfile(asset_path):
            size = os.path.getsize(asset_path)

        return AssetMetadata(
            path=asset_path,
            name=name,
            extension=ext.lower(),
            size_bytes=size,
            asset_class="",
            properties={},
        )