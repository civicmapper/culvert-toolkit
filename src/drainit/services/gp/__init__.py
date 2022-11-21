from click import echo
from ...settings import USE_ESRI

if USE_ESRI:
    try:
        # import arcpy
        from ._esri import GP
        echo("ArcPy available.")
    except ModuleNotFoundError:
        echo("ArcPy not available. ArcPy is currently the only supported geoprocessing backend.")
        # from ._wbt import *
else:
    echo("The WhiteboxTools+GeoPandas integration is not yet implemented.")
    # echo("Using WhiteboxTools and GeoPandas for Geoprocessing tasks.")
    # from ._wbt import *