# Benchmark Results: parallel fetch + pooled HTTP client

Workload: 12 tickers x 2 years daily market data (3 endpoints/ticker = 36 requests),
local mock FMP server with 75 ms artificial latency per request, in-memory output,
median of 3 runs. Machine: Windows 11, Python 3.14.2. Command:
`$env:PYTHONPATH='src'; python benchmarks/run_benchmark.py --tickers 12 --reps 3 --latency 0.075`

| Scenario | Transport | Workers | Median (s) | Speedup vs baseline |
|----------|-----------|---------|------------|---------------------|
| baseline (pre-change) | urllib, no pooling | 1 (sequential) | 3.81 | 1.0x |
| pooled only | httpx pooled | 1 | _pending Task 4_ | |
| pooled + parallel | httpx pooled | 8 | _pending Task 4_ | |

Raw baseline runs: 3.69 / 4.05 / 3.81 s.

Note: localhost HTTP understates pooling gains (no TLS handshake savings vs the real
HTTPS API); parallelism gains are representative of real-world behavior.
