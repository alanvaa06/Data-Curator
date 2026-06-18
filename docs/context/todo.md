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
- [done] Phase 0 GATE (research): FRED ToU resolved 2026-06-17 — permitted for this non-commercial OSS / BYO-key tool (clauses bind end-user not the MIT tool; redistribution-scoped); flips to disqualified for any commercial/ML-training use. Verbatim ToU unfetched (bot-blocked) = residual caveat. INPC/headline-CPI source confirmed = INEGI (e_mx_inpc, series 216064).
- [done] Phase 1: EconomicIndicatorRow/Data entities + EconomicIndicatorDataBlock (grouping_identifier_field=None) — TDD.
- [done] Phase 2: Banxico SIE + INEGI adapters behind new MacroDataProviderInterface (verified MX gate; thin direct-HTTP). Capstone declared macro_provider_name ClassVar on the interface to close the mypy contract gap.
- [done] Phase 3: config routing, main() global pre-loop fetch, ColumnBuilder case 'e' forward-fill infill.
- [done] Phase 4: output + e_ group in column_catalog.json (17 e_* columns) + panel picker; README/CHANGELOG/docs-source docs. Registration checklist incl. repo-root workspace __main__.py done.
- [done] Phase 5: global layer shipped in this iteration — FRED (US, BYO-key, non-commercial) + DBnomics (keyless RoW: Euro-area HICP, ECB rate) adapters behind the same interface. World Bank direct not added (DBnomics covers RoW; revisit if an aggregator-free single-license source is wanted).
- [pending] INEGI GDP + core-CPI exact series IDs deferred (only headline INPC + ENOE unemployment wired so far).
- [pending] Live-API smoke test through the panel Save&run path with real Banxico/INEGI/FRED tokens — not yet run (no tokens available); unit suite (862) is the current proof.
- [pending] Quarter-period ('quarterly') macro support for DBnomics/INEGI period parsing (DBnomics adapter currently handles annual/monthly/daily; quarterly series need period-format handling).

## Macro catalog expansion (2026-06-17) — DONE: 17 -> 419 verified e_* columns / 44 economies
- [done] Deep-research fan-out (wf_b7eae361-f5f) — FAILED the enumeration (rate-limited WebFetch, all DBnomics 0-0, 1 usable series / 3.3M tokens). Lesson recorded in lessons.md.
- [done] Pivot: deterministic verifier `scripts/build_macro_catalog.py` — country×concept matrix over wide DBnomics datasets (BIS policy rates, IMF IFS cpi/fx/reserves/short/ind-prod/unemployment, Eurostat 10Y, World Bank GDP) + FRED US deepening.
- [done] Live-API verify each series_id before write (DBnomics num_found; FRED fredgraph.csv via curl) — 402 kept, 51 non-existent dropped. Zero hallucinated IDs.
- [done] Written to macro_catalog.json (419 rows, schema-clean, 0 dupes). Panel picker auto-includes via `_build_macro_group` (no column_catalog.json edit needed). Resolver routes; real end-to-end adapter fetch verified; 806 unit tests green; README/CHANGELOG updated.
- [pending] commercial_ok licensing pass: current per-source defaults (Eurostat/WB=yes, IMF/BIS=restricted, FRED=no) are conservative reads, not adjudicated terms — confirm verbatim redistribution terms before any commercial ship.
- [pending] Optional: quarterly-frequency macro series (AU/NZ CPI, GDP) need DBnomics quarterly period parsing (deferred; none added so no current breakage).
- [pending] Optional: MX catalog depth via Banxico/INEGI needs tokens to live-verify new IDs (existing 7 untouched).

## Follow-ups
- [pending] Burn down the mypy ignore_errors baseline (fmp/lseg providers, data_blocks, column_builder, helpers, data_column).
- [done] Dev environment: stale non-editable install replaced with `pip install --user -e .`; CLI now reflects `src/`. Added package `__main__.py` so `python -m kaxanuk.data_curator` works regardless of PATH.
- [pending] PATH: `%APPDATA%\Python\Python314\Scripts` is not on PATH, so the bare `kaxanuk.data_curator` command needs either that dir added to PATH manually or the `python -m kaxanuk.data_curator` form.
- [pending] Panel run output: stream logs live (currently captured at process completion); consider line-buffered reads or SSE.
- [pending] Perf, next real lever: vectorize per-row entity assembly / column packing (profiling shows ~610k isinstance + ~480k getattr calls per 12 tickers in data_blocks/entities/DataColumn; compute stage = ~0.6s of the measured 0.79s/ticker on real S&P 500 runs). Threading proven useless on GIL builds — see benchmarks/RESULTS.md addendum. Alternatives: process-pool compute, or FMP bulk endpoints for the fetch side.
