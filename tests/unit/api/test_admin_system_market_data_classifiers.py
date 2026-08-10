"""Unit tests for the pure, zero-I/O market-data classifier helpers in
src.api.routes.admin.system -- _classify_market_data_health and
_classify_market_data_status. These back GET /api/v1/admin/system/
summary's market_data_health/market_data_status fields, which used to
be silently None whenever a live SAHMK probe failed under
STRICT_REAL_DATA (2026-08-10 production evidence) -- these tests only
exercise the classification logic itself (no DB/Redis/network), so
they run in any environment.
"""

from src.api.routes.admin.system import (
    _classify_market_data_health,
    _classify_market_data_status,
)


def _health(**overrides):
    base = {
        "configured_provider": "auto",
        "strict_real_data": True,
        "synthetic_allowed": False,
        "sahmk_key_present": True,
        "current_provider_kind": None,
        "last_connectivity_status": None,
        "last_connectivity_at": None,
        "last_real_data_at": None,
    }
    base.update(overrides)
    return base


# --- _classify_market_data_status -------------------------------------------


def test_status_live_when_sahmk_selected_and_last_probe_succeeded():
    health = _health(current_provider_kind="sahmk", last_connectivity_status="SUCCESS")
    assert _classify_market_data_status(health, None, None) == "LIVE"


def test_status_unavailable_when_nothing_ever_selected():
    health = _health(current_provider_kind=None)
    assert _classify_market_data_status(health, None, None) == "UNAVAILABLE"


def test_status_degraded_when_falling_back_to_dev_provider():
    health = _health(current_provider_kind="dev", last_connectivity_status="FAILED")
    assert _classify_market_data_status(health, None, None) == "DEGRADED"


def test_status_stale_when_sahmk_selected_but_last_probe_failed_with_prior_real_data():
    health = _health(
        current_provider_kind="sahmk", last_connectivity_status="FAILED", last_real_data_at="2026-08-09T10:00:00Z"
    )
    assert _classify_market_data_status(health, None, None) == "STALE"


def test_status_unavailable_when_sahmk_selected_probe_failed_and_never_had_real_data():
    health = _health(current_provider_kind="sahmk", last_connectivity_status="FAILED", last_real_data_at=None)
    assert _classify_market_data_status(health, None, None) == "UNAVAILABLE"


def test_status_degraded_when_real_upstream_quota_evidence_says_exhausted():
    """The core regression this fixes: even a perfectly-fine
    last_connectivity_status=SUCCESS must not be reported as LIVE once
    SAHMK's own real evidence says the account is out of budget --
    provider truth (SahmkRateLimiter.get_status()) always wins."""
    health = _health(current_provider_kind="sahmk", last_connectivity_status="SUCCESS")
    quota_status = {"upstream_confirmed_exhausted": True, "upstream_reset_at_utc": "2026-08-10T21:00:00+00:00"}
    assert _classify_market_data_status(health, quota_status, None) == "DEGRADED"


def test_status_degraded_when_circuit_breaker_is_open():
    health = _health(current_provider_kind="sahmk", last_connectivity_status="SUCCESS")
    assert _classify_market_data_status(health, None, "OPEN") == "DEGRADED"


def test_status_not_degraded_when_quota_status_present_but_not_exhausted():
    health = _health(current_provider_kind="sahmk", last_connectivity_status="SUCCESS")
    quota_status = {"upstream_confirmed_exhausted": False}
    assert _classify_market_data_status(health, quota_status, None) == "LIVE"


# --- _classify_market_data_health -------------------------------------------


def test_health_unhealthy_when_no_sahmk_key_configured():
    health = _health(sahmk_key_present=False)
    assert _classify_market_data_health(health, None) == "unhealthy"


def test_health_healthy_when_sahmk_selected_and_last_probe_succeeded():
    health = _health(current_provider_kind="sahmk", last_connectivity_status="SUCCESS")
    assert _classify_market_data_health(health, None) == "healthy"


def test_health_degraded_when_circuit_breaker_open():
    health = _health(current_provider_kind="sahmk", last_connectivity_status="SUCCESS")
    assert _classify_market_data_health(health, "OPEN") == "degraded"


def test_health_unhealthy_when_nothing_ever_selected():
    health = _health(current_provider_kind=None)
    assert _classify_market_data_health(health, None) == "unhealthy"


def test_health_degraded_when_falling_back_to_dev():
    health = _health(current_provider_kind="dev")
    assert _classify_market_data_health(health, None) == "degraded"
