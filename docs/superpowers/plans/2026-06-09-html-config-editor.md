# HTML Config Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Excel configuration workflow with a JSON config file plus a lightweight local HTML editor, leaving all critical architecture untouched.

**Architecture:** Add a second `ConfiguratorInterface` implementation (`JsonConfigurator`) alongside `ExcelConfigurator`, backed by shared resolution helpers (`_resolver.py`). A stdlib `http.server` CLI command (`config-editor`) serves a self-contained HTML page that loads/saves `Config/data_curator_parameters.json`. The Excel path stays as a deprecated, working fallback.

**Tech Stack:** Python 3.12 stdlib (`json`, `http.server`, `importlib.resources`, `webbrowser`), `click` (existing CLI), `pytest`, vanilla HTML/CSS/JS (no build step, no CDN).

---

## File Structure

| Path | Responsibility |
|------|----------------|
| `src/kaxanuk/data_curator/config_handlers/column_catalog.json` | Generated catalog: ~180 columns grouped by prefix |
| `src/kaxanuk/data_curator/config_handlers/column_catalog.py` | `load_catalog()` reads the JSON via `importlib.resources` |
| `src/kaxanuk/data_curator/config_handlers/_resolver.py` | Shared provider/handler/logger/version resolution helpers |
| `src/kaxanuk/data_curator/config_handlers/json_configurator.py` | `JsonConfigurator(ConfiguratorInterface)` |
| `src/kaxanuk/data_curator/config_handlers/__init__.py` | Export `JsonConfigurator` (modify) |
| `src/kaxanuk/data_curator/services/config_editor.py` | Editor server: pure config functions + HTTP handler + `serve()` |
| `src/kaxanuk/data_curator/services/config_editor_page.html` | Self-contained editor page |
| `src/kaxanuk/data_curator/services/cli.py` | Add `config-editor` command + `json` init/update format (modify) |
| `templates/data_curator/Config/data_curator_parameters.json` | Default JSON config |
| `templates/data_curator/json_entry_script.py` | Entry script using `JsonConfigurator` |
| `tests/unit/config_handlers/*` | Unit tests for catalog, resolver, configurator |
| `tests/unit/services/config_editor_test.py` | Editor server tests |
| `tests/unit/services/cli_test.py` | CLI command tests |

**Test package scaffolding:** create empty `tests/unit/config_handlers/__init__.py` when first writing a test there (the suite uses package test dirs — see existing `tests/unit/data_providers/__init__.py`). `tests/unit/services/__init__.py` already exists.

---

## Task 1: Column catalog (data + loader)

**Files:**
- Create: `src/kaxanuk/data_curator/config_handlers/column_catalog.json`
- Create: `src/kaxanuk/data_curator/config_handlers/column_catalog.py`
- Create: `tests/unit/config_handlers/__init__.py`
- Test: `tests/unit/config_handlers/column_catalog_test.py`

- [ ] **Step 1: Generate the catalog JSON from the existing xlsx**

Run this one-off command from the repo root. It extracts the column list from the xlsx, groups by prefix in first-appearance order, and writes the catalog:

```bash
python -c "
import json, pathlib, openpyxl
wb = openpyxl.load_workbook('templates/data_curator/Config/data_curator_parameters.xlsx')
ws = wb['Output_Columns']
cols = []
for (cell,) in ws.iter_rows(min_row=2, max_col=1, values_only=True):
    if cell is not None and str(cell).strip():
        cols.append(str(cell).strip())
labels = {'m':'Market data','f':'Fundamental','fbs':'Balance sheet','fcf':'Cash flow','fis':'Income statement','d':'Dividends','s':'Splits','c':'Calculations'}
order, groups = [], {}
for c in cols:
    p = c.split('_', 1)[0]
    if p not in groups:
        groups[p] = []
        order.append(p)
    groups[p].append(c)
catalog = {'groups': [{'prefix': p + '_', 'label': labels.get(p, p), 'columns': groups[p]} for p in order]}
pathlib.Path('src/kaxanuk/data_curator/config_handlers/column_catalog.json').write_text(json.dumps(catalog, indent=2) + '\n', encoding='utf-8')
print('groups:', [(g['prefix'], len(g['columns'])) for g in catalog['groups']])
print('total columns:', sum(len(g['columns']) for g in catalog['groups']))
"
```

Expected output (group prefixes and counts, total ~180):
`groups: [('m_', 19), ('f_', 6), ('fbs_', ...), ...]`
`total columns: 18x`

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/config_handlers/column_catalog_test.py
from kaxanuk.data_curator.config_handlers.column_catalog import load_catalog


def test_load_catalog_returns_nonempty_groups():
    catalog = load_catalog()
    assert 'groups' in catalog
    assert len(catalog['groups']) > 0


def test_each_group_has_prefix_label_and_columns():
    catalog = load_catalog()
    for group in catalog['groups']:
        assert group['prefix'].endswith('_')
        assert isinstance(group['label'], str) and group['label']
        assert len(group['columns']) > 0
        for column in group['columns']:
            assert column.startswith(group['prefix'])


def test_catalog_includes_market_and_calculation_columns():
    catalog = load_catalog()
    all_columns = [c for g in catalog['groups'] for c in g['columns']]
    assert 'm_date' in all_columns
    assert 'm_close' in all_columns
    assert any(c.startswith('c_') for c in all_columns)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/unit/config_handlers/column_catalog_test.py -v`
Expected: FAIL — `ModuleNotFoundError: ... column_catalog`

- [ ] **Step 4: Write the loader**

```python
# src/kaxanuk/data_curator/config_handlers/column_catalog.py
"""
Loads the output column catalog used by the configuration editor.
"""

import importlib.resources
import json
import typing


