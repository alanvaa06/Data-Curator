import datetime
import decimal

from kaxanuk.data_curator.data_providers import MacroDataProviderInterface
from kaxanuk.data_curator.entities import EconomicIndicatorData, EconomicIndicatorRow


class FakeMacroProvider(MacroDataProviderInterface):
    """Returns deterministic, sparse monthly series for tests (no network)."""

    def __init__(
        self,
        *,
        monthly_values: dict[str, list[tuple[str, str]]] | None = None,
        provider_name: str = "banxico_sie",
    ):
        # monthly_values: {series_id: [(iso_date, value_str), ...]}
        # provider_name must match the catalog routing for the columns under test
        # (e.g. "banxico_sie" for e_mx_*); main() looks it up via macro_provider_name.
        self.macro_provider_name = provider_name
        self._monthly_values = monthly_values or {}

    def get_economic_data(self, *, series_ids, start_date, end_date):
        out = {}
        for sid in series_ids:
            pairs = self._monthly_values.get(sid, [])
            rows = {
                iso: EconomicIndicatorRow(
                    date=datetime.date.fromisoformat(iso),
                    value=None if v is None else decimal.Decimal(v),
                )
                for (iso, v) in pairs
            }
            out[sid] = EconomicIndicatorData(
                start_date=start_date, end_date=end_date,
                series_id=sid, series_name=sid, rows=rows,
            )
        return out

    def validate_api_key(self):
        return None
