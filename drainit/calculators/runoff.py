import math
from collections import OrderedDict
from typing import Tuple
# dependencies
import numpy
import math
import pint
from dataclasses import dataclass

units = pint.UnitRegistry()

def time_of_concentration_calculator(
    max_flow_length, #units of meters
    mean_slope_pct, # percent slope
    const_a=0.000325,
    const_b=0.77,
    const_c=-0.385
    ) -> float:
    """
    calculate time of concentration (hourly)

    Inputs:
        - max_flow_length: maximum flow length of a catchment area, derived
            from the DEM for the catchment area.
        - mean_slope: average slope, from the DEM *for just the catchment area*. This must be
        percent slope, provided as an integer (e.g., 23, not 0.23)

    Outputs:
        tc_hr: time of concentration (hourly)
    """
    if not mean_slope_pct:
        mean_slope_pct = 0.00001
    tc_hr = const_a * math.pow(max_flow_length, const_b) * math.pow((mean_slope_pct / 100), const_c)
    return tc_hr

def time_of_concentration_calculator_simple(
    min_elevation,
    max_elevation,
    max_flow_length,
    const_a=0.000325,
    const_b=0.77,
    const_c=-0.385
    ) -> float:
    """
    Thhis equation is from Cornell's ArcMap Field Calculator-based implementation
    
    """
    return const_a * math.pow(max_flow_length, const_b) * math.pow( ((max_elevation - min_elevation) / max_flow_length), const_c)

def peak_flow_calculator_via_precip_table(
    catchment_area_sqkm,
    tc_hr,
    avg_cn,
    precip_table,
    init_abstraction=0.2
    ) -> OrderedDict:
    """Calculate peak runoff statistics at a "pour point" (e.g., a stormwater
    inlet, a culvert, or otherwise a basin's outlet of some sort) using
    parameters dervied from prior analysis of that pour point's catchment 
    area (i.e., it's watershed or contributing area) and *24-hour* precipitation 
    estimates.

    Note that the TR-55 methodology is designed around a 24-hour storm *duration*. 
    YMMV if providing rainfall estimates (via the precip_table parameter) for 
    other storm durations.
    
    This calculator by default returns peak flow for storm *frequencies* 
    ranging from 1 to 1000 year events.
    
    Inputs:
        - catchment_area_sqkm: area measurement of catchment in *square kilometers*
        - tc_hr: hourly time of concentration number for the catchment area
        - avg_cn: average curve number for the catchment area
        - precip_table: precipitation estimates derived from standard NOAA 
            Preciptation Frequency Estimates. Values in centimeters. Provided
            as a dictionary, where keys are the frequency labels (e.g., P100)
            are the keys and the values are rainfall, in centimeters. Example:
                {"P1": <rainfall>, "P2": <rainfall>, ...}
        - init_abstraction: percent of rainfall that never has a chance to
            become runoff.
    
    Outputs:
        - runoff: a dictionary indicating peak runoff at the pour point for
        storm events by frequency
    """

    # ensure that the precip_table maintains its ordering
    precip_table = OrderedDict(precip_table)

    # extract the header and values from the precip table
    qp_header = list(precip_table.keys())
    P = numpy.array(precip_table.values()) #values in P must be in cm
    
    # Skip calculation altogether for these conditions
    # if curve number or time of concentration are 0.
    if any([
        avg_cn in [0,'',None],
        tc_hr in [0,'',None],
        catchment_area_sqkm < 0.01
    ]):
        if avg_cn in [0,'',None] or tc_hr in [0,'',None]:
            qp_data = [0 for i in range(0,len(qp_header))]
            return OrderedDict(zip(qp_header, qp_data))

    # calculate storage, S in cm
    Storage = 0.1 * ((25400.0 / avg_cn) - 254.0) #cm
    # inital abstraction, amount of precip that never has a chance to become 
    # runoff, as cm
    Ia = init_abstraction * Storage # cm

    # calculate depth of runoff from each storm
    # if P < Ia NO runoff is produced
    Pe = (P - Ia)
    Pe = numpy.array([0 if i < 0 else i for i in Pe]) # get rid of negative Pe's
    Q = (Pe**2) / (P + (Storage - Ia)) # cm
    
    # calculate q_peak, cubic meters per second
    # q_u is an adjustment based on Tc.
    # The relationship was found by Jo Archibald 2019
    # Note - the relationship for return interval = 1 year is derived from 2-year information
    # the 1-year results were unreliable from USGS data-derived P-3 curves

    # keep rain ratio within limits set by TR55
    Const0 = numpy.array([2.798, 2.798, 3.225, 3.529, 3.932, 4.244, 4.57, 4.914, 5.403])
    Const1 = numpy.array([0.367, 0.367, 0.481, 0.559, 0.658, 0.733, 0.81, 0.888, 0.996])

    qu = (Const0 - Const1 * tc_hr) / 8.64
    qu = numpy.array([0.14 if i < 0.14 else i for i in qu]) # prevents peak flow being less than 1.2x daily flow
    # qu would have to be m^3/s per km^2 per cm :
    # / 8.64 creates those units from a unitless value
    #qu has weird units which take care of the difference between Q in cm and area in km2

    q_peak = Q * qu * catchment_area_sqkm #m^3/s
    # Q_daily = Q * catchment_area_sqkm *10000/(3600*24)   # updated 6/3/2019 for cms units
    
    # zip up the results with the header
    results = OrderedDict(zip(qp_header,q_peak))

    return results

