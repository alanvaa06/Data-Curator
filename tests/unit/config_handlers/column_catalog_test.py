from kaxanuk.data_curator.config_handlers.column_catalog import (
    load_catalog,
    load_identifier_presets,
)


class TestIdentifierPresets:
    def test_loads_three_index_presets(self):
        presets = load_identifier_presets()
        keys = [p['key'] for p in presets['presets']]
        assert keys == ['sp500', 'nasdaq100', 'russell2000']

    def test_presets_have_labels_and_plausible_sizes(self):
        presets = {p['key']: p for p in load_identifier_presets()['presets']}
        assert presets['sp500']['label'] == 'S&P 500'
        assert 480 <= len(presets['sp500']['identifiers']) <= 520
        assert 90 <= len(presets['nasdaq100']['identifiers']) <= 110
        assert 1500 <= len(presets['russell2000']['identifiers']) <= 2100

    def test_known_members_present(self):
        presets = {p['key']: p for p in load_identifier_presets()['presets']}
        assert 'AAPL' in presets['sp500']['identifiers']
        assert 'NVDA' in presets['nasdaq100']['identifiers']


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