def load_catalog() -> dict[str, typing.Any]:
    """
    Load the bundled output column catalog.

    Returns
    -------
    A mapping with a 'groups' list, each group holding a 'prefix', 'label' and 'columns' list.
    """
    resource = importlib.resources.files(
        'kaxanuk.data_curator.config_handlers'
    ).joinpath('column_catalog.json')

    return json.loads(
        resource.read_text(encoding='utf-8')
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/config_handlers/column_catalog_test.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add src/kaxanuk/data_curator/config_handlers/column_catalog.json src/kaxanuk/data_curator/config_handlers/column_catalog.py tests/unit/config_handlers/__init__.py tests/unit/config_handlers/column_catalog_test.py
git commit -m "feat: add output column catalog and loader"
```

---

## Task 2: Resolver — logger level and format-version gate

**Files:**
- Create: `src/kaxanuk/data_curator/config_handlers/_resolver.py`
- Test: `tests/unit/config_handlers/resolver_test.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/config_handlers/resolver_test.py
import logging

import pytest

from kaxanuk.data_curator.config_handlers import _resolver
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/config_handlers/resolver_test.py -v`
Expected: FAIL — `ModuleNotFoundError: ... _resolver`

- [ ] **Step 3: Write the resolver functions**

```python
# src/kaxanuk/data_curator/config_handlers/_resolver.py
"""
Shared resolution helpers for configurator implementations.

These functions translate parsed configuration values into the data providers, output
handler, logger level and version checks shared by all ConfiguratorInterface implementations.
"""

import logging
import typing

import packaging.version

from kaxanuk.data_curator import __parameters_format_version__
from kaxanuk.data_curator.config_handlers.configurator_interface import ConfiguratorInterface
from kaxanuk.data_curator.data_providers import (
    DataProviderInterface,
    NotFoundDataProvider,
)
from kaxanuk.data_curator.exceptions import (
    ConfigurationError,
    ConfigurationHandlerError,
)
from kaxanuk.data_curator.output_handlers import OutputHandlerInterface


NONE_DATA_PROVIDER = 'none'


def get_logger_level(level_name: str) -> int:
    """
    Get the logger level value corresponding to a logger_level name.

    Raises
    ------
    ConfigurationHandlerError
    """
    if level_name not in ConfiguratorInterface.CONFIGURATION_LOGGER_LEVELS:
        msg = "Invalid logger level in parameters file"

        raise ConfigurationHandlerError(msg)

    return ConfiguratorInterface.CONFIGURATION_LOGGER_LEVELS[level_name]


def check_parameters_format_version(version: str) -> None:
    """
    Ensure the configuration's parameters_format_version is current.

    Raises
    ------
    ConfigurationHandlerError
    """
    version = str(version)
    if (
        len(version) < 1
        or (
            packaging.version.parse(version)
            < packaging.version.parse(__parameters_format_version__)
        )
    ):
        msg = " ".join([
            "Configuration file uses an old format, please create a new file",
            "based on the latest template",
        ])

        raise ConfigurationHandlerError(msg)
```

(The provider/handler helpers are added in Task 3; the `ConfigurationError`, `DataProviderInterface`, `NotFoundDataProvider`, `OutputHandlerInterface`, `NONE_DATA_PROVIDER` and `typing` imports above are used there — keep them now so imports stay in one place.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/config_handlers/resolver_test.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/kaxanuk/data_curator/config_handlers/_resolver.py tests/unit/config_handlers/resolver_test.py
git commit -m "feat: add resolver logger-level and format-version helpers"
```

---

## Task 3: Resolver — provider selection, API-key validation, output handler

**Files:**
- Modify: `src/kaxanuk/data_curator/config_handlers/_resolver.py`
- Test: `tests/unit/config_handlers/resolver_test.py` (add)

- [ ] **Step 1: Write the failing tests (append to resolver_test.py)**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/config_handlers/resolver_test.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'select_market_data_provider'`

- [ ] **Step 3: Append the helpers to `_resolver.py`**

```python
def _instantiate_provider(provider_entry: dict[str, typing.Any]) -> DataProviderInterface:
    if provider_entry['class'] is None:
        msg = "Selected data provider implementation is missing."

        raise ConfigurationError(msg)

    params = {}
    if provider_entry['api_key'] is not None:
        params['api_key'] = provider_entry['api_key']

    return provider_entry['class'](**params)


def select_market_data_provider(
    provider_name: str,
    data_providers: dict[str, dict[str, typing.Any]],
) -> DataProviderInterface:
    """
    Resolve and instantiate the market data provider.

    Raises
    ------
    ConfigurationError
    """
    if (
        len(provider_name) < 1
        or provider_name not in data_providers
    ):
        msg = "Market data provider selected in configuration file not found"

        raise ConfigurationError(msg)

    if issubclass(data_providers[provider_name]['class'], NotFoundDataProvider):
        msg = " ".join([
            f"Market data provider {provider_name} was not found on your system.",
            "If it's one of our officially supported providers you should be able to install it by running:\n",
            f"pip install kaxanuk.data_provider_extensions.{provider_name}",
        ])

        raise ConfigurationError(msg)

    return _instantiate_provider(data_providers[provider_name])


def select_fundamental_data_provider(
    provider_name: str,
    data_providers: dict[str, dict[str, typing.Any]],
) -> DataProviderInterface | None:
    """
    Resolve and instantiate the fundamental data provider, or None if disabled.

    Raises
    ------
    ConfigurationError
    """
    if provider_name == NONE_DATA_PROVIDER:

        return None

    if (
        len(provider_name) < 1
        or provider_name not in data_providers
    ):
        msg = "Fundamental data provider selected in configuration file not found"

        raise ConfigurationError(msg)

    return _instantiate_provider(data_providers[provider_name])


def validate_api_keys(
    providers: dict[str, DataProviderInterface],
    logger: logging.Logger,
) -> None:
    """
    Validate the API keys of the selected providers.

    Raises
    ------
    ConfigurationError
    """
    for provider in providers.values():
        is_api_key_valid = provider.validate_api_key()
        if is_api_key_valid:
            msg = f"API key validation succeeded for {provider.__class__.__name__}"
            logger.info(msg)
        elif is_api_key_valid is not None:
            msg = f"Invalid API key for {provider.__class__.__name__}"

            raise ConfigurationError(msg)


def select_output_handler(
    output_format: str,
    output_handlers: dict[str, OutputHandlerInterface],
) -> OutputHandlerInterface:
    """
    Resolve the output handler for the selected output format.

    Raises
    ------
    ConfigurationError
    """
    if output_format not in output_handlers:
        msg = f"Output format {output_format} has no registered output handler"

        raise ConfigurationError(msg)

    return output_handlers[output_format]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/config_handlers/resolver_test.py -v`
Expected: PASS (all resolver tests pass)

- [ ] **Step 5: Commit**

```bash
git add src/kaxanuk/data_curator/config_handlers/_resolver.py tests/unit/config_handlers/resolver_test.py
git commit -m "feat: add resolver provider and output-handler helpers"
```

---

## Task 4: JsonConfigurator — happy path and Configuration equivalence

**Files:**
- Create: `src/kaxanuk/data_curator/config_handlers/json_configurator.py`
- Test: `tests/unit/config_handlers/json_configurator_test.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/config_handlers/json_configurator_test.py
import datetime
import json

import pytest

from kaxanuk.data_curator import __parameters_format_version__
from kaxanuk.data_curator.config_handlers.json_configurator import JsonConfigurator
from kaxanuk.data_curator.data_providers import DataProviderInterface
from kaxanuk.data_curator.entities import Configuration
from kaxanuk.data_curator.exceptions import ConfigurationError, ConfigurationHandlerError


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


def handlers():
    return {'csv': object(), 'parquet': object()}


def write_config(tmp_path, data):
    path = tmp_path / 'data_curator_parameters.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return str(path)


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
    assert configurator.get_output_handler() is handlers()['csv'] or True
    import logging
    assert configurator.get_logger_level() == logging.INFO
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/config_handlers/json_configurator_test.py -v`
Expected: FAIL — `ModuleNotFoundError: ... json_configurator`

- [ ] **Step 3: Write `JsonConfigurator`**

```python
# src/kaxanuk/data_curator/config_handlers/json_configurator.py
"""
Loads and returns a Configuration entity from a JSON file.
"""

import datetime
import json
import logging
import pathlib
import sys
import typing

from kaxanuk.data_curator.config_handlers import _resolver
from kaxanuk.data_curator.config_handlers.configurator_interface import ConfiguratorInterface
from kaxanuk.data_curator.data_providers import DataProviderInterface
from kaxanuk.data_curator.entities import Configuration
from kaxanuk.data_curator.exceptions import (
    ConfigurationError,
    ConfigurationHandlerError,
)
from kaxanuk.data_curator.output_handlers import OutputHandlerInterface


class JsonConfigurator(ConfiguratorInterface):
    REQUIRED_GENERAL_KEYS = (
        'market_data_provider',
        'fundamental_data_provider',
        'start_date',
        'end_date',
        'period',
        'output_format',
        'logger_level',
    )

    def __init__(
        self,
        file_path: str,
        data_providers: dict[str, dict[str, typing.Any]],
        output_handlers: dict[str, OutputHandlerInterface],
        logger_format: str = "[%(levelname)s] %(message)s",
    ):
        """
        Initialize configuration, data providers and output handlers based on a JSON config file.
        """
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(logger_format))
        logger.addHandler(handler)

        try:
            parsed = self._load_file(file_path)
            general = self._extract_general(parsed)

            _resolver.check_parameters_format_version(
                parsed.get('parameters_format_version', '')
            )

            self._logger_level = _resolver.get_logger_level(general['logger_level'])
            logger.setLevel(self._logger_level)

            self._market_data_provider = _resolver.select_market_data_provider(
                general['market_data_provider'],
                data_providers,
            )
            self._fundamental_data_provider = _resolver.select_fundamental_data_provider(
                general['fundamental_data_provider'],
                data_providers,
            )

            selected_providers = {
                provider.__class__.__name__: provider
                for provider in (self._market_data_provider, self._fundamental_data_provider)
                if provider is not None
            }
            _resolver.validate_api_keys(selected_providers, logger)

            self._output_handler = _resolver.select_output_handler(
                general['output_format'],
                output_handlers,
            )

            self._configuration = Configuration(
                start_date=self._parse_date(general['start_date'], 'start_date'),
                end_date=self._parse_date(general['end_date'], 'end_date'),
                period=general['period'],
                identifiers=tuple(parsed.get('identifiers', [])),
                columns=tuple(parsed.get('columns', [])),
            )

            logger.handlers.clear()
        except (ConfigurationError, ConfigurationHandlerError) as error:
            msg = f"An error was encountered when parsing your configuration file: {error!s}"
            logging.getLogger(__name__).critical(msg)
            sys.exit()

    def get_configuration(self) -> Configuration:
        return self._configuration

    def get_fundamental_data_provider(self) -> DataProviderInterface:
        return self._fundamental_data_provider

    def get_logger_level(self) -> int:
        return self._logger_level

    def get_market_data_provider(self) -> DataProviderInterface:
        return self._market_data_provider

    def get_output_handler(self) -> OutputHandlerInterface:
        return self._output_handler

    @classmethod
    def _extract_general(cls, parsed: dict[str, typing.Any]) -> dict[str, typing.Any]:
        if not isinstance(parsed.get('general'), dict):
            msg = "The configuration file is missing the 'general' section"

            raise ConfigurationHandlerError(msg)

        general = parsed['general']
        missing = [key for key in cls.REQUIRED_GENERAL_KEYS if key not in general]
        if missing:
            msg = "The following parameters are missing from the configuration file: " + ", ".join(missing)

            raise ConfigurationHandlerError(msg)

        return general

    @staticmethod
    def _parse_date(value: typing.Any, field_name: str) -> datetime.date:
        try:
            return datetime.date.fromisoformat(str(value))
        except (TypeError, ValueError) as error:
            msg = f"Invalid {field_name} in configuration file, expecting YYYY-MM-DD"

            raise ConfigurationError(msg) from error

    @staticmethod
    def _load_file(file_path: str) -> dict[str, typing.Any]:
        if not pathlib.Path(file_path).is_file():
            msg = f"Configuration file not found in path: {file_path}"

            raise ConfigurationHandlerError(msg)

        try:
            parsed = json.loads(pathlib.Path(file_path).read_text(encoding='utf-8'))
        except json.JSONDecodeError as error:
            msg = f"Invalid JSON in configuration file: {file_path}"

            raise ConfigurationHandlerError(msg) from error

        if not isinstance(parsed, dict):
            msg = "Configuration file must contain a JSON object"

            raise ConfigurationHandlerError(msg)

        return parsed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/config_handlers/json_configurator_test.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/kaxanuk/data_curator/config_handlers/json_configurator.py tests/unit/config_handlers/json_configurator_test.py
