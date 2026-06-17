"""
Unit tests for the DBnomics macro data adapter.
"""

import datetime
import decimal
import pytest
import httpx
from kaxanuk.data_curator.data_providers.dbnomics import Dbnomics
from kaxanuk.data_curator.entities import EconomicIndicatorData
from kaxanuk.data_curator.exceptions import ApiEndpointError

SAMPLE = {"series": {"docs": [
    {"series_code": "M.I15.CP00.EA", "dataset_code": "prc_hicp_midx", "provider_code": "Eurostat",
     "period": ["2020-01", "2020-02", "2020-03"],
     "value": [105.1, 105.4, "NA"]},
]}}


def test_parse_maps_parallel_arrays():
    data = Dbnomics._parse_series_payload(
        SAMPLE, requested_id="Eurostat/prc_hicp_midx/M.I15.CP00.EA",
        start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 3, 1),
    )
    series = data["Eurostat/prc_hicp_midx/M.I15.CP00.EA"]
    assert isinstance(series, EconomicIndicatorData)
    assert series.rows["2020-01-01"].value == decimal.Decimal("105.1")
    assert series.rows["2020-03-01"].value is None  # "NA" -> None
    assert list(series.rows.keys()) == ["2020-01-01", "2020-02-01", "2020-03-01"]


def test_parse_annual_and_daily_periods():
    payload = {"series": {"docs": [{"period": ["2020", "2021-06-15"], "value": [1.0, 2.0]}]}}
    data = Dbnomics._parse_series_payload(payload, requested_id="X",
        start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2021, 12, 31))
    assert data["X"].rows["2020-01-01"].value == decimal.Decimal("1.0")
    assert data["X"].rows["2021-06-15"].value == decimal.Decimal("2.0")


def test_keyless_validate_returns_none():
    assert Dbnomics(api_key=None).validate_api_key() is None


def test_malformed_payload_raises_api_endpoint_error(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {"series": {"docs": [{"period": ["not-a-date"], "value": [1.0]}]}}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse())
    with pytest.raises(ApiEndpointError):
        Dbnomics(api_key=None).get_economic_data(
            series_ids=["X"], start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 3, 1))
