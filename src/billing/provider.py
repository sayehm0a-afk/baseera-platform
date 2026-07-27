"""IPaymentProvider: the one seam a real gateway (Stripe, HyperPay,
Moyasar, Apple Pay, Mada, STC Pay) plugs into later -- no gateway is
integrated in this milestone, only this interface and one
implementation (NoopPaymentProvider) that never fakes a real charge.
Every method signature here is shaped around what a real gateway
integration actually needs, not simplified for the no-op case, so
adding a real provider later is a new class, not an interface change.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from src.domain.models import Invoice, Payment


@dataclass(frozen=True)
class CheckoutSession:
    checkout_url: str
    provider_reference: str


@dataclass(frozen=True)
class WebhookResult:
    provider_reference: str
    succeeded: bool
    provider_transaction_id: Optional[str] = None
    failure_reason: Optional[str] = None


@dataclass(frozen=True)
class RefundResult:
    succeeded: bool
    provider_transaction_id: Optional[str] = None
    failure_reason: Optional[str] = None


class IPaymentProvider(ABC):
    @abstractmethod
    def create_checkout_session(self, invoice: Invoice) -> CheckoutSession:
        """Starts a hosted checkout for `invoice`. Never marks the
        invoice paid itself -- payment confirmation always arrives
        later, via `handle_webhook`."""

    @abstractmethod
    def handle_webhook(self, payload: dict) -> WebhookResult:
        """Parses a provider's webhook payload into a normalized
        result. Signature verification (provider-specific) belongs
        inside a real provider's implementation, not this interface."""

    @abstractmethod
    def refund_payment(self, payment: Payment) -> RefundResult:
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Whether this provider can currently be reached/used --
        the same convention IMarketDataProvider/IFundamentalDataProvider
        already establish."""