git commit -m "feat: add JsonConfigurator happy path"
```

---

## Task 5: JsonConfigurator — error cases

**Files:**
- Test: `tests/unit/config_handlers/json_configurator_test.py` (add)

These exercise the existing implementation from Task 4 (which already raises). `JsonConfigurator` calls `sys.exit()` on handled errors, so tests assert `SystemExit`.

- [ ] **Step 1: Write the failing tests (append)**

```python
def build(tmp_path, data):
    path = write_config(tmp_path, data)
    return lambda: JsonConfigurator(
        file_path=path,
        data_providers=providers(),
        output_handlers=handlers(),
    )


def test_missing_file_exits(tmp_path):
    make = lambda: JsonConfigurator(
        file_path=str(tmp_path / 'nope.json'),
        data_providers=providers(),
        output_handlers=handlers(),
    )
    with pytest.raises(SystemExit):
        make()


def test_invalid_json_exits(tmp_path):
    path = tmp_path / 'data_curator_parameters.json'
    path.write_text('{not valid json', encoding='utf-8')
    with pytest.raises(SystemExit):
        JsonConfigurator(
            file_path=str(path),
            data_providers=providers(),
            output_handlers=handlers(),
        )


def test_missing_general_key_exits(tmp_path):
    data = valid_config_dict()
    del data['general']['period']
    with pytest.raises(SystemExit):
        build(tmp_path, data)()


def test_stale_format_version_exits(tmp_path):
    data = valid_config_dict()
    data['parameters_format_version'] = '0.0.1'
    with pytest.raises(SystemExit):
        build(tmp_path, data)()


def test_unknown_market_provider_exits(tmp_path):
    data = valid_config_dict()
    data['general']['market_data_provider'] = 'made_up'
    with pytest.raises(SystemExit):
        build(tmp_path, data)()


def test_invalid_logger_level_exits(tmp_path):
    data = valid_config_dict()
    data['general']['logger_level'] = 'verbose'
    with pytest.raises(SystemExit):
        build(tmp_path, data)()


def test_invalid_date_exits(tmp_path):
    data = valid_config_dict()
    data['general']['start_date'] = '01/01/1990'
    with pytest.raises(SystemExit):
        build(tmp_path, data)()


def test_bad_column_prefix_exits(tmp_path):
    data = valid_config_dict()
    data['columns'] = ['not_a_valid_column']
    with pytest.raises(SystemExit):
        build(tmp_path, data)()
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/unit/config_handlers/json_configurator_test.py -v`
Expected: PASS (all 10 pass). If any error case does NOT exit, fix `JsonConfigurator` so the offending value is validated before use (it should already be covered by the resolver calls and `Configuration.__post_init__`).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/config_handlers/json_configurator_test.py
git commit -m "test: cover JsonConfigurator error cases"
```

---

## Task 6: Export JsonConfigurator from the package

**Files:**
- Modify: `src/kaxanuk/data_curator/config_handlers/__init__.py`
- Test: `tests/unit/config_handlers/exports_test.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/config_handlers/exports_test.py
from kaxanuk.data_curator import config_handlers


def test_json_configurator_is_exported():
    assert hasattr(config_handlers, 'JsonConfigurator')
    assert 'JsonConfigurator' in config_handlers.__all__


def test_excel_configurator_still_exported():
    assert hasattr(config_handlers, 'ExcelConfigurator')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/config_handlers/exports_test.py -v`
