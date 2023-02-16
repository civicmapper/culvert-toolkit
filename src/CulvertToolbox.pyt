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
            arcpy.Parameter(category="DEM", displayName="Flow Length", name="raster_flowlen_filepath", datatype="GPRasterLayer", parameterType='Optional', direction='Input'),
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

        try:
            if arcpy.CheckExtension("Spatial") != "Available":
                raise Exception
        except Exception:
            return False  # The tool cannot be run

        return True  # The tool can be run

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

        kwargs = {}
        for p in parameters:
            arcpy.AddMessage(f"{p.name} | {p.datatype}")
            if p.parameterType != 'Derived':
                if p.datatype in ('Feature Layer', 'Raster Layer'):
                    if p.value:
                        kwargs[p.name] = p.value.dataSource
                elif p.datatype == 'Feature Class':
                    if p.value:
                        kwargs[p.name] = p.value.value
                else:
                    if p.value:
                        kwargs[p.name] = p.value.value

            # try:
            #     arcpy.AddMessage(f"{p.name} >>> {p.value.__class__.__name__}")
            #     arcpy.AddMessage(f"\t{p.value.dataSource}")
            #     kwargs[p.name] = p.value.dataSource
            # except:
            #     arcpy.AddMessage(f"{p.name} >>> {type(p.value)}")
            #     arcpy.AddMessage(f"\t{p.value.value}")

        kwargs['output_sheds_filepath'] = f"{kwargs['output_points_filepath']}_sheds"
        
        culvert_capacity_calc = CulvertCapacity(**kwargs)
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

        # turn parameters into keyword args
        tool_kwargs = {p.name: p.value.value for p in parameters}

        # print some things
        for k, v in tool_kwargs.items():
            arcpy.AddMessage(f"{k} | {v}")
        
        n = NaaccDataIngest(**tool_kwargs)

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
            arcpy.Parameter(displayName="feature class", name="naacc_points_table", datatype="DEFeatureClass", parameterType='Required', direction='Input', category="Input NAACC culverts (original locations)"),
            arcpy.Parameter(displayName="crossing/survey ID field", name="naacc_points_table_join_field", datatype="Field", parameterType='Required', direction='Input', category="Input NAACC culverts (original locations)"),
            arcpy.Parameter(displayName="NAACC crossing feature class", name="geometry_source_table", datatype="DEFeatureClass", parameterType='Required', direction='Input', category="Input NAACC snapped crossings (target locations)"),
            arcpy.Parameter(displayName="NAACC crossing/survey ID field", name="geometry_source_table_join_field", datatype="Field", parameterType='Required', direction='Input', category="Input NAACC snapped crossings (target locations)"),
            arcpy.Parameter(displayName="Output Feature Class", name="output_fc", datatype="DEFeatureClass", parameterType='Required', direction='Output', category="Output NAACC culverts with updated locations"),
        ]
        self.params = params

        params[1].value = "Survey_Id"
        params[3].value = "Survey_Id"

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""

        # TODO: check for Spatial Analyst

        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        # if parameters[0].value:
        #     parameters[1] = arcpy.Describe(parameters[0].value).fields

        # if parameters[2].value:
        #     parameters[3] = arcpy.Describe(parameters[2].value).fields

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter. This method is called after internal validation."""

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""

        # turn parameters into keyword args
        tool_kwargs = {p.name: p.value.value for p in parameters}

        # print some things
        for k, v in tool_kwargs.items():
            arcpy.AddMessage(f"{k} | {v}")
        
        arcpy.AddMessage(f"replacing the geometry in {tool_kwargs['naacc_points_table']} with geometry from {tool_kwargs['geometry_source_table']} based on the match between fields {tool_kwargs['naacc_points_table_join_field']} and {tool_kwargs['geometry_source_table_join_field']}")

        # run the tool
        result = NaaccDataSnapping(**tool_kwargs)

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
            arcpy.Parameter(displayName="Output Rainfall Configuration File Name", name="out_file_name",datatype="GPString", parameterType='Optional', direction='Output'),
        ]
        # default for the output file name
        parameters[3].value = "culvert_toolbox_rainfall_config.json"
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""

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
        # required parameters
        kwargs = dict(
            aoi_geo=parameters[0].value.dataSource,
            out_folder=parameters[2].value.value
        )

        #optional paramters
        if parameters[1].value:
            kwargs.update(dict(
                target_raster=parameters[1].value.dataSource
            ))
        if parameters[3].value:
            kwargs.update(dict(
                out_file_name=parameters[3].value
            ))

        # arcpy.AddMessage(kwargs)
        messages.AddMessage("Retrieving NOAA rainfall rasters for the area of interest...")
        rdg = RainfallDataGetter(**kwargs)
        arcpy.AddMessage("Completed")
        return

    def postExecute(self, parameters):
        """This method takes place after outputs are processed and
        added to the display."""
        return        