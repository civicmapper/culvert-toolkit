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
def sample_rainfall_rasters(tmp_path):
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
    yield rconfig
    shutil.rmtree(d)