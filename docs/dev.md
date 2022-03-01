# Development

## Setup Anaconda Python and dependencies

## Project Structure

The project is structure so there is a fairly clear separation of concerns between the code that handles

* the science behind the calculators
* the geoprocessing tools used to derive spatial statistics from the various map layers
* the specific i/o requirements and interfaces expected in end-user workflows

### src/

The folder contains external-facing interfaces that use the `drainit` package. Includes":

* `tbx_*.py` scripts, which are workflow-specific and map 1:1 with tools in the ArcGIS Pro toolbox `drainit.tbx`.
* `cli.py`, the command line interface to the `drainit` package

### src/drainit/

This is the top-level package.

It contains a few scripts:

#### workflows.py

Contains the code for executing analytical workflows at the highest level of abstraction. A single workflow is represented by a single python classes. 

All workflow classes inherit from a base class that contains properties and methods for reading/writing workflow state to

#### cli.py

#### config.py and settings.py

#### models.py

Internal data models used throughout the package. 

#### calculators

Module containing the science and business logic of the various calculators available in the package: runoff/peak flow, culvert capacity, etc.

#### services

Scripts for interacting with third-party domain-specific data sources (e.g., NOAA rainfall data, NAACC culvert data) and geoprocessing tools (e.g., Esri ArcPy, Whitebox tools).

##### gp

Geoprocessing services designed on specific provider tools (e.g., ESRI, Whitebox) and exposed through a generic class that is called by the workflow tools. This ensures `workflow.py` can run GP tools without needing to know exactly what underlying geoprocessing library is being used.

### tests

Integration tests for workflows and tasks within workflows.
