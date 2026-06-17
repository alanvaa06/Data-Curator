# Macro-Economic Data Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add macro-economic series (rates, inflation, GDP, employment, FX) to the Data Curator as a non-ticker Data Block whose `e_*` columns broadcast onto every ticker's existing output, sourced from Banxico SIE + INEGI (Mexico), FRED (US), and DBnomics (rest-of-world).

**Architecture:** A new `MacroDataProviderInterface` (sibling to the ticker-scoped equity `DataProviderInterface`) feeds a new `EconomicIndicatorDataBlock` with `grouping_identifier_field = None`. Macro is fetched **once** before the per-ticker loop in `main()`, then `ColumnBuilder` forward-fills each series to each ticker's market dates via the existing `_infill_data` and emits `e_*` columns through a new `case 'e':`. A curated JSON catalog maps each `e_*` column to `(provider, series_id)`; selecting `e_*` columns activates exactly the providers needed.

**Tech Stack:** Python 3.12+, pyarrow, httpx (existing pooled-HTTP helpers), pytest. Zero new runtime dependencies. Read `docs/references/python_best_practices.md` before writing code.

---

## Conventions for every task

- Run tests with the project runner: `pdm run test` for the full suite, or `pytest tests/path::test -v` for one test (the project sets `pythonpath=["src"]`).
- Lint after implementing: `pdm run lint` (ruff). Macro modules must pass ruff (see existing per-file ignores in `pyproject.toml` for any provider-specific carve-outs you need to add).
- TDD: write the failing test, run it red, implement minimal, run it green, commit.
- Commit messages: `feat:` / `test:` / `docs:` prefix; end with the `Co-Authored-By` trailer the repo uses.
- All adapter tests use **captured/sample JSON fixtures — never live API calls.**

## File structure (created/modified)

**Create:**
- `src/kaxanuk/data_curator/entities/economic_indicator_row.py`
- `src/kaxanuk/data_curator/entities/economic_indicator_data.py`
- `src/kaxanuk/data_curator/data_blocks/economic_indicators/__init__.py`
- `src/kaxanuk/data_curator/data_providers/macro_data_provider_interface.py`
- `src/kaxanuk/data_curator/data_providers/banxico_sie.py`
- `src/kaxanuk/data_curator/data_providers/inegi.py`
- `src/kaxanuk/data_curator/data_providers/fred.py`
- `src/kaxanuk/data_curator/data_providers/dbnomics.py`
- `src/kaxanuk/data_curator/config_handlers/macro_catalog.json`
- `tests/unit/entities/economic_indicator_data_test.py`
- `tests/unit/data_blocks/economic_indicator_data_block_test.py`
- `tests/unit/data_providers/banxico_sie_test.py`, `inegi_test.py`, `fred_test.py`, `dbnomics_test.py`
- `tests/unit/data_providers/fake_macro_provider.py`
- `tests/unit/services/column_builder_macro_test.py`
- `tests/unit/config_handlers/macro_resolver_test.py`

