"""Unit tests for src.market_data.ingestion._common's shared helpers."""

from unittest.mock import AsyncMock, patch

import pytest

from src.market_data.ingestion._common import sleep_if_rate_limited


@pytest.mark.asyncio
async def test_sleep_if_rate_limited_sleeps_for_retry_after():
    """A real production gap this session found: SahmkClient parses a
    429's Retry-After header into SahmkRateLimitError.retry_after, but
    nothing previously read it once the exception reached an ingestion
    job's per-symbol loop -- the very next symbol's request went out
    immediately. This is the fix: honor it."""

    class _RateLimited(Exception):
        retry_after = 12.5

    with patch("src.market_data.ingestion._common.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await sleep_if_rate_limited(_RateLimited())

    mock_sleep.assert_awaited_once_with(12.5)


@pytest.mark.asyncio
async def test_sleep_if_rate_limited_caps_an_excessive_retry_after():
    class _RateLimited(Exception):
        retry_after = 9999.0

    with patch("src.market_data.ingestion._common.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await sleep_if_rate_limited(_RateLimited())

    mock_sleep.assert_awaited_once_with(30.0)


@pytest.mark.asyncio
async def test_sleep_if_rate_limited_is_a_noop_without_retry_after():
    with patch("src.market_data.ingestion._common.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await sleep_if_rate_limited(RuntimeError("some other failure"))

    mock_sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_sleep_if_rate_limited_is_a_noop_when_retry_after_is_none():
    class _RateLimited(Exception):
        retry_after = None

    with patch("src.market_data.ingestion._common.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await sleep_if_rate_limited(_RateLimited())

    mock_sleep.assert_not_awaited()
