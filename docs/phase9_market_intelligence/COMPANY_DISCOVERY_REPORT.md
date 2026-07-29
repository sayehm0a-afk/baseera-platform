# Company Discovery Report — Basirah Phase 9

Source: GitHub Actions run 30444421326, STEP 2 and STEP 8b. All 100 discovered symbols are real Tadawul-listed tickers returned by the live SAHMK `/companies/` endpoint (confirmed via `MARKET_DATA_PROVIDER=sahmk`, `SAHMK_API_KEY` present).

## Full 100-symbol discovered universe

Recovered from the log's per-symbol placeholder-row lines (`Creating placeholder Stock row for symbol 'X' with no reference data`) plus the 95 that additionally appear in the STEP 8b scan table:

```
1010 1020 1030 1050 1060 1080 1111 1113 1120 1140 1150 1180 1182 1183 1201 1202
1210 1211 1212 1213 1214 1263 1295 1301 1302 1303 1304 1320 1321 1322 1323 1324
1810 1820 1830 1831 1832 1833 1834 1835 2001 2010 2020 2030 2040 2050 2060 2070
2080 2081 2082 2083 2084 2090 2100 2110 2120 2130 2140 2150 2160 2170 2180 2190
2200 2210 2220 2222 2223 2230 2240 2250 2270 2280 2281 2282 2283 2284 2285 2286
2287 2288 2290 2300 2310 2315 2320 2330 2340 2350 2360 2370 2380 2381 2382 3002
3003 3004 3005 3007
```

100 symbols, 100 distinct — no duplicates.

## 95 symbols that were actually scanned

See `AI_RECOMMENDATIONS_REPORT.md` for the full per-company table (symbol, name, price, technical/fundamental scores, confidence, recommendation, target, stop, horizon, risk). The 5 discovered-but-not-scanned symbols (1263, 1295, 2001, 2210, 2315) are documented with their known/unknown reasons in `MARKET_COVERAGE_REPORT.md`.

## Company reference data (name/sector) at ingestion time

Every one of the 100 symbols was logged with the identical message:

```
Creating placeholder Stock row for symbol 'X' with no reference data (name/sector) -- real reference data ingestion is a later milestone's concern, not this one's.
```

This is a pre-existing, disclosed design decision in the bulk `discover_all=True` path — not a bug introduced by this run. `name_en` values visible in the STEP 8b company table (e.g., "SAUDI ARAMCO", "RIBL", "ALRAJHI") were populated later, during the scan itself, from a different code path (see `DATA_QUALITY_REPORT.md` for the exact mechanism and its own gaps — `sector` and `name_ar` were **not** backfilled by that path).

## Market/instrument-type breakdown (Main Market / Nomu / ETF / REIT / fund)

**NOT VERIFIED.** No field distinguishing exchange segment or instrument type was captured by this run's ingestion or logging — `Stock.exchange` is not populated by the bulk-directory path (see `DATA_QUALITY_REPORT.md`), and no separate classification step exists in the current codebase. This breakdown cannot be produced from available evidence without either a code change or an additional live call, both out of scope for this report per the explicit "no new runs" constraint.
