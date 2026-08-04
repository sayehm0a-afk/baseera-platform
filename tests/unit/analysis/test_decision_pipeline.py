"""Unit tests for compute_investment_decision -- the single shared
call site introduced during the Phase 2 Foundation Cleanup so
/decision, /decision-v2, and /analyst-report (via AnalystEngine) all
invoke AIDecisionEngine through one function instead of three
independent call sites.
"""

from src.analysis.decision.ai_decision_engine import AIDecisionEngine
from src.analysis.decision_pipeline import compute_investment_decision
from src.analysis.recommendation.recommendation_engine import RecommendationEngine
from src.analysis.recommendation.types import AnalysisContext, ScoreContribution


class _FakeContributor:
    def __init__(self, name, score, weight=1.0, confidence=100.0):
        self.name = name
        self.default_weight = weight
        self._score = score
        self._confidence = confidence

    def contribute(self, context: AnalysisContext) -> ScoreContribution:
        return ScoreContribution(
            source=self.name, score=self._score, weight=self.default_weight, confidence=self._confidence
        )


def _context():
    return AnalysisContext(symbol="2222", latest_price=100.0)


def test_compute_investment_decision_defaults_to_a_fresh_ai_decision_engine():
    context = _context()

    decision = compute_investment_decision(context)

    assert decision.symbol == "2222"


def test_compute_investment_decision_reuses_a_provided_engine_instance():
    contributors = [_FakeContributor("fake", score=80.0)]
    engine = AIDecisionEngine(recommendation_engine=RecommendationEngine(contributors=contributors))

    decision = compute_investment_decision(_context(), decision_engine=engine)

    assert decision.symbol == "2222"


def test_compute_investment_decision_forwards_requesting_user_id(monkeypatch):
    captured = {}

    class _RecordingEngine(AIDecisionEngine):
        def decide(self, context, requesting_user_id=None):
            captured["requesting_user_id"] = requesting_user_id
            return super().decide(context, requesting_user_id=requesting_user_id)

    compute_investment_decision(_context(), decision_engine=_RecordingEngine(), requesting_user_id=42)

    assert captured["requesting_user_id"] == 42


def test_compute_investment_decision_omits_requesting_user_id_by_default():
    captured = {}

    class _RecordingEngine(AIDecisionEngine):
        def decide(self, context, requesting_user_id=None):
            captured["requesting_user_id"] = requesting_user_id
            return super().decide(context, requesting_user_id=requesting_user_id)

    compute_investment_decision(_context(), decision_engine=_RecordingEngine())

    assert captured["requesting_user_id"] is None
