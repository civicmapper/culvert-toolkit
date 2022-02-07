'''tbx_culvert_capacity1.py

ArcToolbox script interface to the culvert capacity tool.
'''

from arcpy import GetParameterAsText
from drainit.workflows import NaaccDataIngest

x = NaaccDataIngest(
    naacc_csv=GetParameterAsText(0),
    output_folder=GetParameterAsText(1),
    output_workspace=GetParameterAsText(2),
    output_fc_name=GetParameterAsText(3),
    crs_wkid=GetParameterAsText(4), #4326
    naacc_x=GetParameterAsText(5), #"GIS_Longitude",
    naacc_y=GetParameterAsText(6)# "GIS_Latitude",
)

x.run()