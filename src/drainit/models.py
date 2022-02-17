from typing import List, Optional, Union
import pint
from dataclasses import dataclass, field, asdict, fields
from marshmallow import EXCLUDE, pre_load
from marshmallow_dataclass import class_schema

from .calculators.runoff import Runoff, time_of_concentration_calculator
from .calculators.capacity import Capacity
from .calculators.overflow import Overflow, max_return_calculator

units = pint.UnitRegistry()

# ------------------------------------------------------------------------------
# HELPERS

def req_field(): 
    """shortcut to create a marshmallow-dataclass required field
    """
    return field(metadata=dict(required=True))

def cast_to_numeric_fields(data, dataclass_model, **kwargs):
    """when loading or validating, attempt to cast numbers from strings based on the model field types."""
    numeric_fields = {k: v.type for k, v in dataclass_model.__dataclass_fields__.items() if v.type in [int, float]}
    # for each numeric field name and type
    for fld, typ in numeric_fields.items():
        # if the field is present in the data being serialized:
        if fld in data.keys():
            # if the value (data) being serialized isn't of the type spec'd in the
            # dataclasse, and the data isn't empty:
            if not isinstance(data[fld], typ) and data[fld] is not None:
                #print(data[fld], type(data[fld]), isinstance(data[fld], typ), type(data[fld]) is not None)
                # try to cast the value to the spec'd data type
                try:
                    data[fld] = typ(data[fld])
                # If it can't be cast to the numeric type, then leave it.
                # The record will fail validation.
                except ValueError as e:
                    #print(e, fld, data[fld])
                    pass
    return data

def cast_fields(data, dataclass_model, **kwargs):
    """when loading or validating, attempt to cast values to their spec'd types."""
    ftypes = {}
    # create a lookup of fields grouped by type
    for d in [dict(n=f.name, t=f.type) for f in fields(dataclass_model)]:
        ftypes.setdefault(d['t'], []).append(d['n'])
    # handle any of the fields are not type (like a Union)
    for k in [t for t in ftypes.keys() if type(t) is not type]:
        # filter out the NoneTypes
        types = [x for x in k.__args__ if x != type(None)]
        # get the first type spec'd
        if len(types) > 0:
            # replace the item in ftypes
            t = types[0]
            v = ftypes.pop(k)
            ftypes[t] = v

    for ftype, flds in ftypes.items():
        for fld in flds:
            # if the field is present in the data being serialized:
            if fld in data.keys():
                # if the value (data) being serialized isn't of the type spec'd in the
                # dataclasse, and the data isn't empty:
                if not isinstance(data[fld], ftype) and data[fld] is not None:
                    #print(data[fld], type(data[fld]), isinstance(data[fld], typ), type(data[fld]) is not None)
                    # try to cast the value to the spec'd data type
                    try:
                        data[fld] = ftype(data[fld])
                    # If it can't be cast to the numeric type, then leave it.
                    # The record will fail validation.
                    except ValueError as e:
                        #print(e, fld, data[fld])
                        pass
    return data    

# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# DATA MODELS + SCHEMAS


# -------------------------------------
# RAINFALL DATA REFERENCE
# Rainfall data comes in up to 10 rasters from NOAA. Rather than
# force the end-user to provide 10 file inputs or a folder, we store information
# about each raster (RainfallRaster) in a config object, RainfallRasterConfig,
# that is written out to a JSON file.

@dataclass
class RainfallRaster:
    """Store a reference on disk to a NOAA Rainfall raster. NOAA Rainfall data 
    comes as 1000ths of an inch.
    TODO: Optionally, supply a constant value via `const`, which will be used 
    in place of a raster.
    
    """

    path: Optional[str] = None
    freq: int = None
    ext: str = None
    const: Optional[float] = None
    units: Optional[str] = "inches / 1000"

RainfallRasterSchema = class_schema(RainfallRaster)


@dataclass
class RainfallRasterConfig:
    """store rainfall download metadata with methods for portability
    """

    root: str = None
    rasters: List[RainfallRaster] = field(default_factory=list)

    # def read(self, f):
    #     with open(f) as fp:
    #        RainfallRasterConfigSchema().load(json.load(fp))
    #     return
    
    # def write(self, fp):
    #     return        

