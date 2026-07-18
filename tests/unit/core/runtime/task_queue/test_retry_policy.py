import pytest
import logging
from core.runtime.task_queue.retry_policy import ExponentialBackoffRetryPolicy, IRetryPolicy

@pytest.fixture(autouse=True)
def set_logging_level():
    logging.getLogger("src.core.runtime.task_queue.retry_policy").setLevel(logging.INFO)

@pytest.fixture
def retry_policy() -> ExponentialBackoffRetryPolicy:
    return ExponentialBackoffRetryPolicy(max_attempts=3, initial_delay=1, max_delay=10)

@pytest.mark.asyncio
async def test_retry_policy_should_retry_true(retry_policy: ExponentialBackoffRetryPolicy):
    task_id = "test_task"
    error = ValueError("Test Error")

    assert await retry_policy.should_retry(task_id, 1, error) is True
    assert await retry_policy.should_retry(task_id, 2, error) is True

@pytest.mark.asyncio
async def test_retry_policy_should_retry_false_max_attempts(retry_policy: ExponentialBackoffRetryPolicy):
    task_id = "test_task"
    error = ValueError("Test Error")

    assert await retry_policy.should_retry(task_id, 3, error) is False
    assert await retry_policy.should_retry(task_id, 4, error) is False

@pytest.mark.asyncio
async def test_retry_policy_get_delay_seconds(retry_policy: ExponentialBackoffRetryPolicy):
    task_id = "test_task"

    assert await retry_policy.get_delay_seconds(task_id, 1) == 1  # initial_delay * (2^0)
    assert await retry_policy.get_delay_seconds(task_id, 2) == 2  # initial_delay * (2^1)
    assert await retry_policy.get_delay_seconds(task_id, 3) == 4  # initial_delay * (2^2)

@pytest.mark.asyncio
async def test_retry_policy_get_delay_seconds_max_delay(retry_policy: ExponentialBackoffRetryPolicy):
    task_id = "test_task"
    # max_delay is 10
    assert await retry_policy.get_delay_seconds(task_id, 4) == 8  # min(10, 1 * (2^3))
    assert await retry_policy.get_delay_seconds(task_id, 5) == 10 # min(10, 1 * (2^4))

@pytest.mark.asyncio
async def test_retry_policy_custom_parameters():
    custom_policy = ExponentialBackoffRetryPolicy(max_attempts=5, initial_delay=2, max_delay=20)
    task_id = "custom_task"
    error = TypeError("Custom Error")

    assert await custom_policy.should_retry(task_id, 1, error) is True
    assert await custom_policy.should_retry(task_id, 5, error) is False
    assert await custom_policy.get_delay_seconds(task_id, 1) == 2
    assert await custom_policy.get_delay_seconds(task_id, 2) == 4
    assert await custom_policy.get_delay_seconds(task_id, 3) == 8
    assert await custom_policy.get_delay_seconds(task_id, 4) == 16
    assert await custom_policy.get_delay_seconds(task_id, 5) == 20
