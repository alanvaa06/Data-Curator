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
