import datetime
import json
import logging

import pytest

from kaxanuk.data_curator import __parameters_format_version__
from kaxanuk.data_curator.config_handlers.json_configurator import JsonConfigurator
from kaxanuk.data_curator.data_providers import DataProviderInterface
from kaxanuk.data_curator.entities import Configuration
from kaxanuk.data_curator.exceptions import (
    ConfigurationError,
    ConfigurationHandlerError,
    DataCuratorError,
)


class FakeProvider(DataProviderInterface):
    def __init__(self, api_key=None):
        self.api_key = api_key

    def get_dividend_data(self, *, main_identifier, start_date, end_date): ...
    def get_fundamental_data(self, *, main_identifier, period, start_date, end_date): ...
    def get_market_data(self, *, main_identifier, start_date, end_date): ...
    def get_split_data(self, *, main_identifier, start_date, end_date): ...
    def initialize(self, *, configuration): ...
    def validate_api_key(self):
        return None


def valid_config_dict():
    return {
        'parameters_format_version': __parameters_format_version__,
        'general': {
            'market_data_provider': 'financial_modeling_prep',
            'fundamental_data_provider': 'none',
            'start_date': '1990-01-01',
            'end_date': '2025-12-31',
            'period': 'quarterly',
            'output_format': 'csv',
            'logger_level': 'info',
        },
        'identifiers': ['AAPL', 'MSFT'],
        'columns': ['m_date', 'm_open', 'm_close'],
    }


def providers():
    return {
        'financial_modeling_prep': {'class': FakeProvider, 'api_key': 'KEY'},
    }


CSV_HANDLER = object()
PARQUET_HANDLER = object()


def handlers():
    return {'csv': CSV_HANDLER, 'parquet': PARQUET_HANDLER}


def write_config(tmp_path, data):
    path = tmp_path / 'data_curator_parameters.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return str(path)


def build(tmp_path, data):
    path = write_config(tmp_path, data)
    return lambda: JsonConfigurator(
        file_path=path,
        data_providers=providers(),
        output_handlers=handlers(),
    )


def test_builds_expected_configuration(tmp_path):
    path = write_config(tmp_path, valid_config_dict())
    configurator = JsonConfigurator(
        file_path=path,
        data_providers=providers(),
        output_handlers=handlers(),
    )
    config = configurator.get_configuration()
    assert isinstance(config, Configuration)
    assert config.start_date == datetime.date(1990, 1, 1)
    assert config.end_date == datetime.date(2025, 12, 31)
    assert config.period == 'quarterly'
    assert config.identifiers == ('AAPL', 'MSFT')
    assert config.columns == ('m_date', 'm_open', 'm_close')


def test_getters_return_selected_dependencies(tmp_path):
    path = write_config(tmp_path, valid_config_dict())
    configurator = JsonConfigurator(
        file_path=path,
        data_providers=providers(),
        output_handlers=handlers(),
    )
    assert isinstance(configurator.get_market_data_provider(), FakeProvider)
    assert configurator.get_fundamental_data_provider() is None
    assert configurator.get_output_handler() is CSV_HANDLER
    assert configurator.get_logger_level() == logging.INFO


def test_missing_file_raises(tmp_path):
    def make():
        return JsonConfigurator(
            file_path=str(tmp_path / 'nope.json'),
            data_providers=providers(),
            output_handlers=handlers(),
        )

    with pytest.raises(ConfigurationHandlerError, match='not found'):
        make()


def test_missing_api_key_raises_with_clear_error(tmp_path, capsys):
    from kaxanuk.data_curator.exceptions import DataProviderMissingKeyError

    class KeyDemandingProvider(FakeProvider):
        def __init__(self, api_key=None):
            if api_key is None:
                raise DataProviderMissingKeyError
            super().__init__(api_key)

    path = write_config(tmp_path, valid_config_dict())
    with pytest.raises(DataCuratorError):
        JsonConfigurator(
            file_path=path,
            data_providers={'financial_modeling_prep': {'class': KeyDemandingProvider, 'api_key': None}},
            output_handlers=handlers(),
        )
    captured = capsys.readouterr()
    assert 'API key' in captured.err + captured.out


def test_invalid_json_raises(tmp_path):
    path = tmp_path / 'data_curator_parameters.json'
    path.write_text('{not valid json', encoding='utf-8')
    with pytest.raises(ConfigurationHandlerError, match='Invalid JSON'):
        JsonConfigurator(
            file_path=str(path),
            data_providers=providers(),
            output_handlers=handlers(),
        )


def test_missing_general_key_raises(tmp_path):
    data = valid_config_dict()
    del data['general']['period']
    with pytest.raises(ConfigurationHandlerError, match='period'):
        build(tmp_path, data)()


def test_stale_format_version_raises(tmp_path):
    data = valid_config_dict()
    data['parameters_format_version'] = '0.0.1'
    with pytest.raises(DataCuratorError):
        build(tmp_path, data)()


def test_unknown_market_provider_raises(tmp_path):
    data = valid_config_dict()
    data['general']['market_data_provider'] = 'made_up'
    with pytest.raises(DataCuratorError):
        build(tmp_path, data)()


def test_invalid_logger_level_raises(tmp_path):
    data = valid_config_dict()
    data['general']['logger_level'] = 'verbose'
    with pytest.raises(DataCuratorError):
        build(tmp_path, data)()


def test_invalid_date_raises(tmp_path):
    data = valid_config_dict()
    data['general']['start_date'] = '01/01/1990'
    with pytest.raises(ConfigurationError, match='start_date'):
        build(tmp_path, data)()


def test_bad_column_prefix_raises(tmp_path):
    data = valid_config_dict()
    data['columns'] = ['not_a_valid_column']
    with pytest.raises(DataCuratorError):
        build(tmp_path, data)()


def test_macro_only_run_skips_equity_provider_and_key(tmp_path):
    # A run with no identifiers is a standalone macro export: the equity providers are never
    # used, so the configurator must not construct or validate them (which would otherwise
    # require an equity provider API key a macro-only run has no reason to supply).
    from kaxanuk.data_curator.exceptions import DataProviderMissingKeyError

    class KeyDemandingProvider(FakeProvider):
        def __init__(self, api_key=None):
            if api_key is None:
                raise DataProviderMissingKeyError
            super().__init__(api_key)

    data = valid_config_dict()
    data['identifiers'] = []
    data['columns'] = ['m_close']
    path = write_config(tmp_path, data)

    configurator = JsonConfigurator(
        file_path=path,
        data_providers={'financial_modeling_prep': {'class': KeyDemandingProvider, 'api_key': None}},
        output_handlers=handlers(),
    )

    assert configurator.get_market_data_provider() is None
    assert configurator.get_fundamental_data_provider() is None
    assert configurator.get_configuration().identifiers == ()
