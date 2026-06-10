.. _custom_calculator:

Custom Calculator Workflow
==========================

In “custom calculator” mode, you start from a Zero-Coder installation of Data Curator (i.e., you have already installed Data Curator, run ``kaxanuk.data_curator start``, and configured providers, dates, identifiers, and output columns through the parameter panel or directly in ``Config/data_curator_parameters.json``, as described in the Zero-Coder guide). Then, in addition to that configuration, you add one or more Python functions that generate extra columns on a per-row basis. Follow these steps to install (if you haven’t already), configure, and run Data Curator with your own calculations.

Prerequisites (Zero-Coder Setup)
--------------------------------

Before adding custom calculations, ensure you have completed the Zero-Coder steps.

Create a Python 3.12 Environment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use Conda or ``venv`` to isolate Data Curator’s dependencies.

**Conda example (Windows/macOS/Linux):**

.. code-block:: bash

   conda create --name datacurator_env python=3.12
   conda activate datacurator_env

**venv example:**

.. code-block:: bash

   python3.12 -m venv datacurator_env
   source datacurator_env/bin/activate    # macOS/Linux
   datacurator_env\Scripts\activate.bat   # Windows

Install Data Curator via pip
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

With the virtual environment active, run:

.. code-block:: bash

   pip install --upgrade kaxanuk.data_curator

This installs Data Curator along with its dependencies (e.g., ``pandas``, ``pyarrow``, etc.).

Initialize the Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Choose or create a project directory and move into it:

.. code-block:: bash

   mkdir ~/data_curator_project
   cd ~/data_curator_project

Run the one-command workflow, which scaffolds the workspace and opens the parameter panel
in your browser:

.. code-block:: bash

   kaxanuk.data_curator start

After this command, your directory will contain:

- ``__main__.py`` — the entry script that runs the system
- ``Config/data_curator_parameters.json`` — the configuration file
- ``Config/custom_calculations.py`` — where your custom functions go
- ``Config/.env`` — API keys for the data providers
- ``Output/`` — empty output folder

(If you only want the files without the panel, run ``kaxanuk.data_curator init json`` instead.)

Configure Data Curator (Zero-Coder Settings)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In the parameter panel (or directly in ``Config/data_curator_parameters.json``), set:

- **General**: data providers, ``start_date`` / ``end_date``, ``period`` (``annual`` or
  ``quarterly``), ``output_format`` (``csv`` or ``parquet``), ``logger_level``, and
  ``output_directory``.
- **API keys**: paste each provider’s key in the panel’s **API keys** section, or edit
  ``Config/.env`` directly:

  .. code-block:: text

     KNDC_API_KEY_FMP=<your_financial_modeling_prep_api_key>
     KNDC_API_KEY_LSEG=<your_lseg_workspace_api_key>

- **Identifiers**: the ticker symbols to fetch, e.g., ``AAPL``, ``MSFT``.
- **Output columns**: the raw data columns and predefined calculations you want.

See :ref:`zero_coder` for the full walkthrough. To verify the base setup works, click
**Save & run** in the panel, or run from the terminal:

.. code-block:: bash

   kaxanuk.data_curator run

and confirm that Data Curator fetches default data and writes output into ``Output/``.

Create Your Custom Calculation Function
---------------------------------------

Data Curator looks for any Python function in ``Config/custom_calculations.py`` whose name begins with ``c_``. Each such function is applied row-wise over the assembled dataset once the raw market/fundamental data has been collected. A custom function should:

- Be defined in ``Config/custom_calculations.py``.
- Take as positional arguments the column names (as Pandas Series) needed for the computation.
- Return a Pandas Series of the same length, with ``None`` or ``NaN`` in rows where inputs are missing or the operation is undefined.

Locate the Custom Calculations File
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In your project directory, open:

- ``Config/custom_calculations.py``

This file already contains template functions and import statements. At the top you’ll see helper imports such as:

.. code-block:: python

   import pandas as pd
   from datetime import datetime
   from kaxanuk.data_curator.features.helpers import (
       cumulative_return,
       log_return,
       ...
   )

Define a New Function
~~~~~~~~~~~~~~~~~~~~~

Choose a clear, snake_case name prefixed with ``c_``. For example, to compute a 10-day price difference, you might write:

.. code-block:: python

   def c_price_difference_10d(m_close: pd.Series) -> pd.Series:
       """
       Returns the difference between the close price and its value 10 trading days ago.
       Leaves first 10 rows as NaN.
       """
       # Use Pandas to shift by 10 rows
       return m_close - m_close.shift(10)

If you need multiple input columns, add them as separate parameters. For example:

.. code-block:: python

   def c_return_over_volume(m_close: pd.Series, m_volume: pd.Series) -> pd.Series:
       """
       Returns the ratio of daily log returns to volume.
       Rows with zero or missing volume will be NaN.
       """
       # Compute the log return using a helper
       log_ret = log_return(m_close)
       # Avoid division by zero
       return log_ret.where(m_volume != 0, None) / m_volume

