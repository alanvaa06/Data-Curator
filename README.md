# KaxaNuk Data Curator

|                                                                                                                                                                                                                                                                                                                                                                                |
|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue?logo=python&logoColor=ffdd54)](https://www.python.org) [![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE) [![Build Status](https://github.com/alanvaa06/Data-Curator/actions/workflows/main.yml/badge.svg)](https://github.com/alanvaa06/Data-Curator/actions/workflows/main.yml) |

Component library for downloading, validating, homogenizing, and combining financial stocks' data from different data providers.
Can be run in standalone mode, configurable through a browser-based parameter panel, or as a component of a larger Python-based system. 

Features:
* **Configurable** from a browser-based parameter panel (backed by a JSON file), or directly in a Python script. Docker image also available.
* Fully readable and specific **tag names**, homogenized between data providers, based on the US GAAP taxonomy. Switch between data providers without changing your code.
* Automatically validates market and fundamental data, discarding datasets that make no sense (like high price below low, etc.) or can't guarantee point-in-time validity (like amended statements).
* Easily create your own **calculated feature functions** without need for Numpy or Pandas (though you can also use those if you want to).
* **Output** to CSV or Parquet files, or to in-memory Pandas Dataframes for further processing.
* Completely **extensible architecture**: implement your own data providers, feature combinations, and output handlers on top of clear, stable interfaces.
* Readable, well-documented, and tested **code**.


## Documentation
Full documentation sources live in [docs/source](docs/source); build them locally with `pdm run docs html`.

## Requirements
The system can run either on your local Python (versions `3.12`, `3.13`, or `3.14`) or on Docker.


## Supported Data Providers
### Equity / ticker data
* Financial Modeling Prep (free and discounted plans available through [our referral link](https://site.financialmodelingprep.com/pricing-plans?couponCode=xss2L2sI))
* LSEG Workspace (API key required)
* Yahoo Finance (requires installing a separate extension package, and doesn't support most data types)

### Macro / economic data
Alongside the per-ticker providers above, the Data Curator can also fetch macro-economic series
(rates, inflation, GDP, employment, FX, monetary aggregates) from four sources:

* **Banxico SIE** — Mexican central-bank series (target rate, TIIE, Cetes, USD/MXN FIX, international reserves). Free token from the [Banxico SIE API page](https://www.banxico.org.mx/SieAPIRest/service/v1/token).
* **INEGI** — Mexican statistics-agency series (INPC / headline CPI, ENOE unemployment). Free token via [INEGI token registration](https://www.inegi.org.mx/app/api/indicadores/interna_v1_1/tokenVerify.aspx).
* **FRED** — US Federal Reserve (St. Louis Fed) series (CPI, core CPI, fed funds, 2Y/10Y Treasuries, unemployment, real GDP, M2). Free [FRED API key](https://fredaccount.stlouisfed.org/apikey).
* **DBnomics** — keyless rest-of-world aggregator. Routes the cross-country catalog through wide datasets so the same concept is comparable across economies: policy rates (BIS), CPI / core CPI / PPI / FX-vs-USD / reserves / short rates (IMF IFS), 10Y government yields & retail sales & harmonised unemployment & economic sentiment (Eurostat), real/nominal GDP & GDP growth & current account & trade & youth unemployment (World Bank), business/consumer confidence & M1/M3 money (OECD), credit / REER / NEER / house prices (BIS), and government debt & budget balance (IMF WEO). **Keyless** — no token required.

The bundled catalog ships **1292 curated `e_*` columns across 44 economies** (US, Mexico, euro area, and ~40 other developed and emerging markets) spanning ~59 indicators — rates, money & credit, prices, activity, sentiment, labour, and the external sector. Every series id is machine-verified against its live provider API before inclusion via `scripts/build_macro_catalog.py`; re-run that script to extend or re-validate the catalog. Each row carries a `commercial_ok` flag for the underlying source's redistribution terms (Eurostat / World Bank = `yes`; IMF / BIS / OECD = `restricted`; FRED = `no`). In the parameter panel the macro columns are nested under a single **Economic** set with one collapsible subgroup per country/area (a two-level Economic → country → columns tree) for easy navigation.

Macro series are not per-ticker: you select them as regular output columns prefixed `e_*`
(e.g. `e_mx_target_rate`, `e_us_cpi`, `e_jp_policy_rate`, `e_de_10y`) in the parameter panel's column picker, and
the system **forward-fills** each macro series onto every ticker's dates (macro cadence is
monthly/quarterly/weekly; markets are daily), broadcasting the same macro value to all
identifiers on each date.

Each macro source brings its own free, bring-your-own API key, set the same way as any other
provider key (panel's API keys section, or the `Config/.env` file):

| Source | Env var | Key needed? |
|--------|---------|-------------|
| Banxico SIE | `KNDC_API_KEY_BANXICO` | Yes (free token) |
| INEGI | `KNDC_API_KEY_INEGI` | Yes (free token) |
| FRED | `KNDC_API_KEY_FRED` | Yes (free key) |
| DBnomics | — | No (keyless) |

> **FRED licensing note.** FRED's Terms of Use restrict redistribution of large datasets and
> the use of FRED data for developing or training machine-learning / LLM models. The Data Curator
> ships code, not FRED data — each user supplies their own key and the data flows to that user's
> own disk — so it is appropriate here for **non-commercial / research** use. A commercial product
> that ships FRED data or trains models on it needs a separate licensing review.


## Running on Local Python
### Installation
1. Make sure you're running one of the required versions of Python, preferably in its own virtual environment.
2. Open a terminal and run:
    ```
    pip install --upgrade pip
    pip install kaxanuk.data_curator
    ```

3. If you want to use the Yahoo Finance data provider, install the extension package:
    ```
    pip install kaxanuk.data_curator_extensions.yahoo_finance
    ```


### Configuration
1. Open a terminal in any directory and run the following command:
    ```
    kaxanuk.data_curator start
    ```
    This creates two subdirectories, `Config` and `Output`, plus the entry script `__main__.py` in the current
    directory (never overwriting existing files), and opens the parameter panel in your browser.

    > The panel is served by this command, so **keep the terminal open** — the panel stays up only while
    > `start` is running; press `Ctrl+C` to stop it. If the `kaxanuk.data_curator` command is not on your
    > `PATH`, use the equivalent module form instead:
    > ```
    > python -m kaxanuk.data_curator start
    > ```
2. In the panel, pick the data providers, dates, period, output format, identifiers, and output columns, then click
   **Save & run** — the run output appears on the page and the data is saved to the `Output` folder.
3. If your data provider requires an API key, set it in the panel's API keys section, or open the `Config/.env` file
    in a text editor and paste the key after the `=` sign of the provider's corresponding `API_KEY` variable.
    Don't add any quotes or spaces before or after the key.

*_If on MacOS, the `.env` file will be hidden in Finder by default. Just use the keys `Command` + `Shift` + `.` to toggle
the visibility of hidden files._


### Usage
Now you can run the entry script with either:
```
kaxanuk.data_curator run
```
or by executing the `__main__.py` script directly with Python:
```
python __main__.py
```
The system will download the data for the tickers configured in the file, and save the data to the `Output` folder.


## Running on Docker
### Pull the Docker image:
```
docker pull ghcr.io/kaxanuk/data-curator:latest
```

### Docker Configuration
#### Volumes
You need to mount the following volume to the container:
* Path on the host: (select the directory on your PC where you want the Data Curator configuration and output files to be created)
* Path inside the container: `/app`

#### Environment Variables
If your data provider requires an API key, you need to pass it as an environment variable when running the container.
* Name: `KNDC_API_KEY_FMP`
* Value: API key for the Financial Modeling Prep data provider, as a string.
* Name: `KNDC_API_KEY_LSEG`
* Value: API key for the LSEG Workspace data provider, as a string.

#### Running the Container
1. On the first run, the container will create the `Config` and `Output` subdirectories in the mounted volume, as well as
the entry script `__main__.py`.
2. Edit the `Config/data_curator_parameters.json` file with your providers, dates, identifiers and output columns
(or run `kaxanuk.data_curator config-editor` on the host against the mounted volume to edit it in the browser).

Now that the configuration is set up, each time you run the container again, it will download the data for the tickers/identifiers
as configured in the parameters file, and save it to the `Output` folder.


## Customization
The `__main__.py` entry script is customizable, so you can implement your own data providers and configuration and output
handlers, and inject them from there.

You can also create your own calculated feature functions by adding them to the `Config/custom_calculations.py` file,
and adding their function name to the `columns` list in the `Config/data_curator_parameters.json` file (or typing it
into the parameter panel's column picker).
As long as the names start with the `c_` prefix, the system will use them as any other feature.

Check the [API Reference](docs/source/api_reference) to learn how to easily implement your own calculated features.


## The Road to v1.0
We believe in the need for a stable API, and have expended considerable effort into finalizing the API as much as 
possible before the first public release. We plan to avoid any changes that severely break backwards compatibility
before version 1.0, with one major exception: The Data Blocks functionality.

Data Blocks will generalize the link between the data providers and the feature column prefixes, which will allow users
to create their own data providers and feature columns for any type of data from any source without having to modify
the core code of the Data Curator. This will open the door to calculated features that incorporate all kinds of data,
like economic indicators, alternative data, financial indices and benchmarks, etc.

Once Data Blocks are implemented, we will rapidly make any necessary adjustments to the public API, and when we're
happy with it, we will work on finalizing the version 1.0 release.
