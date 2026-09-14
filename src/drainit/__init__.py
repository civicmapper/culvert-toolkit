"""Public package API.

The ArcGIS workflows are imported lazily so the data models, calculators, and
HTTP/ETL services remain usable in ordinary Python environments without ArcPy.
"""

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("culvert-toolkit")
except PackageNotFoundError:  # source checkout that has not been installed
    __version__ = "0+unknown"

_WORKFLOW_EXPORTS = {"NaaccDataIngest", "RainfallDataGetter", "CulvertCapacity"}
__all__ = ["__version__", *_WORKFLOW_EXPORTS]


def __getattr__(name):
    if name in _WORKFLOW_EXPORTS:
        return getattr(import_module(".workflows", __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")