Save your changes. Any function name not prefixed with ``c_`` will be ignored.

Best Practices for Custom Functions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Use only Pandas operations or existing helper functions for performance and consistency.
- Handle missing data explicitly (e.g., avoid dividing by zero; propagate ``NaN`` where appropriate).
- Document your function with a short docstring explaining inputs, outputs, and any edge-case behavior.
- If you import new libraries (e.g., ``numpy``), ensure they are already installed in your environment.

Add Your Custom Calculation to the Configuration
------------------------------------------------

After defining one or more functions in ``Config/custom_calculations.py``, you must tell Data Curator to include them in the output by adding each function name to the ``columns`` list of your configuration. There are two equivalent ways to do this.

Option A: Through the Parameter Panel
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Open the panel with ``kaxanuk.data_curator start`` (or ``kaxanuk.data_curator config-editor``
   if the workspace already exists).
2. In the **Output columns** section, type the full function name (including the ``c_`` prefix)
   into the search box and press **Enter**.
   For example, if your function is:

   .. code-block:: text

      def c_price_difference_10d(m_close: pd.Series) -> pd.Series: …

   then type:

   .. code-block:: text

      c_price_difference_10d

3. The column is added to your selection, listed under the **Custom / other** group.

Option B: Directly in the JSON File
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Open ``Config/data_curator_parameters.json`` in a text editor and add the function name to the
``columns`` array:

.. code-block:: json

   {
     "columns": [
       "m_date",
       "m_close",
       "m_volume",
       "c_price_difference_10d"
     ]
   }

Verify the Naming
~~~~~~~~~~~~~~~~~

- The configuration entry must exactly match the function name in ``custom_calculations.py``.
- Do **not** include parentheses or arguments—only the bare function name.

Save the Configuration
~~~~~~~~~~~~~~~~~~~~~~

Once you’ve added all desired custom-calculation names, click **Save** (or **Save & run**) in
the panel, or save ``data_curator_parameters.json`` in your editor.
If you are editing on macOS and don’t see hidden files (e.g., ``.env``), press **Command+Shift+Period** in Finder dialogs to reveal them.

Run Data Curator with Custom Calculations
-----------------------------------------

With both ``Config/custom_calculations.py`` and ``Config/data_curator_parameters.json`` updated, click **Save & run** in the panel, or run from your project directory:

.. code-block:: bash

   kaxanuk.data_curator run

What happens under the hood:

- Data Curator loads all raw data providers and writes default columns into memory.
- It then imports ``Config/custom_calculations.py`` and looks for any functions whose names start with ``c_``.
- For each such function listed in your ``columns``, it calls the function with the specified input columns (as Pandas Series).
- The returned Series is appended as a new column in the in-memory DataFrame.
- Finally, Data Curator writes one output file per identifier under your output directory
  (``Output/`` by default), named ``<IDENTIFIER>.<csv|parquet>``, containing the market data,
  fundamental data, dividend, split, and calculation columns you selected — including your
  custom columns prefixed ``c_``.

Troubleshooting & Tips
----------------------

**No output for your custom column?**
- Verify there are no syntax errors in ``custom_calculations.py``.
- Ensure the function name appears in the ``columns`` list of ``data_curator_parameters.json`` (in the panel, check the **Output columns** selection under **Custom / other**).
- Check that the input column names you referenced (e.g., ``m_close``, ``m_volume``) match the raw-data columns exactly.

**Getting many NaNs in your new column?**
- By design, custom calculations propagate ``NaN`` for rows where inputs are missing or invalid.
- Review your logic to see if you need to “forward-fill” or otherwise handle gaps before applying the calculation.

**Want to test a function interactively?**
1. Open a Python REPL (or Jupyter Notebook) in the same virtual environment.
2. Run:

   .. code-block:: python

      import pandas as pd
      # Load a small sample of raw data to a DataFrame
      df = pd.read_parquet("Output/AAPL.parquet", engine="pyarrow")
      from Config.custom_calculations import c_price_difference_10d
      # Apply it to the 'm_close' column
      sample = c_price_difference_10d(df["m_close"])
      print(sample.head())

**Reordering columns**
The output columns follow the order of the ``columns`` array in
``data_curator_parameters.json``. To change the order, edit the array directly in the JSON
file before rerunning.

Next Steps
----------

- **Organize Multiple Custom Functions**
  If you plan to maintain many custom calculations, group related helpers into separate Python modules under ``Config/`` and import them from ``custom_calculations.py``.

- **Version Control**
  Commit both ``custom_calculations.py`` and ``data_curator_parameters.json`` into your git repository to track changes to your custom logic.

- **Automated Testing**
  Write small unit tests for your custom functions (e.g., using ``pytest``) to ensure they behave as expected when inputs have gaps or extreme values.

See also
--------

- :ref:`Zero-Coder Workflow <zero_coder>` for end-user installation and usage.
- :ref:`Component Integrator Workflow <component_integrator>` for programmatic integration.
- :ref:`Developer/Tester Workflow <developer_tester>` for contributing code and running tests.
