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
    DataProviderPaymentError,
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
    def __init__(
        self,
        *,
        fail_identifiers=(),
        fatal_identifiers=(),
        payment_fail_identifiers=(),
        barrier=None,
        fetch_started_hook=None,
    ):
        self.fail_identifiers = set(fail_identifiers)
        self.fatal_identifiers = set(fatal_identifiers)
        self.payment_fail_identifiers = set(payment_fail_identifiers)
        self.barrier = barrier
        self.fetch_started_hook = fetch_started_hook

    def get_market_data(self, *, main_identifier, start_date, end_date):
        if self.fetch_started_hook is not None:
            self.fetch_started_hook(main_identifier)
        if self.barrier is not None:
            # only passes if at least 2 fetches run concurrently
            self.barrier.wait(timeout=10)
        if main_identifier in self.fail_identifiers:
            msg = f"{main_identifier} not found"
            raise IdentifierNotFoundError(msg)
        if main_identifier in self.fatal_identifiers:
            msg = f"{main_identifier} endpoint exploded"
            raise ApiEndpointError(msg)
        if main_identifier in self.payment_fail_identifiers:
            msg = f"{main_identifier} requires payment"
            raise DataProviderPaymentError(msg)
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
        self._lock = threading.Lock()

    def output_data(self, *, main_identifier, columns):
        with self._lock:
            self.identifiers.append(main_identifier)
        return True


class TestMainParallelCompute:
    def test_all_identifiers_processed_in_order_with_parallel_compute(self):
        identifiers = ('AAA', 'BBB', 'CCC', 'DDD', 'EEE', 'FFF', 'GGG', 'HHH')
        handler = RecordingOutputHandler()
        data_curator.main(
            configuration=_build_configuration(identifiers),
            market_data_provider=StubMarketDataProvider(),
            fundamental_data_provider=None,
            output_handlers=[handler],
            max_concurrent_fetches=4,
            max_concurrent_computations=2,
        )
        # output handlers run in the parent process, drained in submission order
        assert handler.identifiers == list(identifiers)

    def test_default_keeps_sequential_deterministic_order(self):
        identifiers = ('AAA', 'BBB', 'CCC', 'DDD')
        handler = RecordingOutputHandler()
        data_curator.main(
            configuration=_build_configuration(identifiers),
            market_data_provider=StubMarketDataProvider(),
            fundamental_data_provider=None,
            output_handlers=[handler],
            max_concurrent_fetches=4,
        )
        assert handler.identifiers == list(identifiers)

    def test_invalid_max_concurrent_computations_rejected(self):
        for bad in (0, -1, True, 'x', None):
            with pytest.raises(PassedArgumentError):
                data_curator.main(
                    configuration=_build_configuration(('AAA',)),
                    market_data_provider=StubMarketDataProvider(),
                    fundamental_data_provider=None,
                    output_handlers=[RecordingOutputHandler()],
                    max_concurrent_computations=bad,
                )

    def test_failed_identifier_skipped_with_parallel_compute(self):
        identifiers = ('AAA', 'BAD', 'CCC', 'DDD')
        handler = RecordingOutputHandler()
        data_curator.main(
            configuration=_build_configuration(identifiers),
            market_data_provider=StubMarketDataProvider(fail_identifiers=('BAD',)),
            fundamental_data_provider=None,
            output_handlers=[handler],
            max_concurrent_fetches=2,
            max_concurrent_computations=2,
        )
        assert handler.identifiers == ['AAA', 'CCC', 'DDD']


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

    def test_output_order_preserved_when_first_identifier_finishes_last(self):
        identifiers = ('AAA', 'BBB', 'CCC', 'DDD', 'EEE', 'FFF')
        release_first = threading.Event()

        def fetch_started_hook(main_identifier):
            if main_identifier == 'AAA':
                # block the first identifier until the last one has started fetching
                released = release_first.wait(timeout=10)
                if not released:
                    msg = 'AAA was never released, fetches are not concurrent'
                    raise RuntimeError(msg)
            elif main_identifier == 'FFF':
                release_first.set()

        handler = RecordingOutputHandler()
        data_curator.main(
            configuration=_build_configuration(identifiers),
            market_data_provider=StubMarketDataProvider(fetch_started_hook=fetch_started_hook),
            fundamental_data_provider=None,
            output_handlers=[handler],
            max_concurrent_fetches=6,
        )
        assert handler.identifiers == list(identifiers)

    def test_window_refills_and_prefetch_is_bounded(self):
        identifiers = tuple(f'TK{i}' for i in range(10))
        handler = RecordingOutputHandler()
        outputs_seen_when_window_refilled = []

        def fetch_started_hook(main_identifier):
            if main_identifier == 'TK4':
                # workers=2 gives a window of 4, so the 5th identifier can only be
                # submitted after the first consumed identifier produced output
                outputs_seen_when_window_refilled.append(list(handler.identifiers))

        data_curator.main(
            configuration=_build_configuration(identifiers),
            market_data_provider=StubMarketDataProvider(fetch_started_hook=fetch_started_hook),
            fundamental_data_provider=None,
            output_handlers=[handler],
            max_concurrent_fetches=2,
        )
        assert handler.identifiers == list(identifiers)
        # the 5th identifier's fetch must start only after at least the first
        # identifier was consumed and output (bounded prefetch, refilled window)
        assert len(outputs_seen_when_window_refilled) == 1
        assert len(outputs_seen_when_window_refilled[0]) >= 1
        assert outputs_seen_when_window_refilled[0][0] == 'TK0'

    def test_payment_error_identifier_skipped_others_processed(self):
        identifiers = ('AAA', 'BAD', 'CCC')
        handler = RecordingOutputHandler()
        data_curator.main(
            configuration=_build_configuration(identifiers),
            market_data_provider=StubMarketDataProvider(payment_fail_identifiers=('BAD',)),
            fundamental_data_provider=None,
            output_handlers=[handler],
            max_concurrent_fetches=2,
        )
        assert handler.identifiers == ['AAA', 'CCC']

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
