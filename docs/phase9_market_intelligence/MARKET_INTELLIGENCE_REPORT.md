# Market Intelligence Report — Basirah Phase 9

This is the top-level index for Phase 9's evidence-based Saudi market intelligence validation. It summarizes the run and points to the detailed reports; it does not duplicate their full data.

## Source of truth

- **Workflow run:** [30444421326](https://github.com/sayehm0a-afk/baseera-platform/actions/runs/30444421326) — `sahmk-live-pipeline-validation.yml`, `mode=full_universe`
- **Branch:** `feature/sahmk-live-verification` (never merged to `main`)
- **Commit scanned:** `dfbece1`
- **Status:** completed / success
- **Window:** 2026-07-29T10:37:59Z → 2026-07-29T10:58:32Z (20m33s)
- **Data source:** live SAHMK API only (`market_data_provider=sahmk`, `fundamental_data_provider=sahmk`, both confirmed at STEP 1). No fixtures, no mocks, no synthetic fallback data anywhere in this run's evidence chain.

## Headline numbers

| Metric | Value |
|---|---|
| Companies discovered | 100 (real, but see universe-size caveat below) |
| Companies successfully ingested (OHLCV) | 100 |
| Companies with valid fundamentals | 96 |
| Companies actually scanned | 95 |
| Recommendations generated | 95 (BUY 19 / HOLD 57 / SELL 19 / STRONG_BUY 0 / STRONG_SELL 0) |
| Real SAHMK API calls made | 400 |
| Sectors with usable data | 0 (NOT VERIFIED — see `SECTOR_ANALYSIS_REPORT.md`) |

## Verdict: PARTIAL MARKET VERIFIED

Not FULL MARKET VERIFIED (universe size unconfirmed, 5 discovered symbols unscanned, sector data entirely absent). Not NOT VERIFIED (95 real companies were discovered, ingested, and scanned end-to-end with zero fabricated data, every number reproducible from the job log, and every gap precisely quantified). Full justification in `MARKET_COVERAGE_REPORT.md`.

## Report index

| File | Covers |
|---|---|
| `MARKET_COVERAGE_REPORT.md` | Discovery/ingestion/scan coverage, the 100→95 gap, universe-size caveat |
| `COMPANY_DISCOVERY_REPORT.md` | Full 100-symbol discovered list, reference-data ingestion notes |
| `SECTOR_ANALYSIS_REPORT.md` | Sector data = NOT VERIFIED finding and root-cause candidates |
| `AI_RECOMMENDATIONS_REPORT.md` | Full 95-company table, recommendation/risk/horizon distributions, ranking + watchlist tables |
| `TECHNICAL_ANALYSIS_REPORT.md` | Indicator inventory and this run's technical-score findings |
| `FUNDAMENTAL_ANALYSIS_REPORT.md` | Ratio inventory, the 4 exact fundamentals failures |
| `AI_DECISION_ENGINE_REPORT.md` | Contributor-weight architecture and how it behaved live |
| `MARKET_PERFORMANCE_REPORT.md` | Timings, real API-call accounting, artifact-retrievability finding |
| `DATA_QUALITY_REPORT.md` | Consolidated, ranked list of every real data-quality gap |
| `READINESS_SCORECARD.md` | Working/Gap/Not-Verified scorecard across every pipeline stage |
| `FINAL_EXECUTIVE_REPORT.md` | Executive summary and recommended next phase |
