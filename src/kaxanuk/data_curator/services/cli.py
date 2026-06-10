"""
The cli entry points are defined and implemented here.
"""
import enum
import errno
import importlib
import importlib.metadata
import json
import pathlib
import re
import shutil
import subprocess
import sys
import sysconfig
import urllib.parse

import click

from kaxanuk.data_curator import (
    __version__,
    __package_name__,
    __package_title__,
)
from kaxanuk.data_curator.services import config_editor


CONFIG_SUBDIR = 'Config'
DATA_DIR = sysconfig.get_path('data')
DEV_TEMPLATES_SUBDIR = 'templates/data_curator'
ENTRY_SCRIPT_DEFAULT_NAME = '__main__.py'
JSON_ENTRY_SCRIPT_NAME = 'json_entry_script.py'
OUTPUT_SUBDIR = 'Output'
PARAMETERS_EXCEL_FILE = 'data_curator_parameters.xlsx'
PARAMETERS_JSON_FILE = 'data_curator_parameters.json'
TEMPLATES_DIR = f'{DATA_DIR}/data_curator'

INIT_DIRS = (
    CONFIG_SUBDIR,
    OUTPUT_SUBDIR,
)

class InitFormats(enum.StrEnum):
    EXCEL = 'excel'
    JSON = 'json'

class UpdateFormats(enum.StrEnum):
    EXCEL = 'excel'
    ENTRY_SCRIPT = 'entry_script'
    JSON = 'json'


@click.version_option(
    version=__version__,
    prog_name=__package_title__
)
@click.group()
def cli() -> None:
    """
    Entrypoint required for the click library, body can be empty.
    """


@cli.command()
def autorun() -> None:
    """
    Install the required files and directories for the Excel entry script if missing, otherwise run the system.
    """
    entry_script_path = pathlib.Path(ENTRY_SCRIPT_DEFAULT_NAME)
    if not pathlib.Path.exists(entry_script_path):
        try:
            _install_excel_files(ENTRY_SCRIPT_DEFAULT_NAME)
        except NotADirectoryError as error:
            msg = f"Templates directory not found in {DATA_DIR}. Please uninstall and reinstall this library"

            raise click.ClickException(msg) from error
        except OSError as error:
            if error.errno == errno.EACCES:
                msg = "Unable to access or modify target files"
            else:
                msg = f"OS error occurred while copying: {error}"

            raise click.ClickException(msg) from error

        click.echo("Installed all files successfully. Please configure the files in the Config folder and run again")
    else:
        try:
            _run_entry_script(entry_script_path)
        except subprocess.CalledProcessError as e:
            msg = "\n".join([
                "Failure executing the entry script process",
                f"Process output: {e.stdout}",
                f"Process errors: {e.stderr}",
            ])

            raise click.ClickException(msg) from e


@cli.command()
@click.argument(
    'config_format',
    type=click.Choice(
        f.value for f in InitFormats
    ),
)
@click.option(
    '--entry_script',
    default=ENTRY_SCRIPT_DEFAULT_NAME,
    help=f"The name of the entry script that will be generated. Default: {ENTRY_SCRIPT_DEFAULT_NAME}",
    type=click.STRING,
)
def init(
    config_format: str,
    entry_script: str
) -> None:
    """
    Create the files and folders required by the specified configuration format.

    \f

    Parameters
    ----------
    config_format
        The name of the configuration format to be initialized
    entry_script
        The name of the entry script that will be generated
    """
    click.echo(f"Initializing data curator with format: {config_format}")
    if config_format == InitFormats.EXCEL:
        config_path = pathlib.Path(CONFIG_SUBDIR)
        if pathlib.Path.exists(config_path):
            msg = f"The directory {CONFIG_SUBDIR} already exists. Please run the 'update' command instead"

            raise click.ClickException(msg)

        if not _validate_filename(entry_script):
            msg = ' '.join([
                "The entry script file name can only contain alphanumeric characters, hyphens,",
                "underscores, and periods, and must end in .py"
            ])

            raise click.ClickException(msg)

        try:
            _install_excel_files(entry_script)
        except NotADirectoryError as error:
            msg = f"Templates directory not found in {DATA_DIR}. Please uninstall and reinstall this library"

            raise click.ClickException(msg) from error
        except OSError as error:
            if error.errno == errno.EACCES:
                msg = "Unable to access or modify target files"
            else:
                msg = f"OS error occurred while copying: {error}"

            raise click.ClickException(msg) from error

        click.echo("Installed all files successfully")

    elif config_format == InitFormats.JSON:
        config_path = pathlib.Path(CONFIG_SUBDIR)
        if pathlib.Path.exists(config_path):
            msg = f"The directory {CONFIG_SUBDIR} already exists. Please run the 'update' command instead"

            raise click.ClickException(msg)

        if not _validate_filename(entry_script):
            msg = ' '.join([
                "The entry script file name can only contain alphanumeric characters, hyphens,",
                "underscores, and periods, and must end in .py"
            ])

            raise click.ClickException(msg)

        try:
            _install_json_files(entry_script)
        except NotADirectoryError as error:
            msg = f"Templates directory not found in {DATA_DIR}. Please uninstall and reinstall this library"

            raise click.ClickException(msg) from error
        except OSError as error:
            if error.errno == errno.EACCES:
                msg = "Unable to access or modify target files"
            else:
                msg = f"OS error occurred while copying: {error}"

            raise click.ClickException(msg) from error

        click.echo("Installed all files successfully")