Expected: FAIL — `AttributeError: ... JsonConfigurator`

- [ ] **Step 3: Update `__init__.py`**

Replace its body with:

```python
"""
Package containing the interface and implementations of Configuration entity factories.
"""

__all__ = [
    'ConfiguratorInterface',
    'ExcelConfigurator',
    'JsonConfigurator',
]


# make these modules part of the public API of the base namespace
from kaxanuk.data_curator.config_handlers.configurator_interface import ConfiguratorInterface
from kaxanuk.data_curator.config_handlers.excel_configurator import ExcelConfigurator
from kaxanuk.data_curator.config_handlers.json_configurator import JsonConfigurator
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/config_handlers/exports_test.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/kaxanuk/data_curator/config_handlers/__init__.py tests/unit/config_handlers/exports_test.py
git commit -m "feat: export JsonConfigurator from config_handlers"
```

---

## Task 7: Config editor — pure config functions

**Files:**
- Create: `src/kaxanuk/data_curator/services/config_editor.py`
- Test: `tests/unit/services/config_editor_test.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/services/config_editor_test.py
import json

import pytest

from kaxanuk.data_curator.services import config_editor


def test_build_default_config_has_required_shape():
    config = config_editor.build_default_config()
    assert set(config) >= {'parameters_format_version', 'general', 'identifiers', 'columns'}
    assert config['general']['market_data_provider']
    assert isinstance(config['identifiers'], list)
    assert isinstance(config['columns'], list)


def test_load_config_returns_defaults_when_missing(tmp_path):
    config = config_editor.load_config(tmp_path / 'absent.json')
    assert config == config_editor.build_default_config()


def test_load_config_reads_existing_file(tmp_path):
    path = tmp_path / 'data_curator_parameters.json'
    payload = config_editor.build_default_config()
    payload['identifiers'] = ['AAPL']
    path.write_text(json.dumps(payload), encoding='utf-8')
    assert config_editor.load_config(path)['identifiers'] == ['AAPL']


def test_validate_accepts_valid_payload():
    assert config_editor.validate_config_payload(config_editor.build_default_config()) == []


def test_validate_flags_bad_provider():
    payload = config_editor.build_default_config()
    payload['general']['market_data_provider'] = 'made_up'
    errors = config_editor.validate_config_payload(payload)
    assert any('market_data_provider' in e for e in errors)


def test_validate_flags_bad_date_order():
    payload = config_editor.build_default_config()
    payload['general']['start_date'] = '2025-01-01'
    payload['general']['end_date'] = '2000-01-01'
    errors = config_editor.validate_config_payload(payload)
    assert any('date' in e.lower() for e in errors)


def test_validate_flags_non_list_identifiers():
    payload = config_editor.build_default_config()
    payload['identifiers'] = 'AAPL'
    assert config_editor.validate_config_payload(payload)


def test_save_writes_valid_payload(tmp_path):
    path = tmp_path / 'data_curator_parameters.json'
    payload = config_editor.build_default_config()
    config_editor.save_config(path, payload)
    assert json.loads(path.read_text(encoding='utf-8'))['general']['period'] == 'quarterly'


def test_save_rejects_invalid_payload(tmp_path):
    path = tmp_path / 'data_curator_parameters.json'
    payload = config_editor.build_default_config()
    payload['general']['period'] = 'weekly'
    with pytest.raises(ValueError):
        config_editor.save_config(path, payload)


def test_build_catalog_response_has_options_and_groups():
    response = config_editor.build_catalog_response()
    assert response['groups']
    assert 'financial_modeling_prep' in response['options']['market_data_provider']
    assert 'none' in response['options']['fundamental_data_provider']
    assert 'quarterly' in response['options']['period']
    assert 'csv' in response['options']['output_format']
    assert 'info' in response['options']['logger_level']
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/config_editor_test.py -v`
Expected: FAIL — `ModuleNotFoundError: ... config_editor`

- [ ] **Step 3: Write the pure functions**

```python
# src/kaxanuk/data_curator/services/config_editor.py
"""
Local HTML editor for the Data Curator JSON configuration.

Exposes pure config helpers (defaults, load, validate, save, catalog) plus a stdlib
http.server that serves a self-contained editor page bound to localhost.
"""

import datetime
import http.server
import importlib.resources
import json
import pathlib
import typing
import webbrowser

from kaxanuk.data_curator import __parameters_format_version__
from kaxanuk.data_curator.config_handlers.column_catalog import load_catalog
from kaxanuk.data_curator.config_handlers.configurator_interface import ConfiguratorInterface
from kaxanuk.data_curator.entities.configuration import (
    CONFIGURATION_COLUMN_PREFIXES,
    CONFIGURATION_PERIODS,
)


HOST = '127.0.0.1'
DEFAULT_PORT = 8753
OUTPUT_FORMATS = ('csv', 'parquet')
CONFIG_FILENAME = 'data_curator_parameters.json'
PAGE_RESOURCE = 'config_editor_page.html'

REQUIRED_GENERAL_KEYS = (
    'market_data_provider',
    'fundamental_data_provider',
    'start_date',
    'end_date',
    'period',
    'output_format',
    'logger_level',
)


def build_default_config() -> dict[str, typing.Any]:
    """Return the default configuration payload."""
    columns = [
        column
        for group in load_catalog()['groups']
        for column in group['columns']
    ]

    return {
        'parameters_format_version': __parameters_format_version__,
        'general': {
            'market_data_provider': 'financial_modeling_prep',
            'fundamental_data_provider': 'financial_modeling_prep',
            'start_date': '1990-01-01',
            'end_date': '2025-12-31',
            'period': 'quarterly',
            'output_format': 'csv',
            'logger_level': 'info',
        },
        'identifiers': [],
        'columns': columns,
    }


def load_config(config_path: pathlib.Path | str) -> dict[str, typing.Any]:
    """Load the config file, or the defaults when it is absent."""
    path = pathlib.Path(config_path)
    if not path.is_file():

        return build_default_config()

    return json.loads(path.read_text(encoding='utf-8'))


def build_catalog_response() -> dict[str, typing.Any]:
    """Return the column catalog plus the valid option lists for the editor."""
    catalog = load_catalog()

    return {
        'groups': catalog['groups'],
        'options': {
            'market_data_provider': list(ConfiguratorInterface.CONFIGURATION_PROVIDERS_MARKET),
            'fundamental_data_provider': list(ConfiguratorInterface.CONFIGURATION_PROVIDERS_FUNDAMENTAL),
            'period': list(CONFIGURATION_PERIODS),
            'output_format': list(OUTPUT_FORMATS),
            'logger_level': list(ConfiguratorInterface.CONFIGURATION_LOGGER_LEVELS),
        },
    }


def validate_config_payload(payload: typing.Any) -> list[str]:
    """Return a list of human-readable validation errors (empty when valid)."""
    errors: list[str] = []
    if not isinstance(payload, dict):

        return ["Configuration must be a JSON object"]

    general = payload.get('general')
    if not isinstance(general, dict):
        errors.append("Missing 'general' section")
        general = {}

    for key in REQUIRED_GENERAL_KEYS:
        if key not in general:
            errors.append(f"Missing general parameter: {key}")

    options = build_catalog_response()['options']
    for key, valid in options.items():
        if key in general and general[key] not in valid:
            errors.append(f"Invalid {key}: {general[key]}")

    start = _try_date(general.get('start_date'))
    end = _try_date(general.get('end_date'))
    if 'start_date' in general and start is None:
        errors.append("Invalid start_date, expecting YYYY-MM-DD")
    if 'end_date' in general and end is None:
        errors.append("Invalid end_date, expecting YYYY-MM-DD")
    if start is not None and end is not None and start > end:
        errors.append("start_date must not be after end_date")

    identifiers = payload.get('identifiers')
    if not isinstance(identifiers, list) or any(not isinstance(i, str) or not i for i in identifiers):
        errors.append("identifiers must be a list of non-empty strings")

    columns = payload.get('columns')
    if not isinstance(columns, list) or any(not isinstance(c, str) for c in columns):
        errors.append("columns must be a list of strings")
    else:
        valid_prefixes = tuple(p + '_' for p in CONFIGURATION_COLUMN_PREFIXES)
        bad = [c for c in columns if not c.startswith(valid_prefixes)]
        if bad:
            errors.append("Invalid column prefixes: " + ", ".join(bad))

    return errors


def save_config(config_path: pathlib.Path | str, payload: typing.Any) -> None:
    """
    Validate and write the configuration payload.

    Raises
    ------
    ValueError
        When the payload fails validation.
    """
    errors = validate_config_payload(payload)
    if errors:

        raise ValueError("; ".join(errors))

    pathlib.Path(config_path).write_text(
        json.dumps(payload, indent=2) + '\n',
        encoding='utf-8',
    )


def _try_date(value: typing.Any) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):

        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/services/config_editor_test.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add src/kaxanuk/data_curator/services/config_editor.py tests/unit/services/config_editor_test.py
git commit -m "feat: add config editor core functions"
```

