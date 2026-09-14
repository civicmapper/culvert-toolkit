"""Read-only ArcGIS Pro smoke validation; run inside a cloned Pro environment."""

from importlib.metadata import version
from pathlib import Path
import sys


def main():
    import arcpy
    import drainit
    import drainit.calculators
    import drainit.models
    import drainit.services.naacc
    import drainit.services.noaa

    package_root = Path(drainit.__file__).resolve().parent
    toolbox = package_root / "esri" / "toolboxes" / "CulvertToolbox.pyt"
    if not toolbox.is_file():
        raise FileNotFoundError(f"Packaged toolbox not found: {toolbox}")

    product = arcpy.GetInstallInfo()
    print(f"ArcGIS Pro: {product.get('Version', 'unknown')}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"culvert-toolkit: {version('culvert-toolkit')}")
    print(f"Spatial Analyst: {arcpy.CheckExtension('Spatial')}")
    if arcpy.CheckExtension("Spatial") != "Available":
        raise RuntimeError("Spatial Analyst extension is not available")

    arcpy.ImportToolbox(str(toolbox), "culvert_toolkit_validation")
    tools = sorted(arcpy.ListTools("*_culvert_toolkit_validation"))
    if len(tools) < 4:
        raise RuntimeError(f"Expected at least four toolbox tools; discovered {tools}")
    print(f"Toolbox: {toolbox}")
    print("Discovered tools:")
    for tool in tools:
        print(f"  - {tool}")
    print("Smoke validation passed. Complete the data-driven checklist in the docs.")


if __name__ == "__main__":
    main()
