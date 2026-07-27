"""NoopPaymentProvider: the only IPaymentProvider implementation today
-- no real gateway (Stripe/HyperPay/Moyasar/Apple Pay/Mada/STC Pay) is
integrated. "No fake payment success" is a hard rule here, not a
toggle: every method is honest about doing nothing real.

- create_checkout_session() returns a placeholder `noop://` URL --
  nothing can actually complete a purchase at it.
- handle_webhook() always reports failure: no real gateway exists to
  ever call this, so any payload reaching it is not a legitimate
  payment confirmation.
- refund_payment() always fails -- there is never a real charge to
  refund.

See src.billing.billing_service.simulate_dev_payment_success for the
one, explicitly-gated, loudly-logged exception used to exercise the
PAID/SUCCEEDED code paths in local development before a real gateway
exists -- that function lives in the service layer (not here) because
it mutates Invoice/Payment rows directly rather than going through a
provider call, which is exactly the point: it is not something a real
provider integration would ever need to expose.
"""

import logging

from src.billing.provider import CheckoutSession, IPaymentProvider, RefundResult, WebhookResult
from src.domain.models import Invoice, Payment

logger = logging.getLogger(__name__)


class NoopPaymentProvider(IPaymentProvider):
    def create_checkout_session(self, invoice: Invoice) -> CheckoutSession:
        logger.warning(
            "[NoopPaymentProvider] No real payment gateway configured -- "
            "returning a placeholder checkout URL for invoice %s. No real "
            "checkout page exists at this URL.",
            invoice.id,
        )
        return CheckoutSession(
            checkout_url=f"noop://checkout/{invoice.id}",
            provider_reference=f"noop-invoice-{invoice.id}",
        )

    def handle_webhook(self, payload: dict) -> WebhookResult:
        logger.warning(
            "[NoopPaymentProvider] Received a webhook call, but no real "
            "payment gateway is configured -- no gateway exists that could "
            "have sent this, so it cannot be treated as a genuine payment "
            "confirmation. Payload ignored: %r",
            payload,
        )
        return WebhookResult(
            provider_reference=str(payload.get("provider_reference", "")),
            succeeded=False,
            failure_reason="No real payment gateway is configured.",
        )

    def refund_payment(self, payment: Payment) -> RefundResult:
        logger.warning(
            "[NoopPaymentProvider] Refund requested for payment %s, but no "
            "real payment gateway is configured -- there is no real charge "
            "to refund.",
            payment.id,
        )
        return RefundResult(succeeded=False, failure_reason="No real payment gateway is configured.")

    def health_check(self) -> bool:
        return True
