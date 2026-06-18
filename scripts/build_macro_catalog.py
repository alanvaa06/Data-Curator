"""
Macro catalog builder / verifier.

Generates verified entries for the bundled macro catalog
(``src/kaxanuk/data_curator/config_handlers/macro_catalog.json``) by querying each
provider's API live and keeping ONLY series ids that resolve to real data.

Design
------
- DBnomics (keyless): an id is real iff ``GET .../series/<path>?observations=0`` returns
  ``series.num_found >= 1``.
- FRED (keyless verify): an id is real iff ``GET fredgraph.csv?id=<ID>`` returns HTTP 200.
- Banxico SIE / INEGI: token-gated; NOT live-verified here. Their existing catalog rows
  are preserved untouched; this builder does not invent new MX ids.

Cross-region consistency comes from *wide* datasets where one code pattern spans many
countries (BIS policy rates, IMF IFS, Eurostat, World Bank WDI). The same canonical
concept is emitted per country by swapping the country code; the catalog ``region`` /
``column`` always uses a stable lowercase code so columns stay comparable even though the
underlying provider country-code systems differ.

Run
---
    python scripts/build_macro_catalog.py            # dry-run: verify + print report only
    python scripts/build_macro_catalog.py --write    # merge verified rows into the catalog json

Idempotent: re-running never duplicates rows (dedup on column and on (provider, series_id)).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import httpx

REPO = pathlib.Path(__file__).resolve().parents[1]
CATALOG = REPO / "src" / "kaxanuk" / "data_curator" / "config_handlers" / "macro_catalog.json"

DBNOMICS = "https://api.db.nomics.world/v22/series"
FREDGRAPH = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_UA = {"User-Agent": "Mozilla/5.0 (KaxanukDataCurator catalog builder)"}
_WORKERS = 8
_TIMEOUT = 30


# --------------------------------------------------------------------------------------
# Country universe.  canon = stable lowercase code used in column/region.
# Per-provider overrides only where a provider's code differs from ISO-2.
# euro_geo set only for Eurostat-covered (EU/EZ) geographies (note EL=Greece, UK=United Kingdom).
# --------------------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class Country:
    canon: str
    name: str
    iso2: str            # BIS + IMF default
    wb3: str = ""        # World Bank ISO-3 (blank => skip WB concepts)
    euro_geo: str = ""   # Eurostat geo (blank => skip Eurostat concepts)
    imf: str = ""        # IMF override (blank => iso2)
    bis: str = ""        # BIS override (blank => iso2)

    @property
    def imf_code(self) -> str:
        return self.imf or self.iso2

    @property
    def bis_code(self) -> str:
        return self.bis or self.iso2


COUNTRIES: list[Country] = [
    # canon  name                     iso2  wb3    euro_geo  imf   bis
    Country("ez", "Euro area",        "XM", "EMU", "EA",     "U2", "XM"),
    Country("de", "Germany",          "DE", "DEU", "DE"),
    Country("fr", "France",           "FR", "FRA", "FR"),
    Country("it", "Italy",            "IT", "ITA", "IT"),
    Country("es", "Spain",            "ES", "ESP", "ES"),
    Country("nl", "Netherlands",      "NL", "NLD", "NL"),
    Country("be", "Belgium",          "BE", "BEL", "BE"),
    Country("at", "Austria",          "AT", "AUT", "AT"),
    Country("ie", "Ireland",          "IE", "IRL", "IE"),
    Country("gr", "Greece",           "GR", "GRC", "EL"),
    Country("pt", "Portugal",         "PT", "PRT", "PT"),
    Country("fi", "Finland",          "FI", "FIN", "FI"),
    Country("uk", "United Kingdom",   "GB", "GBR", "UK"),
    Country("ca", "Canada",           "CA", "CAN"),
    Country("jp", "Japan",            "JP", "JPN"),
    Country("cn", "China",            "CN", "CHN"),
    Country("in", "India",            "IN", "IND"),
    Country("br", "Brazil",           "BR", "BRA"),
    Country("kr", "South Korea",      "KR", "KOR"),
    Country("au", "Australia",        "AU", "AUS"),
    Country("ch", "Switzerland",      "CH", "CHE", "CH"),
    Country("se", "Sweden",           "SE", "SWE", "SE"),
    Country("no", "Norway",           "NO", "NOR", "NO"),
    Country("dk", "Denmark",          "DK", "DNK", "DK"),
    Country("pl", "Poland",           "PL", "POL", "PL"),
    Country("cz", "Czechia",          "CZ", "CZE", "CZ"),
    Country("hu", "Hungary",          "HU", "HUN", "HU"),
    Country("ru", "Russia",           "RU", "RUS"),
    Country("za", "South Africa",     "ZA", "ZAF"),
    Country("id", "Indonesia",        "ID", "IDN"),
    Country("tr", "Turkey",           "TR", "TUR"),
    Country("sa", "Saudi Arabia",     "SA", "SAU"),
    Country("cl", "Chile",            "CL", "CHL"),
    Country("co", "Colombia",         "CO", "COL"),
    Country("pe", "Peru",             "PE", "PER"),
    Country("hk", "Hong Kong",        "HK", "HKG"),
    Country("nz", "New Zealand",      "NZ", "NZL"),
    Country("il", "Israel",           "IL", "ISR"),
    Country("th", "Thailand",         "TH", "THA"),
    Country("my", "Malaysia",         "MY", "MYS"),
    Country("ph", "Philippines",      "PH", "PHL"),
    Country("ar", "Argentina",        "AR", "ARG"),
]

# US and MX are owned by FRED / native Banxico+INEGI routing — excluded from the DBnomics matrix.
# EZ already has e_ecb_rate + e_ez_hicp, so its policy_rate/cpi concepts are skipped below.
EZ_SKIP_CONCEPTS = {"policy_rate", "cpi"}


# --------------------------------------------------------------------------------------
# Concepts.  Each yields candidate DBnomics paths; first that verifies wins.
# `commercial_ok` is the conservative redistribution read for the underlying source:
#   Eurostat / World Bank  -> "yes"        (open data, CC-BY-style, commercial reuse w/ attribution)
#   IMF / BIS              -> "restricted" (reuse permitted but conditioned; flag for a licensing pass)
# --------------------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class Concept:
    key: str               # column suffix: e_<canon>_<key>
    label: str             # human concept label
    freq: str
    commercial_ok: str
    paths: callable        # Country -> list[str] candidate DBnomics series paths


def imf(ind: str):
    return lambda c, ind=ind: [f"IMF/IFS/M.{c.imf_code}.{ind}"]


def imf_multi(*inds: str):
    return lambda c, inds=inds: [f"IMF/IFS/M.{c.imf_code}.{i}" for i in inds]


CONCEPTS: list[Concept] = [
    Concept("policy_rate", "central-bank policy rate",  "monthly",   "restricted",
            lambda c: [f"BIS/WS_CBPOL/M.{c.bis_code}"]),
    Concept("cpi",         "CPI (all items, index)",    "monthly",   "restricted", imf("PCPI_IX")),
    Concept("core_cpi",    "core CPI (index)",          "monthly",   "restricted",
            imf_multi("PCPIHA_IX", "PCPIC_IX", "PCPIX_IX")),
    Concept("fx_usd",      "FX rate (LCU per USD)",     "monthly",   "restricted", imf("ENDE_XDC_USD_RATE")),
    Concept("reserves",    "FX reserves (USD)",         "monthly",   "restricted", imf("RAFA_USD")),
    Concept("short_rate",  "short-term interest rate",  "monthly",   "restricted",
            imf_multi("FITB_PA", "FIMM_PA", "FIDR_PA")),
    Concept("ind_prod",    "industrial production (index)", "monthly", "restricted",
            imf_multi("AIP_IX", "AIPMA_IX")),
    Concept("unemployment", "unemployment rate (%)",    "monthly",   "restricted",
            imf_multi("LUR_PT", "LUR_PA")),
    Concept("10y",         "10Y govt bond yield",       "monthly",   "yes",
            lambda c: [f"Eurostat/irt_lt_mcby_m/M.MCBY.{c.euro_geo}"] if c.euro_geo else []),
    Concept("gdp_real",    "real GDP (constant USD)",   "annual",    "yes",
            lambda c: [f"WB/WDI/A-NY.GDP.MKTP.KD-{c.wb3}"] if c.wb3 else []),
    Concept("gdp_nominal", "nominal GDP (current USD)", "annual",    "yes",
            lambda c: [f"WB/WDI/A-NY.GDP.MKTP.CD-{c.wb3}"] if c.wb3 else []),
]


# --------------------------------------------------------------------------------------
# FRED US deepening (Lane B).  (column_suffix, fred_id, label, freq)
# commercial_ok kept "no" to match the existing file's conservative FRED convention.
# --------------------------------------------------------------------------------------
FRED_US: list[tuple[str, str, str, str]] = [
    ("ppi",          "PPIACO",   "US PPI (all commodities)",        "monthly"),
    ("core_pce",     "PCEPILFE", "US core PCE price index",         "monthly"),
    ("pce",          "PCEPI",    "US PCE price index",              "monthly"),
    ("3m",           "DGS3MO",   "US 3M Treasury",                  "daily"),
    ("5y",           "DGS5",     "US 5Y Treasury",                  "daily"),
    ("30y",          "DGS30",    "US 30Y Treasury",                 "daily"),
    ("ind_prod",     "INDPRO",   "US industrial production",        "monthly"),
    ("retail",       "RSAFS",    "US retail sales",                 "monthly"),
    ("payrolls",     "PAYEMS",   "US nonfarm payrolls",             "monthly"),
    ("gdp_nominal",  "GDP",      "US nominal GDP",                  "quarterly"),
    ("trade_balance", "BOPGSTB", "US trade balance (goods & svcs)", "monthly"),
    ("housing_starts", "HOUST",  "US housing starts",               "monthly"),
    ("initial_claims", "ICSA",   "US initial jobless claims",       "weekly"),
    ("sofr",         "SOFR",     "US SOFR overnight rate",          "daily"),
    ("2y10y_spread", "T10Y2Y",   "US 10Y-2Y term spread",           "daily"),
]


def verify_dbnomics(client: httpx.Client, path: str) -> bool:
    try:
        r = client.get(f"{DBNOMICS}/{path}", params={"observations": "0"}, timeout=_TIMEOUT)
        if r.status_code != 200:
            return False
        return r.json().get("series", {}).get("num_found", 0) >= 1
    except (httpx.HTTPError, ValueError):
        return False


def verify_fred(fred_id: str) -> bool:
    # httpx stalls on FRED's first TLS handshake intermittently; curl is reliable.
    # real id => HTTP 200 (CSV); bogus id => 404 (html).
    try:
        out = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "--retry", "2", "--max-time", "25", f"{FREDGRAPH}?id={fred_id}"],
            capture_output=True, text=True, timeout=90, check=False,
        )
        return out.stdout.strip() == "200"
    except (subprocess.SubprocessError, OSError):
        return False


def build_candidates() -> list[dict]:
    """Expand the matrix into flat candidate rows (unverified)."""
    rows: list[dict] = []
    # Lane A — DBnomics wide matrix
    for c in COUNTRIES:
        for concept in CONCEPTS:
            if c.canon == "ez" and concept.key in EZ_SKIP_CONCEPTS:
                continue
            paths = concept.paths(c)
            if not paths:
                continue
            rows.append({
                "_kind": "dbnomics",
                "_paths": paths,
                "column": f"e_{c.canon}_{concept.key}",
                "provider": "dbnomics",
                "name": f"{c.name} {concept.label}",
                "region": c.canon.upper(),
                "frequency": concept.freq,
                "commercial_ok": concept.commercial_ok,
            })
    # Lane B — FRED US
    for suffix, fred_id, label, freq in FRED_US:
        rows.append({
            "_kind": "fred",
            "_fred": fred_id,
            "column": f"e_us_{suffix}",
            "provider": "fred",
            "series_id": fred_id,
            "name": label,
            "region": "US",
            "frequency": freq,
            "commercial_ok": "no",
        })
    return rows


def verify_row(row: dict) -> dict | None:
    """Return a clean catalog entry if verified, else None."""
    if row["_kind"] == "fred":
        ok = verify_fred(row["_fred"])
        sid = row["_fred"]
    else:
        sid = None
        with httpx.Client(headers=_UA, follow_redirects=True) as client:
            for path in row["_paths"]:
                if verify_dbnomics(client, path):
                    sid = path
                    break
        ok = sid is not None
    if not ok:
        return None
    return {
        "column": row["column"],
        "provider": row["provider"],
        "series_id": sid,
        "name": row["name"],
        "region": row["region"],
        "frequency": row["frequency"],
        "commercial_ok": row["commercial_ok"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="merge verified rows into the catalog json")
    args = ap.parse_args()

    existing = json.loads(CATALOG.read_text(encoding="utf-8"))
    existing_cols = {e["column"] for e in existing}
    existing_pairs = {(e["provider"], e["series_id"]) for e in existing}

    candidates = build_candidates()
    print(f"Verifying {len(candidates)} candidates against live provider APIs "
          f"({_WORKERS} workers)...\n", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        results = list(pool.map(verify_row, candidates))

    verified: list[dict] = []
    dropped: list[str] = []
    for cand, res in zip(candidates, results, strict=True):
        if res is None:
            dropped.append(cand["column"])
            continue
        if res["column"] in existing_cols:
            continue  # already in catalog
        if (res["provider"], res["series_id"]) in existing_pairs:
            continue
        verified.append(res)

    # dedup within this run (column + provider/series_id)
    seen_cols: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    new_rows: list[dict] = []
    for r in verified:
        pair = (r["provider"], r["series_id"])
        if r["column"] in seen_cols or pair in seen_pairs:
            continue
        seen_cols.add(r["column"])
        seen_pairs.add(pair)
        new_rows.append(r)

    by_provider: dict[str, int] = {}
    for r in new_rows:
        by_provider[r["provider"]] = by_provider.get(r["provider"], 0) + 1

    print(f"VERIFIED NEW: {len(new_rows)}  (by provider: {by_provider})", file=sys.stderr)
    print(f"DROPPED (no live data): {len(dropped)}", file=sys.stderr)
    print("  " + ", ".join(sorted(dropped)), file=sys.stderr)

    if args.write:
        merged = existing + new_rows
        merged.sort(key=lambda e: (e["region"], e["column"]))
        CATALOG.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nWROTE {len(merged)} entries ({len(existing)} existing + {len(new_rows)} new) "
              f"-> {CATALOG}", file=sys.stderr)
    else:
        print("\n(dry-run; pass --write to merge)\n", file=sys.stderr)
        print(json.dumps(new_rows, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
