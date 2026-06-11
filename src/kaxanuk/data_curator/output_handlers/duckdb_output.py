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
            Structure example:
            {
                'm_open': pyarrow.Array,
                'm_close': pyarrow.array,
                ....
            }

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
            self._ensure_table(connection)
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
    ) -> None:
        incoming_types = connection.execute(
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
            # upsert: restated (identifier, date) rows update in place, new dates append
            connection.execute(
                f'INSERT OR REPLACE INTO {table} BY NAME {select_incoming}',
                [main_identifier],
            )
        else:
            # no date column to key on: replace the identifier's rows wholesale
            connection.execute(
                f'DELETE FROM {table} '
                f'WHERE {self._quote_identifier(self.IDENTIFIER_COLUMN)} = ?',
                [main_identifier],
            )
            connection.execute(
                f'INSERT INTO {table} BY NAME {select_incoming}',
                [main_identifier],
            )
