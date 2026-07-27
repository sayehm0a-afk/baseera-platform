"""get_payment_provider(): the one seam a future real-provider
selection (env-var driven, matching src.market_data.provider_factory's
network-aware selection) plugs into. Only NoopPaymentProvider exists
today, so this always returns it -- kept as a factory function (not a
bare `NoopPaymentProvider()` at call sites) so that future selection
logic is a change in one place.
"""

from typing import Optional

from src.billing.provider import IPaymentProvider
from src.billing.providers.noop_payment_provider import NoopPaymentProvider

_provider: Optional[IPaymentProvider] = None


def get_payment_provider() -> IPaymentProvider:
    global _provider
    if _provider is None:
        _provider = NoopPaymentProvider()
    return _provider
