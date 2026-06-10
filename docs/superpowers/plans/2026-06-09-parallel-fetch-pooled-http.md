# Parallel Per-Ticker Fetch + Pooled HTTP Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Data Curator runs dramatically faster by fetching identifiers concurrently over pooled (keep-alive) HTTP connections, with a reproducible before/after benchmark.

**Architecture:** Two bounded changes: (1) `DataProviderInterface._request_data` switches from per-request `urllib` to a shared, lazily-initialized `httpx.Client` (one connection pool for all providers/threads, identical exception semantics); (2) `data_curator.main` replaces its sequential per-identifier loop with a `ThreadPoolExecutor` bounded-sliding-window prefetch consumed strictly in configuration order (column building + output stay sequential in the main thread). A `benchmarks/` harness (local mock FMP server with artificial latency + URL-rewrite shim) measures wall clock pre/post.

**Tech Stack:** Python 3.12+, httpx (new explicit dep), concurrent.futures (stdlib), pytest + httpx.MockTransport, stdlib http.server for the benchmark mock.

**Spec:** `docs/superpowers/specs/2026-06-09-parallel-fetch-pooled-http-design.md`

**Environment notes:**
- Repo: `C:\Users\alanv\OneDrive\Documentos\Business\Kaxanuk\Data-Curator`, branch `perf/parallel-fetch-pooled-http`.
- Installed package is NOT editable → always run tests/benchmarks with repo `src` on `PYTHONPATH` (pytest already configures `pythonpath = ["src"]`; benchmarks need `$env:PYTHONPATH='src'`).
- httpx 0.27.2 already importable (transitive via lseg-data); we still pin it explicitly.
- Existing retry quirk preserved on purpose: the loop raises on attempt `_MAX_CONNECTION_RETRIES - 1`, so a permanently failing endpoint performs **4** requests (not 5). Tests encode 4.

---

### Task 1: Benchmark harness + baseline measurement (BEFORE any code change)

**Files:**
- Create: `benchmarks/fmp_mock_server.py`
- Create: `benchmarks/run_benchmark.py`
- Create: `benchmarks/RESULTS.md`
- Modify: `pyproject.toml` (ruff per-file-ignores for `benchmarks/**`)

- [ ] **Step 1: Create the mock FMP server**

`benchmarks/fmp_mock_server.py`:

```python
"""
Local mock of the 3 FMP market-data endpoints, with configurable artificial latency.

Serves deterministic per-symbol OHLC JSON shaped exactly like FMP's
historical-price-eod endpoints, so the full Data Curator production path
(transport, retry, JSON parse, entities, column builder, output) runs unmodified.
"""
import datetime
import hashlib
import json
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse


def generate_market_rows(symbol, start_date, end_date, *, adjusted_keys):
    """Deterministic weekday OHLC rows in descending date order (like FMP)."""
    seed = int(hashlib.md5(symbol.encode()).hexdigest()[:8], 16)
    base_price = 50 + (seed % 200)
    rows = []
    current = end_date
    day_index = 0
    while current >= start_date:
        if current.weekday() < 5:
            price = base_price * (1 + 0.001 * ((seed + day_index) % 21 - 10))
            low = round(price * 0.99, 2)
            high = round(price * 1.01, 2)
            open_price = round(price * 0.995, 2)
            close_price = round(price * 1.005, 2)
            volume = 1_000_000 + (seed + day_index) % 500_000
            if adjusted_keys:
                rows.append({
                    'symbol': symbol,
                    'date': current.isoformat(),
                    'adjOpen': open_price,
                    'adjHigh': high,
                    'adjLow': low,
                    'adjClose': close_price,
                    'volume': volume,
                })
            else:
                rows.append({
                    'symbol': symbol,
                    'date': current.isoformat(),
                    'open': open_price,
                    'high': high,
                    'low': low,
                    'close': close_price,
                    'volume': volume,
                    'vwap': round(price, 2),
                })
            day_index += 1
        current -= datetime.timedelta(days=1)
    return rows


class MockFmpHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'   # keep-alive support, so pooling is measurable
    latency_seconds = 0.075         # simulated WAN round-trip

    def do_GET(self):
        time.sleep(self.latency_seconds)
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        symbol = query.get('symbol', ['UNKNOWN'])[0]
        start = datetime.date.fromisoformat(query.get('from', ['2024-01-01'])[0])
        end = datetime.date.fromisoformat(query.get('to', ['2024-12-31'])[0])
        if 'historical-price-eod/full' in parsed.path:
            rows = generate_market_rows(symbol, start, end, adjusted_keys=False)
        elif 'historical-price-eod' in parsed.path:
            rows = generate_market_rows(symbol, start, end, adjusted_keys=True)
        else:
            rows = []
        body = json.dumps(rows).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass
```

