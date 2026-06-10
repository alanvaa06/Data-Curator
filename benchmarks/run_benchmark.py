"""
End-to-end Data Curator benchmark against the local mock FMP server.

Usage (from repo root):
    $env:PYTHONPATH='src'; python benchmarks/run_benchmark.py --label baseline
    $env:PYTHONPATH='src'; python benchmarks/run_benchmark.py --label parallel --workers 8

The URL-rewrite shim redirects FMP endpoint hosts to the local server while the
full production transport/retry/parse/entity/column/output path runs unmodified.
Works identically pre- and post-change (forwards max_concurrent_fetches only if
data_curator.main supports it).
"""
import argparse
import datetime
import inspect
import logging
import statistics
import threading
import time
from http.server import ThreadingHTTPServer

from fmp_mock_server import MockFmpHandler

import kaxanuk.data_curator as dc
from kaxanuk.data_curator.data_providers import FinancialModelingPrep
from kaxanuk.data_curator.data_providers.data_provider_interface import DataProviderInterface
from kaxanuk.data_curator.entities import Configuration
from kaxanuk.data_curator.output_handlers import InMemoryOutput


def install_url_rewrite(base_url):
    original = DataProviderInterface._request_data.__func__

    def rewriting_request_data(cls, endpoint_id, endpoint_url, main_identifier, params, *args, **kwargs):
        rewritten = str(endpoint_url).replace('https://financialmodelingprep.com', base_url)
        return original(cls, endpoint_id, rewritten, main_identifier, params, *args, **kwargs)

    DataProviderInterface._request_data = classmethod(rewriting_request_data)


def run_once(workers, identifiers, start_date, end_date, compute_workers=1):
    output = InMemoryOutput()
    kwargs = {}
    main_params = inspect.signature(dc.main).parameters
    if 'max_concurrent_fetches' in main_params:
        kwargs['max_concurrent_fetches'] = workers
    if 'max_concurrent_computations' in main_params:
        kwargs['max_concurrent_computations'] = compute_workers
    begin = time.perf_counter()
    dc.main(
        configuration=Configuration(
            start_date=start_date,
            end_date=end_date,
            period='annual',
            identifiers=identifiers,
            columns=(
                'm_date', 'm_open', 'm_high', 'm_low', 'm_close', 'm_volume', 'm_vwap',
                'c_annualized_volatility_5d_log_returns_dividend_and_split_adjusted',
                'c_annualized_volatility_21d_log_returns_dividend_and_split_adjusted',
                'c_annualized_volatility_63d_log_returns_dividend_and_split_adjusted',
                'c_annualized_volatility_252d_log_returns_dividend_and_split_adjusted',
                'c_simple_moving_average_5d_close_split_adjusted',
                'c_simple_moving_average_21d_close_split_adjusted',
                'c_simple_moving_average_63d_close_split_adjusted',
                'c_simple_moving_average_252d_close_split_adjusted',
                'c_exponential_moving_average_21d_close_split_adjusted',
                'c_exponential_moving_average_63d_close_split_adjusted',
                'c_macd_26d_12d_split_adjusted',
                'c_macd_signal_9d_split_adjusted',
                'c_rsi_14d_split_adjusted',
                'c_log_returns_dividend_and_split_adjusted',
                'c_log_difference_high_to_low',
                'c_daily_traded_value',
                'c_daily_traded_value_sma_21d',
                'c_chaikin_money_flow_21d_split_adjusted',
            ),
        ),
        market_data_provider=FinancialModelingPrep(api_key='benchmark-key'),
        fundamental_data_provider=None,
        output_handlers=[output],
        logger_level=logging.ERROR,
        **kwargs,
    )
    elapsed = time.perf_counter() - begin
    if len(output.data) != len(identifiers):
        msg = f'only {len(output.data)}/{len(identifiers)} identifiers produced output'
        raise RuntimeError(msg)
    return elapsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--compute-workers', type=int, default=1)
    parser.add_argument('--tickers', type=int, default=12)
    parser.add_argument('--latency', type=float, default=0.075)
    parser.add_argument('--reps', type=int, default=3)
    parser.add_argument('--label', type=str, default='run')
    args = parser.parse_args()

    print('using package:', dc.__file__)
    MockFmpHandler.latency_seconds = args.latency
    server = ThreadingHTTPServer(('127.0.0.1', 0), MockFmpHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    install_url_rewrite(f'http://127.0.0.1:{port}')

    identifiers = tuple(f'TK{i:02d}' for i in range(args.tickers))
    start_date = datetime.date(2024, 1, 2)
    end_date = datetime.date(2025, 12, 31)

    times = [
        run_once(args.workers, identifiers, start_date, end_date, compute_workers=args.compute_workers)
        for _ in range(args.reps)
    ]
    print(
        f'{args.label}: workers={args.workers} compute={args.compute_workers} '
        f'latency={args.latency * 1000:.0f}ms '
        f'tickers={args.tickers} requests={args.tickers * 3} reps={args.reps} '
        f'median={statistics.median(times):.2f}s all={[f"{t:.2f}" for t in times]}'
    )
    server.shutdown()


if __name__ == '__main__':
    main()
