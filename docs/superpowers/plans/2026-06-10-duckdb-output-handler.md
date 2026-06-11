# DuckDB Output Handler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `duckdb` output format that writes all identifiers into a single DuckDB database file with upsert semantics, enabling incremental updates (e.g., refresh only the most recent observations of a 10-year S&P 500 download) and cross-ticker SQL.

**Architecture:** New `DuckdbOutput` class implementing the existing `OutputHandlerInterface` (one `output_data(main_identifier, columns)` call per ticker, always from the main process — verified in `data_curator.py:_output_identifier_columns`, so no concurrent writes). All identifiers share one table `curated_data` keyed by `(main_identifier, m_date)`; re-runs upsert via `INSERT OR REPLACE`. Registered exactly like the CSV/Parquet handlers: template entry script dict + `OUTPUT_FORMATS` in the config editor.

**Tech Stack:** Python 3.12–3.14, duckdb >= 1.0 (1.5.3 verified installed on the dev env, Python 3.14.2), pyarrow Tables in (zero-copy `register`), pytest, ruff, mypy.

**Design decisions (from spec discussion):**
- Single DB file `{output_base_dir}/data_curator.duckdb` (name overridable via constructor), one table `curated_data` with a `main_identifier VARCHAR` column prepended.
- If incoming data has `m_date`: table is created with `PRIMARY KEY (main_identifier, m_date)` and writes use `INSERT OR REPLACE ... BY NAME` → restated values update in place, new dates append, history preserved.
- If no `m_date` (interface does not guarantee it): table without PK; writes `DELETE` the identifier's rows then `INSERT` (full replace per identifier — never silently duplicates).
- Schema evolution across runs with different column configs: new columns get `ALTER TABLE ADD COLUMN`; columns missing from incoming data are filled with NULL by `INSERT ... BY NAME`.
- Connection opened/closed per `output_data` call: no lingering file locks, ~500 calls is trivial overhead.
- duckdb errors wrapped in `OutputHandlerError` (existing exception, already used by `InMemoryOutput`).
- duckdb is a hard dependency (handlers are instantiated eagerly in the template entry script, so optional-extra lazy imports would complicate the default path).

**Files (whole plan):**
- Create: `src/kaxanuk/data_curator/output_handlers/duckdb_output.py`
- Modify: `src/kaxanuk/data_curator/output_handlers/__init__.py`
- Modify: `tests/unit/output_handlers/output_handlers_test.py`
- Modify: `templates/data_curator/__main__.py` (handler registration)
- Modify: `src/kaxanuk/data_curator/services/config_editor.py:36` (`OUTPUT_FORMATS`)
- Modify: `tests/unit/services/config_editor_test.py:133` (options assertion)
- Modify: `pyproject.toml` (dependency, ruff per-file-ignore, mypy override if needed)
- Modify: `docs/source/user_guide/zero_coder.rst:101`, `CHANGELOG.md`

---

### Task 1: duckdb dependency

**Files:**
- Modify: `pyproject.toml:21-30` (dependencies)

- [ ] **Step 1: Add duckdb to dependencies**

In `pyproject.toml`, in the `dependencies` list (alphabetical order, after `click`):

```toml
dependencies = [    # dev dependencies are in the [tool.pdm.dev-dependencies] section
    "click>=8.1.7",
    "duckdb>=1.0",
    "httpx>=0.27",
    ...
]
```

- [ ] **Step 2: Verify duckdb imports**

Run: `python -c "import duckdb; print(duckdb.__version__)"`
Expected: prints `1.5.3` (already pip-installed on this env; the pyproject entry covers fresh installs).

- [ ] **Step 3: Commit**

```powershell
git add pyproject.toml
git commit -m "build: add duckdb dependency for the DuckDB output handler"
```

---

### Task 2: DuckdbOutput — basic write path (TDD)

**Files:**
- Create: `src/kaxanuk/data_curator/output_handlers/duckdb_output.py`
- Modify: `src/kaxanuk/data_curator/output_handlers/__init__.py`
- Test: `tests/unit/output_handlers/output_handlers_test.py`

- [ ] **Step 1: Write failing tests**

In `tests/unit/output_handlers/output_handlers_test.py`, add `import duckdb` to the imports, add `DuckdbOutput` to the `from kaxanuk.data_curator.output_handlers import (...)` block, add `DuckdbOutput` to `test_all_handlers_implement_the_interface`:

