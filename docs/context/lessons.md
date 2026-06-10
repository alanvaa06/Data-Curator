# Lessons

Patterns from corrections. One entry per lesson.

- 2026-06-09 — "didn't worked" after feature shipped: all verification ran through pytest (`pythonpath=["src"]`) and PYTHONPATH-injected smokes, so a stale non-editable site-packages install + missing Scripts dir on PATH silently shadowed every new command on the user's real shell.
  **Rule: before declaring CLI work done, run the exact documented command in a fresh shell the way the user would (installed entry point, no PYTHONPATH crutch). If the env is stale, fix the env (editable install) as part of the task — not as a "follow-up" note.**
- 2026-06-09 — `python -m package` execution is the PATH-proof fallback; ship a package `__main__.py` for any CLI so docs can offer it when the console script isn't resolvable.