- [ ] **Step 2: Create the benchmark runner**

`benchmarks/run_benchmark.py`:

```python
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


def run_once(workers, identifiers, start_date, end_date):
    output = InMemoryOutput()
    kwargs = {}
    if 'max_concurrent_fetches' in inspect.signature(dc.main).parameters:
        kwargs['max_concurrent_fetches'] = workers
    begin = time.perf_counter()
    dc.main(
        configuration=Configuration(
            start_date=start_date,
            end_date=end_date,
            period='annual',
            identifiers=identifiers,
            columns=('m_date', 'm_open', 'm_high', 'm_low', 'm_close', 'm_volume'),
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
        run_once(args.workers, identifiers, start_date, end_date)
        for _ in range(args.reps)
    ]
    print(
        f'{args.label}: workers={args.workers} latency={args.latency * 1000:.0f}ms '
        f'tickers={args.tickers} requests={args.tickers * 3} reps={args.reps} '
        f'median={statistics.median(times):.2f}s all={[f"{t:.2f}" for t in times]}'
    )
    server.shutdown()


if __name__ == '__main__':
    main()
```

- [ ] **Step 3: Exempt benchmarks/ from strict ruff rules**

In `pyproject.toml` under `[tool.ruff.lint.per-file-ignores]` add:

```toml
"benchmarks/**" = [
    "ANN",      # benchmark scripts don't need annotations
    "D",        # nor strict docstrings
    "DTZ",      # naive dates are fine here
    "EM",       # message style not critical
    "INP001",   # not a package
    "PLR2004",  # magic values fine
    "S",        # bandit rules don't apply to a local benchmark
    "SLF001",   # intentionally patches private transport for URL rewrite
    "T20",      # prints results to stdout
    "A002",     # BaseHTTPRequestHandler.log_message signature uses `format`
]
```

- [ ] **Step 4: Smoke-test the harness (1 ticker, 1 rep, low latency)**

Run: `$env:PYTHONPATH='src'; python benchmarks/run_benchmark.py --label smoke --tickers 1 --reps 1 --latency 0.01`
Expected: `using package: ...\Data-Curator\src\...` and a `smoke: ... median=...` line. If entity/consolidation errors appear, fix mock JSON until clean.

- [ ] **Step 5: Run the baseline benchmark (pre-change code)**

Run: `$env:PYTHONPATH='src'; python benchmarks/run_benchmark.py --label baseline --tickers 12 --reps 3 --latency 0.075`
Expected: median in multiple seconds (36 sequential requests x ~75ms + overhead).

- [ ] **Step 6: Record baseline in `benchmarks/RESULTS.md`**

```markdown
# Benchmark Results: parallel fetch + pooled HTTP client

Workload: 12 tickers x 2 years daily market data (3 endpoints/ticker = 36 requests),
local mock FMP server with 75 ms artificial latency per request, in-memory output,
median of 3 runs. Machine: <fill in>. Command:
`$env:PYTHONPATH='src'; python benchmarks/run_benchmark.py --tickers 12 --reps 3 --latency 0.075`

| Scenario | Transport | Workers | Median (s) |
|----------|-----------|---------|------------|
| baseline (main) | urllib, no pooling | 1 (sequential) | <fill in> |
| pooled only | httpx pooled | 1 | <fill in after Task 4> |
| pooled + parallel | httpx pooled | 8 | <fill in after Task 4> |
```

