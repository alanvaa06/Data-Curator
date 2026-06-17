import datetime
import decimal

import pytest

from kaxanuk.data_curator.data_providers.banxico_sie import BanxicoSie
from kaxanuk.data_curator.entities import EconomicIndicatorData
from kaxanuk.data_curator.exceptions import DataProviderMissingKeyError

SAMPLE = {
    "bmx": {"series": [
        {"idSerie": "SF61745", "titulo": "Tasa objetivo",
         "datos": [{"fecha": "01/01/2020", "dato": "7.25"},
                   {"fecha": "01/02/2020", "dato": "7.00"},
                   {"fecha": "01/03/2020", "dato": "N/E"}]},
    ]}
}

SAMPLE_TWO_SERIES = {
    "bmx": {"series": [
        {"idSerie": "SF61745", "titulo": "Tasa objetivo",
         "datos": [{"fecha": "01/01/2020", "dato": "7.25"},
                   {"fecha": "01/02/2020", "dato": "7.00"}]},
        {"idSerie": "SF43783", "titulo": "INPC",
         "datos": [{"fecha": "01/01/2020", "dato": "1,234.56"},
                   {"fecha": "01/02/2020", "dato": "1,240.00"}]},
    ]}
}

SAMPLE_EMPTY_STRING = {
    "bmx": {"series": [
        {"idSerie": "SF61745", "titulo": "Tasa objetivo",
         "datos": [{"fecha": "01/01/2020", "dato": ""},
                   {"fecha": "01/02/2020", "dato": "7.00"}]},
    ]}
}


def test_parse_maps_series_to_entity():
    data = BanxicoSie._parse_series_payload(
        SAMPLE, start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 3, 1),
    )
    series = data["SF61745"]
    assert isinstance(series, EconomicIndicatorData)
    assert series.rows["2020-01-01"].value == decimal.Decimal("7.25")
    assert series.rows["2020-03-01"].value is None  # N/E -> None
    assert list(series.rows.keys()) == ["2020-01-01", "2020-02-01", "2020-03-01"]


def test_parse_comma_thousands_value():
    """Comma-separated thousands (e.g. 1,234.56) must be parsed correctly."""
    data = BanxicoSie._parse_series_payload(
        SAMPLE_TWO_SERIES,
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2020, 2, 1),
    )
    inpc = data["SF43783"]
    assert inpc.rows["2020-01-01"].value == decimal.Decimal("1234.56")
    assert inpc.rows["2020-02-01"].value == decimal.Decimal("1240.00")


def test_parse_multiple_series_in_one_payload():
    """Multiple series in a single payload are all returned."""
    data = BanxicoSie._parse_series_payload(
        SAMPLE_TWO_SERIES,
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2020, 2, 1),
    )
    assert set(data.keys()) == {"SF61745", "SF43783"}
    assert data["SF61745"].series_name == "Tasa objetivo"
    assert data["SF43783"].series_name == "INPC"


def test_parse_empty_string_treated_as_missing():
    """An empty string dato is treated as None (missing), same as 'N/E'."""
    data = BanxicoSie._parse_series_payload(
        SAMPLE_EMPTY_STRING,
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2020, 2, 1),
    )
    assert data["SF61745"].rows["2020-01-01"].value is None
    assert data["SF61745"].rows["2020-02-01"].value == decimal.Decimal("7.00")


def test_rows_are_sorted_by_date():
    """rows dict must be sorted ascending by date regardless of payload order."""
    unsorted_payload = {
        "bmx": {"series": [
            {"idSerie": "SF61745", "titulo": "Tasa objetivo",
             "datos": [{"fecha": "01/03/2020", "dato": "6.50"},
                       {"fecha": "01/01/2020", "dato": "7.25"},
                       {"fecha": "01/02/2020", "dato": "7.00"}]},
        ]}
    }
    data = BanxicoSie._parse_series_payload(
        unsorted_payload,
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2020, 3, 1),
    )
    assert list(data["SF61745"].rows.keys()) == ["2020-01-01", "2020-02-01", "2020-03-01"]


def test_validate_api_key_true_when_token_set():
    provider = BanxicoSie(api_key="a" * 64)
    assert provider.validate_api_key() is True


def test_validate_api_key_false_when_none():
    provider = BanxicoSie(api_key=None)
    assert provider.validate_api_key() is False


def test_get_economic_data_raises_without_token():
    """get_economic_data must fail fast with DataProviderMissingKeyError — no network needed."""
    provider = BanxicoSie(api_key=None)
    with pytest.raises(DataProviderMissingKeyError):
        provider.get_economic_data(
            series_ids=["SF61745"],
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2020, 3, 1),
        )


SAMPLE_NUMERIC_DATO = {
    "bmx": {"series": [
        {"idSerie": "SF61745", "titulo": "Tasa objetivo",
         "datos": [{"fecha": "01/01/2020", "dato": 7.25}]},
    ]}
}


def test_parse_numeric_dato():
    """A numeric (float/int) dato in the JSON must parse to the correct Decimal."""
    data = BanxicoSie._parse_series_payload(
        SAMPLE_NUMERIC_DATO,
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2020, 1, 1),
    )
    assert data["SF61745"].rows["2020-01-01"].value == decimal.Decimal("7.25")