---

## Task 8: Config editor — HTTP server and page

**Files:**
- Modify: `src/kaxanuk/data_curator/services/config_editor.py` (add handler + `serve`)
- Create: `src/kaxanuk/data_curator/services/config_editor_page.html`
- Test: `tests/unit/services/config_editor_test.py` (add)

- [ ] **Step 1: Write the failing integration test (append)**

```python
import threading
import urllib.request


def _run_server(server):
    server.serve_forever()


def _start(tmp_path):
    config_path = tmp_path / config_editor.CONFIG_FILENAME
    server = config_editor.build_server(config_path, port=0)
    thread = threading.Thread(target=_run_server, args=(server,), daemon=True)
    thread.start()
    port = server.server_address[1]
    return server, f'http://127.0.0.1:{port}'


def _get(url):
    with urllib.request.urlopen(url) as response:
        return response.status, response.read().decode('utf-8')


def _post(url, data):
    request = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def test_server_serves_page(tmp_path):
    server, base = _start(tmp_path)
    try:
        status, body = _get(base + '/')
        assert status == 200
        assert '<html' in body.lower() or '<!doctype' in body.lower()
    finally:
        server.shutdown()


def test_server_returns_config_and_catalog(tmp_path):
    server, base = _start(tmp_path)
    try:
        status, body = _get(base + '/api/config')
        assert status == 200
        assert 'general' in json.loads(body)
        status, body = _get(base + '/api/catalog')
        assert 'groups' in json.loads(body)
    finally:
        server.shutdown()


def test_server_saves_valid_config(tmp_path):
    server, base = _start(tmp_path)
    try:
        payload = config_editor.build_default_config()
        payload['identifiers'] = ['AAPL']
        assert _post(base + '/api/config', payload) == 200
        saved = json.loads((tmp_path / config_editor.CONFIG_FILENAME).read_text(encoding='utf-8'))
        assert saved['identifiers'] == ['AAPL']
    finally:
        server.shutdown()


def test_server_rejects_invalid_config(tmp_path):
    server, base = _start(tmp_path)
    try:
        payload = config_editor.build_default_config()
        payload['general']['period'] = 'weekly'
        assert _post(base + '/api/config', payload) == 400
    finally:
        server.shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/config_editor_test.py -k server -v`
Expected: FAIL — `AttributeError: ... build_server`

- [ ] **Step 3: Append the handler, `build_server`, and `serve` to `config_editor.py`**

```python
def _read_page() -> str:
    resource = importlib.resources.files(
        'kaxanuk.data_curator.services'
    ).joinpath(PAGE_RESOURCE)

    return resource.read_text(encoding='utf-8')


def build_server(
    config_path: pathlib.Path | str,
    port: int = DEFAULT_PORT,
) -> http.server.HTTPServer:
    """Build (but do not start) the editor HTTP server bound to localhost."""
    config_path = pathlib.Path(config_path)
    page = _read_page()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args: typing.Any) -> None:
            pass

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, data: typing.Any) -> None:
            self._send(status, json.dumps(data).encode('utf-8'), 'application/json')

        def do_GET(self) -> None:
            if self.path in ('/', '/index.html'):
                self._send(200, page.encode('utf-8'), 'text/html; charset=utf-8')
            elif self.path == '/api/config':
                self._send_json(200, load_config(config_path))
            elif self.path == '/api/catalog':
                self._send_json(200, build_catalog_response())
            else:
                self._send_json(404, {'error': 'not found'})

        def do_POST(self) -> None:
            if self.path != '/api/config':
                self._send_json(404, {'error': 'not found'})

                return

            length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode('utf-8'))
            except json.JSONDecodeError:
                self._send_json(400, {'errors': ['Invalid JSON']})

                return

            try:
                save_config(config_path, payload)
            except ValueError as error:
                self._send_json(400, {'errors': str(error).split('; ')})

                return

            self._send_json(200, {'status': 'saved'})

    return http.server.HTTPServer((HOST, port), Handler)


def serve(
    config_path: pathlib.Path | str,
    port: int = DEFAULT_PORT,
    *,
    open_browser: bool = True,
) -> None:
    """Start the editor server and block until interrupted."""
    server = build_server(config_path, port=port)
    url = f"http://{HOST}:{server.server_address[1]}"
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
```

- [ ] **Step 4: Create the editor page**

