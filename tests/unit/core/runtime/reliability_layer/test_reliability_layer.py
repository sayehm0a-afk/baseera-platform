import pytest
import logging
import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.core.runtime.reliability_layer.reliability_layer import ReliabilityLayer, IReliabilityLayer
from src.core.runtime.reliability_layer.circuit_breaker import ICircuitBreaker, CircuitBreakerOpenError
from src.core.runtime.reliability_layer.failure_recovery import IFailureRecovery
from src.core.runtime.reliability_layer.compensation import ICompensation


@pytest.fixture(autouse=True)
def set_logging_level():
    logging.getLogger("src.core.runtime.reliability_layer.reliability_layer").setLevel(logging.INFO)


@pytest.fixture
def mock_circuit_breaker() -> AsyncMock:
    mock = AsyncMock(spec=ICircuitBreaker)

    async def _cb_execute_side_effect(func, *args, **kwargs):
        return await func(*args, **kwargs)
    mock.execute.side_effect = _cb_execute_side_effect
    return mock


@pytest.fixture
def mock_failure_recovery() -> AsyncMock:
    return AsyncMock(spec=IFailureRecovery)


@pytest.fixture
def mock_compensation() -> AsyncMock:
    return AsyncMock(spec=ICompensation)


@pytest.fixture
def reliability_layer(mock_circuit_breaker, mock_failure_recovery, mock_compensation) -> ReliabilityLayer:
    return ReliabilityLayer(
        circuit_breaker=mock_circuit_breaker,
        failure_recovery=mock_failure_recovery,
        compensation=mock_compensation
    )


@pytest.mark.asyncio
async def test_reliability_layer_execute_reliable_success(reliability_layer: ReliabilityLayer, mock_circuit_breaker: AsyncMock, mock_compensation: AsyncMock):
    mock_func = AsyncMock(return_value="Success Result")
    operation_id = "op_success"

    result = await reliability_layer.execute_reliable(mock_func, operation_id=operation_id)

    assert result == "Success Result"
    mock_circuit_breaker.execute.assert_called_once_with(mock_func, *(), **{})
    mock_compensation.compensate.assert_not_called()
    mock_compensation.clear_compensation.assert_called_once_with(operation_id)


@pytest.mark.asyncio
async def test_reliability_layer_execute_reliable_circuit_breaker_open_with_fallback(reliability_layer: ReliabilityLayer, mock_circuit_breaker: AsyncMock, mock_failure_recovery: AsyncMock, mock_compensation: AsyncMock):
    mock_func = AsyncMock()
    mock_fallback_func = AsyncMock(return_value="Fallback Result")
    operation_id = "op_cb_fallback"

    mock_circuit_breaker.execute.side_effect = CircuitBreakerOpenError("CB Open")

    result = await reliability_layer.execute_reliable(mock_func, fallback_func=mock_fallback_func, operation_id=operation_id)

    assert result == "Fallback Result"
    mock_circuit_breaker.execute.assert_called_once_with(mock_func, *(), **{})
    mock_fallback_func.assert_called_once_with(*(), **{})
    mock_compensation.compensate.assert_not_called()
    mock_compensation.run_compensation.assert_not_called()
    mock_compensation.clear_compensation.assert_not_called()


@pytest.mark.asyncio
async def test_reliability_layer_execute_reliable_circuit_breaker_open_no_fallback(reliability_layer: ReliabilityLayer, mock_circuit_breaker: AsyncMock, mock_compensation: AsyncMock):
    mock_func = AsyncMock()
    operation_id = "op_cb_no_fallback"

    mock_circuit_breaker.execute.side_effect = CircuitBreakerOpenError("CB Open")

    with pytest.raises(CircuitBreakerOpenError, match="CB Open"):
        await reliability_layer.execute_reliable(mock_func, operation_id=operation_id)

    mock_circuit_breaker.execute.assert_called_once_with(mock_func, *(), **{})
    mock_compensation.compensate.assert_not_called()
    mock_compensation.run_compensation.assert_called_once_with(operation_id)
    mock_compensation.clear_compensation.assert_not_called()


