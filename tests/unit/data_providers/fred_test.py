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


def test_non_finite_value_is_treated_as_missing():
    """A value that coerces to a non-finite Decimal (NaN/Infinity) must be stored
    as missing (None), not as a live value."""
    payload = {"observations": [
        {"date": "2020-01-01", "value": "NaN"},
        {"date": "2020-02-01", "value": "1.6"},
    ]}
    data = Fred._parse_observations(
        payload, series_id="X",
        start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 2, 1),
    )
    assert data["X"].rows["2020-01-01"].value is None
    assert data["X"].rows["2020-02-01"].value == decimal.Decimal("1.6")


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


def test_series_not_found_is_skipped_not_fatal(monkeypatch):
    """A 400 'The series does not exist' (stale/unknown id) is skipped, not fatal."""
    body = {"error_code": 400, "error_message": "Bad Request.  The series does not exist."}

    def fake_get(url=None, *args, params=None, **kwargs):
        return httpx.Response(
            400, request=httpx.Request("GET", "https://api.stlouisfed.org/fred/series/observations"), json=body
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    out = Fred(api_key="tok").get_economic_data(
        series_ids=["NOPE"],
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2020, 3, 1),
    )

    assert out == {}  # series omitted, no exception raised


def test_bad_api_key_400_stays_fatal(monkeypatch):
    """A 400 for an unregistered api_key must STAY fatal — never misread as not-found."""
    body = {
        "error_code": 400,
        "error_message": "Bad Request.  The value for variable api_key is not registered.",
    }

    def fake_get(url=None, *args, params=None, **kwargs):
        return httpx.Response(
            400, request=httpx.Request("GET", "https://api.stlouisfed.org/fred/series/observations"), json=body
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(ApiEndpointError):
        Fred(api_key="tok").get_economic_data(
            series_ids=["GDP"],
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2020, 3, 1),
        )


def test_not_found_skips_only_bad_series_keeps_good(monkeypatch):
    """One stale id must not drop the request's other (valid) series."""
    good = {"observations": [{"date": "2020-01-01", "value": "1.5"}]}
    not_found = {"error_code": 400, "error_message": "Bad Request.  The series does not exist."}

    def fake_get(url=None, *args, params=None, **kwargs):
        sid = params["series_id"]
        status, payload = (400, not_found) if sid == "NOPE" else (200, good)
        return httpx.Response(
            status, request=httpx.Request("GET", "https://api.stlouisfed.org/fred/series/observations"), json=payload
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    out = Fred(api_key="tok").get_economic_data(
        series_ids=["NOPE", "GDP"],
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2020, 3, 1),
    )

    assert "NOPE" not in out
    assert out["GDP"].rows["2020-01-01"].value == decimal.Decimal("1.5")


def test_http_error_does_not_leak_api_key(monkeypatch):
    """A 401 HTTPStatusError must NOT expose the api_key in the raised message or cause chain."""
    req = httpx.Request("GET", "https://api.stlouisfed.org/fred/series/observations?api_key=SUPERSECRET")
    resp = httpx.Response(401, request=req)
    err = httpx.HTTPStatusError(
        "Client error '401 Unauthorized' for url 'https://api.stlouisfed.org/fred/series/observations?api_key=SUPERSECRET'",
        request=req,
        response=resp,
    )

    class _FakeResponse:
        def raise_for_status(self):
            raise err

        def json(self):  # pragma: no cover — never reached
            return {}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse())

    with pytest.raises(ApiEndpointError) as excinfo:
        Fred(api_key="SUPERSECRET").get_economic_data(
            series_ids=["X"],
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2020, 3, 1),
        )

    assert "SUPERSECRET" not in str(excinfo.value)
    assert "401" in str(excinfo.value)
    assert excinfo.value.__cause__ is None
