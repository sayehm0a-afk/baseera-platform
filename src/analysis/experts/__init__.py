"""Basirah Expert Intelligence Framework (BEIF): expert-level
interpretation over already-computed engine results (Technical,
Fundamental, and any future engine satisfying
src.analysis.core.contracts).

An expert never reads raw OHLCV data or raw fundamental facts, and
never recomputes an indicator or ratio itself -- it only reads
already-computed IndicatorOutput/RatioOutput/CompositeFactorOutput
values via an EngineResultEnvelope, exactly as
CompositeIntelligenceEngine already does one layer below. Experts are
grouped into councils (src.analysis.experts.types.Council); a
CouncilEngine runs one council's experts and produces one
CouncilResult, which itself satisfies AnalysisEngineResult exactly
like CompositeResult does, so a future Signal Engine can consume a
council's output identically to how Composite consumes Technical or
Fundamental today.
"""
