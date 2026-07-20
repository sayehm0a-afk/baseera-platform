
import pytest
from datetime import datetime, timedelta, UTC
from src.core.autonomous_intelligence_layer.roi_calculator.roi_calculator import (
    ROICalculator, ROICalculatorConfig, Investment, Return, ROIAnalysis, InvestmentType
)

@pytest.fixture
def roi_calculator():
    return ROICalculator()

@pytest.fixture
def sample_config():
    return ROICalculatorConfig(
        currency="EUR",
        enable_payback_analysis=True,
        max_investments=10
    )

def test_roi_calculator_init(roi_calculator, sample_config):
    assert isinstance(roi_calculator.config, ROICalculatorConfig)
    assert not roi_calculator.investments
    assert not roi_calculator.returns
    assert not roi_calculator.analyses

    custom_calculator = ROICalculator(config=sample_config)
    assert custom_calculator.config == sample_config

def test_record_investment_success(roi_calculator):
    investment = roi_calculator.record_investment(
        "inv1", InvestmentType.INFRASTRUCTURE, 1000.0, "New server infrastructure"
    )
    assert isinstance(investment, Investment)
    assert investment.investment_id == "inv1"
    assert roi_calculator.get_investment("inv1") == investment

def test_record_investment_limit_reached(roi_calculator, sample_config):
    custom_calculator = ROICalculator(config=sample_config)
    for i in range(sample_config.max_investments):
        custom_calculator.record_investment(f"inv{i}", InvestmentType.TOOL, 100.0, "Tool")
    
    investment = custom_calculator.record_investment(
        "inv_exceed", InvestmentType.TOOL, 100.0, "Exceed limit"
    )
    assert investment is None

def test_record_return_success(roi_calculator):
    roi_calculator.record_investment("inv1", InvestmentType.INFRASTRUCTURE, 1000.0, "New server infrastructure")
    ret = roi_calculator.record_return("ret1", "inv1", 200.0, "Savings from efficiency")
    assert isinstance(ret, Return)
    assert ret.return_id == "ret1"
    assert roi_calculator.get_return("ret1") == ret

def test_record_return_investment_not_found(roi_calculator):
    ret = roi_calculator.record_return("ret1", "non_existent_inv", 200.0, "Savings")
    assert ret is None

def test_calculate_roi_positive(roi_calculator):
    roi_calculator.record_investment("inv1", InvestmentType.INFRASTRUCTURE, 1000.0, "New server infrastructure")
    roi_calculator.record_return("ret1", "inv1", 700.0, "Savings 1")
    roi_calculator.record_return("ret2", "inv1", 500.0, "Savings 2")
    
    analysis = roi_calculator.calculate_roi("analysis1", "inv1")
    assert isinstance(analysis, ROIAnalysis)
    assert analysis.roi_percentage == pytest.approx(20.0)
    assert analysis.net_profit == 200.0
    assert analysis.roi_status == "POSITIVE"
    assert analysis.payback_period_days is not None

def test_calculate_roi_negative(roi_calculator):
    roi_calculator.record_investment("inv1", InvestmentType.INFRASTRUCTURE, 1000.0, "New server infrastructure")
    roi_calculator.record_return("ret1", "inv1", 200.0, "Savings 1")
    
    analysis = roi_calculator.calculate_roi("analysis1", "inv1")
    assert isinstance(analysis, ROIAnalysis)
    assert analysis.roi_percentage == pytest.approx(-80.0)
    assert analysis.net_profit == -800.0
    assert analysis.roi_status == "NEGATIVE"
    assert analysis.payback_period_days is None

def test_calculate_roi_break_even(roi_calculator):
    roi_calculator.record_investment("inv1", InvestmentType.INFRASTRUCTURE, 1000.0, "New server infrastructure")
    roi_calculator.record_return("ret1", "inv1", 1000.0, "Savings")
    
    analysis = roi_calculator.calculate_roi("analysis1", "inv1")
    assert isinstance(analysis, ROIAnalysis)
    assert analysis.roi_percentage == pytest.approx(0.0)
    assert analysis.net_profit == 0.0
    assert analysis.roi_status == "BREAK_EVEN"
    assert analysis.payback_period_days is not None

def test_calculate_roi_no_returns(roi_calculator):
    roi_calculator.record_investment("inv1", InvestmentType.INFRASTRUCTURE, 1000.0, "New server infrastructure")
    
    analysis = roi_calculator.calculate_roi("analysis1", "inv1")
    assert isinstance(analysis, ROIAnalysis)
    assert analysis.roi_percentage == pytest.approx(-100.0)
    assert analysis.net_profit == -1000.0
    assert analysis.roi_status == "NEGATIVE"
    assert analysis.payback_period_days is None

