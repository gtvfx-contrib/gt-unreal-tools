"""Overdraw heuristic validation rule.

Since actual GPU overdraw cannot be measured without rendering, this module
provides a heuristic rule that flags assets likely to cause overdraw issues
based on translucent material usage.

Rules:
    OverdrawHeuristicRule: Flags assets likely to cause overdraw issues.

"""
from __future__ import annotations

import logging

from .base import AbstractRule, Severity, ValidationResult
from ..env import loadUnrealAsset
from ..errors import UnrealAPIError
from ..registry import registry

logger = logging.getLogger(__name__)


@registry.register(category="overdraw", severity=Severity.WARNING)
class OverdrawHeuristicRule(AbstractRule):
    """Heuristic rule to flag assets likely to cause overdraw issues.

    Since true GPU overdraw requires rendering, this rule uses heuristics:
    materials with translucent blend modes are high-overdraw candidates, and
    StaticMeshes with many translucent material slots compound the problem.

    Attributes:
        name: Rule identifier ``"overdraw_heuristic"``.
        category: Rule category ``"overdraw"``.
        severity: :attr:`Severity.WARNING`.
    
    """
    name     = "overdraw_heuristic"
    category = "overdraw"
    severity = Severity.WARNING

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate the overdraw heuristic for the given asset.

        Args:
            asset_path: Content-browser path of the asset to validate.

        Returns:
            A :class:`ValidationResult` indicating whether the asset is likely
            to cause excessive overdraw based on translucent material usage.
        
        """
        try:
            asset = loadUnrealAsset(asset_path)
        except UnrealAPIError as exc:
            return self._makeSkipped(asset_path, str(exc))
        import unreal  # noqa: PLC0415 - deferred Unreal import

        try:
            if isinstance(asset, unreal.StaticMesh):
                return self._checkStaticMesh(asset_path, asset)
            if isinstance(asset, unreal.Material):
                return self._checkMaterial(asset_path, asset)
        except Exception as exc:  # noqa: BLE001 - Unreal bridge safety
            return self._makeSkipped(asset_path, f"Validation error: {exc}")

        return self._makeSkipped(
            asset_path,
            f"Overdraw heuristic not applicable to {type(asset).__name__}."
        )

    def _checkStaticMesh(self, asset_path: str, asset) -> ValidationResult:
        """Check StaticMesh material slots for translucent materials.

        Args:
            asset_path: Content-browser path of the asset being validated.
            asset: The loaded ``unreal.StaticMesh`` object.

        Returns:
            A :class:`ValidationResult` indicating whether the translucent
            material slot count is within the configured limit.
        
        """
        import unreal  # noqa: PLC0415 - deferred Unreal import
        try:
            max_translucent: int = self.config.get("max_translucent_materials", 2)
            slots = asset.static_materials or []
            translucent_count = 0

            _translucent_modes = {
                unreal.BlendMode.BLEND_TRANSLUCENT,
                unreal.BlendMode.BLEND_ADDITIVE,
                unreal.BlendMode.BLEND_MODULATE,
            }

            for slot in slots:
                try:
                    mat = slot.material_interface
                    if mat is None:
                        continue
                    if isinstance(mat, unreal.Material):
                        blend = mat.blend_mode
                    else:
                        try:
                            base = mat.get_editor_property("parent")
                            blend = base.blend_mode if base else None
                        except Exception as exc:  # noqa: BLE001 - Unreal bridge safety
                            logger.debug(
                                "Skipping parent blend read for '%s': %s",
                                asset_path,
                                exc,
                            )
                            blend = None
                    if blend in _translucent_modes:
                        translucent_count += 1
                except Exception as exc:  # noqa: BLE001 - Unreal bridge safety
                    logger.debug("Skipping material slot for '%s': %s", asset_path, exc)

            if translucent_count > max_translucent:
                return self._makeResult(
                    asset_path, passed=False,
                    message=(
                        f"StaticMesh has {translucent_count} translucent material slot(s) — "
                        f"limit is {max_translucent}. High overdraw risk."
                    ),
                    asset_class="StaticMesh",
                    fix_hint=(
                        "Reduce translucent material usage. Use Masked or Opaque blend modes "
                        "where possible, or split the mesh into opaque and translucent sections."
                    ),
                )
            return self._makeResult(
                asset_path, passed=True,
                message=(
                    f"StaticMesh has {translucent_count} translucent "
                    "material(s) — within limit."
                ),
                asset_class="StaticMesh",
            )
        except Exception as exc:  # noqa: BLE001 - Unreal bridge safety
            return self._makeSkipped(asset_path, f"Validation error: {exc}")

    def _checkMaterial(self, asset_path: str, asset) -> ValidationResult:
        """Check a Material asset's blend mode directly.

        Args:
            asset_path: Content-browser path of the asset being validated.
            asset: The loaded ``unreal.Material`` object.

        Returns:
            A :class:`ValidationResult` indicating whether the material blend
            mode poses an overdraw risk.
        
        """
        import unreal  # noqa: PLC0415 - deferred Unreal import
        try:
            blend = asset.blend_mode
            is_translucent = blend in (
                unreal.BlendMode.BLEND_TRANSLUCENT,
                unreal.BlendMode.BLEND_ADDITIVE,
                unreal.BlendMode.BLEND_MODULATE,
            )
            if is_translucent:
                return self._makeResult(
                    asset_path, passed=False,
                    message=f"Material uses translucent blend mode '{blend}' — overdraw risk.",
                    asset_class="Material",
                    fix_hint="Use Opaque or Masked blend mode unless transparency is essential.",
                )
            return self._makeResult(
                asset_path, passed=True,
                message=f"Material blend mode '{blend}' — low overdraw risk.",
                asset_class="Material",
            )
        except Exception as exc:  # noqa: BLE001 - Unreal bridge safety
            return self._makeSkipped(asset_path, f"Validation error: {exc}")