**Modify:**
- `src/kaxanuk/data_curator/entities/__init__.py` — export the new entities
- `src/kaxanuk/data_curator/data_providers/__init__.py` — export the interface + 4 adapters
- `src/kaxanuk/data_curator/services/column_builder.py` — `economic_data` param + `case 'e':`
- `src/kaxanuk/data_curator/data_curator.py` — `macro_data_providers` arg + global fetch + thread through compute
- `src/kaxanuk/data_curator/config_handlers/_resolver.py` + `configurator_interface.py` + `json_configurator.py` — macro routing + `get_macro_data_providers()`
- `templates/data_curator/__main__.py` **and** repo-root `__main__.py` — inject `macro_data_providers={...}`
- `config_handlers/column_catalog.json` (or the editor's served catalog) — add the `e_` group
- `README.md`, `CHANGELOG.md`, `docs/source/...` — provider docs
- `templates/data_curator/Config/data_curator_parameters.json` — bump `parameters_format_version`

---

## Phase 1 — Foundation: entities + non-ticker data block

### Task 1: `EconomicIndicatorRow` + `EconomicIndicatorData` entities

**Files:**
- Create: `src/kaxanuk/data_curator/entities/economic_indicator_row.py`
- Create: `src/kaxanuk/data_curator/entities/economic_indicator_data.py`
- Modify: `src/kaxanuk/data_curator/entities/__init__.py`
- Test: `tests/unit/entities/economic_indicator_data_test.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/entities/economic_indicator_data_test.py
import datetime
import decimal
import pytest
from kaxanuk.data_curator.entities import (
    EconomicIndicatorRow,
    EconomicIndicatorData,
)


def test_row_holds_date_and_value():
    row = EconomicIndicatorRow(date=datetime.date(2020, 1, 1), value=decimal.Decimal("4.25"))
    assert row.date == datetime.date(2020, 1, 1)
    assert row.value == decimal.Decimal("4.25")


def test_row_allows_none_value():
    row = EconomicIndicatorRow(date=datetime.date(2020, 1, 1), value=None)
    assert row.value is None


def test_data_holds_sorted_rows_and_metadata():
    rows = {
        "2020-01-01": EconomicIndicatorRow(date=datetime.date(2020, 1, 1), value=decimal.Decimal("4.25")),
        "2020-02-01": EconomicIndicatorRow(date=datetime.date(2020, 2, 1), value=decimal.Decimal("4.50")),
    }
    data = EconomicIndicatorData(
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2020, 2, 1),
        series_id="SF61745",
        series_name="Mexico overnight target rate",
        rows=rows,
    )
    assert data.series_id == "SF61745"
    assert list(data.rows.keys()) == ["2020-01-01", "2020-02-01"]


def test_data_rejects_unsorted_rows():
    rows = {
        "2020-02-01": EconomicIndicatorRow(date=datetime.date(2020, 2, 1), value=decimal.Decimal("4.50")),
        "2020-01-01": EconomicIndicatorRow(date=datetime.date(2020, 1, 1), value=decimal.Decimal("4.25")),
    }
    with pytest.raises(Exception):
        EconomicIndicatorData(
            start_date=datetime.date(2020, 1, 1),
            end_date=datetime.date(2020, 2, 1),
            series_id="SF61745",
            series_name="x",
            rows=rows,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/entities/economic_indicator_data_test.py -v`
Expected: FAIL with ImportError (`EconomicIndicatorRow` not in entities).

- [ ] **Step 3: Write minimal implementation**

```python
# src/kaxanuk/data_curator/entities/economic_indicator_row.py
import dataclasses
import datetime
import decimal

from kaxanuk.data_curator.entities.base_data_entity import BaseDataEntity


@dataclasses.dataclass(frozen=True, slots=True)
class EconomicIndicatorRow(BaseDataEntity):
    """A single (date, value) observation of an economic indicator series."""
    date: datetime.date
    value: decimal.Decimal | None
```

```python
# src/kaxanuk/data_curator/entities/economic_indicator_data.py
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

    def __post_init__(self):
        keys = list(self.rows.keys())
        if keys != sorted(keys):
            msg = f"EconomicIndicatorData rows for {self.series_id} must be sorted by date"
            raise EntityValueError(msg)
        for row in self.rows.values():
            if not isinstance(row, EconomicIndicatorRow):
                msg = f"EconomicIndicatorData rows for {self.series_id} must be EconomicIndicatorRow"
                raise EntityValueError(msg)
```

Add to `src/kaxanuk/data_curator/entities/__init__.py` (follow the existing `__all__` + import ordering):

```python
from kaxanuk.data_curator.entities.economic_indicator_row import EconomicIndicatorRow
from kaxanuk.data_curator.entities.economic_indicator_data import EconomicIndicatorData
```
and add `'EconomicIndicatorRow'`, `'EconomicIndicatorData'` to `__all__`.

> Note: confirm `EntityValueError` exists in `kaxanuk.data_curator.exceptions` (it is imported by `base_data_block.py`). If the project prefers a different entity error, match `market_data.py`'s `__post_init__` raise.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/entities/economic_indicator_data_test.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/kaxanuk/data_curator/entities/economic_indicator_row.py src/kaxanuk/data_curator/entities/economic_indicator_data.py src/kaxanuk/data_curator/entities/__init__.py tests/unit/entities/economic_indicator_data_test.py
git commit -m "feat: add EconomicIndicatorRow/Data entities for the macro layer"
```

### Task 2: `EconomicIndicatorDataBlock` (non-ticker block)

**Files:**
- Create: `src/kaxanuk/data_curator/data_blocks/economic_indicators/__init__.py`
- Test: `tests/unit/data_blocks/economic_indicator_data_block_test.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/data_blocks/economic_indicator_data_block_test.py
from kaxanuk.data_curator.data_blocks.economic_indicators import EconomicIndicatorDataBlock
from kaxanuk.data_curator.entities import EconomicIndicatorRow, EconomicIndicatorData


def test_block_is_non_ticker():
    # None grouping = columns broadcast to every identifier
    assert EconomicIndicatorDataBlock.grouping_identifier_field is None


def test_block_prefix_maps_e_to_row():
    assert EconomicIndicatorDataBlock.prefix_entity_map == {"e": EconomicIndicatorRow}


def test_block_clock_sync_is_date():
    assert EconomicIndicatorDataBlock.clock_sync_field is EconomicIndicatorRow.date


def test_block_main_entity():
    assert EconomicIndicatorDataBlock.main_entity is EconomicIndicatorData
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/data_blocks/economic_indicator_data_block_test.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Write minimal implementation**

```python
# src/kaxanuk/data_curator/data_blocks/economic_indicators/__init__.py
from kaxanuk.data_curator.data_blocks.base_data_block import BaseDataBlock
from kaxanuk.data_curator.entities import (
    EconomicIndicatorData,
    EconomicIndicatorRow,
)


class EconomicIndicatorDataBlock(BaseDataBlock):
    """
    Non-ticker macro data block.

    grouping_identifier_field is None, so its columns are accessible for all
    identifiers (macro series are global, not per-ticker).
    """
    clock_sync_field = EconomicIndicatorRow.date
    grouping_identifier_field = None
    main_entity = EconomicIndicatorData
    prefix_entity_map = {"e": EconomicIndicatorRow}
```

> `BaseDataBlock.__init_subclass__` validates that all four class vars are defined; `clock_sync_field = EconomicIndicatorRow.date` resolves to the slot member descriptor, matching how `MarketDailyDataBlock` references `MarketDataDailyRow.date`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/data_blocks/economic_indicator_data_block_test.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/kaxanuk/data_curator/data_blocks/economic_indicators/__init__.py tests/unit/data_blocks/economic_indicator_data_block_test.py
git commit -m "feat: add non-ticker EconomicIndicatorDataBlock"
```

### Task 3: `MacroDataProviderInterface`

**Files:**
- Create: `src/kaxanuk/data_curator/data_providers/macro_data_provider_interface.py`
- Modify: `src/kaxanuk/data_curator/data_providers/__init__.py`
- Test: `tests/unit/data_providers/macro_data_provider_interface_test.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/data_providers/macro_data_provider_interface_test.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/data_providers/macro_data_provider_interface_test.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Write minimal implementation**

```python
# src/kaxanuk/data_curator/data_providers/macro_data_provider_interface.py
import abc
import datetime

from kaxanuk.data_curator.entities import EconomicIndicatorData


class MacroDataProviderInterface(metaclass=abc.ABCMeta):
    """
    Interface for non-ticker macro-economic data providers.

    Unlike the equity DataProviderInterface, macro providers are not
    identifier-scoped: they return whole series keyed by provider series id.
    """

    @abc.abstractmethod
    def get_economic_data(
        self,
        *,
        series_ids: list[str],
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> dict[str, EconomicIndicatorData]:
        """Return {series_id -> EconomicIndicatorData} for the requested ids."""

    @abc.abstractmethod
    def validate_api_key(self) -> bool | None:
        """Validate the provider key/token; return None if the provider needs none."""
```

Add to `src/kaxanuk/data_curator/data_providers/__init__.py` `__all__` and imports:
```python
from kaxanuk.data_curator.data_providers.macro_data_provider_interface import MacroDataProviderInterface
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/data_providers/macro_data_provider_interface_test.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/kaxanuk/data_curator/data_providers/macro_data_provider_interface.py src/kaxanuk/data_curator/data_providers/__init__.py tests/unit/data_providers/macro_data_provider_interface_test.py
git commit -m "feat: add MacroDataProviderInterface"
```

### Task 4: Fake macro provider (test double)

**Files:**
- Create: `tests/unit/data_providers/fake_macro_provider.py`

- [ ] **Step 1: Write the test double** (no separate test — it is exercised by later tasks)

```python
# tests/unit/data_providers/fake_macro_provider.py
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
```

- [ ] **Step 2: Commit**

```bash
git add tests/unit/data_providers/fake_macro_provider.py
git commit -m "test: add FakeMacroProvider double for macro layer tests"
```

---

## Phase 2 — Mexico adapters (Banxico verified IDs; INEGI gated on Phase 0)

> **Phase 0 gate:** before writing INEGI catalog rows, confirm the INEGI series IDs for INPC, GDP, employment (Banxico-CPI was refuted in research). The INEGI *adapter* (Task 6) can be built and tested against a fixture now; only the catalog series IDs are gated.

### Task 5: Banxico SIE adapter

**Files:**
- Create: `src/kaxanuk/data_curator/data_providers/banxico_sie.py`
- Modify: `src/kaxanuk/data_curator/data_providers/__init__.py`
- Test: `tests/unit/data_providers/banxico_sie_test.py`

- [ ] **Step 1: Write the failing test** (maps a documented-shape fixture → entities; no network)

```python
# tests/unit/data_providers/banxico_sie_test.py
import datetime
import decimal
from kaxanuk.data_curator.data_providers.banxico_sie import BanxicoSie
from kaxanuk.data_curator.entities import EconomicIndicatorData

# Documented Banxico SIE shape: dd/mm/yyyy dates, "dato" string values, "N/E" = missing.
SAMPLE = {
    "bmx": {"series": [
        {"idSerie": "SF61745", "titulo": "Tasa objetivo",
         "datos": [{"fecha": "01/01/2020", "dato": "7.25"},
                   {"fecha": "01/02/2020", "dato": "7.00"},
                   {"fecha": "01/03/2020", "dato": "N/E"}]},
    ]}


def test_parse_maps_series_to_entity():
    data = BanxicoSie._parse_series_payload(
        SAMPLE, start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 3, 1),
    )
    series = data["SF61745"]
    assert isinstance(series, EconomicIndicatorData)
    assert series.rows["2020-01-01"].value == decimal.Decimal("7.25")
    assert series.rows["2020-03-01"].value is None  # N/E -> None
    assert list(series.rows.keys()) == ["2020-01-01", "2020-02-01", "2020-03-01"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/data_providers/banxico_sie_test.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Write minimal implementation**

```python
# src/kaxanuk/data_curator/data_providers/banxico_sie.py
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

    def __init__(self, *, api_key: str | None):
        self._token = api_key

    def get_economic_data(self, *, series_ids, start_date, end_date):
        ids = ",".join(series_ids)
        url = f"{_BASE}/{ids}/datos/{start_date.isoformat()}/{end_date.isoformat()}"
        response = httpx.get(url, headers={"Bmx-Token": self._token or ""}, timeout=30)
        response.raise_for_status()
        return self._parse_series_payload(response.json(), start_date=start_date, end_date=end_date)

    @staticmethod
    def _parse_series_payload(payload, *, start_date, end_date):
        out = {}
        for series in payload.get("bmx", {}).get("series", []):
            rows = {}
            for point in series.get("datos", []):
                iso = datetime.datetime.strptime(point["fecha"], "%d/%m/%Y").date().isoformat()  # noqa: DTZ007
                raw = point.get("dato")
                value = None if raw in _MISSING else decimal.Decimal(raw.replace(",", ""))
                rows[iso] = EconomicIndicatorRow(date=datetime.date.fromisoformat(iso), value=value)
            sid = series["idSerie"]
            out[sid] = EconomicIndicatorData(
                start_date=start_date, end_date=end_date,
                series_id=sid, series_name=series.get("titulo", sid),
                rows=dict(sorted(rows.items())),
            )
        return out

    def validate_api_key(self):
        return bool(self._token)
```

Export `BanxicoSie` from `data_providers/__init__.py`. Add a `pyproject.toml` per-file ruff ignore for `banxico_sie.py` only if needed (e.g. `DTZ007` is already handled with the inline noqa).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/data_providers/banxico_sie_test.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kaxanuk/data_curator/data_providers/banxico_sie.py src/kaxanuk/data_curator/data_providers/__init__.py tests/unit/data_providers/banxico_sie_test.py
git commit -m "feat: add Banxico SIE macro adapter"
```

### Task 6: INEGI adapter

**Files:**
- Create: `src/kaxanuk/data_curator/data_providers/inegi.py`
- Modify: `src/kaxanuk/data_curator/data_providers/__init__.py`
- Test: `tests/unit/data_providers/inegi_test.py`

- [ ] **Step 1: Write the failing test** (documented INEGI Indicator-Bank JSON shape)

```python
# tests/unit/data_providers/inegi_test.py
import datetime
import decimal
from kaxanuk.data_curator.data_providers.inegi import Inegi

SAMPLE = {
    "Series": [
        {"INDICADOR": "910392",
         "OBSERVATIONS": [
             {"TIME_PERIOD": "2020/01", "OBS_VALUE": "100.5"},
             {"TIME_PERIOD": "2020/02", "OBS_VALUE": "101.2"},
             {"TIME_PERIOD": "2020/03", "OBS_VALUE": ""},
         ]},
    ]
}


def test_parse_maps_inegi_observations():
    data = Inegi._parse_series_payload(
        SAMPLE, requested_id="910392",
        start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 3, 1),
    )
    series = data["910392"]
    assert series.rows["2020-01-01"].value == decimal.Decimal("100.5")
    assert series.rows["2020-03-01"].value is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/data_providers/inegi_test.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Write minimal implementation**

```python
# src/kaxanuk/data_curator/data_providers/inegi.py
import datetime
import decimal

import httpx

from kaxanuk.data_curator.data_providers.macro_data_provider_interface import (
    MacroDataProviderInterface,
)
from kaxanuk.data_curator.entities import EconomicIndicatorData, EconomicIndicatorRow

_BASE = "https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml/INDICATOR"


class Inegi(MacroDataProviderInterface):
    """Thin HTTP adapter for INEGI's Indicator Bank API (token in path)."""

    def __init__(self, *, api_key: str | None):
        self._token = api_key

    def get_economic_data(self, *, series_ids, start_date, end_date):
        out = {}
        for sid in series_ids:
            # geographic area 00 = national; en/BISE per the indicator
            url = f"{_BASE}/{sid}/es/00/false/BISE/2.0/{self._token}?type=json"
            response = httpx.get(url, timeout=30)
            response.raise_for_status()
            out.update(self._parse_series_payload(
                response.json(), requested_id=sid, start_date=start_date, end_date=end_date,
            ))
        return out

    @staticmethod
    def _period_to_iso(period: str) -> str:
        # INEGI periods: "2020", "2020/01", "2020/Q1" etc. Normalize to first-of-month/year ISO.
        parts = period.replace("-", "/").split("/")
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        return datetime.date(year, month, 1).isoformat()

    @classmethod
    def _parse_series_payload(cls, payload, *, requested_id, start_date, end_date):
        rows = {}
        for series in payload.get("Series", []):
            for obs in series.get("OBSERVATIONS", []):
                iso = cls._period_to_iso(obs["TIME_PERIOD"])
                raw = obs.get("OBS_VALUE")
                value = None if raw in {"", None} else decimal.Decimal(raw)
                rows[iso] = EconomicIndicatorRow(date=datetime.date.fromisoformat(iso), value=value)
        return {
            requested_id: EconomicIndicatorData(
                start_date=start_date, end_date=end_date,
                series_id=requested_id, series_name=requested_id,
                rows=dict(sorted(rows.items())),
            )
        }

    def validate_api_key(self):
        return bool(self._token)
```

> **Phase-0 dependency:** the exact INEGI indicator IDs for INPC/GDP/employment go into the catalog (Task 9), not here. Verify this URL shape and the `OBSERVATIONS`/`TIME_PERIOD` keys against one live payload during Phase 0; adjust `_parse_series_payload`/`_period_to_iso` if the live shape differs, keeping the test fixture in sync.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/data_providers/inegi_test.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kaxanuk/data_curator/data_providers/inegi.py src/kaxanuk/data_curator/data_providers/__init__.py tests/unit/data_providers/inegi_test.py
git commit -m "feat: add INEGI macro adapter"
```

---

## Phase 3 — Wiring: ColumnBuilder, main(), config routing

> **Task order within this phase:** implement Task 7 (ColumnBuilder), then **Task 9 (catalog + `resolve_macro_requests`) before Task 8 (`main()`)** — `main()._fetch_macro_data` imports `resolve_macro_requests` from `_resolver`, so the resolver must exist first. The tasks are numbered for readability but execute 7 → 9 → 8 → 10.

### Task 7: `ColumnBuilder` — `economic_data` param + `case 'e':` + infill

**Files:**
- Modify: `src/kaxanuk/data_curator/services/column_builder.py`
- Test: `tests/unit/services/column_builder_macro_test.py`

- [ ] **Step 1: Write the failing test** (forward-fill of a monthly series onto daily market dates)

```python
# tests/unit/services/column_builder_macro_test.py
import datetime
import decimal
from kaxanuk.data_curator.services.column_builder import ColumnBuilder
from kaxanuk.data_curator.entities import (
    Configuration, DividendData, FundamentalData, MarketData, MarketDataDailyRow,
    SplitData, MainIdentifier, EconomicIndicatorData, EconomicIndicatorRow,
)
from kaxanuk.data_curator.features import calculations


def _market(dates):
    rows = {d: MarketDataDailyRow(date=datetime.date.fromisoformat(d), open=None, high=None,
                                  low=None, close=decimal.Decimal("1"), volume=None, vwap=None)
            for d in dates}
    return MarketData(start_date=datetime.date.fromisoformat(dates[0]),
                      end_date=datetime.date.fromisoformat(dates[-1]),
                      main_identifier=MainIdentifier("AAPL"), daily_rows=rows)


def _empty_fundamentals(ident="AAPL"):
    return (FundamentalData(main_identifier=MainIdentifier(ident), rows={}),
            DividendData(main_identifier=MainIdentifier(ident), rows={}),
            SplitData(main_identifier=MainIdentifier(ident), rows={}))


def test_macro_column_forward_fills_to_market_dates():
    market = _market(["2020-01-01", "2020-01-15", "2020-02-01", "2020-02-15"])
    fundamentals, dividends, splits = _empty_fundamentals()
    econ = {
        "e_mx_target_rate": EconomicIndicatorData(
            start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 2, 1),
            series_id="SF61745", series_name="rate",
            rows={"2020-01-01": EconomicIndicatorRow(date=datetime.date(2020, 1, 1), value=decimal.Decimal("7.25")),
                  "2020-02-01": EconomicIndicatorRow(date=datetime.date(2020, 2, 1), value=decimal.Decimal("7.00"))},
        )
    }
    config = Configuration(  # construct via the project's Configuration factory/fields
        identifiers=(MainIdentifier("AAPL"),), columns=("m_close", "e_mx_target_rate"),
        start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 2, 15), period="quarterly",
    )
    builder = ColumnBuilder(
        calculation_modules=[calculations], configuration=config,
        dividend_data=dividends, fundamental_data=fundamentals,
        market_data=market, split_data=splits, economic_data=econ,
    )
    table = builder.process_columns(("m_close", "e_mx_target_rate"))
    col = table.column("e_mx_target_rate").to_pylist()
    # Jan 1 & Jan 15 carry 7.25; Feb 1 & Feb 15 carry 7.00 (forward fill)
    assert [str(v) for v in col] == ["7.25", "7.25", "7.00", "7.00"]
```

> Build `Configuration` using the real constructor/fields in `entities/configuration.py` — adjust the kwargs above to match (the test must use the actual Configuration signature).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/column_builder_macro_test.py -v`
Expected: FAIL — `ColumnBuilder.__init__` has no `economic_data` parameter.

- [ ] **Step 3: Write minimal implementation**

In `column_builder.py`:

1. Import the entity at the top:
```python
from kaxanuk.data_curator.entities import (
    # ...existing...
    EconomicIndicatorData,
)
```

2. Add `economic_data` to `__init__` and infill each series to market dates:
```python
    def __init__(
        self,
        *,
        calculation_modules: CalculationModules,
        configuration: Configuration,
        dividend_data: DividendData,
        fundamental_data: FundamentalData,
        market_data: MarketData,
        split_data: SplitData,
        economic_data: dict[str, EconomicIndicatorData] | None = None,
    ):
        # ...existing assignments unchanged...
        self.infilled_economic_data_rows = {
            column: self._infill_data(iter(market_data.daily_rows.keys()), series.rows)
            for column, series in (economic_data or {}).items()
        }
```

3. Thread `infilled_economic_data_rows` into both `_process_columns_with_available_dependencies` calls in `process_columns` and into the recursive call inside the method (mirror exactly how `infilled_fundamental_data_rows` is passed), adding the parameter to the method signature:
```python
    @classmethod
    def _process_columns_with_available_dependencies(
        cls,
        columns, completed_columns, postponed_columns,
        *,
        calculation_modules,
        expanded_dividend_data_rows,
        expanded_split_data_rows,
        infilled_fundamental_data_rows,
        infilled_economic_data_rows,
        market_data_rows,
    ) -> None:
```
and pass `infilled_economic_data_rows=self.infilled_economic_data_rows` at the two call sites in `process_columns`, and `infilled_economic_data_rows=infilled_economic_data_rows` at the recursive call.

4. Add the `case 'e':` to the `match column_type:` block (alongside `case 'm':`):
```python
                case 'e':       # macro economic indicators (non-ticker, broadcast to all identifiers)
                    if column not in infilled_economic_data_rows:
                        msg = f"Column not available in economic data: {column}"
                        raise ColumnBuilderUnavailableEntityFieldError(msg)
                    completed_columns[column] = cls._generate_column(
                        infilled_economic_data_rows[column],
                        'value',
                    )
```

> The macro dict is keyed by the full column name (`e_mx_target_rate`), unlike `m_`/`f_` which key by the post-prefix `column_name`. That is intentional: `_generate_column(rows, 'value')` pulls the single `value` field from each `EconomicIndicatorRow`. `_infill_data` returns `dict[date_str, EconomicIndicatorRow|None]`; `_get_field_from_row` returns None for None rows (dates before the first observation), which is correct.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/services/column_builder_macro_test.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite (no regressions — `economic_data` defaults to None)**

Run: `pdm run test`
Expected: all existing tests PASS (the new param is optional).

- [ ] **Step 6: Commit**

```bash
git add src/kaxanuk/data_curator/services/column_builder.py tests/unit/services/column_builder_macro_test.py
git commit -m "feat: ColumnBuilder emits forward-filled e_* macro columns"
```

### Task 8: `main()` — `macro_data_providers` arg + global pre-loop fetch

**Files:**
- Modify: `src/kaxanuk/data_curator/data_curator.py`
- Test: `tests/unit/data_curator_macro_test.py`

- [ ] **Step 1: Write the failing test** (macro fetched once, broadcast to two tickers)

```python
# tests/unit/data_curator_macro_test.py
import datetime
import decimal
import pyarrow
from kaxanuk.data_curator import data_curator
from kaxanuk.data_curator.entities import Configuration, MainIdentifier
from kaxanuk.data_curator.output_handlers import OutputHandlerInterface
from tests.unit.data_providers.fake_macro_provider import FakeMacroProvider
# Reuse the existing fake equity provider + a simple capture handler from the test suite.


class _Capture(OutputHandlerInterface):
    def __init__(self):
        self.tables = {}
    def output_data(self, *, main_identifier, columns):
        self.tables[main_identifier] = columns
        return True


def test_macro_fetched_once_and_broadcast(monkeypatch):
    macro = FakeMacroProvider(monthly_values={"SF61745": [("2020-01-01", "7.25")]})
    calls = {"n": 0}
    original = macro.get_economic_data
    def counting(**kw):
        calls["n"] += 1
        return original(**kw)
    macro.get_economic_data = counting
    # ... construct Configuration with identifiers ("AAPL","MSFT"), columns ("m_close","e_mx_target_rate"),
    #     a fake equity market provider returning 2 daily rows each, and a _Capture handler ...
    # ... call data_curator.main(..., macro_data_providers=[macro]) ...
    # Assert the macro provider was called exactly once (global, not per-ticker):
    assert calls["n"] == 1
```

> Fill in the Configuration + fake equity provider wiring using the existing equity-provider test doubles in `tests/unit/data_providers/`. The load-bearing assertion is `calls["n"] == 1`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/data_curator_macro_test.py -v`
Expected: FAIL — `main()` has no `macro_data_providers` parameter.

- [ ] **Step 3: Write minimal implementation**

In `data_curator.py`:

1. Add the parameter to `main()` (keyword-only, optional):
```python
    macro_data_providers: list["MacroDataProviderInterface"] | None = None,
```
Import `MacroDataProviderInterface` and `EconomicIndicatorData` at module top.

2. After `*.initialize(...)` and **before** the `executor = ThreadPoolExecutor(...)` loop, fetch macro once. The catalog routing (which columns → which provider+series) is resolved by the configurator, but `main()` receives already-instantiated providers; resolve the selected `e_*` columns against the catalog here via a helper from `config_handlers` (Task 9 exposes `resolve_macro_requests(columns)` → `{provider_name: [(column, series_id)]}`). Build:
```python
        economic_data: dict[str, EconomicIndicatorData] = {}
        if macro_data_providers:
            economic_data = _fetch_macro_data(
                configuration=configuration,
                macro_data_providers=macro_data_providers,
            )
```

3. Add `_fetch_macro_data` helper:
```python
def _fetch_macro_data(*, configuration, macro_data_providers):
    from kaxanuk.data_curator.config_handlers._resolver import resolve_macro_requests
    by_provider = resolve_macro_requests(configuration.columns)  # {provider_name: [(column, series_id)]}
    providers_by_name = {p.macro_provider_name: p for p in macro_data_providers}
    economic_data = {}
    for provider_name, requests in by_provider.items():
        provider = providers_by_name.get(provider_name)
        if provider is None:
            continue
        series_ids = [series_id for (_column, series_id) in requests]
        fetched = provider.get_economic_data(
            series_ids=series_ids,
            start_date=configuration.start_date,
            end_date=configuration.end_date,
        )
        for (column, series_id) in requests:
            if series_id in fetched:
                economic_data[column] = fetched[series_id]
    return economic_data
```
(Each adapter class gets a `macro_provider_name` class attribute: `"banxico_sie"`, `"inegi"`, `"fred"`, `"dbnomics"` — add it in their respective tasks.)

4. Pass `economic_data` into both compute paths — add `economic_data=economic_data` to the `_compute_identifier_columns(...)` call and to the `compute_executor.submit(_compute_identifier_columns_in_worker, ..., economic_data=economic_data)` kwargs, and add the parameter to both `_compute_identifier_columns` and `_compute_identifier_columns_in_worker`, forwarding into `ColumnBuilder(..., economic_data=economic_data)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/data_curator_macro_test.py -v`
Expected: PASS (macro fetched exactly once).

- [ ] **Step 5: Full suite**

Run: `pdm run test`
Expected: all PASS (`macro_data_providers` defaults to None → equity path unchanged).

- [ ] **Step 6: Commit**

```bash
git add src/kaxanuk/data_curator/data_curator.py tests/unit/data_curator_macro_test.py
git commit -m "feat: main() fetches macro data once and broadcasts to all identifiers"
```

### Task 9: catalog + `_resolver` routing + `get_macro_data_providers()`

**Files:**
- Create: `src/kaxanuk/data_curator/config_handlers/macro_catalog.json`
- Modify: `src/kaxanuk/data_curator/config_handlers/_resolver.py`, `configurator_interface.py`, `json_configurator.py`
- Test: `tests/unit/config_handlers/macro_resolver_test.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/config_handlers/macro_resolver_test.py
from kaxanuk.data_curator.config_handlers._resolver import resolve_macro_requests


def test_routes_columns_to_providers():
    requests = resolve_macro_requests(("m_close", "e_mx_target_rate", "e_us_cpi"))
    assert ("e_mx_target_rate", "SF61745") in requests["banxico_sie"]
    assert ("e_us_cpi", "CPIAUCSL") in requests["fred"]
    assert "m_close" not in str(requests)  # non-e_ columns ignored


def test_unknown_e_column_raises():
    import pytest
    from kaxanuk.data_curator.exceptions import ConfigurationError
    with pytest.raises(ConfigurationError):
        resolve_macro_requests(("e_not_in_catalog",))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/config_handlers/macro_resolver_test.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Write minimal implementation**

Create `config_handlers/macro_catalog.json` (starter set; INEGI IDs are placeholders to confirm in Phase 0 — mark them clearly):
```json
[
  {"column": "e_us_cpi", "provider": "fred", "series_id": "CPIAUCSL", "name": "US CPI (all items)", "region": "US", "frequency": "monthly", "commercial_ok": "no"},
  {"column": "e_us_core_cpi", "provider": "fred", "series_id": "CPILFESL", "name": "US core CPI", "region": "US", "frequency": "monthly", "commercial_ok": "no"},
  {"column": "e_us_fed_funds", "provider": "fred", "series_id": "FEDFUNDS", "name": "US fed funds rate", "region": "US", "frequency": "monthly", "commercial_ok": "no"},
  {"column": "e_us_2y", "provider": "fred", "series_id": "DGS2", "name": "US 2Y Treasury", "region": "US", "frequency": "daily", "commercial_ok": "no"},
  {"column": "e_us_10y", "provider": "fred", "series_id": "DGS10", "name": "US 10Y Treasury", "region": "US", "frequency": "daily", "commercial_ok": "no"},
  {"column": "e_us_unemployment", "provider": "fred", "series_id": "UNRATE", "name": "US unemployment", "region": "US", "frequency": "monthly", "commercial_ok": "no"},
  {"column": "e_us_gdp", "provider": "fred", "series_id": "GDPC1", "name": "US real GDP", "region": "US", "frequency": "quarterly", "commercial_ok": "no"},
  {"column": "e_us_m2", "provider": "fred", "series_id": "M2SL", "name": "US M2", "region": "US", "frequency": "monthly", "commercial_ok": "no"},
  {"column": "e_mx_target_rate", "provider": "banxico_sie", "series_id": "SF61745", "name": "MX target rate", "region": "MX", "frequency": "daily", "commercial_ok": "unverified"},
  {"column": "e_mx_tiie28", "provider": "banxico_sie", "series_id": "SF60648", "name": "MX TIIE 28d", "region": "MX", "frequency": "daily", "commercial_ok": "unverified"},
  {"column": "e_mx_cetes28", "provider": "banxico_sie", "series_id": "SF60633", "name": "MX Cetes 28d", "region": "MX", "frequency": "daily", "commercial_ok": "unverified"},
  {"column": "e_mx_usdmxn_fix", "provider": "banxico_sie", "series_id": "SF43718", "name": "USD/MXN FIX", "region": "MX", "frequency": "daily", "commercial_ok": "unverified"},
  {"column": "e_mx_reserves", "provider": "banxico_sie", "series_id": "SF43707", "name": "MX intl reserves", "region": "MX", "frequency": "weekly", "commercial_ok": "unverified"},
  {"column": "e_ez_hicp", "provider": "dbnomics", "series_id": "Eurostat/prc_hicp_midx/M.I15.CP00.EA", "name": "Euro-area HICP", "region": "EZ", "frequency": "monthly", "commercial_ok": "unverified"},
  {"column": "e_ecb_rate", "provider": "dbnomics", "series_id": "ECB/FM/B.U2.EUR.4F.KR.MRR_FR.LEV", "name": "ECB main refi rate", "region": "EZ", "frequency": "daily", "commercial_ok": "unverified"}
]
```
> INEGI rows (`e_mx_inpc`, `e_mx_gdp`, `e_mx_unemployment`) are intentionally omitted until Phase 0 confirms their indicator IDs; add them then with the same shape and `"provider": "inegi"`.

Add to `_resolver.py`:
```python
import json
import pathlib
from kaxanuk.data_curator.exceptions import ConfigurationError

_MACRO_CATALOG_PATH = pathlib.Path(__file__).parent / "macro_catalog.json"
_MACRO_CATALOG = {row["column"]: row for row in json.loads(_MACRO_CATALOG_PATH.read_text(encoding="utf-8"))}


def resolve_macro_requests(columns):
    """Map selected e_* columns to {provider_name: [(column, series_id), ...]}."""
    requests: dict[str, list[tuple[str, str]]] = {}
    for column in columns:
        if not column.startswith("e_"):
            continue
        entry = _MACRO_CATALOG.get(column)
        if entry is None:
            msg = f"Unknown macro column not in catalog: {column}"
            raise ConfigurationError(msg)
        requests.setdefault(entry["provider"], []).append((column, entry["series_id"]))
    return requests


def required_macro_providers(columns):
    """The set of provider names the selected columns need."""
    return set(resolve_macro_requests(columns).keys())
```

Add `get_macro_data_providers()` to `ConfiguratorInterface` (abstract) and implement in `JsonConfigurator`: read the injected `macro_data_providers` candidate dict, compute `required_macro_providers(self._columns)`, instantiate each required provider's class with its api_key, validate the key (raise `ConfigurationError` if missing/invalid), and return the list. Wire the candidate dict through `JsonConfigurator.__init__` (new `macro_data_providers` kwarg, default `{}`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/config_handlers/macro_resolver_test.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/kaxanuk/data_curator/config_handlers/ tests/unit/config_handlers/macro_resolver_test.py
git commit -m "feat: macro catalog + column->provider routing + get_macro_data_providers()"
```

### Task 10: entry scripts + format version + first end-to-end (MX)

**Files:**
- Modify: `templates/data_curator/__main__.py`, repo-root `__main__.py`
- Modify: `templates/data_curator/Config/data_curator_parameters.json` (`parameters_format_version` bump)
- Modify: `src/kaxanuk/data_curator/data_providers/banxico_sie.py`, `inegi.py` (add `macro_provider_name`)

- [ ] **Step 1: Add `macro_provider_name` class attribute to each adapter**

In `banxico_sie.py`: `macro_provider_name = "banxico_sie"` (class attr). In `inegi.py`: `macro_provider_name = "inegi"`.

- [ ] **Step 2: Inject macro providers in the entry script**

In **both** `templates/data_curator/__main__.py` and the repo-root `__main__.py`, add a `macro_data_providers={...}` kwarg to the `JsonConfigurator(...)` call:
```python
            macro_data_providers={
                'banxico_sie': {'class': kaxanuk.data_curator.data_providers.BanxicoSie,
                                'api_key': os.getenv('KNDC_API_KEY_BANXICO')},
                'inegi': {'class': kaxanuk.data_curator.data_providers.Inegi,
                          'api_key': os.getenv('KNDC_API_KEY_INEGI')},
                'fred': {'class': kaxanuk.data_curator.data_providers.Fred,
                         'api_key': os.getenv('KNDC_API_KEY_FRED')},
                'dbnomics': {'class': kaxanuk.data_curator.data_providers.Dbnomics,
                             'api_key': None},
            },
```
and pass `macro_data_providers=configurator.get_macro_data_providers()` into `kaxanuk.data_curator.main(...)`. Add the three env keys to the entry script's module docstring.

- [ ] **Step 3: Bump format version**

In `templates/data_curator/Config/data_curator_parameters.json`, bump `parameters_format_version` to the next version, and update the matching constant the configurator checks.

- [ ] **Step 4: End-to-end smoke (MX, live — requires a Banxico token)**

Run the panel: `python -m kaxanuk.data_curator start`, select a couple of tickers plus `e_mx_target_rate` and `e_mx_usdmxn_fix`, set `KNDC_API_KEY_BANXICO` in the panel, click **Save & run**.
Expected: output rows carry forward-filled `e_mx_*` columns next to `m_*`. If no token is available, instead run the full pytest suite and defer the live smoke to whoever has a token (note it explicitly in `results.md`).

- [ ] **Step 5: Commit**

```bash
git add templates/data_curator/__main__.py __main__.py templates/data_curator/Config/data_curator_parameters.json src/kaxanuk/data_curator/data_providers/banxico_sie.py src/kaxanuk/data_curator/data_providers/inegi.py
git commit -m "feat: wire macro providers into entry scripts; bump parameters format version"
```

**At this point Mexico macro works end-to-end. Phases 4-6 add FRED, DBnomics, and panel/docs polish.**

---

## Phase 4 — FRED adapter (US)

### Task 11: FRED adapter

**Files:**
- Create: `src/kaxanuk/data_curator/data_providers/fred.py`
- Modify: `src/kaxanuk/data_curator/data_providers/__init__.py`
- Test: `tests/unit/data_providers/fred_test.py`

- [ ] **Step 1: Write the failing test** (FRED observations shape)

```python
# tests/unit/data_providers/fred_test.py
import datetime
import decimal
from kaxanuk.data_curator.data_providers.fred import Fred

SAMPLE = {"observations": [
    {"date": "2020-01-01", "value": "1.5"},
    {"date": "2020-02-01", "value": "1.6"},
    {"date": "2020-03-01", "value": "."},   # FRED uses "." for missing
]}


def test_parse_maps_observations():
    data = Fred._parse_observations(
        SAMPLE, series_id="CPIAUCSL",
        start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 3, 1),
    )
    series = data["CPIAUCSL"]
    assert series.rows["2020-01-01"].value == decimal.Decimal("1.5")
    assert series.rows["2020-03-01"].value is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/data_providers/fred_test.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Write minimal implementation**

```python
# src/kaxanuk/data_curator/data_providers/fred.py
import datetime
import decimal

import httpx

from kaxanuk.data_curator.data_providers.macro_data_provider_interface import (
    MacroDataProviderInterface,
)
from kaxanuk.data_curator.entities import EconomicIndicatorData, EconomicIndicatorRow

_BASE = "https://api.stlouisfed.org/fred/series/observations"


class Fred(MacroDataProviderInterface):
    """Thin HTTP adapter for FRED (St. Louis Fed). Bring-your-own free API key."""

    macro_provider_name = "fred"

    def __init__(self, *, api_key: str | None):
        self._api_key = api_key

    def get_economic_data(self, *, series_ids, start_date, end_date):
        out = {}
        for sid in series_ids:
            params = {
                "series_id": sid, "api_key": self._api_key or "", "file_type": "json",
                "observation_start": start_date.isoformat(),
                "observation_end": end_date.isoformat(),
            }
            response = httpx.get(_BASE, params=params, timeout=30)
            response.raise_for_status()
            out.update(self._parse_observations(
                response.json(), series_id=sid, start_date=start_date, end_date=end_date,
            ))
        return out

    @staticmethod
    def _parse_observations(payload, *, series_id, start_date, end_date):
        rows = {}
        for obs in payload.get("observations", []):
            iso = obs["date"]
            raw = obs.get("value")
            value = None if raw in {".", "", None} else decimal.Decimal(raw)
            rows[iso] = EconomicIndicatorRow(date=datetime.date.fromisoformat(iso), value=value)
        return {
            series_id: EconomicIndicatorData(
                start_date=start_date, end_date=end_date,
                series_id=series_id, series_name=series_id, rows=dict(sorted(rows.items())),
            )
        }

    def validate_api_key(self):
        return bool(self._api_key)
```
Export `Fred` from `data_providers/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/data_providers/fred_test.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kaxanuk/data_curator/data_providers/fred.py src/kaxanuk/data_curator/data_providers/__init__.py tests/unit/data_providers/fred_test.py
git commit -m "feat: add FRED macro adapter (US, BYO-key)"
```

---

## Phase 5 — DBnomics adapter (rest-of-world)

### Task 12: DBnomics adapter

**Files:**
- Create: `src/kaxanuk/data_curator/data_providers/dbnomics.py`
- Modify: `src/kaxanuk/data_curator/data_providers/__init__.py`
- Test: `tests/unit/data_providers/dbnomics_test.py`

- [ ] **Step 1: Write the failing test** (DBnomics v22 series shape: parallel `period`/`value` arrays)

```python
# tests/unit/data_providers/dbnomics_test.py
import datetime
import decimal
from kaxanuk.data_curator.data_providers.dbnomics import Dbnomics

SAMPLE = {"series": {"docs": [
    {"series_code": "M.I15.CP00.EA",
     "dataset_code": "prc_hicp_midx", "provider_code": "Eurostat",
     "period": ["2020-01", "2020-02", "2020-03"],
     "value": [105.1, 105.4, "NA"]},
]}}


def test_parse_maps_parallel_arrays():
    data = Dbnomics._parse_series_payload(
        SAMPLE, requested_id="Eurostat/prc_hicp_midx/M.I15.CP00.EA",
        start_date=datetime.date(2020, 1, 1), end_date=datetime.date(2020, 3, 1),
    )
    series = data["Eurostat/prc_hicp_midx/M.I15.CP00.EA"]
    assert series.rows["2020-01-01"].value == decimal.Decimal("105.1")
    assert series.rows["2020-03-01"].value is None  # "NA" -> None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/data_providers/dbnomics_test.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Write minimal implementation**

```python
# src/kaxanuk/data_curator/data_providers/dbnomics.py
import datetime
import decimal

import httpx

from kaxanuk.data_curator.data_providers.macro_data_provider_interface import (
    MacroDataProviderInterface,
)
from kaxanuk.data_curator.entities import EconomicIndicatorData, EconomicIndicatorRow

_BASE = "https://api.db.nomics.world/v22/series"


class Dbnomics(MacroDataProviderInterface):
    """Thin HTTP adapter for DBnomics (keyless aggregator: OECD/WB/IMF/Eurostat/ECB/BIS)."""

    macro_provider_name = "dbnomics"

    def __init__(self, *, api_key: str | None = None):
        pass  # keyless

    def get_economic_data(self, *, series_ids, start_date, end_date):
        out = {}
        for sid in series_ids:
            response = httpx.get(_BASE, params={"series_ids": sid, "observations": "1"}, timeout=30)
            response.raise_for_status()
            out.update(self._parse_series_payload(
                response.json(), requested_id=sid, start_date=start_date, end_date=end_date,
            ))
        return out

    @staticmethod
    def _period_to_iso(period: str) -> str:
        parts = period.split("-")
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
        return datetime.date(year, month, day).isoformat()

    @classmethod
    def _parse_series_payload(cls, payload, *, requested_id, start_date, end_date):
        rows = {}
        for doc in payload.get("series", {}).get("docs", []):
            for period, value in zip(doc.get("period", []), doc.get("value", []), strict=False):
                iso = cls._period_to_iso(period)
                num = None if value in ("NA", None, "") else decimal.Decimal(str(value))
                rows[iso] = EconomicIndicatorRow(date=datetime.date.fromisoformat(iso), value=num)
        return {
            requested_id: EconomicIndicatorData(
                start_date=start_date, end_date=end_date,
                series_id=requested_id, series_name=requested_id, rows=dict(sorted(rows.items())),
            )
        }

    def validate_api_key(self):
        return None  # keyless
```
Export `Dbnomics` from `data_providers/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/data_providers/dbnomics_test.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite + lint**

Run: `pdm run test` then `pdm run lint`
Expected: all PASS, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add src/kaxanuk/data_curator/data_providers/dbnomics.py src/kaxanuk/data_curator/data_providers/__init__.py tests/unit/data_providers/dbnomics_test.py
git commit -m "feat: add DBnomics macro adapter (rest-of-world aggregator)"
```

---

## Phase 6 — Panel picker, docs, final verification

### Task 13: Panel column picker shows the `e_` group

**Files:**
- Modify: `src/kaxanuk/data_curator/config_handlers/column_catalog.json` (or the catalog the editor serves)
- Modify: `src/kaxanuk/data_curator/services/config_editor_page.html` if the prefix-group labels are hardcoded
- Test: extend the existing config-editor catalog test

- [ ] **Step 1: Write/extend the failing test** — assert the served catalog includes an `e_` group with `e_mx_target_rate` and `e_us_cpi`. Mirror the existing catalog test in `tests/unit/...` (find it with `pytest -k catalog`).

- [ ] **Step 2: Run it red.**

- [ ] **Step 3: Add the `e_` group** entries to `column_catalog.json` from `macro_catalog.json` (the macro catalog is the source of truth; generate the `e_` group from it). Add a human-readable group label "Economic (macro)" wherever prefix labels live.

- [ ] **Step 4: Run it green.** Run: `pdm run test -k catalog`.

- [ ] **Step 5: Commit.**

```bash
git add src/kaxanuk/data_curator/config_handlers/column_catalog.json src/kaxanuk/data_curator/services/config_editor_page.html tests/
git commit -m "feat: panel column picker exposes the e_ macro group"
```

### Task 14: Docs + CHANGELOG + final verification

**Files:**
- Modify: `README.md` (Supported Data Providers — add FRED/Banxico/INEGI/DBnomics macro layer note + the three new env keys), `docs/source/...` provider pages, `CHANGELOG.md`

- [ ] **Step 1: Update README** Supported Data Providers section: document the macro layer, the `e_*` columns, the BYO-key model, and FRED's research/non-commercial constraint (link the proposal's §6.2). Document `KNDC_API_KEY_FRED`, `KNDC_API_KEY_BANXICO`, `KNDC_API_KEY_INEGI`.

