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
import urllib.parse
import webbrowser

import httpx

from kaxanuk.data_curator import __parameters_format_version__
from kaxanuk.data_curator.config_handlers._resolver import resolve_macro_requests
from kaxanuk.data_curator.data_providers import (
    BanxicoSie,
    Dbnomics,
    Fred,
    Inegi,
)
from kaxanuk.data_curator.config_handlers.column_catalog import (
    load_catalog,
    load_etf_catalog,
    load_identifier_presets,
    load_macro_catalog,
    load_mx_fund_catalog,
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
CUSTOM_LISTS_FILENAME = 'identifier_lists.json'
PAGE_RESOURCE = 'config_editor_page.html'
RUN_TARGET_DEFAULT = '__main__.py'
RUN_OUTPUT_MAX_CHARS = 20_000
# data provider APIs pass keys as URL query parameters, which end up in logged URLs
_API_KEY_PATTERN = re.compile(
    # query-string forms (api_key=, apikey=, token=) and header forms (Bmx-Token:, Authorization:)
    r'((?:api[_-]?key|token)=|(?:bmx-token|authorization)\s*:\s*)[^&\s"\']+',
    re.IGNORECASE,
)


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
# Out-of-band run controls, guarded by _run_lock and mutated in place (never
# rebound) so no module-level `global` is needed: 'process' is the live pipeline
# subprocess (None when no run is active) and 'stop_requested' lets the worker
# report 'stopped' rather than 'failed' after a user-initiated stop.
_run_control: dict[str, typing.Any] = {'process': None, 'stop_requested': False}

API_KEY_ENV_VARS = (
    'KNDC_API_KEY_FMP',
    'KNDC_API_KEY_LSEG',
    'KNDC_API_KEY_FRED',
    'KNDC_API_KEY_BANXICO',
    'KNDC_API_KEY_INEGI',
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


# Display names for the macro catalog's region codes, so the column picker can
# group the e_ columns into one collapsible section per country/area.
REGION_NAMES: dict[str, str] = {
    'US': 'United States', 'MX': 'Mexico', 'EZ': 'Euro area',
    'DE': 'Germany', 'FR': 'France', 'IT': 'Italy', 'ES': 'Spain',
    'NL': 'Netherlands', 'BE': 'Belgium', 'AT': 'Austria', 'IE': 'Ireland',
    'GR': 'Greece', 'PT': 'Portugal', 'FI': 'Finland', 'UK': 'United Kingdom',
    'CA': 'Canada', 'JP': 'Japan', 'CN': 'China', 'IN': 'India', 'BR': 'Brazil',
    'KR': 'South Korea', 'AU': 'Australia', 'CH': 'Switzerland', 'SE': 'Sweden',
    'NO': 'Norway', 'DK': 'Denmark', 'PL': 'Poland', 'CZ': 'Czechia',
    'HU': 'Hungary', 'RU': 'Russia', 'ZA': 'South Africa', 'ID': 'Indonesia',
    'TR': 'Turkey', 'SA': 'Saudi Arabia', 'CL': 'Chile', 'CO': 'Colombia',
    'PE': 'Peru', 'HK': 'Hong Kong', 'NZ': 'New Zealand', 'IL': 'Israel',
    'TH': 'Thailand', 'MY': 'Malaysia', 'PH': 'Philippines', 'AR': 'Argentina',
}


def _build_macro_group() -> dict[str, typing.Any]:
    """
    Build a single ``Economic (macro)`` catalog group whose columns are nested
    into one collapsible subgroup per country/area.

    The two-level shape (one Economic set → country subsets → columns) keeps the
    picker navigable now that the catalog spans dozens of economies and ~59
    indicators each. Routing is unchanged (by column name, not group); subgroups
    are ordered by region code.
    """
    macro_rows = load_macro_catalog()
    by_region: dict[str, list[dict[str, typing.Any]]] = {}
    for row in macro_rows:
        by_region.setdefault(row['region'], []).append(row)

    subgroups: list[dict[str, typing.Any]] = []
    for region in sorted(by_region):
        rows = by_region[region]
        name = REGION_NAMES.get(region, region)
        subgroups.append({
            'label': f'{name} ({region})',
            'columns': [row['column'] for row in rows],
            'column_labels': {row['column']: row['name'] for row in rows},
        })

    return {
        'prefix': 'e_',
        'label': 'Economic (macro)',
        'subgroups': subgroups,
    }


def build_catalog_response() -> dict[str, typing.Any]:
    """Return the column catalog plus the valid option lists for the editor."""
    catalog = load_catalog()
    groups = [*catalog['groups'], _build_macro_group()]

    return {
        'groups': groups,
        'identifier_presets': load_identifier_presets()['presets'],
        'etf_groups': load_etf_catalog()['groups'],
        'mx_fund_groups': load_mx_fund_catalog()['groups'],
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


def read_custom_lists(lists_path: pathlib.Path | str) -> list[dict[str, typing.Any]]:
    """
    Read the user's saved identifier lists.

    Returns an empty list when the file is absent or malformed, so a corrupt file
    never blocks the editor from loading.
    """
    path = pathlib.Path(lists_path)
    if not path.is_file():

        return []

    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):

        return []

    lists = data.get('lists') if isinstance(data, dict) else None
    if not isinstance(lists, list):

        return []

    return [
        {'name': entry['name'], 'identifiers': entry['identifiers']}
        for entry in lists
        if isinstance(entry, dict)
        and isinstance(entry.get('name'), str)
        and isinstance(entry.get('identifiers'), list)
    ]


def _validate_custom_list(name: typing.Any, identifiers: typing.Any) -> str:
    """Return a validated, stripped name or raise ValueError on bad input."""
    if not isinstance(name, str) or not name.strip():
        msg = "List name must be a non-empty string"

        raise ValueError(msg)
    if (
        not isinstance(identifiers, list)
        or any(not isinstance(i, str) or not i.strip() for i in identifiers)
    ):
        msg = "identifiers must be a list of non-empty strings"

        raise ValueError(msg)

    return name.strip()


def save_custom_list(
    lists_path: pathlib.Path | str,
    name: typing.Any,
    identifiers: typing.Any,
) -> list[dict[str, typing.Any]]:
    """
    Upsert a named identifier list by name and persist the file.

    Returns the full list collection after the change.

    Raises
    ------
    ValueError
        When the name is empty or identifiers are not a list of non-empty strings.
    """
    clean_name = _validate_custom_list(name, identifiers)
    clean_ids = [i.strip() for i in identifiers]

    path = pathlib.Path(lists_path)
    lists = read_custom_lists(path)
    lists = [entry for entry in lists if entry['name'] != clean_name]
    lists.append({'name': clean_name, 'identifiers': clean_ids})

    path.write_text(
        json.dumps({'lists': lists}, indent=2) + '\n',
        encoding='utf-8',
    )

    return lists


def delete_custom_list(
    lists_path: pathlib.Path | str,
    name: typing.Any,
) -> list[dict[str, typing.Any]]:
    """
    Remove a named identifier list and persist the file (no-op when absent).

    Returns the full list collection after the change.

    Raises
    ------
    ValueError
        When the name is not a non-empty string.
    """
    if not isinstance(name, str) or not name.strip():
        msg = "List name must be a non-empty string"

        raise ValueError(msg)

    clean_name = name.strip()
    path = pathlib.Path(lists_path)
    lists = read_custom_lists(path)
    remaining = [entry for entry in lists if entry['name'] != clean_name]
    if len(remaining) != len(lists):
        path.write_text(
            json.dumps({'lists': remaining}, indent=2) + '\n',
            encoding='utf-8',
        )

    return remaining


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
        _run_control.update(process=None, stop_requested=False)


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
        _run_control.update(process=None, stop_requested=False)

    def _worker() -> None:
        proc = subprocess.Popen(  # noqa: S603
            [sys.executable, str(entry_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # Publish the handle so stop_pipeline_run() can reach it, and honor a stop
        # that arrived in the window before the process existed.
        with _run_lock:
            _run_control['process'] = proc
            stop_now = _run_control['stop_requested']
        if stop_now:
            proc.terminate()

        out, err = proc.communicate()
        output = (out or '')
        if err:
            output += ('\n' if output else '') + err
        with _run_lock:
            stopped = _run_control['stop_requested']
            _run_control['process'] = None
            if stopped:
                final_state = 'stopped'
            elif proc.returncode == 0:
                final_state = 'done'
            else:
                final_state = 'failed'
            _run_state.update(
                state=final_state,
                output=_redact_api_keys(output[-RUN_OUTPUT_MAX_CHARS:]),
                returncode=proc.returncode,
                finished_at=time.time(),
            )

    threading.Thread(target=_worker, daemon=True).start()

    return True


def stop_pipeline_run() -> bool:
    """
    Request termination of the active pipeline run.

    Returns
    -------
    True when a running process was signalled to stop; False when no run is
    currently active.
    """
    with _run_lock:
        if _run_state['state'] != 'running':

            return False

        _run_control['stop_requested'] = True
        proc = _run_control['process']

    if proc is not None:
        proc.terminate()

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


_SERIES_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'
_MACRO_KEY_ENV = {
    'banxico_sie': 'KNDC_API_KEY_BANXICO',
    'inegi': 'KNDC_API_KEY_INEGI',
    'fred': 'KNDC_API_KEY_FRED',
}
_MACRO_PROVIDER_CLASSES: dict[str, typing.Any] = {
    'dbnomics': Dbnomics,
    'banxico_sie': BanxicoSie,
    'inegi': Inegi,
    'fred': Fred,
}


def _env_value(env_path: pathlib.Path, name: str) -> str | None:
    """Read a single variable's value from a .env file, or None when absent."""
    try:
        lines = env_path.read_text(encoding='utf-8').splitlines()
    except OSError:

        return None

    prefix = f'{name}='
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(prefix):
            value = stripped[len(prefix):].strip()

            return value or None

    return None


def _ticker_series(symbol: str) -> dict[str, typing.Any]:
    """Daily closes for an equity/ETF symbol from Yahoo Finance (keyless)."""
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}'
    response = httpx.get(
        url,
        params={'range': '5y', 'interval': '1d'},
        headers={'User-Agent': _SERIES_UA},
        timeout=30.0,
    )
    response.raise_for_status()
    result = response.json()['chart']['result'][0]
    timestamps = result['timestamp']
    closes = result['indicators']['quote'][0]['close']
    points = [
        {
            'time': datetime.datetime.fromtimestamp(stamp, datetime.UTC).date().isoformat(),
            'value': round(float(close), 4),
        }
        for stamp, close in zip(timestamps, closes, strict=False)
        if close is not None
    ]

    return {'points': points, 'label': symbol, 'kind': 'price'}


def _macro_series(column: str, env_path: pathlib.Path) -> dict[str, typing.Any]:
    """A macro (e_*) series as (date, value) points, via the curator's own providers."""
    requests = resolve_macro_requests([column])
    if not requests:
        msg = f'{column} is not a known macro column'

        raise ValueError(msg)

    provider_name, pairs = next(iter(requests.items()))
    series_id = pairs[0][1]
    key_env = _MACRO_KEY_ENV.get(provider_name)
    api_key = _env_value(env_path, key_env) if key_env else None
    if key_env and not api_key:
        msg = f'{column} needs {key_env} set in the panel API keys'

        raise ValueError(msg)

    provider = _MACRO_PROVIDER_CLASSES[provider_name](api_key=api_key)
    end_date = datetime.datetime.now(datetime.UTC).date()
    start_date = datetime.date(2000, 1, 1)
    fetched = provider.get_economic_data(series_ids=[series_id], start_date=start_date, end_date=end_date)
    series = fetched.get(series_id)
    points = (
        [
            {'time': iso, 'value': round(float(row.value), 6)}
            for iso, row in series.rows.items()
            if row.value is not None
        ]
        if series is not None
        else []
    )

    return {'points': points, 'label': series.series_name if series else column, 'kind': 'macro'}


def build_series_response(query: str, env_path: pathlib.Path) -> tuple[int, dict[str, typing.Any]]:
    """Resolve a /api/series query (?symbol= or ?macro=) into a chart payload."""
    params = urllib.parse.parse_qs(query)
    symbol = (params.get('symbol') or [''])[0].strip()
    macro = (params.get('macro') or [''])[0].strip()
    try:
        if symbol:

            return 200, _ticker_series(symbol)
        if macro:

            return 200, _macro_series(macro, env_path)
    except (httpx.HTTPError, ValueError, LookupError, KeyError, TypeError) as error:

        return 400, {'error': str(error)}

    return 400, {'error': 'pass ?symbol= or ?macro='}


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
            elif self.path == '/api/lists':
                self._send_json(200, {'lists': read_custom_lists(config_file.parent / CUSTOM_LISTS_FILENAME)})
            elif self.path.startswith('/api/series'):
                query = urllib.parse.urlsplit(self.path).query
                status, payload = build_series_response(query, config_file.parent / '.env')
                self._send_json(status, payload)
            else:
                self._send_json(404, {'error': 'not found'})

        def do_POST(self) -> None:
            # DNS-rebinding / CSRF defense: state-changing requests must carry a loopback Host.
            # The panel binds to 127.0.0.1, so a legitimate request always has a 127.0.0.1 /
            # localhost Host header; a rebound DNS name (or cross-site form post) would not.
            host = self.headers.get('Host', '')
            if host.rsplit(':', 1)[0].lower() not in ('127.0.0.1', 'localhost'):
                self._send_json(403, {'error': 'forbidden host'})

                return

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
            elif self.path == '/api/run/stop':
                if stop_pipeline_run():
                    self._send_json(200, {'status': 'stopping'})
                else:
                    self._send_json(409, get_run_status())
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
            elif self.path in ('/api/lists', '/api/lists/delete'):
                length = int(self.headers.get('Content-Length', 0))
                raw = self.rfile.read(length)
                lists_file = config_file.parent / CUSTOM_LISTS_FILENAME
                try:
                    payload = json.loads(raw.decode('utf-8'))
                    if not isinstance(payload, dict):
                        msg = "Expected a JSON object"

                        raise ValueError(msg)
                    if self.path == '/api/lists/delete':
                        lists = delete_custom_list(lists_file, payload.get('name'))
                        list_action = 'deleted'
                    else:
                        lists = save_custom_list(
                            lists_file, payload.get('name'), payload.get('identifiers'),
                        )
                        list_action = 'saved'
                except (json.JSONDecodeError, ValueError) as error:
                    self._send_json(400, {'errors': [str(error)]})

                    return

                self._send_json(200, {'status': list_action, 'lists': lists})
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
