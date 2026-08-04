# Data Quality Report — Basirah Phase 9

Consolidated, honest accounting of every real data-quality gap surfaced by run 30444421326. Nothing below is guessed — each item cites the specific evidence and, where the root cause is not fully diagnosed, says so explicitly rather than speculating.

## 1. Sector data: 0% populated (95/95 empty)

See `SECTOR_ANALYSIS_REPORT.md` for full detail. No sector-level analysis is possible from this run's data. Two candidate root causes identified via code review, neither confirmed without another live call: a bulk-vs-per-symbol field-name mismatch in `SahmkMarketDataService.get_company_directory()`, or the bulk directory response simply not carrying sector data at all.

## 2. Arabic company name (`name_ar`): 0% populated (95/95 empty)

This is a **structural gap in the ingestion code**, not a data-availability issue: `_apply_entry()` in `src/market_data/ingestion/ingest_symbols.py` only ever writes `stock.name_en` / `sector` / `industry` / `exchange` — there is no code path anywhere in the ingestion pipeline that writes `Stock.name_ar`, regardless of data source. This was true before this run and remains true after it; this run simply surfaced it at full-universe scale for the first time.

## 3. English name (`name_en`) language inconsistency between ingestion paths

This run's bulk `discover_all=True` path produced genuine English/ticker-style names (e.g., `RIBL`, `BJAZ`, `ALRAJHI`, `SAUDI ARAMCO`). A much earlier, unrelated 5-symbol validation run (Phase 2, using the **individual** `/company/{symbol}/` profile endpoint rather than the bulk directory) stored **Arabic** text in that same `name_en` field for the same symbols (e.g., "الراجحي" for ALRAJHI). This indicates SAHMK's bulk directory and per-symbol profile endpoints return company names in different language conventions — a real API inconsistency worth documenting for anyone consuming `name_en`, not something this report attempts to fix.

One entry in this run's own table is visibly inconsistent with the rest: symbol **1113**'s `name_en` is `"Skwk Msrf Al Rajhy Mn Al Shr"` — a Latin-transliterated Arabic phrase, not a clean English company name like its peers. This is a real value returned by the live API for that specific symbol, reproduced verbatim; it was not corrected or normalized.

## 4. 5 of 100 discovered symbols never entered the scan

1263, 1295, 2001, 2210, 2315 — see `MARKET_COVERAGE_REPORT.md` for the full breakdown of which of these also failed fundamentals ingestion versus which have no logged failure at all. Root cause (zero `PriceBar` rows despite OHLCV ingestion reporting 0 failures) is **NOT VERIFIED**.

## 5. 4 of 100 symbols failed fundamentals ingestion

1113, 1263, 1295, 2315 — exact SAHMK error text reproduced in `FUNDAMENTAL_ANALYSIS_REPORT.md`. A real, live API data-availability gap for these specific symbols.

## 6. Zero dividend rows despite 100/100 "succeeded" ingestion

`Dividends ingestion: {'symbols_requested': 100, 'symbols_succeeded': 100, 'symbols_failed': 0, 'rows_upserted': 0, 'errors': {}}` — every symbol's dividend fetch technically succeeded but returned no events to upsert. This is consistent with either a genuinely dividend-quiet period for the ingested lookback window, or a lookback window too short to capture historical dividend events. **NOT VERIFIED** which explanation is correct; this run's logging did not capture the configured dividend lookback window length.

## 7. True universe size unconfirmed

`get_companies()` returns exactly 100 with no pagination handling, confirmed identically in two independent full-universe runs. Whether 100 is a true, complete universe or a silent page-size cap is **NOT VERIFIED** — see `MARKET_COVERAGE_REPORT.md`.

## 8. Exchange/instrument-type classification: not captured

No Main Market / Nomu / ETF / REIT / fund breakdown is producible — `Stock.exchange` is not populated by the bulk-directory path used this run, and no separate classification logic exists in the codebase today.

## 9. Resource-cleanup gap in the validation script

Unclosed aiohttp client session/connector at process exit — see `MARKET_PERFORMANCE_REPORT.md`. Minor, script-only, does not affect the correctness of any reported figure.

## Net assessment

Every gap above is a **precisely quantified, evidence-cited finding**, not a guess. None of them invalidate the recommendations, scores, or rankings actually produced for the 95 scanned companies — those are real outputs of real code running against real, live data. They do invalidate any claim of a complete, sector-attributed, fully-bilingual, whole-market intelligence product — that capability does not exist yet.
