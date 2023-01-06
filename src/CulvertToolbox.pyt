# -*- coding: utf-8 -*-

from pathlib import Path
import arcpy

from drainit.workflows import CulvertCapacity
from drainit.workflows import NaaccDataIngest
from drainit.workflows import RainfallDataGetter

class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Culvert Analysis Toolkit"
        self.alias = "CulvertToolkit"

        # List of tool classes associated with this toolbox
        self.tools = [
            NaaccEtlPytTool,
            NoaaRainfallEtlPytTool,
            CulvertCapacityPytTool,
        ]

class CulvertCapacityPytTool(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "NAACC Culvert Capacity"
        self.description = CulvertCapacity.__doc__
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""
        params=[
            arcpy.Parameter(category="Culverts", displayName="Culvert Points", name="points_filepath", datatype="GPFeatureLayer", parameterType='Required', direction='Input'),
            arcpy.Parameter(category="DEM", displayName="Flow Direction", name="raster_flowdir_filepath", datatype="GPRasterLayer", parameterType='Required', direction='Input'),
            arcpy.Parameter(category="DEM", displayName="Flow Length", name="raster_flowlen_filepath", datatype="GPRasterLayer", parameterType='Required', direction='Input'),
            arcpy.Parameter(category="DEM", displayName="Slope", name="raster_slope_filepath", datatype="GPRasterLayer", parameterType='Required', direction='Input'),
            arcpy.Parameter(category="Curve Number", displayName="Curve Number", name="raster_curvenumber_filepath", datatype="GPRasterLayer", parameterType='Required', direction='Input'),
            arcpy.Parameter(category="Rainfall", displayName="Precipitation Configuration File", name="precip_src_config_filepath", datatype="DEFile", parameterType='Required', direction='Input'),
            arcpy.Parameter(category="Outputs", displayName="Result Points", name="output_points_filepath",datatype="DEFeatureClass", parameterType='Required', direction='Output'),
            arcpy.Parameter(category="Outputs", displayName="Result Delineations", name="output_sheds_filepath",datatype="DEFeatureClass", parameterType='Derived', direction='Output'),
        ]

        params[0].filter.list = ['Point']

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""

        # TODO: check for Spatial Analyst

        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        # TODO: auto-set the output sheds filepath based on the output points 
        # filepath, (which will be limited to a fgdb feature class)

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        # TODO: validate the Precip Source config JSON file input

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        
        culvert_capacity_calc = CulvertCapacity(
            **{p.name: p.value for p in parameters}
        )
        # run the calculator
        # * Internally this method calls the load_points method, which ETLs the feature class 
        # at `points_filepath` to the internal data model and perform validation.
        # * It then runs the delineations and derives the attributes required for peak flow.
        # * With delineations complete, it calculates overflow
        # * outputs are saved to the user-spec'd feature class
        culvert_capacity_calc.run() 
        return

    def postExecute(self, parameters):
        """This method takes place after outputs are processed and
        added to the display."""
        return


class NaaccEtlPytTool(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "NAACC Table Ingest"
        self.description = NaaccDataIngest.__doc__
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""
        params=[
            arcpy.Parameter(displayName="NAACC Table (CSV or Feature Class)", name="naacc_src_table", datatype=["DEFile", "DEFeatureClass"], parameterType='Required', direction='Input'),
            arcpy.Parameter(displayName="Output Folder", name="output_folder",datatype="DEFolder", parameterType='Required', direction='Output'),
            arcpy.Parameter(displayName="Output Feature Class", name="output_fc",datatype="DEFeatureClass", parameterType='Required', direction='Output'),
            arcpy.Parameter(displayName="Alternative Geometry Reference Table", name="alt_geom_table", datatype="DEFeatureClass", parameterType='Optional', direction='Input'),
            arcpy.Parameter(displayName="Survey ID Field in Alt. Geometry Ref. Table ", name="alt_geom_table_join_field", datatype="DEFeatureClass", parameterType='Optional', direction='Input')
        ]

        # params[0].filter.list = ['txt', 'csv']

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""

        # TODO: check for Spatial Analyst

        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""

        naacc_src_table = parameters[0].value
        output_folder = parameters[1].value
        output_fc_param = parameters[2].value

        output_fc_path = Path(output_fc_param)
        output_fc_name = output_fc_path.name
        output_workspace = output_fc_path.parent
        
        n = NaaccDataIngest(
            naacc_src_table=naacc_src_table,
            output_folder=output_folder,
            output_workspace=output_workspace,
            output_fc_name=output_fc_name
            # crs_wkid=GetParameterAsText(4), #4326
            # naacc_x=GetParameterAsText(5), #"GIS_Longitude",
            # naacc_y=GetParameterAsText(6)# "GIS_Latitude",
        )
        return n.output_points_filepath

    def postExecute(self, parameters):
        """This method takes place after outputs are processed and
        added to the display."""
        return        


class NoaaRainfallEtlPytTool(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "NOAA Rainfall Raster Data Downloader"
        self.description = RainfallDataGetter.__doc__
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""
        parameters=[
            arcpy.Parameter(displayName="Area of Interest", name="aoi_geo", datatype="GPFeatureLayer", parameterType='Required', direction='Input'),
            arcpy.Parameter(displayName="Reference Raster", name="target_raster",datatype="GPRasterLayer", parameterType='Optional', direction='Input'),
            arcpy.Parameter(displayName="Output Folder", name="out_folder",datatype="DEFolder", parameterType='Required', direction='Input'),
            arcpy.Parameter(displayName="Output Rainfall Configuration File Name", name="out_file_name",datatype="GPString", parameterType='Required', direction='Output'),
        ]
        parameters[3].value = "culvert_toolbox_rainfall_config"
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""

        # TODO: check for Spatial Analyst

        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""

        rdg = RainfallDataGetter(
            aoi_geo=parameters[0].value,
            target_raster=parameters[1].value,
            out_folder=parameters[2].value,
            out_file_name=parameters[3].value    
        )
        return

    def postExecute(self, parameters):
        """This method takes place after outputs are processed and
        added to the display."""
        return        