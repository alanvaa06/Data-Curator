.. _quick_start:

Quick Start
=========================

Installation
------------

The system can run either on your local Python environment or on Docker.

**Requirements for Local Installation**

- Python 3.12, 3.13, or 3.14

**Installing on Python**

1. Make sure you're running the required version of Python, preferably in its own virtual environment.
2. Open a terminal and run:

   .. code-block:: bash

      pip install kaxanuk.data_curator

3. If you want to use the Yahoo Finance data provider, install the extension package:

   .. code-block:: bash

      pip install kaxanuk.data_curator_extensions.yahoo_finance

4. Set the path where Data Curator should generate its configuration files

    .. code-block:: bash

        cd /path/to/your/datacurator/project

**One-command workflow**

Run a single command from your project directory:

.. code-block:: bash

   kaxanuk.data_curator start

This does everything:

1. Creates the ``Config`` and ``Output`` directories, the configuration file and the entry
   script if they don't exist yet (existing files are never overwritten).
2. Opens the parameter panel in your browser (``http://127.0.0.1:8753``), where you pick the
   data providers, dates, period, output format, identifiers, and output columns.
3. Click **Save & run** to save your parameters and run the system directly from the panel;
   the run output appears on the page and the data is saved in the ``Output`` folder.

Stop the panel with ``Ctrl+C`` in the terminal.

If any provider requires an API key, edit the ``Config/.env`` file and set the key using the
variable indicated in the provider documentation. Do not add quotes or extra spaces.

*On macOS, the `.env` file may be hidden. Use `Cmd + Shift + .` to show hidden files.*

**Advanced: separate commands**

Each step is also available as its own command if you prefer finer control:

.. code-block:: bash

   kaxanuk.data_curator init json        # scaffold the workspace
   kaxanuk.data_curator config-editor    # edit parameters in the browser
   kaxanuk.data_curator run              # run the system headlessly

**Legacy: Excel configuration**

The Excel workflow is still supported as a fallback. Run ``kaxanuk.data_curator init excel`` to
scaffold an ``Config/data_curator_parameters.xlsx`` file and edit it directly, then
``kaxanuk.data_curator run``. New projects should prefer the ``start`` workflow above.
