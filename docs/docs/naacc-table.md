# Working with NAACC Culvert Data

## Initial Download and Clean-Up

* Download the XLSX file from NAACC
* Delete headers (first eight rows)
* Save as CSV

### Optionally: 

While the *NAACC Table Ingest* will flag records that aren't valid for capacity calculations, you may want to pair back to download to records of interest.

You may want to remove certain types of culvert, e.g., bridges, fords, or ones that don't have any capacity measurements. Or, you may need to import this table into GIS, and move features to streams or flow lines on a digital elevation model. 

Regardless, as long as the NAACC schema is preserved, subsequent tools will be able to use it.

## Run the *NAACC Table Ingest* tool

The *NAACC Table Ingest* tool will read in, validate, and extend a NAACC-compliant source table, saving the output as geodata (e.g., a file geodatabase feature class.

Use the prepared CSV above as an input. If you've imported that CSV to a file geodatabase feature class already, that feature class will also work.

An optional input for this tool allows you to supply a table representing corrected locations for crossings. If provided, the tool will update the input NAACC-compliant source table with locations from this optional input.