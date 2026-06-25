"""
KaxaNuk Data Curator: Request, combine and save financial data from different provider web services.

Requires an entry script that injects the required dependencies
cf. __main__.py on the GitHub repository root

Functions
---------
main:
    Receives injected dependencies and runs the system
"""

import collections
import concurrent.futures
import importlib
import logging
import os
import sys
import types

import httpx
import pyarrow

from kaxanuk.data_curator.config_handlers._resolver import resolve_macro_requests
from kaxanuk.data_curator.entities import (
    Configuration,
    DividendData,
    EconomicIndicatorData,
    FundamentalData,
    MarketData,
    SplitData,
    MainIdentifier,
)
from kaxanuk.data_curator.exceptions import (
    ApiEndpointError,
    ColumnBuilderCircularDependenciesError,
    ColumnBuilderCustomFunctionNotFoundError,
    ColumnBuilderUnavailableEntityFieldError,
    DataBlockRowEntityErrorGroup,
    DataCuratorError,
    DataProviderPaymentError,
    EntityProcessingError,
    InjectedDependencyError,
    PassedArgumentError,
    IdentifierNotFoundError,
)
from kaxanuk.data_curator.data_providers import (
    DataProviderInterface,
    MacroDataProviderInterface,
)
from kaxanuk.data_curator.features import calculations
from kaxanuk.data_curator.output_handlers import OutputHandlerInterface
from kaxanuk.data_curator.services.column_builder import ColumnBuilder


