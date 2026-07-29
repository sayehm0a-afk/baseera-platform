# AI Decision Engine Report — Basirah Phase 9

## Architecture (code-verified, unchanged by this run)

`src/analysis/decision/ai_decision_engine.py` is **explicitly not an LLM/generative-AI engine**. Its own docstring states: "this engine makes no LLM call (it is a deterministic, weighted-contributor scoring engine; 'AI' in its name refers to automated decision-making, not a generative model)."

`RecommendationEngine.generate()` blends 11 `ScoreContributor`s with fixed weights summing to 1.0:

| Contributor | Weight | Real or disclosed no-op |
|---|---|---|
| Technical | 0.22 | Real |
| Fundamental | 0.22 | Real |
| Momentum | 0.13 | Real |
| Volume | 0.09 | Real |
| Risk | 0.10 | Real |
| Price Structure | 0.08 | Real |
| Value Area | 0.05 | Real |
| News Sentiment | 0.04 | Real — the one contributor backed by external data (`src.news_intelligence`); not exercised meaningfully in this scan since no news ingestion ran alongside it |
| Macro | 0.04 | Disclosed no-op |
| Insider Transactions | 0.02 | Disclosed no-op |
| Sector Rotation | 0.01 | Disclosed no-op (compounded by 0% sector data this run — see `SECTOR_ANALYSIS_REPORT.md`) |

Only 5 of these 11 have dedicated `RecommendationSnapshot` columns (technical_score, fundamental_score, momentum_score, volume_score, risk_score); the other 6 live only in the `contributor_breakdown` JSON blob, which is part of the market_intelligence_data.json artifact this run produced but which was not independently retrievable (Azure Blob Storage artifact download is blocked in this validation environment — see `MARKET_PERFORMANCE_REPORT.md`).

## What this run confirms in practice

- The engine ran end-to-end for 95 real symbols against real technical and (mostly) real fundamental inputs, producing a real `Recommendation` (BUY/HOLD/SELL), `confidence` (0-100), `final_score`, `target_price`, `stop_loss`, `time_horizon`, `risk_level`, and `expected_return_pct` for every one — no exceptions, no fallback-to-default recommendations.
- Graceful degradation for missing fundamentals was confirmed live: symbol 1113 (fundamentals ingestion failed) still received a full recommendation, driven by the remaining contributors.
- 3 of the 11 contributors (Macro, Insider, Sector Rotation — 7% of total decision weight) are confirmed no-ops in production as designed, not a regression introduced by this run.
- Confidence values observed ranged from 57.3 to 86.2 across the 95 companies — no company received a confidence outside a fairly narrow band, and no company crossed whatever threshold the ranking engine uses to escalate BUY to STRONG_BUY or SELL to STRONG_SELL (0 STRONG_BUY, 0 STRONG_SELL occurred this run — see `AI_RECOMMENDATIONS_REPORT.md`).

## Not evaluated by this report

Accuracy/calibration of these recommendations against real subsequent market outcomes is out of scope for a single same-day scan — that is the purpose of the separate, already-built `OutcomeEvaluationScheduler`/`recommendation_outcomes` tracking (see `docs/current-status.md` for that subsystem's status), which requires calendar time to accumulate real outcome samples and was not exercised by this run.
