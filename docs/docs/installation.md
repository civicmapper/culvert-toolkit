# Installation

## 1. Download the Culvert Toolkit installation file

Head to the [Releases page (github.com/civicmapper/drain-it/releases)](https://github.com/civicmapper/drain-it/releases) and download the `.whl` file from the latest version of the tool.

## 2. Create a dedicated Python environment in ArcGIS Pro

To use this package, you'll need to install it a custom Python environment for ArcGIS Pro.

1. [Clone the default ArcGIS Pro conda environment](https://pro.arcgis.com/en/pro-app/latest/arcpy/get-started/clone-an-environment.htm).
2. [Switch the current ArcGIS Pro conda environment to the cloned environment using the Python Package Manager](https://pro.arcgis.com/en/pro-app/latest/arcpy/get-started/activate-an-environment.htm).

For more information on working with Python environments in ArcGIS Pro, see [Esri's documentation](https://pro.arcgis.com/en/pro-app/latest/arcpy/get-started/what-is-conda.htm).

## 3. Install 

Now that you have the installation file and the custom Python environment, you can install the toolbox.

ArcGIS Pro comes with a **"Python Command Prompt"** shortcut available, which runs a batch script that automatically starts a command prompt with ArcGIS Pro's active Conda environment available. 

Typically this gets added to your Windows Start Menu alongside the shortcut to ArcGIS Pro.

1. Open the Python Command Prompt that came with your ArcGIS Pro installation.
3. In the command prompt, run `pip install <path-to-the-whl-file\drainit.whl>`. You'll replace `<path-to-the-whl-file\drainit.whl>` with the full path to the wheel file you downloaded in the previous step.

After that you should see a `Culvert Toolkit` toolbox listed alongside other toolboxes in the ArcToolbox pane of ArcGIS Pro. You may need to restart ArcGIS Pro before you see it.