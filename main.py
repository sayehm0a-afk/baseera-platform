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
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import uvicorn

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Import structured logging -- must come after sys.path.insert above so `src` is importable
from src.core.config import settings  # noqa: E402
from src.core.monitoring.structured_logging import init_logging, get_logger  # noqa: E402
from src.api.error_handlers import register_error_handlers  # noqa: E402
from src.api.middleware.csrf import CSRFMiddleware  # noqa: E402
from src.api.middleware.rate_limiting import limiter  # noqa: E402
from src.api.middleware.request_id import RequestIDMiddleware  # noqa: E402
from src.api.middleware.security_headers import SecurityHeadersMiddleware  # noqa: E402
from src.api.routes.admin import router as admin_router  # noqa: E402
from src.api.routes.auth import router as auth_router  # noqa: E402
from src.api.routes.backtests import router as backtests_router  # noqa: E402
from src.api.routes.bootstrap import router as bootstrap_router  # noqa: E402
from src.api.routes.calibrations import router as calibrations_router  # noqa: E402
from src.api.routes.market import router as market_router  # noqa: E402
from src.api.routes.news import router as news_router  # noqa: E402
from src.api.routes.portfolio import router as portfolio_router  # noqa: E402
from src.api.routes.stocks import router as stocks_router  # noqa: E402
from src.api.routes.subscriptions import router as subscriptions_router  # noqa: E402

# Sentry: opt-in only (settings.sentry_dsn is None unless SENTRY_DSN is set),
# so a dev/CI run with no DSN configured never attempts a network call.
if settings.sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.0,
    )

# Initialize structured logging
init_logging(log_level=settings.log_level)
logger = get_logger(__name__)

# FastAPI app
app = FastAPI(
    title="Basirah",
    description="Enterprise AI Platform for Saudi Financial Market Analysis",
    version="1.0.0",
)

# Middleware stack -- Starlette applies the LAST-added middleware
# outermost, so CORS (added last, when configured) wraps everything
# else, exactly as a preflight OPTIONS request needs. RequestIDMiddleware
# is added after CSRF/SecurityHeaders so the request_id contextvar is set
# before either of them (and every route/log line) runs.
app.add_middleware(CSRFMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)

# TRUSTED_HOSTS (Settings.trusted_hosts) is a comma-separated allowlist
# of Host headers this app will answer to -- defends against Host
# header injection (cache poisoning, password-reset-link poisoning via
# a spoofed Host). Deliberately empty (not enforced) by default, same
# secure-by-default-when-configured posture as CORS_ALLOWED_ORIGINS
# below: every existing deployment keeps working unchanged until this
# is explicitly set for staging/production (see
# docs/PRODUCTION_CONFIGURATION.md).
if settings.trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

# CORS_ALLOWED_ORIGINS is a comma-separated list of allowed frontend
# origins (e.g. "http://localhost:3000,https://app.example.com").
# Deliberately empty (no cross-origin access) by default -- same
# secure-by-default posture as SAHMK_LIVE_DATA_ENABLED: a frontend
# origin must be explicitly opted in, never assumed or wildcarded.
# Read via `settings.cors_allowed_origins` (not a second independent
# os.getenv parse) so there is exactly one place this list is derived
# from CORS_ALLOWED_ORIGINS.
if settings.cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

register_error_handlers(app)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(auth_router)
app.include_router(bootstrap_router)
app.include_router(admin_router)
app.include_router(stocks_router)
app.include_router(backtests_router)
app.include_router(calibrations_router)
app.include_router(market_router)
app.include_router(news_router)
app.include_router(portfolio_router)
app.include_router(subscriptions_router)

