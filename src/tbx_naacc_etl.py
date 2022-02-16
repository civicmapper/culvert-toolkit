'''tbx_naacc_etl.py

ArcToolbox script interface to the NAACC table ETL script.
'''
from pathlib import Path
from arcpy import GetParameterAsText
from drainit.workflows import NaaccDataIngest

output_folder = GetParameterAsText(1)
fgdb_name = GetParameterAsText(2)
# In the toolbox, the user inputs the gdb name, and we create it in the folder they
# picked if it doesn't exist.
output_workspace = str(Path(output_folder) / f"{fgdb_name}.gdb")

x = NaaccDataIngest(
    naacc_src_table=GetParameterAsText(0),
    output_folder=output_folder,
    output_workspace=output_workspace,
    output_fc_name=GetParameterAsText(3)
    # crs_wkid=GetParameterAsText(4), #4326
    # naacc_x=GetParameterAsText(5), #"GIS_Longitude",
    # naacc_y=GetParameterAsText(6)# "GIS_Latitude",
)