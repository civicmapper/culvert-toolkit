from typing import List
import pint
from dataclasses import dataclass, field, asdict
from marshmallow import Schema, fields, EXCLUDE, pre_load
from marshmallow_dataclass import class_schema

units = pint.UnitRegistry()

from ..calculators.runoff import Runoff
from ..calculators.capacity import Capacity
from ..calculators.overflow import Overflow
from ..config import (
    NAACC_HEADER_LOOKUP, 
    NAACC_TYPECASTS_FULLNAME,
    NAACC_INLET_SHAPE_CROSSWALK, 
    NAACC_INLET_TYPE_CROSSWALK
)


# ------------------------------------------------------------------------------
# HELPERS

def req_field(): 
    """shortcut to create a marshmallow-dataclass required field
    """
    return field(metadata=dict(required=True))

def cast_to_numeric_fields(data, dataclass_model, **kwargs):
    """when loading or validating, attempt to cast numbers from strings based on the model field types."""
    numeric_fields = {k: v.type for k, v in dataclass_model.__dataclass_fields__.items() if v.type in [int, float]}
    for fld, typ in numeric_fields.items():
        if fld in data.keys():
            if not isinstance(data[fld], typ) and data[fld] is not None:
                #print(data[fld], type(data[fld]), isinstance(data[fld], typ), type(data[fld]) is not None)
                try:
                    data[fld] = typ(data[fld])
                except ValueError as e:
                    #print(e, fld, data[fld])
                    pass
    return data    

# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# DATA MODELS + SCHEMAS


# -------------------------------------
# RAINFALL

@dataclass
class RainfallRaster:
    """store a reference to a NOAA Rainfall raster
    """

    path: str = None
    freq: int = None
    ext: str = None

RainfallRasterSchema = class_schema(RainfallRaster)


@dataclass
class RainfallRasterConfig:
    """store rainfall download metadata with methods for portability
    """

    root: str = None
    rasters: List[RainfallRaster] = field(default_factory=[])

RainfallRasterConfigSchema = class_schema(RainfallRasterConfig)

# -------------------------------------
# ANALYSIS RESULTS

@dataclass
class Analytics:
    """analysis results from the calculators
    """

    runoff: Runoff = None

    # requires naacc_capacity:
    overflow: Overflow = None 


@dataclass
class Frequency:
    """storm frequency interval with rainfall values and rainfall-dependent 
    analytical results from the calculators
    """    

    year: int = None
    rainfall: float = None
    analytics: Analytics = None

FrequencySchema = class_schema(Frequency)

# -------------------------------------
# LOCATION TYPES

 
@dataclass
class NaaccCulvert:
    """NAACC model for a single culvert. Use primarily for validating and 
    type-casting incoming NAACC CSVs.
    
    NOTE: this is only a subset of available NAACC fields
    """

    Naacc_Culvert_Id: str = req_field() # 'field_short': 'NAACC_ID'
    Survey_Id: str = req_field() # 'field_short': 'Survey_ID'

    GIS_Latitude: float = req_field() # 'field_short': 'Lat'
    GIS_Longitude: float = req_field() # 'field_short': 'Long'        
        
    Number_Of_Culverts: int = req_field() # 'field_short': 'Flags'

    Material: str = req_field() # 'field_short': 'Culv_Mat'
    Inlet_Type: str = req_field() # 'field_short': 'In_Type'
    Inlet_Structure_Type: str = req_field() # 'field_short': 'In_Shape'

    Inlet_Width: float = req_field() # 'field_short': 'In_A'
    Inlet_Height: float = req_field() # 'field_short': 'In_B'
    Road_Fill_Height: float = req_field() # 'field_short': 'HW'
    Slope_Percent: float = req_field() # 'field_short': 'Slope'
    Crossing_Structure_Length: float = req_field() # 'field_short': 'Length'
    Outlet_Structure_Type: str = req_field() # 'field_short': 'Out_Shape'
    Outlet_Width: float = req_field() # 'field_short': 'Out_A'
    Outlet_Height: float = req_field() # 'field_short': 'Out_B'
    Crossing_Type: str = req_field() # 'field_short': 'Crossing_Type'
    
    Road: str = None # 'field_short': 'Rd_Name'
    Crossing_Comment: str = None # 'field_short': 'Comments'


    @pre_load
    def cast_numeric_fields(self, data, **kwargs):
        """when loading or validating, attempt to cast numbers from strings before checking."""
        return cast_to_numeric_fields(data, NaaccCulvert, **kwargs)
    
    class Meta:
        unknown = EXCLUDE    

NaaccCulvertSchema = class_schema(NaaccCulvert)


@dataclass
class NaaccCrossing:
    """a model for representing multiple Culverts NaaccPoints
    """

    crossing_id: str
    culverts: List[NaaccCulvert]

