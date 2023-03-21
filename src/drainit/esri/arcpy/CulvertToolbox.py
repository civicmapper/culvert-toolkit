# -*- coding: utf-8 -*-
r"""A toolbox for analyzing peak flows and capacities of culverts based
on the NAACC culvert model and TR-55 runoff model implemented by the
Cornell Soil &amp; Water Lab."""
__all__ = ['CulvertCapacityPytTool', 'NaaccEtlPytTool', 'NaaccSnappingPytTool',
           'NoaaRainfallEtlPytTool']
__alias__ = 'CulvertToolkit'
from arcpy.geoprocessing._base import gptooldoc, gp, gp_fixargs
from arcpy.arcobjects.arcobjectconversion import convertArcObjectToPythonObject

# Tools
@gptooldoc('CulvertCapacityPytTool_CulvertToolkit', None)
def CulvertCapacityPytTool(points_filepath=None, raster_flowdir_filepath=None, raster_flowlen_filepath=None, raster_slope_filepath=None, raster_curvenumber_filepath=None, precip_src_config_filepath=None, output_points_filepath=None):
    """CulvertCapacityPytTool_CulvertToolkit(points_filepath, raster_flowdir_filepath, {raster_flowlen_filepath}, raster_slope_filepath, raster_curvenumber_filepath, precip_src_config_filepath, output_points_filepath)

        Measure the capacity of culverts by calculating peak flow over a
        hydrologically corrected digital elevation model. Culvert location
        data must be NAACC schema-compliant and processed through the  NAACC
        Table Ingest  tool.

     INPUTS:
      points_filepath (Feature Layer):
          Points feature class compliant with the NAACC schema. Use the
          NAACC Table Ingest tool to generate this data from NAACC downloads.
      raster_flowdir_filepath (Raster Layer):
          Flow direction raster, derived from hydrologically corrected DEM
      raster_flowlen_filepath {Raster Layer}:
          Flow length raster, derived from hydrologically corrected DEM
      raster_slope_filepath (Raster Layer):
          Slope raster, derived from hydrologically corrected DEM. Must be
          percent slope .
      raster_curvenumber_filepath (Raster Layer):
          Curve Number raster, representing curve numbers calculated
          according the the  TR-55 method
      precip_src_config_filepath (File):
          A Culvert-Toolkit precipitation data source configuration JSON
          file. Create this file by running the NOAA Rainfall Raster Data
          Download tool.

     OUTPUTS:
      output_points_filepath (Feature Class):
          Output point feature class, which will include all submitted
          culverts (even those that aren't valid), with calculated capacity and
          peak-flow/runoff estimates as a field, per record. An accompanying
          polygon feature class containing the delineated watersheds of the
          culverts will be saved along with the point feature. It's name will be
          based on the name of the point feature class, suffixed with  "_sheds"."""
    from arcpy.geoprocessing._base import gp, gp_fixargs
    from arcpy.arcobjects.arcobjectconversion import convertArcObjectToPythonObject
    try:
        retval = convertArcObjectToPythonObject(gp.CulvertCapacityPytTool_CulvertToolkit(*gp_fixargs((points_filepath, raster_flowdir_filepath, raster_flowlen_filepath, raster_slope_filepath, raster_curvenumber_filepath, precip_src_config_filepath, output_points_filepath), True)))
        return retval
    except Exception as e:
        raise e

@gptooldoc('NaaccEtlPytTool_CulvertToolkit', None)
def NaaccEtlPytTool(naacc_src_table=None, output_fc=None):
    """NaaccEtlPytTool_CulvertToolkit(naacc_src_table, output_fc)

        Read in, validate, and extend a NAACC-compliant source table,
        saving the output as geodata (e.g., a file geodatabase feature class)
        for use in other culvert analysis tools.

     INPUTS:
      naacc_src_table (File / Feature Class):
          Path to CSV, SHP, or FGDB feature class containing data with a
          NAACC-compliant schema.

     OUTPUTS:
      output_fc (Feature Class):
          Path in a geodatabase to save the new, ready-to-use feature class"""
    from arcpy.geoprocessing._base import gp, gp_fixargs
    from arcpy.arcobjects.arcobjectconversion import convertArcObjectToPythonObject
    try:
        retval = convertArcObjectToPythonObject(gp.NaaccEtlPytTool_CulvertToolkit(*gp_fixargs((naacc_src_table, output_fc), True)))
        return retval
    except Exception as e:
        raise e

