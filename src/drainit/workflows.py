"""classes encapsulating workflows
"""

import json
from copy import deepcopy
from pathlib import Path
from dataclasses import asdict, replace, fields
from typing import Tuple, List
from tempfile import mkdtemp
from collections import Counter, OrderedDict
import pdb

import petl as etl
import click
import pint
from tqdm import tqdm
from codetiming import Timer

from .models import (
    Analytics,
    WorkflowConfig, 
    WorkflowConfigSchema, 
    RainfallRasterConfig, 
    RainfallRasterConfigSchema,
    PeakFlow01Schema,
    DrainItPoint,
    DrainItPointSchema,
    NaaccCulvert
)
from .calculators import runoff, capacity, overflow
from .settings import USE_ESRI
from .services.gp import GP
from .services.noaa import retrieve_noaa_rainfall_rasters, retrieve_noaa_rainfall_pf_est
from .services.naacc import NaaccEtl
from .config import FREQUENCIES
from .utils import get_type

# ------------------------------------------------------------------------------
# Workflow Base Class


class WorkflowManager:
    """Base class for all workflows. Provides methods for storing and 
    persisting results for workflows.
    """

    def __init__(
        self,
        config_json_filepath=None,
        use_esri=USE_ESRI, 
        use_multiprocessing=False,
        **kwargs
    ):
        # print("WorkflowManager")

        # initialize an empty WorkflowConfig object with default values
        self.config: WorkflowConfig = WorkflowConfig()
        # click.echo(self.config)

        # if any config files provided, load here. This will replace the
        # config object entirely
        self.config_json_filepath = config_json_filepath
        self.load_config()
        # click.echo(self.config)
        
        # regardless of what happens above, we have a config object. Now we
        # use the provided keyword arguments to update it, overriding any that
        # were provided in the JSON file.
        # print(kwargs)
        self.config = replace(self.config, **kwargs)
        # (individual workflows that subclass WorkflowManager handle whether or 
        # not the needed kwargs are actually present)

        # self.schema = WorkflowConfigSchema().load(**kwargs)
        # click.echo(self.config)
        
        self.using_esri = use_esri
        self.using_wbt = not use_esri
        self.use_multiprocessing = use_multiprocessing
        self.units = pint.UnitRegistry()
        self.gp = GP(self.config)

        # code.interact(local=locals())

    def load_config(self, config_json_filepath=None):
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
            click.echo("Reading general config from JSON file")
            with open(cjf) as fp:
                config_as_dict = json.load(fp)
                # print(config_as_dict)
            self.config = WorkflowConfigSchema().load(config_as_dict, partial=True, unknown="INCLUDE")

        # ----------------------------------------------------------------------
        # Rainfall Raster Config (nested within the workflow config)
        # print("Workflow Manager: precip_src_config_filepath", self.config.precip_src_config_filepath)

        if self.config.precip_src_config_filepath is not None:
            click.echo("Reading rainfall config from JSON file")
            with open(self.config.precip_src_config_filepath) as fp:
                rainfall_config_as_dict = json.load(fp)
                self.config.precip_src_config = RainfallRasterConfigSchema().load(rainfall_config_as_dict)            

        return self        
    
    def save_config(self, config_json_filepath):
        """Save workflow config to JSON. 

        Note that validation via WorkflowConfigSchema will only fail
        if our code is doing something wrong.
        """

        self.config_json_filepath = Path(config_json_filepath)

        c = WorkflowConfigSchema().dump(self.config)
        # print(c)
        with open(config_json_filepath, 'w') as fp:
            json.dump(c, fp)

        return self


# ------------------------------------------------------------------------------
# Data Prep Workflows


