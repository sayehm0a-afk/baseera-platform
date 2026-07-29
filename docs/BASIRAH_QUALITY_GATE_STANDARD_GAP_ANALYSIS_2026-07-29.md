# Basirah Quality Gate Standard — Gap Analysis & Implementation Order

**Date:** 2026-07-29
**Scope:** Gap analysis of the "Final Investment Research Standard" against the current codebase, plus the requested critical challenge of the standard itself. Builds directly on `docs/ENGINEERING_MASTER_AUDIT_2026-07-29.md` and `docs/BASIRAH_WORLD_CLASS_AI_MASTER_PLAN_2026-07-29.md` (referenced, not repeated). **No code was written or changed to produce this document.**
**Method:** Every "Implemented" claim below was verified against real code this session (file/line references given); every "Missing" claim was verified by grep returning no match, not assumed.

---

## 1. The Challenge (per Task Item 10 — answered first, not buried)

The instruction explicitly asked me not to simply agree. Four parts of the standard need pushback before anything is designed around them as written.

### 1.1 "Scalp" and "Intraday" trade types are not honestly deliverable today, and probably shouldn't be promised

The standard asks for five trade types: Scalp, Intraday, Swing, Position, Investment. The platform's `TimeHorizon` enum has exactly three values (`SHORT_TERM`/`MEDIUM_TERM`/`LONG_TERM`, `src/analysis/decision/types.py:34-36`), and — more fundamentally — **no intraday price data exists anywhere in this platform.** This was already established in the prior master plan (Section 4.1): "Intraday tick/order-flow data (not available from SAHMK at this tier — a data-vendor limitation, not an engineering gap)." A Scalp recommendation (minutes-to-hours holding period) or an Intraday one (same trading day) is meaningless without intraday bars — Basirah ingests daily OHLCV only. Labeling a recommendation "Scalp" when the entire technical analysis behind it was computed from daily closes would be a direct violation of this platform's own "never exaggerate, never invent" standard.

**Recommendation:** drop Scalp and Intraday from the trade-type taxonomy until intraday data availability from SAHMK (or a supplementary vendor) is confirmed — a diagnostic task, not an engineering one. Ship with **Swing, Position, Investment**, plus the two already-real, already-built watchlist archetypes that don't fit that three-word scale cleanly but are genuinely computable today: **Dividend** and **Recovery** (both are real `WatchlistCategory` values already, prior audit Section 4.10). Five honest categories beat five categories where two are fabricated.

### 1.2 Gating on Confidence before Confidence is calibrated makes the gate worse than useless

The standard lists "Confidence confirmation" as one of twelve required quality gates — implying a recommendation is rejected if confidence falls below some threshold. But per the master plan's Section 4.23 (unchanged, re-confirmed here): confidence today is an **uncalibrated** Platt/isotonic design whose scheduler defaults to off — there is currently no evidence a "70% confidence" score is right 70% of the time. Using an unvalidated number as a hard pass/fail gate doesn't reduce risk, it **launders** the risk: a bad recommendation that happens to score 75/100 on an unvalidated scale sails through a gate that looks rigorous but isn't. This is arguably more dangerous than not gating on confidence at all, because a gate implies validation that hasn't happened.

**Recommendation:** confidence stays a *reported field*, not a *gate*, until prior audit Section 4.13/4.9's calibration scheduler has run long enough on real data to validate it. Until then, gate on the things that are already real and don't need calibration to be trustworthy (technical/fundamental/liquidity/risk-level thresholds computed directly from real data), and treat confidence as informational.

### 1.3 Several required gates depend on data that doesn't exist yet — this needs an explicit decision, not a silent one

