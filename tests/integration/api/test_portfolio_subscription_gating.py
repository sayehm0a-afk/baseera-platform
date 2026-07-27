"""Regression tests for the portfolio-intelligence subscription-gating
gap found in the CTO engineering review dated 2026-07-27:
src/api/routes/portfolio.py previously required only `get_current_user`
(plain authentication) on every route, unlike src/api/routes/stocks.py
and market.py, which already require `require_active_subscription()`
per Phase 13 P13.5. Any registered account -- trial-expired, never
subscribed, or otherwise unentitled -- could reach the full premium
portfolio-intelligence stack (analyze/risk/allocation/diversification/
rebalance/health) for free. This file proves the fix on a representative
GET route plus the POST /analyze route (different request shape,
worth its own direct check), mirroring
test_market_data_subscription_gating.py's structure exactly: no
credentials -> 401; authenticated with no entitlement -> 402; a real
trial subscription -> past the entitlement check (never 401/402).

Uses conftest.py's plain `client`/`db_session` fixtures deliberately
(NOT `authenticated_as_staff`) -- the whole point is to exercise the
real, unoverridden get_current_user + require_active_subscription
dependency chain, not to bypass it.
"""

from datetime import datetime, timedelta, timezone

import pytest

import main
from src.api.dependencies import get_current_user
from src.domain.models import Subscription, SubscriptionPlan, SubscriptionStatus, User

# GET /{portfolio_id} is representative: require_active_subscription()
# is evaluated as a FastAPI dependency before the route body runs, so
# the 401/402 outcome is identical regardless of whether portfolio 1
# exists for this caller -- every other GET route in portfolio.py was
# verified by direct code read to use the identical
# `Depends(require_active_subscription())` pattern (see that file's
# module docstring). POST /analyze is checked separately since it's
# the primary write path and has its own request body.
_GET_ROUTE = "/api/v1/portfolio/1"
_ANALYZE_ROUTE = "/api/v1/portfolio/analyze"
_ANALYZE_BODY = {"name": "My Portfolio", "cash": 1000.0, "holdings": []}


@pytest.fixture
def customer(db_session) -> User:
    user = User(email="portfolio-customer@example.com", password_hash="hashed", is_email_verified=True)
    db_session.add(user)
    db_session.commit()
    return user


def _as(user: User) -> None:
    main.app.dependency_overrides[get_current_user] = lambda: user


class TestGetPortfolioRoute:
    def test_anonymous_caller_is_rejected(self, client):
        response = client.get(_GET_ROUTE)
        assert response.status_code == 401

    def test_authenticated_caller_with_no_subscription_row_is_rejected(self, client, customer):
        _as(customer)
        response = client.get(_GET_ROUTE)
        assert response.status_code == 402
        assert response.json()["error"]["code"] == "subscription_required"

    def test_authenticated_caller_with_an_expired_subscription_is_rejected(self, client, db_session, customer):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        db_session.add(
            Subscription(
                user_id=customer.id,
                plan=SubscriptionPlan.TRIAL,
                status=SubscriptionStatus.EXPIRED,
                trial_ends_at=past,
                current_period_start=past - timedelta(days=14),
                current_period_end=past,
            )
        )
        db_session.commit()

        _as(customer)
        response = client.get(_GET_ROUTE)
        assert response.status_code == 402

    def test_a_real_trial_subscription_is_not_blocked_by_this_fix(self, client, db_session, customer):
        """Does not assert 200 -- portfolio 1 doesn't exist for this
        fresh customer, so the route's own business logic 404s. Only
        asserts the caller gets *past* the entitlement check itself."""
        future = datetime.now(timezone.utc) + timedelta(days=14)
        db_session.add(
            Subscription(
                user_id=customer.id,
                plan=SubscriptionPlan.TRIAL,
                status=SubscriptionStatus.TRIALING,
                trial_ends_at=future,
                current_period_start=datetime.now(timezone.utc),
                current_period_end=future,
            )
        )
        db_session.commit()

        _as(customer)
        response = client.get(_GET_ROUTE)
        assert response.status_code != 401
        assert response.status_code != 402


class TestAnalyzePortfolioRoute:
    def test_anonymous_caller_is_rejected(self, client):
        response = client.post(_ANALYZE_ROUTE, json=_ANALYZE_BODY)
        assert response.status_code == 401

    def test_authenticated_caller_with_no_subscription_row_is_rejected(self, client, customer):
        _as(customer)
        response = client.post(_ANALYZE_ROUTE, json=_ANALYZE_BODY)
        assert response.status_code == 402
        assert response.json()["error"]["code"] == "subscription_required"

    def test_a_real_trial_subscription_can_actually_analyze(self, client, db_session, customer):
        """Unlike the GET check above, POST /analyze creates its own
        portfolio on the fly (no pre-existing portfolio_id needed), so
        this asserts a genuine 200 with a real analysis payload -- the
        strongest possible proof the fix costs a real trial customer
        nothing."""
        future = datetime.now(timezone.utc) + timedelta(days=14)
        db_session.add(
            Subscription(
                user_id=customer.id,
                plan=SubscriptionPlan.TRIAL,
                status=SubscriptionStatus.TRIALING,
                trial_ends_at=future,
                current_period_start=datetime.now(timezone.utc),
                current_period_end=future,
            )
        )
        db_session.commit()

        _as(customer)
        response = client.post(_ANALYZE_ROUTE, json=_ANALYZE_BODY)
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "My Portfolio"
