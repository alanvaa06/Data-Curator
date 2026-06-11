"""
Local HTML editor for the Data Curator JSON configuration.

Exposes pure config helpers (defaults, load, validate, save, catalog) plus a stdlib
http.server that serves a self-contained editor page bound to localhost.
"""

import datetime
import http.server
import importlib.resources
import json
import pathlib
import re
import socket
import subprocess
import sys
import threading
import time
import typing
import webbrowser

from kaxanuk.data_curator import __parameters_format_version__
from kaxanuk.data_curator.config_handlers.column_catalog import (
    load_catalog,
    load_identifier_presets,
)
from kaxanuk.data_curator.config_handlers.configurator_interface import ConfiguratorInterface
from kaxanuk.data_curator.entities.configuration import (
    CONFIGURATION_COLUMN_PREFIXES,
    CONFIGURATION_PERIODS,
)


HOST = '127.0.0.1'
DEFAULT_PORT = 8753
OUTPUT_FORMATS = ('csv', 'duckdb', 'parquet')
CONFIG_FILENAME = 'data_curator_parameters.json'
PAGE_RESOURCE = 'config_editor_page.html'
RUN_TARGET_DEFAULT = '__main__.py'
RUN_OUTPUT_MAX_CHARS = 20_000
# data provider APIs pass keys as URL query parameters, which end up in logged URLs
_API_KEY_PATTERN = re.compile(r'(api[_-]?key=)[^&\s"\']+', re.IGNORECASE)


def _redact_api_keys(text: str) -> str:
    return _API_KEY_PATTERN.sub(r'\1***', text)

_run_lock = threading.Lock()
_RUN_STATE_IDLE: dict[str, typing.Any] = {
    'state': 'idle',
    'output': '',
    'returncode': None,
    'started_at': None,
    'finished_at': None,
}
_run_state: dict[str, typing.Any] = dict(_RUN_STATE_IDLE)

API_KEY_ENV_VARS = (
    'KNDC_API_KEY_FMP',
    'KNDC_API_KEY_LSEG',
)

REQUIRED_GENERAL_KEYS = (
    'market_data_provider',
    'fundamental_data_provider',
    'start_date',
    'end_date',
    'period',
    'output_format',
    'logger_level',
)


def build_default_config() -> dict[str, typing.Any]:
    """Return the default configuration payload."""
    columns = [
        column
        for group in load_catalog()['groups']
        for column in group['columns']
    ]

    return {
        'parameters_format_version': __parameters_format_version__,
        'general': {
            'market_data_provider': 'financial_modeling_prep',
            'fundamental_data_provider': 'financial_modeling_prep',
            'start_date': '1990-01-01',
            'end_date': '2025-12-31',
            'period': 'quarterly',
            'output_format': 'csv',
            'logger_level': 'info',
            'output_directory': 'Output',
        },
        'identifiers': [],
        'columns': columns,
    }


def load_config(config_path: pathlib.Path | str) -> dict[str, typing.Any]:
    """Load the config file, or the defaults when it is absent."""
    path = pathlib.Path(config_path)
    if not path.is_file():

        return build_default_config()

    return json.loads(
        path.read_text(encoding='utf-8')
    )


def build_catalog_response() -> dict[str, typing.Any]:
    """Return the column catalog plus the valid option lists for the editor."""
    catalog = load_catalog()

    return {
        'groups': catalog['groups'],
        'identifier_presets': load_identifier_presets()['presets'],
        'options': {
            'market_data_provider': list(ConfiguratorInterface.CONFIGURATION_PROVIDERS_MARKET),
            'fundamental_data_provider': list(ConfiguratorInterface.CONFIGURATION_PROVIDERS_FUNDAMENTAL),
            'period': list(CONFIGURATION_PERIODS),
            'output_format': list(OUTPUT_FORMATS),
            'logger_level': list(ConfiguratorInterface.CONFIGURATION_LOGGER_LEVELS),
        },
    }


