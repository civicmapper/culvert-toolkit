# -*- coding: utf-8 -*-
r""""""
__all__ = ['CulvertCapacityPytTool', 'SampleTool']
__alias__ = 'CulvertToolbox'
from arcpy.geoprocessing._base import gptooldoc, gp, gp_fixargs
from arcpy.arcobjects.arcobjectconversion import convertArcObjectToPythonObject

# Tools
@gptooldoc('CulvertCapacityPytTool_CulvertToolbox', None)
def CulvertCapacityPytTool(points_filepath=None, raster_flowdir_filepath=None, raster_flowlen_filepath=None, raster_slope_filepath=None, raster_curvenumber_filepath=None, precip_src_config_filepath=None, output_points_filepath=None):
    """CulvertCapacityPytTool_CulvertToolbox(points_filepath, raster_flowdir_filepath, raster_flowlen_filepath, raster_slope_filepath, raster_curvenumber_filepath, precip_src_config_filepath, output_points_filepath)

     INPUTS:
      points_filepath (Feature Layer):
          Culvert Points
      raster_flowdir_filepath (Raster Layer):
          Flow Direction
      raster_flowlen_filepath (Raster Layer):
          Flow Length
      raster_slope_filepath (Raster Layer):
          Slope
      raster_curvenumber_filepath (Raster Layer):
          Curve Number
      precip_src_config_filepath (File):
          Precipitation Configuration File

     OUTPUTS:
      output_points_filepath (Feature Class):
          Result Points"""
    from arcpy.geoprocessing._base import gp, gp_fixargs
    from arcpy.arcobjects.arcobjectconversion import convertArcObjectToPythonObject
    try:
        retval = convertArcObjectToPythonObject(gp.CulvertCapacityPytTool_CulvertToolbox(*gp_fixargs((points_filepath, raster_flowdir_filepath, raster_flowlen_filepath, raster_slope_filepath, raster_curvenumber_filepath, precip_src_config_filepath, output_points_filepath), True)))
        return retval
    except Exception as e:
        raise e

@gptooldoc('SampleTool_CulvertToolbox', None)
def SampleTool():
    """SampleTool_CulvertToolbox()"""
    from arcpy.geoprocessing._base import gp, gp_fixargs
    from arcpy.arcobjects.arcobjectconversion import convertArcObjectToPythonObject
    try:
        retval = convertArcObjectToPythonObject(gp.SampleTool_CulvertToolbox(*gp_fixargs((), True)))
        return retval
    except Exception as e:
        raise e


# End of generated toolbox code
del gptooldoc, gp, gp_fixargs, convertArcObjectToPythonObject