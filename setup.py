"""setup.py

This file is for packaging `culvert-toolkit` for distribution as a package and for use
in ArcGIS Pro using `setuptools`.

References:

* https://packaging.python.org/en/latest/guides/distributing-packages-using-setuptools/#

"""

from setuptools import setup, find_packages
import pathlib

HERE = pathlib.Path(__file__).parent.resolve()

setup(
    name='culvert-toolkit',
    version='0.1.0',
    author='CivicMapper',
    author_email="info@civicmapper.com",
    description="A geospatial data-powered TR-55 model for modeling culvert capacity",
    long_description=(HERE / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    url="https://github.com/civicmapper/culvert-toolkit",
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Programming Language :: Python :: 3.9',
        'Private :: Do Not Upload'
    ],    
    package_dir={"":"src"},
    packages=find_packages(where="src"),  # Required
    python_requires=">=3.9, <4",
    install_requires=[
        "codetiming",
        "pint",
        "click",
        "tqdm",
        "requests",
        "petl",
        "marshmallow",
        "marshmallow-dataclass[union]",
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