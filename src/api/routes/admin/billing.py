"""GET /api/v1/admin/billing/* -- Admin Dashboard read-only billing
history: view a user's invoices and an invoice's payment attempts.
Read-only by design -- no route here can mark an invoice paid or
create a payment; only `src.billing.billing_service` (triggered by a
real webhook, or explicitly by `simulate_dev_payment_success` outside
production) ever mutates billing state, so staff can see billing
history but never fabricate a payment through the admin surface.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.admin.exceptions import AdminInvoiceNotFoundError, AdminUserNotFoundError
from src.api.schemas.admin import AdminInvoiceListOut, AdminInvoiceOut, AdminPaymentListOut, AdminPaymentOut
from src.auth.rbac import require_staff_role
from src.auth.repository import AuthRepository
from src.billing.repository import BillingRepository
from src.core.db.database import get_db
from src.domain.models import StaffRole, User

router = APIRouter(prefix="/api/v1/admin/billing", tags=["admin"])

_repository = BillingRepository()
_auth_repository = AuthRepository()


@router.get("/users/{user_id}/invoices", response_model=AdminInvoiceListOut)
def list_invoices_for_user(
    user_id: int,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> AdminInvoiceListOut:
    if _auth_repository.get_user_by_id(session, user_id) is None:
        raise AdminUserNotFoundError(f"No user {user_id}.")

    total, invoices = _repository.list_invoices_for_user(session, user_id, limit=limit, offset=offset)
    return AdminInvoiceListOut(total=total, invoices=[AdminInvoiceOut.model_validate(i) for i in invoices])


@router.get("/invoices/{invoice_id}/payments", response_model=AdminPaymentListOut)
def list_payments_for_invoice(
    invoice_id: int,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> AdminPaymentListOut:
    if _repository.get_invoice(session, invoice_id) is None:
        raise AdminInvoiceNotFoundError(f"No invoice {invoice_id}.")

    payments = _repository.list_payments_for_invoice(session, invoice_id)
    return AdminPaymentListOut(payments=[AdminPaymentOut.model_validate(p) for p in payments])
