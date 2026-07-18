"""
Unit tests for Cost Analyzer
"""

import pytest
from core.autonomous_intelligence_layer.cost_analyzer import (
    CostAnalyzer,
    CostCategory,
    CostOptimizerConfig,
)


class TestCostAnalyzer:
    """Test cases for CostAnalyzer class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.analyzer = CostAnalyzer()

    def test_cost_analyzer_initialization(self):
        """Test that CostAnalyzer initializes correctly."""
        assert self.analyzer is not None
        assert self.analyzer.config is not None
        assert isinstance(self.analyzer.config, CostOptimizerConfig)

    def test_cost_analyzer_with_custom_config(self):
        """Test CostAnalyzer with custom config."""
        custom_config = CostOptimizerConfig(
            enable_trend_analysis=False,
            enable_optimization_suggestions=False,
        )
        analyzer = CostAnalyzer(config=custom_config)
        assert analyzer.config.enable_trend_analysis is False

    def test_record_cost(self):
        """Test recording a cost item."""
        cost = self.analyzer.record_cost(
            cost_id="cost_001",
            category=CostCategory.COMPUTE,
            amount=100.0,
            description="Server costs",
        )

        assert cost is not None
        assert cost.amount == 100.0
        assert cost.category == CostCategory.COMPUTE

    def test_record_multiple_costs(self):
        """Test recording multiple costs."""
        for i in range(5):
            self.analyzer.record_cost(
                cost_id=f"cost_{i:03d}",
                category=CostCategory.COMPUTE if i % 2 == 0 else CostCategory.STORAGE,
                amount=100.0 + i * 10,
                description=f"Cost {i}",
            )

        assert len(self.analyzer.cost_items) == 5

    def test_analyze_costs(self):
        """Test analyzing costs."""
        self.analyzer.record_cost(
            cost_id="cost_001",
            category=CostCategory.COMPUTE,
            amount=500.0,
            description="Compute",
        )

        self.analyzer.record_cost(
            cost_id="cost_002",
            category=CostCategory.STORAGE,
            amount=300.0,
            description="Storage",
        )

        analysis = self.analyzer.analyze_costs("analysis_001")

        assert analysis is not None
        assert analysis.total_cost == 800.0
        assert CostCategory.COMPUTE in analysis.cost_by_category
        assert CostCategory.STORAGE in analysis.cost_by_category

    def test_get_cost_by_category(self):
        """Test getting cost by category."""
        self.analyzer.record_cost(
            cost_id="cost_001",
            category=CostCategory.COMPUTE,
            amount=500.0,
            description="Compute",
        )

        self.analyzer.record_cost(
            cost_id="cost_002",
            category=CostCategory.COMPUTE,
            amount=300.0,
            description="Compute",
        )

        self.analyzer.record_cost(
            cost_id="cost_003",
            category=CostCategory.STORAGE,
            amount=200.0,
            description="Storage",
        )

        cost_by_category = self.analyzer.get_cost_by_category()

        assert cost_by_category[CostCategory.COMPUTE] == 800.0
        assert cost_by_category[CostCategory.STORAGE] == 200.0

    def test_get_total_cost(self):
        """Test getting total cost."""
        self.analyzer.record_cost(
            cost_id="cost_001",
            category=CostCategory.COMPUTE,
            amount=500.0,
            description="Compute",
        )

        self.analyzer.record_cost(
            cost_id="cost_002",
            category=CostCategory.STORAGE,
            amount=300.0,
            description="Storage",
        )

        total = self.analyzer.get_total_cost()
        assert total == 800.0

    def test_get_cost_item(self):
        """Test retrieving a cost item."""
        self.analyzer.record_cost(
            cost_id="cost_001",
            category=CostCategory.COMPUTE,
            amount=100.0,
            description="Server costs",
        )

        cost = self.analyzer.get_cost_item("cost_001")
        assert cost is not None
        assert cost.amount == 100.0

    def test_get_nonexistent_cost_item(self):
        """Test retrieving nonexistent cost item."""
        cost = self.analyzer.get_cost_item("nonexistent")
        assert cost is None

    def test_get_analysis(self):
        """Test retrieving an analysis."""
        self.analyzer.record_cost(
            cost_id="cost_001",
            category=CostCategory.COMPUTE,
            amount=100.0,
            description="Compute",
        )

        self.analyzer.analyze_costs("analysis_001")
        analysis = self.analyzer.get_analysis("analysis_001")

        assert analysis is not None
        assert analysis.analysis_id == "analysis_001"

    def test_cost_trends_analysis(self):
        """Test cost trends analysis."""
        # Record costs with different timestamps
        for i in range(10):
            self.analyzer.record_cost(
                cost_id=f"cost_{i:03d}",
                category=CostCategory.COMPUTE,
                amount=100.0 + i * 5,
                description=f"Compute {i}",
            )

        analysis = self.analyzer.analyze_costs("analysis_001")

        assert "compute" in analysis.cost_trends

    def test_optimization_suggestions_high_compute(self):
        """Test optimization suggestions for high compute costs."""
        # Record high compute costs
        for i in range(10):
            self.analyzer.record_cost(
                cost_id=f"cost_{i:03d}",
                category=CostCategory.COMPUTE,
                amount=500.0,
                description="Compute",
            )

        analysis = self.analyzer.analyze_costs("analysis_001")

        # Should suggest compute optimization
        assert len(analysis.optimization_opportunities) > 0

    def test_optimization_suggestions_high_storage(self):
        """Test optimization suggestions for high storage costs."""
        # Record high storage costs
        for i in range(10):
            self.analyzer.record_cost(
                cost_id=f"cost_{i:03d}",
                category=CostCategory.STORAGE,
                amount=400.0,
                description="Storage",
            )

        analysis = self.analyzer.analyze_costs("analysis_001")

        # Should suggest storage optimization
        assert len(analysis.optimization_opportunities) > 0

    def test_multiple_cost_categories(self):
        """Test handling multiple cost categories."""
        categories = [
            CostCategory.COMPUTE,
            CostCategory.STORAGE,
            CostCategory.NETWORK,
            CostCategory.API_CALLS,
            CostCategory.PERSONNEL,
        ]

        for i, category in enumerate(categories):
            self.analyzer.record_cost(
                cost_id=f"cost_{i:03d}",
                category=category,
                amount=100.0 + i * 50,
                description=f"Cost {category.value}",
            )

        cost_by_category = self.analyzer.get_cost_by_category()
        assert len(cost_by_category) == len(categories)

    def test_cost_analysis_with_no_costs(self):
        """Test cost analysis with no recorded costs."""
        analysis = self.analyzer.analyze_costs("analysis_001")

        assert analysis is not None
        assert analysis.total_cost == 0.0
        assert len(analysis.cost_by_category) == 0

    def test_cost_item_metadata(self):
        """Test cost item metadata."""
        metadata = {"project": "test_project", "team": "engineering"}

        cost = self.analyzer.record_cost(
            cost_id="cost_001",
            category=CostCategory.COMPUTE,
            amount=100.0,
            description="Compute",
        )

        cost.metadata = metadata

        retrieved_cost = self.analyzer.get_cost_item("cost_001")
        assert retrieved_cost.metadata == metadata