class NaaccDataIngest(WorkflowManager):
    """Read in, validate, and extend a NAACC-compliant source table, saving the output as geodata (e.g., a file geodatabase feature class) for use in other culvert analysis tools.
    """

    def __init__(
        self, 
        naacc_src_table:str,
        output_fc:str,
        crs_wkid:int=4326,
        naacc_x:str="GIS_Longitude",
        naacc_y:str="GIS_Latitude",
        **kwargs
        ):  
        """read in, validate, and extend a NAACC compliant source table, saving
        the output to a geodata format (e.g., feature class in a geodatabase)

        Args:
            naacc_src_table (str): The path to the NAACC table
            output_fc (str): output path of the feature class. The parent folder is used for additional outputs
            crs_wkid (int, optional): the WKID of the coordinates in the NAACC CSV. Defaults to 4326.
            naacc_x (str, optional): name of the field in the naacc_src_table with Longitude/Y. Defaults to "GIS_Longitude".
            naacc_y (str, optional): name of the field in the naacc_src_table with Latitude/X. Defaults to "GIS_Latitude".
        """        

        super().__init__(**kwargs)

        self.naacc_src_table = naacc_src_table

        self.output_fc = output_fc
        self.output_file_name_root = Path(self.output_fc).name

        self.output_folder = None
        self.output_workspace = None

        self.crs_wkid = crs_wkid
        self.naacc_x = naacc_x
        self.naacc_y = naacc_y

        self.naacc_table = None

        # save path for the output table in the config property
        self.output_points_filepath = self.output_fc

        self._run()

    def _run(self):

        # initialize the appropriate GP object with the config variables
        self.gp = GP(self.config)
        
        self.output_folder, self.output_workspace = self.gp.create_featureclass_parents(self.output_fc)

        # set the file name of the output csv (will be used to derive subset tables as well)
        output_csv = self.output_folder / str(self.output_file_name_root + ".csv")

        # detect the input type.
        dt = self.gp.detect_data_type(self.naacc_src_table)
        # self.gp._msg(f"data type detected: {dt}")
        # handle different input types
        # CSVs end up here:
        if dt == 'TextFile':
            naacc = NaaccEtl(
                naacc_csv_file=self.naacc_src_table,
                output_path=output_csv,
                wkid=self.crs_wkid,
                naacc_x=self.naacc_x,
                naacc_y=self.naacc_y
            )
        # anything else ends up here:
        else:
            t, fs, wkid = self.gp.create_petl_table_from_geodata(self.naacc_src_table, include_geom=True)
            self.crs_wkid = wkid
            # the lat/lon fields will have been derived from the input geodata's
            # geometry field instead of a table column; reset those params
            # TODO: handle from kwargs
            self.naacc_x = "x"
            self.naacc_y = "y"

            naacc = NaaccEtl(
                naacc_petl_table=t,
                output_path=output_csv,
                wkid=self.crs_wkid,
                naacc_x=self.naacc_x,
                naacc_y=self.naacc_y
            )

        # extract the NAACC-compliant table to a PETL table, validating all fields *and* calculating
        # culvert capacity on-the-fly

        naacc.validate_extend_hydrate_naacc_table()
        self.naacc_table = naacc.table
        
        # specify which fields we'll carry over to the geodata using existing models
        # TODO: make this work within the GP provider's context; use a flattened 
        # DrainItPoint object to derive fields
        field_types_lookup = {}
        field_types_lookup.update({f.name: get_type(f.type) for f in fields(NaaccCulvert)})
        field_types_lookup.update({f.name: get_type(f.type) for f in fields(capacity.Capacity)})
        field_types_lookup.update({'validation_errors': str, 'include': str})
        
        # save the PETL-ified NAACC table to a geodata table (default: Esri FGDB feature class)
        featureset_json = self.gp.create_geodata_from_petl_table(
            petl_table=self.naacc_table,
            field_types_lookup=field_types_lookup,
            x_column=self.naacc_x, 
            y_column=self.naacc_y,
            output_featureclass=str(self.output_points_filepath),
            crs_wkid=self.crs_wkid
        )

        with open(self.output_folder / str(self.output_fc + ".json"), 'w') as fp:
            json.dump(featureset_json, fp)

        # return the location of the output on disk
        return self.output_points_filepath

    def _testing_output_geodata(self):
        """function used to read the saved geodata into a dictionary 
        in a geoprocessing-library-agnostic way
        """
        if Path(self.output_points_filepath).exists:
            d = self.gp.create_dicts_from_geodata(self.output_points_filepath)
            return d['features']
        else: return {}


