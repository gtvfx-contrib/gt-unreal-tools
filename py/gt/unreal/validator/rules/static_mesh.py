"""StaticMesh validation rules.

Rules:
    StaticMeshLODCountRule: Validates the LOD count is within the configured range.
    StaticMeshMaterialSlotRule: Validates the material slot count is within the limit.
    StaticMeshBoundsRule: Validates the bounding box extent is within the limit.

"""
from __future__ import annotations

from .base import AbstractRule, Severity, ValidationResult
from ..env import loadUnrealAsset
from ..errors import UnrealAPIError
from ..registry import registry


@registry.register(category="static_mesh", severity=Severity.ERROR)
class StaticMeshLODCountRule(AbstractRule):
    """Validates that a StaticMesh has the required number of LODs.

    Attributes:
        name: Rule identifier ``"static_mesh_lod_count"``.
        category: Rule category ``"static_mesh"``.
        severity: :attr:`Severity.ERROR`.
    
    """
    name     = "static_mesh_lod_count"
    category = "static_mesh"
    severity = Severity.ERROR

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate the LOD count of the given StaticMesh asset.

        Args:
            asset_path: Content-browser path of the asset to validate.

        Returns:
            A :class:`ValidationResult` indicating whether the LOD count is within
            the configured minimum and maximum bounds.
        
        """
        try:
            asset = loadUnrealAsset(asset_path)
        except UnrealAPIError as exc:
            return self._makeSkipped(asset_path, str(exc))
        import unreal  # noqa: PLC0415 - deferred Unreal import

        if not isinstance(asset, unreal.StaticMesh):
            return self._makeSkipped(asset_path, f"Not a StaticMesh (got {type(asset).__name__}).")

        try:
            lod_count = asset.get_num_lods()
            min_lods: int = self.config.get("min_lod_count", 1)
            max_lods: int = self.config.get("max_lod_count", 8)

            if lod_count < min_lods:
                return self._makeResult(
                    asset_path, passed=False,
                    message=f"StaticMesh has {lod_count} LOD(s) — minimum required is {min_lods}.",
                    asset_class="StaticMesh",
                    fix_hint=(
                        f"Add at least {min_lods - lod_count} more LOD "
                        "level(s) in the Static Mesh Editor."
                    ),
                )
            if lod_count > max_lods:
                return self._makeResult(
                    asset_path, passed=False,
                    message=f"StaticMesh has {lod_count} LOD(s) — maximum allowed is {max_lods}.",
                    asset_class="StaticMesh",
                    fix_hint=f"Remove {lod_count - max_lods} LOD level(s) to reduce to {max_lods}.",
                )
            return self._makeResult(
                asset_path, passed=True,
                message=f"StaticMesh has {lod_count} LOD(s) — within [{min_lods}, {max_lods}].",
                asset_class="StaticMesh",
            )
        except Exception as exc:  # noqa: BLE001 - Unreal bridge safety
            return self._makeSkipped(asset_path, f"Validation error: {exc}")


@registry.register(category="static_mesh", severity=Severity.WARNING)
class StaticMeshMaterialSlotRule(AbstractRule):
    """Validates the number of material slots on a StaticMesh.

    Attributes:
        name: Rule identifier ``"static_mesh_material_slots"``.
        category: Rule category ``"static_mesh"``.
        severity: :attr:`Severity.WARNING`.
    
    """
    name     = "static_mesh_material_slots"
    category = "static_mesh"
    severity = Severity.WARNING

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate the material slot count of the given StaticMesh asset.

        Args:
            asset_path: Content-browser path of the asset to validate.

        Returns:
            A :class:`ValidationResult` indicating whether the number of material
            slots is within the configured limit.
        
        """
        try:
            asset = loadUnrealAsset(asset_path)
        except UnrealAPIError as exc:
            return self._makeSkipped(asset_path, str(exc))
        import unreal  # noqa: PLC0415 - deferred Unreal import

        if not isinstance(asset, unreal.StaticMesh):
            return self._makeSkipped(asset_path, f"Not a StaticMesh (got {type(asset).__name__}).")

        try:
            slot_count = len(asset.static_materials)
            max_slots: int = self.config.get("max_material_slots", 4)

            if slot_count > max_slots:
                return self._makeResult(
                    asset_path, passed=False,
                    message=f"StaticMesh has {slot_count} material slots — maximum is {max_slots}.",
                    asset_class="StaticMesh",
                    fix_hint="Merge materials in your DCC tool to reduce the material slot count.",
                )
            return self._makeResult(
                asset_path, passed=True,
                message=(
                    f"StaticMesh has {slot_count} material slot(s) — "
                    f"within limit of {max_slots}."
                ),
                asset_class="StaticMesh",
            )
        except Exception as exc:  # noqa: BLE001 - Unreal bridge safety
            return self._makeSkipped(asset_path, f"Validation error: {exc}")


@registry.register(category="static_mesh", severity=Severity.WARNING)
class StaticMeshBoundsRule(AbstractRule):
    """Validates the bounding box extent of a StaticMesh.

    Attributes:
        name: Rule identifier ``"static_mesh_bounds"``.
        category: Rule category ``"static_mesh"``.
        severity: :attr:`Severity.WARNING`.
    
    """
    name     = "static_mesh_bounds"
    category = "static_mesh"
    severity = Severity.WARNING

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate the bounding box extent of the given StaticMesh asset.

        Args:
            asset_path: Content-browser path of the asset to validate.

        Returns:
            A :class:`ValidationResult` indicating whether the bounding box extent
            is within the configured limit.
        
        """
        try:
            asset = loadUnrealAsset(asset_path)
        except UnrealAPIError as exc:
            return self._makeSkipped(asset_path, str(exc))
        import unreal  # noqa: PLC0415 - deferred Unreal import

        if not isinstance(asset, unreal.StaticMesh):
            return self._makeSkipped(asset_path, f"Not a StaticMesh (got {type(asset).__name__}).")

        try:
            bounds = asset.get_bounding_box()
            extent = bounds.get_extent()
            max_component = max(abs(extent.x), abs(extent.y), abs(extent.z))
            max_uu: float = self.config.get("max_bounds_extent_uu", 500.0)

            if max_component > max_uu:
                return self._makeResult(
                    asset_path, passed=False,
                    message=(
                        f"Bounds extent {max_component:.1f} UU exceeds limit {max_uu} UU "
                        f"(X={extent.x:.1f}, Y={extent.y:.1f}, Z={extent.z:.1f})."
                    ),
                    asset_class="StaticMesh",
                    fix_hint=(
                        "Check the mesh scale — it may have been imported "
                        "with incorrect units."
                    ),
                )
            return self._makeResult(
                asset_path, passed=True,
                message=(
                    f"Bounds extent {max_component:.1f} UU — within limit "
                    f"of {max_uu} UU."
                ),
                asset_class="StaticMesh",
            )
        except Exception as exc:  # noqa: BLE001 - Unreal bridge safety
            return self._makeSkipped(asset_path, f"Validation error: {exc}")