def validate_config_payload(payload: typing.Any) -> list[str]:
    """Return a list of human-readable validation errors (empty when valid)."""
    errors: list[str] = []
    if not isinstance(payload, dict):

        return ["Configuration must be a JSON object"]

    general = payload.get('general')
    if not isinstance(general, dict):
        errors.append("Missing 'general' section")
        general = {}

    errors.extend(
        f"Missing general parameter: {key}"
        for key in REQUIRED_GENERAL_KEYS
        if key not in general
    )

    options = build_catalog_response()['options']
    for key, valid in options.items():
        if key in general and general[key] not in valid:
            errors.append(f"Invalid {key}: {general[key]}")

    if 'output_directory' in general and (
        not isinstance(general['output_directory'], str)
        or not general['output_directory'].strip()
    ):
        errors.append("Invalid output_directory: must be a non-empty folder path")

    start = _try_date(general.get('start_date'))
    end = _try_date(general.get('end_date'))
    if 'start_date' in general and start is None:
        errors.append("Invalid start_date, expecting YYYY-MM-DD")
    if 'end_date' in general and end is None:
        errors.append("Invalid end_date, expecting YYYY-MM-DD")
    if start is not None and end is not None and start > end:
        errors.append("start_date must not be after end_date")

    identifiers = payload.get('identifiers')
    if (
        not isinstance(identifiers, list)
        or any(not isinstance(i, str) or not i for i in identifiers)
    ):
        errors.append("identifiers must be a list of non-empty strings")

    columns = payload.get('columns')
    if (
        not isinstance(columns, list)
        or any(not isinstance(c, str) for c in columns)
    ):
        errors.append("columns must be a list of strings")
    else:
        valid_prefixes = tuple(p + '_' for p in CONFIGURATION_COLUMN_PREFIXES)
        bad = [c for c in columns if not c.startswith(valid_prefixes)]
        if bad:
            errors.append("Invalid column prefixes: " + ", ".join(bad))

    return errors


def save_config(
    config_path: pathlib.Path | str,
    payload: typing.Any
) -> None:
    """
    Validate and write the configuration payload.

    Raises
    ------
    ValueError
        When the payload fails validation.
    """
    errors = validate_config_payload(payload)
    if errors:

        raise ValueError("; ".join(errors))

    pathlib.Path(config_path).write_text(
        json.dumps(payload, indent=2) + '\n',
        encoding='utf-8',
    )


def _parse_env_lines(env_path: pathlib.Path) -> list[str]:
    if not env_path.is_file():

        return []

    return env_path.read_text(encoding='utf-8').splitlines()


def read_env_status(env_path: pathlib.Path | str) -> list[dict[str, typing.Any]]:
    """
    Report which API key environment variables are set in the .env file.

    Never returns the values themselves, only whether each is non-empty.
    """
    values: dict[str, str] = {}
    for line in _parse_env_lines(pathlib.Path(env_path)):
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and '=' in stripped:
            name, _, value = stripped.partition('=')
            values[name.strip()] = value.strip()

    return [
        {'name': name, 'set': bool(values.get(name))}
        for name in API_KEY_ENV_VARS
    ]


def save_env_values(
    env_path: pathlib.Path | str,
    updates: dict[str, str],
) -> None:
    """
    Write API key values into the .env file, preserving any other content.

    Raises
    ------
    ValueError
        On unknown variable names or values containing line breaks.
    """
    for name, value in updates.items():
        if name not in API_KEY_ENV_VARS:
            msg = f"Unknown environment variable: {name}"

            raise ValueError(msg)
        if '\n' in value or '\r' in value:
            msg = f"Invalid value for {name}"

            raise ValueError(msg)

    env_path = pathlib.Path(env_path)
    lines = _parse_env_lines(env_path)
    remaining = dict(updates)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and '=' in stripped:
            name = stripped.partition('=')[0].strip()
            if name in remaining:
                lines[index] = f"{name}={remaining.pop(name)}"

    lines.extend(f"{name}={value}" for name, value in remaining.items())
    env_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _try_date(value: typing.Any) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):

        return None


def get_run_status() -> dict[str, typing.Any]:
    """
    Return a snapshot of the current pipeline run state.

    While a run is active (or after it finishes) the snapshot includes the
    'elapsed' seconds since it started.
    """
    with _run_lock:
        snapshot = dict(_run_state)

    if snapshot['started_at'] is None:
        snapshot['elapsed'] = None
    else:
        end = snapshot['finished_at'] if snapshot['finished_at'] is not None else time.time()
        snapshot['elapsed'] = round(end - snapshot['started_at'], 1)

    for internal_key in ('started_at', 'finished_at'):
        del snapshot[internal_key]

    return snapshot


def reset_run_state() -> None:
    """Reset the pipeline run state to idle (mainly for tests)."""
    with _run_lock:
        _run_state.update(_RUN_STATE_IDLE)