- [ ] **Step 7: Run lint and commit**

Run: `ruff check benchmarks pyproject.toml`
Expected: clean.

```powershell
git add benchmarks pyproject.toml
git commit -m "Add reproducible FMP benchmark harness and baseline measurement"
```

---

### Task 2: Fix 2 — pooled HTTP client in `DataProviderInterface._request_data`

**Files:**
- Modify: `pyproject.toml` (add `httpx>=0.27` dependency; remove obsolete S310 per-file ignore)
- Modify: `src/kaxanuk/data_curator/data_providers/data_provider_interface.py`
- Test: `tests/unit/data_providers/request_data_test.py` (new)

- [ ] **Step 1: Write the failing tests**

`tests/unit/data_providers/request_data_test.py`:

```python
import httpx
import pytest

from kaxanuk.data_curator.data_providers import DataProviderInterface
from kaxanuk.data_curator.exceptions import (
    ApiEndpointError,
    DataProviderPaymentError,
    IdentifierNotFoundError,
)


@pytest.fixture
def _reset_http_client():
    DataProviderInterface._close_http_client()
    yield
    DataProviderInterface._close_http_client()


def _install_mock_client(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    DataProviderInterface._http_client = client
    return client


@pytest.mark.usefixtures('_reset_http_client')
class TestRequestData:
    def test_returns_response_body_on_success(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, text='[{"a": 1}]')

        _install_mock_client(handler)
        result = DataProviderInterface._request_data(
            'TEST_ENDPOINT',
            'https://example.com/endpoint',
            'AAPL',
            {'apikey': 'x', 'symbol': 'AAPL'},
        )
        assert result == '[{"a": 1}]'
        assert len(calls) == 1
        assert calls[0].url.params['symbol'] == 'AAPL'

    def test_retries_server_error_then_succeeds(self, monkeypatch):
        monkeypatch.setattr(DataProviderInterface, '_REQUEST_RETRY_TIME', 0)
        responses = [httpx.Response(500), httpx.Response(200, text='data')]

        def handler(request):
            return responses.pop(0)

        _install_mock_client(handler)
        result = DataProviderInterface._request_data(
            'TEST_ENDPOINT', 'https://example.com/endpoint', 'AAPL', {},
        )
        assert result == 'data'

    def test_exhausted_retries_raise_api_endpoint_error(self, monkeypatch):
        monkeypatch.setattr(DataProviderInterface, '_REQUEST_RETRY_TIME', 0)
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(500)

        _install_mock_client(handler)
        with pytest.raises(ApiEndpointError):
            DataProviderInterface._request_data(
                'TEST_ENDPOINT', 'https://example.com/endpoint', 'AAPL', {},
            )
        # existing behavior: raises on attempt _MAX_CONNECTION_RETRIES - 1
        assert len(calls) == DataProviderInterface._MAX_CONNECTION_RETRIES - 1

    def test_transport_errors_retried_then_raise(self, monkeypatch):
        monkeypatch.setattr(DataProviderInterface, '_REQUEST_RETRY_TIME', 0)

        def handler(request):
            raise httpx.ConnectError('connection refused', request=request)

        _install_mock_client(handler)
        with pytest.raises(ApiEndpointError):
            DataProviderInterface._request_data(
                'TEST_ENDPOINT', 'https://example.com/endpoint', 'AAPL', {},
            )

    def test_not_found_with_no_data_message_raises_identifier_not_found(self):
        def handler(request):
            return httpx.Response(404, text='No data found for this symbol')

        _install_mock_client(handler)
        with pytest.raises(IdentifierNotFoundError):
            DataProviderInterface._request_data(
                'TEST_ENDPOINT', 'https://example.com/endpoint', 'NOPE', {},
            )

    def test_not_found_without_no_data_message_raises_api_endpoint_error(self):
        def handler(request):
            return httpx.Response(404, text='gone')

        _install_mock_client(handler)
        with pytest.raises(ApiEndpointError):
            DataProviderInterface._request_data(
                'TEST_ENDPOINT', 'https://example.com/endpoint', 'NOPE', {},
            )

    def test_payment_required_raises_payment_error_with_body(self):
        def handler(request):
            return httpx.Response(402, text='please upgrade your plan')

        _install_mock_client(handler)
        with pytest.raises(DataProviderPaymentError, match='please upgrade your plan'):
            DataProviderInterface._request_data(
                'TEST_ENDPOINT', 'https://example.com/endpoint', 'AAPL', {},
            )

    def test_client_error_raises_api_endpoint_error_without_retry(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(403, text='forbidden')

        _install_mock_client(handler)
        with pytest.raises(ApiEndpointError):
            DataProviderInterface._request_data(
                'TEST_ENDPOINT', 'https://example.com/endpoint', 'AAPL', {},
            )
        assert len(calls) == 1

    def test_http_client_is_shared_across_provider_classes(self):
        from kaxanuk.data_curator.data_providers import FinancialModelingPrep

        client_a = DataProviderInterface._get_http_client()
        client_b = FinancialModelingPrep._get_http_client()
        assert client_a is client_b
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/data_providers/request_data_test.py -v`
Expected: FAIL — `AttributeError: ... has no attribute '_close_http_client'`

