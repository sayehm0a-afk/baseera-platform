"""Response schemas for the four analysis endpoints
(src/api/routes/analysis.py). These wrap the already-existing
dataclasses -- they do not redesign them.

Two deliberately different levels of wrapping, chosen per what each
underlying `.value` actually holds (a real, disclosed data-shape
decision, not an inconsistency):

- Technical/Fundamental (`IndicatorSummary`/`RatioSummary`): a
  per-output `{name, category, latest}` view built from each
  `IndicatorOutput`/`RatioOutput`'s own `.name`/`.category`/`.latest()`
  -- exactly the three-property `AnalysisOutput` Protocol shape
  (src/analysis/core/contracts.py) every such object already
  satisfies. This deliberately avoids serializing `.value` directly:
  a technical indicator's `.value` can be a raw `pd.Series` (the full
  historical window computed for that indicator), which is not
  JSON-serializable as-is and is a much larger payload than a
  "current analysis" endpoint should return -- that data belongs to
  the separate `/market-data/{symbol}/ohlcv` endpoint, not duplicated
  here.
- Composite/Council (`CompositeFactorSchema`/`ExpertResultSchema`):
  full field-for-field wrapping, because neither `CompositeFactorOutput`
  nor `ExpertResult` carries a raw `pd.Series` (both `.value`/
  `.normalized_score` are already scalar), and because BEIF's entire
  design intent for `ExpertResult` -- confidence, evidence, warnings,
  limitations -- would be lost by collapsing it to a single number.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel


class IndicatorSummary(BaseModel):
    """Wraps one IndicatorOutput via its own .name/.category/.latest()."""

    name: str
    category: str
    latest: Any


class RatioSummary(BaseModel):
    """Wraps one RatioOutput via its own .name/.category/.latest()."""

    name: str
    category: str
    latest: Any


class TechnicalAnalysisResponse(BaseModel):
    symbol: str
    indicators: List[IndicatorSummary]


class FundamentalAnalysisResponse(BaseModel):
    symbol: str
    ratios: List[RatioSummary]


class CompositeFactorSchema(BaseModel):
    """Full field-for-field wrap of CompositeFactorOutput
    (src/analysis/composite/types.py) -- see module docstring."""

    name: str
    category: str
    value: Optional[float]
    completeness: str
    agreement: Optional[str]
    contributing_engines: List[str]
    explanation: Dict[str, Any]


class CompositeAnalysisResponse(BaseModel):
    symbol: str
    factors: List[CompositeFactorSchema]


class EvidenceItemSchema(BaseModel):
    """Full field-for-field wrap of EvidenceItem (src/analysis/experts/types.py)."""

    metric_name: str
    observed_value: Any
    rule_id: str
    contribution: float


class ExpertResultSchema(BaseModel):
    """Full field-for-field wrap of ExpertResult
    (src/analysis/experts/types.py) -- see module docstring for why
    this one is not collapsed to a single number."""

    expert_id: str
    expert_name: str
    council: str
    domain: str
    symbol: str
    as_of: datetime
    direction: str
    normalized_score: Optional[float]
    confidence: float
    completeness: str
    freshness: str
    evidence: Tuple[EvidenceItemSchema, ...]
    contributing_metrics: Tuple[str, ...]
    rule_ids: Tuple[str, ...]
    warnings: Tuple[str, ...]
    conflicts: Tuple[str, ...]
    limitations: Tuple[str, ...]
    version: str
    metadata: Dict[str, Any]


class CouncilAnalysisResponse(BaseModel):
    symbol: str
    council: str
    experts: List[ExpertResultSchema]
