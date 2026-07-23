import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Agent status enumeration."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    TERMINATED = "terminated"


class RealAgentRuntime:
    """Production-grade agent runtime for managing agent lifecycle."""

    def __init__(self, message_bus: Any, task_queue: Any):
        """Initialize real agent runtime."""
        self.message_bus = message_bus
        self.task_queue = task_queue
        self.agents: Dict[str, Dict[str, Any]] = {}
        self.agent_tasks: Dict[str, asyncio.Task] = {}
        self.is_running = False
        self.start_time = None

    async def register_agent(self, agent_id: str, agent: Any) -> bool:
        """Register an agent with the runtime."""
        try:
            self.agents[agent_id] = {
                "agent": agent,
                "status": AgentStatus.IDLE,
                "created_at": datetime.now(),
                "last_activity": datetime.now(),
                "task_count": 0,
                "error_count": 0,
            }
            logger.info(f"Registered agent {agent_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to register agent {agent_id}: {e}")
            return False

    async def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent from the runtime."""
        try:
            if agent_id in self.agents:
                # Stop agent if running
                if agent_id in self.agent_tasks:
                    task = self.agent_tasks[agent_id]
                    if not task.done():
                        task.cancel()
                    del self.agent_tasks[agent_id]

                del self.agents[agent_id]
                logger.info(f"Unregistered agent {agent_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to unregister agent {agent_id}: {e}")
            return False

    async def execute_agent_task(self, agent_id: str, task: Dict[str, Any]) -> bool:
        """Execute a task on an agent."""
        try:
            if agent_id not in self.agents:
                logger.error(f"Agent {agent_id} not found")
                return False

            agent_info = self.agents[agent_id]
            agent = agent_info["agent"]

            # Update agent status
            agent_info["status"] = AgentStatus.RUNNING
            agent_info["last_activity"] = datetime.now()
            agent_info["task_count"] += 1

            # Execute task
            logger.info(f"Executing task on agent {agent_id}: {task.get('task_id', 'unknown')}")

            if hasattr(agent, "process_task"):
                if asyncio.iscoroutinefunction(agent.process_task):
                    await agent.process_task(task)
                else:
                    agent.process_task(task)
            else:
                logger.warning(f"Agent {agent_id} does not have process_task method")

            # Update agent status
            agent_info["status"] = AgentStatus.IDLE
            return True

        except Exception as e:
            logger.error(f"Failed to execute task on agent {agent_id}: {e}")
            agent_info = self.agents.get(agent_id)
            if agent_info:
                agent_info["status"] = AgentStatus.FAILED
                agent_info["error_count"] += 1
            return False

    async def start(self) -> None:
        """Start the agent runtime."""
        self.is_running = True
        self.start_time = datetime.now()
        logger.info("Agent runtime started")

        while self.is_running:
            try:
                # Process tasks from task queue
                task = self.task_queue.dequeue_task()

                if task:
                    agent_id = task.get("agent_id")
                    if agent_id:
                        await self.execute_agent_task(agent_id, task)
                else:
                    await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Agent runtime error: {e}")
                await asyncio.sleep(5)

    async def stop(self) -> None:
        """Stop the agent runtime gracefully."""
        logger.info("Stopping agent runtime...")
        self.is_running = False

        # Cancel all agent tasks
        for agent_id, task in self.agent_tasks.items():
            if not task.done():
                task.cancel()

        # Wait for all tasks to complete
        if self.agent_tasks:
            await asyncio.gather(*self.agent_tasks.values(), return_exceptions=True)

        logger.info("Agent runtime stopped")

    def get_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of an agent."""
        if agent_id in self.agents:
            agent_info = self.agents[agent_id]
            return {
                "agent_id": agent_id,
                "status": agent_info["status"].value,
                "created_at": agent_info["created_at"].isoformat(),
                "last_activity": agent_info["last_activity"].isoformat(),
                "task_count": agent_info["task_count"],
                "error_count": agent_info["error_count"],
            }
        return None

    def get_runtime_stats(self) -> Dict[str, Any]:
        """Get runtime statistics."""
        uptime = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        total_tasks = sum(info["task_count"] for info in self.agents.values())
        total_errors = sum(info["error_count"] for info in self.agents.values())

        return {
            "is_running": self.is_running,
            "uptime_seconds": uptime,
            "agent_count": len(self.agents),
            "total_tasks": total_tasks,
            "total_errors": total_errors,
            "queue_length": self.task_queue.get_task_count(),
            "dead_letter_count": self.task_queue.get_dead_letter_count(),
        }
