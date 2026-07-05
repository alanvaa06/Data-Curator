"""
FRED macro-economic data adapter.

Thin HTTP adapter for the Federal Reserve Bank of St. Louis Economic Data (FRED)
REST API. Authentication is via an ``api_key`` query parameter (free BYO key at
https://fred.stlouisfed.org/docs/api/api_key.html).
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

_BASE = "https://api.stlouisfed.org/fred/series/observations"
_MISSING = {".", "", None}
_HTTP_BAD_REQUEST = 400


def _is_series_not_found(response: httpx.Response) -> bool:
    """
    Return True when a FRED HTTP 400 body signals an unknown series id.

    FRED returns 400 for several distinct causes; only an unknown series id says
    "The series does not exist." A bad key instead says "...api_key is not
    registered...", and a malformed id says "Invalid value for variable
    series_id..." — both must stay fatal, so this matches the not-found wording
    only. The response body carries no api_key (that lives in the request URL),
    so it is safe to inspect.
    """
    return "does not exist" in response.text.lower()


class Fred(MacroDataProviderInterface):
    """Thin HTTP adapter for the FRED REST API (api_key query parameter)."""

    macro_provider_name = "fred"

    def __init__(self, *, api_key: str | None) -> None:
        self._api_key = api_key

    def get_economic_data(
        self,
        *,
        series_ids: list[str],
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> dict[str, EconomicIndicatorData]:
        """Fetch economic series from FRED and return as entities."""
        if not self._api_key:
            msg = "FRED requires an API key (set KNDC_API_KEY_FRED)"
            raise DataProviderMissingKeyError(msg)
        out: dict[str, EconomicIndicatorData] = {}
        for sid in series_ids:
            params = {
                "series_id": sid,
                "api_key": self._api_key,
                "file_type": "json",
                "observation_start": start_date.isoformat(),
                "observation_end": end_date.isoformat(),
            }
            try:
                response = httpx.get(_BASE, params=params, timeout=30)
                response.raise_for_status()
                out.update(
                    self._parse_observations(
                        response.json(),
                        series_id=sid,
                        start_date=start_date,
                        end_date=end_date,
                    )
                )
            except httpx.HTTPStatusError as error:
                # Do NOT interpolate the error — its str() contains the full request
                # URL, which carries the api_key query parameter. The response body is
                # key-free, so it is safe to inspect.
                if error.response.status_code == _HTTP_BAD_REQUEST and _is_series_not_found(error.response):
                    # Stale/unknown series id (400 "The series does not exist."). One bad
                    # series must not abort the run nor drop the other requested series — skip it.
                    logging.getLogger(__name__).warning(
                        "FRED has no series %r (series does not exist); skipping it.", sid
                    )
                    continue
                msg = f"FRED request failed for series {sid!r}: HTTP {error.response.status_code}"
                raise ApiEndpointError(msg) from None
            except httpx.HTTPError as error:
                # connect / timeout / other transport errors — type name only;
                # the str() may also contain the URL.
                msg = f"FRED request failed for series {sid!r}: {type(error).__name__}"
                raise ApiEndpointError(msg) from None
            except (ValueError, LookupError, decimal.InvalidOperation, TypeError) as error:
                # Parse errors do not contain secrets; safe to include detail.
                msg = f"FRED response parsing failed for series {sid!r}: {error}"
                raise ApiEndpointError(msg) from error
        return out

    @staticmethod
    def _parse_observations(
        payload: dict,
        *,
        series_id: str,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> dict[str, EconomicIndicatorData]:
        """
        Parse a raw FRED JSON payload into an ``EconomicIndicatorData`` entity.

        FRED dates are already ISO ``YYYY-MM-DD`` — no conversion needed.
        The FRED missing-value sentinel is the string ``"."``; empty string and
        ``None`` are also treated as missing.

        Kept as a staticmethod so unit tests can exercise parsing without network calls.
        """
        rows: dict[str, EconomicIndicatorRow] = {}

        for obs in payload.get("observations", []):
            iso = datetime.date.fromisoformat(obs["date"]).isoformat()
            raw = obs.get("value")
            value = (
                None
                if raw in _MISSING
                else decimal.Decimal(str(raw))
            )
            if value is not None and not value.is_finite():
                # NaN/Infinity is never a valid observation: treat it as missing so
                # it can't silently poison downstream rolling means/ratios.
                value = None
            rows[iso] = EconomicIndicatorRow(
                date=datetime.date.fromisoformat(iso), value=value
            )

        return {
            series_id: EconomicIndicatorData(
                start_date=start_date,
                end_date=end_date,
                series_id=series_id,
                series_name=series_id,
                rows=dict(sorted(rows.items())),
            )
        }

    def validate_api_key(self) -> bool:
        """Return True when an API key is configured, False otherwise."""
        return bool(self._api_key)