- [ ] **Step 2: CHANGELOG** entry under the next version.

- [ ] **Step 3: Full verification gate.**

Run: `pdm run test` (full suite green), `pdm run lint` (ruff clean), `pdm run docs html` if docs changed.
Expected: all green.

- [ ] **Step 4: Live panel smoke (mixed run)** — a few US + MX tickers with `e_us_cpi`, `e_mx_target_rate`, `e_ez_hicp` selected, keys set in the panel, **Save & run**; confirm `e_*` columns appear forward-filled in CSV + DuckDB output. Record the result in `docs/context/results.md`.

- [ ] **Step 5: Commit + update context docs.**

```bash
git add README.md CHANGELOG.md docs/
git commit -m "docs: document the macro data layer (FRED, Banxico, INEGI, DBnomics)"
```
Then update `docs/context/results.md`, `docs/context/sesion-log.md`, and mark the macro todo items done.

---

## Self-review notes (coverage vs spec)

- Entities → Task 1; non-ticker block → Task 2; interface → Task 3; adapters → Tasks 5, 6, 11, 12; catalog + routing → Task 9; `main()` global fetch → Task 8; `ColumnBuilder` `case 'e'` + infill → Task 7; config injection + format bump → Tasks 9, 10; panel → Task 13; docs/CHANGELOG + verification → Task 14. Output handlers need no change (covered by "e_* rides per-ticker table" — verified in Tasks 7/10).
- **Open Phase-0 gate** (INEGI INPC/GDP/employment series IDs) is called out in Tasks 6 and 9; INEGI catalog rows are deliberately deferred, so the plan ships working software (US + MX-Banxico + global) without them.
- **Adapter JSON shapes** for FRED/Banxico are well-established; **INEGI and DBnomics fixtures are documented-shape-based and must be confirmed against one live payload** (noted in Tasks 6, 12) — adjust parse + fixture together if the live shape differs.
