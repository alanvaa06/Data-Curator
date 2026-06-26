import datetime
import decimal
import pytest
import httpx
from kaxanuk.data_curator.config_handlers._resolver import resolve_macro_requests
from kaxanuk.data_curator.config_handlers.column_catalog import load_macro_catalog
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


def test_not_found_series_is_skipped_not_fatal(monkeypatch):
    """A 400 'No se encontraron resultados' (stale/unknown id) is skipped, not fatal."""
    not_found = [
        "ErrorInfo:No se encontraron resultados",
        "ErrorDetails:No se encontraron resultados",
        "ErrorCode:100",
    ]

    def fake_get(url, *args, **kwargs):
        return httpx.Response(400, request=httpx.Request("GET", url), json=not_found)

    monkeypatch.setattr(httpx, "get", fake_get)

    out = Inegi(api_key="tok").get_economic_data(
        series_ids=["216064"],
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2020, 3, 1),
    )

    assert out == {}  # series omitted, no exception raised


def test_not_found_skips_only_bad_series_keeps_good(monkeypatch):
    """One stale id must not drop the provider's other (valid) series."""
    not_found = ["ErrorInfo:No se encontraron resultados", "ErrorCode:100"]
    good = {
        "Series": [
            {"INDICADOR": "111", "FREQ": "8",
             "OBSERVATIONS": [{"TIME_PERIOD": "2020/01", "OBS_VALUE": "5.0"}]},
        ]
    }

    def fake_get(url, *args, **kwargs):
        status, body = (400, not_found) if "/216064/" in url else (200, good)
        return httpx.Response(status, request=httpx.Request("GET", url), json=body)

    monkeypatch.setattr(httpx, "get", fake_get)

    out = Inegi(api_key="tok").get_economic_data(
        series_ids=["216064", "111"],
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2020, 3, 1),
    )

    assert "216064" not in out
    assert out["111"].rows["2020-01-01"].value == decimal.Decimal("5.0")


def test_non_not_found_400_stays_fatal(monkeypatch):
    """A 400 that is NOT a 'no results' reply must stay fatal, not be skipped."""
    other_400 = ["ErrorInfo:Token no valido", "ErrorCode:200"]

    def fake_get(url, *args, **kwargs):
        return httpx.Response(400, request=httpx.Request("GET", url), json=other_400)

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(ApiEndpointError):
        Inegi(api_key="tok").get_economic_data(
            series_ids=["216064"],
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2020, 3, 1),
        )


def test_http_error_does_not_leak_token(monkeypatch):
    """A 401 HTTPStatusError must NOT expose the token in the raised message or cause chain."""
    secret_url = "https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml/INDICATOR/216064/es/00/false/BIE/2.0/SUPERSECRET?type=json"  # noqa: S105
    req = httpx.Request("GET", secret_url)
    resp = httpx.Response(401, request=req)
    err = httpx.HTTPStatusError(
        f"Client error '401 Unauthorized' for url '{secret_url}'",
        request=req,
        response=resp,
    )

    class _FakeResponse:
        def raise_for_status(self):
            raise err

        def json(self):  # pragma: no cover — never reached
            return {}

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _FakeResponse())

    with pytest.raises(ApiEndpointError) as excinfo:
        Inegi(api_key="SUPERSECRET").get_economic_data(
            series_ids=["216064"],
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2020, 3, 1),
        )

    assert "SUPERSECRET" not in str(excinfo.value)
    assert "401" in str(excinfo.value)
    assert excinfo.value.__cause__ is None


# --- BISE bank wiring (the free token reaches BISE only, never BIE) ---


def test_provider_builds_bise_url_at_national_geography(monkeypatch):
    """Regression guard: the token is BISE-scoped, so the adapter must query BISE/00, not BIE."""
    captured = {}
    good = {"Series": [{"OBSERVATIONS": [{"TIME_PERIOD": "2020/01", "OBS_VALUE": "100.0"}]}]}

    def fake_get(url, *args, **kwargs):
        captured["url"] = url
        return httpx.Response(200, request=httpx.Request("GET", url), json=good)

    monkeypatch.setattr(httpx, "get", fake_get)

    Inegi(api_key="tok").get_economic_data(
        series_ids=["6207136901"],
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2020, 3, 1),
    )

    url = captured["url"]
    assert "/false/BISE/2.0/" in url
    assert "/false/BIE/" not in url
    assert "/es/00/false/" in url
    assert url.endswith("?type=json")


