# Culvert Analysis Toolkit

*NOTE: this repository is work-in-progress* 

The Culvert Analysis Toolkit is a collection of GIS tools designed to support analysis of culvert performance within their watershed. It uses a [TR-55 Model](https://www.nrcs.usda.gov/Internet/FSE_DOCUMENTS/stelprdb1044171.pdf) and parameters derived from geospatial data to calculate peak-flow and culvert capacity.

This software encompasses work originally developed by the Cornell Soil & Water Lab (on GitHub @ https://github.com/SoilWaterLab)

## Installation and Use

Check out the documentation at https://civicmapper.github.io/culvert-toolkit.

The package currently requires Python 3.11 or newer. ArcGIS Pro compatibility
is established per Pro/Python release by running the Windows validation
checklist; no Pro version is considered release-validated solely from this
Linux work. The calculators, models, NAACC ETL, and
NOAA client are importable and testable without ArcPy; geoprocessing workflows
still require ArcGIS Pro and Spatial Analyst. See
[`windows-arcgis-validation.md`](docs/docs/windows-arcgis-validation.md) for the
release checklist.

Published wheel metadata links to that compatibility checklist so each release
can state its validated ArcGIS Pro/Python combinations rather than implying
support for all Pro 3.x versions.

## Credits/Contributors

This repository represents an evolution of a previous effort, the [Peak-Flow Calculator](https://github.com/civicmapper/peak-flow-calculator/), which was a hard fork of the Water Lab's [CulvertEvalution](https://github.com/SoilWaterLab/CulvertEvaluation) repository. 

Made in collaboration with the Cornell S&W lab, this repository includes additional updates to the science of the analysis from [CulvertModel_2.1](https://github.com/SoilWaterLab/CulvertModel_2.1), as well as a ground-up rebuild of the supporting codebase.

* Original peak flow analytics are based on the culvert evaluation model developed by Rebecca Marjerison at the Cornell Soil and Water Lab in 2013, as [CulvertEvalution](https://github.com/SoilWaterLab/CulvertEvaluation)
* David Gold, python script development, August 4, 2015
* Object-oriented structure and resiliency updates built by Noah Warnke, August 31 2016 (no formulas changed).
* Updated by Zoya Kaufmann June 2016 - August 2017
* Merged with older versions by Tanvi Naidu June 19 2017
* Fork, refactor, and creation of CLI and ArcMap interfaces by Christian Gass @ CivicMapper, Fall 2017, as [peak-flow-calculator](https://github.com/civicmapper/peak-flow-calculator/)
* Updates for use within ArcGIS Pro by Christian Gass @ CivicMapper, Spring/Summer 2019, in [peak-flow-calculator](https://github.com/civicmapper/peak-flow-calculator/)
* [CulvertModel_2.1](https://github.com/SoilWaterLab/CulvertModel_2.1)by Jo Archibald in 2019
* Drain-It / Culvert Analysis Toolkit repository by CivicMapper, 2021-present
