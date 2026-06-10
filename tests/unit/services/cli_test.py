import json
import pathlib

from click.testing import CliRunner

from kaxanuk.data_curator.services import cli as cli_module


def _repo_templates():
    return pathlib.Path(cli_module.__file__).resolve().parents[4] / 'templates' / 'data_curator'


def _fake_serve(calls):
    def fake(config_path, port=8753, *, open_browser=True, entry_script='__main__.py'):
        calls['config_path'] = str(config_path)
        calls['open_browser'] = open_browser
        calls['entry_script'] = str(entry_script)
    return fake


def test_config_editor_invokes_serve(monkeypatch, tmp_path):
    calls = {}
    monkeypatch.setattr(cli_module.config_editor, 'serve', _fake_serve(calls))
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
    monkeypatch.setattr(cli_module, '_find_templates_dir', lambda: str(_repo_templates()))

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli_module.cli, ['init', 'json'])
        assert result.exit_code == 0, result.output
        assert pathlib.Path('Config/data_curator_parameters.json').is_file()
        assert pathlib.Path('Config/custom_calculations.py').is_file()
        assert pathlib.Path('__main__.py').is_file()
        assert not pathlib.Path('Config/data_curator_parameters.xlsx').is_file()


def test_start_scaffolds_missing_workspace_and_serves(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_module, '_find_templates_dir', lambda: str(_repo_templates()))
    calls = {}
    monkeypatch.setattr(cli_module.config_editor, 'serve', _fake_serve(calls))

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli_module.cli, ['start', '--no-browser'])
        assert result.exit_code == 0, result.output
        assert pathlib.Path('Config/data_curator_parameters.json').is_file()
        assert pathlib.Path('Config/custom_calculations.py').is_file()
        assert pathlib.Path('__main__.py').is_file()
        assert pathlib.Path('Output').is_dir()
    assert calls['config_path'].endswith('data_curator_parameters.json')
    assert calls['entry_script'].endswith('__main__.py')
    assert calls['open_browser'] is False


def test_start_preserves_existing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_module, '_find_templates_dir', lambda: str(_repo_templates()))
    calls = {}
    monkeypatch.setattr(cli_module.config_editor, 'serve', _fake_serve(calls))

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        pathlib.Path('Config').mkdir()
        custom_config = {'custom': True}
        pathlib.Path('Config/data_curator_parameters.json').write_text(
            json.dumps(custom_config), encoding='utf-8'
        )
        pathlib.Path('__main__.py').write_text('# my custom entry\n', encoding='utf-8')

        result = runner.invoke(cli_module.cli, ['start', '--no-browser'])
        assert result.exit_code == 0, result.output
        saved = json.loads(pathlib.Path('Config/data_curator_parameters.json').read_text(encoding='utf-8'))
        assert saved == custom_config
        assert pathlib.Path('__main__.py').read_text(encoding='utf-8') == '# my custom entry\n'
