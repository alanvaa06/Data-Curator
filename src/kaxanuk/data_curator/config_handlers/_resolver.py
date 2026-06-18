"""
Shared resolution helpers for configurator implementations.

These functions translate parsed configuration values into the data providers, output
handler, logger level and version checks shared by all ConfiguratorInterface implementations.
"""

import functools
import logging
import typing

import packaging.version

from kaxanuk.data_curator import __parameters_format_version__
from kaxanuk.data_curator.config_handlers.column_catalog import load_macro_catalog
from kaxanuk.data_curator.config_handlers.configurator_interface import ConfiguratorInterface
from kaxanuk.data_curator.data_providers import (
    DataProviderInterface,
    MacroDataProviderInterface,
    NotFoundDataProvider,
)
from kaxanuk.data_curator.exceptions import (
    ConfigurationError,
    ConfigurationHandlerError,
    DataProviderMissingKeyError,
)
from kaxanuk.data_curator.output_handlers import OutputHandlerInterface


NONE_DATA_PROVIDER = 'none'


@functools.lru_cache(maxsize=1)
def _macro_catalog_index() -> dict[str, dict]:
    return {row['column']: row for row in load_macro_catalog()}


def resolve_macro_requests(
    columns: typing.Iterable[str],
) -> dict[str, list[tuple[str, str]]]:
    """
    Map selected e_* columns to {provider_name: [(column, series_id), ...]}.

    Non-macro columns (anything not prefixed with ``e_``) are ignored.

    Raises
    ------
    ConfigurationError
        A column prefixed with ``e_`` is not present in the macro catalog.
    """
    requests: dict[str, list[tuple[str, str]]] = {}
    for column in columns:
        if not column.startswith("e_"):
            continue
        entry = _macro_catalog_index().get(column)
        if entry is None:
            msg = f"Unknown macro column not in catalog: {column}"

            raise ConfigurationError(msg)
        requests.setdefault(entry["provider"], []).append(
            (column, entry["series_id"])
        )

    return requests


def required_macro_providers(columns: typing.Iterable[str]) -> set[str]:
    """Return the set of provider names needed for the selected e_* columns."""
    return set(resolve_macro_requests(columns).keys())


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


def _instantiate_provider(provider_entry: dict[str, typing.Any]) -> DataProviderInterface:
    if provider_entry['class'] is None:
        msg = "Selected data provider implementation is missing."

        raise ConfigurationError(msg)

    params = {}
    if provider_entry['api_key'] is not None:
        params['api_key'] = provider_entry['api_key']

    try:
        return provider_entry['class'](**params)
    except DataProviderMissingKeyError as error:
        msg = " ".join([
            f"Data provider {provider_entry['class'].__name__} requires an API key.",
            "Set it in the Config/.env file (or through the API keys section of the configuration panel).",
        ])

        raise ConfigurationError(msg) from error


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


def _instantiate_macro_provider(
    provider_name: str,
    provider_entry: dict[str, typing.Any],
) -> MacroDataProviderInterface:
    if provider_entry.get('class') is None:
        msg = f"Selected macro data provider implementation is missing: {provider_name}"

        raise ConfigurationError(msg)

    try:
        # Always pass api_key= (even when None) because all macro adapters declare (*, api_key: str | None).
        return provider_entry['class'](api_key=provider_entry.get('api_key'))
    except DataProviderMissingKeyError as error:
        msg = " ".join([
            f"Macro data provider {provider_name} requires an API key.",
            "Set it in the Config/.env file (or through the API keys section of the configuration panel).",
        ])

        raise ConfigurationError(msg) from error


def select_macro_data_providers(
    columns: typing.Iterable[str],
    macro_data_providers: dict[str, dict[str, typing.Any]],
    logger: logging.Logger,
) -> list[MacroDataProviderInterface]:
    """
    Resolve and instantiate the macro data providers required by the selected columns.

    Returns an empty list when no e_* columns are selected.

    Raises
    ------
    ConfigurationError
        A required provider is not registered, missing an implementation, or its
        API key is missing or invalid.
    """
    required = required_macro_providers(columns)
    selected: list[MacroDataProviderInterface] = []
    for provider_name in sorted(required):
        if provider_name not in macro_data_providers:
            msg = f"Macro data provider required by selected columns not found: {provider_name}"

            raise ConfigurationError(msg)

        provider = _instantiate_macro_provider(
            provider_name,
            macro_data_providers[provider_name],
        )
        is_api_key_valid = provider.validate_api_key()
        if is_api_key_valid:
            msg = f"API key validation succeeded for {provider.__class__.__name__}"
            logger.info(msg)
        elif is_api_key_valid is not None:
            msg = f"Invalid API key for {provider.__class__.__name__}"

            raise ConfigurationError(msg)

        selected.append(provider)

    return selected


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
