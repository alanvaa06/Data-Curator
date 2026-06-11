import datetime

import pandas
import pyarrow
import pyarrow.csv
import pyarrow.parquet
import pytest

from kaxanuk.data_curator.exceptions import OutputHandlerError
from kaxanuk.data_curator.output_handlers import (
    CsvOutput,
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
    assert issubclass(ParquetOutput, OutputHandlerInterface)
    assert issubclass(InMemoryOutput, OutputHandlerInterface)
