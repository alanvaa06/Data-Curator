# Lessons

Patterns from corrections. One entry per lesson.

- 2026-06-09 — "didn't worked" after feature shipped: all verification ran through pytest (`pythonpath=["src"]`) and PYTHONPATH-injected smokes, so a stale non-editable site-packages install + missing Scripts dir on PATH silently shadowed every new command on the user's real shell.
  **Rule: before declaring CLI work done, run the exact documented command in a fresh shell the way the user would (installed entry point, no PYTHONPATH crutch). If the env is stale, fix the env (editable install) as part of the task — not as a "follow-up" note.**
- 2026-06-09 — `python -m package` execution is the PATH-proof fallback; ship a package `__main__.py` for any CLI so docs can offer it when the console script isn't resolvable.
- 2026-06-09 — "NOT WORKING" after a UI fix traced to two server bugs, not the UI: (1) the server cached the page at startup, so a long-running instance kept serving stale HTML across updates — read assets per request in dev-facing servers; (2) stdlib HTTPServer's SO_REUSEADDR lets two processes silently bind the same port on Windows — bind with SO_EXCLUSIVEADDRUSE there and surface 'port in use' clearly.
  **Rule: when a user reruns a long-lived local server across code updates, ask first: which process is actually serving, and which version is in its memory? Check the live process list and the served bytes, not the source files.**
- 2026-06-10 — "Output format duckdb has no registered output handler" on first real run: the new handler was registered in `templates/data_curator/__main__.py`, but runs execute the user's scaffolded workspace copy (repo-root `__main__.py`), which `start` deliberately never overwrites — so template changes silently don't reach existing workspaces.
  **Rule: when changing the entry-script template, also update every live workspace copy the user actually runs (repo root here), and smoke-test through the panel's real run path — not just the library tests. Registering a new handler/provider touches: handler module, `__init__`, template, workspace `__main__.py`, `OUTPUT_FORMATS`, docs.**
