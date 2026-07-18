import pytest
import logging
from core.runtime.observability_layer.health_checks.health_checks import (
    HealthCheckManager, HealthStatus, HealthCheckResult, IHealthCheck, DatabaseHealthCheck, ServiceHealthCheck
)
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def health_check_manager():
    return HealthCheckManager()

@pytest.mark.asyncio
async def test_register_check(health_check_manager, caplog):
    mock_check = AsyncMock(spec=IHealthCheck)
    with caplog.at_level(logging.INFO):
        await health_check_manager.register_check("mock_db_check", mock_check)
    assert "Health check \'mock_db_check\' registered." in caplog.text
    assert "mock_db_check" in health_check_manager._checks

@pytest.mark.asyncio
async def test_run_all_checks_healthy(health_check_manager):
    db_check = DatabaseHealthCheck("db_check", "test_db", is_healthy=True)
    service_check = ServiceHealthCheck("service_check", "test_service", response_time_ms=50)

    await health_check_manager.register_check("db_check", db_check)
    await health_check_manager.register_check("service_check", service_check)

    results = await health_check_manager.run_all_checks()

    assert len(results) == 2
    assert results[db_check.name].status == HealthStatus.HEALTHY
    assert results[service_check.name].status == HealthStatus.HEALTHY
    assert await health_check_manager.get_overall_status(results) == HealthStatus.HEALTHY

@pytest.mark.asyncio
async def test_run_all_checks_unhealthy(health_check_manager):
    db_check = DatabaseHealthCheck("db_check", "test_db", is_healthy=False)
    service_check = ServiceHealthCheck("service_check", "test_service", response_time_ms=50)

    await health_check_manager.register_check("db_check", db_check)
    await health_check_manager.register_check("service_check", service_check)

    results = await health_check_manager.run_all_checks()

    assert len(results) == 2
    assert results[db_check.name].status == HealthStatus.UNHEALTHY
    assert results[service_check.name].status == HealthStatus.HEALTHY
    assert await health_check_manager.get_overall_status(results) == HealthStatus.UNHEALTHY

@pytest.mark.asyncio
async def test_run_all_checks_degraded(health_check_manager):
    db_check = DatabaseHealthCheck("db_check", "test_db", is_healthy=True)
    service_check = ServiceHealthCheck("service_check", "test_service", response_time_ms=150)

    await health_check_manager.register_check("db_check", db_check)
    await health_check_manager.register_check("service_check", service_check)

    results = await health_check_manager.run_all_checks()

    assert len(results) == 2
    assert results[db_check.name].status == HealthStatus.HEALTHY
    assert results[service_check.name].status == HealthStatus.DEGRADED
    assert await health_check_manager.get_overall_status(results) == HealthStatus.DEGRADED

@pytest.mark.asyncio
async def test_check_exception_handling(health_check_manager):
    class FailingHealthCheck(IHealthCheck):
        async def check(self):
            raise Exception("Simulated check failure")

    failing_check = FailingHealthCheck()
    await health_check_manager.register_check("failing_check", failing_check)

    results = await health_check_manager.run_all_checks()

    assert len(results) == 1
    assert results["failing_check"].status == HealthStatus.UNHEALTHY
    assert "Simulated check failure" in results["failing_check"].message
    assert await health_check_manager.get_overall_status(results) == HealthStatus.UNHEALTHY

@pytest.mark.asyncio
async def test_health_check_result_to_dict():
    result = HealthCheckResult("test_name", HealthStatus.HEALTHY, "All good", {"version": "1.0"})
    expected_dict = {
        "name": "test_name",
        "status": "Healthy",
        "message": "All good",
        "details": {"version": "1.0"}
    }
    assert result.to_dict() == expected_dict
