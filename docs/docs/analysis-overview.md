# Toolbox Overview

The Culvert Analysis Toolkit is currently implemented as ArcToolbox for use in ArcGIS Pro

![Culvert Analysis Toolkit in the ArcGIS Pro geoprocessing pane](assets/toolbox-02.png)

Each tool in the toolbox contains built-in help text to explain tool functionality, inputs, and outputs. Summaries of tool usage follow.

## NOAA Rainfall Raster Data Downloader

The *NOAA Rainfall Raster Data Downloader* does just that: it downloads rainfall rasters for your study area from [NOAA's National Weather Service - Hydrometeorological Design Studies Center - Precipitation Frequency Data Server (PFDS)](https://hdsc.nws.noaa.gov/hdsc/pfds/). 

By default, this tool acquires rainfall data for 24hr events for frequencies from 1 to 1000 years. All rasters are saved to a user-specified folder. 

This tool creates a precipitation source configuration `JSON` file in the output folder. The `JSON` file is used as a required input to other tools&mdash;specifically those that calculate runoff/peak-flow.

Note that NOAA Atlas 14 precip values are in *1000ths of an inch*; the capacity calculator an other tools convert the values to *centimeters* on-the-fly.

NOAA rainfall rasters cover a large geographic area, so you may only need to use this tool occassionally.

## NAACC Table Ingest

The *NAACC Table Ingest* tool will read in, validate, and extend a NAACC-compliant source table, saving the output as geodata (e.g., a file geodatabase feature class) for use in other culvert analysis tools, like the NAACC Culvert Capacity Calculator

## NAACC Data Snapping

The *NAACC Data Snapping* tool can be used to reposition features in a NAACC-compliant feature class to locations in another feature class; e.g., move the NAACC culvert records to point features that have been snapped to streams on a hydrologically corrected DEM.

## Curve Number Generator

(planned; previously implemented in the stand-alone [Peak Flow Calculator toolbox](https://github.com/civicmapper/peak-flow-calculator/))

## NAACC Culvert Capacity

The *NAACC Culvert Capacity* tool measure the capacity of culverts to handle storm events using the TR-55 model. It does this by: 

* calculating the capacity of the culvert(s) at a crossing
* calculating peak flow at the culvert over a hydrologically corrected digital elevation model for 24 hour storm events with frequencies of 1 to 1000 years
* comparing capacity of individual culverts and all culverts at a crossing to each peak-flow, and flagging the event at which the culverts and crossings exceed capacity.

Culvert location data must be NAACC schema-compliant. 

See the [Worfklow Guide](capacitycalc-run-one.md) for more information on using this tool.

## Peak-Flow Calculator

(planned; currently implemented with the NAACC Culvert Capacity tool)

Calculate peak-flow for one or more points over a hydrologically corrected DEM. Points do not need comply with any predefined data model (such as NAACC).