@cli.command()
@click.argument(
    'entry_script_locations',
    nargs=-1,   # variable number of arguments
    type=str,
)
def run(entry_script_locations: list[str]) -> None:
    """
    Run the system.

    If passed any string arguments, each one needs to be the path to an entry script (or to a directory with a
    __main__.py entry script) that will be executed. If called without arguments, the entry script in the current
    directory will be run.

    \f

    Parameters
    ----------
    entry_script_locations
        The locations of the entry scripts that will be executed
    """
    entry_script_path = None

    try:
        if not entry_script_locations:
            entry_script_path = pathlib.Path(ENTRY_SCRIPT_DEFAULT_NAME)
            if not entry_script_path.exists():
                msg = f"No entry script found in the current directory, expecting it at {ENTRY_SCRIPT_DEFAULT_NAME}"

                raise click.ClickException(msg)

            _run_entry_script(entry_script_path)
        else:
            for location in entry_script_locations:
                entry_script_path = pathlib.Path(location)
                if not entry_script_path.exists():
                    msg = f"No entry script found in location {location}, aborting"

                    raise click.ClickException(msg)

                _run_entry_script(entry_script_path)
    except subprocess.CalledProcessError as e:
        msg = "\n".join([
            f"Failure executing the entry script process for path {entry_script_path!s}",
            f"Process output: {e.stdout}",
            f"Process errors: {e.stderr}",
        ])

        raise click.ClickException(msg) from e


@cli.command(name='config-editor')
@click.option(
    '--port',
    default=config_editor.DEFAULT_PORT,
    help=f"Port for the local editor server. Default: {config_editor.DEFAULT_PORT}",
    type=click.INT,
)
@click.option(
    '--no-browser',
    is_flag=True,
    default=False,
    help="Do not open a browser window automatically.",
)
def config_editor_command(port: int, no_browser: bool) -> None:    # noqa: FBT001
    """
    Launch the local HTML editor for the JSON configuration file.
    """
    config_path = pathlib.Path(CONFIG_SUBDIR) / PARAMETERS_JSON_FILE
    click.echo(f"Starting config editor at http://{config_editor.HOST}:{port} (Ctrl+C to stop)")
    _serve_panel(
        config_path,
        port=port,
        open_browser=not no_browser,
    )


