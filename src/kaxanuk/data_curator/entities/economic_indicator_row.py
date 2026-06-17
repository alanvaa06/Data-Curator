import dataclasses
import datetime
import decimal

from kaxanuk.data_curator.entities.base_data_entity import BaseDataEntity


@dataclasses.dataclass(frozen=True, slots=True)
class EconomicIndicatorRow(BaseDataEntity):
    """A single (date, value) observation of an economic indicator series."""

    date: datetime.date
    value: decimal.Decimal | None
