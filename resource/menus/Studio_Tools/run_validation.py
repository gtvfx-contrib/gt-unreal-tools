# label: Run Validation
# tooltip: Runs the validation tool
# order: 1.0
# section: Validation
"""
Unreal Engine entrypoint for the Session 13 demo.

Run this script from within Unreal Engine's Python editor (Edit ->
Execute Python Script) to validate the open project's content.  It uses
the fully hardened S13 validator package from step 04.

Usage (inside UE Python console):
    import unreal
    exec(open("/path/to/unreal_entrypoint.py").read())
"""
import unreal

from gt.unreal.validator.config import Config
from gt.unreal.validator.runner import ValidationRunner
from gt.unreal.validator.reporting.formatters import ConsoleFormatter

# Inside Unreal, use serial mode (max_workers=1) to avoid C++ bridge races.
config  = Config()
runner  = ValidationRunner(config, max_workers=1)

# Replace with your project's actual content path.
CONTENT_PATH = "/Game"

report = runner.run_and_report(CONTENT_PATH)
unreal.log(ConsoleFormatter(show_passing=False).format(report))

if report.has_errors():
    unreal.log("[Validator] Validation FAILED — see failures above.")
else:
    unreal.log("[Validator] Validation PASSED.")