# Global runtime kernel
kernel = None
container = None
ingestion_scheduler = None
market_intelligence_scheduler = None
outcome_evaluation_scheduler = None
pattern_discovery_scheduler = None
daily_reflection_scheduler = None
daily_intelligence_aggregation_scheduler = None
live_market_mode_scheduler = None


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
    global kernel, container, ingestion_scheduler, market_intelligence_scheduler
    global outcome_evaluation_scheduler, pattern_discovery_scheduler, daily_reflection_scheduler
    global daily_intelligence_aggregation_scheduler, live_market_mode_scheduler

    # Live Market Mode (LIVE_MARKET_MODE_ENABLED) supersedes the two
    # standalone schedulers below -- it owns its own internal instances
    # of IngestionScheduler/IntervalMarketIntelligenceScheduler and only
    # runs them while the Tadawul market is actually open (see
    # src.market_intelligence.live_market_mode). Checked first so the
    # two `if` guards below skip starting a second, redundant pair of
    # always-on schedulers when Live Market Mode already owns that job.
    live_market_mode_enabled = False
    try:
        from src.market_intelligence.config import is_live_market_mode_enabled
        from src.market_intelligence.live_market_mode import LiveMarketModeScheduler

        live_market_mode_enabled = is_live_market_mode_enabled()
        if live_market_mode_enabled:
            live_market_mode_scheduler = LiveMarketModeScheduler()
            live_market_mode_scheduler.start()
            logger.info("Live Market Mode started (Tadawul-hours-gated ingestion + scanning).")
        else:
            logger.info("Live Market Mode disabled (set LIVE_MARKET_MODE_ENABLED=true to enable).")
    except Exception as e:
        logger.error(f"Error starting Live Market Mode: {e}", exc_info=True)

    # The ingestion scheduler needs only the DB and a market/fundamental
    # data provider -- no Redis, no runtime kernel. Started first, in its
    # own try/except, so a Redis/kernel outage (which the block below
    # depends on and can raise from) never prevents scheduled ingestion
    # from starting, and a scheduler problem never prevents the kernel
    # from starting either. Skipped when Live Market Mode already owns
    # an ingestion scheduler of its own (see above).
    try:
        from src.market_data.ingestion.config import is_ingestion_scheduler_enabled
        from src.market_data.ingestion.scheduler import IngestionScheduler

        if live_market_mode_enabled:
            logger.info("Ingestion scheduler: owned by Live Market Mode, not started standalone.")
        elif is_ingestion_scheduler_enabled():
            ingestion_scheduler = IngestionScheduler()
            ingestion_scheduler.start()
            logger.info("Ingestion scheduler started.")
        else:
            logger.info(
                "Ingestion scheduler disabled (set INGESTION_SCHEDULER_ENABLED=true to enable)."
            )
    except Exception as e:
        logger.error(f"Error starting ingestion scheduler: {e}", exc_info=True)

    # Same reasoning, same isolation: an unattended, recurring
    # full-market scan is real workload an operator must opt into (see
    # src.market_intelligence.config.is_market_intelligence_scheduler_enabled),
    # disabled by default, and never allowed to prevent the ingestion
    # scheduler or the kernel from starting. Skipped when Live Market
    # Mode already owns a scan scheduler of its own (see above).
    try:
        from src.market_intelligence.config import is_market_intelligence_scheduler_enabled
        from src.market_intelligence.scheduler import IntervalMarketIntelligenceScheduler

        if live_market_mode_enabled:
            logger.info("Market intelligence scheduler: owned by Live Market Mode, not started standalone.")
        elif is_market_intelligence_scheduler_enabled():
            market_intelligence_scheduler = IntervalMarketIntelligenceScheduler()
            market_intelligence_scheduler.start()
            logger.info("Market intelligence scheduler started.")
        else:
            logger.info(
                "Market intelligence scheduler disabled "
                "(set MARKET_INTELLIGENCE_SCHEDULER_ENABLED=true to enable)."
            )
    except Exception as e:
        logger.error(f"Error starting market intelligence scheduler: {e}", exc_info=True)

    # AI Evolution Layer (E2): scores already-issued live recommendations
    # against real forward price data once their horizon has elapsed.
    # Same isolation, same disabled-by-default posture as the two
    # schedulers above.
    try:
        from src.ai_evolution.config import is_outcome_evaluation_scheduler_enabled
        from src.ai_evolution.scheduler import OutcomeEvaluationScheduler

        if is_outcome_evaluation_scheduler_enabled():
            outcome_evaluation_scheduler = OutcomeEvaluationScheduler()
            outcome_evaluation_scheduler.start()
            logger.info("Outcome evaluation scheduler started.")
        else:
            logger.info(
                "Outcome evaluation scheduler disabled "
                "(set OUTCOME_EVALUATION_SCHEDULER_ENABLED=true to enable)."
            )
    except Exception as e:
        logger.error(f"Error starting outcome evaluation scheduler: {e}", exc_info=True)

    # AI Evolution Layer (E5): weekly re-discovery of signal conditions
    # statistically associated with a different win rate. Same isolation,
    # same disabled-by-default posture as the schedulers above.
    try:
        from src.ai_evolution.config import is_pattern_discovery_scheduler_enabled
        from src.ai_evolution.scheduler import PatternDiscoveryScheduler

        if is_pattern_discovery_scheduler_enabled():
            pattern_discovery_scheduler = PatternDiscoveryScheduler()
            pattern_discovery_scheduler.start()
            logger.info("Pattern discovery scheduler started.")
        else:
            logger.info(
                "Pattern discovery scheduler disabled "
                "(set PATTERN_DISCOVERY_SCHEDULER_ENABLED=true to enable)."
            )
    except Exception as e:
        logger.error(f"Error starting pattern discovery scheduler: {e}", exc_info=True)

    # AI Evolution Layer (E6): daily, non-LLM review of that day's
    # evaluated recommendations. Same isolation, same disabled-by-default
    # posture as the schedulers above.
    try:
        from src.ai_evolution.config import is_daily_reflection_scheduler_enabled
        from src.ai_evolution.scheduler import DailyReflectionScheduler

        if is_daily_reflection_scheduler_enabled():
            daily_reflection_scheduler = DailyReflectionScheduler()
            daily_reflection_scheduler.start()
            logger.info("Daily reflection scheduler started.")
        else:
            logger.info(
                "Daily reflection scheduler disabled "
                "(set DAILY_REFLECTION_SCHEDULER_ENABLED=true to enable)."
            )
    except Exception as e:
        logger.error(f"Error starting daily reflection scheduler: {e}", exc_info=True)

    # AI Evolution Layer (E9): daily pre-aggregation feeding the
    # staff-only Intelligence Dashboard. Same isolation, same
    # disabled-by-default posture as the schedulers above.
    try:
        from src.ai_evolution.config import is_daily_intelligence_aggregation_scheduler_enabled
        from src.ai_evolution.scheduler import DailyIntelligenceAggregationScheduler

        if is_daily_intelligence_aggregation_scheduler_enabled():
            daily_intelligence_aggregation_scheduler = DailyIntelligenceAggregationScheduler()
            daily_intelligence_aggregation_scheduler.start()
            logger.info("Daily intelligence aggregation scheduler started.")
        else:
            logger.info(
                "Daily intelligence aggregation scheduler disabled "
                "(set DAILY_INTELLIGENCE_AGGREGATION_SCHEDULER_ENABLED=true to enable)."
            )
    except Exception as e:
        logger.error(f"Error starting daily intelligence aggregation scheduler: {e}", exc_info=True)

    # Legacy runtime kernel / worker / sample-agent bootstrap. No real
    # route (market/stocks/portfolio/analyst/news/admin) reaches into the
    # `kernel`/`container` globals set here -- see the standalone comment
    # in src/api/routes/admin/system.py confirming this subsystem is
    # orthogonal to actual request handling. It previously re-raised on
    # any failure (e.g. Redis unreachable at boot), which would crash
    # the entire app's startup -- taking down the real Saudi-market
    # analysis endpoints along with it even though they never use this
    # subsystem. Isolated in its own try/except, matching every
    # scheduler above, so a problem here is logged loudly but never
    # prevents the real API from serving requests.
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
            raise RuntimeError("Failed to initialize runtime kernel")

        # Create and register workers
        container.get_service("message_bus")  # instantiate the singleton at startup
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
        logger.error(
            f"Error starting legacy runtime kernel/worker subsystem (does not affect "
            f"market/stocks/portfolio/analyst/news/admin API routes): {e}",
            exc_info=True,
        )


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    try:
        logger.info("Shutting down Basirah...")

        if live_market_mode_scheduler is not None:
            await live_market_mode_scheduler.stop()

        if ingestion_scheduler is not None:
            await ingestion_scheduler.stop()

        if market_intelligence_scheduler is not None:
            await market_intelligence_scheduler.stop()

        if outcome_evaluation_scheduler is not None:
            await outcome_evaluation_scheduler.stop()

        if pattern_discovery_scheduler is not None:
            await pattern_discovery_scheduler.stop()

        if daily_reflection_scheduler is not None:
            await daily_reflection_scheduler.stop()

        if daily_intelligence_aggregation_scheduler is not None:
            await daily_intelligence_aggregation_scheduler.stop()

        if kernel:
            await kernel.stop()

        from src.core.db.database import shutdown_engine
        shutdown_engine()

        logger.info("Basirah shut down successfully")

    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


