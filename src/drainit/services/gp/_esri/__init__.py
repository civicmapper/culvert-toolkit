'''
_esri.py

geoprocessing tasks with Esri Arcpy

'''

# __all__ = [
#     'GP'
# ]

# standard library
import os, time
from pathlib import Path
from typing import List, Tuple, Dict
import json
from statistics import mean
import pdb

# third party tools
import petl as etl
import pint
import click
import pandas as pd
from codetiming import Timer
from tqdm import tqdm
# from mpire import WorkerPool

# ArcGIS imports
# this import enables the Esri Spatially-Enabled DataFrame extension to Pandas DataFrames
# from arcgis.features import GeoAccessor, GeoSeriesAccessor 

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
from arcpy.da import (
    SearchCursor, 
    InsertCursor, 
    Describe as DaDescribe
)
from arcpy.management import (
    CreateFileGDB,
    Delete,
    Dissolve,
    CopyFeatures,
    ProjectRaster,
    MinimumBoundingGeometry,
    Merge,
    CalculateFields,
    CopyRaster,
    Project,
    Resample
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
from ....config import FREQUENCIES, QP_HEADER, VALIDATION_ERRORS_FIELD_LENGTH
from ....models import WorkflowConfig, DrainItPoint, DrainItPointSchema, Shed, Rainfall, RainfallRasterConfig
from ...naacc import NaaccEtl


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

    def msg(self, text, arc_status=None, set_progressor_label=False, echo=False):
        """
        output messages through Click.echo (cross-platform shell printing) 
        and the ArcPy GP messaging interface and progress bars
        """
        if echo:
            if arc_status:
                click.echo("{0}: {1}".format(arc_status.upper(), text))
            else:
                click.echo(text)

        if arc_status == "warning":
            AddWarning(text)
        elif arc_status == "error":
            AddError(text)
        else:
            AddMessage(text)
        
        if set_progressor_label:
            SetProgressorLabel(text)

    def _so(self, prefix, suffix="unique", where="in_memory"):
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
        
        if isinstance(location , str):
            location = Path(location)
        
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

    def _clean(self, val):
        """post-process empty values ("") from ArcPy geoprocessing tools.
        """
        if val in ["", None]:
            return 0
        else:
            return val

    # --------------------------------------------------------------------------
    # Provider-specific utilities

    def _csv_to_fgdb_table(self, csv):
        """loads a csv into the ArcMap scratch geodatabase. Use for temporary files only.
        Output: path to the imported csv
        """
        t = self._so("csv","random","fgdb")
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
        if t is bool:
            return "SHORT"
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
                # print(col)
                df[col] = df[col].astype("str")
            df[col].replace({pd.NA:None})
        # Return modified df
        return df

    def _fallback_to_json_str(self, v):
        if isinstance(v, dict) or isinstance(v, list):
            return json.dumps(v)#[:254]
        return v

    def _join_to_copy(self, in_data, out_data, join_table, in_field, join_field):
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
    # public Workspace and ETL methods

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
        return out_folder_path / f'{out_name}.gdb'

    def create_featureclass_parents(self, out_feature_class: str):
        """given a full path to feature class in a geodatabase, create any all
        parent directories that don't already exist, plus the fgdb if it doesn't
        exist

        Returns a tuple of the parent folder of the workspace and the workspace (FGDB) name
        
        """
        fc_path = Path(out_feature_class)
        found_gdb_idx, found_gdb = False, False
        for idx, p in enumerate(fc_path.parts):
            found_gdb = p.endswith(".gdb")
            if found_gdb:
                found_gdb_idx = idx
            # print(idx, p, found_gdb, found_gdb_idx)
        # print(found_gdb_idx, found_gdb)
            
        if found_gdb_idx:
            output_workspace = Path(*fc_path.parts[:found_gdb_idx+1])
            print("output_workspace", output_workspace)
            if not output_workspace.exists():
                output_workspace = self.create_workspace(output_workspace.parent, output_workspace.name)
            return output_workspace.parent, output_workspace.name
        
        return False, False

    def detect_data_type(self, filepath:str):
        return Describe(filepath).dataType

    def create_csv_from_geodata(self, feature_class, out_csv) -> str:
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

    def create_petl_table_from_geodata( 
        self,
        feature_class:str, 
        include_geom:bool=False,
        # alt_xy_fields:List[str]=None 
        ) -> Tuple[etl.Table, dict, int]:
        """Convert an Esri Feature Class to a PETL table object.

        Convert an Esri Feature Class to a PETL table object.

        :param feature_class: path to feature class
        :type feature_class: str
        :param include_geom: include the feature geometry in the table.  Defaults to False
        :param include_geom: bool, optional
        :return: tuple containing a PETL Table object, FeatureSet, and the WKID of the feature_class CRS
        :rtype: Tuple(petl.Table, FeatureSet, int)
        """
        # print("Reading {0} into a PETL table object".format(feature_class))
        
        feature_set = FeatureSet(feature_class)
        # convert the FeatureSet object to a python dictionary
        fs = json.loads(feature_set.JSON)

        # describe the feature class and get some properties
        described_fc = Describe(feature_class)
        field_objs = described_fc.fields # all fields
        oid_field = None # OBJECTID OR FID field
        if described_fc.hasOID:
            oid_field = described_fc.OIDFieldName
        shp_field = described_fc.shapeFieldName # SHAPE (geometry) field
        crs_wkid = described_fc.spatialReference.factoryCode # spatial reference

        # derive a list of fields to exclude from table conversion
        fields_to_exclude = [x for x in [oid_field, shp_field] if x]        
        # make a list of field names to include
        attr_fields = [f.name for f in field_objs if f.name not in fields_to_exclude]
        # add a geometry field, which will contain geometry as a dictionary
        if include_geom:
            attr_fields.append('geometry')

        # self.msg(f"fields_to_exclude: {fields_to_exclude}", )
        # self.msg(f"attr_fields {attr_fields}")
        
        table = etl.fromdicts(fs['features'])

        if etl.nrows(table) > 0:
            table = etl\
                .unpackdict(table, 'attributes')\
                .cut(*attr_fields)

            if include_geom:
                # remove existing x/y fields if any, unpack the geometry dict
                fields_to_keep = [f for f in etl.header(table) if f not in ["x", "y"]]
                table = etl\
                    .cut(table, fields_to_keep)\
                    .unpackdict('geometry')

            return table, feature_set, crs_wkid
        else:
            self.msg("The feature class is empty.", 'warning', echo=True)
            return table, feature_set, crs_wkid

    def create_dicts_from_geodata(self, path_to_geodata):
        """convert provider-formatted geodata to a Python dictionary"""
        if Path(path_to_geodata).exists:
            fs = FeatureSet(path_to_geodata)
            return json.loads(fs.JSON)
        else:
            return {}

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
        x_column,
        y_column,
        output_featureclass=None,
        crs_wkid=4326,
        field_types_lookup={}        
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
        # print(petl_table)
        # Remove system fields look-alikes that may have snuck through;
        # e.g., 'OBJECTID' may not be the actual oid field, but a duplicate
        # due to whatever happend to the data before hand. It's presence here
        # though will muck things up.
        if 'OBJECTID' in list(etl.header(petl_table)):
            petl_table = etl.cutout(petl_table, 'OBJECTID')

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

        if not field_types_lookup:
            field_types_lookup = {}
            for h in etl.header(petl_table):
                ftypes = [n for n in etl.typeset(petl_table, h) if n != 'NoneType']
                if 'float' in ftypes:
                    field_types_lookup[h] = float
                elif 'int' in ftypes:
                    field_types_lookup[h] = int
                elif 'str' in ftypes:
                    field_types_lookup[h] = str
                elif 'bool' in ftypes:
                    field_types_lookup[h] = bool
                else:
                    field_types_lookup[h] = str                    

        with EnvManager(overwriteOutput=True):

            spatial_ref = SpatialReference(crs_wkid)

            # Create an in_memory feature class to initially contain the points
            temp_fc = Path(self._so('temp_drainit_points',where="in_memory", suffix="random"))
            temp_feature_class = CreateFeatureclass_management(
                out_path=str(temp_fc.parent), #"memory",
                out_name=temp_fc.name,
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
            # TODO - do this in a more generic way (e.g., a schema-agnostic 
            # field_lookup format)
            fields_to_add = []
            for h in etl.header(petl_table):
                if h == 'validation_errors':
                    fields_to_add.append([h, self._xwalk_types_to_arcgis_fields(field_types_lookup.get(h, str)), h, VALIDATION_ERRORS_FIELD_LENGTH])
                else:
                    fields_to_add.append([h, self._xwalk_types_to_arcgis_fields(field_types_lookup.get(h, str))])
            # print([f[0] for f in fields_to_add])
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
                    r = [self._fallback_to_json_str(v) for v in row] # all field values
                    try:
                        r.append([float(row[x_column]), float(row[y_column])]) # "SHAPE@XY"
                        cursor.insertRow(r)
                    except TypeError as e:
                        self.msg(f"NULL geometry for row {idx}")
                        pass

        # print("temp_feature_class", int(GetCount(temp_feature_class).getOutput(0)))
        if output_featureclass:
            CopyFeatures(temp_feature_class, output_featureclass)
            # print("output_featureclass", int(GetCount(output_featureclass).getOutput(0)))

        # Create a FeatureSet object and load in_memory feature class JSON as dict
        feature_set = FeatureSet(temp_feature_class)
        # feature_set.load(feature_class)

        # return the dictionary (geoservices JSON as Python dictionary)
        # if as_dict:
        #     return json.loads(feature_set.JSON)
        # else:
        return json.loads(feature_set.JSON)

    def create_geodata_from_drainitpoints(
        self, 
        points: List[DrainItPoint],
        output_points_filepath=None,
        as_dict=True,
        input_crs_wkid_override=4326,
        output_crs_wkid=None
        ) -> dict:
        """from a list of Drain-It Point objects, create an ArcPy FeatureSet,
        for use in other ArcPy GP tools.
        """
        # self.msg(points)
        
        with EnvManager(overwriteOutput=True):

            # self.msg(f"DEBUG: creating geodata from {points}")

            #get the spatial ref from the first available point
            p_srs = [p.spatial_ref_code for p in points if p.spatial_ref_code is not None]
            # self.msg(p_srs)
            if len(p_srs) > 0:
                try:
                    spatial_ref = SpatialReference(p_srs[0])
                    # self.msg(f'DEBUG: using crs {spatial_ref.factoryCode} from point')
                except Exception as e:
                    # self.msg(e)
                    spatial_ref = SpatialReference(input_crs_wkid_override)
                    # self.msg(f'DEBUG: warning: falling back to default crs: {spatial_ref.factoryCode}')
                    
            else:
                spatial_ref = SpatialReference(input_crs_wkid_override)
                # self.msg(f'DEBUG: falling back to default crs: {spatial_ref.factoryCode}')

            

            # Create an in_memory feature class to initially contain the points
            temp_fc = Path(self._so('temp_drainit_points',where="in_memory", suffix="random"))
            feature_class = CreateFeatureclass_management(
                out_path=str(temp_fc.parent), #"memory",
                out_name=temp_fc.name,
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

            # reproject if output_crs_wkid is spec'd.
            
            if output_crs_wkid:
                self.msg(f"reprojecting to {output_crs_wkid}")
                feature_class_rp = CreateFeatureclass_management(
                    out_path=env.scratchGDB, #"memory", 
                    out_name="temp_drainit_points_rp", 
                    geometry_type="POINT",
                    spatial_reference=SpatialReference(output_crs_wkid)
                )
                Project(feature_class, feature_class_rp, SpatialReference(output_crs_wkid))
                # Create a FeatureSet object and load in_memory feature class JSON as dict
                feature_set = FeatureSet()
                feature_set.load(feature_class_rp)
            
            else:
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

    def create_drainitpoints_from_geodata(
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
        raw_table, feature_set, crs_wkid = self.create_petl_table_from_geodata(
            points_filepath,
            include_geom=True
        )

        # convert the FeatureSet to its JSON representation
        feature_set_json = json.loads(feature_set.JSON)

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
            # Since this is coming from geodata via create_petl_table_from_geodata,
            # we use the columns from the raw table
            naacc_etl = NaaccEtl(wkid=crs_wkid, naacc_x="x", naacc_y="y")
            # assign the PETL table to the object
            naacc_etl.table = raw_table
            # print(etl.vis.lookall(raw_table))
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
                    lat=float(r['y']),
                    lng=float(r['x']),
                    include=True,
                    raw=r,
                    spatial_ref_code=crs_wkid
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
        return points, feature_set_json, crs_wkid

    def get_centroid_of_feature_envelope(self, in_features, project_as=4326) -> Dict:
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

    def create_geotiffs_from_rainfall_rasters(
        self, 
        rrc: RainfallRasterConfig, 
        out_folder: str, 
        target_crs_wkid=None, 
        project_raster_kwargs=None, 
        target_raster=None
        ) -> RainfallRasterConfig:
        """Converts all rasters in the rainfall rasters config to geotiffs; 
        reprojects if a target crs is specified. Updates the path in the config 
        object"""
        for r in rrc.rasters:

            p = Path(r.path)
            n = f'{str(p.stem)}.tif'
            o = Path(out_folder) / n
            self.msg(f"creating {n}")

            if target_raster:
                tsr = Raster(target_raster)
                tsr.extent
                tsr.meanCellWidth
                tmp = self._so(n,where="in_memory")
                # tmp = str(Path(out_folder) / f'temp_{str(p.stem)}.tif')
                with EnvManager(
                    snapRaster=tsr,
                    extent=tsr.extent,
                    overwriteOutput=True
                ):
                    ProjectRaster(str(p), tmp, out_coor_system=tsr.spatialReference)
                with EnvManager(
                    extent=tsr.extent,
                    snapRaster=tsr,
                    overwriteOutput=True
                ):
                    Resample(tmp, str(o), f'{tsr.meanCellWidth} {tsr.meanCellHeight}', "BILINEAR")

            if target_crs_wkid:
                sr=SpatialReference(target_crs_wkid)
                kwargs=dict(
                    in_raster=str(p), 
                    out_raster=str(o), 
                    out_coor_system=sr
                )
                if project_raster_kwargs:
                    kwargs.update(project_raster_kwargs)
                ProjectRaster(**kwargs)

            if not target_crs_wkid and not target_raster:
                CopyRaster(str(p),str(o))

            r.path = str(o)
            r.ext="tif"

        rrc.root = out_folder
        
        return rrc

    def update_geodata_geoms_with_other_geodata(
        self, 
        target_feature_class, 
        target_join_field,  
        source_feature_class, 
        source_join_field, 
        output_feature_class, 
        crs_wkid=4326,
        include_moved_field=True,
        moved_field="moved"
        ):

        # read features classes into PETL table objects
        # (this will remove any old fields named "x" or "y")
        target_table, target_fs, target_crs_wkid = self.create_petl_table_from_geodata(target_feature_class, include_geom=True)
        source_table, source_fs, source_crs_wkid = self.create_petl_table_from_geodata(source_feature_class, include_geom=True)

        # derive the CRS WKID from the new source geometry table
        sr = DaDescribe(source_feature_class).get('spatialReference')
        if sr:
            if sr.PCSCode:
                crs_wkid = sr.PCSCode
            elif sr.GCSCode:
                crs_wkid = sr.GCSCode
            else:
                # crs_wkid will default to 4326
                pass

        # clean up fields in the target table, removing any x y (possibly from
        # previous run); also cast target join field values to text
        target_table_clean = etl\
            .rename(target_table, {"x": "shape@x", "y": "shape@y"})\
            .convert(target_join_field, str)

        
        # clean up fields in the source geometry table, including casting
        # the join field values to text
        geometry_table = etl\
            .cut(source_table, *[source_join_field, "x", "y"])\
            .convert(source_join_field, str)
        
        t = etl\
            .leftjoin(
                left=target_table_clean, 
                right=geometry_table, 
                lkey=target_join_field, 
                rkey=source_join_field
            )\
            .convert('x', lambda v,r: v if v is not None else r['shape@x'], pass_row=True)\
            .convert('y', lambda v,r: v if v is not None else r['shape@y'], pass_row=True)
        
        if include_moved_field:
            if moved_field in etl.header(t):
                t2 = etl.cutout(t, moved_field)
            else:
                t2 = t
            t3 = etl\
                .addfield(
                    t2, 
                    moved_field, 
                    lambda r: not all([
                        # if these are the same, it means the feature wasn't moved
                        r['x'] == r['shape@x'], r['y'] == r['shape@y']
                    ])
                )\
                .convert(moved_field, bool)
        else:
            t3 = t

        t4 = etl.cutout(t3, 'shape@x', 'shape@y')

        self.create_geodata_from_petl_table(t4,"x","y",output_feature_class, crs_wkid)
        
        return t4
        

    # --------------------------------------------------------------------------
    # Public Pre-Processing methods for rasters
    # DEM, Slope, Curve Number

    def prep_curvenumber_raster(self, 
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
        clipped_cn = self._so("cn_clipped")
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
            prepped_cn = self._so("cn_prepped")
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

    def build_curvenumber_raster(self, 
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
        :param soils_hydrogroup_field: [description], defaults to "SOIL_HYDRO" (from the NCRS low-resolution soils dataset)
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
        with EnvManager(
            snapRaster = reference_raster,
            cellSize = reference_raster.meanCellWidth,
            extent = reference_raster,
            outputCoordinateSystem = reference_raster,
        ):

            
            cs = env.outputCoordinateSystem.exportToString()

            # SOILS -------------------------------------
            
            self.msg("Processing Soils...")
            # read the soils polygon into a raster, get list(set()) of all cell values from the landcover raster
            soils_raster_path = self._so("soils_raster")
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
                out_cn_raster = self._so("cn_raster","random","fgdb")

            ProjectRaster_management(
                in_raster=cn_raster,
                out_raster=out_cn_raster,
                out_coor_system=cs,
                resampling_type="NEAREST",
                cell_size=env.cellSize
            )
            
            # cn_raster.save(out_cn_raster)
            return out_cn_raster

    def derive_analysis_rasters_from_dem(self, dem, force_flow="NORMAL"):
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
        flow_direction_raster = self._so("flowdir","random","fgdb")
        flowdir = FlowDirection(in_surface_raster=dem, force_flow=force_flow)
        flowdir.save(flow_direction_raster)
        
        # calculate slope for the whole DEM
        slope = Slope(in_raster=dem, output_measurement="PERCENT_RISE", method="PLANAR")
        slope_raster = self._so("slope","random","fgdb")
        slope.save(slope_raster)

        return {
            "flow_direction_raster": flow_direction_raster,
            "slope_raster": slope_raster,
        }


    # --------------------------------------------------------------------------
    # Analytics for delineation and data derivation in Parallel
    # Used for *culvert* analysis; works with multiple overlapping watershed 
    # rasters, where each raster contains only a single watershed

    @staticmethod
    def _calc_rainfall_avg(rr, table_rainfall_avg, one_shed_filepath, raster_field):


        # self.msg(f"...{rr['freq']} year")
        print(f"...{rr['freq']} year")
        # print(rr)
        
        rrr = Raster(rr['path'])

        # calculate the average rainfall for the watershed
        with EnvManager(
            cellSizeProjectionMethod="CONVERT_UNITS",
            extent="MINOF",
            cellSize="MINOF",
            overwriteOutput=True,
            # parallelProcessingFactor='100%'
        ):
            args = [
                Raster(one_shed_filepath),
                raster_field,
                rrr,
                table_rainfall_avg,
                "DATA",
                "MEAN"                        
            ]
            # self.msg(f"DEBUG: {args}")
            ZonalStatisticsAsTable(*args)

        rainfall_stats = json.loads(RecordSet(table_rainfall_avg).JSON)

        # rainfall_units = "inches"

        if len(rainfall_stats['features']) > 0:
            # there shouldn't be multiple polygon features here, but this 
            # willhandle edge cases:
            means = [f['attributes']['MEAN'] for f  in rainfall_stats['features']]
            avg_rainfall = mean(means)
            # NOAA Atlas 14 precip values are in 1000ths/inch, 
            # converted to inches using Pint:
            # avg_rainfall = units.Quantity(f'{avg_rainfall}/1000 {rainfall_units}').m
        else:
            avg_rainfall = None

        return dict(
            freq=rr['freq'], 
            dur='24hr', 
            value=avg_rainfall
        )

    def _delineate_and_analyze_one_catchment(
        self,
        point_geodata: FeatureSet,
        uid: str,
        group_id: str,
        flow_direction_raster: str,
        flow_length_raster: str,
        slope_raster: str,
        curve_number_raster: str,
        out_shed_polygon: str,
        rainfall_rasters: tuple = None,
        out_catchment_polygons_simplify: bool = False,
        save_featureset: bool = True,
        pour_point_field: str = None,
        use_multiprocessing: bool = False
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
        # fprops = fs['features'][0]['attributes']
        shed = Shed(
            # uid=fprops['uid'],
            # group_id=fprops['group_id'],
            uid=uid,
            group_id=group_id
        )


        desc_flowdir = Describe(flow_direction_raster)
        try:
            # get the crs units from the spatial ref object
            flowdir_crs_unit = desc_flowdir.spatialReference.linearUnitName.lower()
        except:
            self.msg("Unable to get units from input raster. Falling back to meters.", arc_status="warning")
            flowdir_crs_unit = "meter"

        # self.msg(f"DEBUG: raster spatial reference wkid: {desc_flowdir.spatialReference.factoryCode}")

        ## ---------------------------------------------------------------------
        # DELINEATION & CONVERSION
        with Timer(name="delineating catchment", text="{name}: {:.1f} seconds", logger=self.msg):
            self.msg('delineating catchment')
            with EnvManager(
                snapRaster=flow_direction_raster,
                cellSize=flow_direction_raster,
                extent=desc_flowdir.extent, #"MAXOF"
                parallelProcessingFactor='100%'
            ):
                # delineate one watershed
                
                one_shed = Watershed(
                    in_flow_direction_raster=flow_direction_raster,
                    in_pour_point_data=point_geodata,
                )
                
                shed.filepath_raster = self._so("shed_{}_delineation".format(shed.uid))
                # print(shed.filepath_raster)
                one_shed.save(shed.filepath_raster)

        ## ---------------------------------------------------------------------
        # convert raster to polygon
        with Timer(name="vectorizing catchment", text="{name}: {:.1f} seconds", logger=self.msg):
        
            self.msg("vectorizing catchment")
            
            #ZonalGeometryAsTable(catchment_areas,"Value","output_table") # crashes like a mfer
            #cp = self.so("catchmentpolygons","timestamp","fgdb")
            cp = self._so("shed_{}_polygon".format(shed.uid))
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
                shed.filepath_vector = self._so("shed_{}_dissolved".format(shed.uid), where="fgdb")
                # print(shed.filepath_vector)
            
            Dissolve(
                in_features=cp,
                out_feature_class=shed.filepath_vector,
                dissolve_field="gridcode",
                multi_part="MULTI_PART"
            )            
        
        ## ---------------------------------------------------------------------
        # ANALYSIS

        ## ---------------------------------------------------------------------
        # calculate area of catchment

        with Timer(name="calculating area", text="{name}: {:.1f} seconds", logger=self.msg):

            self.msg("calculating area")

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
        # calculate average rainfall for each storm frequency

        with Timer(name="calculating average rainfall", text="{name}: {:.1f} seconds", logger=self.msg):
                    
            self.msg('calculating average rainfall')

            # if use_multiprocessing:

            #     with WorkerPool() as pool:
            #         results = pool.map(
            #             self._calc_rainfall_avg,
            #             [
            #                 (
            #                     rr, 
            #                     self._so("shed_{0}_rain_avg_{1}".format(shed.uid, rr['freq'])),
            #                     shed.filepath_raster,
            #                     self.raster_field
            #                 ) 
            #                 for rr in rainfall_rasters
            #             ]
            #         )
            #     rainfalls = [Rainfall(**result) for result in results] 

            # else:
            rainfalls = []
            # for each rainfall raster representing a storm frequency:
            for rr in rainfall_rasters:

                self.msg(f"...{rr['freq']} year")
                # print(rr)

                table_rainfall_avg = self._so(
                    "shed_{0}_rain_avg_{1}".format(shed.uid, rr['freq']),
                )
                
                rrr = Raster(rr['path'])

                # calculate the average rainfall for the watershed
                with EnvManager(
                    cellSizeProjectionMethod="CONVERT_UNITS",
                    extent="MINOF",
                    cellSize="MINOF",
                    overwriteOutput=True,
                    # parallelProcessingFactor='100%'
                ):
                    args = [
                        one_shed,
                        self.raster_field,
                        rrr,
                        table_rainfall_avg,
                        "DATA",
                        "MEAN"                        
                    ]
                    # self.msg(f"DEBUG: {args}")
                    ZonalStatisticsAsTable(*args)

                rainfall_stats = json.loads(RecordSet(table_rainfall_avg).JSON)

                # rainfall_units = "inches"

                if len(rainfall_stats['features']) > 0:
                    # there shouldn't be multiple polygon features here, but this 
                    # willhandle edge cases:
                    means = [f['attributes']['MEAN'] for f  in rainfall_stats['features']]
                    avg_rainfall = mean(means)
                    # NOAA Atlas 14 precip values are in 1000ths/inch, 
                    # converted to inches using Pint:
                    # avg_rainfall = units.Quantity(f'{avg_rainfall}/1000 {rainfall_units}').m
                else:
                    avg_rainfall = None

                # self.msg(rr['freq'], "year event:", avg_rainfall)
                rainfalls.append(
                    Rainfall(
                        freq=rr['freq'], 
                        dur='24hr', 
                        value=avg_rainfall
                        # units=rainfall_units
                    )
                )
                
            
            shed.avg_rainfall = sorted(rainfalls, key=lambda x: x.freq)

        
        ## ---------------------------------------------------------------------
        # calculate flow length

        with Timer(name="calculating flow length", text="{name}: {:.1f} seconds", logger=self.msg):

            
            
            with EnvManager(
                snapRaster=flow_direction_raster,
                cellSize=flow_direction_raster,
                overwriteOutput=True,
                extent=one_shed.extent,
                parallelProcessingFactor='100%'
            ):

                # Use the input flow length raster here if provided. Clip it to 
                # the shed and calculate max as raster max minus raster min. 
                # This saves a ton of time over deriving the flow length raster.
                if flow_length_raster:
                    self.msg("calculating flow length (using provided flow length raster)")
                    clipped_flowlen = SetNull(IsNull(one_shed), Raster(flow_length_raster))
                    desc_flowflen = Describe(flow_length_raster)
                    try:
                        # get the crs units from the spatial ref object
                        flowlen_crs_unit = desc_flowflen.spatialReference.linearUnitName.lower()
                    except:
                        self.msg("Unable to get units from input flow length raster. Falling back to meters.", arc_status="warning")
                        flowlen_crs_unit = "meter"
                    max_fl = clipped_flowlen.maximum - clipped_flowlen.minimum
                    shed.max_fl = units.Quantity(max_fl, flowlen_crs_unit).m_as("meter")
                
                # otherwise, generate a flow length raster for the shed and get 
                # its maximum value
                else:
                    self.msg("calculating flow length for catchment area")
                    # clip the flow direction raster to the catchment area (zone value)
                    clipped_flowdir = SetNull(IsNull(one_shed), Raster(flow_direction_raster))

                    Raster(clipped_flowdir).save(
                        self._so("shed_{0}_clipped_flowdir".format(shed.uid))
                    )
                    
                    # calculate flow length
                    flow_len_raster = FlowLength(clipped_flowdir, "UPSTREAM")
                    # determine maximum flow length
                    #shed.max_fl = flow_len_raster.maximum
                    #TODO: convert length to ? using leng_conv_factor (detected from the flow direction raster)
                    #fl_max = fl_max * leng_conv_factor
                    if flow_len_raster.maximum:
                        shed.max_fl = units.Quantity(flow_len_raster.maximum, flowdir_crs_unit).m_as("meter")
                    else:
                        shed.max_fl = 0

        ## ---------------------------------------------------------------------
        # calculate average slope

        with Timer(name="calculating average slope", text="{name}: {:.1f} seconds", logger=self.msg):

            self.msg("calculating average slope")
            
            table_slope_avg = self._so("shed_{0}_slope_avg".format(shed.uid))

            # debugging
            # sloped = Describe(Raster(slope_raster))
            # sloped.
            
            with EnvManager(
                cellSizeProjectionMethod="PRESERVE_RESOLUTION",
                extent="MINOF",
                cellSize=one_shed,
                overwriteOutput=True,
                parallelProcessingFactor='100%'
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
        # calculate average curve number

        with Timer(name="calculating average curve number", text="{name}: {:.1f} seconds", logger=self.msg):

            self.msg("calculating average curve number")
            
            table_cn_avg = self._so("shed_{0}_cn_avg".format(shed.uid))

            rcn = Raster(curve_number_raster)

            with EnvManager(
                # cellSizeProjectionMethod="PRESERVE_RESOLUTION",
                extent="MINOF",
                cellSize=rcn.meanCellWidth,
                overwriteOutput=True,
                parallelProcessingFactor='100%'
            ):
                ZonalStatisticsAsTable(
                    one_shed,
                    self.raster_field,
                    rcn,
                    table_cn_avg, 
                    "DATA",
                    "MEAN"
                )
                cn_stats = json.loads(RecordSet(table_cn_avg).JSON)
                

                if len(cn_stats['features']) > 0:
                    # in the event we get more than one record here, we avg the avg
                    means = [f['attributes']['MEAN'] for f in cn_stats['features']]
                    shed.avg_cn = mean(means)
        

        #-----------------------------------------------------------------------
        # add all derived properties to the vector file output

        with Timer(name="saving delineation features", text="{name}: {:.1f} seconds", logger=self.msg):
            
            # self.msg('saving delineation features')

            with EnvManager(overwriteOutput=True):
                
                # spec the fields to add
                fields_to_add = [
                    ['uid', 'TEXT', shed.uid],
                    ['group_id', 'TEXT', shed.group_id],
                    ['area_sqkm', 'FLOAT', shed.area_sqkm],
                    ['avg_slope_pct', 'FLOAT', shed.avg_slope_pct],
                    ['avg_cn', 'FLOAT', shed.avg_cn],
                    ['max_fl', 'FLOAT', shed.max_fl]
                ]
                # we flatten the rainfall array into table columns
                for r in shed.avg_rainfall:
                    fields_to_add.append([
                        f'avg_rain_{r.freq}y_{r.dur}', 'FLOAT', r.value
                    ])

                # add the fields
                AddFields_management(
                    shed.filepath_vector,
                    [[f[0], f[1]] for f in fields_to_add]
                )
                # add the values to the fields
                CalculateFields(
                    in_table=shed.filepath_vector,
                    expression_type="PYTHON3",
                    fields=[
                        [f[0], '{}'.format(f[2])] for f in fields_to_add] # note the quotation syntax here
                )

        #-----------------------------------------------------------------------
        # add the shed feature(s) to the shed model instance
        if save_featureset:
            shed.shed_geom = json.loads(FeatureSet(shed.filepath_vector).JSON)

        return shed

    @staticmethod
    def _delineation_and_analysis_in_parallel_job(
        cls,
        point: dict,
        pour_point_field: str,
        flow_direction_raster: str,
        flow_length_raster: str,
        slope_raster: str,
        curve_number_raster: str,
        precip_src_config: dict,
        out_shed_polygons_simplify: bool = False,
        override_skip: bool = False
    ):

        point = DrainItPointSchema().load(point)

        if not override_skip and not point.include:

            

            # create a FeatureSet for each individual Point object
            # this lets us keep our Point objects around while feeding
            # the GP tools a native input format.
            point_geodata = cls.create_geodata_from_points([point], as_dict=False)

            # delineate a catchment/basin/watershed ("shed") and derive 
            # some data from that, storing it in a Shed object.
            shed = cls._delineate_and_analyze_one_catchment(
                cls,
                uid=point.uid,
                group_id=point.group_id,
                point_geodata=point_geodata,
                pour_point_field=pour_point_field,
                flow_direction_raster=flow_direction_raster,
                flow_length_raster=flow_length_raster,
                slope_raster=slope_raster,
                curve_number_raster=curve_number_raster,
                rainfall_rasters=precip_src_config['rasters'],
                out_shed_polygon=None,
                out_catchment_polygons_simplify=out_shed_polygons_simplify
            )

            point.shed = shed

        return DrainItPointSchema().dump(point)

    def delineation_and_analysis_in_parallel(
        self,
        points: List[DrainItPoint],
        pour_point_field: str,
        flow_direction_raster: str,
        flow_length_raster: str,
        slope_raster: str,
        curve_number_raster: str,
        precip_src_config: dict,
        out_shed_polygons: str = None,
        out_shed_polygons_simplify: bool = False,
        override_skip: bool = False,
        use_multiprocessing: bool = False,
        clear_memory_workspace: bool = True
        ) -> Tuple[DrainItPoint]:

        shed_geodata = []

        # if use_multiprocessing:

        #     args = [
        #         (
        #             DrainItPointSchema().dump(p),
        #             pour_point_field,
        #             flow_direction_raster,
        #             flow_length_raster,
        #             slope_raster,
        #             curve_number_raster,
        #             precip_src_config,
        #             out_shed_polygons,
        #             out_shed_polygons_simplify,
        #             override_skip
        #         )
        #         for p in points
        #     ]
            
        #     with WorkerPool() as pool:
        #         results = pool.map(
        #             self._delineation_and_analysis_in_parallel_job,
        #             args
        #         )

        #     # new points list created here:
        #     points = []
        #     for point in results:
        #         pt = DrainItPointSchema().load(point)
        #         points.append(pt)
        #         shed_geodata.append(pt.shed.filepath_vector)

        # else:

        # for each Point in the input points list
        # for point in tqdm(points):
        for point in points:

            self.msg("--------------------------------")
            

            # if point is marked as not include and override_skip is false,
            # skip this iteration.
            if not override_skip and not point.include:
                continue
            
            self.msg("Analyzing point {0} | group {1}".format(point.uid, point.group_id))
            # with Timer(name="Analyzing point {0} | group {1}".format(point.uid, point.group_id), text="{name}: {:.1f} seconds", logger=self.msg):
            # create a FeatureSet for each individual Point object
            # this lets us keep our Point objects around while feeding
            # the GP tools a native input format.
            # desc_flowdir = Describe(flow_direction_raster)
            point_geodata = self.create_geodata_from_drainitpoints([point], as_dict=False) #, output_crs_wkid=desc_flowdir.spatialReference.factoryCode)
            # self.msg(point_geodata)

            # delineate a catchment/basin/watershed ("shed") and derive 
            # some data from that, storing it in a Shed object.
        
            shed = self._delineate_and_analyze_one_catchment(
                uid=point.uid,
                group_id=point.group_id,
                point_geodata=point_geodata,
                pour_point_field=pour_point_field,
                flow_direction_raster=flow_direction_raster,
                flow_length_raster=flow_length_raster,
                slope_raster=slope_raster,
                curve_number_raster=curve_number_raster,
                rainfall_rasters=precip_src_config['rasters'],
                out_shed_polygon=None,
                out_catchment_polygons_simplify=out_shed_polygons_simplify,
                use_multiprocessing=use_multiprocessing
            )

            # save that to the Point object
            point.shed = shed
            shed_geodata.append(shed.filepath_vector)

            if clear_memory_workspace:
                Delete('memory')
            
        # merge the sheds into a single layer
        if out_shed_polygons:
            Merge(shed_geodata, out_shed_polygons)

        # return all updated Point objects, which includes nested shed data
        return points