- [ ] **Step 3: Implement the pooled client**

In `src/kaxanuk/data_curator/data_providers/data_provider_interface.py`:

Replace imports `urllib.error` / `urllib.request` (keep `urllib.parse`) and add `threading` + `httpx`:

```python
import abc
import datetime
import http
import logging
import ssl
import threading
import time
import typing
import urllib.parse

import httpx
```

After the existing `_ssl_context` / `_MAX_CONNECTION_RETRIES` / `_REQUEST_RETRY_TIME` attributes add:

```python
    _http_client: typing.ClassVar[httpx.Client | None] = None
    _http_client_lock: typing.ClassVar[threading.Lock] = threading.Lock()
    _HTTP_TIMEOUT_SECONDS = 30.0
    _HTTP_MAX_CONNECTIONS = 32
    _HTTP_MAX_KEEPALIVE_CONNECTIONS = 16
```

Add the client lifecycle methods (note: always read/write the attribute on `DataProviderInterface` explicitly so all provider subclasses share one pool):

```python
    @classmethod
    def _get_http_client(cls) -> httpx.Client:
        """
        Return the shared pooled HTTP client, lazily initializing it.

        The client (and its connection pool) is shared by all provider classes and
        threads; httpx.Client is thread-safe.
        """
        if DataProviderInterface._http_client is None:
            with DataProviderInterface._http_client_lock:
                if DataProviderInterface._http_client is None:
                    DataProviderInterface._http_client = httpx.Client(
                        verify=cls._load_ssl_context(),
                        timeout=httpx.Timeout(cls._HTTP_TIMEOUT_SECONDS),
                        limits=httpx.Limits(
                            max_connections=cls._HTTP_MAX_CONNECTIONS,
                            max_keepalive_connections=cls._HTTP_MAX_KEEPALIVE_CONNECTIONS,
                        ),
                    )

        return DataProviderInterface._http_client

    @classmethod
    def _close_http_client(cls) -> None:
        """
        Close and discard the shared HTTP client, mainly for tests and clean shutdown.
        """
        with DataProviderInterface._http_client_lock:
            if DataProviderInterface._http_client is not None:
                DataProviderInterface._http_client.close()
                DataProviderInterface._http_client = None
```

Replace the body of `_request_data`'s while-loop (keep signature and docstring; behavior table in spec):

