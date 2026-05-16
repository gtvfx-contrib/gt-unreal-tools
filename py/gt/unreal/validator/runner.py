"""Orchestrates the asset validation pipeline.

Discovers and instantiates rules from the :class:`RuleRegistry`, then runs
them against assets in a directory.  Supports both serial mode (safe inside
Unreal Editor) and parallel mode via :class:`concurrent.futures.ThreadPoolExecutor`.
The number of worker threads is controlled by the ``max_workers`` constructor
argument or the ``VALIDATOR_MAX_WORKERS`` environment variable.
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import time
from typing import Iterator, Type

from .config import Config
from .registry import registry
from .rules.base import AbstractRule, ValidationResult, Severity
from .reporting.models import ValidationReport

logger = logging.getLogger(__name__)


class ValidationRunner:
    """Orchestrates validation using rules sourced from the RuleRegistry.

    Discovers rules from the registry, instantiates them with the provided
    configuration, and runs them against assets in a directory — optionally
    using a thread pool for parallel processing.
    """

    def __init__(
        self,
        config: Config,
        category: str | None = None,
        severity: Severity | None = None,
        rules: list[Type[AbstractRule]] | None = None,
        context=None,
        allowlist=None,
        max_workers: int | None = None,
    ) -> None:
        """Initialise the runner with configuration and optional filters.

        Args:
            config: Layered Config object.
            category: Optional string filter — only rules in this category run.
            severity: Optional Severity filter.
            rules: Explicit list of rule classes — bypasses registry lookup.
            context: Optional ValidationContext instance (reserved for future use).
            allowlist: Optional AllowlistManager instance.
            max_workers: Number of worker threads.  ``1`` = serial (safe in
                Unreal).  Default: ``VALIDATOR_MAX_WORKERS`` env var or CPU count.
        """
        self.config    = config
        self.context   = context
        self.allowlist = allowlist
        self.max_workers = max_workers or int(
            os.environ.get("VALIDATOR_MAX_WORKERS", os.cpu_count() or 4)
        )

        if rules is not None:
            self.rules = [R(config) for R in rules]
        else:
            registry.discover()
            rule_classes = registry.get_rules(category=category, severity=severity)
            if not rule_classes:
                logger.warning(
                    "[ValidationRunner] No rules matched "
                    "(category=%r, severity=%r). Registered: %s",
                    category, severity, list(registry.list_rules().keys()),
                )
            self.rules = [R(config) for R in rule_classes]

    def validate_asset(self, asset_path: str) -> list[ValidationResult]:
        """Run every active rule against a single asset path.

        Args:
            asset_path: Filesystem or content-browser path of the asset.

        Returns:
            A list of :class:`ValidationResult` objects, one per rule.
        """
        results = []
        for rule in self.rules:
            t0 = time.perf_counter()
            result = rule.validate(asset_path)
            result.duration_ms = (time.perf_counter() - t0) * 1000
            results.append(result)
        return results

    def run_and_report(self, directory: str) -> ValidationReport:
        """Validate a directory and return an aggregated report.

        Assets are validated concurrently using a thread pool.  The number of
        worker threads is controlled by ``max_workers`` (default: CPU count) or
        the ``VALIDATOR_MAX_WORKERS`` environment variable.

        Note on thread safety: each ``rule.validate()`` call is independent.
        Rules must not share mutable state.  The Unreal Python API is generally
        NOT thread-safe; parallel processing is most beneficial in standalone
        (filesystem-only) mode.  In Unreal, set ``max_workers=1``.

        Args:
            directory: Root filesystem path or Unreal content path to validate.

        Returns:
            A :class:`ValidationReport` aggregating all rule results.
        """
        from . import __version__
        t0 = time.perf_counter()
        assets = list(self._iter_assets(directory))

        if self.max_workers == 1:
            all_results: list[ValidationResult] = []
            for asset_path in assets:
                all_results.extend(self.validate_asset(asset_path))
        else:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_workers,
                thread_name_prefix="validator",
            ) as executor:
                futures = {
                    executor.submit(self.validate_asset, path): path
                    for path in assets
                }
                all_results = []
                for future in concurrent.futures.as_completed(futures):
                    try:
                        all_results.extend(future.result())
                    except Exception as exc:  # noqa: BLE001 – thread boundary safety net; workers may raise any exception
                        asset_path = futures[future]
                        logger.error("[Runner] Error validating '%s': %s", asset_path, exc)

        duration = (time.perf_counter() - t0) * 1000
        return ValidationReport(
            results=all_results,
            asset_count=len(assets),
            rule_count=len(self.rules),
            duration_ms=duration,
            tool_version=__version__,
        )

    def _iter_assets(self, directory: str) -> Iterator[str]:
        """Yield asset paths from a directory.

        Handles both real filesystem paths and Unreal virtual content paths
        (e.g. ``/Game/``).  When an Unreal path is given and Unreal is
        available, uses :class:`UnrealContext` to enumerate via
        ``EditorAssetLibrary``.  Unreal's Python API is single-threaded;
        set ``max_workers=1`` in the constructor when using this from inside
        the Editor.

        Args:
            directory: Root filesystem path or Unreal content path.

        Raises:
            ValueError: If directory is neither a valid filesystem directory
                nor a resolvable Unreal content path.
        """
        from .env import UNREAL_AVAILABLE

        if not os.path.isdir(directory) and directory.startswith('/'):
            if not UNREAL_AVAILABLE:
                raise ValueError(
                    f"'{directory}' is an Unreal content path but Unreal Engine "
                    f"is not available.  Run inside Unreal Editor, or supply a "
                    f"real filesystem directory."
                )
            import unreal
            for asset_path in unreal.EditorAssetLibrary.list_assets(
                directory, recursive=True
            ):
                yield asset_path
        else:
            if not os.path.isdir(directory):
                raise ValueError(f"Not a valid directory: '{directory}'")
            for root, _dirs, files in os.walk(directory):
                for filename in sorted(files):
                    yield os.path.join(root, filename)