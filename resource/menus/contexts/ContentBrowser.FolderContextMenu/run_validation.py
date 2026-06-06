# label: Run Validation
# tooltip: Runs the validation tool
# order: 1.0
# section: Validation

from gt.validator.entry_points import run_validation
print("FolderContextMenu > Run Validation")
run_validation.runOnSelectedFolders()