def qpeak_via_rain_ratio_method1(
    init_abstraction, 
    avg_rainfall_cm, 
    tc_hr, 
    Q, 
    basin_area_sqkm
    ) -> float:
    """RAIN RATIO: Method from the original Cornell Culvert model (v1).
    Works for *n* number of rainfall frequencies.
    """

    # calculate q_peak, cubic meters per second
    # q_u is an adjustment because these watersheds are very small. It is a function of tc_hr,
    # and constants Const0, Const1, and Const2 which are in turn functions of Ia/P (rain_ratio) and rainfall type
    # We are using rainfall Type II because that is applicable to most of New York State
    # rain_ratio is a vector with one element per input return period
    rain_ratio = init_abstraction / avg_rainfall_cm
    rain_ratio = [.1 if i < .1 else .5 if i > .5 else i for i in [rain_ratio]][0] # keep rain ratio within limits set by TR55
    
    CONST_0 = (rain_ratio**2) * -2.2349 + (rain_ratio * 0.4759) + 2.5273
    CONST_1 = (rain_ratio**2) * 1.5555 - (rain_ratio * 0.7081) - 0.5584
    CONST_2 = (rain_ratio**2) * 0.6041 + (rain_ratio * 0.0437) - 0.1761

    # qu has weird units which take care of the difference between Q in cm and area in km2 
    # qu is in m^3 s^-1 km^-2 cm^-1
    qu = 10 ** (CONST_0 + CONST_1 * numpy.log10(tc_hr) + CONST_2 *  (numpy.log10(tc_hr))**2 - 2.366)
    q_peak = Q * qu * basin_area_sqkm # m^3 s^-1

    return q_peak

def qpeak_via_rain_ratio_method2(
    tc_hr, 
    Q,
    basin_area_sqkm,
    const0_values=[2.798, 2.798, 3.225, 3.529, 3.932, 4.244, 4.57, 4.914, 5.403],
    const1_values=[0.367, 0.367, 0.481, 0.559, 0.658, 0.733, 0.81, 0.888, 0.996]
    ) -> float:
    """Rain Ratio: Method 2 from Cornell (v2.1).
    Works for exactly 9 rainfall frequencies: the 1 through 500-year storms.
    """

    #calculate q_peak, cubic meters per second
    # q_u is an adjustment based on Tc.
    # The relationship was found by Jo Archibald 2019
    # Note - the relationship for return interval = 1 year is derived from 2-year information
    # the 1-year results were unreliable from USGS data-derived P-3 curves

    # keep rain ratio within limits set by TR55
    Const0 = numpy.array(const0_values)
    Const1 = numpy.array(const1_values)

    qu = (Const0 - Const1 * tc_hr) / 8.64
    qu = numpy.array([0.14 if i < 0.14 else i for i in qu]) # prevents peak flow being less than 1.2x daily flow
    # qu would have to be m^3/s per km^2 per cm :
    # / 8.64 creates those units from a unitless value

    q_peak = Q * qu * basin_area_sqkm #m^3/s
    #qu has weird units which take care of the difference between Q in cm and area in km2
    # Q_daily = Q * basin_area_sqkm *10000/(3600*24) # updated 6/3/2019 for cms units

    return q_peak

