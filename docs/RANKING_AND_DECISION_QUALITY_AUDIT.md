# Ranking & Decision-Quality Audit (CONT Phase 9)

## Scope

Audits `src.market_intelligence.personal_scan`'s composite ranking score
(`_composite_score`/`_sort_key`) together with Decision Engine V2
(`src/analysis/decision_v2/`) against the mandate's explicit checklist:
does ranking consider decision tier, entry readiness, confidence,
risk/reward, volume/liquidity confirmation, technical structure,
fundamental quality, relevant news impact, market regime permission,
contradictions, invalidation proximity, and data freshness -- without
arbitrary unjustified weights, and without ever letting duplicate symbols
or a fabricated fifth pick reach a user.

## Checklist result

| Dimension | Where it enters the score | Evidence |
|---|---|---|
| Decision tier | `_sort_key`'s primary sort key, dominates every other factor | `_DECISION_PRIORITY` -- STRONG_BUY_CANDIDATE > BUY_CANDIDATE > WAIT_FOR_ENTRY, tested by `test_decision_priority_still_dominates_every_composite_score_factor` |
| Entry readiness | `_ENTRY_READINESS_POINTS` (+10 READY_NOW ... -15 MISSED_ENTRY) | real `entry_status` from `trade_classification.py`, never guessed |
| Confidence | `confidence * 0.25` | `DecisionV2Snapshot.confidence_score`, already calibrated (Phase 2 confidence-calibration wiring) |
| Risk / reward | `(risk_reward / 5.0) * 100 * 0.15`, capped at 5:1 | `risk_reward_target_1`, real target/stop math |
| Volume / liquidity confirmation | `+5` confirmed, `-5` abnormal | `volume_confirms_decision`/`abnormal_volume`, both real gate outputs |
| Technical structure | embedded in `opportunity_quality_score * 0.30` | `opportunity_quality_score` already blends `trend_score` (SMA/EMA/SuperTrend/ADX) + `momentum_score` (RSI/MACD) + `volume_score` (OBV) -- see `scoring.py` |
| Fundamental quality | **was missing before this phase; now added** | see "Fix applied" below |
| Relevant news impact | `_NEWS_IMPACT_POINTS` (+5 POSITIVE, -8 NEGATIVE) | real `news_impact` classification (`news_impact.py`), never NEUTRAL/NO_RELEVANT_NEWS penalized |
| Market regime permission | `-10` when `market_risk_entry_permitted is False` | real 9-state `market_risk.py` classifier output |
| Contradictions | `-2` per disclosed caveat, capped at `-10` | `why_not_buy_reasons`, real gate-surfaced caveats, never hidden even though penalized |
| Invalidation proximity | `-10` within 2%, `-5` within 5% of `invalidation_price` | real `current_price` vs. `invalidation_price` distance |
| Data freshness | not per-candidate -- see rationale below | `PersonalScanResult.freshness_state` (Phase 6) |

## Fix applied: fundamental quality was absent from ranking

**Before this phase**, `_composite_score` had no fundamental-quality
term at all. `DecisionV2Snapshot.fundamental_summary` (real ratios:
ROE, net margin, debt/equity, revenue growth, EPS growth, P/E, P/B --
`fundamental_summary.py`) was persisted and shown on the stock detail
page, but never influenced *ranking*. Two candidates with identical
technical/confidence/risk-reward numbers but opposite fundamentals (one
profitable and growing, one lossmaking and over-leveraged) would have
ranked identically.

**Fix**: `_fundamental_quality_points()` (new in `personal_scan.py`)
scores the five ratios that most directly indicate financial health
(ROE, net margin, debt/equity, revenue growth, EPS growth) and adds the
result to the composite score. Critically, this does **not** invent new
thresholds -- it imports and reuses `fundamental_contributor.py`'s own
`_score_roe`/`_score_net_margin`/`_score_debt_to_equity`/
`_score_revenue_growth`/`_score_eps_growth` functions verbatim, the same
bucket thresholds `FundamentalScoreContributor` already uses elsewhere
in the codebase (and that a user already sees explained via the
Investment Committee's fundamental agent). This keeps the mandate's "no
arbitrary unjustified weights" rule: the thresholds are the one
established, already-reviewed set in this codebase, not a new number
invented for this ranking. A `None` ratio (no reported financials
available) contributes exactly 0 -- neutral, never guessed -- matching
every other `_composite_score` component's missing-data rule.

Regression tests: `test_stronger_fundamentals_rank_above_otherwise_identical_candidate`,
`test_missing_fundamental_ratios_are_neutral_not_penalized`
(`tests/unit/market_intelligence/test_personal_scan.py`).

## Why data freshness is not a per-candidate ranking term

All candidates in one `PersonalScanResult` come from the same
`scan_run_id` (`select_top_opportunities` queries
`DecisionV2Snapshot.scan_run_id == scan_run.id`), so every candidate in
a given result shares exactly the same age. Freshness genuinely
distinguishes *scans* (Phase 6's FRESH/AGING/STALE/NO_SCAN states,
disclosed via `FreshnessBanner`), not *candidates within a scan* -- there
is no real evidence to weight one candidate's freshness differently from
another's within the same run, so no such term is added (avoiding a
term that would be arbitrary by construction).

## Duplicate-stock invariant (re-verified)

`_latest_snapshot_per_symbol()` collapses every row to at most one per
symbol *before* ranking runs -- structurally impossible for the final
list to contain a duplicate symbol, independent of the scoring logic
above. Re-verified by `test_returns_unique_symbols_even_when_a_symbol_has_multiple_rows_for_the_same_run`
(pre-existing, still passing).

## Zero-to-five invariant (re-verified)

`select_top_opportunities` returns `sorted(deduped, key=_sort_key)[:max_results]`
-- a plain slice of however many candidates exist, never padded. Zero
qualifying candidates yields an empty list (rendered as an honest empty
state per Phase 6), never a fabricated fifth pick. No change was needed
here; re-verified by reading the code path, no synthetic-candidate code
exists anywhere in this module.

## Verdict

Every dimension the mandate lists is now real evidence already computed
by Decision Engine V2, with one genuine gap (fundamental quality) closed
in this phase by reusing an existing, already-reviewed scoring module
rather than inventing new weights. No other change to `_composite_score`
was evidence-justified by this audit.