def main(
    *,  # Force user to call function with keyword arguments
    configuration: Configuration,
    market_data_provider: DataProviderInterface,
    fundamental_data_provider: DataProviderInterface | None,
    output_handlers: list[OutputHandlerInterface],
    macro_data_providers: list[MacroDataProviderInterface] | None = None,
    custom_calculation_modules: list[types.ModuleType]|None = None,
    max_concurrent_fetches: int = 8,
    max_concurrent_computations: int = 1,
    logger_level: int = logging.WARNING,
    logger_format: str = "[%(levelname)s] %(message)s",
    logger_file: str | os.PathLike[str] | None = None,
) -> bool:
    """
    Run the data curator system.

    Parameters
    ----------
    configuration
        Assembled Configuration entity containing the user's selected configurations
    market_data_provider
        The market data provider object instance
    fundamental_data_provider
        The fundamental data provider object instance
    output_handlers
        Objects that will handle the columnar data output, will be run one by one per each main_identifier
    macro_data_providers
        Optional list of macro (non-ticker) data provider instances. When provided, the macro series
        required by the selected e_* columns are fetched once for the whole run and broadcast to every
        identifier's ColumnBuilder. None (the default) disables macro fetching, keeping behavior identical
        to runs without any e_* columns.
    custom_calculation_modules
        List of modules containing custom column calculation functions. Modules will be searched in order,
        with the function taken from the first module that declares it. If not found, the function will be
        searched in kaxanuk.data_curator.features.calculations
    max_concurrent_fetches
        Maximum number of identifiers whose data is downloaded concurrently.
        1 reproduces fully sequential fetching. Values above 32 are effectively
        capped by the shared HTTP connection pool size.
    max_concurrent_computations
        Maximum number of identifiers whose columns are calculated concurrently
        in worker processes (sidestepping the GIL). 1 (the default) keeps the
        column calculation stage fully sequential in this process. Output
        handlers always run in this process in configuration order, so output
        behavior is identical in both modes. When above 1, the calculation
        modules must be importable by name in a fresh interpreter (which is the
        case for the standard Config/custom_calculations.py setup). On
        Windows the entry script must guard its executable code with
        `if __name__ == '__main__':`, as worker processes re-import it.
    logger_level
        All logs of priority logger_level or higher will be printed to stderr
    logger_format
        The format for the logger messages. will be injected to logging.basicConfig()
    logger_file
        An optional logger file to write the logging messages to. Accepts the same argument types as `os.fspath`

    Returns
    -------
    True when all identifiers were processed to the end, False when a fatal
    error aborted the run (the error is logged at critical level).
    """
    if not isinstance(configuration, Configuration):
        msg = "Incorrect Configuration passed to main"

        raise InjectedDependencyError(msg)

    if not _is_valid_log_level(logger_level):
        msg = "Incorrect logger_level passed to main"

        raise PassedArgumentError(msg)

    logging.basicConfig(
        format=logger_format,
        level=logger_level,
        filename=logger_file
    )

    if not isinstance(market_data_provider, DataProviderInterface):
        msg = "Market data provider passed to main doesn't implement FinancialDataProviderInterface"

        raise InjectedDependencyError(msg)

    if (
        fundamental_data_provider is not None
        and not isinstance(fundamental_data_provider, DataProviderInterface)
    ):
        msg = "Fundamental data provider passed to main doesn't implement FinancialDataProviderInterface"

        raise InjectedDependencyError(msg)

    if (
        len(output_handlers) < 1
        or not all(
            isinstance(output_handler, OutputHandlerInterface)
            for output_handler in output_handlers
        )
    ):
        msg = "One or more output handlers passed to main don't implement OutputHandlerInterface"

        raise InjectedDependencyError(msg)

    if (
        not isinstance(max_concurrent_fetches, int)
        or isinstance(max_concurrent_fetches, bool)
        or max_concurrent_fetches < 1
    ):
        msg = "max_concurrent_fetches passed to main must be an integer of 1 or more"

        raise PassedArgumentError(msg)

    if (
        not isinstance(max_concurrent_computations, int)
        or isinstance(max_concurrent_computations, bool)
        or max_concurrent_computations < 1
    ):
        msg = "max_concurrent_computations passed to main must be an integer of 1 or more"

        raise PassedArgumentError(msg)

    if custom_calculation_modules is None:
        custom_calculation_modules = []

    calculation_modules = [
        *custom_calculation_modules,
        calculations
    ]

    try:
        market_data_provider.initialize(configuration=configuration)

        if fundamental_data_provider is not None:
            fundamental_data_provider.initialize(configuration=configuration)

        # Macro series are non-ticker: fetch once for the whole run, then broadcast to every identifier.
        economic_data: dict[str, EconomicIndicatorData] = {}
        if macro_data_providers:
            try:
                economic_data = _fetch_macro_data(
                    configuration=configuration,
                    macro_data_providers=macro_data_providers,
                )
            except (httpx.HTTPError, DataCuratorError, ValueError, LookupError) as error:
                # untrusted external-I/O boundary: any fetch/parse failure is fatal -> return False
                logging.getLogger(__name__).critical(str(error))

                return False

        # No identifiers: this is a standalone macro export (macro series are non-ticker),
        # handled directly and returned before any equity fetch/compute machinery is created.
        if not configuration.identifiers:
            return _export_macro_only(
                configuration=configuration,
                economic_data=economic_data,
                output_handlers=output_handlers,
            )

        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_concurrent_fetches,
            thread_name_prefix='data_curator_fetch',
        )
        compute_executor = None
        if max_concurrent_computations > 1:
            compute_executor = concurrent.futures.ProcessPoolExecutor(
                max_workers=max_concurrent_computations,
                initializer=_compute_worker_initializer,
                initargs=(list(sys.path),),
            )
        calculation_module_names = [
            module.__name__
            for module in calculation_modules
        ]
        try:
            identifiers = configuration.identifiers
            max_pending_fetches = max_concurrent_fetches * 2
            pending_fetches: collections.deque[
                tuple[
                    str,
                    concurrent.futures.Future[
                        tuple[MarketData, FundamentalData, DividendData, SplitData]
                    ],
                ]
            ] = collections.deque()
            next_identifier_index = 0
            pending_computes: collections.deque[
                tuple[str, concurrent.futures.Future]
            ] = collections.deque()
            max_pending_computes = max_concurrent_computations * 2

            while pending_fetches or next_identifier_index < len(identifiers):
                # keep up to max_pending_fetches downloads in flight, ahead of consumption
                while (
                    next_identifier_index < len(identifiers)
                    and len(pending_fetches) < max_pending_fetches
                ):
                    submitted_identifier = identifiers[next_identifier_index]
                    pending_fetches.append((
                        submitted_identifier,
                        executor.submit(
                            _fetch_identifier_data,
                            submitted_identifier,
                            configuration,
                            market_data_provider,
                            fundamental_data_provider,
                        )
                    ))
                    next_identifier_index += 1

                # consume strictly in configuration order so output is deterministic
                (main_identifier, fetch_future) = pending_fetches.popleft()
                try:
                    (
                        full_market_data,
                        full_fundamental_data,
                        full_dividend_data,
                        full_split_data,
                    ) = fetch_future.result()
                except IdentifierNotFoundError as error:
                    msg = "\n  ".join([
                        f"{main_identifier} skipping output as it presented the following error during data retrieval:",
                        str(error)
                    ])
                    logging.getLogger(__name__).error(msg)

                    continue
                except EntityProcessingError as error:
                    error_messages = _get_nested_exception_messages(error)
                    msg = "\n  ".join([
                        f"{main_identifier} skipping output as it presented the following error during data assembly:",
                        ": ".join(error_messages)
                    ])
                    logging.getLogger(__name__).error(msg)

                    continue
                except DataProviderPaymentError as error:
                    msg = "\n  ".join([
                        f"{main_identifier} skipping output as it presented the following data provider error:",
                        str(error)
                    ])
                    logging.getLogger(__name__).error(msg)

                    continue
                except DataBlockRowEntityErrorGroup as error_group:
                    msg = "\n  ".join([
                        f"{main_identifier} skipping output as it presented the following errors during data assembly:",
                        str(error_group),
                        *[
                            str(error)
                            for error in error_group.exceptions
                        ]
                    ])
                    logging.getLogger(__name__).error(msg)

                    continue

                if compute_executor is None:
                    output_columns = _compute_identifier_columns(
                        configuration=configuration,
                        calculation_modules=calculation_modules,
                        market_data=full_market_data,
                        fundamental_data=full_fundamental_data,
                        dividend_data=full_dividend_data,
                        split_data=full_split_data,
                        economic_data=economic_data,
                    )
                    _output_identifier_columns(
                        main_identifier=main_identifier,
                        output_columns=output_columns,
                        output_handlers=output_handlers,
                    )
                else:
                    # bound the compute queue so fetches don't outrun computation unbounded;
                    # draining in submission order keeps output handler order deterministic
                    while len(pending_computes) >= max_pending_computes:
                        (computed_identifier, compute_future) = pending_computes.popleft()
                        _output_identifier_columns(
                            main_identifier=computed_identifier,
                            output_columns=compute_future.result(),
                            output_handlers=output_handlers,
                        )
                    pending_computes.append((
                        main_identifier,
                        compute_executor.submit(
                            _compute_identifier_columns_in_worker,
                            configuration=configuration,
                            calculation_module_names=calculation_module_names,
                            market_data=full_market_data,
                            fundamental_data=full_fundamental_data,
                            dividend_data=full_dividend_data,
                            split_data=full_split_data,
                            economic_data=economic_data,
                        )
                    ))

            while pending_computes:
                (computed_identifier, compute_future) = pending_computes.popleft()
                _output_identifier_columns(
                    main_identifier=computed_identifier,
                    output_columns=compute_future.result(),
                    output_handlers=output_handlers,
                )
        except (
            ApiEndpointError,
            ColumnBuilderCircularDependenciesError,
            ColumnBuilderCustomFunctionNotFoundError,
            ColumnBuilderUnavailableEntityFieldError,
        ) as error:
            # logged before the executor drain in the finally block, so the
            # failure is visible immediately instead of after in-flight
            # downloads finish
            logging.getLogger(__name__).critical(str(error))

            return False
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
            if compute_executor is not None:
                compute_executor.shutdown(wait=True, cancel_futures=True)
    except (
        ApiEndpointError,
        ColumnBuilderCircularDependenciesError,
        ColumnBuilderCustomFunctionNotFoundError,
        ColumnBuilderUnavailableEntityFieldError,
    ) as error:
        logging.getLogger(__name__).critical(str(error))

        return False
    else:
        logging.getLogger(__name__).info("Finished processing data!")

        return True


