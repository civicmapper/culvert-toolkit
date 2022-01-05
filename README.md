# Drain-It

Inlet + Culvert Peak-Flow and Capacity Calculator using a TR-55 Model and
parameters derived from geospatial data.

* NAACC ETL: new from 2.1. Transform to a standardized generic point format.
* Get rainfall rasters from NOAA
* Delineation: Series currently this is part of peak flow, but could be separated out
* Peak flow: Calculate from a TR-55 model with rainfall rasters from NOAA.
* Capacity: new from 2.1. Depends on the kinds of fields collected in the NAACC format. If those fields are unavailable, we skip this part just like any other step.
* Return Period Eval: new in 2.1. Relies on peak-flow and capacity results together
* Workflow-oriented model runs: save and load a config file to reload and re-run models

## Installation

Download and unzip, or `git clone` a copy of this repository locally. Then follow the steps bellow based on where you want to use the tools.

### Using Drain-It in **Esri ArcGIS Pro**

*Requires:*

* ArcGIS Pro 2.7.\* (which includes Anaconda Python 3.7.\*)
* Python dependencies listed in `setup/esri-cloned-requirements.txt`

*Steps:*

1. Run `setup-for-arcgispro.bat`. This will clone the base `arcgispro-py3` Anaconda Python environment from ArcGIS Pro and install a few additional python packages in it. The new environment, `drainit-for-arcgispro`, will then be available in ArcGIS Pro. *Note: the `.bat` script assumes you have installed ArcGIS Pro in its default location so that the root Ananconda Python envrionment is available at `C:\Program Files\ArcGIS\Pro\bin\Python\Scripts`).*
2. After the install script finishes, fire up ArcGIS Pro and go to *Settings >>> Python >>> Manage Environments*. Select the `drainit-for-arcgispro` environment; you'll be notified to restart ArcGIS Pro for the changes to take effect.
3. Open up a new or existing ArcGIS Pro project, and add `drainit.tbx` to your available toolboxes.

### *Planned Functionality:* Using Drain-It without **Esri ArcGIS Pro**

This planned enhancement will rely on Whitebox Tools and GeoPandas instead of Esri ArcPy for geoprocessing; its user interface will be available at the command line or a Python package.

*Requires:*

* Python 3.7+
