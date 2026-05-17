"""Abstract base classes for ValidationContext and AssetMetadata.

The context abstraction decouples rules from where they get asset data.
Rules call context methods; the context determines whether to use the
Unreal Python API or the local filesystem.

The same rule implementation can run in:

- Unreal Editor (:class:`UnrealContext`)
- CI/standalone mode (:class:`FilesystemContext`)
- Unit tests (mock context)

"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AssetMetadata:
    """Normalised metadata for one asset, collected by a :class:`ValidationContext`.

    All fields have safe defaults so rules can inspect without ``None`` guards.

    Attributes:
        path: Filesystem or content-browser path to the asset.
        name: Basename of the asset (no extension for Unreal assets).
        extension: Lowercase file extension including the dot (e.g. ``".uasset"``).
        size_bytes: File size in bytes; ``0`` when unavailable.
        asset_class: Unreal asset class name (e.g. ``"StaticMesh"``); empty
            when unknown.
        properties: Arbitrary key/value metadata returned by the context.
    
    """
    path: str = ""
    name: str = ""
    extension: str = ""
    size_bytes: int = 0
    asset_class: str = ""
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def sizeMb(self) -> float:
        """Asset file size in megabytes."""
        return self.size_bytes / (1024 * 1024)


class ValidationContext(ABC):
    """Abstract base for context adapters.

    A context knows how to collect :class:`AssetMetadata` for a given path.
    Concrete implementations: :class:`FilesystemContext`, :class:`UnrealContext`.
    
    """

    @abstractmethod
    def collect(self, asset_path: str) -> AssetMetadata:
        """Collect metadata for the asset at the given path.

        Args:
            asset_path: Filesystem or content-browser path of the asset.

        Returns:
            A populated :class:`AssetMetadata` instance for the asset.
        
        """
        ...

    @abstractmethod
    def isAvailable(self) -> bool:
        """Return ``True`` if this context can operate in the current environment."""
        ...

    def __repr__(self) -> str:
        return f"{type(self).__name__}(available={self.isAvailable()})"