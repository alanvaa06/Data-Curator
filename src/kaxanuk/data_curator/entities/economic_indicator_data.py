import dataclasses
import datetime

from kaxanuk.data_curator.entities.base_data_entity import BaseDataEntity
from kaxanuk.data_curator.entities.economic_indicator_row import EconomicIndicatorRow
from kaxanuk.data_curator.exceptions import EntityValueError


@dataclasses.dataclass(frozen=True, slots=True)
class EconomicIndicatorData(BaseDataEntity):
    """A full economic-indicator time series, keyed by ISO-date string."""

    start_date: datetime.date
    end_date: datetime.date
    series_id: str
    series_name: str
    rows: dict[str, EconomicIndicatorRow]

    def __post_init__(self) -> None:
        keys = list(self.rows.keys())
        if keys != sorted(keys):
            msg = f"EconomicIndicatorData rows for {self.series_id} must be sorted by date"
            raise EntityValueError(msg)
        for row in self.rows.values():
            if not isinstance(row, EconomicIndicatorRow):
                msg = f"EconomicIndicatorData rows for {self.series_id} must be EconomicIndicatorRow"
                raise EntityValueError(msg)
