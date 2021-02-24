'''
_esri.py

geoprocessing tasks with Esri Arcpy

'''
# standard library
from drainit.services.naacc import etl_naacc_table
import os, time
from collections import defaultdict
from pathlib import Path
from types import List, Tuple
import json

# ArcPy imports
from arcpy import Describe, Raster, CreateUniqueName
from arcpy import GetCount_management, Clip_management, Dissolve_management, CopyFeatures_management, CreateFeatureclass_management, AddFields_management
from arcpy import JoinField_management, MakeTableView_management
from arcpy import BuildRasterAttributeTable_management, ProjectRaster_management
from arcpy import RasterToPolygon_conversion, TableToTable_conversion, PolygonToRaster_conversion
from arcpy import FeatureSet
from arcpy.sa import Watershed, FlowLength, Slope, SetNull, ZonalStatisticsAsTable, FlowDirection, Con, CellStatistics #, ZonalGeometryAsTable
from arcpy.da import SearchCursor, InsertCursor
from arcpy import SetProgressor, SetProgressorLabel, SetProgressorPosition, ResetProgressor
from arcpy import AddMessage, AddWarning, AddError
from arcpy import env

# third party tools
import petl as etl
import pint
import click

# this package
from ...config import FREQUENCIES, QP_HEADER
from ...models import WorkflowConfig, Shed, Point, NaaccCulvert
# from ..naacc import etl_naacc_table

