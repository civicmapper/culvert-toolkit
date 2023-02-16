# Getting NOAA Rainfall Data

Location-specific rainfall measurements from NOAA are required inputs for the tool. Specifically: rainfall rasters from [NOAA's National Weather Service - Hydrometeorological Design Studies Center - Precipitation Frequency Data Server (PFDS)](https://hdsc.nws.noaa.gov/hdsc/pfds/) are used to calculate average rainfall over the upstream contributing area to a culvert, which is used to calculate peak-flow at the culvert.

## NOAA Rainfall Raster Downloader

The Culvert Analysis Toolkit includes a tool that automatically downloads the correct rasters for your area of interest: **NOAA Rainfall Raster Downloader**.

The NOAA Rainfall Raster Data Downloader does just that: it downloads rainfall rasters for your study area from NOAA's National Weather Service - Hydrometeorological Design Studies Center - Precipitation Frequency Data Server (PFDS).

By default, this tool acquires rainfall data for 24hr events for frequencies from 1 to 1000 years. All rasters are saved to a user-specified folder.

This tool creates a precipitation source configuration JSON file in the output folder. The JSON file is used as a required input to other tools—specifically those that calculate runoff/peak-flow.

Note that NOAA Atlas 14 precip values are in 1000ths of an inch; the capacity calculator an other tools convert the values to centimeters on-the-fly.

NOAA rainfall rasters cover a large geographic area, so you may only need to use this tool occassionally.