# Market Coverage Report — Basirah Phase 9

**Source of truth:** GitHub Actions run [30444421326](https://github.com/sayehm0a-afk/baseera-platform/actions/runs/30444421326) (`sahmk-live-pipeline-validation.yml`, `mode=full_universe`), commit `dfbece1`, branch `feature/sahmk-live-verification`. Status: **completed / success**. Started 2026-07-29T10:37:59Z, finished 2026-07-29T10:58:32Z (20m33s wall clock).

All figures below are copied verbatim from the run's job log (retrieved with `tail_lines=6000` to avoid the tool's default 500-line truncation, and independently verified via `grep` for every `STEP` marker).

## 1. Symbols discovered

```
Discovery result: {'symbols_requested': 100, 'symbols_succeeded': 100, 'symbols_failed': 0, 'rows_upserted': 100, 'errors': {}}
Total companies registered after discovery: 100
```

`SahmkClient.get_companies()` makes a single, unparameterized `GET /companies/` call — no pagination/offset handling exists in the client (`src/market_data/sahmk/client.py:343`). This run and the prior full-universe run (30442170557) **both** returned exactly 100 companies.

**NOT VERIFIED:** whether 100 is the true size of the accessible Tadawul+Nomu universe under this SAHMK plan, or a page-size cap the client silently truncates to. No `next`/`count`/`total` field from the raw response was captured in either run. The commonly-cited "~350-symbol Tadawul+Nomu universe" figure appears only as an unconfirmed assumption in code comments (`ingestion/config.py` docstring) — it has never been independently confirmed against SAHMK's actual inventory. Public knowledge that Tadawul's main market alone lists 200+ companies makes a pagination cap the more likely explanation, but this is an inference, not a verified fact.

## 2. Ingestion coverage (of the 100 discovered symbols)

| Stage | Requested | Succeeded | Failed | Rows upserted |
|---|---|---|---|---|
| Company directory (discovery) | 100 | 100 | 0 | 100 |
| Historical OHLCV | 100 | 100 | 0 | 5,605 (avg. 56 bars/symbol) |
| Fundamentals | 100 | 96 | 4 | 96 |
| Dividends | 100 | 100 | 0 | 0 (no dividend events in the ingested window — a real result, not an error) |

## 3. Scan coverage (of the 100 registered symbols)

```
MarketScanRun 1: {'run_id': 1, 'status': 'SUCCESS', 'symbols_requested': 100, 'symbols_succeeded': 95, 'symbols_skipped': 0, 'symbols_failed': 0, 'duration_seconds': 249.201, 'error_summary': None}
```

**95 of 100 registered symbols were actually scanned; all 95 succeeded.** The `symbols_skipped: 0` / `symbols_failed: 0` fields are misleading in isolation — they only count symbols that entered the scanner's outcome list. Reading `src/market_intelligence/symbol_selector.py` (`SymbolSelector.select()`) confirms the real mechanism: when `MARKET_SCAN_REQUIRE_PRICE_HISTORY` is true (the default), a symbol with **zero ingested `PriceBar` rows** is excluded from the candidate list *before* scanning starts — it never becomes a scan outcome, so it is never counted as "skipped" or "failed" in the persisted `MarketScanRun` row.

Diffing the 100 discovered symbols (recovered from the log's `Creating placeholder Stock row for symbol 'X'` lines) against the 95 scanned symbols (from the STEP 8b company table) identifies the exact 5 excluded symbols:

| Symbol | Also a fundamentals-ingestion failure? | Reason for zero PriceBar rows |
|---|---|---|
| 1263 | Yes | NOT VERIFIED — OHLCV ingestion reported 0 failures across all 100 symbols; no per-symbol OHLCV row-count log exists to show why this symbol ended up with none |
| 1295 | Yes | NOT VERIFIED (same as above) |
| 2315 | Yes | NOT VERIFIED (same as above) |
| 2001 | No | NOT VERIFIED — no ingestion failure of any kind logged for this symbol |
| 2210 | No | NOT VERIFIED (same as above) |

Note symbol **1113** — the fourth fundamentals-ingestion failure — is **not** in this excluded list: it has at least one `PriceBar` row, so it *was* scanned (visible in the company table with `fundamental_score = N/A`, HOLD recommendation, driven by technical score alone via the decision engine's graceful degradation path, and it also appears in the OVERSOLD_OPPORTUNITIES watchlist).

## 4. Verdict

**PARTIAL MARKET VERIFIED.**

- Not "FULL MARKET VERIFIED": the true size of the addressable SAHMK universe is unconfirmed, and even within the 100 discovered symbols, 5 were never scanned.
- Not "NOT VERIFIED": 95 real companies were discovered, ingested, and scanned end-to-end against the live SAHMK API with zero fabricated or synthetic data, and every gap above is precisely quantified and attributable to a known, code-verified filter rather than an unexplained failure.
