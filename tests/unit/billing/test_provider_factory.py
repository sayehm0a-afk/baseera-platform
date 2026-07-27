from src.billing.provider_factory import get_payment_provider
from src.billing.providers.noop_payment_provider import NoopPaymentProvider


def test_returns_a_noop_provider():
    assert isinstance(get_payment_provider(), NoopPaymentProvider)


def test_returns_the_same_instance_across_calls():
    assert get_payment_provider() is get_payment_provider()
