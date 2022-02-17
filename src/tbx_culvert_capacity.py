'''tbx_culvert_capacity1.py

ArcToolbox script interface to the culvert capacity tool.
'''
import sys
import pathlib
# sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
# print(pathlib.Path(__file__).parent.parent)

from arcpy import GetParameterAsText
from drainit.workflows import CulvertCapacityCore
# from workflows import CulvertCapacityCore

# instantiate the calculator class with the required inputs
# passed in from ArcToolbox

# set the output sheds filepath based on the output points filepath,
# (which will be limited to a fgdb feature class)
output_points_filepath = GetParameterAsText(6)
output_sheds_filepath = output_points_filepath + "_sheds"

culvert_capacity_calc = CulvertCapacityCore(
    points_filepath=GetParameterAsText(0),
    raster_flowdir_filepath=GetParameterAsText(1),
    raster_flowlen_filepath=GetParameterAsText(2),
    raster_slope_filepath=GetParameterAsText(3),
    raster_curvenumber_filepath=GetParameterAsText(4),
    precip_src_config_filepath=GetParameterAsText(5),
    output_points_filepath=output_points_filepath,
    output_sheds_filepath=output_sheds_filepath
)

# run the calculator
# * Internally this method calls the load_points method, which ETLs the feature class 
# at `points_filepath` to the internal data model and perform validation.
# * It then runs the delineations and derives the attributes required for peak flow.
# * With delineations complete, it calculates overflow
# * outputs are saved to the user-spec'd feature class
culvert_capacity_calc.run()