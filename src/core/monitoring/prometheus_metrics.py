"""
Prometheus metrics and monitoring for Basirah.

Provides comprehensive metrics collection for:
- Request latency and throughput
- Agent performance
- Market data provider health
- Database operations
- Task queue metrics
- System resource usage
"""

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Summary,
    CollectorRegistry,
    generate_latest,
)
import logging

logger = logging.getLogger(__name__)


class PrometheusMetrics:
    """Prometheus metrics collection for Basirah."""

    def __init__(self, registry: CollectorRegistry = None):
        """Initialize Prometheus metrics."""
        self.registry = registry or CollectorRegistry()

        # HTTP Request Metrics
        self.http_requests_total = Counter(
            "basirah_http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status"],
            registry=self.registry,
        )

        self.http_request_duration_seconds = Histogram(
            "basirah_http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "endpoint"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
            registry=self.registry,
        )

        # Agent Metrics
        self.agent_executions_total = Counter(
            "basirah_agent_executions_total",
            "Total agent executions",
            ["agent_type", "status"],
            registry=self.registry,
        )

        self.agent_execution_duration_seconds = Histogram(
            "basirah_agent_execution_duration_seconds",
            "Agent execution duration in seconds",
            ["agent_type"],
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
            registry=self.registry,
        )

        self.agent_errors_total = Counter(
            "basirah_agent_errors_total",
            "Total agent errors",
            ["agent_type", "error_type"],
            registry=self.registry,
        )

        # Market Data Provider Metrics
        self.market_data_requests_total = Counter(
            "basirah_market_data_requests_total",
            "Total market data requests",
            ["provider", "data_type", "status"],
            registry=self.registry,
        )

        self.market_data_request_duration_seconds = Histogram(
            "basirah_market_data_request_duration_seconds",
            "Market data request duration in seconds",
            ["provider", "data_type"],
            buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0),
            registry=self.registry,
        )

        self.market_data_provider_health = Gauge(
            "basirah_market_data_provider_health",
            "Market data provider health status (1=healthy, 0.5=degraded, 0=unhealthy)",
            ["provider"],
            registry=self.registry,
        )

        # Database Metrics
        self.db_queries_total = Counter(
            "basirah_db_queries_total",
            "Total database queries",
            ["operation", "status"],
            registry=self.registry,
        )

        self.db_query_duration_seconds = Histogram(
            "basirah_db_query_duration_seconds",
            "Database query duration in seconds",
            ["operation"],
            buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
            registry=self.registry,
        )

        self.db_connection_pool_size = Gauge(
            "basirah_db_connection_pool_size",
            "Database connection pool size",
            registry=self.registry,
        )

        self.db_connection_pool_available = Gauge(
            "basirah_db_connection_pool_available",
            "Available database connections in pool",
            registry=self.registry,
        )

        # Task Queue Metrics
        self.task_queue_size = Gauge(
            "basirah_task_queue_size",
            "Current task queue size",
            registry=self.registry,
        )

        self.tasks_processed_total = Counter(
            "basirah_tasks_processed_total",
            "Total tasks processed",
            ["status"],
            registry=self.registry,
        )

        self.task_processing_duration_seconds = Histogram(
            "basirah_task_processing_duration_seconds",
            "Task processing duration in seconds",
            buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0),
            registry=self.registry,
        )

        self.worker_active_tasks = Gauge(
            "basirah_worker_active_tasks",
            "Number of active tasks per worker",
            ["worker_id"],
            registry=self.registry,
        )

        # System Metrics
        self.system_uptime_seconds = Gauge(
            "basirah_system_uptime_seconds",
            "System uptime in seconds",
            registry=self.registry,
        )

        self.active_agents = Gauge(
            "basirah_active_agents",
            "Number of active agents",
            registry=self.registry,
        )

        # Cache Metrics
        self.cache_hits_total = Counter(
            "basirah_cache_hits_total",
            "Total cache hits",
            ["cache_name"],
            registry=self.registry,
        )

        self.cache_misses_total = Counter(
            "basirah_cache_misses_total",
            "Total cache misses",
            ["cache_name"],
            registry=self.registry,
        )

        self.cache_size_bytes = Gauge(
            "basirah_cache_size_bytes",
            "Cache size in bytes",
            ["cache_name"],
            registry=self.registry,
        )

        # Error Metrics
        self.errors_total = Counter(
            "basirah_errors_total",
            "Total errors",
            ["error_type", "component"],
            registry=self.registry,
        )

        self.exceptions_total = Counter(
            "basirah_exceptions_total",
            "Total exceptions",
            ["exception_type"],
            registry=self.registry,
        )

    def record_http_request(
        self,
        method: str,
        endpoint: str,
        status: int,
        duration: float,
    ) -> None:
        """Record HTTP request metrics."""
        self.http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status=status,
        ).inc()
        self.http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint,
        ).observe(duration)

    def record_agent_execution(
        self,
        agent_type: str,
        status: str,
        duration: float,
    ) -> None:
        """Record agent execution metrics."""
        self.agent_executions_total.labels(
            agent_type=agent_type,
            status=status,
        ).inc()
        self.agent_execution_duration_seconds.labels(
            agent_type=agent_type,
        ).observe(duration)

    def record_agent_error(self, agent_type: str, error_type: str) -> None:
        """Record agent error metrics."""
        self.agent_errors_total.labels(
            agent_type=agent_type,
            error_type=error_type,
        ).inc()

    def record_market_data_request(
        self,
        provider: str,
        data_type: str,
        status: str,
        duration: float,
    ) -> None:
        """Record market data request metrics."""
        self.market_data_requests_total.labels(
            provider=provider,
            data_type=data_type,
            status=status,
        ).inc()
        self.market_data_request_duration_seconds.labels(
            provider=provider,
            data_type=data_type,
        ).observe(duration)

    def set_provider_health(self, provider: str, health_value: float) -> None:
        """Set market data provider health status."""
        self.market_data_provider_health.labels(provider=provider).set(health_value)

    def record_db_query(
        self,
        operation: str,
        status: str,
        duration: float,
    ) -> None:
        """Record database query metrics."""
        self.db_queries_total.labels(
            operation=operation,
            status=status,
        ).inc()
        self.db_query_duration_seconds.labels(
            operation=operation,
        ).observe(duration)

    def set_db_pool_metrics(self, pool_size: int, available: int) -> None:
        """Set database connection pool metrics."""
        self.db_connection_pool_size.set(pool_size)
        self.db_connection_pool_available.set(available)

    def set_task_queue_size(self, size: int) -> None:
        """Set current task queue size."""
        self.task_queue_size.set(size)

    def record_task_processed(self, status: str, duration: float) -> None:
        """Record task processing metrics."""
        self.tasks_processed_total.labels(status=status).inc()
        self.task_processing_duration_seconds.observe(duration)

    def set_worker_active_tasks(self, worker_id: str, count: int) -> None:
        """Set active task count for a worker."""
        self.worker_active_tasks.labels(worker_id=worker_id).set(count)

    def set_system_uptime(self, uptime_seconds: float) -> None:
        """Set system uptime."""
        self.system_uptime_seconds.set(uptime_seconds)

    def set_active_agents(self, count: int) -> None:
        """Set active agent count."""
        self.active_agents.set(count)

    def record_cache_hit(self, cache_name: str) -> None:
        """Record cache hit."""
        self.cache_hits_total.labels(cache_name=cache_name).inc()

    def record_cache_miss(self, cache_name: str) -> None:
        """Record cache miss."""
        self.cache_misses_total.labels(cache_name=cache_name).inc()

    def set_cache_size(self, cache_name: str, size_bytes: int) -> None:
        """Set cache size."""
        self.cache_size_bytes.labels(cache_name=cache_name).set(size_bytes)

    def record_error(self, error_type: str, component: str) -> None:
        """Record error."""
        self.errors_total.labels(
            error_type=error_type,
            component=component,
        ).inc()

    def record_exception(self, exception_type: str) -> None:
        """Record exception."""
        self.exceptions_total.labels(exception_type=exception_type).inc()

    def get_metrics(self) -> bytes:
        """Get metrics in Prometheus format."""
        return generate_latest(self.registry)


# Global metrics instance
_metrics_instance: PrometheusMetrics = None


def get_metrics() -> PrometheusMetrics:
    """Get or create global metrics instance."""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = PrometheusMetrics()
    return _metrics_instance


def init_metrics() -> PrometheusMetrics:
    """Initialize metrics."""
    global _metrics_instance
    _metrics_instance = PrometheusMetrics()
    return _metrics_instance