@cli.command()
@click.option(
    '--port',
    default=config_editor.DEFAULT_PORT,
    help=f"Port for the local editor server. Default: {config_editor.DEFAULT_PORT}",
    type=click.INT,
)
@click.option(
    '--no-browser',
    is_flag=True,
    default=False,
    help="Do not open a browser window automatically.",
)
def start(port: int, no_browser: bool) -> None:    # noqa: FBT001
    """
    One-command workflow: set up the JSON workspace if needed, then open the parameter panel.

    Creates any missing Config/Output directories, configuration file and entry script
    (never overwriting existing files), then launches the local HTML panel where you can
    edit the parameters and run the system with the "Save & run" button.
    """
    try:
        _ensure_json_workspace(ENTRY_SCRIPT_DEFAULT_NAME)
    except NotADirectoryError as error:
        msg = f"Templates directory not found in {DATA_DIR}. Please uninstall and reinstall this library"

        raise click.ClickException(msg) from error
    except OSError as error:
        if error.errno == errno.EACCES:
            msg = "Unable to access or modify target files"
        else:
            msg = f"OS error occurred while copying: {error}"

        raise click.ClickException(msg) from error

    config_path = pathlib.Path(CONFIG_SUBDIR) / PARAMETERS_JSON_FILE
    click.echo(f"Starting Data Curator panel at http://{config_editor.HOST}:{port} (Ctrl+C to stop)")
    click.echo("Edit your parameters in the browser and click 'Save & run' to run the system.")
    _serve_panel(
        config_path,
        port=port,
        open_browser=not no_browser,
    )


def _serve_panel(
    config_path: pathlib.Path,
    *,
    port: int,
    open_browser: bool,
) -> None:
    """
    Serve the configuration panel, translating port conflicts into a clear message.

    Raises
    ------
    click.ClickException
        When the port is already in use by another process
    """
    try:
        config_editor.serve(
            config_path,
            port=port,
            open_browser=open_browser,
            entry_script=ENTRY_SCRIPT_DEFAULT_NAME,
        )
    except OSError as error:
        if error.errno == errno.EADDRINUSE:
            msg = " ".join([
                f"Port {port} is already in use — a Data Curator panel is probably already running.",
                f"Open http://{config_editor.HOST}:{port} in your browser, close the other process,",
                "or pass a different port with --port.",
            ])

            raise click.ClickException(msg) from error

        raise


@cli.command()
@click.argument(
    'config_format',
    type=click.Choice(
        f.value for f in UpdateFormats
    ),
)
def update(config_format: str) -> None:
    """
    Update the configuration files for the specified format.

    \f

    Parameters
    ----------
    config_format
        The name of the configuration format to be reinitialized
    """
    click.echo(f"Updating data curator configuration files for format: {config_format}")

    match config_format:
        case UpdateFormats.ENTRY_SCRIPT:
            _update_entry_script(
                ENTRY_SCRIPT_DEFAULT_NAME,
                ENTRY_SCRIPT_DEFAULT_NAME
            )
            click.echo('Updated entry script')
        case UpdateFormats.EXCEL:
            config_path = pathlib.Path(CONFIG_SUBDIR)
            if not pathlib.Path.is_dir(config_path):
                msg = f"The {CONFIG_SUBDIR} directory does not exist. Please run the 'init' command instead"

                raise click.ClickException(msg)

            try:
                _update_excel_files()
                click.echo("Updated all files successfully")
            except OSError as error:
                if error.errno == errno.EACCES:
                    msg = "Unable to access or modify target files"
                else:
                    msg = f"OS error occurred while copying: {error}"

                raise click.ClickException(msg) from error
        case UpdateFormats.JSON:
            config_path = pathlib.Path(CONFIG_SUBDIR)
            if not pathlib.Path.is_dir(config_path):
                msg = f"The {CONFIG_SUBDIR} directory does not exist. Please run the 'init' command instead"

                raise click.ClickException(msg)

            try:
                _update_json_files()
                click.echo("Updated all files successfully")
            except OSError as error:
                if error.errno == errno.EACCES:
                    msg = "Unable to access or modify target files"
                else:
                    msg = f"OS error occurred while copying: {error}"

                raise click.ClickException(msg) from error


def _install_excel_files(entry_script: str) -> None:
    """
    Install the directories and files required for the Excel entry script.

    Parameters
    ----------
    entry_script
        The name of the entry script that will be generated

    Raises
    ------
    NotADirectoryError
        The templates directory was not found
    OSError
        Usually when there's a file permissions error
    shutil.Error
        Shutil failed for some reason
    """
    # create the folders
    for dir_name in INIT_DIRS:
        try:
            pathlib.Path.mkdir(
                pathlib.Path(dir_name)
            )
            click.echo(f"Created directory {dir_name}")
        except FileExistsError:
            click.echo(f"The directory {dir_name} already exists, omitting the creation")

    actual_templates_dir = _find_templates_dir()
    # @todo: check if dir has expected files

    if actual_templates_dir is None:
        raise NotADirectoryError

    shutil.copytree(
        f'{actual_templates_dir}/{CONFIG_SUBDIR}',
        CONFIG_SUBDIR,
        dirs_exist_ok=True,
    )
    shutil.copy(
        f'{actual_templates_dir}/__main__.py',
        entry_script
    )