def _compute_worker_initializer(parent_sys_path: list[str]) -> None:
    """
    Initialize a compute worker process with the parent's module search path.

    Ensures the calculation modules (including the user's Config.custom_calculations)
    resolve identically to the parent process.
    """
    sys.path[:] = parent_sys_path


def _compute_identifier_columns(
    *,
    configuration: Configuration,
    calculation_modules: list[types.ModuleType],
    market_data: MarketData,
    fundamental_data: FundamentalData,
    dividend_data: DividendData,
    split_data: SplitData,
    economic_data: dict[str, EconomicIndicatorData],
) -> pyarrow.Table:
    """
    Calculate the output columns for one identifier's data.

    economic_data is the run-wide macro series, fetched once and broadcast to every identifier.
    """
    column_builder = ColumnBuilder(
        calculation_modules=calculation_modules,
        configuration=configuration,
        dividend_data=dividend_data,
        fundamental_data=fundamental_data,
        market_data=market_data,
        split_data=split_data,
        economic_data=economic_data,
    )

    return column_builder.process_columns(configuration.columns)


def _compute_identifier_columns_in_worker(
    *,
    configuration: Configuration,
    calculation_module_names: list[str],
    market_data: MarketData,
    fundamental_data: FundamentalData,
    dividend_data: DividendData,
    split_data: SplitData,
    economic_data: dict[str, EconomicIndicatorData],
) -> pyarrow.Table:
    """
    Worker-process wrapper: resolve calculation modules by name, then calculate columns.

    Modules can't cross the process boundary, so they're re-imported here;
    sys.modules caches them after the first task in each worker. economic_data is a dict of
    frozen-slots dataclasses, so it pickles cleanly across the ProcessPool boundary.
    """
    calculation_modules = [
        importlib.import_module(module_name)
        for module_name in calculation_module_names
    ]

    return _compute_identifier_columns(
        configuration=configuration,
        calculation_modules=calculation_modules,
        market_data=market_data,
        fundamental_data=fundamental_data,
        dividend_data=dividend_data,
        split_data=split_data,
        economic_data=economic_data,
    )


