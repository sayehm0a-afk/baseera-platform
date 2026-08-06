"""Unit tests for the Investment Committee's eight agents -- pure
functions over hand-built `InvestmentDecision`/`DecisionResult`
fixtures (see _fixtures.py), no database except for `analyze_news`
(session is monkeypatched, same technique
tests/unit/ai_evolution/agents/test_llm_agents.py already uses).
"""

import pytest

from src.ai_evolution.committee import agents as committee_agents
from src.ai_evolution.agents import llm_agents as llm_agents_module
from src.analysis.decision.types import PositionSize
from src.domain.models import AgentStance
from tests.unit.ai_evolution.committee._fixtures import breakdown, make_decision_result, make_investment_decision


class TestAnalyzeTechnical:
    def test_unavailable_when_category_missing(self):
        decision = make_investment_decision(breakdown_items=[])
        result = make_decision_result()
        verdict = committee_agents.analyze_technical(decision, result)
        assert verdict.stance is AgentStance.UNAVAILABLE
        assert verdict.role == "technical"

    def test_bullish_and_evidence_includes_points_and_trend(self):
        decision = make_investment_decision(breakdown_items=[breakdown("Technical Analysis", points=12.0)])
        result = make_decision_result(trend_direction_ar="صاعد")
        verdict = committee_agents.analyze_technical(decision, result)
        assert verdict.stance is AgentStance.BULLISH
        assert any("صاعد" in e for e in verdict.evidence)

    def test_low_confidence_adds_rejection_reason(self):
        decision = make_investment_decision(breakdown_items=[breakdown("Technical Analysis", points=5.0, confidence=20.0)])
        verdict = committee_agents.analyze_technical(decision, make_decision_result())
        assert verdict.rejection_reasons


class TestAnalyzeFundamental:
    def test_unavailable_when_no_breakdown_and_no_ratios(self):
        empty_summary = {k: None for k in [
            "revenue_growth", "profit_growth", "net_profit_margin", "gross_profit_margin",
            "return_on_equity", "debt_to_equity", "price_to_earnings", "price_to_book",
            "dividend_yield", "eps_growth",
        ]}
        decision = make_investment_decision(breakdown_items=[])
        result = make_decision_result(fundamental_summary=empty_summary)
        verdict = committee_agents.analyze_fundamental(decision, result)
        assert verdict.stance is AgentStance.UNAVAILABLE

    def test_evidence_built_from_real_ratios(self):
        decision = make_investment_decision(breakdown_items=[breakdown("Fundamental Analysis", points=10.0)])
        result = make_decision_result()
        verdict = committee_agents.analyze_fundamental(decision, result)
        assert any("نمو الإيرادات" in e for e in verdict.evidence)
        assert verdict.stance is AgentStance.BULLISH


class TestAnalyzeMarketSentiment:
    def test_unavailable_without_breadth_data(self):
        result = make_decision_result(
            market_breadth_buy_count=None, market_breadth_sell_count=None, market_breadth_symbols_scanned=None,
        )
        verdict = committee_agents.analyze_market_sentiment(result)
        assert verdict.stance is AgentStance.UNAVAILABLE

    def test_bullish_when_buy_count_dominates(self):
        result = make_decision_result(
            market_breadth_buy_count=70, market_breadth_sell_count=10, market_breadth_symbols_scanned=100,
        )
        verdict = committee_agents.analyze_market_sentiment(result)
        assert verdict.stance is AgentStance.BULLISH

    def test_bearish_when_sell_count_dominates(self):
        result = make_decision_result(
            market_breadth_buy_count=10, market_breadth_sell_count=70, market_breadth_symbols_scanned=100,
        )
        verdict = committee_agents.analyze_market_sentiment(result)
        assert verdict.stance is AgentStance.BEARISH

    def test_neutral_when_balanced(self):
        result = make_decision_result(
            market_breadth_buy_count=50, market_breadth_sell_count=48, market_breadth_symbols_scanned=100,
        )
        verdict = committee_agents.analyze_market_sentiment(result)
        assert verdict.stance is AgentStance.NEUTRAL

    def test_rejection_reason_when_entry_not_permitted(self):
        result = make_decision_result(
            market_breadth_buy_count=70, market_breadth_sell_count=10, market_breadth_symbols_scanned=100,
            market_risk_entry_permitted=False,
        )
        verdict = committee_agents.analyze_market_sentiment(result)
        assert verdict.rejection_reasons


