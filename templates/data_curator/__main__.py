"""
Example entry script that reads configuration from a JSON file and outputs to csv or parquet.

Edit the parameters through the editor:  kaxanuk.data_curator config-editor

The `if __name__ == '__main__'` guard is required: column calculations run in
worker processes, which re-import this script on Windows.

Environment Variables
---------------------
KNDC_API_KEY_FMP : str
    Api key for the Financial Modeling Prep data provider
KNDC_API_KEY_LSEG : str
    Api key for the LSEG Workspace data provider
"""

import json
import os
import pathlib

import kaxanuk.data_curator


def run():
    # Load the user's environment variables from Config/.env, including data provider API keys
    kaxanuk.data_curator.load_config_env()

    # Load user's custom calculations module, if exists in Config dir
    custom_calculations_file = 'Config/custom_calculations.py'
    if pathlib.Path(custom_calculations_file).is_file():
        from Config import custom_calculations  # noqa: PLC0415  # only importable when the user created it
        custom_calculation_modules = [custom_calculations]
    else:
        custom_calculation_modules = []

    # Load the configuration from the JSON file
    parameters_json_file = 'Config/data_curator_parameters.json'

    # the output directory is configurable in the parameters file (panel: General section);
    # a folder outside cloud-synced locations (OneDrive/Dropbox) runs noticeably faster
    output_base_dir = 'Output'
    try:
        parameters_content = pathlib.Path(parameters_json_file).read_text(encoding='utf-8')
        configured_dir = json.loads(parameters_content).get('general', {}).get('output_directory')
        if isinstance(configured_dir, str) and configured_dir.strip():
            output_base_dir = configured_dir.strip()
    except (OSError, json.JSONDecodeError):
        pass  # missing/invalid file is reported properly by the configurator below
    try:
        configurator = kaxanuk.data_curator.config_handlers.JsonConfigurator(
            file_path=parameters_json_file,
            data_providers={
                'financial_modeling_prep': {
                    'class': kaxanuk.data_curator.data_providers.FinancialModelingPrep,
                    'api_key': os.getenv('KNDC_API_KEY_FMP'),   # set this up in the Config/.env file
                },
                'lseg_workspace': {
                    'class': kaxanuk.data_curator.data_providers.LsegWorkspace,
                    'api_key': os.getenv('KNDC_API_KEY_LSEG'),  # set this up in the Config/.env file
                },
                'yahoo_finance': {
                    'class': kaxanuk.data_curator.load_data_provider_extension(
                        extension_name='yahoo_finance',
                        extension_class_name='YahooFinance',
                    ),
                    'api_key': None     # this provider doesn't use API key
                },
            },
            output_handlers={
                'csv': kaxanuk.data_curator.output_handlers.CsvOutput(
                    output_base_dir=output_base_dir,
                ),
                'duckdb': kaxanuk.data_curator.output_handlers.DuckdbOutput(
                    output_base_dir=output_base_dir,
                ),
                'parquet': kaxanuk.data_curator.output_handlers.ParquetOutput(
                    output_base_dir=output_base_dir,
                ),
            },
        )
    except kaxanuk.data_curator.exceptions.DataCuratorError:
        # the configurator already logged the error details
        return False

    # Run this puppy! Returns False when a fatal error aborted the run.
    return kaxanuk.data_curator.main(
        configuration=configurator.get_configuration(),
        market_data_provider=configurator.get_market_data_provider(),
        fundamental_data_provider=configurator.get_fundamental_data_provider(),
        output_handlers=[configurator.get_output_handler()],
        custom_calculation_modules=custom_calculation_modules,  # Optional
        max_concurrent_computations=4,  # column calculations in worker processes; set to 1 for fully sequential
        logger_level=configurator.get_logger_level(),           # Optional
    )


if __name__ == '__main__':
    raise SystemExit(0 if run() else 1)
