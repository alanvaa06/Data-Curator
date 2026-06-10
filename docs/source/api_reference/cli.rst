.. _CLI_Documentation:

CLI Documentation
=================

Overview
--------

This page contains the complete documentation for the Data Curator command-line interface (CLI),
including all available commands, options, and usage examples.

Usage
-----

Below is the entry point for the CLI. Run ``kaxanuk.data_curator --help`` to see all commands, or
``kaxanuk.data_curator <command> --help`` for details on a specific command.

.. click:: kaxanuk.data_curator.services.cli:cli
   :prog: kaxanuk.data_curator
   :show-nested:

Commands
--------

start
~~~~~

One-command workflow: creates any missing workspace files (never overwriting existing ones),
then opens the HTML parameter panel in the browser, where the system can be run with **Save & run**.

Options:
- ``--port <number>``: Port for the local panel server. Defaults to ``8753``.
- ``--no-browser``: Do not open a browser window automatically.

config-editor
~~~~~~~~~~~~~

Launches the local HTML editor for the JSON configuration file without scaffolding any files.

Options:
- ``--port <number>``: Port for the local panel server. Defaults to ``8753``.
- ``--no-browser``: Do not open a browser window automatically.

init
~~~~

Creates all files and folders required by the specified configuration format.

Arguments:
- ``CONFIG_FORMAT`` (required, choices: ``json``): The configuration format to initialize.

Options:
- ``--entry_script <name>.py``: Name of the entry script to generate. Defaults to ``__main__.py``.

run
~~~

Runs the system. If no arguments are provided, it looks for ``__main__.py`` in the current directory;
otherwise, each argument must be a path to an entry script (or a directory containing ``__main__.py``).

Arguments:
- ``ENTRY_SCRIPT_LOCATIONS`` (0 or more): Path(s) to entry script file(s) or directories.

update
~~~~~~

Updates configuration files for the specified format.

Arguments:
- ``CONFIG_FORMAT`` (required, choices: ``json``, ``entry_script``): The configuration format to update.

Examples
--------

Initialize a new JSON configuration (creates ``Config/``, ``Output/`` and a new ``__main__.py``):

.. code-block:: console

   $ kaxanuk.data_curator init json
   Initializing data curator with format: json
   Created directory Config
   Created directory Output
   Installed all files successfully

Run the system using the default entry script:

.. code-block:: console

   $ kaxanuk.data_curator run
   Running...  # (or appropriate output from __main__.py)

Run the system on a specific entry script in another folder:

.. code-block:: console

   $ kaxanuk.data_curator run path/to/project/__main__.py
   Running...  # (or appropriate output from that __main__.py)

Update only the entry script to the latest template:

.. code-block:: console

   $ kaxanuk.data_curator update entry_script
   Updated entry script

Set up the workspace and open the parameter panel in one step:

.. code-block:: console

   $ kaxanuk.data_curator start
   Starting Data Curator panel at http://127.0.0.1:8753 (Ctrl+C to stop)
   Edit your parameters in the browser and click 'Save & run' to run the system.