```python
        url = url_builder(
            endpoint_url,
            main_identifier,
            params
        )
        attempt_number = 0
        response = None
        client = cls._get_http_client()

        while attempt_number < cls._MAX_CONNECTION_RETRIES:
            attempt_number += 1
            try:
                http_response = client.get(url)
            except httpx.HTTPError as error:
                cls._raise_or_wait_before_retry(
                    endpoint_id=endpoint_id,
                    attempt_number=attempt_number,
                    error_description=str(error),
                    cause=error,
                )

                continue

            status_code = http_response.status_code
            if status_code == http.HTTPStatus.PAYMENT_REQUIRED.value:
                detailed_error_message = http_response.text
                if len(detailed_error_message) < 1:
                    detailed_error_message = f"HTTP code {status_code}"

                raise DataProviderPaymentError(detailed_error_message)
            elif (
                status_code == http.HTTPStatus.NOT_FOUND.value
                and "No data found" in http_response.text
            ):
                msg = f"API Error accessing endpoint {endpoint_id}, returned error {http_response.text}"

                raise IdentifierNotFoundError(msg)
            elif (
                http.HTTPStatus.BAD_REQUEST.value
                <= status_code
                < http.HTTPStatus.INTERNAL_SERVER_ERROR.value
            ):  # client error, so no point in retrying
                msg = " ".join([
                    f"Data provider server error accessing endpoint {endpoint_id},",
                    f"returned HTTP code {status_code}",
                    (
                        f"with message {http_response.text}"
                        if len(http_response.text) > 0
                        else ""
                    )
                ])

                raise ApiEndpointError(msg)
            elif status_code >= http.HTTPStatus.INTERNAL_SERVER_ERROR.value:
                cls._raise_or_wait_before_retry(
                    endpoint_id=endpoint_id,
                    attempt_number=attempt_number,
                    error_description=f"HTTP code {status_code}",
                    cause=None,
                )
            else:
                response = http_response.text
                if response:
                    break

        return response
```

Add the retry helper:

```python
    @classmethod
    def _raise_or_wait_before_retry(
        cls,
        *,
        endpoint_id: str,
        attempt_number: int,
        error_description: str,
        cause: Exception | None,
    ) -> None:
        """
        Raise ApiEndpointError if retries are exhausted, otherwise log and sleep before the next attempt.
        """
        if attempt_number >= (cls._MAX_CONNECTION_RETRIES - 1):  # last attempt
            msg = " ".join([
                f"Data provider server error accessing endpoint {endpoint_id}",
                (
                    f"with message {error_description}"
                    if len(error_description) > 0
                    else ""
                )
            ])

            raise ApiEndpointError(msg) from cause

        msg = f"API Server error on endpoint {endpoint_id}, retrying request attempt {attempt_number}"
        logging.getLogger(__name__).warning(msg)
        time.sleep(cls._REQUEST_RETRY_TIME)
```

- [ ] **Step 4: Add httpx dependency, drop obsolete ruff ignore**

In `pyproject.toml`:
- Add `"httpx>=0.27",` to `[project] dependencies`.
- Delete the per-file-ignores block for `"src/kaxanuk/data_curator/data_providers/data_provider_interface.py"` (the S310 urlopen audit ignore — urlopen is gone).

- [ ] **Step 5: Run new tests + existing interface tests**

Run: `python -m pytest tests/unit/data_providers -v`
Expected: ALL PASS.

- [ ] **Step 6: Run full suite + lint**

Run: `python -m pytest tests -q` then `ruff check`
Expected: all pass, lint clean.

- [ ] **Step 7: Commit**

```powershell
git add src/kaxanuk/data_curator/data_providers/data_provider_interface.py tests/unit/data_providers/request_data_test.py pyproject.toml
git commit -m "Replace per-request urllib with shared pooled httpx client"
```

- [ ] **Step 8: Dispatch reviewer subagent on this commit's diff; fix any findings, amend/commit fixes**

---

### Task 3: Fix 1 — parallel per-ticker fetch in `data_curator.main`

**Files:**
- Modify: `src/kaxanuk/data_curator/data_curator.py`
- Test: `tests/unit/data_curator_main_test.py` (new)

- [ ] **Step 1: Write the failing tests**

`tests/unit/data_curator_main_test.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/data_curator_main_test.py -v`
Expected: FAIL — `TypeError: main() got an unexpected keyword argument 'max_concurrent_fetches'`

- [ ] **Step 3: Implement the bounded prefetch pipeline**

