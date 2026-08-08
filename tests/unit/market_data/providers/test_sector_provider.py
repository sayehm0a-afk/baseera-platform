"""Unit tests for src.market_data.providers.sector_provider."""

import pytest

from src.market_data.providers.sector_provider import (
    NullSectorProvider,
    get_sector_classification_provider,
)


@pytest.mark.asyncio
async def test_null_sector_provider_always_returns_none():
    provider = NullSectorProvider()
    assert await provider.get_sector("2222") is None
    assert provider.is_configured is False


def test_factory_defaults_to_null_provider(monkeypatch):
    monkeypatch.delenv("SECTOR_CLASSIFICATION_PROVIDER", raising=False)
    provider = get_sector_classification_provider()
    assert isinstance(provider, NullSectorProvider)
    assert provider.is_configured is False


def test_factory_falls_back_to_null_for_an_unimplemented_named_provider(monkeypatch):
    """No real provider exists yet -- requesting one by name must not
    crash or silently fabricate data, just fall back honestly."""
    monkeypatch.setenv("SECTOR_CLASSIFICATION_PROVIDER", "tadawul_official")
    provider = get_sector_classification_provider()
    assert isinstance(provider, NullSectorProvider)
