# Sector Analysis Report — Basirah Phase 9

## Finding: sector data is NOT VERIFIED — 0 of 95 scanned companies have a populated sector

Parsing the complete STEP 8b company table (95 rows) from run 30444421326's log against the `sector` field confirms:

```
sector non-empty: 0 / 95
```

Every scanned company's sector column is empty. This means:

- **No per-sector breakdown, ranking, or rotation analysis can be produced from this run's real data.** Any such table would be fabricated. Per the explicit instruction not to guess or hide weaknesses, this report states plainly: **sector coverage = NOT VERIFIED.**
- `SectorRankingCategory`-style groupings, `SECTOR_ANALYSIS`-style summaries, and the `_sector_breakdown()` helper in `scripts/verify_sahmk_market_intelligence.py` all degrade to a single `"UNKNOWN"` bucket containing all 95 companies.

## Root cause (partially diagnosed, not fully confirmed)

Two candidate explanations were identified from code review, neither confirmed without an additional live call (out of scope for this report):

1. `SahmkMarketDataService.get_company_directory()`'s sector-key guesses (`["sector", "sector_name"]`) may not match the actual field name SAHMK's **bulk** `/companies/` response uses — as opposed to the **individual** `/company/{symbol}/` profile endpoint, which in an earlier, unrelated 5-symbol validation run (Phase 2) did successfully populate sector data for those 5 symbols.
2. The `discover_all=True` path may simply not carry sector data through from whatever the bulk response contains, independent of key-name mismatches.

**NOT VERIFIED which of these is the actual cause** — distinguishing them requires inspecting the raw bulk `/companies/` JSON response, which was not captured by this run's logging and cannot be obtained without another live SAHMK call.

## Consequence for downstream rankings

The `RankingEngine`'s and `WatchlistEngine`'s outputs are all valid at the individual-symbol level (technical/fundamental scores, confidence, recommendation) but **carry no real sector attribution** in this run. Any report elsewhere in this Phase 9 deliverable set that shows a `sector` column for these 95 companies will show it empty — this is a faithful reflection of the real data, not a rendering bug.

## Recommendation

Before sector-level analysis can be delivered as a real capability (not a placeholder), a future, explicitly-authorized live run should:
1. Capture and log the raw bulk `/companies/` response's field names (or a sample of them) before any sector-key mapping is applied.
2. Confirm whether the sector field is present under a different key, absent entirely, or requires a per-symbol profile call to obtain (which would have real API-budget cost implications for a 100+ symbol universe).
