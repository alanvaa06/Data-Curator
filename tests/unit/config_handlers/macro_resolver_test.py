import json

import pytest

from kaxanuk.data_curator import __parameters_format_version__
from kaxanuk.data_curator.config_handlers._resolver import (
    required_macro_providers,
    resolve_macro_requests,
)
from kaxanuk.data_curator.config_handlers.json_configurator import JsonConfigurator
from kaxanuk.data_curator.data_providers import MacroDataProviderInterface
from kaxanuk.data_curator.exceptions import ConfigurationError, DataProviderMissingKeyError


def test_routes_columns_to_providers():
    requests = resolve_macro_requests(
        ("m_close", "e_mx_target_rate", "e_us_cpi", "e_mx_inpc", "e_mx_unemployment")
    )
    assert ("e_mx_target_rate", "SF61745") in requests["banxico_sie"]
    # e_mx_inpc / e_mx_unemployment were re-sourced off INEGI (token lacks BIE access)
    # onto providers already working in the pipeline.
    assert ("e_mx_inpc", "SP1") in requests["banxico_sie"]
    assert ("e_us_cpi", "CPIAUCSL") in requests["fred"]
    assert ("e_mx_unemployment", "LRHUTTTTMXM156S") in requests["fred"]
    assert "inegi" not in requests  # no catalog column routes to INEGI any more
    assert "m_close" not in str(requests)


def test_required_providers_set():
    assert required_macro_providers(("e_us_cpi", "e_mx_target_rate")) == {"fred", "banxico_sie"}


def test_no_macro_columns_returns_empty():
    assert resolve_macro_requests(("m_open", "m_close")) == {}
    assert required_macro_providers(("m_open", "m_close")) == set()


def test_unknown_e_column_raises():
    with pytest.raises(ConfigurationError):
        resolve_macro_requests(("e_not_in_catalog",))


# --- JsonConfigurator-level macro wiring ---


class _FmpProvider:
    """Minimal equity market provider stand-in for the JSON config fixtures."""

    def __init__(self, api_key=None):
        self.api_key = api_key

    def get_dividend_data(self, *, main_identifier, start_date, end_date): ...
    def get_fundamental_data(self, *, main_identifier, period, start_date, end_date): ...
    def get_market_data(self, *, main_identifier, start_date, end_date): ...
    def get_split_data(self, *, main_identifier, start_date, end_date): ...
    def initialize(self, *, configuration): ...
    def validate_api_key(self):
        return None


class _FakeMacroProvider(MacroDataProviderInterface):
    """No-network macro provider whose key is always considered valid (None)."""

    macro_provider_name = "banxico_sie"

    def __init__(self, *, api_key=None):
        self._api_key = api_key

    def get_economic_data(self, *, series_ids, start_date, end_date):
        return {}

    def validate_api_key(self):
        return None


class _KeyDemandingMacroProvider(MacroDataProviderInterface):
    """Macro provider that requires an API key at construction time."""

    macro_provider_name = "banxico_sie"

    def __init__(self, *, api_key=None):
        if not api_key:
            raise DataProviderMissingKeyError
        self._api_key = api_key

    def get_economic_data(self, *, series_ids, start_date, end_date):
        return {}

    def validate_api_key(self):
        return True


def _base_config_dict():
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
        'identifiers': ['AAPL'],
        'columns': ['m_close', 'e_mx_target_rate'],
    }


def _equity_providers():
    return {'financial_modeling_prep': {'class': _FmpProvider, 'api_key': 'KEY'}}


def _handlers():
    return {'csv': object()}


def _write(tmp_path, data):
    path = tmp_path / 'data_curator_parameters.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return str(path)


def test_configurator_returns_macro_provider_for_selected_column(tmp_path):
    path = _write(tmp_path, _base_config_dict())
    configurator = JsonConfigurator(
        file_path=path,
        data_providers=_equity_providers(),
        output_handlers=_handlers(),
        macro_data_providers={
            'banxico_sie': {'class': _FakeMacroProvider, 'api_key': 'TOKEN'},
        },
    )
    providers = configurator.get_macro_data_providers()
    assert len(providers) == 1
    assert isinstance(providers[0], _FakeMacroProvider)


def test_configurator_no_macro_columns_returns_empty_list(tmp_path):
    data = _base_config_dict()
    data['columns'] = ['m_close']
    path = _write(tmp_path, data)
    configurator = JsonConfigurator(
        file_path=path,
        data_providers=_equity_providers(),
        output_handlers=_handlers(),
        macro_data_providers={
            'banxico_sie': {'class': _FakeMacroProvider, 'api_key': 'TOKEN'},
        },
    )
    assert configurator.get_macro_data_providers() == []


def test_configurator_missing_macro_provider_raises(tmp_path):
    path = _write(tmp_path, _base_config_dict())
    with pytest.raises(ConfigurationError):
        JsonConfigurator(
            file_path=path,
            data_providers=_equity_providers(),
            output_handlers=_handlers(),
            macro_data_providers={},
        )


def test_configurator_missing_macro_key_raises(tmp_path):
    path = _write(tmp_path, _base_config_dict())
    with pytest.raises(ConfigurationError):
        JsonConfigurator(
            file_path=path,
            data_providers=_equity_providers(),
            output_handlers=_handlers(),
            macro_data_providers={
                'banxico_sie': {'class': _KeyDemandingMacroProvider, 'api_key': None},
            },
        )
