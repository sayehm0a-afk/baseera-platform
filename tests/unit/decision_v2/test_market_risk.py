from datetime import datetime, timezone

from src.analysis.decision_v2.market_risk import (
    MARKET_RISK_LABELS_AR,
    MarketRiskState,
    classify_market_risk,
)
from src.market_intelligence.types import MarketBreadthSummary


def _breadth(buy=0, sell=0, scanned=20, confidence=60.0) -> MarketBreadthSummary:
    return MarketBreadthSummary(
        scan_run_id=1,
        generated_at=datetime.now(timezone.utc),
        symbols_scanned=scanned,
        buy_count=buy,
        sell_count=sell,
        average_confidence=confidence,
    )


class TestMarketClosed:
    def test_market_closed_with_no_breadth_data(self):
        result = classify_market_risk(market_is_open=False, breadth=None)
        assert result.state == MarketRiskState.MARKET_CLOSED
        assert result.is_live is False
        assert result.entry_permitted is True
        assert "لا تتوفر" in result.basis_ar

    def test_market_closed_with_too_few_symbols_for_last_session_display(self):
        result = classify_market_risk(market_is_open=False, breadth=_breadth(buy=5, sell=1, scanned=5))
        assert result.state == MarketRiskState.MARKET_CLOSED
        assert result.is_live is False
        assert "5" in result.basis_ar

    def test_market_closed_shows_last_session_state_in_basis(self):
        result = classify_market_risk(
            market_is_open=False, breadth=_breadth(buy=15, sell=2, scanned=20, confidence=70.0)
        )
        assert result.state == MarketRiskState.MARKET_CLOSED
        assert result.is_live is False
        assert result.buy_count == 15
        assert result.sell_count == 2
        assert MARKET_RISK_LABELS_AR[MarketRiskState.STRONG_ENTRY] in result.basis_ar
        assert result.entry_permitted is True  # closed market never itself blocks


class TestInsufficientData:
    def test_open_market_no_breadth_is_insufficient_data(self):
        result = classify_market_risk(market_is_open=True, breadth=None)
        assert result.state == MarketRiskState.INSUFFICIENT_DATA
        assert result.entry_permitted is True
        assert result.is_live is False

    def test_open_market_too_few_symbols_is_insufficient_data(self):
        result = classify_market_risk(market_is_open=True, breadth=_breadth(buy=3, sell=1, scanned=4))
        assert result.state == MarketRiskState.INSUFFICIENT_DATA
        assert result.entry_permitted is True


class TestLiveBreadthClassification:
    def test_strong_entry_requires_high_ratio_and_confidence(self):
        result = classify_market_risk(
            market_is_open=True, breadth=_breadth(buy=14, sell=2, scanned=20, confidence=70.0)
        )
        assert result.state == MarketRiskState.STRONG_ENTRY
        assert result.entry_permitted is True
        assert result.is_live is True

    def test_high_ratio_but_low_confidence_is_not_strong_entry(self):
        result = classify_market_risk(
            market_is_open=True, breadth=_breadth(buy=14, sell=2, scanned=20, confidence=40.0)
        )
        assert result.state == MarketRiskState.SELECTIVE_ENTRY

    def test_selective_entry_band(self):
        result = classify_market_risk(market_is_open=True, breadth=_breadth(buy=11, sell=9, scanned=20))
        assert result.state == MarketRiskState.SELECTIVE_ENTRY
        assert result.entry_permitted is True

    def test_neutral_band(self):
        result = classify_market_risk(market_is_open=True, breadth=_breadth(buy=10, sell=10, scanned=20))
        assert result.state == MarketRiskState.NEUTRAL
        assert result.entry_permitted is True

    def test_caution_band_still_permits_entry(self):
        result = classify_market_risk(market_is_open=True, breadth=_breadth(buy=7, sell=13, scanned=20))
        assert result.state == MarketRiskState.CAUTION
        assert result.entry_permitted is True

    def test_reduce_positions_blocks_entry(self):
        result = classify_market_risk(market_is_open=True, breadth=_breadth(buy=5, sell=15, scanned=20))
        assert result.state == MarketRiskState.REDUCE_POSITIONS
        assert result.entry_permitted is False

    def test_partial_exit_blocks_entry(self):
        result = classify_market_risk(market_is_open=True, breadth=_breadth(buy=3, sell=17, scanned=20))
        assert result.state == MarketRiskState.PARTIAL_EXIT
        assert result.entry_permitted is False

    def test_defensive_exit_blocks_entry(self):
        result = classify_market_risk(market_is_open=True, breadth=_breadth(buy=1, sell=19, scanned=20))
        assert result.state == MarketRiskState.DEFENSIVE_EXIT
        assert result.entry_permitted is False

    def test_zero_buy_and_sell_signals_is_neutral_not_a_crash(self):
        result = classify_market_risk(market_is_open=True, breadth=_breadth(buy=0, sell=0, scanned=20))
        assert result.state == MarketRiskState.NEUTRAL

    def test_basis_ar_cites_real_counts_not_generic_filler(self):
        result = classify_market_risk(
            market_is_open=True, breadth=_breadth(buy=14, sell=2, scanned=20, confidence=70.0)
        )
        assert "14" in result.basis_ar
        assert "2" in result.basis_ar
        assert "20" in result.basis_ar

    def test_all_nine_states_have_arabic_labels(self):
        assert len(MARKET_RISK_LABELS_AR) == 9
        for state in MarketRiskState:
            assert state in MARKET_RISK_LABELS_AR
            assert MARKET_RISK_LABELS_AR[state]
