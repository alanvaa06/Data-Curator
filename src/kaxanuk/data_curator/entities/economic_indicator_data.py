import dataclasses
import datetime

from kaxanuk.data_curator.entities.base_data_entity import BaseDataEntity
from kaxanuk.data_curator.entities.economic_indicator_row import EconomicIndicatorRow
from kaxanuk.data_curator.exceptions import (
    EntityTypeError,
    EntityValueError,
)
from kaxanuk.data_curator.services import (
    entity_helper,
    validator,
)


@dataclasses.dataclass(frozen=True, slots=True)
class EconomicIndicatorData(BaseDataEntity):
    """A full economic-indicator time series, keyed by ISO-date string."""

    start_date: datetime.date
    end_date: datetime.date
    series_id: str
    series_name: str
    rows: dict[str, EconomicIndicatorRow]

    def __post_init__(self) -> None:
        field_type_errors = entity_helper.detect_field_type_errors(self)
        if len(field_type_errors):
            msg = " ".join([
                f"Field type errors found in {self.__class__.__name__}:",
                "\n\t".join(field_type_errors)
            ])

            raise EntityTypeError(msg)

        if any(
            not validator.is_date_pattern(key)
            for key in self.rows
        ):
            msg = f"{self.__class__.__name__}.rows keys need to be date strings in 'YYYY-MM-DD' format"

            raise EntityValueError(msg)

        if list(self.rows.keys()) != sorted(self.rows.keys()):
            msg = f"{self.__class__.__name__}.rows are not correctly sorted by date"

            raise EntityValueError(msg)

        if not all(
            isinstance(row, EconomicIndicatorRow)
            for row in self.rows.values()
        ):
            msg = f"Incorrect data in {self.__class__.__name__}.rows"

            raise EntityValueError(msg)