def start_pipeline_run(
    entry_script: pathlib.Path | str,
) -> bool:
    """
    Run the entry script in a background thread, capturing its output.

    Parameters
    ----------
    entry_script
        The script to execute

    Returns
    -------
    True when a new run was started; False when one is already running or the
    entry script is missing (state set to 'failed' in that case).
    """
    entry_path = pathlib.Path(entry_script)

    with _run_lock:
        if _run_state['state'] == 'running':

            return False

        if not entry_path.is_file():
            _run_state.update(
                state='failed',
                output=f"Entry script not found: {entry_path}",
                returncode=None,
                started_at=None,
                finished_at=None,
            )

            return False

        _run_state.update(
            state='running',
            output='',
            returncode=None,
            started_at=time.time(),
            finished_at=None,
        )

    def _worker() -> None:
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(entry_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        output = (result.stdout or '')
        if result.stderr:
            output += ('\n' if output else '') + result.stderr
        with _run_lock:
            _run_state.update(
                state='done' if result.returncode == 0 else 'failed',
                output=_redact_api_keys(output[-RUN_OUTPUT_MAX_CHARS:]),
                returncode=result.returncode,
                finished_at=time.time(),
            )

    threading.Thread(target=_worker, daemon=True).start()

    return True


def _read_page() -> str:
    resource = importlib.resources.files(
        'kaxanuk.data_curator.services'
    ).joinpath(PAGE_RESOURCE)

    return resource.read_text(encoding='utf-8')


class _PanelServer(http.server.HTTPServer):
    """
    HTTPServer with exclusive port binding on Windows.

    The stdlib default sets SO_REUSEADDR, which on Windows silently allows two
    servers to bind the same port — the second instance must fail loudly instead.
    """

    def server_bind(self) -> None:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.allow_reuse_address = False
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def build_server(
    config_path: pathlib.Path | str,
    port: int = DEFAULT_PORT,
    entry_script: pathlib.Path | str = RUN_TARGET_DEFAULT,
) -> http.server.HTTPServer:
    """Build (but do not start) the editor HTTP server bound to localhost."""
    config_file = pathlib.Path(config_path)
    run_target = pathlib.Path(entry_script)

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args: typing.Any) -> None:
            pass

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, data: typing.Any) -> None:
            self._send(status, json.dumps(data).encode('utf-8'), 'application/json')

        def do_GET(self) -> None:
            if self.path in ('/', '/index.html'):
                # read per request so server restarts are never needed to pick up page updates
                self._send(200, _read_page().encode('utf-8'), 'text/html; charset=utf-8')
            elif self.path == '/api/config':
                self._send_json(200, load_config(config_file))
            elif self.path == '/api/catalog':
                self._send_json(200, build_catalog_response())
            elif self.path == '/api/run':
                self._send_json(200, get_run_status())
            elif self.path == '/api/env':
                self._send_json(200, read_env_status(config_file.parent / '.env'))
            else:
                self._send_json(404, {'error': 'not found'})

        def do_POST(self) -> None:
            if self.path == '/api/config':
                length = int(self.headers.get('Content-Length', 0))
                raw = self.rfile.read(length)
                try:
                    payload = json.loads(raw.decode('utf-8'))
                except json.JSONDecodeError:
                    self._send_json(400, {'errors': ['Invalid JSON']})

                    return

                try:
                    save_config(config_file, payload)
                except ValueError as error:
                    self._send_json(400, {'errors': str(error).split('; ')})

                    return

                self._send_json(200, {'status': 'saved'})
            elif self.path == '/api/run':
                if start_pipeline_run(run_target):
                    self._send_json(200, {'status': 'started'})
                else:
                    status = get_run_status()
                    code = 409 if status['state'] == 'running' else 400
                    self._send_json(code, status)
            elif self.path == '/api/env':
                length = int(self.headers.get('Content-Length', 0))
                raw = self.rfile.read(length)
                try:
                    payload = json.loads(raw.decode('utf-8'))
                    if not isinstance(payload, dict):
                        msg = "Expected a JSON object"

                        raise ValueError(msg)
                    save_env_values(config_file.parent / '.env', payload)
                except (json.JSONDecodeError, ValueError) as error:
                    self._send_json(400, {'errors': [str(error)]})

                    return

                self._send_json(200, {'status': 'saved'})
            else:
                self._send_json(404, {'error': 'not found'})

    return _PanelServer((HOST, port), Handler)


def serve(
    config_path: pathlib.Path | str,
    port: int = DEFAULT_PORT,
    *,
    open_browser: bool = True,
    entry_script: pathlib.Path | str = RUN_TARGET_DEFAULT,
) -> None:
    """Start the editor server and block until interrupted."""
    server = build_server(config_path, port=port, entry_script=entry_script)
    url = f"http://{HOST}:{server.server_address[1]}"
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
