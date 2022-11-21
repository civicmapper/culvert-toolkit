# -*- coding: utf-8 -*-
r""""""
__all__ = ['CulvertCapacityPytTool', 'NaaccEtlPytTool',
           'NoaaRainfallEtlPytTool']
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

@gptooldoc('NaaccEtlPytTool_CulvertToolbox', None)
def NaaccEtlPytTool(naacc_src_table=None, output_folder=None, output_fc=None):
    """NaaccEtlPytTool_CulvertToolbox(naacc_src_table, output_folder, output_fc)

     INPUTS:
      naacc_src_table (File):
          NAACC CSV

     OUTPUTS:
      output_folder (Folder):
          Output Folder
      output_fc (Feature Class):
          Output Feature Class"""
    from arcpy.geoprocessing._base import gp, gp_fixargs
    from arcpy.arcobjects.arcobjectconversion import convertArcObjectToPythonObject
    try:
        retval = convertArcObjectToPythonObject(gp.NaaccEtlPytTool_CulvertToolbox(*gp_fixargs((naacc_src_table, output_folder, output_fc), True)))
        return retval
    except Exception as e:
        raise e

@gptooldoc('NoaaRainfallEtlPytTool_CulvertToolbox', None)
def NoaaRainfallEtlPytTool(aoi_geo=None, target_raster=None, out_folder=None, out_file_name=None):
    """NoaaRainfallEtlPytTool_CulvertToolbox(aoi_geo, {target_raster}, out_folder, out_file_name)

     INPUTS:
      aoi_geo (Feature Layer):
          Area of Interest
      target_raster {Raster Layer}:
          Reference Raster
      out_folder (Folder):
          Output Folder

     OUTPUTS:
      out_file_name (String):
          Output Rainfall Configuration File Name"""
    from arcpy.geoprocessing._base import gp, gp_fixargs
    from arcpy.arcobjects.arcobjectconversion import convertArcObjectToPythonObject
    try:
        retval = convertArcObjectToPythonObject(gp.NoaaRainfallEtlPytTool_CulvertToolbox(*gp_fixargs((aoi_geo, target_raster, out_folder, out_file_name), True)))
        return retval
    except Exception as e:
        raise e


# End of generated toolbox code
del gptooldoc, gp, gp_fixargs, convertArcObjectToPythonObject