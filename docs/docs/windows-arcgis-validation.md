# Windows / ArcGIS Pro release validation

## Candidate runtime

The package requires Python 3.11 or newer. Candidate ArcGIS targets must be
tested individually because ArcGIS Pro controls the Python, ArcPy, NumPy, and
other compiled package versions. Record each validated Pro/Python combination
in the release notes rather than claiming compatibility based only on Python's
version. Linux supports the pure-Python calculators, models, NAACC ETL, and
mocked NOAA tests; raster/geodatabase workflows require ArcPy.

`src/drainit/esri/toolboxes/CulvertToolbox.pyt` is the canonical packaged editable toolbox. The top-level `src/CulvertToolbox.pyt` is retained as a compatibility copy for existing development workflows. Do not generate or hand-edit `.pyt.xml` metadata as part of Linux packaging.

## Clean validation

Run this checklist on Windows with a licensed ArcGIS Pro installation and representative non-production fixtures.

1. Clone `arcgispro-py3` to a new environment; do not modify the base environment:
   ```powershell
   .\install-local-build.ps1 -EnvironmentName culvert-toolkit-validation -Wheel .\dist\culvert_toolkit-0.3.0-py3-none-any.whl
   ```
2. In ArcGIS Pro, select `culvert-toolkit-validation`, restart Pro, and run:
   ```powershell
   & "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\conda.exe" run -n culvert-toolkit-validation python .\scripts\validate_arcgispro.py
   ```
   Alternatively run that Python script from the ArcGIS Pro Python Command Prompt.
3. Add `CulvertToolbox.pyt` from the installed package (`...\Lib\site-packages\drainit\esri\toolboxes`) and confirm discovery of all four tools: NAACC ETL, NAACC snapping, NOAA rainfall ETL, and culvert capacity.
4. Check out the Spatial Analyst extension and fail the validation if it is unavailable.
5. Run **NAACC ETL** against a clean CSV. Verify valid/invalid row counts, IDs, coordinates, capacity fields, and output feature class.
6. Run **NAACC snapping**. Verify moved flags, point count, spatial reference, and that source data is unchanged.
7. Run **NOAA rainfall ETL** into an empty folder. Verify every requested frequency exists, each raster opens, and the JSON config references only existing rasters. A partial request must fail without a success config.
8. Run **culvert capacity** once with derived flow length and once with a supplied flow-length raster. Verify the flow-direction, slope, curve-number, and rainfall rasters align and have valid projected units.
9. Inspect outputs in a new file geodatabase: feature/raster counts, spatial references, nonempty delineations, NoData edges, unique IDs, and grouped versus ungrouped crossings.
10. Verify derived outputs for representative records: time of concentration, culvert/crossing capacity, peak flow and overflow for every rainfall frequency, maximum return period, validation flags, and saved workflow JSON.
11. Close/reopen the project, rerun each tool, and record Pro version, Python version, package version, Spatial Analyst license, fixture hashes, results, warnings, and failures.
12. Confirm that a missing `arcpy.env.scratchFolder` falls back to the system temporary directory and still produces the workflow configuration file.
13. Test a current NAACC export containing literal `NULL`, 0/1 flag fields, and duplicate/renamed inlet-type columns. Record the exact source headers; Linux normalizes `NULL`, but duplicate-column semantics require a real current export before adding an alias rule.

## Known toolbox-boundary issue

GitHub issue #17 remains open: the current Python toolbox converts feature
layer parameters to `dataSource`, which can discard an interactive map
selection. Until a Windows-tested boundary change is available, explicitly
validate this behavior by selecting a strict subset of input culverts in the
map, running each point-based tool, and comparing input/output IDs and row
counts. Do not claim selection preservation in release notes unless that test
passes. The Linux stabilization does not change this boundary because ArcPy
layer-object behavior cannot be safely proven here.

A release is not ArcGIS-validated until every step passes on at least one clean Windows machine. Live NOAA availability is an integration dependency; the automated Linux suite uses mocks and fixtures only.
