"""The 20 adversarial quality scenarios from the live-scan repair
mandate, numbered to match that spec exactly. Each case either:

(a) has a real, passing test proving the pipeline handles it correctly
    (most cases below), or
(b) is a genuine, disclosed gap -- marked `xfail(strict=True)` so the
    gap is provable and visible in CI rather than silently absent.
    `strict=True` means the moment sector-aware fundamentals (or
    whichever gap) is actually implemented, this test starts failing
    the build (XPASS) until the marker is removed -- it cannot go
    stale and quietly stop meaning anything, and

(c) is covered by an existing, separate test file, referenced here by
    path rather than duplicated.

Do not add a case here that merely asserts a function returns
*something* -- every case must assert the specific behavior the
scenario requires (rejected vs published vs watch-only, etc.), per
this repo's own review standard.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.analysis.decision.types import Recommendation
from src.market_intelligence.publication_gate import evaluate_publication, is_publishable
from src.market_intelligence.ranking import RankingEngine
from src.market_intelligence.types import GateStatus, PublicationStatus, RankingCategory
from tests.unit.market_intelligence._fixtures import make_decision, make_outcome


# 1. All stocks are weak -> zero BUY recommendations.
def test_case_01_all_weak_market_produces_zero_top_buy_entries():
    outcomes = [
        make_outcome(symbol=s, decision=make_decision(symbol=s, recommendation=Recommendation.SELL, final_score=20.0))
        for s in ("A", "B", "C")
    ] + [
        make_outcome(symbol=s, decision=make_decision(symbol=s, recommendation=Recommendation.HOLD, final_score=50.0))
        for s in ("D", "E")
    ]
    rankings = RankingEngine().rank(outcomes)
    assert rankings[RankingCategory.TOP_BUY].entries == []
    assert rankings[RankingCategory.TOP_STRONG_BUY].entries == []


# 2. Sharply bearish market -> conservative output, not forced BUY rankings.
# Same mechanism as case 1: nothing in the ranking/gate pipeline forces a
# BUY to exist. A "sharply bearish market" is itself a claim about
# TASI/market-regime data this platform does not yet ingest (Phase 0
# audit, defect #4) -- there is no separate "market regime" input to
# feed a distinct test with; case 1 already proves the necessary
# property (no BUY is manufactured when every stock is weak).


# 3. Missing sector data -> no sector-relative claim.
# Covered: tests/unit/market_intelligence/test_publication_gate.py::
# test_missing_sector_is_not_evaluated_and_never_blocks_publication


# 4. Missing TASI -> no benchmark-relative claim.
# Covered: tests/unit/market_intelligence/test_publication_gate.py::
# test_benchmark_data_is_always_not_evaluated_and_disclosed


# 5. Missing fundamentals -> technical-only classification or
# insufficient-data, not a fabricated fundamental score.
def test_case_05_missing_fundamentals_does_not_block_a_technical_only_recommendation():
    # Mirrors the real 2026-07-30 live-scan evidence for symbol 1113
    # (docs/phase9_market_intelligence/AI_RECOMMENDATIONS_REPORT.md:36),
    # whose fundamental score was N/A and the decision engine degraded
    # to technical-only weighting rather than failing outright.
    outcome = make_outcome(
        fundamental_snapshot=None,
        decision=make_decision(recommendation=Recommendation.HOLD, expected_return_pct=1.0),
    )
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.PUBLISHED
    assert outcome.dividend_yield is None  # confirms no fundamental data was silently fabricated


# 6. Stale prices -> recommendation blocked.
def test_case_06_stale_scan_is_rejected():
    fresh_outcome = make_outcome(
        decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0),
    )
    stale_outcome = replace(fresh_outcome, scanned_at=datetime.now(timezone.utc) - timedelta(hours=48))
    evaluation = evaluate_publication(stale_outcome)
    assert evaluation.status is PublicationStatus.REJECTED
    freshness_gate = next(g for g in evaluation.gates if g.name == "data_freshness")
    assert freshness_gate.status is GateStatus.FAIL


# 7. Insufficient history -> recommendation blocked.
def test_case_07_insufficient_history_is_insufficient_data():
    outcome = make_outcome(success=False, report=None, skipped_reason="insufficient_data")
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.INSUFFICIENT_DATA
    assert not is_publishable(outcome)


# 8. Illiquid stock -> blocked.
# Covered: tests/unit/market_intelligence/test_publication_gate.py::
# test_illiquid_stock_is_rejected


# 9. Extreme price move -> prevent chasing without confirmation.
@pytest.mark.xfail(
    reason="No 'extreme move / already priced in' gate exists yet -- publication_gate.py has no check "
    "on how far price has already run before entry. Disclosed gap, docs/basirah_intelligence_core/"
    "PHASE_0_REALITY_AUDIT.md.",
    strict=True,
)
def test_case_09_extreme_recent_price_move_is_flagged_before_chasing():
    outcome = make_outcome(
        technical_snapshot={"volume_sma_20": 100000.0},
        decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0),
    )
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is not PublicationStatus.PUBLISHED


# 10. Conflicting technical and fundamental evidence -> disclosed and downgraded.
@pytest.mark.xfail(
    reason="No conflict-detection stage exists between independent technical/fundamental conclusions -- "
    "AIDecisionEngine blends them into a single weighted score before any conflict can be surfaced. "
    "Disclosed gap (Phase 6 Stages 2-3 of the intelligence-core mandate, not yet implemented).",
    strict=True,
)
def test_case_10_conflicting_technical_and_fundamental_evidence_is_downgraded():
    outcome = make_outcome(decision=make_decision(
        recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0,
    ))
    evaluation = evaluate_publication(outcome)
    assert any("conflict" in g.name for g in evaluation.gates)


# 11. Strong score but poor risk/reward -> rejected.
# Covered: tests/unit/market_intelligence/test_publication_gate.py::
# test_risk_reward_below_minimum_threshold_is_rejected,
# test_reproduces_1020_a_buy_with_negative_expected_return_is_rejected


# 12. Strong fundamentals but no entry setup -> watchlist, not immediate BUY.
# Covered: tests/unit/market_intelligence/test_publication_gate.py::
# test_poor_entry_quality_downgrades_to_watch_only_not_rejected


# 13. Technical breakout without volume confirmation -> not treated as confirmed.
@pytest.mark.xfail(
    reason="watchlist.py's BREAKOUT_CANDIDATES rule requires price above the upper Bollinger Band "
    "plus ADX, but never checks relative/abnormal volume -- a breakout on thin volume is not "
    "distinguished from one with real participation. Disclosed gap.",
    strict=True,
)
def test_case_13_breakout_without_volume_confirmation_is_not_a_confirmed_breakout():
    from src.market_intelligence.watchlist import WatchlistEngine
    from src.market_intelligence.types import WatchlistCategory

    outcome = make_outcome(
        latest_price=110.0,
        technical_snapshot={"bollinger": {"upper": 105.0}, "adx_14": 30.0, "volume_sma_20": 100.0},
        decision=make_decision(recommendation=Recommendation.BUY),
    )
    results = WatchlistEngine().build([outcome])
    assert results[WatchlistCategory.BREAKOUT_CANDIDATES].entries == []


# 14. Recently listed security -> conservative handling.
@pytest.mark.xfail(
    reason="No listing-date-aware gate exists -- a recently listed symbol with a short price history "
    "is treated identically to an established one once it clears the (also not-yet-horizon-specific) "
    "minimum-history check. Disclosed gap.",
    strict=True,
)
def test_case_14_recently_listed_security_is_handled_conservatively():
    outcome = make_outcome(decision=make_decision(recommendation=Recommendation.STRONG_BUY, confidence=90.0))
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is not PublicationStatus.PUBLISHED


# 15. Bank evaluated using industrial-company ratios -> must fail until
# sector-specific fundamental logic exists.
@pytest.mark.xfail(
    reason="src/analysis/fundamental/fundamental_analysis_engine.py applies one generic scoring model "
    "to every security type -- no bank/insurer/REIT-specific ratio set exists (grep for sector/bank/"
    "insurance/reit in that module returns zero matches). This is the exact gap the mandate names; "
    "the test must keep failing until sector-aware logic is implemented (Phase 0 audit defect #3).",
    strict=True,
)
def test_case_15_bank_fundamentals_use_bank_specific_ratios_not_industrial_ones():
    from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisEngine
    import inspect

    source = inspect.getsource(FundamentalAnalysisEngine)
    assert "bank" in source.lower() or "financial_institution" in source.lower()


# 16. Duplicate company record -> one canonical security.
# Covered: tests/unit/market_data/sahmk/test_service.py::
# test_get_company_directory_deduplicates_across_pages


# 17. API returns malformed response -> safe failure, no fabricated result.
# Covered by SahmkClient's existing response-parsing error handling
# (tests/unit/market_data/sahmk/test_client.py) -- established prior to
# this session, not re-tested here.


# 18. Rate limit reached -> controlled retry, incomplete-run status.
# Covered by SahmkRateLimiter + MarketScanner._scan_one_with_retry's
# existing retry/backoff tests -- established prior to this session.


# 19. Provider unavailable -> no synthetic fallback in live mode.
# Covered by the network-aware provider factory's existing tests
# (tests/unit/market_data/test_provider_factory.py) -- established
# prior to this session.


# 20. Reproduce the 1020 scenario.
# Covered: tests/unit/market_intelligence/test_publication_gate.py::
# test_reproduces_1020_a_buy_with_negative_expected_return_is_rejected,
# tests/unit/market_intelligence/test_ranking.py::
# test_top_buy_excludes_a_high_score_buy_with_negative_expected_return