@app.get("/health/live")
async def liveness_check():
    """Liveness check endpoint."""
    return {"status": "healthy"}


@app.get("/health/ready")
async def readiness_check():
    """Readiness check endpoint -- a readiness probe that never touches
    its own datastores isn't one, so this checks a real `SELECT 1`
    against Postgres and a real `PING` against Redis. The legacy
    in-process kernel (sample-agent/worker scaffolding, unused by every
    real market/stocks/portfolio/analyst/news/admin route -- see
    src/api/routes/admin/system.py) is reported for visibility but
    deliberately excluded from the pass/fail gate below: it failing to
    initialize once at boot (e.g. a transient Redis hiccup) must never
    permanently mark an otherwise-healthy app unready, since nothing it
    powers is on the real request path."""
    from sqlalchemy import text

    from src.auth.token_store import get_redis_client
    from src.core.db.database import get_session_factory

    health_status = {}
    dependency_status = {}

    try:
        if kernel:
            health_status.update(kernel.health_check())
        else:
            health_status["kernel"] = False
    except Exception as e:
        logger.error(f"Readiness kernel check failed: {e}")
        health_status["kernel"] = False

    try:
        session_factory = get_session_factory()
        db_session = session_factory()
        try:
            db_session.execute(text("SELECT 1"))
            dependency_status["database"] = True
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Readiness DB check failed: {e}")
        dependency_status["database"] = False

    try:
        dependency_status["redis"] = bool(get_redis_client().ping())
    except Exception as e:
        logger.error(f"Readiness Redis check failed: {e}")
        dependency_status["redis"] = False

    health_status.update(dependency_status)
    if all(dependency_status.values()):
        return {"status": "healthy", "details": health_status}
    raise HTTPException(status_code=503, detail=f"Degraded health: {health_status}")


