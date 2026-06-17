# Design — Macro-Economic Data Layer (Mexico + FRED + DBnomics)

Date: 2026-06-17
Status: Approved (design gate passed)
Branch: `feat/macro-data-layer`
Supersedes: the source-selection rationale lives in
`docs/superpowers/specs/2026-06-17-macro-data-layer-proposal.md`; this is the technical design.

## Goal

Add macro-economic series (rates, inflation, GDP, employment, FX, monetary aggregates) to the
Data Curator as a new **non-ticker Data Block**, sourced from **FRED** (US, bring-your-own-key),
**Banxico SIE + INEGI** (Mexico, direct), and **DBnomics** (rest-of-world aggregator). Macro
columns (`e_*`) attach to every ticker's existing CSV/Parquet/DuckDB output. No equity-path
change, no new runtime dependency.

## Locked decisions

| Decision | Choice |
|----------|--------|
| Series selection | **Curated catalog with internal routing** — `e_*` columns map to `(provider, series_id)`; user picks named columns like equity columns |
| Vintages | **Latest-values-only in v1** — entity is `date → value`; FRED/ALFRED vintages deferred |
| Adapters | **Thin direct HTTP** for all four, reusing the interface's pooled-httpx helpers — **zero new runtime deps** |
| Provider activation | **Column-driven** — selecting `e_*` columns activates exactly the providers those columns route to (and that have a key/token); no separate provider-pick field |
| Join semantics | Macro series **forward-filled to each ticker's market dates** via the existing `ColumnBuilder._infill_data` |
| Catalog growth | Catalog is a **data file built to expand** to a comprehensive set; each entry carries a `commercial_ok` licensing flag |

## Architectural principle

Two existing seams carry this with no core surgery:

1. **Data Blocks already support non-ticker data.** `base_data_block.py:52-55` documents
   `grouping_identifier_field: EntityField | None`, where `None` means "no grouping, columns
   accessible for all identifiers." Macro is global → `grouping_identifier_field = None`.
2. **`ColumnBuilder` already has the machinery.** The prefix dispatch is a `match column_type`
   in `_process_columns_with_available_dependencies`
   (`services/column_builder.py:604-744`); adding macro = one new `case 'e':`. Forward-fill
   already exists as `_infill_data` (`column_builder.py:507`) — the same call used for
   fundamental data (`column_builder.py:95-98`) is exactly what monthly/quarterly macro needs
   against daily market dates.

**Untouched (critical) code:** the equity `DataProviderInterface` and its providers, the
`Configuration` entity's equity fields, output handlers, `features/`, and `main()`'s equity
fetch/compute/output loop semantics.

## Components (all additive)

### 1. Entities — `entities/economic_indicator_row.py`, `entities/economic_indicator_data.py`
Frozen-`slots` dataclasses mirroring `MarketDataDailyRow` / `MarketData`:
```python
@dataclasses.dataclass(frozen=True, slots=True)
class EconomicIndicatorRow(BaseDataEntity):
    date: datetime.date
    value: decimal.Decimal | None

@dataclasses.dataclass(frozen=True, slots=True)
class EconomicIndicatorData(BaseDataEntity):
    start_date: datetime.date
    end_date: datetime.date
    series_id: str          # provider-native, e.g. 'SF61745'
    series_name: str        # human label, e.g. 'MX target rate'
    rows: dict[str, EconomicIndicatorRow]   # ISO-date-string keys, sorted
```
Exported from `entities/__init__.py`. Picklable (frozen-slots + dict) → survives the
ProcessPool compute path.

### 2. Data block — `data_blocks/economic_indicators/__init__.py`
```python
class EconomicIndicatorDataBlock(BaseDataBlock):
    clock_sync_field = EconomicIndicatorRow.date
    grouping_identifier_field = None          # broadcast to all identifiers
    main_entity = EconomicIndicatorData
    prefix_entity_map = {'e': EconomicIndicatorRow}
```

### 3. Provider interface — `data_providers/macro_data_provider_interface.py`
Sibling to the equity interface (do **not** bend the ticker-scoped one):
```python
class MacroDataProviderInterface(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def get_economic_data(
        self, *, series_ids: list[str],
        start_date: datetime.date, end_date: datetime.date,
    ) -> dict[str, EconomicIndicatorData]:
        """Return {series_id -> EconomicIndicatorData}. Not identifier-scoped."""

    @abc.abstractmethod
    def validate_api_key(self) -> bool | None: ...
```
May reuse the equity interface's pooled-HTTP helpers (extract the shared `_request_data` /
`_get_http_client` into a small mixin or a module-level helper if cleaner — decided at plan time).

