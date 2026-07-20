#!/usr/bin/env python3
"""
Basirah - Enterprise AI Platform for Saudi Financial Market Analysis
Main entry point for production deployment with FastAPI.
"""

import asyncio
import os
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Import structured logging
from src.core.monitoring.structured_logging import init_logging, get_logger

# Initialize structured logging
init_logging()
logger = get_logger(__name__)

# FastAPI app
app = FastAPI(
    title="Basirah",
    description="Enterprise AI Platform for Saudi Financial Market Analysis",
    version="1.0.0",
)

# Global runtime kernel
kernel = None
container = None

class TaskRequest(BaseModel):
    """Task request model."""
    task_id: str
    agent_id: str
    task_type: str
    data: dict

class TaskResponse(BaseModel):
    """Task response model."""
    status: str
    message: str
    task_id: str

@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    global kernel, container
    
    try:
        logger.info("Starting Basirah Enterprise AI Platform...")
        
        # Setup production dependencies
        from src.core.runtime.dependency_injection import setup_production_dependencies
        from src.core.runtime.real_runtime_kernel import RealRuntimeKernel
        from src.core.runtime.worker.real_worker import RealWorker
        from src.core.base_agent.base_agent import BaseAgent
        
        # Initialize dependency container
        container = setup_production_dependencies()
        logger.info("Dependency container initialized")
        
        # Create runtime kernel
        kernel = RealRuntimeKernel(container)
        
        # Initialize kernel
        if not await kernel.initialize():
            logger.error("Failed to initialize runtime kernel")
            raise RuntimeError("Failed to initialize runtime kernel")
        
        # Create and register workers
        message_bus = container.get_service("message_bus")
        task_queue = container.get_service("task_queue")
        
        worker_count = int(os.getenv("WORKER_COUNT", 2))
        for i in range(worker_count):
            worker = RealWorker(f"worker-{i}", task_queue)
            kernel.add_worker(worker)
        
        logger.info(f"Created {worker_count} workers")
        
        # Register sample agents
        agent_runtime = container.get_service("agent_runtime")
        
        # Create sample agent
        sample_agent = BaseAgent(
            agent_id="sample-agent-1",
            name="Sample Analysis Agent",
            description="Sample agent for testing",
        )
        
        await agent_runtime.register_agent("sample-agent-1", sample_agent)
        logger.info("Registered sample agent")
        
        # Start runtime kernel in background
        asyncio.create_task(kernel.start())
        
        logger.info("Basirah started successfully")
    
    except Exception as e:
        logger.error(f"Error during startup: {e}", exc_info=True)
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    global kernel
    
    try:
        logger.info("Shutting down Basirah...")
        
        if kernel:
            await kernel.stop()
        
        logger.info("Basirah shut down successfully")
    
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)

@app.get("/health/live")
async def liveness_check():
    """Liveness check endpoint."""
    return {"status": "healthy"}

@app.get("/health/ready")
async def readiness_check():
    """Readiness check endpoint."""
    try:
        if not kernel:
            raise HTTPException(status_code=503, detail="kernel not initialized")
        
        health_status = kernel.health_check()
        
        if all(health_status.values()):
            return {"status": "healthy", "details": health_status}
        else:
            raise HTTPException(status_code=503, detail=f"Degraded health: {health_status}")
    
    except Exception as e:
        logger.error(f"Readiness check error: {e}")
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    from src.core.monitoring.prometheus_metrics import get_metrics
    return get_metrics().get_metrics().decode("utf-8")


@app.get("/stats")
async def get_stats():
    """Get runtime statistics."""
    try:
        if not kernel:
            raise HTTPException(status_code=503, detail="Kernel not initialized")
        
        stats = kernel.get_stats()
        return stats
    
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tasks", response_model=TaskResponse)
async def submit_task(task_request: TaskRequest):
    """Submit a task for processing."""
    try:
        if not kernel or not kernel.service_layer:
            raise HTTPException(status_code=503, detail="Service layer not available")
        
        task = {
            "task_id": task_request.task_id,
            "agent_id": task_request.agent_id,
            "task_type": task_request.task_type,
            "data": task_request.data,
        }
        
        success = await kernel.service_layer.submit_task(task)
        
        if success:
            return TaskResponse(
                status="accepted",
                message=f"Task {task_request.task_id} enqueued for processing",
                task_id=task_request.task_id,
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to enqueue task")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Get task status."""
    try:
        if not kernel or not kernel.service_layer:
            raise HTTPException(status_code=503, detail="Service layer not available")
        
        status = await kernel.service_layer.get_task_status(task_id)
        
        if status:
            return status
        else:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/agents/{agent_id}")
async def get_agent_status(agent_id: str):
    """Get agent status."""
    try:
        if not kernel or not kernel.service_layer:
            raise HTTPException(status_code=503, detail="Service layer not available")
        
        status = await kernel.service_layer.get_agent_status(agent_id)
        
        if status:
            return status
        else:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    try:
        port = int(os.getenv("PORT", 8000))
        host = os.getenv("HOST", "0.0.0.0")
        
        logger.info(f"Starting Basirah API server on {host}:{port}")
        
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
        )
    
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        sys.exit(1)
