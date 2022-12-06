"""mak_tbx_files.py

This file runs the ArcPy `createtoolboxsupportfiles` function to generate all 
the metadata files needed so that when the package is built by `setup.py` as a 
Python wheel and installed into an ArcGIS Pro conda environment, the toolbox 
appears in the system ArcToolbox.

References:

* https://pro.arcgis.com/en/pro-app/latest/arcpy/geoprocessing_and_python/extending-geoprocessing-through-python-modules.htm

"""

import pathlib
from os import remove
import shutil
import arcpy

HERE = pathlib.Path(__file__).parent.parent.resolve()
PYT = HERE / 'src' / 'CulvertToolbox.pyt'
ESRI_SOURCE_PATH = HERE / 'src' / 'esri'
ESRI_TARGET_PATH = HERE / 'src' / 'drainit' / 'esri'

def build_arcpy_support_files(
    source_pyt=PYT, 
    target_build_path=ESRI_TARGET_PATH
    ):

    print("building ArcPy support files")

    # source build path is in the same folder as the PYT
    source_build_path = source_pyt.parent / 'esri'
    # targets for documentation
    target_docs_path = target_build_path / 'help' / 'gp' 
    target_pyt = target_build_path / 'toolboxes' / source_pyt.name

    # create Python Toolbox support files
    # this will create anything that's missing as well as a master xml
    # file in help/gp/toolboxes
    arcpy.gp.createtoolboxsupportfiles(str(source_pyt))

    # remove the initially generated esri support files folder
    if target_build_path.exists():
        shutil.rmtree(target_build_path)

    # move the created support files
    dest = shutil.move(str(source_build_path), str(target_build_path))

    # make a toolboxes folder with the support files
    if not target_pyt.parent.exists():
        target_pyt.parent.mkdir()
    # copy the toolbox into it
    shutil.copyfile(source_pyt, target_pyt)

    # copy in our versions of the metadata files to the right places, with the 
    # right names, to the distribution folder
    for i in source_pyt.parent.glob(f"{source_pyt.name}*.xml"):
        print("copying", i.name)
        if i.name == f"{source_pyt.name}.xml":
            renamed = f"{source_pyt.stem}_toolbox.xml"
        else:
            parts = i.name.split(".")
            renamed = f"{parts[1]}_{parts[0]}.xml"
        
        shutil.copyfile(
            str(i),
            str(target_docs_path / renamed)
        )

build_arcpy_support_files()