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

**Configuration (HTML editor)**

1. Open a terminal and run:

   .. code-block:: bash

      kaxanuk.data_curator init json

   This will create two subdirectories: ``Config`` and ``Output``, along with the entry script ``__main__.py``.

2. Launch the parameter editor and adjust your settings in the browser:

   .. code-block:: bash

      kaxanuk.data_curator config-editor

   This opens a local page (``http://127.0.0.1:8753``) where you can pick the data providers,
   dates, period, output format, identifiers, and output columns. Click **Save** to write
   ``Config/data_curator_parameters.json``. Stop the editor with ``Ctrl+C``.

3. If any provider requires an API key, edit the ``Config/.env`` file and set the key using the variable indicated in the provider documentation. Do not add quotes or extra spaces.

   *On macOS, the `.env` file may be hidden. Use `Cmd + Shift + .` to show hidden files.*

**Legacy: Excel configuration**

The Excel workflow is still supported as a fallback. Run ``kaxanuk.data_curator init excel`` to
scaffold an ``Config/data_curator_parameters.xlsx`` file and edit it directly. New projects
should prefer the JSON + editor path above.

**Usage**

You can run the tool using:

.. code-block:: bash

   kaxanuk.data_curator run

Or by running the main script directly:

.. code-block:: bash

   python __main__.py

The system will pull the data for the configured tickers and save results in the ``Output`` folder.