### 4. Adapters (thin HTTP) — one small module each
- `data_providers/fred.py` — `https://api.stlouisfed.org/fred/series/observations`, key as query param.
- `data_providers/banxico_sie.py` — `.../SieAPIRest/service/v1/series/{ids}/datos`, `Bmx-Token` header.
- `data_providers/inegi.py` — Indicator Bank API, token in path.
- `data_providers/dbnomics.py` — `https://api.db.nomics.world/v22/series?series_ids=...` (flat JSON observations; keyless).
Each maps its provider-native JSON → `EconomicIndicatorData`. Exported from
`data_providers/__init__.py`.

### 5. Catalog — `config_handlers/macro_catalog.json`
Single source of truth mapping columns to sources. One row per macro column:
```json
{
  "column": "e_mx_target_rate",
  "provider": "banxico_sie",
  "series_id": "SF61745",
  "name": "Mexico overnight target rate",
  "region": "MX",
  "frequency": "daily",
  "commercial_ok": "unverified"
}
```
`commercial_ok` ∈ `{"yes","no","unverified"}` bakes the licensing classification into the data
(World Bank = yes; FRED = no; Banxico/INEGI/OECD/IMF = unverified) so a future commercial build
can filter. The file is designed to grow to a comprehensive catalog; v1 seeds the starter set
(§ v1 catalog). Loaded by the configurator (routing) and served to the panel picker.

### 6. Config resolution — `config_handlers/_resolver.py` + `JsonConfigurator`
- The entry script injects candidate macro providers into `JsonConfigurator` via a new
  `macro_data_providers={...}` dict — parallel to the existing `data_providers={...}` dict —
  each entry `{'class': <Adapter>, 'api_key': os.getenv(...)}` (DBnomics `'api_key': None`).
- New `get_macro_data_providers()` on `ConfiguratorInterface` / `JsonConfigurator`, returning the
  list of **instantiated, needed** macro providers (from the injected candidates).
- `_resolver` helper: from the selected `e_*` columns + `macro_catalog.json`, compute the set of
  required providers; instantiate only those whose key/token is present; raise the usual
  `ConfigurationError` if a selected `e_*` column needs a provider whose key is missing.
- **No new JSON `general` field** — macro is fully column-driven; the existing `columns` list
  carries the `e_*` selections. Bump `parameters_format_version` (new recognized prefix).

### 7. Orchestration — `data_curator.py main()`
- New keyword arg `macro_data_providers: list[MacroDataProviderInterface] | None = None`.
- After `*.initialize()` and **before** the per-identifier loop, fetch macro **once, globally**:
  resolve selected `e_*` columns → `(provider, series_id)` via the catalog, call each provider's
  `get_economic_data`, and assemble `economic_data: dict[e_column_name, EconomicIndicatorData]`.
- Pass `economic_data` into `_compute_identifier_columns(...)` and through the worker wrapper
  `_compute_identifier_columns_in_worker(...)` kwargs (picklable) into `ColumnBuilder`.
- Macro fetch is global, not per-ticker → it does **not** enter `_fetch_identifier_data`.

### 8. Column building — `services/column_builder.py`
- `ColumnBuilder.__init__` gains `economic_data: dict[str, EconomicIndicatorData]`. For each
  selected `e_*` column, infill its series to market dates with the existing
  `_infill_data(iter(market_data.daily_rows.keys()), economic_data[column].rows)`, stored as
  `self.infilled_economic_data_rows[column]`.
- Add `case 'e':` to `_process_columns_with_available_dependencies` →
  `_generate_column(infilled_economic_data_rows[column], 'value')`. Thread
  `infilled_economic_data_rows` through the same call sites that already pass
  `infilled_fundamental_data_rows` (the two `_process_columns_with_available_dependencies` calls
  in `process_columns` and the recursive call for `c_` dependencies).
- A selected `e_*` column with no catalog entry / no fetched data → `ColumnBuilderUnavailableEntityFieldError`, consistent with the other prefixes.

### 9. Panel + keys
- Add the `e_` group to the panel's column catalog so macro columns are pickable (extend
  `column_catalog.json` / the catalog the editor serves).
- Entry script reads `KNDC_API_KEY_FRED`, `KNDC_API_KEY_BANXICO`, `KNDC_API_KEY_INEGI` from
  `Config/.env` (existing panel API-keys section writes `.env`; DBnomics needs none).

## v1 catalog (starter set)

US/FRED: `e_us_cpi` `e_us_core_cpi` `e_us_fed_funds` `e_us_2y` `e_us_10y` `e_us_unemployment`
`e_us_gdp` `e_us_m2`.
MX/Banxico (verified IDs): `e_mx_target_rate` (SF61745) `e_mx_tiie28` (SF60648)
`e_mx_cetes28` (SF60633) `e_mx_usdmxn_fix` (SF43718) `e_mx_reserves` (SF43707).
MX/INEGI: `e_mx_inpc` `e_mx_gdp` `e_mx_unemployment` — **exact series IDs are the open Phase-0
gate**.
Global/DBnomics: `e_ez_hicp` `e_ecb_rate` (+ the pattern to add more).

