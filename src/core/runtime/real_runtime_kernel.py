import asyncio
import logging
import signal
from typing import Any, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class RealRuntimeKernel:
    """Production-grade runtime kernel for orchestrating all components."""

    def __init__(self, container: Any):
        """Initialize real runtime kernel."""
        self.container = container
        self.message_bus = None
        self.task_queue = None
        self.agent_runtime = None
        self.service_layer = None
        self.workers = []
        self.is_running = False
        self.start_time = None

    async def initialize(self) -> bool:
        """Initialize all components."""
        try:
            logger.info("Initializing runtime kernel...")

            # Get services from container
            self.message_bus = self.container.get_service("message_bus")
            self.task_queue = self.container.get_service("task_queue")
            self.agent_runtime = self.container.get_service("agent_runtime")
            self.service_layer = self.container.get_service("service_layer")

            if not all([self.message_bus, self.task_queue, self.agent_runtime, self.service_layer]):
                logger.error("Failed to initialize required services")
                return False

            logger.info("Runtime kernel initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Error initializing runtime kernel: {e}")
            return False

    async def start(self) -> bool:
        """Start the runtime kernel."""
        try:
            logger.info("Starting runtime kernel...")
            self.is_running = True
            self.start_time = datetime.now()

            # Setup signal handlers for graceful shutdown
            def signal_handler(sig, frame):
                logger.info("Received shutdown signal")
                asyncio.create_task(self.stop())

            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)

            # Start service layer
            await self.service_layer.start()

            # Start agent runtime
            runtime_task = asyncio.create_task(self.agent_runtime.start())

            # Start workers
            worker_tasks = [asyncio.create_task(worker.start()) for worker in self.workers]

            logger.info("Runtime kernel started successfully")

            # Wait for all tasks
            all_tasks = [runtime_task] + worker_tasks
            await asyncio.gather(*all_tasks, return_exceptions=True)

            return True

        except Exception as e:
            logger.error(f"Error starting runtime kernel: {e}")
            return False

    async def stop(self) -> bool:
        """Stop the runtime kernel gracefully."""
        try:
            logger.info("Stopping runtime kernel...")
            self.is_running = False

            # Stop service layer
            if self.service_layer:
                await self.service_layer.stop()

            # Stop agent runtime
            if self.agent_runtime:
                await self.agent_runtime.stop()

            # Stop workers
            for worker in self.workers:
                await worker.stop()

            # Close connections
            if self.message_bus:
                self.message_bus.close()

            if self.task_queue:
                self.task_queue.close()

            logger.info("Runtime kernel stopped successfully")
            return True

        except Exception as e:
            logger.error(f"Error stopping runtime kernel: {e}")
            return False

    def add_worker(self, worker: Any) -> None:
        """Add a worker to the runtime kernel."""
        self.workers.append(worker)
        logger.info(f"Added worker: {worker.worker_id}")

    def health_check(self) -> Dict[str, bool]:
        """Perform health check on all components."""
        try:
            health_status = {
                "is_running": self.is_running,
                "message_bus": self.message_bus.health_check() if self.message_bus else False,
                "task_queue": self.task_queue.health_check() if self.task_queue else False,
                "service_layer": self.service_layer.health_check() if self.service_layer else False,
            }

            logger.debug(f"Health check: {health_status}")
            return health_status

        except Exception as e:
            logger.error(f"Health check error: {e}")
            return {"error": str(e)}

    async def get_stats(self) -> Dict[str, Any]:
        """Get runtime statistics."""
        try:
            uptime = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0

            stats = {
                "is_running": self.is_running,
                "uptime_seconds": uptime,
                "worker_count": len(self.workers),
            }

            # Add worker stats
            worker_stats = []
            for worker in self.workers:
                worker_stats.append(worker.get_stats())
            stats["workers"] = worker_stats

            # Add service layer stats
            if self.service_layer:
                stats.update(await self.service_layer.get_runtime_stats())

            return stats

        except Exception as e:
            logger.error(f"Error getting runtime stats: {e}")
            return {}