In `src/kaxanuk/data_curator/data_curator.py`:

Add imports:

```python
import collections
import concurrent.futures
```

and `MarketData` to the entities import list.

Add the parameter to `main` (after `custom_calculation_modules`):

```python
    max_concurrent_fetches: int = 8,
```

with docstring entry:

```
    max_concurrent_fetches
        Maximum number of identifiers whose data is downloaded concurrently.
        1 reproduces fully sequential fetching.
```

Add validation alongside the other argument checks:

```python
    if (
        not isinstance(max_concurrent_fetches, int)
        or isinstance(max_concurrent_fetches, bool)
        or max_concurrent_fetches < 1
    ):
        msg = "max_concurrent_fetches passed to main must be an integer of 1 or more"

        raise PassedArgumentError(msg)
```

Add a module-level fetch worker (above `main` or below it, near the other helpers):

```python
def _fetch_identifier_data(
    main_identifier: str,
    configuration: Configuration,
    market_data_provider: DataProviderInterface,
    fundamental_data_provider: DataProviderInterface | None,
) -> tuple[MarketData, FundamentalData, DividendData, SplitData]:
    """
    Download all the data for a single identifier; runs inside a fetch worker thread.

    Parameters
    ----------
    main_identifier
        The identifier whose data to download
    configuration
        The assembled Configuration entity
    market_data_provider
        The market data provider object instance
    fundamental_data_provider
        The fundamental data provider object instance, or None

    Returns
    -------
    Tuple of the full market, fundamental, dividend and split data entities
    """
    logging.getLogger(__name__).info(
        "Loading data for: %s",
        main_identifier
    )
    full_market_data = market_data_provider.get_market_data(
        main_identifier=main_identifier,
        start_date=configuration.start_date,
        end_date=configuration.end_date,
    )
    if fundamental_data_provider is not None:
        full_fundamental_data = fundamental_data_provider.get_fundamental_data(
            main_identifier=main_identifier,
            period=configuration.period,
            start_date=configuration.start_date,
            end_date=configuration.end_date,
        )
        full_dividend_data = fundamental_data_provider.get_dividend_data(
            main_identifier=main_identifier,
            start_date=configuration.start_date,
            end_date=configuration.end_date,
        )
        full_split_data = fundamental_data_provider.get_split_data(
            main_identifier=main_identifier,
            start_date=configuration.start_date,
            end_date=configuration.end_date,
        )
    else:
        full_fundamental_data = FundamentalData(
            main_identifier=MainIdentifier(main_identifier),
            rows={}
        )
        full_dividend_data = DividendData(
            main_identifier=MainIdentifier(main_identifier),
            rows={}
        )
        full_split_data = SplitData(
            main_identifier=MainIdentifier(main_identifier),
            rows={}
        )

    return (
        full_market_data,
        full_fundamental_data,
        full_dividend_data,
        full_split_data,
    )
```

Replace the `for main_identifier in configuration.identifiers:` loop inside the outer `try` with the bounded sliding-window pipeline (the four per-identifier `except` blocks keep their exact current bodies):