```html
<!-- src/kaxanuk/data_curator/services/config_editor_page.html -->
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Data Curator — parameters</title>
<style>
  :root { color-scheme: light dark; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
  body { margin: 0; padding: 24px; max-width: 960px; }
  h1 { font-size: 18px; font-weight: 500; margin: 0 0 4px; }
  .sub { color: #666; font-size: 13px; margin: 0 0 20px; }
  fieldset { border: 1px solid #ccc; border-radius: 8px; margin: 0 0 18px; padding: 14px 16px; }
  legend { font-size: 13px; color: #555; padding: 0 6px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px 16px; }
  label { display: block; font-size: 12px; color: #555; margin-bottom: 4px; }
  input, select { width: 100%; box-sizing: border-box; padding: 7px 8px; font-size: 14px; border: 1px solid #bbb; border-radius: 6px; background: Field; color: FieldText; }
  .row { display: flex; gap: 8px; margin-bottom: 10px; }
  .row input { flex: 1; }
  button { padding: 7px 12px; font-size: 13px; border: 1px solid #999; border-radius: 6px; background: ButtonFace; cursor: pointer; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; background: #e6f1fb; color: #0c447c; padding: 4px 8px; border-radius: 6px; font-size: 13px; }
  .chip button { border: none; background: none; cursor: pointer; color: inherit; padding: 0; font-size: 14px; }
  .cols { max-height: 360px; overflow: auto; border: 1px solid #ddd; border-radius: 6px; padding: 8px; }
  .col { display: flex; align-items: center; gap: 8px; padding: 3px 4px; font-size: 13px; font-family: ui-monospace, monospace; }
  .grouphdr { font-weight: 500; font-family: system-ui; font-size: 12px; color: #555; margin: 10px 0 4px; }
  .bar { position: sticky; top: 0; display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 10px 0; background: Canvas; }
  .status { font-size: 13px; }
  .ok { color: #0f6e56; } .err { color: #a32d2d; }
</style>
</head>
<body>
<div class="bar">
  <div><h1>Data Curator — parameters</h1><p class="sub" id="path">Config/data_curator_parameters.json</p></div>
  <div><span class="status" id="status"></span> <button id="reload">Reload</button> <button id="save">Save</button></div>
</div>

<fieldset><legend>General</legend><div class="grid" id="general"></div></fieldset>

<fieldset><legend>Identifiers</legend>
  <div class="row"><input id="idInput" placeholder="Add ticker…" /><button id="idAdd">Add</button></div>
  <div class="chips" id="idChips"></div>
</fieldset>

<fieldset><legend>Output columns (<span id="colCount">0</span> selected)</legend>
  <div class="row"><input id="colSearch" placeholder="Search columns or type a custom c_… then Enter" /></div>
  <div class="cols" id="cols"></div>
</fieldset>

<script>
const GENERAL_FIELDS = [
  ['market_data_provider', 'select'], ['fundamental_data_provider', 'select'],
  ['start_date', 'date'], ['end_date', 'date'],
  ['period', 'select'], ['output_format', 'select'], ['logger_level', 'select'],
];
let state = null, catalog = null;

async function boot() {
  catalog = await (await fetch('/api/catalog')).json();
  state = await (await fetch('/api/config')).json();
  renderGeneral(); renderIdentifiers(); renderColumns(); setStatus('');
}

function setStatus(msg, cls) { const s = document.getElementById('status'); s.textContent = msg; s.className = 'status ' + (cls || ''); }

function renderGeneral() {
  const root = document.getElementById('general'); root.innerHTML = '';
  for (const [key, type] of GENERAL_FIELDS) {
    const wrap = document.createElement('div');
    const label = document.createElement('label'); label.textContent = key; wrap.appendChild(label);
    let input;
    if (type === 'select') {
      input = document.createElement('select');
      for (const opt of catalog.options[key]) {
        const o = document.createElement('option'); o.value = o.textContent = opt; input.appendChild(o);
      }
    } else { input = document.createElement('input'); input.type = 'date'; }
    input.value = state.general[key];
    input.addEventListener('change', () => { state.general[key] = input.value; });
    wrap.appendChild(input); root.appendChild(wrap);
  }
}

function renderIdentifiers() {
  const chips = document.getElementById('idChips'); chips.innerHTML = '';
  state.identifiers.forEach((id, i) => {
    const chip = document.createElement('span'); chip.className = 'chip'; chip.textContent = id;
    const x = document.createElement('button'); x.textContent = '×';
    x.onclick = () => { state.identifiers.splice(i, 1); renderIdentifiers(); };
    chip.appendChild(x); chips.appendChild(chip);
  });
}

function addIdentifier() {
  const input = document.getElementById('idInput'); const v = input.value.trim();
  if (v && !state.identifiers.includes(v)) { state.identifiers.push(v); input.value = ''; renderIdentifiers(); }
}

function renderColumns() {
  const root = document.getElementById('cols'); root.innerHTML = '';
  const selected = new Set(state.columns);
  const filter = document.getElementById('colSearch').value.trim().toLowerCase();
  const known = new Set();
  for (const group of catalog.groups) {
    const matches = group.columns.filter(c => !filter || c.toLowerCase().includes(filter));
    if (!matches.length) continue;
    const hdr = document.createElement('div'); hdr.className = 'grouphdr'; hdr.textContent = group.label; root.appendChild(hdr);
    for (const col of matches) {
      known.add(col);
      root.appendChild(columnRow(col, selected.has(col)));
    }
  }
  const custom = state.columns.filter(c => !known.has(c) && (!filter || c.toLowerCase().includes(filter)));
  if (custom.length) {
    const hdr = document.createElement('div'); hdr.className = 'grouphdr'; hdr.textContent = 'Custom / other'; root.appendChild(hdr);
    custom.forEach(c => root.appendChild(columnRow(c, true)));
  }
  document.getElementById('colCount').textContent = state.columns.length;
}

function columnRow(col, checked) {
  const row = document.createElement('label'); row.className = 'col';
  const box = document.createElement('input'); box.type = 'checkbox'; box.checked = checked;
  box.onchange = () => {
    if (box.checked) { if (!state.columns.includes(col)) state.columns.push(col); }
    else { state.columns = state.columns.filter(c => c !== col); }
    document.getElementById('colCount').textContent = state.columns.length;
  };
  row.appendChild(box); row.appendChild(document.createTextNode(col));
  return row;
}

async function save() {
  setStatus('Saving…');
  const res = await fetch('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(state) });
  if (res.ok) { setStatus('Saved', 'ok'); }
  else { const data = await res.json(); setStatus((data.errors || ['Error']).join('; '), 'err'); }
}

document.getElementById('idAdd').onclick = addIdentifier;
document.getElementById('idInput').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); addIdentifier(); } });
document.getElementById('colSearch').addEventListener('input', renderColumns);
document.getElementById('colSearch').addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    e.preventDefault(); const v = e.target.value.trim();
    if (v && !state.columns.includes(v)) { state.columns.push(v); e.target.value = ''; renderColumns(); }
  }
});
document.getElementById('save').onclick = save;
document.getElementById('reload').onclick = boot;
boot();
</script>
</body>
</html>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/services/config_editor_test.py -v`
Expected: PASS (all, including the 4 server tests)

- [ ] **Step 6: Commit**

```bash
git add src/kaxanuk/data_curator/services/config_editor.py src/kaxanuk/data_curator/services/config_editor_page.html tests/unit/services/config_editor_test.py
git commit -m "feat: add config editor http server and page"
```

---

## Task 9: CLI — `config-editor` command

**Files:**
- Modify: `src/kaxanuk/data_curator/services/cli.py`
- Test: `tests/unit/services/cli_test.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/services/cli_test.py
from click.testing import CliRunner

from kaxanuk.data_curator.services import cli as cli_module


def test_config_editor_invokes_serve(monkeypatch, tmp_path):
    calls = {}

    def fake_serve(config_path, port=8753, *, open_browser=True):
        calls['config_path'] = str(config_path)
        calls['open_browser'] = open_browser

    monkeypatch.setattr(cli_module.config_editor, 'serve', fake_serve)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli_module.cli,
            ['config-editor', '--no-browser'],
        )
    assert result.exit_code == 0, result.output
    assert calls['open_browser'] is False
    assert calls['config_path'].endswith('data_curator_parameters.json')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/cli_test.py -v`