class GP:

    def __init__(self):#, workflow_config: WorkflowConfig):

        self.raster_field = "Value"
        self.all_sheds_raster = ""
        self.sheds = []

    # --------------------------------------------------------------------------
    # HELPERS

    def msg(self, text, arc_status=None, set_progressor_label=False):
        """
        output messages through Click.echo (cross-platform shell printing) 
        and the ArcPy GP messaging interface and progress bars
        """
        click.echo(text)

        if arc_status == "warning":
            AddWarning(text)
        elif arc_status == "error":
            AddError(text)
        else:
            AddMessage(text)
        
        if set_progressor_label:
            SetProgressorLabel(text)

    def so(self, prefix, suffix="random", where="fgdb"):
        """complete path generator for Scratch Output (for use with ArcPy GP tools)

        Generates a string represnting a complete and unique file path, which is
        useful to have for setting as the output parameters for ArcPy functions,
        especially those for intermediate data.

        Inputs:
            prefix: a string for a temporary file name, prepended to suffix
            suffix: unique value type that will be used to make the name unique:
                "unique": filename using arcpy.CreateUniqueName(),
                "timestamp": uses local time,
                "random": randomness plus hash of local time
                "<user string>": any other value provided will be used directly
            where: a string that dictates which available workspace will be
                utilized:
                "fgdb": ArcGIS scratch file geodatabase. this is the default
                "folder": ArcGIS scratch file folder. use sparingly
                "in_memory": the ArcGIS in-memory workspace. good for big
                    datasets, but not too big. only set to this for intermediate
                    data, as the workspace is not persistent.
                "<user string>": any other value provided that is an existing Path
                will be used as the save location; fallback is `fgdb`
                    
        Returns:
            A string representing a complete and unique file path.

        """
        
        # set workspace location
        if where == "in_memory":
            location = "in_memory"
        elif where == "fgdb":
            location = Path(env.scratchGDB)
        elif where == "folder":
            location = Path(env.scratchFolder)
        else:
            loc = Path(where)
            if loc.exists():
                location = loc
            else:
                location = Path(env.scratchGDB)
        
        # create and return full path
        if suffix == "unique":
            return CreateUniqueName(prefix, str(location))
        elif suffix == "random":
            return str(
                location / "{0}_{1}".format(
                    prefix,
                    abs(hash(time.strftime("%Y%m%d%H%M%S", time.localtime())))
                )
            )
        elif suffix == "timestamp":
            return str(
                location /
                "{0}_{1}".format(
                    prefix,
                    time.strftime("%Y%m%d%H%M%S", time.localtime())
                )
            )
        else:
            return str(location / "_".join([prefix, suffix]))

    def clean(self, val):
        """post-process empty values ("") from ArcPy geoprocessing tools.
        """
        if val in ["", None]:
            return 0
        else:
            return val

    def csv_to_fgdb_table(self, csv):
        """loads a csv into the ArcMap scratch geodatabase. Use for temporary files only.
        Output: path to the imported csv
        """
        t = self.so("csv","random","fgdb")
        TableToTable_conversion(
            in_rows=csv, 
            out_path=os.path.dirname(t), 
            out_name=os.path.basename(t)
        )
        return t

    def fc_to_csv(self, feature_class, out_csv):
        """Convert an Esri Feature Class to a CSV file.

        Convert an Esri Feature Class to a CSV file. Requires ArcPy.

        :param feature_class: path to feature class (file geodatabase or shapefile) on disk
        :type feature_class: str
        :param out_csv: path to output csv
        :type out_csv: str
        :return: path to output csv
        :rtype: str
        """

        p = Path(out_csv)
        self.msg("Converting feature class @ {0} to CSV table @ {1}".format(feature_class, out_csv))
        TableToTable_conversion(feature_class, str(p.parent), str(p.name))

        return out_csv

    def fc_to_petl_table(
        self, 
        feature_class, 
        include_geom=False,
        return_featureset=False
        ):
        """Convert an Esri Feature Class to a PETL table object. Optionally,
        return the FeatureSet used to create the PETL table.

        Convert an Esri Feature Class to a PETL table object.

        :param feature_class: [description]
        :type feature_class: [type]
        :param include_geom: [description], defaults to False
        :param include_geom: bool, optional
        :return: PETL Table object
        :rtype: petl.Table
        """
        self.msg("Reading {0} into a PETL table object".format(feature_class))
        # describe the feature class
        described_fc = Describe(feature_class)
        # get a list of field objects
        field_objs = described_fc.fields

        # make a list of field names, excluding geometry and the OID field
        if include_geom:
            self.msg("Including geometry column.")
            fields = [field.name for field in field_objs]
        else:
            self.msg("Excluding geometry column.")
            fields = [field.name for field in field_objs if field.type not in ['Geometry', 'Shape']]

        # Remove the object ID field. We don't have any need for it here.
        if described_fc.hasOID:
            fields = [f for f in fields if f != described_fc.OIDFieldName]

        # generate a table from the features list of a FeatureSet
        feature_set = FeatureSet(feature_class)
        fs = json.loads(feature_set.JSON)

        table = etl\
            .fromdicts(fs['features'])\
            .unpackdict('attributes')\
            .cut(*fields)
            

        # # use ArcPy's search cursor to generate new rows
        # with SearchCursor(feature_class, fields) as sc:
        #     for row in sc:
        #         # w/ the field list and the row values returned by the search
        #         # cursor, create a list of tuples: [(field-name, value), ...]
        #         z = list(zip(fields, list(row)))
        #         # turn each of those into a dict
        #         new_row = {k: v for k, v in z}
        #         # ... and append that to our list
        #         new_rows.append(new_row)

        # return that list as a PETL table object
        # return etl.fromdicts(new_rows)

        if return_featureset:
            return table, feature_set
        else:
            return table

    def join_to_copy(self, in_data, out_data, join_table, in_field, join_field):
        """given an input feature class, make a copy, then execute a join on that copy.
        Return the copy.
        """
        self.msg(in_data)
        self.msg(out_data)
        self.msg(join_table)
        self.msg(in_field)
        self.msg(join_field)
        # copy the inlets file
        CopyFeatures_management(
            in_features=in_data, 
            out_feature_class=out_data
        )
        # join the table to the copied file
        JoinField_management(
            in_data=out_data, 
            in_field=in_field, 
            join_table=join_table, 
            join_field=join_field
        )
        return out_data


    # --------------------------------------------------------------------------
    # GEOPROCESSING 

    def prep_cn_raster(self, 
        dem,
        curve_number_raster,
        out_cn_raster=None,
        out_coor_system="PROJCS['NAD_1983_StatePlane_Pennsylvania_South_FIPS_3702_Feet',GEOGCS['GCS_North_American_1983',DATUM['D_North_American_1983',SPHEROID['GRS_1980',6378137.0,298.257222101]],PRIMEM['Greenwich',0.0],UNIT['Degree',0.0174532925199433]],PROJECTION['Lambert_Conformal_Conic'],PARAMETER['False_Easting',1968500.0],PARAMETER['False_Northing',0.0],PARAMETER['Central_Meridian',-77.75],PARAMETER['Standard_Parallel_1',39.93333333333333],PARAMETER['Standard_Parallel_2',40.96666666666667],PARAMETER['Latitude_Of_Origin',39.33333333333334],UNIT['Foot_US',0.3048006096012192]]"
        ):
        """
        Clip, reproject, and resample the curve number raster to match the DEM.
        Ensure everything utilizes the DEM as the snap raster.
        The result is returned in a dictionary referencing an ArcPy Raster object
        for the file gdb location of the processed curve number raster.
        
        For any given study area, this will only need to be run once.
        """
        
        # make the DEM an ArcPy Raster object, so we can get the raster properties
        if not isinstance(dem,Raster):
            dem = Raster(dem)
        
        self.msg("Clipping...")
        # clip the curve number raster, since it is likely for a broader study area
        clipped_cn = self.so("cn_clipped")
        Clip_management(
            in_raster=curve_number_raster,
            out_raster=clipped_cn,
            in_template_dataset=dem,
            clipping_geometry="NONE",
            maintain_clipping_extent="NO_MAINTAIN_EXTENT"
        )
        
        # set the snap raster for subsequent operations
        env.snapRaster = dem
        
        # reproject and resample he curve number raster to match the dem
        if not out_cn_raster:
            prepped_cn = self.so("cn_prepped")
        else:
            prepped_cn = out_cn_raster
        self.msg("Projecting and Resampling...")
        ProjectRaster_management(
            in_raster=clipped_cn,
            out_raster=prepped_cn,
            out_coor_system=out_coor_system,
            resampling_type="NEAREST",
            cell_size=dem.meanCellWidth
        )
        
        return {
            "curve_number_raster": Raster(prepped_cn)
        } 

    def build_cn_raster(self, 
        landcover_raster,
        lookup_csv,
        soils_polygon,
        soils_hydrogroup_field="SOIL_HYDRO",
        reference_raster=None,
        out_cn_raster=None
        ):
        """Build a curve number raster from landcover raster, soils polygon, and a crosswalk between 
        landcover classes, soil hydro groups, and curve numbers.

        :param lookup_csv: [description]
        :type lookup_csv: [type]
        :param landcover_raster: [description]
        :type landcover_raster: [type]
        :param soils_polygon: polygon containing soils with a hydro classification. 
        :type soils_polygon: [type]
        :param soils_hydrogroup_field: [description], defaults to "SOIL_HYDRO" (from the NCRS soils dataset)
        :type soils_hydrogroup_field: str, optional
        :param out_cn_raster: [description]
        :type out_cn_raster: [type]    
        """

        # GP Environment ----------------------------
        self.msg("Setting up GP Environment...")
        # if reference_raster is provided, we use it to set the GP environment for 
        # subsequent raster operations
        if reference_raster: 
            if not isinstance(reference_raster,Raster):
                # read in the reference raster as a Raster object.
                reference_raster = Raster(reference_raster)
        else:
            reference_raster = Raster(landcover_raster)

        # set the snap raster, cell size, and extent, and coordinate system for subsequent operations
        env.snapRaster = reference_raster
        env.cellSize = reference_raster.meanCellWidth
        env.extent = reference_raster
        env.outputCoordinateSystem = reference_raster
        
        cs = env.outputCoordinateSystem.exportToString()

        # SOILS -------------------------------------
        
        self.msg("Processing Soils...")
        # read the soils polygon into a raster, get list(set()) of all cell values from the landcover raster
        soils_raster_path = self.so("soils_raster")
        PolygonToRaster_conversion(soils_polygon, soils_hydrogroup_field, soils_raster_path, "CELL_CENTER")
        soils_raster = Raster(soils_raster_path)

        # use the raster attribute table to build a lookup of raster values to soil hydro codes
        # from the polygon (that were stored in the raster attribute table after conversion)
        if not soils_raster.hasRAT:
            self.msg("Soils raster does not have an attribute table. Building...", "warning")
            BuildRasterAttributeTable_management(soils_raster, "Overwrite")
        # build a 2D array from the RAT
        fields = ["Value", soils_hydrogroup_field]
        rows = [fields]
        # soils_raster_table = MakeTableView_management(soils_raster_path)
        with SearchCursor(soils_raster_path, fields) as sc:
            for row in sc:
                rows.append([row[0], row[1]])
        # turn that into a dictionary, where the key==soil hydro text and value==the raster cell value
        lookup_from_soils = {v: k for k, v in etl.records(rows)}
        # also capture a list of just the values, used to iterate conditionals later
        soil_values = [v['Value'] for v in etl.records(rows)]

        # LANDCOVER ---------------------------------
        self.msg("Processing Landcover...")
        if not isinstance(landcover_raster, Raster):
            # read in the reference raster as a Raster object.
            landcover_raster = Raster(landcover_raster)
        landcover_values = []
        with SearchCursor(landcover_raster, ["Value"]) as sc:
            for row in sc:
                landcover_values.append(row[0])

        # LOOKUP TABLE ------------------------------
        self.msg("Processing Lookup Table...")
        # read the lookup csv, clean it up, and use the lookups from above to limit it to just
        # those values in the rasters
        t = etl\
            .fromcsv(lookup_csv)\
            .convert('utc', int)\
            .convert('cn', int)\
            .select('soil', lambda v: v in lookup_from_soils.keys())\
            .convert('soil', lookup_from_soils)\
            .select('utc', lambda v: v in landcover_values)
        
        # This gets us a table where we the landcover class (as a number) corresponding to the 
        # correct value in the converted soil raster, with the corresponding curve number.

        # DETERMINE CURVE NUMBERS -------------------
        self.msg("Assigning Curve Numbers...")
        # Use that to reassign cell values using conditional map algebra operations
        cn_rasters = []
        for rec in etl.records(t):
            cn_raster_component = Con((landcover_raster == rec.utc) & (soils_raster == rec.soil), rec.cn, 0)
            cn_rasters.append(cn_raster_component)

        cn_raster = CellStatistics(cn_rasters, "MAXIMUM")

        # REPROJECT THE RESULTS -------------------
        self.msg("Reprojecting and saving the results....")
        if not out_cn_raster:
            out_cn_raster = self.so("cn_raster","random","fgdb")

        ProjectRaster_management(
            in_raster=cn_raster,
            out_raster=out_cn_raster,
            out_coor_system=cs,
            resampling_type="NEAREST",
            cell_size=env.cellSize
        )
        
        # cn_raster.save(out_cn_raster)
        return out_cn_raster

    def derive_from_dem(self, dem, force_flow="NORMAL"):
        """derive slope and flow direction from a DEM.
        Results are returned in a dictionary that contains references to
        ArcPy Raster objects stored in the "fgdb" (temporary) workspace

        Returns:
            {
                "flow_direction_raster": Raster(flow_direction_raster),
                "slope_raster": Raster(slope_raster),
            }

        """
        from arcpy import env
        
        # set the snap raster for subsequent operations
        env.snapRaster = dem
        
        # calculate flow direction for the whole DEM
        flow_direction_raster = self.so("flowdir","random","fgdb")
        flowdir = FlowDirection(in_surface_raster=dem, force_flow=force_flow)
        flowdir.save(flow_direction_raster)
        
        # calculate slope for the whole DEM
        slope = Slope(in_raster=dem, output_measurement="PERCENT_RISE", method="PLANAR")
        slope_raster = self.so("slope","random","fgdb")
        slope.save(slope_raster)

        return {
            "flow_direction_raster": flow_direction_raster,
            "slope_raster": slope_raster,
        }


    # --------------------------------------------------------------------------
    # Analytics


    def _catchment_delineation(
        self, 
        inlets, 
        flow_direction_raster, 
        pour_point_field, 
        series=True
    ):
        """Delineate the catchment area(s) for the inlet(s), and provide a count.

        :param inlets: path to point shapefile or feature class representing inlet location(s) from which catchment area(s) will be determined. Can be one or many inlets.
        :type inlets: str
        :param flow_direction_raster: [description]
        :type flow_direction_raster: [type]
        :param pour_point_field: [description]
        :type pour_point_field: [type]
        :param series: determines if watersheds be delineated to represent flow in series (i.e., no overlap; the default) or not (downstream catchments include upstream catchments). defaults to True (no overlap)
        :type series: bool, optional
        :return: a python dictionary structured as follows: 
            {
                "catchments": <path to the catchments raster created by the Arcpy.sa Watershed function>,
                "count": <count (int) of the number of inlets/catchments>
            }
        :rtype: dict
        """

        if series:

            # ------------------------------------------------------------------
            # delineation

            # delineate the watershed(s) for all the inlets simultaneously. The 
            # resulting basins will have no overlap. 
            all_sheds = Watershed(
                in_flow_direction_raster=flow_direction_raster,
                in_pour_point_data=inlets,
                pour_point_field=pour_point_field
            )

            if not all_sheds.hasRAT:
                BuildRasterAttributeTable_management(all_sheds, "Overwrite")

            # save the catchment raster
            self.all_sheds_raster = self.so("catchments","timestamp","fgdb")
            all_sheds.save(self.all_sheds_raster)
            self.msg("Catchments raster saved:\n\t{0}".format(self.config.all_sheds_raster))

            # ------------------------------------------------------------------
            # Create individual watershed rasters

            # # make a table view of the catchment raster
            # catchment_table = 'catchment_table'
            # MakeTableView_management(all_sheds, catchment_table) #, {where_clause}, {workspace}, {field_info})

            # # for each catchment in the raster
            # with SearchCursor(catchment_table, [self.raster_field]) as all_sheds:
            #     for idx, each in enumerate(all_sheds):
            #         this_id = each[0]
            #         # self.msg("{0}".format(this_id))
            #         # calculate flow length for each "zone" in the raster

        # for the non-series (parallel?) approach, approp. for culvert modeling, 
        # calculate every basin individually. The resulting basins may overlap.
        else:
            with SearchCursor(inlets, [pour_point_field]) as sc:
                for inlet in sc:

                    # ------------------------------------------------------------------
                    # delineation
                    
                    one_shed = Watershed(
                        in_flow_direction_raster=flow_direction_raster,
                        in_pour_point_data=inlet,
                        pour_point_field=pour_point_field
                    )
                    # save the catchments layer to the fgdb set by the arcpy.env.scratchgdb setting)
                    catchment_save = self.so("catchment{0}".format(inlet[0]),"timestamp","fgdb")
                    one_shed.save(catchment_save)
                    self.msg("...catchment raster saved:\n\t{0}".format(catchment_save))
                    self.sheds.append(
                        Shed()
                    )
                    # get count of how many watersheds we should have gotten (# of inlets)
                    # count = int(GetCount_management(inlets).getOutput(0))

            return

    def _calc_catchment_flowlength_max(self, 
        catchment_area_raster,
        zone_value,
        flow_direction_raster,
        leng_conv_factor=1 #???
        ):
        
        """
        Derives flow length for a *single catchment area using a provided zone
        value (the "Value" column of the catchment_area_raster's attr table).
        
        Inputs:
            catchment_area: *raster* representing the catchment area(s)
            zone_value: an integer from the "Value" column of the
                catchment_area_raster's attr table.
            flow_direction_raster: flow direction raster for the broader
        outputs:
            returns the 
        """
        # use watershed raster to clip flow_direction, slope rasters
        # make a raster object with the catchment_area_raster raster
        if not isinstance(catchment_area_raster, Raster):
            c = Raster(catchment_area_raster)
        else:
            c = catchment_area_raster    
        # clip the flow direction raster to the catchment area (zone value)
        fd = SetNull(c != zone_value, flow_direction_raster)
        # calculate flow length
        fl = FlowLength(fd,"UPSTREAM")
        # determine maximum flow length
        fl_max = fl.maximum 
        #TODO: convert length to ? using leng_conv_factor (detected from the flow direction raster)
        fl_max = fl_max * leng_conv_factor
            
        return fl_max

    def _derive_data_for_all_catchments(self, 
        catchment_areas,
        flow_direction_raster,
        slope_raster,
        curve_number_raster,
        area_conv_factor=0.00000009290304,
        leng_conv_factor=1,
        out_catchment_polygons=None,
        precip_table=None,
        precip_raster_lookup=None,
        out_catchment_polygons_simplify=False
        ):
        """Generates statistics for all catchments using spatially-based 
        characteristics.

        :param catchment_areas: [description]
        :type catchment_areas: [type]
        :param flow_direction_raster: [description]
        :type flow_direction_raster: [type]
        :param slope_raster: [description]
        :type slope_raster: [type]
        :param curve_number_raster: [description]
        :type curve_number_raster: [type]
        :param area_conv_factor: for converting the area of the catchments to Sq. Km, which is expected by the core business logic. By default, the factor converts from square feet , defaults to 0.00000009290304
        :type area_conv_factor: float, optional
        :param leng_conv_factor: [description], defaults to 1
        :type leng_conv_factor: int, optional
        :param out_catchment_polygons: will optionally return a catchment polygon feature class, defaults to None
        :type out_catchment_polygons: [type], optional
        :param precip_table: [description], defaults to None
        :type precip_table: dict, optional
        :param precip_raster_lookup: [description], defaults to None
        :type precip_raster_lookup: dict, optional,
        :param out_catchment_polygons_simplify: [description], defaults to None
        :type out_catchment_polygons_simplify: bool, optional    
        :return: [description]
        :rtype: [type]

        Output: an array of records containing info about each inlet's catchment, e.g.:
            [
                {
                    "id": <ID value from pour_point_field (spec'd in catchment_delineation func)> 
                    "area_sqkm": <area of inlet's catchment in square km>
                    "avg_slope": <average slope of DEM in catchment>
                    "avg_cn": <average curve number in the catchment>
                    "max_fl": <maximum flow length in the catchment>
                    "precip_table": <catchment-specific precipitation estimates>
                },
                {...},
                ...
            ]

        NOTE: For tools that handle multiple inputs quickly, we execute here (e.g., zonal
        stats). For those we need to run on individual catchments, this parses the
        catchments raster and passes individual catchments, along with other required 
        data, to the calc_catchment_flowlength_max function.

        """

        # store the results, keyed by a catchment ID (int) that comes from the
        # catchments layer gridcode
        results = defaultdict(dict)
        
        # ------------------------------------------------------------------------
        # CATCHMENTS 

        # make a raster object with the catchment raster
        if not isinstance(catchment_areas,Raster):
            c = Raster(catchment_areas)
        else:
            c = catchment_areas
        # if the catchment raster does not have an attribute table, build one
        if not c.hasRAT:
            BuildRasterAttributeTable_management(c, "Overwrite")

        # make a table view of the catchment raster
        catchment_table = 'catchment_table'
        MakeTableView_management(c, catchment_table) #, {where_clause}, {workspace}, {field_info})

        # ------------------------------------------------------------------------
        # FLOW LENGTH
        # calculate flow length for each zone. Zones must be isolated as individual
        # rasters for this to work. We handle that with calc_catchment_flowlength_max()
        # using the table to get the zone values

        catchment_count = int(GetCount_management(catchment_table).getOutput(0))
        with SearchCursor(catchment_table, [self.raster_field]) as catchments:

            # TODO: implement multi-processing for this loop.
            
            ResetProgressor()
            SetProgressor('step', "Mapping flow length for catchments", 0, catchment_count, 1)
            # self.msg("Mapping flow length for catchments")

            for idx, each in enumerate(catchments):
                this_id = each[0]
                # self.msg("{0}".format(this_id))
                # calculate flow length for each "zone" in the raster
                fl_max = self._calc_catchment_flowlength_max(
                    catchment_areas,
                    this_id,
                    flow_direction_raster,
                    leng_conv_factor
                )
                results[this_id]["max_fl"] = self.clean(fl_max)
                # if this_id in results.keys():
                #     results[this_id]["max_fl"] = self.clean(fl_max)
                # else:
                #     results[this_id] = {"max_fl": self.clean(fl_max)}
                SetProgressorPosition(idx+1)
            ResetProgressor()

        # ------------------------------------------------------------------------
        # AVERAGE RAINFALL (FROM RAINFALL RASTERS, IF PROVIDED)

        # calculate average rainfall within each catchment for all catchments,
        # but only if this parameter was provided:
        if precip_raster_lookup:

            for p, path_to_rainfall_raster in precip_raster_lookup.items():

                # calculate average curve number within each catchment for all catchments
                table_rainfall_avg = self.so("rainfall_avg", p, "fgdb")
                self.msg("Average Rainfall Table: {0}".format(table_rainfall_avg))
                ZonalStatisticsAsTable(
                    catchment_areas, 
                    self.raster_field, 
                    path_to_rainfall_raster, 
                    table_rainfall_avg, 
                    "DATA", "MEAN"
                )
                # push table into results object
                with SearchCursor(table_rainfall_avg, [self.raster_field,"MEAN"]) as c:
                    for r in c:
                        this_id = r[0]
                        this_val= r[1]
                        results[this_id]['rainfall'][p] = self.clean(this_val)
        elif precip_table:
            # TODO: allow fall-back to a NOAA precip table here
            # For now, this won't work.
            for h in QP_HEADER:
                results[this_id][h]['rainfall'] = {}
        else:
            for h in QP_HEADER:
                results[this_id][h]['rainfall'] = {}

        # ------------------------------------------------------------------------
        # AVERAGE CURVE NUMBER

        # calculate average curve number within each catchment for all catchments
        table_cns = self.so("cn_zs_table","timestamp","fgdb")
        self.msg("CN Table: {0}".format(table_cns))
        ZonalStatisticsAsTable(catchment_areas, self.raster_field, curve_number_raster, table_cns, "DATA", "MEAN")
        # push table into results object
        with SearchCursor(table_cns,[self.raster_field,"MEAN"]) as c:
            for r in c:
                this_id = r[0]
                this_val = r[1]
                results[this_id]["avg_cn"] = self.clean(this_val)
                # if this_id in results.keys():
                #     results[this_id]["avg_cn"] = self.clean(this_area)
                # else:
                #     results[this_id] = {"avg_cn": self.clean(this_area)}

        # ------------------------------------------------------------------------
        # AVERAGE SLOPE
        # calculate average slope within each catchment for all catchments

        if slope_raster:

            table_slopes = self.so("slopes_zs_table","timestamp","fgdb")
            self.msg("Slopes Table: {0}".format(table_slopes))
            ZonalStatisticsAsTable(catchment_areas, self.raster_field, slope_raster, table_slopes, "DATA", "MEAN")
            # push table into results object
            with SearchCursor(table_slopes,[self.raster_field,"MEAN"]) as c:
                for r in c:
                    this_id = r[0]
                    this_val = r[1]
                    results[this_id]["avg_slope"] = self.clean(this_val)
                    # if this_id in results.keys():
                    #     results[this_id]["avg_slope"] = self.clean(this_area)
                    # else:
                    #     results[this_id] = {"avg_slope": self.clean(this_area)}
        # if the slope raster was not provided, we fall-back to a simplified 
        # calculation: catchment_max_elevation - catchment_min_elevation) / max_flow_length
        else: 
            table_slopes_alt = self.so("slopes_zs_table","timestamp","fgdb")
            self.msg("Slopes Table (Alternate Method): {0}".format(table_slopes_alt))
            ZonalStatisticsAsTable(catchment_areas, self.raster_field, slope_raster, table_slopes_alt, "DATA", "MEAN")
            # push table into results object
            with SearchCursor(table_slopes_alt, [self.raster_field,"MEAN"]) as c:
                for r in c:
                    this_id = r[0]
                    this_val = r[1]
                    results[this_id]["avg_slope"] = self.clean(this_val)        

            
        # ------------------------------------------------------------------------
        # AREA

        # calculate area of each catchment
        #ZonalGeometryAsTable(catchment_areas,"Value","output_table") # crashes like a mfer
        cp = self.so("catchmentpolygons","timestamp","fgdb")
        #RasterToPolygon copies our ids from self.raster_field into "gridcode"
        if out_catchment_polygons_simplify:
            simplify = "SIMPLIFY"
        else:
            simplify = "NO_SIMPLIFY"
        RasterToPolygon_conversion(catchment_areas, cp, simplify, self.raster_field)

        # Dissolve the converted polygons, since some of the raster zones may have corner-corner links
        if not out_catchment_polygons:
            cpd = self.so("catchmentpolygonsdissolved","timestamp","fgdb")
        else:
            cpd = out_catchment_polygons
        Dissolve_management(
            in_features=cp,
            out_feature_class=cpd,
            dissolve_field="gridcode",
            multi_part="MULTI_PART"
        )

        # get the area for each record, and push into results object
        with SearchCursor(cpd,["gridcode","SHAPE@AREA"]) as c:
            for r in c:
                this_id = r[0]
                this_area = r[1] * area_conv_factor
                if this_id in results.keys():
                    results[this_id]["area_up"] = self.clean(this_area)
                else:
                    results[this_id] = {"area_up": self.clean(this_area)}
        
        # flip results object into a records-style array of dictionaries
        # (this makes conversion to table later on simpler)
        # self.msg(results,"warning")
        records = []
        for k in results.keys():
            record = {
                "area_up":0,
                "avg_slope":0,
                "max_fl":0,
                "avg_cn":0,
                "tc_hr":0,
                "rainfall": {}
            }
            for each_result in record.keys():
                if each_result in results[k].keys():
                    record[each_result] = results[k][each_result]
            record["id"] = k
            records.append(record)
        
        if out_catchment_polygons:
            return records, cpd
        else:
            return records, None

    
    # def calc_average_rainfall(self, catchment_area_raster, zone_value, rainfall_rasters=[]):
    #     return

    # --------------------------------------------------------------------------
    # Wrappers
    # Passes Workflow Config to the Analytics functions with GP environment set

    def create_geodata_from_points(
        self, 
        points: List[Point], 
        output_points_filepath=None
        ) -> FeatureSet:
        """from a list of Drain-It Point objects, create an ArcPy FeatureSet,
        for use in other ArcPy GP tools.

        :param points: list of drainit.models.Point objects. Only the uid and group_id are used here; extended attributes from naacc aren't used.
        :type points: List[Point]
        """
        
        env.overwriteOutput = True
        # Create an in_memory feature class to initially contain the points
        feature_class = CreateFeatureclass_management("in_memory", "temp_drainit_points", "POINT")

        AddFields_management(
            feature_class, 
            [
                #[Field Name, Field Type]
                ['uid', 'TEXT', 64],
                ['group_id', 'TEXT', 64],
            ]
        )

        # Open an insert cursor
        with InsertCursor(feature_class, ['uid', 'group_id', "SHAPE@XY"]) as cursor:
            # Iterate through list of coordinates and add to cursor
            for pt in points:
                row = [pt.uid, pt.group_id, (pt.lng, pt.lat)]
                cursor.insertRow(row)

        # Create a FeatureSet object and load in_memory feature class JSON as dict
        feature_set = FeatureSet()
        feature_set.load(feature_class)
        #fsd = json.loads(feature_set.JSON)

        if output_points_filepath:
            feature_set.save(output_points_filepath)

        # return the dictionary (A geoservices JSON as Python dictionary)
        return feature_set

    def extract_points_from_geodata(
        self, 
        points_filepath, 
        uid_field=None,
        is_naacc=False,
        group_id_field=None,
        output_points_filepath=None
        ) -> Tuple(List[Point], FeatureSet):
        """from geodata, create a list of Point objects and a FeatureSet
        """

        # # handle inputs that are from an interactive selection in ArcMap/Pro
        if isinstance(self.config.points_filepath, FeatureSet):
            self.msg("Reading from interactive selection")
        else:
            self.msg('Reading from file')
        
        # extract feature class to a PETL table and a FeatureSet
        raw_table, feature_set = self.fc_to_petl_table(
            self, 
            points_filepath, 
            include_geom=True,
            return_featureset=True
        )

        # if this is geodata that follows the NAACC format, we use the NAACC
        # etl function to transform the table to a list of Point objects
        # with nested NAACC and Capacity values if possible
        if is_naacc:
            self.msg('reading points and capturing NAACC attributes')
            points = etl_naacc_table(naacc_petl_table=raw_table)

        # otherwise we transform the raw table to a list of Point objects here
        else:
            self.msg('reading points')
            points = []
            for idx, r in enumerate(list(etl.dicts(raw_table))):
                
                kwargs = dict(
                    uid=r[uid_field],
                    lat=float(r["geometry"]['x']),
                    lng=float(r["geometry"]['y']),
                    include=True,
                    raw=r
                )
                
                if group_id_field:
                    kwargs['group_id'] = r[group_id_field],
                
                p = Point(**kwargs)
                points.append(p)

        # then dump that model to a dict, then table, then shapefile

    
        self.msg('saving points')
        # save a copy of the points feature_set to the output location
        feature_set.save(output_points_filepath)

        return points, feature_set

    def catchment_delineation(
        self,
        points_featureset,
        raster_flowdir_filepath,
        points_id_fieldname,
        **kwargs
        ):

        from arcpy import env

        self.msg('Setting environment parameters...', set_progressor_label=True)
        env_raster = Raster(raster_flowdir_filepath)
        env.snapRaster = env_raster
        env.cellSize = (env_raster.meanCellHeight + env_raster.meanCellWidth) / 2.0
        env.extent = env_raster.extent

        if isinstance(points_featureset, dict):
            points_featureset = FeatureSet(json.dumps(points_featureset))

        delineations = self._catchment_delineation(
            inlets=points_featureset,
            flow_direction_raster=raster_flowdir_filepath,
            pour_point_field=points_id_fieldname,
            **kwargs
        )

    def derive_data_from_catchments(self):

        # -----------------------------------------------------
        # SET ENVIRONMENT VARIABLES

        from arcpy import env

        self.msg('Setting environment parameters...', set_progressor_label=True)
        env_raster = Raster(self.config.raster_flowdir_filepath)
        env.snapRaster = env_raster
        env.cellSize = (env_raster.meanCellHeight + env_raster.meanCellWidth) / 2.0
        env.extent = env_raster.extent        

        # --------------------------------------------------------------------------
        # DETERMINE UNITS OF INPUT DATASETS
        # Determine the units from the input flow-direction raster's spatial ref.
        # This is used to determine the conversion factor, if any, that needs
        # to be applied to measurements taken from the input rasters
        # before calculating peak flow

        units = pint.UnitRegistry()

        self.msg('Determing units of reference raster dataset...', set_progressor_label=True)

        acf, lcf = None, None
        area_conv_factor, leng_conv_factor = 1, 1

        # get the name of the linear unit from env_raster
        unit_name = env_raster.spatialReference.linearUnitName

        # attempt to auto-dectect unit names with the Pint package, and get the
        # appropriate conversion factors for linear and area units
        if unit_name:
            if 'foot'.upper() in unit_name.upper():
                acf = 1 * units.square_foot
                lcf = 1 * units.foot
                self.msg("...auto-detected 'feet' from the source data")
            elif 'meter'.upper() in unit_name.upper():
                acf = 1 * (units.meter ** 2)
                lcf = 1 * units.meter
                self.msg("...auto-detected 'meters' from the source data")
            else:
                self.msg("Could not determine conversion factor for '{0}'. You may need to reproject your data.".format(unit_name))
        else:
            self.msg("Reference raster dataset has no spatial reference information.")
        # set the conversion factors for length an area based on the detected units
        if acf and lcf:
            # get correct conversion factor for casting units to that required by equations in calc.py
            area_conv_factor = acf.to(units.kilometer ** 2).magnitude #square kilometers
            leng_conv_factor = lcf.to(units.meter).magnitude #meters
            self.msg("Area conversion factor: {0}".format(area_conv_factor))
            self.msg("Length conversion factor: {0}".format(leng_conv_factor))
            
            self.config.area_conv_factor = area_conv_factor
            self.config.leng_conv_factor = leng_conv_factor

        self._derive_data_for_all_catchments(
            catchment_areas=self.config.basins,
            flow_direction_raster=self.config.raster_flowdir_filepath,
            slope_raster=self.config.raster_slope_filepath,
            curve_number_raster=self.config.raster_curvenumber_filepath,
            area_conv_factor=self.config.area_conv_factor,
            leng_conv_factor=self.config.leng_conv_factor,
            out_catchment_polygons=None,
            precip_table=None,
            precip_raster_lookup=None,
            out_catchment_polygons_simplify=False            
        )