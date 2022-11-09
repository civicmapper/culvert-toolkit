"""setup.py

This file is for packaging `drain-it` for distribution as a package and for use
in ArcGIS Pro using `setuptools`.

~Prior to the typical `setuptools.setup` method, this file runs runs the ArcPy
`createtoolboxsupportfiles` function to generate all the files needed to install
this package into an ArcGIS Pro conda environment from a Python wheel, including
dependencies from PyPi.~

References:

* https://packaging.python.org/en/latest/guides/distributing-packages-using-setuptools/#

"""

from setuptools import setup, find_packages
import pathlib
from os import remove
import shutil
import arcpy

HERE = pathlib.Path(__file__).parent.resolve()
# PYT = HERE / 'src' / 'CulvertToolbox.pyt'
# ESRI_SOURCE_PATH = HERE / 'src' / 'esri'
# ESRI_TARGET_PATH = HERE / 'src' / 'drainit' / 'esri'

# def build_arcpy_support_files(
#     here=HERE, 
#     source_pyt=PYT, 
#     source_build_path=ESRI_SOURCE_PATH, 
#     target_build_path=ESRI_TARGET_PATH
#     ):
#     print("building ArcPy support files")

#     target_pyt = target_build_path / 'toolboxes' / source_pyt.name

#     # create Python Toolbox support files
#     arcpy.gp.createtoolboxsupportfiles(str(source_pyt))

#     # remove existing esri support files folder
#     if target_build_path.exists():
#         shutil.rmtree(target_build_path)

#     # move the created support files
#     dest = shutil.move(source_build_path, target_build_path)

#     # make a toolboxes folder with the support files
#     if not target_pyt.parent.exists():
#         target_pyt.parent.mkdir()

#     # copy the toolbox into it
#     shutil.copyfile(source_pyt, target_pyt)

#     # delete the extra XML files
#     for i in source_pyt.parent.glob("*.xml"):
#         # find the XML files with a prefix matching the .pyt in the same folder
#         if str(i.name).startswith(source_pyt.stem):
#             f = str(source_pyt.parent / i)
#             print("deleting", f)
#             remove(f)


# build_arcpy_support_files(here=HERE)

setup(
    name='drain-it',
    version='0.1.0',
    author='CivicMapper',
    author_email="info@civicmapper.com",
    description="A geospatial data-powered TR-55 model for modeling culvert capacity",
    long_description=(HERE / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    url="https://github.com/civicmapper/drain-it",
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Programming Language :: Python :: 3.7',
        'Private :: Do Not Upload'
    ],    
    package_dir={"":"src"},
    # packages=['drainit'],
    packages=find_packages(where="src"),  # Required
    python_requires=">=3.7, <4",
    install_requires=[
        "codetiming",
        "pint",
        "click",
        "tqdm",
        "requests",
        "petl",
        "marshmallow",
        "marshmallow-dataclass",
    ],    
    package_data={
        'drainit':[
            'esri/toolboxes/*',  
            'esri/arcpy/*', 
            'esri/help/gp/*',  
            'esri/help/gp/toolboxes/*', 
            'esri/help/gp/messages/*'
        ]
    },
    # include_package_data=True,
    # entry_points='''
    #     [console_scripts]
    # ''',
)