from kaxanuk.data_curator.data_blocks.economic_indicators import EconomicIndicatorDataBlock
from kaxanuk.data_curator.entities import EconomicIndicatorRow, EconomicIndicatorData


def test_block_is_non_ticker():
    # None grouping = columns broadcast to every identifier
    assert EconomicIndicatorDataBlock.grouping_identifier_field is None


def test_block_prefix_maps_e_to_row():
    assert EconomicIndicatorDataBlock.prefix_entity_map == {"e": EconomicIndicatorRow}


def test_block_clock_sync_is_date():
    assert EconomicIndicatorDataBlock.clock_sync_field is EconomicIndicatorRow.date


def test_block_main_entity():
    assert EconomicIndicatorDataBlock.main_entity is EconomicIndicatorData
