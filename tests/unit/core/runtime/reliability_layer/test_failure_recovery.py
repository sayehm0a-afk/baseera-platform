import pytest
import logging
from unittest.mock import AsyncMock
from src.core.runtime.reliability_layer.failure_recovery import FailureRecovery


@pytest.fixture(autouse=True)
def set_logging_level():
    logging.getLogger("src.core.runtime.reliability_layer.failure_recovery").setLevel(logging.INFO)


@pytest.fixture
def failure_recovery() -> FailureRecovery:
    return FailureRecovery()


@pytest.mark.asyncio
async def test_failure_recovery_success(failure_recovery: FailureRecovery):
    mock_func = AsyncMock(return_value="Success Result")
    result = await failure_recovery.execute_with_recovery(mock_func)
    assert result == "Success Result"
    mock_func.assert_called_once()


@pytest.mark.asyncio
async def test_failure_recovery_with_fallback_success(failure_recovery: FailureRecovery):
    mock_func = AsyncMock(side_effect=ValueError("Original failure"))
    mock_fallback_func = AsyncMock(return_value="Fallback Result")

    result = await failure_recovery.execute_with_recovery(mock_func, fallback_func=mock_fallback_func)
    assert result == "Fallback Result"
    mock_func.assert_called_once()
    mock_fallback_func.assert_called_once()


@pytest.mark.asyncio
async def test_failure_recovery_with_fallback_and_compensation_success(failure_recovery: FailureRecovery):
    mock_func = AsyncMock(side_effect=ValueError("Original failure"))
    mock_fallback_func = AsyncMock(side_effect=ValueError("Fallback failure"))
    mock_compensation_func = AsyncMock(return_value="Compensation Done")

    with pytest.raises(ValueError, match="Fallback failure"):
        await failure_recovery.execute_with_recovery(mock_func, fallback_func=mock_fallback_func, compensation_func=mock_compensation_func)

    mock_func.assert_called_once()
    mock_fallback_func.assert_called_once()
    mock_compensation_func.assert_called_once()


@pytest.mark.asyncio
async def test_failure_recovery_no_fallback_no_compensation_failure(failure_recovery: FailureRecovery):
    mock_func = AsyncMock(side_effect=ValueError("Original failure"))

    with pytest.raises(ValueError, match="Original failure"):
        await failure_recovery.execute_with_recovery(mock_func)
    mock_func.assert_called_once()


@pytest.mark.asyncio
async def test_failure_recovery_only_compensation_failure(failure_recovery: FailureRecovery):
    mock_func = AsyncMock(side_effect=ValueError("Original failure"))
    mock_compensation_func = AsyncMock(return_value="Compensation Done")

    with pytest.raises(ValueError, match="Original failure"):
        await failure_recovery.execute_with_recovery(mock_func, compensation_func=mock_compensation_func)

    mock_func.assert_called_once()
    mock_compensation_func.assert_called_once()


@pytest.mark.asyncio
async def test_failure_recovery_compensation_fails(failure_recovery: FailureRecovery):
    mock_func = AsyncMock(side_effect=ValueError("Original failure"))
    mock_fallback_func = AsyncMock(side_effect=ValueError("Fallback failure"))
    mock_compensation_func = AsyncMock(side_effect=RuntimeError("Compensation failure"))

    with pytest.raises(ValueError, match="Fallback failure"):
        await failure_recovery.execute_with_recovery(mock_func, fallback_func=mock_fallback_func, compensation_func=mock_compensation_func)

    mock_func.assert_called_once()
    mock_fallback_func.assert_called_once()
    mock_compensation_func.assert_called_once()


@pytest.mark.asyncio
async def test_failure_recovery_compensation_only_fails(failure_recovery: FailureRecovery):
    mock_func = AsyncMock(side_effect=ValueError("Original failure"))
    mock_compensation_func = AsyncMock(side_effect=RuntimeError("Compensation failure"))

    with pytest.raises(ValueError, match="Original failure"):
        await failure_recovery.execute_with_recovery(mock_func, compensation_func=mock_compensation_func)

    mock_func.assert_called_once()
    mock_compensation_func.assert_called_once()