## Data flow

`columns` includes `e_*` → configurator routes them via `macro_catalog.json`, instantiates the
needed macro providers (keys present) → `main()` fetches all series once, builds
`{e_column → EconomicIndicatorData}` → per ticker, `ColumnBuilder` infills each series to that
ticker's market dates → `process_columns` emits `e_*` alongside `m_*`/`f_*`/`c_*` in the pyarrow
table → existing output handlers write it unchanged.

## Error handling

- Missing key/token for a selected provider → `ConfigurationError`, logged critical, exit 1
  (mirrors equity provider key validation).
- Macro fetch failure (network/HTTP) → surfaces as the existing `ApiEndpointError` path in
  `main()`; a macro fetch error aborts the run (it is global, not per-ticker).
- Unknown `e_*` column → `ColumnBuilderUnavailableEntityFieldError`, same as other prefixes.

## Testing strategy (TDD, follow `docs/references/python_best_practices.md`)

1. **Entities** — construction, type/None handling, sorted-date invariant.
2. **`EconomicIndicatorDataBlock`** — the novel non-ticker path: `grouping_identifier_field=None`
   packs correctly; all-null series; a series whose dates don't align to any market date;
   per-batch precision variance (the DuckDB lesson — realistic decimals, not clean doubles).
3. **Adapters** — each maps a captured sample JSON payload → `EconomicIndicatorData`; token/key
   wiring; empty/missing-series responses. **No live API calls** — fixture payloads only.
4. **`_resolver` routing** — selected `e_*` columns → correct provider set; missing-key →
   `ConfigurationError`; unknown column → error.
5. **`ColumnBuilder` `case 'e'`** — forward-fill correctness (monthly series → daily dates;
   value carried until next observation; dates before first observation → None); `e_*` coexists
   with `c_*` calculated columns that consume it.
6. **`main()` global fetch** — macro fetched once (not per-ticker); `economic_data` survives the
   ProcessPool worker path; broadcast to multiple tickers.
A fake macro adapter under `tests/unit/data_providers/` mirrors the existing fake-provider pattern.

## Registration checklist (from the 2026-06-10 DuckDB lesson — a provider touches many files)

entities + `entities/__init__` · data block + registration · `MacroDataProviderInterface` ·
4 adapters + `data_providers/__init__` · `macro_catalog.json` · `_resolver` +
`ConfiguratorInterface` + `JsonConfigurator` (`get_macro_data_providers`) · `main()` signature +
global fetch · `ColumnBuilder` (`case 'e'` + infill + threaded params) · panel picker `e_` group
+ `.env` keys · **entry-script template `templates/data_curator/__main__.py` AND the repo-root
workspace `__main__.py` the user actually runs** · README provider list + API reference ·
CHANGELOG · `parameters_format_version` bump. **Verify through the panel's real Save & run** with
a mixed run (a few US + MX tickers, monthly + daily macro series) — not just pytest.

## Phasing (incremental, MX-first to de-risk the shared core)

- **Phase 0 (gate):** confirm INEGI/Banxico INPC + GDP + employment series IDs.
- **Phase 1:** entities + `EconomicIndicatorDataBlock` + `MacroDataProviderInterface` (the shared
  novel core), strict TDD.
- **Phase 2:** Banxico + INEGI adapters (verified anchor).
- **Phase 3:** `_resolver` routing + `main()` global fetch + `ColumnBuilder` `case 'e'` + infill —
  end-to-end with the MX adapters.
- **Phase 4:** FRED adapter (US).
- **Phase 5:** DBnomics adapter (rest-of-world).
- **Phase 6:** catalog finalize + panel picker + entry scripts + docs + CHANGELOG; full panel
  smoke test.

Each phase commits green (covered-AC tests + full repo suite) before the next.

## Scope guard / non-goals (v1)

- No data vintages / point-in-time (FRED/ALFRED) — deferred.
- No macro-only runs — the pipeline stays ticker-driven; macro columns ride per-ticker output.
- No new runtime dependency.
- No change to the equity `DataProviderInterface`, providers, output handlers, or `main()`'s
  equity loop semantics.
- Catalog ships the starter set only; comprehensive expansion is a deliberate follow-up (the
  data-file design makes it append-only).

## Open gate

Mexican **INPC/CPI, GDP, employment** series identity and source — Banxico-CPI was refuted in
research (1-0), INEGI is the assumed INPC owner but the exact series IDs were not verified. Close
in Phase 0 before wiring the `e_mx_inpc` / `e_mx_gdp` / `e_mx_unemployment` catalog rows.
