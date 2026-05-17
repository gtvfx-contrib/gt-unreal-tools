"""Texture validation rules.

Rules:
    TextureDimensionRule: Validates texture dimensions are power-of-two and within the limit.
    TextureCompressionRule: Validates that textures use appropriate compression settings.

"""
from __future__ import annotations

from .base import AbstractRule, Severity, ValidationResult
from ..env import loadUnrealAsset
from ..errors import UnrealAPIError
from ..registry import registry


@registry.register(category="texture", severity=Severity.ERROR)
class TextureDimensionRule(AbstractRule):
    """Validates texture dimensions are power-of-two and within the configured limit.

    Attributes:
        name: Rule identifier ``"texture_dimension"``.
        category: Rule category ``"texture"``.
        severity: :attr:`Severity.ERROR`.
    
    """
    name     = "texture_dimension"
    category = "texture"
    severity = Severity.ERROR

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate the dimensions of the given texture asset.

        Args:
            asset_path: Content-browser path of the asset to validate.

        Returns:
            A :class:`ValidationResult` indicating whether the texture dimensions
            are power-of-two and within the configured maximum.
        
        """
        try:
            asset = loadUnrealAsset(asset_path)
        except UnrealAPIError as exc:
            return self._makeSkipped(asset_path, str(exc))
        import unreal  # noqa: PLC0415 - deferred Unreal import

        if not isinstance(asset, unreal.Texture2D):
            return self._makeSkipped(asset_path, f"Not a Texture2D (got {type(asset).__name__}).")

        try:
            width  = asset.blueprint_get_size_x()
            height = asset.blueprint_get_size_y()
            max_dim: int = self.config.get("max_texture_dimension", 4096)

            def isPowerOfTwo(n: int) -> bool:
                return n > 0 and (n & (n - 1)) == 0

            issues = []
            if width > max_dim or height > max_dim:
                issues.append(
                    f"Dimensions {width}x{height} exceed max {max_dim}x{max_dim}."
                )
            if not isPowerOfTwo(width) or not isPowerOfTwo(height):
                issues.append(
                    f"Dimensions {width}x{height} are not powers of two."
                )

            if issues:
                return self._makeResult(
                    asset_path, passed=False,
                    message=" ".join(issues),
                    asset_class="Texture2D",
                    fix_hint=f"Resize texture to a power-of-two dimension <= {max_dim}px.",
                )
            return self._makeResult(
                asset_path, passed=True,
                message=f"Texture dimensions {width}x{height} are valid.",
                asset_class="Texture2D",
            )
        except Exception as exc:  # noqa: BLE001 - Unreal bridge safety
            return self._makeSkipped(asset_path, f"Validation error: {exc}")


@registry.register(category="texture", severity=Severity.WARNING)
class TextureCompressionRule(AbstractRule):
    """Validates that textures use an appropriate compression setting.

    Normal maps must use ``TC_Normalmap`` compression.

    Attributes:
        name: Rule identifier ``"texture_compression"``.
        category: Rule category ``"texture"``.
        severity: :attr:`Severity.WARNING`.
    
    """
    name     = "texture_compression"
    category = "texture"
    severity = Severity.WARNING

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate the compression settings of the given texture asset.

        Args:
            asset_path: Content-browser path of the asset to validate.

        Returns:
            A :class:`ValidationResult` indicating whether the compression setting
            is appropriate for the detected texture type.
        
        """
        try:
            asset = loadUnrealAsset(asset_path)
        except UnrealAPIError as exc:
            return self._makeSkipped(asset_path, str(exc))
        import unreal  # noqa: PLC0415 - deferred Unreal import

        if not isinstance(asset, unreal.Texture2D):
            return self._makeSkipped(asset_path, f"Not a Texture2D (got {type(asset).__name__}).")

        try:
            compression = asset.compression_settings

            # Heuristic: detect normal maps by path/name
            path_str = str(asset_path)
            is_normal_map = (
                "_N." in path_str or
                "_Normal." in path_str or
                "_NRM." in path_str or
                "Normal" in path_str
            )

            if is_normal_map and compression != unreal.TextureCompressionSettings.TC_NORMALMAP:
                return self._makeResult(
                    asset_path, passed=False,
                    message=(
                        f"Normal map texture uses compression '{compression}' — "
                        f"should use TC_Normalmap."
                    ),
                    asset_class="Texture2D",
                    fix_hint=(
                        "Set Compression Settings to 'Normalmap (DXT5, BC5 "
                        "on DX11)' in the Texture Editor."
                    ),
                )

            return self._makeResult(
                asset_path, passed=True,
                message=f"Texture compression '{compression}' is acceptable.",
                asset_class="Texture2D",
            )
        except Exception as exc:  # noqa: BLE001 - Unreal bridge safety
            return self._makeSkipped(asset_path, f"Validation error: {exc}")