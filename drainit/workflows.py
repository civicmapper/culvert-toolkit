"""classes encapsulating workflows
"""

import json
from pathlib import Path
from dataclasses import asdict, replace
from marshmallow import ValidationError
from typing import Tuple, List

import click
import pint

from .models import (
    WorkflowConfig, 
    WorkflowConfigSchema, 
    RainfallRasterConfig, 
    RainfallRasterConfigSchema,
    PeakFlow01Schema,
    Point
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
        self.config: WorkflowConfig = WorkflowConfig()
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


class NaaccDataIngest(WorkflowManager):
    """read in and validate a NAACC compliant CSV, save to a Geodatabase.

    Inputs are: 

    * The path to the NAACC CSV
    * the CRS of the coordinates in the NAACC CSV
    * the output geodatabase
    * the output feature class name

    """
    pass


# ------------------------------------------------------------------------------
# Peak-Flow Calculator

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

        self.load_points()

        # delineate watersheds
        self.gp.catchment_delineation_in_series()

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
        self.gp.load_points()

        # derive the rasters from input DEM and save refs
        derived_rasters = self.gp.derive_from_dem(self.config.raster_dem_filepath)
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
# Culvert Capacity Calculator
# Calculates the capacity of culverts during storm events using a combination of
# peak-flow and a culvert capacity models. Relies on a culvert data that 
# follows the NAACC-standard.

class CulvertCapacityCore(WorkflowManager):

    def __init__(
        self, 
        rainfall_raster_json_filepath,
        save_config_json_filepath=None,
        **kwargs
    ):
        """End-to-end calculation of culvert capacity, peak-flow, and overflow. 
        Relies on points that follow the NAACC standard, which are required for 
        the capacity calculations to work here.
        """

        super().__init__(**kwargs)
        self.save_config_json_filepath = save_config_json_filepath
        self.load(rainfall_raster_json_filepath=rainfall_raster_json_filepath)

        # initialize the appropriate GP object with the config variables
        self.gp = GP(self.config)
    
    def load_points(self) -> Tuple(List[Point], dict):
        """workflow-specific approach to ETL of source point dataset. Handles
        Either the NAACC csv or a points geodataset that matches the NAACC
        schema can work here; this handles the ETL appropriately.
        """

        p = Path(self.config.points_filepath)
        
        # for a NAACC CSV input, we ETL the table, create a Python representation
        # of that data in a geo-format (dependent on the GP service used), and 
        # save the geo-formatted version to disk using output_points_filepath
        if p.suffix == ".csv":
            points = etl_naacc_table(
                naacc_csv_file=self.config.points_filepath,
                spatial_ref=4326 # TODO: require spatial reference WKID for NAACC coords to be provided as input
            )
            points_features = self.gp.create_geodata_from_points(
                points=self.config.points,
                output_points_filepath=self.config.output_points_filepath
            )
            points_spatial_ref_code = 4326 # TODO: require spatial reference WKID for NAACC coords to be provided as input
            
        # for anything else (assuming we've already restricted input types to
        # a geodatabase feature class, geopackage table, geoservices json, or 
        # geojson), load it into a Python representation of that data in a 
        # geo-format (dependent on the GP service used), ETL the table
        else:
            points, points_features, points_spatial_ref_code = self.gp.extract_points_from_geodata(
                points_filepath=self.config.points_filepath,
                uid_field=self.config.points_id_fieldname,
                is_naacc=True,
                output_points_filepath=self.config.output_points_filepath
            )
        
        # save those to the config
        # ...as a list of Drain-It Point objects:
        self.config.points = points
        # ...as the geo/json (GeoJSON or Geoservices JSON depending on the GP module used)
        self.config.points_features = points_features
        # the spatial ref of the points
        self.config.points_spatial_ref_code = points_spatial_ref_code

        return self.config.points, self.config.points_features
    
    def run(self):

        # load points
        # with NAACC data, capacity is calculated on load
        self.load_points() # updates self.config.points and self.config.points_features

        # delineate and analyze catchments for each point
        self.config.points, self.config.sheds = self.gp.delineation_and_analysis_in_parallel(
            points=self.config.points,
            pour_point_field=self.config.points_id_fieldname,
            flow_direction_raster=self.config.raster_flowdir_filepath,
            slope_raster=self.config.raster_slope_filepath,
            curve_number_raster=self.config.raster_curvenumber_filepath,
            out_shed_polygons=self.config.output_sheds_filepath,
            rainfall_config=self.config.rainfall_rasters,
            out_catchment_polygons_simplify=self.config.sheds_simplify
        )
        
        for pt in self.config.points:
            
            # copy rainfall intervals from point.shed to point.analytics
            pt.rainfall_from_shed_to_point()
            # calculate time of concentration for the point's shed
            pt.shed.calculate_tc()

            # for each rainfall interval, calculate peak flow
            for rainfall_interval in pt.analytics:

                # instantiate a Runoff dataclass
                rainfall_interval.runoff = runoff.Runoff()
                # add in the tc that has already been calculated for the shed
                rainfall_interval.runoff.time_of_concentration = pt.shed.tc_hr
                # calculate peak flow
                rainfall_interval.runoff.calculate_peak_flow(
                    mean_slope_pct=pt.shed.avg_slope_pct,
                    max_flow_length_m=pt.shed.max_fl,
                    rainfall_cm=rainfall_interval.rain_val,
                    basin_area_sqkm=pt.shed.area_sqkm,
                    avg_cn=pt.shed.avg_cn,
                    tc_hr=pt.shed.tc_hr
                )
            
            # if capacity was calculated, calculate overflow
            rainfall_interval.overflow = overflow.Overflow()


        # save the config
        if self.save_config_json_filepath:
            self.save(self.save_config_json_filepath)
        
        return