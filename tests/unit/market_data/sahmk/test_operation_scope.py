"""Unit tests for the SAHMK operation-scope contextvar mechanism (SAHMK
quota optimization mandate, 2026-08-16) -- mirrors
test_request_priority.py's own test structure, since operation_scope.py
is deliberately the same contextvar pattern."""

import asyncio

import pytest

from src.market_data.sahmk.operation_scope import (
    ADMIN_DIAGNOSTICS,
    INGESTION,
    MARKET_SCAN,
    STOCK_DETAIL,
    get_current_operation,
    operation_scope,
)


def test_default_operation_is_none():
    assert get_current_operation() is None


def test_operation_scope_sets_and_restores():
    assert get_current_operation() is None
    with operation_scope(STOCK_DETAIL):
        assert get_current_operation() == STOCK_DETAIL
    assert get_current_operation() is None


def test_operation_scope_restores_on_exception():
    with pytest.raises(ValueError):
        with operation_scope(MARKET_SCAN):
            assert get_current_operation() == MARKET_SCAN
            raise ValueError("boom")
    assert get_current_operation() is None


def test_nested_operation_scope_restores_the_outer_value():
    with operation_scope(INGESTION):
        assert get_current_operation() == INGESTION
        with operation_scope(ADMIN_DIAGNOSTICS):
            assert get_current_operation() == ADMIN_DIAGNOSTICS
        assert get_current_operation() == INGESTION
    assert get_current_operation() is None


@pytest.mark.asyncio
async def test_operation_scope_is_visible_across_an_await():
    async def _inner() -> str:
        await asyncio.sleep(0)
        return get_current_operation()

    with operation_scope(STOCK_DETAIL):
        result = await _inner()
    assert result == STOCK_DETAIL


@pytest.mark.asyncio
async def test_concurrent_tasks_do_not_leak_operation_into_each_other():
    """Each asyncio task gets its own copy of the contextvar at creation
    time -- an ingestion job's subsystem tag must never bleed into a
    concurrently-running stock-detail request's SAHMK calls, and vice
    versa."""

    async def _ingestion_task() -> str:
        with operation_scope(INGESTION):
            await asyncio.sleep(0.01)
            return get_current_operation()

    async def _stock_detail_task() -> str:
        with operation_scope(STOCK_DETAIL):
            await asyncio.sleep(0.005)
            return get_current_operation()

    ingestion_result, stock_detail_result = await asyncio.gather(
        _ingestion_task(), _stock_detail_task()
    )
    assert ingestion_result == INGESTION
    assert stock_detail_result == STOCK_DETAIL