RainfallRasterConfigSchema = class_schema(RainfallRasterConfig)

# -------------------------------------
# ANALYSIS RESULTS

@dataclass
class Rainfall:
    """Rainfall amounts stored by storm frequency and duration interval.
    NOAA Rainfall data comes as 1000ths of an inch.
    """

    freq: str = None
    dur: str = None
    value: float = None
    valtyp: Optional[str] = "mean"
    units: Optional[str] = "inches / 1000"


@dataclass
class Analytics:
    """analytics--runoff and overflow--for a given rainfall storm frequency and duration interval
    """
    # rainfall 
    frequency: str = None
    duration: str = None
    avg_rainfall_cm: float = None
    # analytics
    peakflow: Optional[Runoff] = None
    overflow: Optional[Overflow] = None

AnalyticsSchema = class_schema(Analytics)

# -------------------------------------
# LOCATION TYPES

 
@dataclass
class NaaccCulvert:
    """NAACC model for a single culvert. Use primarily for validating and 
    type-casting incoming NAACC CSVs.
    
    NOTE: this is the subset of available NAACC fields required for capacity 
    modeling
    """

    Naacc_Culvert_Id: Union[str, int] = req_field() # 'field_short': 'NAACC_ID'
    Survey_Id: Union[str, int] = req_field() # 'field_short': 'Survey_ID'

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
    
    Road: Optional[str] = None # 'field_short': 'Rd_Name'
    Crossing_Comment: Optional[str] = None # 'field_short': 'Comments'

    # TODO: eventually include the date/time capture from the NAACC model here 
    # so that we can filter multiple surveys for a single location.

    # @pre_load
    # def cast_numeric_fields(self, data, **kwargs):
    #     """when loading or validating, attempt to cast numbers from strings before checking."""
    #     return cast_to_numeric_fields(data, NaaccCulvert, **kwargs)
    @pre_load
    def cast_fields(self, data, **kwargs):
        return cast_fields(data, NaaccCulvert, **kwargs)
    
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
    uid: Optional[str] = None
    
    # a group id field. non-unique ID field that indicates groups of related
    # outlets. Used primarily for NAACC-based culvert modeling, this is the
    # NAACC Survey_Id field
    group_id: Optional[str] = None

    # characteristics used for calculating peak flow
    area_sqkm: Optional[float] = None# <area of inlet's catchment in square km>
    avg_slope_pct: Optional[float] = None # <average slope of DEM in catchment>
    avg_cn: Optional[float] = None # <average curve number in the catchment>
    max_fl: Optional[float] = None # <maximum flow length in the catchment>
    avg_rainfall: Optional[List[Rainfall]] = field(default_factory=list) # <average rainfall in the catchment>

    # derived attributes
    tc_hr: Optional[float] = None # time of concentration for runoff in the shed

    # geometries
    inlet_geom: Optional[str] = None
    shed_geom: Optional[str] = None
    
    # for recording the location of intermediate geospatial output files
    filepath_raster: Optional[str] = None
    filepath_vector: Optional[str] = None

    def calculate_tc(self):
        if self.avg_slope_pct and self.max_fl:
            self.tc_hr = time_of_concentration_calculator(self.max_fl, self.avg_slope_pct)
            return self.tc_hr

ShedSchema = class_schema(Shed)


