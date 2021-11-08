import json
from pathlib import Path
import zipfile
from .conftest import TEST_DATA_DIR
from drainit import workflows
from drainit import models


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

    def test_mock_e2e_rainfall_data_getter(self, sample_rainfall_rasters):

        rconfig = sample_rainfall_rasters
        for r in rconfig.rasters:
            p = Path(r.path)
            assert p.exists()

    # def test_mock_e2e_rainfall_data_getter(self, tmp_path, monkeypatch):


class TestNaaccETL:

    def test_naacc_data_ingest(self, tmp_path):
        d = tmp_path / "naacc" / "naacc.gdb"
        results = workflows.NaaccDataIngest(
            str(TEST_DATA_DIR / 'test_naacc_sample.csv'),
            str(d),
            'naacc_points'
        )
        # evaluate the sample results:
        # 8 records
        assert len(results.points) == 8
        # 2 with validation errors
        assert len([p for p in results.points if bool(p.validation_errors)]) == 2
        # the results were saves as geodata
        d = results._testing_output_geodata()
        assert isinstance(d, dict)




