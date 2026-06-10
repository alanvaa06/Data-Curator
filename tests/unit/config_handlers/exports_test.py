from kaxanuk.data_curator import config_handlers


def test_json_configurator_is_exported():
    assert hasattr(config_handlers, 'JsonConfigurator')
    assert 'JsonConfigurator' in config_handlers.__all__


def test_excel_configurator_removed():
    assert not hasattr(config_handlers, 'ExcelConfigurator')
    assert 'ExcelConfigurator' not in config_handlers.__all__
