# Basirah World-Class AI Master Plan

**Date:** 2026-07-29
**Mandate:** Build the most intelligent stock analysis platform in the world. No shortcuts, no speed pressure, no UI work. This document is diagnostic and architectural only — **no code was written or changed to produce it.**
**Method:** Every claim is grounded in direct inspection of this session — file paths, function names, and in several places verbatim code comments the platform's own engineers left explaining a real limitation. Where evidence is missing, this document says "NOT VERIFIED" or "ABSENT" rather than estimating. This document supersedes and sharpens `docs/ENGINEERING_MASTER_AUDIT_2026-07-29.md`'s findings specifically through the lens of *investment-decision intelligence quality* — infrastructure findings from that audit (dead multi-agent code, disabled self-improvement schedulers, single-key rate ceiling) are not repeated in full here except where they directly bear on recommendation defensibility.
**Revision note (final architectural review):** Section 5 has been restructured and Sections 4, 6, 8, 10, and 11 extended to adopt the **Investment Thesis Engine** as Basirah's core output architecture, per a final review request. This is not an addition bolted onto the prior design — it changes what the 15-score system from the original Section 5 is *for*: those scores stop being the end-product presented to a user and become the cited, traceable evidence inside a structured thesis. The reasoning for this decision is in the new closing portion of Section 1 and fully specified in the new Section 5.2. No code was written or changed to produce this revision either.

---

## 1. Executive Summary

Basirah can currently produce a recommendation. It cannot currently **defend** one. That is the finding this entire document is built around, and it is proven concretely in Section 3 using the platform's own real evidence for symbol 1020 — the exact case raised.

The underlying reason is structural, not a bug: every recommendation today is the output of a **fixed-weight linear scoring formula** (11 contributors, hand-set weights, `src/analysis/decision/ai_decision_engine.py`). A linear formula can report a number. It cannot, by construction, tell you *why that number beat the next ten companies* unless something is built specifically to generate that comparison — and nothing is. It cannot express *uncertainty* about a specific factor — it produces one point estimate per contributor, no confidence interval, no data-quality flag baked into the score itself. It cannot say *what would invalidate the call* — no invalidation-condition logic exists anywhere in the codebase.

None of the institutions the mandate names — Renaissance, Two Sigma, Citadel, Jane Street on the quant side; Goldman/Morgan Stanley/JPMorgan on the research side; Buffett/Lynch/Dalio on the discretionary side — operate this way. Quant shops validate a signal's statistical significance and decay before trusting it. Research houses write a thesis with explicit bear-case invalidation triggers. Discretionary legends have an explicit, articulable reason a specific holding beats the next-best alternative. Basirah currently has the shape of all of this (a scoring pipeline, a ranking engine, a narrative generator) without the substance that makes any of it defensible: no comparative reasoning, no statistical validation against real outcomes yet (the loop exists, it's switched off — see prior audit), no market-index benchmark data at all (confirmed: `MarketSnapshot`, the model built to hold it, is never populated — beta is always `None` in production), no earnings-quality or cash-flow analysis, no event awareness, and 6 of 15 requested composite sub-scores below don't exist as distinct signals today.

This is fixable. It is not fixable by tuning the existing formula's weights. It requires: (1) an explicit, structured explainability layer that computes *comparative* justification, not just a score; (2) closing real data gaps (index/benchmark data, cash flow statements, earnings-quality metrics) that no amount of algorithm work can substitute for; (3) an institutional-grade backtesting framework that actually runs the comparisons the mandate demands, most of which do not exist yet; and (4) eventually, a learned model — but only *after* the deterministic system can defend itself, because an unexplainable learned model would make this problem worse, not better.

**Architectural decision reached in this final review: yes, Basirah should become an Investment Thesis Engine, and this should be the core organizing structure, not an optional add-on.** The reasoning: everything diagnosed above — the comparative-explanation gap, the invalidation-condition gap, the missing earnings-quality/cash-flow/benchmark data — describes symptoms of the same root design choice, which is that Basirah's output today is *a number with a paragraph attached*, not *a case*. A number-with-a-paragraph is what a screener produces (Finviz, a basic scanner). A case — why this company, why now, why it beats the alternative, what could prove it wrong, what the range of outcomes looks like, who it's for — is what an actual research desk produces, and it is a categorically different kind of artifact, not a longer version of the same one. Adopting this as the core means: the 15 scores designed in the original Section 5 do not go away — they become the *cited evidence* inside a thesis, exactly as a Goldman Sachs or Morgan Stanley note cites specific ratios and price targets while telling a structured, falsifiable story. This restructuring is detailed in Section 5.2, with four new components required to support it (Section 4.30–4.33), one of which (investor-suitability classification) is flagged as needing an explicit compliance/legal-review gate before any implementation, because it edges toward regulated suitability-determination territory rather than pure research publishing — consistent with this document's own "never hide uncertainty" standard, that risk is being surfaced now, not discovered later.

---

## 2. Current-State Scorecard (Investment-Intelligence Lens)

