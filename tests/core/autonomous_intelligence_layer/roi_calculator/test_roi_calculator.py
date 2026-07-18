"""
Unit tests for ROI Calculator
"""

import pytest
from datetime import datetime, timedelta
from core.autonomous_intelligence_layer.roi_calculator import (
    ROICalculator,
    InvestmentType,
    ROICalculatorConfig,
)


class TestROICalculator:
    """Test cases for ROICalculator class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.calculator = ROICalculator()

    def test_roi_calculator_initialization(self):
        """Test that ROICalculator initializes correctly."""
        assert self.calculator is not None
        assert self.calculator.config is not None
        assert isinstance(self.calculator.config, ROICalculatorConfig)

    def test_roi_calculator_with_custom_config(self):
        """Test ROICalculator with custom config."""
        custom_config = ROICalculatorConfig(
            currency="EUR",
            enable_payback_analysis=False,
        )
        calculator = ROICalculator(config=custom_config)
        assert calculator.config.currency == "EUR"
        assert calculator.config.enable_payback_analysis is False

    def test_record_investment(self):
        """Test recording an investment."""
        investment = self.calculator.record_investment(
            investment_id="inv_001",
            investment_type=InvestmentType.INFRASTRUCTURE,
            initial_cost=1000.0,
            description="Server infrastructure",
        )

        assert investment is not None
        assert investment.initial_cost == 1000.0
        assert investment.investment_type == InvestmentType.INFRASTRUCTURE

    def test_record_return(self):
        """Test recording a return."""
        self.calculator.record_investment(
            investment_id="inv_001",
            investment_type=InvestmentType.INFRASTRUCTURE,
            initial_cost=1000.0,
            description="Server infrastructure",
        )

        return_obj = self.calculator.record_return(
            return_id="ret_001",
            investment_id="inv_001",
            amount=500.0,
            description="Monthly savings",
        )

        assert return_obj is not None
        assert return_obj.amount == 500.0

    def test_record_return_invalid_investment(self):
        """Test recording return for nonexistent investment."""
        return_obj = self.calculator.record_return(
            return_id="ret_001",
            investment_id="nonexistent",
            amount=500.0,
            description="Monthly savings",
        )

        assert return_obj is None

    def test_calculate_roi_positive(self):
        """Test calculating positive ROI."""
        self.calculator.record_investment(
            investment_id="inv_001",
            investment_type=InvestmentType.INFRASTRUCTURE,
            initial_cost=1000.0,
            description="Server infrastructure",
        )

        self.calculator.record_return(
            return_id="ret_001",
            investment_id="inv_001",
            amount=600.0,
            description="Return 1",
        )

        self.calculator.record_return(
            return_id="ret_002",
            investment_id="inv_001",
            amount=600.0,
            description="Return 2",
        )

        analysis = self.calculator.calculate_roi("analysis_001", "inv_001")

        assert analysis is not None
        assert analysis.total_return == 1200.0
        assert analysis.net_profit == 200.0
        assert analysis.roi_percentage == 20.0
        assert analysis.roi_status == "POSITIVE"

    def test_calculate_roi_negative(self):
        """Test calculating negative ROI."""
        self.calculator.record_investment(
            investment_id="inv_001",
            investment_type=InvestmentType.INFRASTRUCTURE,
            initial_cost=1000.0,
            description="Server infrastructure",
        )

        self.calculator.record_return(
            return_id="ret_001",
            investment_id="inv_001",
            amount=300.0,
            description="Return 1",
        )

        analysis = self.calculator.calculate_roi("analysis_001", "inv_001")

        assert analysis is not None
        assert analysis.total_return == 300.0
        assert analysis.net_profit == -700.0
        assert analysis.roi_percentage == -70.0
        assert analysis.roi_status == "NEGATIVE"

    def test_calculate_roi_break_even(self):
        """Test calculating break-even ROI."""
        self.calculator.record_investment(
            investment_id="inv_001",
            investment_type=InvestmentType.INFRASTRUCTURE,
            initial_cost=1000.0,
            description="Server infrastructure",
        )

        self.calculator.record_return(
            return_id="ret_001",
            investment_id="inv_001",
            amount=1000.0,
            description="Return 1",
        )

        analysis = self.calculator.calculate_roi("analysis_001", "inv_001")

        assert analysis is not None
        assert analysis.net_profit == 0.0
        assert analysis.roi_percentage == 0.0
        assert analysis.roi_status == "BREAK_EVEN"

    def test_calculate_roi_no_investment(self):
        """Test calculating ROI for nonexistent investment."""
        analysis = self.calculator.calculate_roi("analysis_001", "nonexistent")
        assert analysis is None

    def test_get_investment(self):
        """Test retrieving an investment."""
        self.calculator.record_investment(
            investment_id="inv_001",
            investment_type=InvestmentType.INFRASTRUCTURE,
            initial_cost=1000.0,
            description="Server infrastructure",
        )

        investment = self.calculator.get_investment("inv_001")
        assert investment is not None
        assert investment.initial_cost == 1000.0

    def test_get_return(self):
        """Test retrieving a return."""
        self.calculator.record_investment(
            investment_id="inv_001",
            investment_type=InvestmentType.INFRASTRUCTURE,
            initial_cost=1000.0,
            description="Server infrastructure",
        )

        self.calculator.record_return(
            return_id="ret_001",
            investment_id="inv_001",
            amount=500.0,
            description="Monthly savings",
        )

        return_obj = self.calculator.get_return("ret_001")
        assert return_obj is not None
        assert return_obj.amount == 500.0

    def test_get_analysis(self):
        """Test retrieving an analysis."""
        self.calculator.record_investment(
            investment_id="inv_001",
            investment_type=InvestmentType.INFRASTRUCTURE,
            initial_cost=1000.0,
            description="Server infrastructure",
        )

        self.calculator.record_return(
            return_id="ret_001",
            investment_id="inv_001",
            amount=500.0,
            description="Return",
        )

        self.calculator.calculate_roi("analysis_001", "inv_001")
        analysis = self.calculator.get_analysis("analysis_001")

        assert analysis is not None
        assert analysis.analysis_id == "analysis_001"

    def test_get_investment_returns(self):
        """Test getting all returns for an investment."""
        self.calculator.record_investment(
            investment_id="inv_001",
            investment_type=InvestmentType.INFRASTRUCTURE,
            initial_cost=1000.0,
            description="Server infrastructure",
        )

        for i in range(5):
            self.calculator.record_return(
                return_id=f"ret_{i:03d}",
                investment_id="inv_001",
                amount=200.0,
                description=f"Return {i}",
            )

        returns = self.calculator.get_investment_returns("inv_001")
        assert len(returns) == 5

    def test_compare_investments(self):
        """Test comparing multiple investments."""
        for i in range(3):
            self.calculator.record_investment(
                investment_id=f"inv_{i:03d}",
                investment_type=InvestmentType.INFRASTRUCTURE,
                initial_cost=1000.0 + i * 100,
                description=f"Investment {i}",
            )

            self.calculator.record_return(
                return_id=f"ret_{i:03d}",
                investment_id=f"inv_{i:03d}",
                amount=500.0 + i * 50,
                description=f"Return {i}",
            )

        comparison = self.calculator.compare_investments(
            ["inv_000", "inv_001", "inv_002"]
        )

        assert len(comparison) == 3
        assert "inv_000" in comparison

    def test_get_best_roi_investment(self):
        """Test getting investment with best ROI."""
        # Investment 1: 1000 -> 1500 (50% ROI)
        self.calculator.record_investment(
            investment_id="inv_001",
            investment_type=InvestmentType.INFRASTRUCTURE,
            initial_cost=1000.0,
            description="Investment 1",
        )

        self.calculator.record_return(
            return_id="ret_001",
            investment_id="inv_001",
            amount=1500.0,
            description="Return 1",
        )

        # Investment 2: 2000 -> 2200 (10% ROI)
        self.calculator.record_investment(
            investment_id="inv_002",
            investment_type=InvestmentType.INFRASTRUCTURE,
            initial_cost=2000.0,
            description="Investment 2",
        )

        self.calculator.record_return(
            return_id="ret_002",
            investment_id="inv_002",
            amount=2200.0,
            description="Return 2",
        )

        best_investment = self.calculator.get_best_roi_investment()
        assert best_investment == "inv_001"

    def test_get_best_roi_no_investments(self):
        """Test getting best ROI with no investments."""
        best_investment = self.calculator.get_best_roi_investment()
        assert best_investment is None

    def test_payback_period_calculation(self):
        """Test payback period calculation."""
        investment = self.calculator.record_investment(
            investment_id="inv_001",
            investment_type=InvestmentType.INFRASTRUCTURE,
            initial_cost=1000.0,
            description="Investment",
        )

        # Record returns over time
        for i in range(3):
            return_time = investment.timestamp + timedelta(days=i * 30)
            return_obj = self.calculator.record_return(
                return_id=f"ret_{i:03d}",
                investment_id="inv_001",
                amount=400.0,
                description=f"Return {i}",
            )
            # Manually set timestamp for testing
            return_obj.timestamp = return_time

        analysis = self.calculator.calculate_roi("analysis_001", "inv_001")

        # Payback should occur after second return (800 < 1000, 1200 > 1000)
        assert analysis.payback_period_days is not None

    def test_multiple_investment_types(self):
        """Test handling multiple investment types."""
        types = [
            InvestmentType.INFRASTRUCTURE,
            InvestmentType.TRAINING,
            InvestmentType.TOOL,
            InvestmentType.OPTIMIZATION,
            InvestmentType.RESEARCH,
        ]

        for i, inv_type in enumerate(types):
            self.calculator.record_investment(
                investment_id=f"inv_{i:03d}",
                investment_type=inv_type,
                initial_cost=1000.0 + i * 100,
                description=f"Investment {inv_type.value}",
            )

        assert len(self.calculator.investments) == len(types)
