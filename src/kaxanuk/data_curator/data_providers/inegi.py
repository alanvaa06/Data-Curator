"""
INEGI macro-economic data adapter.

Thin HTTP adapter for Mexico's Instituto Nacional de Estadística y Geografía (INEGI)
Indicator Bank API (BIE — Banco de Información Económica). Authentication is via a
token embedded directly in the URL path (free registration at inegi.org.mx).
"""

import datetime
import decimal
import logging

import httpx

from kaxanuk.data_curator.data_providers.macro_data_provider_interface import (
    MacroDataProviderInterface,
)
from kaxanuk.data_curator.entities import EconomicIndicatorData, EconomicIndicatorRow
from kaxanuk.data_curator.exceptions import ApiEndpointError, DataProviderMissingKeyError

_BASE = "https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml/INDICATOR"
_MISSING = {"", None}
_HTTP_BAD_REQUEST = 400


def _is_no_results(response: httpx.Response) -> bool:
    """
    Return True when an INEGI HTTP 400 body signals 'no results' for the requested id.

    A stale or unknown indicator id makes INEGI reply 400 with a JSON array of
    ``"Key:Value"`` strings containing ``ErrorCode:100`` / "No se encontraron
    resultados" — a per-series miss, not a provider failure. The response body
    carries no token (the token lives only in the request URL path), so it is
    safe to inspect. Matched case-insensitively so a casing change upstream
    cannot silently turn a not-found back into a fatal error.
    """
    body = response.text.lower()
    return "errorcode:100" in body or "no se encontraron resultados" in body


class Inegi(MacroDataProviderInterface):
    """Thin HTTP adapter for INEGI's Indicator Bank API (BIE bank, token in path)."""

    macro_provider_name = "inegi"

    def __init__(self, *, api_key: str | None) -> None:
        self._token = api_key

    def get_economic_data(
        self,
        *,
        series_ids: list[str],
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> dict[str, EconomicIndicatorData]:
        """Fetch economic series from INEGI BIE and return as entities."""
        if not self._token:
            msg = "INEGI requires an API token (set KNDC_API_KEY_INEGI)"
            raise DataProviderMissingKeyError(msg)
        out: dict[str, EconomicIndicatorData] = {}
        for sid in series_ids:
            url = f"{_BASE}/{sid}/es/00/false/BIE/2.0/{self._token}?type=json"
            try:
                response = httpx.get(url, timeout=30)
                response.raise_for_status()
                out.update(
                    self._parse_series_payload(
                        response.json(),
                        requested_id=sid,
                        start_date=start_date,
                        end_date=end_date,
                    )
                )
            except httpx.HTTPStatusError as error:
                # Do NOT interpolate the error — its str() contains the full request
                # URL, which carries the token in the URL path. The response body is
                # token-free, so it is safe to inspect.
                if error.response.status_code == _HTTP_BAD_REQUEST and _is_no_results(error.response):
                    # Stale/unknown indicator id (400 + ErrorCode 100). One bad series must
                    # not abort the run nor drop this provider's other series — skip it.
                    logging.getLogger(__name__).warning(
                        "INEGI returned no results for series %r; skipping it.", sid
                    )
                    continue
                msg = f"INEGI request failed for series {sid!r}: HTTP {error.response.status_code}"
                raise ApiEndpointError(msg) from None
            except httpx.HTTPError as error:
                # connect / timeout / other transport errors — type name only;
                # the str() may also contain the URL.
                msg = f"INEGI request failed for series {sid!r}: {type(error).__name__}"
                raise ApiEndpointError(msg) from None
            except (ValueError, LookupError, decimal.InvalidOperation, TypeError) as error:
                # Parse errors do not contain secrets; safe to include detail.
                msg = f"INEGI response parsing failed for series {sid!r}: {error}"
                raise ApiEndpointError(msg) from error
        return out

    @staticmethod
    def _period_to_iso(period: str) -> str:
        """
        Convert an INEGI TIME_PERIOD string to an ISO date string (YYYY-MM-DD).

        Supported formats:
        - ``"YYYY"``      → annual   → ``YYYY-01-01``
        - ``"YYYY/MM"``   → monthly  → ``YYYY-MM-01``

        Quarterly (FREQ "6") notes:
        # TODO: confirm quarterly TIME_PERIOD format against a live payload (FREQ 6);
        #       GDP series are deferred for v1 so this path is untested against real data.
        #       Current behaviour: treats the segment after "/" as a month number (1-12),
        #       which will be wrong for quarter-index notation (e.g. "2020/01" for Q1,
        #       "2020/02" for Q2). Refine once a live GDP payload is available.
        """
        parts = period.replace("-", "/").split("/")
        year = int(parts[0])
        month = 1
        if len(parts) > 1 and parts[1].strip():
            token = parts[1].strip().lstrip("0") or "1"
            if token.isdigit():
                month = int(token)
        return datetime.date(year, month, 1).isoformat()

    @classmethod
    def _parse_series_payload(
        cls,
        payload: dict,
        *,
        requested_id: str,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> dict[str, EconomicIndicatorData]:
        """
        Parse a raw INEGI BIE JSON payload into ``EconomicIndicatorData`` entities.

        INEGI returns observations NEWEST-FIRST; this method sorts them ascending
        before building the entity (which enforces sorted ISO keys).

        Kept as a classmethod so unit tests can exercise parsing without network calls.
        """
        rows: dict[str, EconomicIndicatorRow] = {}

        for series in payload.get("Series", []):
            for obs in series.get("OBSERVATIONS", []):
                iso = cls._period_to_iso(obs["TIME_PERIOD"])
                raw = obs.get("OBS_VALUE")
                value = None if raw in _MISSING else decimal.Decimal(str(raw))
                rows[iso] = EconomicIndicatorRow(
                    date=datetime.date.fromisoformat(iso), value=value
                )

        return {
            requested_id: EconomicIndicatorData(
                start_date=start_date,
                end_date=end_date,
                series_id=requested_id,
                series_name=requested_id,
                rows=dict(sorted(rows.items())),  # newest-first → sorted ascending
            )
        }

    def validate_api_key(self) -> bool:
        """Return True when a token is configured, False otherwise."""
        return bool(self._token)
