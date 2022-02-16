from dataclasses import dataclass
from typing import Optional, Any, List
from ..config import FREQUENCIES
 

def culvert_overflow_calculator(culvert_capacity, peak_flow):
    """Compare the peak flow coming to a culvert with the 
    capacity of a culvert. Postive results indicate excess capacity,
    negative results indicate an overflow condition.

    For now, assumes units are the same.
    """
    return culvert_capacity - peak_flow

def max_return_calculator(list_of_overflows:List[float], list_of_frequencies: List[Any]=FREQUENCIES):
    """Given a list of calculated overflows and corresponding list of frequencies,
    return the highest frequency with >= 0 overflow.

    Args:
        list_of_overflows (List[float]): [description]
        list_of_frequencies (List[int], optional): [description]. Defaults to FREQUENCIES.

    Returns:
        [int]: [description]
    """
    handled_return_periods = []
    for freq, ovf in zip(list_of_frequencies, list_of_overflows):
        if ovf is not None:
            if ovf >= 0: 
                handled_return_periods.append(freq)
    if len(handled_return_periods) > 0:
        return max(handled_return_periods)
    return None


@dataclass
class Overflow:

    culvert_overflow_m3s: Optional[float] = None
    crossing_overflow_m3s: Optional[float] = None

    def calculate_overflow(self, **kwargs):
        self.culvert_overflow_m3s = culvert_overflow_calculator(**kwargs)    