class TestAnalyzeRisk:
    def test_unavailable_when_category_missing(self):
        decision = make_investment_decision(breakdown_items=[])
        verdict = committee_agents.analyze_risk(decision, make_decision_result())
        assert verdict.stance is AgentStance.UNAVAILABLE

    def test_failing_gate_becomes_rejection_reason(self):
        from src.analysis.decision_v2.types import GateOutcome, GateStatus
        decision = make_investment_decision(breakdown_items=[breakdown("Risk", points=10.0)])
        result = make_decision_result(
            gates=[GateOutcome(name="thin_liquidity", status=GateStatus.FAIL, detail="سيولة ضعيفة", blocking=True)]
        )
        verdict = committee_agents.analyze_risk(decision, result)
        assert any("سيولة ضعيفة" in r for r in verdict.rejection_reasons)


class TestAnalyzeLiquidityVolume:
    def test_unavailable_without_liquidity_data(self):
        result = make_decision_result(liquidity_confidence=None, relative_volume=None)
        verdict = committee_agents.analyze_liquidity_volume(result)
        assert verdict.stance is AgentStance.UNAVAILABLE

    def test_bullish_when_volume_confirms_and_not_abnormal(self):
        result = make_decision_result(volume_confirms_decision=True, abnormal_volume=False)
        verdict = committee_agents.analyze_liquidity_volume(result)
        assert verdict.stance is AgentStance.BULLISH

    def test_bearish_when_abnormal_volume(self):
        result = make_decision_result(abnormal_volume=True)
        verdict = committee_agents.analyze_liquidity_volume(result)
        assert verdict.stance is AgentStance.BEARISH
        assert verdict.rejection_reasons


class TestAnalyzeMacro:
    def test_always_unavailable(self):
        verdict = committee_agents.analyze_macro()
        assert verdict.stance is AgentStance.UNAVAILABLE
        assert verdict.role == "macro"
        assert verdict.rejection_reasons


class TestAnalyzePortfolioAllocation:
    def test_bearish_when_position_size_none(self):
        decision = make_investment_decision(position_size=PositionSize.NONE)
        verdict = committee_agents.analyze_portfolio_allocation(decision, make_decision_result())
        assert verdict.stance is AgentStance.BEARISH
        assert verdict.rejection_reasons

    def test_bullish_when_standard_size_and_good_risk_reward(self):
        decision = make_investment_decision(position_size=PositionSize.STANDARD)
        result = make_decision_result(risk_reward_target_1=2.5)
        verdict = committee_agents.analyze_portfolio_allocation(decision, result)
        assert verdict.stance is AgentStance.BULLISH

    def test_bearish_when_risk_reward_below_minimum(self):
        decision = make_investment_decision(position_size=PositionSize.SMALL)
        result = make_decision_result(risk_reward_target_1=0.5)
        verdict = committee_agents.analyze_portfolio_allocation(decision, result)
        assert verdict.stance is AgentStance.BEARISH
        assert verdict.rejection_reasons


@pytest.fixture
def fake_session():
    return object()


class TestAnalyzeNews:
    @pytest.mark.asyncio
    async def test_unavailable_without_llm_adapter_and_no_events(self, fake_session, monkeypatch):
        monkeypatch.setattr(committee_agents, "get_agent_panel_llm_adapter", lambda: None)
        monkeypatch.setattr(llm_agents_module, "_load_symbol_sentiment", lambda session, symbol: None)
        verdict = await committee_agents.analyze_news(fake_session, "2222", news_events=[])
        assert verdict.stance is AgentStance.UNAVAILABLE
        assert verdict.rejection_reasons

    @pytest.mark.asyncio
    async def test_evidence_built_from_real_news_events(self, fake_session, monkeypatch):
        monkeypatch.setattr(committee_agents, "get_agent_panel_llm_adapter", lambda: None)
        monkeypatch.setattr(llm_agents_module, "_load_symbol_sentiment", lambda session, symbol: None)
        events = [
            {"headline": "أرباح فصلية قوية", "category": "EARNINGS", "sentiment_score": 0.6, "confidence": 80.0,
             "impact_points": 5.0},
        ]
        verdict = await committee_agents.analyze_news(fake_session, "2222", news_events=events)
        assert any("أرباح فصلية قوية" in e for e in verdict.evidence)
        assert verdict.rejection_reasons == []
