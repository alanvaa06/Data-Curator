# Todo

Status: pending | in_progress | done

- [done] Replace Excel config with a lightweight HTML parameter editor (JSON + `config-editor` CLI). Branch `feat/html-config-editor`.
- [done] Seamless UX: single `start` command with in-panel "Save & run" (no separate init/editor/run commands needed).

- [done] Repo migration: private standalone github.com/alanvaa06/Data-Curator; branches merged to main.
- [done] Strip Excel config entirely (configurator, CLI paths, templates, panel import, openpyxl, docs).
- [done] Configurators raise instead of sys.exit; entry template maps DataCuratorError to exit 1.
- [done] mypy blocking in CI (legacy modules baselined in pyproject overrides — ratchet down).
- [done] Output-handler unit tests; removed empty column_builder/instance_test.py.
- [done] URLs/badges → alanvaa06/Data-Curator; RTD/PyPI badges dropped.

## Follow-ups
- [pending] Burn down the mypy ignore_errors baseline (fmp/lseg providers, data_blocks, column_builder, helpers, data_column).
- [done] Dev environment: stale non-editable install replaced with `pip install --user -e .`; CLI now reflects `src/`. Added package `__main__.py` so `python -m kaxanuk.data_curator` works regardless of PATH.
- [pending] PATH: `%APPDATA%\Python\Python314\Scripts` is not on PATH, so the bare `kaxanuk.data_curator` command needs either that dir added to PATH manually or the `python -m kaxanuk.data_curator` form.
- [pending] Panel run output: stream logs live (currently captured at process completion); consider line-buffered reads or SSE.
- [pending] Perf, next real lever: vectorize per-row entity assembly / column packing (profiling shows ~610k isinstance + ~480k getattr calls per 12 tickers in data_blocks/entities/DataColumn; compute stage = ~0.6s of the measured 0.79s/ticker on real S&P 500 runs). Threading proven useless on GIL builds — see benchmarks/RESULTS.md addendum. Alternatives: process-pool compute, or FMP bulk endpoints for the fetch side.
