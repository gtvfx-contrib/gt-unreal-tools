"""Level of Detail (LOD) validation rules.

Rules:
    LODCountRule: Validates the LOD count for StaticMesh and SkeletalMesh assets.
    LODScreenSizeRatioRule: Validates that LOD screen size thresholds decrease monotonically.
"""
from __future__ import annotations

from .base import AbstractRule, Severity, ValidationResult
from ..env import load_unreal_asset
from ..errors import UnrealAPIError
from ..registry import registry


@registry.register(category="lod", severity=Severity.ERROR)
class LODCountRule(AbstractRule):
    """Validates the LOD count for StaticMesh and SkeletalMesh assets.

    Attributes:
        name: Rule identifier ``"lod_count"``.
        category: Rule category ``"lod"``.
        severity: :attr:`Severity.ERROR`.
    """
    name     = "lod_count"
    category = "lod"
    severity = Severity.ERROR

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate the LOD count of the given mesh asset.

        Args:
            asset_path: Content-browser path of the asset to validate.

        Returns:
            A :class:`ValidationResult` indicating whether the LOD count is within
            the configured minimum and maximum bounds.
        """
        try:
            asset = load_unreal_asset(asset_path)
        except UnrealAPIError as exc:
            return self._make_skipped(asset_path, str(exc))
        import unreal  # noqa: PLC0415 – local import; safe here because load_unreal_asset guarantees Unreal is available

        if not isinstance(asset, (unreal.StaticMesh, unreal.SkeletalMesh)):
            return self._make_skipped(
                asset_path,
                f"LOD count check only applies to StaticMesh/SkeletalMesh (got {type(asset).__name__})."
            )

        try:
            lod_count = asset.get_num_lods()
            min_lods: int = self.config.get("min_lod_count", 1)
            max_lods: int = self.config.get("max_lod_count", 8)
            asset_class = type(asset).__name__

            if lod_count < min_lods:
                return self._make_result(
                    asset_path, passed=False,
                    message=f"{asset_class} has {lod_count} LOD(s) — minimum is {min_lods}.",
                    asset_class=asset_class,
                    fix_hint=f"Add at least {min_lods - lod_count} more LOD level(s).",
                )
            if lod_count > max_lods:
                return self._make_result(
                    asset_path, passed=False,
                    message=f"{asset_class} has {lod_count} LOD(s) — maximum is {max_lods}.",
                    asset_class=asset_class,
                    fix_hint=f"Remove {lod_count - max_lods} LOD level(s).",
                )
            return self._make_result(
                asset_path, passed=True,
                message=f"{asset_class} has {lod_count} LOD(s) — within [{min_lods}, {max_lods}].",
                asset_class=asset_class,
            )
        except Exception as exc:  # noqa: BLE001 – Unreal C++ bridge raises undocumented exceptions
            return self._make_skipped(asset_path, f"Validation error: {exc}")


@registry.register(category="lod", severity=Severity.WARNING)
class LODScreenSizeRatioRule(AbstractRule):
    """Validates that LOD screen size thresholds decrease monotonically.

    Attributes:
        name: Rule identifier ``"lod_screen_size_ratio"``.
        category: Rule category ``"lod"``.
        severity: :attr:`Severity.WARNING`.
    """
    name     = "lod_screen_size_ratio"
    category = "lod"
    severity = Severity.WARNING

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate that LOD screen size thresholds decrease monotonically.

        Args:
            asset_path: Content-browser path of the asset to validate.

        Returns:
            A :class:`ValidationResult` indicating whether screen size values
            decrease correctly across all LOD levels.
        """
        try:
            asset = load_unreal_asset(asset_path)
        except UnrealAPIError as exc:
            return self._make_skipped(asset_path, str(exc))
        import unreal  # noqa: PLC0415 – local import; safe here because load_unreal_asset guarantees Unreal is available

        if not isinstance(asset, unreal.StaticMesh):
            return self._make_skipped(
                asset_path,
                f"LOD screen size check only applies to StaticMesh (got {type(asset).__name__})."
            )

        try:
            lod_count = asset.get_num_lods()
            if lod_count < 2:
                return self._make_result(
                    asset_path, passed=True,
                    message="Only one LOD — no screen size ratio to validate.",
                    asset_class="StaticMesh",
                )

            screen_sizes = []
            try:
                source_models = asset.get_editor_property("source_models")
                for i in range(lod_count):
                    lod_info = source_models[i]
                    size = lod_info.get_editor_property("screen_size")
                    screen_sizes.append(
                        size.default_value if hasattr(size, "default_value") else float(size)
                    )
            except Exception:  # noqa: BLE001 – Unreal C++ bridge raises undocumented exceptions
                return self._make_skipped(
                    asset_path,
                    "Could not read LOD screen sizes — may require resaving in Editor.",
                )

            min_ratio: float = self.config.get("min_lod_screen_size_ratio", 0.5)
            violations = []
            for i in range(1, len(screen_sizes)):
                prev = screen_sizes[i - 1]
                curr = screen_sizes[i]
                if prev <= 0:
                    continue
                # Screen sizes should be strictly decreasing
                if curr >= prev:
                    violations.append(
                        f"LOD{i - 1}({prev:.3f}) -> LOD{i}({curr:.3f}): not decreasing"
                    )

            if violations:
                return self._make_result(
                    asset_path, passed=False,
                    message=f"LOD screen size thresholds not monotonically decreasing: {violations}.",
                    asset_class="StaticMesh",
                    fix_hint="Adjust LOD screen size thresholds in the Static Mesh Editor to decrease with each LOD.",
                )
            return self._make_result(
                asset_path, passed=True,
                message=f"LOD screen size thresholds decrease correctly across {lod_count} LODs.",
                asset_class="StaticMesh",
            )
        except Exception as exc:  # noqa: BLE001 – Unreal C++ bridge raises undocumented exceptions
            return self._make_skipped(asset_path, f"Validation error: {exc}")