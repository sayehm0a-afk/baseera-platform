import pytest
import logging
from unittest.mock import AsyncMock, MagicMock
from src.core.runtime.task_queue.scheduler import Scheduler, IScheduler

@pytest.fixture(autouse=True)
def set_logging_level():
    logging.getLogger("src.core.runtime.task_queue.scheduler").setLevel(logging.INFO)

@pytest.fixture
def scheduler() -> Scheduler:
    return Scheduler()

@pytest.mark.asyncio
async def test_scheduler_schedule_task(scheduler: Scheduler):
    task_id = "test_task_1"
    task_payload = {"action": "do_work", "data": 123}
    await scheduler.schedule_task(task_id, task_payload)

    scheduled_tasks = await scheduler.get_scheduled_tasks()
    assert len(scheduled_tasks) == 1
    assert scheduled_tasks[0]["task_id"] == task_id
    assert scheduled_tasks[0]["task_payload"] == task_payload
    assert scheduled_tasks[0]["status"] == "scheduled"

@pytest.mark.asyncio
async def test_scheduler_schedule_task_with_delay_and_priority(scheduler: Scheduler):
    task_id = "test_task_2"
    task_payload = {"action": "delayed_work"}
    delay = 60
    priority = 5
    await scheduler.schedule_task(task_id, task_payload, delay_seconds=delay, priority=priority)

    scheduled_tasks = await scheduler.get_scheduled_tasks()
    assert len(scheduled_tasks) == 1
    assert scheduled_tasks[0]["task_id"] == task_id
    assert scheduled_tasks[0]["delay_seconds"] == delay
    assert scheduled_tasks[0]["priority"] == priority

@pytest.mark.asyncio
async def test_scheduler_cancel_task(scheduler: Scheduler):
    task_id = "task_to_cancel"
    task_payload = {"action": "cancel_me"}
    await scheduler.schedule_task(task_id, task_payload)

    cancelled = await scheduler.cancel_task(task_id)
    assert cancelled is True
    scheduled_tasks = await scheduler.get_scheduled_tasks()
    assert len(scheduled_tasks) == 0

@pytest.mark.asyncio
async def test_scheduler_cancel_non_existent_task(scheduler: Scheduler):
    task_id = "non_existent_task"
    cancelled = await scheduler.cancel_task(task_id)
    assert cancelled is False

@pytest.mark.asyncio
async def test_scheduler_get_scheduled_tasks_limit(scheduler: Scheduler):
    for i in range(5):
        await scheduler.schedule_task(f"task_{i}", {"data": i})
    
    tasks = await scheduler.get_scheduled_tasks(limit=3)
    assert len(tasks) == 3
    assert tasks[0]["task_id"] == "task_0"
    assert tasks[2]["task_id"] == "task_2"

@pytest.mark.asyncio
async def test_scheduler_overwrite_task(scheduler: Scheduler, caplog):
    task_id = "overwrite_task"
    payload_1 = {"data": 1}
    payload_2 = {"data": 2}

    await scheduler.schedule_task(task_id, payload_1)
    await scheduler.schedule_task(task_id, payload_2)

    scheduled_tasks = await scheduler.get_scheduled_tasks()
    assert len(scheduled_tasks) == 1
    assert scheduled_tasks[0]["task_id"] == task_id
    assert scheduled_tasks[0]["task_payload"] == payload_2
    assert "Task overwrite_task already scheduled. Overwriting." in caplog.text
