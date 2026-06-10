# Design — Replace Excel config with a lightweight HTML parameter editor

Date: 2026-06-09
Branch: `feat/html-config-editor`
Status: Approved (design gate passed)

## Goal

Replace the `.xlsx` configuration workflow with a lightweight HTML app for managing
the KaxaNuk Data Curator run parameters. The Excel configurator stays as a working,
deprecated fallback; the JSON + HTML path becomes the default. No critical
architecture is modified.

## Locked decisions

| Decision | Choice |
|----------|--------|
| Config file format | JSON (`Config/data_curator_parameters.json`) — stdlib read/write, zero new runtime deps, native to browser JS |
| HTML app delivery | Local `http.server` (stdlib) launched by a new CLI command, bound to `127.0.0.1`, serves a self-contained page that loads/saves the JSON directly |
| Excel disposition | `ExcelConfigurator` kept as a deprecated, still-functional fallback; not deleted, `openpyxl` retained |
| Output-columns UX | Searchable checklist grouped by prefix + free-text entry for custom columns |

## Architectural principle

`ConfiguratorInterface` (`src/kaxanuk/data_curator/config_handlers/__init__.py`) is the
designed extension seam. The entry script wires the available data providers and output
handlers and hands them to a configurator; the configurator selects among them and
produces a `Configuration` entity. Adding a second `ConfiguratorInterface` implementation
is therefore the non-invasive change the architecture was built for.

**Untouched (critical) code:** `data_curator.py` (`main()`), `entities/` (`Configuration`),
`data_providers/`, `output_handlers/`, `features/`, `modules/`, and the internals of
`ExcelConfigurator`.

## Components

All components are new code, except the additive CLI wiring.

1. **`config_handlers/json_configurator.py` — `JsonConfigurator(ConfiguratorInterface)`**
   - Loads and parses `Config/data_curator_parameters.json`.
   - Produces the same `Configuration` object as `ExcelConfigurator` from equivalent input.
   - Mirrors Excel error semantics: missing file, invalid JSON, missing keys, stale
     `parameters_format_version`, unknown/unavailable provider, invalid API key, invalid
     logger level → `ConfigurationHandlerError` / `ConfigurationError` → logged critical,
     `sys.exit()`.
   - Implements the five interface methods: `get_configuration`,
     `get_fundamental_data_provider`, `get_logger_level`, `get_market_data_provider`,
     `get_output_handler`.

2. **`config_handlers/_resolver.py` — shared resolution helpers**
   - Pure functions operating on a plain parsed-parameters dict: provider resolution,
     API-key validation, output-handler selection, logger-level lookup, format-version gate.
   - Consumed by `JsonConfigurator`. New code; `ExcelConfigurator` is left untouched to keep
     the legacy (currently untested) path at zero risk.
   - **Trade-off (flagged):** this duplicates rather than refactors Excel's post-parse logic.
     Refactoring `ExcelConfigurator` to delegate to `_resolver` is a noted follow-up, to be
     done only behind a characterization-test safety net.

3. **`config_handlers/column_catalog.json` — output column catalog**
   - The ~180 known output columns grouped by prefix (`m_`, `fbs_`, `fcf_`, `fis_`, `d_`,
     `s_`, `c_`), generated once from the existing xlsx template.
   - Single source of truth for the HTML picker; served by the editor server.
   - Free-text entry in the UI covers custom-calculation columns not in the catalog.

4. **`services/config_editor.py` — local editor server**
   - stdlib `http.server` / `BaseHTTPRequestHandler`, bound to `127.0.0.1` on a fixed port.
   - Routes:
     - `GET /` → the self-contained editor page.
     - `GET /api/config` → current `Config/data_curator_parameters.json` (or defaults if absent).
     - `POST /api/config` → validate and write the JSON; `400` + message on invalid payload.
     - `GET /api/catalog` → the column catalog + valid option lists (providers, periods,
       output formats, logger levels).
   - No arbitrary code execution; serves one fixed page file and one config path.

5. **`services/config_editor_page.html` — the page**
   - Self-contained vanilla HTML/CSS/JS, no build step, no external CDN (works offline).
   - Packaged in the wheel under `src/`; read at runtime via `importlib.resources`.
   - General fields as dropdowns/date inputs; identifiers as add/remove chips; output
     columns as a searchable, prefix-grouped checklist plus a free-text add box.

6. **`services/cli.py` — additive wiring**
   - New `config-editor` command: launches the server and opens the browser.
   - `json` added to `InitFormats` and `UpdateFormats`; `init json` / `update json`
     scaffold the JSON config and JSON entry script. Excel formats keep their behavior.

7. **Templates**
   - `templates/data_curator/Config/data_curator_parameters.json` — defaults mirroring the
     xlsx defaults.
   - A JSON entry-script template using `JsonConfigurator` (the existing `__main__.py` Excel
     entry script is retained for the excel format).

## JSON schema

```json
{
  "parameters_format_version": "0.47.0",
  "general": {
    "market_data_provider": "financial_modeling_prep",
    "fundamental_data_provider": "financial_modeling_prep",
    "start_date": "1990-01-01",
    "end_date": "2025-12-31",
    "period": "quarterly",
    "output_format": "csv",
    "logger_level": "info"
  },
  "identifiers": ["AAPL", "MSFT"],
  "columns": ["m_date", "m_open", "..."]
}
```

Dates are ISO `YYYY-MM-DD` strings parsed to `datetime.date`.

## Data flow

`kndc init json` → scaffolds `Config/` (JSON params + custom_calculations.py + JSON entry
script) → `kndc config-editor` → browser edits parameters, Save writes the JSON → `kndc run`
→ entry script constructs `JsonConfigurator` → `main()`. Everything downstream of the
`Configuration` object is unchanged.

## Error handling

- Configurator-level errors mirror `ExcelConfigurator`: raised as `ConfigurationError` /
  `ConfigurationHandlerError`, logged at critical, then `sys.exit()`.
- Server endpoints never crash the process: validation failures return HTTP `400` with a
  human-readable message; the editor surfaces it inline.

## Testing strategy (TDD, sequential; each step red → green before the next)

1. `_resolver` unit tests — provider resolution, missing/unavailable provider, API-key
   validation outcomes, output-handler selection, logger-level lookup, format-version gate.
2. `JsonConfigurator` unit tests — happy path builds the expected `Configuration`;
   equivalence with `ExcelConfigurator` for matching input; every error case enumerated above.
3. Column catalog — loads, is grouped by the expected prefixes, non-empty per group.
4. `config-editor` request handler — `GET /` returns the page; `GET /api/config` returns
   current/defaults; `POST /api/config` writes valid payloads and `400`s invalid ones;
   `GET /api/catalog` returns catalog + option lists. Driven against a loopback server on a
   throwaway port.
5. CLI — `init json` and `update json` scaffold the expected files; existing excel paths
   unaffected.

Fake providers/output handlers follow the existing patterns under
`tests/unit/data_providers/`.

## Scope guard / non-goals

- No changes to `main()`, `Configuration`, providers, output handlers, features, or modules.
- No refactor of `ExcelConfigurator` internals in this pass.
- No new runtime dependencies.
- The HTML app is a local parameter editor only — not a server, not networked, not a GUI for
  running the pipeline.

## Documentation

User-guide pages that reference the Excel config (`zero_coder.rst`, `quick_start.rst`,
`component_integrator.rst`) get follow-up updates to describe the JSON + editor path as the
default, with Excel noted as the legacy fallback. CHANGELOG entry added.
