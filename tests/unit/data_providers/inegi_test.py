import datetime
import decimal
import pytest
import httpx
from kaxanuk.data_curator.data_providers.inegi import Inegi
from kaxanuk.data_curator.entities import EconomicIndicatorData
from kaxanuk.data_curator.exceptions import ApiEndpointError, DataProviderMissingKeyError

# Monthly INPC sample, NEWEST-FIRST as INEGI returns it, with a missing value:
SAMPLE = {
    "Header": {"Name": "BIE"},
    "Series": [
        {"INDICADOR": "216064", "FREQ": "8",
         "OBSERVATIONS": [
             {"TIME_PERIOD": "2020/03", "OBS_VALUE": ""},
             {"TIME_PERIOD": "2020/02", "OBS_VALUE": "101.2"},
             {"TIME_PERIOD": "2020/01", "OBS_VALUE": "100.5"},
         ]},
    ],
}


def test_parse_maps_inegi_observations_sorted_ascending():
    data = Inegi._parse_series_payload(
        SAMPLE, requested_id="216064",
        start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 3, 1),
    )
    series = data["216064"]
    assert isinstance(series, EconomicIndicatorData)
    assert list(series.rows.keys()) == ["2020-01-01", "2020-02-01", "2020-03-01"]  # sorted ascending
    assert series.rows["2020-01-01"].value == decimal.Decimal("100.5")
    assert series.rows["2020-03-01"].value is None  # "" -> None


def test_parse_annual_period():
    payload = {"Series": [{"INDICADOR": "1", "FREQ": "1",
        "OBSERVATIONS": [{"TIME_PERIOD": "2020", "OBS_VALUE": "5.0"}]}]}
    data = Inegi._parse_series_payload(payload, requested_id="1",
        start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 12, 31))
    assert data["1"].rows["2020-01-01"].value == decimal.Decimal("5.0")


def test_get_economic_data_raises_without_token():
    with pytest.raises(DataProviderMissingKeyError):
        Inegi(api_key=None).get_economic_data(
            series_ids=["216064"], start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 3, 1))


def test_malformed_payload_raises_api_endpoint_error(monkeypatch):
    """A malformed HTTP-200 body must surface as ApiEndpointError, not a raw traceback."""
    # Payload has an unparseable TIME_PERIOD string — triggers ValueError in _period_to_iso
    malformed_payload = {
        "Series": [
            {"INDICADOR": "216064", "FREQ": "8",
             "OBSERVATIONS": [{"TIME_PERIOD": "not-a-date", "OBS_VALUE": "5.0"}]},
        ]
    }

    class _FakeResponse:
        def raise_for_status(self):
            pass  # pretend HTTP 200

        def json(self):
            return malformed_payload

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _FakeResponse())

    provider = Inegi(api_key="tok")
    with pytest.raises(ApiEndpointError):
        provider.get_economic_data(
            series_ids=["216064"],
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2020, 3, 1),
        )
