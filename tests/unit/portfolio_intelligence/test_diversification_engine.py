"""Unit tests for DiversificationEngine."""

from src.portfolio_intelligence.diversification_engine import DiversificationEngine
from src.portfolio_intelligence.types import SectorExposure
from tests.unit.portfolio_intelligence._fixtures import make_holding_analysis


def _sector(sector, weight):
    return SectorExposure(sector=sector, market_value=weight * 1000, weight=weight, holdings_count=1, symbols=[sector])


def test_equal_weights_produce_high_diversification_score():
    # 5 equal holdings (20% each) sit below the default 25% concentration
    # threshold, so this also exercises the "not concentrated" path.
    holdings = [make_holding_analysis(symbol=f"S{i}", weight=0.2) for i in range(5)]
    sectors = [_sector(f"Sector{i}", 0.2) for i in range(5)]
    diversification, concentration = DiversificationEngine().compute(holdings, sectors)

    assert diversification.effective_number_of_holdings == 5.0
    assert diversification.score > 70.0
    assert concentration.is_concentrated is False


def test_single_position_is_flagged_as_concentrated():
    holdings = [make_holding_analysis(symbol="A", weight=1.0)]
    sectors = [_sector("Energy", 1.0)]
    diversification, concentration = DiversificationEngine().compute(holdings, sectors)

    assert concentration.is_concentrated is True
    assert concentration.largest_position_symbol == "A"
    assert concentration.largest_position_weight == 1.0
    assert diversification.effective_number_of_holdings == 1.0
    assert diversification.score < 50.0


def test_top_3_weight_sums_the_three_largest_positions():
    holdings = [
        make_holding_analysis(symbol="A", weight=0.5),
        make_holding_analysis(symbol="B", weight=0.3),
        make_holding_analysis(symbol="C", weight=0.1),
        make_holding_analysis(symbol="D", weight=0.1),
    ]
    _, concentration = DiversificationEngine().compute(holdings, [])
    assert concentration.top_3_weight == 0.9


def test_concentration_threshold_is_configurable(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_POSITION_CONCENTRATION_THRESHOLD", "0.5")
    holdings = [make_holding_analysis(symbol="A", weight=0.4), make_holding_analysis(symbol="B", weight=0.6)]
    _, concentration = DiversificationEngine().compute(holdings, [])
    assert concentration.is_concentrated is True  # 0.6 >= 0.5
    assert concentration.concentration_threshold == 0.5


def test_no_holdings_yields_zero_score_not_a_crash():
    diversification, concentration = DiversificationEngine().compute([], [])
    assert diversification.score == 0.0
    assert concentration.largest_position_symbol is None
