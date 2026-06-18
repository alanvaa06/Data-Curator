"""
Interface for non-ticker macro-economic data providers.
"""

import abc
import datetime
import typing

from kaxanuk.data_curator.entities import EconomicIndicatorData


class MacroDataProviderInterface(metaclass=abc.ABCMeta):
    """
    Interface for non-ticker macro-economic data providers.

    Unlike the equity DataProviderInterface, macro providers are not
    identifier-scoped: they return whole series keyed by provider series id.
    """

    # The stable lookup key the configuration uses to route series to this provider;
    # each concrete adapter sets it (e.g. "banxico_sie", "inegi", "fred", "dbnomics").
    macro_provider_name: typing.ClassVar[str]

    @abc.abstractmethod
    def get_economic_data(
        self,
        *,
        series_ids: list[str],
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> dict[str, EconomicIndicatorData]:
        """Return {series_id -> EconomicIndicatorData} for the requested ids."""

    @abc.abstractmethod
    def validate_api_key(self) -> bool | None:
        """Validate the provider key/token; return None if the provider needs none."""