@dataclass
class DrainItPoint:
    """Basic model for points used as source delineations for peak-flow-calcs;
    minimal attributes required.
    """

    # unique id field, derived from the outlet point; the value from the
    # "pour_point_field". For NAACC-based culvert modeling, this is the
    # NAACC `Naacc_Culvert_Id` field...though some NAACC data doesn't
    # have this, so it has to be optional.
    uid: Optional[str]

    # geometry
    lat: float = None
    lng: float = None
    spatial_ref_code: int = None

    # a group id field. non-unique ID field that indicates groups of related
    # outlets. Used primarily for NAACC-based culvert modeling, this is the
    # NAACC `Survey_Id` field
    group_id: Optional[str] = None

    # optionally extend with NAACC attributes
    naacc: Optional[NaaccCulvert] = None

    # ---------------------------------
    ## analytics

    # the flow capacity of the culvert feature. auto-derived for NAACC data.
    capacity: Optional[Capacity] = None

    # Attributes of the area delineated upstream of the point.
    # Includes average rainfall per storm event.
    shed: Optional[Shed] = None

    # Rainfall frequency-based analytical results for the point:
    # runoff (peak-flow) and overflow (peak-flow vs capacity)
    analytics: Optional[List[Analytics]] = field(default_factory=list)

    # flags, errors, and notes
    include: bool = True
    validation_errors: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    # place to optionally store the raw input
    raw: Optional[dict] = None


    def derive_rainfall_analytics(self):
        """Derive an initial calculator results object using the 
        geographically-derived data from the shed.

        # NOTE: !!!
        # NOAA Atlas 14 precip values are in 1000ths/inch, converted to 
        # centimeters **here** using Pint
        # TODO: put the unit conversion somewhere else

        """
        if not self.shed:
            return
        # copy rainfall analytics 
        for r in self.shed.avg_rainfall:
            if r.value:
                avg_rainfall_cm = units.Quantity(f'{r.value} {r.units}').m_as('cm')
            else:
                avg_rainfall_cm = 0
            self.analytics.append(Analytics(
                duration=r.dur,
                frequency=r.freq,
                avg_rainfall_cm=avg_rainfall_cm
            ))
    
    def calculate_summary_analytics(self):
        """derive additional analytics once all others are calculated
        """
        if self.capacity and self.analytics:
            freqs = []
            ovfs = []
            for r in self.analytics:
                freqs.append(r.frequency)
                if r.overflow:
                    ovfs.append(r.overflow.crossing_overflow_m3s)
                else:
                    ovfs.append(None)
            self.capacity.max_return_period = max_return_calculator(ovfs, freqs)

DrainItPointSchema = class_schema(DrainItPoint)

# ------------------------------------------------------------------------------
# WORKFLOW MODELS

@dataclass
class WorkflowConfig:
    """Store all parameters required for any of our model runs.
    """

    # directories
    work_dir: Optional[str] = None

    # -----------------------------
    # input points (culverts or catch-basins)

    # filepath to source data
    points_filepath: str = None
    # in-memory representation of that source data; format depends on GP service
    points_features: Optional[dict] = field(default_factory=dict)
    points_id_fieldname: Optional[str] = None
    points_group_fieldname: Optional[str] = None
    points_spatial_ref_code: Optional[int] = None
    
    # -----------------------------
    # input landscape rasters

    # optional
    raster_dem_filepath: Optional[str] = None
    raster_watershed_filepath: Optional[str] = None
    raster_flowlen_filepath: Optional[str] = None

    # required
    raster_flowdir_filepath: str = None
    raster_slope_filepath: str = None
    raster_curvenumber_filepath: str = None
    

    # --------------------------
    # input rainfall

    precip_src_config_filepath: Optional[str] = None
    precip_noaa_csv_filepath: Optional[str] = None

    precip_src_config: Optional[RainfallRasterConfig] = None

    # --------------------------
    # analysis parameters
    
    area_conv_factor: float = 0.00000009290304
    leng_conv_factor: float = 1

    sheds_simplify: bool = False

    # --------------------------
    # file output parameters
    output_points_filepath: Optional[str] = None
    output_sheds_filepath: Optional[str] = None

    # --------------------------
    # intermediate and internal data
    all_sheds_raster: Optional[str] = None
    all_sheds_vector: Optional[str] = None

    # List of Points for this workflow.
    # A Point optionally has its associated "Shed" object nested internally
    points: Optional[List[DrainItPoint]] = field(default_factory=list)
    # List of Sheds generated for this workflow. Each shed is associated with 
    # a point on the `uid` attribute.
    # sheds: Optional[List[Shed]] = field(default_factory=list)


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

@dataclass
class PeakFlow:
# class PeakFlow01Schema(Schema):

    points_filepath: str
    # points_features = fields.Dict()
    points_id_fieldname: str
    raster_curvenumber_filepath: str
    precip_src_config_filepath: str
    raster_dem_filepath: str
    basins_in_series: bool

    output_points_filepath: str
    output_basins_filepath: Optional[str]

    class Meta:
        unknown = EXCLUDE

PeakFlow01Schema = class_schema(PeakFlow)