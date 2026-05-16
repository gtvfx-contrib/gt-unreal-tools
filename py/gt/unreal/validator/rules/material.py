"""Material validation rules.

Rules:
    MaterialBlendModeRule: Flags materials with translucent blend modes.
    MaterialTwoSidedRule: Flags materials with two-sided rendering enabled.
    MaterialTextureSampleRule: Validates the texture sample count is within the limit.
    MaterialExpensiveNodeRule: Detects expensive shader nodes in the material graph.
"""
from __future__ import annotations

from .base import AbstractRule, Severity, ValidationResult
from ..env import loadUnrealAsset
from ..errors import UnrealAPIError
from ..registry import registry


@registry.register(category="material", severity=Severity.WARNING)
class MaterialBlendModeRule(AbstractRule):
    """Flags materials with translucent blend modes.

    Translucent materials incur extra rendering overhead.  This rule warns
    when a material uses translucent, additive, or modulate blending.

    Attributes:
        name: Rule identifier ``"material_blend_mode"``.
        category: Rule category ``"material"``.
        severity: :attr:`Severity.WARNING`.
    """
    name     = "material_blend_mode"
    category = "material"
    severity = Severity.WARNING

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate the blend mode of the given material asset.

        Args:
            asset_path: Content-browser path of the asset to validate.

        Returns:
            A :class:`ValidationResult` indicating whether the material uses an
            acceptable blend mode.
        """
        try:
            asset = loadUnrealAsset(asset_path)
        except UnrealAPIError as exc:
            return self._makeSkipped(asset_path, str(exc))
        import unreal  # noqa: PLC0415 – local import; safe here because loadUnrealAsset guarantees Unreal is available

        if not isinstance(asset, unreal.Material):
            return self._makeSkipped(asset_path, f"Not a Material (got {type(asset).__name__}).")

        try:
            blend_mode = asset.blend_mode
            is_translucent = blend_mode in (
                unreal.BlendMode.BLEND_TRANSLUCENT,
                unreal.BlendMode.BLEND_ADDITIVE,
                unreal.BlendMode.BLEND_MODULATE,
            )

            if is_translucent:
                return self._makeResult(
                    asset_path, passed=False,
                    message=(
                        f"Material uses translucent blend mode '{blend_mode}'. "
                        f"Translucent materials are expensive — use with caution."
                    ),
                    asset_class="Material",
                    fix_hint="Consider using Masked or Opaque blend mode if transparency is not essential.",
                )
            return self._makeResult(
                asset_path, passed=True,
                message=f"Material blend mode '{blend_mode}' is acceptable.",
                asset_class="Material",
            )
        except Exception as exc:  # noqa: BLE001 – Unreal C++ bridge raises undocumented exceptions
            return self._makeSkipped(asset_path, f"Validation error: {exc}")


@registry.register(category="material", severity=Severity.INFO)
class MaterialTwoSidedRule(AbstractRule):
    """Flags materials with two-sided rendering enabled.

    Two-sided rendering doubles the number of fragments to shade.

    Attributes:
        name: Rule identifier ``"material_two_sided"``.
        category: Rule category ``"material"``.
        severity: :attr:`Severity.INFO`.
    """
    name     = "material_two_sided"
    category = "material"
    severity = Severity.INFO

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate the two-sided setting of the given material asset.

        Args:
            asset_path: Content-browser path of the asset to validate.

        Returns:
            A :class:`ValidationResult` indicating whether two-sided rendering
            is disabled on the material.
        """
        try:
            asset = loadUnrealAsset(asset_path)
        except UnrealAPIError as exc:
            return self._makeSkipped(asset_path, str(exc))
        import unreal  # noqa: PLC0415 – local import; safe here because loadUnrealAsset guarantees Unreal is available

        if not isinstance(asset, unreal.Material):
            return self._makeSkipped(asset_path, f"Not a Material (got {type(asset).__name__}).")

        try:
            if asset.two_sided:
                return self._makeResult(
                    asset_path, passed=False,
                    message="Material has Two-Sided rendering enabled — increases draw call cost.",
                    asset_class="Material",
                    fix_hint="Disable Two-Sided unless required (e.g., foliage). Consider geometry normals instead.",
                )
            return self._makeResult(
                asset_path, passed=True,
                message="Material Two-Sided is disabled.",
                asset_class="Material",
            )
        except Exception as exc:  # noqa: BLE001 – Unreal C++ bridge raises undocumented exceptions
            return self._makeSkipped(asset_path, f"Validation error: {exc}")


