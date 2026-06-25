# ETF browser + custom identifier lists — design

**Date:** 2026-06-24
**Status:** Approved (design)
**Surface:** Data Curator config editor panel (`python -m kaxanuk.data_curator start`)

## Goal

Two additions to the Identifiers section of the config editor:

1. A **browsable ETF catalog** — a large, curated set of US-listed ETFs grouped by
   topic (US Sectors, Thematic, Factor/Style/Size, Broad/Bonds/Commodities/Intl).
   Each ETF is one ticker; clicking a pill adds that ticker to the identifiers.
2. **Custom identifier lists** — save the current identifiers as a named, persisted
   list that reappears as a button to reload or delete later.

## Context

The editor already renders index *presets* (`S&P 500`, `Nasdaq 100`, `Russell 2000`)
as flat pill buttons, each adding a whole constituent list. Source files:

- `src/kaxanuk/data_curator/config_handlers/identifier_presets.json` — preset data.
- `src/kaxanuk/data_curator/config_handlers/column_catalog.py` — bundled-JSON loaders.
- `src/kaxanuk/data_curator/services/config_editor.py` — stdlib HTTP server + pure
  config/catalog/env helpers; `.env` is stored as a sibling of the config file.
- `src/kaxanuk/data_curator/services/config_editor_page.html` — the single-page UI;
  `renderPresets()` draws preset pills, `renderColumns()`/`groupHeader()` implement
  the collapsible group → subgroup tree used by Output columns.

An ETF differs from an index preset: it is itself one security to fetch, not a
500-name list. So ETFs are modeled as individually selectable pills, grouped for
browsing — not as add-the-whole-list buttons.

## Architecture

### A. ETF data — new bundled file `etf_catalog.json`

Kept separate from `identifier_presets.json` (single responsibility: presets are
constituent lists, the ETF catalog is a browsable security tree). Nested shape:

```json
{
  "as_of": "2026-06-24",
  "groups": [
    {"label": "US Sectors", "subgroups": [
      {"label": "SPDR Select Sector", "etfs": [{"ticker": "XLK", "name": "Technology"}]}
    ]},
    {"label": "Thematic", "subgroups": []},
    {"label": "Factor / Style / Size", "subgroups": []},
    {"label": "Broad / Bonds / Commodities / Intl", "subgroups": []}
  ]
}
```

- `ticker` — US-listed ETF symbol (verified real / currently listed).
- `name` — short descriptive label (shown on hover / aria).
- Tickers are unique across the whole catalog (each ETF assigned to its best-fit
  subgroup).

New loader `load_etf_catalog() -> dict` in `column_catalog.py`, mirroring
`load_identifier_presets()` (uses the same `_load_bundled_json` helper).

### B. Backend — `config_editor.py`

1. `build_catalog_response()` gains `'etf_groups': load_etf_catalog()['groups']`,
   served by the existing `GET /api/catalog`.
2. **Custom lists** persisted at `config_file.parent / 'identifier_lists.json'`
   (sibling file, same placement convention as `.env`). File shape:
   `{"lists": [{"name": "...", "identifiers": ["AAPL", ...]}]}`.
   Pure helpers (testable without a server):
   - `read_custom_lists(path) -> list[dict]` — `[]` when the file is absent.
   - `save_custom_list(path, name, identifiers)` — upsert by name; validates a
     non-empty name and a list of non-empty string identifiers.
   - `delete_custom_list(path, name)` — remove by name; no-op when absent.
3. Endpoints (stdlib `BaseHTTPRequestHandler`, POST-only style like `/api/env`):
   - `GET  /api/lists` → `{"lists": [...]}`.
   - `POST /api/lists` → body `{name, identifiers}` → save → `{"status": "saved"}`.
   - `POST /api/lists/delete` → body `{name}` → delete → `{"status": "deleted"}`.
   Validation errors return `400 {"errors": [...]}`, matching existing handlers.

### C. Frontend — `config_editor_page.html`

1. **ETF browser**: a new collapsible block beneath the presets row inside the
   Identifiers fieldset. `renderEtfBrowser()` walks `catalog.etf_groups`, reusing
   the same collapsible mechanics as the column tree:
   - group header → subgroup header → row of ETF pills.
   - each pill shows the ticker, `title`/aria = fund name, click adds the single
     ticker to `state.identifiers` (dedupe), then `renderIdentifiers()`.
   - each subgroup header carries an `all` button (adds every ETF in it).
   - all groups collapsed by default; state tracked in the existing
     `collapsedGroups` set so it does not fight the column tree (namespaced keys,
     e.g. `ETF ▸ <group>`).
2. **Custom lists**: `renderCustomLists()` draws saved lists as pills next to the
   presets, distinct styling (e.g. a leading ★ or a subtle border) to separate
   them from index presets. Clicking re-adds the list's identifiers (dedupe). Each
   custom-list pill has a small × that calls `POST /api/lists/delete`. A
   `Save list…` button beside `Clear` prompts for a name (`prompt()`), POSTs the
   current `state.identifiers`, then re-fetches and re-renders. Empty identifiers
   or empty name → no-op with a status hint.

### Data flow

`boot()` already fetches `/api/catalog`; it now also fetches `/api/lists`. Render
order in `boot()`: presets → custom lists → ETF browser → identifiers. Saving or
deleting a custom list re-fetches `/api/lists` and re-renders that block only.

### Error handling

- Loader: a malformed/missing `etf_catalog.json` is a packaging bug — surfaces as a
  normal exception at catalog build (consistent with the other bundled loaders).
- Custom-list endpoints validate input and return `400` with messages; the UI shows
  the message via `setStatus(..., 'err')` and leaves identifiers unchanged.
- ETF pills and custom-list re-add never produce duplicates (set-guarded), matching
  preset behavior.

## Testing

Extend `tests/unit`:

- `column_catalog` test: `load_etf_catalog()` returns the four top-level groups, the
  expected nested shape, unique tickers across the catalog, and a known anchor
  (e.g. `XLK` present under US Sectors).
- `config_editor` test: `build_catalog_response()` includes `etf_groups`; custom-list
  `save → read → delete` round-trips on a `tmp_path` file, including upsert-by-name
  and validation rejection of empty name / non-string identifiers.

## ETF universe (content)

Compiled and adversarially verified (each ticker confirmed real, US-listed, correct
issuer; deduped) before landing in `etf_catalog.json`. Target breadth: a large
curated set across all four groups — sectors (SPDR select + equal-weight + industry),
thematics (AI/robotics, semis, cybersecurity, cloud, fintech/blockchain incl. spot
crypto, clean energy, genomics, disruptive, EV/battery, infrastructure, defense,
water, space, cannabis, miners, REITs, consumer, volatility, leveraged/inverse),
factor/style/size, and broad/bonds/commodities/international building blocks.

## Out of scope (YAGNI)

- No live ETF holdings / constituent lookup.
- No editing the ETF catalog from the UI.
- No ETF metadata beyond ticker + name.
- No bulk-paste input (custom lists chosen over bulk paste).