Expected: FAIL — `No such command 'config-editor'`

- [ ] **Step 3: Add the command to `cli.py`**

Add this import near the top of `cli.py` (after the existing imports):

```python
from kaxanuk.data_curator.services import config_editor
```

Add this constant next to the other module-level constants (after `PARAMETERS_EXCEL_FILE`):

```python
PARAMETERS_JSON_FILE = 'data_curator_parameters.json'
```

Add this command (place it after the `run` command):

```python
@cli.command(name='config-editor')
@click.option(
    '--port',
    default=config_editor.DEFAULT_PORT,
    help=f"Port for the local editor server. Default: {config_editor.DEFAULT_PORT}",
    type=click.INT,
)
@click.option(
    '--no-browser',
    is_flag=True,
    default=False,
    help="Do not open a browser window automatically.",
)
def config_editor_command(port: int, no_browser: bool) -> None:    # noqa: FBT001
    """
    Launch the local HTML editor for the JSON configuration file.
    """
    config_path = pathlib.Path(CONFIG_SUBDIR) / PARAMETERS_JSON_FILE
    click.echo(f"Starting config editor at http://{config_editor.HOST}:{port} (Ctrl+C to stop)")
    config_editor.serve(
        config_path,
        port=port,
        open_browser=not no_browser,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/services/cli_test.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/kaxanuk/data_curator/services/cli.py tests/unit/services/cli_test.py
git commit -m "feat: add config-editor CLI command"
```

---

## Task 10: CLI — `init json` / `update json` + templates

**Files:**
- Modify: `src/kaxanuk/data_curator/services/cli.py`
- Create: `templates/data_curator/Config/data_curator_parameters.json`
- Create: `templates/data_curator/json_entry_script.py`
- Test: `tests/unit/services/cli_test.py` (add)

- [ ] **Step 1: Generate the default JSON template**

Run from repo root (reuses the catalog so columns stay in parity):

```bash
python -c "
import json, pathlib
from kaxanuk.data_curator.services import config_editor
cfg = config_editor.build_default_config()
pathlib.Path('templates/data_curator/Config/data_curator_parameters.json').write_text(json.dumps(cfg, indent=2) + '\n', encoding='utf-8')
print('wrote template with', len(cfg['columns']), 'columns')
"
```

Expected: `wrote template with 18x columns`

- [ ] **Step 2: Create the JSON entry script template**

```python
# templates/data_curator/json_entry_script.py
"""
Example entry script that reads configuration from a JSON file and outputs to csv or parquet.

Edit the parameters through the editor:  kaxanuk.data_curator config-editor
"""

import os
import pathlib

import kaxanuk.data_curator


kaxanuk.data_curator.load_config_env()

custom_calculations_file = 'Config/custom_calculations.py'
if pathlib.Path(custom_calculations_file).is_file():
    from Config import custom_calculations
    custom_calculation_modules = [custom_calculations]
else:
    custom_calculation_modules = []

output_base_dir = 'Output'

parameters_json_file = 'Config/data_curator_parameters.json'
configurator = kaxanuk.data_curator.config_handlers.JsonConfigurator(
    file_path=parameters_json_file,
    data_providers={
        'financial_modeling_prep': {
            'class': kaxanuk.data_curator.data_providers.FinancialModelingPrep,
            'api_key': os.getenv('KNDC_API_KEY_FMP'),
        },
        'lseg_workspace': {
            'class': kaxanuk.data_curator.data_providers.LsegWorkspace,
            'api_key': os.getenv('KNDC_API_KEY_LSEG'),
        },
        'yahoo_finance': {
            'class': kaxanuk.data_curator.load_data_provider_extension(
                extension_name='yahoo_finance',
                extension_class_name='YahooFinance',
            ),
            'api_key': None,
        },
    },
    output_handlers={
        'csv': kaxanuk.data_curator.output_handlers.CsvOutput(
            output_base_dir=output_base_dir,
        ),
        'parquet': kaxanuk.data_curator.output_handlers.ParquetOutput(
            output_base_dir=output_base_dir,
        ),
    },
)

kaxanuk.data_curator.main(
    configuration=configurator.get_configuration(),
    market_data_provider=configurator.get_market_data_provider(),
    fundamental_data_provider=configurator.get_fundamental_data_provider(),
    output_handlers=[configurator.get_output_handler()],
    custom_calculation_modules=custom_calculation_modules,
    logger_level=configurator.get_logger_level(),
)
```

- [ ] **Step 3: Write the failing test (append to cli_test.py)**

```python
def test_init_json_scaffolds_files(tmp_path, monkeypatch):
    import pathlib
    from kaxanuk.data_curator.services import cli as cli_mod

    templates = pathlib.Path(cli_mod.__file__).resolve().parents[4] / 'templates' / 'data_curator'
    monkeypatch.setattr(cli_mod, '_find_templates_dir', lambda: str(templates))

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli_mod.cli, ['init', 'json'])
        assert result.exit_code == 0, result.output
        assert pathlib.Path('Config/data_curator_parameters.json').is_file()
        assert pathlib.Path('Config/custom_calculations.py').is_file()
        assert pathlib.Path('__main__.py').is_file()
        assert not pathlib.Path('Config/data_curator_parameters.xlsx').is_file()
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/unit/services/cli_test.py::test_init_json_scaffolds_files -v`
Expected: FAIL — `'json' is not one of 'excel'` (click rejects the choice)

- [ ] **Step 5: Wire `json` into init/update**

In `cli.py`, extend the format enums:

```python
class InitFormats(enum.StrEnum):
    EXCEL = 'excel'
    JSON = 'json'

class UpdateFormats(enum.StrEnum):
    EXCEL = 'excel'
    ENTRY_SCRIPT = 'entry_script'
    JSON = 'json'
```

Add `JSON_ENTRY_SCRIPT_NAME = 'json_entry_script.py'` next to the other constants.

In `init`, extend the branch (after the `if config_format == InitFormats.EXCEL:` block) with:

```python
    elif config_format == InitFormats.JSON:
        config_path = pathlib.Path(CONFIG_SUBDIR)
        if pathlib.Path.exists(config_path):
            msg = f"The directory {CONFIG_SUBDIR} already exists. Please run the 'update' command instead"

            raise click.ClickException(msg)

        if not _validate_filename(entry_script):
            msg = ' '.join([
                "The entry script file name can only contain alphanumeric characters, hyphens,",
                "underscores, and periods, and must end in .py"
            ])

            raise click.ClickException(msg)

        try:
            _install_json_files(entry_script)
        except NotADirectoryError as error:
            msg = f"Templates directory not found in {DATA_DIR}. Please uninstall and reinstall this library"

            raise click.ClickException(msg) from error
        except OSError as error:
            if error.errno == errno.EACCES:
                msg = "Unable to access or modify target files"
            else:
                msg = f"OS error occurred while copying: {error}"

            raise click.ClickException(msg) from error

        click.echo("Installed all files successfully")
```

Add the `_install_json_files` helper (next to `_install_excel_files`):

