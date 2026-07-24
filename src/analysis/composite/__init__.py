"""Composite Intelligence Engine: fuses already-computed results from
independent analysis engines (Technical, Fundamental, and any future
engine satisfying src.analysis.core.contracts) into one structured,
explainable view.

Deliberately scores cross-engine *agreement, context, and data
quality* -- never the stock itself. Producing a single trading
score/decision is explicitly the job of a later, not-yet-built Signal
Engine / Confidence Scoring / AI Decision Layer; this package only
prepares the extension point those will consume.

Pure computation only -- no I/O, no database, no import of any
concrete engine class (TechnicalAnalysisEngine, FundamentalAnalysisEngine)
in this package's core logic. Everything here depends only on
src.analysis.core's structural AnalysisOutput/AnalysisEngineResult
contract.
"""
