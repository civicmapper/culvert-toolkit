import math
from typing import Optional, Union
from dataclasses import dataclass, field, fields
from marshmallow import EXCLUDE
from marshmallow_dataclass import class_schema
import pint

from ..utils import get_type

units = pint.UnitRegistry()


def calc_culvert_capacity(
    culvert_area_sqm, 
    head_over_invert, 
    culvert_depth_m, 
    slope_rr, 
    coefficient_slope=-0.5, 
    coefficient_y=-0.04,
    coefficient_c=0.7, 
    si_conv_factor=1.811
    ):
    """Compute capacity of a culvert.

    Constants c, Y, Ks tabulated, depend on entrance type, from FHWA 
    engineering pub HIF12026, appendix A

    Culvert equation from FHWA Eqn A.3, pg 191.
    Culvert capacity submerged outlet, inlet control (m^3/s)

    :param culvert_area_sqm: internal surface area of the culvert
    :type culvert_area_sqm: float
    :param head_over_invert: Hydraulic head above the culvert invert, meters
    :type head_over_invert: float
    :param culvert_depth_m: Culvert depth. Diameter or dimension b, (height of culvert) meters
    :type culvert_depth_m: float
    :param slope_rr: # slope rise/run (meters)
    :type slope_rr: float    
    :param coefficient_slope: (slope coefficient from FHWA engineering pub HIF12026, appendix A). -0.5, except where inlet is mitered in which case +0.7
    :type coefficient_slope: float
    :param coefficient_y: coefficient based on shape and material from FHWA engineering pub HIF12026
    :type coefficient_y: float    
    :param coefficient_c: coefficient based on shape and material from FHWA engineering pub HIF12026
    :type coefficient_c: float
    :param si_conv_factor: adjustment factor for units (SI=1.811), defaults to 1.811
    :type si_conv_factor: float, optional
    :return: culvert capacity, in cubic meters / second (m^3/s)
    :rtype: float
    """
    
    # Calculate and return the capacity for the culvert
    try:
        capacity = (culvert_area_sqm * math.sqrt(culvert_depth_m * ((head_over_invert / culvert_depth_m) - coefficient_y - coefficient_slope * slope_rr) / coefficient_c)) / si_conv_factor
        # print("capacity", capacity)
        return capacity
    except:
        return None


def req_field(): 
    """shortcut to create a marshmallow-dataclass required field
    """
    return field(metadata=dict(required=True))

@dataclass
class Capacity:
    """Model for culvert capacity. Includes parameters both crosswalked and 
    derived from the NAACC data required for the culvert capacity calculation.
    """

    # ----------------------------
    # Cross-walked attributes:
    # 
    # These are the short names for the subset of fields
    # needed to calculate capacity

    culv_mat: Optional[str] = None
    in_type: Optional[str] = None
    in_shape: Optional[str] = None
    in_a: Optional[float] = None
    in_b: Optional[float] = None
    hw: Optional[float] = None
    slope: Optional[float] = None
    length: Optional[float] = None
    out_shape: Optional[str] = None
    out_a: Optional[float] = None
    out_b: Optional[float] = None
    xing_type: Optional[str] = None
        
    #flags: int = 1

    # ----------------------------
    # derived attributes

    # culvert area (square meters)
    culvert_area_sqm: Optional[float] = None
    # culvert depth (meters)
    culvert_depth_m: Optional[float] = None
    # coefficients based on shape and material from FHWA engineering pub HIF12026, appendix A
    coefficient_c: Optional[float] = 0.04
    coefficient_y: Optional[float] = 0.7
    # slope coefficient from FHWA engineering pub HIF12026, appendix A
    coefficient_slope: Optional[float] = -0.5
    # slope as rise/run
    slope_rr: Optional[float] = None
    #  head over invert by adding dist from road to top of culvert to D 
    head_over_invert: Optional[float] = None

    # comment field
    comments: Optional[str] = None
    # include flag
    include: Optional[bool] = True

    # ---------------------------------
    ## analytics    

    # culvert capacity, in cubic meters / second (m^3/s)
    culvert_capacity: Optional[float] = None
    
    # crossing capacity, in cubic meters / second (m^3/s)
    # this will be the same as culvert_capacity unless
    # this point is part of a group of >= 2 culvert,
    # in which case it will be the sum of all capacities
    # in the group
    crossing_capacity: Optional[float] = None
    
    # max return period / storm frequency that the 
    max_return_period: Optional[float] = None 

    class Meta:
        unknown = EXCLUDE
    
    def calculate(self, si_conv_factor=1.811):
        
        self.culvert_capacity = calc_culvert_capacity(
            culvert_area_sqm=self.culvert_area_sqm, 
            head_over_invert=self.head_over_invert, 
            culvert_depth_m=self.culvert_depth_m, 
            slope_rr=self.slope_rr, 
            coefficient_slope=self.coefficient_slope,
            coefficient_y=self.coefficient_y,
            coefficient_c=self.coefficient_c, 
            si_conv_factor=si_conv_factor
        )
        return self.culvert_capacity

CapacitySchema = class_schema(Capacity)

# helper that creates a lookup of numeric fields, used during crosswalking + validation
CAPACITY_FIELDS_AND_DEFAULTS = [(f.name, f.default) for f in fields(Capacity)]
CAPACITY_NUMERIC_FIELDS = {f.name: get_type(f.type) for f in fields(Capacity) if get_type(f.type) in [int, float]}