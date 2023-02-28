# Culvert Capacity

Culvert Capacity is calculated using an equation from [USDOT FHA Publication No. FHWA-HIF-12-026, Equation A.3, pg 191](assets/hif12026.pdf).

The equation, expressed in [Python](https://www.python.org/), is as follows:

```python
capacity = (
    culvert_area_sqm * math.sqrt(
        culvert_depth_m * (
            (
                head_over_invert / culvert_depth_m
            ) - coefficient_y - coefficient_slope * slope_rr
        ) / coefficient_c
    )
) / si_conv_factor
```
Variables shown above are as follows:

* `culvert_area_sqm`: internal surface area of the culvert
* `head_over_invert`: Hydraulic head above the culvert invert, meters
* `culvert_depth_m`: Culvert depth. Diameter or dimension b, (height of culvert) meters
* `slope_rr`: slope rise/run (meters)
* `coefficient_slope`: slope coefficient from FHWA engineering pub HIF12026, appendix A. -0.5, except where inlet is mitered in which case +0.7
* `coefficient_y`: coefficient based on shape and material from FHWA engineering pub HIF12026
* `coefficient_c`: coefficient based on shape and material from FHWA engineering pub HIF12026
* `si_conv_factor`: adjustment factor for units (SI=1.811), defaults to 1.811

The equation returns `capacity`: capacity in cubic meters / second (m^3/s)

Constants `coefficient_c`, `coefficient_y`, `coefficient_slope` are set based on the culvert entrance shape and material, from FHWA engineering pub HIF12026, appendix A.

## In the code

The capacity calculator module in this tool is located in [`src/drainit/calculators/capacity.py`](https://github.com/civicmapper/culvert-toolkit/blob/dev/src/drainit/calculators/capacity.py)