.. _data_providers:

Data Providers
===============

This section contains the list of data providers integrated into the library. These providers enable access to stock market data, financial statements, historical prices, and other financial information.

Each provider is documented with its technical details, including the methods available for interacting with their APIs and how to use them effectively within the library.

What you’ll find here:

- :ref:`fmp` – Financial Modeling Prep integration, supported fields and setup
- :ref:`data_tag_homogenization` – standard naming conventions applied to unify external tags

Macro / economic data providers
--------------------------------

In addition to the per-ticker equity providers above, the library can fetch macro-economic
series (rates, inflation, GDP, employment, FX, monetary aggregates) from four non-ticker
sources behind ``MacroDataProviderInterface``:

- **Banxico SIE** – Mexican central-bank series (``KNDC_API_KEY_BANXICO``, free token)
- **INEGI** – Mexican statistics-agency series (``KNDC_API_KEY_INEGI``, free token)
- **FRED** – US Federal Reserve series (``KNDC_API_KEY_FRED``, free key; **non-commercial /
  research use only** — its Terms of Use restrict redistribution and ML/LLM-training use)
- **DBnomics** – rest-of-world aggregator (keyless, no token required)

Macro series are selected as regular output columns prefixed ``e_*`` (for example
``e_mx_target_rate``, ``e_us_cpi``, ``e_ecb_rate``) and are **forward-filled** onto every
ticker's market dates, broadcasting the same macro value to all identifiers on each date.

.. toctree::
   :maxdepth: 2
   :hidden:

   financial_modeling_prep
   data_tag_homogenization
