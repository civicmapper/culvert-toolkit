'''tbx_culvert_capacity1.py

ArcToolbox script interface to the culvert capacity tool.
'''

from arcpy import GetParameterAsText
from drainit.workflows import NaaccDataIngest

x = NaaccDataIngest(
    points_filepath=GetParameterAsText(0),
    raster_flowdir_filepath=GetParameterAsText(1),
    raster_slope_filepath=GetParameterAsText(2),
    raster_curvenumber_filepath=GetParameterAsText(3),
    precip_src_config_filepath=GetParameterAsText(5),
    output_points_filepath=GetParameterAsText(4)
)

x.run()