```python
def test_all_handlers_implement_the_interface():
    assert issubclass(CsvOutput, OutputHandlerInterface)
    assert issubclass(DuckdbOutput, OutputHandlerInterface)
    assert issubclass(ParquetOutput, OutputHandlerInterface)
    assert issubclass(InMemoryOutput, OutputHandlerInterface)
```

and add this class (helper + 3 tests):

```python
def read_duckdb_rows(database_path, order_by='main_identifier, m_date'):
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        return connection.execute(
            f'SELECT * FROM curated_data ORDER BY {order_by}'  # noqa: S608
        ).fetchall()
    finally:
        connection.close()


class TestDuckdbOutput:
    def test_creates_database_file_in_missing_directory(self, tmp_path):
        nested_dir = tmp_path / 'deeply' / 'nested' / 'Output'
        handler = DuckdbOutput(output_base_dir=str(nested_dir))
        assert handler.output_data(main_identifier='AAPL', columns=sample_table()) is True
        assert (nested_dir / 'data_curator.duckdb').is_file()

    def test_written_rows_roundtrip_data(self, tmp_path):
        handler = DuckdbOutput(output_base_dir=str(tmp_path))
        handler.output_data(main_identifier='AAPL', columns=sample_table())
        rows = read_duckdb_rows(tmp_path / 'data_curator.duckdb')
        assert rows == [
            ('AAPL', datetime.date(2024, 1, 2), 187.15, 185.64),
            ('AAPL', datetime.date(2024, 1, 3), 184.22, 184.25),
        ]

    def test_multiple_identifiers_share_one_table(self, tmp_path):
        handler = DuckdbOutput(output_base_dir=str(tmp_path))
        handler.output_data(main_identifier='AAPL', columns=sample_table())
        handler.output_data(main_identifier='MSFT', columns=sample_table())
        rows = read_duckdb_rows(tmp_path / 'data_curator.duckdb')
        identifiers = {row[0] for row in rows}
        assert identifiers == {'AAPL', 'MSFT'}
        assert len(rows) == 4
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/unit/output_handlers/output_handlers_test.py -v`
Expected: `ImportError: cannot import name 'DuckdbOutput'`

- [ ] **Step 3: Minimal implementation**

Create `src/kaxanuk/data_curator/output_handlers/duckdb_output.py`:

```python
import pathlib

import duckdb
import pyarrow

from kaxanuk.data_curator.exceptions import OutputHandlerError
from kaxanuk.data_curator.output_handlers.output_handler_interface import OutputHandlerInterface


class DuckdbOutput(OutputHandlerInterface):
    """
    Appends the processed columns data to a single table in a DuckDB database file.

    All identifiers share the `curated_data` table, with a `main_identifier`
    column prepended to the output columns. When the data contains the
    `m_date` column, rows are upserted on (main_identifier, m_date): re-runs
    update restated values in place and append new dates without losing
    history. Without a date column, each identifier's rows are fully replaced
    on every run.

    Parameters
    ----------
    output_base_dir
        The path that will contain the database file
    database_file_name
        The name of the database file to create inside output_base_dir
    """

    DATE_COLUMN = 'm_date'
    IDENTIFIER_COLUMN = 'main_identifier'
    TABLE_NAME = 'curated_data'

    def __init__(
        self,
        *,
        output_base_dir: str,
        database_file_name: str = 'data_curator.duckdb',
    ):
        self.output_base_dir = output_base_dir
        self.database_file_name = database_file_name

    def output_data(
        self,
        *,
        main_identifier: str,
        columns: pyarrow.Table
    ) -> bool:
        """
        Upsert the identifier's processed data into the DuckDB database file.

        Parameters
        ----------
        main_identifier
            The identifier (ticker, etc.) of the data
        columns
            PyArrow Table containing all output columns.

        Returns
        -------
        bool

        Raises
        ------
        OutputHandlerError
            When the database rejects the write (e.g. incompatible schema).
        """
        (
            pathlib
                .Path(self.output_base_dir)
                .mkdir(parents=True, exist_ok=True)
        )
        database_path = f'{self.output_base_dir}/{self.database_file_name}'

        connection = duckdb.connect(database_path)
        try:
            connection.register('incoming_columns', columns)
            self._ensure_table(connection, columns)
            self._write_identifier_rows(connection, main_identifier)
        except duckdb.Error as error:
            msg = f"Failed writing {main_identifier} to DuckDB database {database_path}: {error}"

            raise OutputHandlerError(msg) from error
        finally:
            connection.close()

        return True

    @staticmethod
    def _quote_identifier(name: str) -> str:
        escaped = name.replace('"', '""')

        return f'"{escaped}"'

    def _ensure_table(
        self,
        connection: duckdb.DuckDBPyConnection,
        columns: pyarrow.Table,
    ) -> None:
        incoming_types: list[tuple] = connection.execute(
            'DESCRIBE SELECT * FROM incoming_columns'
        ).fetchall()

        column_definitions = ', '.join(
            f'{self._quote_identifier(name)} {column_type}'
            for (name, column_type, *_) in incoming_types
        )
        connection.execute(
            f'CREATE TABLE IF NOT EXISTS {self._quote_identifier(self.TABLE_NAME)} ('
            f'{self._quote_identifier(self.IDENTIFIER_COLUMN)} VARCHAR, '
            f'{column_definitions})'
        )

    def _write_identifier_rows(
        self,
        connection: duckdb.DuckDBPyConnection,
        main_identifier: str,
    ) -> None:
        table = self._quote_identifier(self.TABLE_NAME)
        connection.execute(
            f'INSERT INTO {table} BY NAME '
            f'SELECT ? AS {self._quote_identifier(self.IDENTIFIER_COLUMN)}, * '
            'FROM incoming_columns',
            [main_identifier],
        )
```

