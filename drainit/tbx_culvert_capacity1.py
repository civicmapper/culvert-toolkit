'''tbx_culvert_capacity1.py

ArcToolbox script interface to the culvert capacity tool.
'''

from arcpy import GetParameterAsText
from drainit.workflows import CulvertCapacityCore

# instantiate the calculator class with the required inputs
# passed in from ArcToolbox
culvert_capacity_calc = CulvertCapacityCore(
    points_filepath=GetParameterAsText(0),
    raster_flowdir_filepath=GetParameterAsText(1),
    raster_slope_filepath=GetParameterAsText(2),
    raster_curvenumber_filepath=GetParameterAsText(3),
    precip_src_config_filepath=GetParameterAsText(5),
    output_points_filepath=GetParameterAsText(4)
)

# run the calculator
# * Internally this method calls the load_points method, which ETLs the feature class 
# at `points_filepath` to the internal data model and perform validation.
# * It then runs the delineations and derives the attributes required for peak flow.
# * With delineations complete, it calculates overflow
# * outputs are saved to the user-spec'd feature class
culvert_capacity_calc.run()