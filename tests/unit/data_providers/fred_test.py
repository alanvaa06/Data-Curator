import datetime
import decimal
import pytest
import httpx
from kaxanuk.data_curator.data_providers.fred import Fred
from kaxanuk.data_curator.entities import EconomicIndicatorData
from kaxanuk.data_curator.exceptions import DataProviderMissingKeyError, ApiEndpointError

SAMPLE = {"observations": [
    {"date": "2020-01-01", "value": "1.5"},
    {"date": "2020-02-01", "value": "1.6"},
    {"date": "2020-03-01", "value": "."},   # FRED missing sentinel
]}

SAMPLE_LEADING_MISSING = {"observations": [
    {"date": "2020-01-01", "value": "."},   # missing first
    {"date": "2020-02-01", "value": "2.3"},
    {"date": "2020-03-01", "value": "2.4"},
]}

SAMPLE_UNSORTED = {"observations": [
    {"date": "2020-03-01", "value": "3.0"},
    {"date": "2020-01-01", "value": "1.0"},
    {"date": "2020-02-01", "value": "2.0"},
]}


def test_parse_maps_observations():
    data = Fred._parse_observations(
        SAMPLE, series_id="CPIAUCSL",
        start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 3, 1),
    )
    series = data["CPIAUCSL"]
    assert isinstance(series, EconomicIndicatorData)
    assert series.rows["2020-01-01"].value == decimal.Decimal("1.5")
    assert series.rows["2020-02-01"].value == decimal.Decimal("1.6")
    assert series.rows["2020-03-01"].value is None
    assert list(series.rows.keys()) == ["2020-01-01", "2020-02-01", "2020-03-01"]


def test_missing_key_raises():
    with pytest.raises(DataProviderMissingKeyError):
        Fred(api_key=None).get_economic_data(
            series_ids=["CPIAUCSL"], start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 3, 1))


def test_malformed_payload_raises_api_endpoint_error(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {"observations": [{"date": "bad-date", "value": "1"}]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse())
    with pytest.raises(ApiEndpointError):
        Fred(api_key="tok").get_economic_data(
            series_ids=["X"], start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 3, 1))


def test_leading_missing_sentinel_is_none():
    """A '.' as the first value must produce None, not raise."""
    data = Fred._parse_observations(
        SAMPLE_LEADING_MISSING, series_id="UNRATE",
        start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 3, 1),
    )
    series = data["UNRATE"]
    assert series.rows["2020-01-01"].value is None
    assert series.rows["2020-02-01"].value == decimal.Decimal("2.3")


def test_rows_are_sorted_ascending():
    """Rows must be sorted by date ascending regardless of payload order."""
    data = Fred._parse_observations(
        SAMPLE_UNSORTED, series_id="GDP",
        start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 3, 1),
    )
    assert list(data["GDP"].rows.keys()) == ["2020-01-01", "2020-02-01", "2020-03-01"]


def test_empty_string_value_is_none():
    """An empty string value must be treated as missing (None)."""
    payload = {"observations": [{"date": "2020-01-01", "value": ""}]}
    data = Fred._parse_observations(
        payload, series_id="X",
        start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 1, 1),
    )
    assert data["X"].rows["2020-01-01"].value is None


def test_validate_api_key_true_when_set():
    assert Fred(api_key="abc123").validate_api_key() is True


def test_validate_api_key_false_when_none():
    assert Fred(api_key=None).validate_api_key() is False
