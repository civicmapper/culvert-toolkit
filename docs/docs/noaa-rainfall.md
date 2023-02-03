# Getting NOAA Rainfall Data

Location-specific rainfall measurements from NOAA are required inputs for the tool. Specifically: rainfall rasters from [NOAA's National Weather Service - Hydrometeorological Design Studies Center - Precipitation Frequency Data Server (PFDS)](https://hdsc.nws.noaa.gov/hdsc/pfds/) are used to calculate average rainfall over the upstream contributing area to a culvert, which is used to calculate peak-flow at the culvert.

The Culvert Analysis Toolkit includes a tool that automatically downloads the correct rasters for your area of interest: [analysis-overview/#noaa-rainfall-raster-data-downloader] and generates a file that is used as an input to other tools.