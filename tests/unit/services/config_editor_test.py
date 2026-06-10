import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from kaxanuk.data_curator.services import config_editor


def _wait_for_run_completion(timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = config_editor.get_run_status()
        if status['state'] in ('done', 'failed'):
            return status
        time.sleep(0.1)
    return config_editor.get_run_status()


def test_build_default_config_has_required_shape():
    config = config_editor.build_default_config()
    assert set(config) >= {'parameters_format_version', 'general', 'identifiers', 'columns'}
    assert config['general']['market_data_provider']
    assert isinstance(config['identifiers'], list)
    assert isinstance(config['columns'], list)


def test_load_config_returns_defaults_when_missing(tmp_path):
    config = config_editor.load_config(tmp_path / 'absent.json')
    assert config == config_editor.build_default_config()


def test_load_config_reads_existing_file(tmp_path):
    path = tmp_path / 'data_curator_parameters.json'
    payload = config_editor.build_default_config()
    payload['identifiers'] = ['AAPL']
    path.write_text(json.dumps(payload), encoding='utf-8')
    assert config_editor.load_config(path)['identifiers'] == ['AAPL']


def test_validate_accepts_valid_payload():
    assert config_editor.validate_config_payload(config_editor.build_default_config()) == []


def test_validate_flags_bad_provider():
    payload = config_editor.build_default_config()
    payload['general']['market_data_provider'] = 'made_up'
    errors = config_editor.validate_config_payload(payload)
    assert any('market_data_provider' in e for e in errors)


def test_validate_flags_bad_date_order():
    payload = config_editor.build_default_config()
    payload['general']['start_date'] = '2025-01-01'
    payload['general']['end_date'] = '2000-01-01'
    errors = config_editor.validate_config_payload(payload)
    assert any('date' in e.lower() for e in errors)


def test_validate_flags_non_list_identifiers():
    payload = config_editor.build_default_config()
    payload['identifiers'] = 'AAPL'
    assert config_editor.validate_config_payload(payload)


def test_save_writes_valid_payload(tmp_path):
    path = tmp_path / 'data_curator_parameters.json'
    payload = config_editor.build_default_config()
    config_editor.save_config(path, payload)
    assert json.loads(path.read_text(encoding='utf-8'))['general']['period'] == 'quarterly'


def test_save_rejects_invalid_payload(tmp_path):
    path = tmp_path / 'data_curator_parameters.json'
    payload = config_editor.build_default_config()
    payload['general']['period'] = 'weekly'
    with pytest.raises(ValueError):
        config_editor.save_config(path, payload)


def test_build_catalog_response_has_options_and_groups():
    response = config_editor.build_catalog_response()
    assert response['groups']
    assert 'financial_modeling_prep' in response['options']['market_data_provider']
    assert 'none' in response['options']['fundamental_data_provider']
    assert 'quarterly' in response['options']['period']
    assert 'csv' in response['options']['output_format']
    assert 'info' in response['options']['logger_level']


def test_build_catalog_response_includes_identifier_presets():
    response = config_editor.build_catalog_response()
    presets = {p['key']: p for p in response['identifier_presets']}
    assert 'sp500' in presets
    assert len(presets['russell2000']['identifiers']) > 1000


def _run_server(server):
    server.serve_forever()


def _start(tmp_path, entry=None):
    config_path = tmp_path / config_editor.CONFIG_FILENAME
    kwargs = {} if entry is None else {'entry_script': entry}
    server = config_editor.build_server(config_path, port=0, **kwargs)
    thread = threading.Thread(target=_run_server, args=(server,), daemon=True)
    thread.start()
    port = server.server_address[1]
    return server, f'http://127.0.0.1:{port}'


def _post_empty(url):
    request = urllib.request.Request(url, data=b'', method='POST')
    try:
        with urllib.request.urlopen(request) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def _get(url):
    with urllib.request.urlopen(url) as response:
        return response.status, response.read().decode('utf-8')


def _post(url, data):
    request = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def test_server_serves_page(tmp_path):
    server, base = _start(tmp_path)
    try:
        status, body = _get(base + '/')
        assert status == 200
        assert '<html' in body.lower() or '<!doctype' in body.lower()
    finally:
        server.shutdown()


def test_server_returns_config_and_catalog(tmp_path):
    server, base = _start(tmp_path)
    try:
        status, body = _get(base + '/api/config')
        assert status == 200
        assert 'general' in json.loads(body)
        status, body = _get(base + '/api/catalog')
        assert 'groups' in json.loads(body)
    finally:
        server.shutdown()


def test_server_saves_valid_config(tmp_path):
    server, base = _start(tmp_path)
    try:
        payload = config_editor.build_default_config()
        payload['identifiers'] = ['AAPL']
        assert _post(base + '/api/config', payload) == 200
        saved = json.loads((tmp_path / config_editor.CONFIG_FILENAME).read_text(encoding='utf-8'))
        assert saved['identifiers'] == ['AAPL']
    finally:
        server.shutdown()


def test_server_rejects_invalid_config(tmp_path):
    server, base = _start(tmp_path)
    try:
        payload = config_editor.build_default_config()
        payload['general']['period'] = 'weekly'
        assert _post(base + '/api/config', payload) == 400
    finally:
        server.shutdown()


class TestRunEndpoints:
    def test_post_run_executes_entry_script(self, tmp_path):
        config_editor.reset_run_state()
        entry = tmp_path / 'entry.py'
        entry.write_text("print('pipeline ok')", encoding='utf-8')
        server, base = _start(tmp_path, entry=entry)
        try:
            assert _post_empty(base + '/api/run') == 200
            status = _wait_for_run_completion()
            assert status['state'] == 'done'
            body = json.loads(_get(base + '/api/run')[1])
            assert 'pipeline ok' in body['output']
        finally:
            server.shutdown()

    def test_post_run_missing_entry_returns_400(self, tmp_path):
        config_editor.reset_run_state()
        server, base = _start(tmp_path, entry=tmp_path / 'missing.py')
        try:
            assert _post_empty(base + '/api/run') == 400
        finally:
            server.shutdown()

    def test_get_run_returns_idle_status(self, tmp_path):
        config_editor.reset_run_state()
        server, base = _start(tmp_path)
        try:
            status, body = _get(base + '/api/run')
            assert status == 200
            assert json.loads(body)['state'] == 'idle'
        finally:
            server.shutdown()

    def test_page_has_run_controls(self, tmp_path):
        server, base = _start(tmp_path)
        try:
            _, body = _get(base + '/')
            assert 'Save &amp; run' in body
            assert '/api/run' in body
        finally:
            server.shutdown()

    def test_page_explains_server_requirement_when_offline(self, tmp_path):
        server, base = _start(tmp_path)
        try:
            _, body = _get(base + '/')
            assert 'needs the Data Curator server' in body
            assert 'catch' in body
        finally:
            server.shutdown()

    def test_page_read_per_request_not_cached(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config_editor, '_read_page', lambda: '<html>version one</html>')
        server, base = _start(tmp_path)
        try:
            _, body = _get(base + '/')
            assert 'version one' in body
            monkeypatch.setattr(config_editor, '_read_page', lambda: '<html>version two</html>')
            _, body = _get(base + '/')
            assert 'version two' in body
        finally:
            server.shutdown()


class TestRunManager:
    def test_run_executes_script_and_captures_output(self, tmp_path):
        config_editor.reset_run_state()
        script = tmp_path / 'entry.py'
        script.write_text("print('hello run')", encoding='utf-8')
        assert config_editor.start_pipeline_run(script) is True
        status = _wait_for_run_completion()
        assert status['state'] == 'done'
        assert 'hello run' in status['output']
        assert status['returncode'] == 0

    def test_run_missing_script_fails_immediately(self, tmp_path):
        config_editor.reset_run_state()
        assert config_editor.start_pipeline_run(tmp_path / 'missing.py') is False
        assert config_editor.get_run_status()['state'] == 'failed'

    def test_run_failure_reports_failed_state(self, tmp_path):
        config_editor.reset_run_state()
        script = tmp_path / 'entry.py'
        script.write_text("import sys; print('boom'); sys.exit(3)", encoding='utf-8')
        assert config_editor.start_pipeline_run(script) is True
        status = _wait_for_run_completion()
        assert status['state'] == 'failed'
        assert status['returncode'] == 3

    def test_concurrent_run_rejected(self, tmp_path):
        config_editor.reset_run_state()
        script = tmp_path / 'entry.py'
        script.write_text("import time; time.sleep(1.5); print('slow done')", encoding='utf-8')
        assert config_editor.start_pipeline_run(script) is True
        assert config_editor.start_pipeline_run(script) is False
        status = _wait_for_run_completion()
        assert status['state'] == 'done'
