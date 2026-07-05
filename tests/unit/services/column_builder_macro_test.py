"""
Tests for ColumnBuilder's macro-economic (e_*) column emission and forward-fill.

The macro series are non-ticker: a single (date, value) series is forward-filled
onto each ticker's market dates via the existing _infill_data, and exposed through
a new `case 'e':` in _process_columns_with_available_dependencies.
"""

import datetime
import decimal

import pytest

from kaxanuk.data_curator.entities import (
    Configuration,
    DividendData,
    EconomicIndicatorData,
    EconomicIndicatorRow,
    FundamentalData,
    MainIdentifier,
    MarketData,
    MarketDataDailyRow,
    SplitData,
)
from kaxanuk.data_curator.exceptions import ColumnBuilderUnavailableEntityFieldError
from kaxanuk.data_curator.features import calculations
from kaxanuk.data_curator.services.column_builder import ColumnBuilder


def _market(dates):
    rows = {
        d: MarketDataDailyRow(
            date=datetime.date.fromisoformat(d),
            open=None,
            high=None,
            low=None,
            close=decimal.Decimal("1"),
            volume=None,
            vwap=None,
            open_split_adjusted=None,
            high_split_adjusted=None,
            low_split_adjusted=None,
            close_split_adjusted=None,
            volume_split_adjusted=None,
            vwap_split_adjusted=None,
            open_dividend_and_split_adjusted=None,
            high_dividend_and_split_adjusted=None,
            low_dividend_and_split_adjusted=None,
            close_dividend_and_split_adjusted=None,
            volume_dividend_and_split_adjusted=None,
            vwap_dividend_and_split_adjusted=None,
        )
        for d in dates
    }

    return MarketData(
        start_date=datetime.date.fromisoformat(dates[0]),
        end_date=datetime.date.fromisoformat(dates[-1]),
        main_identifier=MainIdentifier("AAPL"),
        daily_rows=rows,
    )


def _empty_fundamentals(ident="AAPL"):
    return (
        FundamentalData(main_identifier=MainIdentifier(ident), rows={}),
        DividendData(main_identifier=MainIdentifier(ident), rows={}),
        SplitData(main_identifier=MainIdentifier(ident), rows={}),
    )


def _configuration():
    # Configuration.columns is validated against the m_/f_/c_/d_/s_ prefixes only;
    # the e_ columns are passed directly to process_columns, not stored here.
    return Configuration(
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2020, 2, 15),
        period="quarterly",
        identifiers=("AAPL",),
        columns=("m_close",),
    )


def _builder(market, fundamentals, dividends, splits, economic_data):
    return ColumnBuilder(
        calculation_modules=[calculations],
        configuration=_configuration(),
        dividend_data=dividends,
        fundamental_data=fundamentals,
        market_data=market,
        split_data=splits,
        economic_data=economic_data,
    )


def test_macro_column_forward_fills_to_market_dates():
    market = _market(["2020-01-01", "2020-01-15", "2020-02-01", "2020-02-15"])
    fundamentals, dividends, splits = _empty_fundamentals()
    # First observation (2019-12-01) precedes the first market date, so every market date has a
    # prior value to carry forward. (_infill_data only assigns a value once a market date is strictly
    # past an observation; an observation that coincides with the first market date would leave that
    # first date None -- see test_macro_leading_dates_before_first_observation_are_none.)
    economic_data = {
        "e_mx_target_rate": EconomicIndicatorData(
            start_date=datetime.date(2019, 12, 1),
            end_date=datetime.date(2020, 2, 1),
            series_id="SF61745",
            series_name="rate",
            rows={
                "2019-12-01": EconomicIndicatorRow(
                    date=datetime.date(2019, 12, 1), value=decimal.Decimal("7.25")
                ),
                "2020-02-01": EconomicIndicatorRow(
                    date=datetime.date(2020, 2, 1), value=decimal.Decimal("7.00")
                ),
            },
        )
    }

    builder = _builder(market, fundamentals, dividends, splits, economic_data)
    table = builder.process_columns(("m_close", "e_mx_target_rate"))

    col = table.column("e_mx_target_rate").to_pylist()
    # Jan 1 & Jan 15 carry 7.25 (from the Dec 1 observation); Feb 1 & Feb 15 carry 7.00 (forward fill)
    assert [str(v) for v in col] == ["7.25", "7.25", "7.00", "7.00"]


