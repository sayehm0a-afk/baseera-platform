import pytest
import logging
import asyncio
from unittest.mock import AsyncMock, MagicMock

from core.runtime.task_queue.task_queue import TaskQueue
from core.runtime.task_queue.scheduler import IScheduler
from core.runtime.task_queue.priority_queue import IPriorityQueue
from core.runtime.task_queue.retry_policy import IRetryPolicy
from core.runtime.task_queue.dead_letter_queue import IDeadLetterQueue

@pytest.fixture(autouse=True)
def set_logging_level():
    logging.getLogger("src.core.runtime.task_queue.task_queue").setLevel(logging.INFO)

@pytest.fixture
def mock_scheduler() -> AsyncMock:
    mock = AsyncMock(spec=IScheduler)
    mock.get_scheduled_tasks.return_value = []
    return mock

@pytest.fixture
def mock_priority_queue() -> AsyncMock:
    mock = AsyncMock(spec=IPriorityQueue)
    mock.empty.return_value = True
    return mock

@pytest.fixture
def mock_retry_policy() -> AsyncMock:
    mock = AsyncMock(spec=IRetryPolicy)
    mock.should_retry.return_value = False
    return mock

@pytest.fixture
def mock_dead_letter_queue() -> AsyncMock:
    mock = AsyncMock(spec=IDeadLetterQueue)
    return mock

@pytest.fixture
def task_queue(mock_scheduler, mock_priority_queue, mock_retry_policy, mock_dead_letter_queue) -> TaskQueue:
    return TaskQueue(
        scheduler=mock_scheduler,
        priority_queue=mock_priority_queue,
        retry_policy=mock_retry_policy,
        dead_letter_queue=mock_dead_letter_queue
    )

@pytest.mark.asyncio
async def test_task_queue_enqueue_task(task_queue: TaskQueue, mock_scheduler: AsyncMock):
    task_id = "test_task_1"
    task_payload = {"data": "value"}
    handler = AsyncMock()

    await task_queue.enqueue_task(task_id, task_payload, handler)

    mock_scheduler.schedule_task.assert_called_once_with(
        task_id,
        {"payload": task_payload, "handler_id": task_id},
        0,
        0
    )
    assert task_queue._handlers[task_id] == handler

@pytest.mark.asyncio
async def test_task_queue_start_and_stop(task_queue: TaskQueue):
    await task_queue.start()
    assert task_queue._running is True
    assert task_queue._processing_task is not None

    await task_queue.stop()
    assert task_queue._running is False
    assert task_queue._processing_task.done() is True

@pytest.mark.asyncio
async def test_task_queue_process_tasks_from_scheduler_to_priority_queue(task_queue: TaskQueue, mock_scheduler: AsyncMock, mock_priority_queue: AsyncMock):
    task_id = "scheduled_task"
    task_payload = {"data": "scheduled"}
    handler = AsyncMock()
    
    mock_scheduler.get_scheduled_tasks.return_value = [{
        "task_id": task_id,
        "task_payload": {"payload": task_payload, "handler_id": task_id},
        "delay_seconds": 0,
        "priority": 0,
        "status": "scheduled"
    }]
    mock_scheduler.cancel_task.return_value = True
    mock_priority_queue.empty.return_value = True # Ensure nothing is in PQ initially

    await task_queue.enqueue_task(task_id, task_payload, handler)
    await task_queue.start()
    await asyncio.sleep(0.01) # Allow some time for the processing loop to run
    await task_queue.stop()

    mock_scheduler.get_scheduled_tasks.assert_called()
    mock_scheduler.cancel_task.assert_called_once_with(task_id)
    mock_priority_queue.put.assert_called_once()

@pytest.mark.asyncio
async def test_task_queue_execute_task_success(task_queue: TaskQueue, mock_scheduler: AsyncMock, mock_priority_queue: AsyncMock):
    task_id = "exec_task_success"
    task_payload = {"data": "success"}
    handler = AsyncMock()
    handler.return_value = None

    mock_scheduler.get_scheduled_tasks.return_value = [{
        "task_id": task_id,
        "task_payload": {"payload": task_payload, "handler_id": task_id},
        "delay_seconds": 0,
        "priority": 0,
        "status": "scheduled"
    }]
    mock_scheduler.cancel_task.return_value = True
    mock_priority_queue.empty.side_effect = [False, True] # PQ not empty first, then empty
    mock_priority_queue.get.return_value = {
        "task_id": task_id,
        "payload": task_payload,
        "handler_id": task_id,
        "priority": 0
    }

    await task_queue.enqueue_task(task_id, task_payload, handler)
    await task_queue.start()
    await asyncio.sleep(0.01)
    await task_queue.stop()

    handler.assert_called_once_with(task_payload)
    mock_scheduler.schedule_task.assert_called_once() # For initial enqueue
    mock_priority_queue.get.assert_called_once()

