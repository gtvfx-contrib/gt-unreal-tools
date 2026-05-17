"""Filesystem-level asset validation rules.

Rules:
    FileSizeRule: Validates that assets do not exceed the configured file size limit.
    ValidExtensionRule: Validates that assets have an approved file extension.

"""
from __future__ import annotations

import os

from .base import AbstractRule, Severity, ValidationResult
from ..registry import registry


@registry.register(category="filesystem", severity=Severity.ERROR)
class FileSizeRule(AbstractRule):
    """Validates that assets do not exceed the configured file size limit.

    Attributes:
        name: Rule identifier ``"file_size"``.
        category: Rule category ``"filesystem"``.
        severity: :attr:`Severity.ERROR`.
    
    """
    name     = "file_size"
    category = "filesystem"
    severity = Severity.ERROR

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate the file size for the given asset.

        Args:
            asset_path: Filesystem path of the asset to validate.

        Returns:
            A :class:`ValidationResult` indicating whether the file size is within
            the configured limit.  Skipped for non-filesystem paths.
        
        """
        max_mb: float = self.config.get("max_file_size_mb", 50)

        # Filesystem size check requires a real disk path.
        if not os.path.exists(asset_path):
            return self._makeSkipped(
                asset_path,
                "FileSizeRule skipped: not a filesystem path. "
                "File size is managed by Unreal when running inside the Editor."
            )

        size_bytes = os.path.getsize(asset_path)
        sizeMb = size_bytes / (1024 * 1024)

        if sizeMb > max_mb:
            return self._makeResult(
                asset_path, passed=False,
                message=f"File size {sizeMb:.2f} MB exceeds limit of {max_mb} MB.",
                fix_hint=(
                    f"Reduce asset complexity or compress textures to bring "
                    f"file size below {max_mb} MB."
                ),
            )
        return self._makeResult(
            asset_path, passed=True,
            message=f"File size {sizeMb:.2f} MB is within limit of {max_mb} MB.",
        )


@registry.register(category="filesystem", severity=Severity.ERROR)
class ValidExtensionRule(AbstractRule):
    """Validates that assets have an approved file extension.

    Attributes:
        name: Rule identifier ``"valid_extension"``.
        category: Rule category ``"filesystem"``.
        severity: :attr:`Severity.ERROR`.
    
    """
    name     = "valid_extension"
    category = "filesystem"
    severity = Severity.ERROR

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate the file extension for the given asset.

        Args:
            asset_path: Filesystem path of the asset to validate.

        Returns:
            A :class:`ValidationResult` indicating whether the extension is in the
            approved list.  Skipped for non-filesystem paths.
        
        """
        _, ext = os.path.splitext(asset_path)
        ext = ext.lower()

        # Extension check on Unreal content paths is not meaningful —
        # all .uasset files have the same extension on disk.
        if not os.path.exists(asset_path):
            return self._makeSkipped(
                asset_path,
                "ValidExtensionRule skipped: not a filesystem path. "
                "Asset type is available via AssetData.asset_class in Unreal."
            )

        valid_exts: list = self.config.get(
            "valid_extensions", [".uasset", ".fbx", ".png", ".tga", ".exr"]
        )

        if ext in valid_exts:
            return self._makeResult(
                asset_path, passed=True,
                message=f"Extension '{ext}' is in the approved list.",
            )
        return self._makeResult(
            asset_path, passed=False,
            message=f"Extension '{ext}' is not in approved list: {valid_exts}.",
            fix_hint=f"Convert or remove this file. Approved types: {', '.join(valid_exts)}.",
        )