def test_catalog_pins_igae_to_inegi():
    """e_mx_igae (IGAE index, id 6207136901) is the one catalog column served by INEGI."""
    rows = [row for row in load_macro_catalog() if row["column"] == "e_mx_igae"]
    assert len(rows) == 1
    row = rows[0]
    assert row["provider"] == "inegi"
    assert row["series_id"] == "6207136901"
    assert row["region"] == "MX"
    assert row["frequency"] == "monthly"


def test_resolver_routes_igae_to_inegi():
    assert resolve_macro_requests(("e_mx_igae",)) == {"inegi": [("e_mx_igae", "6207136901")]}


def test_inpc_and_unemployment_stay_off_inegi():
    """INPC and the unemployment rate are BIE-only; they must stay on Banxico/FRED."""
    requests = resolve_macro_requests(("e_mx_inpc", "e_mx_unemployment"))
    assert "inegi" not in requests
    assert ("e_mx_inpc", "SP1") in requests["banxico_sie"]
    assert ("e_mx_unemployment", "LRHUTTTTMXM156S") in requests["fred"]


# --- Quarterly cadence (FREQ 4 Trimestral): post-slash segment is a quarter index ---


def test_parse_quarterly_payload_maps_quarter_to_first_month():
    """A FREQ-4 quarterly series ("YYYY/0Q", Q in 1..4) must map to the quarter's first month."""
    payload = {
        "Series": [
            {
                "INDICADOR": "6200093973",
                "FREQ": "4",
                "OBSERVATIONS": [
                    {"TIME_PERIOD": "2024/04", "OBS_VALUE": "1769806"},  # Q4 -> Oct
                    {"TIME_PERIOD": "2024/03", "OBS_VALUE": "1700000"},  # Q3 -> Jul
                    {"TIME_PERIOD": "2024/02", "OBS_VALUE": "1650000"},  # Q2 -> Apr
                    {"TIME_PERIOD": "2024/01", "OBS_VALUE": "1560697"},  # Q1 -> Jan
                ],
            }
        ]
    }
    data = Inegi._parse_series_payload(
        payload, requested_id="6200093973",
        start_date=datetime.date(2024, 1, 1), end_date=datetime.date(2024, 12, 31),
    )
    rows = data["6200093973"].rows
    assert list(rows.keys()) == ["2024-01-01", "2024-04-01", "2024-07-01", "2024-10-01"]
    assert rows["2024-10-01"].value == decimal.Decimal("1769806")


def test_period_disambiguates_month_vs_quarter_by_freq():
    """The same "YYYY/04" string is April when monthly (FREQ 8) but Q4/October when quarterly (FREQ 4)."""
    assert Inegi._period_to_iso("2024/04", "8") == "2024-04-01"   # monthly -> April
    assert Inegi._period_to_iso("2024/04", "4") == "2024-10-01"   # quarterly -> Q4 -> October
    assert Inegi._period_to_iso("2024/01", "4") == "2024-01-01"   # Q1 -> January
    assert Inegi._period_to_iso("2024", "3") == "2024-01-01"      # annual
    assert Inegi._period_to_iso("2024/06", None) == "2024-06-01"  # no freq -> legacy month path


def test_catalog_pins_unemployed_persons_to_inegi():
    """e_mx_unemployed_persons (ENOE level, id 6200093973) is INEGI-sourced and quarterly."""
    rows = [row for row in load_macro_catalog() if row["column"] == "e_mx_unemployed_persons"]
    assert len(rows) == 1
    row = rows[0]
    assert row["provider"] == "inegi"
    assert row["series_id"] == "6200093973"
    assert row["region"] == "MX"
    assert row["frequency"] == "quarterly"


def test_resolver_routes_unemployed_persons_to_inegi():
    assert resolve_macro_requests(("e_mx_unemployed_persons",)) == {
        "inegi": [("e_mx_unemployed_persons", "6200093973")]
    }