class NaaccDataSnapping(WorkflowManager):
    
    def __init__(
        self, 
        output_fc:str,
        naacc_points_table:str,
        geometry_source_table:str,
        naacc_points_table_join_field:str="Survey_Id",
        geometry_source_table_join_field:str="Survey_Id",
        crs_wkid:int=4326,
        **kwargs
        ):
        """Move points in an existing ingested NAACC points table to new locations by referencing another table, and joining the geometry of features in that table based on a join ID. This tool is most useful after culverts have been snapped to raster flow lines, which typically results in only the crossing location being mapped.

        Args:
            output_fc (str): path to a new output feature class
            naacc_points_table (str): feature class with NAACC data (prepped via NaaccDataIngest)
            naacc_points_table_join_field (str): field in naacc_points_table used to match geometries to geometry_source_table records
            geometry_source_table (str): path to geodata table that includes modified geometries to replace those in naacc_src_table
            geometry_source_table_join_field (str, optional): field in geometry_source_table used to match geometries to naacc_points_table records. Defaults to "Survey_Id".
        """        

        super().__init__(**kwargs)
        self.gp = GP(self.config)

        self.output_fc = output_fc
        
        self.naacc_points_table = naacc_points_table
        self.naacc_points_table_join_field = naacc_points_table_join_field
        self.geometry_source_table = geometry_source_table
        self.geometry_source_table_join_field = geometry_source_table_join_field
        self.crs_wkid = crs_wkid

        self.output_table = None

        self._run()

    def _run(self):

        output_workspace = self.gp.create_featureclass_parents(self.output_fc)
        self.gp.msg(output_workspace)

        self.output_table = self.gp.update_geodata_geoms_with_other_geodata(
            target_feature_class=self.naacc_points_table,
            target_join_field=self.naacc_points_table_join_field,
            source_feature_class=self.geometry_source_table,
            source_join_field=self.geometry_source_table_join_field,
            output_feature_class=self.output_fc,
            crs_wkid=self.crs_wkid
        )

        return self.output_table


