# -*- coding: utf-8 -*-

from pathlib import Path
import arcpy

from drainit.workflows import (
    CulvertCapacity,
    NaaccDataIngest,
    NaaccDataSnapping,
    RainfallDataGetter
)

class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Culvert Analysis Toolkit"
        self.alias = "CulvertToolkit"

        # List of tool classes associated with this toolbox
        self.tools = [
            NaaccEtlPytTool,
            NaaccSnappingPytTool,
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
            arcpy.Parameter(displayName="Output Feature Class", name="output_fc",datatype="DEFeatureClass", parameterType='Required', direction='Output')
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


class NaaccSnappingPytTool(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "NAACC Culvert Snapping"
        self.description = NaaccDataSnapping.__doc__
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""
        params=[
            arcpy.Parameter(displayName="Input NAACC culvert feature class", name="naacc_points_table", datatype="DEFeatureClass", parameterType='Required', direction='Input'),
            arcpy.Parameter(displayName="Input NAACC culvert feature class - crossing/survey ID field", name="naacc_points_table_join_field", datatype="Field", parameterType='Required', direction='Input'),
            arcpy.Parameter(displayName="Input snapped NAACC crossing feature class", name="geometry_source_table", datatype="DEFeatureClass", parameterType='Required', direction='Input'),
            arcpy.Parameter(displayName="Input snapped NAACC crossing feature class - crossing/survey ID field", name="geometry_source_table_join_field", datatype="Field", parameterType='Required', direction='Input'),
            arcpy.Parameter(displayName="Output Feature Class", name="output_fc", datatype="DEFeatureClass", parameterType='Required', direction='Output'),
        ]
        self.params = params

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""

        # TODO: check for Spatial Analyst

        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        if parameters[0].value:
            parameters[1] = arcpy.Describe(parameters[0].value).fields

        if parameters[2].value:
            parameters[3] = arcpy.Describe(parameters[2].value).fields

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter. This method is called after internal validation."""

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""

        # naacc_points_table = parameters[0].value
        # naacc_points_table_join_field = parameters[1].value
        # geometry_source_table = parameters[2].value
        # geometry_source_table_join_field = parameters[3].value
        # output_fc = parameters[4].value

        # populate a dictionary of keyword arguments for the workflow tool
        for p in parameters:
            arcpy.AddMessage(f"{p.name} | {p.value}")
        
        kwargs = dict(
            output_fc=parameters[4].value.value,
            naacc_points_table=parameters[0].value.value,
            geometry_source_table= parameters[2].value.value,
            naacc_points_table_join_field=parameters[1].value.value,
            geometry_source_table_join_field= parameters[3].value.value            
        )            

        # derive the spatial reference WKID to be applied to the output from 
        # the geometry_source_table
        sr = arcpy.da.Describe(kwargs['geometry_source_table']).get('spatialReference')
        if sr:
            if sr.PCSCode:
                kwargs['crs_wkid'] = sr.PCSCode
            elif sr.GCSCode:
                kwargs['crs_wkid'] = sr.GCSCode
            else:
                # crs_wkid will default to 4326
                pass
        
        result = NaaccDataSnapping(**kwargs)

        return result.output_table

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