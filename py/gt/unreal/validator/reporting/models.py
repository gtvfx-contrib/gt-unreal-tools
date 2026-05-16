"""ValidationReport dataclass with filtering and statistics helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..rules.base import ValidationResult, Severity


@dataclass
class ValidationReport:
    """Aggregated output of a full validation run.

    Attributes:
        results: Flat list of all :class:`~validator.rules.base.ValidationResult`
            objects.
        asset_count: Number of distinct asset files checked.
        rule_count: Number of rules that ran.
        duration_ms: Wall-clock time for the full run in milliseconds.
        tool_version: Framework version string.
        
    """
    results:      list[ValidationResult]
    asset_count:  int   = 0
    rule_count:   int   = 0
    duration_ms:  float = 0.0
    tool_version: str   = ""

    @property
    def total(self) -> int:
        """Total number of validation results (all statuses)."""
        return len(self.results)

    @property
    def passed(self) -> int:
        """Number of results that passed (non-skipped)."""
        return sum(1 for r in self.results if r.passed and not r.skipped)

    @property
    def failed(self) -> int:
        """Number of results that failed (non-skipped)."""
        return sum(1 for r in self.results if not r.passed and not r.skipped)

    @property
    def skipped(self) -> int:
        """Number of results that were skipped."""
        return sum(1 for r in self.results if r.skipped)

    @property
    def errors(self) -> int:
        """Number of ERROR-severity failures."""
        return sum(
            1 for r in self.results
            if not r.passed and not r.skipped and r.severity == Severity.ERROR
        )

    @property
    def warnings(self) -> int:
        """Number of WARNING-severity failures."""
        return sum(
            1 for r in self.results
            if not r.passed and not r.skipped and r.severity == Severity.WARNING
        )

    @property
    def infos(self) -> int:
        """Number of INFO-severity failures."""
        return sum(
            1 for r in self.results
            if not r.passed and not r.skipped and r.severity == Severity.INFO
        )

    def hasErrors(self) -> bool:
        """Return True if any ERROR-severity rule failed."""
        return self.errors > 0

    def summaryLine(self) -> str:
        """Single-line human-readable summary."""
        status = "FAIL" if self.hasErrors() else "PASS"
        return (
            f"[{status}] {self.asset_count} assets | "
            f"{self.failed} failures ({self.errors} errors, {self.warnings} warnings) | "
            f"{self.skipped} skipped | "
            f"{self.duration_ms:.0f}ms"
        )

    def filterBySeverity(self, severity: Severity) -> list[ValidationResult]:
        """Return only results matching the given severity.

        Args:
            severity: The severity level to filter by.

        Returns:
            A list of :class:`~validator.rules.base.ValidationResult` objects
            whose severity matches.
        """
        return [r for r in self.results if r.severity == severity]

    def filterByCategory(self, category: str) -> list[ValidationResult]:
        """Return only results matching the given category.

        Args:
            category: The rule category to filter by.

        Returns:
            A list of :class:`~validator.rules.base.ValidationResult` objects
            whose category matches.
        """
        return [r for r in self.results if r.category == category]

    def failures(self) -> list[ValidationResult]:
        """Return only failed (non-skipped) results."""
        return [r for r in self.results if not r.passed and not r.skipped]

    def passing(self) -> list[ValidationResult]:
        """Return only passed (non-skipped) results."""
        return [r for r in self.results if r.passed and not r.skipped]

    def assetsWithFailures(self) -> dict[str, list[ValidationResult]]:
        """Group failed results by asset path."""
        grouped: dict[str, list[ValidationResult]] = {}
        for r in self.failures():
            grouped.setdefault(r.asset_path, []).append(r)
        return grouped