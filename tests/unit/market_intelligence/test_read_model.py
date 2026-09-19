"""Unit tests for read_model.outcome_from_record and
read_model.decision_v2_snapshots_by_symbol."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db.database import Base
from src.domain.models import DecisionV2Snapshot, RecommendationLabel, SymbolIntelligenceRecord
from src.market_intelligence.read_model import decision_v2_snapshots_by_symbol, outcome_from_record


def _record(**overrides):
    defaults = dict(
        scan_run_id=1, stock_id=1, symbol="2222", sector="Energy",
        recommendation=RecommendationLabel.BUY, confidence=Decimal("70.0"), final_score=Decimal("65.0"),
        target_price=Decimal("105.0"), stop_loss=Decimal("97.0"), expected_return_pct=Decimal("5.0"),
        risk_level="MEDIUM", time_horizon="MEDIUM_TERM", position_size="STANDARD",
        technical_score=Decimal("60.0"), fundamental_score=Decimal("55.0"), dividend_yield=Decimal("0.04"),
        rsi=Decimal("55.0"), adx=Decimal("28.0"), latest_price=Decimal("100.0"), bollinger_upper=Decimal("102.0"),
        bullish_factors=["Bullish."], bearish_factors=["Bearish."],
        evaluated_at=datetime.now(timezone.utc), engine_version="1.0.0",
    )
    defaults.update(overrides)
    return SymbolIntelligenceRecord(**defaults)


def test_reconstructs_decision_level_fields_faithfully():
    outcome = outcome_from_record(_record())
    assert outcome.symbol == "2222"
    assert outcome.sector == "Energy"
    assert outcome.success is True
    assert outcome.recommendation.value == "BUY"
    assert outcome.confidence == 70.0
    assert outcome.final_score == 65.0
    assert outcome.target_price == 105.0
    assert outcome.expected_return_pct == 5.0
    assert outcome.risk_level.value == "MEDIUM"


def test_reconstructs_technical_and_fundamental_scores_via_breakdown():
    outcome = outcome_from_record(_record())
    assert outcome.technical_score == 60.0
    assert outcome.fundamental_score == 55.0


def test_reconstructs_indicator_and_yield_fields():
    outcome = outcome_from_record(_record())
    assert outcome.rsi == 55.0
    assert outcome.adx == 28.0
    assert outcome.bollinger_upper == 102.0
    assert outcome.dividend_yield == 0.04
    assert outcome.latest_price == 100.0


def test_reconstructs_bullish_and_bearish_factors():
    outcome = outcome_from_record(_record())
    assert outcome.report.explanation.bullish_factors == ["Bullish."]
    assert outcome.report.explanation.bearish_factors == ["Bearish."]


def test_handles_missing_optional_fields_gracefully():
    outcome = outcome_from_record(
        _record(technical_score=None, fundamental_score=None, rsi=None, adx=None, bollinger_upper=None, dividend_yield=None)
    )
    assert outcome.technical_score is None
    assert outcome.fundamental_score is None
    assert outcome.rsi is None
    assert outcome.dividend_yield is None
    assert outcome.technical_snapshot is None


# --- decision_v2_snapshots_by_symbol ----------------------------------------


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def _snapshot(**overrides):
    defaults = dict(
        stock_id=1, symbol="2222", company_name_en="Stock 2222",
        decision="BUY_CANDIDATE", decision_label_ar="مرشح شراء",
        confidence_score=Decimal("80.0"), opportunity_quality_score=Decimal("75.0"),
        risk_score=Decimal("20.0"), data_quality_score=Decimal("90.0"),
        data_freshness_status="FRESH", market_status="OPEN",
        decision_timestamp=datetime.now(timezone.utc), analysis_version="2.0.0",
        data_source="DEV_SYNTHETIC", scan_run_id=1,
    )
    defaults.update(overrides)
    return DecisionV2Snapshot(**defaults)


def test_decision_v2_snapshots_by_symbol_returns_empty_dict_for_no_symbols(session):
    assert decision_v2_snapshots_by_symbol(session, 1, []) == {}


def test_decision_v2_snapshots_by_symbol_keys_by_symbol_for_the_matching_run(session):
    session.add(_snapshot(symbol="2222", scan_run_id=1))
    session.add(_snapshot(symbol="1010", scan_run_id=1, stock_id=2))
    session.commit()

    result = decision_v2_snapshots_by_symbol(session, 1, ["2222", "1010"])

    assert set(result.keys()) == {"2222", "1010"}
    assert result["2222"].decision == "BUY_CANDIDATE"
    assert result["2222"].decision_label_ar == "مرشح شراء"


def test_decision_v2_snapshots_by_symbol_excludes_a_different_scan_run(session):
    session.add(_snapshot(symbol="2222", scan_run_id=1, decision="BUY_CANDIDATE"))
    session.add(_snapshot(symbol="2222", scan_run_id=2, decision="WATCH"))
    session.commit()

    result = decision_v2_snapshots_by_symbol(session, 1, ["2222"])

    assert result["2222"].decision == "BUY_CANDIDATE"


def test_decision_v2_snapshots_by_symbol_omits_a_symbol_with_no_snapshot(session):
    """Honest-absence contract: a symbol never scored by Decision Engine
    V2 for this run is simply absent, never a fabricated entry."""
    session.add(_snapshot(symbol="2222", scan_run_id=1))
    session.commit()

    result = decision_v2_snapshots_by_symbol(session, 1, ["2222", "9999"])

    assert "9999" not in result
    assert "2222" in result


def test_decision_v2_snapshots_by_symbol_picks_the_latest_row_per_symbol(session):
    """`decision_v2_snapshots` is insert-only with no unique constraint
    on (scan_run_id, symbol) -- the windowed-latest-per-key read must
    pick the most recent decision_timestamp, not an arbitrary row."""
    older = datetime(2026, 1, 1, tzinfo=timezone.utc)
    newer = datetime(2026, 1, 2, tzinfo=timezone.utc)
    session.add(_snapshot(symbol="2222", scan_run_id=1, decision="WATCH", decision_timestamp=older))
    session.add(_snapshot(symbol="2222", scan_run_id=1, decision="BUY_CANDIDATE", decision_timestamp=newer))
    session.commit()

    result = decision_v2_snapshots_by_symbol(session, 1, ["2222"])

    assert result["2222"].decision == "BUY_CANDIDATE"