@registry.register(category="material", severity=Severity.WARNING)
class MaterialTextureSampleRule(AbstractRule):
    """Validates the number of texture samples in a material is within the limit.

    Attributes:
        name: Rule identifier ``"material_texture_samples"``.
        category: Rule category ``"material"``.
        severity: :attr:`Severity.WARNING`.
    """
    name     = "material_texture_samples"
    category = "material"
    severity = Severity.WARNING

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate the texture sample count of the given material asset.

        Args:
            asset_path: Content-browser path of the asset to validate.

        Returns:
            A :class:`ValidationResult` indicating whether the number of texture
            samples is within the configured limit.
        """
        try:
            asset = loadUnrealAsset(asset_path)
        except UnrealAPIError as exc:
            return self._makeSkipped(asset_path, str(exc))
        import unreal  # noqa: PLC0415 – local import; safe here because loadUnrealAsset guarantees Unreal is available

        if not isinstance(asset, unreal.Material):
            return self._makeSkipped(asset_path, f"Not a Material (got {type(asset).__name__}).")

        try:
            expressions = asset.get_editor_property("expressions") or []
            sample_count = sum(
                1 for expr in expressions
                if isinstance(expr, unreal.MaterialExpressionTextureSample)
            )
            max_samples: int = self.config.get("max_texture_samples", 16)

            if sample_count > max_samples:
                return self._makeResult(
                    asset_path, passed=False,
                    message=f"Material has {sample_count} texture samples — limit is {max_samples}.",
                    asset_class="Material",
                    fix_hint="Consolidate texture channels into packed textures to reduce sample count.",
                )
            return self._makeResult(
                asset_path, passed=True,
                message=f"Material has {sample_count} texture sample(s) — within limit of {max_samples}.",
                asset_class="Material",
            )
        except Exception as exc:  # noqa: BLE001 – Unreal C++ bridge raises undocumented exceptions
            return self._makeSkipped(asset_path, f"Validation error: {exc}")


@registry.register(category="material", severity=Severity.WARNING)
class MaterialExpensiveNodeRule(AbstractRule):
    """Detects expensive shader nodes in the material graph.

    Nodes such as ``sin``, ``cos``, ``pow``, and ``noise`` significantly
    increase shader complexity and compile time.

    Attributes:
        name: Rule identifier ``"material_expensive_nodes"``.
        category: Rule category ``"material"``.
        severity: :attr:`Severity.WARNING`.
    """
    name     = "material_expensive_nodes"
    category = "material"
    severity = Severity.WARNING

    _EXPENSIVE_TYPES = (
        "MaterialExpressionSine",
        "MaterialExpressionCosine",
        "MaterialExpressionPower",
        "MaterialExpressionNoise",
        "MaterialExpressionPerlinNoise3D",
        "MaterialExpressionVectorNoise",
    )

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate that the material graph contains no expensive nodes.

        Args:
            asset_path: Content-browser path of the asset to validate.

        Returns:
            A :class:`ValidationResult` indicating whether any expensive shader
            nodes were detected in the material expression graph.
        """
        try:
            asset = loadUnrealAsset(asset_path)
        except UnrealAPIError as exc:
            return self._makeSkipped(asset_path, str(exc))
        import unreal  # noqa: PLC0415 – local import; safe here because loadUnrealAsset guarantees Unreal is available

        if not isinstance(asset, unreal.Material):
            return self._makeSkipped(asset_path, f"Not a Material (got {type(asset).__name__}).")

        try:
            expressions = asset.get_editor_property("expressions") or []
            expensive = [
                type(expr).__name__
                for expr in expressions
                if type(expr).__name__ in self._EXPENSIVE_TYPES
            ]

            if expensive:
                return self._makeResult(
                    asset_path, passed=False,
                    message=f"Material contains expensive nodes: {expensive}.",
                    asset_class="Material",
                    fix_hint="Consider baking expensive operations into textures using Bake Material Attributes.",
                )
            return self._makeResult(
                asset_path, passed=True,
                message="No expensive material nodes detected.",
                asset_class="Material",
            )
        except Exception as exc:  # noqa: BLE001 – Unreal C++ bridge raises undocumented exceptions
            return self._makeSkipped(asset_path, f"Validation error: {exc}")