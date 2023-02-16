# Overview

## Getting Data

![](assets/workflow.png)

*Preparing data for use in the tools*

* Get DEM, derive rasters
* Get Curve Number data
* Get Rainfall data
* Get NAACC data

## Considerations for Preparing Data

You'll need to determine the the trade-off between speed and accuracy based on your use case:

* Ideal: full hydrologic correction of the DEM and re-locating of culverts with LIDAR and imagery
* Workable: fill sinks in DEM; burn hydro lines into the DEMs; snap culverts to available hydro steam lines; 

The best approach for determining DEM hydrologic-accuracy and NAACC location-correctedness depends on your use case.