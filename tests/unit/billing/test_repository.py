import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.billing.repository import BillingRepository
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
def repo():
    return BillingRepository()


@pytest.fixture
def user(session):
    u = User(email="billing@example.com", password_hash="hashed")
    session.add(u)
    session.commit()
    return u


def test_create_and_get_invoice(session, repo, user):
    invoice = repo.create_invoice(session, user_id=user.id, amount=49.0)
    fetched = repo.get_invoice(session, invoice.id)
    assert fetched.id == invoice.id
    assert float(fetched.amount) == 49.0
    assert fetched.status == InvoiceStatus.PENDING
    assert fetched.provider == "noop"


def test_get_invoice_for_user_scopes_by_owner(session, repo, user):
    other = User(email="other@example.com", password_hash="hashed")
    session.add(other)
    session.commit()

    invoice = repo.create_invoice(session, user_id=user.id, amount=49.0)
    assert repo.get_invoice_for_user(session, invoice.id, user.id).id == invoice.id
    assert repo.get_invoice_for_user(session, invoice.id, other.id) is None


def test_get_invoice_by_provider_reference(session, repo, user):
    invoice = repo.create_invoice(session, user_id=user.id, amount=49.0)
    repo.set_invoice_provider_reference(session, invoice.id, "noop-invoice-1")
    fetched = repo.get_invoice_by_provider_reference(session, "noop-invoice-1")
    assert fetched.id == invoice.id


def test_list_invoices_for_user(session, repo, user):
    repo.create_invoice(session, user_id=user.id, amount=10.0)
    repo.create_invoice(session, user_id=user.id, amount=20.0)
    total, rows = repo.list_invoices_for_user(session, user.id, limit=50, offset=0)
    assert total == 2
    assert len(rows) == 2


def test_set_invoice_status(session, repo, user):
    invoice = repo.create_invoice(session, user_id=user.id, amount=49.0)
    repo.set_invoice_status(session, invoice.id, InvoiceStatus.PAID)
    assert repo.get_invoice(session, invoice.id).status == InvoiceStatus.PAID


def test_create_and_list_payments(session, repo, user):
    invoice = repo.create_invoice(session, user_id=user.id, amount=49.0)
    repo.create_payment(session, invoice.id, 49.0)
    payments = repo.list_payments_for_invoice(session, invoice.id)
    assert len(payments) == 1
    assert payments[0].status == PaymentStatus.PENDING


def test_set_payment_status(session, repo, user):
    invoice = repo.create_invoice(session, user_id=user.id, amount=49.0)
    payment = repo.create_payment(session, invoice.id, 49.0)
    repo.set_payment_status(session, payment.id, PaymentStatus.SUCCEEDED, provider_transaction_id="txn-1")
    payments = repo.list_payments_for_invoice(session, invoice.id)
    assert payments[0].status == PaymentStatus.SUCCEEDED
    assert payments[0].provider_transaction_id == "txn-1"
