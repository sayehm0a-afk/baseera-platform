"""
Integration tests for production-grade components.
"""

import asyncio
import pytest
import os
from unittest.mock import MagicMock, patch


def is_redis_available():
    """Check if Redis is available."""
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, socket_connect_timeout=1)
        r.ping()
        return True
    except:
        return False


class TestRedisMessageBus:
    """Test Redis message bus."""
    
    @pytest.mark.skipif(not is_redis_available(), reason="Redis not available")
    def test_redis_message_bus_initialization(self):
        """Test Redis message bus initialization."""
        from src.core.messaging.redis_message_bus import RedisMessageBus
        
        bus = RedisMessageBus(host='localhost', port=6379)
        assert bus.health_check()
        bus.close()
    
    @pytest.mark.skipif(not is_redis_available(), reason="Redis not available")
    def test_redis_message_bus_publish_subscribe(self):
        """Test Redis message bus publish/subscribe."""
        from src.core.messaging.redis_message_bus import RedisMessageBus
        
        bus = RedisMessageBus(host='localhost', port=6379)
        
        # Test publish
        result = bus.publish("test:topic", {"message": "test"})
        assert result is not None
        
        bus.close()
    
    @pytest.mark.skipif(not is_redis_available(), reason="Redis not available")
    def test_redis_message_bus_queue_operations(self):
        """Test Redis message bus queue operations."""
        from src.core.messaging.redis_message_bus import RedisMessageBus
        
        bus = RedisMessageBus(host='localhost', port=6379)
        
        # Clear queue first
        bus.clear_queue("test:queue")
        
        # Test enqueue
        assert bus.enqueue_task("test:queue", {"task_id": "1", "data": "test"})
        
        # Test queue length
        assert bus.get_queue_length("test:queue") == 1
        
        # Test dequeue
        task = bus.dequeue_task("test:queue", timeout=1)
        assert task is not None
        assert task["task_id"] == "1"
        
        bus.close()


class TestRealTaskQueue:
    """Test real task queue."""
    
    @pytest.mark.skipif(not is_redis_available(), reason="Redis not available")
    def test_real_task_queue_initialization(self):
        """Test real task queue initialization."""
        from src.core.runtime.task_queue.real_task_queue import RealTaskQueue
        
        queue = RealTaskQueue(host='localhost', port=6379)
        assert queue.health_check()
        queue.close()
    
    @pytest.mark.skipif(not is_redis_available(), reason="Redis not available")
    def test_real_task_queue_enqueue_dequeue(self):
        """Test real task queue enqueue/dequeue."""
        from src.core.runtime.task_queue.real_task_queue import RealTaskQueue
        
        queue = RealTaskQueue(host='localhost', port=6379)
        
        # Clear queue first
        queue.clear_queue()
        
        # Test enqueue
        task = {"task_id": "1", "task_type": "analysis", "data": {"key": "value"}}
        assert queue.enqueue_task(task, priority=1)
        
        # Test task count
        assert queue.get_task_count() == 1
        
        # Test dequeue
        dequeued_task = queue.dequeue_task()
        assert dequeued_task is not None
        assert dequeued_task["task_id"] == "1"
        
        queue.close()
    
    @pytest.mark.skipif(not is_redis_available(), reason="Redis not available")
    def test_real_task_queue_dead_letter(self):
        """Test real task queue dead letter queue."""
        from src.core.runtime.task_queue.real_task_queue import RealTaskQueue
        
        queue = RealTaskQueue(host='localhost', port=6379)
        
        # Test move to dead letter
        task = {"task_id": "1", "task_type": "analysis"}
        assert queue.move_to_dead_letter(task, "Test error")
        
        # Test dead letter count
        assert queue.get_dead_letter_count() >= 1
        
        queue.close()


class TestRealWorker:
    """Test real worker."""
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not is_redis_available(), reason="Redis not available")
    async def test_real_worker_initialization(self):
        """Test real worker initialization."""
        from src.core.runtime.worker.real_worker import RealWorker
        from src.core.runtime.task_queue.real_task_queue import RealTaskQueue
        
        queue = RealTaskQueue(host='localhost', port=6379)
        worker = RealWorker("test-worker", queue)
        
        assert worker.worker_id == "test-worker"
        assert worker.processed_count == 0
        assert worker.failed_count == 0
        
        queue.close()
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not is_redis_available(), reason="Redis not available")
    async def test_real_worker_handler_registration(self):
        """Test real worker handler registration."""
        from src.core.runtime.worker.real_worker import RealWorker
        from src.core.runtime.task_queue.real_task_queue import RealTaskQueue
        
        queue = RealTaskQueue(host='localhost', port=6379)
        worker = RealWorker("test-worker", queue)
        
        # Register handler
        def test_handler(task):
            return True
        
        worker.register_handler("test_task", test_handler)
        assert "test_task" in worker.handlers
        
        queue.close()