class RainfallDataGetter(WorkflowManager):
    """Download rainfall rasters for your study area from NOAA. By default, this tool acquires rainfall data for 24hr events for frequencies from 1 to 1000 year. All rasters are saved to the user-specified folder. A JSON file is automatically created; this file is used as a required input to other tools. Note that NOAA Atlas 14 precip values are in 1000ths/inch.
    """
    
    def __init__(
        self,
        aoi_geo,
        out_folder,
        out_file_name="rainfall_rasters_config.json",
        target_raster=None,
        target_crs_wkid=None,
        **kwargs
        ):
        """Tool for acquiring and persisting rainfall rasters for a study area.
        Defaults to acquiring rainfall data for 24hr events for frequencies from 1 to 1000 year.
        All rasters are saved to a specified folder. A JSON file is automatically created; this 
        file is used as a required input to other tools.

        Note that NOAA Atlas 14 precip values are in 1000ths/inch. The Peak Flow calculator 
        requires those values be converted to cm. Currently that happens in the gp
        module.

        Args:
            aoi_geo (str): Path to anything geo from which a minimum bounding geometry can be derived. Used to identify the correct region for downloading rasters.
            out_folder (_type_): path on disk where outputs will be saved
            out_file_name (str, optional): name of JSON file that will store reference to outputs and is used as an input to other tools. Defaults to "rainfall_rasters_config.json".
            target_raster (_type_, optional): Optional raster used for snapping and clipping the rainfall rasters. An appropriate input here is the DEM used for your study area. Depending on the size and resolution of that raster, you may see a decrease in processing times for peak-flow calculations.
            target_crs_wkid (_type_, optional): Optional CRS WKID, used for reprojecting the rasters.
        """

        super().__init__(**kwargs)
        
        self.aoi_geo = aoi_geo
        self.out_folder = out_folder
        self.out_file_name = out_file_name
        self.out_path = Path(out_folder) / out_file_name
        self.results = None
        self.target_crs_wkid = target_crs_wkid
        self.target_raster = target_raster

        # auto run on init
        self._run()
        print("saved to {0}".format(self.out_path))

    def _run(self):
        # from a method in the GP module, get the centroid of the aoi
        with Timer(name="Determing NOAA region", text="{name}: {:.1f} seconds", logger=self.gp.msg):
            coords = self.gp.get_centroid_of_feature_envelope(self.aoi_geo)
            # pass it to retrieve_noaa_rainfall_pf_est, which will give us the region
            r = retrieve_noaa_rainfall_pf_est(lat=coords['lat'], lon=coords['lon'])
        # pass the region to this function, which gets the rasters
        # and saves them to the specified folder
        temp_out_folder = mkdtemp()
        with Timer(name="Retrieving rainfall rasters", text="{name}: {:.1f} seconds", logger=self.gp.msg):
            rainfall_raster_config1 = retrieve_noaa_rainfall_rasters(
                out_folder=temp_out_folder,
                out_file_name=self.out_file_name, 
                study=r['reg']
            )
        # resample, reproject, and crop the downloaded rasters
        with Timer(name="Post-processing rainfall rasters", text="{name}: {:.1f} seconds", logger=self.gp.msg):
            rainfall_raster_config2 = self.gp.create_geotiffs_from_rainfall_rasters(
                rrc=rainfall_raster_config1, 
                out_folder=self.out_folder,
                target_crs_wkid=self.target_crs_wkid, 
                target_raster=self.target_raster
            )
        # save the config to JSON
        rrc = RainfallRasterConfigSchema().dump(asdict(rainfall_raster_config2))
        with open(self.out_path, 'w') as fp:
            json.dump(rrc, fp)
            self.gp.msg(f"Saving configuration file to: {self.out_path}")
        self.results = rainfall_raster_config2
        return self.results


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
    def __init__(self):  
        pass


# ------------------------------------------------------------------------------
# Peak-Flow Calculator

#     """Peak flow calculator; BYO watersheds (to skip delineations)
#     """
#     """Peak flow calculator, with BYO dem-derived slope and flow direction 
#     rasters.
#     """


# class PeakFlowCore(WorkflowManager):

#     def __init__(
#         self, 
#         precip_src_config_filepath,
#         save_config_json_filepath=None,
#         **kwargs
#     ):
#         """Core Peak Flow workflow.

#         :param save_config_json_filepath: save workflow config to a file, defaults to None
#         :type save_config_json_filepath: str, optional
#         :param kwargs: relevant properties in the WorkflowConfig object
#         :type kwargs: kwargs, optional 
#         """

#         super().__init__(**kwargs)
#         self.save_config_json_filepath = save_config_json_filepath
#         self.load_config(precip_src_config_filepath=precip_src_config_filepath)

#         # initialize the appropriate GP object with the config variables
#         self.gp = GP(self.config)
    
#     def load_points(self):
#         self.gp.create_point_objects_from_geodata()
#         pass
    
#     def run_core_workflow(self):

#         self.load_points()

#         # delineate watersheds
#         self.gp.catchment_delineation_in_series()

#         # derive data from catchments
#         self.gp.derive_data_from_catchments()

#         # calculate peak flow (t of c and flow per return period)
        