@pytest.mark.asyncio
async def test_task_queue_execute_task_failure_retry(task_queue: TaskQueue, mock_scheduler: AsyncMock, mock_priority_queue: AsyncMock, mock_retry_policy: AsyncMock):
    task_id = "exec_task_retry"
    task_payload = {"data": "fail_then_retry"}
    handler = AsyncMock(side_effect=ValueError("Simulated error"))

    mock_retry_policy.should_retry.return_value = True
    mock_retry_policy.get_delay_seconds.return_value = 1

    mock_scheduler.get_scheduled_tasks.return_value = [{
        "task_id": task_id,
        "task_payload": {"payload": task_payload, "handler_id": task_id},
        "delay_seconds": 0,
        "priority": 0,
        "status": "scheduled"
    }]
    mock_scheduler.cancel_task.return_value = True
    mock_priority_queue.empty.side_effect = [False, True] # PQ not empty first, then empty
    mock_priority_queue.get.return_value = {
        "task_id": task_id,
        "payload": task_payload,
        "handler_id": task_id,
        "priority": 0
    }

    await task_queue.enqueue_task(task_id, task_payload, handler)
    await task_queue.start()
    await asyncio.sleep(0.01)
    await task_queue.stop()

    handler.assert_called_once_with(task_payload)
    mock_retry_policy.should_retry.assert_called_once()
    mock_retry_policy.get_delay_seconds.assert_called_once()
    # Expect a re-schedule with incremented attempt_count
    mock_scheduler.schedule_task.assert_called_with(
        task_id,
        {"payload": task_payload, "handler_id": task_id, "attempt_count": 2},
        1,
        0
    )

@pytest.mark.asyncio
async def test_task_queue_execute_task_failure_dlq(task_queue: TaskQueue, mock_scheduler: AsyncMock, mock_priority_queue: AsyncMock, mock_retry_policy: AsyncMock, mock_dead_letter_queue: AsyncMock):
    task_id = "exec_task_dlq"
    task_payload = {"data": "fail_to_dlq"}
    handler = AsyncMock(side_effect=ValueError("Simulated error"))

    mock_retry_policy.should_retry.return_value = False # No retry

    mock_scheduler.get_scheduled_tasks.return_value = [{
        "task_id": task_id,
        "task_payload": {"payload": task_payload, "handler_id": task_id},
        "delay_seconds": 0,
        "priority": 0,
        "status": "scheduled"
    }]
    mock_scheduler.cancel_task.return_value = True
    mock_priority_queue.empty.side_effect = [False, True] # PQ not empty first, then empty
    mock_priority_queue.get.return_value = {
        "task_id": task_id,
        "payload": task_payload,
        "handler_id": task_id,
        "priority": 0
    }

    await task_queue.enqueue_task(task_id, task_payload, handler)
    await task_queue.start()
    await asyncio.sleep(0.01)
    await task_queue.stop()

    handler.assert_called_once_with(task_payload)
    mock_retry_policy.should_retry.assert_called_once()
    mock_dead_letter_queue.enqueue.assert_called_once_with(task_id, task_payload, "Simulated error")

@pytest.mark.asyncio
async def test_task_queue_handler_not_found(task_queue: TaskQueue, mock_scheduler: AsyncMock, mock_priority_queue: AsyncMock, mock_dead_letter_queue: AsyncMock, caplog):
    task_id = "no_handler_task"
    task_payload = {"data": "no_handler"}
    
    mock_scheduler.get_scheduled_tasks.return_value = [{
        "task_id": task_id,
        "task_payload": {"payload": task_payload, "handler_id": "non_existent_handler"},
        "delay_seconds": 0,
        "priority": 0,
        "status": "scheduled"
    }]
    mock_scheduler.cancel_task.return_value = True
    mock_priority_queue.empty.side_effect = [False, True] # PQ not empty first, then empty
    mock_priority_queue.get.return_value = {
        "task_id": task_id,
        "payload": task_payload,
        "handler_id": "non_existent_handler",
        "priority": 0
    }

    # Enqueue the task with a handler, then remove it to simulate a missing handler
    await task_queue.enqueue_task(task_id, task_payload, AsyncMock())
    del task_queue._handlers[task_id]

    await task_queue.start()
    await asyncio.sleep(0.01)
    await task_queue.stop()

    mock_dead_letter_queue.enqueue.assert_called_once_with(task_id, task_payload, "Handler not found")
    assert "Handler for task no_handler_task not found. Moving to DLQ." in caplog.text

@pytest.mark.asyncio
async def test_task_queue_stop_not_running(task_queue: TaskQueue, caplog):
    await task_queue.stop()
    assert "TaskQueue is not running." in caplog.text

@pytest.mark.asyncio
async def test_task_queue_start_already_running(task_queue: TaskQueue, caplog):
    await task_queue.start()
    await task_queue.start()
    assert "TaskQueue is already running." in caplog.text
    await task_queue.stop()
