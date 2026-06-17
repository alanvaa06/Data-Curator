import dataclasses
import datetime
import decimal

from kaxanuk.data_curator.entities.base_data_entity import BaseDataEntity
from kaxanuk.data_curator.exceptions import EntityTypeError
from kaxanuk.data_curator.services import entity_helper


@dataclasses.dataclass(frozen=True, slots=True)
class EconomicIndicatorRow(BaseDataEntity):
    """A single (date, value) observation of an economic indicator series."""

    date: datetime.date
    value: decimal.Decimal | None

    def __post_init__(self):
        field_type_errors = entity_helper.detect_field_type_errors(self)
        if len(field_type_errors):
            msg = " ".join([
                f"Field type errors found in {self.__class__.__name__} for date {self.date!s}:",
                "\n\t".join(field_type_errors)
            ])

            raise EntityTypeError(msg)
