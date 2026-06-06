# label: Run Validation
# tooltip: Runs the validation tool
# order: 1.0
# section: Validation

from gt.validator.entry_points.unreal import run_validation
print("AssetContextMenu > Run Validation")
run_validation.runOnSelectedAssets()
