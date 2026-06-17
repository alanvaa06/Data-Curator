import datetime
import decimal
import pytest
from kaxanuk.data_curator.entities import (
    EconomicIndicatorData,
    EconomicIndicatorRow,
)
from kaxanuk.data_curator.exceptions import EntityValueError


def test_row_holds_date_and_value():
    row = EconomicIndicatorRow(date=datetime.date(2020, 1, 1), value=decimal.Decimal("4.25"))
    assert row.date == datetime.date(2020, 1, 1)
    assert row.value == decimal.Decimal("4.25")


def test_row_allows_none_value():
    row = EconomicIndicatorRow(date=datetime.date(2020, 1, 1), value=None)
    assert row.value is None


def test_data_holds_sorted_rows_and_metadata():
    rows = {
        "2020-01-01": EconomicIndicatorRow(date=datetime.date(2020, 1, 1), value=decimal.Decimal("4.25")),
        "2020-02-01": EconomicIndicatorRow(date=datetime.date(2020, 2, 1), value=decimal.Decimal("4.50")),
    }
    data = EconomicIndicatorData(
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2020, 2, 1),
        series_id="SF61745",
        series_name="Mexico overnight target rate",
        rows=rows,
    )
    assert data.series_id == "SF61745"
    assert list(data.rows.keys()) == ["2020-01-01", "2020-02-01"]


def test_data_rejects_unsorted_rows():
    rows = {
        "2020-02-01": EconomicIndicatorRow(date=datetime.date(2020, 2, 1), value=decimal.Decimal("4.50")),
        "2020-01-01": EconomicIndicatorRow(date=datetime.date(2020, 1, 1), value=decimal.Decimal("4.25")),
    }
    with pytest.raises(EntityValueError):
        EconomicIndicatorData(
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2020, 2, 1),
            series_id="SF61745",
            series_name="x",
            rows=rows,
        )
