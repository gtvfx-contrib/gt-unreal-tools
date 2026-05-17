"""Reusable entry-point helpers for running the GT validator from Unreal Editor.

Provides thin public functions that context-menu scripts and other callers can
invoke in a single line, keeping those scripts free of boilerplate.

Public API
----------
runOnSelectedAssets()
    Validate the assets currently selected in the Content Browser.

runOnSelectedFolders()
    Validate all assets in the folder(s) selected in the Content Browser
    path view (``ContentBrowser.FolderContextMenu``).

runOnPath(content_path)
    Validate all assets under an explicit content-browser path.

"""
from __future__ import annotations

from pathlib import Path

import unreal

from gt.unreal.validator.config import Config
from gt.unreal.validator.errors import UnrealAPIError
from gt.unreal.validator.reporting import HTMLFormatter, JSONFormatter
from gt.unreal.validator.reporting.models import ValidationReport
from gt.unreal.validator.runner import ValidationRunner


# ── Logging ───────────────────────────────────────────────────────────────── #

def _log(message: str) -> None:
    """Print a message to the Unreal Output Log."""
    unreal.log(message)


def _logWarning(message: str) -> None:
    """Print a warning to the Unreal Output Log."""
    unreal.log_warning(message)


def _logError(message: str) -> None:
    """Print an error to the Unreal Output Log."""
    unreal.log_error(message)


# ── Internal helpers ──────────────────────────────────────────────────────── #

def _makeRunner() -> ValidationRunner:
    """Create a serial ValidationRunner configured for Unreal Editor."""
    config = Config()
    runner = ValidationRunner(config, max_workers=1)
    if not runner.rules:
        _logWarning("[Validator] No rules matched. Check your validator/rules/ folder.")
    else:
        _log(f"[Validator] Rules active: {[type(r).__name__ for r in runner.rules]}")
    return runner


def _outputReport(report: ValidationReport) -> None:
    """Log failures, print the summary line, and write JSON + HTML artifacts."""
    for result in report.failures():
        _logError(str(result))

    _log(report.summaryLine())

    if report.hasErrors():
        _logError(
            f"[Validator] {report.failed} failure(s) found. "
            "See Output Log for details."
        )
    else:
        _log("[Validator] Validation complete — no errors found.")

    home = Path.home()
    json_report = home / "validation" / "report.json"
    json_report.parent.mkdir(parents=True, exist_ok=True)
    json_report.write_text(JSONFormatter().render(report))

    html_report = home / "validation" / "report.html"
    html_report.write_text(HTMLFormatter().render(report))


# ── Public API ────────────────────────────────────────────────────────────── #

def runOnSelectedAssets() -> None:
    """Validate the assets currently selected in the Content Browser.

    Reads the current Content Browser asset selection via
    ``EditorUtilityLibrary.get_selected_assets()``.

    Raises:
        UnrealAPIError: If the Unreal Python bridge raises during validation.

    """
    selections = unreal.EditorUtilityLibrary.get_selected_assets()
    if not selections:
        _logWarning("[Validator] No assets selected.")
        return
    paths = [s.get_path_name() for s in selections]
    _log(f"[Validator] Validating {len(paths)} selected asset(s)...")
    try:
        report = _makeRunner().validateAssets(paths)
    except UnrealAPIError as exc:
        _logError(f"[Validator] Unreal API error: {exc}")
        raise
    _outputReport(report)


def runOnSelectedFolders() -> None:
    """Validate all assets in the folder(s) selected in the path view.

    Reads the current Content Browser folder selection via
    ``EditorUtilityLibrary.get_selected_path_view_folder_paths()``.
    Assets in multiple selected folders are deduplicated before validation.

    Raises:
        UnrealAPIError: If the Unreal Python bridge raises during validation.

    """
    folders = list(unreal.EditorUtilityLibrary.get_selected_path_view_folder_paths())
    if not folders:
        _logWarning("[Validator] No folders selected.")
        return
    _log(f"[Validator] Validating {len(folders)} selected folder(s)...")

    seen: set[str] = set()
    asset_paths: list[str] = []
    for folder in folders:
        # get_selected_path_view_folder_paths() returns /All/Game/... paths.
        # list_assets expects /Game/... — strip the /All prefix if present.
        folder_path = folder[4:] if folder.startswith('/All') else folder
        # list_assets requires a trailing slash
        if not folder_path.endswith('/'):
            folder_path = folder_path + '/'
        folder_assets = list(
            unreal.EditorAssetLibrary.list_assets(folder_path, recursive=True)
        )
        _log(f"[Validator] {folder_path} — {len(folder_assets)} asset(s) found")
        for ap in folder_assets:
            if ap not in seen:
                seen.add(ap)
                asset_paths.append(ap)

    if not asset_paths:
        _logWarning("[Validator] No assets found in the selected folder(s).")
        return

    try:
        report = _makeRunner().validateAssets(asset_paths)
    except UnrealAPIError as exc:
        _logError(f"[Validator] Unreal API error: {exc}")
        raise
    _outputReport(report)


def runOnPath(content_path: str = "/Game/") -> None:
    """Validate all assets under an explicit content-browser path.

    Args:
        content_path: Unreal content-browser path to validate, e.g.
            ``"/Game/"`` or ``"/Game/Characters/"``.

    Raises:
        UnrealAPIError: If the Unreal Python bridge raises during validation.
        ValueError: If ``content_path`` cannot be resolved.

    """
    _log(f"[Validator] Validating content path: {content_path}")
    try:
        report = _makeRunner().runAndReport(content_path)
    except (UnrealAPIError, ValueError) as exc:
        _logError(f"[Validator] Error during validation: {exc}")
        raise
    _outputReport(report)
