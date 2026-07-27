"""Simple, transparent comparison strategies for the Backtesting &
Calibration Engine -- Phase 6's "honest baselines," so a claim that
Basirah adds value is always measured against something a reasonable
person could implement in an afternoon.

Every strategy here (including the real AIDecisionEngine-backed one)
implements the same `Strategy` protocol so `BacktestingEngine` can run
any of them identically: build an `AsOfDataset` (data_access.py,
already anti-look-ahead-safe), pass it to `strategy.evaluate()`, get
back one `StrategyCall`. Nothing here recomputes an indicator or a
ratio -- every rule reads values `TechnicalAnalysisEngine`/
`FundamentalAnalysisEngine` already computed.

"Equal-weight market baseline" (Phase 6) is deliberately not a
separate strategy class: with no ingested TASI/market-index history
(see the architecture audit), the honest equal-weight market baseline
*is* running BuyAndHoldStrategy across every symbol in a run's universe
and aggregating results equally -- exactly what BacktestingEngine
already does for any strategy run against multiple symbols. A second,
parallel implementation would just be this same thing under a
different name.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Protocol, runtime_checkable

from src.analysis.decision.ai_decision_engine import AIDecisionEngine, default_contributors
from src.analysis.decision.types import AIDecisionTuning
from src.analysis.recommendation.fundamental_contributor import FundamentalScoreContributor
from src.analysis.recommendation.recommendation_engine import RecommendationEngine
from src.analysis.recommendation.technical_contributor import TechnicalScoreContributor
from src.analysis.recommendation.types import RecommendationTuning
from src.backtesting.data_access import AsOfDataset


@dataclass(frozen=True)
class StrategyCall:
    """One strategy's opinion for one symbol, one evaluation date --
    the common shape BacktestingEngine records into a
    RecommendationSnapshot regardless of which strategy produced it."""

    recommendation: str
    confidence: float
    total_score: float
    technical_score: Optional[float] = None
    fundamental_score: Optional[float] = None
    momentum_score: Optional[float] = None
    volume_score: Optional[float] = None
    risk_score: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    time_horizon: Optional[str] = None
    risk_level: Optional[str] = None
    position_size: Optional[str] = None
    reasons: List[str] = field(default_factory=list)
    signals: List[dict] = field(default_factory=list)
    contributor_breakdown: List[dict] = field(default_factory=list)


@runtime_checkable
class Strategy(Protocol):
    name: str

    def evaluate(self, dataset: AsOfDataset) -> Optional[StrategyCall]:
        """`None` means this strategy has nothing to say for this
        symbol/date (e.g. not enough history) -- BacktestingEngine
        records that as a skipped evaluation, never a forced HOLD."""
        ...


class BuyAndHoldStrategy:
    """Always BUY, full conviction, regardless of any input. Evaluated
    on the same rolling-forward-return basis as every other strategy
    (not a single buy-at-start/sell-at-end trade) -- see the module
    docstring for why this also stands in for the "equal-weight market
    baseline" when run across a run's full symbol universe."""

    name = "buy_and_hold"

    def evaluate(self, dataset: AsOfDataset) -> Optional[StrategyCall]:
        if dataset.context.latest_price is None:
            return None
        return StrategyCall(recommendation="BUY", confidence=100.0, total_score=100.0)


class SMACrossoverStrategy:
    """Classic single-moving-average rule: price above SMA(20) -> BUY,
    below -> SELL. Reuses TechnicalAnalysisEngine's already-computed
    sma_20 and the as-of latest close; computes nothing new."""

    name = "sma_crossover"

    def evaluate(self, dataset: AsOfDataset) -> Optional[StrategyCall]:
        result = dataset.context.technical_result
        price = dataset.context.latest_price
        if result is None or price is None:
            return None

        sma = result.indicators["sma_20"].latest()
        if sma is None:
            return None

        if price > sma:
            return StrategyCall(recommendation="BUY", confidence=60.0, total_score=65.0)
        if price < sma:
            return StrategyCall(recommendation="SELL", confidence=60.0, total_score=35.0)
        return StrategyCall(recommendation="HOLD", confidence=50.0, total_score=50.0)


class RSIOnlyStrategy:
    """Classic standalone RSI mean-reversion rule: RSI<30 -> BUY
    (oversold), RSI>70 -> SELL (overbought), else HOLD. Deliberately
    simpler than TechnicalScoreContributor's own RSI treatment (which
    blends momentum and reversal reads together) -- this is the
    "RSI-only" baseline a reasonable person would implement standalone,
    not a component reused for scoring anywhere else."""

    name = "rsi_only"

    def evaluate(self, dataset: AsOfDataset) -> Optional[StrategyCall]:
        result = dataset.context.technical_result
        if result is None:
            return None

        rsi = result.indicators["rsi_14"].latest()
        if rsi is None:
            return None

        if rsi <= 30:
            return StrategyCall(recommendation="BUY", confidence=55.0, total_score=62.0)
        if rsi >= 70:
            return StrategyCall(recommendation="SELL", confidence=55.0, total_score=38.0)
        return StrategyCall(recommendation="HOLD", confidence=40.0, total_score=50.0)


def _recommendation_result_to_call(result) -> StrategyCall:
    return StrategyCall(
        recommendation=result.recommendation.value,
        confidence=result.confidence,
        total_score=result.final_score,
        technical_score=result.technical_score,
        fundamental_score=result.fundamental_score,
        reasons=[result.explanation],
        signals=[
            {"name": s.name, "description": s.description, "direction": s.direction.value, "source": s.source, "impact": s.impact}
            for s in result.signals
        ],
        contributor_breakdown=[
            {"source": c.source, "score": c.score, "weight": c.weight, "confidence": c.confidence, "notes": c.notes}
            for c in result.contributions
        ],
    )


