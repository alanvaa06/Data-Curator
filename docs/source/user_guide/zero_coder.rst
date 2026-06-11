.. _zero_coder:

Zero-Coder Workflow
====================

In “zero-coder” mode, everything is configured without writing Python code: a local web panel
edits the JSON configuration file for you, and a single **Save & run** button runs the system.
Follow these steps to install, configure, and run Data Curator.

Install Data Curator
--------------------

Create a Python 3.12 Environment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use Conda or `venv` to isolate Data Curator’s dependencies.

**Conda example (Windows/macOS/Linux):**

.. code-block:: bash

   conda create --name datacurator_env python=3.12
   conda activate datacurator_env

**venv example:**

.. code-block:: bash

   python3.12 -m venv datacurator_env
   source datacurator_env/bin/activate    # macOS/Linux
   datacurator_env\Scripts\activate.bat   # Windows


Install the Package via pip
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

With the virtual environment active, run:

.. code-block:: bash

   pip install --upgrade kaxanuk.data_curator

This installs Data Curator plus all dependencies specified in `pyproject.toml` (e.g., `pandas`, `pyarrow`, etc.).

If you want to use the Yahoo Finance data provider, also install its extension package:

.. code-block:: bash

   pip install kaxanuk.data_curator_extensions.yahoo_finance


Start the Configuration Panel
-----------------------------

Choose or create a project directory and move into it:

.. code-block:: bash

   mkdir ~/data_curator_project
   cd ~/data_curator_project

Run the one-command workflow:

.. code-block:: bash

   kaxanuk.data_curator start

.. tip::

   If your terminal reports the command is not found, use the module form instead:
   ``python -m kaxanuk.data_curator start``. Add ``--port N`` to serve on a different
   port, or ``--no-browser`` to skip opening the browser automatically.

The ``start`` command:

1. Scaffolds any missing workspace files (existing files are never overwritten):

   - ``__main__.py`` — the entry script that runs the system
   - ``Config/data_curator_parameters.json`` — the configuration file
   - ``Config/custom_calculations.py`` — optional Python calculations (see :ref:`custom_calculator`)
   - ``Config/.env`` — API keys for the data providers
   - ``Output/`` — where results are written

2. Serves the parameter panel at ``http://127.0.0.1:8753`` and opens it in your browser.

Stop the panel with ``Ctrl+C`` in the terminal.


Configure Data Curator in the Panel
-----------------------------------

Everything you set in the panel is saved to ``Config/data_curator_parameters.json``.

General
~~~~~~~

- ``market_data_provider`` / ``fundamental_data_provider``: pick the data vendors
  (e.g., ``financial_modeling_prep``, ``lseg_workspace``, ``yahoo_finance``).
- ``start_date`` / ``end_date`` (YYYY-MM-DD): first and last dates of the data fetch.
- ``period``: fundamental data frequency, ``annual`` or ``quarterly``.
- ``output_format``: choose between ``csv``, ``parquet`` or ``duckdb``. The first two
  write one file per identifier; ``duckdb`` writes all identifiers into a single
  database file (``data_curator.duckdb``, table ``curated_data``) and re-runs update
  existing rows in place instead of rewriting files, so you can refresh just the most
  recent dates of a long history.
- ``logger_level``: log verbosity (e.g., ``info``, ``debug``).
- ``output_directory``: where output files are written (defaults to ``Output``). A directory
  outside cloud-synced locations (OneDrive/Dropbox) runs noticeably faster.

API Keys
~~~~~~~~

Paste each provider’s key in the **API keys** section of the panel; keys are stored in
``Config/.env``, never in the configuration file. You can also edit ``Config/.env`` directly:

.. code-block:: text

   KNDC_API_KEY_FMP=<your_financial_modeling_prep_api_key>
   KNDC_API_KEY_LSEG=<your_lseg_workspace_api_key>

Do not add quotes or extra spaces around the keys.

- On macOS, press **Command+Shift+Period** in Finder dialogs to reveal hidden files like ``.env``.

Identifiers
~~~~~~~~~~~

Type each ticker symbol (e.g., ``AAPL``, ``MSFT``) and press **Enter** or click **Add**.

Output Columns
~~~~~~~~~~~~~~

Tick the columns you want in the output files:

- Raw market data (prefixed ``m_``), e.g., ``m_open``, ``m_close``, ``m_volume``.
- Fundamental data (prefixed ``f_``, ``fbs_``, ``fis_``, ``fcf_``), e.g., ``fis_net_income``.
- Dividends and splits (prefixed ``d_`` and ``s_``).
- Predefined calculations (prefixed ``c_``), e.g., ``c_simple_moving_average_5d_close_split_adjusted``.

Use the search box to filter the list.


Run Data Curator
----------------

Click **Save & run**. The panel saves your parameters, runs the system, and shows progress and
log output on the page. Data Curator will:

- Read your settings from ``Config/data_curator_parameters.json``.
- Read the API keys from ``Config/.env``.
- Fetch market and fundamental data from the selected providers.
- Apply any predefined and custom calculations you selected.
- Write one file per identifier into your output directory (``Output/`` by default), named:

  ::

     <IDENTIFIER>.<csv|parquet>

Each output file contains one row per date, with the columns you selected: market data,
fundamental data, dividends, splits, and calculation columns (prefixed ``c_``).

To iterate, adjust the parameters in the panel and click **Save & run** again — previous
output files are overwritten.


Running Without the Panel
-------------------------

Once the configuration is saved, you can also run headlessly from your project directory:

.. code-block:: bash

   kaxanuk.data_curator run

This executes the entry script (``__main__.py``), reading ``Config/data_curator_parameters.json``
and ``Config/.env``. Other useful commands:

.. code-block:: bash

   kaxanuk.data_curator init json             # scaffold the workspace without serving the panel
   kaxanuk.data_curator config-editor         # serve the panel without scaffolding
   kaxanuk.data_curator update json           # refresh the config file from the template (renames the existing one first)
   kaxanuk.data_curator update entry_script   # refresh __main__.py from the template (renames the existing one first)


Editing the JSON File by Hand
-----------------------------

The panel is optional — ``Config/data_curator_parameters.json`` is a plain JSON file you can
edit in any text editor:

.. code-block:: json

   {
     "parameters_format_version": "0.47.0",
     "general": {
       "market_data_provider": "financial_modeling_prep",
       "fundamental_data_provider": "financial_modeling_prep",
       "start_date": "2020-01-01",
       "end_date": "2025-12-31",
       "period": "quarterly",
       "output_format": "csv",
       "logger_level": "info",
       "output_directory": "Output"
     },
     "identifiers": ["AAPL", "MSFT"],
     "columns": ["m_date", "m_close", "m_volume", "c_market_cap"]
   }

Keep the ``parameters_format_version`` value that comes with the scaffolded file. After saving
your changes, run ``kaxanuk.data_curator run``.


See also
--------

- :ref:`Custom Calculator Workflow <custom_calculator>` for adding Python-based features.
- :ref:`Component Integrator Workflow <component_integrator>` for programmatic integration.
- :ref:`Developer/Tester Workflow <developer_tester>` for contributing code and running tests.
