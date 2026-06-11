# Memory

Architectural decisions and durable context. One line per item.

- decision (2026-06-09): JSON config + local HTML editor (`config-editor` CLI) replaces Excel as the default configuration path; `ExcelConfigurator` kept as a deprecated, working fallback via the `ConfiguratorInterface` seam.
- decision (2026-06-09): shared post-parse logic for configurators lives in `config_handlers/_resolver.py`; `JsonConfigurator` uses it, `ExcelConfigurator` left untouched (follow-up: refactor Excel to delegate behind characterization tests).
- decision (2026-06-09): output column catalog is a bundled `config_handlers/column_catalog.json` (201 columns, 8 prefix groups), generated from the xlsx; single source of truth for the editor picker.
- decision (2026-06-09): `start` is the single user-facing command — non-destructive workspace scaffold + panel + in-panel "Save & run" (`POST/GET /api/run`, background thread, output captured at completion); `init json`/`config-editor`/`run` remain as granular commands.
- decision (2026-06-10): repo is now a private standalone at github.com/alanvaa06/Data-Curator (fork deleted, no KaxaNuk remote); MIT license retained.
- decision (2026-06-10): Excel configuration fully removed (ExcelConfigurator, autorun, init/update excel, xlsx template, panel import-excel, openpyxl dep) — JSON + panel is the only config path; templates/__main__.py is the JSON entry script.
- decision (2026-06-10): configurators raise (ConfigurationError/ConfigurationHandlerError) instead of sys.exit; entry-script template catches DataCuratorError and exits 1.
- decision (2026-06-10): mypy is a blocking CI step; legacy modules (~1200 errors, mostly fmp/lseg god-modules) baselined via ignore_errors overrides in pyproject — ratchet down over time.
