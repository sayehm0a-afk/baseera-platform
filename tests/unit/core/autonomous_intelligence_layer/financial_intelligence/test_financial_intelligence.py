import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone
from src.core.autonomous_intelligence_layer.financial_intelligence.financial_intelligence import (
    FinancialIntelligence, FinancialIntelligenceConfig, Transaction, Budget, FinancialReport,
    TransactionType, FinancialMetric
)
from src.core.shared_models.base_transaction import BaseTransaction

# Mock BaseTransaction for testing purposes
class MockBaseTransaction(BaseTransaction):
    def __init__(self, amount: float, description: str, timestamp: datetime = None):
        self.amount = amount
        self.description = description
        self.timestamp = timestamp if timestamp else datetime.now(timezone.utc)

@pytest.fixture
def financial_intelligence_instance():
    return FinancialIntelligence()

def test_financial_intelligence_init(financial_intelligence_instance):
    assert isinstance(financial_intelligence_instance.config, FinancialIntelligenceConfig)
    assert not financial_intelligence_instance.transactions
    assert not financial_intelligence_instance.budgets
    assert not financial_intelligence_instance.reports

def test_record_transaction(financial_intelligence_instance):
    transaction = financial_intelligence_instance.record_transaction(
        "trans1", TransactionType.REVENUE, 100.0, "Sale"
    )
    assert transaction is not None
    assert transaction.transaction_id == "trans1"
    assert transaction.transaction_type == TransactionType.REVENUE
    assert transaction.amount == 100.0
    assert "trans1" in financial_intelligence_instance.transactions

def test_record_transaction_max_limit(financial_intelligence_instance):
    financial_intelligence_instance.config.max_transactions = 1
    financial_intelligence_instance.record_transaction("trans1", TransactionType.REVENUE, 100.0, "Sale")
    with patch("src.core.autonomous_intelligence_layer.financial_intelligence.financial_intelligence.logger") as mock_logger:
        transaction = financial_intelligence_instance.record_transaction("trans2", TransactionType.EXPENSE, 50.0, "Purchase")
        assert transaction is None
        mock_logger.error.assert_called_once_with("Maximum transactions limit reached", exc_info=True)

def test_create_budget(financial_intelligence_instance):
    budget = financial_intelligence_instance.create_budget("budget1", "Marketing", 1000.0)
    assert budget is not None
    assert budget.budget_id == "budget1"
    assert budget.category == "Marketing"
    assert budget.allocated_amount == 1000.0
    assert budget.spent_amount == 0.0
    assert "budget1" in financial_intelligence_instance.budgets

def test_update_budget_spending(financial_intelligence_instance):
    financial_intelligence_instance.create_budget("budget1", "Marketing", 1000.0)
    updated = financial_intelligence_instance.update_budget_spending("budget1", 200.0)
    assert updated is True
    assert financial_intelligence_instance.budgets["budget1"].spent_amount == 200.0

def test_update_budget_spending_not_found(financial_intelligence_instance):
    with patch("src.core.autonomous_intelligence_layer.financial_intelligence.financial_intelligence.logger") as mock_logger:
        updated = financial_intelligence_instance.update_budget_spending("nonexistent_budget", 100.0)
        assert updated is False
        mock_logger.error.assert_called_once_with("Budget nonexistent_budget not found", exc_info=True)

def test_update_budget_spending_alert(financial_intelligence_instance):
    financial_intelligence_instance.create_budget("budget1", "Marketing", 1000.0)
    financial_intelligence_instance.config.alert_threshold = 0.5
    with patch("src.core.autonomous_intelligence_layer.financial_intelligence.financial_intelligence.logger") as mock_logger:
        financial_intelligence_instance.update_budget_spending("budget1", 600.0)
        mock_logger.warning.assert_called_once()
        assert "Budget alert" in mock_logger.warning.call_args[0][0]

def test_calculate_metrics(financial_intelligence_instance):
    financial_intelligence_instance.record_transaction("rev1", TransactionType.REVENUE, 500.0, "Sale")
    financial_intelligence_instance.record_transaction("exp1", TransactionType.EXPENSE, 200.0, "Rent")
    financial_intelligence_instance.record_transaction("rev2", TransactionType.REVENUE, 300.0, "Service")

    metrics = financial_intelligence_instance.calculate_metrics()
    assert metrics[FinancialMetric.TOTAL_REVENUE] == 800.0
    assert metrics[FinancialMetric.TOTAL_COST] == 200.0
    assert metrics[FinancialMetric.PROFIT] == 600.0
    assert pytest.approx(metrics[FinancialMetric.MARGIN]) == 75.0

