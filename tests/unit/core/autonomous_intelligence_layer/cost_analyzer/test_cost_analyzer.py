import pytest
from datetime import datetime, UTC
from src.core.autonomous_intelligence_layer.cost_analyzer.cost_analyzer import (
    CostAnalyzer,
    CostOptimizerConfig,
    CostCategory,
    CostItem,
    CostAnalysis
)

@pytest.fixture
def cost_analyzer():
    return CostAnalyzer()

def test_record_cost(cost_analyzer):
    cost = cost_analyzer.record_cost("c1", CostCategory.COMPUTE, 100.0, "Compute cost")
    assert cost is not None
    assert cost.cost_id == "c1"
    assert cost.category == CostCategory.COMPUTE
    assert cost.amount == 100.0
    assert len(cost_analyzer.cost_items) == 1

def test_record_cost_max_limit():
    config = CostOptimizerConfig(max_cost_items=1)
    analyzer = CostAnalyzer(config)
    analyzer.record_cost("c1", CostCategory.COMPUTE, 100.0, "Compute cost")
    cost = analyzer.record_cost("c2", CostCategory.STORAGE, 50.0, "Storage cost")
    assert cost is None
    assert len(analyzer.cost_items) == 1

def test_analyze_costs(cost_analyzer):
    cost_analyzer.record_cost("c1", CostCategory.COMPUTE, 100.0, "Compute cost")
    cost_analyzer.record_cost("c2", CostCategory.STORAGE, 50.0, "Storage cost")
    cost_analyzer.record_cost("c3", CostCategory.COMPUTE, 150.0, "Another compute cost")

    analysis = cost_analyzer.analyze_costs("analysis_1")
    assert analysis is not None
    assert analysis.analysis_id == "analysis_1"
    assert analysis.total_cost == 300.0
    assert analysis.cost_by_category[CostCategory.COMPUTE] == 250.0
    assert analysis.cost_by_category[CostCategory.STORAGE] == 50.0
    assert len(analysis.optimization_opportunities) > 0

def test_analyze_trends(cost_analyzer):
    cost_analyzer.record_cost("c1", CostCategory.COMPUTE, 100.0, "Compute cost")
    cost_analyzer.record_cost("c2", CostCategory.COMPUTE, 120.0, "Compute cost")
    cost_analyzer.record_cost("c3", CostCategory.COMPUTE, 140.0, "Compute cost")

    trends = cost_analyzer._analyze_trends()
    assert CostCategory.COMPUTE.value in trends
    assert trends[CostCategory.COMPUTE.value] > 0 # Should be increasing trend

def test_generate_optimization_suggestions(cost_analyzer):
    cost_by_category = {
        CostCategory.COMPUTE: 1000.0,
        CostCategory.STORAGE: 100.0,
        CostCategory.API_CALLS: 50.0
    }
    suggestions = cost_analyzer._generate_optimization_suggestions(cost_by_category)
    assert len(suggestions) > 0
    assert "Consider optimizing compute resources or using auto-scaling" in suggestions

def test_getters(cost_analyzer):
    cost_analyzer.record_cost("c1", CostCategory.COMPUTE, 100.0, "Compute cost")
    cost_analyzer.record_cost("c2", CostCategory.STORAGE, 50.0, "Storage cost")

    assert cost_analyzer.get_total_cost() == 150.0

    cost_by_category = cost_analyzer.get_cost_by_category()
    assert cost_by_category[CostCategory.COMPUTE] == 100.0
    assert cost_by_category[CostCategory.STORAGE] == 50.0

    assert cost_analyzer.get_cost_item("c1") is not None
    assert cost_analyzer.get_cost_item("nonexistent") is None

    cost_analyzer.analyze_costs("analysis_1")
    assert cost_analyzer.get_analysis("analysis_1") is not None
    assert cost_analyzer.get_analysis("nonexistent") is None