def peak_flow_calculator( 
    mean_slope_pct,
    max_flow_length_m,
    avg_rainfall_cm,
    basin_area_sqkm,
    avg_cn,
    tc_hr=None,
    rain_ratio_method=2
    ) -> Tuple[float, float]:
    """Calculate peak runoff statistics at a "pour point" (e.g., a stormwater
    inlet, a culvert, or otherwise a basin's outlet of some sort) using
    parameters dervied from prior analysis of that pour point's catchment 
    area (i.e., it's watershed or contributing area) an a *24-hour* 
    precipitation estimate for a single storm frequency (e.g., 100 year storm).

    Note that the TR-55 methodology is designed around a 24-hour storm *duration*. 
    YMMV if providing a rainfall estimate based on for other storm durations.
    
    This calculator by default returns peak flow in cubic meters/second and the 
    time of concentration in hours.
    
    This uses the calculator logic originally developed by the Cornell Soil and Water lab.
    
    Numbers go in, numbers come out.
    
    :param mean_slope_pct: average slope in the basin, as percent rise
    :type mean_slope_pct: float
    :param max_flow_length_m: maximum flow length, in meters
    :type max_flow_length_m: float
    :param avg_rainfall_cm: rainfall for a 24 hour event, in centimeters
    :type avg_rainfall_cm: float
    :param basin_area_sqkm: area of the basin, in square kilometers
    :type basin_area_sqkm: float
    :param avg_cn: average curve number of the basin, area-weighted
    :type avg_cn: float
    :param tc_hr: time of concentration for the basin
    :type tc_hr: float    
    :param rain_ratio_method: flag [1,2] to indicate method to use for calculating the rain ratio
    :type rain_ratio_method: int
    :return: a tuple of peak flow, in cubic meters / second, and time of concentration, in hours
    :rtype: tuple[float, float]
    """

    q_peak = -9999

    # INIITAL CHECKS ------------------------------------------

    # Skip calculation altogether if curve number or time of concentration are 0.
    # (this indicates invalid data)
    if avg_cn in [0,'',None]:
        return None    

    # -------------------------------------------
    # TIME OF CONCENTRATION

    if not tc_hr:
        tc_hr = time_of_concentration_calculator(max_flow_length_m, mean_slope_pct)
    
    # -------------------------------------------
    # STORAGE 
    
    # calculate storage, S in cm  
    storage = 0.1 * ((25400.0 / avg_cn) - 254.0)
    
    # inital abstraction, amount of precip that never has a chance to become runoff
    init_abstraction = 0.2 * storage
    
    # -------------------------------------------
    # RUNOFF DEPTH 
    
    # calculate depth of runoff from each storm
    # if P < Ia NO runoff is produced
    Pe = (avg_rainfall_cm - init_abstraction)
    # print("RUNOFF DEPTH", storage, avg_rainfall_cm, init_abstraction, Pe)
    if Pe < 0:
        return q_peak, tc_hr

    Q = (Pe**2) / (avg_rainfall_cm + (storage - init_abstraction))
    # print("Q", Q)
    
    # -------------------------------------------
    # RAIN RATIO AND PEAK FLOW
    # alternative approaches from Cornell
    # calculate q_peak

    if rain_ratio_method == 2:
        q_peak = qpeak_via_rain_ratio_method1(init_abstraction, avg_rainfall_cm, tc_hr, Q, basin_area_sqkm)
    else:
        q_peak = qpeak_via_rain_ratio_method2(tc_hr, Q, basin_area_sqkm)

    return q_peak, tc_hr


@dataclass
class Runoff:

    time_of_concentration_hr: float = None
    culvert_peakflow_m3s: float = None
    crossing_peakflow_m3s: float = None

    def calculate_time_of_concentration(self, **kwargs):
        self.time_of_concentration_hr = time_of_concentration_calculator(**kwargs)

    def calculate_peak_flow(self, **kwargs):
        # print(kwargs)
        results = peak_flow_calculator(**kwargs)
        self.culvert_peakflow_m3s, self.time_of_concentration_hr = results
        