@app.get("/health/market-data")
async def market_data_health():
    """Safe operational status for the SAHMK market-data integration --
    no secret value is ever read or returned. Reports whether Basirah
    is currently permitted to run/publish a real market scan under
    strict real-data mode (STRICT_REAL_DATA=true), and the most recent
    provider-selection outcome any caller in this process has observed
    (in-process only; resets on restart, not a persisted audit trail --
    see src.market_data.provider_factory.get_market_data_health)."""
    from src.market_data.provider_factory import get_market_data_health

    health = get_market_data_health()
    strict = health["strict_real_data"]
    current_kind = health["current_provider_kind"]
    last_scan_source = {"sahmk": "SAHMK_REAL", "dev": "DEV_SYNTHETIC"}.get(current_kind)

    # Under strict mode, only ever true when the most recent real
    # selection actually resolved to SAHMK -- never true merely because
    # no failure has been observed yet. Non-strict deployments make no
    # "this is real data" claim in the first place, so this field is
    # not the relevant gate for them.
    can_publish = (current_kind == "sahmk") if strict else True

    return {
        **health,
        "last_scan_source": last_scan_source,
        "can_publish_recommendations": can_publish,
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint. Must be returned as a raw
    `text/plain` Response (the Prometheus exposition format), never a
    bare string -- FastAPI otherwise JSON-encodes a plain `str` return
    value, which double-escapes every newline and mislabels the
    content-type, producing a body no real Prometheus server can
    actually scrape."""
    from fastapi import Response

    from src.auth.repository import AuthRepository
    from src.core.db.database import get_session_factory
    from src.core.monitoring.prometheus_metrics import get_metrics

    session_factory = get_session_factory()
    db_session = session_factory()
    try:
        # active_sessions is recomputed from a real COUNT() query at
        # scrape time, not tracked incrementally, so it can never drift
        # from the database's actual state.
        total, _ = AuthRepository().list_all_active_sessions(db_session, limit=1, offset=0)
        get_metrics().set_active_sessions(total)
    except Exception as e:
        logger.error(f"Failed to refresh active_sessions gauge: {e}")
    finally:
        db_session.close()

    return Response(content=get_metrics().get_metrics(), media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/market-data/status")
async def market_data_status():
    """Reports which market-data and fundamentals providers are
    currently active.

    src.market_data.provider_factory / fundamental_provider_factory
    each automatically select the live SAHMK provider whenever
    SAHMK_API_KEY is configured and sahmk.sa is reachable, and fall
    back to the synthetic dev provider otherwise (e.g. in a
    network-restricted environment) -- this endpoint exposes that
    decision and each provider's own health check for operators.
    Never returns the configured API key.
    """
    try:
        from src.market_data.fundamental_provider_factory import (
            get_fundamental_data_provider,
            get_last_selected_fundamental_provider_kind,
        )
        from src.market_data.provider_factory import (
            get_last_selected_provider_kind,
            get_market_data_provider,
        )

        market_provider = await get_market_data_provider()
        fundamental_provider = await get_fundamental_data_provider()
        market_health = await market_provider.health_check()
        fundamental_health = await fundamental_provider.health_check()
        return {
            "market_data": {
                "provider": get_last_selected_provider_kind(),
                "health": market_health.value,
            },
            "fundamentals": {
                "provider": get_last_selected_fundamental_provider_kind(),
                "health": fundamental_health.value,
            },
        }
    except Exception as e:
        logger.error(f"Error checking market data provider status: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to determine market data provider status"
        )


@app.get("/ingestion/status")
async def ingestion_status():
    """Reports whether the ingestion scheduler is running and the most
    recent run of each job (status, timing, row counts), from
    IngestionRunLog -- so an operator can see "is the database still
    syncing with SAHMK" without grepping logs.
    """
    try:
        from src.core.db.database import get_session_factory
        from src.domain.models import IngestionRunLog

        session = get_session_factory()()
        try:
            job_names = [
                row[0] for row in session.query(IngestionRunLog.job_name).distinct().all()
            ]
            latest_runs = {}
            for job_name in job_names:
                run = (
                    session.query(IngestionRunLog)
                    .filter_by(job_name=job_name)
                    .order_by(IngestionRunLog.started_at.desc())
                    .first()
                )
                if run is not None:
                    latest_runs[job_name] = {
                        "status": run.status.value,
                        "started_at": run.started_at.isoformat(),
                        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                        "duration_seconds": (
                            float(run.duration_seconds) if run.duration_seconds is not None else None
                        ),
                        "symbols_requested": run.symbols_requested,
                        "symbols_succeeded": run.symbols_succeeded,
                        "symbols_failed": run.symbols_failed,
                        "rows_upserted": run.rows_upserted,
                        "retry_count": run.retry_count,
                    }
        finally:
            session.close()

        return {
            "scheduler_running": ingestion_scheduler is not None and ingestion_scheduler.is_running,
            "live_market_mode_running": (
                live_market_mode_scheduler is not None and live_market_mode_scheduler.is_running
            ),
            "live_market_mode_tadawul_open": (
                live_market_mode_scheduler.is_market_currently_open if live_market_mode_scheduler is not None else None
            ),
            "jobs": latest_runs,
        }
    except Exception as e:
        logger.error(f"Error checking ingestion status: {e}")
        raise HTTPException(status_code=500, detail="Failed to determine ingestion status")


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
