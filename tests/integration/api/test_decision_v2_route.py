"""Integration tests for GET /api/v1/stocks/{symbol}/decision-v2 --
real FastAPI routing, real dependency injection, the real
TechnicalAnalysisEngine/RecommendationEngine/AIDecisionEngine/
DecisionEngineV2 pipeline, against an in-memory SQLite DB and Dev*
providers (see conftest.py). No live network call anywhere.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

import numpy as np
import pytest

from src.analysis.decision_v2.types import DataFreshnessStatus, Decision, DecisionResult, GateOutcome, SubScores
from src.analysis.recommendation.types import Recommendation
from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.domain.models import (
    DecisionV2Snapshot, FundamentalSnapshot, MarketScanStatus, PeriodType, PriceBar, Stock, Timeframe,
)
from src.market_data.providers.market_data_provider import IMarketDataProvider, ProviderHealth
from src.market_intelligence.market_status import MarketSessionStatus, MarketStatusInfo
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository
from tests.unit.market_intelligence._fixtures import make_decision, make_outcome


@pytest.fixture(autouse=True)
def _staff_auth(authenticated_as_staff):
    """Every /api/v1/stocks/* route requires require_active_subscription()
    (Phase 13 P13.5) -- see conftest.py's authenticated_as_staff."""


class _AlwaysDownProvider(IMarketDataProvider):
    async def authenticate(self):
        return False

    async def get_stock_data(self, symbol):
        raise CircuitBreakerOpenError()

    async def get_historical_ohlcv(self, symbol, start, end, interval="1d"):
        raise CircuitBreakerOpenError()

    async def get_index_data(self, index_name):
        raise NotImplementedError

    async def get_market_news(self, limit=10):
        raise NotImplementedError

    async def health_check(self):
        return ProviderHealth.UNHEALTHY

    async def disconnect(self):
        pass


def _make_stock(session: Session, symbol: str = "2222") -> Stock:
    stock = Stock(symbol=symbol, name_en="Saudi Aramco", name_ar="أرامكو السعودية", sector="Energy")
    session.add(stock)
    session.commit()
    return stock


def _add_bars(session: Session, stock: Stock, count: int, uptrend: bool = True) -> None:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(count):
        step = Decimal("0.1") * i if uptrend else Decimal("0.0")
        session.add(
            PriceBar(
                stock_id=stock.id,
                timeframe=Timeframe.ONE_DAY,
                timestamp=base + timedelta(days=i),
                open=Decimal("30.0") + step,
                high=Decimal("31.0") + step,
                low=Decimal("29.0") + step,
                close=Decimal("30.5") + step,
                volume=1000 + i,
            )
        )
    session.commit()


def _add_fundamentals(session: Session, stock: Stock, fiscal_year: int = 2025) -> None:
    session.add(
        FundamentalSnapshot(
            stock_id=stock.id,
            period_type=PeriodType.ANNUAL,
            fiscal_period_end=date(fiscal_year, 12, 31),
            revenue=Decimal("1000000"),
            net_income=Decimal("150000"),
            total_assets=Decimal("2000000"),
            total_liabilities=Decimal("700000"),
            total_equity=Decimal("1300000"),
            current_assets=Decimal("900000"),
            current_liabilities=Decimal("400000"),
            shares_outstanding=1_000_000,
            eps=Decimal("0.15"),
            dividend_per_share=Decimal("0.02"),
            source="dev-synthetic",
            is_synthetic=True,
        )
    )
    session.commit()


_VALID_DECISIONS = {
    "STRONG_BUY_CANDIDATE", "BUY_CANDIDATE", "WAIT_FOR_ENTRY", "WATCH",
    "HOLD", "REDUCE", "EXIT", "REJECT", "INSUFFICIENT_DATA",
}
_VALID_FRESHNESS = {"LIVE", "LAST_SESSION", "STALE", "UNKNOWN"}


def test_decision_v2_with_both_legs_available(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/decision-v2")
    assert response.status_code == 200
    body = response.json()

    assert body["symbol"] == "2222"
    assert body["company_name_ar"] == "أرامكو السعودية"
    assert body["company_name_en"] == "Saudi Aramco"
    assert body["sector_ar"] == "الطاقة"
    assert body["decision"] in _VALID_DECISIONS
    assert body["decision_label_ar"]
    assert 0.0 <= body["confidence_score"] <= 100.0
    assert body["confidence_disclaimer_ar"] == (
        "درجة الثقة تقيس قوة وتوافق الأدلة المتاحة، ولا تعني ضمان تحقق الهدف."
    )
    assert body["analysis_disclaimer_ar"].startswith("هذا تحليل آلي مساعد")
    assert 0.0 <= body["opportunity_quality_score"] <= 100.0
    assert 0.0 <= body["risk_score"] <= 100.0
    assert body["data_freshness_status"] in _VALID_FRESHNESS
    assert body["analysis_version"] == "2.0.0"
    assert body["data_source"]
    assert isinstance(body["sub_scores"], dict)
    assert isinstance(body["gates"], list) and len(body["gates"]) > 0
    for gate in body["gates"]:
        assert {"name", "passed", "detail", "blocking"} <= gate.keys()

    # A best-effort DecisionV2Snapshot row should have been inserted.
    # (The test fixture's staff user is an in-memory, never-persisted
    # User -- see authenticated_as_staff's own docstring -- so its id is
    # None and requested_by_user_id is correctly null here; a real
    # session would have a real id.)
    rows = db_session.query(DecisionV2Snapshot).filter(DecisionV2Snapshot.symbol == "2222").all()
    assert len(rows) == 1
    assert rows[0].decision == body["decision"]


def _make_numpy_laden_decision_v2_result(symbol: str) -> DecisionResult:
    """A real DecisionResult with every numeric field as numpy.float64
    and every gate bool as numpy.bool_ -- matches exactly what
    DecisionEngineV2.decide() actually returns in production (ATR/
    entry-zone computations run over numpy-backed indicator arrays).
    Used to prove this route's own DecisionV2Snapshot insert survives
    real Postgres, not just SQLite (which silently tolerates numpy)."""
    return DecisionResult(
        symbol=symbol, company_name_ar="أرامكو السعودية", company_name_en="Saudi Aramco", sector_ar="الطاقة",
        decision=Decision.BUY_CANDIDATE, decision_label_ar="شراء",
        confidence_score=np.float64(78.2), opportunity_quality_score=np.float64(65.0),
        risk_score=np.float64(40.0), data_quality_score=np.float64(100.0),
        data_freshness_status=DataFreshnessStatus.LIVE,
        current_price=np.float64(65.1), entry_zone_low=np.float64(64.79), entry_zone_high=np.float64(65.19),
        stop_loss=np.float64(62.95), target_1=np.float64(66.31), target_2=np.float64(67.0), target_3=np.float64(68.0),
        expected_return_target_1=np.float64(3.12), expected_return_target_2=np.float64(5.0),
        downside_to_stop=np.float64(1.6), risk_reward_target_1=np.float64(1.49), risk_reward_target_2=np.float64(2.0),
        expected_holding_period_min_days=1, expected_holding_period_max_days=15,
        expected_holding_period_label_ar="من جلسة إلى 3 أسابيع", horizon_type="SHORT_TERM",
        market_status="OPEN", decision_timestamp=datetime.now(timezone.utc),
        invalidation_conditions=[], positive_reasons=[], negative_reasons=[], warnings=[],
        recommendation_basis="test", analysis_version="2.0.0", data_source="SAHMK_REAL", scan_run_id=None,
        sub_scores=SubScores(
            trend_score=np.float64(50.0), momentum_score=np.float64(57.4), volume_score=np.float64(65.0),
            liquidity_score=np.float64(70.0), volatility_score=np.float64(30.0),
            risk_reward_score=np.float64(64.75), market_context_score=np.float64(75.0),
            data_quality_score=np.float64(100.0),
        ),
        gates=[GateOutcome(name="real_data_source", passed=np.bool_(True), detail="ok", blocking=np.bool_(True))],
    )


def test_decision_v2_persists_a_real_numpy_laden_result_without_crashing(client, db_session, monkeypatch):
    """Regression: production confirmed (2026-08-06) that this route's
    single-row DecisionV2Snapshot insert crashes against real Postgres
    with 'schema "np" does not exist' whenever DecisionEngineV2's real
    numpy-backed computation reaches it -- the exact same failure mode
    the scan-pipeline batch insert was fixed for (commit 8d8e4d0), which
    this single-row insert had not been. SQLite (this test's own DB)
    silently tolerates the un-coerced type, so this test instead spies
    on session.add() to check the object's attribute types at insert
    time (same technique as
    test_market_intelligence_repository.py::test_save_symbol_records_coerces_numpy_types_in_decision_v2_snapshot),
    which is what actually reaches the SQL layer."""
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    monkeypatch.setattr(
        "src.api.routes.stocks.DecisionEngineV2.decide",
        lambda self, *a, **kw: _make_numpy_laden_decision_v2_result("2222"),
    )

    numeric_fields = (
        "confidence_score", "opportunity_quality_score", "risk_score", "data_quality_score",
        "current_price", "entry_zone_low", "entry_zone_high", "stop_loss",
        "target_1", "target_2", "target_3",
        "expected_return_target_1", "expected_return_target_2", "downside_to_stop",
        "risk_reward_target_1", "risk_reward_target_2",
    )
    captured = []
    original_add = Session.add

    def _spy_add(self, obj):
        if type(obj).__name__ == "DecisionV2Snapshot":
            captured.append({f: type(getattr(obj, f)) for f in numeric_fields})
        return original_add(self, obj)

    # The route's session comes from the `get_db` dependency override,
    # which creates its own Session instance (see conftest.py's
    # `_override_get_db`) -- a different object than the `db_session`
    # fixture used to seed data here. Patching the class method (not
    # the `db_session` instance) intercepts the route's own session too.
    monkeypatch.setattr(Session, "add", _spy_add)

    response = client.get("/api/v1/stocks/2222/decision-v2")
    assert response.status_code == 200

    assert len(captured) == 1
    for field, field_type in captured[0].items():
        assert field_type is float, f"DecisionV2Snapshot.{field} was {field_type!r}, expected plain float"

    rows = db_session.query(DecisionV2Snapshot).filter(DecisionV2Snapshot.symbol == "2222").all()
    assert len(rows) == 1
    assert rows[0].decision == "BUY_CANDIDATE"


_VALID_ENTRY_STATUSES = {
    "READY_NOW", "NEAR_ENTRY", "WAIT_FOR_PULLBACK", "MISSED_ENTRY",
    "CONDITIONAL_ON_BREAKOUT", "NOT_SUITABLE",
}
_VALID_TRADE_TYPES = {
    "SCALP", "INTRADAY", "SHORT_SWING_2_5_DAYS", "WEEKLY_SWING", "SWING_TRADE",
    "MONTHLY_INVESTMENT", "MEDIUM_TERM_INVESTMENT", "LONG_TERM_INVESTMENT",
}


def test_decision_v2_response_includes_the_phase_2a_canonical_fields(client, db_session):
    """Phase 2A: the response must carry the full canonical stock-
    intelligence output (trade type, price plan, support/resistance,
    liquidity/accumulation, confidence breakdown, Arabic reasoning),
    not just the Phase 1 subset."""
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/decision-v2")
    assert response.status_code == 200
    body = response.json()

    assert isinstance(body["is_real_data"], bool)
    assert body["entry_status"] in _VALID_ENTRY_STATUSES
    assert body["entry_status_label_ar"]
    assert body["risk_level"] in {"LOW", "MEDIUM", "HIGH", "VERY_HIGH"}
    assert body["risk_level_label_ar"]
    assert body["entry_quality"] in {"POOR", "FAIR", "GOOD", "EXCELLENT"}
    assert body["entry_quality_label_ar"]
    if body["trade_type"] is not None:
        assert body["trade_type"] in _VALID_TRADE_TYPES
        assert body["trade_type"] not in ("SCALP", "INTRADAY")
    assert isinstance(body["technical_evidence"], dict)
    assert len(body["technical_evidence"]) > 0
    assert body["decision_summary_ar"]
    assert body["why_now_ar"]
    assert body["why_not_stronger_ar"]
    assert isinstance(body["entry_confirmation_conditions_ar"], list)
    assert isinstance(body["watch_next_session_ar"], list)
    assert body["accumulation_score"] == body["sub_scores"]["volume_score"]
    assert body["technical_confidence"] == body["sub_scores"]["trend_score"]


def test_decision_v2_never_shows_strong_buy_without_gates_passing(client, db_session):
    """A clearly-uptrending, fully-available-data symbol may legitimately
    reach STRONG_BUY_CANDIDATE/BUY_CANDIDATE -- but only via the real gate
    cascade, never bypassing it. This just asserts internal consistency:
    an actionable buy-side decision always carries a valid entry zone and
    stop below it, per gates.py's own invariants."""
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=90, uptrend=True)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/decision-v2")
    assert response.status_code == 200
    body = response.json()

    if body["decision"] in ("STRONG_BUY_CANDIDATE", "BUY_CANDIDATE"):
        assert body["entry_zone_low"] is not None and body["entry_zone_high"] is not None
        assert body["entry_zone_low"] <= body["entry_zone_high"]
        assert body["stop_loss"] is not None and body["stop_loss"] < body["entry_zone_low"]
        assert body["target_1"] is not None and body["target_1"] > body["entry_zone_high"]


def test_decision_v2_404_for_unknown_symbol(client, db_session):
    response = client.get("/api/v1/stocks/9999/decision-v2")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "stock_not_found"


def test_decision_v2_422_when_neither_leg_available(client, db_session):
    _make_stock(db_session)  # no bars, no fundamentals ingested

    response = client.get("/api/v1/stocks/2222/decision-v2")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "insufficient_data"


def test_decision_v2_degrades_when_provider_is_down_but_technical_data_exists(client, db_session):
    import main
    from src.api.dependencies import get_market_provider

    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)

    main.app.dependency_overrides[get_market_provider] = lambda: _AlwaysDownProvider()
    try:
        response = client.get("/api/v1/stocks/2222/decision-v2")
    finally:
        del main.app.dependency_overrides[get_market_provider]

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] in _VALID_DECISIONS


def test_decision_v2_response_never_exposes_credentials(client, db_session):
    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/decision-v2")
    body_text = response.text.lower()
    assert "sahmk_api_key" not in body_text
    assert "shmk_" not in body_text


# --- Phase 2I: end-to-end market-risk coverage (Phase 2C's fields were
# previously only unit-tested against a hand-built MarketBreadthSummary
# -- these seed a real MarketScanRun + SymbolIntelligenceRecord rows and
# hit the route itself). ------------------------------------------------


async def _seed_real_breadth(db_session: Session, *, buy_count: int, sell_count: int, confidence: float) -> None:
    """Seeds `buy_count` real BUY outcomes and `sell_count` real SELL
    outcomes into a completed MarketScanRun, via the same repository
    methods a real scan run uses -- not a hand-built MarketBreadthSummary."""
    repo = MarketIntelligenceRepository()
    total = buy_count + sell_count
    symbols = [f"90{i:02d}" for i in range(total)]
    for symbol in symbols:
        db_session.add(Stock(symbol=symbol, name_en=f"Stock {symbol}"))
    db_session.commit()

    run = repo.create_scan_run(db_session, symbols_requested=total)
    outcomes = [
        make_outcome(
            symbol=symbol,
            decision=make_decision(symbol=symbol, recommendation=Recommendation.BUY, confidence=confidence),
        )
        for symbol in symbols[:buy_count]
    ] + [
        make_outcome(
            symbol=symbol,
            decision=make_decision(symbol=symbol, recommendation=Recommendation.SELL, confidence=confidence),
        )
        for symbol in symbols[buy_count:]
    ]
    await repo.save_symbol_records(db_session, run.id, outcomes)
    repo.finish_run(
        db_session, run.id, MarketScanStatus.SUCCESS,
        symbols_succeeded=total, symbols_skipped=0, symbols_failed=0,
    )


def _open_market_status() -> MarketStatusInfo:
    """A fixed, always-OPEN MarketStatusInfo -- these tests assert on
    the LIVE breadth-classification path, which must not depend on
    whatever the real wall-clock happens to be when CI runs."""
    return MarketStatusInfo(
        status=MarketSessionStatus.OPEN,
        label_ar="السوق مفتوح",
        is_trading_day=True,
        server_time_riyadh=datetime(2026, 1, 4, 12, 0, tzinfo=timezone.utc),
        seconds_until_next_open=0.0,
        seconds_until_close=3600.0,
        last_completed_session_date=None,
    )


@pytest.mark.asyncio
async def test_decision_v2_includes_live_market_risk_fields_from_a_real_scan_run(client, db_session, monkeypatch):
    """Phase 2C E2E: market_risk_* fields must come from a real,
    persisted scan run read via get_market_breadth(), not just a
    hand-built MarketBreadthSummary (see test_market_risk.py)."""
    monkeypatch.setattr("src.api.routes.stocks.get_market_status", _open_market_status)
    await _seed_real_breadth(db_session, buy_count=18, sell_count=2, confidence=80.0)  # STRONG_ENTRY

    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/decision-v2")
    assert response.status_code == 200
    body = response.json()

    assert body["market_risk_state"] == "STRONG_ENTRY"
    assert body["market_risk_is_live"] is True
    assert body["market_risk_entry_permitted"] is True
    assert body["market_breadth_buy_count"] == 18
    assert body["market_breadth_sell_count"] == 2
    assert body["market_breadth_symbols_scanned"] == 20
    assert body["market_risk_basis_ar"]


@pytest.mark.asyncio
async def test_decision_v2_market_risk_reports_last_session_when_market_is_closed(client, db_session, monkeypatch):
    """Phase 2C E2E: when the market is closed, the real last completed
    session's breadth-derived classification must still surface, marked
    non-live -- never presented as a live read."""
    await _seed_real_breadth(db_session, buy_count=3, sell_count=17, confidence=80.0)  # DEFENSIVE_EXIT bias

    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    closed_status = MarketStatusInfo(
        status=MarketSessionStatus.WEEKEND,
        label_ar="عطلة أسبوعية",
        is_trading_day=False,
        server_time_riyadh=datetime(2026, 1, 3, 12, 0, tzinfo=timezone.utc),
        seconds_until_next_open=3600.0,
        seconds_until_close=None,
        last_completed_session_date=None,
    )
    monkeypatch.setattr("src.api.routes.stocks.get_market_status", lambda: closed_status)

    response = client.get("/api/v1/stocks/2222/decision-v2")
    assert response.status_code == 200
    body = response.json()

    assert body["market_risk_state"] == "MARKET_CLOSED"
    assert body["market_risk_is_live"] is False
    assert body["market_breadth_buy_count"] == 3
    assert body["market_breadth_sell_count"] == 17
    assert "الجلسة السابقة" in body["market_risk_basis_ar"]


def test_decision_v2_degrades_gracefully_when_breadth_read_raises(client, db_session, monkeypatch):
    """Phase 2C: a breadth-read failure (transient DB error, corrupted
    run row, etc.) must never turn into a 500 -- _latest_market_breadth
    swallows it and the route falls back to INSUFFICIENT_DATA."""
    import src.api.routes.stocks as stocks_module

    monkeypatch.setattr("src.api.routes.stocks.get_market_status", _open_market_status)

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated breadth-read failure")

    monkeypatch.setattr(stocks_module._market_repository, "get_latest_successful_run", _raise)

    stock = _make_stock(db_session)
    _add_bars(db_session, stock, count=60)
    _add_fundamentals(db_session, stock)

    response = client.get("/api/v1/stocks/2222/decision-v2")
    assert response.status_code == 200
    body = response.json()

    assert body["market_risk_state"] == "INSUFFICIENT_DATA"
    assert body["market_risk_entry_permitted"] is True