#         # save the config
#         if self.save_config_json_filepath:
#             self.save_config(self.save_config_json_filepath)        
        
#         return


# class PeakFlow01(PeakFlowCore):
#     """Peak flow calculator; derives needed rasters from the DEM.
#     """
#     def __init__(self, **kwargs):
        
#         super().__init__(**kwargs)

#         # Serialize the parameters from workflow config that are applicable to 
#         # this workflow -- make sure we have what we need
#         errors = PeakFlow01Schema().validate(asdict(self.config))

#         if errors:
#             for k, v in errors:
#                 print("errors for {0}: {1}".format(k, "; ".join(v)))
#             self.validation_errors.append(errors)
#             return

#         # ETL the input points. We don't need NAACC for peak flow, just 
#         # locations and UID
#         self.gp.load_points()

#         # derive the rasters from input DEM and save refs
#         derived_rasters = self.gp.derive_analysis_rasters_from_dem(self.config.raster_dem_filepath)
#         self.config.raster_flowdir_filepath = derived_rasters['flow_direction_raster']
#         self.config.raster_slope_filepath = derived_rasters['slope_raster']

#         # run the rest of the peak-flow-calc workflow
#         self.run_core_workflow()
        


# ------------------------------------------------------------------------------
# Culvert Capacity Calculator

