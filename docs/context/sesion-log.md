# Session Log

One line per session. Newest last.

- 2026-06-09: replaced Excel config with JSON + local HTML editor (`config-editor` CLI) on branch `feat/html-config-editor`; brainstorm → spec → TDD plan → 11 tasks executed sequentially; 708 tests pass.
- 2026-06-09 (later): simplified UX to one `start` command (auto-scaffold + panel + in-panel Save & run); TDD, 718 tests pass, e2e smoke verified.
- 2026-06-09 (later): fixed env (stale install + PATH) with editable install + package `__main__.py`; fixed panel dark-mode contrast and column list layout (light-dark() palette, sorted groups, all/none toggles); verified via live DOM/computed-style inspection.
- 2026-06-09 (later): panel UX round 2 — collapsible column groups, one-click index presets (S&P 500: 503 / Nasdaq 100: 101 / Russell 2000: 1935, bundled from Wikipedia + Vanguard VTWO), viewport-locked no-scroll layout; verified end-to-end in user's Chrome.
- 2026-06-09 (later): run-failure root cause — stale Excel `__main__.py` in repo root + empty API keys; replaced entry script with JSON version, added panel API-keys section writing Config/.env (values never echoed), missing-key now clean ConfigurationError + exit 1. Yahoo extension blocked on Python 3.14 (<3.14 required) — FMP key is the path to live data.
- 2026-06-10: perf diagnosis — download slowness was the unmerged `perf/parallel-fetch-pooled-http` branch (serial urllib on our branch); merged it (one CHANGELOG conflict), 766 tests green, re-benchmarked locally: 3.37s→0.88s (3.8x) at default 8 workers; panel runs get it automatically via main()'s max_concurrent_fetches=8 default.