def _fetch_macro_data(
    *,
    configuration: Configuration,
    macro_data_providers: list[MacroDataProviderInterface],
) -> dict[str, EconomicIndicatorData]:
    """
    Fetch the macro series required by the selected e_* columns, once for the whole run.

    Resolves each e_* column to its (provider, series_id) via the macro catalog, groups the
    series ids per provider, fetches them in a single call per provider, and re-keys the result
    by the full column name (e.g. 'e_mx_target_rate') so the ColumnBuilder can broadcast each
    series onto every identifier's market dates.

    Providers required by the columns but not present in macro_data_providers are skipped; the
    ColumnBuilder will then raise on the missing e_* column, surfacing the misconfiguration.

    Parameters
    ----------
    configuration
        The assembled Configuration entity (supplies columns and the date window)
    macro_data_providers
        The macro data provider instances, looked up by their macro_provider_name

    Returns
    -------
    Mapping of full e_* column name to its fetched EconomicIndicatorData series
    """
    by_provider = resolve_macro_requests(configuration.columns)
    providers_by_name = {
        provider.macro_provider_name: provider
        for provider in macro_data_providers
    }
    economic_data: dict[str, EconomicIndicatorData] = {}
    for provider_name, requests in by_provider.items():
        provider = providers_by_name.get(provider_name)
        if provider is None:
            logging.getLogger(__name__).warning(
                "Macro provider %r is required by the selected columns but is not registered in "
                "macro_data_providers; those columns will fail during computation.",
                provider_name,
            )
            continue
        series_ids = [series_id for (_column, series_id) in requests]
        fetched = provider.get_economic_data(
            series_ids=series_ids,
            start_date=configuration.start_date,
            end_date=configuration.end_date,
        )
        for (column, series_id) in requests:
            if series_id in fetched:
                economic_data[column] = fetched[series_id]
            else:
                logging.getLogger(__name__).warning(
                    "Provider %r returned no data for series %r (column %r); "
                    "that column will fail during computation.",
                    provider_name,
                    series_id,
                    column,
                )

    return economic_data


def _export_macro_only(
    *,
    configuration: Configuration,
    economic_data: dict[str, EconomicIndicatorData],
    output_handlers: list[OutputHandlerInterface],
) -> bool:
    """
    Output the selected macro series directly, for a run that has no equity identifiers.

    Each selected ``e_*`` column is written as its own two-column (m_date, value) table at the
    series' native cadence — no forward-fill, no ticker — reusing the configured output
    handlers (the column name becomes the output's main_identifier, so csv/parquet write one
    ``{column}.{ext}`` file per series). Macro series are non-ticker, so they stand alone.

    Returns
    -------
    True when at least one macro series was written. False (with a critical log) when no
    ``e_*`` columns were selected, or when none of the selected series returned data — so an
    empty run surfaces as a clear failure instead of a silent success.
    """
    logger = logging.getLogger(__name__)
    macro_columns = [
        column
        for column in configuration.columns
            if column.startswith("e_")
    ]
    if not macro_columns:
        logger.critical(
            "No identifiers configured and no macro (e_*) columns selected; nothing to do."
        )

        return False

    written = 0
    for column in macro_columns:
        series = economic_data.get(column)
        if series is None:
            logger.warning(
                "No data fetched for macro column %r; skipping its output.",
                column,
            )

            continue
        _output_identifier_columns(
            main_identifier=column,
            output_columns=_build_macro_series_table(series),
            output_handlers=output_handlers,
        )
        written += 1

    if written == 0:
        logger.critical(
            "No identifiers configured and none of the selected macro columns returned data; "
            "no output was written."
        )

        return False

    logger.info("Wrote %d macro series to the configured output.", written)

    return True


