"""Asset Validation Framework for Unreal Engine 5.5.x.

Public API::

    from validator import ValidationRunner, Config, ValidationReport

    runner = ValidationRunner(Config())
    report = runner.run_and_report("/path/to/assets")
    print(report.summary_line())
    
"""
__version__ = "0.0.13"
__author__ = "Technical Artist Course — ELVTR"
__all__ = ["ValidationRunner", "Config", "ValidationReport"]

from .runner import ValidationRunner
from .config import Config
from .reporting.models import ValidationReport
