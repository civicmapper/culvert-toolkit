from click import echo
from ...settings import USE_ESRI

if USE_ESRI:
    try:
        import arcpy
        from ._esri import *
        echo("ArcPy available.")
    except ModuleNotFoundError:
        echo("ArcPy not available. Falling back to WhiteboxTools and GeoPandas")
        # from ._wbt import *
else:
    echo("The WhiteboxTools+GeoPandas integration is not yet ready for use quite yet--please use Esri.")
    # echo("Using WhiteboxTools and GeoPandas for Geoprocessing tasks.")
    # from ._wbt import *