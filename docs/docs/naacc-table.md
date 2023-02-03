# Working with NAACC Culvert Data

(Notes NAACC culvert data accuracy (spatial and temporal))

## Initial Download and Clean-Up

* Download the XLSX file from NAACC
* Delete headers (first eight rows)
* Save as CSV

### Optionally: 

While the [*NAACC Table Ingest* (described below)](#run-the-naacc-table-ingest-tool) will flag records that aren't valid for capacity calculations, you may want to pair back to download to records of interest.

You may want to remove certain types of culvert, e.g., bridges, fords, or ones that don't have any capacity measurements. Or, you may need to import this table into GIS, and move features to streams or flow lines on a digital elevation model. 

Regardless, as long as the NAACC schema is preserved, subsequent tools will be able to use it.

## Run the *NAACC Table Ingest* tool

The *NAACC Table Ingest* tool will read in, validate, and extend a NAACC-compliant source table, saving the output as geodata (e.g., an Esri file geodatabase feature class).

Use the prepared CSV above as an input. If you've imported that CSV to a file geodatabase feature class already, that feature class will also work.

## Optionally: Run the *NAACC Data Snapping* tool

Depending on your needs, you may find that the location precision of the supplied NAACC data was not adequate compared to the accuracy of your [hydrologically corrected DEM](dem-rasters.md). In that case, you may have moved culverts manually or snapped points to streams.

If you need to update your NAACC table with better location data from an external table, use the *NAACC Data Snapping tool* to update the input NAACC-compliant source table with locations from another table.

(This tool basically runs a reverse 1-to-many join, replacing geometry in one or more feature class records with a single geometry from feature in a reference table using a column-based match)