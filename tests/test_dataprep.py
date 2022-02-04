import json
from pathlib import Path
import zipfile

import pytest
import petl as etl

from .conftest import TEST_DATA_DIR

from drainit import workflows
from drainit import models
from drainit import utils
from drainit.calculators import (
    runoff, 
    capacity, 
    overflow
)

pp = utils.pretty_print


# class TestWorkflowManagement:

#     def test_workflow_config_init(self):
#         w = workflows.WorkflowManager()
#         assert w is not None

 
class TestRainfallETL:

    def test_e2e_rainfall_data_getter(self, tmp_path):
        # temp path for the test download
        d = tmp_path / "rainfall"
        d.mkdir()
        # tests the ETL workflow
        results = workflows.RainfallDataGetter(
            str(TEST_DATA_DIR / "test_aoi.json"),
            str(d)
        )
        # tests loading and serializing the resul  ts
        with open(results.out_path) as fp:
            rconfig_dict = json.load(fp)
        rconfig = models.RainfallRasterConfigSchema().load(rconfig_dict)
        # tests if the results exist on disk
        for r in rconfig.rasters:
            p = Path(r.path)
            assert p.exists()

    def test_mock_e2e_rainfall_data_getter(self, sample_rainfall_data):

        rconfig, rconfig_path = sample_rainfall_data
        for r in rconfig.rasters:
            p = Path(r.path)
            assert p.exists()

    # def test_mock_e2e_rainfall_data_getter(self, tmp_path, monkeypatch):


class TestNaaccETL:

    def test_naacc_data_ingest_from_csv(self, tmp_path):
        d = tmp_path
        # x = Path(r'C:\Users\chris\OneDrive\Documents\dev\drainage\drainit')
        results = workflows.NaaccDataIngest(
            naacc_csv=str(TEST_DATA_DIR / 'test_naacc_sample.csv'),
            output_folder=str(d),
            output_workspace=str(d / "naacc.gdb"),
            output_fc_name='naacc_points'
        )
        t = results.naacc_table # petl table
        
        # evaluate the sample results:
        # 8 records
        assert etl.nrows(t) == 8
        
        # 3 with validation errors
        assert etl.nrows(etl.selectfalse(t, "include")) == 3
        assert etl.nrows(etl.selectnotnone(t, "validation_errors")) == 3

        # the results were saved as geodata; check we have 8 features
        f = results._testing_output_geodata()
        assert len(f) == 8

        # capacity calculated for 5 records

    # def test_naacc_data_ingest_for_capacitycalculator(self, tmp_path):

    #     models.WorkflowConfig()

    #     ccc = workflows.CulvertCapacityCore(
    #         points_filepath=
    #         points_id_fieldname=
    #         points_group_fieldname=
    #     )
    #     ccc.load_points()

    #     return