class TestRealAgentRuntime:
    """Test real agent runtime."""
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not is_redis_available(), reason="Redis not available")
    async def test_real_agent_runtime_initialization(self):
        """Test real agent runtime initialization."""
        from src.core.runtime.real_agent_runtime import RealAgentRuntime
        from src.core.messaging.redis_message_bus import RedisMessageBus
        from src.core.runtime.task_queue.real_task_queue import RealTaskQueue
        
        message_bus = RedisMessageBus(host='localhost', port=6379)
        task_queue = RealTaskQueue(host='localhost', port=6379)
        
        runtime = RealAgentRuntime(message_bus, task_queue)
        assert runtime.is_running is False
        
        message_bus.close()
        task_queue.close()
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not is_redis_available(), reason="Redis not available")
    async def test_real_agent_runtime_agent_registration(self):
        """Test real agent runtime agent registration."""
        from src.core.runtime.real_agent_runtime import RealAgentRuntime
        from src.core.messaging.redis_message_bus import RedisMessageBus
        from src.core.runtime.task_queue.real_task_queue import RealTaskQueue
        
        message_bus = RedisMessageBus(host='localhost', port=6379)
        task_queue = RealTaskQueue(host='localhost', port=6379)
        
        runtime = RealAgentRuntime(message_bus, task_queue)
        
        # Mock agent
        mock_agent = MagicMock()
        
        # Register agent
        result = await runtime.register_agent("agent-1", mock_agent)
        assert result is True
        assert "agent-1" in runtime.agents
        
        message_bus.close()
        task_queue.close()


class TestRealServiceLayer:
    """Test real service layer."""
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not is_redis_available(), reason="Redis not available")
    async def test_real_service_layer_initialization(self):
        """Test real service layer initialization."""
        from src.core.runtime.real_service_layer import RealServiceLayer
        from src.core.messaging.redis_message_bus import RedisMessageBus
        from src.core.runtime.task_queue.real_task_queue import RealTaskQueue
        from src.core.runtime.real_agent_runtime import RealAgentRuntime
        
        message_bus = RedisMessageBus(host='localhost', port=6379)
        task_queue = RealTaskQueue(host='localhost', port=6379)
        agent_runtime = RealAgentRuntime(message_bus, task_queue)
        
        service_layer = RealServiceLayer(message_bus, task_queue, agent_runtime)
        assert service_layer.is_running is False
        
        message_bus.close()
        task_queue.close()
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not is_redis_available(), reason="Redis not available")
    async def test_real_service_layer_health_check(self):
        """Test real service layer health check."""
        from src.core.runtime.real_service_layer import RealServiceLayer
        from src.core.messaging.redis_message_bus import RedisMessageBus
        from src.core.runtime.task_queue.real_task_queue import RealTaskQueue
        from src.core.runtime.real_agent_runtime import RealAgentRuntime
        
        message_bus = RedisMessageBus(host='localhost', port=6379)
        task_queue = RealTaskQueue(host='localhost', port=6379)
        agent_runtime = RealAgentRuntime(message_bus, task_queue)
        
        service_layer = RealServiceLayer(message_bus, task_queue, agent_runtime)
        
        # Health check should pass
        assert service_layer.health_check() is True
        
        message_bus.close()
        task_queue.close()


class TestDependencyInjection:
    """Test dependency injection container."""
    
    def test_dependency_container_registration(self):
        """Test dependency container registration."""
        from src.core.runtime.dependency_injection import DependencyContainer
        
        container = DependencyContainer()
        
        # Register service
        def create_service():
            return "test_service"
        
        container.register_service("test", create_service, singleton=True)
        
        # Get service
        service = container.get_service("test")
        assert service == "test_service"
        
        # Get service again (should be same instance)
        service2 = container.get_service("test")
        assert service is service2
    
    def test_dependency_container_instance_registration(self):
        """Test dependency container instance registration."""
        from src.core.runtime.dependency_injection import DependencyContainer
        
        container = DependencyContainer()
        
        # Register instance
        instance = {"key": "value"}
        container.register_instance("test_instance", instance)
        
        # Get instance
        retrieved = container.get_service("test_instance")
        assert retrieved is instance


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
