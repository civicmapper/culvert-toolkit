# Developing the Toolkit

## Setup Anaconda Python and dependencies

Development requires access to the `arcpy` library include with ArcGIS Pro, and a ArcGIS Pro-dervied Conda environment that includes the dependenices listed in `setup\requirements.txt`

## Project Structure

The project is structure so there is a fairly clear separation of concerns between the code that handles

* the science behind the calculators
* the geoprocessing tools used to derive spatial statistics from the various map layers
* the specific i/o requirements and interfaces expected in end-user workflows

### src/

The folder contains external-facing interfaces that use the `drainit` package. It includes:

* `CulvertToolbox.pyt` and associated `xml` metadata.
* legacy `drainit.tbx` file (replaced by `CulvertToolbox.pyt`)
* `tbx_*.py` scripts, which are workflow-specific and map 1:1 with tools in the ArcGIS Pro toolbox `drainit.tbx`.

### src/drainit/

This is the top-level package.

It contains a few scripts:

#### workflows.py

Contains the code for executing analytical workflows at the highest level of abstraction. A single workflow is represented by a single python class. 

All workflow classes inherit from a base class that contains properties and methods for reading/writing workflow state to a JSON configuration file.

#### cli.py

Command line interface to the scripting tools (WIP).

#### config.py and settings.py

Constants used for script execution.

#### models.py

Internal data models used throughout the package. 

#### calculators/

Module containing the science and business logic of the various calculators available in the package: 

* [runoff/peak flow](calcs-peak-flow.md)
* [culvert capacity](calcs-culvert-capacity.md)

#### services/

Scripts for interacting with third-party domain-specific data sources (e.g., NOAA rainfall data, NAACC culvert data) and geoprocessing tools (e.g., Esri ArcPy, Whitebox tools).

##### gp/

Geoprocessing services designed on specific provider tools (e.g., ESRI, Whitebox) and exposed through a generic class that is called by the workflow tools. This ensures `workflow.py` can run GP tools without needing to know exactly what underlying geoprocessing library is being used.

#### esri/

This folder contains the built ArcGIS Pro Python toolbox, its metadata, and an `arcpy` interface script. 

These are automatically created during the build process and do not need to be manually edited under normal circumstances.

#### Scripts: `noaa` and `naaccc` 

These are data provider-specific scripts that do domain-specific work with specific data types.

### tests/

Integration tests for workflows and tasks within workflows.
