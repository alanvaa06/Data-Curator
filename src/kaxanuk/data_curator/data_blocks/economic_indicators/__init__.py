__all__ = [
    'EconomicIndicatorDataBlock',
]


import typing

from kaxanuk.data_curator.data_blocks.base_data_block import BaseDataBlock
from kaxanuk.data_curator.entities import (
    EconomicIndicatorData,
    EconomicIndicatorRow,
)


class EconomicIndicatorDataBlock(BaseDataBlock):
    """
    Non-ticker macro data block.

    grouping_identifier_field is None, so its columns are accessible for all
    identifiers (macro series are global, not per-ticker).
    """

    clock_sync_field = EconomicIndicatorRow.date
    grouping_identifier_field = None
    main_entity = EconomicIndicatorData
    prefix_entity_map: typing.Final = {"e": EconomicIndicatorRow}
