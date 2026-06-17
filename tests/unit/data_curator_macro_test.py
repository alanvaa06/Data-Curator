"""
Task 8 — main() fetches macro data once (globally) and broadcasts it to every identifier.

These tests prove:
  * macro is fetched exactly ONCE for the whole run (not per-ticker);
  * each identifier's output table carries the requested e_* macro column,
    forward-filled to a real value; and
  * with no macro providers, main() stays fully backward-compatible (no e_* columns).
  * a fatal error in the macro fetch causes main() to return False, NOT raise.
"""

import datetime
import decimal
import threading

import httpx

from kaxanuk.data_curator import data_curator
from kaxanuk.data_curator.data_providers import DataProviderInterface, MacroDataProviderInterface
from kaxanuk.data_curator.entities import (
    Configuration,
    DividendData,
    FundamentalData,
    MainIdentifier,
    MarketData,
    MarketDataDailyRow,
    SplitData,
)
from kaxanuk.data_curator.output_handlers import OutputHandlerInterface

from tests.unit.data_providers.fake_macro_provider import FakeMacroProvider


def _build_market_data(identifier, start_date, end_date):
    price = decimal.Decimal('100')
    rows = {}
    row_date = start_date
    while row_date <= end_date:
        rows[row_date.isoformat()] = MarketDataDailyRow(
            date=row_date,
            open=price,
            high=price,
            low=price,
            close=price,
            volume=1000,
            vwap=price,
            open_split_adjusted=price,
            high_split_adjusted=price,
            low_split_adjusted=price,
            close_split_adjusted=price,
            volume_split_adjusted=1000,
            vwap_split_adjusted=price,
            open_dividend_and_split_adjusted=price,
            high_dividend_and_split_adjusted=price,
            low_dividend_and_split_adjusted=price,
            close_dividend_and_split_adjusted=price,
            volume_dividend_and_split_adjusted=1000,
            vwap_dividend_and_split_adjusted=price,
        )
        row_date += datetime.timedelta(days=1)

    return MarketData(
        start_date=start_date,
        end_date=end_date,
        main_identifier=MainIdentifier(identifier),
        daily_rows=rows,
    )


class StubMarketDataProvider(DataProviderInterface):
    """Minimal equity provider: a couple of daily MarketData rows per identifier, no network."""

    def get_market_data(self, *, main_identifier, start_date, end_date):
        return _build_market_data(main_identifier, start_date, end_date)

    def get_dividend_data(self, *, main_identifier, start_date, end_date):
        return DividendData(main_identifier=MainIdentifier(main_identifier), rows={})

    def get_fundamental_data(self, *, main_identifier, period, start_date, end_date):
        return FundamentalData(main_identifier=MainIdentifier(main_identifier), rows={})

    def get_split_data(self, *, main_identifier, start_date, end_date):
        return SplitData(main_identifier=MainIdentifier(main_identifier), rows={})

    def initialize(self, *, configuration):
        pass

    def validate_api_key(self):
        return None


class CaptureOutputHandler(OutputHandlerInterface):
    """Stores each identifier's columns table for later inspection."""

    def __init__(self):
        self.tables = {}
        self._lock = threading.Lock()

    def output_data(self, *, main_identifier, columns):
        with self._lock:
            self.tables[main_identifier] = columns
        return True


def _build_configuration(identifiers, columns):
    return Configuration(
        start_date=datetime.date(2024, 1, 1),
        end_date=datetime.date(2024, 1, 10),
        period='annual',
        identifiers=tuple(identifiers),
        columns=tuple(columns),
    )


def _counting_macro_provider():
    """A FakeMacroProvider whose get_economic_data is wrapped with a call counter."""
    macro = FakeMacroProvider(
        # obs at 2019-12-01 so it forward-fills to a real value (not None)
        # under _infill_data's strict '>' boundary for 2024 market dates.
        monthly_values={"SF61745": [("2019-12-01", "7.25")]},
        provider_name="banxico_sie",
    )
    counter = {"calls": 0}
    original = macro.get_economic_data

    def counting_get_economic_data(*, series_ids, start_date, end_date):
        counter["calls"] += 1
        return original(series_ids=series_ids, start_date=start_date, end_date=end_date)

    macro.get_economic_data = counting_get_economic_data

    return macro, counter


