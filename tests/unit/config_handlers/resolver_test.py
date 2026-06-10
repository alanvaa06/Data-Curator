import logging

import pytest

from kaxanuk.data_curator.config_handlers import _resolver
from kaxanuk.data_curator.data_providers import (
    DataProviderInterface,
    NotFoundDataProvider,
)
from kaxanuk.data_curator.exceptions import (
    ConfigurationError,
    ConfigurationHandlerError,
)


class TestGetLoggerLevel:
    def test_known_level_returns_logging_constant(self):
        assert _resolver.get_logger_level('info') == logging.INFO
        assert _resolver.get_logger_level('debug') == logging.DEBUG

    def test_unknown_level_raises(self):
        with pytest.raises(ConfigurationHandlerError):
            _resolver.get_logger_level('verbose')


class TestCheckParametersFormatVersion:
    def test_current_version_passes(self):
        from kaxanuk.data_curator import __parameters_format_version__
        _resolver.check_parameters_format_version(__parameters_format_version__)

    def test_empty_version_raises(self):
        with pytest.raises(ConfigurationHandlerError):
            _resolver.check_parameters_format_version('')

    def test_older_version_raises(self):
        with pytest.raises(ConfigurationHandlerError):
            _resolver.check_parameters_format_version('0.0.1')


class _FakeProvider(DataProviderInterface):
    def __init__(self, api_key=None, *, api_key_valid=True):
        self.api_key = api_key
        self._api_key_valid = api_key_valid

    def get_dividend_data(self, *, main_identifier, start_date, end_date): ...
    def get_fundamental_data(self, *, main_identifier, period, start_date, end_date): ...
    def get_market_data(self, *, main_identifier, start_date, end_date): ...
    def get_split_data(self, *, main_identifier, start_date, end_date): ...
    def initialize(self, *, configuration): ...
    def validate_api_key(self):
        return self._api_key_valid


def _providers():
    return {
        'financial_modeling_prep': {'class': _FakeProvider, 'api_key': 'KEY'},
        'yahoo_finance': {'class': _FakeProvider, 'api_key': None},
    }


class TestSelectMarketDataProvider:
    def test_returns_instance_for_known_provider(self):
        provider = _resolver.select_market_data_provider('yahoo_finance', _providers())
        assert isinstance(provider, _FakeProvider)

    def test_passes_api_key_when_present(self):
        provider = _resolver.select_market_data_provider('financial_modeling_prep', _providers())
        assert provider.api_key == 'KEY'

    def test_unknown_provider_raises(self):
        with pytest.raises(ConfigurationError):
            _resolver.select_market_data_provider('made_up', _providers())

    def test_not_found_provider_raises(self):
        providers = {'ghost': {'class': NotFoundDataProvider, 'api_key': None}}
        with pytest.raises(ConfigurationError):
            _resolver.select_market_data_provider('ghost', providers)


class TestSelectFundamentalDataProvider:
    def test_none_keyword_returns_none(self):
        assert _resolver.select_fundamental_data_provider('none', _providers()) is None

    def test_returns_instance_for_known_provider(self):
        provider = _resolver.select_fundamental_data_provider('financial_modeling_prep', _providers())
        assert isinstance(provider, _FakeProvider)

    def test_unknown_provider_raises(self):
        with pytest.raises(ConfigurationError):
            _resolver.select_fundamental_data_provider('made_up', _providers())


class TestValidateApiKeys:
    def test_invalid_key_raises(self):
        bad = _FakeProvider(api_key_valid=False)
        with pytest.raises(ConfigurationError):
            _resolver.validate_api_keys({'Bad': bad}, logging.getLogger('test'))

    def test_valid_and_none_keys_pass(self):
        good = _FakeProvider(api_key_valid=True)
        skip = _FakeProvider(api_key_valid=None)
        _resolver.validate_api_keys({'Good': good, 'Skip': skip}, logging.getLogger('test'))


class TestSelectOutputHandler:
    def test_returns_selected_handler(self):
        handlers = {'csv': object(), 'parquet': object()}
        assert _resolver.select_output_handler('csv', handlers) is handlers['csv']

    def test_unknown_handler_raises(self):
        with pytest.raises(ConfigurationError):
            _resolver.select_output_handler('xml', {'csv': object()})