| Score | Value | Basis |
|---|---|---|
| Current Platform Score | 38/100 | Real infrastructure, weak intelligence layer (consistent with prior audit's 34/100 World-Class Readiness, re-weighted here toward decision quality) |
| Current Intelligence Score | 24/100 | A fixed linear formula with no comparative reasoning, no statistical validation of its own weights against real outcomes, and 6 of 15 requested factor scores absent or fed no real data |
| Current AI Score | 18/100 | Zero predictive ML; only 2 of ~9 conceptual "agents" make a real LLM call; the self-improvement loop that would make this system genuinely adaptive is built but disabled by default |
| Current Recommendation Quality | 30/100 | Reproducible and internally consistent, but not provably *correct* or *comparatively justified* — see Section 3 |
| Current Data Quality | 28/100 | Real live data with zero fabrication (verified), but: no market-index data at all, 0% sector data, 0% Arabic names, no cash-flow statements, no earnings-quality data, universe capped at 100 companies of unconfirmed true size |
| Current Explainability Score | 40/100 | A real, safety-conscious narrative generator exists (numeric-grounded LLM adapter — a genuine strength), but it explains a score, not a *ranking* — it cannot currently answer "why better than the next 10" because nothing computes that comparison |
| Current Risk Score | 45/100 | Real per-symbol risk classification and a real portfolio risk engine exist; portfolio-level beta/correlation-to-market is permanently `None` because no index data is ingested; no VaR/CVaR |
| Current Scalability Score | 28/100 | Unchanged from prior audit — single shared API key ceiling, no distributed job execution |
| Current Maintainability Score | 45/100 | Unchanged from prior audit |
| Current Competitive Position | Weak on data breadth and validation; potentially strong on explainability-safety design and Saudi-market focus if the gaps below are closed — see Section 9 | — |

---

## 3. The Core Diagnosis: Can Basirah Defend "1020 Ranked #1 BUY"?

This section directly answers the concern raised. Using only real evidence — the live Phase 9 scan (`docs/phase9_market_intelligence/`, workflow run 30444421326) and direct code inspection — here is exactly what can and cannot currently be said about why symbol **1020 (BJAZ)** ranked first in `TOP_BUY`.

**What the system can prove today:**
- 1020's `technical_score` was 100.0 (the maximum, tied with 1831 and 2300) and its `final_score` (a blend, not the raw technical score) was 70.5 — the highest `rank_value` among all 19 BUY-rated companies.
- The `final_score` is a documented linear combination: `0.22×technical + 0.22×fundamental + 0.13×momentum + 0.09×volume + 0.10×risk + 0.08×price_structure + 0.05×value_area + 0.04×news + 0.04×macro(no-op) + 0.02×insider(no-op) + 0.01×sector_rotation(no-op)`. This arithmetic is fully reproducible from the stored `contributor_breakdown`.

**What the system cannot currently prove — and this is the actual finding:**
1. **Why these specific weights.** 0.22 for technical, 0.13 for momentum, etc. were never fit to real outcome data. There is no statistical evidence in the codebase that this weighting scheme outperforms, say, 0.30 technical / 0.10 momentum, or any other combination. The `CalibrationEngine`/`statistical_calibration.py` machinery that *could* generate that evidence exists but has never been run on a schedule (prior audit, Section 4.17).
2. **Why 1020 beats the next 10 companies specifically, not just "scored higher."** `RankingEngine` sorts by `rank_value` — it does not generate any comparative statement like "1020 beats 1140 because its technical score is 2 points higher while its fundamental score is tied, and its risk-adjusted momentum is superior." No code path computes a pairwise or percentile-relative explanation anywhere in the platform. The narrative generator (`src/analysis/analyst/narrative_builder.py`) explains *one stock's own* score composition — it has no access to, and makes no reference to, any other stock's scores.
3. **Whether 1020's fundamental score (64.0) reflects real earnings quality.** No earnings-quality check (accrual ratio, Beneish M-Score, Piotroski F-Score — none exist in this codebase) validates that the reported net income backing that fundamental score is *cash-backed* rather than accounting-driven. Institutional research would never sign off on a BUY without at least an accrual-quality sanity check.
4. **Whether 1020's momentum score is genuinely differentiated or an artifact of a thin lookback.** The live run ingested an average of ~56 OHLCV bars/symbol (prior audit, Section 4.6) — adequate for the 20-period indicators feeding momentum, but there is no confidence interval or data-sufficiency flag attached to the momentum score itself. A momentum score computed from 56 bars and one computed from 500 bars are reported with identical apparent certainty today.
5. **Whether 1020 is attractive *relative to its sector*.** 1020's `sector` field is empty (0/95 companies have sector data — confirmed live). Any claim that 1020 is a standout *within banking* (BJAZ is a bank) is currently unverifiable from real data, not just unstated.
6. **Whether 1020 is attractive relative to the real market (TASI).** No TASI index data is ingested anywhere in the platform (`src/backtesting/baselines.py`'s own code comment: *"with no ingested TASI/market-index history"*). There is no way to say 1020 is beating, matching, or lagging the real Saudi market, only that it scored well against Basirah's own internal formula.
7. **What would invalidate this recommendation.** No code path anywhere computes or stores an explicit invalidation condition ("if RSI crosses above 70 with declining volume, reassess" or similar). The recommendation is a point-in-time score with a target/stop, not a thesis with a stated failure condition.

**Conclusion:** 1020's rank is *arithmetically correct* given the current formula and *not currently defensible* as an investment claim, because the formula's own weights are unvalidated, no comparative or sector-relative reasoning exists, no earnings-quality check exists, no market-benchmark context exists, and no invalidation condition is ever stated. This is precisely the gap Sections 5–8 are designed to close.

---

## 4. Engine-by-Engine Audit

Organized by architectural reality, not by the requested list's order, because that reality is itself a critical finding: **some of the 28 requested "engines" are real and separate, some are sub-parts of a broader engine, some exist as a formula that is never fed real data (a "wired no-op"), and some are entirely absent from the codebase.** Pretending otherwise would misrepresent the platform. Each entry below states which category it falls into before the 16-field detail.

### 4.1 Technical Analysis Engine — REAL, separate — Maturity 68%

*(Carried forward from the prior audit's Section 4.6 with additions specific to this mandate.)*

- **Strengths:** 16 real indicators computed against live data for every scanned symbol; registry-pattern design is genuinely extensible.
- **Weaknesses:** No Ichimoku/Parabolic SAR/Williams %R/CCI/MFI; VWAP is rolling, not session-anchored; no confidence/data-sufficiency metadata attached to any indicator's output.
- **Hidden risks:** Two separate indicator-reading implementations exist (`src/analysis/registry.py` live path vs. `src/backtesting/calibration/indicator_signals.py` backtesting-only path) that can silently drift apart, meaning backtested indicator performance may not reflect what production actually computes.
- **Technical debt:** The dual-implementation issue above.
- **Missing algorithms:** Ichimoku Cloud, Williams %R, CCI, MFI, session-anchored VWAP, a genuine standalone breakout-strength indicator (currently only exists as a watchlist rule, not a scored indicator).
- **Missing data:** Intraday tick/order-flow data (not available from SAHMK at this tier — a data-vendor limitation, not an engineering gap).
- **Missing signals:** No indicator confidence interval; no explicit divergence-detection signal (price vs. RSI/MACD divergence — a real, standard technique, absent here).
- **Possible false positives:** RSI/MACD signals on thin (~56-bar) history can flag "oversold"/"overbought" states that are statistical noise rather than real mean-reversion setups — no sample-size gating exists to suppress this.
- **Possible false negatives:** Absence of divergence detection means genuine early-reversal setups (price makes a new high, RSI does not) go entirely undetected today.
- **How institutions solve this:** Quant shops (Two Sigma, Renaissance-style) treat every indicator as a *candidate signal* subjected to a decay/half-life and out-of-sample validation before it's trusted, rather than a fixed always-on input — exactly the discipline `statistical_calibration.py` is built for but never runs on schedule.
- **How the world's best platforms solve it:** TrendSpider and TrendSpider-class platforms auto-detect divergences and pattern completions with explicit confidence scoring; Bloomberg/Refinitiv attach data-sufficiency flags to every technical output.
- **Recommended redesign:** Add a `signal_confidence` field to every indicator's output, computed from lookback-length adequacy; add divergence detection; reconcile the two indicator implementations into one.
- **Expected improvement:** Medium-high for false-positive reduction; directly addresses finding #4 in Section 3.
- **Priority:** High
- **Effort:** Medium

### 4.2 Fundamental Analysis Engine — REAL, separate — Maturity 65%

*(Carried forward from prior audit Section 4.7.)* 18 ratios across profitability/liquidity/leverage/efficiency/valuation/growth. No P/S ratio, no DCF, no real peer comparison (blocked by 0% sector data). **Recommended redesign:** add P/S; add a percentile-relative valuation score once sector data exists (Section 4.4 of the prior audit); this is the natural home for the new "Valuation Score" and "Growth Score" outputs required in Section 5 below. Priority: Critical (feeds 3 of the 15 required sub-scores). Effort: Medium once sector data is fixed.

### 4.3 Dividend Engine — REAL but thin — Maturity 40%

- **Strengths:** Real ingestion, real dividend-yield ratio, a real DIVIDEND watchlist rule.
- **Weaknesses:** The live Phase 9 run ingested **zero dividend rows across all 100 symbols** despite 100/100 reported ingestion "success" — ambiguous between a genuinely dividend-quiet window and a too-short lookback (prior audit, Section 4.5, unresolved).
- **Hidden risks:** A user could conclude "no dividend stocks exist in this market" from a data artifact, not reality — a real trust risk in a market where dividend investing is a common Saudi retail strategy.
- **Technical debt:** No logged, configurable lookback window.
- **Missing algorithms:** No dividend-growth-streak analysis (consecutive years of increases — a standard Peter-Lynch/dividend-investor signal), no payout-ratio sustainability check, no dividend-cut risk model.
- **Missing data:** Multi-year dividend history depth is unconfirmed.
- **Missing signals:** Dividend growth rate, payout ratio trend, dividend coverage from free cash flow (blocked on 4.6 below).
- **False positives:** A high current yield with a deteriorating payout ratio would currently score as attractive with no warning — a classic "yield trap" the engine cannot detect.
- **False negatives:** A company with a modest but consistently growing dividend (attractive to long-term dividend investors) scores no differently than a flat or declining one, since no streak/growth-trend logic exists.
- **How institutions solve this:** Dividend-focused funds explicitly screen for payout-ratio sustainability and cut risk, not yield alone.
- **How the best platforms solve it:** Morningstar and Simply Safe Dividends-class tools score dividend *safety*, not just yield.
- **Recommended redesign:** Widen and log the ingestion lookback; add payout-ratio-trend and streak analysis; add a dividend-safety sub-score feeding the new Dividend Score in Section 5.
- **Expected improvement:** Medium-high for dividend-seeking use cases specifically.
- **Priority:** Medium
- **Effort:** Medium

### 4.4 Earnings Quality — ABSENT — Maturity 0%

- **Strengths:** None — does not exist.
- **Weaknesses:** No accrual-ratio analysis, no Beneish M-Score (earnings-manipulation risk), no Piotroski F-Score (fundamental strength composite), confirmed absent by direct grep across `src/`.
- **Hidden risks:** This is the single largest *credibility* risk in the fundamental scoring path — a company can report strong net income driven by accounting choices rather than real cash generation, and Basirah's fundamental score today cannot tell the difference. This directly weakens finding #3 in Section 3.
- **Technical debt:** N/A (nothing to have debt in).
- **Missing algorithms:** Beneish M-Score, Piotroski F-Score, accrual ratio ((net income − operating cash flow) / total assets).
- **Missing data:** Requires real cash flow statement data (see 4.6) and multi-period balance sheet history to compute accruals and F-Score components.
- **Missing signals:** Earnings-quality flag (clean / caution / red-flag) is entirely absent from every recommendation today.
- **Possible false positives:** Every "strong fundamentals" BUY today is vulnerable to this exact failure mode — a company with manipulated or low-quality earnings would currently score well.
- **Possible false negatives:** N/A — this is a pure omission, not a detection engine with a false-negative rate.
- **How institutions solve this:** This is table-stakes at any serious research desk (Goldman/Morgan Stanley/JPMorgan equity research) and is exactly what quant funds like Renaissance/Two Sigma build systematic accrual/quality factors around — earnings-quality screening is one of the best-documented, most reproducible alpha factors in academic and practitioner literature (Sloan 1996 accrual anomaly, Piotroski 2000).
- **How the world's best platforms solve it:** Bloomberg/Capital IQ/Refinitiv expose these directly as computed fields; most retail platforms (TradingView, Finviz) do not — this would be a genuine differentiator for Basirah, not just parity.
- **Recommended redesign:** Build a dedicated `EarningsQualityEngine` computing accrual ratio, Piotroski F-Score (9 binary criteria, well-documented, computable from existing balance-sheet/income-statement fields plus cash flow once ingested), and a Beneish-style red-flag screen, feeding directly into the new Quality Score in Section 5.
- **Expected improvement:** High — closes one of the most concrete credibility gaps identified in Section 3.
- **Priority:** Critical
- **Effort:** Medium (the formulas are standard and well-documented; the blocker is data, see 4.6)

### 4.5 Financial Statement Analysis — PARTIAL, embedded in 4.2 — Maturity 55%

Full income statement and balance sheet fields are ingested and used across the 18 ratios; **cash flow statement is not** (see 4.6). No multi-period trend analysis beyond the single-period growth ratios already in the 18-ratio set (revenue/income/EPS growth are single-year, not multi-year CAGR or trend-consistency checks). **Recommended redesign:** add 3-5 year CAGR and trend-consistency scoring once multi-period history depth is confirmed. Priority: High. Effort: Medium.

### 4.6 Cash Flow Analysis — ABSENT — Maturity 0%

- **Strengths:** None — genuinely absent. Confirmed: `cash_flows` appears exactly once in the entire `src/` tree, in a doc-comment in `src/market_data/sahmk/service.py` describing what SAHMK's endpoint *conceptually* returns — no code parses, stores, or computes anything from it.
- **Weaknesses:** No free cash flow (FCF), no FCF yield, no FCF margin, no operating-cash-flow-to-net-income ratio (the core earnings-quality check), no cash conversion cycle.
- **Hidden risks:** This is the data prerequisite for 4.4's earnings-quality engine and for real dividend-sustainability analysis in 4.3 — its absence blocks two other critical fixes, not just itself.
- **Technical debt:** N/A.
- **Missing algorithms:** FCF = operating cash flow − capex; FCF yield = FCF / market cap; FCF margin = FCF / revenue.
- **Missing data:** Real cash flow statement ingestion from SAHMK's `/financials/` endpoint (or whichever sub-resource carries it) — **not verified whether SAHMK's API actually exposes this data at all**; this must be confirmed before committing engineering time to parsing it.
- **Missing signals:** FCF-based valuation (often more reliable than earnings-based valuation, especially for capital-intensive Saudi sectors like petrochemicals and utilities that dominate this market).
- **Possible false positives:** A company can report GAAP profitability while burning real cash (common in capital-intensive buildouts) — currently invisible to Basirah.
- **Possible false negatives:** A company with temporarily depressed accounting earnings but strong real cash generation (e.g., due to heavy depreciation) would be undervalued by Basirah's current earnings-only view.
- **How institutions solve this:** Cash flow analysis is a first-principles requirement at every serious equity research desk and every quant value factor (Buffett's own stated framework is explicitly cash-flow-centric, not earnings-centric).
- **How the world's best platforms solve it:** Every institutional platform listed in Section 9 (Bloomberg, Capital IQ, Refinitiv, Morningstar) treats cash flow statements as a first-class, always-present dataset, not an optional extra.
- **Recommended redesign:** First, verify SAHMK API availability of cash flow statement data (a diagnostic task, not an implementation one). If available: build ingestion + FCF/FCF-yield/FCF-margin ratios, feeding the Quality and Valuation scores in Section 5. If unavailable at this SAHMK tier: this becomes a vendor/data-sourcing decision, not an engineering one, and should be escalated as such rather than silently worked around.
- **Expected improvement:** Very high — this is one of the two or three highest-leverage data gaps in the entire platform.
- **Priority:** Critical
- **Effort:** Low (diagnostic check) then Medium-High (full implementation), entirely gated on data availability

### 4.7 Valuation Models — PARTIAL, embedded in 4.2 — Maturity 35%

P/E, P/B, dividend yield, market cap exist (real, live-verified). **No DCF, no relative/peer valuation (blocked by sector data), no FCF-yield valuation (blocked by 4.6).** This is one of the most consequential gaps for a platform claiming Buffett/Lynch-caliber analysis, since intrinsic-value estimation is the core of that tradition. **Recommended redesign:** a simple, transparent 2-stage DCF (explicit growth-rate and discount-rate assumptions, always shown, never hidden — consistent with the "state your assumptions" explainability requirement in Section 6) as a genuinely new capability; peer-relative valuation once sector data exists. Priority: Critical. Effort: High (DCF requires careful, explicit assumption-handling to avoid presenting false precision).

### 4.8 Growth Models — PARTIAL, embedded in 4.2 — Maturity 45%

Single-year revenue/net-income/EPS growth exist. No multi-year CAGR, no growth-consistency/quality scoring (a company with volatile boom-bust growth should score differently than one with steady growth, even at the same average rate — a genuine Peter-Lynch-style distinction currently invisible to Basirah). Priority: High. Effort: Medium.

### 4.9 Profitability Models — PARTIAL, embedded in 4.2 — Maturity 55%

Net margin, gross margin, ROE, ROA exist and are real. No DuPont decomposition (ROE = net margin × asset turnover × equity multiplier — all three components already independently computed but never assembled into the standard decomposition that explains *why* ROE is high, e.g., leverage-driven vs. genuinely efficient). **Recommended redesign:** assemble the existing components into an explicit DuPont breakdown — near-zero new computation required, pure synthesis of numbers already produced. Priority: Medium. Effort: Low.

### 4.10 Liquidity Analysis — PARTIAL, embedded in 4.2 — Maturity 60%

Current ratio, quick ratio, cash ratio all exist and are real. Reasonably mature relative to the rest of the fundamental suite. Priority: Low. Effort: Low.

### 4.11 Volatility Analysis — PARTIAL, embedded across ATR (technical) and risk_engine.py (portfolio) — Maturity 35%

- **Strengths:** ATR exists at the symbol level (technical engine); a real, numpy-based volatility computation exists in the portfolio risk engine.
- **Weaknesses:** No standalone, symbol-level "Volatility Score" as a first-class output; no volatility regime detection (is the *market* currently high- or low-volatility, which changes how every other signal should be weighted — a standard quant technique).
- **Hidden risks:** Treating a technical or momentum signal identically in a high-volatility regime and a low-volatility regime is a well-documented source of false signals.
- **Missing algorithms:** Realized-volatility regime classification (e.g., rolling volatility percentile vs. its own history); implied volatility (not available — no options data from SAHMK, a real vendor limitation).
- **Missing data:** Options/implied-vol data (vendor limitation, not fixable in-house).
- **Missing signals:** Volatility-regime-adjusted confidence — a signal generated during a volatility spike should carry explicitly lower confidence than the same signal in calm conditions; this adjustment does not exist anywhere today.
- **False positives/negatives:** Momentum and breakout signals during abnormal volatility spikes (e.g., around unscheduled news events, which Basirah also cannot detect — see 4.19) are currently treated with the same confidence as normal-regime signals.
- **How institutions solve this:** Regime-conditioning is standard practice at every systematic fund (Two Sigma, Renaissance-style); Ray Dalio's "All Weather" framework is explicitly regime-based.
- **How the best platforms solve it:** TrendSpider and similar platforms surface volatility regime explicitly; Bloomberg's implied-vol surfaces are a core institutional tool (unavailable to Basirah without options data).
- **Recommended redesign:** Build a realized-volatility-regime classifier (rolling percentile of ATR or realized std. dev. against its own trailing history — needs no new data, only new computation) and use it to scale confidence, not just as an informational display.
- **Expected improvement:** Medium-high — directly improves confidence calibration quality, which Section 5/6 depend on.
- **Priority:** High
- **Effort:** Medium

### 4.12 Momentum Analysis — REAL, embedded in decision engine — Maturity 55%

A real `MomentumScoreContributor` exists (0.13 weight) and RSI/MACD/Stochastic feed it. No confirmation of statistical robustness (never validated against real outcomes — same root cause as Section 3's finding #1). Priority: High (shares the calibration fix already identified in the prior audit). Effort: Low once the calibration scheduler is on.

### 4.13 Relative Strength — FORMULA EXISTS, NEVER FED REAL DATA (wired no-op) — Maturity 10%

- **Strengths:** A real `sector_relative_strength` input path exists in `external_factor_contributors.py`, expecting `context.extra["sector_rotation"]["sector_relative_strength"]`.
- **Weaknesses:** **Confirmed by grep: nothing in the entire codebase ever populates that key.** This is a formula waiting for data that never arrives — production always evaluates this as a neutral/absent signal.
- **Hidden risks:** A future engineer reading `external_factor_contributors.py` could reasonably believe relative strength is a live, working signal — it is not.
- **Missing data:** Sector-level aggregate performance (blocked by 0% sector data, Section 4.3 of the prior audit) and/or TASI index-level performance (blocked by 4.16 below) — either would need to exist before this formula could ever produce a real value.
- **How institutions solve this:** Relative strength (a stock vs. its sector, and a stock vs. the broad index) is one of the most standard, well-validated momentum-adjacent factors in both academic and practitioner quant research (this is literally the "RS Rating" IBD/MarketSmith is built around).
- **How the best platforms solve it:** MarketSmith's entire value proposition centers on relative strength ranking; TradingView and Finviz both expose it as a standard screen field.
- **Recommended redesign:** Once sector data (4.3, prior audit) and/or TASI index data (4.16 below) are ingested, wire real values into this already-built formula — this is one of the cheapest large wins available once its two data prerequisites are closed, since the scoring logic is already written and tested.
- **Expected improvement:** High, and unusually cheap once unblocked.
- **Priority:** Critical (high value, low marginal cost once prerequisites close)
- **Effort:** Low once data prerequisites (4.3 prior audit + 4.16 below) are met; the blocking work is entirely in data, not algorithm.

### 4.14 Sector Strength — BLOCKED, same root cause as 4.13 — Maturity 5%

Structurally identical situation to 4.13 — blocked entirely on the 0% sector-data gap. No separate engineering work needed beyond what 4.13 already requires. Priority: Critical (shared with 4.13). Effort: Zero marginal effort beyond fixing sector data.

### 4.15 Industry Rotation — FORMULA EXISTS AS DISCLOSED NO-OP — Maturity 5%

This is `SectorRotationScoreContributor` (0.01 weight), already documented in the prior audit as a disclosed no-op. Same fix path as 4.13/4.14. Priority: Medium (lowest-weighted contributor even once fixed — 0.01 of total score — so real-world impact of fixing it is smaller than 4.13's, despite sharing a root cause).

### 4.16 Correlation Engine — REAL but narrow scope — Maturity 45%

- **Strengths:** A real `CorrelationMatrix` type and computation exist in `src/portfolio_intelligence/risk_engine.py`, used for portfolio-holdings diversification analysis; `src/backtesting/metrics.py` also computes correlation for strategy-comparison purposes. Both are genuine, working code.
- **Weaknesses:** This is *portfolio-holdings-to-each-other* correlation and *strategy-return* correlation — there is no market-wide, cross-sectional correlation/clustering engine (e.g., "which stocks move together, forming a real cluster distinct from the stated sector taxonomy" — often more informative than static sector labels, and notably would not be blocked by the sector-data gap since it needs only price history, not metadata).
- **Hidden risks:** None beyond scope limitation.
- **Missing algorithms:** Rolling pairwise correlation matrix across the full scanned universe; hierarchical clustering to discover natural groupings independent of (and validating against) any eventual sector taxonomy.
- **Missing data:** None — this only requires the OHLCV data already being ingested.
- **Missing signals:** "Correlation cluster" as an alternative or complement to sector for relative-strength comparisons — genuinely useful *even before* the sector-data gap is fixed, since it's derived purely from price behavior.
- **How institutions solve this:** Statistical/cluster-based grouping is standard in quant risk management (used explicitly to catch correlated risk that static sector labels miss, a lesson from numerous real market-stress episodes).
- **How the best platforms solve it:** Institutional risk platforms (Bloomberg PORT, BlackRock Aladdin conceptually) build correlation-based risk decomposition as a core feature, not an afterthought.
- **Recommended redesign:** Extend the existing correlation computation (already real, already tested for portfolios) to the full scanned universe on a schedule, producing a market-wide correlation/cluster map — genuinely available *before* the sector-data fix lands, and a good candidate for quick, real value.
- **Expected improvement:** Medium — a real, currently-untapped opportunity given the underlying computation already exists.
- **Priority:** Medium-High (notably not blocked by the sector-data critical path, unlike most other gaps in this section)
- **Effort:** Low-Medium

### 4.17 Macro Economy Signals — FORMULA EXISTS AS DISCLOSED NO-OP — Maturity 5%

`MacroScoreContributor` (0.04 weight), a disclosed no-op (prior audit). No real macroeconomic data source (oil price, interest rates, USD/SAR peg dynamics — all first-order drivers of the Saudi market specifically) is wired anywhere. **This is a real, Saudi-market-specific gap**: oil price and Saudi/Gulf monetary policy are unusually dominant macro drivers for this specific market (heavier than most developed markets, given the economy's structure), making this a higher-priority fix for Basirah specifically than a generic "macro factor" would be for a diversified-market platform. **Recommended redesign:** wire real Brent/WTI oil price and SAR interest-rate-proxy data (both are realistically obtainable from public/low-cost sources independent of SAHMK) into this already-built contributor. Priority: High (elevated specifically because of this market's structure). Effort: Medium (new data source integration, but the scoring slot already exists).

### 4.18 News Intelligence — REAL, separate — Maturity 70%

*(Carried forward from prior audit Section 4.15.)* Real LLM-based analysis with proper numeric grounding; correctly weighted low (0.04) given LLM-sourced uncertainty. **Recommended addition specific to this mandate:** feed aggregated news sentiment into the still-no-op Macro contributor (4.17) as a genuine, if partial, macro proxy while dedicated macro-data integration is built. Priority: Medium. Effort: Low (synthesis of two already-real subsystems).

### 4.19 Event Detection — ABSENT — Maturity 0%

- **Strengths:** None — confirmed absent by grep across the entire `src/` tree (no "event_detection," no earnings-calendar awareness, no corporate-action detection).
- **Weaknesses:** No awareness of scheduled events (earnings releases, dividend ex-dates, AGMs) or unscheduled ones (analyst rating changes, regulatory announcements) that materially change a stock's risk profile around a specific date.
- **Hidden risks:** A recommendation issued the day before an earnings release carries fundamentally different risk than the same score issued mid-quarter — Basirah cannot currently distinguish these, and would present both with identical confidence.
- **Technical debt:** N/A.
- **Missing algorithms:** Earnings-calendar-proximity flag; a simple "elevated event risk" downgrade to confidence when a known catalyst is imminent.
- **Missing data:** An earnings calendar / corporate-actions calendar feed — **not verified whether SAHMK exposes this**; may require a supplementary data source.
- **Missing signals:** "Days to next earnings" as an explicit field on every recommendation; would materially improve both explainability (Section 6's "what could invalidate this" question) and risk scoring.
- **Possible false positives:** A momentum-driven BUY issued right before an earnings release that misses expectations is a completely foreseeable, currently-undetected risk category.
- **Possible false negatives:** N/A (pure omission).
- **How institutions solve this:** Every institutional research desk explicitly flags earnings-proximity risk; algorithmic funds routinely reduce position sizing or pause signal generation around known catalysts.
- **How the best platforms solve it:** Finviz, TradingView, and Koyfin all surface earnings-calendar proximity as a standard, prominent field.
- **Recommended redesign:** Source an earnings-calendar feed (SAHMK first, a supplementary vendor if unavailable); add a "days to next known event" field and a confidence-dampening rule when that window is small.
- **Expected improvement:** High relative to its likely engineering cost — this is a well-understood, standard capability elsewhere in the industry.
- **Priority:** Critical
- **Effort:** Medium (mostly data-sourcing; the confidence-dampening logic itself is simple once the data exists)

### 4.20 Insider Activity — DISCLOSED NO-OP, USER-LABELED FUTURE CAPABILITY — Maturity 2%

`InsiderTransactionsScoreContributor` (0.02 weight) exists as a disclosed no-op. Per the mandate's own framing ("future capability"), this is correctly deprioritized relative to the critical gaps above. Note for the record: this data is often not available for the Saudi market at retail-accessible cost even from premium vendors — worth confirming feasibility before committing to a timeline. Priority: Low (explicitly deferred by the user). Effort: Unknown pending data-source research.

### 4.21 Institutional Flow — ABSENT, USER-LABELED FUTURE CAPABILITY — Maturity 0%

No code, no data source identified. Same treatment as 4.20 — correctly deferred. Worth flagging: "institutional flow" data (block trades, 13F-style holdings disclosure) has a materially different, often much higher, cost/availability profile in the Saudi market than in the US — this should be a data-feasibility research task before any engineering estimate is attempted. Priority: Low (explicitly deferred). Effort: Unknown, data-feasibility research needed first.

### 4.22 AI Recommendation Engine — REAL, the central subject of this document — Maturity 55% as engineering, 24% as intelligence

Fully covered in Section 3 and redesigned in Section 5. Not re-summarized here to avoid duplication.

### 4.23 Confidence Engine — REAL design, unvalidated in production — Maturity 60% as built, 0% as proven

*(Carried forward from prior audit Section 4.9.)* Statistically sound Platt/isotonic design; never calibrated against real outcomes because the scheduler that would do so defaults to off. **Directly relevant to this mandate:** an unvalidated confidence number is itself an explainability failure — presenting "70% confidence" without evidence it means what it claims is a form of false precision the mandate explicitly rejects ("never exaggerate... if evidence is missing, say so"). **Recommended immediate action:** either turn on real calibration (prior audit's top recommendation) or, until enough real samples exist, relabel the field honestly (e.g., "model certainty" rather than "confidence," with an explicit note that it is not yet calibrated against real outcomes) so the platform is never overstating what it currently knows. Priority: Critical. Effort: Low (scheduler activation) to relabel immediately at near-zero cost.

### 4.24 Ranking Engine — REAL, clean architecture, but structurally cannot answer "why better than #2–#11" — Maturity 80% as engineering, 20% as comparative-explainability

*(Carried forward from prior audit Section 4.10.)* This is the central mechanical gap behind Section 3's finding #2. **Recommended redesign:** covered in full in Section 6 (a new comparative-explanation layer that consumes the ranking engine's output, not a change to the ranking engine's own sorting logic, which is already sound). Priority: Critical. Effort: Medium.

### 4.25 Portfolio Construction — REAL breadth, no real optimizer — Maturity 55%

*(Carried forward from prior audit Section 4.12.)* No mean-variance/efficient-frontier solver despite the "OptimizationEngine" name. Directly relevant here: a portfolio built without genuine optimization cannot claim BlackRock/Two-Sigma-caliber construction, regardless of how good the underlying stock-level scores become. Priority: High. Effort: High.

### 4.26 Risk Management — REAL per-symbol and per-portfolio computation, no market-benchmark risk — Maturity 50%

*(Carried forward from prior audit Section 4.11, sharpened here.)* Beta is always `None` (no index data — 4.16 below). No VaR/CVaR. Given the mandate's explicit inclusion of "Ray Dalio" and "Risk Manager" as required viewpoints, this is a significant gap — Dalio's entire framework is risk-parity/regime-based, which requires exactly the market-benchmark and regime data currently missing. Priority: Critical. Effort: High.

### 4.27 Watchlists — REAL, clean architecture — Maturity 80%

*(Carried forward from prior audit Section 4.10, unchanged — no new findings specific to this mandate.)* Priority: Low. Effort: Low.

### 4.28 Explainability Engine — REAL narrative generation, cannot yet do comparative or invalidation-condition explanation — Maturity 62% as narrative generation, 20% against this mandate's specific 9-question standard

Fully redesigned in Section 6.

### 4.29 (Additional, not in the original 28 but load-bearing) Market Index / TASI Benchmark Data — ABSENT — Maturity 0%

- **Strengths:** None — the domain model (`MarketSnapshot`) that would hold this exists; it is simply never populated. Confirmed via the platform's own code comment in `risk_engine.py`: *"No market/TASI index price history is ingested in this platform... portfolio beta cannot be computed against a live benchmark."*
- **Weaknesses:** This single gap independently blocks: real beta (4.26), real relative strength (4.13/4.14), a real TASI-comparison backtesting baseline (Section 7), and any claim about market-relative performance anywhere in the platform.
- **Hidden risks:** This is arguably the single most consequential missing dataset in the entire audit, given how many other findings trace back to it.
- **Missing data:** Daily (ideally intraday) TASI index level history — likely obtainable either from SAHMK directly (not yet confirmed) or a public/supplementary source.
- **How institutions solve this:** No serious equity research or quant platform operates without a benchmark series — this is the most basic possible requirement for any "beats the market" or "risk-adjusted" claim.
- **Recommended redesign:** Ingest TASI (and ideally sector sub-indices, once available) as a first-class, always-present dataset — the domain model already exists, this is a data-sourcing and ingestion-pipeline task, not new architecture.
- **Expected improvement:** Extremely high — the single highest-leverage data fix identified in this entire document, unlocking 3+ other findings at once.
- **Priority:** Critical — arguably the single highest-priority item in this whole audit.
- **Effort:** Low-Medium, entirely dependent on data-source availability (diagnostic check needed first).

### 4.30 Catalyst Detection Engine — ABSENT, required for the Investment Thesis Engine — Maturity 0%

- **Strengths:** None yet — but real building blocks exist to draw on. The `RankingEngine`'s MOST_IMPROVED_TODAY/RECENTLY_UPGRADED categories (prior audit 4.10) were designed for exactly this kind of "what changed" signal and have simply never been exercised (no two consecutive scans have been run back-to-back in this engagement's evidence) — this is not a new concept for the codebase, it is an existing, unexercised one.
- **Weaknesses:** No code anywhere distinguishes a *static* score from a *fresh trigger* — every recommendation today reads the same whether the setup formed yesterday or three months ago.
- **Hidden risks:** Without this, "why now" (a required element of the thesis) cannot be answered honestly — a recommendation with no freshness signal is really answering "why ever," not "why now."
- **Technical debt:** N/A (new).
- **Missing algorithms:** A "signal freshness" diff (this scan's score vs. the immediately prior scan's, once consecutive scans exist); a technical-catalyst detector for forward-looking triggers computable from data already ingested (e.g., "price is 1.2% from a confirmed resistance breakout," "a 20/50-day MA cross is projected within N sessions at current trajectory").
- **Missing data:** Fundamental/event catalysts (earnings date, dividend ex-date) are blocked on 4.19's earnings-calendar gap; technical catalysts are not data-blocked.
- **Missing signals:** "Days/sessions to projected catalyst" as an explicit field.
- **Possible false positives:** A projected technical trigger (e.g., "MA cross imminent") is an extrapolation, not a certainty — must be labeled as a projection with the assumption stated (current trend continues), never presented as a scheduled event the way an earnings date would be.
- **Possible false negatives:** Real catalysts this platform cannot see at all (regulatory announcements, analyst actions, macro surprises) will never be flagged — an honest, permanent limitation given current data sources, not a bug to be silently fixed.
- **How institutions solve this:** Sell-side research explicitly separates "thesis" from "catalyst" sections precisely because a good company without a near-term catalyst is a different trade than one with one imminent.
- **How the best platforms solve it:** Finviz/Koyfin/TradingView all surface earnings-date proximity prominently; none of the platforms reviewed in Section 9 combine that with a technical-catalyst projection the way this design proposes.
- **Recommended redesign:** Build the technical-catalyst half now (no new data required, reuses existing indicators); wire the fundamental/event half once 4.19's calendar data is confirmed available.
- **Expected improvement:** High — directly closes the "why now" gap identified in the architectural decision above.
- **Priority:** Critical (technical half); High (event half, data-gated)
- **Effort:** Low (technical half); Medium (event half, gated on 4.19)

### 4.31 Scenario Engine (Bull / Base / Bear Case Modeling) — ABSENT, required for the Investment Thesis Engine — Maturity 0%

- **Strengths:** None yet, but the arithmetic foundation is real and already built — the DCF proposed in 4.7 and the existing target-price/expected-return computation are exactly the machinery a scenario engine needs to run three times under three different assumption sets, not new math.
- **Weaknesses:** Today's single `target_price` is presented as if it were the only plausible outcome, with no stated alternative and no stated probability weighting — a real precision-overstatement risk the mandate explicitly warns against.
- **Hidden risks:** If built carelessly (e.g., letting an LLM freely narrate "in the bull case, the stock could reach X"), this becomes the single highest-risk component in the entire redesign for hallucinated numbers, precisely because a scenario narrative *sounds* more authoritative than a bare score. This must be built as a **deterministic re-run of the existing scoring/valuation math under explicitly different, stated input assumptions** (e.g., Bull = above-trend growth-rate assumption fed through the same 4.7 DCF; Bear = a confirmed technical breakdown level from 4.1's support/resistance detection) — never a free-text LLM generation of a price number. The existing numeric-grounding (R3) discipline must extend to cover every number in every scenario, with zero exceptions.
- **Technical debt:** N/A (new).
- **Missing algorithms:** Three-scenario valuation re-run (bull/base/bear) with explicit, always-displayed assumption deltas per scenario; scenario-to-price-target mapping.
- **Missing data:** None beyond what 4.7's DCF and 4.1's support/resistance already need.
- **Missing signals:** Scenario-conditional expected return and risk (today's single Risk Score is scenario-blind).
- **Possible false positives:** An overly wide bull case (unrealistic upside) or overly narrow bear case (understated downside) if assumption bounds aren't disciplined — this needs explicit, documented, defensible bounds (e.g., historical volatility-derived ranges), not arbitrary multipliers.
- **Possible false negatives:** A bear case that fails to incorporate real known risks (e.g., an approaching earnings date from 4.30, if the event turns unfavorable) would understate real downside.
- **How institutions solve this:** Bull/base/bear scenario modeling with explicit price targets per case is standard structure at every sell-side research note (Goldman/Morgan Stanley/JPMorgan) and every serious buy-side memo.
- **How the best platforms solve it:** None of the retail-tier platforms in Section 9 (TradingView, Finviz, Koyfin) do this natively; Capital IQ/Bloomberg support it as an analyst-driven workflow, not an automated one — a genuine differentiation opportunity if built with the grounding discipline above, and a genuine credibility risk if built without it.
- **Recommended redesign:** Build as a deterministic re-parameterization of already-real valuation/scoring code, with every assumption explicitly logged and displayed — never as free-form LLM narrative generation of numbers.
- **Expected improvement:** Very high for perceived and actual research quality — this is the single most visible element of "reads like an institutional research report."
- **Priority:** Critical
- **Effort:** Medium-High, and the grounding discipline is non-negotiable regardless of time pressure

### 4.32 Probability / Return-Distribution Engine — ABSENT, required for the Investment Thesis Engine — Maturity 0%

- **Strengths:** None yet, but a statistically honest version is genuinely buildable now without waiting on any live-outcome data, because it can be derived purely from the OHLCV history Basirah already ingests.
- **Weaknesses:** A "probability distribution" is the single most easily-abused element of this entire request if built dishonestly — a number like "68% probability of a positive return" implies a validated statistical model, and presenting one that isn't validated would be exactly the kind of exaggeration the mandate explicitly forbids.
- **Hidden risks:** This must be built and labeled as **two distinct, never-conflated tiers**: **(a) a historical-simulation probability** — a Monte Carlo / bootstrap resampling of the stock's own real historical daily/weekly returns projected over the stated time horizon, producing a real, statistically legitimate (if backward-looking) distribution of outcomes — buildable today from existing ingested price history, no live-outcome data required; **(b) an empirically-calibrated probability** — "recommendations with this exact score profile have historically been right X% of the time" — which is **not available until the confidence-calibration loop (prior audit 4.9/4.13) has run long enough on real accumulated outcome data to mean anything**, and must never be presented before that. Tier (a) must always be clearly labeled "historical price simulation, not a validated forecast track record"; conflating it with tier (b) is the single most important thing to avoid getting wrong in this entire document.
- **Technical debt:** N/A (new).
- **Missing algorithms:** Bootstrap/Monte Carlo resampling of historical returns (tier a, buildable now); the empirical calibration itself is already designed (prior audit 4.9) and just needs its scheduler turned on and enough real samples to accumulate (tier b).
- **Missing data:** None for tier (a); real accumulated `recommendation_outcomes` at sufficient sample size for tier (b) (prior audit's 30-sample Platt-scaling minimum, ideally the 1,000-sample isotonic-regression threshold for a real distribution shape, not just a point calibration).
- **Missing signals:** Tier (a) exists nowhere today; tier (b) is designed but dormant.
- **Possible false positives/negatives:** Tier (a) alone, if mislabeled as a forecast rather than a historical-pattern simulation, would systematically overstate confidence in a way the mandate explicitly prohibits — this is a labeling discipline, not just a technical one, and should be enforced at the API/schema level (a mandatory `distribution_type: "historical_simulation" | "calibrated_forecast"` field), not just in prose.
- **How institutions solve this:** Quant funds distinguish backtested/simulated distributions from live-validated ones as a matter of course; presenting the former as the latter is a well-known, well-documented failure mode across the industry (backtest overfitting).
- **How the best platforms solve it:** Genuinely, none of the retail-tier platforms in Section 9 offer this distinction cleanly — most present a single "AI confidence" number with no such disclosure. Doing this honestly, with the two-tier labeling, would be a real, differentiated strength, not mere parity.
- **Recommended redesign:** Build tier (a) now; gate tier (b) explicitly on prior audit Section 4.13's scheduler activation and real sample accumulation; never merge the two into one displayed number.
- **Expected improvement:** High if built honestly with the two-tier distinction; **negative** (a genuine credibility risk) if the distinction is skipped under time pressure.
- **Priority:** Critical for tier (a); Critical-but-time-gated for tier (b) (cannot be rushed — depends on real calendar time accumulating real samples, exactly as prior audit Section 4.13 already established for confidence calibration generally)
- **Effort:** Medium for tier (a); Low additional engineering for tier (b) beyond what prior audit 4.9/4.13 already specified, but gated on time, not effort

### 4.33 Investor Suitability Classifier — ABSENT, required for the Investment Thesis Engine, flagged for compliance review before any implementation — Maturity 0%

- **Strengths:** None yet.
- **Weaknesses:** Does not exist; more importantly, **this is the one new component in this entire document that should not proceed straight to an engineering estimate.**
- **Hidden risks:** Classifying a recommendation as "suitable for a conservative, income-focused investor" vs. "suitable for a high-risk-tolerance growth investor" moves Basirah from *publishing research* toward *making a suitability determination* — in many real-world regulatory regimes (comparable to KYC/suitability rules in investment-advisory contexts), automated suitability determinations carry real compliance obligations that are categorically different from publishing a scored, explained recommendation. This exact class of risk was already disclosed, in different words, in this platform's own AI Evolution design (prior sessions' plan: *"publishing AI accuracy/track-record numbers for a financial product likely has real regulatory/disclosure implications... a legal-review item, not an engineering decision to make unilaterally"*) — the same standard applies here, arguably more directly.
- **Technical debt:** N/A.
- **Missing algorithms:** A mapping from {time horizon, risk score, volatility regime, dividend profile} to a descriptive investor-archetype label — technically simple once the inputs exist (mostly Section 5.1's existing Risk/Dividend/Volatility scores).
- **Missing data:** None technical; the missing piece is a legal/compliance determination of what this platform is and isn't allowed to say, and in what jurisdiction(s), before any label like this is ever shown to a user.
- **Missing signals:** N/A — this is a labeling/classification layer over signals that mostly already exist elsewhere in the design.
- **Possible false positives/negatives:** N/A — the primary risk here is regulatory/trust exposure, not statistical error.
- **How institutions solve this:** Real broker-dealers and advisors operate under explicit, licensed suitability frameworks with compliance sign-off; research-only publishers (which Basirah more closely resembles today) typically avoid personalized suitability claims specifically to stay outside that regulatory perimeter, describing a security's own risk/return profile instead of telling a user who it is "for."
- **How the best platforms solve it:** None of the platforms in Section 9 present per-recommendation "suitable investor" labels as a marketed feature — this is worth noting as possibly a deliberate industry-wide avoidance of exactly this risk, not an oversight Basirah would be first to fix.
- **Recommended redesign:** **Do not implement a personalized "suitable for X investor" classifier without an explicit legal/compliance review first.** A safer, lower-risk alternative that achieves most of the same explanatory value: describe the *security's own* profile in objective terms already computed elsewhere in this design ("short-horizon, high-volatility, momentum-driven profile" — a restatement of Section 5.1's Risk/Momentum/Volatility scores) rather than telling a user who they are or should be. This reframing should be the default recommendation pending legal review, not a stopgap.
- **Expected improvement:** Meaningful for perceived completeness of the thesis; the compliance risk of getting this wrong outweighs that benefit until reviewed.
- **Priority:** Deferred pending legal/compliance review — do not schedule engineering effort until that review concludes.
- **Effort:** Low (technical) / Unknown (compliance review timeline, outside engineering's control)

---

## 5. The Recommendation & Investment Thesis Architecture

### 5.1 The Scoring Layer (Evidence Inputs to the Thesis)

This subsection is the original Section 5 design, unchanged in substance — it now serves as the evidence layer feeding Section 5.2's thesis, rather than being the end product shown to a user.

**Design principle:** every one of the 15 required scores must be traceable to real, named inputs — never a black-box number. Where an input doesn't exist yet, the score must be marked `NOT AVAILABLE` rather than silently defaulting to neutral, so a user can never mistake "no data" for "neutral data." This is a direct response to "never hide uncertainty."

| Score | Composition | Status today |
|---|---|---|
| **Technical Score** | Existing `TechnicalScoreContributor` output, extended with the signal-confidence field from 4.1 | Real, needs the confidence extension |
| **Fundamental Score** | Existing `FundamentalScoreContributor`, extended with DuPont decomposition (4.9) and multi-year trend consistency (4.5) | Real, needs extension |
| **Valuation Score** | New — P/E, P/B, dividend yield percentile-ranked (once sector data exists) plus a transparent-assumption DCF (4.7) | Needs to be built |
| **Growth Score** | New — multi-year CAGR + growth-consistency scoring, replacing today's single-year growth ratios (4.8) | Needs to be built from real, already-ingested data |
| **Quality Score** | New — Piotroski F-Score + accrual ratio (4.4), gated on cash-flow data (4.6) | Needs to be built; partially data-blocked |
| **Momentum Score** | Existing `MomentumScoreContributor`, extended with volatility-regime adjustment (4.11) | Real, needs extension |
| **Risk Score** | Existing `RiskScoreContributor` + portfolio-level VaR/CVaR (4.26), extended with real beta once index data exists (4.29) | Real, materially incomplete without 4.29 |
| **Liquidity Score** | New, first-class — current/quick/cash ratios already computed (4.10), simply not currently surfaced as an independent score | Cheap to build — pure synthesis of existing numbers |
| **Sector Score** | New — requires sector data (prior audit 4.3) and the correlation-cluster alternative (4.16) as a fallback if taxonomy data remains unavailable | Data-blocked; correlation-cluster fallback is available sooner |
| **Dividend Score** | New — dividend safety/payout-sustainability, replacing today's raw yield-only signal (4.3) | Needs to be built |
| **Macro Score** | Existing `MacroScoreContributor` slot, wired to real oil-price/rate data for the first time (4.17) | Currently a no-op; needs real data wiring |
| **News Score** | Existing `NewsSentimentScoreContributor` | Real, unchanged |
| **AI Composite Score** | The full weighted blend of all scores above — **this is what "Overall Score" and "AI Composite Score" both refer to today, and that conflation should end.** Recommend explicitly distinguishing: **Overall Score** = the blend as currently computed (transparent, deterministic, always available); **AI Composite Score** = the *eventual* learned-model output (prior audit Section 4.8's Phase E), run only as a paper-trading challenger until it statistically outperforms Overall Score via the existing significance-testing framework. Presenting a not-yet-validated learned score as authoritative today would itself violate "never exaggerate." | Overall Score real today; AI Composite Score does not yet exist and should not be presented as if it does |
| **Confidence** | The existing Platt/isotonic-calibrated confidence (prior audit 4.9), **honestly labeled as uncalibrated until the evaluation scheduler has run long enough to validate it** | Real design, unvalidated in production today |
| **Overall Score** | See AI Composite Score row — this is the current deterministic blend, kept as the always-available, fully-explainable "baseline" score even after a learned model exists | Real today |

**Weighting philosophy:** Do not hand-tune new weights for the newly added scores either. Every new sub-score should enter the blend at a provisional, clearly-labeled-as-unvalidated weight, and should be included in the very first real run of the (already-built, currently-unscheduled) statistical calibration job the moment enough outcome data exists to test it. Repeating the current mistake — hand-set weights presented as authoritative — with a longer list of factors would not be an improvement.

### 5.2 The Investment Thesis Engine — Basirah's New Core Output Layer

**This is the architectural decision reached in this final review.** Basirah should stop presenting a score-plus-paragraph and start producing a structured, falsifiable investment case — every recommendation becomes an `InvestmentThesis` object, not a `Recommendation` row with a narrative attached. The distinction matters: a score answers "how much do I like this," a thesis answers "here is the specific, checkable claim, here is what would prove it wrong, and here is the range of ways it could play out." Only the second is defensible in the sense Section 3 found lacking.

**Field-by-field mapping — every element requested, honestly assessed against what exists, what's new, and what it depends on:**

| Thesis element | Source | Status |
|---|---|---|
| Why this company? | Existing narrative generator (`narrative_builder.py`), extended with Section 5.1's new scores | Real today, needs 5.1's extensions |
| Why now? | **New — 4.30 Catalyst Detection Engine**, using the ranking engine's already-designed-but-unexercised "what changed" categories plus new technical-catalyst projection | Needs to be built; the underlying ranking-category infrastructure already exists and has simply never been exercised |
| Why superior to competing companies? | **New — the `ComparativeExplanationEngine`** (Section 6) | Needs to be built; zero new data required |
| Which catalysts are expected? | **New — 4.30**, technical half buildable now, fundamental/event half gated on 4.19's earnings-calendar data | Partially buildable now |
| Which assumptions were made? | Existing plan from Section 6, extended to cover every Scenario Engine (4.31) assumption explicitly | Design exists; must be mandatory, not optional, for every scenario |
| Which risks exist? | Risk Score (5.1) + a structured risk-enumeration narrative synthesized from already-computed factors | Cheap synthesis of existing numbers |
| Which events would invalidate the thesis? | **New — the `InvalidationConditionGenerator`** (Section 6) | Needs to be built; zero new data required |
| Bull Case / Base Case / Bear Case | **New — 4.31 Scenario Engine** — three deterministic re-runs of the same real valuation/scoring math under three explicit, stated assumption sets | Needs to be built; must never be free-form LLM number generation (see 4.31's grounding requirement) |
| Expected Return | Existing target-price/expected-return computation, reframed as the Base Case output once 4.31 exists | Real today, needs reframing |
| Expected Risk | Risk Score (5.1) + stop-loss-derived downside estimate | Mostly real today |
| Time Horizon | Existing `TimeHorizon` field + watchlist taxonomy (Section 6) | Real today, minor formalization needed |
| Suitable Investor Profile | **New — 4.33 Investor Suitability Classifier — compliance-gated, do not implement without legal review** | Blocked pending compliance decision; a safer objective-profile alternative is recommended in 4.33 as the default |
| Probability Distribution | **New — 4.32 Probability/Return-Distribution Engine — two explicitly separate tiers (historical simulation, buildable now; empirically-calibrated, gated on real accumulated outcomes)** | Tier (a) buildable now; tier (b) time-gated, not effort-gated |
| Supporting Evidence | **New — an `EvidenceCitationLayer`** formalizing today's `contributor_breakdown` into an explicit, numbered claim-to-data-point citation list (e.g., "Claim: improving momentum — Evidence: RSI 28.4→61.2 over 10 sessions") | Needs to be built; pure synthesis of numbers already computed |

**Non-negotiable safety requirement:** the existing numeric-grounding discipline (the R3 pattern already used in `openai_llm_adapter.py` — an LLM's output can never introduce a number not already present in its input context) must extend to **every number in every part of the thesis**, with zero exceptions, and especially to the Scenario Engine (4.31) and Probability Engine (4.32). A thesis-shaped narrative reads as more authoritative than a bare score, which makes it a more dangerous surface for hallucinated numbers, not a safer one. Any implementation that lets free-form LLM generation produce a bull-case price target, a catalyst date, or a probability figure without tracing it to a real computed input would be a regression from the platform's own existing safety standard, not an advance.

**Illustrative structure only (not a real output — no analysis has been run to produce this):**

```
InvestmentThesis {
  symbol, company_name, generated_at, engine_version
  why_this_company: { narrative, evidence_citations[] }
  why_now: { narrative, catalysts[], freshness_signal }
  why_superior: { comparison_set[], factor_deltas[] }
  assumptions: { dcf_growth_rate, dcf_discount_rate, scenario_assumptions[] }
  risks: { risk_factors[], risk_score, data_sufficiency_flags[] }
  invalidation_conditions: [ { trigger, rationale } ]
  scenarios: {
    bull: { assumptions[], target_price, expected_return_pct },
    base: { assumptions[], target_price, expected_return_pct },
    bear: { assumptions[], target_price, expected_return_pct }
  }
  probability_distribution: {
    type: "historical_simulation" | "calibrated_forecast",   // never presented without this label
    distribution: [...]
  }
  time_horizon: SHORT_TERM | MEDIUM_TERM | LONG_TERM
  security_profile: { risk_level, volatility_regime, dividend_character }  // replaces "suitable investor" pending 4.33's compliance review
  scores: { technical, fundamental, valuation, growth, quality, momentum,
            risk, liquidity, sector, dividend, macro, news, confidence,
            overall_score }   // from Section 5.1 -- cited as evidence, not presented standalone
  supporting_evidence: [ { claim, data_points[] } ]
}
```

**What this replaces vs. what it adds:** Section 5.1's 15-score architecture is not discarded — it becomes the `scores` block above, cited as evidence throughout the rest of the object, exactly as an institutional research note cites specific ratios and targets while telling a structured story. Four new components are required to complete this (4.30–4.33); three are buildable with no new data and no compliance gate (4.30's technical half, 4.31, 4.32's tier a); one (4.33) is explicitly held pending a decision outside engineering's control.

---

## 6. Explainability Framework — Answering the 9 Required Questions

For each question, what exists today vs. what must be built:

| Question | Exists today? | What's needed |
|---|---|---|
| Why is this BUY? | **Partial.** The narrative generator explains this stock's own contributor breakdown. | Extend with the Section 5 scores as they come online. |
| Why is it better than the next 10 companies? | **Absent.** No comparative reasoning exists anywhere. | **New: a `ComparativeExplanationEngine`** that takes the ranked list from `RankingEngine` and generates an explicit factor-by-factor delta against the next N companies ("beats 1140 on technical (+2.1) and risk (+0.8), ties on fundamental, trails on momentum (-1.4)") — this is new logic operating on data the platform already computes, not new data collection. |
| Which factors increased the score? | **Partial** — the `contributor_breakdown` JSON has this, but only 5 of 11 contributors are first-class queryable columns (prior audit finding). | Promote all real (non-no-op) contributors to first-class columns; the new Section 5 scores should be first-class from day one. |
| Which factors reduced the score? | Same as above. | Same fix. |
| Which factors are uncertain? | **Absent.** No factor carries a confidence/data-sufficiency flag today. | **New:** every score in Section 5 must carry a paired `data_sufficiency` flag (e.g., "momentum score based on only 56 bars — below the 100-bar threshold for high confidence"). This is the single most direct fix for "never hide uncertainty." |
| What could invalidate this recommendation? | **Absent.** No invalidation-condition logic exists. | **New: an `InvalidationConditionGenerator`** — a simple rule layer (e.g., "if RSI crosses above 70 with a confirmed MACD bearish cross, re-evaluate," or "if the next earnings release, in N days per 4.19, misses consensus by more than X%") stated explicitly on every recommendation, not left implicit. |
| What assumptions were made? | **Absent** for anything beyond raw indicator math. Becomes critical once the DCF (4.7) exists — every DCF assumption (growth rate, discount rate) must be shown, never hidden, per the mandate's own instruction. | Any new valuation model must ship with mandatory, always-visible assumption disclosure — a hard requirement, not a nice-to-have, for 4.7's DCF specifically. |
| What investment horizon? (Swing/Position/Long-term/Dividend/Recovery/Momentum) | **Partial.** `TimeHorizon` (SHORT_TERM/MEDIUM_TERM/LONG_TERM) exists; the watchlist engine's 9 categories (MOMENTUM, SWING, INVESTMENT, DIVIDEND, RECOVERY, etc. — prior audit 4.10) already map closely to the requested taxonomy. | Mostly exists — recommend formally aligning the recommendation-level `time_horizon` field with the watchlist taxonomy so every recommendation states its horizon-archetype explicitly, not just a coarse 3-value enum. |

**Design conclusion:** the two genuinely new pieces of infrastructure required — a comparative-explanation engine and an invalidation-condition generator — are both achievable **without any new data**, purely by adding new logic on top of scores the platform already computes. These should be built *before* any new data source integration, since they are the cheapest, highest-leverage fixes for the exact complaint that opened this document.

**Extension for the Investment Thesis Engine (Section 5.2):** the final review added five further required elements beyond the original 9 questions. Mapped the same way:

| Additional element | Exists today? | What's needed |
|---|---|---|
| Which catalysts are expected? | **Absent.** | New — 4.30 Catalyst Detection Engine; technical half buildable now, event half gated on earnings-calendar data (4.19). |
| Bull Case / Base Case / Bear Case | **Absent.** | New — 4.31 Scenario Engine; must be a deterministic re-parameterization of existing valuation math, never free-form LLM number generation. |
| Probability Distribution | **Absent.** | New — 4.32 Probability/Return-Distribution Engine; must ship as two explicitly labeled, never-conflated tiers (historical simulation vs. empirically-calibrated forecast). |
| Suitable Investor Profile | **Absent, and should stay absent in its literal form.** | New — 4.33 Investor Suitability Classifier; **flagged for legal/compliance review before implementation**, with an objective security-profile description recommended as the safer default in the meantime. |
| Supporting Evidence (as a formal, citable structure) | **Partial** — the data exists in `contributor_breakdown`, but not as an explicit claim-to-evidence citation list. | New — the `EvidenceCitationLayer` (Section 5.2); pure synthesis of numbers already computed. |

Together with the original 9, these complete the field set specified in Section 5.2's `InvestmentThesis` structure.

---

## 7. Institutional-Grade Backtesting & Validation Framework

**What already exists (real, verified via `src/backtesting/baselines.py`):** `BuyAndHoldStrategy`, `SMACrossoverStrategy`, `RSIOnlyStrategy`, `TechnicalOnlyStrategy`, `FundamentalOnlyStrategy`, `AIDecisionEngineStrategy` — 6 real, backtestable strategies, all implementing a shared `Strategy` protocol against an already anti-lookahead-safe `AsOfDataset`. This is a genuinely strong foundation; the requested comparison is an extension of a working pattern, not new architecture.

**What's requested but does not exist yet, and what it takes to add each:**

| Requested comparison | Status | What's needed |
|---|---|---|
| TASI (real index) | **Impossible today** — no TASI data ingested anywhere (Section 4.29). | Ingest TASI first; this blocks the comparison entirely, not just weakens it. |
| Buy and Hold | **Exists** (`BuyAndHoldStrategy`) | None |
| RSI | **Exists** (`RSIOnlyStrategy`) | None |
| MACD | **Absent** as a dedicated strategy | New `MACDOnlyStrategy` class, following the exact existing pattern — low effort |
| Moving Average | **Exists** (`SMACrossoverStrategy`) | None |
| SuperTrend | **Absent** as a dedicated strategy (the indicator itself exists, 4.1) | New `SuperTrendOnlyStrategy` — low effort |
| Bollinger Bands | **Absent** as a dedicated strategy (indicator exists) | New `BollingerBandsStrategy` — low effort |
| Momentum | **Partial** — `MomentumScoreContributor` exists but has no standalone baseline-strategy wrapper | New `MomentumOnlyStrategy` — low effort |
| Value Investing | **Absent** | New `ValueOnlyStrategy` using existing P/E, P/B, dividend-yield ratios — low effort, but honesty requires disclosing this is a simplified proxy, not a rigorous academic value factor, unless/until 4.7's real valuation work lands |
| Growth Investing | **Absent** | New `GrowthOnlyStrategy` using existing growth ratios — same caveat as above |
| Dividend Investing | **Absent** | New `DividendOnlyStrategy` — same caveat, and materially weakened until 4.3's dividend-data-quality fix lands |
| Relative Strength | **Impossible today** — the underlying signal itself doesn't exist yet (4.13) | Blocked on 4.13, which is itself blocked on sector/index data |
| Market Leaders | **Ambiguous requirement** — likely means "top-N by some strength/leadership metric" (MarketSmith-style); not currently defined anywhere in this codebase | Needs an explicit definition decision before it can be built — flagging rather than guessing, per the mandate's own instruction |

**Recommended validation-framework redesign:**
1. Extend `baselines.py` with the 6 missing strategy classes above (MACD, SuperTrend, Bollinger, Momentum, Value, Growth, Dividend) — each is a small, low-risk addition following an already-proven pattern.
2. Ingest TASI index data (4.29) — this is the single blocking dependency for the most important comparison requested.
3. Run every strategy, including the real `AIDecisionEngineStrategy`, through the existing `BacktestingEngine`'s walk-forward validation (already real, already anti-lookahead-safe) over the same historical window, and report the full existing metrics suite (win rate, Sharpe, Sortino, max drawdown, profit factor, calibration error) side-by-side.
4. **Do not claim superiority until this actually runs and the real numbers say so.** This section is a design, not a set of results — no backtest has been executed as part of this document, consistent with "prove it, don't claim it."

**Priority:** Critical. **Effort:** Medium for the 6 new strategy classes; the TASI ingestion dependency (4.29) is the pacing item.

---

## 8. Deep-Dive Requirement Reconciliation: Missing Capabilities, Algorithms, Datasets

Consolidated, deduplicated from Sections 4–7 (not repeated in full — cross-referenced):

**Every required algorithm:** Piotroski F-Score, Beneish M-Score / accrual ratio (4.4); FCF/FCF-yield/FCF-margin (4.6); 2-stage DCF (4.7); multi-year CAGR + growth-consistency (4.8); DuPont decomposition (4.9); volatility-regime classifier (4.11); dividend payout-sustainability/streak analysis (4.3); market-wide correlation-cluster engine (4.16); comparative-explanation engine (Section 6); invalidation-condition generator (Section 6); 7 new backtesting strategy classes (Section 7); technical-catalyst projection (4.30); three-scenario deterministic valuation re-run (4.31); historical-return-simulation Monte Carlo (4.32, tier a).

**Every required dataset:** TASI/market-index history (4.29 — highest priority, unlocks the most downstream items); real cash flow statements (4.6, availability unconfirmed); real macroeconomic series (oil price, SAR rates) (4.17); earnings-calendar/corporate-actions feed (4.19, availability unconfirmed, also required for 4.30's event-catalyst half); sector taxonomy (carried from prior audit).

**Every requirement for the Investment Thesis Engine specifically (Section 5.2):** the `InvestmentThesis` structure itself (new, Section 5.2); the `EvidenceCitationLayer` (new, pure synthesis of existing numbers); the compliance/legal review gate on 4.33 before any suitability-classification code is written — this is a decision dependency, not an engineering one, and should not be silently bypassed by reframing the feature under a different name.

**Every required AI improvement:** turn on the existing self-improvement schedulers (prior audit, unchanged top recommendation); build the eventual learned-model challenger only after the deterministic system is defensible per Section 3 (prior audit's Phase E, now explicitly sequenced *after* explainability work, not before).

**Every required quant improvement:** real statistical weight calibration (prior audit, unscheduled today); real portfolio optimizer (prior audit 4.12); real beta/VaR/CVaR (4.26, blocked on 4.29).

**Every required financial improvement:** cash flow analysis (4.6), earnings quality (4.4), DCF valuation (4.7) — the three most consequential, all financial-statement-analysis-grade capabilities a serious research desk would consider baseline, currently absent.

**Every required architecture improvement:** distinguish Overall Score from AI Composite Score explicitly (Section 5); promote all real contributors to first-class, queryable columns (Section 6); reconcile the dual technical-indicator implementations (4.1).

**Every required validation/benchmark/backtesting module:** Section 7 in full.

**Every required explainability module:** comparative-explanation engine and invalidation-condition generator, both detailed in Section 6 — the two highest-leverage, lowest-data-cost fixes in this entire document.

**Every required confidence model:** the existing Platt/isotonic design (prior audit 4.9), honestly relabeled until validated, then genuinely calibrated once the scheduler runs.

**Every required decision layer change:** Section 5 in full — 15 explicit, individually-traceable sub-scores replacing the current single opaque blend, with `NOT AVAILABLE` as a first-class, honest state for any score whose inputs don't exist yet.

---

## 9. Competitor Analysis

| Platform | What they do better than Basirah today | What Basirah can do better (once this plan executes) |
|---|---|---|
| **TradingView** | Massive charting breadth, huge community-driven indicator library, real-time multi-asset coverage | Deeper, Saudi-market-specific fundamental+AI integration; explicit invalidation conditions (TradingView alerts are user-configured, not AI-derived) |
| **TrendSpider** | Automated pattern/divergence detection (exactly the gap flagged in 4.1), multi-timeframe automation | Basirah's planned comparative-explanation and invalidation-condition layers (Section 6) go further than TrendSpider's pattern-alerting toward a genuine investment thesis, not just a technical trigger |
| **MarketSmith** | Purpose-built relative-strength (RS) ranking (IBD methodology) — exactly what 4.13 needs to build | Once built, Basirah's RS can be fused with real fundamental quality (4.4) and AI-blended confidence in one place, which MarketSmith's technical-first design doesn't attempt |
| **Trading Central** | Mature, long-established technical-signal-as-a-service business, broad multi-market coverage | Basirah's integrated portfolio-construction-to-recommendation pipeline (once 4.25's real optimizer lands) is a genuinely different, more complete product shape |
| **Finviz** | Extremely fast, broad-market screening across many fundamental/technical fields at once | Finviz has no AI reasoning or explainability layer at all — this is Basirah's core differentiation opportunity if Sections 5-6 are executed well |
| **Koyfin** | Broad, institutional-style data terminal experience at accessible pricing, strong macro dashboards | Basirah's Saudi-market specialization and (once built) AI-driven comparative explainability are not Koyfin's focus |
| **AlphaSense** | Best-in-class document/transcript search and NLP over qualitative research (earnings calls, filings) | Basirah's News Intelligence (4.18) is a real but much narrower analog; genuinely closing this gap would require transcript/filing ingestion, not in current scope |
| **Bloomberg (conceptually)** | Comprehensive real-time data across every asset class, unmatched breadth, deep institutional trust | Basirah cannot and should not try to match Bloomberg's breadth; the honest competitive angle is depth-of-explainability and Saudi-market focus, not breadth |
| **Refinitiv Workspace** | Deep, standardized financial-statement datasets (including cash flow — exactly 4.6's current gap) at institutional depth | Same as Bloomberg — compete on explainability depth and market focus, not data breadth |
| **Capital IQ** | Best-in-class fundamental screening across a huge universe with deep historical financials | Basirah's AI-composite reasoning is not something Capital IQ offers as a first-class feature — a real opportunity once Section 5 exists for real |
| **Morningstar** | Mature, trusted quality/moat scoring methodology (economic moat ratings) — conceptually adjacent to 4.4's quality-score gap | Basirah's real-time AI recommendation blending (once defensible per this document) is more dynamic than Morningstar's slower-moving analyst-driven ratings |
| **Institutional Quant Platforms** (Two Sigma/Renaissance/Citadel/Jane Street-style internal tooling) | Vastly larger data, compute, and research staff; genuine ML with rigorous statistical validation, live for years | Not a realistic near-term comparison target on raw capability — the honest, achievable goal is to adopt their *discipline* (statistical validation before trust, explicit uncertainty, regime-awareness) at Basirah's actual scale, which this document's Sections 5-7 are built to do |

**Honest positioning:** Basirah's realistic, defensible competitive edge is not breadth (it will never out-data Bloomberg) and not raw quant sophistication (it will never out-compute Renaissance). It is the combination of **Saudi-market specialization + genuinely defensible, comparative, uncertainty-honest explainability + an integrated recommendation-to-portfolio pipeline** — a combination none of the platforms above fully offer together. That combination is achievable with the work in this document; claiming parity with Bloomberg's data breadth or Renaissance's statistical firepower would not be honest and is explicitly not the target.

---

## 10. New Roadmap — Ordered Strictly by Impact on Intelligence Quality

Not calendar-paced. Ordered by which fix unlocks the most other findings, per this document's own dependency chains.

**Tier 1 — Unlocks everything else, buildable now, mostly no new data required:**
1. Comparative-explanation engine + invalidation-condition generator (Section 6) — directly answers the concern that opened this document, zero new data needed.
2. The `InvestmentThesis` structure and `EvidenceCitationLayer` (Section 5.2) — the organizing skeleton every other thesis element attaches to; buildable now purely as synthesis of scores that already exist.
3. Scenario Engine (4.31) and the technical half of the Catalyst Detection Engine (4.30) — both deterministic re-parameterizations of existing math, no new data, and the non-negotiable numeric-grounding discipline must be built in from the start, not retrofitted.
4. Probability/Return-Distribution Engine, tier (a) only — historical-simulation Monte Carlo (4.32) — buildable now from existing OHLCV history, always labeled `"historical_simulation"`, never presented as a validated forecast.
5. Market-index (TASI) data ingestion (4.29) — the single highest-leverage data fix, unlocking real beta, real relative strength, real backtesting comparisons, and real "beats the market" claims, none of which are possible without it.
6. Turn on the existing self-improvement schedulers + honestly relabel confidence until it's genuinely validated (4.23, prior audit) — near-zero cost, starts the clock every later statistical claim depends on, including 4.32's tier (b).
7. Route 4.33 (Investor Suitability Classifier) to legal/compliance review immediately, in parallel with all engineering work above — do not schedule any implementation of the literal feature until that review concludes; ship the objective security-profile alternative in the meantime.

**Tier 2 — Data-sourcing diagnostics (must happen before committing engineering estimates):**
8. Confirm SAHMK cash-flow-statement availability (4.6) — blocks earnings quality (4.4) and real FCF valuation (4.7) entirely if unavailable.
9. Confirm SAHMK (or supplementary) earnings-calendar availability (4.19) — also unlocks 4.30's event-catalyst half.
10. Confirm sector-taxonomy fix path (prior audit) — unlocks relative strength (4.13), sector strength (4.14), and peer-relative valuation (4.7).

**Tier 3 — Real financial-analysis capability build-out (the "Buffett/Lynch/Goldman" layer):**
11. Earnings-quality engine (4.4) and FCF-based ratios (4.6), once data-confirmed.
12. Transparent-assumption DCF (4.7) — feeds directly into Tier 1's Scenario Engine (4.31) once it lands, sharpening the bull/base/bear price targets.
13. Multi-year CAGR/growth-consistency (4.8) and DuPont decomposition (4.9) — both buildable from data already ingested, no new sourcing needed, so these can proceed in parallel with Tier 2's diagnostics.
14. Dividend-safety/payout-sustainability scoring (4.3).

**Tier 4 — The "Two Sigma/Renaissance/Dalio" quant-risk layer (depends on Tier 1's index data):**
15. Real beta/VaR/CVaR (4.26).
16. Volatility-regime classifier and confidence-dampening (4.11).
17. Market-wide correlation-cluster engine (4.16) — notably can start immediately, in parallel with everything above, since it needs no new data.
18. Relative strength and sector strength go live once their data prerequisites (Tier 1 item 5's TASI ingestion + Tier 2 item 10's sector fix) land (4.13, 4.14).

**Tier 5 — Validation, proof, and the eventual learned model:**
19. Extend `baselines.py` with the 6-7 missing strategy classes (Section 7).
20. Run the full institutional-grade backtesting comparison for real, report real numbers, publish honestly — including if Basirah's own AI decision engine does *not* beat a simple baseline on some metric.
21. Turn on tier (b) of the Probability/Return-Distribution Engine (4.32) once enough real accumulated outcomes exist to validate it — this is calendar-gated, not effort-gated, per Tier 1 item 6's scheduler activation.
22. Only after all of the above: prototype a learned model (prior audit's Phase E) as a paper-trading challenger, evaluated by the now-real backtesting framework and the now-real statistical significance testing — never presented as production truth until it earns that status the same way any of the deterministic improvements above must.

**What this roadmap deliberately does not include:** any UI/UX work, any new feature unrelated to recommendation defensibility, and no work on the dead multi-agent code (`autonomous_intelligence_layer`) or scale/HA infrastructure (prior audit Phase G) — both remain correctly deferred, since neither moves the needle on whether a recommendation can be trusted, which is this document's entire mandate.

---

## 11. Final Recommendation

The platform's current failure mode is not "the technology is bad" — the retry logic, the circuit breaker, the test discipline, the numeric-grounding LLM safety pattern are all genuinely good engineering. The failure mode is **presenting a fixed-weight formula's output with more certainty than the formula itself has earned.** Symbol 1020 is not wrong to have scored well by the current formula's own math — the formula itself has never been proven right, has no comparative reasoning, has no market benchmark to be measured against, and cannot say what would prove it wrong. That is the actual, single, unifying problem this document has traced through 33 subsystems, and it is the problem Section 5's redesigned scoring, Section 6's explainability layer, and Section 7's real backtesting are built specifically to solve — in that order, because explainability and proof must come before any claim of intelligence, not after.

**Final answer to the question this review asked: yes, the Investment Thesis Engine (Section 5.2) should become Basirah's core.** Not as a rebrand of the existing scoring output, and not as a decorative narrative layer wrapped around a black-box number — as a genuine restructuring where the score becomes cited evidence inside a falsifiable case, with three of its four required new components (Catalyst Detection's technical half, the Scenario Engine, and the Probability Engine's historical-simulation tier) buildable immediately with no new data, and the fourth (Investor Suitability) correctly held for a compliance decision rather than quietly built around. This is the same discipline the rest of this document has applied throughout — build what's real, label what's uncertain, and never let a more persuasive-sounding output substitute for a more defensible one. A thesis-shaped narrative is a strictly higher bar to meet honestly than a scored recommendation was, not a lower one, and every design choice in Section 5.2 was made to hold that bar, not to make the platform merely sound more sophisticated.

This document recommends proceeding with Tiers 1 through 5 as ordered above (now 22 items, reflecting the added thesis-engine work), pending approval, with no implementation started until that approval is given.
