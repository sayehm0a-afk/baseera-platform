"""Basirah Brain Stage 1 -- a structured, grounded AI-analyst synthesis
layer that sits above the existing, unmodified deterministic
DecisionEngineV2 pipeline. Shadow-only: nothing in this package can
affect a production recommendation, write to a consumer-facing table,
or trigger a real SAHMK/provider request. See this package's individual
modules for the full architecture, and the Stage 1 mandate's final
report for the isolation proof.
"""

from .provider import BasirahBrainProvider, BasirahBrainProviderOutcome
from .schemas import BasirahBrainDecisionV1, BasirahBrainInputV1, SCHEMA_VERSION
from .service import BasirahBrainService, ShadowAnalysisResult

__all__ = [
    "BasirahBrainProvider",
    "BasirahBrainProviderOutcome",
    "BasirahBrainInputV1",
    "BasirahBrainDecisionV1",
    "SCHEMA_VERSION",
    "BasirahBrainService",
    "ShadowAnalysisResult",
]