def _install_json_files(entry_script: str) -> None:
    """
    Install the directories and files required for the JSON entry script.

    Parameters
    ----------
    entry_script
        The name of the entry script that will be generated

    Raises
    ------
    NotADirectoryError
        The templates directory was not found
    OSError
        Usually when there's a file permissions error
    """
    # create the folders
    for dir_name in INIT_DIRS:
        try:
            pathlib.Path.mkdir(
                pathlib.Path(dir_name)
            )
            click.echo(f"Created directory {dir_name}")
        except FileExistsError:
            click.echo(f"The directory {dir_name} already exists, omitting the creation")

    actual_templates_dir = _find_templates_dir()

    if actual_templates_dir is None:
        raise NotADirectoryError

    templates_path = pathlib.Path(actual_templates_dir)
    config_source = templates_path / CONFIG_SUBDIR
    # copy the shared config files and the JSON parameters file, but not the Excel parameters file
    for name in ('.env', 'custom_calculations.py', PARAMETERS_JSON_FILE):
        source = config_source / name
        if source.is_file():
            shutil.copy(source, pathlib.Path(CONFIG_SUBDIR) / name)

    shutil.copy(
        templates_path / JSON_ENTRY_SCRIPT_NAME,
        entry_script,
    )


def _ensure_json_workspace(entry_script: str) -> None:
    """
    Create any missing JSON-format directories and files, never overwriting existing ones.

    Parameters
    ----------
    entry_script
        The name of the entry script that will be created if missing

    Raises
    ------
    NotADirectoryError
        The templates directory was not found
    OSError
        Usually when there's a file permissions error
    """
    for dir_name in INIT_DIRS:
        dir_path = pathlib.Path(dir_name)
        if not dir_path.is_dir():
            pathlib.Path.mkdir(dir_path)
            click.echo(f"Created directory {dir_name}")

    actual_templates_dir = _find_templates_dir()
    if actual_templates_dir is None:
        raise NotADirectoryError

    templates_path = pathlib.Path(actual_templates_dir)
    for name in ('.env', 'custom_calculations.py', PARAMETERS_JSON_FILE):
        source = templates_path / CONFIG_SUBDIR / name
        destination = pathlib.Path(CONFIG_SUBDIR) / name
        if source.is_file() and not destination.exists():
            shutil.copy(source, destination)
            click.echo(f"Created {destination}")

    entry_path = pathlib.Path(entry_script)
    if not entry_path.exists():
        shutil.copy(
            templates_path / JSON_ENTRY_SCRIPT_NAME,
            entry_path,
        )
        click.echo(f"Created entry script {entry_script}")


def _find_templates_dir() -> str | None:
    """
    Determine the templates directory from the list of possible directories.

    Returns
    -------
    The path to the existing templates directory, or None if no directory is found.
    """
    # Cf. https://stackoverflow.com/a/77824551/5220723
    package_distribution = importlib.metadata.Distribution.from_name(__package_name__)
    direct_url = package_distribution.read_text("direct_url.json")

    if direct_url is None:
        package_is_editable = False
    else:
        direct_url_obj = json.loads(direct_url)
        package_is_editable = (
            direct_url_obj
                .get("dir_info", {})
                .get("editable", False)
        )

    if package_is_editable:
        base_dir_url = urllib.parse.unquote(
            direct_url_obj.get('url', '')
        )
        base_dir = base_dir_url.replace('file:///', '')
        windows_volume_pattern = re.compile(r'^[A-Z]:/.*')
        linux_proper_volume_pattern = re.compile(r'^/.*')
        if (
            not windows_volume_pattern.match(base_dir)
            and not linux_proper_volume_pattern.match(base_dir)
        ):
            base_path = pathlib.Path(f'/{base_dir}')
        else:
            base_path = pathlib.Path(base_dir)

        dev_templates_path = base_path / DEV_TEMPLATES_SUBDIR

        if pathlib.Path.is_dir(
            dev_templates_path
        ):
            return str(dev_templates_path)

    elif pathlib.Path.is_dir(
        pathlib.Path(TEMPLATES_DIR)
    ):
        return TEMPLATES_DIR

    return None


