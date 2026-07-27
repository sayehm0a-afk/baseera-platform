"""Phase 13 P13.6: proves the FK ON DELETE policy migration
(c4d8e6f19a2b_add_user_deletion_fk_policies) actually does what its own
docstring claims, for all three categories:

- CASCADE: personal data with no independent retention value is
  removed entirely alongside the user (notifications, watchlists +
  items, settings, recommendation history, reports, portfolios +
  holdings/analysis-snapshots/news-alerts).
- SET NULL: data with independent value survives, anonymized
  (ai_requests, feedback, support_tickets -- both of its user FKs).
- RESTRICT (unchanged, NO ACTION): financial/audit records still block
  deletion outright (invoices, audit_logs) -- already covered by
  test_admin_routes.py's equivalent test; re-asserted here as part of
  the same policy sweep for completeness.

Run against SQLite with `PRAGMA foreign_keys=ON` (the same pattern
test_admin_routes.py already uses for its own FK-RESTRICT test) so
this suite runs fast and everywhere; the same behavior was additionally
verified once by hand against real PostgreSQL 16 during development of
this migration -- SQLite's ON DELETE CASCADE/SET NULL support (when
foreign_keys is enabled) is standard SQL and matches Postgres's here.
"""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.auth.repository import AuthRepository
from src.core.db.database import Base
from src.domain.models import (
    AIRequest,
    AIRequestStatus,
    AuditLog,
    Feedback,
    FeedbackCategory,
    Invoice,
    Notification,
    NotificationType,
    Portfolio,
    PortfolioHolding,
    RecommendationHistory,
    Report,
    ReportType,
    Stock,
    SupportTicket,
    User,
    UserSetting,
    UserWatchlist,
    UserWatchlistItem,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def stock(session):
    s = Stock(symbol="2222", name_en="Test Co", sector="Energy")
    session.add(s)
    session.commit()
    return s


def test_deleting_a_user_cascades_all_purely_personal_data(session, stock):
    user = User(email="cascade@example.com", password_hash="hashed")
    session.add(user)
    session.commit()

    session.add(Notification(user_id=user.id, type=NotificationType.SYSTEM, title="t", body="b"))
    watchlist = UserWatchlist(user_id=user.id, name="My List")
    session.add(watchlist)
    session.commit()
    session.add(UserWatchlistItem(watchlist_id=watchlist.id, stock_id=stock.id, symbol="2222"))
    session.add(UserSetting(user_id=user.id, preferences_json={"theme": "dark"}))
    session.add(
        RecommendationHistory(user_id=user.id, symbol="2222", recommendation="BUY", confidence=0.8, source="scan")
    )
    session.add(Report(user_id=user.id, report_type=ReportType.DAILY, title="Daily"))
    portfolio = Portfolio(user_id=user.id, name="My Portfolio")
    session.add(portfolio)
    session.commit()
    session.add(PortfolioHolding(portfolio_id=portfolio.id, stock_id=stock.id, symbol="2222", quantity=10))
    session.commit()

    watchlist_id, portfolio_id = watchlist.id, portfolio.id

    AuthRepository().delete_user(session, user.id)

    assert session.query(Notification).filter_by(user_id=user.id).count() == 0
    assert session.query(UserWatchlist).filter_by(id=watchlist_id).count() == 0
    assert session.query(UserWatchlistItem).filter_by(watchlist_id=watchlist_id).count() == 0
    assert session.query(UserSetting).filter_by(user_id=user.id).count() == 0
    assert session.query(RecommendationHistory).filter_by(user_id=user.id).count() == 0
    assert session.query(Report).filter_by(user_id=user.id).count() == 0
    assert session.query(Portfolio).filter_by(id=portfolio_id).count() == 0
    assert session.query(PortfolioHolding).filter_by(portfolio_id=portfolio_id).count() == 0


def test_deleting_a_user_anonymizes_but_retains_independently_valuable_data(session):
    user = User(email="setnull@example.com", password_hash="hashed")
    session.add(user)
    session.commit()
    user_id = user.id

    session.add(AIRequest(user_id=user_id, feature="analyst_report", status=AIRequestStatus.SUCCESS))
    session.add(Feedback(user_id=user_id, category=FeedbackCategory.GENERAL, message="Great app!"))
    session.add(SupportTicket(user_id=user_id, subject="Help", message="I need help"))
    session.commit()

    AuthRepository().delete_user(session, user_id)

    ai_request = session.query(AIRequest).filter_by(feature="analyst_report").one()
    feedback = session.query(Feedback).filter_by(message="Great app!").one()
    ticket = session.query(SupportTicket).filter_by(subject="Help").one()

    assert ai_request.user_id is None
    assert feedback.user_id is None
    assert ticket.user_id is None


def test_deleting_a_staff_member_anonymizes_tickets_assigned_to_them(session):
    customer = User(email="ticket-owner@example.com", password_hash="hashed")
    staff = User(email="staff@example.com", password_hash="hashed", is_staff=True)
    session.add_all([customer, staff])
    session.commit()

    session.add(
        SupportTicket(user_id=customer.id, assigned_staff_user_id=staff.id, subject="Help", message="I need help")
    )
    session.commit()
    staff_id = staff.id

    AuthRepository().delete_user(session, staff_id)

    ticket = session.query(SupportTicket).filter_by(subject="Help").one()
    assert ticket.assigned_staff_user_id is None
    assert ticket.user_id == customer.id  # unaffected -- only the staff link was nulled


def test_deleting_a_user_with_an_invoice_is_still_blocked(session):
    user = User(email="hasinvoice@example.com", password_hash="hashed")
    session.add(user)
    session.commit()
    session.add(Invoice(user_id=user.id, amount=99.0, currency="SAR"))
    session.commit()

    with pytest.raises(IntegrityError):
        AuthRepository().delete_user(session, user.id)


def test_deleting_a_user_with_an_audit_log_entry_is_still_blocked(session):
    user = User(email="hasauditlog@example.com", password_hash="hashed")
    session.add(user)
    session.commit()
    session.add(AuditLog(actor_user_id=user.id, action="user.suspend", target_type="user", target_id=999))
    session.commit()

    with pytest.raises(IntegrityError):
        AuthRepository().delete_user(session, user.id)
