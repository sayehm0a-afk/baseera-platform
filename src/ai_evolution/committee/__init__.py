"""AI Multi-Agent Investment Committee -- eight independent analyst
agents that each produce a structured verdict on the same live
Decision Engine V2 result, followed by a weighted-vote Consensus
Engine. Distinct from `src.ai_evolution.agents` (the E7 panel, wired
to the older `RecommendationSnapshot`/scheduled-scan pipeline): this
package is wired into the live `/decision-v2` route and
`DecisionV2Snapshot`, per the explicit requirement that the committee
integrate into the existing Decision Intelligence Engine.
"""
