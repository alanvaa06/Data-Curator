# Proposal — Macro-Economic Data Layer for the Data Curator

Date: 2026-06-17
Status: **Proposal (decision gate not yet passed)** — selection backed by adversarially-verified research; build gated on open verifications below.
Author: AI Strategy & Orchestration Agent (for Alan Vazquez, CFA)

---

## 1. Executive recommendation

Add macro-economic series (rates, inflation, GDP, employment, FX, monetary aggregates) to
the Data Curator as a **new, non-ticker Data Block** — the architecture's intended first
non-equity use — sourced from **direct national providers, not an aggregator**.

| Decision | Pick | Status of evidence |
|----------|------|--------------------|
| **Primary source (decisive Mexico gate)** | **Banxico SIE API REST** (MX rates, TIIE, Cetes, FX/FIX, reserves) + **INEGI Indicator Bank API** (MX INPC/CPI, GDP, employment) | **Verified** (3-0 unanimous, primary central-bank/statistics-agency sources) |
| **US layer** | **FRED** (optional, bring-your-own-key) — deepest/highest-frequency free US macro **plus ALFRED point-in-time vintages**, the only free source here that serves data-vintages (directly serves KaxaNuk's reproducibility/audit mandate). Permitted for this repo because it is **non-commercial open-source**: ships code not data, each user supplies their own key, data flows to the user's own disk | **Re-evaluated 2026-06-17** under corrected non-commercial/OSS framing — one residual caveat, §6.2 |
| **Rest-of-world layer** | **DBnomics** (keyless, one client → OECD + World Bank + IMF + Eurostat + ECB + BIS) for non-US global breadth; **World Bank direct** (CC-BY 4.0, redistributable) as the clean-license minimal fallback | **Verified**: DBnomics 93 providers incl. those; **no FRED, no Banxico** |
| **Aggregator for the Mexico gate** | **Rejected** — DBnomics carries neither Banxico nor adequate INEGI (single thin `DF_STEI`); MX stays direct | **Verified** |
| **Integration shape** | New `EconomicIndicatorDataBlock` with `grouping_identifier_field = None`; columns `e_*` forward-filled to market dates; existing CSV/Parquet/DuckDB output unchanged | **Verified** against current code |

**One-line rationale:** the user's scope is *US + Mexico + global, free-only*, and the repo is
**non-commercial open-source (MIT), bring-your-own-key**. Mexico is the decisive gate and only
**Banxico + INEGI** have verified coverage of it (no aggregator reaches Banxico). For the US,
**FRED** is the deepest free source and — uniquely — offers ALFRED point-in-time vintages that
serve the reproducibility mandate; its redistribution/AI clauses bind the *end user*, not an MIT
tool that ships no data, so it is usable here (see §6.2 for the one residual caveat and the
commercial-future flip). For the rest of the world, **DBnomics** covers OECD/WB/IMF/Eurostat
under one keyless client. Three optional adapters, one `MacroDataProviderInterface`.

---

## 2. Why this, honestly — verified vs. assumed

The provider research ran 105 agents, fetched 23 sources, extracted 99 claims, and put 25
through 3-vote adversarial verification. **Calibration matters here**, so the separation is
explicit:

**Verified (3-0, primary sources):**
- Banxico SIE exposes core MX central-bank series with exact catalog IDs: target rate
  `SF61745`, 28-day TIIE `SF60648`, 91-day TIIE `SF60649`, 28-day Cetes `SF60633`,
  USD FIX `SF43718`, EUR `SF46410`, JPY `SF46406`, GBP `SF46407`, CAD `SF60632`,
  international reserves `SF43707`.
- Banxico is **free but not keyless** — every call needs a no-cost 64-char `Bmx-Token` header.
- INEGI's Indicator Bank API serves indicators at national / state / municipality levels
  (per-indicator availability), free, with a 36-char email-registration token.
- Mature community Python SDKs (`siebanxico`, `sie-banxico`, `INEGIpy`) return **time-indexed
  pandas DataFrames** — matching the Data Curator's Pandas output target.

**Genuinely refuted (a real refute vote, not just absence):**
- The claim that **Banxico** carries CPI (`SP1`) and M1/M2/M3 aggregates was **refuted (1-0)**.
  ⇒ Do not assume Banxico is the inflation source. Working assumption: **INEGI** owns INPC/CPI
  — but that specific series availability was *not* independently confirmed (open gate §6.1).
- The claim that **DBnomics includes INEGI** was **refuted (0-1)**; its INEGI coverage appears
  to be a single thin dataset (`DF_STEI`). ⇒ An aggregator is not a substitute for direct INEGI.

**Unverified — and the reason is infrastructure, not falsehood:** every FRED, DBnomics, and
EconDB claim scored `0-0 (3 abstain)`. The run logs show this is because the verification
agents hit *"Server is temporarily limiting requests · Rate limited"* mid-run — **the claims
were neither confirmed nor disproven.** Treat all FRED/aggregator statements as *leads
requiring fresh verification*, not as findings. This is why the global layer is deferred rather
than decided.

---

## 3. Architectural fit (verified against current code)

The macro layer is **not** core surgery. Two seams already exist for it.

### 3.1 Data Blocks already support non-ticker data — by design

`src/kaxanuk/data_curator/data_blocks/base_data_block.py:52-55` documents the exact hook:

```python
# identifier based block entities will be grouped by this field's type:
# (the system only supports one single identifier type for grouping across all used data blocks)
# (None means no grouping, so this data block's columns will be accessible for all identifiers)
grouping_identifier_field: EntityField | None
```

A macro series (e.g. US CPI, Banxico target rate) is **global**, not per-ticker. Setting
`grouping_identifier_field = None` makes the block's columns attach to **every** identifier's
output — which is precisely the desired join (same macro value broadcast to AAPL, WALMEX, etc.
on each date). The README roadmap ("Data Blocks will generalize the link between data providers
and feature column prefixes … economic indicators, alternative data, indices") and the code
agree: macro is the intended first non-equity block.

### 3.2 The provider seam: a sibling interface, not a forced fit

The equity `DataProviderInterface`
(`src/kaxanuk/data_curator/data_providers/data_provider_interface.py`) is ticker-scoped — its
four abstract methods (`get_market_data`, `get_fundamental_data`, `get_dividend_data`,
`get_split_data`) all take `main_identifier`. A macro provider has no ticker. **Do not bend
the equity interface** (returning stubs for four irrelevant methods is the hacky path). Add a
parallel interface:

```python
# data_providers/macro_data_provider_interface.py
class MacroDataProviderInterface(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def get_economic_data(
        self, *, start_date: datetime.date, end_date: datetime.date,
    ) -> dict[str, EconomicIndicatorData]:
        """Return {series_id -> EconomicIndicatorData}; not identifier-scoped."""

    @abc.abstractmethod
    def validate_api_key(self) -> bool | None: ...
```

It can reuse the existing pooled-HTTP helpers (`_request_data`, `_get_http_client`) that the
equity interface already exposes — Banxico is plain REST + a token header.

---

## 4. Components (new code, additive)

1. **Entities** — `entities/economic_indicator_row.py`, `entities/economic_indicator_data.py`
   (frozen `slots` dataclasses, mirroring `MarketDataDailyRow` / `MarketData`):
   ```python
   @dataclasses.dataclass(frozen=True, slots=True)
   class EconomicIndicatorRow(BaseDataEntity):
       date: datetime.date
       value: decimal.Decimal | None

   @dataclasses.dataclass(frozen=True, slots=True)
   class EconomicIndicatorData(BaseDataEntity):
       start_date: datetime.date
       end_date: datetime.date
       series_id: str          # e.g. 'banxico:SF61745'
       series_name: str        # e.g. 'MX target rate'
       rows: dict[str, EconomicIndicatorRow]   # ISO-date keys
   ```

2. **Data block** — `data_blocks/economic_indicators/__init__.py`:
   ```python
   class EconomicIndicatorDataBlock(BaseDataBlock):
       clock_sync_field = EconomicIndicatorRow.date
       grouping_identifier_field = None          # <-- broadcast to all tickers
       main_entity = EconomicIndicatorData
       prefix_entity_map = {'e': EconomicIndicatorRow}
   ```

3. **Macro provider interface** — `data_providers/macro_data_provider_interface.py` (§3.2).

4. **First adapter** — `data_providers/banxico_sie.py` + `data_providers/inegi.py`
   (the verified MX pair). Each maps a configured set of series IDs → `EconomicIndicatorData`.
   Thin direct-HTTP adapter preferred over the aged community SDKs to avoid dependency
   staleness (`siebanxico` last released Sept 2023), but the SDK output shape confirms the
   contract is clean.

5. **Column wiring** — `e_*` columns (e.g. `e_mx_target_rate`, `e_mx_inpc`, `e_us_cpi`),
   **forward-filled to market dates** in `ColumnBuilder` (macro cadence is monthly/quarterly;
   markets are daily). This mirrors the existing fundamental-data infill.

6. **Config seam** — extend the JSON config `general` block with `macro_data_provider` and a
   `macro_series` list; resolve it in `config_handlers/_resolver.py` behind the existing
   `ConfiguratorInterface`. Bump `parameters_format_version`.

7. **Fetch orchestration** — fetch macro data **once, globally, before the per-identifier
   loop** in `data_curator.main()` (not per-ticker), cache it, pass to every `ColumnBuilder`.

8. **Panel + catalog** — add the `e_` group to `config_handlers/column_catalog.json` and the
   panel picker so macro columns are selectable in the UI.

---

## 5. The registration checklist (from a prior production lesson)

Adding a provider/handler is **not** one file. The 2026-06-10 DuckDB lesson cost a failed real
run because a template change never reached the live workspace. A macro provider touches:

- the adapter module(s) + `data_providers/__init__.py` export
- the new entities + `entities/__init__.py` export
- the new data block + its registration
- `_resolver.py` / `ConfiguratorInterface` (provider selection)
- `data_curator.main()` signature (accept the macro provider + global fetch)
- `ColumnBuilder` (macro infill)
- `column_catalog.json` + panel picker (`e_` group)
- **the entry-script template `templates/data_curator/__main__.py` AND the repo-root workspace
  `__main__.py` the user actually runs** (template edits do not propagate to existing workspaces)
- docs (README provider list, API reference) + CHANGELOG

**Verification rule (from the 2026-06-09 lesson):** smoke-test through the panel's real
`Save & run` path with a realistic mixed run (a few MX + US tickers, monthly macro series), not
just pytest — and run the documented command in a fresh shell.

---

## 6. Open gates — MUST close before build (do not skip)

These are decision-critical and were left open because the research verifier got rate-limited.

1. **INPC/CPI source-of-truth + exact series IDs.** Banxico-CPI was refuted; INEGI is the
   assumed INPC source but unconfirmed. *Without this, the inflation gate is not covered.*
2. **FRED Terms of Use — RE-EVALUATED (2026-06-17) for the corrected non-commercial/OSS
   framing: FRED is PERMITTED here, with one caveat.** The June-2024 ToU does prohibit
   *"storing, caching, or archiving any portion of FRED …"* and *"development or training of any
   … machine learning …"* — but the binding analysis depends on **who** is bound and **for
   what**:
   - The bound party is the **API-key holder (end user)**, not the MIT-licensed Data Curator,
     which **ships code, not FRED data** — each user supplies their own key and the data flows to
     that user's own disk. The tool redistributes nothing.
   - FRED **explicitly endorses** *"economic research, financial modeling, academic research"*
     use, its ToU *"govern your use … to develop, reproduce and distribute applications that
     interoperate with the FRED API"* (building such a tool is contemplated), and its Fair-Use
     concern is *"unauthorized redistribution of **large datasets**"* — redistribution-scoped,
     not personal-storage-scoped. The sanctioned FRED Python ecosystem (`fredapi`,
     `pandas-datareader`) writes to local disk and remained current after the June-2024 update.
   - The ML/AI clause binds the end user only if they train models on FRED content; the
     fetch-and-store tool does not, and must simply surface the obligation to users.
   - **Residual caveat (calibration):** I could not fetch the verbatim current ToU (FRED
     bot-blocks automated fetches), so the redistribution-scoped reading rests on the Fair-Use
     language + ecosystem practice + third-party summaries, not the primary clause text. Confidence
     high for a non-commercial OSS tool, not certain. **This flips back to DISQUALIFIED the moment
     KaxaNuk ships FRED data inside a commercial product or trains models on it** — gate the
     commercial path separately.
   Net: FRED = optional US adapter (BYO-key); DBnomics/World Bank cover the rest of the world.
3. **Banxico / INEGI redistribution licensing** for a commercial product — not examined.
4. **Point-in-time / data-vintage (ALFRED-style).** Only FRED was *claimed* to support it
   (unverified); no evidence Banxico or INEGI do. This matters for KaxaNuk's
   reproducibility/audit pitch — absence is a known limitation to design around, not a silent gap.
5. **Rate limits** — unverified for every source.

---

## 7. Phased plan (gated)

- **Phase 0 — close gates §6.1–§6.5** (research, ~1–2 days). Output: confirmed INPC source/IDs,
  FRED go/no-go, licensing read. *Gate: do not build until §6.1 and §6.2 are answered.*
- **Phase 1 — entities + `EconomicIndicatorDataBlock`**, strict TDD (non-ticker grouping is the
  novel path; test it hard with all-null and precision-varying series per the DuckDB lesson).
- **Phase 2 — Banxico + INEGI adapters** behind `MacroDataProviderInterface`, with a fake adapter
  for tests mirroring `tests/unit/data_providers/`.
- **Phase 3 — config + `main()` global fetch + `ColumnBuilder` macro infill**; format-version bump.
- **Phase 4 — output + catalog + panel + docs**; full registration checklist (§5); panel smoke test.
- **Phase 5 (optional, later) — US + rest-of-world layer**, all behind the same
  `MacroDataProviderInterface`:
  - **FRED adapter** for US (optional, BYO-key) — best depth/frequency + ALFRED point-in-time
    vintages for reproducibility. Surface FRED's BYO-key + research-use obligations in the docs;
    gate any future commercial/ML-training use separately (§6.2).
  - **DBnomics adapter** for non-US global (keyless; OECD + World Bank + IMF + Eurostat + ECB +
    BIS; namespaced by provider_code/dataset_code). Honor each underlying provider's license per
    series (World Bank CC-BY is clean; OECD/IMF read once). If an aggregator dependency is
    unwanted, ship **World Bank direct** as a minimal single-license alternative.
  - Confirm the DBnomics Python client → Pandas path in Phase 1 (rate-limited-unverified in
    research, but the client is well-established).

---

## 8. Scope guard / non-goals

- No change to the equity `DataProviderInterface` or to `main()`'s equity path semantics.
- No new heavy runtime dependency if a thin direct-HTTP adapter suffices (Banxico/INEGI are REST).
- Macro layer is **read + join only** — no new alt-data, no point-in-time engine in v1
  (vintage support is a documented limitation pending §6.4).
- The aggregator route is explicitly out of v1 for the Mexico gate.

---

## Sources (verified, primary)

- Banxico SIE API REST — https://www.banxico.org.mx/SieAPIRest/service/v1/?locale=en
- INEGI Indicator Bank API — https://en.www.inegi.org.mx/servicios/api_indicadores.html
- siebanxico (Python SDK, DataFrame output) — https://github.com/chekecocol/siebanxico
- INEGIpy (Python SDK) — https://pypi.org/project/INEGIpy/
- World Bank summary terms of use (global-layer candidate) — https://data.worldbank.org/summary-terms-of-use
- OECD terms — https://www.oecd.org/en/about/terms-conditions.html
- FRED API + Terms of Use (UNVERIFIED — gate §6.2) — https://fred.stlouisfed.org/docs/api/fred/ ·
  https://fred.stlouisfed.org/docs/api/terms_of_use.html
- DBnomics providers (aggregator, UNVERIFIED) — https://db.nomics.world/providers
