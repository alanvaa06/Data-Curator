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

    return json.loads(
        path.read_text(encoding='utf-8')
    )


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
    if (
        not isinstance(identifiers, list)
        or any(not isinstance(i, str) or not i for i in identifiers)
    ):
        errors.append("identifiers must be a list of non-empty strings")

    columns = payload.get('columns')
    if (
        not isinstance(columns, list)
        or any(not isinstance(c, str) for c in columns)
    ):
        errors.append("columns must be a list of strings")
    else:
        valid_prefixes = tuple(p + '_' for p in CONFIGURATION_COLUMN_PREFIXES)
        bad = [c for c in columns if not c.startswith(valid_prefixes)]
        if bad:
            errors.append("Invalid column prefixes: " + ", ".join(bad))

    return errors


def save_config(
    config_path: pathlib.Path | str,
    payload: typing.Any
) -> None:
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
