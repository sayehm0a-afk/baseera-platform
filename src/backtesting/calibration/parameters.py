"""Translates a CalibrationConfig row's JSON `config` blob into the
actual dataclasses/contributor instances RecommendationEngine and
AIDecisionEngine already accept -- `RecommendationTuning`,
`AIDecisionTuning`, and a contributor list with overridden weights.

This is the one place that knows the JSON shape a calibration
candidate is expressed in:

    {
      "contributor_weights": {"technical": 0.30, "fundamental": 0.30, ...},
      "recommendation_tuning": {"buy_threshold": 58.0, ...},
      "ai_tuning": {"stop_atr_multiple": 1.2, ...}
    }

Every key is optional; an absent key means "use that engine's own
default for this parameter," so a minimal `{"recommendation_tuning":
{"buy_threshold": 58.0}}` candidate only touches the one parameter it
means to. An unrecognized key inside `recommendation_tuning`/
`ai_tuning` raises `TypeError` from the dataclass constructor itself
(no silent typo-swallowing); an unrecognized contributor name in
`contributor_weights` raises `KeyError` -- both deliberate, a
malformed calibration candidate should fail loudly at validation time,
not silently apply a subset of what was intended.
"""

from typing import Dict, List, Optional

from src.analysis.decision.ai_decision_engine import default_contributors
from src.analysis.decision.contributors.external_factor_contributors import (
    InsiderTransactionScoreContributor,
    MacroEconomicScoreContributor,
    NewsSentimentScoreContributor,
    SectorRotationScoreContributor,
)
from src.analysis.decision.contributors.momentum_contributor import MomentumScoreContributor
from src.analysis.decision.contributors.price_structure_contributor import PriceStructureScoreContributor
from src.analysis.decision.contributors.risk_contributor import RiskScoreContributor
from src.analysis.decision.contributors.value_area_contributor import ValueAreaScoreContributor
from src.analysis.decision.contributors.volume_contributor import VolumeScoreContributor
from src.analysis.decision.types import AIDecisionTuning
from src.analysis.recommendation.fundamental_contributor import FundamentalScoreContributor
from src.analysis.recommendation.technical_contributor import TechnicalScoreContributor
from src.analysis.recommendation.types import RecommendationTuning

_CONTRIBUTOR_CLASSES = {
    "technical": TechnicalScoreContributor,
    "fundamental": FundamentalScoreContributor,
    "momentum": MomentumScoreContributor,
    "volume": VolumeScoreContributor,
    "risk": RiskScoreContributor,
    "price_structure": PriceStructureScoreContributor,
    "value_area": ValueAreaScoreContributor,
    "news_sentiment": NewsSentimentScoreContributor,
    "macro": MacroEconomicScoreContributor,
    "insider_transactions": InsiderTransactionScoreContributor,
    "sector_rotation": SectorRotationScoreContributor,
}


def contributor_names() -> List[str]:
    """Every known contributor name, sorted -- the single-contributor
    equivalent of `build_contributors()`'s own key set, for a caller
    (e.g. statistical_calibration.py) that needs to iterate contributors
    one at a time rather than build the full eleven-contributor list."""
    return sorted(_CONTRIBUTOR_CLASSES)


def contributor_class(name: str):
    """Looks up a single contributor class by its `ScoreContributor.name`.
    Raises `KeyError` for an unknown name, matching `build_contributors()`'s
    own fail-loudly convention for a typo'd contributor name."""
    if name not in _CONTRIBUTOR_CLASSES:
        raise KeyError(f"Unknown contributor name {name!r}. Known contributors: {sorted(_CONTRIBUTOR_CLASSES)}")
    return _CONTRIBUTOR_CLASSES[name]


def build_contributors(contributor_weights: Optional[Dict[str, float]]) -> Optional[List]:
    """`None` if no override is given -- AIDecisionEngineStrategy then
    falls back to AIDecisionEngine's own default contributor set
    unchanged. Otherwise builds the full eleven-contributor list with
    the given weights substituted in (unnamed contributors keep their
    engine default weight)."""
    if not contributor_weights:
        return None

    defaults = {c.name: c.default_weight for c in default_contributors()}
    unknown = set(contributor_weights) - set(_CONTRIBUTOR_CLASSES)
    if unknown:
        raise KeyError(f"Unknown contributor name(s) in contributor_weights: {sorted(unknown)}")

    merged = {**defaults, **contributor_weights}
    return [_CONTRIBUTOR_CLASSES[name](weight=merged[name]) for name in _CONTRIBUTOR_CLASSES]


def build_recommendation_tuning(config: Dict) -> RecommendationTuning:
    return RecommendationTuning(**config.get("recommendation_tuning", {}))


def build_ai_tuning(config: Dict) -> AIDecisionTuning:
    return AIDecisionTuning(**config.get("ai_tuning", {}))


def build_strategy_kwargs(config: Dict, name: str) -> Dict:
    """The exact kwargs src.backtesting.baselines.AIDecisionEngineStrategy
    accepts -- what BacktestConfig.strategy_kwargs is set to when
    running a calibration candidate (or the active/default config)
    through BacktestingEngine."""
    return {
        "contributors": build_contributors(config.get("contributor_weights")),
        "recommendation_tuning": build_recommendation_tuning(config),
        "ai_tuning": build_ai_tuning(config),
        "name": name,
    }
