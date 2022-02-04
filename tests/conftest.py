from os import path
import json
import zipfile
import shutil
from pathlib import Path
import pytest
# models from project
from drainit import models

# Test Data on disk
TEST_DATA_DIR = Path(path.dirname(path.abspath(__file__))) / "data"

@pytest.fixture
def sample_rainfall_data(tmp_path):
    """ Sample data and config file, like what is returned by noaa.retrieve_noaa_rainfall_rasters
    """
    # rainfall
    rainfall_zip = TEST_DATA_DIR / "rainfall" / "sample_rainfall_rasters.zip"
    # temp directory to extract sample data to
    d = tmp_path / "rainfall"
    d.mkdir()
    # extract the zip to temp directory
    with zipfile.ZipFile(str(rainfall_zip), 'r') as zip_ref:
        zip_ref.extractall(d)
    # open/parse the config file
    rconfig_path = d / 'rainfall_rasters_config.json'
    with open(rconfig_path) as fp:
        rconfig_dict = json.load(fp)
    # load the serialized json into the model
    rconfig_schema = models.RainfallRasterConfigSchema()
    rconfig = rconfig_schema.load(rconfig_dict)
    # update the root path property to the temp dir
    # update the path for all the listed rasters
    rconfig.root = str(d)
    for r in rconfig.rasters:
        r.path = d / Path(r.path).name
    # deserialize to dict and save as JSON
    rconfig_dict = rconfig_schema.dump(rconfig)
    with open(rconfig_path, 'w') as fp:
        json.dump(rconfig_dict, fp)
    # return the rainfall config object
    yield rconfig, rconfig_path
    # shutil.rmtree(d)

@pytest.fixture
def sample_prepped_naacc_geodata(tmp_path):
    """Sample geodatabase and JSON data created from the NAACC ETL tool.
    """
    data_zip = TEST_DATA_DIR / "culverts" / "naacc_gdb.zip"
    # temp directory to extract sample data to
    d = tmp_path / "naacc_gdb"
    d.mkdir()
    # extract the zip to temp directory
    with zipfile.ZipFile(str(data_zip), 'r') as zip_ref:
        zip_ref.extractall(d)
    yield d / "naacc.gdb"
    # shutil.rmtree(d)

@pytest.fixture
def sample_landscape_data(tmp_path):
    """Sample landscape rasters for testing purposes.
    """
    data_zip = TEST_DATA_DIR / "landscape" / "sample_landscape_rasters.zip"
    # temp directory to extract sample data to
    d = tmp_path / "landscape"
    d.mkdir()
    # extract the zip to temp directory
    with zipfile.ZipFile(str(data_zip), 'r') as zip_ref:
        zip_ref.extractall(d)
    # return a dictionary
    yield dict(
        flowdir = d / "dem_filled_flowdir.tif",
        curveno = d / "curveno.tif",
        slope = d / "dem_filled_slope.tif"
    )
    # shutil.rmtree(d)

@pytest.fixture
def all_sample_inputs(
    sample_rainfall_data,
    sample_prepped_naacc_geodata,
    sample_landscape_data
    ):
    """combines results of multiple test data-unpacking fixtures into a 
    dictionary for use in workflow tools
    """

    # arguments for the culvert capacity tester
    kwargs = dict(
        points_filepath=sample_prepped_naacc_geodata / "naacc_points",
        precip_src_config_filepath=sample_rainfall_data[1],
        raster_flowdir_filepath=sample_landscape_data['flowdir'],
        raster_slope_filepath=sample_landscape_data['slope'],
        raster_curvenumber_filepath=sample_landscape_data['curveno'],
        # output_points_filepath=str()
    )
    # convert what may be Path objects to strings for use in the tool
    kwargs = {k: str(v) for k, v in kwargs.items()}

    return kwargs

@pytest.fixture
def sample_completed_delineation_config(tmp_path, all_sample_inputs):

    shutil.copyfile(
        TEST_DATA_DIR / 'config_completed_delineation.json',
        tmp_path / 'config_completed_delineation.json'
    )

    return tmp_path / 'config_completed_delineation.json'

@pytest.fixture
def sample_completed_capacity_config(tmp_path):

    shutil.copyfile(
        TEST_DATA_DIR / 'config_completed_analytics.json',
        tmp_path / 'config_completed_analytics.json'
    )

    return tmp_path / 'config_completed_analytics.json'    
