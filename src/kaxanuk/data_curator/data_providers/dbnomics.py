"""
DBnomics macro-economic data adapter.

Thin HTTP adapter for the DBnomics REST API (https://db.nomics.world/).
DBnomics is a keyless public aggregator — no authentication is required.
Series are identified by a three-part slash-separated path:
``<provider_code>/<dataset_code>/<series_code>``
(e.g. ``Eurostat/prc_hicp_midx/M.I15.CP00.EA``).

The API returns observations as two parallel arrays (``period`` and ``value``)
inside ``series.docs[0]`` rather than a list of objects, so parsing zips them.
"""

import datetime
import decimal

import httpx

from kaxanuk.data_curator.data_providers.macro_data_provider_interface import (
    MacroDataProviderInterface,
)
from kaxanuk.data_curator.entities import EconomicIndicatorData, EconomicIndicatorRow
from kaxanuk.data_curator.exceptions import ApiEndpointError

_BASE = "https://api.db.nomics.world/v22/series"
_MISSING = {"NA", "", None}
_PERIOD_PARTS_ANNUAL = 1
_PERIOD_PARTS_MONTHLY = 2
_PERIOD_PARTS_DAILY = 3


class Dbnomics(MacroDataProviderInterface):
    """Thin HTTP adapter for the DBnomics REST API (keyless, no authentication)."""

    macro_provider_name = "dbnomics"

    def __init__(self, *, api_key: str | None = None) -> None:
        # api_key accepted for interface symmetry but ignored — DBnomics is keyless.
        pass

    def get_economic_data(
        self,
        *,
        series_ids: list[str],
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> dict[str, EconomicIndicatorData]:
        """Fetch economic series from DBnomics and return as entities."""
        out: dict[str, EconomicIndicatorData] = {}
        for sid in series_ids:
            params = {
                "series_ids": sid,
                "observations": "1",
            }
            try:
                response = httpx.get(_BASE, params=params, timeout=30)
                response.raise_for_status()
                out.update(
                    self._parse_series_payload(
                        response.json(),
                        requested_id=sid,
                        start_date=start_date,
                        end_date=end_date,
                    )
                )
            except (httpx.HTTPError, ValueError, LookupError, decimal.InvalidOperation, TypeError) as error:
                msg = f"DBnomics request or response parsing failed for series {sid!r}: {error}"
                raise ApiEndpointError(msg) from error
        return out

    @staticmethod
    def _period_to_iso(period: str) -> str:
        """
        Convert a DBnomics period string to an ISO date string (YYYY-MM-DD).

        DBnomics uses dash-separated period formats:
        - Annual:  ``YYYY``        → ``YYYY-01-01``
        - Monthly: ``YYYY-MM``     → ``YYYY-MM-01``
        - Daily:   ``YYYY-MM-DD``  → ``YYYY-MM-DD`` (passthrough)

        Raises ``ValueError`` for any unrecognised format.
        """
        parts = period.split("-")
        if len(parts) == _PERIOD_PARTS_ANNUAL:
            # Annual — must be a 4-digit year
            return f"{parts[0]}-01-01"
        if len(parts) == _PERIOD_PARTS_MONTHLY:
            # Monthly — YYYY-MM
            return f"{parts[0]}-{parts[1]}-01"
        if len(parts) == _PERIOD_PARTS_DAILY:
            # Daily — YYYY-MM-DD (validate via fromisoformat)
            return datetime.date.fromisoformat(period).isoformat()
        msg = f"Unrecognised DBnomics period format: {period!r}"
        raise ValueError(msg)

    @staticmethod
    def _parse_series_payload(
        payload: dict,
        *,
        requested_id: str,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> dict[str, EconomicIndicatorData]:
        """
        Parse a raw DBnomics JSON payload into an ``EconomicIndicatorData`` entity.

        The DBnomics response wraps observations as two parallel arrays
        (``period`` and ``value``) inside ``series.docs[0]``.  Values may be
        JSON numbers or the string sentinel ``"NA"``; empty string and ``None``
        are also treated as missing.

        Kept as a staticmethod so unit tests can exercise parsing without
        network calls.
        """
        rows: dict[str, EconomicIndicatorRow] = {}

        docs = payload["series"]["docs"]
        if docs:
            doc = docs[0]
            periods = doc.get("period", [])
            values = doc.get("value", [])
            for period, raw in zip(periods, values, strict=False):
                iso = Dbnomics._period_to_iso(period)
                value = (
                    None
                    if raw in _MISSING
                    else decimal.Decimal(str(raw))
                )
                rows[iso] = EconomicIndicatorRow(
                    date=datetime.date.fromisoformat(iso), value=value
                )

        return {
            requested_id: EconomicIndicatorData(
                start_date=start_date,
                end_date=end_date,
                series_id=requested_id,
                series_name=requested_id,
                rows=dict(sorted(rows.items())),
            )
        }

    def validate_api_key(self) -> None:
        """DBnomics is keyless — always returns None."""
