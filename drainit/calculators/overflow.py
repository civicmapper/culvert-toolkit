from dataclasses import dataclass
from typing import Optional
 

def culvert_overflow_calculator(culvert_capacity, peak_flow):
    """Compare the peak flow coming to a culvert with the 
    capacity of a culvert. Postive results indicate excess capacity,
    negative results indicate an overflow condition.

    For now, assumes units are the same.
    """
    return culvert_capacity - peak_flow


@dataclass
class Overflow:

    culvert_overflow_m3s: Optional[float] = None
    crossing_overflow_m3s: Optional[float] = None

    def calculate_overflow(self, **kwargs):
        self.culvert_overflow_m3s = culvert_overflow_calculator(**kwargs)    