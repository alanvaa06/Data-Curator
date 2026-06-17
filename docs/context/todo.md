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

## DuckDB output handler (plan: docs/superpowers/plans/2026-06-10-duckdb-output-handler.md)
- [done] Task 1: duckdb dependency in pyproject.
- [done] Task 2: DuckdbOutput basic write path (TDD).
- [done] Task 3: upsert on (main_identifier, m_date) — restatements + incremental appends.
- [done] Task 4: dateless replace semantics + schema evolution.
- [done] Task 5: register 'duckdb' format (template entry script + config editor).
- [done] Task 6: docs, full verification (801 tests, ruff, mypy, e2e smoke), context updates.
- [pending] Follow-up: fetch-side incremental mode (auto start-date from MAX(m_date) per identifier + restatement buffer) — storage layer ready, needs orchestration change in data_curator.py.

## Macro-economic data layer (proposal: docs/superpowers/specs/2026-06-17-macro-data-layer-proposal.md)
- [pending] Phase 0 GATE (research, do before any build): confirm INPC/CPI source-of-truth + exact series IDs (Banxico-CPI was refuted; INEGI assumed); read Banxico/INEGI redistribution licensing; check point-in-time/vintage + rate limits. [RESOLVED 2026-06-17: FRED ToU — permitted for this non-commercial OSS / BYO-key tool (clauses bind end-user not the MIT tool; redistribution-scoped); flips to disqualified for any commercial/ML-training use. Verbatim ToU unfetched (bot-blocked) = residual caveat.]
- [pending] Phase 1: EconomicIndicatorRow/Data entities + EconomicIndicatorDataBlock (grouping_identifier_field=None) — TDD, test all-null + per-batch precision variance.
- [pending] Phase 2: Banxico SIE + INEGI adapters behind new MacroDataProviderInterface (verified MX gate; thin direct-HTTP over aged community SDKs).
- [pending] Phase 3: config (macro_data_provider + macro_series, format-version bump), main() global pre-loop fetch, ColumnBuilder e_* forward-fill infill.
- [pending] Phase 4: output + e_ group in column_catalog.json + panel picker + docs; full provider registration checklist (incl. repo-root workspace __main__.py); panel Save&run smoke test.
- [pending] Phase 5 (later): global layer — World Bank first (CC-BY redistributable), FRED only if TOU clears; revisit DBnomics aggregator for OECD/WB/IMF breadth after fresh verification.

## Follow-ups
- [pending] Burn down the mypy ignore_errors baseline (fmp/lseg providers, data_blocks, column_builder, helpers, data_column).
- [done] Dev environment: stale non-editable install replaced with `pip install --user -e .`; CLI now reflects `src/`. Added package `__main__.py` so `python -m kaxanuk.data_curator` works regardless of PATH.
- [pending] PATH: `%APPDATA%\Python\Python314\Scripts` is not on PATH, so the bare `kaxanuk.data_curator` command needs either that dir added to PATH manually or the `python -m kaxanuk.data_curator` form.
- [pending] Panel run output: stream logs live (currently captured at process completion); consider line-buffered reads or SSE.
- [pending] Perf, next real lever: vectorize per-row entity assembly / column packing (profiling shows ~610k isinstance + ~480k getattr calls per 12 tickers in data_blocks/entities/DataColumn; compute stage = ~0.6s of the measured 0.79s/ticker on real S&P 500 runs). Threading proven useless on GIL builds — see benchmarks/RESULTS.md addendum. Alternatives: process-pool compute, or FMP bulk endpoints for the fetch side.
