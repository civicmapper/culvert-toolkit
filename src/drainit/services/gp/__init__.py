import tempfile

from ...settings import USE_ESRI


def resolve_scratch_folder(scratch_folder):
    """Return ArcPy's scratch folder or the system temporary directory."""
    if scratch_folder:
        return str(scratch_folder)
    return tempfile.gettempdir()

class ArcPyNotAvailableError(ModuleNotFoundError):
    """Raised when an ArcGIS workflow is invoked without ArcPy."""


class _UnavailableArcPyGP:
    def __init__(self, *args, **kwargs):
        raise ArcPyNotAvailableError(
            "ArcGIS geoprocessing workflows require the 'arcpy' package supplied "
            "with a supported ArcGIS Pro Python environment. Pure-Python "
            "drainit calculators, models, NAACC, and NOAA services do not.",
            name="arcpy",
        ) from _ARCPY_IMPORT_ERROR

if USE_ESRI:
    try:
        # Probe the backend's defining dependency before importing the larger
        # adapter, whose ArcGIS environment also supplies packages like pandas.
        import arcpy  # noqa: F401
        from ._esri import GP
    except ModuleNotFoundError as exc:
        # Only defer a genuinely missing ArcPy dependency. A missing package in
        # our own backend must not be disguised as "ArcPy unavailable".
        if exc.name != "arcpy":
            raise
        _ARCPY_IMPORT_ERROR = exc
        GP = _UnavailableArcPyGP
else:
    _ARCPY_IMPORT_ERROR = ModuleNotFoundError(
        "The WhiteboxTools+GeoPandas backend is not implemented."
    )
    GP = _UnavailableArcPyGP