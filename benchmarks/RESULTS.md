# Benchmark Results: parallel fetch + pooled HTTP client

Workload: 12 tickers x 2 years daily market data (3 endpoints/ticker = 36 requests),
local mock FMP server with 75 ms artificial latency per request, in-memory output,
median of 3 runs. Machine: Windows 11, Python 3.14.2. Command:
`$env:PYTHONPATH='src'; python benchmarks/run_benchmark.py --tickers 12 --reps 3 --latency 0.075 --workers N`

| Scenario | Transport | Workers | Median (s) | Speedup vs baseline |
|----------|-----------|---------|------------|---------------------|
| baseline (pre-change) | urllib, no pooling | 1 (sequential) | 3.81 | 1.0x |
| pooled only | httpx pooled | 1 | 3.63 | 1.05x |
| pooled + parallel (default) | httpx pooled | 8 | 0.92 | **4.1x** |
| pooled + parallel | httpx pooled | 12 | 0.85 | **4.5x** |

Raw runs:
- baseline: 3.69 / 4.05 / 3.81 s
- pooled-sequential: 3.48 / 3.66 / 3.63 s
- pooled-parallel (8): 0.92 / 0.91 / 0.95 s
- pooled-parallel (12): 0.94 / 0.72 / 0.85 s

Interpretation:
- Parallelism dominates the gain: fetch wall-clock shrinks roughly by the worker
  count until column computation (still sequential by design, for deterministic
  output) becomes the bottleneck — classic Amdahl behavior. With more tickers the
  speedup grows toward the worker count.
- The pooled-only gain (~5%) is understated here: the mock server is plain local
  HTTP, so there are no TLS handshakes to eliminate. Against the real FMP HTTPS API
  every request previously paid a fresh TCP+TLS handshake; connection reuse there is
  worth far more, and it also reduces handshake-related transient failures.
- Real-world WAN latency is typically higher than the simulated 75 ms, which
  increases the absolute time saved proportionally.

## Addendum (2026-06-10): compute-stage threading experiment

Tested `max_concurrent_computations` (threaded per-identifier column calculation +
output) after observing that the sequential compute stage, not fetching, bounds
wall-clock once the prefetch pipeline is warm (24 tickers, 8 fetch workers: ~2.3s
total of which ~1.1s is compute at zero latency).

| Columns | compute=1 | compute=4 | Verdict |
|---------|-----------|-----------|---------|
| 6 market columns | 2.62 s | 2.68 s | no gain |
| +18 heavy calculations (volatility/SMA/EMA/MACD/RSI/CMF) | 3.24 s | 3.27 s | no gain |

Interpretation: the compute stage is GIL-bound. Profiling (12 tickers, zero
latency) shows the time goes to per-row entity assembly — ~610k `isinstance` and
~480k `getattr` calls in `data_blocks`/`entities`/`DataColumn` — pure-Python call
overhead that threads cannot parallelize on a standard (GIL) CPython build.
`max_concurrent_computations` is kept (default 1 = unchanged behavior): it becomes
useful on free-threaded CPython builds and harms nothing otherwise.

Real-run reference: a production S&P 500 run (499 tickers, full FMP data, 201
columns) measured from output file timestamps took 392 s ≈ 0.79 s/ticker, of which
fetch accounts for roughly 0.15 s/ticker at 8 workers — confirming compute as the
dominant cost in production.

Next real lever (out of scope here): vectorize entity assembly / column packing to
eliminate the per-row Python call storms, or process-based compute parallelism.

## Addendum 2 (2026-06-10): process-pool compute

`max_concurrent_computations` reimplemented on `ProcessPoolExecutor`: workers
calculate one identifier's columns and return the pyarrow table; output handlers
always run in the parent in configuration order, so output behavior is unchanged.
Custom calculation modules are re-imported by name in each worker (verified with
the template's `c_test`).

Mock benchmark (heavy calculation columns, 8 fetch workers, 75 ms latency):

| Tickers | compute=1 | compute=4 (processes) | Net |
|---------|-----------|------------------------|-----|
| 48 | 6.55 s | 5.42 s | -17% |
| 96 | 12.47 s | 11.47 s | -8% |

Real FMP run (24 tickers, full 201-column set, warm network, back to back):

| Mode | Wall time |
|------|-----------|
| compute=1 | 5.8 s |
| compute=4 | 4.6 s (**-21%**, including ~2 s one-time pool spawn) |

The fixed ~2 s Windows process-spawn cost dominates small runs and amortizes on
large ones; the parallelizable compute share grows with column count. The JSON
entry-script template now defaults to `max_concurrent_computations=4`.

Caveat (root-caused during validation): on Windows the worker processes re-import
the parent's `__main__`, so entry scripts MUST guard their executable code with
`if __name__ == '__main__':` — otherwise the pool dies with `BrokenProcessPool`.
The JSON entry-script template ships guarded.