def _run_entry_script(entry_script_path: pathlib.Path) -> subprocess.CompletedProcess:
    """
    Run the entry script on entry_script_path.

    Parameters
    ----------
    entry_script_path
        The entry script to run

    Returns
    -------
    The CompletedProcess object

    Raises
    ------
    subprocess.CalledProcessError
    """
    return subprocess.run(
        [sys.executable, entry_script_path],
        check=True
    )


def _safe_rename_file(path: pathlib.Path) -> None:
    """
    Rename a file appending a number to the filename, increasing it if it collides with an existing file.

    Parameters
    ----------
    path
        The current path to the file to be renamed

    Raises
    ------
    FileNotFoundError
    """
    filename = path.stem
    directory = path.parent
    extension = path.suffix
    counter = 1
    new_path = path

    while pathlib.Path.exists(new_path):
        new_path = pathlib.Path(
            directory / f"{filename}.{counter!s}{extension}"
        )
        counter += 1

    pathlib.Path.rename(path, new_path)


def _update_entry_script(
    source_entry_script_name: str,
    destination_entry_script_name: str,
) -> None:
    """
    Install the source entry script into the current directory, renaming any existing file beforehand.

    Parameters
    ----------
    source_entry_script_name
        The filename of the source entry script
    destination_entry_script_name
        The filename of the entry script that will be created

    Raises
    ------
    NotADirectoryError
        The templates directory was not found
    OSError
        Shutil failed for some reason
    """
    # @todo change to load from examples scripts

    actual_templates_dir = _find_templates_dir()
    if actual_templates_dir is None:
        raise NotADirectoryError

    source_entry_script_path = pathlib.Path(actual_templates_dir) / source_entry_script_name
    destination_entry_script_path = pathlib.Path.cwd() / destination_entry_script_name
    if not pathlib.Path.exists(source_entry_script_path):
        msg = f"Entry script {source_entry_script_name} missing from {actual_templates_dir}"

        raise click.ClickException(msg)

    # @todo: check if dir has expected file

    if pathlib.Path.exists(destination_entry_script_path):
        _safe_rename_file(destination_entry_script_path)

    shutil.copy(
        source_entry_script_path,
        destination_entry_script_path
    )


def _update_excel_files() -> None:
    """
    Update the Excel configuration files into the Config subdirectory, renaming any existing file beforehand.

    Raises
    ------
    NotADirectoryError
        The templates directory was not found
    OSError
        File permissions or shutil error
    """
    actual_templates_dir = _find_templates_dir()
    if actual_templates_dir is None:
        raise NotADirectoryError

    actual_templates_path = pathlib.Path(actual_templates_dir)
    config_path = pathlib.Path(CONFIG_SUBDIR)
    template_file_path = actual_templates_path / CONFIG_SUBDIR / PARAMETERS_EXCEL_FILE

    local_file = config_path / template_file_path.name
    if pathlib.Path.exists(local_file):
        _safe_rename_file(local_file)
    shutil.copy(template_file_path, local_file)


def _update_json_files() -> None:
    """
    Update the JSON configuration file into the Config subdirectory, renaming any existing file beforehand.

    Raises
    ------
    NotADirectoryError
        The templates directory was not found
    OSError
        File permissions or shutil error
    """
    actual_templates_dir = _find_templates_dir()
    if actual_templates_dir is None:
        raise NotADirectoryError

    template_file_path = pathlib.Path(actual_templates_dir) / CONFIG_SUBDIR / PARAMETERS_JSON_FILE
    local_file = pathlib.Path(CONFIG_SUBDIR) / PARAMETERS_JSON_FILE
    if pathlib.Path.exists(local_file):
        _safe_rename_file(local_file)
    shutil.copy(template_file_path, local_file)


def _validate_filename(filename: str) -> bool:
    """
    Validate the filename to ensure it can be used in any supported file system.

    Parameters
    ----------
    filename

    Returns
    -------
    Whether the filename is valid
    """
    filename_pattern = re.compile(r'^[A-Za-z0-9_\-.]+.py$')
    return bool(
        filename_pattern.match(filename)
    )
