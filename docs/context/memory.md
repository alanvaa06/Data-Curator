# Memory

Architectural decisions and durable context. One line per item.

- decision (2026-06-09): JSON config + local HTML editor (`config-editor` CLI) replaces Excel as the default configuration path; `ExcelConfigurator` kept as a deprecated, working fallback via the `ConfiguratorInterface` seam.
- decision (2026-06-09): shared post-parse logic for configurators lives in `config_handlers/_resolver.py`; `JsonConfigurator` uses it, `ExcelConfigurator` left untouched (follow-up: refactor Excel to delegate behind characterization tests).
- decision (2026-06-09): output column catalog is a bundled `config_handlers/column_catalog.json` (201 columns, 8 prefix groups), generated from the xlsx; single source of truth for the editor picker.
