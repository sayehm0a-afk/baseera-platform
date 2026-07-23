import pytest
import logging
from src.core.runtime.task_queue.priority_queue import PriorityQueue, IPriorityQueue


@pytest.fixture(autouse=True)
def set_logging_level():
    logging.getLogger("src.core.runtime.task_queue.priority_queue").setLevel(logging.INFO)


@pytest.fixture
def priority_queue() -> PriorityQueue:
    return PriorityQueue()


@pytest.mark.asyncio
async def test_priority_queue_put_and_get_basic(priority_queue: PriorityQueue):
    await priority_queue.put("low_priority_item", priority=1)
    await priority_queue.put("high_priority_item", priority=10)
    await priority_queue.put("medium_priority_item", priority=5)

    assert await priority_queue.get() == "high_priority_item"
    assert await priority_queue.get() == "medium_priority_item"
    assert await priority_queue.get() == "low_priority_item"


@pytest.mark.asyncio
async def test_priority_queue_get_empty(priority_queue: PriorityQueue):
    with pytest.raises(IndexError, match="get from an empty priority queue"):
        await priority_queue.get()


@pytest.mark.asyncio
async def test_priority_queue_qsize(priority_queue: PriorityQueue):
    assert await priority_queue.qsize() == 0
    await priority_queue.put("item1")
    assert await priority_queue.qsize() == 1
    await priority_queue.put("item2")
    assert await priority_queue.qsize() == 2
    await priority_queue.get()
    assert await priority_queue.qsize() == 1


@pytest.mark.asyncio
async def test_priority_queue_empty(priority_queue: PriorityQueue):
    assert await priority_queue.empty() is True
    await priority_queue.put("item")
    assert await priority_queue.empty() is False
    await priority_queue.get()
    assert await priority_queue.empty() is True


@pytest.mark.asyncio
async def test_priority_queue_same_priority_order(priority_queue: PriorityQueue):
    await priority_queue.put("item_a", priority=5)
    await priority_queue.put("item_b", priority=5)
    await priority_queue.put("item_c", priority=5)

    # Items with same priority should be retrieved in insertion order (due to entry_id)
    assert await priority_queue.get() == "item_a"
    assert await priority_queue.get() == "item_b"
    assert await priority_queue.get() == "item_c"


@pytest.mark.asyncio
async def test_priority_queue_mixed_priorities(priority_queue: PriorityQueue):
    await priority_queue.put("item_1_p1", priority=1)
    await priority_queue.put("item_2_p10", priority=10)
    await priority_queue.put("item_3_p5", priority=5)
    await priority_queue.put("item_4_p10", priority=10)
    await priority_queue.put("item_5_p1", priority=1)

    assert await priority_queue.get() == "item_2_p10"
    assert await priority_queue.get() == "item_4_p10"
    assert await priority_queue.get() == "item_3_p5"
    assert await priority_queue.get() == "item_1_p1"
    assert await priority_queue.get() == "item_5_p1"
