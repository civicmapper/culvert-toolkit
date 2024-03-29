import json
from pathlib import Path
import zipfile

import pytest
import petl as etl

from .conftest import TEST_DATA_DIR

from src.drainit import workflows
from src.drainit import models
from src.drainit import utils
from src.drainit.calculators import (
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
        d = tmp_path / "TestRainfallETL"
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
        output_fc = str(d / "TestNaaccETL.gdb" / "test_naacc_data_ingest_from_csv")
        results = workflows.NaaccDataIngest(
            naacc_src_table=str(TEST_DATA_DIR / 'culverts'/ 'test_naacc_sample.csv'),
            output_fc=str(d / "naacc.gdb" / 'naacc_points')
        )
        t = results.naacc_table # petl table
        
        # evaluate the sample results:
        # 8 records
        assert etl.nrows(t) == 8
        
        # 3 with validation errors
        assert etl.nrows(etl.selectfalse(t, "include")) == 3
        assert etl.nrows(etl.selectnotnone(t, "validation_errors")) == 3

        # the results were saved as geodata; check we have 8 features
        features = results._testing_output_geodata()
        assert len(features) == 8

        # that values in the Naacc_Culvert_Id and Survey_Id fields are either numbers or None, but not text
        for fld in ['Naacc_Culvert_Id', 'Survey_Id']:
            checks = [any([
                isinstance(f.get('attributes',{}).get(fld), int),
                isinstance(f.get('attributes',{}).get(fld), float)
            ]) for f in features if f.get('attributes',{}).get(fld) is not None]
            print(fld, checks)
            assert all(checks)



    @pytest.mark.parametrize("csv_name", ["test_naacc_sample_bad1.csv", "test_naacc_sample_bad2.csv", "test_naacc_sample_bad3.csv"])
    def test_bad_naacc_data_ingest_from_csv(self, tmp_path, csv_name):
        """this test should be 
        """
        d = tmp_path
        naacc_src_table = str(TEST_DATA_DIR / 'culverts'/ csv_name)

        # get a row count from the source table
        ct = etl.nrows(etl.fromcsv(naacc_src_table))

        # test the ingest tool
        output_fc = str(d / "TestNaaccETL.gdb" / csv_name.split(".")[0])
        results = workflows.NaaccDataIngest(
            naacc_src_table=naacc_src_table,
            output_fc=output_fc
        )
        t = results.naacc_table # petl table
        
        # evaluate the sample results:
        # 8 records
        assert etl.nrows(t) == ct

        # the results were saved as geodata; check we have 8 features
        f = results._testing_output_geodata()
        assert len(f) == ct

    def test_naacc_data_ingest_from_fgdb_fc(self, tmp_path, sample_prepped_naacc_geodata):
        d = tmp_path
        output_fc = str(d / "TestNaaccETL.gdb" / "test_naacc_data_ingest_from_fgdb_fc")
        results = workflows.NaaccDataIngest(
            naacc_src_table=str(sample_prepped_naacc_geodata / 'test_naacc_sample'),
            output_fc=output_fc
        )
        t = results.naacc_table # petl table
        
        # evaluate the sample results:
        # 8 records
        assert etl.nrows(t) == 8

        # 5 without validation errors
        assert etl.nrows(etl.selectnone(t, "validation_errors")) == 5

        # the results were saved as geodata; check we have 3 features
        f = results._testing_output_geodata()
        assert len(f) == 8

    def test_naacc_data_resnapping(self, tmp_path, sample_prepped_naacc_geodata):
        d = tmp_path
        output_fc = str(d / "TestNaaccETL.gdb" / "test_naacc_data_resnapping")
        results = workflows.NaaccDataSnapping(
            output_fc=output_fc,
            naacc_points_table=str(sample_prepped_naacc_geodata / 'naacc_points'),
            geometry_source_table=str(sample_prepped_naacc_geodata / 'naacc_crossings_snapped'),
            include_moved_field=True
        )
        t = results.output_table
        
        # evaluate the sample results:
        # 3 records
        assert etl.nrows(t) == 8

        # 5 without validation errors
        assert etl.nrows(etl.selectnone(t, "validation_errors")) == 5

        # check the moved field and its contents
        assert "moved" in etl.header(t)
        # assert all([isinstance(i, int) for i in etl.values(t, "moved")])

    def test_naacc_data_sensitivity(self, tmp_path):
        """Throwaway test that exists just for batch running and checking
        capacity model calculations performed during NaaccETL.

        Args:
            tmp_path (_type_): _description_
        """
        d = tmp_path
        output_fc = str(d / "TestNaaccETL.gdb" / "test_naacc_data_sensitivity")
        results = workflows.NaaccDataIngest(
            naacc_src_table=str(TEST_DATA_DIR / 'culverts'/ 'test_naacc_sample_sensitivity_testing.csv'),
            output_fc=str(d / "naacc.gdb" / 'test_naacc_data_sensitivity')
        )
        t = results.naacc_table # petl table

        assert True