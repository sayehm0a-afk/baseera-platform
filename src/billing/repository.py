"""BillingRepository: the only module that reads/writes `invoices` and
`payments` -- persistence only, business rules live in
billing_service.py, the same split every other package in this
codebase already uses."""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from src.domain.models import Invoice, InvoiceStatus, Payment, PaymentStatus


class BillingRepository:
    # --- Invoice -----------------------------------------------------------

    def create_invoice(
        self,
        session: Session,
        user_id: int,
        amount: float,
        currency: str = "SAR",
        subscription_id: Optional[int] = None,
        provider: str = "noop",
    ) -> Invoice:
        invoice = Invoice(
            user_id=user_id,
            subscription_id=subscription_id,
            amount=amount,
            currency=currency,
            provider=provider,
        )
        session.add(invoice)
        session.commit()
        return invoice

    def get_invoice(self, session: Session, invoice_id: int) -> Optional[Invoice]:
        return session.query(Invoice).filter_by(id=invoice_id).one_or_none()

    def get_invoice_for_user(self, session: Session, invoice_id: int, user_id: int) -> Optional[Invoice]:
        return session.query(Invoice).filter_by(id=invoice_id, user_id=user_id).one_or_none()

    def get_invoice_by_provider_reference(self, session: Session, provider_reference: str) -> Optional[Invoice]:
        return session.query(Invoice).filter_by(provider_reference=provider_reference).one_or_none()

    def list_invoices_for_user(
        self, session: Session, user_id: int, limit: int, offset: int
    ) -> Tuple[int, List[Invoice]]:
        query = session.query(Invoice).filter_by(user_id=user_id).order_by(Invoice.issued_at.desc())
        total = query.count()
        return total, query.offset(offset).limit(limit).all()

    def set_invoice_provider_reference(self, session: Session, invoice_id: int, provider_reference: str) -> None:
        session.query(Invoice).filter_by(id=invoice_id).update({"provider_reference": provider_reference})
        session.commit()

    def set_invoice_status(
        self, session: Session, invoice_id: int, status: InvoiceStatus, paid_at: Optional[datetime] = None
    ) -> None:
        values = {"status": status}
        if paid_at is not None:
            values["paid_at"] = paid_at
        session.query(Invoice).filter_by(id=invoice_id).update(values)
        session.commit()

    # --- Payment -------------------------------------------------------------

    def create_payment(
        self, session: Session, invoice_id: int, amount: float, status: PaymentStatus = PaymentStatus.PENDING
    ) -> Payment:
        payment = Payment(invoice_id=invoice_id, amount=amount, status=status)
        session.add(payment)
        session.commit()
        return payment

    def list_payments_for_invoice(self, session: Session, invoice_id: int) -> List[Payment]:
        return session.query(Payment).filter_by(invoice_id=invoice_id).order_by(Payment.created_at).all()

    def set_payment_status(
        self,
        session: Session,
        payment_id: int,
        status: PaymentStatus,
        provider_transaction_id: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ) -> None:
        values = {"status": status, "updated_at": datetime.now(timezone.utc)}
        if provider_transaction_id is not None:
            values["provider_transaction_id"] = provider_transaction_id
        if failure_reason is not None:
            values["failure_reason"] = failure_reason
        session.query(Payment).filter_by(id=payment_id).update(values)
        session.commit()
