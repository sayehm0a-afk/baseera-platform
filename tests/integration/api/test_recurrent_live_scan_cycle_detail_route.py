"""Integration tests for GET /api/v1/admin/market-intelligence/
recurrent-live-scan/cycles/{cycle_id} -- the Day-1 Shadow observability
gap closure: per-symbol detail for one recurrent Shadow cycle, read
entirely from already-persisted DecisionV2Snapshot/ShadowLiveSignal
rows. Mirrors test_recurrent_live_scan_status_route.py's own fixture
pattern.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from src.api.dependencies import get_current_user, get_market_provider
from src.core.db import database
from src.core.db.database import Base, get_db
from src.domain.models import (
    DecisionV2Snapshot,
    RecurrentScanCycle,
    RecurrentScanCycleStatus,
    ShadowLifecycleResult,
    ShadowLiveSignal,
    StaffRole,
    Stock,
    User,
)
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider


@pytest.fixture
def session_factory(monkeypatch):
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "get_session_factory", lambda: factory)

    def _override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = _override_get_db
    main.app.dependency_overrides[get_market_provider] = lambda: DevMarketDataProvider()
    yield factory
    Base.metadata.drop_all(bind=engine)
    main.app.dependency_overrides.clear()


@pytest.fixture
def client(session_factory):
    yield TestClient(main.app)


@pytest.fixture
def as_staff():
    staff_user = User(email="staff@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.ADMIN)
    main.app.dependency_overrides[get_current_user] = lambda: staff_user
    yield staff_user


@pytest.fixture(autouse=True)
def _no_real_shared_redis(monkeypatch):
    import src.market_data.sahmk.rate_limiter as rate_limiter_module

    monkeypatch.setattr(rate_limiter_module, "_get_shared_redis_client", lambda: None)


def _stock(session, symbol):
    stock = Stock(symbol=symbol, name_en=symbol, is_active=True)
    session.add(stock)
    session.flush()
    return stock


def _snapshot(session, stock, scan_run_id, decision="BUY_CANDIDATE", confidence=70.0, quality=55.0):
    snapshot = DecisionV2Snapshot(
        stock_id=stock.id,
        symbol=stock.symbol,
        company_name_en=stock.name_en,
        decision=decision,
        decision_label_ar="x",
        confidence_score=confidence,
        opportunity_quality_score=quality,
        risk_score=30.0,
        data_quality_score=90.0,
        data_freshness_status="LIVE",
        current_price=100.0,
        entry_zone_low=98.0,
        entry_zone_high=101.0,
        stop_loss=95.0,
        target_1=105.0,
        target_2=110.0,
        target_3=115.0,
        market_status="OPEN",
        decision_timestamp=datetime.now(timezone.utc),
        analysis_version="2.0.0",
        data_source="sahmk",
        scan_run_id=scan_run_id,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def _cycle(session, cycle_id, scan_run_id=None, status=RecurrentScanCycleStatus.SUCCESS_NO_CHANGE, **kwargs):
    now = datetime.now(timezone.utc)
    kwargs.setdefault("triggered_at", now)
    kwargs.setdefault("finished_at", now)
    cycle = RecurrentScanCycle(
        cycle_id=cycle_id,
        status=status,
        scan_run_id=scan_run_id,
        **kwargs,
    )
    session.add(cycle)
    session.commit()
    return cycle


def _url(cycle_id):
    return f"/api/v1/admin/market-intelligence/recurrent-live-scan/cycles/{cycle_id}"


# --- auth --------------------------------------------------------------


def test_requires_authentication(client, session_factory):
    response = client.get(_url("nope"))
    assert response.status_code in (401, 403)


def test_no_public_unauthenticated_access_even_for_a_real_cycle(client, session_factory):
    session = session_factory()
    _cycle(session, "cyc-1")
    session.close()

    response = client.get(_url("cyc-1"))
    assert response.status_code in (401, 403)


def test_ordinary_consumer_user_is_denied(client, session_factory):
    consumer = User(email="consumer@example.com", password_hash="hashed", is_staff=False, staff_role=None)
    main.app.dependency_overrides[get_current_user] = lambda: consumer
    try:
        response = client.get(_url("nope"))
        assert response.status_code in (401, 403)
    finally:
        del main.app.dependency_overrides[get_current_user]


def test_support_staff_role_is_denied_not_in_the_allowed_set(client, session_factory):
    """require_any_staff_role is an exact-membership check
    (ANALYST/ADMIN/OWNER) -- SUPPORT is real staff but must still be
    denied, proving there is no role-ladder inheritance bypass."""
    support_user = User(
        email="support@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.SUPPORT,
    )
    main.app.dependency_overrides[get_current_user] = lambda: support_user
    try:
        response = client.get(_url("nope"))
        assert response.status_code in (401, 403)
    finally:
        del main.app.dependency_overrides[get_current_user]


@pytest.mark.parametrize("role", [StaffRole.ANALYST, StaffRole.ADMIN, StaffRole.OWNER])
def test_each_allowed_staff_role_can_read_a_real_cycle(client, session_factory, role):
    session = session_factory()
    _cycle(session, "cyc-role-check")
    session.close()

    role_user = User(email=f"{role.value.lower()}@example.com", password_hash="hashed", is_staff=True, staff_role=role)
    main.app.dependency_overrides[get_current_user] = lambda: role_user
    try:
        response = client.get(_url("cyc-role-check"))
        assert response.status_code == 200
    finally:
        del main.app.dependency_overrides[get_current_user]


def test_missing_cycle_id_path_segment_does_not_match_this_route(client, session_factory, as_staff):
    """No cycle_id at all (.../cycles or .../cycles/) must not silently
    resolve to some default/latest cycle -- it's simply not this
    route (FastAPI 404s on an unmatched path), never a 200 with
    unintended data."""
    response = client.get("/api/v1/admin/market-intelligence/recurrent-live-scan/cycles")
    assert response.status_code == 404
    response_trailing_slash = client.get("/api/v1/admin/market-intelligence/recurrent-live-scan/cycles/")
    assert response_trailing_slash.status_code == 404


# --- lookup --------------------------------------------------------------


def test_unknown_cycle_returns_404(client, session_factory, as_staff):
    response = client.get(_url("does-not-exist"))
    assert response.status_code == 404


def test_skipped_cycle_with_no_scan_run_returns_empty_symbols_not_404(client, session_factory, as_staff):
    session = session_factory()
    _cycle(
        session, "cyc-skipped", scan_run_id=None,
        status=RecurrentScanCycleStatus.SKIPPED_QUOTA, skip_reason="upstream_confirmed_exhausted",
    )
    session.close()

    response = client.get(_url("cyc-skipped"))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SKIPPED_QUOTA"
    assert body["skip_reason"] == "upstream_confirmed_exhausted"
    assert body["market_scan_run_id"] is None
    assert body["symbols"] == []


# --- per-symbol rows, unchanged case (Day-1's actual shape) -------------


def test_unchanged_symbols_have_no_shadow_signal_row_and_report_state_change_unchanged(
    client, session_factory, as_staff,
):
    session = session_factory()
    stock_a = _stock(session, "1010")
    stock_b = _stock(session, "2020")
    stock_c = _stock(session, "3030")
    _snapshot(session, stock_a, scan_run_id=132)
    _snapshot(session, stock_b, scan_run_id=132)
    _snapshot(session, stock_c, scan_run_id=132)
    session.commit()
    _cycle(
        session, "cyc-132", scan_run_id=132,
        symbols_selected_count=3, symbols_evaluated_count=3, signals_unchanged_count=3,
    )
    session.close()

    response = client.get(_url("cyc-132"))
    assert response.status_code == 200
    body = response.json()
    assert body["stage2_count"] == 3
    assert len(body["symbols"]) == 3
    symbols = {row["symbol"] for row in body["symbols"]}
    assert symbols == {"1010", "2020", "3030"}
    for row in body["symbols"]:
        assert row["state_change"] == "UNCHANGED"
        assert row["previous_decision"] is None
        assert row["selection_reason"] is None
        assert row["decision"] == "BUY_CANDIDATE"
        assert row["confidence_score"] == 70.0
        assert row["basirah_score"] == 55.0
        assert row["signal_price"] == 100.0
        assert row["entry_zone_low"] == 98.0
        assert row["stop_loss"] == 95.0
        assert row["target_1"] == 105.0


def test_symbols_are_deterministically_ordered_by_symbol(client, session_factory, as_staff):
    session = session_factory()
    for symbol in ("9999", "1111", "5555"):
        stock = _stock(session, symbol)
        _snapshot(session, stock, scan_run_id=200)
    session.commit()
    _cycle(session, "cyc-order", scan_run_id=200)
    session.close()

    response = client.get(_url("cyc-order"))
    assert response.status_code == 200
    body = response.json()
    assert [row["symbol"] for row in body["symbols"]] == ["1111", "5555", "9999"]


# --- per-symbol rows, material-change case -------------------------------


def test_material_change_symbol_reports_the_real_shadow_signal_row(client, session_factory, as_staff):
    session = session_factory()
    stock = _stock(session, "4040")
    snapshot = _snapshot(session, stock, scan_run_id=300, decision="BUY_CANDIDATE", confidence=82.0)
    session.add(
        ShadowLiveSignal(
            cycle_id="cyc-material",
            symbol="4040",
            stock_id=stock.id,
            decision_v2_snapshot_id=snapshot.id,
            lifecycle_result=ShadowLifecycleResult.NEW_INTRADAY_OPPORTUNITY,
            change_reason="First live shadow signal for 4040: reached actionable decision.",
            selection_reason="NEW_STAGE1_CANDIDATE",
            classification="BUY_CANDIDATE",
            confidence_score=82.0,
            emitted_at=datetime.now(timezone.utc),
        )
    )
    session.commit()
    _cycle(session, "cyc-material", scan_run_id=300, signals_new_opportunity_count=1)
    session.close()

    response = client.get(_url("cyc-material"))
    assert response.status_code == 200
    body = response.json()
    assert len(body["symbols"]) == 1
    row = body["symbols"][0]
    assert row["state_change"] == "NEW_INTRADAY_OPPORTUNITY"
    assert row["selection_reason"] == "NEW_STAGE1_CANDIDATE"
    assert "First live shadow signal" in row["state_change_reason"]


# --- aggregate consistency ------------------------------------------------


def test_aggregate_counts_match_the_cycle_row_not_a_recomputation(client, session_factory, as_staff):
    session = session_factory()
    stock = _stock(session, "6060")
    _snapshot(session, stock, scan_run_id=400)
    session.commit()
    _cycle(
        session, "cyc-agg", scan_run_id=400,
        symbols_selected_count=1, symbols_evaluated_count=1,
        signals_new_opportunity_count=0, signals_refreshed_count=0,
        signals_unchanged_count=1, signals_invalidated_count=0,
        quota_remaining_before=70, quota_remaining_after=65,
    )
    session.close()

    response = client.get(_url("cyc-agg"))
    assert response.status_code == 200
    body = response.json()
    assert body["stage2_count"] == 1
    assert body["unchanged_count"] == 1
    assert body["new_count"] == 0
    assert body["request_cost"] == 5


# --- no SAHMK cost, no consumer/forward-test mutation --------------------


def test_never_makes_a_sahmk_request(client, session_factory, as_staff, monkeypatch):
    session = session_factory()
    stock = _stock(session, "7070")
    _snapshot(session, stock, scan_run_id=500)
    session.commit()
    _cycle(session, "cyc-nosahmk", scan_run_id=500)
    session.close()

    def _fail(*args, **kwargs):
        raise AssertionError("must never call the SAHMK provider from a read-only observability endpoint")

    import src.market_data.provider_factory as provider_factory_module

    monkeypatch.setattr(provider_factory_module, "get_market_data_provider", _fail)

    response = client.get(_url("cyc-nosahmk"))
    assert response.status_code == 200


def test_never_creates_or_mutates_a_radar_opportunity(client, session_factory, as_staff):
    session = session_factory()
    stock = _stock(session, "8080")
    _snapshot(session, stock, scan_run_id=600)
    session.commit()
    _cycle(session, "cyc-noradar", scan_run_id=600)
    session.close()

    response = client.get(_url("cyc-noradar"))
    assert response.status_code == 200

    from src.domain.models import RadarOpportunity

    verify_session = session_factory()
    assert verify_session.query(RadarOpportunity).count() == 0
    verify_session.close()


def test_never_creates_or_mutates_a_decision_v2_outcome(client, session_factory, as_staff):
    session = session_factory()
    stock = _stock(session, "9090")
    _snapshot(session, stock, scan_run_id=700)
    session.commit()
    _cycle(session, "cyc-nooutcome", scan_run_id=700)
    session.close()

    response = client.get(_url("cyc-nooutcome"))
    assert response.status_code == 200

    from src.domain.models import DecisionV2Outcome

    verify_session = session_factory()
    assert verify_session.query(DecisionV2Outcome).count() == 0
    verify_session.close()


# --- stale/old cycle handling ---------------------------------------------


def test_an_old_cycle_from_days_ago_is_still_readable(client, session_factory, as_staff):
    session = session_factory()
    stock = _stock(session, "1212")
    _snapshot(session, stock, scan_run_id=800)
    session.commit()
    _cycle(
        session, "cyc-old-stale", scan_run_id=800,
        triggered_at=datetime.now(timezone.utc) - timedelta(days=3),
        finished_at=datetime.now(timezone.utc) - timedelta(days=3),
    )
    session.close()

    response = client.get(_url("cyc-old-stale"))
    assert response.status_code == 200
    body = response.json()
    assert body["cycle_id"] == "cyc-old-stale"
    assert len(body["symbols"]) == 1


# --- cross-cycle / cross-scan contamination -------------------------------


def test_two_cycles_with_different_scan_run_ids_never_mix_symbols(client, session_factory, as_staff):
    session = session_factory()
    stock_a = _stock(session, "1313")
    stock_b = _stock(session, "1414")
    _snapshot(session, stock_a, scan_run_id=900)
    _snapshot(session, stock_b, scan_run_id=901)
    session.commit()
    _cycle(session, "cyc-900", scan_run_id=900)
    _cycle(session, "cyc-901", scan_run_id=901)
    session.close()

    body_900 = client.get(_url("cyc-900")).json()
    body_901 = client.get(_url("cyc-901")).json()

    assert [row["symbol"] for row in body_900["symbols"]] == ["1313"]
    assert [row["symbol"] for row in body_901["symbols"]] == ["1414"]


def test_an_ordinary_non_shadow_scan_run_never_leaks_into_a_shadow_cycle(client, session_factory, as_staff):
    """Simulates the real Day-1 topology: an ordinary opening-scan
    MarketScanRun (like production's run 131) that no RecurrentScanCycle
    ever references. Its DecisionV2Snapshot rows must never appear when
    querying an unrelated Shadow cycle's own, different scan_run_id."""
    session = session_factory()
    consumer_stock = _stock(session, "1515")
    _snapshot(session, consumer_stock, scan_run_id=131)  # the "ordinary opening scan" analogue
    shadow_stock = _stock(session, "1616")
    _snapshot(session, shadow_stock, scan_run_id=132)  # the Shadow cycle's own scan
    session.commit()
    _cycle(session, "cyc-132-only", scan_run_id=132)
    session.close()

    body = client.get(_url("cyc-132-only")).json()
    symbols = [row["symbol"] for row in body["symbols"]]
    assert symbols == ["1616"]
    assert "1515" not in symbols


# --- immutability ----------------------------------------------------------


def test_no_row_count_changes_anywhere_across_all_relevant_tables(client, session_factory, as_staff):
    session = session_factory()
    stock = _stock(session, "1717")
    _snapshot(session, stock, scan_run_id=1000)
    session.commit()
    _cycle(session, "cyc-immutable", scan_run_id=1000)
    session.close()

    from src.domain.models import DecisionV2Outcome, DecisionV2Snapshot, RadarOpportunity, ShadowLiveSignal

    def _counts():
        s = session_factory()
        try:
            return {
                "RecurrentScanCycle": s.query(RecurrentScanCycle).count(),
                "DecisionV2Snapshot": s.query(DecisionV2Snapshot).count(),
                "ShadowLiveSignal": s.query(ShadowLiveSignal).count(),
                "RadarOpportunity": s.query(RadarOpportunity).count(),
                "DecisionV2Outcome": s.query(DecisionV2Outcome).count(),
            }
        finally:
            s.close()

    before = _counts()
    response = client.get(_url("cyc-immutable"))
    assert response.status_code == 200
    after = _counts()

    assert before == after, f"row counts changed from a read-only GET: before={before} after={after}"


def test_repeated_reads_of_the_same_cycle_are_byte_identical(client, session_factory, as_staff):
    session = session_factory()
    stock = _stock(session, "1818")
    _snapshot(session, stock, scan_run_id=1100)
    session.commit()
    _cycle(session, "cyc-repeat", scan_run_id=1100)
    session.close()

    first = client.get(_url("cyc-repeat"))
    second = client.get(_url("cyc-repeat"))
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


# --- query boundedness ------------------------------------------------------


def test_a_large_unrelated_snapshot_table_does_not_leak_into_a_small_cycle(client, session_factory, as_staff):
    """Proves the query is bounded by scan_run_id, not an accidental
    full-table read: many unrelated DecisionV2Snapshot rows exist
    (different scan_run_ids, simulating routine ingestion/other scans),
    but the cycle's own response only ever contains its own symbols."""
    session = session_factory()
    for i in range(50):
        stock = _stock(session, f"U{i:03d}")
        _snapshot(session, stock, scan_run_id=2000 + i)
    target_stock = _stock(session, "TARGET")
    _snapshot(session, target_stock, scan_run_id=9999)
    session.commit()
    _cycle(session, "cyc-bounded", scan_run_id=9999)
    session.close()

    body = client.get(_url("cyc-bounded")).json()
    assert [row["symbol"] for row in body["symbols"]] == ["TARGET"]


# --- PR #107: fairness/observability telemetry -----------------------------


def test_new_telemetry_fields_present_for_a_pre_pr107_row_are_all_null_or_empty(
    client, session_factory, as_staff,
):
    """Phase 14 (test 16): a legacy cycle row with the new columns NULL
    must remain fully readable -- no 500, no validation error."""
    session = session_factory()
    stock = _stock(session, "2121")
    _snapshot(session, stock, scan_run_id=1200)
    session.commit()
    _cycle(session, "cyc-legacy", scan_run_id=1200)  # no PR #107 fields set
    session.close()

    response = client.get(_url("cyc-legacy"))
    assert response.status_code == 200
    body = response.json()
    assert body["active_signal_candidate_count"] is None
    assert body["selected_active_signal_count"] is None
    assert body["stage1_universe_size"] is None
    assert body["stage1_evaluated_count"] is None
    assert body["stage1_candidate_count"] is None
    assert body["top_stage1_candidates"] == []


def test_admin_detail_exposes_new_selection_and_stage1_telemetry(client, session_factory, as_staff):
    session = session_factory()
    stock = _stock(session, "2222")
    _snapshot(session, stock, scan_run_id=1300)
    session.commit()

    from src.domain.models import MarketScanRun

    run = session.query(MarketScanRun).filter(MarketScanRun.id == 1300).first()
    if run is None:
        run = MarketScanRun(id=1300, symbols_requested=3, is_shadow_internal=True)
        session.add(run)
        session.flush()
    run.stage1_universe_size = 372
    run.stage1_evaluated_count = 350
    run.stage1_candidate_count = 25
    session.commit()

    top_stage1 = [
        {"symbol": "2222", "rank": 1, "score": 91.2, "selected_for_stage2": True, "selection_source": "NEW_STAGE1_CANDIDATE"},
        {"symbol": "3333", "rank": 2, "score": 88.5, "selected_for_stage2": False, "selection_source": None},
    ]
    _cycle(
        session, "cyc-telemetry", scan_run_id=1300,
        active_signal_candidate_count=14, new_stage1_candidate_count=1,
        symbols_selected_count=3, symbols_evaluated_count=3,
        top_stage1_candidates=top_stage1,
    )
    session.close()

    response = client.get(_url("cyc-telemetry"))
    assert response.status_code == 200
    body = response.json()
    assert body["active_signal_candidate_count"] == 14
    assert body["stage1_count"] == 1
    assert body["selected_active_signal_count"] == 2  # 3 evaluated - 1 discovery
    assert body["stage1_universe_size"] == 372
    assert body["stage1_evaluated_count"] == 350
    assert body["stage1_candidate_count"] == 25
    assert body["top_stage1_candidates"] == top_stage1

    # PR #106/#107 isolation regression, at the repository layer this
    # route's own data comes from (see
    # test_market_intelligence_repository.py's
    # test_get_latest_run_with_stage1_metrics_excludes_a_shadow_run_even_when_most_recent
    # for the full end-to-end proof that a consumer-facing reader of
    # these same MarketScanRun columns can never resolve to this
    # Shadow run merely because it now carries stage1 metrics too).