NaaccCrossingSchema = class_schema(NaaccCrossing)


@dataclass
class Shed:
    """Characteristics of a single point's contributing area
    """
    # unique id field, derived from the outlet point; the value from the
    # "pour_point_field". For NAACC-based culvert modeling, this is the
    # NAACC Naacc_Culvert_Id field
    uid: str = None
    
    # a group id field. non-unique ID field that indicates groups of related
    # outlets. Used primarily for NAACC-based culvert modeling, this is the
    # NAACC Survey_Id field
    group_id: str = None

    # characteristics used for calculating peak flow
    area_sqkm: float = None# <area of inlet's catchment in square km>
    avg_slope_pct: float = None # <average slope of DEM in catchment>
    avg_cn: float = None # <average curve number in the catchment>
    max_fl: float = None # <maximum flow length in the catchment>
    rainfall: float = None # average rainfall in the catchment

    # geometries
    inlet_geom: str = None
    shed_geom: str = None
    
    # for recording the location of intermediate geospatial output files
    shed_polygon_filepath: str = None
    shed_raster_filepath: str = None

ShedSchema = class_schema(Shed)


@dataclass
class Point:
    """Basic model for points used as source delineations for peak-flow-calcs;
    minimal attributes required.
    """

    # unique id field, derived from the outlet point; the value from the
    # "pour_point_field". For NAACC-based culvert modeling, this is the
    # NAACC Naacc_Culvert_Id field
    uid: str

    lat: float = None
    lng: float = None

    # a group id field. non-unique ID field that indicates groups of related
    # outlets. Used primarily for NAACC-based culvert modeling, this is the
    # NAACC Survey_Id field
    group_id: str = None

    # optionally extend with NAACC & capacity attributes
    naacc: NaaccCulvert = None
    capacity: Capacity = None

    # optionally extend with the Shed and its characteristics
    shed: Shed = None

    # storm frequency-based analytical results for the point
    analytics: List[Frequency] = field(default_factory=list)

    # flags, errors, and notes
    include: bool = True
    validation_errors: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    # place to store the raw input
    raw: dict = None


PointSchema = class_schema(Point)

# ------------------------------------------------------------------------------
# WORKFLOW MODELS

@dataclass
class WorkflowConfig:
    """Store all parameters required for any of our model runs.
    """

    # directories
    work_dir: str = None

    # -----------------------------
    # input points (culverts or catch-basins)

    # filepath to source data
    points_filepath: str = None
    # in-memory representation of that source data; format depends on GP service
    points_features: dict = None
    points_id_fieldname: str = None
    
    # -----------------------------
    # input landscape rasters

    # optional for peak-flow-calc
    raster_dem_filepath: str = None
    raster_watershed_filepath: str = None

    # required for peak-flow-calc (can be derived)
    raster_flowdir_filepath: str = None
    raster_slope_filepath: str = None
    raster_curvenumber_filepath: str = None

    # --------------------------
    # input rainfall

    precip_src_config_filepath: str = None
    precip_noaa_csv_filepath: str = None

    rainfall_rasters: List[RainfallRaster] = field(default_factory=list)

    # --------------------------
    # analysis parameters
    
    area_conv_factor: float = 0.00000009290304
    leng_conv_factor: float = 1

    basins_simplify: bool = False
    basins_in_series: bool = True

    # --------------------------
    # file output parameters
    output_points_filepath: str = None
    output_basins_filepath: str = None

    # --------------------------
    # intermediate and internal data

    all_basins_raster: str = None
    all_basins_vector: str = None

    points: List[Point] = field(default_factory=list)
    basins: List[Shed] = field(default_factory=list)


WorkflowConfigSchema = class_schema(WorkflowConfig)

# ------------------------------------------------------------------------------
# WORKFLOW SCHEMAS
# Used to ensure the right subset of required inputs are stored in the
# WorkflowConfig by subclasses of workflows.WorkflowManager

# For Peak Flow, inputs are largely the same with exception of DEM sources:

# workflow 01
# dem_raster

# workflow 02
# flow_dir_raster
# slope_raster

# workflow 03
# input_watershed_raster

class PeakFlow01Schema(Schema):

    points_filepath = fields.Str(required=True) # inlets
    # points_features = fields.Dict()
    points_id_fieldname = fields.Str(required=True) # pour_point_field
    raster_curvenumber_filepath = fields.Str(required=True) # cn_raster
    precip_src_config_filepath = fields.Str(required=True) # precip_data
    raster_dem_filepath = fields.Str(required=True)
    basins_in_series = fields.Bool(default=True)

    output_points_filepath = fields.Str(required=True) # output
    output_basins_filepath = fields.Str() # output_catchments

    class Meta:
        unknown = EXCLUDE