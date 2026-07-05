"""
INEGI macro-economic data adapter.

Thin HTTP adapter for Mexico's Instituto Nacional de Estadística y Geografía (INEGI)
Indicator Bank API. Queries the BISE bank (Banco de Indicadores) at national
geography (``00``); the standard free developer token is provisioned for BISE only,
not the BIE economic bank — every BIE query returns HTTP 400 ``ErrorCode:100``.
Series that live solely in BIE (e.g. INPC, the headline unemployment rate) are
therefore sourced from other providers in the catalog, not from here.
Authentication is via a token embedded directly in the URL path (free registration
at inegi.org.mx).
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
# INEGI CL_FREQ codes whose TIME_PERIOD post-slash segment is a quarter index (1-4),
# not a month. Only 4 = "Trimestral" per INEGI's frequency catalogue (CL_FREQ).
_QUARTERLY_FREQS = frozenset({"4"})


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
    """Thin HTTP adapter for INEGI's Indicator Bank API (BISE bank, geo 00, token in path)."""

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
        """Fetch economic series from INEGI BISE and return as entities."""
        if not self._token:
            msg = "INEGI requires an API token (set KNDC_API_KEY_INEGI)"
            raise DataProviderMissingKeyError(msg)
        out: dict[str, EconomicIndicatorData] = {}
        for sid in series_ids:
            url = f"{_BASE}/{sid}/es/00/false/BISE/2.0/{self._token}?type=json"
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
    def _period_to_iso(period: str, freq: str | None = None) -> str:
        """
        Convert an INEGI TIME_PERIOD string to an ISO date string (YYYY-MM-DD).

        Supported formats (INEGI ``FREQ`` code from CL_FREQ in parentheses):
        - ``"YYYY"``      annual / decadal (3 Anual, 1 Decenal, …) → ``YYYY-01-01``
        - ``"YYYY/MM"``   monthly (8 Mensual)                      → ``YYYY-MM-01``
        - ``"YYYY/0Q"``   quarterly (4 Trimestral), Q in 1..4      → first month of
                          the quarter (Q1→01, Q2→04, Q3→07, Q4→10), matching the
                          DBnomics adapter's quarter convention.

        The post-slash segment is ambiguous between a month and a quarter index
        (``"2026/01"`` is both January and Q1), so ``freq`` disambiguates: only the
        quarterly FREQ codes map it as a quarter; every other slashed period is a
        month. ``freq`` is ``None`` only when a caller parses a period in isolation,
        in which case the segment is treated as a month (legacy behaviour).
        """
        parts = period.replace("-", "/").split("/")
        year = int(parts[0])
        month = 1
        if len(parts) > 1 and parts[1].strip():
            token = parts[1].strip().lstrip("0") or "1"
            if token.isdigit():
                sub = int(token)
                month = (sub - 1) * 3 + 1 if freq in _QUARTERLY_FREQS else sub
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
        Parse a raw INEGI BISE JSON payload into ``EconomicIndicatorData`` entities.

        INEGI returns observations NEWEST-FIRST; this method sorts them ascending
        before building the entity (which enforces sorted ISO keys).

        Kept as a classmethod so unit tests can exercise parsing without network calls.
        """
        rows: dict[str, EconomicIndicatorRow] = {}

        for series in payload.get("Series", []):
            freq = str(series.get("FREQ") or "")
            for obs in series.get("OBSERVATIONS", []):
                iso = cls._period_to_iso(obs["TIME_PERIOD"], freq)
                raw = obs.get("OBS_VALUE")
                value = None if raw in _MISSING else decimal.Decimal(str(raw))
                if value is not None and not value.is_finite():
                    # NaN/Infinity is never a valid observation: treat it as missing so
                    # it can't silently poison downstream rolling means/ratios.
                    value = None
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
