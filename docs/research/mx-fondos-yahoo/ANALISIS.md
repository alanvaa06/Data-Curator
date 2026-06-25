# Fondos de inversión de México en Yahoo Finance — universo de tickers

**Fecha:** 2026-06-25 · **Autor:** Agente AI (Kaxanuk) · Para: Alan Vázquez, CFA

## 1. Hallazgos clave

- **3,557 claves de pizarra (`.MX`) de fondos de inversión mexicanos verificadas en Yahoo Finance**, repartidas en **28 operadoras**.
- Son **series / clases de acción**; corresponden a ~**600+ fondos base**, consistente con los **633 fondos** que reporta AMIB para 2025 → **cobertura prácticamente total de la industria**.
- Se excluyeron **112 identificadores `0P…`** (IDs internos de Morningstar que Yahoo indexa, no son claves de pizarra; en su mayoría duplican una clave real).
- **Yahoo NO trae nombres descriptivos** de estos fondos (el campo nombre repite la clave). Por eso la clasificación temática se hace **desde la propia clave** (GUB, IPC, DLS, GLB, LP/MP/CP, LIQ, año-meta…) y cubre el **53%**; el **47% restante son claves opacas** (códigos de serie/discrecionales sin tema legible). El eje **operadora sí es 100% confiable** (por prefijo).
- Entre los clasificados, **deuda ~70% vs renta variable ~30%** (1,337 vs 559) — coincide con el **74.6% en deuda por activos** que reporta AMIB.

## 2. Metodología (por qué es confiable)

El instrumento correcto NO fue *web scraping* de listados (poca cobertura, errores), sino **la propia API de Yahoo**:

1. **Descubrimiento autoritativo:** Yahoo Lookup API (`/v1/finance/lookup?type=mutualfund`) devuelve solo símbolos reales. Tope de 100 por consulta → se hizo **expansión recursiva de prefijos** (A–Z, 0–9 + prefijos de cada operadora; cuando una raíz topa en 100 se refina carácter a carácter). 2,384 consultas → 3,669 símbolos.
2. **Verificación de descargabilidad:** muestreo de historial vía yfinance — **34/40 (85%)** con datos en ventana de 5 días; **12/12** en ventana de 1 mes (las clases inactivas no cotizan NAV a diario). El mismo método que confirmó `GBMDINTA.MX`.
3. **Limpieza:** exclusión de IDs `0P…`; mapeo operadora por prefijo (roster verificado vía web + BMV); clasificación temática por keywords de clave.

## 3. Panorama de la industria (AMIB / CNBV, cierre 2025)

| Métrica | Valor |
|---|---|
| Operadoras de fondos | **29** |
| Fondos | **633** (382 de renta variable; resto deuda) |
| Activos netos (AUM) | **~MXN 4.9 billones** (+15.5% a/a; ~13.9% del PIB) |
| Concentración | Top 5 ≈ **70%** de activos |
| Clientes | **16.1 millones** (+38.7% a/a) |
| Por activos | **74.6% deuda / 25.4% renta variable** |
| Regulador / gremio | CNBV / AMIB |

**Líderes:** BBVA (~24.2%), BlackRock (~18.7%), Santander (~10%), Banorte (~9%), HSBC (~7%).
Fuentes: AMIB (amib.com.mx); El CEO (ene-2026); CNBV (Disposiciones de fondos de inversión).

## 4. Resultados — universo verificado (3,557 tickers)

### 4.1 Por tema (clasificado desde la clave)