In `src/kaxanuk/data_curator/output_handlers/__init__.py` add to `__all__` (alphabetical) and import:

```python
__all__ = [
    'CsvOutput',
    'DuckdbOutput',
    'InMemoryOutput',
    'OutputHandlerInterface',
    'ParquetOutput',
]


# make these modules part of the public API of the base namespace
from kaxanuk.data_curator.output_handlers.output_handler_interface import OutputHandlerInterface
from kaxanuk.data_curator.output_handlers.csv_output import CsvOutput
from kaxanuk.data_curator.output_handlers.duckdb_output import DuckdbOutput
from kaxanuk.data_curator.output_handlers.in_memory_output import InMemoryOutput
from kaxanuk.data_curator.output_handlers.parquet_output import ParquetOutput
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `python -m pytest tests/unit/output_handlers/output_handlers_test.py -v`
Expected: all PASS (including the 3 new DuckDB tests).

- [ ] **Step 5: Ruff check (S608 expected)**

Run: `python -m ruff check src/kaxanuk/data_curator/output_handlers/duckdb_output.py`
If S608 (string-built SQL) fires: add a per-file-ignore in `pyproject.toml` under `[tool.ruff.lint.per-file-ignores]` (identifiers can't be bound parameters; all *values* are parameterized):

```toml
"src/kaxanuk/data_curator/output_handlers/duckdb_output.py" = [
    "S608",     # table/column names can't be bound parameters; all values use parameter binding
]
```

Re-run ruff. Expected: clean.

- [ ] **Step 6: Commit**

```powershell
git add src/kaxanuk/data_curator/output_handlers/duckdb_output.py src/kaxanuk/data_curator/output_handlers/__init__.py tests/unit/output_handlers/output_handlers_test.py pyproject.toml
git commit -m "feat: add DuckdbOutput handler writing all identifiers to one DuckDB table"
```

---

### Task 3: Upsert semantics — restatements and incremental appends (TDD)

**Files:**
- Modify: `src/kaxanuk/data_curator/output_handlers/duckdb_output.py`
- Test: `tests/unit/output_handlers/output_handlers_test.py`

- [ ] **Step 1: Write failing tests**

Add to `TestDuckdbOutput`:

```python
    def test_rerun_with_restated_values_updates_rows_without_duplicates(self, tmp_path):
        handler = DuckdbOutput(output_base_dir=str(tmp_path))
        handler.output_data(main_identifier='AAPL', columns=sample_table())
        restated = pyarrow.table({
            'm_date': [datetime.date(2024, 1, 3)],
            'm_open': [184.22],
            'm_close': [999.99],
        })
        handler.output_data(main_identifier='AAPL', columns=restated)
        rows = read_duckdb_rows(tmp_path / 'data_curator.duckdb')
        assert rows == [
            ('AAPL', datetime.date(2024, 1, 2), 187.15, 185.64),
            ('AAPL', datetime.date(2024, 1, 3), 184.22, 999.99),
        ]

    def test_new_dates_append_while_history_is_preserved(self, tmp_path):
        handler = DuckdbOutput(output_base_dir=str(tmp_path))
        handler.output_data(main_identifier='AAPL', columns=sample_table())
        new_day = pyarrow.table({
            'm_date': [datetime.date(2024, 1, 4)],
            'm_open': [184.35],
            'm_close': [181.91],
        })
        handler.output_data(main_identifier='AAPL', columns=new_day)
        rows = read_duckdb_rows(tmp_path / 'data_curator.duckdb')
        assert len(rows) == 3
        assert rows[2] == ('AAPL', datetime.date(2024, 1, 4), 184.35, 181.91)
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/unit/output_handlers/output_handlers_test.py::TestDuckdbOutput -v`
Expected: the restatement test FAILS with 3 rows instead of 2 (plain INSERT duplicates the 2024-01-03 row).

- [ ] **Step 3: Implement primary key + upsert**

In `duckdb_output.py`, replace `_ensure_table` and `_write_identifier_rows`:

```python
    def _ensure_table(
        self,
        connection: duckdb.DuckDBPyConnection,
        columns: pyarrow.Table,
    ) -> None:
        incoming_types: list[tuple] = connection.execute(
            'DESCRIBE SELECT * FROM incoming_columns'
        ).fetchall()

        column_definitions = ', '.join(
            f'{self._quote_identifier(name)} {column_type}'
            for (name, column_type, *_) in incoming_types
        )
        incoming_names = {name for (name, *_) in incoming_types}
        primary_key = (
            f', PRIMARY KEY ({self._quote_identifier(self.IDENTIFIER_COLUMN)}, '
            f'{self._quote_identifier(self.DATE_COLUMN)})'
            if self.DATE_COLUMN in incoming_names
            else ''
        )
        connection.execute(
            f'CREATE TABLE IF NOT EXISTS {self._quote_identifier(self.TABLE_NAME)} ('
            f'{self._quote_identifier(self.IDENTIFIER_COLUMN)} VARCHAR, '
            f'{column_definitions}{primary_key})'
        )

    def _table_has_primary_key(
        self,
        connection: duckdb.DuckDBPyConnection,
    ) -> bool:
        constraint = connection.execute(
            "SELECT 1 FROM duckdb_constraints() "
            "WHERE table_name = ? AND constraint_type = 'PRIMARY KEY'",
            [self.TABLE_NAME],
        ).fetchone()

        return constraint is not None

    def _write_identifier_rows(
        self,
        connection: duckdb.DuckDBPyConnection,
        main_identifier: str,
    ) -> None:
        table = self._quote_identifier(self.TABLE_NAME)
        select_incoming = (
            f'SELECT ? AS {self._quote_identifier(self.IDENTIFIER_COLUMN)}, * '
            'FROM incoming_columns'
        )
        if self._table_has_primary_key(connection):
            connection.execute(
                f'INSERT OR REPLACE INTO {table} BY NAME {select_incoming}',
                [main_identifier],
            )
        else:
            connection.execute(
                f'DELETE FROM {table} '
                f'WHERE {self._quote_identifier(self.IDENTIFIER_COLUMN)} = ?',
                [main_identifier],
            )
            connection.execute(
                f'INSERT INTO {table} BY NAME {select_incoming}',
                [main_identifier],
            )
