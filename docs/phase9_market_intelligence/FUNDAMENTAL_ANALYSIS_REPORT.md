# Fundamental Analysis Report — Basirah Phase 9

## Ingestion result

```
Fundamentals ingestion: {'symbols_requested': 100, 'symbols_succeeded': 96, 'symbols_failed': 4, 'rows_upserted': 96, 'errors': {...}}
```

96 of 100 discovered symbols had real fundamentals successfully ingested from the live SAHMK `/financials/{symbol}/` endpoint.

## The 4 failures — exact reasons (verbatim from the log)

| Symbol | Exact error |
|---|---|
| 1113 | `SAHMK /financials/1113/ response is missing required field(s) ['revenue', 'net_income', 'total_assets', 'total_liabilities', 'total_equity', 'fiscal_period_end'] (after trying every known alternate field name)` |
| 1263 | `SAHMK /financials/1263/ response is missing required field(s) ['revenue', 'net_income', 'total_assets', 'total_liabilities', 'total_equity', 'fiscal_period_end'] (after trying every known alternate field name)` |
| 1295 | `SAHMK /financials/1295/ response is missing required field(s) ['revenue', 'net_income', 'total_assets', 'total_liabilities', 'total_equity', 'fiscal_period_end'] (after trying every known alternate field name)` |
| 2315 | `SAHMK /financials/2315/ response is missing required field(s) ['revenue', 'net_income', 'total_assets', 'total_liabilities', 'total_equity', 'fiscal_period_end'] (after trying every known alternate field name)` |

All four fail identically — the SAHMK financials endpoint returned a response missing every core financial statement field for these specific symbols, even after the client tried every known alternate field name (`docs/SAHMK_INTEGRATION.md` documents this endpoint's field-name inconsistency across symbols). This is a real, live API data-availability gap, not a code defect in Basirah's parsing.

## Downstream effect on the scan

- Symbol **1113** still had at least one `PriceBar` row, so it *was* scanned. Its fundamental score is `N/A` in the company table; the `AIDecisionEngine` degraded gracefully to a technical-score-only weighting for that symbol and still produced a HOLD recommendation.
- Symbols **1263, 1295, 2315** additionally had zero `PriceBar` rows and were excluded from the scan entirely by `SymbolSelector` before fundamentals mattered (see `MARKET_COVERAGE_REPORT.md`) — their fundamentals failure is real but not the direct cause of their exclusion from the scan; the exclusion is a separate, unconfirmed OHLCV gap.

## Fundamental ratio inventory actually computed (code-verified)

18 ratios across 6 categories, applied to the 91 scanned symbols with valid fundamentals data:

| Category | Ratios |
|---|---|
| Profitability | net_profit_margin, gross_profit_margin, ROE, ROA |
| Liquidity | current_ratio, quick_ratio, cash_ratio |
| Leverage | debt_to_equity, debt_to_assets, equity_multiplier |
| Efficiency | asset_turnover |
| Valuation | P/E, P/B, dividend_yield, market_cap |
| Growth | revenue_growth, net_income_growth, eps_growth |

**Explicitly not implemented**: P/S ratio (Price-to-Sales), intrinsic value/DCF valuation, real industry/peer comparison (the `SectorRotationScoreContributor` exists but is a disclosed no-op placeholder unless externally fed data — and sector data itself is 0% populated this run, see `SECTOR_ANALYSIS_REPORT.md`).

## This run's fundamental score distribution (91 of 95 scanned companies with a real fundamental score)

Fundamental scores in the STEP 8b table range from 26.0 (multiple companies: 1201, 1213, 1820, 2281, 2287) to 71.0 (many companies). No systematic outlier pattern was analyzed beyond the raw table — see `AI_RECOMMENDATIONS_REPORT.md` for the full per-symbol table.