class TestMainMacroBroadcast:
    def test_macro_fetched_once_and_broadcast_to_all_identifiers(self):
        macro, counter = _counting_macro_provider()
        handler = CaptureOutputHandler()

        result = data_curator.main(
            configuration=_build_configuration(
                ('AAA', 'BBB'),
                ('m_close', 'e_mx_target_rate'),
            ),
            market_data_provider=StubMarketDataProvider(),
            fundamental_data_provider=None,
            output_handlers=[handler],
            macro_data_providers=[macro],
            max_concurrent_computations=1,
        )

        assert result is True
        # (a) macro fetched exactly once for the whole run, NOT per-ticker
        assert counter["calls"] == 1
        # (b) both identifiers carry the macro column
        assert 'e_mx_target_rate' in handler.tables['AAA'].column_names
        assert 'e_mx_target_rate' in handler.tables['BBB'].column_names
        # (c) the macro value is forward-filled to a real value on every row
        for identifier in ('AAA', 'BBB'):
            values = handler.tables[identifier].column('e_mx_target_rate').to_pylist()
            assert decimal.Decimal('7.25') in values

    def test_macro_fetched_once_across_parallel_compute(self):
        # economic_data crosses the ProcessPool boundary; prove the single fetch
        # still broadcasts correctly when computations run in worker processes.
        macro, counter = _counting_macro_provider()
        handler = CaptureOutputHandler()

        result = data_curator.main(
            configuration=_build_configuration(
                ('AAA', 'BBB', 'CCC'),
                ('m_close', 'e_mx_target_rate'),
            ),
            market_data_provider=StubMarketDataProvider(),
            fundamental_data_provider=None,
            output_handlers=[handler],
            macro_data_providers=[macro],
            max_concurrent_computations=2,
        )

        assert result is True
        assert counter["calls"] == 1
        for identifier in ('AAA', 'BBB', 'CCC'):
            assert 'e_mx_target_rate' in handler.tables[identifier].column_names
            values = handler.tables[identifier].column('e_mx_target_rate').to_pylist()
            assert decimal.Decimal('7.25') in values


class TestMainMacroBackwardCompatibility:
    def test_no_macro_providers_produces_no_e_columns(self):
        handler = CaptureOutputHandler()

        result = data_curator.main(
            configuration=_build_configuration(
                ('AAA', 'BBB'),
                ('m_date', 'm_close'),
            ),
            market_data_provider=StubMarketDataProvider(),
            fundamental_data_provider=None,
            output_handlers=[handler],
            # macro_data_providers omitted -> defaults to None
        )

        assert result is True
        for identifier in ('AAA', 'BBB'):
            column_names = handler.tables[identifier].column_names
            assert not any(name.startswith('e_') for name in column_names)


class RaisingMacroProvider(MacroDataProviderInterface):
    """A macro provider whose get_economic_data always raises, to test the fatal-error contract."""

    def __init__(self, *, error: Exception, provider_name: str = "banxico_sie"):
        self.macro_provider_name = provider_name
        self._error = error

    def get_economic_data(self, *, series_ids, start_date, end_date):
        raise self._error

    def validate_api_key(self):
        return None


class TestMainMacroFatalErrorContract:
    """main() must return False on a fatal macro fetch error, never raise."""

    def test_httpx_connect_error_returns_false(self):
        """A network blip (httpx.ConnectError) from the macro provider returns False, not raise."""
        handler = CaptureOutputHandler()

        result = data_curator.main(
            configuration=_build_configuration(
                ('AAA',),
                ('m_close', 'e_mx_target_rate'),
            ),
            market_data_provider=StubMarketDataProvider(),
            fundamental_data_provider=None,
            output_handlers=[handler],
            macro_data_providers=[
                RaisingMacroProvider(
                    error=httpx.ConnectError("boom"),
                    provider_name="banxico_sie",
                )
            ],
        )

        assert result is False

    def test_httpx_http_status_error_returns_false(self):
        """An HTTP 500 from the macro provider (httpx.HTTPStatusError) returns False, not raise."""
        handler = CaptureOutputHandler()
        request = httpx.Request("GET", "https://example.com")
        response = httpx.Response(500, request=request)

        result = data_curator.main(
            configuration=_build_configuration(
                ('AAA',),
                ('m_close', 'e_mx_target_rate'),
            ),
            market_data_provider=StubMarketDataProvider(),
            fundamental_data_provider=None,
            output_handlers=[handler],
            macro_data_providers=[
                RaisingMacroProvider(
                    error=httpx.HTTPStatusError("server error", request=request, response=response),
                    provider_name="banxico_sie",
                )
            ],
        )

        assert result is False
