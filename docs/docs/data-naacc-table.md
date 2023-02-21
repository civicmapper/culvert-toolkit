# Working with NAACC Culvert Data

(Notes NAACC culvert data accuracy (spatial and temporal))

## Initial Download and Clean-Up

* Download the XLSX file from NAACC
* Delete headers (first eight rows)
* Save as CSV

### Optionally: Pre-Process the NAACC table

While the [*NAACC Table Ingest* (described below)](#run-the-naacc-table-ingest-tool) will flag records that aren't valid for capacity calculations, you may want to pair back to download to records of interest.

You may want to:

* remove certain types of culvert, e.g., bridges, fords, or ones that don't have any capacity measurements.
* import this table into GIS, and move features to streams or flow lines on a digital elevation model

Regardless, as long as the NAACC schema is preserved, subsequent tools will be able to use it.

## Run the *NAACC Table Ingest* tool

The *NAACC Table Ingest* tool will read in, validate, and extend a NAACC-compliant source table, saving the output as geodata (e.g., an Esri file geodatabase feature class).

Use the prepared CSV above as an input. If you've imported that CSV to a file geodatabase feature class already, that feature class will also work.

### What is changed in the data by this tool:

* new fields related to data validation: 
  * `include` 
  * `validation_errors`
* new fields for storing transformed copies of capacity model-specific attributes (e.g. values with unit conversion applied). 
  * *NAACC field: new field*
  * `Material`: `culv_mat`
  * `Inlet_Type`: `in_type`
  * `Inlet_Structure_Type`: `in_shape`
  * `Inlet_Width`: `in_a`
  * `Inlet_Height`: `in_b`
  * `Road_Fill_Height`: `hw`
  * `Slope_Percent`: `slope`
  * `Crossing_Structure_Length`: `length`
  * `Outlet_Structure_Type`: `out_shape`
  * `Outlet_Width`: `out_a`
  * `Outlet_Height`: `out_b`
  * `Crossing_Type`: `crossing_type`
  * `Crossing_Comment`: `comments`
  * new fields for storing calculator results:
  * 

## Optionally: Run the *NAACC Data Snapping* tool

Depending on your needs, you may find that the location precision of the supplied NAACC data was not adequate compared to the accuracy of your [hydrologically corrected DEM](data-dem.md). In that case, you may have moved culverts manually or snapped points to streams.

If you need to update your NAACC table with better location data from an external table--a *Adjusted Geometry File*--use the *NAACC Data Snapping tool* to update the input NAACC-compliant source table with locations from another table.

(This tool basically runs a reverse 1-to-many join, replacing geometry in one or more feature class records with a single geometry from feature in a reference table using a column-based match).

### What is changed in the data by this tool:

* updated geometry
* new field: `resnapped`: boolean field indicating if the record has been re-snapped based on the supplied reference geometry.