from abc import ABC, abstractmethod
from typing import Dict, Any
import asyncio
import logging

logger = logging.getLogger(__name__)


class HealthStatus:
    HEALTHY = "Healthy"
    UNHEALTHY = "Unhealthy"
    DEGRADED = "Degraded"


class HealthCheckResult:
    def __init__(
        self,
        name: str,
        status: str,
        message: str = None,
        details: Dict[str, Any] = None,
    ):
        self.name = name
        self.status = status
        self.message = message
        self.details = details if details is not None else {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": self.details,
        }


class IHealthCheck(ABC):
    @abstractmethod
    async def check(self) -> HealthCheckResult:
        """
        يقوم بإجراء فحص صحي ويعيد النتيجة.
        """
        raise NotImplementedError


class IHealthCheckManager(ABC):
    @abstractmethod
    async def register_check(self, name: str, check: IHealthCheck):
        """
        يسجل فحصًا صحيًا جديدًا.
        """
        raise NotImplementedError

    @abstractmethod
    async def run_all_checks(self) -> Dict[str, HealthCheckResult]:
        """
        يقوم بتشغيل جميع الفحوصات الصحية المسجلة ويعيد النتائج.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_overall_status(self, results: Dict[str, HealthCheckResult]) -> str:
        """
        يعيد الحالة العامة للنظام بناءً على جميع الفحوصات.
        """
        raise NotImplementedError


class HealthCheckManager(IHealthCheckManager):
    def __init__(self):
        self._checks: Dict[str, IHealthCheck] = {}

    async def register_check(self, name: str, check: IHealthCheck):
        self._checks[name] = check
        logger.info(f"Health check '{name}' registered.")

    async def run_all_checks(self) -> Dict[str, HealthCheckResult]:
        results = {}
        for name, check in self._checks.items():

            try:
                result = await check.check()
                results[name] = result
            except Exception as e:
                results[name] = HealthCheckResult(
                    name, HealthStatus.UNHEALTHY, f"Check failed with exception: {e}"
                )
        return results

    async def get_overall_status(self, results: Dict[str, HealthCheckResult]) -> str:
        statuses = [result.status for result in results.values()]

        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        else:
            return HealthStatus.HEALTHY


# Example Health Check Implementation


class DatabaseHealthCheck(IHealthCheck):
    def __init__(self, name: str, db_identifier: str, is_healthy: bool = True):
        self.name = name
        self.db_identifier = db_identifier
        self._is_healthy = is_healthy

    async def check(self) -> HealthCheckResult:
        # Simulate database connection check
        await asyncio.sleep(0.01)  # Simulate async operation

        if self._is_healthy:
            return HealthCheckResult(
                self.name,
                HealthStatus.HEALTHY,
                f"Successfully connected to database {self.db_identifier}.",
            )
        else:
            return HealthCheckResult(
                self.name,
                HealthStatus.UNHEALTHY,
                f"Failed to connect to database {self.db_identifier}.",
            )


class ServiceHealthCheck(IHealthCheck):
    def __init__(self, name: str, service_name: str, response_time_ms: int = 50):
        self.name = name
        self.service_name = service_name
        self.response_time_ms = response_time_ms

    async def check(self) -> HealthCheckResult:
        # Simulate API call to a service
        # Simulate async operation
        await asyncio.sleep(self.response_time_ms / 1000.0)
        if self.response_time_ms < 100:
            return HealthCheckResult(
                self.name,
                HealthStatus.HEALTHY,
                f"Service responded in {self.response_time_ms}ms.",
            )
        elif self.response_time_ms < 200:
            return HealthCheckResult(
                self.name,
                HealthStatus.DEGRADED,
                f"Service responded slowly in {self.response_time_ms}ms.",
            )
        else:
            return HealthCheckResult(
                self.name,
                HealthStatus.UNHEALTHY,
                f"Service timed out after {self.response_time_ms}ms.",
            )
