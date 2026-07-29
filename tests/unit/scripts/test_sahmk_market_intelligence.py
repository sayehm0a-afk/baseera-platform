"""Unit tests for scripts/verify_sahmk_market_intelligence.py's pure
serialization/aggregation helpers. Local only, no network, no
database -- the one real, unmocked full-universe run lives in the
script itself, dispatched only via GitHub Actions manual dispatch.
"""

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from scripts.verify_sahmk_market_intelligence import (  # noqa: E402
    _json_default,
    _outcome_to_dict,
    _ranking_lists_to_dict,
    _sector_breakdown,
    _watchlists_to_dict,
)
from src.analysis.analyst.types import AnalystReport, Explanation  # noqa: E402
from src.analysis.decision.types import (  # noqa: E402
    EntryQuality,
    InvestmentDecision,
    PositionSize,
    RiskLevel,
    TimeHorizon,
)
from src.analysis.recommendation.types import Recommendation  # noqa: E402
from src.market_intelligence.types import (  # noqa: E402
    RankingCategory,
    RankingEntry,
    RankingList,
    SymbolScanOutcome,
    WatchlistCategory,
    WatchlistEntry,
    WatchlistResult,
)


def _decision(**overrides):
    defaults = dict(
        symbol="2222", recommendation=Recommendation.BUY, confidence=70.0, final_score=65.0,
        target_price=30.0, stop_loss=25.0, time_horizon=TimeHorizon.SHORT_TERM,
        expected_return_pct=5.0, risk_level=RiskLevel.MEDIUM, position_size=PositionSize.STANDARD,
        reasons=["r1"], breakdown=[], signals=[], generated_at=datetime.now(timezone.utc),
        entry_quality=EntryQuality.GOOD, entry_quality_notes="n", risk_reward_ratio=2.0,
        stop_loss_basis="atr", target_price_basis="atr",
    )
    defaults.update(overrides)
    return InvestmentDecision(**defaults)


def _explanation(**overrides):
    defaults = dict(
        investment_summary="s", technical_reasoning="t", fundamental_reasoning="f",
        risk_explanation="r", bullish_factors=["b1"], bearish_factors=["b2"],
        confidence_explanation="c", target_price_explanation="tp", stop_loss_explanation="sl",
        time_horizon_explanation="th", alternative_scenarios=["alt"], final_recommendation_rationale="final",
    )
    defaults.update(overrides)
    return Explanation(**defaults)


class TestJsonDefault:
    def test_decimal_converted_to_float(self):
        assert _json_default(Decimal("1.5")) == 1.5

    def test_datetime_converted_to_isoformat(self):
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert _json_default(dt) == dt.isoformat()

    def test_enum_like_object_converted_to_value(self):
        assert _json_default(Recommendation.BUY) == "BUY"

    def test_nan_float_converted_to_none(self):
        assert _json_default(float("nan")) is None

    def test_unknown_type_falls_back_to_str(self):
        class Weird:
            def __str__(self):
                return "weird"

        assert _json_default(Weird()) == "weird"


class TestSectorBreakdown:
    def test_groups_by_sector_with_counts_and_symbols(self):
        companies = [
            {"symbol": "2222", "sector": "Energy"},
            {"symbol": "1120", "sector": "Financials"},
            {"symbol": "2010", "sector": "Energy"},
        ]
        result = _sector_breakdown(companies)
        assert result["Energy"] == {"count": 2, "symbols": ["2010", "2222"]}
        assert result["Financials"] == {"count": 1, "symbols": ["1120"]}

    def test_missing_sector_grouped_as_unknown(self):
        result = _sector_breakdown([{"symbol": "X", "sector": None}])
        assert result["UNKNOWN"] == {"count": 1, "symbols": ["X"]}


class TestOutcomeToDict:
    def test_successful_outcome_carries_full_decision_and_explanation(self):
        decision = _decision()
        explanation = _explanation()
        report = AnalystReport(
            symbol="2222", decision=decision, explanation=explanation,
            generated_at=datetime.now(timezone.utc), engine_version="1.0.0",
        )
        outcome = SymbolScanOutcome(
            symbol="2222", sector="Energy", success=True, report=report,
            latest_price=26.0, technical_snapshot={"rsi_14": 55.0},
            fundamental_snapshot={"return_on_equity": 0.1},
        )
        stock_meta = {"name_en": "Saudi Aramco", "name_ar": "أرامكو", "industry": "Oil", "exchange": "Tadawul"}
        snapshot_row = {"db_id": 1, "evaluated_at": "2026-01-01T00:00:00+00:00"}

        entry = _outcome_to_dict(outcome, snapshot_row, stock_meta)

        assert entry["symbol"] == "2222"
        assert entry["recommendation"] == "BUY"
        assert entry["technical_reasoning"] == "t"
        assert entry["fundamental_reasoning"] == "f"
        assert entry["technical_snapshot"] == {"rsi_14": 55.0}
        assert entry["fundamental_snapshot"] == {"return_on_equity": 0.1}
        assert entry["name_en"] == "Saudi Aramco"
        assert entry["db_id"] == 1
        assert entry["entry_quality"] == "GOOD"
        assert entry["risk_reward_ratio"] == 2.0

    def test_failed_outcome_has_no_decision_fields(self):
        outcome = SymbolScanOutcome(
            symbol="9999", sector=None, success=False, report=None,
            error="insufficient data", skipped_reason="no price history",
        )
        entry = _outcome_to_dict(outcome, None, None)
        assert entry["success"] is False
        assert entry["error"] == "insufficient data"
        assert "recommendation" not in entry


class TestRankingAndWatchlistDicts:
    def test_ranking_lists_to_dict(self):
        entry = RankingEntry(
            symbol="2222", sector="Energy", recommendation="BUY", confidence=70.0,
            final_score=65.0, target_price=30.0, expected_return_pct=5.0,
            risk_level="MEDIUM", rank_value=65.0,
        )
        rankings = {
            RankingCategory.TOP_BUY: RankingList(
                category=RankingCategory.TOP_BUY, entries=[entry], generated_at=datetime.now(timezone.utc)
            )
        }
        result = _ranking_lists_to_dict(rankings)
        assert result["TOP_BUY"] == [
            {
                "symbol": "2222", "sector": "Energy", "recommendation": "BUY", "confidence": 70.0,
                "final_score": 65.0, "target_price": 30.0, "expected_return_pct": 5.0,
                "risk_level": "MEDIUM", "rank_value": 65.0,
            }
        ]

    def test_watchlists_to_dict(self):
        entry = WatchlistEntry(symbol="2222", sector="Energy", recommendation="BUY", confidence=70.0, reason="x")
        watchlists = {
            WatchlistCategory.MOMENTUM: WatchlistResult(
                category=WatchlistCategory.MOMENTUM, entries=[entry], generated_at=datetime.now(timezone.utc)
            )
        }
        result = _watchlists_to_dict(watchlists)
        assert result["MOMENTUM"] == [
            {"symbol": "2222", "sector": "Energy", "recommendation": "BUY", "confidence": 70.0, "reason": "x"}
        ]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
