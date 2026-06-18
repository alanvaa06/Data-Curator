"""
Loads the output column catalog and identifier presets used by the configuration editor.
"""

import importlib.resources
import json
import typing


def _load_bundled_json(filename: str) -> typing.Any:
    resource = importlib.resources.files(
        'kaxanuk.data_curator.config_handlers'
    ).joinpath(filename)

    return json.loads(
        resource.read_text(encoding='utf-8')
    )


def load_catalog() -> dict[str, typing.Any]:
    """
    Load the bundled output column catalog.

    Returns
    -------
    A mapping with a 'groups' list, each group holding a 'prefix', 'label' and 'columns' list.
    """
    return _load_bundled_json('column_catalog.json')


def load_identifier_presets() -> dict[str, typing.Any]:
    """
    Load the bundled identifier presets (index constituent ticker lists).

    Returns
    -------
    A mapping with an 'as_of' date and a 'presets' list, each preset holding a
    'key', 'label' and 'identifiers' list.
    """
    return _load_bundled_json('identifier_presets.json')


def load_macro_catalog() -> list[dict[str, typing.Any]]:
    """
    Load the bundled macro column catalog.

    Returns
    -------
    A list of entries, each holding at minimum 'column', 'provider' and 'series_id'.
    """
    return _load_bundled_json('macro_catalog.json')
