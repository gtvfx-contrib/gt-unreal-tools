"""Niagara particle system validation rules.

Rules:
    NiagaraEmitterCountRule: Validates the emitter count is within the limit.
    NiagaraFixedBoundsRule: Validates that fixed bounds are enabled.
    NiagaraGPUSimRule: Validates GPU simulation usage against project policy.
"""
from __future__ import annotations

import logging

from .base import AbstractRule, Severity, ValidationResult
from ..env import loadUnrealAsset
from ..errors import UnrealAPIError
from ..registry import registry

logger = logging.getLogger(__name__)


@registry.register(category="niagara", severity=Severity.WARNING)
class NiagaraEmitterCountRule(AbstractRule):
    """Validates the number of emitters in a Niagara system.

    Attributes:
        name: Rule identifier ``"niagara_emitter_count"``.
        category: Rule category ``"niagara"``.
        severity: :attr:`Severity.WARNING`.
    """
    name     = "niagara_emitter_count"
    category = "niagara"
    severity = Severity.WARNING

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate the emitter count of the given Niagara system.

        Args:
            asset_path: Content-browser path of the asset to validate.

        Returns:
            A :class:`ValidationResult` indicating whether the emitter count
            is within the configured limit.
        """
        try:
            asset = loadUnrealAsset(asset_path)
        except UnrealAPIError as exc:
            return self._makeSkipped(asset_path, str(exc))
        import unreal  # noqa: PLC0415 – local import; safe here because loadUnrealAsset guarantees Unreal is available

        if not isinstance(asset, unreal.NiagaraSystem):
            return self._makeSkipped(
                asset_path, f"Not a NiagaraSystem (got {type(asset).__name__})."
            )

        try:
            emitters = asset.get_editor_property("emitter_handles") or []
            emitter_count = len(emitters)
            max_emitters: int = self.config.get("max_niagara_emitters", 8)

            if emitter_count > max_emitters:
                return self._makeResult(
                    asset_path, passed=False,
                    message=f"Niagara system has {emitter_count} emitters — limit is {max_emitters}.",
                    asset_class="NiagaraSystem",
                    fix_hint=(
                        f"Consolidate emitters. Reduce to {max_emitters} or fewer "
                        f"by merging similar emitters."
                    ),
                )
            return self._makeResult(
                asset_path, passed=True,
                message=f"Niagara system has {emitter_count} emitter(s) — within limit of {max_emitters}.",
                asset_class="NiagaraSystem",
            )
        except Exception as exc:  # noqa: BLE001 – Unreal C++ bridge raises undocumented exceptions
            return self._makeSkipped(asset_path, f"Validation error: {exc}")


@registry.register(category="niagara", severity=Severity.ERROR)
class NiagaraFixedBoundsRule(AbstractRule):
    """Validates that Niagara systems have fixed bounds set.

    Dynamic bounds force the engine to recompute bounds every frame, which
    is expensive for large particle systems.

    Attributes:
        name: Rule identifier ``"niagara_fixed_bounds"``.
        category: Rule category ``"niagara"``.
        severity: :attr:`Severity.ERROR`.
    """
    name     = "niagara_fixed_bounds"
    category = "niagara"
    severity = Severity.ERROR

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate that fixed bounds are configured on the given Niagara system.

        Args:
            asset_path: Content-browser path of the asset to validate.

        Returns:
            A :class:`ValidationResult` indicating whether fixed bounds are set,
            or a passing result when the check is disabled via config.
        """
        require_fixed: bool = self.config.get("require_niagara_fixed_bounds", True)
        if not require_fixed:
            return self._makeResult(
                asset_path, passed=True,
                message="Fixed bounds check disabled via config.",
                asset_class="NiagaraSystem",
            )

        try:
            asset = loadUnrealAsset(asset_path)
        except UnrealAPIError as exc:
            return self._makeSkipped(asset_path, str(exc))
        import unreal  # noqa: PLC0415 – local import; safe here because loadUnrealAsset guarantees Unreal is available

        if not isinstance(asset, unreal.NiagaraSystem):
            return self._makeSkipped(
                asset_path, f"Not a NiagaraSystem (got {type(asset).__name__})."
            )

        try:
            fixed_bounds = asset.get_editor_property("fixed_bounds")
            if not fixed_bounds:
                return self._makeResult(
                    asset_path, passed=False,
                    message="Niagara system does not have fixed bounds set.",
                    asset_class="NiagaraSystem",
                    fix_hint=(
                        "Enable 'Fixed Bounds' in the Niagara System editor and set "
                        "appropriate values to avoid per-frame bounds calculation."
                    ),
                )
            return self._makeResult(
                asset_path, passed=True,
                message="Niagara system has fixed bounds configured.",
                asset_class="NiagaraSystem",
            )
        except Exception as exc:  # noqa: BLE001 – Unreal C++ bridge raises undocumented exceptions
            return self._makeSkipped(asset_path, f"Validation error: {exc}")