```python
        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_concurrent_fetches,
            thread_name_prefix='data_curator_fetch',
        )
        try:
            identifiers = configuration.identifiers
            max_pending_fetches = max_concurrent_fetches * 2
            pending_fetches: collections.deque[
                tuple[str, concurrent.futures.Future]
            ] = collections.deque()
            next_identifier_index = 0

            while pending_fetches or next_identifier_index < len(identifiers):
                # keep up to max_pending_fetches downloads in flight, ahead of consumption
                while (
                    next_identifier_index < len(identifiers)
                    and len(pending_fetches) < max_pending_fetches
                ):
                    submitted_identifier = identifiers[next_identifier_index]
                    pending_fetches.append((
                        submitted_identifier,
                        executor.submit(
                            _fetch_identifier_data,
                            submitted_identifier,
                            configuration,
                            market_data_provider,
                            fundamental_data_provider,
                        )
                    ))
                    next_identifier_index += 1

                # consume strictly in configuration order so output is deterministic
                (main_identifier, fetch_future) = pending_fetches.popleft()
                try:
                    (
                        full_market_data,
                        full_fundamental_data,
                        full_dividend_data,
                        full_split_data,
                    ) = fetch_future.result()
                except IdentifierNotFoundError as error:
                    ...unchanged current body...
                    continue
                except EntityProcessingError as error:
                    ...unchanged current body...
                    continue
                except DataProviderPaymentError as error:
                    ...unchanged current body...
                    continue
                except DataBlockRowEntityErrorGroup as error_group:
                    ...unchanged current body...
                    continue

                column_builder = ColumnBuilder(
                    calculation_modules=calculation_modules,
                    configuration=configuration,
                    dividend_data=full_dividend_data,
                    fundamental_data=full_fundamental_data,
                    market_data=full_market_data,
                    split_data=full_split_data,
                )
                output_columns = column_builder.process_columns(configuration.columns)

                for output_handler in output_handlers:
                    output_handler.output_data(
                        main_identifier=main_identifier,
                        columns=output_columns
                    )

                logging.getLogger(__name__).info(
                    "Output processed for: %s",
                    main_identifier
                )
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
```

(`...unchanged current body...` = copy the existing `except` bodies verbatim from the current loop — they log and `continue`.)

- [ ] **Step 4: Run new tests**

Run: `python -m pytest tests/unit/data_curator_main_test.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Run full suite + lint**

Run: `python -m pytest tests -q` then `ruff check`
Expected: all pass, lint clean.

- [ ] **Step 6: Commit**

```powershell
git add src/kaxanuk/data_curator/data_curator.py tests/unit/data_curator_main_test.py
git commit -m "Parallelize per-identifier data fetching with bounded prefetch pipeline"
```

- [ ] **Step 7: Dispatch reviewer subagent on this commit's diff; fix any findings, commit fixes**

---

### Task 4: Post-change benchmarks

**Files:**
- Modify: `benchmarks/RESULTS.md`

- [ ] **Step 1: Run pooled-only benchmark (isolates Fix 2)**

Run: `$env:PYTHONPATH='src'; python benchmarks/run_benchmark.py --label pooled-sequential --workers 1 --tickers 12 --reps 3 --latency 0.075`

- [ ] **Step 2: Run pooled + parallel benchmark (Fix 1 + Fix 2)**

Run: `$env:PYTHONPATH='src'; python benchmarks/run_benchmark.py --label pooled-parallel --workers 8 --tickers 12 --reps 3 --latency 0.075`
Expected: median several times lower than baseline.

- [ ] **Step 3: Fill in `benchmarks/RESULTS.md` table + speedup factors; commit**

```powershell
git add benchmarks/RESULTS.md
git commit -m "Record post-change benchmark results"
```

---

### Task 5: Final verification, changelog, context docs

- [ ] **Step 1: Full suite + lint one more time** (`python -m pytest tests -q; ruff check`)
- [ ] **Step 2: Add CHANGELOG.md entry** (follow the file's existing format; mention pooled httpx client, parallel fetch with `max_concurrent_fetches`, new explicit httpx dependency, new 30 s request timeout)
- [ ] **Step 3: Final reviewer subagent over the whole branch diff vs main; fix findings**
- [ ] **Step 4: Update Kaxanuk context docs** (`docs/context/results.md`, `sesion-log.md`, `memory.md` decision line)
- [ ] **Step 5: Commit remaining changes; report benchmark table + branch status to user**

---

## Self-Review Notes

- Spec coverage: Fix 2 (Task 2), Fix 1 (Task 3), benchmark before/after (Tasks 1+4), tests (Tasks 2+3), reviewer-per-task (Tasks 2/3/5). ✓
- Retry-count quirk encoded in tests (4 attempts) to preserve current behavior. ✓
- Types consistent: `_fetch_identifier_data` returns the 4-tuple consumed via `fetch_future.result()`. ✓
- `FinancialModelingPrep(api_key='benchmark-key')` constructor signature must be verified at execution time (Task 1 smoke test will catch it).