def test_calculate_metrics_no_revenue(financial_intelligence_instance):
    financial_intelligence_instance.record_transaction("exp1", TransactionType.EXPENSE, 200.0, "Rent")
    metrics = financial_intelligence_instance.calculate_metrics()
    assert metrics[FinancialMetric.MARGIN] == 0.0

def test_generate_report(financial_intelligence_instance):
    financial_intelligence_instance.record_transaction("rev1", TransactionType.REVENUE, 500.0, "Sale")
    financial_intelligence_instance.create_budget("budget1", "Marketing", 1000.0)
    report = financial_intelligence_instance.generate_report("report1", "Q1")
    assert report is not None
    assert report.report_id == "report1"
    assert report.period == "Q1"
    assert report.total_revenue == 500.0
    assert len(report.transactions) == 1
    assert len(report.budgets) == 1
    assert "report1" in financial_intelligence_instance.reports

def test_forecast_trend(financial_intelligence_instance):
    # Mock timestamps for predictable sorting
    with patch('src.core.autonomous_intelligence_layer.financial_intelligence.financial_intelligence.datetime') as mock_dt:
        mock_dt.now.return_value = datetime(2023, 1, 1, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *args, **kw: datetime.now(timezone.utc) if args else datetime(1, 1, 1, tzinfo=timezone.utc)
        financial_intelligence_instance.record_transaction("trans1", TransactionType.REVENUE, 100.0, "Old Sale")

    with patch('src.core.autonomous_intelligence_layer.financial_intelligence.financial_intelligence.datetime') as mock_dt:
        mock_dt.now.return_value = datetime(2023, 2, 1, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *args, **kw: datetime.now(timezone.utc) if args else datetime(1, 1, 1, tzinfo=timezone.utc)
        financial_intelligence_instance.record_transaction("trans2", TransactionType.REVENUE, 120.0, "Recent Sale")

    forecast = financial_intelligence_instance.forecast_trend(TransactionType.REVENUE, historical_periods=1)
    assert pytest.approx(forecast) == 120.0 * 1.1

def test_forecast_trend_no_transactions(financial_intelligence_instance):
    forecast = financial_intelligence_instance.forecast_trend(TransactionType.REVENUE)
    assert forecast == 0.0

def test_get_budget_status(financial_intelligence_instance):
    financial_intelligence_instance.create_budget("budget1", "Marketing", 1000.0)
    financial_intelligence_instance.update_budget_spending("budget1", 300.0)
    status = financial_intelligence_instance.get_budget_status("budget1")
    assert status is not None
    assert status["budget_id"] == "budget1"
    assert status["spent"] == 300.0
    assert status["remaining"] == 700.0
    assert pytest.approx(status["spending_ratio"]) == 0.3

def test_get_budget_status_not_found(financial_intelligence_instance):
    with patch("src.core.autonomous_intelligence_layer.financial_intelligence.financial_intelligence.logger") as mock_logger:
        status = financial_intelligence_instance.get_budget_status("nonexistent_budget")
        assert status is None
        mock_logger.error.assert_called_once_with("Budget nonexistent_budget not found", exc_info=True)

def test_get_transaction(financial_intelligence_instance):
    financial_intelligence_instance.record_transaction("trans1", TransactionType.REVENUE, 100.0, "Sale")
    transaction = financial_intelligence_instance.get_transaction("trans1")
    assert transaction is not None
    assert transaction.transaction_id == "trans1"
    assert financial_intelligence_instance.get_transaction("nonexistent") is None

def test_get_report(financial_intelligence_instance):
    financial_intelligence_instance.record_transaction("rev1", TransactionType.REVENUE, 500.0, "Sale")
    financial_intelligence_instance.generate_report("report1", "Q1")
    report = financial_intelligence_instance.get_report("report1")
    assert report is not None
    assert report.report_id == "report1"
    assert financial_intelligence_instance.get_report("nonexistent") is None
