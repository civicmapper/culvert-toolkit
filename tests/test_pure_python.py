import importlib
import io
import json
import warnings
import zipfile
from pathlib import Path

import numpy as np
import petl as etl
import pytest
import requests

from drainit.calculators import capacity, overflow, runoff
from drainit.models import DrainItPoint, Rainfall, RainfallRasterConfig, Shed, WorkflowConfig
from drainit.services import noaa
from drainit.services.naacc import NaaccEtl


def _zip_bytes(name="nested/rain.asc", content=b"ncols 1\n"):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(name, content)
    return stream.getvalue()


class FakeResponse:
    def __init__(self, *, text="", content=b"", status=200):
        self.text = text
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def test_public_and_pure_modules_import_without_arcpy():
    package = importlib.import_module("drainit")
    for name in ("drainit.calculators", "drainit.models", "drainit.services.naacc", "drainit.services.noaa"):
        importlib.import_module(name)
    workflow_class = package.CulvertCapacity
    with pytest.raises(ModuleNotFoundError, match="arcpy") as error:
        workflow_class()
    assert error.value.name == "arcpy"


def test_peak_flow_dispatch_and_scalar_contract(monkeypatch):
    monkeypatch.setattr(runoff, "qpeak_via_rain_ratio_method1", lambda *args: 12.5)
    result, _ = runoff.peak_flow_calculator(2, 100, 10, 1, 75, tc_hr=1, rain_ratio_method=1)
    assert result == 12.5

    with pytest.raises(ValueError, match="nine-frequency vector"):
        runoff.peak_flow_calculator(2, 100, 10, 1, 75, tc_hr=1, rain_ratio_method=2)
    with pytest.raises(ValueError, match="must be 1 or 2"):
        runoff.peak_flow_calculator(2, 100, 10, 1, 75, tc_hr=1, rain_ratio_method=99)


def test_method2_remains_the_explicit_vector_calculator():
    result = runoff.qpeak_via_rain_ratio_method2(1.0, 2.0, 3.0)
    assert isinstance(result, np.ndarray)
    assert result.shape == (9,)


@pytest.mark.parametrize("tc_hr", [0, -1, float("nan"), float("inf")])
def test_peak_flow_rejects_nonpositive_or_nonfinite_tc_without_numeric_warnings(tc_hr):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        peak, returned_tc = runoff.peak_flow_calculator(
            2, 100, 10, 1, 75, tc_hr=tc_hr
        )
    assert peak is None
    assert returned_tc is tc_hr or returned_tc == tc_hr or np.isnan(returned_tc)
    assert caught == []


def test_rain_ratio_helpers_validate_their_logarithm_and_divisor_inputs():
    with pytest.raises(ValueError, match="tc_hr"):
        runoff.qpeak_via_rain_ratio_method1(1, 10, 0, 1, 1)
    with pytest.raises(ValueError, match="avg_rainfall_cm"):
        runoff.qpeak_via_rain_ratio_method1(1, 0, 1, 1, 1)
    with pytest.raises(ValueError, match="tc_hr"):
        runoff.qpeak_via_rain_ratio_method2(float("nan"), 1, 1)


def test_rainfall_analytics_rederivation_is_idempotent():
    point = DrainItPoint(
        uid=1,
        shed=Shed(avg_rainfall=[
            Rainfall(freq="Y2", dur="24h", value=1.0, units="cm"),
            Rainfall(freq="Y10", dur="24h", value=2.0, units="cm"),
        ]),
    )
    point.derive_rainfall_analytics()
    point.derive_rainfall_analytics()
    assert [(a.frequency, a.avg_rainfall_cm) for a in point.analytics] == [
        ("Y2", 1.0), ("Y10", 2.0)
    ]


def test_none_group_ids_are_never_a_crossing():
    from drainit.workflows import _multiculvert_group_ids

    points = [
        DrainItPoint(uid=1, group_id=None),
        DrainItPoint(uid=2, group_id=None),
        DrainItPoint(uid=3, group_id=7),
        DrainItPoint(uid=4, group_id=7),
    ]
    assert _multiculvert_group_ids(points) == [7]


def test_naacc_explicit_table_argument_overrides_constructor_default(monkeypatch):
    default = etl.wrap([("marker",), ("default",)])
    explicit = etl.wrap([("marker",), ("explicit",)])
    service = NaaccEtl(naacc_petl_table=default)
    observed = {}

    def passthrough(validated_table, **kwargs):
        observed["marker"] = next(iter(etl.dicts(validated_table)))["marker"]
        return validated_table

    monkeypatch.setattr(service, "_extend_and_hydrate", passthrough)
    service.validate_extend_hydrate_naacc_table(naacc_petl_table=explicit)
    assert observed["marker"] == "explicit"