def test_macro_leading_dates_before_first_observation_are_none():
    # Market dates start 2020-01-01 but the series' first observation is 2020-02-01,
    # so the January dates have nothing to forward-fill from yet -> None.
    market = _market(["2020-01-01", "2020-01-15", "2020-02-01", "2020-02-15"])
    fundamentals, dividends, splits = _empty_fundamentals()
    economic_data = {
        "e_mx_target_rate": EconomicIndicatorData(
            start_date=datetime.date(2020, 2, 1),
            end_date=datetime.date(2020, 2, 1),
            series_id="SF61745",
            series_name="rate",
            rows={
                "2020-02-01": EconomicIndicatorRow(
                    date=datetime.date(2020, 2, 1), value=decimal.Decimal("7.00")
                ),
            },
        )
    }

    builder = _builder(market, fundamentals, dividends, splits, economic_data)
    table = builder.process_columns(("m_close", "e_mx_target_rate"))

    col = table.column("e_mx_target_rate").to_pylist()
    assert col[0] is None
    assert col[1] is None
    assert [str(v) for v in col[2:]] == ["7.00", "7.00"]


def test_unknown_economic_column_raises():
    market = _market(["2020-01-01", "2020-01-15", "2020-02-01", "2020-02-15"])
    fundamentals, dividends, splits = _empty_fundamentals()
    economic_data = {
        "e_mx_target_rate": EconomicIndicatorData(
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2020, 1, 1),
            series_id="SF61745",
            series_name="rate",
            rows={
                "2020-01-01": EconomicIndicatorRow(
                    date=datetime.date(2020, 1, 1), value=decimal.Decimal("7.25")
                ),
            },
        )
    }

    builder = _builder(market, fundamentals, dividends, splits, economic_data)
    with pytest.raises(ColumnBuilderUnavailableEntityFieldError, match="economic data"):
        builder.process_columns(("e_not_in_economic_data",))


def test_macro_forward_fill_uses_latest_observation_denser_than_market_grid():
    # Regression: when >=2 observations fall strictly between two consecutive market
    # dates (a daily macro series published on weekends over a business-day grid), the
    # forward-fill must carry the LATEST observation <= the market date. _infill_data's
    # else-branch advanced the observation cursor only ONE step per market date, so it
    # lagged behind and returned a stale earlier value when observations were denser
    # than the date grid.
    market = _market(["2020-01-06", "2020-01-20"])
    fundamentals, dividends, splits = _empty_fundamentals()
    economic_data = {
        "e_mx_target_rate": EconomicIndicatorData(
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2020, 1, 18),
            series_id="SF61745",
            series_name="rate",
            rows={
                "2020-01-01": EconomicIndicatorRow(
                    date=datetime.date(2020, 1, 1), value=decimal.Decimal("1")
                ),
                "2020-01-10": EconomicIndicatorRow(
                    date=datetime.date(2020, 1, 10), value=decimal.Decimal("2")
                ),
                "2020-01-15": EconomicIndicatorRow(
                    date=datetime.date(2020, 1, 15), value=decimal.Decimal("3")
                ),
                "2020-01-18": EconomicIndicatorRow(
                    date=datetime.date(2020, 1, 18), value=decimal.Decimal("4")
                ),
            },
        )
    }

    builder = _builder(market, fundamentals, dividends, splits, economic_data)
    table = builder.process_columns(("m_close", "e_mx_target_rate"))

    col = table.column("e_mx_target_rate").to_pylist()
    # 2020-01-06 -> latest obs <= it = 2020-01-01 (=1).
    # 2020-01-20 -> latest obs <= it = 2020-01-18 (=4), NOT the stale 2020-01-10 (=2)
    # produced by advancing the observation cursor only one step.
    assert [str(v) for v in col] == ["1", "4"]
