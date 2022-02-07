import json
from pathlib import Path
import zipfile
from math import isclose
from dataclasses import asdict

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


class TestCalculators:

    # def test_runoff_tc(self):
    #     runoff.calc_time_of_concentration()

    @pytest.mark.parametrize(
        "pf_args,expected_pf", [
        # mean_slope_pct, max_flow_length_m,avg_rainfall_cm,basin_area_sqkm,avg_cn,tc_hr=None
        # we're providing tc_hr so we can ignore the first two args
        ([None,None,58.3362007,27.2290001,68.4257965,0.0149833], 7.045),
        ([None,None,57.97,19.69,66.48,1.15], 1242.67)
    ])
    def test_runoff(self, pf_args, expected_pf):
        calcd_pf, tc = runoff.peak_flow_calculator(*pf_args)
        assert isclose(calcd_pf, expected_pf, rel_tol=0.01)

    # def test_capacity(self):
    #     capacity.calc_culvert_capacity()

    # def test_overflow(self):
    #     overflow.calc_overflow_for_frequency()


class TestCapacityCalc:

    def test_init_culvertcapacity(self, all_sample_inputs,tmp_path):
        """test initialization of the core Culvert Capacity tool
        """
        kw = all_sample_inputs

        # instantiate the class with the kwargs and run the load_points method
        cc = workflows.CulvertCapacityCore(**kw)
        cc.load_points()

        # test that all inputs are present in the config object
        assert cc.config.points_filepath == kw['points_filepath']
        assert cc.config.raster_curvenumber_filepath == kw['raster_curvenumber_filepath']
        assert cc.config.raster_flowdir_filepath == kw['raster_flowdir_filepath']
        assert cc.config.raster_slope_filepath == kw['raster_slope_filepath']
        assert cc.config.precip_src_config_filepath == kw['precip_src_config_filepath']

        # test that the rainfall config has been serialized to the config object
        assert isinstance(cc.config.precip_src_config, models.RainfallRasterConfig)

        # test that the input points have been serialized correctly
        assert len(cc.config.points) == 8
        assert cc.config.points_spatial_ref_code == 4326

        output_config_filepath = Path(tmp_path) / 'drainit_config.json'
        cc.save_config(str(output_config_filepath))

        assert output_config_filepath.exists()

    def test_delineate_and_analyze_one_catchment(self, all_sample_inputs, tmp_path):
        """run one good point through the single delineate/analyze function
        """

        # instantiate the class with the kwargs and run the load_points method
        kw = all_sample_inputs
        cc = workflows.CulvertCapacityCore(**kw)
        cc.load_points()

        # get a single passing test point from the test data
        test_point = cc.config.points[3]
        point_geodata = cc.gp.create_geodata_from_points([test_point], as_dict=False)
        # serialize the precip src config object as a dictionary
        precip_src_config = models.RainfallRasterConfigSchema().dump(cc.config.precip_src_config)

        # create a temp output workspace for saving the sheds
        workspace_path = cc.gp.create_workspace(tmp_path, 'outputs')
        cc.config.output_sheds_filepath = str(Path(workspace_path) / 'test_shed')        

        shed = cc.gp._delineate_and_analyze_one_catchment(
                point_geodata=point_geodata,
                pour_point_field=cc.config.points_id_fieldname,
                flow_direction_raster=cc.config.raster_flowdir_filepath,
                slope_raster=cc.config.raster_slope_filepath,
                curve_number_raster=cc.config.raster_curvenumber_filepath,
                out_shed_polygon=cc.config.output_sheds_filepath,
                rainfall_rasters=precip_src_config['rasters']
        )

        # print(cc.config)
        # pp(shed)
        output_config_filepath = Path(tmp_path) / 'drainit_config.json'
        cc.save_config(str(output_config_filepath))        

        assert Path(shed.filepath_raster).exists
        assert Path(shed.filepath_vector).exists

        assert shed.avg_cn is not None
        assert shed.avg_slope_pct is not None
        assert shed.max_fl is not None
        assert shed.area_sqkm is not None

    def test_delineation_and_analysis_in_parallel_unit(self, all_sample_inputs, tmp_path):
        """runs the delineation/analysis loop function, which runs and collects 
        the results from the single delineation/analysis run over a list of 
        points.
        """

        # instantiate the class with the kwargs and run the load_points method
        kw = all_sample_inputs
        cc = workflows.CulvertCapacityCore(**kw)
        cc.load_points()

        # for testing, set a temp output path for the shed polygons
        # cc.config.output_sheds_filepath = cc.gp.so("test_delineations")
        # create a temp output workspace for saving the sheds
        workspace_path = cc.gp.create_workspace(tmp_path, 'outputs')
        cc.config.output_sheds_filepath = str(Path(workspace_path) / 'test_delineations')            

        cc.config.points = cc.gp.delineation_and_analysis_in_parallel(
            points=cc.config.points,
            pour_point_field=cc.config.points_id_fieldname,
            flow_direction_raster=cc.config.raster_flowdir_filepath,
            slope_raster=cc.config.raster_slope_filepath,
            curve_number_raster=cc.config.raster_curvenumber_filepath,
            precip_src_config=models.RainfallRasterConfigSchema().dump(cc.config.precip_src_config),
            out_shed_polygons=cc.config.output_sheds_filepath,
            out_shed_polygons_simplify=cc.config.sheds_simplify,
            override_skip=True
        )
        
        # pp(cc.config)
        # pp(cc.config.points)
        # pp(cc.config.output_sheds_filepath)

        output_config_filepath = Path(tmp_path) / 'drainit_config.json'
        cc.save_config(str(output_config_filepath))

        assert output_config_filepath.exists()

        have_sheds = [p for p in cc.config.points if p.shed is not None]
        assert len(have_sheds) == 8

        # good_points = [p for p in cc.config.points if p.include == True]
        # assert len(good_points) == 5
        
        # bad_points = [p for p in cc.config.points if p.include == False]
        # assert len(bad_points) == 3

    def test_analytics(self, sample_completed_delineation_config, tmp_path):
        
        cc = workflows.CulvertCapacityCore(save_config_json_filepath=str(sample_completed_delineation_config))

        # run the calculation
        cc._analyze_all_points()
        
        # for all the points:
        for pt in cc.config.points:
            # confirm that we have an analytics object
            assert pt.analytics is not None
            # confirm that the analytics for each frequency exist
            for ri in pt.analytics:
                assert ri.peakflow.time_of_concentration_hr == pt.shed.tc_hr
                assert ri.peakflow.culvert_peakflow_m3s is not None
                assert ri.overflow.culvert_overflow_m3s is not None
                assert ri.peakflow.crossing_peakflow_m3s is not None
                assert ri.overflow.crossing_overflow_m3s is not None
            if pt.include:
                assert pt.capacity.max_return_period is not None

        # for select points
        # crossings:
        test_crossings = list(filter(lambda pt: pt.group_id == "75158", cc.config.points))
        assert len(test_crossings) == 2
        assert test_crossings[0].shed.area_sqkm == test_crossings[0].shed.area_sqkm
        assert test_crossings[0].analytics[0].overflow.crossing_overflow_m3s == test_crossings[1].analytics[0].overflow.crossing_overflow_m3s
        
        output_config_filepath = Path(tmp_path) / 'drainit_config.json'
        # pp(cc.config)
        # cc.save_config(str(output_config_filepath))
        with open(output_config_filepath, 'w') as fp:
            json.dump(asdict(cc.config), fp)

    def test_export(self, tmp_path, sample_completed_capacity_config):

        cc = workflows.CulvertCapacityCore(save_config_json_filepath=str(sample_completed_capacity_config))

        workspace_path = cc.gp.create_workspace(tmp_path, 'outputs')

        cc.config.output_points_filepath = str(Path(workspace_path) / 'points')
        
        cc._export_culvert_featureclass()

        