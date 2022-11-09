# -*- coding: utf-8 -*-

import arcpy
import os
from drainit.workflows import CulvertCapacity

class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Culvert Toolbox"
        self.alias = "CulvertToolbox"

        # List of tool classes associated with this toolbox
        self.tools = [
            CulvertCapacityPytTool,
            SampleTool
        ]

class CulvertCapacityPytTool(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "NAACC Culvert Capacity"
        self.description = "Measure the capacity of culverts by calculating peak flow over a hydrologically corrected digital elevation model. Culvert location data must be NAACC schema-compliant."
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""
        parameters=[
            arcpy.Parameter(displayName="Culvert Points", name="points_filepath", datatype="GPFeatureLayer", parameterType='Required', direction='Input'),
            arcpy.Parameter(displayName="Flow Direction", name="raster_flowdir_filepath", datatype="GPRasterLayer", parameterType='Required', direction='Input'),
            arcpy.Parameter(displayName="Flow Length", name="raster_flowlen_filepath", datatype="GPRasterLayer", parameterType='Required', direction='Input'),
            arcpy.Parameter(displayName="Slope", name="raster_slope_filepath", datatype="GPRasterLayer", parameterType='Required', direction='Input'),
            arcpy.Parameter(displayName="Curve Number", name="raster_curvenumber_filepath", datatype="GPRasterLayer", parameterType='Required', direction='Input'),
            arcpy.Parameter(displayName="Precipitation Configuration File", name="precip_src_config_filepath", datatype="DEFile", parameterType='Required', direction='Input'),
            arcpy.Parameter(displayName="Result Points", name="output_points_filepath",datatype="DEFeatureClass", parameterType='Required', direction='Output'),
            arcpy.Parameter(displayName="Result Delineations", name="output_sheds_filepath",datatype="DEFeatureClass", parameterType='Derived', direction='Output'),
        ]
        return parameters

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


class SampleTool(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Sample Tool"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""
        parameters=[arcpy.Parameter(displayName='Msg', 
                                  name='msg',
                                  datatype='GPString',
                                  parameterType='Derived',
                                  direction='Output')
                                  ]
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
        result = os.getenv("username")
        messages.AddMessage(f"{result}, welcome to the sample tool")
        messages.AddMessage(CulvertCapacity.__init__.__doc__)
        parameters[0].value = result
        return