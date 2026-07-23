import pytest
import logging
import asyncio
from unittest.mock import AsyncMock
from src.core.runtime.reliability_layer.compensation import Compensation, ICompensation


@pytest.fixture(autouse=True)
def set_logging_level():
    logging.getLogger("src.core.runtime.reliability_layer.compensation").setLevel(logging.INFO)


@pytest.fixture
def compensation_manager() -> Compensation:
    return Compensation()


@pytest.mark.asyncio
async def test_compensation_register_and_run_success(compensation_manager: Compensation):
    mock_compensation_func = AsyncMock(return_value="Compensated")
    operation_id = "op_123"

    await compensation_manager.compensate(operation_id, mock_compensation_func, "arg1", kwarg1="val1")
    await compensation_manager.run_compensation(operation_id)

    mock_compensation_func.assert_called_once_with("arg1", kwarg1="val1")
    assert operation_id not in compensation_manager._compensations


@pytest.mark.asyncio
async def test_compensation_run_non_existent_operation(compensation_manager: Compensation, caplog):
    operation_id = "non_existent_op"
    await compensation_manager.run_compensation(operation_id)

    assert f"No compensation registered for operation {operation_id}." in caplog.text


@pytest.mark.asyncio
async def test_compensation_run_failure(compensation_manager: Compensation, caplog):
    mock_compensation_func = AsyncMock(side_effect=ValueError("Compensation failed"))
    operation_id = "op_fail"

    await compensation_manager.compensate(operation_id, mock_compensation_func)
    await compensation_manager.run_compensation(operation_id)

    mock_compensation_func.assert_called_once()
    assert f"Compensation for operation {operation_id} failed: Compensation failed" in caplog.text
    assert operation_id not in compensation_manager._compensations


@pytest.mark.asyncio
async def test_compensation_clear_compensation(compensation_manager: Compensation):
    mock_compensation_func = AsyncMock()
    operation_id = "op_clear"

    await compensation_manager.compensate(operation_id, mock_compensation_func)
    assert operation_id in compensation_manager._compensations

    await compensation_manager.clear_compensation(operation_id)
    assert operation_id not in compensation_manager._compensations


@pytest.mark.asyncio
async def test_compensation_clear_non_existent_compensation(compensation_manager: Compensation, caplog):
    operation_id = "non_existent_clear"
    await compensation_manager.clear_compensation(operation_id)

    assert f"No compensation to clear for operation {operation_id}." in caplog.text


@pytest.mark.asyncio
async def test_compensation_register_multiple_compensations(compensation_manager: Compensation):
    mock_func1 = AsyncMock()
    mock_func2 = AsyncMock()
    op_id1 = "op_a"
    op_id2 = "op_b"

    await compensation_manager.compensate(op_id1, mock_func1)
    await compensation_manager.compensate(op_id2, mock_func2)

    assert op_id1 in compensation_manager._compensations
    assert op_id2 in compensation_manager._compensations

    await compensation_manager.run_compensation(op_id1)
    mock_func1.assert_called_once()
    assert op_id1 not in compensation_manager._compensations
    assert op_id2 in compensation_manager._compensations

    await compensation_manager.run_compensation(op_id2)
    mock_func2.assert_called_once()
    assert op_id2 not in compensation_manager._compensations