@registry.register(category="niagara", severity=Severity.WARNING)
class NiagaraGPUSimRule(AbstractRule):
    """Validates GPU simulation usage in Niagara systems.

    Attributes:
        name: Rule identifier ``"niagara_gpu_sim"``.
        category: Rule category ``"niagara"``.
        severity: :attr:`Severity.WARNING`.
    """
    name     = "niagara_gpu_sim"
    category = "niagara"
    severity = Severity.WARNING

    def validate(self, asset_path: str) -> ValidationResult:
        """Validate GPU simulation usage in the given Niagara system.

        Args:
            asset_path: Content-browser path of the asset to validate.

        Returns:
            A :class:`ValidationResult` indicating whether GPU simulation emitters
            comply with the project policy.
        """
        try:
            asset = loadUnrealAsset(asset_path)
        except UnrealAPIError as exc:
            return self._makeSkipped(asset_path, str(exc))
        import unreal  # noqa: PLC0415 – local import; safe here because loadUnrealAsset guarantees Unreal is available

        if not isinstance(asset, unreal.NiagaraSystem):
            return self._makeSkipped(
                asset_path, f"Not a NiagaraSystem (got {type(asset).__name__})."
            )

        try:
            allow_gpu: bool = self.config.get("allow_gpu_simulation", True)
            emitters = asset.get_editor_property("emitter_handles") or []
            gpu_emitters = []

            for handle in emitters:
                try:
                    emitter = handle.get_editor_property("instance")
                    sim_target = emitter.get_editor_property("sim_target")
                    if "GPU" in str(sim_target).upper():
                        name = handle.get_editor_property("name")
                        gpu_emitters.append(str(name))
                except Exception as exc:  # noqa: BLE001 – Unreal C++ bridge raises undocumented exceptions
                    logger.debug("Skipping emitter handle for '%s': %s", asset_path, exc)

            if gpu_emitters and not allow_gpu:
                return self._makeResult(
                    asset_path, passed=False,
                    message=(
                        f"GPU simulation is disabled by policy, but {len(gpu_emitters)} "
                        f"emitter(s) use GPU sim: {gpu_emitters}."
                    ),
                    asset_class="NiagaraSystem",
                    fix_hint="Set emitter Simulation Target to 'CPU Simulation' or enable allow_gpu_simulation in config.",
                )

            if gpu_emitters:
                return self._makeResult(
                    asset_path, passed=True,
                    message=f"{len(gpu_emitters)} GPU emitter(s) detected — GPU simulation is allowed.",
                    asset_class="NiagaraSystem",
                )
            return self._makeResult(
                asset_path, passed=True,
                message="No GPU simulation emitters detected.",
                asset_class="NiagaraSystem",
            )
        except Exception as exc:  # noqa: BLE001 – Unreal C++ bridge raises undocumented exceptions
            return self._makeSkipped(asset_path, f"Validation error: {exc}")