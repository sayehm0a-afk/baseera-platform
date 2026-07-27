from src.billing.providers.noop_payment_provider import NoopPaymentProvider
from src.domain.models import Invoice, Payment


def test_create_checkout_session_returns_a_placeholder_url():
    provider = NoopPaymentProvider()
    invoice = Invoice(id=42, user_id=1, amount=99.0)
    session = provider.create_checkout_session(invoice)
    assert session.checkout_url == "noop://checkout/42"
    assert session.provider_reference == "noop-invoice-42"


def test_handle_webhook_never_reports_success():
    provider = NoopPaymentProvider()
    result = provider.handle_webhook({"provider_reference": "noop-invoice-42"})
    assert result.succeeded is False
    assert result.provider_reference == "noop-invoice-42"


def test_refund_payment_always_fails():
    provider = NoopPaymentProvider()
    payment = Payment(id=7, invoice_id=42, amount=99.0)
    result = provider.refund_payment(payment)
    assert result.succeeded is False


def test_health_check_is_always_true():
    assert NoopPaymentProvider().health_check() is True
