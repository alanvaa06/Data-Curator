import datetime
import pytest
from kaxanuk.data_curator.data_providers import MacroDataProviderInterface
from kaxanuk.data_curator.entities import EconomicIndicatorData, EconomicIndicatorRow


class _Stub(MacroDataProviderInterface):
    def get_economic_data(self, *, series_ids, start_date, end_date):
        return {
            sid: EconomicIndicatorData(
                start_date=start_date, end_date=end_date, series_id=sid, series_name=sid,
                rows={"2020-01-01": EconomicIndicatorRow(date=datetime.date(2020, 1, 1), value=None)},
            )
            for sid in series_ids
        }

    def validate_api_key(self):
        return None


def test_cannot_instantiate_abstract():
    with pytest.raises(TypeError):
        MacroDataProviderInterface()


def test_concrete_subclass_returns_series_dict():
    provider = _Stub()
    out = provider.get_economic_data(
        series_ids=["A", "B"], start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 2, 1),
    )
    assert set(out.keys()) == {"A", "B"}
    assert isinstance(out["A"], EconomicIndicatorData)