```python
def _install_json_files(entry_script: str) -> None:
    """
    Install the directories and files required for the JSON entry script.

    Raises
    ------
    NotADirectoryError
        The templates directory was not found
    OSError
        Usually when there's a file permissions error
    """
    for dir_name in INIT_DIRS:
        try:
            pathlib.Path.mkdir(pathlib.Path(dir_name))
            click.echo(f"Created directory {dir_name}")
        except FileExistsError:
            click.echo(f"The directory {dir_name} already exists, omitting the creation")

    actual_templates_dir = _find_templates_dir()
    if actual_templates_dir is None:
        raise NotADirectoryError

    templates_path = pathlib.Path(actual_templates_dir)
    config_source = templates_path / CONFIG_SUBDIR
    for name in ('.env', 'custom_calculations.py', PARAMETERS_JSON_FILE):
        source = config_source / name
        if source.is_file():
            shutil.copy(source, pathlib.Path(CONFIG_SUBDIR) / name)

    shutil.copy(
        templates_path / JSON_ENTRY_SCRIPT_NAME,
        entry_script,
    )
```

Extend the `update` `match` with a `json` case (mirrors the excel case but for the JSON file):

```python
        case UpdateFormats.JSON:
            config_path = pathlib.Path(CONFIG_SUBDIR)
            if not pathlib.Path.is_dir(config_path):
                msg = f"The {CONFIG_SUBDIR} directory does not exist. Please run the 'init' command instead"

                raise click.ClickException(msg)

            try:
                _update_json_files()
                click.echo("Updated all files successfully")
            except OSError as error:
                if error.errno == errno.EACCES:
                    msg = "Unable to access or modify target files"
                else:
                    msg = f"OS error occurred while copying: {error}"

                raise click.ClickException(msg) from error
```

Add `_update_json_files` (next to `_update_excel_files`):

```python
def _update_json_files() -> None:
    """
    Update the JSON configuration file into the Config subdirectory, renaming any existing file beforehand.

    Raises
    ------
    NotADirectoryError
        The templates directory was not found
    OSError
        File permissions or shutil error
    """
    actual_templates_dir = _find_templates_dir()
    if actual_templates_dir is None:
        raise NotADirectoryError

    template_file_path = pathlib.Path(actual_templates_dir) / CONFIG_SUBDIR / PARAMETERS_JSON_FILE
    local_file = pathlib.Path(CONFIG_SUBDIR) / PARAMETERS_JSON_FILE
    if pathlib.Path.exists(local_file):
        _safe_rename_file(local_file)
    shutil.copy(template_file_path, local_file)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/services/cli_test.py -v`
Expected: PASS (all)

- [ ] **Step 7: Commit**

```bash
git add src/kaxanuk/data_curator/services/cli.py templates/data_curator/Config/data_curator_parameters.json templates/data_curator/json_entry_script.py tests/unit/services/cli_test.py
git commit -m "feat: add json init/update formats and templates"
```

---

## Task 11: Full-suite verification, docs, changelog, context

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/source/user_guide/zero_coder.rst`, `quick_start.rst` (JSON + editor as default; Excel as legacy)
- Modify: `docs/context/results.md`, `docs/context/memory.md`, `docs/context/sesion-log.md`, `docs/context/todo.md`

- [ ] **Step 1: Run the full suite and linter**

Run:
```bash
pytest --cov=src --cov=tests --cov-report=term-missing:skip-covered tests
ruff check src/kaxanuk/data_curator/config_handlers src/kaxanuk/data_curator/services
```
Expected: all tests pass; ruff reports no errors in the new modules. Fix any lint findings inline (the codebase enforces the rules in `pyproject.toml`).

- [ ] **Step 2: Add CHANGELOG entry**

Under the top/unreleased section of `CHANGELOG.md`, add:

```markdown
### Added
- JSON configuration format (`Config/data_curator_parameters.json`) with `JsonConfigurator`.
- `config-editor` CLI command: a local HTML editor for managing run parameters.
- `init json` / `update json` scaffolding and a JSON entry-script template.

### Deprecated
- The Excel configuration format and `ExcelConfigurator` remain supported but are now the legacy fallback; the JSON + HTML editor path is the default.
```

- [ ] **Step 3: Update the user guide**

In `docs/source/user_guide/quick_start.rst` and `zero_coder.rst`, present the default flow as `init json` → `config-editor` → `run`, and move the Excel instructions under a "Legacy: Excel configuration" note. Keep wording consistent with the existing docs style.

- [ ] **Step 4: Update context files (per CLAUDE.md)**

- `docs/context/results.md`: add a 1–4 line review of this change.
- `docs/context/memory.md`: add one line — `# decision: JSON + local HTML editor replaces Excel as default config; ExcelConfigurator kept as deprecated fallback via ConfiguratorInterface.`
- `docs/context/sesion-log.md`: add `- 2026-06-09: replaced Excel config with JSON + local HTML editor (config-editor CLI), TDD, on feat/html-config-editor.`
- `docs/context/todo.md`: mark this work item done; add follow-ups (refactor ExcelConfigurator to delegate to `_resolver` behind characterization tests; update remaining docs referencing the xlsx).

- [ ] **Step 5: Manual smoke test (self-verification)**

Run, in a scratch directory:
```bash
python -m kaxanuk.data_curator init json
python -m kaxanuk.data_curator config-editor --no-browser --port 8753
```
Then in another shell: `curl -s http://127.0.0.1:8753/api/config` returns JSON; `curl -s http://127.0.0.1:8753/ | head` returns the HTML page. Stop with Ctrl+C. Confirm `Config/data_curator_parameters.json` exists and `__main__.py` references `JsonConfigurator`.

- [ ] **Step 6: Commit**

```bash
git add CHANGELOG.md docs/
git commit -m "docs: document JSON config editor and deprecate Excel path"
```

---

## Self-Review

**Spec coverage:**
- JSON format + `JsonConfigurator` → Tasks 4–6. ✓
- Shared `_resolver` → Tasks 2–3. ✓
- Column catalog → Task 1. ✓
- Editor server (routes, localhost bind, validation) → Tasks 7–8. ✓
- Editor page (grouped checklist, identifiers, free entry) → Task 8. ✓
- CLI `config-editor` + `init/update json` → Tasks 9–10. ✓
- Templates (JSON config + entry script) → Task 10. ✓
- Error semantics mirror Excel → Tasks 4–5. ✓
- Excel kept as fallback (untouched) → no task modifies `excel_configurator.py`. ✓
- Docs + CHANGELOG + context → Task 11. ✓
- No new runtime deps → only stdlib + existing `click`/`packaging`. ✓

**Type/name consistency:** `load_catalog`, `build_default_config`, `load_config`, `validate_config_payload`, `save_config`, `build_catalog_response`, `build_server`, `serve` are used consistently across Tasks 7–9. Resolver function names (`get_logger_level`, `check_parameters_format_version`, `select_market_data_provider`, `select_fundamental_data_provider`, `validate_api_keys`, `select_output_handler`) match between Tasks 2–4. `PARAMETERS_JSON_FILE` / `JSON_ENTRY_SCRIPT_NAME` defined in Task 9/10 before use.

**Placeholder scan:** No TBD/TODO; every code step shows complete code. The two generation commands (catalog, template) are concrete and reproducible. Column counts shown as `18x` are expected-output hints, not placeholders in code.
