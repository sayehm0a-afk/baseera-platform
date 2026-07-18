"""
Unit tests for Financial Intelligence
"""

import pytest
from core.autonomous_intelligence_layer.financial_intelligence import (
    FinancialIntelligence,
    TransactionType,
    FinancialMetric,
    FinancialIntelligenceConfig,
)


class TestFinancialIntelligence:
    """Test cases for FinancialIntelligence class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.fi = FinancialIntelligence()

    def test_financial_intelligence_initialization(self):
        """Test that FinancialIntelligence initializes correctly."""
        assert self.fi is not None
        assert self.fi.config is not None
        assert isinstance(self.fi.config, FinancialIntelligenceConfig)

    def test_financial_intelligence_with_custom_config(self):
        """Test FinancialIntelligence with custom config."""
        custom_config = FinancialIntelligenceConfig(
            currency="EUR",
            enable_forecasting=False,
        )
        fi = FinancialIntelligence(config=custom_config)
        assert fi.config.currency == "EUR"
        assert fi.config.enable_forecasting is False

    def test_record_transaction_expense(self):
        """Test recording an expense transaction."""
        transaction = self.fi.record_transaction(
            transaction_id="trans_001",
            transaction_type=TransactionType.EXPENSE,
            amount=100.0,
            description="Server costs",
        )

        assert transaction is not None
        assert transaction.amount == 100.0
        assert transaction.transaction_type == TransactionType.EXPENSE

    def test_record_transaction_revenue(self):
        """Test recording a revenue transaction."""
        transaction = self.fi.record_transaction(
            transaction_id="trans_001",
            transaction_type=TransactionType.REVENUE,
            amount=500.0,
            description="API sales",
        )

        assert transaction is not None
        assert transaction.amount == 500.0
        assert transaction.transaction_type == TransactionType.REVENUE

    def test_create_budget(self):
        """Test creating a budget."""
        budget = self.fi.create_budget(
            budget_id="budget_001",
            category="Operations",
            allocated_amount=1000.0,
        )

        assert budget is not None
        assert budget.allocated_amount == 1000.0
        assert budget.spent_amount == 0.0

    def test_update_budget_spending(self):
        """Test updating budget spending."""
        self.fi.create_budget(
            budget_id="budget_001",
            category="Operations",
            allocated_amount=1000.0,
        )

        result = self.fi.update_budget_spending(
            budget_id="budget_001",
            amount=300.0,
        )

        assert result is True

        budget = self.fi.budgets["budget_001"]
        assert budget.spent_amount == 300.0

    def test_update_nonexistent_budget(self):
        """Test updating nonexistent budget."""
        result = self.fi.update_budget_spending(
            budget_id="nonexistent",
            amount=100.0,
        )

        assert result is False

    def test_calculate_metrics(self):
        """Test calculating financial metrics."""
        self.fi.record_transaction(
            transaction_id="trans_001",
            transaction_type=TransactionType.REVENUE,
            amount=1000.0,
            description="Revenue",
        )

        self.fi.record_transaction(
            transaction_id="trans_002",
            transaction_type=TransactionType.EXPENSE,
            amount=300.0,
            description="Expense",
        )

        metrics = self.fi.calculate_metrics()

        assert metrics[FinancialMetric.TOTAL_REVENUE] == 1000.0
        assert metrics[FinancialMetric.TOTAL_COST] == 300.0
        assert metrics[FinancialMetric.PROFIT] == 700.0

    def test_calculate_margin(self):
        """Test margin calculation."""
        self.fi.record_transaction(
            transaction_id="trans_001",
            transaction_type=TransactionType.REVENUE,
            amount=1000.0,
            description="Revenue",
        )

        self.fi.record_transaction(
            transaction_id="trans_002",
            transaction_type=TransactionType.EXPENSE,
            amount=300.0,
            description="Expense",
        )

        metrics = self.fi.calculate_metrics()
        # (1000 - 300) / 1000 * 100 = 70%
        assert metrics[FinancialMetric.MARGIN] == 70.0

    def test_generate_report(self):
        """Test generating a financial report."""
        self.fi.record_transaction(
            transaction_id="trans_001",
            transaction_type=TransactionType.REVENUE,
            amount=1000.0,
            description="Revenue",
        )

        self.fi.record_transaction(
            transaction_id="trans_002",
            transaction_type=TransactionType.EXPENSE,
            amount=300.0,
            description="Expense",
        )

        report = self.fi.generate_report(
            report_id="report_001",
            period="2026-Q1",
        )

        assert report is not None
        assert report.total_revenue == 1000.0
        assert report.total_expenses == 300.0
        assert report.profit == 700.0

    def test_forecast_trend_revenue(self):
        """Test forecasting revenue trend."""
        for i in range(5):
            self.fi.record_transaction(
                transaction_id=f"trans_{i:03d}",
                transaction_type=TransactionType.REVENUE,
                amount=100.0 + i * 10,
                description="Revenue",
            )

        forecast = self.fi.forecast_trend(TransactionType.REVENUE)
        assert forecast > 0

    def test_forecast_trend_no_transactions(self):
        """Test forecasting with no transactions."""
        forecast = self.fi.forecast_trend(TransactionType.REVENUE)
        assert forecast == 0.0

    def test_get_budget_status(self):
        """Test getting budget status."""
        self.fi.create_budget(
            budget_id="budget_001",
            category="Operations",
            allocated_amount=1000.0,
        )

        self.fi.update_budget_spending(
            budget_id="budget_001",
            amount=600.0,
        )

        status = self.fi.get_budget_status("budget_001")

        assert status is not None
        assert status["allocated"] == 1000.0
        assert status["spent"] == 600.0
        assert status["remaining"] == 400.0
        assert status["spending_ratio"] == 0.6

    def test_get_nonexistent_budget_status(self):
        """Test getting status of nonexistent budget."""
        status = self.fi.get_budget_status("nonexistent")
        assert status is None

    def test_get_transaction(self):
        """Test retrieving a transaction."""
        self.fi.record_transaction(
            transaction_id="trans_001",
            transaction_type=TransactionType.EXPENSE,
            amount=100.0,
            description="Server costs",
        )

        transaction = self.fi.get_transaction("trans_001")
        assert transaction is not None
        assert transaction.amount == 100.0

    def test_get_nonexistent_transaction(self):
        """Test retrieving nonexistent transaction."""
        transaction = self.fi.get_transaction("nonexistent")
        assert transaction is None

    def test_get_report(self):
        """Test retrieving a report."""
        self.fi.record_transaction(
            transaction_id="trans_001",
            transaction_type=TransactionType.REVENUE,
            amount=1000.0,
            description="Revenue",
        )

        self.fi.generate_report(
            report_id="report_001",
            period="2026-Q1",
        )

        report = self.fi.get_report("report_001")
        assert report is not None
        assert report.period == "2026-Q1"

    def test_multiple_transactions(self):
        """Test handling multiple transactions."""
        for i in range(10):
            self.fi.record_transaction(
                transaction_id=f"trans_{i:03d}",
                transaction_type=TransactionType.EXPENSE if i % 2 == 0 else TransactionType.REVENUE,
                amount=100.0 + i * 10,
                description=f"Transaction {i}",
            )

        assert len(self.fi.transactions) == 10

    def test_budget_alert_threshold(self):
        """Test budget alert threshold."""
        custom_config = FinancialIntelligenceConfig(
            enable_alerts=True,
            alert_threshold=0.8,
        )
        fi = FinancialIntelligence(config=custom_config)

        fi.create_budget(
            budget_id="budget_001",
            category="Operations",
            allocated_amount=1000.0,
        )

        # Spend 85% of budget (should trigger alert)
        result = fi.update_budget_spending(
            budget_id="budget_001",
            amount=850.0,
        )

        assert result is True

    def test_multiple_budgets(self):
        """Test handling multiple budgets."""
        for i in range(5):
            self.fi.create_budget(
                budget_id=f"budget_{i:03d}",
                category=f"Category {i}",
                allocated_amount=1000.0 + i * 100,
            )

        assert len(self.fi.budgets) == 5

    def test_zero_revenue_margin(self):
        """Test margin calculation with zero revenue."""
        self.fi.record_transaction(
            transaction_id="trans_001",
            transaction_type=TransactionType.EXPENSE,
            amount=100.0,
            description="Expense",
        )

        metrics = self.fi.calculate_metrics()
        assert metrics[FinancialMetric.MARGIN] == 0.0

    def test_transaction_refund(self):
        """Test recording a refund transaction."""
        transaction = self.fi.record_transaction(
            transaction_id="trans_001",
            transaction_type=TransactionType.REFUND,
            amount=50.0,
            description="Customer refund",
        )

        assert transaction is not None
        assert transaction.transaction_type == TransactionType.REFUND