def test_calculate_roi_investment_not_found(roi_calculator):
    analysis = roi_calculator.calculate_roi("analysis1", "non_existent_inv")
    assert analysis is None

def test_payback_period_calculation(roi_calculator):
    roi_calculator.record_investment("inv1", InvestmentType.INFRASTRUCTURE, 1000.0, "New server infrastructure")
    
    # Simulate returns over time
    now = datetime.now(UTC)
    roi_calculator.returns["ret1"] = Return("ret1", "inv1", 300.0, "R1", timestamp=now - timedelta(days=30))
    roi_calculator.returns["ret2"] = Return("ret2", "inv1", 400.0, "R2", timestamp=now - timedelta(days=15))
    roi_calculator.returns["ret3"] = Return("ret3", "inv1", 500.0, "R3", timestamp=now)

    analysis = roi_calculator.calculate_roi("analysis1", "inv1")
    assert analysis.payback_period_days == pytest.approx(0) # Because the last return makes it break even on the same day

def test_payback_period_disabled(roi_calculator):
    roi_calculator.config.enable_payback_analysis = False
    roi_calculator.record_investment("inv1", InvestmentType.INFRASTRUCTURE, 1000.0, "New server infrastructure")
    roi_calculator.record_return("ret1", "inv1", 1200.0, "Savings")
    analysis = roi_calculator.calculate_roi("analysis1", "inv1")
    assert analysis.payback_period_days is None

def test_get_investment(roi_calculator):
    inv = roi_calculator.record_investment("inv1", InvestmentType.TOOL, 500.0, "Tool A")
    assert roi_calculator.get_investment("inv1") == inv
    assert roi_calculator.get_investment("non_existent") is None

def test_get_return(roi_calculator):
    roi_calculator.record_investment("inv1", InvestmentType.TOOL, 500.0, "Tool A")
    ret = roi_calculator.record_return("ret1", "inv1", 100.0, "Return A")
    assert roi_calculator.get_return("ret1") == ret
    assert roi_calculator.get_return("non_existent") is None

def test_get_analysis(roi_calculator):
    roi_calculator.record_investment("inv1", InvestmentType.INFRASTRUCTURE, 1000.0, "New server infrastructure")
    roi_calculator.record_return("ret1", "inv1", 1200.0, "Savings")
    analysis = roi_calculator.calculate_roi("analysis1", "inv1")
    assert roi_calculator.get_analysis("analysis1") == analysis
    assert roi_calculator.get_analysis("non_existent") is None

def test_get_investment_returns(roi_calculator):
    roi_calculator.record_investment("inv1", InvestmentType.INFRASTRUCTURE, 1000.0, "New server infrastructure")
    ret1 = roi_calculator.record_return("ret1", "inv1", 200.0, "Savings 1")
    ret2 = roi_calculator.record_return("ret2", "inv1", 300.0, "Savings 2")
    roi_calculator.record_return("ret3", "inv2", 100.0, "Savings 3")
    
    investment_returns = roi_calculator.get_investment_returns("inv1")
    assert len(investment_returns) == 2
    assert ret1 in investment_returns
    assert ret2 in investment_returns

def test_compare_investments(roi_calculator):
    roi_calculator.record_investment("inv1", InvestmentType.INFRASTRUCTURE, 1000.0, "Infra")
    roi_calculator.record_return("ret1", "inv1", 1200.0, "R1")
    
    roi_calculator.record_investment("inv2", InvestmentType.TOOL, 500.0, "Tool")
    roi_calculator.record_return("ret2", "inv2", 400.0, "R2")
    
    comparison = roi_calculator.compare_investments(["inv1", "inv2", "inv3"])
    assert "inv1" in comparison
    assert comparison["inv1"]["roi_percentage"] == pytest.approx(20.0)
    assert "inv2" in comparison
    assert comparison["inv2"]["roi_percentage"] == pytest.approx(-20.0)
    assert "inv3" not in comparison

def test_get_best_roi_investment(roi_calculator):
    roi_calculator.record_investment("inv1", InvestmentType.INFRASTRUCTURE, 1000.0, "Infra")
    roi_calculator.record_return("ret1", "inv1", 1500.0, "R1") # ROI 50%
    
    roi_calculator.record_investment("inv2", InvestmentType.TOOL, 500.0, "Tool")
    roi_calculator.record_return("ret2", "inv2", 750.0, "R2") # ROI 50%

    roi_calculator.record_investment("inv3", InvestmentType.RESEARCH, 2000.0, "Research")
    roi_calculator.record_return("ret3", "inv3", 1000.0, "R3") # ROI -50%

    best_inv = roi_calculator.get_best_roi_investment()
    assert best_inv in ["inv1", "inv2"] # Both have 50% ROI, order might vary

def test_get_best_roi_investment_empty(roi_calculator):
    best_inv = roi_calculator.get_best_roi_investment()
    assert best_inv is None

