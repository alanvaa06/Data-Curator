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

        Parameters
        ----------
        file_path
            The path to the JSON configuration file
        data_providers
            All the data provider options that the configuration file will choose from, along with their API keys if any
        output_handlers
            All the output handlers options that the configuration file will choose from
        logger_format
            The format for the logger messages. will be injected to logging.Formatter()
        """
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(logger_format)
        )
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
                for provider in (
                    self._market_data_provider,
                    self._fundamental_data_provider,
                )
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
        except (
            ConfigurationError,
            ConfigurationHandlerError,
        ) as error:
            msg = f"An error was encountered when parsing your configuration file: {error!s}"
            logging.getLogger(__name__).critical(msg)
            sys.exit(1)

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
    def _extract_general(
        cls,
        parsed: dict[str, typing.Any]
    ) -> dict[str, typing.Any]:
        """
        Extract and validate the presence of the 'general' section and its required keys.

        Raises
        ------
        ConfigurationHandlerError
        """
        if not isinstance(parsed.get('general'), dict):
            msg = "The configuration file is missing the 'general' section"

            raise ConfigurationHandlerError(msg)

        general = parsed['general']
        missing = [
            key
            for key in cls.REQUIRED_GENERAL_KEYS
            if key not in general
        ]
        if missing:
            msg = "The following parameters are missing from the configuration file: " + ", ".join(missing)

            raise ConfigurationHandlerError(msg)

        return general

    @staticmethod
    def _parse_date(
        value: typing.Any,
        field_name: str
    ) -> datetime.date:
        """
        Parse an ISO date string into a datetime.date.

        Raises
        ------
        ConfigurationError
        """
        try:
            return datetime.date.fromisoformat(str(value))
        except (TypeError, ValueError) as error:
            msg = f"Invalid {field_name} in configuration file, expecting YYYY-MM-DD"

            raise ConfigurationError(msg) from error

    @staticmethod
    def _load_file(file_path: str) -> dict[str, typing.Any]:
        """
        Load and parse the JSON configuration file.

        Raises
        ------
        ConfigurationHandlerError
        """
        if not pathlib.Path(file_path).is_file():
            msg = f"Configuration file not found in path: {file_path}"

            raise ConfigurationHandlerError(msg)

        try:
            parsed = json.loads(
                pathlib.Path(file_path).read_text(encoding='utf-8')
            )
        except json.JSONDecodeError as error:
            msg = f"Invalid JSON in configuration file: {file_path}"

            raise ConfigurationHandlerError(msg) from error

        if not isinstance(parsed, dict):
            msg = "Configuration file must contain a JSON object"

            raise ConfigurationHandlerError(msg)

        return parsed
