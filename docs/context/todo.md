# Todo

Status: pending | in_progress | done

- [done] Replace Excel config with a lightweight HTML parameter editor (JSON + `config-editor` CLI). Branch `feat/html-config-editor`.
- [done] Seamless UX: single `start` command with in-panel "Save & run" (no separate init/editor/run commands needed).

## Follow-ups
- [pending] Refactor `ExcelConfigurator` to delegate its post-parse logic to `config_handlers/_resolver.py`, behind characterization tests, to remove duplication.
- [pending] Update remaining docs that reference the xlsx (`component_integrator.rst`, `custom_calculator.rst`, release notes) to mention the JSON + editor default.
- [done] Dev environment: stale non-editable install replaced with `pip install --user -e .`; CLI now reflects `src/`. Added package `__main__.py` so `python -m kaxanuk.data_curator` works regardless of PATH.
- [pending] PATH: `%APPDATA%\Python\Python314\Scripts` is not on PATH, so the bare `kaxanuk.data_curator` command needs either that dir added to PATH manually or the `python -m kaxanuk.data_curator` form.
- [pending] Panel run output: stream logs live (currently captured at process completion); consider line-buffered reads or SSE.
