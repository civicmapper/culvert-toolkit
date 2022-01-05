from dataclasses import dataclass
 

def calc_culvert_overflow(culvert_capacity, peak_flow):
    """Compare the peak flow coming to a culvert with the 
    capacity of a culvert.
    """
    return peak_flow - culvert_capacity

@dataclass
class Overflow:
    pass

def calc_overflow_for_frequency():
    return