class TechnicalOnlyStrategy:
    """RecommendationEngine with only TechnicalScoreContributor --
    pure reuse of the existing engine, no new scoring logic."""

    name = "technical_only"

    def __init__(self):
        self._engine = RecommendationEngine(contributors=[TechnicalScoreContributor(weight=1.0)])

    def evaluate(self, dataset: AsOfDataset) -> Optional[StrategyCall]:
        if dataset.context.technical_result is None:
            return None
        return _recommendation_result_to_call(self._engine.generate(dataset.context))


class FundamentalOnlyStrategy:
    """RecommendationEngine with only FundamentalScoreContributor --
    pure reuse of the existing engine, no new scoring logic."""

    name = "fundamental_only"

    def __init__(self):
        self._engine = RecommendationEngine(contributors=[FundamentalScoreContributor(weight=1.0)])

    def evaluate(self, dataset: AsOfDataset) -> Optional[StrategyCall]:
        if dataset.context.fundamental_result is None:
            return None
        return _recommendation_result_to_call(self._engine.generate(dataset.context))


def _decision_to_call(decision) -> StrategyCall:
    return StrategyCall(
        recommendation=decision.recommendation.value,
        confidence=decision.confidence,
        total_score=decision.final_score,
        technical_score=next((b.points + 50.0 for b in decision.breakdown if b.category == "Technical Analysis" and b.available), None),
        fundamental_score=next((b.points + 50.0 for b in decision.breakdown if b.category == "Fundamental Analysis" and b.available), None),
        momentum_score=next((b.points + 50.0 for b in decision.breakdown if b.category == "Momentum" and b.available), None),
        volume_score=next((b.points + 50.0 for b in decision.breakdown if b.category == "Volume" and b.available), None),
        risk_score=next((b.points + 50.0 for b in decision.breakdown if b.category == "Risk" and b.available), None),
        target_price=decision.target_price,
        stop_loss=decision.stop_loss,
        time_horizon=decision.time_horizon.value,
        risk_level=decision.risk_level.value,
        position_size=decision.position_size.value,
        reasons=decision.reasons,
        signals=[
            {"name": s.name, "description": s.description, "direction": s.direction.value, "source": s.source, "impact": s.impact}
            for s in decision.signals
        ],
        contributor_breakdown=[
            {"category": b.category, "points": b.points, "weight": b.weight, "confidence": b.confidence, "available": b.available, "notes": b.notes}
            for b in decision.breakdown
        ],
    )


class AIDecisionEngineStrategy:
    """The real production strategy: AIDecisionEngine, the platform's
    actual top-layer output. Uncalibrated (default construction, no
    overrides) unless `recommendation_tuning`/`ai_tuning`/`contributors`
    are supplied -- CalibrationEngine builds a separate instance of
    this same class with a candidate configuration's overrides, so
    "uncalibrated" and "calibrated" runs are the identical code path,
    only the tuning differs."""

    def __init__(
        self,
        contributors=None,
        recommendation_tuning: Optional[RecommendationTuning] = None,
        ai_tuning: Optional[AIDecisionTuning] = None,
        name: str = "ai_decision_engine",
    ):
        self.name = name
        # AIDecisionEngine's default contributor set (nine modules) is
        # not RecommendationEngine's own default (two modules) -- an
        # explicit contributor list is only built here when the caller
        # actually wants to override it or the tuning, so an
        # uncalibrated AIDecisionEngineStrategy() is bit-for-bit the
        # same as a bare `AIDecisionEngine()`.
        if contributors is None and recommendation_tuning is None:
            recommendation_engine = None
        else:
            recommendation_engine = RecommendationEngine(
                contributors=contributors if contributors is not None else default_contributors(),
                tuning=recommendation_tuning,
            )
        self._engine = AIDecisionEngine(recommendation_engine=recommendation_engine, tuning=ai_tuning)

    def evaluate(self, dataset: AsOfDataset) -> Optional[StrategyCall]:
        if not dataset.has_any_input:
            return None
        return _decision_to_call(self._engine.decide(dataset.context))


def uncalibrated_ai_decision_engine_strategy() -> AIDecisionEngineStrategy:
    """The exact production default -- no calibration overrides at
    all. This is the "uncalibrated Basirah decision engine" baseline
    Phase 6 asks for, and also what production behaves like whenever
    no CalibrationConfig is active."""
    return AIDecisionEngineStrategy(name="uncalibrated_ai_decision_engine")


DEFAULT_STRATEGIES = {
    "ai_decision_engine": AIDecisionEngineStrategy,
    "uncalibrated_ai_decision_engine": uncalibrated_ai_decision_engine_strategy,
    "buy_and_hold": BuyAndHoldStrategy,
    "sma_crossover": SMACrossoverStrategy,
    "rsi_only": RSIOnlyStrategy,
    "technical_only": TechnicalOnlyStrategy,
    "fundamental_only": FundamentalOnlyStrategy,
}


def build_strategy(strategy_name: str, **kwargs) -> Strategy:
    """Looks up a strategy by name (the same names BacktestRun.strategy
    stores) and constructs it -- the one place BacktestingEngine and
    the REST layer need to know the full registry. `strategy_name`
    (not `name`) so it can never collide with a `name=` kwarg meant
    for the strategy's own constructor (AIDecisionEngineStrategy takes
    one, to label a calibration candidate/baseline run distinctly)."""
    if strategy_name not in DEFAULT_STRATEGIES:
        raise ValueError(f"Unknown strategy {strategy_name!r}. Known strategies: {sorted(DEFAULT_STRATEGIES)}")
    factory = DEFAULT_STRATEGIES[strategy_name]
    return factory(**kwargs) if kwargs else factory()
