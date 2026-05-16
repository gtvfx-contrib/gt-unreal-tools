"""Unified CLI entry-point for the asset validation framework.

Supports environment variable overrides for every flag (useful in CI)::

    VALIDATOR_FORMAT=json
    VALIDATOR_OUTPUT_DIR=/artifacts
    VALIDATOR_MAX_WORKERS=4

Exit codes:
    0 — all checks passed (or only warnings/infos)
    1 — at least one ERROR-severity failure
    2 — configuration error or invalid arguments

"""
from __future__ import annotations

import argparse
import os
import sys

from .config import Config
from .rules.base import Severity
from .runner import ValidationRunner
from .reporting.formatters import ConsoleFormatter, JSONFormatter, HTMLFormatter
from .reporting.models import ValidationReport


_FORMATTERS = {
    "console": ConsoleFormatter,
    "json":    JSONFormatter,
    "html":    HTMLFormatter,
}


def buildParser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser.

    Returns:
        A configured :class:`argparse.ArgumentParser` instance.
    """
    parser = argparse.ArgumentParser(
        prog="python run_validator.py",
        description="Asset Validation Framework — Production-hardened pipeline tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
environment variable overrides (all optional):
  VALIDATOR_CONFIG_PATH   — path to JSON config file
  VALIDATOR_FORMAT        — output format: console | json | html
  VALIDATOR_OUTPUT_DIR    — directory to write report file
  VALIDATOR_LOG_LEVEL     — logging verbosity: DEBUG | INFO | WARNING | ERROR
  VALIDATOR_MAX_WORKERS   — number of parallel worker threads (1 = serial)

exit codes:
  0   all checks passed (or only warnings/infos)
  1   at least one ERROR-severity failure
  2   configuration or argument error
  
""",
    )
    parser.add_argument(
        "--directory", "-d",
        metavar="PATH",
        required=False,
        help="Root directory to validate (recursively).",
    )
    parser.add_argument(
        "--config", "-c",
        default=None,
        metavar="FILE",
        help="Path to a JSON config file.",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["console", "json", "html"],
        default=None,
        help="Output format (default: console, or VALIDATOR_FORMAT env var).",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=None,
        metavar="DIR",
        help="Directory to write report file (console writes to stdout).",
    )
    parser.add_argument(
        "--category",
        default=None,
        metavar="NAME",
        help="Only run rules in this category.",
    )
    parser.add_argument(
        "--severity",
        default=None,
        choices=["ERROR", "WARNING", "INFO"],
        help="Only run rules at this exact severity.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        metavar="N",
        help="Number of parallel worker threads (1 = serial, safe in Unreal).",
    )
    parser.add_argument(
        "--show-passing",
        action="store_true",
        default=False,
        help="Include passing results in report output.",
    )
    parser.add_argument(
        "--list-rules",
        action="store_true",
        dest="listRules",
        help="List all registered rules and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the validation CLI and return an exit code.

    Args:
        argv: Argument list to parse.  When ``None``, ``sys.argv[1:]`` is
            used.

    Returns:
        ``0`` if all checks passed, ``1`` if any ERROR-severity rule failed,
        ``2`` if there was a configuration or argument error.
    """
    import logging

    parser = buildParser()
    args = parser.parse_args(argv)

    config_path = args.config or os.environ.get("VALIDATOR_CONFIG_PATH")
    try:
        config = Config(config_path=config_path)
    except ValueError as exc:
        print(f"[CLI] ERROR: {exc}", file=sys.stderr)
        return 2

    log_level = (
        os.environ.get("VALIDATOR_LOG_LEVEL")
        or config.get("log_level", "WARNING")
    ).upper()
    logging.basicConfig(level=getattr(logging, log_level, logging.WARNING))

    if args.listRules:
        from .registry import registry
        registry.discover()
        rules = registry.listRules()
        if not rules:
            print("No rules registered.")
        else:
            print(f"{'NAME':<35} {'CATEGORY':<20} {'SEVERITY'}")
            print("-" * 65)
            for name, cls in sorted(rules.items()):
                print(f"{name:<35} {cls.category:<20} {cls.severity.value}")
        return 0

    if not args.directory:
        parser.error("--directory is required unless --list-rules is specified.")
        return 2

    fmt = (
        args.format
        or os.environ.get("VALIDATOR_FORMAT")
        or config.get("report_format", "console")
    )
    output_dir = args.output_dir or os.environ.get("VALIDATOR_OUTPUT_DIR")
    severity_filter = Severity(args.severity) if args.severity else None
    max_workers = args.max_workers

    runner = ValidationRunner(
        config,
        category=args.category,
        severity=severity_filter,
        max_workers=max_workers,
    )

    report: ValidationReport = runner.runAndReport(args.directory)

    formatter_cls = _FORMATTERS.get(fmt, ConsoleFormatter)
    formatter = formatter_cls(show_passing=args.show_passing or config.get("show_passing", False))
    output_text = formatter.format(report)

    if output_dir and fmt != "console":
        os.makedirs(output_dir, exist_ok=True)
        ext = {"json": ".json", "html": ".html"}.get(fmt, ".txt")
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(output_dir, f"validation_report_{ts}{ext}")
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(output_text)
        print(f"[CLI] Report written to: {out_path}")
    else:
        print(output_text)

    if report.hasErrors():
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())