# Peak Flow

Runoff peak discharge of given point's watershed is determined using the SCS graphical curve number method. For more information on this method, see [Technical Release 55](assets/Urban-Hydrology-for-Small-Watersheds-TR-55.pdf).

## In the code

The time of concentration equation used in this tool is located in [`src/drainit/calculators/runoff.py`, in the `time_of_concentration_calculator` function](https://github.com/civicmapper/culvert-toolkit/blob/a76c866f438ec49f0acac161e35bc30f1511b416/src/drainit/calculators/runoff.py#L12)

The peak flow calculator function in this tool is located in [`src/drainit/calculators/runoff.py`, in the `peak_flow_calculator` function](https://github.com/civicmapper/culvert-toolkit/blob/a76c866f438ec49f0acac161e35bc30f1511b416/src/drainit/calculators/runoff.py#L203).
