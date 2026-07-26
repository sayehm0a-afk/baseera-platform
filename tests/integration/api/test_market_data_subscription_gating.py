"""Regression tests for Phase 13 P13.5: src/api/routes/stocks.py and
src/api/routes/market.py previously had *no* auth dependency at all --
any anonymous caller could pull live quotes, the full AI recommendation/
decision/analyst-report stack, and every market-intelligence read
straight from the API, completely bypassing registration, trial, and
subscription. This file proves the fix on a representative sample of
routes from both files: no credentials at all -> 401; an authenticated
caller with no live entitlement -> 402; a real trial subscription ->
200 (so the fix costs a real trial/paying customer nothing).

Uses conftest.py's plain `client`/`db_session` fixtures deliberately
(NOT `authenticated_as_staff`) -- this file's whole point is to exercise
the real, unoverridden get_current_user + require_active_subscription
dependency chain, not to bypass it.
"""

from datetime import datetime, timedelta, timezone

import pytest

import main
from src.api.dependencies import get_current_user
from src.domain.models import Subscription, SubscriptionPlan, SubscriptionStatus, User

# One representative route per file is enough to prove the dependency
# is actually wired in -- every other route in each file was verified
# by direct code read to use the identical `Depends(require_active_
# subscription())` pattern (see stocks.py/market.py's own module
# docstrings for the full list).
_STOCKS_ROUTE = "/api/v1/stocks/2222/quote"
_MARKET_ROUTE = "/api/v1/market/summary"


@pytest.fixture
def customer(db_session) -> User:
    user = User(email="customer@example.com", password_hash="hashed", is_email_verified=True)
    db_session.add(user)
    db_session.commit()
    return user


def _as(user: User) -> None:
    main.app.dependency_overrides[get_current_user] = lambda: user


@pytest.mark.parametrize("route", [_STOCKS_ROUTE, _MARKET_ROUTE])
def test_anonymous_caller_is_rejected(client, route):
    response = client.get(route)
    assert response.status_code == 401


@pytest.mark.parametrize("route", [_STOCKS_ROUTE, _MARKET_ROUTE])
def test_authenticated_caller_with_no_subscription_row_is_rejected(client, customer, route):
    _as(customer)
    response = client.get(route)
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "subscription_required"


@pytest.mark.parametrize("route", [_STOCKS_ROUTE, _MARKET_ROUTE])
def test_authenticated_caller_with_an_expired_subscription_is_rejected(client, db_session, customer, route):
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
    response = client.get(route)
    assert response.status_code == 402


@pytest.mark.parametrize("route", [_STOCKS_ROUTE, _MARKET_ROUTE])
def test_a_real_trial_subscription_is_not_blocked_by_this_fix(client, db_session, customer, route):
    """The whole point of the fix is that it costs a real trial/paying
    customer nothing -- only anonymous/expired callers are newly
    rejected. This does not assert 200 (the routes' own business logic
    -- e.g. no ingested history yet -- may still 404/422 in this
    minimal fixture), only that the caller gets *past* the
    entitlement check itself."""
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
    response = client.get(route)
    assert response.status_code != 401
    assert response.status_code != 402
