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
