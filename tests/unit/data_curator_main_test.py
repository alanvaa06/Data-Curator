import datetime
import decimal
import threading

import pytest

from kaxanuk.data_curator import data_curator
from kaxanuk.data_curator.data_providers import DataProviderInterface
from kaxanuk.data_curator.entities import (
    Configuration,
    DividendData,
    FundamentalData,
    MainIdentifier,
    MarketData,
    MarketDataDailyRow,
    SplitData,
)
from kaxanuk.data_curator.exceptions import (
    ApiEndpointError,
    IdentifierNotFoundError,
    PassedArgumentError,
)
from kaxanuk.data_curator.output_handlers import OutputHandlerInterface


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


def _build_configuration(identifiers):
    return Configuration(
        start_date=datetime.date(2024, 1, 1),
        end_date=datetime.date(2024, 1, 10),
        period='annual',
        identifiers=tuple(identifiers),
        columns=('m_date', 'm_close'),
    )


class StubMarketDataProvider(DataProviderInterface):
    def __init__(self, *, fail_identifiers=(), fatal_identifiers=(), barrier=None):
        self.fail_identifiers = set(fail_identifiers)
        self.fatal_identifiers = set(fatal_identifiers)
        self.barrier = barrier

    def get_market_data(self, *, main_identifier, start_date, end_date):
        if self.barrier is not None:
            # only passes if at least 2 fetches run concurrently
            self.barrier.wait(timeout=10)
        if main_identifier in self.fail_identifiers:
            msg = f"{main_identifier} not found"
            raise IdentifierNotFoundError(msg)
        if main_identifier in self.fatal_identifiers:
            msg = f"{main_identifier} endpoint exploded"
            raise ApiEndpointError(msg)
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


class RecordingOutputHandler(OutputHandlerInterface):
    def __init__(self):
        self.identifiers = []

    def output_data(self, *, main_identifier, columns):
        self.identifiers.append(main_identifier)
        return True


class TestMainParallelFetch:
    def test_output_order_matches_configuration_order(self):
        identifiers = ('AAA', 'BBB', 'CCC', 'DDD', 'EEE', 'FFF')
        handler = RecordingOutputHandler()
        data_curator.main(
            configuration=_build_configuration(identifiers),
            market_data_provider=StubMarketDataProvider(),
            fundamental_data_provider=None,
            output_handlers=[handler],
            max_concurrent_fetches=4,
        )
        assert handler.identifiers == list(identifiers)

    def test_fetches_run_concurrently(self):
        handler = RecordingOutputHandler()
        data_curator.main(
            configuration=_build_configuration(('AAA', 'BBB')),
            market_data_provider=StubMarketDataProvider(barrier=threading.Barrier(2)),
            fundamental_data_provider=None,
            output_handlers=[handler],
            max_concurrent_fetches=2,
        )
        assert handler.identifiers == ['AAA', 'BBB']

    def test_sequential_mode_still_works(self):
        identifiers = ('AAA', 'BBB', 'CCC')
        handler = RecordingOutputHandler()
        data_curator.main(
            configuration=_build_configuration(identifiers),
            market_data_provider=StubMarketDataProvider(),
            fundamental_data_provider=None,
            output_handlers=[handler],
            max_concurrent_fetches=1,
        )
        assert handler.identifiers == list(identifiers)

    def test_default_concurrency_works(self):
        identifiers = ('AAA', 'BBB', 'CCC')
        handler = RecordingOutputHandler()
        data_curator.main(
            configuration=_build_configuration(identifiers),
            market_data_provider=StubMarketDataProvider(),
            fundamental_data_provider=None,
            output_handlers=[handler],
        )
        assert handler.identifiers == list(identifiers)

    def test_not_found_identifier_skipped_others_processed(self):
        identifiers = ('AAA', 'BAD', 'CCC')
        handler = RecordingOutputHandler()
        data_curator.main(
            configuration=_build_configuration(identifiers),
            market_data_provider=StubMarketDataProvider(fail_identifiers=('BAD',)),
            fundamental_data_provider=None,
            output_handlers=[handler],
            max_concurrent_fetches=2,
        )
        assert handler.identifiers == ['AAA', 'CCC']

    def test_fatal_error_aborts_processing(self):
        identifiers = ('AAA', 'BAD', 'CCC')
        handler = RecordingOutputHandler()
        # fatal errors are caught by main's outer handler and logged as critical
        data_curator.main(
            configuration=_build_configuration(identifiers),
            market_data_provider=StubMarketDataProvider(fatal_identifiers=('BAD',)),
            fundamental_data_provider=None,
            output_handlers=[handler],
            max_concurrent_fetches=2,
        )
        assert handler.identifiers == ['AAA']

    @pytest.mark.parametrize('bad_value', [0, -1, 1.5, True])
    def test_invalid_max_concurrent_fetches_rejected(self, bad_value):
        handler = RecordingOutputHandler()
        with pytest.raises(PassedArgumentError):
            data_curator.main(
                configuration=_build_configuration(('AAA',)),
                market_data_provider=StubMarketDataProvider(),
                fundamental_data_provider=None,
                output_handlers=[handler],
                max_concurrent_fetches=bad_value,
            )
