import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.billing import billing_service
from src.billing.repository import BillingRepository
from src.core.config import settings
from src.core.db.database import Base
from src.domain.models import InvoiceStatus, PaymentStatus, User


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def user(session):
    u = User(email="billing-service@example.com", password_hash="hashed")
    session.add(u)
    session.commit()
    return u


def test_create_invoice_for_subscription(session, user):
    invoice = billing_service.create_invoice_for_subscription(session, user, amount=99.0)
    assert invoice.user_id == user.id
    assert float(invoice.amount) == 99.0
    assert invoice.status == InvoiceStatus.PENDING


def test_start_checkout_persists_the_provider_reference(session, user):
    invoice = billing_service.create_invoice_for_subscription(session, user, amount=99.0)
    checkout = billing_service.start_checkout(session, invoice)
    assert checkout.checkout_url.startswith("noop://")

    reloaded = BillingRepository().get_invoice(session, invoice.id)
    assert reloaded.provider_reference == checkout.provider_reference


def test_process_webhook_never_marks_paid_via_the_noop_provider(session, user):
    invoice = billing_service.create_invoice_for_subscription(session, user, amount=99.0)
    billing_service.start_checkout(session, invoice)

    billing_service.process_webhook(session, {"provider_reference": invoice.provider_reference})

    reloaded = BillingRepository().get_invoice(session, invoice.id)
    assert reloaded.status == InvoiceStatus.FAILED  # noop provider never succeeds


def test_process_webhook_ignores_an_unknown_invoice_reference(session):
    # Should not raise -- simply nothing to update.
    billing_service.process_webhook(session, {"provider_reference": "does-not-exist"})


def test_simulate_dev_payment_success_marks_invoice_paid(session, user, monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "billing_noop_auto_approve", True)

    invoice = billing_service.create_invoice_for_subscription(session, user, amount=99.0)
    billing_service.simulate_dev_payment_success(session, invoice)

    reloaded = BillingRepository().get_invoice(session, invoice.id)
    assert reloaded.status == InvoiceStatus.PAID
    assert reloaded.paid_at is not None

    payments = BillingRepository().list_payments_for_invoice(session, invoice.id)
    assert payments[0].status == PaymentStatus.SUCCEEDED


def test_simulate_dev_payment_success_refuses_in_production(session, user, monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "billing_noop_auto_approve", True)
    monkeypatch.setattr(settings, "secret_key", "a-real-production-secret")

    invoice = billing_service.create_invoice_for_subscription(session, user, amount=99.0)
    with pytest.raises(RuntimeError):
        billing_service.simulate_dev_payment_success(session, invoice)


def test_simulate_dev_payment_success_refuses_without_the_flag(session, user, monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "billing_noop_auto_approve", False)

    invoice = billing_service.create_invoice_for_subscription(session, user, amount=99.0)
    with pytest.raises(RuntimeError):
        billing_service.simulate_dev_payment_success(session, invoice)