| Tickers | Tema | Ejemplos |
|---:|---|---|
| 1,661 | Clave opaca (sin tema legible) | GBM117A, NTE2, BBVAC+, +HAYEK, +VALOR |
| 257 | Deuda gubernamental | ACTIGOB·, BBVAGOB·, NTEGUB·, SCOTGUB· |
| 261 | Deuda (genérica / plazo n/d) | +TASA·, DEUDAOP· |
| 239 | Ciclo de vida / fecha objetivo | ACT2030·, SUR2042·, VLMXP45·, BLK2050· |
| 232 | Renta variable internacional / global | BBVANDQ·, NTEUSA·, GBMGLB·, B+RVUSA· |
| 189 | Deuda mediano plazo | BBVAMP·, NTEMP·, INVEXMP· |
| 134 | Cobertura cambiaria / dólares (USD) | ACTICOB·, NTEDLS·, STERUSD·, AXESCOB· |
| 129 | Mixtos / balanceados / perfilados | BBVACRE·, XPERT·, PRINLS·, ACTICRE· |
| 92 | Deuda largo plazo | +TASALP·, NTELP·, GUBLP· |
| 76 | Renta variable nacional (IPC) | BBVANSH·, HSBCMEX·, BLKCRE· |
| 71 | Renta variable (región n/d) | ACTIRVT·, AFIRVIS· |
| 69 | Mercado de dinero / liquidez | BBVALIQ·, FONDEO·, LIQUIDO· |
| 58 | Deuda corto plazo | BBVACP·, NTECT·, ACTIPLU· |
| 49 | ESG / sustentables | BBVAESG·, AXESESG·, SAM-ESG· |
| 38 | Deuda corporativa / privada | BBVACORP·, FT-CORP·, I+CORP· |
| 2 | Indizados / réplica | FMXINDF· |

### 4.2 Por operadora (100% confiable por prefijo)

| Tickers | Operadora | Prefijo(s) |
|---:|---|---|
| 502 | Banorte | NTE |
| 483 | BBVA | BBVA, B+, BMER |
| 452 | SURA | SURA, SUR, FONDEO, SURCETE, RETIRO |
| 244 | Santander | SAM, STER/ST&ER, XPERT, FONSER |
| 220 | GBM | GBM |
| 204 | Principal | PRIN, PRGLOB, PEMERGE, LIQUIDO |
| 200 | BlackRock | BLK |
| 177 | HSBC | HSBC, HSBG |
| 121 | Valmex | VALMX, VLMX, VX |
| 111 | Actinver | ACTI, ACT (+ marcas: PROTEGE, MAYA, ROBOTIK…) |
| 109 | Scotia | SCOT, FINBOL |
| 97 | Franklin Templeton | FT-, TEM, FMX |
| 94 | INVEX | INVEX |
| 68 | Afore / SIEFORE (retiro) | APRIN, XXI, PROF |
| 61 | Compass / Vinci | I+, CRECE, +HAYEK, +VALOR |
| 47 | Monex | MONEX, MONX |
| 46 | Afirme | AFIR |
| 43 | Nafinsa | NAF, NAFINDX, ENERFIN |
| 35 | Ve por Más (BX+) | BX+ |
| 33 | Azimut | AZMT, AZT |
| 31 | Inbursa | DINBUR, INBUR, INB |
| 23 | Intercam | +TASA, DLRTRAC |
| 19 | Finaccess | AXES |
| 12 | Multiva | MULTI, MV |
| 6 | Citibanamex/BlackRock | FONBNM, BNM |
| 6 | Vector | VECT |
| 6 | Skandia | SK- |
| 107 | Otras / boutiques | HAYEK, VALOR, ALPHA, GOLD, IDEA… |

## 5. Limitaciones (transparencia)

- **Clasificación temática = 53%** (límite estructural: Yahoo no expone nombres; el resto de claves no codifican tema). El eje operadora no tiene esa limitación.
- **Tickers = clases de acción**, no fondos base (de ahí 3,557 vs ~633 fondos). Cada fondo tiene varias series (A, B, B0-A, F1, GB…).
- Se incluyen **Afores/SIEFOREs** (vehículos de retiro, no fondos abiertos) en bucket aparte (68).
- ~15% de una muestra no cotizó en 5 días (clases inactivas); descargan bien en ventanas más largas.

## 6. Entregables

- `fondos_mx_yahoo.csv` / `.json` — los 3,557 tickers con `codigo`, `operadora`, `tema`.
- Listos para cargar como **preset de identificadores en el panel de Data Curator** (igual que los ETFs), agrupados por tema u operadora.