```

(If `INSERT OR REPLACE ... BY NAME` is rejected by the installed duckdb version, fall back to `INSERT INTO ... BY NAME ... ON CONFLICT DO UPDATE` with explicit `SET` clauses built from the non-key incoming columns: `', '.join(f'{q(c)} = EXCLUDED.{q(c)}' for c in incoming_names - {IDENTIFIER_COLUMN, DATE_COLUMN})`.)

- [ ] **Step 4: Run tests, verify all pass**

Run: `python -m pytest tests/unit/output_handlers/output_handlers_test.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/kaxanuk/data_curator/output_handlers/duckdb_output.py tests/unit/output_handlers/output_handlers_test.py
git commit -m "feat: upsert on (main_identifier, m_date) for incremental DuckDB updates"
```

---

### Task 4: Dateless replace semantics + schema evolution (TDD)

**Files:**
- Modify: `src/kaxanuk/data_curator/output_handlers/duckdb_output.py`
- Test: `tests/unit/output_handlers/output_handlers_test.py`

- [ ] **Step 1: Write failing tests**

Add to `TestDuckdbOutput`:

```python
    def test_dateless_data_replaces_identifier_rows_on_rerun(self, tmp_path):
        handler = DuckdbOutput(output_base_dir=str(tmp_path))
        dateless = pyarrow.table({'m_open': [1.0, 2.0], 'm_close': [3.0, 4.0]})
        handler.output_data(main_identifier='AAPL', columns=dateless)
        handler.output_data(main_identifier='AAPL', columns=dateless)
        rows = read_duckdb_rows(tmp_path / 'data_curator.duckdb', order_by='m_open')
        assert len(rows) == 2

    def test_later_run_with_new_column_extends_schema(self, tmp_path):
        handler = DuckdbOutput(output_base_dir=str(tmp_path))
        handler.output_data(main_identifier='AAPL', columns=sample_table())
        extended = pyarrow.table({
            'm_date': [datetime.date(2024, 1, 4)],
            'm_open': [184.35],
            'm_close': [181.91],
            'c_returns': [0.012],
        })
        handler.output_data(main_identifier='AAPL', columns=extended)
        rows = read_duckdb_rows(tmp_path / 'data_curator.duckdb')
        assert len(rows) == 3
        # original rows get NULL for the new column, new row carries its value
        assert rows[0][3] is None
        assert rows[2][3] == 0.012
