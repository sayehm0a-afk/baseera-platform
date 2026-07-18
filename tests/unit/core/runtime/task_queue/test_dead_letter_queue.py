import pytest
import logging
from core.runtime.task_queue.dead_letter_queue import DeadLetterQueue, IDeadLetterQueue

@pytest.fixture(autouse=True)
def set_logging_level():
    logging.getLogger("src.core.runtime.task_queue.dead_letter_queue").setLevel(logging.INFO)

@pytest.fixture
def dlq() -> DeadLetterQueue:
    return DeadLetterQueue()

@pytest.mark.asyncio
async def test_dlq_enqueue_and_size(dlq: DeadLetterQueue):
    task_id = "failed_task_1"
    task_payload = {"data": "some_data"}
    error = "Task failed unexpectedly"

    await dlq.enqueue(task_id, task_payload, error)
    assert await dlq.size() == 1

    enqueued_task = (await dlq.dequeue())[0]
    assert enqueued_task["task_id"] == task_id
    assert enqueued_task["task_payload"] == task_payload
    assert enqueued_task["error"] == error

@pytest.mark.asyncio
async def test_dlq_dequeue_empty(dlq: DeadLetterQueue):
    assert await dlq.dequeue() == []

@pytest.mark.asyncio
async def test_dlq_remove_task(dlq: DeadLetterQueue):
    task_id = "task_to_remove"
    await dlq.enqueue(task_id, {"data": "remove_me"}, "Error")
    assert await dlq.size() == 1

    removed = await dlq.remove(task_id)
    assert removed is True
    assert await dlq.size() == 0

@pytest.mark.asyncio
async def test_dlq_remove_non_existent_task(dlq: DeadLetterQueue):
    task_id = "non_existent"
    removed = await dlq.remove(task_id)
    assert removed is False

@pytest.mark.asyncio
async def test_dlq_overwrite_enqueue(dlq: DeadLetterQueue, caplog):
    task_id = "overwrite_task"
    payload_1 = {"data": 1}
    error_1 = "Error 1"
    payload_2 = {"data": 2}
    error_2 = "Error 2"

    await dlq.enqueue(task_id, payload_1, error_1)
    await dlq.enqueue(task_id, payload_2, error_2)

    assert await dlq.size() == 1
    enqueued_task = (await dlq.dequeue())[0]
    assert enqueued_task["task_payload"] == payload_2
    assert enqueued_task["error"] == error_2
    assert "Task overwrite_task already in DLQ. Overwriting." in caplog.text

@pytest.mark.asyncio
async def test_dlq_dequeue_limit(dlq: DeadLetterQueue):
    for i in range(5):
        await dlq.enqueue(f"task_{i}", {"data": i}, f"Error {i}")
    
    dequeued_tasks = await dlq.dequeue(limit=3)
    assert len(dequeued_tasks) == 3
    assert await dlq.size() == 2
    assert dequeued_tasks[0]["task_id"] == "task_0"
    assert dequeued_tasks[2]["task_id"] == "task_2"

    remaining_tasks = await dlq.dequeue(limit=5)
    assert len(remaining_tasks) == 2
    assert await dlq.size() == 0
    assert remaining_tasks[0]["task_id"] == "task_3"
    assert remaining_tasks[1]["task_id"] == "task_4"
