"""The cross-engine analysis contract.

Every analysis engine Basirah has today (TechnicalAnalysisEngine, M2.2)
or will ever have (FundamentalAnalysisEngine and beyond -- News
Intelligence, Market Intelligence, Sector Intelligence, Macro Analysis,
Smart Money/ICT, Wyckoff, ...) depends only on this package for its
shared output shape. This package depends on none of them. That keeps
every engine free to evolve independently while still being uniformly
consumable by a future Composite Analysis Engine, Signal Engine,
Confidence Scoring layer, Explainable AI layer, AI Decision Layer, or
Multi-Agent Orchestrator -- none of which exist yet and none of which
this package needs to know about in advance.
"""
