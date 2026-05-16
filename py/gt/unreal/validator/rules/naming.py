"""Asset naming convention validation rules.

Rules:
    NamingConventionRule: Validates asset filenames match the configured naming pattern.
    PrefixConventionRule: Validates assets have the correct prefix for their extension.
    FilenameLengthRule: Validates asset filenames do not exceed the configured length.
"""
from __future__ import annotations

import os
import re

from .base import AbstractRule, Severity, ValidationResult
from ..registry import registry


def _getAssetStem(asset_path: str) -> str:
    """Return the asset name stem for either an Unreal content path or a filesystem path.

    Args:
        asset_path: Content-browser path (e.g. ``/Game/Assets/SM_Rock``) or
            a filesystem path.

    Returns:
        The bare asset name without directory or extension.

    """
    if asset_path.startswith('/') and not os.path.exists(asset_path):
        return asset_path.rstrip('/').split('/')[-1]
    return os.path.splitext(os.path.basename(asset_path))[0]


@registry.register(category="naming", severity=Severity.ERROR)
class NamingConventionRule(AbstractRule):
    """Validates that asset filenames match the configured naming pattern.

    Attributes:
        name: Rule identifier ``"naming_convention"``.
        category: Rule category ``"naming"``.
        severity: :attr:`Severity.ERROR`.
    """
    name     = "naming_convention"
    category = "naming"
    severity = Severity.ERROR

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate the naming convention for the given asset.

        Args:
            asset_path: Filesystem path or Unreal content-browser path of the asset.

        Returns:
            A :class:`ValidationResult` indicating whether the asset name matches
            the configured pattern.
        """
        stem = _getAssetStem(asset_path)

        pattern: str = self.config.get("naming_pattern", r"^[A-Z][a-zA-Z0-9_]+$")

        if re.match(pattern, stem):
            return self._makeResult(
                asset_path, passed=True,
                message=f"Filename '{stem}' matches naming convention.",
            )
        return self._makeResult(
            asset_path, passed=False,
            message=f"Filename '{stem}' does not match pattern '{pattern}'.",
            fix_hint=f"Rename to match: {pattern} (e.g., 'SM_MyAsset').",
        )


@registry.register(category="naming", severity=Severity.ERROR)
class PrefixConventionRule(AbstractRule):
    """Validates that assets have the correct prefix for their file extension.

    Attributes:
        name: Rule identifier ``"prefix_convention"``.
        category: Rule category ``"naming"``.
        severity: :attr:`Severity.ERROR`.
    """
    name     = "prefix_convention"
    category = "naming"
    severity = Severity.ERROR

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate the prefix convention for the given asset.

        Args:
            asset_path: Filesystem path or Unreal content-browser path of the asset.

        Returns:
            A :class:`ValidationResult` indicating whether the file uses the correct
            prefix for its extension.
        """
        stem = _getAssetStem(asset_path)
        is_unreal_path = asset_path.startswith('/') and not os.path.exists(asset_path)

        if not is_unreal_path:
            filename = os.path.basename(asset_path)
            _, ext = os.path.splitext(filename)
            ext = ext.lower()
            required_prefixes: dict = self.config.get("required_prefixes", {})
            for prefix, extensions in required_prefixes.items():
                if ext in extensions:
                    if not stem.startswith(prefix):
                        return self._makeResult(
                            asset_path, passed=False,
                            message=(
                                f"File '{filename}' with extension '{ext}' "
                                f"must start with prefix '{prefix}'."
                            ),
                            fix_hint=f"Rename to '{prefix}{stem}{ext}'.",
                        )
                    return self._makeResult(
                        asset_path, passed=True,
                        message=f"File '{filename}' has correct prefix '{prefix}'.",
                    )
            return self._makeResult(
                asset_path, passed=True,
                message=f"No prefix rule configured for extension '{ext}' — skipped.",
            )

        if stem:
            return self._makeResult(
                asset_path, passed=True,
                message=f"Asset name '{stem}' is valid (extension validation on Unreal path deferred).",
            )
        return self._makeResult(
            asset_path, passed=False,
            message=f"Unable to extract asset name from Unreal path: {asset_path}.",
            fix_hint="Ensure the path is a valid Unreal content path like '/Game/Assets/MyAsset'.",
        )


@registry.register(category="naming", severity=Severity.WARNING)
class FilenameLengthRule(AbstractRule):
    """Validates that asset filenames do not exceed the configured length limit.

    Attributes:
        name: Rule identifier ``"filename_length"``.
        category: Rule category ``"naming"``.
        severity: :attr:`Severity.WARNING`.
    """
    name     = "filename_length"
    category = "naming"
    severity = Severity.WARNING

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate the filename length for the given asset.

        Args:
            asset_path: Filesystem or content-browser path of the asset.

        Returns:
            A :class:`ValidationResult` indicating whether the filename length
            is within the configured limit.
        """
        filename = os.path.basename(asset_path)
        max_len: int = self.config.get("max_filename_length", 64)

        if len(filename) > max_len:
            return self._makeResult(
                asset_path, passed=False,
                message=(
                    f"Filename '{filename}' is {len(filename)} characters "
                    f"— exceeds limit of {max_len}."
                ),
                fix_hint=f"Shorten the filename to {max_len} characters or fewer.",
            )
        return self._makeResult(
            asset_path, passed=True,
            message=f"Filename length {len(filename)} is within limit of {max_len}.",
        )