"Macro confirmation," "Sector confirmation," and "Market confirmation" are three of the twelve required gates. Per the master plan: Macro is a disclosed no-op (no real oil-price/rate data wired), Sector is 0% populated (confirmed live, Phase 9), and Market confirmation almost certainly means "vs. TASI," which is entirely absent (no index data ingested anywhere — confirmed via the platform's own code comment in `risk_engine.py`). **If these three gates are implemented literally as hard requirements today, using the current data, they can never pass — every candidate fails on data absence, and the system produces zero recommendations forever, not zero on days without a real opportunity.** That is a different outcome than the one the standard describes ("no investment opportunity meets Basirah's standards today"), and conflating "we have no opinion because we have no data" with "we looked and found nothing good" would itself be a form of hiding uncertainty, not disclosing it.

**Recommendation:** every gate needs a third state beyond PASS/FAIL: **NOT_EVALUATED (insufficient data)**, and the standard needs one more explicit rule this document is adding: **a recommendation may only be shown if every gate is either PASS or explicitly, visibly disclosed as NOT_EVALUATED — never silently treated as an auto-pass.** This is not a weakening of the standard; it is the only way to implement "reject rather than guess" honestly when three of the twelve required inputs don't exist yet. As each data gap (TASI ingestion, sector taxonomy, macro data) closes per the master plan's roadmap, its gate converts from NOT_EVALUATED to a real PASS/FAIL gate — the system gets *stricter* over time as real data arrives, not weaker.

### 1.4 Everything else in the standard is sound and should not be watered down

The "reject rather than recommend" principle, the terse-primary/expandable-report product shape, the multi-target-with-probability design, the mandatory backtesting-before-trust requirement, and the continuous-outcome-tracking requirement are all correct, all consistent with the master plan's existing direction, and none of them need pushback. Section 1.1–1.3 above are the only places this document disagrees with the standard as written — everywhere else, the standard is adopted as specified.

---

## 2. Feature-by-Feature Gap Table

Status legend: **Implemented** (real, verified in code) · **Partial** (real component exists but doesn't meet the standard as specified) · **Missing** (confirmed absent) · **Needs Redesign** (exists but the existing design conflicts with the standard's requirement).

| Requirement | Status | Evidence / Note |
|---|---|---|
| Recommendation exists only if score is high | **Needs Redesign** | Today's `AIDecisionEngine` always emits STRONG_BUY/BUY/HOLD/SELL/STRONG_SELL for every scanned symbol — no rejection path exists (confirmed: no `NO_RECOMMENDATION` value, no suppression logic anywhere in `ai_decision_engine.py`/`recommendation_engine.py`). This is the single largest behavioral change the standard requires. |
| Recommendation (Buy/Strong Buy/Hold/Sell) | **Implemented** | `Recommendation` enum already has exactly these 5 values (`src/analysis/recommendation/types.py`). |
| Trade Type (Scalp/Intraday/Swing/Position/Investment) | **Missing, and 2 of 5 values are not honestly deliverable** | See Challenge 1.1. `TimeHorizon` has 3 values today, none matching this taxonomy. |
| Expected Holding Period | **Partial** | `TimeHorizon`'s 3 buckets are a coarse proxy; no explicit "N–M days" numeric estimate exists. |
| Entry Price | **Partial** | `latest_price` at scan time exists and is real; not currently exposed/labeled as a distinct "Entry Price" field, and no "ideal entry zone" (e.g., near a support level) exists — would need explicit design. |
| Target 1 / Target 2 / Target 3 | **Missing (multi-target)** | `target_price` is a single `Optional[float]` (`decision/types.py:126`) — confirmed no multi-target support anywhere. |
| Stop Loss | **Implemented** | Real, already computed with a stated basis (`stop_loss_basis` field already exists). |
| Risk Level | **Implemented** | Real (`RiskLevel` enum, LOW/MEDIUM/HIGH/VERY_HIGH). |
| Confidence | **Implemented but unvalidated** | Real field, real Platt/isotonic calibration design exists but has never run against real outcomes (scheduler off by default) — see Challenge 1.2. |
| Quality Gates (12 required) | **Missing entirely** | No gate/filter layer of any kind exists — every scanned symbol reaches a recommendation today. See Section 3 for the gate-by-gate breakdown. |
| "No opportunity today" state | **Missing** | No code path produces this; every scan always returns a full recommendation set. |
| Why this company? | **Partial** | Narrative generator exists (`narrative_builder.py`), real. |
| Why now? | **Missing** | Requires the Catalyst Detection Engine (master plan 4.30) — the underlying "what changed" ranking categories exist but have never been exercised (no back-to-back scans run yet). |
| Why better than all alternatives? | **Missing** | Requires the `ComparativeExplanationEngine` (master plan Section 6) — confirmed no comparative reasoning exists anywhere. |
| What changed today? | **Missing** | Same as "why now" — depends on consecutive-scan diffing, which the `RankingEngine`'s change-detection categories (MOST_IMPROVED_TODAY etc.) were designed for but have never been exercised. |
| What confirms this opportunity? | **Missing** | This is the positive-evidence half of the Quality Gate system (Section 3) — needs to be built alongside the gates, not separately. |
| Invalidation conditions | **Missing** | Requires the `InvalidationConditionGenerator` (master plan Section 6) — confirmed absent. |
| Major risks | **Partial** | Risk Score exists; a structured risk-enumeration narrative does not. |
| Required assumptions | **Missing (for anything beyond raw indicator math)** | Becomes mandatory once a DCF (master plan 4.7) exists. |
| Why Target 1 / Target 2 / Why Stop Loss | **Partial (stop loss only)** | Stop loss already has a stated basis field; no equivalent exists for a (currently nonexistent) multi-target system. |
| Why this holding period | **Missing** | No explanatory text tied to `TimeHorizon` today. |
| Comparative Engine (A ranks above B, explained) | **Missing** | Same gap as "why better than all alternatives" — one engine, cited under both headings. |
| Investment Thesis Engine (full structure) | **Designed, not built** | Fully specified in master plan Section 5.2 (`InvestmentThesis` structure) — this document does not redesign it, it is adopted as-is. |
| Business summary / competitive advantages / growth drivers | **Partial** | Fundamental data (financials, growth ratios) is real; a synthesized qualitative "competitive advantage" narrative does not exist and would need LLM synthesis under the same numeric-grounding discipline as everything else. |
| Bull / Base / Bear Case | **Missing** | Requires the Scenario Engine (master plan 4.31) — confirmed absent, design specified, not built. |
| Probability Target 1/2/3, Stop Loss, Bull/Base/Bear | **Missing** | Requires the Probability/Return-Distribution Engine (master plan 4.32) — the historical-simulation tier can produce exactly this (a Monte Carlo path-crossing probability per level), design exists, not built. |
| "Never claim certainty" discipline | **Partially implemented as a principle, not yet enforced** | The numeric-grounding (R3) LLM-safety pattern already enforces this for narrative text; no equivalent enforcement exists for a bare probability number yet — needs the same `distribution_type` labeling requirement from master plan 4.32. |
| Backtest vs. TASI | **Impossible today** | No TASI data ingested (master plan 4.29) — blocks this requirement entirely, not just weakens it. |
| Backtest vs. Buy & Hold | **Implemented** | Real, `BuyAndHoldStrategy` (`src/backtesting/baselines.py`). |
| Backtest vs. Random selection | **Missing** | Confirmed absent from `baselines.py` — trivial to add, see Section 6. |
| Backtest vs. Current/Previous Basirah version | **Partial** | The champion/challenger paper-trading infrastructure (AI Evolution E8, prior audit) has the right shape for this but has never been exercised for an actual version-over-version comparison. |
| Backtest vs. alternative weighting systems | **Partial** | `CalibrationEngine`/`statistical_calibration.py` can generate alternative weight proposals (real, built, prior audit 4.17) but has never been scheduled to run, so no such comparison has ever been produced. |
| Self-improvement / outcome tracking | **Built, disabled by default** | The entire AI Evolution layer (E1–E9) — unchanged from prior audit's central finding: real, wired, every scheduler off by default. |
| Ranking-quality tracking | **Missing** | Confirmed absent from `src/ai_evolution/accuracy_metrics.py` — no NDCG or rank-correlation metric exists; win rate, Sharpe, ECE, Brier score, precision/recall all exist, but nothing measures "was the *ranking order* correct," only "was each individual call correct." |
| Confidence-quality tracking (calibration error) | **Implemented, unused** | ECE/Brier/MCE already exist in `metrics.py` (prior audit 4.2) — just never run against real data. |
| Two-tier display (terse primary + "Why this stock?" expandable report) | **Not yet designed as an API contract** | This is a data-shape decision, not a UI-polish task — Section 4 below proposes the API-level split (`RecommendationCard` vs. `RecommendationFullReport`) without touching any frontend code, consistent with the standing "no UI work" instruction. |

---

## 3. The Quality Gate System — Design

Twelve gates as specified, each mapped to a real data source or explicitly marked as currently unable to evaluate (per Challenge 1.3's three-state rule):

| Gate | Data source today | State if built now |
|---|---|---|
| Technical confirmation | Real (`TechnicalScoreContributor` + extensions from master plan 4.1) | **Evaluable** |
| Fundamental confirmation | Real (`FundamentalScoreContributor`) | **Evaluable** |
| Valuation confirmation | Real for P/E, P/B, dividend yield today; DCF-based valuation (master plan 4.7) not yet built | **Evaluable (partial basis)**, strengthens once 4.7 lands |
| Liquidity confirmation | Real (current/quick/cash ratios, master plan 4.10) | **Evaluable** |
| Risk confirmation | Real (`RiskScoreContributor`) | **Evaluable** |
| Volatility confirmation | Real ATR exists; volatility-regime classifier (master plan 4.11) not yet built | **Evaluable (basic)**, strengthens once 4.11 lands |
| News confirmation | Real (`NewsSentimentScoreContributor`) | **Evaluable** |
| Sector confirmation | **0% sector data populated** | **NOT_EVALUATED until the sector-data gap closes (master plan, prior audit 4.3)** |
| Market confirmation (vs. TASI) | **No TASI data ingested anywhere** | **NOT_EVALUATED until TASI ingestion (master plan 4.29) lands** |
| Macro confirmation | **Disclosed no-op, no real data wired** | **NOT_EVALUATED until master plan 4.17 lands** |
| Confidence confirmation | Real field exists, **uncalibrated** | **Advisory only, not a hard gate, until calibration is validated (Challenge 1.2)** |
| Data-quality confirmation | New — needs to be built from the `data_sufficiency` flags already specified in master plan Section 6 | **Evaluable once those flags exist (cheap, pure synthesis of already-computed signals)** |

**Consequence of this table, stated plainly:** built today, exactly 3 of 12 gates (Sector, Market, Macro) cannot evaluate at all, and Confidence should not be a hard gate yet. That leaves **8 gates that are real and can be enforced immediately** (Technical, Fundamental, Valuation-partial, Liquidity, Risk, Volatility-basic, News, Data-quality) — enough to build a genuinely stricter recommendation filter than exists today, with the remaining 3 gates converting from NOT_EVALUATED to real gates as the master plan's data-completeness work lands, at which point the filter gets meaningfully stricter still, exactly matching "the system gets stricter over time, not weaker."

---

## 4. Product Shape as an API Contract (not UI work)

Two response shapes, both backend/schema decisions:

- **`RecommendationCard`** (the default, terse view): recommendation, trade type, expected holding period, entry price, target(s), stop loss, risk level, confidence. Nothing else.
- **`RecommendationFullReport`** (behind "Why this stock?"): the complete `InvestmentThesis` object already specified in master plan Section 5.2, including every gate's pass/fail/not-evaluated state, the comparative explanation, catalysts, assumptions, bull/base/bear scenarios with probabilities, and the evidence citation list.

This is purely a matter of which fields a REST endpoint returns by default vs. on request (e.g., a `?full=true` parameter or a separate `/report` sub-route) — no frontend rendering decision is implied or needed to define this contract, consistent with the standing instruction to do no UI/UX work.

---

## 5. Multi-Target and Per-Level Probability Design

Concrete mapping, built entirely on components the master plan already specified — no new architecture, only a new field-level composition:

- **Target 1** = the Scenario Engine's (master plan 4.31) **Base Case** price target.
- **Target 2** = the Scenario Engine's **Bull Case** price target.
- **Target 3 (optional)** = an extended/stretch target, derived from an existing computable input (e.g., a Fibonacci extension level, already part of the technical engine's real indicator set, or a historical-analog extreme) — shown only when such a level exists and is meaningfully distinct from Target 2, never fabricated to fill the slot.
- **Probability of each target / stop loss / scenario** = the Probability Engine's (master plan 4.32) **tier (a) historical-simulation Monte Carlo**, run once per level (a standard Monte Carlo output — "probability the simulated price path crosses level X within the stated holding period" is not additional new math beyond what 4.32 already specifies, only additional reporting granularity). Every probability figure carries the same mandatory `distribution_type: "historical_simulation"` label from the master plan until tier (b), the empirically-calibrated version, is validated.

**Why Stop Loss / Why Target N:** each of these becomes a mandatory `basis` field, following the pattern the codebase already uses for `stop_loss_basis` (real today) — e.g., `target_1_basis: "base-case DCF fair value"`, `target_2_basis: "bull-case DCF fair value assuming above-trend growth"`. No target may exist in the API response without a populated basis field — this is the mechanical enforcement of "why Target 1 / why Target 2" as a schema constraint, not just a documentation promise.

---

## 6. Backtesting: New Required Baselines

Extends master plan Section 7's already-designed extension of `baselines.py`:

| New baseline | Effort | Note |
|---|---|---|
| `RandomSelectionStrategy` | Trivial | A genuinely useful sanity-check floor — if Basirah's engine cannot beat random symbol selection, that is a critical, immediate finding, not a nice-to-have comparison. Should be one of the very first new baselines added. |
| Current-version-vs-previous-version comparison | Medium | Reuses the already-built champion/challenger paper-trading infrastructure (AI Evolution E8) — needs explicit version tagging on `RecommendationSnapshot` rows (a small schema addition) and a comparison report, not new statistical machinery. |
| Alternative-weighting-systems comparison | Low | `CalibrationEngine`/`statistical_calibration.py` already generates alternative weight proposals — this baseline is "run the backtest with a proposed alternative weight set instead of production weights," which the existing `Strategy` protocol already supports via constructor parameters (`AIDecisionEngineStrategy` already takes tuning parameters, `baselines.py:212`). |
| TASI | **Blocked** | Same dependency as everywhere else in this document — master plan 4.29. |

---

## 7. Optimal Implementation Order

Ordered by what unlocks the most other requirements and what's honestly buildable given today's real data, not by the standard's own listed order.

**Phase 1 — Foundation (no new data required, buildable immediately):**
1. Three-state gate architecture (PASS/FAIL/NOT_EVALUATED) with the 8 currently-evaluable gates wired for real (Technical, Fundamental, Valuation-partial, Liquidity, Risk, Volatility-basic, News, Data-quality).
2. The rejection path itself — "no recommendation" as a first-class, real system state, not a hypothetical. This is the single most consequential behavioral change in this entire document and should land first, since everything else (gates, thesis, targets) plugs into a system that can already say no.
3. `RandomSelectionStrategy` baseline (trivial, immediate sanity-check value).
4. Multi-target schema + mandatory basis fields (Section 5) — reuses existing target-computation math from a single target to three, no new data.
5. `RecommendationCard` / `RecommendationFullReport` API split (Section 4).

**Phase 2 — The Investment Thesis Engine build-out (per master plan Tier 1, unchanged):**
6. Comparative-explanation engine, invalidation-condition generator, Catalyst Detection (technical half), Scenario Engine, Probability Engine tier (a) — all as already specified in the master plan, now feeding the multi-target/probability fields from Phase 1 item 4 directly.
7. Turn on the self-improvement schedulers (near-zero cost, starts the calendar clock every later calibration depends on, including Confidence eventually becoming a real gate).

**Phase 3 — Data-completeness work that upgrades NOT_EVALUATED gates to real ones (per master plan Tiers 1–2):**
8. TASI ingestion — converts the Market gate from NOT_EVALUATED to real, unlocks the TASI backtest requirement, unlocks real beta/relative strength.
9. Sector-data fix — converts the Sector gate from NOT_EVALUATED to real.
10. Macro-data wiring — converts the Macro gate from NOT_EVALUATED to real.

**Phase 4 — Financial-analysis depth (per master plan Tier 3, unchanged):** earnings quality, cash flow analysis, DCF, multi-year growth/DuPont — strengthens the Valuation and Fundamental gates from "partial basis" to full depth.

**Phase 5 — Validation and proof (per master plan Tier 5, extended):** full backtesting suite including the new Random/version/alternative-weighting baselines from Section 6; ranking-quality metric (NDCG or equivalent) added to `accuracy_metrics.py`; only after all of this, Confidence graduates from advisory to a real gate once calibration is validated on real accumulated data.

**Deliberately not reordered ahead of data-completeness:** the Investor Suitability Classifier (master plan 4.33) remains gated on legal/compliance review, independent of this phasing, and Scalp/Intraday trade types remain out of scope pending confirmed intraday data availability (Challenge 1.1).

---

## 8. Impact vs. Cost

| Item | Impact | Cost | Notes |
|---|---|---|---|
| Rejection path ("no recommendation") | Very High | Low | The single highest-impact, lowest-cost item in this entire document — a behavioral change, not new data or new math. |
| 8 evaluable quality gates | Very High | Low-Medium | Mostly wiring already-real scores into pass/fail thresholds. |
| Multi-target + basis fields | High | Low | Reuses existing single-target computation, extended to 3 via the already-designed Scenario Engine. |
| Random-selection baseline | Medium (as a sanity check, could be very high if it reveals a real problem) | Trivial | Should not be skipped given how cheap it is. |
| Comparative-explanation + invalidation engines | Very High | Medium | Unchanged from master plan — still the cheapest large win available in terms of new-data-required. |
| Scenario Engine + Probability tier (a) | Very High | Medium-High | The grounding discipline (never free-form LLM numbers) is non-negotiable and adds real engineering care, not just time. |
| TASI ingestion | Very High (unlocks 3+ other items) | Low-Medium (data-source-dependent) | Unchanged top data priority from the master plan. |
| Sector/Macro data fixes | High | Medium | Unchanged from prior audits. |
| Ranking-quality metric | Medium | Low | Small, well-defined addition (NDCG or Spearman rank correlation against realized returns). |
| Version-vs-version / alternative-weighting backtests | Medium | Low-Medium | Reuses existing infrastructure, needs version tagging + reporting. |
| Investor Suitability Classifier | Deferred | N/A until compliance review | Unchanged from master plan. |
| Scalp/Intraday trade types | Not recommended | N/A | See Challenge 1.1 — do not build without confirmed intraday data. |

---

## 9. Quick Wins vs. Long-Term Research

**Quick wins (Phase 1, days-to-low-weeks of focused work):** the rejection path itself; the 8 evaluable gates; multi-target schema with mandatory basis fields; `RandomSelectionStrategy`; the API response split.

**Long-term research (genuinely open-ended, correctly not time-boxed per the mandate):** the Scenario Engine and Probability Engine's grounding discipline needs to be gotten right, not fast — rushing the "never invent a number" guarantee under the terse-vs-full-report product pressure would be exactly the kind of shortcut this entire engagement has been built to avoid; the eventual empirically-calibrated probability tier (b) is explicitly gated on real calendar time accumulating real outcomes, not on engineering effort, and cannot be accelerated by working harder; ranking-quality-driven model improvement (once real outcome data exists) is genuinely open-ended research, not a scoped deliverable.

---

## 10. Final Recommendation

This standard is the right one, with the three corrections in Section 1: drop Scalp/Intraday until intraday data is confirmed, keep Confidence advisory until it's genuinely calibrated, and give every gate an explicit NOT_EVALUATED state rather than pretending three gates that depend on absent data can evaluate today. With those three corrections, this document finds the standard fully consistent with, and a sharper product expression of, the Investment Thesis Engine architecture already approved in the prior master plan — nothing here requires reopening that design, only sequencing its delivery against a stricter, gate-based product shape.

The single highest-leverage next step, ahead of any data work, is Phase 1 item 2: building the rejection path itself. Every other item in this document — the gates, the multi-target system, the thesis engine — is more valuable in a system that has already proven it's willing to say no than in one that hasn't.

No implementation has been performed. This document recommends proceeding with Phases 1 through 5 as ordered above, pending approval.
