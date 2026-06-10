# Design: Parallel Per-Ticker Fetch + Pooled HTTP Client

**Date:** 2026-06-09
**Author:** AI Strategy & Orchestration Agent (for Alan Vazquez, AI Lead)
**Status:** Approved scope (user directive: "execute parallelized fix 1 and 2"); design decisions made autonomously per goal mode.

## Problem

The Data Curator pipeline is fully sequential. For N identifiers it issues up to 8 HTTPS
requests per identifier (3 market, 3 fundamental statements, 1 dividend, 1 split), one
after another, on `urllib.request.urlopen` with a fresh TCP+TLS connection per request
(`data_provider_interface.py:396`). The per-identifier loop in `data_curator.main`
(`data_curator.py:136`) only starts identifier k+1 after identifier k finished fetching,
computing, and writing. Wall clock is dominated by network latency while the CPU idles.

## Goals

1. **Fix 2 — pooled HTTP client:** persistent connections (keep-alive) reused across all
   requests, eliminating per-request TCP/TLS handshakes.
2. **Fix 1 — parallel per-ticker fetch:** fetch multiple identifiers' data concurrently,
   while keeping column computation and output handling sequential and deterministic.
3. Demonstrate the improvement with a reproducible before/after benchmark.

## Non-Goals

- Async rewrite of the provider interface (future work; this design is async-compatible).
- Caching (separate initiative).
- Parallelizing column computation or output handlers.
- Changing the LSEG provider (it already bulk-prefetches in `initialize()` via its own SDK).

## Design

### Fix 2: Pooled HTTP client (`data_provider_interface.py`)

Replace the urllib transport inside `DataProviderInterface._request_data` with a shared
`httpx.Client`:

- **Library:** `httpx>=0.27`, added as an explicit dependency in `pyproject.toml`.
  Rationale: thread-safe sync client with connection pooling now, drop-in `AsyncClient`
  path later (the codebase already has `@todo` markers pointing at async http); it is
  already present in the dependency tree via `lseg-data`.
- **Lifecycle:** lazy-initialized class attribute `_http_client` on
  `DataProviderInterface`, guarded by a `threading.Lock` (double-checked init). All
  providers and threads share one client → one connection pool.
- **Pool/timeout config:** `max_connections=32`, `max_keepalive_connections=16`,
  explicit 30 s timeout (urllib previously had no timeout — hung connections blocked
  forever; the retry loop makes a bounded timeout the correct behavior).
- **TLS:** reuse the existing `_load_ssl_context()` context via `verify=`.
- **Error mapping** (preserves existing exception semantics exactly):
  - HTTP 404 with "No data found" in body → `IdentifierNotFoundError`
  - HTTP 402 → `DataProviderPaymentError` (detailed body message preserved)
  - other 4xx → `ApiEndpointError` (no retry, same as today)
  - 5xx → retry up to `_MAX_CONNECTION_RETRIES` with `_REQUEST_RETRY_TIME` sleep,
    then `ApiEndpointError`
  - transport errors (`httpx.TransportError`) → retried like 5xx, then `ApiEndpointError`
  - Note: urllib raises on non-2xx; httpx does not — status handling becomes explicit
    `response.status_code` checks, which simplifies the retry loop.
- **Testability:** `_http_client` can be injected (e.g., `httpx.MockTransport`) by tests;
  a `_close_http_client()` classmethod resets state between tests.

### Fix 1: Parallel per-ticker fetch (`data_curator.py`)

Restructure `main`'s identifier loop into a **bounded prefetch pipeline**:

- New keyword-only parameter `max_concurrent_fetches: int = 8` on `main()`.
  Validated `>= 1`; `1` reproduces today's sequential fetching. Default 8 balances
  speedup against provider rate limits.
- A `ThreadPoolExecutor(max_workers=max_concurrent_fetches)` runs a `_fetch_identifier_data`
  worker per identifier. Each worker performs that identifier's market + fundamental +
  dividend + split calls sequentially within the thread (cross-ticker parallelism, not
  intra-ticker).
- **Bounded sliding window:** futures are submitted ahead of consumption up to
  `max_concurrent_fetches * 2` outstanding, and consumed strictly in configuration
  order. This bounds memory (no unbounded accumulation of fetched entity graphs) and
  keeps output deterministic and identical in order to today's behavior.
- **Error semantics preserved:**
  - Per-identifier skippable errors (`IdentifierNotFoundError`, `EntityProcessingError`,
    `DataProviderPaymentError`, `DataBlockRowEntityErrorGroup`) propagate through
    `future.result()` and are caught at the consumption site with the exact same
    log-and-continue handling as today.
  - Fatal errors (`ApiEndpointError`, `ColumnBuilder*`) propagate to the existing outer
    handler and abort the run; the executor is shut down with `cancel_futures=True`.
- Column building and output handling stay in the main thread, sequential, in order.

**Thread-safety audit:** `FinancialModelingPrep` get-methods are stateless except
`self.api_key` (read-only) and the class-level `_is_paid_account_plan` flag. Concurrent
first-hit on the 402-fallback path can at worst duplicate one free-limit probe request and
redundantly write the same flag value — benign. `httpx.Client` is documented thread-safe.
Output handlers are never called concurrently (main thread only).

### Benchmark harness (`benchmarks/`, not shipped in the wheel)

- `fmp_mock_server.py`: stdlib `ThreadingHTTPServer` on localhost serving the 3 FMP
  market-data endpoints with deterministic per-symbol OHLC JSON (~2 years daily) and a
  configurable artificial latency per request (default 75 ms) to simulate WAN RTT.
- `run_benchmark.py`: wraps `DataProviderInterface._request_data` with a URL-rewriting
  shim (`https://financialmodelingprep.com` → `http://127.0.0.1:<port>`) so the full
  production transport/retry/parse/entity/column/output path runs unmodified. Workload:
  12 tickers × 2 years daily market data, `fundamental_data_provider=None`, in-memory
  output. Reports median of 3 runs. Run with `PYTHONPATH=src` (installed package is
  non-editable).
- Same harness runs against pre-change and post-change code; additionally a post-change
  run with `max_concurrent_fetches=1` isolates the pooling-only gain.
- Honest caveat: localhost HTTP understates pooling gains (no TLS handshake savings);
  parallelism gains are representative.

## Testing

TDD per change:

- **Fix 2 unit tests** (`tests/unit/data_providers/`): success path, 5xx-retry-then-success,
  404-no-data → `IdentifierNotFoundError`, 402 → `DataProviderPaymentError`, other 4xx →
  `ApiEndpointError`, retries-exhausted → `ApiEndpointError`, and client reuse (same pool
  across calls) — all via injected `httpx.MockTransport`.
- **Fix 1 unit tests** (`tests/unit/`): with stub providers/output handlers — output order
  matches configuration order under concurrency; skippable error on one identifier doesn't
  affect others; fatal error aborts; `max_concurrent_fetches=1` sequential equivalence;
  invalid value rejected.
- Full existing suite + ruff must pass.

## Risks

- **Provider rate limits:** higher request burst. Mitigated by bounded default (8) and a
  user-controllable knob down to 1.
- **Behavior change:** explicit 30 s timeout where none existed (improvement; documented).
- **New dependency:** httpx (already transitively present; pinned explicitly).
