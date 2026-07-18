import pytest
import logging
import asyncio
from unittest.mock import AsyncMock
from core.runtime.reliability_layer.circuit_breaker import CircuitBreaker, CircuitBreakerState, CircuitBreakerOpenError

@pytest.fixture(autouse=True)
def set_logging_level():
    logging.getLogger("src.core.runtime.reliability_layer.circuit_breaker").setLevel(logging.INFO)

@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    return CircuitBreaker(failure_threshold=3, recovery_timeout=0.1, expected_successes=1)

@pytest.mark.asyncio
async def test_circuit_breaker_initial_state_closed(circuit_breaker: CircuitBreaker):
    assert circuit_breaker.state == CircuitBreakerState.CLOSED

@pytest.mark.asyncio
async def test_circuit_breaker_closed_to_open_on_failures(circuit_breaker: CircuitBreaker):
    mock_func = AsyncMock(side_effect=ValueError("Simulated failure"))

    for _ in range(circuit_breaker._failure_threshold - 1):
        with pytest.raises(ValueError):
            await circuit_breaker.execute(mock_func)
        assert circuit_breaker.state == CircuitBreakerState.CLOSED

    with pytest.raises(ValueError):
        await circuit_breaker.execute(mock_func)
    assert circuit_breaker.state == CircuitBreakerState.OPEN

@pytest.mark.asyncio
async def test_circuit_breaker_open_prevents_execution(circuit_breaker: CircuitBreaker):
    mock_func = AsyncMock(side_effect=ValueError("Simulated failure"))

    # Transition to OPEN state
    for _ in range(circuit_breaker._failure_threshold):
        with pytest.raises(ValueError):
            await circuit_breaker.execute(mock_func)
    assert circuit_breaker.state == CircuitBreakerState.OPEN

    # Attempt execution while OPEN
    with pytest.raises(CircuitBreakerOpenError):
        await circuit_breaker.execute(mock_func)
    assert mock_func.call_count == circuit_breaker._failure_threshold # Should not be called again

@pytest.mark.asyncio
async def test_circuit_breaker_open_to_half_open_after_timeout(circuit_breaker: CircuitBreaker):
    mock_func = AsyncMock(side_effect=ValueError("Simulated failure"))

    # Transition to OPEN state
    for _ in range(circuit_breaker._failure_threshold):
        with pytest.raises(ValueError):
            await circuit_breaker.execute(mock_func)
    assert circuit_breaker.state == CircuitBreakerState.OPEN

    await asyncio.sleep(circuit_breaker._recovery_timeout + 0.01) # Wait for timeout

    # First attempt after timeout should transition to HALF-OPEN
    mock_func.side_effect = None # Make it succeed
    mock_func.return_value = "Success"
    result = await circuit_breaker.execute(mock_func)
    assert result == "Success"
    assert circuit_breaker.state == CircuitBreakerState.CLOSED # Should immediately close on success

@pytest.mark.asyncio
async def test_circuit_breaker_half_open_to_open_on_failure(circuit_breaker: CircuitBreaker):
    mock_func = AsyncMock(side_effect=ValueError("Simulated failure"))

    # Transition to OPEN state
    for _ in range(circuit_breaker._failure_threshold):
        with pytest.raises(ValueError):
            await circuit_breaker.execute(mock_func)
    assert circuit_breaker.state == CircuitBreakerState.OPEN

    await asyncio.sleep(circuit_breaker._recovery_timeout + 0.01) # Wait for timeout

    # Attempt execution while HALF-OPEN, but it fails
    with pytest.raises(ValueError):
        await circuit_breaker.execute(mock_func)
    assert circuit_breaker.state == CircuitBreakerState.OPEN # Should go back to OPEN

@pytest.mark.asyncio
async def test_circuit_breaker_half_open_to_closed_on_success(circuit_breaker: CircuitBreaker):
    mock_func = AsyncMock(side_effect=ValueError("Simulated failure"))

    # Transition to OPEN state
    for _ in range(circuit_breaker._failure_threshold):
        with pytest.raises(ValueError):
            await circuit_breaker.execute(mock_func)
    assert circuit_breaker.state == CircuitBreakerState.OPEN

    await asyncio.sleep(circuit_breaker._recovery_timeout + 0.01) # Wait for timeout

    # Attempt execution while HALF-OPEN, it succeeds
    mock_func.side_effect = None
    mock_func.return_value = "Success"
    result = await circuit_breaker.execute(mock_func)
    assert result == "Success"
    assert circuit_breaker.state == CircuitBreakerState.CLOSED # Should close

@pytest.mark.asyncio
async def test_circuit_breaker_closed_on_success_resets_failures(circuit_breaker: CircuitBreaker):
    mock_func = AsyncMock(side_effect=[ValueError("Fail 1"), ValueError("Fail 2"), "Success"])

    with pytest.raises(ValueError):
        await circuit_breaker.execute(mock_func)
    assert circuit_breaker._failure_count == 1

    with pytest.raises(ValueError):
        await circuit_breaker.execute(mock_func)
    assert circuit_breaker._failure_count == 2

    # This success should reset the failure count
    result = await circuit_breaker.execute(mock_func)
    assert result == "Success"
    assert circuit_breaker._failure_count == 0
    assert circuit_breaker.state == CircuitBreakerState.CLOSED

@pytest.mark.asyncio
async def test_circuit_breaker_multiple_expected_successes_half_open_to_closed():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1, expected_successes=2)
    mock_func = AsyncMock(side_effect=ValueError("Fail"))

    # Open the circuit
    with pytest.raises(ValueError):
        await cb.execute(mock_func)
    assert cb.state == CircuitBreakerState.OPEN

    await asyncio.sleep(cb._recovery_timeout + 0.01)

    # First success in HALF-OPEN
    mock_func.side_effect = None
    mock_func.return_value = "Success 1"
    result1 = await cb.execute(mock_func)
    assert result1 == "Success 1"
    assert cb.state == CircuitBreakerState.HALF_OPEN # Still HALF-OPEN
    assert cb._success_count == 1

    # Second success in HALF-OPEN
    mock_func.return_value = "Success 2"
    result2 = await cb.execute(mock_func)
    assert result2 == "Success 2"
    assert cb.state == CircuitBreakerState.CLOSED # Now CLOSED
    assert cb._success_count == 0