```

- [ ] **Step 2: Run tests, verify expected failures**

Run: `python -m pytest tests/unit/output_handlers/output_handlers_test.py::TestDuckdbOutput -v`
Expected: dateless test PASSES already (delete+insert path from Task 3); schema-evolution test FAILS with a duckdb binder error (`c_returns` column does not exist) surfaced as `OutputHandlerError`.

- [ ] **Step 3: Implement schema evolution**

In `_ensure_table`, after the `CREATE TABLE IF NOT EXISTS` statement, append:

```python
        existing_columns = {
            row[0]
            for row in connection.execute(
                'SELECT column_name FROM information_schema.columns '
                'WHERE table_name = ?',
                [self.TABLE_NAME],
            ).fetchall()
        }
        for (name, column_type, *_) in incoming_types:
            if name not in existing_columns:
                connection.execute(
                    f'ALTER TABLE {self._quote_identifier(self.TABLE_NAME)} '
                    f'ADD COLUMN {self._quote_identifier(name)} {column_type}'
                )
```

- [ ] **Step 4: Run tests, verify all pass**

Run: `python -m pytest tests/unit/output_handlers/output_handlers_test.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/kaxanuk/data_curator/output_handlers/duckdb_output.py tests/unit/output_handlers/output_handlers_test.py
git commit -m "feat: DuckDB schema evolution and dateless replace semantics"
```

---

### Task 5: Registration — template entry script and config editor (TDD)

**Files:**
- Modify: `templates/data_curator/__main__.py:69-76`
- Modify: `src/kaxanuk/data_curator/services/config_editor.py:36`
- Test: `tests/unit/services/config_editor_test.py:133`

- [ ] **Step 1: Write failing test**

In `tests/unit/services/config_editor_test.py`, extend the existing options assertion (around line 133):

```python
    assert 'csv' in response['options']['output_format']
    assert 'duckdb' in response['options']['output_format']
```

- [ ] **Step 2: Run test, verify it fails**

Run: `python -m pytest tests/unit/services/config_editor_test.py -v`
Expected: FAIL on the `'duckdb'` assertion.

- [ ] **Step 3: Register the format**

`src/kaxanuk/data_curator/services/config_editor.py:36`:

```python
OUTPUT_FORMATS = ('csv', 'duckdb', 'parquet')
```

`templates/data_curator/__main__.py` output_handlers dict:

```python
            output_handlers={
                'csv': kaxanuk.data_curator.output_handlers.CsvOutput(
                    output_base_dir=output_base_dir,
                ),
                'duckdb': kaxanuk.data_curator.output_handlers.DuckdbOutput(
                    output_base_dir=output_base_dir,
                ),
                'parquet': kaxanuk.data_curator.output_handlers.ParquetOutput(
                    output_base_dir=output_base_dir,
                ),
            },
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `python -m pytest tests/unit/services/config_editor_test.py tests/unit/output_handlers -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/kaxanuk/data_curator/services/config_editor.py templates/data_curator/__main__.py tests/unit/services/config_editor_test.py
git commit -m "feat: register duckdb output format in entry template and config editor"
```

