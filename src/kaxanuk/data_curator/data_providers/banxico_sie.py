"""
Banxico SIE macro-economic data adapter.

Thin HTTP adapter for the Banco de México Sistema de Información Económica (SIE)
REST API. Authentication is via a ``Bmx-Token`` header (free 64-char token).
"""

import datetime
import decimal

import httpx

from kaxanuk.data_curator.data_providers.macro_data_provider_interface import (
    MacroDataProviderInterface,
)
from kaxanuk.data_curator.entities import EconomicIndicatorData, EconomicIndicatorRow

_BASE = "https://www.banxico.org.mx/SieAPIRest/service/v1/series"
_MISSING = {"N/E", "", None}


class BanxicoSie(MacroDataProviderInterface):
    """Thin HTTP adapter for the Banxico SIE REST API (Bmx-Token header)."""

    macro_provider_name = "banxico_sie"

    def __init__(self, *, api_key: str | None) -> None:
        self._token = api_key

    def get_economic_data(
        self,
        *,
        series_ids: list[str],
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> dict[str, EconomicIndicatorData]:
        """Fetch economic series from Banxico SIE and return as entities."""
        ids = ",".join(series_ids)
        url = f"{_BASE}/{ids}/datos/{start_date.isoformat()}/{end_date.isoformat()}"
        response = httpx.get(url, headers={"Bmx-Token": self._token or ""}, timeout=30)
        response.raise_for_status()

        return self._parse_series_payload(
            response.json(), start_date=start_date, end_date=end_date
        )

    @staticmethod
    def _parse_series_payload(
        payload: dict,
        *,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> dict[str, EconomicIndicatorData]:
        """
        Parse a raw Banxico SIE JSON payload into ``EconomicIndicatorData`` entities.

        Keeps ``_parse_series_payload`` a staticmethod so unit tests can exercise
        parsing logic without network calls.
        """
        out: dict[str, EconomicIndicatorData] = {}

        for series in payload.get("bmx", {}).get("series", []):
            rows: dict[str, EconomicIndicatorRow] = {}

            for point in series.get("datos", []):
                iso = datetime.datetime.strptime(  # noqa: DTZ007
                    point["fecha"], "%d/%m/%Y"
                ).date().isoformat()

                raw = point.get("dato")
                value = (
                    None
                    if raw in _MISSING
                    else decimal.Decimal(raw.replace(",", ""))
                )
                rows[iso] = EconomicIndicatorRow(
                    date=datetime.date.fromisoformat(iso), value=value
                )

            sid = series["idSerie"]
            out[sid] = EconomicIndicatorData(
                start_date=start_date,
                end_date=end_date,
                series_id=sid,
                series_name=series.get("titulo", sid),
                rows=dict(sorted(rows.items())),
            )

        return out

    def validate_api_key(self) -> bool | None:
        """Return True when a token is configured, False otherwise."""
        return bool(self._token)
