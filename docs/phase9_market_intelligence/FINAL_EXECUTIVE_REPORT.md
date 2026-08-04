# Final Executive Report — Basirah Phase 9: Full Saudi Market Intelligence Validation

## Scope and evidence

This report is built exclusively from GitHub Actions workflow run **30444421326** (`sahmk-live-pipeline-validation.yml`, `mode=full_universe`), which completed successfully on 2026-07-29 between 10:37:59Z and 10:58:32Z against the live SAHMK API and a real, ephemeral PostgreSQL instance. No new workflow run was dispatched to produce this report, per explicit instruction. All figures are drawn from the run's complete job log (retrieved with an explicit `tail_lines=6000` override after discovering the log-retrieval tool's default 500-line truncation had silently dropped the run's first six steps on the initial fetch) and cross-checked against the script's own printed summary counters.

## Headline results

- **100 companies discovered**, **95 companies scanned and given a real AI recommendation** — via the live, unmodified production pipeline (SAHMK ingestion → PostgreSQL → technical/fundamental analysis → AI decision engine).
- **400 real, metered SAHMK API calls**, exactly matching the expected 4-calls-per-symbol × 100-symbol budget — confirmed by wrapping the real, shared rate-limiter singleton, not estimated.
- **Zero fabricated or synthetic data** anywhere in this run's evidence chain — both market and fundamental providers were confirmed `sahmk` before any work began, and the market was confirmed open at scan time.
- **Total pipeline time: ~19 minutes** of real, rate-limited work (fundamentals ingestion is the dominant cost at ~9m18s), inside a ~20.5-minute total job wall-clock.

## Recommendations breakdown

| Recommendation | Count |
|---|---|
| STRONG_BUY | 0 |
| BUY | 19 |
| HOLD | 57 |
| SELL | 19 |
| STRONG_SELL | 0 |

## Top 10 recommendations (TOP_BUY ranking, real, this scan)

1. **1020** — BUY, confidence 63.2, score 70.5
2. **1140** — BUY, confidence 60.2, score 68.4
3. **2300** — BUY, confidence 69.2, score 67.8
4. **1831** — BUY, confidence 63.2, score 67.6
5. **1835** — BUY, confidence 66.2, score 67.5
6. **1080** — BUY, confidence 66.2, score 67.1
7. **1323** — BUY, confidence 66.2, score 67.0
8. **1322** — BUY, confidence 69.2, score 66.0
9. **1060** — BUY, confidence 63.2, score 65.0
10. **1303** — BUY, confidence 60.2, score 64.5

Full table of all 95 companies, all 19 BUY entries, and all 17 ranking + 9 watchlist category contents are in `AI_RECOMMENDATIONS_REPORT.md`.

## Watchlists produced

MOMENTUM (15), SWING (19), HIGH_RISK (30), OVERSOLD_OPPORTUNITIES (22) — populated with real entries. INVESTMENT, DIVIDEND, RECOVERY, BREAKOUT_CANDIDATES, and OVERBOUGHT_WARNINGS were empty this run because the underlying real market conditions for those categories simply didn't occur in today's session's real data (e.g., zero dividend events were ingested, so DIVIDEND is genuinely empty, not broken).

## Failed / excluded symbols with exact reasons

| Symbol | Stage | Exact reason |
|---|---|---|
| 1113 | Fundamentals | SAHMK `/financials/1113/` response missing required fields (revenue, net_income, total_assets, total_liabilities, total_equity, fiscal_period_end) — still scanned via technical-only graceful degradation |
| 1263 | Fundamentals + excluded from scan | Same missing-fields error; also had zero `PriceBar` rows, so never entered the scanner |
| 1295 | Fundamentals + excluded from scan | Same as 1263 |
| 2315 | Fundamentals + excluded from scan | Same as 1263 |
| 2001 | Excluded from scan | No logged ingestion failure of any kind; reason for zero `PriceBar` rows is **NOT VERIFIED** |
| 2210 | Excluded from scan | Same as 2001 — **NOT VERIFIED** |

## Real gaps this run surfaced (not hidden, not minimized)

1. **Sector data: 0/95 populated.** No sector-level analysis is possible from this run.
2. **Arabic company names: 0/95 populated.** A structural ingestion gap — no code path writes `Stock.name_ar` at all, from any source.
3. **True SAHMK universe size unconfirmed.** 100 discovered in two independent runs, with no pagination metadata captured to confirm whether that's the full addressable universe.
4. **5 of 100 discovered companies never scanned**, for reasons only partially explained (3 tie to fundamentals failures, 2 remain unexplained).
5. **Full per-company JSON artifact unretrievable in this validation session** due to this environment's network policy blocking Azure Blob Storage — mitigated by printing the same data to job logs, but the full narrative-explanation text and complete contributor-weight breakdown remain unretrieved.

Full detail on every gap: `DATA_QUALITY_REPORT.md`.

## Verdict: PARTIAL MARKET VERIFIED

This is not FULL MARKET VERIFIED and this report does not claim it is. It is also not NOT VERIFIED — a real, substantial fraction of the live Saudi market (95 companies) was discovered, ingested, analyzed, and given a real AI-generated recommendation with zero fabricated data, and every shortfall from full-market coverage is precisely quantified rather than glossed over.

## Overall project readiness

Consistent with — and not superseded by — the standing verdict in `docs/PRODUCTION_READINESS_REPORT_2026-07-29.md` (**Go/No-Go = NO** for Beta), this Phase 9 run confirms the **market-intelligence backend pipeline itself is real, functional, and produces trustworthy per-company recommendations at the scope it actually covers**, but it does **not** close any of that report's open items (sector/company enrichment gaps, universe-completeness, and the broader production-readiness blockers it documented remain open; this run adds two new, precisely-scoped findings — sector/name_ar population and universe-size confirmation — to that backlog rather than resolving any of it).

**Remaining blockers before this can be called a complete Saudi market intelligence product:**
1. Confirm or fix the SAHMK company-directory pagination behavior (is 100 really the whole universe?).
2. Diagnose and fix the sector/`name_ar` population gap in the bulk-discovery ingestion path.
3. Diagnose why 2001 and 2210 have zero price history despite OHLCV ingestion reporting no failures.
4. Add exchange/instrument-type classification (currently absent entirely).
5. Address the artifact-retrievability gap for any future validation run in a similarly network-restricted environment (the log-printing mitigation works but is not a substitute for real artifact access).

**Recommended next phase:** a targeted, narrowly-scoped diagnostic run (not another full-universe scan) that specifically instruments and logs the raw SAHMK bulk `/companies/` response's field names and pagination envelope, and the per-symbol `PriceBar` row count immediately after OHLCV ingestion — closing findings #1 and #3 above with minimal additional API budget, before committing to a second full-universe run.

**Is Basirah ready for UI/UX development, or does it require more backend work?**

The market-intelligence **backend** is demonstrably real and production-shaped for its current scope — this is not a "needs more backend work before UI can start" situation for the recommendation/ranking/watchlist surfaces themselves, which already have a working REST API (built and tested in earlier phases) that UI work could integrate against today. However, any UI screen that intends to show **sector filters, sector breakdowns, or Arabic company names** would currently have nothing real to render for those specific fields, and any UI messaging implying "full market coverage" would be inaccurate given the unconfirmed universe size. Recommendation: UI/UX development can proceed for the symbol-level recommendation, ranking, and watchlist surfaces now, while treating sector-based UI and any "N companies covered" marketing copy as blocked on the backend items above.