@pytest.mark.asyncio
async def test_reliability_layer_execute_reliable_failure_recovery_with_compensation(reliability_layer: ReliabilityLayer, mock_circuit_breaker: AsyncMock, mock_failure_recovery: AsyncMock, mock_compensation: AsyncMock):
    mock_func = AsyncMock(side_effect=ValueError("Original Failure"))
    mock_fallback_func = AsyncMock(return_value="Fallback Result")
    mock_compensation_func = AsyncMock(return_value="Compensation Done")
    operation_id = "op_fr_comp"

    mock_failure_recovery.execute_with_recovery.return_value = "Recovery Result"

    result = await reliability_layer.execute_reliable(mock_func, fallback_func=mock_fallback_func, compensation_func=mock_compensation_func, operation_id=operation_id)

    assert result == "Recovery Result"
    mock_circuit_breaker.execute.assert_called_once_with(mock_func, *(), **{})
    mock_failure_recovery.execute_with_recovery.assert_called_once_with(mock_func, mock_fallback_func, mock_compensation_func, *(), **{})
    mock_compensation.compensate.assert_called_once_with(operation_id, mock_compensation_func, *(), **{})
    mock_compensation.run_compensation.assert_not_called()
    mock_compensation.clear_compensation.assert_not_called()


@pytest.mark.asyncio
async def test_reliability_layer_execute_reliable_failure_recovery_fails_with_compensation(reliability_layer: ReliabilityLayer, mock_circuit_breaker: AsyncMock, mock_failure_recovery: AsyncMock, mock_compensation: AsyncMock):
    mock_func = AsyncMock(side_effect=ValueError("Original Failure"))
    mock_compensation_func = AsyncMock(return_value="Compensation Done")
    operation_id = "op_fr_fails_comp"

    mock_failure_recovery.execute_with_recovery.side_effect = RuntimeError("Recovery Failed")

    with pytest.raises(RuntimeError, match="Recovery Failed"):
        await reliability_layer.execute_reliable(mock_func, compensation_func=mock_compensation_func, operation_id=operation_id)

    mock_circuit_breaker.execute.assert_called_once_with(mock_func, *(), **{})
    mock_failure_recovery.execute_with_recovery.assert_called_once_with(mock_func, None, mock_compensation_func, *(), **{})
    mock_compensation.compensate.assert_called_once_with(operation_id, mock_compensation_func, *(), **{})
    mock_compensation.run_compensation.assert_called_once_with(operation_id)
    mock_compensation.clear_compensation.assert_not_called()


@pytest.mark.asyncio
async def test_reliability_layer_execute_reliable_no_circuit_breaker(reliability_layer: ReliabilityLayer, mock_circuit_breaker: AsyncMock, mock_failure_recovery: AsyncMock, mock_compensation: AsyncMock):
    mock_func = AsyncMock(return_value="Direct Result")
    operation_id = "op_no_cb"

    result = await reliability_layer.execute_reliable(mock_func, operation_id=operation_id, use_circuit_breaker=False)

    assert result == "Direct Result"
    mock_circuit_breaker.execute.assert_not_called()
    mock_func.assert_called_once_with(*(), **{})
    mock_compensation.compensate.assert_not_called()
    mock_compensation.clear_compensation.assert_called_once_with(operation_id)


@pytest.mark.asyncio
async def test_reliability_layer_initialization_with_defaults():
    layer = ReliabilityLayer()
    assert isinstance(layer._circuit_breaker, ICircuitBreaker)
    assert isinstance(layer._failure_recovery, IFailureRecovery)
    assert isinstance(layer._compensation, ICompensation)


@pytest.mark.asyncio
async def test_reliability_layer_initialization_with_provided_instances(mock_circuit_breaker, mock_failure_recovery, mock_compensation):
    layer = ReliabilityLayer(
        circuit_breaker=mock_circuit_breaker,
        failure_recovery=mock_failure_recovery,
        compensation=mock_compensation
    )
    assert layer._circuit_breaker == mock_circuit_breaker
    assert layer._failure_recovery == mock_failure_recovery
    assert layer._compensation == mock_compensation
