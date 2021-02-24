"""classes encapsulating workflows
"""

import json
from pathlib import Path
from dataclasses import asdict, replace
from marshmallow import ValidationError

import click
import pint

from .models import (
    WorkflowConfig, 
    WorkflowConfigSchema, 
    RainfallRasterConfig, 
    RainfallRasterConfigSchema,
    PeakFlow01Schema
)
from .calculators import runoff, capacity, overflow
from .settings import USE_ESRI
from .services.gp import GP
from .services.noaa import retrieve_noaa_rainfall_rasters
from .services.naacc import etl_naacc_table

# ------------------------------------------------------------------------------
# Workflow Base Class

class WorkflowManager():
    """Base class for all workflows. Provides methods for storing and 
    persisting results from various workflow components.
    """

    def __init__(
        self, 
        use_esri=USE_ESRI, 
        config_json_filepath=None, 
        rainfall_raster_json_filepath=None, 
        **kwargs
    ):

        # initialize an empty WorkflowConfig object with default values
        self.config = WorkflowConfig()
        # click.echo(self.config)

        # if any confile files provided, load here. This will replace the
        # config object entirely
        self.config_json_filepath = config_json_filepath
        self.rainfall_raster_json_filepath = rainfall_raster_json_filepath
        self.load()
        # click.echo(self.config)
        
        # regardless of what happens above, we have a config object. Now we
        # use the provided keyword arguments to update it, overriding any that
        # were provided in the JSON file.
        self.config = replace(self.config, **kwargs)
        # (individual workflows that subclass WorkflowManager handle whether or 
        # not the needed kwargs are actually present)

        # self.schema = WorkflowConfigSchema().load(**kwargs)

        self.rainfall_config = None
        
        self.using_esri = use_esri
        self.using_wbt = not use_esri
        self.units = pint.UnitRegistry()

        return self
    
    def save(self, config_json_filepath):
        """Save workflow config to JSON. 

        Note that validation via WorkflowConfigSchema will only fail
        if our code is doing something wrong.
        """

        self.config_json_filepath = Path(config_json_filepath)

        c = WorkflowConfigSchema().dump(asdict(self.config))
        with open(config_json_filepath, 'w') as fp:
            json.dump(c, fp)

        return self

    def load(self, config_json_filepath=None, rainfall_raster_json_filepath=None):
        """load a workflow from a JSON file
        
        Note that validation via WorkflowConfigSchema will fail if the JSON has 
        been manually changed outside in a way that doesn't follow the schema
        (i.e., it has to serialize correctly to load)
        """

        # ----------------------------------------------------------------------
        # Workflow Config

        # select the file path ref to load. defaults to arg, fallsback to 
        # instance variable

        cjf=None
        if config_json_filepath:
            cjf = config_json_filepath
            self.config_json_filepath = cjf
        elif self.config_json_filepath:
            cjf = self.config_json_filepath

        # reads from disk, validates, and stores
        if cjf:
            click.echo("Reading config from JSON file")
            with open(cjf) as fp:
                config_as_dict = json.load(fp)
            self.config = WorkflowConfigSchema().load(config_as_dict)

        # ----------------------------------------------------------------------
        # Rainfall Raster Config

        # select the file path ref to load. defaults to arg, fallsback to 
        # instance variable

        rrj = None
        if rainfall_raster_json_filepath:
            rrj = rainfall_raster_json_filepath
            self.rainfall_raster_json_filepath = rrj
        elif self.rainfall_raster_json_filepath:
            rrj = self.rainfall_raster_json_filepath

        # reads from disk, validates, and stores
        
        if rrj:
            click.echo("Reading config from JSON file")
            with open(rrj) as fp:
                rainfall_config_as_dict = json.load(fp) 
                self.rainfall_config = RainfallRasterConfigSchema().load(rainfall_config_as_dict)

        return self
            

# ------------------------------------------------------------------------------
# Data Prep Workflows

class RainfallDataGetter(WorkflowManager):
    """Tool for acquiring and persisting rainfall rasters for a study area.
    Inputs: 
        * Anything geo that from which an appropriate bounding box can be
        derived.

    Outputs:
        * JSON (as Python dictionary) that contains references to a directory where the
        rainfall rasters have been saved--specifically which raster
        represents which storm event.
    """
    def __init__(**kwargs):
        super().__init__(**kwargs)
        pass


class CurveNumberMaker(WorkflowManager):
    """Tool for creating a curve number raster from landcover, soils, and
    a lookup table.

    Inputs:
        * landcover raster
        * soils raster
        * lookup table (as csv): landcover value + soils value = curve number
        * a reference raster for snapping (optional)
    Output:
        * a curve number raster
    """
    pass


# ------------------------------------------------------------------------------
# Basin Peak Flow 

