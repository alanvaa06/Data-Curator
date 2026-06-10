# Todo

Status: pending | in_progress | done

- [done] Replace Excel config with a lightweight HTML parameter editor (JSON + `config-editor` CLI). Branch `feat/html-config-editor`.

## Follow-ups
- [pending] Refactor `ExcelConfigurator` to delegate its post-parse logic to `config_handlers/_resolver.py`, behind characterization tests, to remove duplication.
- [pending] Update remaining docs that reference the xlsx (`component_integrator.rst`, `custom_calculator.rst`, release notes) to mention the JSON + editor default.
- [pending] Dev environment: the active interpreter loads a stale non-editable install from Python 3.14 site-packages; reinstall editable (`pdm run install_dev`) so the CLI reflects `src/` outside pytest.
