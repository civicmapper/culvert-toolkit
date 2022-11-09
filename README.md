# Drain-It

Inlet + Culvert Peak-Flow and Capacity Calculator using a TR-55 Model and
parameters derived from geospatial data.

* NAACC ETL: new from 2.1. Transform to a standardized generic point format.
* Get rainfall rasters from NOAA
* Delineation: Series currently this is part of peak flow, but could be separated out
* Peak flow: Calculate from a TR-55 model with rainfall rasters from NOAA.
* Capacity: new from 2.1. Depends on the kinds of fields collected in the NAACC format. If those fields are unavailable, we skip this part just like any other step.
* Return Period Eval: new in 2.1. Relies on peak-flow and capacity results together
* Workflow-oriented model runs: save and load a config file to reload and re-run models

## Installation

(to be completed)

## Using Drain-It in **Esri ArcGIS Pro**

(to be completed)