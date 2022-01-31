'''
_esri.py

geoprocessing tasks with Esri Arcpy

'''
# standard library
import os, time
from collections import defaultdict
from pathlib import Path
from typing import List, Tuple, Dict
import json
from statistics import mean
from arcpy.arcobjects.arcobjects import Extent
from tqdm import tqdm
from tempfile import mkdtemp

# third party tools
import petl as etl
import pint
import click
import pandas as pd

# ArcGIS imports
# this import enables the Esri Spatially-Enabled DataFrame extension to Pandas DataFrames
from arcgis.features import GeoAccessor, GeoSeriesAccessor 

# ArcPy imports
from arcpy import EnvManager, env
from arcpy import Describe, Raster, FeatureSet, RecordSet, CreateUniqueName, ListFields
from arcpy import SpatialReference, PointGeometry
from arcpy import Point as ArcPoint

from arcpy.conversion import (
    RasterToPolygon,
    TableToTable,
    PolygonToRaster
)
from arcpy.sa import (
    Watershed, 
    FlowLength, 
    Slope, 
    SetNull, 
    IsNull,
    ZonalStatisticsAsTable, 
    FlowDirection, 
    Con, 
    CellStatistics
) #, ZonalGeometryAsTable
from arcpy.da import SearchCursor, InsertCursor, NumPyArrayToFeatureClass
from arcpy.management import (
    CreateFileGDB,
    Delete,
    SelectLayerByAttribute,
    GetCount,
    Clip,
    Dissolve,
    Copy,
    CopyFeatures,
    CreateFeatureclass,
    AddFields,
    BuildRasterAttributeTable,
    MinimumBoundingGeometry,
    Merge
)
from arcpy import (
    GetCount_management, 
    Clip_management, 
    Dissolve_management, 
    CopyFeatures_management, 
    CreateFeatureclass_management, 
    AddFields_management,
    JoinField_management, 
    MakeTableView_management,
    BuildRasterAttributeTable_management, 
    ProjectRaster_management
)
from arcpy import SetProgressor, SetProgressorLabel, SetProgressorPosition, ResetProgressor
from arcpy import AddMessage, AddWarning, AddError

# this package
from ...config import FREQUENCIES, QP_HEADER, VALIDATION_ERRORS_FIELD_LENGTH
from ...models import WorkflowConfig, DrainItPoint, Shed, Rainfall
from ..naacc import NaaccEtl

units = pint.UnitRegistry()

