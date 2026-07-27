from prometheus_client import CollectorRegistry

from src.core.monitoring.prometheus_metrics import PrometheusMetrics


def _fresh_metrics() -> PrometheusMetrics:
    # A dedicated registry per test -- prometheus_client raises on
    # duplicate metric-name registration, so this must never touch the
    # process-wide default registry that get_metrics() uses.
    return PrometheusMetrics(registry=CollectorRegistry())


def test_record_login_increments_the_labeled_counter():
    metrics = _fresh_metrics()
    metrics.record_login("success")
    metrics.record_login("success")
    metrics.record_login("failure")
    assert metrics.logins_total.labels(status="success")._value.get() == 2
    assert metrics.logins_total.labels(status="failure")._value.get() == 1


def test_record_registration_increments_the_counter():
    metrics = _fresh_metrics()
    metrics.record_registration()
    metrics.record_registration()
    assert metrics.registrations_total._value.get() == 2


def test_set_active_sessions_sets_the_gauge_to_an_absolute_value():
    metrics = _fresh_metrics()
    metrics.set_active_sessions(7)
    assert metrics.active_sessions._value.get() == 7
    metrics.set_active_sessions(3)
    assert metrics.active_sessions._value.get() == 3


def test_record_trial_expiration_increments_the_counter():
    metrics = _fresh_metrics()
    metrics.record_trial_expiration()
    assert metrics.trial_expirations_total._value.get() == 1


def test_record_ai_request_increments_requests_and_tokens_by_feature():
    metrics = _fresh_metrics()
    metrics.record_ai_request(feature="analyst_narration", status="SUCCESS", total_tokens=100)
    metrics.record_ai_request(feature="analyst_narration", status="FAILED")

    assert metrics.ai_requests_total.labels(feature="analyst_narration", status="SUCCESS")._value.get() == 1
    assert metrics.ai_requests_total.labels(feature="analyst_narration", status="FAILED")._value.get() == 1
    assert metrics.ai_tokens_total.labels(feature="analyst_narration")._value.get() == 100


def test_record_ai_request_with_no_tokens_does_not_touch_the_token_counter():
    metrics = _fresh_metrics()
    metrics.record_ai_request(feature="market_scan", status="SUCCESS")
    assert metrics.ai_tokens_total.labels(feature="market_scan")._value.get() == 0


def test_record_admin_action_increments_the_labeled_counter():
    metrics = _fresh_metrics()
    metrics.record_admin_action("user.suspend")
    metrics.record_admin_action("user.suspend")
    assert metrics.admin_actions_total.labels(action="user.suspend")._value.get() == 2
