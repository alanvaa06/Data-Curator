import datetime
import decimal

import pytest

from kaxanuk.data_curator.entities import MarketDataDailyRow
from kaxanuk.data_curator.exceptions import EntityValueError


def _base_kwargs():
    return {
        "date": datetime.date(2020, 1, 1),
        "open": None,
        "high": None,
        "low": None,
        "close": None,
        "volume": None,
        "vwap": None,
        "open_split_adjusted": None,
        "high_split_adjusted": None,
        "low_split_adjusted": None,
        "close_split_adjusted": None,
        "volume_split_adjusted": None,
        "vwap_split_adjusted": None,
        "open_dividend_and_split_adjusted": None,
        "high_dividend_and_split_adjusted": None,
        "low_dividend_and_split_adjusted": None,
        "close_dividend_and_split_adjusted": None,
        "volume_dividend_and_split_adjusted": None,
        "vwap_dividend_and_split_adjusted": None,
    }


def test_row_rejects_nan_ohlc_with_entity_value_error():
    # A NaN OHLC value must fail as a catchable EntityValueError, not a raw
    # decimal.InvalidOperation (which would escape the entity-packing try/except
    # and abort the whole symbol/date-range block).
    kwargs = _base_kwargs()
    kwargs["open"] = decimal.Decimal("NaN")
    with pytest.raises(EntityValueError):
        MarketDataDailyRow(**kwargs)


def test_row_rejects_infinity_ohlc_with_entity_value_error():
    # +Infinity < 0 is False, so the old negative-guard silently accepted it.
    # A non-finite value must be rejected as EntityValueError.
    kwargs = _base_kwargs()
    kwargs["close"] = decimal.Decimal("Infinity")
    with pytest.raises(EntityValueError):
        MarketDataDailyRow(**kwargs)


def test_row_accepts_finite_ohlc():
    kwargs = _base_kwargs()
    kwargs["open"] = decimal.Decimal("1")
    kwargs["high"] = decimal.Decimal("2")
    kwargs["low"] = decimal.Decimal("1")
    kwargs["close"] = decimal.Decimal("2")
    kwargs["volume"] = 1000
    row = MarketDataDailyRow(**kwargs)
    assert row.open == decimal.Decimal("1")
    assert row.volume == 1000
