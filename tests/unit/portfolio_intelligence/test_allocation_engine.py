"""Unit tests for AllocationEngine."""

from src.portfolio_intelligence.allocation_engine import AllocationEngine
from tests.unit.portfolio_intelligence._fixtures import make_holding_analysis


def test_weights_computed_against_total_value_including_cash():
    holdings = [
        make_holding_analysis(symbol="A", quantity=10, latest_price=100.0, weight=None),  # 1000
        make_holding_analysis(symbol="B", quantity=10, latest_price=50.0, weight=None),  # 500
    ]
    breakdown = AllocationEngine().compute(holdings, cash=500.0)

    assert breakdown.total_value == 2000.0
    entries = {e.symbol: e for e in breakdown.entries}
    assert entries["A"].weight == 0.5
    assert entries["B"].weight == 0.25
    assert breakdown.cash_weight == 0.25


def test_holding_with_no_price_has_none_weight():
    holdings = [make_holding_analysis(symbol="A", unavailable=True)]
    breakdown = AllocationEngine().compute(holdings, cash=1000.0)
    assert breakdown.entries[0].weight is None
    assert breakdown.total_value == 1000.0


def test_zero_total_value_does_not_raise():
    breakdown = AllocationEngine().compute([], cash=0.0)
    assert breakdown.total_value == 0.0
    assert breakdown.cash_weight == 0.0