@gptooldoc('NaaccSnappingPytTool_CulvertToolkit', None)
def NaaccSnappingPytTool(naacc_points_table=None, naacc_points_table_join_field=None, geometry_source_table=None, geometry_source_table_join_field=None, output_fc=None):
    """NaaccSnappingPytTool_CulvertToolkit(naacc_points_table, naacc_points_table_join_field, geometry_source_table, geometry_source_table_join_field, output_fc)

        The  NAACC Data Snapping  tool can be used to reposition features
        in a NAACC-compliant feature class to locations in another feature
        class; e.g., move the NAACC culvert records to point features that
        have been snapped to streams on a hydrologically corrected DEM.

     INPUTS:
      naacc_points_table (Feature Class):
          Feature class processed through  NAACC Table Ingest  tool.
      naacc_points_table_join_field (Field):
          Field in naacc_points_table used to match geometries to
          geometry_source_table records. Defaults to "Survey_Id".
      geometry_source_table (Feature Class):
          Feature class that includes modified geometries to replace those in
          naacc_src_table
      geometry_source_table_join_field (Field):
          field in geometry_source_table used to match geometries to
          naacc_points_table records. Defaults to "Survey_Id".

     OUTPUTS:
      output_fc (Feature Class):
          New feature class with updated geometries."""
    from arcpy.geoprocessing._base import gp, gp_fixargs
    from arcpy.arcobjects.arcobjectconversion import convertArcObjectToPythonObject
    try:
        retval = convertArcObjectToPythonObject(gp.NaaccSnappingPytTool_CulvertToolkit(*gp_fixargs((naacc_points_table, naacc_points_table_join_field, geometry_source_table, geometry_source_table_join_field, output_fc), True)))
        return retval
    except Exception as e:
        raise e

@gptooldoc('NoaaRainfallEtlPytTool_CulvertToolkit', None)
def NoaaRainfallEtlPytTool(aoi_geo=None, target_raster=None, out_folder=None, out_file_name=None):
    """NoaaRainfallEtlPytTool_CulvertToolkit(aoi_geo, {target_raster}, out_folder, {out_file_name})

        Download rainfall rasters for your study area from NOAA. By
        default, this tool acquires rainfall data for 24hr events for
        frequencies from 1 to 1000 years. All rasters are saved to the user-
        specified folder. This tool creates a  precipitation source
        configuration JSON file  in the output folder. The JSON file used as a
        required input to other tools. Note that NOAA Atlas 14 precip values
        are in  millimeters ; the capacity calculator an other tools convert
        the values to cm on-the-fly. NOAA rainfall rasters cover a large
        area, so they are not necessarily specific to one culvert analysis
        project.

     INPUTS:
      aoi_geo (Feature Layer):
          A feature class that contains data--any data--in your study area.
          This could be an Area of Interest (AOI) polygon but could also be
          culvert data. The location of the features are just used to determine
          what NOAA region to download rainfall data for.
      target_raster {Raster Layer}:
          Optional raster used for snapping, clipping, re-projecting, and
          resampling the downloaded rainfall rasters. <SPAN />  In most cases,
          this is not necessary . It's only recommended to use this if you
          notice issues during peak flow calculations when rainfall statistics
          are being calculated. An appropriate input here is might be the DEM
          or landcover used for your study area. Note that the NOAA rainfall
          raster resolution is typically relatively low compared to other inputs
          used in this process. Depending on the size and resolution of that
          raster, you may see an increase or decrease in processing times for
          peak-flow calculations as a result of changing the rainfall raster
          resolution.
      out_folder (Folder):
          Output folder for the NOAA rainfall rasters and configuration file.
          Approximately 20 files will be generated by the tool, so it's
          recommended that this be a dedicated folde. Remember: NOAA rainfall
          rasters cover a large area, so they are not necessarily project-
          specific. Don't feel compelled to save these with every culvert
          analysis project!

     OUTPUTS:
      out_file_name {String}:
          Optional filename for the output  rainfall raster configuration
          file . This is a JSON file that will store reference to outputs and is
          used as an input to other tools. Defaults to
          "rainfall_rasters_config.json"."""
    from arcpy.geoprocessing._base import gp, gp_fixargs
    from arcpy.arcobjects.arcobjectconversion import convertArcObjectToPythonObject
    try:
        retval = convertArcObjectToPythonObject(gp.NoaaRainfallEtlPytTool_CulvertToolkit(*gp_fixargs((aoi_geo, target_raster, out_folder, out_file_name), True)))
        return retval
    except Exception as e:
        raise e


# End of generated toolbox code
del gptooldoc, gp, gp_fixargs, convertArcObjectToPythonObject