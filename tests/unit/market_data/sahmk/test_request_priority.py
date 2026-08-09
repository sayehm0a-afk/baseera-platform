"""Unit tests for the SAHMK request-priority contextvar mechanism."""

import asyncio

import pytest

from src.market_data.sahmk.request_priority import (
    BACKGROUND,
    CRITICAL,
    get_current_priority,
    priority_scope,
)


def test_default_priority_is_critical():
    assert get_current_priority() == CRITICAL


def test_priority_scope_sets_and_restores():
    assert get_current_priority() == CRITICAL
    with priority_scope(BACKGROUND):
        assert get_current_priority() == BACKGROUND
    assert get_current_priority() == CRITICAL


def test_priority_scope_restores_on_exception():
    with pytest.raises(ValueError):
        with priority_scope(BACKGROUND):
            assert get_current_priority() == BACKGROUND
            raise ValueError("boom")
    assert get_current_priority() == CRITICAL


def test_nested_priority_scope_restores_the_outer_value():
    with priority_scope(BACKGROUND):
        assert get_current_priority() == BACKGROUND
        with priority_scope(CRITICAL):
            assert get_current_priority() == CRITICAL
        assert get_current_priority() == BACKGROUND
    assert get_current_priority() == CRITICAL


def test_rejects_unknown_priority():
    with pytest.raises(ValueError):
        with priority_scope("urgent"):
            pass


@pytest.mark.asyncio
async def test_priority_scope_is_visible_across_an_await():
    async def _inner() -> str:
        await asyncio.sleep(0)
        return get_current_priority()

    with priority_scope(BACKGROUND):
        result = await _inner()
    assert result == BACKGROUND


@pytest.mark.asyncio
async def test_concurrent_tasks_do_not_leak_priority_into_each_other():
    """Each asyncio task gets its own copy of the contextvar at
    creation time -- a background job's priority must never bleed into
    a concurrently-running live-scan task, and vice versa."""

    async def _background_task() -> str:
        with priority_scope(BACKGROUND):
            await asyncio.sleep(0.01)
            return get_current_priority()

    async def _critical_task() -> str:
        await asyncio.sleep(0.005)
        return get_current_priority()

    background_result, critical_result = await asyncio.gather(
        _background_task(), _critical_task()
    )
    assert background_result == BACKGROUND
    assert critical_result == CRITICAL
