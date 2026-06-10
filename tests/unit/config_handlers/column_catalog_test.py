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
