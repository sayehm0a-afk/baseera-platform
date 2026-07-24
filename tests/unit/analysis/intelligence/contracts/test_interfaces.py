"""Proves each Protocol in interfaces.py is actually satisfiable (not
vacuous) via minimal, test-only fake classes -- the same technique
tests/unit/core/autonomous_intelligence_layer/contracts/test_interfaces.py
already uses.

These fakes are not, and must never be mistaken for, real
implementations: each returns a hand-built output with no actual
scanning/recommendation/risk logic behind it.
"""

from datetime import datetime, timezone

from src.analysis.intelligence.contracts.interfaces import (
    IAIDecisionLayer,
    IAlertSystem,
    IMarketScanner,
    IPortfolioAnalyzer,
    IRecommendationEngine,
    IRiskEngine,
)
from src.analysis.intelligence.contracts.types import (
    AlertEvent,
    AlertRule,
    AlertSeverity,
    DataState,
    DecisionContext,
    DecisionOutput,
    PortfolioAnalysisResult,
    PortfolioPosition,
    RecommendationOutput,
    RecommendationVerdict,
    RiskAssessment,
    RiskLevel,
    ScanCriteria,
    ScanMatch,
    TimeHorizon,
)
from src.market_data.models import RecommendationInput

_NOW = datetime.now(timezone.utc)


class _FakeMarketScanner:
    def scan(self, criteria: ScanCriteria):
        return (ScanMatch(symbol="1010", matched_at=_NOW, reasons=("test",), data_state=DataState.LIVE),)


class _FakeRecommendationEngine:
    def recommend(self, input_data: RecommendationInput) -> RecommendationOutput:
        return RecommendationOutput(
            symbol=input_data.symbol,
            verdict=RecommendationVerdict.WATCH,
            confidence=0.5,
            reasons=("test",),
            risks=("test",),
            time_horizon=TimeHorizon.MEDIUM_TERM,
            support_levels=(),
            resistance_levels=(),
            initial_targets=(),
            data_state=DataState.LIVE,
            as_of=_NOW,
        )


class _FakePortfolioAnalyzer:
    def analyze(self, positions):
        return PortfolioAnalysisResult(
            positions=positions, total_value=0.0, concentration_warnings=(),
            risk_level=RiskLevel.LOW, as_of=_NOW,
        )


class _FakeRiskEngine:
    def assess(self, symbol_or_positions) -> RiskAssessment:
        symbol = symbol_or_positions if isinstance(symbol_or_positions, str) else None
        return RiskAssessment(symbol=symbol, risk_level=RiskLevel.LOW, factors=(), as_of=_NOW)


class _FakeAlertSystem:
    def __init__(self):
        self._rules = []

    def register_rule(self, rule: AlertRule) -> None:
        self._rules.append(rule)

    def evaluate(self):
        return tuple(
            AlertEvent(
                rule_id=r.rule_id, symbol=r.symbol, severity=r.severity,
                message="test", triggered_at=_NOW, data_state=DataState.LIVE,
            )
            for r in self._rules
        )


class _FakeAIDecisionLayer:
    def decide(self, context: DecisionContext) -> DecisionOutput:
        return DecisionOutput(
            symbol=context.symbol, verdict=RecommendationVerdict.WAIT,
            confidence=0.0, reasoning=("test",), as_of=_NOW,
        )


def test_fake_market_scanner_satisfies_interface():
    scanner = _FakeMarketScanner()
    assert isinstance(scanner, IMarketScanner)
    assert scanner.scan(ScanCriteria(filters={}))[0].symbol == "1010"


def test_fake_recommendation_engine_satisfies_interface():
    engine = _FakeRecommendationEngine()
    assert isinstance(engine, IRecommendationEngine)
    result = engine.recommend(RecommendationInput(symbol="1010"))
    assert result.symbol == "1010"


def test_fake_portfolio_analyzer_satisfies_interface():
    analyzer = _FakePortfolioAnalyzer()
    assert isinstance(analyzer, IPortfolioAnalyzer)
    positions = (PortfolioPosition(symbol="1010", quantity=1, average_cost=1.0),)
    assert analyzer.analyze(positions).positions == positions


def test_fake_risk_engine_satisfies_interface():
    engine = _FakeRiskEngine()
    assert isinstance(engine, IRiskEngine)
    assert engine.assess("1010").symbol == "1010"


def test_fake_alert_system_satisfies_interface():
    system = _FakeAlertSystem()
    assert isinstance(system, IAlertSystem)
    system.register_rule(
        AlertRule(rule_id="r1", symbol="1010", condition={"field": "price"}, severity=AlertSeverity.INFO)
    )
    events = system.evaluate()
    assert len(events) == 1
    assert events[0].rule_id == "r1"


def test_fake_ai_decision_layer_satisfies_interface():
    layer = _FakeAIDecisionLayer()
    assert isinstance(layer, IAIDecisionLayer)
    context = DecisionContext(
        symbol="1010", recommendation=None, risk_assessment=None,
        portfolio_context=None, as_of=_NOW,
    )
    assert layer.decide(context).symbol == "1010"


def test_object_missing_required_method_does_not_satisfy_interface():
    class _NotAScanner:
        pass

    assert not isinstance(_NotAScanner(), IMarketScanner)