class GP:

    def __init__(self, config: WorkflowConfig):#, workflow_config: WorkflowConfig):

        self.config = config
        self.raster_field = "Value"
        self.all_sheds_raster = ""

        # create unique scratch directories
        # scratchFolder = mkdtemp(prefix="drainit_{0}_".format(time.strftime("%Y%m%d%H%M%S", time.localtime())))
        # print(scratchFolder)
        # env.scratchFolder = scratchFolder
        # scratchGDB = self.create_workspace(env.scratchFolder, 'scratch.gdb')
        # env.scratchGDB = str(scratchGDB)

    # --------------------------------------------------------------------------
    # Workflow utility functions

    def msg(self, text, arc_status=None, set_progressor_label=False):
        """
        output messages through Click.echo (cross-platform shell printing) 
        and the ArcPy GP messaging interface and progress bars
        """
        # click.echo(text)

        if arc_status == "warning":
            AddWarning(text)
        elif arc_status == "error":
            AddError(text)
        else:
            AddMessage(text)
        
        if set_progressor_label:
            SetProgressorLabel(text)

    def so(self, prefix, suffix="unique", where="fgdb"):
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
                "<user-provided path>": any other value provided that is an 
                existing Path will be used as the save location.
                    
        Returns:
            A string representing a complete and unique file path.

        """
        
        # set workspace location
        if where == "in_memory":
            location = "memory"
        elif where == "fgdb":
            location = Path(env.scratchGDB)
        elif where == "folder":
            location = Path(env.scratchFolder)
        else:
            loc = Path(where)
            if loc.exists():
                location = loc
            else:
                os.makedirs(where)
                # location = Path(env.scratchGDB)
        
        # create and return full path
        if suffix == "unique":
            p = CreateUniqueName(prefix, str(location))
        elif suffix == "random":
            p = str(
                location / "{0}_{1}".format(
                    prefix,
                    abs(hash(time.strftime("%Y%m%d%H%M%S", time.localtime())))
                )
            )
        elif suffix == "timestamp":
            p = str(
                location /
                "{0}_{1}".format(
                    prefix,
                    time.strftime("%Y%m%d%H%M%S", time.localtime())
                )
            )
        else:
            p = str(location / "_".join([prefix, suffix]))

        # print(p)
        return p

    def create_workspace(self, out_folder_path: Path, out_name: str) -> Path:
        """wrapper around arcpy.management.CreateFileGDB that
        will also create the parent directory/directories if they
        don't exist

        Args:
            out_folder_path ([type]): [description]
            out_name ([type]): [description]

        Returns:
            [type]: [description]
        """
        if not out_folder_path.exists():
            out_folder_path.mkdir(parents=True)
        CreateFileGDB(str(out_folder_path), out_name)
        return out_folder_path / out_name

    def clean(self, val):
        """post-process empty values ("") from ArcPy geoprocessing tools.
        """
        if val in ["", None]:
            return 0
        else:
            return val

    def geodata_to_csv(self, feature_class, out_csv):
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
        TableToTable(feature_class, str(p.parent), str(p.name))

        return out_csv

    def geodata_to_petl_table(
        self,
        feature_class, 
        include_geom=False,
        return_featureset=True
        ):
        """Convert an Esri Feature Class to a PETL table object. Optionally,
        return the FeatureSet used to create the PETL table.

        Convert an Esri Feature Class to a PETL table object.

        :param feature_class: [description]
        :type feature_class: [type]
        :param include_geom: [description], defaults to False
        :param include_geom: bool, optional
        :param return_featureset: return Esri FeatureSet, defaults to False
        :param return_featureset: bool, optional        
        :return: tuple containing an PETL Table object and FeatureSet
        :rtype: Tuple(petl.Table, FeatureSet)
        """
        # print("Reading {0} into a PETL table object".format(feature_class))
        
        feature_set = FeatureSet(feature_class)
        # convert the FeatureSet object to a python dictionary
        fs = json.loads(feature_set.JSON)

        # describe the feature class
        described_fc = Describe(feature_class)
        # get a list of field objects
        field_objs = described_fc.fields

        # make a list of fields that doesn't include the Object ID field
        #all_fields = [f for f in field_objs if f.name != described_fc.OIDFieldName]
        # make a list of field names, excluding geometry and the OID field
        attr_fields = [f.name for f in field_objs if f.type not in ['Geometry', 'Shape']]
        # then add 'geometry' to that list, since it will be present in the features in the FeatureSet
        attr_fields.append('geometry')
        
        table = etl\
            .fromdicts(fs['features'])\
            .unpackdict('attributes')\
            .cut(*attr_fields)

        if return_featureset:
            return table, feature_set
        else:
            return table, None

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

    def geodata_as_dict(self, path_to_geodata):
        if Path(path_to_geodata).exists:
            fs = FeatureSet(path_to_geodata)
            return json.loads(fs.JSON)
        else:
            return {}

    def feature_count(self, path_to_geodata):
        fs = FeatureSet(path_to_geodata)
        return GetCount(fs)
        # d = json.loads(fs.JSON)
    
    def fallback_to_json_str(self, v):
        if isinstance(v, dict) or isinstance(v, list):
            return json.dumps(v)#[:254]
        return v

    # --------------------------------------------------------------------------
    # Provider-specific utilities

    def _csv_to_fgdb_table(self, csv):
        """loads a csv into the ArcMap scratch geodatabase. Use for temporary files only.
        Output: path to the imported csv
        """
        t = self.so("csv","random","fgdb")
        TableToTable(
            in_rows=csv, 
            out_path=os.path.dirname(t), 
            out_name=os.path.basename(t)
        )
        return t

    def _xwalk_types_to_arcgis_fields(self, t):
        if t is int:
            return "LONG"
        if t is float:
            return "FLOAT"
        if t is str:
            return "TEXT"
        return "TEXT"

    def _convert_dtypes_arcgis(self, df):
        """Convert dataframe dtypes which are not compatible with ArcGIS
        https://community.esri.com/t5/arcgis-api-for-python-questions/system-error-when-exporting-spatially-enabled/td-p/1044880
        
        """
        
        # Use builtin Pandas dtype conversion
        df = df.convert_dtypes()
        
        # Then str convert any remaining special object/category fields 
        for col in df.columns:
            # if df[col].dtype not in ["str", "float"]:
            #     print(col, '/', df[col].dtype)
            if df[col].dtype == 'object' or df[col].dtype == 'O':
                print(col)
                df[col] = df[col].astype("str")
            df[col].replace({pd.NA:None})
        # Return modified df
        return df

    # --------------------------------------------------------------------------
    # Pre-Processing for supporting raster   
    # DEM, Slope, Curve Number

    def prep_cn_raster(self, 
        dem,
        curve_number_raster,
        out_cn_raster=None,
        out_coor_system=None
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
        PolygonToRaster(soils_polygon, soils_hydrogroup_field, soils_raster_path, "CELL_CENTER")
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
    # ETL for input point datasets
    # extract, transform, and load the input points

    def create_dataframe_from_geodata(
        in_table, 
        input_fields=None, 
        where_clause=None
        ):
        """Convert an arcgis table into a pandas dataframe with an object ID 
        index, and the selected
        input fields using an arcpy.da.SearchCursor.
        https://gist.github.com/d-wasserman/e9c98be1d0caebc2935afecf0ba239a0
        """
        OIDFieldName = Describe(in_table).OIDFieldName
        if input_fields:
            final_fields = [OIDFieldName] + input_fields
        else:
            final_fields = [field.name for field in ListFields(in_table)]
        data = [row for row in SearchCursor(in_table, final_fields, where_clause=where_clause)]
        fc_dataframe = pd.DataFrame(data, columns=final_fields)
        fc_dataframe = fc_dataframe.set_index(OIDFieldName, drop=True)
        return fc_dataframe

    def create_geodata_from_petl_table(
        self,
        petl_table,
        field_types_lookup,
        x_column,
        y_column,
        output_featureclass=None,
        sr=4326
        ):
        """convert a PETL table to a feature class in a file geodatabase. 
        This handles type-casting to column types that work with Esri FGDB 
        feature classes. 

        Args:
            petl_table ([type]): [description]
            field_types_lookup ([type]): [description]
            x_column ([type]): [description]
            y_column ([type]): [description]
            output_featureclass ([type], optional): [description]. Defaults to None.
            sr (int, optional): [description]. Defaults to 4326.

        Returns:
            [type]: [description]
        """        

        # approach 1: via arcgis/pandas spatially-enabled dataframe. 
        # Chokes on None/null/NaN/NAType values and the conversion of column 
        # types between the arcgis package and pandas (e.g., columns with nulls 
        # converted to objects; stringified NoneTypes converted to NAType which 
        # arcgis can't convert back to None) See: https://community.esri.com/t5/arcgis-api-for-python-questions/i-m-done-with-spatially-enabled-dataframes/m-p/1026149#M5535
        # df = etl.todataframe(petl_table)
        # sdf = pd.DataFrame.spatial.from_xy(df=df, x_column=x_column, y_column=y_column, sr=sr)
        # sdf = self.convert_dtypes_arcgis(sdf)
        # sdf.copy().spatial.to_featureclass(location=output_featureclass, sanitize_columns=False)
        # return sdf

        # approach 2: workaround for approach 1 that uses numpy. Similar issues.
        # See: https://my.usgs.gov/confluence/display/cdi/pandas.DataFrame+to+ArcGIS+Table
        # x = np.array(np.rec.fromrecords(df.values))
        # names = df.dtypes.index.tolist()
        # x.dtype.names = tuple(names)
        # print(x)
        # NumPyArrayToFeatureClass(x, output_featureclass, (x_column, y_column), SpatialReference(sr))

        with EnvManager(overwriteOutput=True):

            spatial_ref = SpatialReference(sr)

            # Create an in_memory feature class to initially contain the points
            temp_feature_class = CreateFeatureclass_management(
                out_path="memory", 
                out_name="temp_drainit_points", 
                geometry_type="POINT",
                spatial_reference=spatial_ref
            )

            # fields_to_add = [
            #   ['uid', 'TEXT', 'uid', 255], 
            #   ['group_id', 'TEXT', 'group_id', 255]
            # ]
            # fields_to_add = [
            #     [f[0], self._xwalk_types_to_arcgis_fields(f[1]), f[0]]
            #     for f 
            #     in fields_to_include
            # ]

            # create the fields arg for AddFields_management from the fields in 
            # the provided PETL table, with field types coming from the provided 
            # field_types_lookup and crosswalked to the ArcPy field type args. 
            # Fallback to a string type if the field in the table isn't in the
            # lookup. Handle `validation_errors` field separately.
            # TODO - do this in a more generic way (e.g., a better field_lookup 
            # format)
            fields_to_add = []
            for h in etl.header(petl_table):
                if h == 'validation_errors':
                    fields_to_add.append([h, self._xwalk_types_to_arcgis_fields(field_types_lookup.get(h, str)), h, VALIDATION_ERRORS_FIELD_LENGTH])
                else:
                    fields_to_add.append([h, self._xwalk_types_to_arcgis_fields(field_types_lookup.get(h, str))])
 
            AddFields_management(
                temp_feature_class,
                fields_to_add
            )

            # Use an insert cursor to write rows from the PETL table to the temp feature class
            fields_to_insert = [f[0] for f in fields_to_add]
            fields_to_insert.append("SHAPE@XY")
            with InsertCursor(temp_feature_class, fields_to_insert) as cursor:
                for idx, row in enumerate(list(etl.records(petl_table))):
                    # print(idx, row['Survey_Id'])
                    r = [self.fallback_to_json_str(v) for v in row] # all field values
                    r.append([float(row[x_column]), float(row[y_column])]) # "SHAPE@XY"
                    cursor.insertRow(r)

        print("temp_feature_class", int(GetCount(temp_feature_class).getOutput(0)))
        if output_featureclass:
            CopyFeatures(temp_feature_class, output_featureclass)
            print("output_featureclass", int(GetCount(output_featureclass).getOutput(0)))

        # Create a FeatureSet object and load in_memory feature class JSON as dict
        feature_set = FeatureSet(temp_feature_class)
        # feature_set.load(feature_class)

        # return the dictionary (geoservices JSON as Python dictionary)
        # if as_dict:
        #     return json.loads(feature_set.JSON)
        # else:
        return json.loads(feature_set.JSON)

    def create_geodata_from_points(
        self, 
        points: List[DrainItPoint],
        output_points_filepath=None,
        as_dict=True,
        wkid=4326
        ) -> dict:
        """from a list of Drain-It Point objects, create an ArcPy FeatureSet,
        for use in other ArcPy GP tools.

        :param points: list of drainit.models.Point objects. Only the uid and group_id are used here; extended attributes from naacc aren't used.
        :type points: List[Point]
        :param output_points_filepath: optional path to save points to file on disk, defaults to None
        :type output_points_filepath: str, optional
        :param as_dict: return the geodata as geoservices JSON as Python dictionary, defaults to True
        :type as_dict: bool, optional
        :return: geoservices JSON as Python dictionary; FeatureSet object if as_dict is False
        :rtype: dict
        """
        
        with EnvManager(overwriteOutput=True):

            #get the spatial ref from the first available point
            p_srs = [p.spatial_ref_code for p in points if p.spatial_ref_code is not None]
            if len(p_srs) > 0:
                try:
                    spatial_ref = SpatialReference(p_srs[0].spatial_ref_code)
                except:
                    spatial_ref = SpatialReference(wkid)
            else:
                spatial_ref = SpatialReference(wkid)

            # Create an in_memory feature class to initially contain the points
            feature_class = CreateFeatureclass_management(
                out_path="memory", 
                out_name="temp_drainit_points", 
                geometry_type="POINT",
                spatial_reference=spatial_ref
            )

            fields_to_add = [['uid', 'TEXT', 'uid', 255], ['group_id', 'TEXT', 'group_id', 255]]

            AddFields_management(
                feature_class,
                fields_to_add
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

        if output_points_filepath:
            feature_set.save(output_points_filepath)

        # return the dictionary (geoservices JSON as Python dictionary)
        if as_dict:
            return json.loads(feature_set.JSON)
        else:
            return feature_set

    def extract_points_from_geodata(
        self, 
        points_filepath, 
        uid_field,
        is_naacc=False,
        group_id_field=None,
        output_points_filepath=None
        ) -> Tuple[List[DrainItPoint], dict]:
        """from any geodata input file, create a list of Point objects and an 
        ArcGIS FeatureSet object
        """

        # # handle inputs that are from an interactive selection in ArcMap/Pro
        # if isinstance(points_filepath, FeatureSet):
        #     self.msg("Reading from interactive selection")
        # else:
        #     self.msg('Reading from file')
        
        # extract feature class to a PETL table and a FeatureSet
        raw_table, feature_set = self.geodata_to_petl_table(
            points_filepath,
            include_geom=True,
            return_featureset=True
        )

        # convert the FeatureSet to its JSON representation
        feature_set_json = json.loads(feature_set.JSON)

        # get the spatial reference code from the FeatureSet JSON
        spatial_ref_code = feature_set_json.get('spatialReference', {}).get('wkid', None)

        # if this is geodata that follows the NAACC format, we use the NAACC
        # etl function to transform the table to a list of Point objects
        # with nested NAACC and capacity calc-ready attributes where possible
        # (This is workflow for Culvert Capacity when geodata is provided 
        # instead of a CSV)
        points = []
        if is_naacc:
            self.msg('reading points and capturing NAACC attributes')
            # TODO: make this less clunky and with clearer assumptions:
            # load up the NaaccETL class with defaults
            naacc_etl = NaaccEtl(wkid=spatial_ref_code)
            # assign the PETL table to the object
            naacc_etl.table = raw_table
            # run the DrainItPoint generation method for NAACC data
            naacc_etl.generate_points_from_table()
            # assign the list
            points = naacc_etl.points

        # Otherwise we transform the raw table to a list of Point objects here
        # (This is workflow for Peak-Flow)
        else:
            self.msg('reading points')
            for idx, r in enumerate(list(etl.dicts(raw_table))):
                point_kwargs = dict(
                    uid=r[uid_field],
                    lat=float(r["geometry"]['y']),
                    lng=float(r["geometry"]['x']),
                    spatial_ref_code=spatial_ref_code,
                    include=True,
                    raw=r
                )
                if group_id_field:
                    point_kwargs['group_id'] = r[group_id_field]
                
                p = DrainItPoint(**point_kwargs)
                points.append(p)

        if output_points_filepath:
            # finally, save it out
            self.msg('saving points')
            # save a copy of the points feature_set to the output location
            feature_set.save(output_points_filepath)

        # return the list of Point objects and a dict version of the FeatureSet
        return points, feature_set_json, spatial_ref_code

    # --------------------------------------------------------------------------
    # Catchment delineation functions

    def _delineate_all_catchments(
        self, 
        inlets, 
        flow_direction_raster, 
        pour_point_field,
        ):
        """Delineate the catchment area(s) for the inlet(s), and provide a count.

        :param inlets: path to point shapefile or feature class representing inlet location(s) from which catchment area(s) will be determined. Can be one or many inlets.
        :type inlets: str
        :param flow_direction_raster: [description]
        :type flow_direction_raster: [type]
        :param pour_point_field: [description]
        :type pour_point_field: [type]
        :return: a python dictionary structured as follows: 
            {
                "catchments": <path to the catchments raster created by the Arcpy.sa Watershed function>,
                "count": <count (int) of the number of inlets/catchments>
            }
        :rtype: dict
        """

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

        self.config.all_sheds_raster = self.all_sheds_raster

        return self.all_sheds_raster

    # --------------------------------------------------------------------------
    # Analytics for delineation and data derivation in Series
    # Used for *catch-basin* analysis; works with a single watershed raster 
    # that contains multiple watersheds

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

    def _calc_catchment_average_rainfall(self, catchment_area_raster, zone_value, rainfall_rasters=[]):
        return

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
        RasterToPolygon(catchment_areas, cp, simplify, self.raster_field)

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

    def catchment_delineation_in_series(
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

        delineations = self._delineate_all_catchments(
            inlets=points_featureset,
            flow_direction_raster=raster_flowdir_filepath,
            pour_point_field=points_id_fieldname,
            **kwargs
        )

    def derive_data_from_catchments_in_series(self):

        # -----------------------------------------------------
        # SET ENVIRONMENT VARIABLES

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
            catchment_areas=self.config.sheds,
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

    # --------------------------------------------------------------------------
    # Analytics for delineation and data derivation in Parallel
    # Used for *culvert* analysis; works with multiple overlapping watershed 
    # rasters, where each raster contains only a single watershed

    def _delineate_and_analyze_one_catchment(
        self,
        point_geodata: FeatureSet,
        pour_point_field: str,
        flow_direction_raster: str,
        slope_raster: str,
        curve_number_raster: str,
        out_shed_polygon: str,
        rainfall_rasters: tuple = None,
        out_catchment_polygons_simplify: bool = False
        # rainfall_unit_conversion_factor = 0.1,
        ) -> Shed:
        """perform delineation one point and analysis on the watershed
        Results are saved to a single Shed object.

        Since esri GP tools operate on multiple features, we feed them a
        JSON-ified arcpy.FeatureSet object as a Python dictionary. That 
        FeatureSet should only contain one point feature.
        """
        fs = json.loads(point_geodata.JSON)
        # create a shed (dataclass object) from the feature
        fprops = fs['features'][0]['attributes']
        shed = Shed(
            uid=fprops['uid'],
            group_id=fprops['group_id'],
        )        

        self.msg("--------------------------------")
        self.msg("analyzing point {0}".format(shed.uid))


        # we can get a tabular look at what's in the layer like this:
        # fs = json.loads(FeatureSet(inlet).JSON)
        # ft = etl.fromdicts(fs['features']).unpackdict('attributes').unpackdict('geometry')
        # etl.vis.displayall(ft)
        
        with EnvManager(
            snapRaster=flow_direction_raster,
            cellSize=flow_direction_raster,
        ):
            # delineate one watershed
            self.msg('delineating catchment')
            one_shed = Watershed(
                in_flow_direction_raster=flow_direction_raster,
                in_pour_point_data=point_geodata,
            )
            
            shed.filepath_raster = self.so("shed_{}_delineation".format(shed.uid))
            # print(shed.filepath_raster)
            one_shed.save(shed.filepath_raster)
        
        ## ---------------------------------------------------------------------
        # ANALYSIS
        
        
        ## ---------------------------------------------------------------------
        # calculate area of catchment

        self.msg("converting catchment from raster and calculating area")
        
        #ZonalGeometryAsTable(catchment_areas,"Value","output_table") # crashes like a mfer
        #cp = self.so("catchmentpolygons","timestamp","fgdb")
        cp = self.so("shed_{}_polygon".format(shed.uid))
        #RasterToPolygon copies our ids from self.raster_field into "gridcode"
        simplify = "NO_SIMPLIFY"
        if out_catchment_polygons_simplify:
            simplify = "SIMPLIFY"
            
        RasterToPolygon(one_shed, cp, simplify)

        # Dissolve the converted polygons, since some of the raster zones may have corner-corner links
        #cpd = self.so("catchmentpolygonsdissolved","timestamp","fgdb")
        if out_shed_polygon:
            shed.filepath_vector = out_shed_polygon
        else:
            shed.filepath_vector = self.so("shed_{}_delineation_dissolved".format(shed.uid))
        
        Dissolve(
            in_features=cp,
            out_feature_class=shed.filepath_vector,
            dissolve_field="gridcode",
            multi_part="MULTI_PART"
        )

        # get and sum the areas for all records 
        # (there should only be one at this point, but...)
        areas = []
        with SearchCursor(shed.filepath_vector,["SHAPE@"]) as c:
            for r in c:
                # the "SHAPE@" field token returns a Geometry object.
                # we use the getArea method to get the area in the preferred 
                # units, regardless of coordinate system
                this_area = r[0].getArea(units="SQUAREKILOMETERS")
                areas.append(this_area)
        
        shed.area_sqkm = sum(areas)

        
        ## ---------------------------------------------------------------------
        # calculate flow length

        self.msg("calculating flow length")
        
        with EnvManager(
            snapRaster=flow_direction_raster,
            cellSize=flow_direction_raster,
            overwriteOutput=True
        ):
        
            # clip the flow direction raster to the catchment area (zone value)
            clipped_flowdir = SetNull(IsNull(one_shed), Raster(flow_direction_raster))
            # calculate flow length
            flow_len_raster = FlowLength(clipped_flowdir, "UPSTREAM")
            # determine maximum flow length
            shed.max_fl = flow_len_raster.maximum
            
            #TODO: convert length to ? using leng_conv_factor (detected from the flow direction raster)
            #fl_max = fl_max * leng_conv_factor
        
        
        ## ---------------------------------------------------------------------
        # calculate average curve number

        self.msg("calculating average curve number")
        
        table_cn_avg = self.so("shed_{0}_cn_avg".format(shed.uid))

        with EnvManager(
            cellSizeProjectionMethod="PRESERVE_RESOLUTION",
            extent="MINOF",
            cellSize=one_shed,
            overwriteOutput=True
        ):        
            ZonalStatisticsAsTable(
                one_shed,
                self.raster_field,
                Raster(curve_number_raster),
                table_cn_avg, 
                "DATA",
                "MEAN"
            )
            cn_stats = json.loads(RecordSet(table_cn_avg).JSON)
            

            if len(cn_stats['features']) > 0:
                # in the event we get more than one record here, we avg the avg
                means = [f['attributes']['MEAN'] for f in cn_stats['features']]
                shed.avg_cn = mean(means)
        
        ## ---------------------------------------------------------------------
        # calculate average slope
        
        
        table_slope_avg = self.so("shed_{0}_slope_avg".format(shed.uid))
        
        with EnvManager(
            cellSizeProjectionMethod="PRESERVE_RESOLUTION",
            extent="MINOF",
            cellSize=one_shed,
            overwriteOutput=True
        ):
            ZonalStatisticsAsTable(
                one_shed, 
                self.raster_field, 
                Raster(slope_raster),
                table_slope_avg, 
                "DATA",
                "MEAN"
            )
            
            slope_stats = json.loads(RecordSet(table_slope_avg).JSON)
            if len(slope_stats['features']) > 0:
                # in the event we get more than one record here, we avg the avg                
                means = [f['attributes']['MEAN'] for f in slope_stats['features']]
                shed.avg_slope_pct = mean(means)
        
        
        ## ---------------------------------------------------------------------
        # calculate average rainfall for each storm frequency
        
        rainfalls = []
        
        self.msg('calculating average rainfall')

        # for each rainfall raster representing a storm frequency:
        for rr in rainfall_rasters:
            # self.msg(rr['freq'])
            # print(rr)

            table_rainfall_avg = self.so(
                "shed_{0}_rain_avg_{1}".format(shed.uid, rr['freq'])
            )
            
            # calculate the average rainfall for the watershed
            with EnvManager(
                cellSizeProjectionMethod="PRESERVE_RESOLUTION",
                extent="MINOF",
                cellSize=one_shed,
                overwriteOutput=True
            ):
                ZonalStatisticsAsTable(
                    one_shed,
                    self.raster_field,
                    Raster(rr['path']),
                    table_rainfall_avg,
                    "DATA",
                    "MEAN"
                )

            rainfall_stats = json.loads(RecordSet(table_rainfall_avg).JSON)

            rainfall_units = "inches"

            if len(rainfall_stats['features']) > 0:
                # there shouldn't be multiple polygon features here, but this 
                # willhandle edge cases:
                means = [f['attributes']['MEAN'] for f  in rainfall_stats['features']]
                avg_rainfall = mean(means)
                # NOAA Atlas 14 precip values are in 1000ths/inch, converted to inches here
                # use Pint
                avg_rainfall = units.Quantity(f'{avg_rainfall}/1000 {rainfall_units}').m
            else:
                avg_rainfall = None

            # self.msg(rr['freq'], "year event:", avg_rainfall)
            rainfalls.append(
                Rainfall(
                    freq=rr['freq'], 
                    dur='24hr', 
                    value=avg_rainfall,
                    units=rainfall_units
                )
            )
            
        shed.avg_rainfall = sorted(rainfalls, key=lambda x: x.freq)

        return shed

    def delineation_and_analysis_in_parallel(
        self,
        points: List[DrainItPoint],
        pour_point_field: str,
        flow_direction_raster: str,
        slope_raster: str,
        curve_number_raster: str,
        precip_src_config: dict,
        out_shed_polygons: str = None,
        out_shed_polygons_simplify: bool = False,
        override_skip: bool = False
        ) -> Tuple[DrainItPoint]:

        shed_geodata = []
        
        # open up the rainfall rasters config and get a list of 
        # just the rasters, with the full paths assembled
            
        # rainfall_rasters = [
        #     {
        #         'path': str(Path(precip_src_config['root']) / r['path']),
        #         'freq': r['freq']
        #     }
        #     # TODO: handle multiple formats with this filter:
        #     for r in precip_src_config['rasters'] if r['ext'] == ".asc"
        # ]
        
        # for each Point in the input points list
        for point in tqdm(points):

            # if point is marked as not include and override_skip is false,
            # skip this iteration.
            if not override_skip and not point.include:
                continue

            # create a FeatureSet for each individual Point object
            # this lets us keep our Point objects around while feeding
            # the GP tools a native input format.
            point_geodata = self.create_geodata_from_points([point], as_dict=False)

            # delineate a catchment/basin/watershed ("shed") and derive 
            # some data from that, storing it in a Shed object.
            shed = self._delineate_and_analyze_one_catchment(
                point_geodata=point_geodata,
                pour_point_field=pour_point_field,
                flow_direction_raster=flow_direction_raster,
                slope_raster=slope_raster,
                curve_number_raster=curve_number_raster,
                rainfall_rasters=precip_src_config['rasters'],
                out_shed_polygon=None,
                out_catchment_polygons_simplify=out_shed_polygons_simplify
            )

            # save that to the Point object
            point.shed = shed
            shed_geodata.append(shed.filepath_vector)
        
        # merge the sheds into a single layer
        if out_shed_polygons:
            Merge(shed_geodata, out_shed_polygons)

        # return all updated Point objects and a separate list of sheds.
        return points#, sheds

    def centroid_of_feature_envelope(self, in_features, project_as=4326) -> Dict:
        """given features, calculate the envelope, and return
        the centroid of the envelope as a dictionary
        
        Args:
            in_features ([type]): layer, feature class, etc--anything that arcpy can read.
            project_as (int, optional): WKID of coodinate system to return coordinates as. Defaults to 4326.

        Returns:
            dict: coordinates of the centroid in a dictionary keyed by lat, lon
        """

        fs = FeatureSet(in_features)
        # in-memory
        mbg="memory\mbg"
        
        MinimumBoundingGeometry(
            fs,
            mbg,
            "RECTANGLE_BY_AREA",
            "ALL"
        )
        d = Describe(mbg)
        sr = d.spatialReference

        pt = None

        with SearchCursor(mbg, ["SHAPE@XY"]) as sc: 
            for r in sc:
                x, y = r[0]
                pt = ArcPoint(X=x, Y=y)

        centroid = PointGeometry(inputs=pt, spatial_reference=sr)
        # reproject
        if project_as:
            centroid = centroid.projectAs(SpatialReference(project_as))

        Delete(mbg)
        return dict(
            lon=centroid.centroid.X,
            lat=centroid.centroid.Y
        )
