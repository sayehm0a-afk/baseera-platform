"""BillingService: orchestrates Invoice/Payment against whichever
IPaymentProvider is configured (only NoopPaymentProvider exists today).
Not wired into any registration/subscription flow automatically --
creating an invoice is something a future "upgrade to a paid plan"
action triggers explicitly, which does not exist yet (no billing UI,
no real gateway to charge). This service exists so that action has a
correct, tested place to call into once it does.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from src.billing.provider import CheckoutSession
from src.billing.provider_factory import get_payment_provider
from src.billing.repository import BillingRepository
from src.core.config import settings
from src.domain.models import Invoice, InvoiceStatus, PaymentStatus, Subscription, User

logger = logging.getLogger(__name__)

_repository = BillingRepository()


def create_invoice_for_subscription(
    session: Session, user: User, amount: float, subscription: Optional[Subscription] = None, currency: str = "SAR"
) -> Invoice:
    return _repository.create_invoice(
        session,
        user_id=user.id,
        amount=amount,
        currency=currency,
        subscription_id=subscription.id if subscription else None,
    )


def start_checkout(session: Session, invoice: Invoice) -> CheckoutSession:
    checkout_session = get_payment_provider().create_checkout_session(invoice)
    _repository.set_invoice_provider_reference(session, invoice.id, checkout_session.provider_reference)
    return checkout_session


def process_webhook(session: Session, payload: dict) -> None:
    """Normalizes and applies a provider webhook. With only
    NoopPaymentProvider configured, `result.succeeded` is always
    False (see its docstring) -- this function exists and is fully
    wired so plugging in a real provider later requires no change
    here, only a new IPaymentProvider implementation."""
    result = get_payment_provider().handle_webhook(payload)
    invoice = _repository.get_invoice_by_provider_reference(session, result.provider_reference)
    if invoice is None:
        logger.warning("Webhook referenced unknown invoice provider_reference=%r -- ignoring.", result.provider_reference)
        return

    if result.succeeded:
        _repository.set_invoice_status(session, invoice.id, InvoiceStatus.PAID, paid_at=datetime.now(timezone.utc))
        _repository.create_payment(session, invoice.id, float(invoice.amount), status=PaymentStatus.SUCCEEDED)
    else:
        _repository.set_invoice_status(session, invoice.id, InvoiceStatus.FAILED)
        _repository.create_payment(session, invoice.id, float(invoice.amount), status=PaymentStatus.FAILED)


def simulate_dev_payment_success(session: Session, invoice: Invoice) -> None:
    """Manually marks `invoice` PAID and records a SUCCEEDED payment --
    the one, explicit exception to "no fake payment success," meant
    only for local development/QA to exercise the paid-account code
    path before a real gateway exists. Refuses to run in production or
    unless BILLING_NOOP_AUTO_APPROVE is explicitly set, so it can never
    fire from a real deployment or by silent default.
    """
    if settings.is_production:
        raise RuntimeError("simulate_dev_payment_success must never run in production.")
    if not settings.billing_noop_auto_approve:
        raise RuntimeError("simulate_dev_payment_success requires BILLING_NOOP_AUTO_APPROVE=true.")

    logger.warning(
        "[SIMULATED PAYMENT -- NOT REAL] Marking invoice %s as PAID for local "
        "development/QA purposes. No real charge occurred.",
        invoice.id,
    )
    _repository.set_invoice_status(session, invoice.id, InvoiceStatus.PAID, paid_at=datetime.now(timezone.utc))
    _repository.create_payment(session, invoice.id, float(invoice.amount), status=PaymentStatus.SUCCEEDED)