def _build_macro_series_table(series: EconomicIndicatorData) -> pyarrow.Table:
    """
    Build a two-column (m_date, value) pyarrow.Table from one macro series.

    The date column is named ``m_date`` — the canonical date-column name across every output
    (tickers emit it too), so the DuckDB handler can key its (main_identifier, m_date) upsert
    on it; a bare ``date`` makes that BY NAME upsert raise a Binder Error.

    The table preserves the series' native cadence and raw values (no forward-fill, no
    ticker). Each column is built in a single pyarrow.array() call over ALL the series' rows,
    so the inferred decimal128 precision is consistent across the whole series — building it
    batch-wise can diverge the precision and break downstream concatenation.
    """
    rows = list(series.rows.values())
    dates = [row.date for row in rows]
    values = [row.value for row in rows]

    return pyarrow.table(
        {
            "m_date": pyarrow.array(dates),
            "value": pyarrow.array(values),
        }
    )


def _output_identifier_columns(
    *,
    main_identifier: str,
    output_columns: pyarrow.Table,
    output_handlers: list[OutputHandlerInterface],
) -> None:
    """
    Pass one identifier's calculated columns to all output handlers.
    """
    for output_handler in output_handlers:
        output_handler.output_data(
            main_identifier=main_identifier,
            columns=output_columns
        )

    logging.getLogger(__name__).info(
        "Output processed for: %s",
        main_identifier
    )


def _fetch_identifier_data(
    main_identifier: str,
    configuration: Configuration,
    market_data_provider: DataProviderInterface,
    fundamental_data_provider: DataProviderInterface | None,
) -> tuple[MarketData, FundamentalData, DividendData, SplitData]:
    """
    Download all the data for a single identifier; runs inside a fetch worker thread.

    Parameters
    ----------
    main_identifier
        The identifier whose data to download
    configuration
        The assembled Configuration entity
    market_data_provider
        The market data provider object instance
    fundamental_data_provider
        The fundamental data provider object instance, or None

    Returns
    -------
    Tuple of the full market, fundamental, dividend and split data entities
    """
    logging.getLogger(__name__).info(
        "Loading data for: %s",
        main_identifier
    )
    full_market_data = market_data_provider.get_market_data(
        main_identifier=main_identifier,
        start_date=configuration.start_date,
        end_date=configuration.end_date,
    )
    if fundamental_data_provider is not None:
        full_fundamental_data = fundamental_data_provider.get_fundamental_data(
            main_identifier=main_identifier,
            period=configuration.period,
            start_date=configuration.start_date,
            end_date=configuration.end_date,
        )
        full_dividend_data = fundamental_data_provider.get_dividend_data(
            main_identifier=main_identifier,
            start_date=configuration.start_date,
            end_date=configuration.end_date,
        )
        full_split_data = fundamental_data_provider.get_split_data(
            main_identifier=main_identifier,
            start_date=configuration.start_date,
            end_date=configuration.end_date,
        )
    else:
        full_fundamental_data = FundamentalData(
            main_identifier=MainIdentifier(main_identifier),
            rows={}
        )
        full_dividend_data = DividendData(
            main_identifier=MainIdentifier(main_identifier),
            rows={}
        )
        full_split_data = SplitData(
            main_identifier=MainIdentifier(main_identifier),
            rows={}
        )

    return (
        full_market_data,
        full_fundamental_data,
        full_dividend_data,
        full_split_data,
    )


def _get_nested_exception_messages(
    nested_exception: Exception
) -> list[str]:
    """
    Unravels the nested exception, and creates a flat list of all the nested exception messages.

    Parameters
    ----------
    nested_exception
        A nested exception

    Returns
    -------
    The nested exception messages in a flat list
    """
    messages = []
    remaining_exception: Exception | BaseException | None = nested_exception
    while remaining_exception:
        messages.append(
            str(remaining_exception)
        )
        remaining_exception = remaining_exception.__cause__

    return messages


def _is_valid_log_level(level: int) -> bool:
    """
    Check if the received log level is valid.

    Parameters
    ----------
    level
        The level to check

    Returns
    -------
    Whether the received log level is valid
    """
    level_name = logging.getLevelName(level)

    return not level_name.startswith('Level ')