class CulvertCapacity(WorkflowManager):
    """Measure the capacity of culverts by calculating peak flow over a hydrologically corrected digital elevation model. Culvert location data must be NAACC schema-compliant.
    """

    def __init__(
        self,
        save_config_json_filepath=None,
        # points_filepath,
        # raster_flowdir_filepath,
        # raster_slope_filepath,
        # raster_curvenumber_filepath,
        # precip_src_config_filepath,
        # output_points_filepath=None,
        # points_id_fieldname="Naacc_Culvert_Id",
        # points_group_fieldname="Survey_Id",
        use_multiprocessing=False,
        **kwargs
        ):
        """End-to-end calculation of culvert capacity, peak-flow, and overflow. 
        Relies on points that follow the NAACC standard, which are required for 
        the capacity calculations to work here. Defaults reflect that assumption.
        """
        # print("CulvertCapacityCore")

        super().__init__(**kwargs)
        
        if save_config_json_filepath:
            self.save_config_json_filepath = save_config_json_filepath
            self.load_config(config_json_filepath=save_config_json_filepath)
        else:
            self.save_config_json_filepath = f'{self.gp._so("drainit_config", suffix="", where="folder")}.json'
            self.load_config()
        
        self.use_multiprocessing = use_multiprocessing

        # initialize the appropriate GP module with the config variables
        self.gp = GP(self.config) 

        # Field mappings
        # TODO: move to config and/or derive from dataclass metadata
        self.shed_field_map = OrderedDict({
            "area_sqkm": "shed_area_sqkm", 
            "avg_slope_pct": "shed_avg_slope_pct", 
            "avg_cn": "shed_avg_cn", 
            "max_fl": "shed_max_fl", 
            "tc_hr": "shed_tc_hr", 
            #"avg_rainfall": "shed_avg_rainfall"
        })
        self.analytics_field_map = OrderedDict({
            'culvert_peakflow_m3s': 'ppf_m3s',
            'crossing_peakflow_m3s': 'xpf_m3s',
            'culvert_overflow_m3s': 'pof_m3s',
            'crossing_overflow_m3s': 'xof_m3s'
        })
        self.capacity_field_map = OrderedDict({
            "culv_mat": "culv_mat",
            "in_type": "in_type",
            "in_shape": "in_shape",
            "in_a": "in_a",
            "in_b": "in_b",
            "hw": "hw",
            "slope": "slope",
            "length": "length",
            "out_shape": "out_shape",
            "out_a": "out_a",
            "out_b": "out_b",
            "crossing_type": "crossing_type",
            "culvert_area_sqm": "culvert_area_sqm",
            "culvert_depth_m": "culvert_depth_m",
            "coefficient_c": "coefficient_c",
            "coefficient_y": "coefficient_y",
            "coefficient_slope": "coefficient_slope",
            "slope_rr": "slope_rr",
            "head_over_invert": "head_over_invert",
            "culvert_capacity": "culvert_capacity",
            "crossing_capacity": "crossing_capacity",
            "max_return_period": "max_return_period"
        })             
        self.frequency_fields = [f'y{freq}' for freq in FREQUENCIES]
        
    
    def load_points(self) -> Tuple[List[DrainItPoint], dict]:
        """workflow-specific approach to ETL of source point dataset. Handles a 
        points geodataset that matches the NAACC schema. Performs validation of 
        the NAACC table and calculates capacity of the culverts when valid.
        """
        
        # for a NAACC CSV input, we ETL the table, create a Python representation
        # of that data in a geo-format (dependent on the GP service used), and 
        # save the geo-formatted version to disk using output_points_filepath
        # p = Path(self.config.points_filepath)
        # if p.suffix == ".csv":
        #     # TODO:
        #     pass
            # points = etl_naacc_table(
            #     naacc_csv_file=self.config.points_filepath,
            #     spatial_ref=4326 # TODO: require spatial reference WKID for NAACC coords to be provided as input
            # )
            # points_features = self.gp.create_geodata_from_points(
            #     points=self.config.points,
            #     output_points_filepath=self.config.output_points_filepath
            # )
            # points_spatial_ref_code = 4326 # TODO: require spatial reference WKID for NAACC coords to be provided as inputs
            
        # for anything else (assuming we've already restricted input types to
        # a geodatabase feature class, geopackage table, geoservices json, or 
        # geojson), load it into a Python representation of that data in a 
        # geo-format (e.g., geojson or geoservices json (Esri)), ETL the table
        # else:
        points, points_features, points_spatial_ref_code = self.gp.create_drainitpoints_from_geodata(
            points_filepath=self.config.points_filepath,
            uid_field=self.config.points_id_fieldname,
            group_id_field=self.config.points_group_fieldname,
            is_naacc=True,
            # output_points_filepath=self.config.output_points_filepath
        )
        
        # save those to the config
        # ...as a list of Drain-It Point objects:
        self.config.points = points
        # ...as the geo/json (GeoJSON or Geoservices JSON depending on the GP module used)
        self.config.points_features = points_features
        # the spatial ref of the points
        self.config.points_spatial_ref_code = points_spatial_ref_code

        return self.config.points, self.config.points_features
    
    def _analyze_all_points(self):
        
        # filter out points that we can't analyze
        points_to_analyze: List[DrainItPoint] = [
            pt for pt in self.config.points if pt.include
        ]
        self.gp.msg("--------------------------------")
        self.gp.msg(f"analyzing {len(points_to_analyze)} points...")

        # ----------------------------------------------------------------------
        # ANALYZE all points individually

        for pt in tqdm(points_to_analyze, desc="analyzing points"):
        

            # print(pt.uid, pt.group_id)

            # Copy rainfall intervals from point.shed to point.analytics list.
            # This is object is used for peak-flow and overflow calculations per
            # rainfall frequency.
            pt.derive_rainfall_analytics()

            # ------------------
            # CAPACITY
            # Set crossing capacity equal to culvert capacity
            # (later we re-evaluate if the point is part of a multi-culvert crossing)
            pt.capacity.crossing_capacity = pt.capacity.culvert_capacity

            # ------------------
            # PEAK FLOW
            # calculate time of concentration for the point's shed
            pt.shed.calculate_tc()
            # for each rainfall frequency
            for freq in pt.analytics:
                # print("freq", freq.frequency)
                # instantiate a Runoff dataclass within 
                freq.peakflow = runoff.Runoff()
                # add in the tc that has already been calculated for the shed
                freq.peakflow.time_of_concentration_hr = pt.shed.tc_hr
                # calculate peak flow
                freq.peakflow.calculate_peak_flow(
                    mean_slope_pct=pt.shed.avg_slope_pct,
                    max_flow_length_m=pt.shed.max_fl,
                    avg_rainfall_cm=freq.avg_rainfall_cm,
                    basin_area_sqkm=pt.shed.area_sqkm,
                    avg_cn=pt.shed.avg_cn,
                    tc_hr=pt.shed.tc_hr
                )

                # assign culvert peak-flow for the crossing as well
                # (later we'll calc/reassign if it's part of a multi-culvert crossing)
                freq.peakflow.crossing_peakflow_m3s = freq.peakflow.culvert_peakflow_m3s
                
                # OVERFLOW
                # instantiate the Overflow dataclass
                freq.overflow = overflow.Overflow()
                # if capacity was calculated, calculate overflow
                if all([
                    pt.capacity.culvert_capacity is not None,
                    freq.peakflow.culvert_peakflow_m3s is not None
                ]):
                    # calculate overflow at the single culvert
                    freq.overflow.calculate_overflow(
                        culvert_capacity=pt.capacity.culvert_capacity,
                        peak_flow=freq.peakflow.culvert_peakflow_m3s
                    )
                    
                    # assign culvert overflow for the crossing as well.
                    # (later we'll calc/reassign if it's part of a multi-crossing)
                    freq.overflow.crossing_overflow_m3s = freq.overflow.culvert_overflow_m3s

        
        # ----------------------------------------------------------------------
        # create a list of group_ids for the multi-culvert crossings
        multiculvert_crossing_group_ids = [
            group_id for group_id, count in 
            Counter([pt.group_id for pt in points_to_analyze]).items()
            if count > 1
        ]

        # iterate through the group_ids, getting matching records from the table
        # and running calculations
        for mcc in tqdm(multiculvert_crossing_group_ids, desc="analyzing multi-culvert crossings"):

            # get list of points with the same group id:
            crossing_pts: List[DrainItPoint] = list(filter(lambda pt: pt.group_id == mcc, points_to_analyze))
            
            # CROSSING CAPACITY
            # sum culvert capacity to get crossing capacity
            crossing_capacity = sum([pt.capacity.culvert_capacity for pt in crossing_pts if pt.capacity.culvert_capacity is not None])
            
            # CROSSING PEAK FLOW and OVERFLOW
            # Calculate overflow (peak flow - crossing capacity)

            # use the peak flow from the point with the largest shed (or secondarily, the longest flow length)
            ref_xing_peakflow_point: DrainItPoint = sorted(crossing_pts, key=lambda pt: (pt.shed.area_sqkm, pt.shed.max_fl))[-1]

            # for each point in the crossing
            for each_xing in crossing_pts:
                # (re)assign crossing capacity to all points in the crossing
                each_xing.capacity.crossing_capacity = crossing_capacity

                # for each of the rainfall analytics items in the crossing point
                for xing_ra_item in each_xing.analytics:
                    # get the matching rainall analytics item from crossing point by frequency
                    for ref_xing_point_ra_item in filter(lambda a: a.frequency == xing_ra_item.frequency, ref_xing_peakflow_point.analytics):
                        # (re)assign the reference point's peak flow to the point's crossing peakflow
                        xing_ra_item.peakflow.crossing_peakflow_m3s = ref_xing_point_ra_item.peakflow.culvert_peakflow_m3s
                        # calculate and (re)assign crossing overflow
                        xing_ra_item.overflow.crossing_overflow_m3s = overflow.culvert_overflow_calculator(
                            each_xing.capacity.crossing_capacity, xing_ra_item.peakflow.crossing_peakflow_m3s
                        )

        # ----------------------------------------------------------------------
        # finally, calculate summary analytics (those that derive stats from
        # multiple attributes) on each point

        for pt in tqdm(self.config.points, desc="calculating summary analytics"):
            pt.calculate_summary_analytics()

    def _export_culvert_featureclass(self) -> etl.Table:

        # import and unpack the data structure
        t = etl\
            .fromdicts([DrainItPointSchema(partial=True).dump(pt) for pt in self.config.points])\
            .addrownumbers(field='oid')\
            .cutout(*['naacc', 'raw', 'notes'])\
            .convert('validation_errors', lambda d: "; ".join(['{0} ({1})'.format(k, ",".join([i for i in v])) for k,v in d.items()]))\
            .unpackdict('capacity', keys=list(self.capacity_field_map.keys()))\
            .unpackdict('shed', keys=list(self.shed_field_map.keys()))\
            .rename(self.shed_field_map)\
            .unpack('analytics', self.frequency_fields)

        # unpack the rainfall frequency-based analytics
        t2 = deepcopy(t)

        for ff in self.frequency_fields:
            analytics_table = etl\
                .cut(t2, ['oid', ff])\
                .convert(ff, lambda d: dict(**d['overflow'], **d['peakflow']))\
                .unpackdict(ff, list(self.analytics_field_map.keys()))\
                .prefixheader(f'{ff}_')\
                .rename(f'{ff}_oid', 'oid')
            t2 = etl.join(t2, analytics_table, 'oid')
            
        # clean-up fields
        t3 = etl.cutout(t2, *self.frequency_fields)
        
        # create a feature class from the table
        self.gp.msg(f"saving output points to {self.config.output_points_filepath}")
        self.gp.create_geodata_from_petl_table(
            petl_table=t3, 
            x_column='lng', 
            y_column='lat', 
            output_featureclass=self.config.output_points_filepath,
            crs_wkid=self.config.points_spatial_ref_code
        )
        
        return t3

    def run(self):

        # load points
        # with NAACC data, capacity is calculated on load
        self.load_points() # updates self.config.points and self.config.points_features

        if len(self.config.points) == 0:
            click.echo("WARNING: No points to delineate from or analyze. CulvertCapacity terminating.")
            return

        # delineate and analyze catchments for each point
        self.config.points = self.gp.delineation_and_analysis_in_parallel(
            points=self.config.points,
            pour_point_field=self.config.points_id_fieldname,
            flow_direction_raster=self.config.raster_flowdir_filepath,
            slope_raster=self.config.raster_slope_filepath,
            flow_length_raster=self.config.raster_flowlen_filepath,
            curve_number_raster=self.config.raster_curvenumber_filepath,
            precip_src_config=RainfallRasterConfigSchema().dump(self.config.precip_src_config),
            out_shed_polygons=self.config.output_sheds_filepath,
            out_shed_polygons_simplify=self.config.sheds_simplify,
            override_skip=False, # will run regardless of validation,
            use_multiprocessing=self.use_multiprocessing
        )

        # assigns values to associated crossings and calculates peakflow vs capacity
        self._analyze_all_points()
        
        # exports the result as a feature class, where each feature is a culvert
        culvert_table = self._export_culvert_featureclass()
        # saves that feature class to the config
        self.config.points_features = self.gp.create_dicts_from_geodata(self.config.output_points_filepath)
        # TODO: export a feature class rolled up to crossings.
        # self._export_crossing_feature_class(culvert_table)

        # save the config
        if self.save_config_json_filepath:
            self.save_config(self.save_config_json_filepath)

        return


'''
* Derived analytical outputs
  * field that indicates which storm the  Max Return Period (yr) (it's design) ~~culvert fails on~~
  * layer showing peak flow (size) vs overflow (color)
  * simple tabular summary output for which ones go over
  * flow vs area vs capacity/overflow, to identify risks
* Two point outputs
  * One output with 1:1 between input culvert and output culvert records.
  * One output that is crossing-based: one point per crossing.
'''