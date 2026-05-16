"""Output formatters for :class:`~validator.reporting.models.ValidationReport`.

Implements:

- :class:`ConsoleFormatter` — human-readable terminal output
- :class:`JSONFormatter` — machine-readable JSON output
- :class:`HTMLFormatter` — self-contained HTML report for CI artifacts

"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .models import ValidationReport
from ..rules.base import ValidationResult, Severity


class ConsoleFormatter:
    """Formats a ValidationReport for human-readable terminal output.

    Args:
        show_passing: Include passing results in output (default: ``False``).
    """

    def __init__(self, show_passing: bool = False) -> None:
        self.show_passing = show_passing

    def format(self, report: ValidationReport) -> str:
        """Format the report as a human-readable terminal string.

        Args:
            report: The :class:`~validator.reporting.models.ValidationReport`
                to format.

        Returns:
            A multi-line string suitable for printing to a terminal.
        """
        lines: list[str] = []
        sep = "=" * 72

        lines.append(sep)
        lines.append("  Asset Validation Report")
        lines.append(f"  Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if report.tool_version:
            lines.append(f"  Framework : v{report.tool_version}")
        lines.append(sep)
        lines.append("")

        by_asset: dict[str, list[ValidationResult]] = {}
        for r in report.results:
            by_asset.setdefault(r.asset_path, []).append(r)

        for asset_path, results in sorted(by_asset.items()):
            failures = [r for r in results if not r.passed and not r.skipped]
            skipped  = [r for r in results if r.skipped]
            passing  = [r for r in results if r.passed and not r.skipped]

            if not failures and not self.show_passing and not skipped:
                continue

            lines.append(f"  Asset: {asset_path}")
            lines.append("  " + "-" * 68)

            for r in sorted(failures, key=lambda x: x.severity.value):
                lines.append(f"    [FAIL] [{r.severity.value:<7}] {r.rule_name}")
                lines.append(f"           {r.message}")
                if r.fix_hint:
                    lines.append(f"           Hint: {r.fix_hint}")

            for r in skipped:
                lines.append(f"    [SKIP] [SKIP   ] {r.rule_name}")
                lines.append(f"           {r.message}")

            if self.show_passing:
                for r in passing:
                    lines.append(f"    [PASS] [OK     ] {r.rule_name}")
                    lines.append(f"           {r.message}")

            lines.append("")

        lines.append(sep)
        lines.append(f"  {report.summaryLine()}")
        lines.append(f"  Rules run      : {report.rule_count}")
        lines.append(f"  Assets checked : {report.asset_count}")
        lines.append(f"  Duration       : {report.duration_ms:.0f}ms")
        lines.append(sep)
        return "\n".join(lines)


class JSONFormatter:
    """Formats a ValidationReport as JSON.

    Args:
        show_passing: Include passing results in output (default: ``False``).
    """

    def __init__(self, show_passing: bool = False) -> None:
        self.show_passing = show_passing

    def format(self, report: ValidationReport) -> str:
        """Format the report as a JSON string.

        Args:
            report: The :class:`~validator.reporting.models.ValidationReport`
                to format.

        Returns:
            A JSON-encoded string representing the report.
        """
        results_data = []
        for r in report.results:
            if not self.show_passing and r.passed and not r.skipped:
                continue
            results_data.append({
                "asset_path":  r.asset_path,
                "rule_name":   r.rule_name,
                "category":    r.category,
                "severity":    r.severity.value,
                "passed":      r.passed,
                "skipped":     r.skipped,
                "message":     r.message,
                "fix_hint":    r.fix_hint,
                "asset_class": r.asset_class,
                "timestamp":   r.timestamp,
                "duration_ms": round(r.duration_ms, 3),
            })

        payload: dict[str, Any] = {
            "generated_at":  datetime.now().isoformat(),
            "tool_version":  report.tool_version,
            "summary": {
                "status":       "FAIL" if report.hasErrors() else "PASS",
                "asset_count":  report.asset_count,
                "rule_count":   report.rule_count,
                "duration_ms":  round(report.duration_ms, 3),
                "total":        report.total,
                "passed":       report.passed,
                "failed":       report.failed,
                "skipped":      report.skipped,
                "errors":       report.errors,
                "warnings":     report.warnings,
                "infos":        report.infos,
            },
            "results": results_data,
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)

class HTMLFormatter:
    """Formats a ValidationReport as a self-contained HTML file.

    Args:
        show_passing: Include passing results in the output table.
    """

    def __init__(self, show_passing: bool = False) -> None:
        self.show_passing = show_passing

    def format(self, report: ValidationReport) -> str:
        """Format the report as a self-contained HTML document.

        Args:
            report: The :class:`~validator.reporting.models.ValidationReport`
                to format.

        Returns:
            A complete HTML document string suitable for saving as a
            ``.html`` file.
        """
        status     = "FAIL" if report.hasErrors() else "PASS"
        status_cls = "fail" if report.hasErrors() else "pass"
        generated  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        rows = []
        for r in report.results:
            if not self.show_passing and r.passed and not r.skipped:
                continue

            if r.skipped:
                row_cls, badge = "skipped", "SKIP"
            elif r.passed:
                row_cls, badge = "passed", "PASS"
            else:
                sev_map = {
                    Severity.ERROR:   ("error",   "ERROR"),
                    Severity.WARNING: ("warning", "WARN"),
                    Severity.INFO:    ("info",    "INFO"),
                }
                row_cls, badge = sev_map.get(r.severity, ("error", "ERR"))

            hint_html = (
                f'<br><small>Hint: {self._esc(r.fix_hint)}</small>'
                if r.fix_hint and not r.passed and not r.skipped
                else ""
            )
            rows.append(
                f'<tr class="{row_cls}">'
                f'<td><span class="badge {row_cls}">{badge}</span></td>'
                f'<td class="path">{self._esc(r.asset_path)}</td>'
                f'<td>{self._esc(r.rule_name)}</td>'
                f'<td>{self._esc(r.category)}</td>'
                f'<td>{self._esc(r.message)}{hint_html}</td>'
                f'</tr>'
            )

        rows_html = "\n".join(rows) or '<tr><td colspan="5">No results to display.</td></tr>'

        failed_cls = "fail" if report.failed else ""
        errors_cls = "fail" if report.errors else ""
        warnings_cls = "warn" if report.warnings else ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Validation Report [{status}]</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117; color: #c9d1d9; padding: 24px; }}
    h1   {{ color: #58a6ff; margin-bottom: 4px; font-size: 1.5rem; }}
    .meta {{ color: #8b949e; font-size: 0.85rem; margin-bottom: 24px; }}
    .summary {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 28px; }}
    .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px;
             padding: 12px 18px; min-width: 90px; }}
    .card .label {{ font-size: 11px; color: #8b949e; text-transform: uppercase;
                    letter-spacing: .05em; margin-bottom: 4px; }}
    .card .value {{ font-size: 26px; font-weight: 700; }}
    .pass  {{ color: #3fb950; }}
    .fail  {{ color: #f85149; }}
    .warn  {{ color: #d29922; }}
    .info  {{ color: #58a6ff; }}
    table  {{ width: 100%; border-collapse: collapse; background: #161b22;
             border: 1px solid #30363d; border-radius: 8px; overflow: hidden;
             font-size: 13px; }}
    th     {{ background: #21262d; padding: 10px 14px; text-align: left;
             font-size: 11px; color: #8b949e; text-transform: uppercase;
             letter-spacing: .05em; }}
    td     {{ padding: 8px 14px; border-bottom: 1px solid #21262d; vertical-align: top; }}
    td.path {{ font-family: monospace; font-size: 12px; max-width: 280px;
               word-break: break-all; color: #79c0ff; }}
    tr:last-child td {{ border-bottom: none; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px;
              font-size: 11px; font-weight: 700; white-space: nowrap; }}
    .badge.error   {{ background: #3d1a1a; color: #f85149; }}
    .badge.warning {{ background: #3d2e0a; color: #d29922; }}
    .badge.info    {{ background: #0d2a4a; color: #58a6ff; }}
    .badge.passed  {{ background: #0a2a1a; color: #3fb950; }}
    .badge.skipped {{ background: #1c1c1c; color: #8b949e; }}
    small  {{ color: #8b949e; }}
    footer {{ margin-top: 20px; font-size: 12px; color: #8b949e; }}
  </style>
</head>
<body>
  <h1>Asset Validation Report &mdash; <span class="{status_cls}">{status}</span></h1>
  <p class="meta">Generated: {generated} | Framework v{self._esc(report.tool_version)}</p>

  <div class="summary">
    <div class="card">
      <div class="label">Assets</div>
      <div class="value">{report.asset_count}</div>
    </div>
    <div class="card">
      <div class="label">Failures</div>
      <div class="value {failed_cls}">{report.failed}</div>
    </div>
    <div class="card">
      <div class="label">Errors</div>
      <div class="value {errors_cls}">{report.errors}</div>
    </div>
    <div class="card">
      <div class="label">Warnings</div>
      <div class="value {warnings_cls}">{report.warnings}</div>
    </div>
    <div class="card">
      <div class="label">Skipped</div>
      <div class="value">{report.skipped}</div>
    </div>
    <div class="card">
      <div class="label">Duration</div>
      <div class="value">{report.duration_ms:.0f}ms</div>
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th>Status</th>
        <th>Asset Path</th>
        <th>Rule</th>
        <th>Category</th>
        <th>Message</th>
      </tr>
    </thead>
    <tbody>
{rows_html}
    </tbody>
  </table>

  <footer>
    Asset Validation Framework &bull; {report.rule_count} rules &bull; {report.total} results total
  </footer>
</body>
</html>"""

    @staticmethod
    def _esc(text: str) -> str:
        """HTML-escape a string."""
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
