from click.testing import CliRunner

from kaxanuk.data_curator.services import cli as cli_module


def test_config_editor_invokes_serve(monkeypatch, tmp_path):
    calls = {}

    def fake_serve(config_path, port=8753, *, open_browser=True):
        calls['config_path'] = str(config_path)
        calls['open_browser'] = open_browser

    monkeypatch.setattr(cli_module.config_editor, 'serve', fake_serve)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli_module.cli,
            ['config-editor', '--no-browser'],
        )
    assert result.exit_code == 0, result.output
    assert calls['open_browser'] is False
    assert calls['config_path'].endswith('data_curator_parameters.json')


def test_init_json_scaffolds_files(tmp_path, monkeypatch):
    import pathlib

    templates = pathlib.Path(cli_module.__file__).resolve().parents[4] / 'templates' / 'data_curator'
    monkeypatch.setattr(cli_module, '_find_templates_dir', lambda: str(templates))

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli_module.cli, ['init', 'json'])
        assert result.exit_code == 0, result.output
        assert pathlib.Path('Config/data_curator_parameters.json').is_file()
        assert pathlib.Path('Config/custom_calculations.py').is_file()
        assert pathlib.Path('__main__.py').is_file()
        assert not pathlib.Path('Config/data_curator_parameters.xlsx').is_file()