def test_naacc_current_null_sentinel_is_normalized_before_validation(monkeypatch):
    table = etl.wrap([("marker",), (" NULL ",), ("null",)])
    service = NaaccEtl(naacc_petl_table=table)
    observed = []

    def passthrough(validated_table, **kwargs):
        observed.extend(etl.values(validated_table, "marker"))
        return validated_table

    monkeypatch.setattr(service, "_extend_and_hydrate", passthrough)
    service.validate_extend_hydrate_naacc_table()
    assert observed == [None, None]


def test_empty_rainfall_configs_fail_before_workflow_or_download(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="contains no rasters"):
        RainfallRasterConfig().require_rasters()

    config_path = tmp_path / "empty-rainfall.json"
    config_path.write_text(json.dumps({"root": str(tmp_path), "rasters": []}))
    from drainit.workflows import WorkflowManager

    manager = object.__new__(WorkflowManager)
    manager.config = WorkflowConfig(precip_src_config_filepath=str(config_path))
    manager.config_json_filepath = None
    with pytest.raises(ValueError, match="contains no rasters"):
        manager.load_config()

    monkeypatch.setattr(noaa.requests, "post", lambda *a, **k: pytest.fail("request should not run"))
    with pytest.raises(ValueError, match="At least one"):
        noaa.retrieve_noaa_rainfall_rasters(tmp_path / "download", frequencies=[])
    assert not (tmp_path / "download" / "rainfall_rasters_config.json").exists()


def test_scratch_folder_fallback_is_testable_without_arcpy(monkeypatch, tmp_path):
    from drainit.services import gp

    fallback = tmp_path / "drainit-fallback"
    monkeypatch.setattr(gp.tempfile, "gettempdir", lambda: str(fallback))
    assert gp.resolve_scratch_folder(None) == str(fallback)
    assert gp.resolve_scratch_folder(tmp_path) == str(tmp_path)


def test_capacity_and_overflow_only_tolerate_expected_invalid_numeric_inputs():
    assert capacity.calc_culvert_capacity(None, 1, 1, 1) is None
    assert capacity.calc_culvert_capacity(1, 0, 1, 0, coefficient_y=2) is None
    assert overflow.culvert_overflow_calculator(None, 1) is None

    class UnexpectedOperand:
        def __sub__(self, other):
            raise RuntimeError("programming error")

    with pytest.raises(RuntimeError, match="programming error"):
        overflow.culvert_overflow_calculator(UnexpectedOperand(), 1)


def test_noaa_point_request_uses_timeout_and_validates_response(monkeypatch):
    calls = {}

    def fake_get(url, **kwargs):
        calls.update(kwargs)
        return FakeResponse(text="result = [[1, 2]];\nregion = 'ne';")

    monkeypatch.setattr(noaa.requests, "get", fake_get)
    result = noaa.retrieve_noaa_rainfall_pf_est(42, -76, timeout=(1, 2))
    assert result["result"] == [[1, 2]]
    assert calls["timeout"] == (1, 2)

    monkeypatch.setattr(noaa.requests, "get", lambda *a, **k: FakeResponse(text="", status=200))
    with pytest.raises(ValueError, match="empty"):
        noaa.retrieve_noaa_rainfall_pf_est(42, -76)


def test_noaa_request_retries_transport_failures(monkeypatch):
    responses = iter([
        requests.ConnectionError("temporary failure"),
        FakeResponse(text="result = [[1, 2]];\nregion = 'ne';"),
    ])
    calls = []

    def fake_get(*args, **kwargs):
        calls.append(kwargs)
        result = next(responses)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(noaa.requests, "get", fake_get)
    result = noaa.retrieve_noaa_rainfall_pf_est(
        42, -76, max_attempts=2, retry_delay=0
    )
    assert result["result"] == [[1, 2]]
    assert len(calls) == 2


def test_noaa_raster_download_extracts_safe_members_and_writes_complete_config(monkeypatch, tmp_path):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(kwargs)
        return FakeResponse(content=_zip_bytes())

    monkeypatch.setattr(noaa.requests, "post", fake_post)
    config = noaa.retrieve_noaa_rainfall_rasters(tmp_path, frequencies=[2], timeout=(1, 2))
    assert (tmp_path / "nested" / "rain.asc").exists()
    assert (tmp_path / "rainfall_rasters_config.json").exists()
    assert len(config.rasters) == 1
    assert calls[0]["timeout"] == (1, 2)


def test_noaa_raster_download_rejects_traversal_and_partial_success(monkeypatch, tmp_path):
    responses = iter([
        FakeResponse(content=_zip_bytes()),
        FakeResponse(content=_zip_bytes("../escape.asc")),
    ])
    monkeypatch.setattr(noaa.requests, "post", lambda *a, **k: next(responses))

    with pytest.raises(RuntimeError, match="incomplete"):
        noaa.retrieve_noaa_rainfall_rasters(tmp_path, frequencies=[2, 5])
    assert not (tmp_path / "rainfall_rasters_config.json").exists()
    assert not (tmp_path.parent / "escape.asc").exists()
