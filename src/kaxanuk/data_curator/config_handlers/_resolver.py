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
