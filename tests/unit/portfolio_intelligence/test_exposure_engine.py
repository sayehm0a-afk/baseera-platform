"""Unit tests for ExposureEngine -- dollar-weighted sector exposure,
distinct from market_intelligence's equal-weighted sector averaging.
"""

from src.portfolio_intelligence.exposure_engine import ExposureEngine
from tests.unit.portfolio_intelligence._fixtures import make_holding_analysis


def test_exposure_is_dollar_weighted_not_symbol_count_weighted():
    holdings = [
        make_holding_analysis(symbol="A", sector="Energy", quantity=100, latest_price=100.0),  # 10000
        make_holding_analysis(symbol="B", sector="Energy", quantity=1, latest_price=100.0),  # 100
        make_holding_analysis(symbol="C", sector="Banks", quantity=100, latest_price=1.0),  # 100
    ]
    total_value = 10000 + 100 + 100
    exposures = {e.sector: e for e in ExposureEngine().compute(holdings, total_value)}

    # Energy holds 2 of 3 symbols but should dominate by dollar value, not count.
    assert exposures["Energy"].market_value == 10100
    assert exposures["Energy"].holdings_count == 2
    assert round(exposures["Energy"].weight, 4) == round(10100 / total_value, 4)
    assert exposures["Banks"].market_value == 100


def test_missing_sector_falls_back_to_unclassified():
    holdings = [make_holding_analysis(symbol="A", sector=None, quantity=10, latest_price=10.0)]
    exposures = ExposureEngine().compute(holdings, total_value=100.0)
    assert exposures[0].sector == "Unclassified"


def test_unavailable_holdings_excluded():
    holdings = [make_holding_analysis(symbol="A", unavailable=True)]
    exposures = ExposureEngine().compute(holdings, total_value=1000.0)
    assert exposures == []


def test_exposures_sorted_by_weight_descending():
    holdings = [
        make_holding_analysis(symbol="A", sector="Small", quantity=1, latest_price=10.0),
        make_holding_analysis(symbol="B", sector="Big", quantity=100, latest_price=100.0),
    ]
    exposures = ExposureEngine().compute(holdings, total_value=10010.0)
    assert [e.sector for e in exposures] == ["Big", "Small"]
