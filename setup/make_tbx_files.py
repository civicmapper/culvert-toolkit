"""mak_tbx_files.py

This file runs the ArcPy `createtoolboxsupportfiles` function to generate all 
the files needed so that when the package is built by `setup.py` as a Python
wheel and installed into an ArcGIS Pro conda environment, the toolbox appears 
in the system ArcToolbox.

References:

* https://pro.arcgis.com/en/pro-app/latest/arcpy/geoprocessing_and_python/extending-geoprocessing-through-python-modules.htm

"""

import pathlib
from os import remove
import shutil
import arcpy

HERE = pathlib.Path(__file__).parent.parent.resolve()
PYT = HERE / 'src' / 'CulvertToolbox.pyt'
print(PYT, PYT.exists())
ESRI_SOURCE_PATH = HERE / 'src' / 'esri'
ESRI_TARGET_PATH = HERE / 'src' / 'drainit' / 'esri'

def build_arcpy_support_files(
    here=HERE, 
    source_pyt=PYT, 
    source_build_path=ESRI_SOURCE_PATH, 
    target_build_path=ESRI_TARGET_PATH
    ):
    print("building ArcPy support files")

    target_pyt = target_build_path / 'toolboxes' / source_pyt.name

    # create Python Toolbox support files
    arcpy.gp.createtoolboxsupportfiles(str(source_pyt))

    # remove existing esri support files folder
    if target_build_path.exists():
        shutil.rmtree(target_build_path)

    # move the created support files
    dest = shutil.move(source_build_path, target_build_path)

    # make a toolboxes folder with the support files
    if not target_pyt.parent.exists():
        target_pyt.parent.mkdir()

    # copy the toolbox into it
    shutil.copyfile(source_pyt, target_pyt)

    # # delete the tool metadata files
    # for i in source_pyt.parent.glob("*.xml"):
    #     # find the XML files with a prefix matching the .pyt in the same folder
    #     if str(i.name).startswith(source_pyt.stem):
    #         f = str(source_pyt.parent / i)
    #         print("deleting", f)
    #         remove(f)


build_arcpy_support_files()