from core.runtime.observability_layer.metrics.metrics import MetricsManager, IMetricsManager
from core.runtime.observability_layer.tracing.tracing import Tracer, ITracer
from core.runtime.observability_layer.health_checks.health_checks import HealthCheckManager, IHealthCheckManager

class ObservabilityLayer:
    def __init__(self):
        self._metrics_manager: IMetricsManager = MetricsManager()
        self._tracer: ITracer = Tracer()
        self._health_check_manager: IHealthCheckManager = HealthCheckManager()

    @property
    def metrics(self) -> IMetricsManager:
        return self._metrics_manager

    @property
    def tracer(self) -> ITracer:
        return self._tracer

    @property
    def health_checks(self) -> IHealthCheckManager:
        return self._health_check_manager