---

### Task 6: Docs, full verification, context updates

**Files:**
- Modify: `docs/source/user_guide/zero_coder.rst:101`
- Modify: `CHANGELOG.md` (current unreleased/top section)
- Modify: `docs/context/todo.md`, `docs/context/results.md`, `docs/context/memory.md`, `docs/context/sesion-log.md`

- [ ] **Step 1: Update user guide**

`docs/source/user_guide/zero_coder.rst:101`:

```rst
- ``output_format``: choose between ``csv``, ``parquet`` or ``duckdb`` (single
  database file holding all identifiers in one ``curated_data`` table; re-runs
  update existing rows in place instead of rewriting files).
```

- [ ] **Step 2: Update CHANGELOG**

Read `CHANGELOG.md` heading structure; under the current unreleased section's `### Added` (create the subsection if absent, matching the file's existing style):

```markdown
- `duckdb` output format: all identifiers written to a single DuckDB database
  file (`data_curator.duckdb`, table `curated_data`) with upsert on
  `(main_identifier, m_date)`, enabling incremental refreshes of recent data
  without rewriting full history.
```

- [ ] **Step 3: Full test suite + lint + types**

Run: `python -m pytest tests -q`
Expected: all pass, no regressions.
Run: `python -m ruff check .`
Expected: clean.
Run: `python -m mypy`
Expected: clean; if `duckdb` lacks type info on this version, add to `pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = "duckdb.*"
ignore_missing_imports = true
```

- [ ] **Step 4: End-to-end smoke (handler through public API)**

Run a script that exercises the handler exactly as `data_curator.main` does (per-identifier calls through the package import path, no PYTHONPATH crutch — per lessons.md, fresh-shell realistic invocation):

```powershell
python -c "import datetime, pyarrow, duckdb; from kaxanuk.data_curator.output_handlers import DuckdbOutput; h = DuckdbOutput(output_base_dir='._smoke_duckdb'); t = pyarrow.table({'m_date': [datetime.date(2024,1,2)], 'm_close': [185.64]}); h.output_data(main_identifier='AAPL', columns=t); h.output_data(main_identifier='AAPL', columns=t); c = duckdb.connect('._smoke_duckdb/data_curator.duckdb'); print(c.execute('SELECT * FROM curated_data').fetchall()); c.close()"
```

Expected: exactly one row `[('AAPL', datetime.date(2024, 1, 2), 185.64)]` (upsert, no duplicate). Then remove `._smoke_duckdb`.

- [ ] **Step 5: Update context docs per CLAUDE.md**

- `docs/context/todo.md`: add `[done] DuckDB output handler: single-file DB, upsert on (main_identifier, m_date), registered as 'duckdb' format.`
- `docs/context/results.md`: 1–4 line review entry.
- `docs/context/memory.md`: `- decision (2026-06-10): 'duckdb' output format writes all identifiers to one curated_data table keyed (main_identifier, m_date) via INSERT OR REPLACE — incremental refreshes update in place; csv/parquet remain the interop formats.`
- `docs/context/sesion-log.md`: one-line session entry.

- [ ] **Step 6: Final commit**

```powershell
git add docs CHANGELOG.md
git commit -m "docs: document duckdb output format and log session"
```

---

## Self-Review

1. **Spec coverage:** single-file DB ✓ (Task 2), upsert/incremental ✓ (Task 3), restatement handling ✓ (Task 3 test), dateless fallback ✓ (Task 4), schema evolution ✓ (Task 4), registration template+editor ✓ (Task 5), dependency ✓ (Task 1), docs ✓ (Task 6). Fetch-side incremental (auto start-date from DB) explicitly out of scope — storage layer only, noted in spec discussion.
2. **Placeholders:** none — all steps carry full code and exact commands.
3. **Type consistency:** `DuckdbOutput(output_base_dir=..., database_file_name=...)`, constants `TABLE_NAME='curated_data'`, `IDENTIFIER_COLUMN='main_identifier'`, `DATE_COLUMN='m_date'` used consistently across tasks; helper names `_ensure_table`, `_write_identifier_rows`, `_table_has_primary_key`, `_quote_identifier` match between Tasks 2–4.
