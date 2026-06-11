import datetime
import decimal

import duckdb
import pandas
import pyarrow
import pyarrow.csv
import pyarrow.parquet
import pytest

from kaxanuk.data_curator.exceptions import OutputHandlerError
from kaxanuk.data_curator.output_handlers import (
    CsvOutput,
    DuckdbOutput,
    InMemoryOutput,
    OutputHandlerInterface,
    ParquetOutput,
)


def sample_table():
    return pyarrow.table({
        'm_date': [datetime.date(2024, 1, 2), datetime.date(2024, 1, 3)],
        'm_open': [187.15, 184.22],
        'm_close': [185.64, 184.25],
    })


class TestCsvOutput:
    def test_writes_file_named_after_identifier(self, tmp_path):
        handler = CsvOutput(output_base_dir=str(tmp_path))
        assert handler.output_data(main_identifier='AAPL', columns=sample_table()) is True
        assert (tmp_path / 'AAPL.csv').is_file()

    def test_written_file_roundtrips_data(self, tmp_path):
        handler = CsvOutput(output_base_dir=str(tmp_path))
        table = sample_table()
        handler.output_data(main_identifier='AAPL', columns=table)
        written = pyarrow.csv.read_csv(tmp_path / 'AAPL.csv')
        assert written.column_names == table.column_names
        assert written.num_rows == table.num_rows
        assert written.column('m_close').to_pylist() == table.column('m_close').to_pylist()

    def test_creates_missing_output_directory(self, tmp_path):
        nested_dir = tmp_path / 'deeply' / 'nested' / 'Output'
        handler = CsvOutput(output_base_dir=str(nested_dir))
        assert handler.output_data(main_identifier='MSFT', columns=sample_table()) is True
        assert (nested_dir / 'MSFT.csv').is_file()


class TestParquetOutput:
    def test_writes_file_named_after_identifier(self, tmp_path):
        handler = ParquetOutput(output_base_dir=str(tmp_path))
        assert handler.output_data(main_identifier='AAPL', columns=sample_table()) is True
        assert (tmp_path / 'AAPL.parquet').is_file()

    def test_written_file_roundtrips_data(self, tmp_path):
        handler = ParquetOutput(output_base_dir=str(tmp_path))
        table = sample_table()
        handler.output_data(main_identifier='AAPL', columns=table)
        written = pyarrow.parquet.read_table(tmp_path / 'AAPL.parquet')
        assert written.equals(table)

    def test_creates_missing_output_directory(self, tmp_path):
        nested_dir = tmp_path / 'deeply' / 'nested' / 'Output'
        handler = ParquetOutput(output_base_dir=str(nested_dir))
        assert handler.output_data(main_identifier='MSFT', columns=sample_table()) is True
        assert (nested_dir / 'MSFT.parquet').is_file()


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

    def test_dateless_data_replaces_identifier_rows_on_rerun(self, tmp_path):
        handler = DuckdbOutput(output_base_dir=str(tmp_path))
        dateless = pyarrow.table({'m_open': [1.0, 2.0], 'm_close': [3.0, 4.0]})
        handler.output_data(main_identifier='AAPL', columns=dateless)
        handler.output_data(main_identifier='AAPL', columns=dateless)
        rows = read_duckdb_rows(tmp_path / 'data_curator.duckdb', order_by='m_open')
        assert len(rows) == 2

    def test_wider_decimal_values_in_later_write_promote_column_type(self, tmp_path):
        # first ticker all-zero decimals infer DECIMAL(1,0); later real values must still fit
        handler = DuckdbOutput(output_base_dir=str(tmp_path))
        narrow = pyarrow.table({
            'm_date': [datetime.date(2024, 1, 2)],
            'fcf_fx_effect': pyarrow.array([decimal.Decimal('0')]),
        })
        handler.output_data(main_identifier='AAPL', columns=narrow)
        wide = pyarrow.table({
            'm_date': [datetime.date(2024, 1, 2)],
            'fcf_fx_effect': pyarrow.array([decimal.Decimal('104773000')]),
        })
        handler.output_data(main_identifier='ABNB', columns=wide)
        rows = read_duckdb_rows(tmp_path / 'data_curator.duckdb')
        assert rows[0][2] == decimal.Decimal('0')
        assert rows[1][2] == decimal.Decimal('104773000')

    def test_all_null_column_in_first_write_accepts_values_later(self, tmp_path):
        handler = DuckdbOutput(output_base_dir=str(tmp_path))
        nulls = pyarrow.table({
            'm_date': [datetime.date(2024, 1, 2)],
            'c_metric': pyarrow.array([None], type=pyarrow.null()),
        })
        handler.output_data(main_identifier='AAPL', columns=nulls)
        values = pyarrow.table({
            'm_date': [datetime.date(2024, 1, 2)],
            'c_metric': [1234567890.5],
        })
        handler.output_data(main_identifier='ABNB', columns=values)
        rows = read_duckdb_rows(tmp_path / 'data_curator.duckdb')
        assert rows[0][2] is None
        assert rows[1][2] == 1234567890.5

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
        assert rows[0][4] is None
        assert rows[2][4] == 0.012


class TestInMemoryOutput:
    def test_stores_table_per_identifier(self):
        handler = InMemoryOutput()
        table = sample_table()
        assert handler.output_data(main_identifier='AAPL', columns=table) is True
        assert handler.data['AAPL'] is table

    def test_export_dataframe_combines_identifiers_with_multiindex(self):
        handler = InMemoryOutput()
        handler.output_data(main_identifier='AAPL', columns=sample_table())
        handler.output_data(main_identifier='MSFT', columns=sample_table())
        dataframe = handler.export_dataframe()
        assert isinstance(dataframe, pandas.DataFrame)
        assert dataframe.index.names == ['main_identifier', 'm_date']
        assert set(dataframe.index.get_level_values('main_identifier')) == {'AAPL', 'MSFT'}
        assert len(dataframe) == 4

    def test_export_dataframe_without_data_raises(self):
        handler = InMemoryOutput()
        with pytest.raises(OutputHandlerError, match='No data'):
            handler.export_dataframe()

    def test_export_dataframe_without_date_column_raises(self):
        handler = InMemoryOutput()
        dateless_table = pyarrow.table({'m_open': [1.0], 'm_close': [2.0]})
        handler.output_data(main_identifier='AAPL', columns=dateless_table)
        with pytest.raises(OutputHandlerError, match='m_date'):
            handler.export_dataframe()


def test_all_handlers_implement_the_interface():
    assert issubclass(CsvOutput, OutputHandlerInterface)
    assert issubclass(DuckdbOutput, OutputHandlerInterface)
    assert issubclass(ParquetOutput, OutputHandlerInterface)
    assert issubclass(InMemoryOutput, OutputHandlerInterface)