class PeakFlowCore(WorkflowManager):

    def __init__(
        self, 
        rainfall_raster_json_filepath,
        save_config_json_filepath=None,
        **kwargs
    ):
        """Core Peak Flow workflow.

        :param save_config_json_filepath: save workflow config to a file, defaults to None
        :type save_config_json_filepath: str, optional
        :param kwargs: relevant properties in the WorkflowConfig object
        :type kwargs: kwargs, optional 
        """

        super().__init__(**kwargs)
        self.save_config_json_filepath = save_config_json_filepath
        self.load(rainfall_raster_json_filepath=rainfall_raster_json_filepath)

        # initialize the appropriate GP object with the config variables
        self.gp = GP(self.config)
    
    def load_points(self):
        self.gp.extract_points_from_geodata()
        pass
    
    def run_core_workflow(self):

        # delineate watersheds
        self.gp.catchment_delineation()

        # derive data from catchments
        self.gp.derive_data_from_catchments()

        # calculate peak flow (t of c and flow per return period)
        

        # save the config
        if self.save_config_json_filepath:
            self.save(self.save_config_json_filepath)        
        
        return


class PeakFlow01(PeakFlowCore):
    """Peak flow calculator; derives needed rasters from the DEM.
    """
    def __init__(self, **kwargs):
        
        super().__init__(**kwargs)

        # Serialize the parameters from workflow config that are applicable to 
        # this workflow -- make sure we have what we need
        errors = PeakFlow01Schema().validate(asdict(self.config))

        if errors:
            for k, v in errors:
                print("errors for {0}: {1}".format(k, "; ".join(v)))
            self.validation_errors.append(errors)
            return

        # ETL the input points. We don't need NAACC for peak flow, just 
        # locations and UID
        self.geoprocessor.load_points()

        # derive the rasters from input DEM and save refs
        derived_rasters = self.geoprocessor.derive_from_dem(self.config.raster_dem_filepath)
        self.config.raster_flowdir_filepath = derived_rasters['flow_direction_raster']
        self.config.raster_slope_filepath = derived_rasters['slope_raster']

        # run the rest of the peak-flow-calc workflow
        self.run_core_workflow()
        

# class PeakFlow02(PeakFlowCore):
#     """Peak flow calculator, with BYO dem-derived slope and flow direction 
#     rasters.
#     """
#     def __init__(**kwargs):
#         super().__init__(**kwargs)
#     pass


# class PeakFlow03(PeakFlowCore):
#     """Peak flow calculator; BYO watersheds (to skip delineations)
#     """
#     def __init__(**kwargs):
#         super().__init__(**kwargs)    
#     pass


# ------------------------------------------------------------------------------
# Culvert Capacity

class Capacity01(WorkflowManager):
    """Calculates culverta capacity *only*. Relies on NAACC standard 
    inputs, which are required for capacity calcs to work.
    """
    pass


# ------------------------------------------------------------------------------
# Culvert Overflow

class OverFlowEval(WorkflowManager):

    def __init__(
        self, 
        rainfall_raster_json_filepath,
        save_config_json_filepath=None,
        **kwargs
    ):
        """End-to-end calculation of peak-flow, capacity, and overflow. Uses the
        PeakFlow01 workflow; relies on NAACC standard inputs (req. for capacity 
        calcs to work).
        """

        super().__init__(**kwargs)
        self.save_config_json_filepath = save_config_json_filepath
        self.load(rainfall_raster_json_filepath=rainfall_raster_json_filepath)

        # initialize the appropriate GP object with the config variables
        self.gp = GP(self.config)
    
    def load_points(self):
        p = Path(self.config.points_filepath)
        
        # for a NAACC CSV input, we ETL the table, create a Python representation
        # of that data in a geo-format (dependent on the GP service used), and 
        # save the geo-formatted version to disk using output_points_filepath
        if p.suffix == ".csv":
            points = etl_naacc_table(
                naacc_csv_file=self.config.points_filepath
            )
            points_featureset = self.gp.create_geodata_from_points(
                points=self.config.points,
                output_points_filepath=self.config.output_points_filepath
            )
            
        # for anything else (assuming we've already restricted input to files
        # a geodatabase feature class, geopackage table, geoservices json, or 
        # geojson), load it into a Python representation of that data in a 
        # geo-format (dependent on the GP service used), ETL the table
        else:
            points, points_featureset = self.gp.extract_points_from_geodata(
                points_filepath=self.config.points_filepath,
                is_naacc=True,
                output_points_filepath=self.config.output_points_filepath
            )
        
        # save those to the config
        self.config.points = points
        self.config.points_features = json.loads(points_featureset.JSON)
    
    def run_core_workflow(self):

        # load points
        # with NAACC data, capacity is calculated on load
        self.load_points()

        # delineate watersheds
        self.gp.catchment_delineation(
            points_featureset=self.config.output_points_filepath,
            raster_flowdir_filepath,
            points_id_fieldname,
        )

        # derive data from catchments
        self.gp.derive_data_from_catchments()

        # calculate peak flow (t of c and flow per return period)

        # calculate overflow

        # save the config
        if self.save_config_json_filepath:
            self.save(self.save_config_json_filepath)        
        
        return