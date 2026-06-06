# label: Validate Static Mesh
# tooltip: Runs the validation tool for static meshes
# section: GetAssetActions

from gt.validator.entry_points.unreal import run_validation
print("StaticMesh > validate_mesh")
run_validation.runOnSelectedAssets()
