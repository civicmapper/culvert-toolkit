'''tbx_noaa_etl.py

ArcToolbox script interface to the NOAA rainfall raster ETL script.
'''
from drainit.workflows import RainfallDataGetter
from arcpy import GetParameterAsText

rdg = RainfallDataGetter(
    aoi_geo=GetParameterAsText(0),
    out_folder=GetParameterAsText(1),
    out_file_name=GetParameterAsText(2),
    target_raster=GetParameterAsText(3)
)